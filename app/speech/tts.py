"""Text-to-speech for spoken assistant replies.

Providers mirror the bridge we replaced: Microsoft Edge Read Aloud (no key,
default in this deployment), any OpenAI-compatible ``/audio/speech`` endpoint,
and ElevenLabs. Google Cloud TTS is intentionally not wired: it is not used by
the reference deployment and would add a gRPC credential dependency.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger("bot.tts")

TIMEOUT_SECONDS = 60.0
MAX_INPUT_CHARS = 4_000
EDGE_DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"


@dataclass(frozen=True, slots=True)
class Speech:
    data: bytes
    filename: str = "assistant-reply.mp3"
    mime_type: str = "audio/mpeg"


class TtsError(RuntimeError):
    user_message = "audio replies are unavailable right now"

    def __init__(self, user_message: str | None = None) -> None:
        super().__init__(user_message or self.user_message)
        self.user_message = user_message or self.user_message


class TtsNotConfigured(TtsError):
    user_message = "audio replies are not configured (set TTS_API_URL and TTS_API_KEY)"


class TtsFailed(TtsError):
    user_message = "I could not generate the audio reply"


def strip_markdown_for_speech(text: str) -> str:
    """Remove syntax an engine would read aloud (ported from the old bridge)."""

    clean = re.sub(
        r"```[\s\S]*?```",
        lambda match: re.sub(r"\n?```$", "", re.sub(r"^```\w*\n?", "", match.group(0))).replace(
            "\n", " "
        ),
        text,
    )
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", clean)
    clean = re.sub(r"\*\*(.+?)\*\*", r"\1", clean)
    clean = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", clean)
    clean = re.sub(r"~~(.+?)~~", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"^#{1,6}\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^>\s?", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^[-*]\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\d+\.\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^[-*_]{3,}\s*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"</?[A-Za-z][^>]*>", "", clean)
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


class TtsClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        edge_synthesizer: object | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._edge_synthesizer = edge_synthesizer

    @property
    def available(self) -> bool:
        return self._settings.tts_configured

    async def synthesize(self, text: str, *, voice: str | None = None) -> Speech:
        if not self.available:
            raise TtsNotConfigured()
        spoken = strip_markdown_for_speech(text)
        if not spoken:
            raise TtsFailed()
        if len(spoken) > MAX_INPUT_CHARS:
            raise TtsFailed("the answer is too long to read aloud")

        chosen = voice or self._settings.tts_voice
        try:
            if self._settings.tts_provider == "edge":
                audio = await self._synthesize_edge(spoken, chosen)
            elif self._settings.tts_provider == "elevenlabs":
                audio = await self._synthesize_elevenlabs(spoken, chosen)
            else:
                audio = await self._synthesize_openai(spoken, chosen)
        except TtsError:
            raise
        except TimeoutError as exc:
            raise TtsFailed("the speech service timed out") from exc
        except Exception as exc:  # provider/network failures are user-visible, details are not
            log.warning("speech synthesis failed: %s", type(exc).__name__)
            raise TtsFailed() from exc

        if not audio:
            raise TtsFailed("the speech service returned no audio")
        log.info("generated speech", extra={"event": f"{len(audio)} bytes"})
        return Speech(data=audio)

    async def _synthesize_edge(self, text: str, voice: str) -> bytes:
        if self._edge_synthesizer is not None:
            return await self._edge_synthesizer(text, voice)  # type: ignore[operator]

        import edge_tts

        async def collect() -> bytes:
            communicate = edge_tts.Communicate(text, voice or EDGE_DEFAULT_VOICE)
            chunks = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    chunks.extend(chunk["data"])
            return bytes(chunks)

        async with asyncio.timeout(TIMEOUT_SECONDS):
            return await collect()

    async def _synthesize_openai(self, text: str, voice: str) -> bytes:
        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0)
        ) as client:
            response = await client.post(
                f"{self._settings.tts_url}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self._settings.tts_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.tts_model,
                    "voice": voice,
                    "input": text,
                    "response_format": "mp3",
                },
            )
        if response.status_code >= 400:
            log.warning("speech service rejected synthesis: HTTP %s", response.status_code)
            raise TtsFailed()
        return response.content

    async def _synthesize_elevenlabs(self, text: str, voice: str) -> bytes:
        voice = voice or "21m00Tcm4TlvDq8ikWAM"
        async with httpx.AsyncClient(
            transport=self._transport, timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=10.0)
        ) as client:
            response = await client.post(
                f"{self._settings.tts_url}/text-to-speech/{voice}",
                headers={
                    "xi-api-key": self._settings.tts_api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={"text": text, "model_id": self._settings.tts_model or "eleven_flash_v2_5"},
            )
        if response.status_code >= 400:
            log.warning("speech service rejected synthesis: HTTP %s", response.status_code)
            raise TtsFailed()
        return response.content
