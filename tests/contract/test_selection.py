from __future__ import annotations

import httpx

from app.opencode.client import OpenCodeClient
from tests.fakes.opencode import FakeOpenCode


def build(fake: FakeOpenCode) -> OpenCodeClient:
    return OpenCodeClient(
        "http://fake.local", "pw", transport=httpx.MockTransport(fake.handler)
    )


async def test_model_selection_payload() -> None:
    fake = FakeOpenCode()
    client = build(fake)
    await client.set_model("ses_1", "go", "flash")
    assert fake.model_calls == [("ses_1", "go", "flash")]
    await client.aclose()


async def test_agent_selection_payload() -> None:
    fake = FakeOpenCode()
    client = build(fake)
    await client.set_agent("ses_1", "plan")
    assert fake.agent_calls == [("ses_1", "plan")]
    await client.aclose()


async def test_catalogues_are_unwrapped() -> None:
    fake = FakeOpenCode()
    client = build(fake)
    models = await client.models()
    agents = await client.agents()
    assert models[0]["modelID"] == "flash"
    assert [agent["id"] for agent in agents] == ["build", "plan"]
    await client.aclose()
