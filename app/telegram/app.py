"""Telegram wiring: intake, triggers, commands and callbacks.

Handlers are thin on purpose. Every decision that matters lives in a pure module
(``trigger``, ``identity``, ``streaming``) or in the runner, which keeps the
behaviour testable without a live bot.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from app.config import Settings
from app.health import HealthState
from app.opencode.client import PERMISSION_DECISIONS, OpenCodeClient
from app.opencode.errors import OpenCodeError
from app.opencode.events import FORM_CREATED, PERMISSION_ASKED, Event
from app.store import Store
from app.telegram import commands, keyboards
from app.telegram.attachments import AttachmentError, collect
from app.telegram.auth import Authorizer
from app.telegram.convert import from_update
from app.telegram.messenger import Messenger
from app.telegram.ptb_messenger import TelegramMessenger
from app.telegram.runner import Job, Runner, RunState
from app.telegram.trigger import detect
from app.telegram.types import Inbound

log = logging.getLogger("bot.app")


class BotApp:
    def __init__(
        self,
        *,
        settings: Settings,
        store: Store,
        client: OpenCodeClient,
        runner: Runner,
        state: HealthState,
        messenger: Messenger | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.client = client
        self.runner = runner
        self.state = state
        self.authorizer = Authorizer(settings, store)
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
            .post_init(self.on_startup)
            .concurrent_updates(True)
            .build()
        )
        application.add_handler(MessageHandler(filters.ALL, self.on_message))
        application.add_handler(CallbackQueryHandler(self.on_callback))
        return application

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
        except OpenCodeError as exc:
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

    async def _cmd_sessions(self, message: Inbound, argument: str) -> None:
        bindings = self.store.list_bindings(message.chat_id, message.thread_id, limit=10)
        rows = [(b.session_id, b.title or "untitled", b.active) for b in bindings]
        text = commands.sessions_text(rows)
        keyboard = None
        if bindings:
            keyboard = keyboards.sessions_keyboard(
                message.chat_id,
                message.thread_id,
                [(b.session_id, b.title or "untitled") for b in bindings],
            )
        await self._reply(message, text, keyboard)

    async def _cmd_switch(self, message: Inbound, argument: str) -> None:
        await self._cmd_sessions(message, argument)

    async def _cmd_model(self, message: Inbound, argument: str) -> None:
        session_id, _ = await self.runner.ensure_session(message)
        try:
            models = await self.client.models()
        except OpenCodeError as exc:
            await self._reply(message, exc.user_message)
            return
        entries: list[tuple[str, str, str]] = []
        for item in models[:10]:
            provider = str(item.get("providerID") or item.get("provider") or "?")
            model_id = str(item.get("modelID") or item.get("id") or "?")
            label = str(item.get("name") or model_id)
            entries.append((provider, model_id, label))
        if not entries:
            await self._reply(message, "The server reported no models.")
            return
        await self._reply(
            message, "Pick a model for this conversation:", keyboards.model_keyboard(session_id, entries)
        )

    async def _cmd_agent(self, message: Inbound, argument: str) -> None:
        session_id, _ = await self.runner.ensure_session(message)
        try:
            agents = await self.client.agents()
        except OpenCodeError as exc:
            await self._reply(message, exc.user_message)
            return
        names = [str(item.get("id") or item.get("name")) for item in agents][:10]
        if not names:
            await self._reply(message, "The server reported no agents.")
            return
        await self._reply(
            message, "Pick an agent mode for this conversation:", keyboards.agent_keyboard(session_id, names)
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
        if action == "p":
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
        if decision not in PERMISSION_DECISIONS:
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
        await self.client.reply_permission(session_id, request_id, decision)
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
        await self.client.reply_form(session_id, form_id, {"answer": choice})
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Answered.")
            await self.messenger.edit_text(
                message.chat_id,
                message.message_id,
                f"Answered by {message.display_name}: {choice}",
            )

    async def _callback_model(self, message: Inbound, parts: list[str]) -> None:
        if len(parts) < 3:
            return
        session_id, provider, model_id = parts[0], parts[1], parts[2]
        try:
            await self.client.set_model(session_id, provider, model_id)
        except OpenCodeError as exc:
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", exc.user_message)
            return
        self.store.set_model(message.chat_id, message.thread_id, {"providerID": provider, "modelID": model_id})
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Model updated.")
            await self.messenger.edit_text(
                message.chat_id, message.message_id, f"Model set to {provider}/{model_id}."
            )

    async def _callback_agent(self, message: Inbound, parts: list[str]) -> None:
        if len(parts) < 2:
            return
        session_id, agent = parts[0], parts[1]
        try:
            await self.client.set_agent(session_id, agent)
        except OpenCodeError as exc:
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
        chat_id, thread_id, session_id = int(parts[0]), int(parts[1]), parts[2]
        if (chat_id, thread_id) != (message.chat_id, message.thread_id):
            if self.messenger:
                await self.messenger.answer_callback(message.callback_id or "", "Wrong conversation.")
            return
        self.store.bind_session(chat_id, thread_id, session_id, None, bound_by=message.user_id)
        await self.runner.refresh_dashboard(message)
        if self.messenger:
            await self.messenger.answer_callback(message.callback_id or "", "Switched.")
            await self.messenger.edit_text(
                message.chat_id, message.message_id, f"Switched to session {session_id[-6:]}."
            )

    # -- agent interactions ---------------------------------------------

    async def on_interaction(self, kind: str, event: Event, state: RunState) -> None:
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
