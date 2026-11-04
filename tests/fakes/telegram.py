"""Records outgoing Telegram calls instead of dialling the Bot API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sent:
    chat_id: int
    text: str
    thread_id: int = 0
    reply_to: int | None = None
    keyboard: Any = None
    message_id: int = 0


@dataclass
class Edited:
    chat_id: int
    message_id: int
    text: str
    keyboard: Any = None


@dataclass
class FakeMessenger:
    sent: list[Sent] = field(default_factory=list)
    edited: list[Edited] = field(default_factory=list)
    callbacks: list[tuple[str, str]] = field(default_factory=list)
    pinned: list[tuple[int, int]] = field(default_factory=list)
    typing: list[tuple[int, int]] = field(default_factory=list)
    _next_id: int = 100

    async def send_text(
        self,
        chat_id: int,
        text: str,
        *,
        thread_id: int = 0,
        reply_to: int | None = None,
        keyboard: Any = None,
        markdown: bool = False,
    ) -> int:
        self._next_id += 1
        self.sent.append(
            Sent(
                chat_id=chat_id,
                text=text,
                thread_id=thread_id,
                reply_to=reply_to,
                keyboard=keyboard,
                message_id=self._next_id,
            )
        )
        return self._next_id

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        keyboard: Any = None,
        markdown: bool = False,
    ) -> None:
        self.edited.append(Edited(chat_id=chat_id, message_id=message_id, text=text, keyboard=keyboard))

    async def answer_callback(self, callback_id: str, text: str | None = None) -> None:
        self.callbacks.append((callback_id, text or ""))

    async def send_typing(self, chat_id: int, thread_id: int = 0) -> None:
        self.typing.append((chat_id, thread_id))

    async def pin(self, chat_id: int, message_id: int) -> None:
        self.pinned.append((chat_id, message_id))

    @property
    def last_text(self) -> str:
        if self.edited:
            return self.edited[-1].text
        return self.sent[-1].text if self.sent else ""
