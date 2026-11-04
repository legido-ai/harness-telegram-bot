"""python-telegram-bot implementation of the Messenger surface."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Bot, ReplyParameters
from telegram.error import BadRequest

from app.telegram.render import render_markdown, strip_html

log = logging.getLogger("bot.telegram")


class TelegramMessenger:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        thread_id: int = 0,
        reply_to: int | None = None,
        keyboard: Any | None = None,
        markdown: bool = False,
    ) -> int:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if thread_id:
            kwargs["message_thread_id"] = thread_id
        if reply_to:
            kwargs["reply_parameters"] = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)
        if keyboard is not None:
            kwargs["reply_markup"] = keyboard
        if markdown:
            kwargs["parse_mode"] = "HTML"
            kwargs["text"] = render_markdown(text)
        try:
            message = await self._bot.send_message(**kwargs)
        except BadRequest:
            # Agent output is arbitrary: if Telegram rejects the markup, deliver
            # the readable text instead of losing the answer.
            kwargs.pop("parse_mode", None)
            kwargs["text"] = strip_html(render_markdown(text)) if markdown else text
            message = await self._bot.send_message(**kwargs)
        return message.message_id

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        keyboard: Any | None = None,
        markdown: bool = False,
    ) -> None:
        kwargs: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if keyboard is not None:
            kwargs["reply_markup"] = keyboard
        if markdown:
            kwargs["parse_mode"] = "HTML"
            kwargs["text"] = render_markdown(text)
        try:
            await self._bot.edit_message_text(**kwargs)
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            if markdown:
                kwargs.pop("parse_mode", None)
                kwargs["text"] = strip_html(render_markdown(text))
                await self._bot.edit_message_text(**kwargs)
                return
            raise

    async def answer_callback(self, callback_id: str, text: str | None = None) -> None:
        await self._bot.answer_callback_query(callback_query_id=callback_id, text=text or "")

    async def pin(self, chat_id: int, message_id: int) -> None:
        try:
            await self._bot.pin_chat_message(
                chat_id=chat_id, message_id=message_id, disable_notification=True
            )
        except Exception as exc:  # a group without pin rights must not break a run
            log.warning("could not pin the dashboard: %s", type(exc).__name__)
