"""Speech-to-text through a Whisper-compatible API.

Two request shapes are supported, matching the bridge we replaced:
- ``multipart`` (default): OpenAI/Groq/whisper.cpp ``/audio/transcriptions``.
- ``json``: base64 audio in an ``input_audio`` body (OpenRouter style).

The service URL and key come from the environment; they are never logged.
"""

from __future__ import annotations

import base64
import logging
from pathlib import PurePath

import httpx

from app.config import Settings

log = logging.getLogger("bot.stt")

TIMEOUT_SECONDS = 60.0

AUDIO_FORMAT_BY_EXTENSION = {
    "oga": "ogg",
    "ogg": "ogg",
    "mp3": "mp3",
    "wav": "wav",
    "m4a": "m4a",
    "flac": "flac",
    "aac": "aac",
    "webm": "webm",
}

AUDIO_MIME_BY_FORMAT = {
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "flac": "audio/flac",
    "aac": "audio/aac",
    "webm": "audio/webm",
}


class SttError(RuntimeError):
    """User-facing failure; the message never contains a URL, key or body."""

    user_message = "the speech service returned an unexpected response"

    def __init__(self, user_message: str | None = None) -> None:
        super().__init__(user_message or self.user_message)
        self.user_message = user_message or self.user_message


class SttNotConfigured(SttError):
    user_message = "voice recognition is not configured (set STT_API_URL and STT_API_KEY)"


class SttUnavailable(SttError):
    user_message = "the speech service is unreachable right now"


class SttRejected(SttError):
    user_message = "the speech service rejected the audio"


class SttEmpty(SttError):
    user_message = "no speech was detected in that audio"


def audio_format(filename: str) -> str:
    extension = PurePath(filename).suffix.lstrip(".").lower()
    return AUDIO_FORMAT_BY_EXTENSION.get(extension, "ogg")


def audio_mime(filename: str) -> str:
    return AUDIO_MIME_BY_FORMAT.get(audio_format(filename), "audio/ogg")


class SttClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    @property
    def available(self) -> bool:
        return self._settings.stt_configured

    async def transcribe(self, audio: bytes, filename: str) -> str:
        if not self.available:
            raise SttNotConfigured()
        if not audio:
            raise SttEmpty()

        settings = self._settings
        url = f"{settings.stt_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.stt_api_key}"}
        data: dict[str, str] = {}
        files: dict[str, tuple[str, bytes, str]] | None = None

        if settings.stt_request_format == "json":
            payload: dict[str, object] = {
                "model": settings.stt_model,
                "input_audio": {
                    "data": base64.b64encode(audio).decode("ascii"),
                    "format": audio_format(filename),
                },
            }
            if settings.stt_language:
                payload["language"] = settings.stt_language
            headers["Content-Type"] = "application/json"
            body: dict[str, object] | None = payload
        else:
            files = {"file": (filename, audio, audio_mime(filename))}
            data = {"model": settings.stt_model, "response_format": "json"}
            if settings.stt_language:
                data["language"] = settings.stt_language
            body = None

        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0)
            ) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    data=data if files else None,
                    files=files,
                    json=body,
                )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.HTTPError) as exc:
            log.warning("speech service unavailable: %s", type(exc).__name__)
            raise SttUnavailable() from exc

        if response.status_code >= 400:
            log.warning("speech service rejected audio: HTTP %s", response.status_code)
            raise SttRejected()
        try:
            payload = response.json()
        except ValueError as exc:
            raise SttRejected() from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            raise SttRejected()
        text = text.strip()
        if not text:
            raise SttEmpty()
        log.info("transcribed audio", extra={"event": f"{len(text)} chars"})
        return text
