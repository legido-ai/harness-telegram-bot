from __future__ import annotations

from app.telegram.identity import attribution_prefix, build_prompt
from app.telegram.trigger import Trigger
from app.telegram.types import Quoted
from tests.factories import inbound


def test_prompt_names_the_speaker() -> None:
    message = inbound(user_id=111, display_name="Ana")
    prompt = build_prompt(message, Trigger(kind="mention", text="check the build"), ["Ana", "Luis"])
    assert "[speaker] name: Ana | telegram_id: 111" in prompt
    assert "check the build" in prompt
    assert "participants: Ana, Luis" in prompt


def test_prompt_marks_quoted_context() -> None:
    quote = Quoted(message_id=3, author_id=222, author_name="Luis", text="the deploy failed")
    message = inbound(quote=quote)
    prompt = build_prompt(message, Trigger(kind="reply", text="why?", quote=quote), ["Ana", "Luis"])
    assert "[quoted] author: Luis" in prompt
    assert "the deploy failed" in prompt


def test_prompt_is_bounded() -> None:
    message = inbound()
    huge = "x" * 5000
    prompt = build_prompt(message, Trigger(kind="mention", text=huge), ["Ana"])
    assert len(prompt) <= 2000


def test_attribution_only_when_several_humans() -> None:
    message = inbound(display_name="Ana")
    assert attribution_prefix(message, 1) == ""
    assert attribution_prefix(message, 2) == "Ana:"
