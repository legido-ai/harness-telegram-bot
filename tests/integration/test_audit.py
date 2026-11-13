from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.health import create_app
from app.telegram.app import BotApp
from tests.helpers import wait_for
from tests.telegram_factory import BOT_ID, BOT_USERNAME, update


async def test_operator_can_see_who_asked(
    settings, store, backend, runner, health, messenger
) -> None:
    app = BotApp(settings=settings, store=store, backend=backend, runner=runner, state=health)
    app.bot_id = BOT_ID
    app.bot_username = BOT_USERNAME
    app.messenger = messenger
    runner.set_messenger(messenger)

    await app.on_message(
        update("deploy please", chat_type="private", chat_id=111, update_id=11),
        SimpleNamespace(bot=None),
    )
    await wait_for(
        lambda: bool(store.recent_turns(1)) and store.recent_turns(1)[0].session_id is not None
    )

    api = TestClient(create_app(settings, store, health))
    payload = api.get("/audit?limit=5").json()
    entry = payload["turns"][0]
    assert entry["user_id"] == 111
    assert entry["user"] == "Ana"
    assert entry["session_id"]
    assert "text" not in entry
    assert "deploy please" not in str(payload)
