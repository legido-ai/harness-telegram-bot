from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.app import BotApp
from tests.helpers import wait_for
from tests.telegram_factory import BOT_ID, BOT_USERNAME, callback_update, update

MENTION = [{"type": "mention", "offset": 0, "length": 7}]


@pytest.fixture
def bot_app(settings, store, client, runner, health, messenger) -> BotApp:
    app = BotApp(settings=settings, store=store, client=client, runner=runner, state=health)
    app.bot_id = BOT_ID
    app.bot_username = BOT_USERNAME
    app.messenger = messenger
    runner.set_messenger(messenger)
    runner.set_interaction_hook(app.on_interaction)
    return app


async def send(bot_app: BotApp, telegram_update) -> None:
    await bot_app.on_message(telegram_update, SimpleNamespace(bot=None))


async def test_topics_keep_separate_sessions(bot_app: BotApp, fake_server, store) -> None:
    await send(bot_app, update("@oc3bot alpha task", entities=MENTION, thread_id=5, update_id=1))
    await send(bot_app, update("@oc3bot beta task", entities=MENTION, thread_id=9, update_id=2))
    await wait_for(lambda: len(fake_server.prompts) == 2)

    alpha = store.get_conversation(-100123, 5).active_session_id
    beta = store.get_conversation(-100123, 9).active_session_id
    assert alpha and beta and alpha != beta


async def test_model_choice_is_stored_and_applied(bot_app: BotApp, fake_server, messenger, store) -> None:
    await send(bot_app, update("@oc3bot hello", entities=MENTION, update_id=1))
    await wait_for(lambda: len(fake_server.prompts) == 1)
    session_id = store.get_conversation(-100123, 0).active_session_id

    await bot_app._cmd_model(bot_app._inbound(update("/model", update_id=79)), "")
    menu = next(
        item for item in messenger.sent if hasattr(item.keyboard, "inline_keyboard")
    )
    button = menu.keyboard.inline_keyboard[0][0]
    token = button.callback_data.split(":")[1]
    await bot_app.on_callback(callback_update(f"m:{token}", update_id=80), SimpleNamespace(bot=None))
    await wait_for(lambda: len(fake_server.model_calls) == 1)

    assert fake_server.model_calls[0] == (session_id, "go", "flash")
    assert store.get_conversation(-100123, 0).model == {"providerID": "go", "modelID": "flash"}
    assert any("Model set to go/flash" in item.text for item in messenger.sent)
    latest = [item for item in messenger.sent if item.keyboard is not None][-1]
    assert latest.keyboard.keyboard[0][0].text == "🧠 go/flash"


async def test_agent_choice_is_stored(bot_app: BotApp, fake_server, store, messenger) -> None:
    await send(bot_app, update("@oc3bot hello", entities=MENTION, update_id=1))
    await wait_for(lambda: len(fake_server.prompts) == 1)
    await bot_app._cmd_agent(bot_app._inbound(update("/agent", update_id=80)), "")
    menu = next(
        item for item in messenger.sent if hasattr(item.keyboard, "inline_keyboard")
    )
    button = next(
        b for row in menu.keyboard.inline_keyboard for b in row if b.text == "plan"
    )
    token = button.callback_data.split(":")[1]
    await bot_app.on_callback(callback_update(f"a:{token}", update_id=81), SimpleNamespace(bot=None))
    await wait_for(lambda: len(fake_server.agent_calls) == 1)
    assert store.get_conversation(-100123, 0).agent == "plan"


async def test_new_session_with_a_chosen_model(bot_app, store, fake_server) -> None:
    store.touch_conversation(111, 0, "private", None)
    store.set_model(111, 0, {"providerID": "go", "modelID": "flash"})
    inbound = bot_app._inbound(update("/new", chat_type="private", chat_id=111, update_id=131))
    await bot_app._cmd_new(inbound, "")
    conversation = store.get_conversation(111, 0)
    assert conversation.active_session_id is not None
    assert conversation.active_session_id in fake_server.sessions
