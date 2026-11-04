"""Minimal outbound surface the handlers need, so tests can record instead of dial."""

from __future__ import annotations

from typing import Any, Protocol


class Messenger(Protocol):
    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        thread_id: int = 0,
        reply_to: int | None = None,
        keyboard: Any | None = None,
        markdown: bool = False,
    ) -> int: ...

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        keyboard: Any | None = None,
        markdown: bool = False,
    ) -> None: ...

    async def answer_callback(self, callback_id: str, text: str | None = None) -> None: ...

    async def pin(self, chat_id: int, message_id: int) -> None: ...

    async def send_typing(self, chat_id: int, thread_id: int = 0) -> None: ...
