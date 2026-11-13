from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.backends.opencode.backend import OpenCodeBackend
from app.backends.opencode.client import OpenCodeClient
from app.backends.opencode.events import EventBus
from app.config import Settings
from app.health import HealthState
from app.store import Store
from app.telegram.runner import Runner
from tests.fakes.opencode import FakeOpenCode
from tests.fakes.telegram import FakeMessenger


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456:TESTTOKENVALUE",
            "TELEGRAM_ALLOWED_USER_IDS": "111,222",
            "OPENCODE_SERVER_PASSWORD": "server-secret-value",
            "DATA_DIR": str(tmp_path / "data"),
            "TELEGRAM_TRIGGER": "mention",
            "TTS_PROVIDER": "edge",
            "TTS_VOICE": "es-ES-ElviraNeural",
            "TTS_VOICE_AUDIO": "en-US-AriaNeural",
        }
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "state.db")
    store.migrate()
    return store


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def fake_server(bus: EventBus) -> FakeOpenCode:
    return FakeOpenCode(bus=bus)


@pytest.fixture
def client(fake_server: FakeOpenCode) -> OpenCodeClient:
    return OpenCodeClient(
        "http://fake.local",
        "server-secret-value",
        transport=httpx.MockTransport(fake_server.handler),
    )


@pytest.fixture
def messenger() -> FakeMessenger:
    return FakeMessenger()


@pytest.fixture
def backend(client: OpenCodeClient, bus: EventBus) -> OpenCodeBackend:
    return OpenCodeBackend(client, bus=bus)


@pytest.fixture
def runner(
    settings: Settings, store: Store, backend: OpenCodeBackend, messenger: FakeMessenger
) -> Runner:
    return Runner(settings=settings, store=store, backend=backend, messenger=messenger)


@pytest.fixture
def health() -> HealthState:
    return HealthState()
