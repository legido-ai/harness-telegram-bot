"""Pi adapter, driven against a fake ``pi --mode rpc`` process.

No network, no model, no credentials: the fake speaks the same JSONL protocol
and records what the adapter sent it. Each test runs one event loop, because the
child process belongs to the loop that spawned it.
"""

from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

import pytest

from app.backends.errors import InvalidRequest, Unsupported
from app.backends.pi.backend import PiBackend
from app.backends.pi.rpc import PiRpc

FAKE = Path(__file__).resolve().parents[1] / "fakes" / "pi_rpc.py"


def _executable(tmp_path: Path) -> Path:
    binary = tmp_path / "pi"
    binary.write_text(FAKE.read_text(encoding="utf-8"), encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    return binary


@pytest.fixture
def backend(tmp_path: Path) -> PiBackend:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    rpc = PiRpc(
        binary=str(_executable(tmp_path)),
        provider="fake-provider",
        model="fake-model",
        session_dir=sessions,
        workspace=tmp_path,
        extra_args=("--fake-log", str(tmp_path / "rpc.jsonl")),
    )
    return PiBackend(rpc, session_dir=sessions, run_timeout=10, idle_seconds=0.2)


def test_create_session_reports_a_file(backend: PiBackend) -> None:
    async def scenario() -> str:
        try:
            return await backend.create_session("hello")
        finally:
            await backend.aclose()

    ref = asyncio.run(scenario())
    assert ref.endswith(".jsonl")
    assert Path(ref).exists()


def test_run_streams_deltas_and_settles(backend: PiBackend) -> None:
    async def scenario() -> tuple[str, list[str]]:
        try:
            ref = await backend.create_session("hello")
            deltas: list[str] = []

            async def sink(delta: str) -> None:
                deltas.append(delta)

            outcome = await backend.run(ref, "hi", on_delta=sink)
            return (outcome.text or "", deltas)
        finally:
            await backend.aclose()

    text, deltas = asyncio.run(scenario())
    assert deltas == ["Hello ", "from Pi"]
    assert text == ""


def test_stats_feed_the_footer(backend: PiBackend) -> None:
    async def scenario() -> dict:
        try:
            ref = await backend.create_session("hello")
            return {
                "usage": await backend.context_usage(ref),
                "session": await backend.session(ref),
                "limit": await backend.context_limit("fake-provider", "fake-model"),
            }
        finally:
            await backend.aclose()

    data = asyncio.run(scenario())
    assert data["usage"]["used_tokens"] == 42_000
    assert data["usage"]["model"] == "fake-model"
    assert data["session"]["cost"] == pytest.approx(0.0125)
    assert data["limit"] == 200_000


def test_models_and_providers_come_from_the_agent(backend: PiBackend) -> None:
    async def scenario() -> tuple[list[dict], list[dict], list[dict]]:
        try:
            return await backend.models(), await backend.providers(), await backend.agents()
        finally:
            await backend.aclose()

    models, providers, agents = asyncio.run(scenario())
    assert [model["modelID"] for model in models] == ["fake-model", "second-model"]
    assert models[0]["limit"]["context"] == 200_000
    assert providers == [{"id": "fake-provider", "name": "fake-provider"}]
    assert agents == []


def test_agent_and_permissions_are_declared_unsupported(backend: PiBackend) -> None:
    async def scenario() -> None:
        try:
            ref = await backend.create_session("hello")
            with pytest.raises(Unsupported):
                await backend.set_agent(ref, "build")
            with pytest.raises(Unsupported):
                await backend.reply_permission(ref, "req", "once")
            with pytest.raises(Unsupported):
                await backend.generate(ref, "say something")
        finally:
            await backend.aclose()

    asyncio.run(scenario())


def test_images_reach_the_agent_and_pdfs_are_refused(backend: PiBackend, tmp_path: Path) -> None:
    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    log = tmp_path / "rpc.jsonl"

    async def scenario() -> None:
        try:
            ref = await backend.create_session("hello")
            await backend.run(
                ref, "look", files=[{"type": "file", "path": str(image), "mime": "image/png"}]
            )
            with pytest.raises(InvalidRequest):
                await backend.run(
                    ref,
                    "read this",
                    files=[{"type": "file", "path": str(pdf), "mime": "application/pdf"}],
                )
        finally:
            await backend.aclose()

    asyncio.run(scenario())
    sent = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    prompts = [item for item in sent if item.get("type") == "prompt"]
    assert prompts[0]["images"][0]["mimeType"] == "image/png"
    assert prompts[0]["images"][0]["data"].startswith("iVBOR")


def test_abort_and_describe(backend: PiBackend) -> None:
    async def scenario() -> tuple[bool, str, str]:
        try:
            ref = await backend.create_session("hello")
            await backend.run(ref, "hi")
            return await backend.interrupt(ref), await backend.describe(ref), ref
        finally:
            await backend.aclose()

    interrupted, described, ref = asyncio.run(scenario())
    assert interrupted is True
    assert described == Path(ref).stem[:40]


def test_sessions_are_listed_from_disk(backend: PiBackend) -> None:
    async def scenario() -> list[dict]:
        try:
            await backend.create_session("one")
            await backend.create_session("two")
            return await backend.list_sessions()
        finally:
            await backend.aclose()

    listed = asyncio.run(scenario())
    assert len(listed) == 2
    assert all(item["id"].endswith(".jsonl") for item in listed)


def test_idle_reaping_closes_the_child_and_keeps_the_file(backend: PiBackend) -> None:
    async def scenario() -> tuple[bool, bool]:
        try:
            ref = await backend.create_session("hello")
            node = backend._procs[ref]
            await asyncio.sleep(0.3)
            await backend._reap()
            return node.proc.returncode is not None, Path(ref).exists()
        finally:
            await backend.aclose()

    reaped, file_kept = asyncio.run(scenario())
    assert reaped is True
    assert file_kept is True
