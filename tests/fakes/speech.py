"""Deterministic speech fakes: no sockets, no models, no audio."""

from __future__ import annotations

from app.speech.stt import SttError
from app.speech.tts import Speech, TtsError


class FakeStt:
    def __init__(self, text: str = "hola desde la voz", error: SttError | None = None) -> None:
        self.text = text
        self.error = error
        self.calls: list[tuple[bytes, str]] = []

    @property
    def available(self) -> bool:
        return True

    async def transcribe(self, audio: bytes, filename: str) -> str:
        self.calls.append((audio, filename))
        if self.error is not None:
            raise self.error
        return self.text


class FakeTts:
    def __init__(self, data: bytes = b"ID3fake-mp3", error: TtsError | None = None) -> None:
        self.data = data
        self.error = error
        self.texts: list[str] = []
        self.voices: list[str | None] = []

    @property
    def available(self) -> bool:
        return True

    async def synthesize(self, text: str, *, voice: str | None = None) -> Speech:
        self.texts.append(text)
        self.voices.append(voice)
        if self.error is not None:
            raise self.error
        return Speech(data=self.data)
