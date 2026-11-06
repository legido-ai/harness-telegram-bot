"""Convert python-telegram-bot objects into the bot's own message shapes."""

from __future__ import annotations

from telegram import Message, Update

from app.telegram.types import Entity, Inbound, Quoted


def _display_name(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "unknown"
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    return name or (f"@{user.username}" if user.username else str(user.id))


def _entities(message: Message) -> tuple[Entity, ...]:
    result: list[Entity] = []
    # Captions carry their own entity list; a voice note with "@bot" in its
    # caption must trigger exactly like a text message would.
    entities = message.entities or getattr(message, "caption_entities", None) or ()
    for entity in entities:
        user_id = entity.user.id if getattr(entity, "user", None) is not None else None
        result.append(
            Entity(type=str(entity.type), offset=entity.offset, length=entity.length, user_id=user_id)
        )
    return tuple(result)


def _quoted(message: Message) -> Quoted | None:
    quoted = message.reply_to_message
    if quoted is None:
        return None
    author = quoted.from_user
    name = "unknown"
    if author is not None:
        name = " ".join(p for p in (author.first_name, author.last_name) if p).strip() or str(author.id)
    return Quoted(
        message_id=quoted.message_id,
        author_id=author.id if author else None,
        author_name=name,
        text=quoted.text or quoted.caption or "",
        is_bot=bool(author and author.is_bot),
    )


def from_update(update: Update, bot_id: int) -> Inbound | None:
    """Return an Inbound for messages and callback queries, else None."""

    if update.callback_query is not None:
        query = update.callback_query
        message = query.message
        if message is None or query.from_user is None:
            return None
        return Inbound(
            update_id=update.update_id,
            message_id=message.message_id,
            chat_id=message.chat_id,
            chat_type=message.chat.type,
            chat_title=message.chat.title,
            thread_id=getattr(message, "message_thread_id", 0) or 0,
            user_id=query.from_user.id,
            display_name=" ".join(
                p for p in (query.from_user.first_name, query.from_user.last_name) if p
            ).strip()
            or str(query.from_user.id),
            username=query.from_user.username,
            is_bot=query.from_user.is_bot,
            text="",
            callback_id=query.id,
            callback_data=query.data,
        )

    message = update.effective_message
    if message is None or message.from_user is None:
        return None

    thread_id = getattr(message, "message_thread_id", 0) or 0
    if thread_id and thread_id == getattr(message, "message_thread_id", 0) and message.is_topic_message:
        pass  # explicit: forum topics keep their thread id

    return Inbound(
        update_id=update.update_id,
        message_id=message.message_id,
        chat_id=message.chat_id,
        chat_type=message.chat.type,
        chat_title=message.chat.title,
        thread_id=thread_id,
        user_id=message.from_user.id,
        display_name=_display_name(message),
        username=message.from_user.username,
        is_bot=message.from_user.is_bot,
        text=message.text or message.caption or "",
        entities=_entities(message),
        quote=_quoted(message),
        voice_input=message.voice is not None or message.audio is not None,
    )


def bot_id_hint(bot_username: str) -> str:
    return bot_username.lstrip("@").lower()
