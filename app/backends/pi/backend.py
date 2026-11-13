"""Pi adapter: one ``pi --mode rpc`` child per bound session file.

Pi has no HTTP server and no permission protocol. Sessions are files, the
catalogue comes from the agent itself, and approvals are declared unsupported
so the Telegram layer can say so instead of showing dead buttons.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.backends.base import RunOutcome
from app.backends.errors import (
    Busy,
    HarnessError,
    InvalidRequest,
    SessionGone,
    Unavailable,
    Unsupported,
)
from app.backends.pi import sessions as session_files
from app.backends.pi.rpc import PiProcess, PiRpc

log = logging.getLogger("bot.backend.pi")

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
CATALOGUE_TTL = 300.0


def _refused(message: str) -> InvalidRequest:
    error = InvalidRequest()
    error.user_message = message
    return error


class PiBackend:
    name = "pi"
    supports_agents = False
    supports_permissions = False
    supports_forms = False
    supports_images = True

    def __init__(
        self,
        rpc: PiRpc,
        *,
        session_dir: Path,
        run_timeout: float = 3600.0,
        idle_minutes: float = 30.0,
        idle_seconds: float | None = None,
    ) -> None:
        self._rpc = rpc
        self._session_dir = session_dir
        self._run_timeout = run_timeout
        self._idle_seconds = idle_seconds if idle_seconds is not None else idle_minutes * 60.0
        self._procs: dict[str, PiProcess] = {}
        self._catalogue: tuple[float, list[dict[str, Any]]] | None = None

    # -- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if shutil.which(self._rpc.binary) is None:
            raise Unavailable(f"the Pi binary ({self._rpc.binary}) is not on PATH")
        self._session_dir.mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        for node in list(self._procs.values()):
            await self._rpc.close(node)
        self._procs.clear()

    async def ping(self) -> bool:
        return shutil.which(self._rpc.binary) is not None

    async def background(self, stop: asyncio.Event, state: Any) -> None:
        """Reap idle children; their session files are the binding, not the process."""

        while not stop.is_set():
            state.agent_ok = await self.ping()
            await self._reap()
            try:
                await asyncio.wait_for(stop.wait(), timeout=60)
            except TimeoutError:
                continue

    async def _reap(self) -> None:
        now = time.monotonic()
        for ref, node in list(self._procs.items()):
            if node.lock.locked():
                continue
            if now - node.last_used < self._idle_seconds:
                continue
            await self._rpc.close(node)
            self._procs.pop(ref, None)
            log.info("pi session reaped", extra={"session": ref})

    # -- processes -------------------------------------------------------

    async def _proc(self, ref: str | None) -> PiProcess:
        if ref is not None:
            node = self._procs.get(ref)
            if node is not None and not node.dead:
                return node
            node = await self._rpc.spawn(Path(ref))
            self._procs[ref] = node
            return node
        node = await self._rpc.spawn(None)
        state = await self._rpc.command(node, {"type": "get_state"})
        path = state.get("sessionFile")
        if not isinstance(path, str) or not path:
            await self._rpc.close(node)
            raise Unavailable("Pi did not report a session file")
        self._procs[path] = node
        return node

    # -- sessions --------------------------------------------------------

    async def create_session(
        self,
        title: str | None,
        *,
        agent: str | None = None,
        model: dict[str, str] | None = None,
    ) -> str:
        node = await self._proc(None)
        state = await self._rpc.command(node, {"type": "get_state"})
        path = str(state.get("sessionFile") or "")
        if not path:
            raise Unavailable("Pi did not report a session file")
        if title:
            try:
                await self._rpc.command(node, {"type": "set_session_name", "name": title[:60]})
            except HarnessError:
                log.debug("pi refused the session name")
        if model and model.get("modelID"):
            try:
                await self._rpc.command(
                    node,
                    {
                        "type": "set_model",
                        "provider": model.get("providerID") or self._rpc.provider,
                        "modelId": model["modelID"],
                    },
                )
            except HarnessError:
                log.debug("pi refused the stored model")
        return path

    async def session_exists(self, ref: str) -> bool:
        return await asyncio.to_thread(Path(ref).exists)

    async def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        return [
            {"id": str(item.path), "title": item.label, "updated": int(item.updated)}
            for item in session_files.list_sessions(self._session_dir, limit=limit)
        ]

    async def describe(self, ref: str) -> str:
        return session_files.label_for(Path(ref))

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
    ) -> RunOutcome:
        node = await self._proc(ref)
        images = self._images(files)
        async with node.lock:
            while not node.events.empty():
                node.events.get_nowait()
            response = await self._rpc.command(
                node, {"type": "prompt", "message": prompt, "images": images}
            )
            if response.get("disposition") == "handled":
                return RunOutcome()
            error: str | None = None
            deadline = time.monotonic() + self._run_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._abort(node)
                    return RunOutcome(error="timed out waiting for the agent")
                try:
                    record = await asyncio.wait_for(node.events.get(), timeout=remaining)
                except TimeoutError:
                    await self._abort(node)
                    return RunOutcome(error="timed out waiting for the agent")
                kind = record.get("type")
                if kind == "message_update":
                    if on_delta is not None and (delta := self._delta(record)) is not None:
                        await on_delta(delta)
                    continue
                if kind == "message_end":
                    message = record.get("message")
                    if isinstance(message, dict) and message.get("role") == "assistant":
                        text = message.get("errorMessage")
                        if text:
                            error = str(text)
                    continue
                if kind == "agent_settled":
                    return RunOutcome(error=error)

    @staticmethod
    def _delta(record: dict[str, Any]) -> str | None:
        event = record.get("assistantMessageEvent")
        if not isinstance(event, dict) or event.get("type") != "text_delta":
            return None
        delta = event.get("delta")
        return delta if isinstance(delta, str) and delta else None

    async def _abort(self, node: PiProcess) -> None:
        try:
            await self._rpc.command(node, {"type": "abort"}, timeout=15)
        except HarnessError:
            await self._rpc.close(node)
            self._procs = {ref: item for ref, item in self._procs.items() if item is not node}

    def _images(self, files: Sequence[dict[str, str]] | None) -> list[dict[str, str]]:
        payload: list[dict[str, str]] = []
        for item in files or []:
            mime = str(item.get("mime") or "")
            path = Path(str(item.get("path") or ""))
            if mime not in IMAGE_MIMES:
                raise _refused(
                    "The Pi backend can only carry images. Send a screenshot or drop the file."
                )
            try:
                data = base64.b64encode(path.read_bytes()).decode()
            except OSError as exc:
                raise _refused("I could not read that attachment.") from exc
            payload.append({"type": "image", "data": data, "mimeType": mime})
        return payload

    async def interrupt(self, ref: str) -> bool:
        node = self._procs.get(ref)
        if node is None or node.dead:
            return False
        try:
            await self._rpc.command(node, {"type": "abort"}, timeout=15)
        except HarnessError:
            return False
        return True

    # -- catalogue -------------------------------------------------------

    async def models(self) -> list[dict[str, Any]]:
        return await self._catalogue_models()

    async def providers(self) -> list[dict[str, Any]]:
        seen: dict[str, str] = {}
        for model in await self._catalogue_models():
            provider = str(model.get("providerID") or "")
            if provider and provider not in seen:
                seen[provider] = provider
        return [{"id": key, "name": value} for key, value in seen.items()]

    async def agents(self) -> list[dict[str, Any]]:
        return []

    async def default_model(self) -> dict[str, Any]:
        return {"providerID": self._rpc.provider, "modelID": self._rpc.model}

    async def set_model(self, ref: str, provider: str, model: str) -> None:
        node = await self._proc(ref)
        await self._rpc.command(
            node, {"type": "set_model", "provider": provider, "modelId": model}
        )

    async def set_agent(self, ref: str, agent: str) -> None:
        raise Unsupported("Pi has no agent modes")

    async def _catalogue_models(self) -> list[dict[str, Any]]:
        if self._catalogue is not None and time.monotonic() - self._catalogue[0] < CATALOGUE_TTL:
            return self._catalogue[1]
        node = await self._rpc.spawn(None)
        try:
            data = await self._rpc.command(node, {"type": "get_available_models"})
        finally:
            await self._rpc.close(node)
        raw = data.get("models") if isinstance(data.get("models"), list) else []
        models: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id") or item.get("modelId")
            provider = item.get("provider") or self._rpc.provider
            if not model_id:
                continue
            window = item.get("contextWindow")
            models.append(
                {
                    "providerID": provider,
                    "modelID": str(model_id),
                    "name": str(item.get("name") or model_id),
                    "limit": {"context": int(window)} if isinstance(window, int) and window else {},
                }
            )
        self._catalogue = (time.monotonic(), models)
        return models

    # -- numbers ---------------------------------------------------------

    async def _stats(self, ref: str) -> dict[str, Any]:
        node = await self._proc(ref)
        node.last_used = time.monotonic()
        return await self._rpc.command(node, {"type": "get_session_stats"})

    async def session(self, ref: str) -> dict[str, Any]:
        try:
            stats = await self._stats(ref)
            state = await self._rpc.command(self._procs[ref], {"type": "get_state"})
        except HarnessError:
            return {}
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        return {
            "model": {
                "providerID": model.get("provider") or self._rpc.provider,
                "modelID": model.get("id") or self._rpc.model,
            },
            "cost": stats.get("cost"),
            "sessionId": stats.get("sessionId"),
        }

    async def context_usage(self, ref: str) -> dict[str, Any]:
        try:
            stats = await self._stats(ref)
            state = await self._rpc.command(self._procs[ref], {"type": "get_state"})
        except HarnessError:
            return {"used_tokens": None, "provider": None, "model": None, "error": None}
        usage = stats.get("contextUsage")
        used = usage.get("tokens") if isinstance(usage, dict) else None
        model = state.get("model") if isinstance(state.get("model"), dict) else {}
        return {
            "used_tokens": int(used) if isinstance(used, (int, float)) else None,
            "provider": model.get("provider"),
            "model": model.get("id"),
            "error": None,
        }

    async def context_limit(self, provider: str | None, model: str | None) -> int | None:
        if not model:
            return None
        for item in await self._catalogue_models():
            if str(item.get("modelID")) == model:
                limit = item.get("limit") if isinstance(item.get("limit"), dict) else {}
                value = limit.get("context")
                return int(value) if isinstance(value, int) else None
        return None

    async def generate(self, ref: str, prompt: str) -> str:
        raise Unsupported("Pi cannot generate transient text")

    async def reply_permission(self, ref: str, request_id: str, decision: str) -> None:
        raise Unsupported("Pi has no tool permissions")

    async def reply_form(self, ref: str, form_id: str, answer: dict[str, Any]) -> None:
        raise Unsupported("Pi has no agent forms")


__all__ = ["Busy", "PiBackend", "SessionGone"]
