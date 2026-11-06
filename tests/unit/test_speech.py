from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.speech.stt import SttClient, SttEmpty, SttRejected, SttUnavailable
from app.speech.tts import TtsClient, TtsFailed, strip_markdown_for_speech


def test_markdown_is_not_read_aloud() -> None:
    source = "## Result\n**bold** and `code` and [docs](https://example.com)\n\n```js\nx = 1\n```"
    spoken = strip_markdown_for_speech(source)
    assert "**" not in spoken
    assert "`" not in spoken
    assert "https://example.com" not in spoken
    assert "Result" in spoken and "bold" in spoken and "code" in spoken and "x = 1" in spoken


async def test_stt_multipart_upload(settings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["type"] = request.headers.get("content-type", "")
        seen["body"] = request.read()
        return httpx.Response(200, json={"text": "  hola mundo  "})

    client = SttClient(
        replace(
            settings,
            stt_url="http://stt.local/v1",
            stt_api_key="stt-secret-key",
            stt_model="small",
            stt_language="es",
            stt_request_format="multipart",
        ),
        transport=httpx.MockTransport(handler),
    )
    assert await client.transcribe(b"OggSdata", "voice.ogg") == "hola mundo"
    assert seen["path"] == "/v1/audio/transcriptions"
    assert seen["auth"] == "Bearer stt-secret-key"
    assert "multipart/form-data" in str(seen["type"])
    assert b'name="file"' in seen["body"]  # type: ignore[operator]
    assert b"small" in seen["body"]  # type: ignore[operator]


async def test_stt_json_body_for_openrouter_style(settings) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read()))
        return httpx.Response(200, json={"text": "uno dos"})

    client = SttClient(
        replace(
            settings,
            stt_url="http://stt.local/v1",
            stt_api_key="stt-secret-key",
            stt_model="whisper-1",
            stt_language="",
            stt_request_format="json",
        ),
        transport=httpx.MockTransport(handler),
    )
    assert await client.transcribe(b"abc", "note.oga") == "uno dos"
    assert captured["model"] == "whisper-1"
    assert captured["input_audio"]["format"] == "ogg"  # type: ignore[index]
    assert "language" not in captured


async def test_stt_errors_never_echo_the_body(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="secret body")

    client = SttClient(
        replace(settings, stt_url="http://stt.local/v1", stt_api_key="stt-secret-key"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(SttRejected) as excinfo:
        await client.transcribe(b"abc", "voice.ogg")
    assert "secret" not in excinfo.value.user_message

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "   "})

    client = SttClient(
        replace(settings, stt_url="http://stt.local/v1", stt_api_key="stt-secret-key"),
        transport=httpx.MockTransport(empty),
    )
    with pytest.raises(SttEmpty):
        await client.transcribe(b"abc", "voice.ogg")


async def test_stt_unavailable_when_the_socket_fails(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    client = SttClient(
        replace(settings, stt_url="http://stt.local/v1", stt_api_key="stt-secret-key"),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(SttUnavailable):
        await client.transcribe(b"abc", "voice.ogg")


async def test_openai_compatible_tts(settings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.read())
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"ID3audio")

    client = TtsClient(
        replace(
            settings,
            tts_provider="openai",
            tts_url="http://tts.local/v1",
            tts_api_key="tts-secret-key",
            tts_model="gpt-4o-mini-tts",
            tts_voice="alloy",
        ),
        transport=httpx.MockTransport(handler),
    )
    speech = await client.synthesize("**Hola**")
    assert speech.data == b"ID3audio"
    assert seen["path"] == "/v1/audio/speech"
    assert seen["auth"] == "Bearer tts-secret-key"
    assert seen["body"]["input"] == "Hola"  # type: ignore[index]
    assert seen["body"]["voice"] == "alloy"  # type: ignore[index]


async def test_tts_rejects_empty_provider_audio(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    client = TtsClient(
        replace(
            settings,
            tts_provider="openai",
            tts_url="http://tts.local/v1",
            tts_api_key="tts-secret-key",
        ),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(TtsFailed):
        await client.synthesize("hello")


async def test_edge_tts_uses_the_injected_synthesizer(settings) -> None:
    calls: list[tuple[str, str]] = []

    async def synth(text: str, voice: str) -> bytes:
        calls.append((text, voice))
        return b"edge-mp3"

    client = TtsClient(
        replace(settings, tts_provider="edge", tts_voice="en-US-AriaNeural"),
        edge_synthesizer=synth,
    )
    speech = await client.synthesize("plain text")
    assert speech.data == b"edge-mp3"
    assert calls == [("plain text", "en-US-AriaNeural")]
