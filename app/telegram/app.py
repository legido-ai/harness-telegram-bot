"""Telegram wiring: intake, triggers, commands and callbacks.

Handlers are thin on purpose. Every decision that matters lives in a pure module
(``trigger``, ``identity``, ``streaming``) or in the runner, which keeps the
behaviour testable without a live bot.
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from app.backends.base import FORM_CREATED, PERMISSION_ASKED, Backend, Interaction
from app.backends.errors import HarnessError
from app.config import Settings
from app.health import HealthState
from app.speech.stt import SttClient, SttError
from app.store import TTS_MODES, SessionEntry, Store
from app.telegram import commands, keyboards, sessions, voice
from app.telegram.attachments import AttachmentError, collect
from app.telegram.auth import Authorizer
from app.telegram.convert import from_update
from app.telegram.messenger import Messenger
from app.telegram.ptb_messenger import TelegramMessenger
from app.telegram.runner import Job, Runner, RunState
from app.telegram.trigger import detect
from app.telegram.types import Inbound, Trigger

log = logging.getLogger("bot.app")


class BotApp:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        backend: Backend,
        runner: Runner,
        state: HealthState,
        messenger: Messenger | None = None,
        stt: SttClient | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.backend = backend
        self.runner = runner
        self.state = state
        self.stt = stt
        self.authorizer = Authorizer(settings, store)
        # Telegram caps callback_data at 64 bytes; a short token keeps menus
        # usable without embedding session ids and model names in every button.
        self._choices: dict[str, tuple[str, str, str, str]] = {}
        # What /sessions last showed to *this human* in this conversation.
        # Numbers are resolved against it, so "3" means the third row they read
        # (including after a search) and one member's listing never drives
        # another member's switch. Entries expire after an hour; ids and titles
        # still resolve afterwards.
        self._last_listing: dict[tuple[int, int, int], tuple[list[SessionEntry], float]] = {}
        self.messenger: Messenger | None = messenger
        self.bot_id = 0
        self.bot_username = ""

    # -- startup ---------------------------------------------------------

    async def on_startup(self, application: Application) -> None:
        me = await application.bot.get_me()
        self.bot_id = me.id
        self.bot_username = me.username or ""
        self.messenger = TelegramMessenger(application.bot)
        self.state.poller_alive = True
        log.info("bot identified", extra={"event": f"@{self.bot_username}"})

    def build(self) -> Application:
        application = (
            Application.builder()
            .token(self.settings.bot_token)
            # PTB's defaults (5 s read/connect, 1 s pool) are too short for
            # Telegram file downloads on a small box: voice notes and
            # documents failed with TimedOut. Keep polling responsive but let
            # getFile/downloads finish.
            .connect_timeout(20.0)
            .read_timeout(120.0)
            .write_timeout(120.0)
            .pool_timeout(10.0)
            .media_write_timeout(120.0)
            .post_init(self.on_startup)
            .concurrent_updates(True)
            .build()
        )
        # Registered first, so every delivered update is visible in the log even
        # when the intake path drops it.
        application.add_handler(TypeHandler(Update, self.on_any_update), group=-1)
        # Voice and audio are transcribed before they reach the normal prompt
        # path; register them first so the ALL handler never sees them as an
        # empty text request.
        application.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice)
        )
        application.add_handler(MessageHandler(filters.ALL, self.on_message))
        application.add_handler(CallbackQueryHandler(self.on_callback))
        application.add_error_handler(self.on_error)
        return application

    async def on_any_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        kind = next(
            (
                name
                for name in (
                    "message",
                    "edited_message",
                    "channel_post",
                    "callback_query",
                    "my_chat_member",
                    "chat_member",
                )
                if getattr(update, name, None) is not None
            ),
            "other",
        )
        chat = getattr(getattr(update, "effective_chat", None), "id", None)
        log.info(
            "update delivered",
            extra={"update_id": update.update_id, "chat_id": chat, "event": kind},
        )

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Never fail silently: log the cause and tell the chat something broke."""

        log.exception("handler failed", exc_info=context.error)
        message = from_update(update, self.bot_id) if hasattr(update, "update_id") else None
        if message is None or self.messenger is None:
            return
        try:
            await self.messenger.send_text(
                message.chat_id,
                "That command failed inside the bot. The error is logged; try again.",
                thread_id=message.thread_id,
            )
        except Exception:
            log.debug("could not report the failure to the chat")

    # -- intake ----------------------------------------------------------

    def _inbound(self, update: Update) -> Inbound | None:
        return from_update(update, self.bot_id)

    async def on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self._inbound(update)
        if message is None:
            return
        if message.is_bot:
            log.debug("ignoring message from a bot")
            return
        if message.voice_input:
            # Handled by on_voice, which must transcribe before submitting.
            return
        log.info(
            "update received",
            extra={
                "update_id": message.update_id,
                "chat_id": message.chat_id,
                "session_id": (
                    f"{message.chat_type}/text={len(message.text)}/entities="
                    + (",".join(entity.type for entity in message.entities) or "none")
                ),
            },
        )
        if not self.authorizer.allow(message):
            return
        if not self.store.mark_seen(message.update_id):
            log.debug("duplicate update ignored", extra={"update_id": message.update_id})
            return

        self.state.note_update()
        self.authorizer.register(message)

        # The persistent keyboard sends plain labels; treat them as commands.
        if (menu_command := keyboards.menu_command(message.text)) is not None:
            log.info(
                "keyboard button pressed",
                extra={"event": menu_command, "chat_id": message.chat_id},
            )
            await self._handle_command(message, menu_command)
            return

        conversation = self.store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        policy = conversation.trigger_policy or self.settings.trigger
        trigger = detect(
            message,
            bot_id=self.bot_id,
            bot_username=self.bot_username,
            policy=policy,
        )
        # Quoting the bot's own bookkeeping is not a request: the status card and
        # the sign-off line are the messages clients auto-reply to.
        if trigger is not None and trigger.kind == "reply" and message.quote is not None:
            dashboard_id = self.store.pinned_message_id(message.chat_id, message.thread_id)
            bookkeeping = (message.quote.text or "").strip() in ("✅ I'm done",)
            bookkeeping = bookkeeping or (dashboard_id and message.quote.message_id == dashboard_id)
            bookkeeping = bookkeeping or (message.quote.text or "").startswith("📊")
            # Only ignore it when the human did not address the bot explicitly:
            # an auto-reply plus a mention is still a request.
            mentioned = any(e.type in ("mention", "text_mention") for e in message.entities)
            if bookkeeping and not mentioned:
                return
        if trigger is None:
            return

        if trigger.kind == "command":
            await self._handle_command(message, trigger.text)
            return
        if trigger.kind == "empty":
            await self._reply(message, "Yes? Tell me what you need.")
            return

        files: list[dict[str, str]] = []
        try:
            files = await collect(context.bot, update.effective_message, self.settings)
        except AttachmentError as exc:
            await self._reply(message, str(exc))
            return

        await self.runner.submit(Job(message=message, trigger=trigger, files=files or None))

    async def on_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Transcribe a voice note, then run it through the normal prompt path."""

        message = self._inbound(update)
        if message is None or message.is_bot:
            return
        if not self.authorizer.allow(message):
            return
        if not self.store.mark_seen(message.update_id):
            log.debug("duplicate update ignored", extra={"update_id": message.update_id})
            return

        self.state.note_update()
        self.authorizer.register(message)
        log.info(
            "voice update received",
            extra={"update_id": message.update_id, "chat_id": message.chat_id},
        )

        conversation = self.store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        policy = conversation.trigger_policy or self.settings.trigger
        trigger = detect(
            message,
            bot_id=self.bot_id,
            bot_username=self.bot_username,
            policy=policy,
        )
        if trigger is None:
            # A caption-less voice note still counts as a request when the chat
            # is in "answer everything" mode; otherwise it is a private thought.
            if policy != "all" or message.is_private:
                return
            trigger = Trigger(kind="policy_all", text="", quote=message.quote)

        if trigger.kind == "command":
            await self._handle_command(message, trigger.text)
            return

        if self.stt is None or not self.stt.available:
            await self._reply(
                message,
                "🎤 Voice recognition is not configured.\n\n"
                "Set STT_API_URL and STT_API_KEY to enable it.",
            )
            return

        status_id = await self._reply(message, "🎤 Recognizing audio…")
        try:
            assert context.bot is not None
            audio, filename = await voice.download(
                context.bot, update.effective_message, self.settings
            )
            transcript = await self.stt.transcribe(audio, filename)
        except SttError as exc:
            await self._finish_transcription(message, status_id, f"🔴 Failed to recognize audio: {exc.user_message}")
            return
        except voice.VoiceError as exc:
            await self._finish_transcription(message, status_id, f"🔴 {exc.user_message}")
            return

        await self._finish_transcription(message, status_id, f"🎤 Recognized:\n{transcript}")

        recognized = replace(message, text=transcript, entities=(), voice_input=True)
        prompt_trigger = Trigger(kind=trigger.kind, text=transcript, quote=message.quote)
        note = self.settings.stt_note_prompt
        if note.lower() in ("false", "0"):
            note = ""
        await self.runner.submit(
            Job(message=recognized, trigger=prompt_trigger, prompt_note=note)
        )

    async def _finish_transcription(
        self, message: Inbound, status_id: int | None, text: str
    ) -> None:
        if status_id is None:
            await self._reply(message, text)
            return
        try:
            assert self.messenger is not None
            await self.messenger.edit_text(message.chat_id, status_id, text)
        except Exception:
            log.debug("could not edit the transcription status message")
            await self._reply(message, text)

    # -- commands --------------------------------------------------------

    async def _handle_command(self, message: Inbound, text: str) -> None:
        name, argument = commands.parse(text)
        handler = getattr(self, f"_cmd_{name}", None)
        if handler is None:
            await self._reply(message, "Unknown command. Try /help.")
            return
        await handler(message, argument)

    async def _reply(self, message: Inbound, text: str, keyboard: Any = None) -> int | None:
        if self.messenger is None:
            return None
        return await self.messenger.send_text(
            message.chat_id, text, thread_id=message.thread_id, keyboard=keyboard
        )

    async def _cmd_start(self, message: Inbound, argument: str) -> None:
        await self._reply(
            message,
            commands.help_text(self.bot_username),
            await self.runner.keyboard(message),
        )

    async def _cmd_help(self, message: Inbound, argument: str) -> None:
        await self._reply(
            message,
            commands.help_text(self.bot_username),
            await self.runner.keyboard(message),
        )

    async def _cmd_id(self, message: Inbound, argument: str) -> None:
        await self._reply(message, commands.id_text(message))

    async def _cmd_new(self, message: Inbound, argument: str) -> None:
        session_id, _ = await self.runner.new_session(message, message.user_id)
        await self._reply(
            message,
            f"New session: {session_id[-6:]}",
            await self.runner.keyboard(message),
        )
        await self.runner.refresh_dashboard(message)

    async def _cmd_context(self, message: Inbound, argument: str) -> None:
        await self._reply(
            message,
            await self.runner.context_line(message),
            await self.runner.keyboard(message),
        )

    async def _cmd_status(self, message: Inbound, argument: str) -> None:
        await self._reply(message, self.runner.status_line(message))

    async def _cmd_abort(self, message: Inbound, argument: str) -> None:
        try:
            stopped = await self.runner.abort(message)
        except HarnessError as exc:
            await self._reply(message, exc.user_message)
            return
        await self._reply(
            message, "Stopped." if stopped else "Nothing is running in this conversation."
        )

    async def _cmd_trigger(self, message: Inbound, argument: str) -> None:
        conversation = self.store.get_conversation(message.chat_id, message.thread_id)
        current = conversation.trigger_policy if conversation else self.settings.trigger
        if not argument:
            await self._reply(
                message,
                f"trigger policy here: {current}\nUse /trigger mention or /trigger all.",
            )
            return
        policy = argument.strip().lower()
        if policy not in ("mention", "all"):
            await self._reply(message, "Policy must be mention or all.")
            return
        if message.is_private:
            await self._reply(message, "Trigger policy only applies to groups.")
            return
        if not self.authorizer.is_admin(message):
            await self._reply(message, "Only the operator can change the trigger policy.")
            return
        self.store.set_trigger_policy(message.chat_id, message.thread_id, policy)
        await self._reply(message, f"trigger policy set to {policy}")

    async def _cmd_tts(self, message: Inbound, argument: str) -> None:
        conversation = self.store.touch_conversation(
            message.chat_id, message.thread_id, message.chat_type, message.chat_title
        )
        current = conversation.tts_mode if conversation else "off"
        mode = argument.strip().lower()
        if not mode:
            await self._reply(
                message,
                f"audio replies: {current}\nUse /tts off, /tts all or /tts auto.",
            )
            return
        if mode not in TTS_MODES:
            await self._reply(message, "Audio replies must be off, all or auto.")
            return
        if mode != "off" and not self.settings.tts_configured:
            await self._reply(
                message,
                "⚠️ Audio replies are unavailable. Set TTS_API_URL and TTS_API_KEY first.",
            )
            return
        self.store.set_tts_mode(message.chat_id, message.thread_id, mode)
        copy = {
            "off": "🔇 Audio replies disabled.",
            "all": "🔊 Audio replies enabled for all messages.",
            "auto": "🎤 Audio replies enabled for voice/audio messages only.",
        }
        await self._reply(message, copy[mode])

    async def _cmd_sessions(self, message: Inbound, argument: str) -> None:
        args = sessions.parse_args(argument)
        if args.search == "":
            await self._reply(message, "Usage: /sessions search <query>")
            return
        if args.target:
            await self._resume_target(message, args.target, all_chats=args.all_chats)
            return
        await self._show_sessions(message, args)

    async def _cmd_resume(self, message: Inbound, argument: str) -> None:
        await self._cmd_sessions(message, argument)

    async def _cmd_switch(self, message: Inbound, argument: str) -> None:
        await self._cmd_sessions(message, argument)

    async def _cmd_title(self, message: Inbound, argument: str) -> None:
        conversation = self.store.get_conversation(message.chat_id, message.thread_id)
        session_id = conversation.active_session_id if conversation else None
        if not session_id:
            await self._reply(
                message,
                "This conversation has no session yet. Send a message and one is created.",
            )
            return
        if not argument.strip():
            current = self.store.binding_title(message.chat_id, message.thread_id, session_id)
            await self._reply(
                message,
                f'current title: "{current}"' if current else "this session has no title yet.",
            )
            return
        title = sessions.clean_title(argument)
        if title is None:
            await self._reply(message, "The title cannot be empty.")
            return
        self.store.set_binding_title(message.chat_id, message.thread_id, session_id, title)
        await self._reply(message, f'Session titled "{title}".')

    async def _show_sessions(self, message: Inbound, args: sessions.Args) -> None:
        admin = self.authorizer.is_admin(message)
        cross_origin = args.all_chats and admin
        notice = None
        if args.all_chats and not admin:
            notice = "all (cross-chat listing) is admin-only; showing this chat's sessions."

        entries: list[SessionEntry]
        if cross_origin:
            entries = self.store.list_all_session_entries(limit=50, search=args.search)
            warnings: list[str] = []
            entries = await self._with_unassigned(entries, args.search, warnings)
            if warnings:
                notice = warnings[0]
        else:
            entries = self.store.list_session_entries(
                message.chat_id, message.thread_id, limit=10, search=args.search
            )

        shown = entries[: sessions.MAX_ROWS]
        if cross_origin:
            shown = [self._origin(entry) for entry in shown]
        self._remember_listing(message, shown)
        text = sessions.format_listing(
            shown, search=args.search, all_chats=cross_origin, notice=notice
        )
        keyboard = None
        if shown:
            rows = [
                (self._token("s", entry.session_id, "", ""), entry.title or "untitled")
                for entry in shown
            ]
            keyboard = keyboards.sessions_keyboard(
                message.chat_id, message.thread_id, rows
            )
        await self._reply(message, text, keyboard)

    @staticmethod
    def _origin(entry: SessionEntry) -> SessionEntry:
        """Label the origin of a bound session in the admin view."""

        if entry.unassigned:
            return entry
        if entry.chat_title:
            return entry
        return replace(entry, chat_title=f"chat {entry.chat_id}")

    def _remember_listing(self, message: Inbound, entries: list[SessionEntry]) -> None:
        key = (message.chat_id, message.thread_id, message.user_id)
        if len(self._last_listing) > 200:
            now = time.time()
            self._last_listing = {
                item: value for item, value in self._last_listing.items() if now - value[1] < 3600
            }
        self._last_listing[key] = (entries, time.time())

    def _remembered_listing(self, message: Inbound) -> list[SessionEntry] | None:
        key = (message.chat_id, message.thread_id, message.user_id)
        remembered = self._last_listing.get(key)
        if remembered is None:
            return None
        entries, stamp = remembered
        if time.time() - stamp > 3600:
            self._last_listing.pop(key, None)
            return None
        return entries

    async def _with_unassigned(
        self, entries: list[SessionEntry], search: str | None, notice: list[str]
    ) -> list[SessionEntry]:
        """Append harness sessions that no conversation is bound to (admin only)."""

        known = {entry.session_id for entry in self.store.list_all_session_entries(limit=500)}
        try:
            catalogue = await self.backend.list_sessions(limit=50)
        except HarnessError:
            notice.append("the harness catalogue is unavailable; showing bound sessions only.")
            return entries
        extra: list[SessionEntry] = []
        for item in catalogue:
            session_id = str(item.get("id") or "")
            if not session_id or session_id in known:
                continue
            title = str(item.get("title") or "") or None
            if search:
                needle = search.casefold()
                if needle not in session_id.casefold() and needle not in (title or "").casefold():
                    continue
            extra.append(
                SessionEntry(
                    session_id=session_id,
                    title=title,
                    active=False,
                    turn_count=0,
                    last_active=int(item.get("updated") or time.time()),
                    chat_title=None,
                    unassigned=True,
                )
            )
        return sorted(
            [*entries, *extra], key=lambda entry: entry.last_active, reverse=True
        )

    async def _resume_target(self, message: Inbound, target: str, *, all_chats: bool) -> None:
        admin = self.authorizer.is_admin(message)
        if all_chats and admin:
            entries = await self._with_unassigned(
                self.store.list_all_session_entries(limit=50), None, []
            )
            entries = [self._origin(entry) for entry in entries]
        else:
            entries = self._remembered_listing(message)
            if entries is None:
                target_text = target.strip()
                if target_text.isdigit() and 1 <= int(target_text) <= sessions.MAX_ROWS:
                    # A bare number only means something next to the list the
                    # human just read. After a restart the same number would
                    # point at a different session, so ask for the list instead.
                    await self._reply(
                        message,
                        "That listing has expired. Run /sessions to see the current numbering.",
                    )
                    return
                entries = self.store.list_session_entries(
                    message.chat_id, message.thread_id, limit=sessions.MAX_ROWS
                )

        resolved = sessions.resolve_target(entries, target)
        if isinstance(resolved, sessions.OutOfRange):
            await self._reply(
                message,
                f"There is no session {resolved.index} in this list. "
                "Run /sessions to see the current numbering.",
            )
            return
        if isinstance(resolved, sessions.NotFound):
            await self._reply(
                message, f'No session here matches "{resolved.target}". Run /sessions to see the list.'
            )
            return
        if isinstance(resolved, sessions.Ambiguous):
            lines = [f'"{target}" matches several sessions:', ""]
            for index, entry in enumerate(resolved.entries[: sessions.MAX_ROWS], start=1):
                lines.append(sessions.format_row(index, entry))
            lines.append("")
            lines.append("Use the number or the id.")
            await self._reply(message, "\n".join(lines))
            return

        ok, text = await self._activate_session(message, resolved.entry)
        await self._reply(message, text)
        if not ok:
            return

    async def _activate_session(self, message: Inbound, entry: SessionEntry) -> tuple[bool, str]:
        """Switch this conversation to ``entry``; return (ok, reply copy)."""

        if self.runner.busy(message.key):
            return (
                False,
                "A run is still in progress here. Wait for it to finish or /abort, then switch.",
            )
        admin = self.authorizer.is_admin(message)
        if not admin:
            if entry.unassigned:
                return False, "No session here matches that. Run /sessions to see the list."
            fresh = self.store.get_session_entry(
                message.chat_id, message.thread_id, entry.session_id
            )
            if fresh is None:
                # The binding was removed (or never belonged here) after the
                # listing was rendered. A routing handle is not authority.
                return False, "No session here matches that. Run /sessions to see the list."
            entry = fresh

        try:
            exists = await self.backend.session_exists(entry.session_id)
        except HarnessError as exc:
            return False, exc.user_message
        if not exists:
            return False, "That session no longer exists in the harness. /new starts a fresh one."

        conversation = self.store.get_conversation(message.chat_id, message.thread_id)
        if conversation and conversation.active_session_id == entry.session_id:
            title = entry.title or "this session"
            return True, f'📌 Already on session "{title}".'

        # session_exists awaited; re-check the queue so a message that arrived
        # during that call is not silently retargeted by this switch.
        if self.runner.busy(message.key):
            return (
                False,
                "A run is still in progress here. Wait for it to finish or /abort, then switch.",
            )

        title = entry.title
        self.store.bind_session(
            message.chat_id, message.thread_id, entry.session_id, title, bound_by=message.user_id
        )
        await self.runner.refresh_dashboard(message)
        name = title or sessions.short_id(entry.session_id)
        turns = entry.turn_count
        count = f"{turns} turn{'s' if turns != 1 else ''}"
        return (
            True,
            f'↻ Resumed session "{name}" ({count}). The next message continues it.',
        )

    def _token(self, kind: str, session_id: str, a: str, b: str = "") -> str:
        if len(self._choices) > 400:
            self._choices.clear()
        token = f"c{len(self._choices)}"
        self._choices[token] = (kind, session_id, a, b)
        return token

    async def _cmd_model(self, message: Inbound, argument: str) -> None:
        session_id, _ = await self.runner.ensure_session(message)
        try:
            models = await self.backend.models()
            providers = await self.backend.providers()
        except HarnessError as exc:
            await self._reply(message, exc.user_message)
            return

        names = {
            str(p.get("id")): str(p.get("name") or p.get("id"))
            for p in providers
            if p.get("id")
        }
        counts: dict[str, int] = {}
        for item in models:
            provider = str(item.get("providerID") or "?")
            counts[provider] = counts.get(provider, 0) + 1
        if not counts:
            await self._reply(message, "The server reported no models.")
            return

        if len(counts) == 1:
            only = next(iter(counts))
            await self._show_models(message, session_id, only, names.get(only, only), models)
            return

        entries = [
            (self._token("p", session_id, provider), f"{names.get(provider, provider)} ({count})")
            for provider, count in sorted(counts.items(), key=lambda item: item[0])
        ]
        await self._reply(
            message,
            f"Current: {await self._current_model(message)}\nChoose a provider:",
            keyboards.provider_keyboard(entries),
        )

    async def _current_model(self, message: Inbound) -> str:
        conversation = self.store.get_conversation(message.chat_id, message.thread_id)
        model = conversation.model if conversation else None
        if model:
            return f"{model['providerID']}/{model['modelID']}"
        return "server default"

    async def _show_models(
        self,
        message: Inbound,
        session_id: str,
        provider_id: str,
        provider_name: str,
        models: list[dict[str, Any]] | None = None,
    ) -> None:
        if models is None:
            try:
                models = await self.backend.models()
            except HarnessError as exc:
                await self._reply(message, exc.user_message)
                return
        mine = [m for m in models if str(m.get("providerID")) == provider_id]
        entries = [
            (
                self._token("m", session_id, provider_id, str(m.get("modelID") or m.get("id"))),
                f"{provider_id}/{m.get('modelID') or m.get('id')}",
            )
            for m in mine[:20]
        ]
        if not entries:
            await self._reply(message, f"{provider_name} reports no models.")
            return
        await self._reply(
            message,
            f"{provider_name} — {len(mine)} models\nCurrent: {await self._current_model(message)}",
            keyboards.model_keyboard(entries),
        )

    async def _cmd_agent(self, message: Inbound, argument: str) -> None:
        if not self.backend.supports_agents:
            await self._reply(
                message,
                f"The {self.backend.name} backend has no agent modes. Use /model instead.",
            )
            return
        session_id, _ = await self.runner.ensure_session(message)
        try:
            agents = await self.backend.agents()
        except HarnessError as exc:
            await self._reply(message, exc.user_message)
            return
        names = [str(item.get("id") or item.get("name")) for item in agents][:10]
        if not names:
            await self._reply(message, "The server reported no agents.")
            return
        entries = [(self._token("a", session_id, name), name) for name in names]
        await self._reply(
            message, "Pick an agent mode for this conversation:", keyboards.agent_keyboard(entries)
        )

    # -- callbacks -------------------------------------------------------

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = self._inbound(update)
        if message is None or message.callback_data is None:
            return
        if not self.authorizer.allow(message):
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "Not allowed.")
            return
        if not self.store.mark_seen(message.update_id):
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "Already handled.")
            return
        self.authorizer.register(message)

        action, parts = keyboards.parse_callback(message.callback_data)
        if action == "P":
            await self._callback_provider(message, parts)
        elif action == "p":
            await self._callback_permission(message, parts)
        elif action == "f":
            await self._callback_form(message, parts)
        elif action == "m":
            await self._callback_model(message, parts)
        elif action == "a":
            await self._callback_agent(message, parts)
        elif action == "s":
            await self._callback_switch(message, parts)
        else:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")

    async def _callback_permission(self, message: Inbound, parts: list[str]) -> None:
        if len(parts) < 3:
            return
        session_id, request_id, decision = parts[0], parts[1], parts[2]
        pending_id = f"permission:{request_id}"
        if decision not in ("once", "always", "reject"):
            return
        accepted, pending = self.store.decide_pending(
            pending_id, message.user_id, "allowed" if decision != "reject" else "denied"
        )
        if not accepted:
            who = self.store.participant_name(pending.decided_by) if pending and pending.decided_by else "someone"
            if self.messenger:
                await self.messenger.answer_callback(
                    message.callback_id or "", f"Already decided by {who}."
                )
            return
        await self.backend.reply_permission(session_id, request_id, decision)
        state = "Allowed" if decision != "reject" else "Denied"
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", f"{state}.")
            await self.messenger.edit_text(
                message.chat_id,
                message.message_id,
                f"{state} by {message.display_name}.",
            )

    async def _callback_form(self, message: Inbound, parts: list[str]) -> None:
        if len(parts) < 3:
            return
        session_id, form_id, index = parts[0], parts[1], parts[2]
        pending = self.store.get_pending(f"form:{form_id}")
        if pending is None:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")
            return
        options = pending.payload.get("options") or []
        try:
            choice = str(options[int(index)])
        except (IndexError, ValueError):
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "That option is gone.")
            return
        accepted, _ = self.store.decide_pending(f"form:{form_id}", message.user_id, "answered")
        if not accepted:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "Already answered.")
            return
        await self.backend.reply_form(session_id, form_id, {"answer": choice})
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Answered.")
            await self.messenger.edit_text(
                message.chat_id,
                message.message_id,
                f"Answered by {message.display_name}: {choice}",
            )

    async def _callback_provider(self, message: Inbound, parts: list[str]) -> None:
        if not parts:
            return
        choice = self._choices.get(parts[0])
        if choice is None:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")
            return
        _, session_id, provider_id, _ = choice
        try:
            providers = await self.backend.providers()
        except HarnessError as exc:
            await self._reply(message, exc.user_message)
            return
        name = next(
            (str(p.get("name")) for p in providers if str(p.get("id")) == provider_id),
            provider_id,
        )
        await self._show_models(message, session_id, provider_id, name)

    async def _callback_model(self, message: Inbound, parts: list[str]) -> None:
        if not parts:
            return
        if parts[0].startswith("c"):
            choice = self._choices.get(parts[0])
            if choice is None:
                if self.messenger:
                    await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")
                return
            _, session_id, provider, model_id = choice
        elif len(parts) >= 3:
            session_id, provider, model_id = parts[0], parts[1], parts[2]
        else:
            return
        try:
            await self.backend.set_model(session_id, provider, model_id)
        except HarnessError as exc:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", exc.user_message)
            return
        self.store.set_model(
            message.chat_id, message.thread_id, {"providerID": provider, "modelID": model_id}
        )
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Model updated.")
            # A fresh message is the only way to relabel the reply keyboard.
            await self.messenger.send_text(
                message.chat_id,
                f"Model set to {provider}/{model_id}.",
                thread_id=message.thread_id,
                keyboard=await self.runner.keyboard(message),
            )
            await self.messenger.delete_message(message.chat_id, message.message_id)

    async def _callback_agent(self, message: Inbound, parts: list[str]) -> None:
        if not parts:
            return
        if parts[0].startswith("c"):
            choice = self._choices.get(parts[0])
            if choice is None:
                if self.messenger:
                    await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")
                return
            _, session_id, agent, _ = choice
        elif len(parts) >= 2:
            session_id, agent = parts[0], parts[1]
        else:
            return
        try:
            await self.backend.set_agent(session_id, agent)
        except HarnessError as exc:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", exc.user_message)
            return
        self.store.set_agent(message.chat_id, message.thread_id, agent)
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Agent updated.")
            await self.messenger.edit_text(
                message.chat_id, message.message_id, f"Agent set to {agent}."
            )

    async def _callback_switch(self, message: Inbound, parts: list[str]) -> None:
        if len(parts) < 3:
            return
        chat_id, thread_id, raw = int(parts[0]), int(parts[1]), parts[2]
        if (chat_id, thread_id) != (message.chat_id, message.thread_id):
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "Wrong conversation.")
            return
        choice = self._choices.get(raw)
        if choice is None:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "This control has expired.")
            return
        _, session_id, _, _ = choice
        entries = self._remembered_listing(message) or []
        entry = next(
            (item for item in entries if item.session_id == session_id), None
        ) or self.store.get_session_entry(chat_id, thread_id, session_id)
        if entry is None:
            # Never synthesise one: a token from another conversation's listing
            # (or from before a restart) would otherwise bind a session this
            # chat never owned.
            if self.messenger:
                await self.messenger.answer_callback(
                    message.callback_id or "", "This control has expired."
                )
            return
        ok, text = await self._activate_session(message, entry)
        if self.messenger:
            await self.messenger.answer_callback(
                message.callback_id or "", text[:190] if not ok else "Switched."
            )
            if ok:
                await self.messenger.edit_text(
                    message.chat_id, message.message_id, text
                )

    # -- agent interactions ---------------------------------------------

    async def on_interaction(self, kind: str, event: Interaction, state: RunState) -> None:
        if self.messenger is None:
            return
        if kind == PERMISSION_ASKED:
            request_id = str(event.get("requestID") or event.get("id") or event.get("request") or "")
            if not request_id:
                return
            tool = event.get("tool") or event.get("permission") or event.get("title") or "a tool"
            pending_id = f"permission:{request_id}"
            _, created = self.store.create_pending(
                pending_id=pending_id,
                kind="permission",
                session_id=state.session_id,
                chat_id=state.message.chat_id,
                thread_id=state.message.thread_id,
                telegram_message_id=None,
                payload={"tool": str(tool)},
            )
            if not created:
                return
            message_id = await self.messenger.send_text(
                state.message.chat_id,
                f"{state.message.display_name} — approval needed: {tool}\nWhoever answers first decides.",
                thread_id=state.message.thread_id,
                keyboard=keyboards.permission_keyboard(state.session_id, request_id),
            )
            self.store.set_pending_message(pending_id, message_id)
            return

        if kind == FORM_CREATED:
            form_id = str(event.get("formID") or event.get("id") or "")
            options = event.get("options") or event.get("choices") or []
            if not form_id or not isinstance(options, list) or not options:
                return
            pending_id = f"form:{form_id}"
            _, created = self.store.create_pending(
                pending_id=pending_id,
                kind="form",
                session_id=state.session_id,
                chat_id=state.message.chat_id,
                thread_id=state.message.thread_id,
                telegram_message_id=None,
                payload={"options": [str(option) for option in options]},
            )
            if not created:
                return
            question = event.get("question") or event.get("title") or "The agent asks:"
            message_id = await self.messenger.send_text(
                state.message.chat_id,
                f"{state.message.display_name} — {question}",
                thread_id=state.message.thread_id,
                keyboard=keyboards.form_keyboard(
                    state.session_id, form_id, [str(option) for option in options]
                ),
            )
            self.store.set_pending_message(pending_id, message_id)
