"""Small builders for test messages."""

from __future__ import annotations

from app.telegram.types import Entity, Inbound, Quoted


def inbound(
    *,
    chat_id: int = -100123,
    chat_type: str = "supergroup",
    thread_id: int = 0,
    user_id: int = 111,
    display_name: str = "Ana",
    text: str = "",
    entities: tuple[Entity, ...] = (),
    quote: Quoted | None = None,
    is_bot: bool = False,
    update_id: int = 1,
    message_id: int = 10,
    chat_title: str = "OC3 build",
) -> Inbound:
    return Inbound(
        update_id=update_id,
        message_id=message_id,
        chat_id=chat_id,
        chat_type=chat_type,
        chat_title=chat_title if chat_type != "private" else None,
        thread_id=thread_id,
        user_id=user_id,
        display_name=display_name,
        username=f"user{user_id}",
        is_bot=is_bot,
        text=text,
        entities=entities,
        quote=quote,
    )


def mention_entity(text: str, username: str = "oc3bot", prefix: str = "") -> Entity:
    offset = len(prefix.encode("utf-16-le")) // 2
    return Entity(type="mention", offset=offset, length=len(f"@{username}"))
