"""Download incoming voice notes and audio files within the configured limit."""

from __future__ import annotations

import logging
from pathlib import PurePath
from typing import Any

from app.config import Settings

log = logging.getLogger("bot.voice")

MIME_EXTENSION = {
    "audio/ogg": ".ogg",
    "audio/opus": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
}


class VoiceError(RuntimeError):
    """User-facing download failure."""

    user_message = "I could not download that audio from Telegram."


def voice_file(message: Any) -> Any | None:
    return getattr(message, "voice", None) or getattr(message, "audio", None)


def filename_for(file_obj: Any) -> str:
    declared = getattr(file_obj, "file_name", None)
    if declared:
        return PurePath(declared).name
    mime = str(getattr(file_obj, "mime_type", "") or "audio/ogg").lower()
    extension = MIME_EXTENSION.get(mime, ".ogg")
    unique = str(getattr(file_obj, "file_unique_id", "audio"))[:24]
    return f"voice-{unique}{extension}"


async def download(bot: Any, message: Any, settings: Settings) -> tuple[bytes, str]:
    """Return ``(audio bytes, filename)`` for a voice or audio message."""

    file_obj = voice_file(message)
    if file_obj is None:
        raise VoiceError("that message has no audio I can read")

    size = getattr(file_obj, "file_size", None)
    limit = settings.max_attachment_mb * 1024 * 1024
    if size is not None and size > limit:
        raise VoiceError(f"that audio is larger than the {settings.max_attachment_mb} MB limit.")

    try:
        remote = await bot.get_file(file_obj.file_id)
        payload = await remote.download_as_bytearray()
    except Exception as exc:
        log.warning("audio download failed: %s", type(exc).__name__)
        raise VoiceError() from exc

    data = bytes(payload)
    if not data:
        raise VoiceError("Telegram returned an empty audio file.")
    if len(data) > limit:
        raise VoiceError(f"that audio is larger than the {settings.max_attachment_mb} MB limit.")
    return data, filename_for(file_obj)
