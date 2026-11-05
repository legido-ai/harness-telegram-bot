"""Telegram-agnostic message shapes used by triggers, runners and tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Entity:
    type: str
    offset: int
    length: int
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class Quoted:
    message_id: int
    author_id: int | None
    author_name: str
    text: str
    is_bot: bool = False


@dataclass(frozen=True, slots=True)
class Inbound:
    update_id: int
    message_id: int
    chat_id: int
    chat_type: str
    chat_title: str | None
    thread_id: int
    user_id: int
    display_name: str
    username: str | None
    is_bot: bool
    text: str
    entities: tuple[Entity, ...] = field(default_factory=tuple)
    quote: Quoted | None = None
    callback_id: str | None = None
    callback_data: str | None = None
    thread_title: str | None = None

    @property
    def is_private(self) -> bool:
        return self.chat_type == "private"

    @property
    def key(self) -> tuple[int, int]:
        return (self.chat_id, self.thread_id)


@dataclass(frozen=True, slots=True)
class Trigger:
    kind: str  # private | mention | reply | command | policy_all | empty
    text: str
    quote: Quoted | None = None

    @property
    def has_prompt(self) -> bool:
        return bool(self.text.strip())
