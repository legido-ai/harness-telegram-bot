"""The chat must look alive for the whole turn, not just until the first token."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from app.telegram.streaming import StreamEditor
from tests.fakes.telegram import FakeMessenger


async def test_status_loop_keeps_the_counter_moving_after_text(monkeypatch, runner) -> None:
    import app.telegram.runner as runner_module

    monkeypatch.setattr(runner_module, "STATUS_AFTER", 0.0)
    monkeypatch.setattr(runner_module, "STATUS_INTERVAL", 0.01)

    messenger = FakeMessenger()
    editor = StreamEditor(
        messenger.send_text, messenger.edit_text, chat_id=1, min_interval=0.0, now=lambda: 0.0
    )
    await editor.start()
    editor.append("Checking the existing deployments.")
    await editor.flush(force=True)

    stop = asyncio.Event()
    activity: dict[str, str | None] = {"label": "shell"}
    task = asyncio.create_task(
        runner._status_loop(editor, time.monotonic() - 30.0, stop, activity)
    )
    await asyncio.sleep(0.05)
    stop.set()
    await task

    assert messenger.edited, "the status must still update once the answer exists"
    assert any("Working" in edit.text for edit in messenger.edited)
    assert any("shell" in edit.text for edit in messenger.edited)
    assert any("Checking the existing deployments." in edit.text for edit in messenger.edited)

    await editor.finish()
    assert "Working" not in messenger.last_text


async def test_typing_loop_outlives_the_first_bubble(monkeypatch, runner, messenger) -> None:
    message = SimpleNamespace(chat_id=111, thread_id=0)
    stop = asyncio.Event()

    # A bubble already exists: the old loop returned here and the chat went
    # silent for the rest of the turn.
    editor = StreamEditor(
        messenger.send_text, messenger.edit_text, chat_id=111, min_interval=0.0
    )
    await editor.start()
    editor.append("hello")
    await editor.flush(force=True)

    task = asyncio.create_task(runner._typing_loop(message, stop))
    await asyncio.sleep(0.05)
    stop.set()
    await task

    assert messenger.typing, "the chat action must keep being refreshed mid-turn"
    assert all(chat_id == 111 for chat_id, _ in messenger.typing)
