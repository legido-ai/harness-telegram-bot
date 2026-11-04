from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.app import BotApp
from tests.helpers import wait_for
from tests.telegram_factory import BOT_ID, BOT_USERNAME, update


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
    context = SimpleNamespace(bot=None)
    await bot_app.on_message(telegram_update, context)


async def test_prompt_is_answered_from_a_private_chat(
    bot_app: BotApp, messenger, store, fake_server
) -> None:
    await send(bot_app, update("run the tests", chat_type="private", chat_id=111, update_id=1))

    await wait_for(lambda: any("Hello" in e.text for e in messenger.edited or messenger.sent))
    assert fake_server.prompts
    _session, prompt, metadata = fake_server.prompts[0]
    assert "[speaker] name: Ana" in prompt
    assert metadata["telegram"]["user_id"] == 111
    assert store.recent_turns(1)[0].status in ("succeeded", "running")


async def test_second_prompt_reuses_the_session(bot_app: BotApp, fake_server, messenger) -> None:
    await send(bot_app, update("first", chat_type="private", chat_id=111, update_id=1))
    await wait_for(lambda: len(fake_server.prompts) == 1)
    await send(bot_app, update("second", chat_type="private", chat_id=111, update_id=2))
    await wait_for(lambda: len(fake_server.prompts) == 2)

    first_session = fake_server.prompts[0][0]
    second_session = fake_server.prompts[1][0]
    assert first_session == second_session


async def test_abort_interrupts_the_bound_session(bot_app: BotApp, fake_server, store, messenger) -> None:
    await send(bot_app, update("long task", chat_type="private", chat_id=111, update_id=1))
    await wait_for(lambda: len(fake_server.prompts) == 1)

    session_id = store.get_conversation(111, 0).active_session_id
    assert session_id is not None

    message = update("stop", chat_type="private", chat_id=111, update_id=3)
    inbound = bot_app._inbound(message)
    assert await bot_app.runner.abort(inbound) is True
    assert fake_server.interrupts == [session_id]


async def test_unauthorized_user_never_reaches_the_agent(bot_app: BotApp, fake_server, store) -> None:
    await send(bot_app, update("let me in", chat_type="private", chat_id=999, user_id=999, update_id=5))
    await wait_for(lambda: bot_app.authorizer.rejections == 1)
    assert fake_server.prompts == []
    assert store.recent_turns() == []


async def test_duplicate_update_runs_once(bot_app: BotApp, fake_server) -> None:
    telegram_update = update("do it", chat_type="private", chat_id=111, update_id=7)
    await send(bot_app, telegram_update)
    await wait_for(lambda: len(fake_server.prompts) == 1)
    await send(bot_app, telegram_update)
    await wait_for(lambda: bot_app.store.mark_seen(7) is False)
    assert len(fake_server.prompts) == 1


async def test_answer_carries_the_consumption_footer(bot_app: BotApp, messenger) -> None:
    await send(bot_app, update("how are you", chat_type="private", chat_id=111, update_id=41))
    await wait_for(lambda: any("(21%)" in item.text for item in messenger.edited))

    footer_text = messenger.edited[-1].text
    assert "42K/200K (21%)" in footer_text
    assert "$0.03" in footer_text
    assert "flash" in footer_text


async def test_run_updates_and_pins_a_dashboard(bot_app: BotApp, messenger, store) -> None:
    await send(bot_app, update("ping", chat_type="private", chat_id=111, update_id=51))
    await wait_for(lambda: bool(messenger.pinned))

    dashboard = [item for item in messenger.sent if item.text.startswith("📊")]
    assert dashboard, "no dashboard message"
    assert "context 42K/200K (21%)" in dashboard[0].text
    assert store.pinned_message_id(111, 0) == messenger.pinned[0][1]


async def test_second_run_edits_the_same_dashboard(bot_app: BotApp, messenger) -> None:
    await send(bot_app, update("one", chat_type="private", chat_id=111, update_id=61))
    await wait_for(lambda: bool(messenger.pinned))
    pinned_once = len(messenger.pinned)

    await send(bot_app, update("two", chat_type="private", chat_id=111, update_id=62))
    await wait_for(lambda: sum("📊" in item.text for item in messenger.edited) > 0)
    assert len(messenger.pinned) == pinned_once


def test_menu_labels_map_to_commands() -> None:
    from app.telegram.keyboards import menu_command

    assert menu_command("📚 Sessions") == "/sessions"
    assert menu_command("hello") is None
