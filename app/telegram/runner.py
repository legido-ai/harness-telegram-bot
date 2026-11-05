"""Per-conversation queues and the run lifecycle.

One worker per ``(chat, topic)`` keeps two humans in one room in arrival order
while other conversations keep flowing (contract T4, FR-017).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.opencode.client import OpenCodeClient
from app.opencode.errors import Busy, OpenCodeError, SessionGone, Unavailable
from app.opencode.events import (
    EXECUTION_DONE,
    FORM_CREATED,
    PERMISSION_ASKED,
    Event,
    EventBus,
)
from app.store import Store
from app.telegram.dashboard import dashboard_text
from app.telegram.footer import RunStats, format_cost, format_footer, format_tokens
from app.telegram.identity import attribution_prefix, build_prompt
from app.telegram.keyboards import context_label, main_menu
from app.telegram.messenger import Messenger
from app.telegram.streaming import StreamEditor
from app.telegram.trigger import Trigger
from app.telegram.types import Inbound

log = logging.getLogger("bot.runner")

InteractionHook = Callable[[str, Event, "RunState"], Awaitable[None]]


@dataclass(slots=True)
class Job:
    message: Inbound
    trigger: Trigger
    files: list[dict[str, str]] | None = None
    turn_id: int = 0


@dataclass(slots=True)
class RunState:
    message: Inbound
    conversation_key: tuple[int, int]
    session_id: str
    turn_id: int


class Runner:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        client: OpenCodeClient,
        bus: EventBus,
        messenger: Messenger | None = None,
        on_interaction: InteractionHook | None = None,
        run_timeout: float = 900.0,
    ) -> None:
        self._settings = settings
        self._store = store
        self._client = client
        self._bus = bus
        self.messenger: Messenger | None = messenger
        self._on_interaction = on_interaction
        self._run_timeout = run_timeout
        self._queues: dict[tuple[int, int], asyncio.Queue[Job]] = {}
        self._workers: dict[tuple[int, int], asyncio.Task[None]] = {}
        self._active_session: dict[tuple[int, int], str] = {}
        # Chats where pinning is refused (plain member, no rights): stop asking.
        self._pin_denied: set[tuple[int, int]] = set()
        self._started = False

    # -- lifecycle -------------------------------------------------------

    def set_messenger(self, messenger: Messenger) -> None:
        self.messenger = messenger

    def set_interaction_hook(self, hook: InteractionHook) -> None:
        self._on_interaction = hook

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        for task in self._workers.values():
            task.cancel()
        self._workers.clear()

    def queue_depth(self, key: tuple[int, int]) -> int:
        queue = self._queues.get(key)
        return queue.qsize() if queue else 0

    @property
    def active_sessions(self) -> dict[tuple[int, int], str]:
        return dict(self._active_session)

    # -- submission ------------------------------------------------------

    async def submit(self, job: Job) -> None:
        key = job.message.key
        conversation = self._store.touch_conversation(
            job.message.chat_id, job.message.thread_id, job.message.chat_type, job.message.chat_title
        )
        session_id = conversation.active_session_id
        turn_id = self._store.record_turn(
            chat_id=job.message.chat_id,
            thread_id=job.message.thread_id,
            session_id=session_id,
            user_id=job.message.user_id,
            update_id=job.message.update_id,
            trigger=job.trigger.kind,
            quote_of=job.message.quote.message_id if job.message.quote else None,
        )
        if turn_id is None:
            if self.messenger and job.message.callback_id:
                await self.messenger.answer_callback(job.message.callback_id, None)
            return
        job.turn_id = turn_id

        queue = self._queues.setdefault(key, asyncio.Queue())
        await queue.put(job)
        worker = self._workers.get(key)
        if worker is None or worker.done():
            self._workers[key] = asyncio.create_task(self._drain(key), name=f"runner:{key}")

    async def _drain(self, key: tuple[int, int]) -> None:
        queue = self._queues[key]
        while True:
            job = await queue.get()
            try:
                await self._run(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("run failed", extra={"chat_id": key[0], "thread_id": key[1]})
            finally:
                queue.task_done()

    # -- session binding -------------------------------------------------

    async def ensure_session(self, message: Inbound) -> tuple[str, bool]:
        conversation = self._store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        if conversation.active_session_id:
            return conversation.active_session_id, False
        return await self.new_session(message, message.user_id)

    async def new_session(self, message: Inbound, bound_by: int) -> tuple[str, bool]:
        conversation = self._store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        title = (message.chat_title or message.display_name or "conversation")[:60]
        session_id = await self._client.create_session(
            title=title, agent=conversation.agent, model=conversation.model
        )
        self._store.bind_session(
            message.chat_id, message.thread_id, session_id, title, bound_by=bound_by
        )
        return session_id, True

    # -- one run ---------------------------------------------------------

    async def _run(self, job: Job) -> None:
        if self.messenger is None:
            log.error("runner has no messenger wired; dropping job")
            return
        message = job.message
        key = message.key
        conversation = self._store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        participants = self._store.roster()
        prompt = build_prompt(message, job.trigger, participants)

        session_id = conversation.active_session_id
        created = False
        if session_id:
            # A recreated agent server forgets its sessions while our binding
            # still points at them: verify before prompting, then heal silently.
            try:
                await self._client.session(session_id)
            except SessionGone:
                self._store.clear_session(message.chat_id, message.thread_id)
                session_id = None
            except OpenCodeError:
                pass
        if not session_id:
            session_id, created = await self.new_session(message, message.user_id)

        turn_id = job.turn_id
        if turn_id:
            self._store.attach_turn_session(turn_id, session_id)
            self._store.start_turn(turn_id)
        self._active_session[key] = session_id

        state = RunState(
            message=message,
            conversation_key=key,
            session_id=session_id,
            turn_id=turn_id,
        )

        editor = StreamEditor(
            self.messenger.send_text,
            self.messenger.edit_text,
            message.chat_id,
            thread_id=message.thread_id,
            reply_to=message.message_id if message.is_private else None,
            prefix=attribution_prefix(message, len(participants)),
            markdown=True,
        )

        status = "succeeded"
        error_kind: str | None = None
        stats: RunStats | None = None
        started_at = time.monotonic()

        # Set the indicator before the request goes out: waiting for the loop
        # to be scheduled lets a fast model answer first, and then nothing is
        # ever visible.
        if self.messenger is not None:
            await self.messenger.send_typing(message.chat_id, message.thread_id)

        typing_stop = asyncio.Event()
        typing_task = asyncio.create_task(
            self._typing_loop(message, editor, typing_stop), name=f"typing:{key}"
        )

        try:
            await editor.start()
            events = self._bus.subscribe(session_id)
            try:
                await self._client.prompt(
                    session_id,
                    prompt,
                    files=job.files,
                    metadata={
                        "telegram": {
                            "chat_id": message.chat_id,
                            "thread_id": message.thread_id,
                            "user_id": message.user_id,
                            "update_id": message.update_id,
                        }
                    },
                )
                await self._consume(events, editor, state)
            finally:
                self._bus.unsubscribe(session_id)

            stats = await self._run_stats(
                session_id,
                created=created,
                seconds=time.monotonic() - started_at,
                model_hint=conversation.model,
            )
            if not editor.text.strip():
                # No text at all: either the agent failed or it produced silence.
                failure = await self._last_error(session_id)
                editor.append(failure or "The agent finished without producing an answer.")
                status = "failed" if failure else status
                error_kind = error_kind or ("agent_error" if failure else "empty_answer")
            await editor.finish()
            await self._sign_off(message, stats)
            await self._refresh_dashboard(message, stats, status)
        except SessionGone:
            self._store.clear_session(message.chat_id, message.thread_id)
            status, error_kind = "failed", "session_gone"
            await editor.finish(
                "This session no longer exists on the server. Send the message again to start a new one."
            )
        except Busy:
            status, error_kind = "failed", "busy"
            await editor.finish("The agent is still working on the previous request in this session.")
        except Unavailable as exc:
            status, error_kind = "failed", "unavailable"
            log.warning("agent server unavailable: %s", type(exc).__name__)
            await editor.finish("The agent server is unreachable right now. Nothing was lost; retry in a moment.")
        except OpenCodeError:
            status, error_kind = "failed", "open_code_error"
            await editor.finish("The agent server rejected that request.")
        finally:
            typing_stop.set()
            typing_task.cancel()
            if turn_id:
                self._store.finish_turn(
                    turn_id,
                    status,
                    error_kind=error_kind,
                    cost_usd=stats.cost_usd if stats else None,
                    tokens=stats.used_tokens if stats else None,
                )
            self._active_session.pop(key, None)

    async def _typing_loop(
        self, message: Inbound, editor: StreamEditor, stop: asyncio.Event
    ) -> None:
        """Show 'typing…' while the agent thinks, until the first text lands."""

        while not stop.is_set():
            if editor.message_ids:
                return
            if self.messenger is not None:
                await self.messenger.send_typing(message.chat_id, message.thread_id)
            try:
                await asyncio.wait_for(stop.wait(), timeout=4.0)
            except TimeoutError:
                continue

    async def _consume(
        self, events: asyncio.Queue[Event], editor: StreamEditor, state: RunState
    ) -> None:
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=self._run_timeout)
            except TimeoutError:
                log.warning("run timed out", extra={"session_id": state.session_id})
                editor.append("\n\n[timed out waiting for the agent]")
                return

            if (delta := event.text_delta) is not None:
                editor.append(delta)
                await editor.flush()
                continue
            if event.kind in (PERMISSION_ASKED, FORM_CREATED) and self._on_interaction is not None:
                await self._on_interaction(event.kind, event, state)
                continue
            if event.kind in EXECUTION_DONE:
                if event.kind != "session.idle":
                    text = event.text
                    if text and not editor.text.strip():
                        editor.append(text)
                return

    async def _last_error(self, session_id: str) -> str | None:
        try:
            usage = await self._client.context_usage(session_id)
        except OpenCodeError:
            return None
        error = usage.get("error")
        return f"⚠️ {error}" if isinstance(error, str) and error else None

    async def _sign_off(self, message: Inbound, stats: RunStats) -> None:
        """Close the run with the one message that can also carry the keyboard.

        Telegram refuses to edit a message that holds a reply keyboard and
        refuses to attach one on edit, so a fresh message is the only way the
        context button can show current numbers.
        """

        if self.messenger is None:
            return
        footer = format_footer(stats).lstrip("— ").strip()
        text = f"✅ I'm done · {footer}" if footer else "✅ I'm done"
        model = (
            f"{stats.provider}/{stats.model}" if stats.provider and stats.model else None
        )
        await self.messenger.send_text(
            message.chat_id,
            text,
            thread_id=message.thread_id,
            keyboard=self._keyboard_for(stats, model),
        )

    async def _refresh_dashboard(
        self, message: Inbound, stats: RunStats, status: str = "idle"
    ) -> int | None:
        """Keep the pinned card current: one message per conversation, edited."""

        if self.messenger is None:
            return
        text = dashboard_text(
            title=message.chat_title or message.display_name,
            stats=stats,
            queue_depth=self.queue_depth(message.key),
            last_user=message.display_name,
            status=status,
        )
        existing = self._store.pinned_message_id(message.chat_id, message.thread_id)
        if existing:
            try:
                await self.messenger.edit_text(message.chat_id, existing, text)
                return existing
            except Exception as exc:  # deleted message, revoked rights: start over
                log.warning("dashboard edit failed (%s); recreating", type(exc).__name__)
        message_id = await self.messenger.send_text(
            message.chat_id, text, thread_id=message.thread_id
        )
        if existing and existing != message_id:
            await self.messenger.unpin(message.chat_id, existing)
            await self.messenger.delete_message(message.chat_id, existing)
        self._store.set_pinned_message_id(message.chat_id, message.thread_id, message_id)
        if message.key not in self._pin_denied:
            pinned = await self.messenger.pin(message.chat_id, message_id)
            if not pinned:
                self._pin_denied.add(message.key)
                log.info(
                    "dashboard will stay a normal message in this chat (no pin rights)",
                    extra={"chat_id": message.chat_id},
                )
        return message_id

    @staticmethod
    def _keyboard_for(stats: RunStats | None, model: str | None = None) -> Any:
        return main_menu(
            context_label(
                stats.used_tokens if stats else None,
                stats.limit_tokens if stats else None,
            ),
            model,
        )

    def _model_label(self, message: Inbound) -> str | None:
        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        model = conversation.model if conversation else None
        if model:
            return f"{model['providerID']}/{model['modelID']}"
        return None

    async def refresh_dashboard(self, message: Inbound) -> None:
        """Redraw the pinned card for the current binding (after /new, /switch)."""

        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        session_id = conversation.active_session_id if conversation else None
        stats = None
        if session_id:
            stats = await self._run_stats(
                session_id, created=False, seconds=None, model_hint=conversation.model
            )
        await self._refresh_dashboard(message, stats or RunStats(), "idle")

    async def keyboard(self, message: Inbound) -> Any:
        """Keyboard carrying the current usage, for on-demand commands."""

        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        session_id = conversation.active_session_id if conversation else None
        stats = None
        if session_id:
            stats = await self._run_stats(
                session_id, created=False, seconds=None, model_hint=conversation.model
            )
        return self._keyboard_for(stats, self._model_label(message))

    async def context_line(self, message: Inbound) -> str:
        """One line for the chat, mirroring the status bar of the TUI."""

        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        session_id = conversation.active_session_id if conversation else None

        stats: RunStats | None = None
        if session_id:
            stats = await self._run_stats(
                session_id,
                created=False,
                seconds=None,
                model_hint=conversation.model if conversation else None,
            )

        provider = stats.provider if stats else None
        model = stats.model if stats else None
        used = (stats.used_tokens if stats else None) or 0
        limit = stats.limit_tokens if stats else None
        cost = stats.cost_usd if stats else None

        # An empty session has no model and no usage yet. Show what would be
        # used, at 0 of its window, instead of "server default" with no numbers.
        if not model:
            try:
                default = await self._client.default_model()
            except OpenCodeError:
                default = {}
            provider = provider or default.get("providerID")
            model = model or default.get("modelID")
        if limit is None:
            try:
                limit = await self._client.context_limit(provider, model)
            except OpenCodeError:
                limit = None

        parts = [model or "server default"]
        if limit:
            parts.append(f"{format_tokens(used)}/{format_tokens(limit)} ({round(used / limit * 100)}%)")
        elif used:
            parts.append(f"{format_tokens(used)} tokens")
        if cost:
            parts.append(format_cost(cost))
        parts.append(f"queued {self.queue_depth(message.key)}")
        return " · ".join(parts)

    async def _run_stats(
        self,
        session_id: str,
        *,
        created: bool,
        seconds: float,
        model_hint: dict[str, str] | None = None,
    ) -> RunStats:
        """Collect what the footer shows, degrading quietly when the server is shy."""

        info: dict[str, object] = {}
        try:
            info = await self._client.session(session_id)
        except OpenCodeError:
            log.debug("session info unavailable for footer")

        usage: dict[str, object] = {}
        try:
            usage = await self._client.context_usage(session_id)
        except OpenCodeError:
            log.debug("context usage unavailable for footer")

        used = usage.get("used_tokens") if isinstance(usage.get("used_tokens"), int) else None

        model_ref = info.get("model") if isinstance(info.get("model"), dict) else {}
        provider = (
            usage.get("provider")
            or model_ref.get("providerID")
            or (model_hint or {}).get("providerID")
        )
        model_id = (
            usage.get("model")
            or model_ref.get("modelID")
            or model_ref.get("id")
            or (model_hint or {}).get("modelID")
        )

        if not model_id:
            # Sessions created without an explicit model do not record one, so
            # ask the server which model it would use and show that.
            try:
                default = await self._client.default_model()
            except OpenCodeError:
                default = {}
            provider = provider or default.get("providerID")
            model_id = model_id or default.get("modelID") or default.get("id")

        limit = None
        try:
            limit = await self._client.context_limit(provider, model_id)
        except OpenCodeError:
            log.debug("context limit unavailable for footer")

        cost = info.get("cost")

        return RunStats(
            provider=provider,
            model=model_id,
            used_tokens=used,
            limit_tokens=limit,
            cost_usd=float(cost) if isinstance(cost, (int, float)) else None,
            seconds=seconds,
            session_id=session_id,
            created=created,
        )

    # -- abort -----------------------------------------------------------

    async def abort(self, message: Inbound) -> bool:
        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        session_id = (
            self._active_session.get(message.key)
            or (conversation.active_session_id if conversation else None)
        )
        if not session_id:
            return False
        interrupted = await self._client.interrupt(session_id)
        self._store.cancel_pending_for_session(session_id)
        return interrupted

    # -- helpers ---------------------------------------------------------

    def status_line(self, message: Inbound) -> str:
        conversation = self._store.get_conversation(message.chat_id, message.thread_id)
        session = conversation.active_session_id if conversation else None
        model = conversation.model if conversation else None
        model_text = f"{model['providerID']}/{model['modelID']}" if model else "server default"
        agent = conversation.agent if conversation else None
        depth = self.queue_depth(message.key)
        return (
            f"conversation: {message.chat_type} {message.chat_id}"
            + (f" / topic {message.thread_id}" if message.thread_id else "")
            + f"\nsession: {session or 'none yet'}"
            + f"\nmodel: {model_text}"
            + f"\nagent: {agent or 'server default'}"
            + f"\nqueued: {depth}"
        )


def file_refs(paths: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"type": "file", "path": path, "mime": mime} for path, mime in paths]
