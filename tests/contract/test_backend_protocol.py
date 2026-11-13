"""Both adapters honour the same contract (``specs/003-unified-backend/contracts/backend.md``).

The point is not to test either harness again: it is to prove the Telegram layer
can be written once. Each adapter is driven through the same scripted turn.
"""

from __future__ import annotations

import asyncio

import httpx

from app.backends.base import Backend
from app.backends.opencode.backend import OpenCodeBackend
from app.backends.opencode.client import OpenCodeClient
from app.backends.opencode.events import EventBus
from app.backends.pi.backend import PiBackend
from app.backends.pi.rpc import PiRpc
from tests.fakes.opencode import FakeOpenCode
from tests.unit.test_pi_backend import _executable


def _opencode() -> OpenCodeBackend:
    bus = EventBus()
    server = FakeOpenCode(bus=bus)
    client = OpenCodeClient("http://fake.local", "pw", transport=httpx.MockTransport(server.handler))
    return OpenCodeBackend(client, bus=bus)


def _pi(tmp_path) -> PiBackend:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    rpc = PiRpc(
        binary=str(_executable(tmp_path)),
        provider="p",
        model="m",
        session_dir=sessions,
        workspace=tmp_path,
    )
    return PiBackend(rpc, session_dir=sessions, run_timeout=10)


def _built(tmp_path) -> list[tuple[str, Backend]]:
    return [("opencode", _opencode()), ("pi", _pi(tmp_path))]


def test_adapters_expose_the_same_shape(tmp_path) -> None:
    for name, backend in _built(tmp_path):
        assert isinstance(backend, Backend), name
        assert backend.name == name


def test_same_scripted_turn_on_both(tmp_path) -> None:
    async def run(backend: Backend) -> dict[str, object]:
        await backend.start()
        ref = await backend.create_session("conv")
        deltas: list[str] = []

        async def sink(delta: str) -> None:
            deltas.append(delta)

        outcome = await backend.run(ref, "hello", on_delta=sink)
        stats = await backend.context_usage(ref)
        await backend.aclose()
        return {"ref": ref, "deltas": "".join(deltas), "outcome": outcome, "usage": stats}

    for _, backend in _built(tmp_path):
        result = asyncio.run(run(backend))
        assert result["ref"]
        assert "Hello" in result["deltas"]
        assert result["outcome"].error is None
        assert result["usage"]["used_tokens"] is None or result["usage"]["used_tokens"] >= 0


def test_capabilities_are_declared_not_guessed(tmp_path) -> None:
    flags = {name: (b.supports_agents, b.supports_permissions, b.supports_forms) for name, b in _built(tmp_path)}
    assert flags["opencode"] == (True, True, True)
    assert flags["pi"] == (False, False, False)


async def test_tool_activity_reaches_the_hook() -> None:
    """The status line needs to know which tool is running, not just that it is."""

    bus = EventBus()
    server = FakeOpenCode(bus=bus)
    server.tool_calls = ["shell"]
    client = OpenCodeClient("http://fake.local", "pw", transport=httpx.MockTransport(server.handler))
    backend = OpenCodeBackend(client, bus=bus)

    seen: list[str | None] = []

    async def on_activity(label: str | None) -> None:
        seen.append(label)

    await backend.run("ses_activity", "go", on_activity=on_activity)

    assert "shell" in seen
    assert seen[-1] is None, "the label must clear when the tool finishes"
