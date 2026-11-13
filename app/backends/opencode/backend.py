"""OpenCode V2 adapter: HTTP + SSE behind the generic backend interface."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Any

from app.backends.base import FORM_CREATED, PERMISSION_ASKED, Interaction, RunOutcome
from app.backends.errors import Busy, HarnessError, SessionGone, Unavailable
from app.backends.opencode.client import PERMISSION_DECISIONS, OpenCodeClient
from app.backends.opencode.events import (
    EXECUTION_DONE,
    TEXT_DELTA,
    TOOL_ENDED,
    TOOL_STARTED,
    Event,
    EventBus,
    consume_events,
)

log = logging.getLogger("bot.backend.opencode")


class OpenCodeBackend:
    """The agent server owns the session; this adapter owns the transport."""

    name = "opencode"
    supports_agents = True
    supports_permissions = True
    supports_forms = True
    supports_images = True

    def __init__(
        self,
        client: OpenCodeClient,
        *,
        bus: EventBus | None = None,
        run_timeout: float = 900.0,
        transport: Any = None,
    ) -> None:
        self._client = client
        self._bus = bus if bus is not None else EventBus()
        self._run_timeout = run_timeout
        self._transport = transport

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        return None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ping(self) -> bool:
        try:
            await self._client.info()
            return True
        except HarnessError:
            return False

    async def background(self, stop: asyncio.Event, state: Any) -> None:
        """Keep the SSE stream open for the life of the process."""

        note = getattr(state, "note_sse", None)
        await consume_events(self._client, self._bus, stop, on_state=note)

    # -- sessions --------------------------------------------------------

    async def create_session(
        self,
        title: str | None,
        *,
        agent: str | None = None,
        model: dict[str, str] | None = None,
    ) -> str:
        return await self._client.create_session(title=title, agent=agent, model=model)

    async def session_exists(self, ref: str) -> bool:
        try:
            await self._client.session(ref)
            return True
        except SessionGone:
            return False

    async def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        return await self._client.list_sessions(limit=limit)

    async def describe(self, ref: str) -> str:
        return ref[-6:]

    # -- one turn --------------------------------------------------------

    async def run(
        self,
        ref: str,
        prompt: str,
        *,
        files: Sequence[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
        on_delta: Any = None,
        on_interaction: Any = None,
        on_activity: Any = None,
    ) -> RunOutcome:
        events = self._bus.subscribe(ref)
        streamed = False
        try:
            await self._client.prompt(ref, prompt, files=files, metadata=metadata)
            while True:
                try:
                    event = await asyncio.wait_for(events.get(), timeout=self._run_timeout)
                except TimeoutError:
                    log.warning("run timed out", extra={"session_id": ref})
                    return RunOutcome(text=None, error="timed out waiting for the agent")

                if event.kind == TEXT_DELTA and event.text_delta is not None:
                    streamed = True
                    if on_delta is not None:
                        await on_delta(event.text_delta)
                    continue

                if on_activity is not None and event.kind in TOOL_ENDED:
                    await on_activity(None)
                    continue

                if on_activity is not None and event.kind in TOOL_STARTED:
                    name = event.tool_name
                    if name is not None:
                        await on_activity(name)
                    continue

                if event.kind in (PERMISSION_ASKED, FORM_CREATED) and on_interaction is not None:
                    await on_interaction(
                        event.kind,
                        Interaction(kind=event.kind, session_id=event.session_id, data=event.data),
                    )
                    continue

                if event.kind in EXECUTION_DONE:
                    # A non-idle execution event may carry the whole answer when
                    # the server did not stream it.
                    text = event.text
                    return RunOutcome(text=None if streamed else text)
        finally:
            self._bus.unsubscribe(ref)

    async def interrupt(self, ref: str) -> bool:
        return await self._client.interrupt(ref)

    # -- catalogue -------------------------------------------------------

    async def models(self) -> list[dict[str, Any]]:
        return await self._client.models()

    async def providers(self) -> list[dict[str, Any]]:
        return await self._client.providers()

    async def agents(self) -> list[dict[str, Any]]:
        return await self._client.agents()

    async def default_model(self) -> dict[str, Any]:
        return await self._client.default_model()

    async def set_model(self, ref: str, provider: str, model: str) -> None:
        await self._client.set_model(ref, provider, model)

    async def set_agent(self, ref: str, agent: str) -> None:
        await self._client.set_agent(ref, agent)

    # -- numbers ---------------------------------------------------------

    async def session(self, ref: str) -> dict[str, Any]:
        return await self._client.session(ref)

    async def context_usage(self, ref: str) -> dict[str, Any]:
        return await self._client.context_usage(ref)

    async def context_limit(self, provider: str | None, model: str | None) -> int | None:
        return await self._client.context_limit(provider, model)

    async def generate(self, ref: str, prompt: str) -> str:
        return await self._client.generate(ref, prompt)

    # -- humans in the loop ----------------------------------------------

    async def reply_permission(self, ref: str, request_id: str, decision: str) -> None:
        if decision not in PERMISSION_DECISIONS:
            raise HarnessError("invalid permission decision")
        await self._client.reply_permission(ref, request_id, decision)

    async def reply_form(self, ref: str, form_id: str, answer: dict[str, Any]) -> None:
        await self._client.reply_form(ref, form_id, answer)


__all__ = ["Busy", "Event", "OpenCodeBackend", "Unavailable"]
