"""Helpers to build real python-telegram-bot objects offline."""

from __future__ import annotations

import time
from typing import Any

from telegram import Bot, Update

BOT_ID = 424242
BOT_USERNAME = "oc3bot"
BOT_TOKEN = "123456:TESTTOKENVALUE"


def bot() -> Bot:
    return Bot(BOT_TOKEN)


def message_payload(
    *,
    text: str,
    chat_id: int = -100123,
    chat_type: str = "supergroup",
    user_id: int = 111,
    first_name: str = "Ana",
    username: str | None = None,
    message_id: int = 10,
    thread_id: int | None = None,
    entities: list[dict[str, Any]] | None = None,
    reply_to: dict[str, Any] | None = None,
    is_bot: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message_id": message_id,
        "date": int(time.time()),
        "chat": {
            "id": chat_id,
            "type": chat_type,
            "title": "OC3 build" if chat_type != "private" else None,
        },
        "from": {
            "id": user_id,
            "is_bot": is_bot,
            "first_name": first_name,
            **({"username": username} if username else {}),
        },
        "text": text,
    }
    if not payload["chat"]["title"]:
        payload["chat"].pop("title")
    if thread_id:
        payload["message_thread_id"] = thread_id
        payload["is_topic_message"] = True
    if entities:
        payload["entities"] = entities
    if reply_to:
        payload["reply_to_message"] = reply_to
    return payload


def update(text: str, *, update_id: int = 1, **kwargs: Any) -> Update:
    return Update.de_json(
        {"update_id": update_id, "message": message_payload(text=text, **kwargs)}, bot()
    )


def voice_update(
    *,
    update_id: int = 1,
    caption: str | None = None,
    caption_entities: list[dict[str, Any]] | None = None,
    reply_to: dict[str, Any] | None = None,
    chat_id: int = -100123,
    chat_type: str = "supergroup",
    user_id: int = 111,
    first_name: str = "Ana",
    message_id: int = 10,
    thread_id: int | None = None,
) -> Update:
    payload = message_payload(
        text="",
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
        first_name=first_name,
        message_id=message_id,
        thread_id=thread_id,
    )
    payload.pop("text", None)
    payload["voice"] = {
        "file_id": "voice-file-1",
        "file_unique_id": "voice-unique-1",
        "duration": 2,
        "mime_type": "audio/ogg",
        "file_size": 4096,
    }
    if caption is not None:
        payload["caption"] = caption
    if caption_entities:
        payload["caption_entities"] = caption_entities
    if reply_to:
        payload["reply_to_message"] = reply_to
    return Update.de_json({"update_id": update_id, "message": payload}, bot())


def callback_update(
    data: str,
    *,
    update_id: int = 900,
    chat_id: int = -100123,
    chat_type: str = "supergroup",
    user_id: int = 222,
    first_name: str = "Luis",
    message_id: int = 55,
    thread_id: int | None = None,
) -> Update:
    message = message_payload(
        text="controls",
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=BOT_ID,
        first_name="OC3 bot",
        message_id=message_id,
        thread_id=thread_id,
        is_bot=True,
    )
    payload = {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": first_name},
            "chat_instance": "1",
            "data": data,
            "message": message,
        },
    }
    return Update.de_json(payload, bot())
