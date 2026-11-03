"""python-telegram-bot implementation of the Messenger surface."""

from __future__ import annotations

import logging
from typing import Any

from telegram import Bot, ReplyParameters

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
        try:
            await self._bot.edit_message_text(**kwargs)
        except Exception as exc:  # Telegram raises on "message is not modified"
            if "not modified" not in str(exc).lower():
                raise

    async def answer_callback(self, callback_id: str, text: str | None = None) -> None:
        await self._bot.answer_callback_query(callback_query_id=callback_id, text=text or "")
