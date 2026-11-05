from __future__ import annotations

from app.telegram.trigger import detect, slice_entities
from tests.factories import inbound, mention_entity

BOT_ID = 999
BOT_USERNAME = "oc3bot"


def test_private_message_is_always_addressed() -> None:
    message = inbound(chat_type="private", chat_id=111, text="run the tests")
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "private"
    assert trigger.text == "run the tests"


def test_group_message_is_addressed_by_mention() -> None:
    message = inbound(text="@oc3bot summarise", entities=(mention_entity("@oc3bot summarise"),))
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "mention"
    assert trigger.text == "summarise"


def test_mention_stripping_handles_utf16_offsets() -> None:
    text = "😀 @oc3bot hi there"
    entity = mention_entity(text, prefix="😀 ")
    cleaned = slice_entities(text, (entity,))
    assert "@oc3bot" not in cleaned
    assert cleaned == "😀 hi there"


def test_group_chatter_is_ignored() -> None:
    message = inbound(text="did you see the deploy?")
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None


def test_reply_to_bot_is_addressed() -> None:
    from app.telegram.types import Quoted

    message = inbound(
        text="and then?",
        quote=Quoted(message_id=4, author_id=BOT_ID, author_name="OC3 bot", text="done", is_bot=True),
    )
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "reply"


def test_mention_only_asks_for_a_request() -> None:
    message = inbound(text="@oc3bot", entities=(mention_entity("@oc3bot"),))
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "empty"
    assert not trigger.has_prompt


def test_quoted_mention_does_not_trigger() -> None:
    from app.telegram.types import Quoted

    # The human quotes a previous message that contains the mention: the bot
    # must not treat its own name in quoted text as an address.
    quoted = Quoted(message_id=3, author_id=222, author_name="Luis", text="@oc3bot deploy this")
    message = inbound(text="look at this", quote=quoted, entities=())
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None


def test_bot_authored_message_is_ignored() -> None:
    message = inbound(text="@oc3bot hi", entities=(mention_entity("@oc3bot hi"),), is_bot=True)
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None


def test_command_for_another_bot_is_ignored() -> None:
    from app.telegram.types import Entity

    text = "/new@otherbot"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(text=text, entities=(entity,))
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None


def test_command_for_this_bot_is_detected() -> None:
    from app.telegram.types import Entity

    text = "/new@oc3bot"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(text=text, entities=(entity,))
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "command"
    assert trigger.text == "/new"


def test_policy_all_answers_chatter() -> None:
    message = inbound(text="standup notes")
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME, policy="all")
    assert trigger is not None
    assert trigger.kind == "policy_all"


def test_private_slash_command_is_a_command_not_a_prompt() -> None:
    from app.telegram.types import Entity

    text = "/id"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(chat_type="private", chat_id=111, text=text, entities=(entity,))
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "command"
    assert trigger.text == "/id"


def test_private_command_for_another_bot_is_ignored() -> None:
    from app.telegram.types import Entity

    text = "/id@otherbot"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(chat_type="private", chat_id=111, text=text, entities=(entity,))
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None


def test_bare_command_is_accepted_in_groups_when_it_is_ours() -> None:
    from app.telegram.types import Entity

    text = "/new"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(text=text, entities=(entity,))
    trigger = detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert trigger is not None
    assert trigger.kind == "command"
    assert trigger.text == "/new"


def test_bare_command_of_another_bot_is_ignored() -> None:
    from app.telegram.types import Entity

    text = "/deploy"
    entity = Entity(type="bot_command", offset=0, length=len(text))
    message = inbound(text=text, entities=(entity,))
    assert detect(message, bot_id=BOT_ID, bot_username=BOT_USERNAME) is None
