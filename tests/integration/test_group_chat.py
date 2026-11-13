from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.app import BotApp
from tests.helpers import wait_for
from tests.telegram_factory import BOT_ID, BOT_USERNAME, message_payload, update

MENTION = [{"type": "mention", "offset": 0, "length": 7}]


@pytest.fixture
def bot_app(settings, store, backend, runner, health, messenger) -> BotApp:
    app = BotApp(settings=settings, store=store, backend=backend, runner=runner, state=health)
    app.bot_id = BOT_ID
    app.bot_username = BOT_USERNAME
    app.messenger = messenger
    runner.set_messenger(messenger)
    runner.set_interaction_hook(app.on_interaction)
    return app


async def send(bot_app: BotApp, telegram_update) -> None:
    await bot_app.on_message(telegram_update, SimpleNamespace(bot=None))


async def register_second_human(bot_app: BotApp, update_id: int = 1) -> None:
    await send(
        bot_app,
        update(
            "morning both",
            user_id=222,
            first_name="Luis",
            update_id=update_id,
            chat_id=-100123,
            chat_type="supergroup",
        ),
    )


async def test_mention_triggers_and_is_attributed(
    bot_app: BotApp, messenger, fake_server, store
) -> None:
    await register_second_human(bot_app)
    await send(
        bot_app,
        update(
            "@oc3bot summarise the thread",
            entities=MENTION,
            user_id=111,
            first_name="Ana",
            update_id=2,
        ),
    )

    await wait_for(lambda: any("Hello" in item.text for item in messenger.edited) or len(fake_server.prompts) == 1)
    await wait_for(lambda: any(e.text.startswith("Ana:") for e in messenger.edited))
    prompt = fake_server.prompts[0][1]
    assert prompt.endswith("summarise the thread")
    assert "@oc3bot" not in prompt
    assert store.recent_turns(1)[0].user_id == 111


async def test_chatter_between_humans_stays_silent(bot_app: BotApp, fake_server, messenger) -> None:
    await register_second_human(bot_app)
    await send(bot_app, update("did you see the deploy?", user_id=111, update_id=2))
    await wait_for(lambda: len(bot_app.store.roster()) >= 2)
    assert fake_server.prompts == []
    assert messenger.sent == []


async def test_reply_to_bot_continues_the_same_session(bot_app: BotApp, fake_server) -> None:
    await send(bot_app, update("@oc3bot first", entities=MENTION, user_id=111, update_id=1))
    await wait_for(lambda: len(fake_server.prompts) == 1)

    bot_message = message_payload(
        text="done", chat_id=-100123, user_id=BOT_ID, first_name="OC3 bot", message_id=77, is_bot=True
    )
    await send(
        bot_app,
        update(
            "and then?",
            user_id=111,
            update_id=2,
            reply_to=bot_message,
        ),
    )
    await wait_for(lambda: len(fake_server.prompts) == 2)
    assert fake_server.prompts[0][0] == fake_server.prompts[1][0]


async def test_both_humans_are_answered_in_arrival_order(bot_app: BotApp, fake_server) -> None:
    await send(
        bot_app,
        update("@oc3bot from Ana", entities=MENTION, user_id=111, first_name="Ana", update_id=1),
    )
    await send(
        bot_app,
        update("@oc3bot from Luis", entities=MENTION, user_id=222, first_name="Luis", update_id=2),
    )
    await wait_for(lambda: len(fake_server.prompts) == 2)
    assert fake_server.prompts[0][1].endswith("from Ana")
    assert fake_server.prompts[1][1].endswith("from Luis")


async def test_group_message_from_another_bot_is_ignored(bot_app: BotApp, fake_server) -> None:
    await send(
        bot_app,
        update(
            "@oc3bot ping",
            entities=MENTION,
            user_id=333,
            first_name="Other bot",
            is_bot=True,
            update_id=1,
        ),
    )
    await wait_for(lambda: bot_app.authorizer.rejections >= 0)
    assert fake_server.prompts == []


async def test_trigger_policy_all_can_be_enabled_by_the_operator(
    bot_app: BotApp, fake_server
) -> None:
    await send(
        bot_app,
        update("/trigger@oc3bot all", entities=[{"type": "bot_command", "offset": 0, "length": 15}], update_id=1),
    )
    await wait_for(
        lambda: bot_app.store.get_conversation(-100123, 0).trigger_policy == "all"
    )
    await send(bot_app, update("plain chatter", update_id=2))
    await wait_for(lambda: len(fake_server.prompts) == 1)
