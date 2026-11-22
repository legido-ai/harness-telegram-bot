from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.app import BotApp
from tests.telegram_factory import BOT_ID, BOT_USERNAME, callback_update, update


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


def cmd(text: str, **kwargs):
    """A real Telegram update carries a bot_command entity; the factory does not."""

    head = len(text.split(" ", 1)[0])
    return update(text, entities=[{"type": "bot_command", "offset": 0, "length": head}], **kwargs)


def seed(store, *, chat_id: int = -100123, thread_id: int = 0) -> None:
    store.touch_conversation(chat_id, thread_id, "supergroup", "OC3 build")


def bind(fake_server, store, session_id: str, title: str, *, chat_id: int = -100123) -> None:
    fake_server.sessions[session_id] = {"id": session_id, "title": title}
    store.bind_session(chat_id, 0, session_id, title, bound_by=111)


def listing(messenger) -> str:
    return next(item.text for item in reversed(messenger.sent) if item.text.startswith("📋"))


async def test_sessions_lists_numbered_with_current_marker(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")

    await send(bot_app, cmd("/sessions", update_id=1))

    text = listing(messenger)
    assert "1. Write docs (current)" in text
    assert "2. Nightly build" in text
    assert text.count("ses_") == 0  # only the six-character short id is shown
    assert "/sessions <number>" in text


async def test_resume_by_number_switches_and_persists(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")
    await send(bot_app, cmd("/sessions", update_id=1))

    await send(bot_app, cmd("/sessions 2", update_id=2))

    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"
    assert any('↻ Resumed session "Nightly build"' in item.text for item in messenger.sent)


async def test_resume_by_id_and_suffix(bot_app, fake_server, store) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")

    await send(bot_app, cmd("/sessions ses_aaaaaa111111", update_id=1))
    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"

    await send(bot_app, cmd("/sessions 222222", update_id=2))
    assert store.get_conversation(-100123, 0).active_session_id == "ses_bbbbbb222222"


async def test_resume_alias_and_title(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")

    await send(bot_app, cmd("/title Deploy staging", update_id=1))
    assert store.binding_title(-100123, 0, "ses_bbbbbb222222") == "Deploy staging"
    assert any('Session titled "Deploy staging"' in item.text for item in messenger.sent)

    await send(bot_app, cmd("/resume Nightly build", update_id=2))
    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"


async def test_title_without_session_explains(bot_app, store, messenger) -> None:
    await send(bot_app, cmd("/title late", update_id=1))
    assert any("no session yet" in item.text for item in messenger.sent)


async def test_switch_alias_still_works(bot_app, fake_server, store) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")
    await send(bot_app, cmd("/sessions", update_id=0))

    await send(bot_app, cmd("/switch 2", update_id=1))
    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"


async def test_search_filters_and_numbers_resolve_against_it(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")

    await send(bot_app, cmd("/sessions search docs", update_id=1))
    text = listing(messenger)
    assert 'Sessions matching "docs"' in text
    assert "Write docs" in text and "Nightly build" not in text

    await send(bot_app, cmd("/sessions 1", update_id=2))
    assert store.get_conversation(-100123, 0).active_session_id == "ses_bbbbbb222222"


async def test_search_without_a_query_shows_usage(bot_app, messenger) -> None:
    await send(bot_app, cmd("/sessions search", update_id=1))
    assert any("Usage: /sessions search" in item.text for item in messenger.sent)


async def test_out_of_range_and_unknown_are_explained(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    await send(bot_app, cmd("/sessions", update_id=0))

    await send(bot_app, cmd("/sessions 9", update_id=1))
    await send(bot_app, cmd("/sessions nowhere", update_id=2))
    assert any("no session 9" in item.text for item in messenger.sent)
    assert any('No session here matches "nowhere"' in item.text for item in messenger.sent)


async def test_gone_session_is_not_bound(bot_app, store, messenger) -> None:
    seed(store)
    store.bind_session(-100123, 0, "ses_gone", "Gone", bound_by=111)
    store.bind_session(-100123, 0, "ses_alive", "Alive", bound_by=111)

    await send(bot_app, cmd("/sessions Gone", update_id=1))
    assert any("no longer exists" in item.text for item in messenger.sent)
    assert store.get_conversation(-100123, 0).active_session_id == "ses_alive"


async def test_busy_conversation_refuses_the_switch(bot_app, fake_server, store, messenger, runner) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")
    runner._active_session[(-100123, 0)] = "ses_bbbbbb222222"
    await send(bot_app, cmd("/sessions", update_id=0))

    await send(bot_app, cmd("/sessions 2", update_id=1))
    assert any("/abort" in item.text for item in messenger.sent)
    assert store.get_conversation(-100123, 0).active_session_id == "ses_bbbbbb222222"


async def test_repeated_switch_lists_a_session_once(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")
    await send(bot_app, cmd("/sessions", update_id=0))

    await send(bot_app, cmd("/sessions 2", update_id=1))
    await send(bot_app, cmd("/sessions 1", update_id=2))
    await send(bot_app, cmd("/sessions 2", update_id=3))
    await send(bot_app, cmd("/sessions", update_id=4))

    text = listing(messenger)
    assert text.count("Nightly build") == 1
    assert text.count("Write docs") == 1


async def test_non_admin_all_gets_scoped_list_and_notice(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_other"] = {"id": "ses_other", "title": "Other chat"}
    store.bind_session(777, 0, "ses_other", "Other chat", bound_by=111)

    await send(bot_app, cmd("/sessions all", user_id=222, update_id=1))

    text = listing(messenger)
    assert "Other chat" not in text
    assert "admin-only" in text


async def test_admin_all_shows_other_chats_and_unassigned(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_other1"] = {"id": "ses_other1", "title": "Other chat"}
    store.bind_session(777, 0, "ses_other1", "Other chat", bound_by=111)
    fake_server.sessions["ses_lost11"] = {"id": "ses_lost11", "title": "Orphan"}

    await send(bot_app, cmd("/sessions all", user_id=111, update_id=1))

    text = listing(messenger)
    assert "Sessions (all chats)" in text
    assert "Other chat" in text
    assert "Orphan" in text
    assert "unassigned" in text


async def test_admin_can_resume_an_unassigned_session(bot_app, fake_server, store) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_lost11"] = {"id": "ses_lost11", "title": "Orphan"}

    await send(bot_app, cmd("/sessions all", user_id=111, update_id=1))
    await send(bot_app, cmd("/sessions Orphan", user_id=111, update_id=2))

    assert store.get_conversation(-100123, 0).active_session_id == "ses_lost11"


async def test_callback_switch_uses_the_same_checks(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Nightly build")
    bind(fake_server, store, "ses_bbbbbb222222", "Write docs")
    await send(bot_app, cmd("/sessions", update_id=1))
    menu = next(item for item in messenger.sent if item.keyboard is not None)
    token = menu.keyboard.inline_keyboard[1][0].callback_data.split(":")[-1]

    await bot_app.on_callback(
        callback_update(f"s:-100123:0:{token}", update_id=2), SimpleNamespace(bot=None)
    )

    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"
    assert messenger.callbacks[-1][1] == "Switched."


async def test_search_never_crosses_chats(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_other_shared"] = {"id": "ses_other_shared", "title": "Other chat"}
    store.bind_session(777, 0, "ses_other_shared", "Other chat", bound_by=111)

    await send(bot_app, cmd("/sessions search shared", user_id=222, update_id=1))

    assert any("No sessions found." in item.text for item in messenger.sent)
    assert not any("Other chat" in item.text for item in messenger.sent)


async def test_one_member_listing_never_drives_another_members_switch(
    bot_app, fake_server, store, messenger
) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_other1"] = {"id": "ses_other1", "title": "Other chat"}
    store.bind_session(777, 0, "ses_other1", "Other chat", bound_by=111)

    await send(bot_app, cmd("/sessions all", user_id=111, update_id=1))
    await send(bot_app, cmd("/sessions 1", user_id=222, update_id=2))

    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"
    assert any("Run /sessions" in item.text for item in messenger.sent)


async def test_ordinal_without_a_recent_listing_is_refused(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    bind(fake_server, store, "ses_bbbbbb222222", "Second")

    await send(bot_app, cmd("/sessions 1", update_id=1))

    assert any("listing has expired" in item.text for item in messenger.sent)
    assert store.get_conversation(-100123, 0).active_session_id == "ses_bbbbbb222222"


async def test_removed_binding_is_not_resumed(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    bind(fake_server, store, "ses_bbbbbb222222", "Second")
    await send(bot_app, cmd("/sessions", user_id=222, update_id=1))
    with store._conn:
        store._conn.execute("DELETE FROM session_bindings WHERE session_id='ses_aaaaaa111111'")

    await send(bot_app, cmd("/sessions 2", user_id=222, update_id=2))

    assert store.get_conversation(-100123, 0).active_session_id == "ses_bbbbbb222222"
    assert any("No session here matches" in item.text for item in messenger.sent)


async def test_callback_cannot_bind_another_chats_session(bot_app, fake_server, store, messenger) -> None:
    seed(store)
    bind(fake_server, store, "ses_aaaaaa111111", "Mine")
    fake_server.sessions["ses_other1"] = {"id": "ses_other1", "title": "Other chat"}
    store.bind_session(777, 0, "ses_other1", "Other chat", bound_by=111)
    token = bot_app._token("s", "ses_other1", "", "")

    await bot_app.on_callback(
        callback_update(f"s:-100123:0:{token}", update_id=1), SimpleNamespace(bot=None)
    )

    assert store.get_conversation(-100123, 0).active_session_id == "ses_aaaaaa111111"
    assert messenger.callbacks[-1][1] == "This control has expired."
