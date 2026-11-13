from __future__ import annotations

from app.telegram.streaming import StreamEditor, escape, split_message
from tests.fakes.telegram import FakeMessenger


def test_split_respects_limit_and_boundaries() -> None:
    text = ("paragraph one\n\n" * 500).strip()
    chunks = split_message(text, limit=200)
    assert chunks
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert all(chunk for chunk in chunks)


def test_split_short_text_is_single_chunk() -> None:
    assert split_message("hello") == ["hello"]


def test_escape_neutralises_html() -> None:
    assert escape("<b>x</b> & y") == "&lt;b&gt;x&lt;/b&gt; &amp; y"


async def test_editor_coalesces_edits() -> None:
    messenger = FakeMessenger()
    clock = {"now": 100.0}

    def now() -> float:
        return clock["now"]

    editor = StreamEditor(
        messenger.send_text, messenger.edit_text, chat_id=1, min_interval=1.0, now=now
    )
    await editor.start()
    assert messenger.sent == []  # nothing is sent while the agent thinks

    editor.append("hello")
    await editor.flush()
    assert len(messenger.sent) == 1
    clock["now"] += 0.1
    editor.append(" world")
    await editor.flush()
    # Too soon: no edit yet.
    assert messenger.edited == []

    clock["now"] += 1.5
    await editor.flush()
    assert messenger.edited
    assert "hello world" in messenger.last_text


async def test_editor_splits_growing_answer_into_new_messages() -> None:
    messenger = FakeMessenger()
    editor = StreamEditor(
        messenger.send_text, messenger.edit_text, chat_id=1, min_interval=0.0, now=lambda: 0.0
    )
    await editor.start()
    editor.append("y" * 9000)
    await editor.flush(force=True)
    assert len(messenger.sent) >= 3
    assert all(len(sent.text) <= 4096 for sent in messenger.sent)


async def test_deferred_editor_shows_only_the_filtered_final_text() -> None:
    messenger = FakeMessenger()
    editor = StreamEditor(
        messenger.send_text,
        messenger.edit_text,
        chat_id=1,
        min_interval=0.0,
        now=lambda: 0.0,
        defer_until_finish=True,
    )
    await editor.start()
    editor.append("No puedo generar audio.")
    await editor.flush()
    assert messenger.sent == []

    editor.replace('"Small steps still move you forward."')
    await editor.finish()
    assert [sent.text for sent in messenger.sent] == [
        '"Small steps still move you forward."'
    ]


async def test_editor_prefixes_attribution_once() -> None:
    messenger = FakeMessenger()
    editor = StreamEditor(
        messenger.send_text,
        messenger.edit_text,
        chat_id=1,
        min_interval=0.0,
        now=lambda: 0.0,
        prefix="Ana:",
    )
    await editor.start()
    editor.append("answer")
    await editor.flush(force=True)
    assert messenger.last_text.startswith("Ana:\nanswer")


async def test_status_line_rides_under_the_answer() -> None:
    messenger = FakeMessenger()
    clock = {"now": 0.0}
    editor = StreamEditor(
        messenger.send_text,
        messenger.edit_text,
        chat_id=1,
        min_interval=1.0,
        markdown=True,
        now=lambda: clock["now"],
    )
    await editor.start()
    editor.append("I'll investigate the deployment first.")
    await editor.flush(force=True)

    clock["now"] += 5.0
    await editor.status("⏳ Working… 12s · shell")
    assert "I'll investigate the deployment first." in messenger.last_text
    assert "Working… 12s · shell" in messenger.last_text

    # The counter keeps moving even though the answer itself stopped growing.
    clock["now"] += 5.0
    await editor.status("⏳ Working… 17s · shell")
    assert "Working… 17s" in messenger.last_text
    assert "I'll investigate the deployment first." in messenger.last_text

    # No trailing status in the finished answer.
    clock["now"] += 5.0
    await editor.finish()
    assert "Working" not in messenger.last_text
    assert "I'll investigate the deployment first." in messenger.last_text


async def test_status_before_any_text_is_the_whole_bubble() -> None:
    messenger = FakeMessenger()
    editor = StreamEditor(
        messenger.send_text, messenger.edit_text, chat_id=1, min_interval=0.0, now=lambda: 0.0
    )
    await editor.start()
    await editor.status("⏳ Working… 9s")

    assert len(messenger.sent) == 1
    assert messenger.sent[0].text == "⏳ Working… 9s"

    editor.append("done")
    await editor.flush(force=True)
    assert "done" in messenger.last_text
    assert "Working" in messenger.last_text  # still running until finish()
