"""Streaming answers: coalesced edits, safe splitting, no rate-limit surprises."""

from __future__ import annotations

import html
import time
from collections.abc import Awaitable, Callable

LIMIT = 4096
ATTRIBUTION_LIMIT = 12


def escape(text: str) -> str:
    return html.escape(text, quote=False)


def split_message(text: str, limit: int = LIMIT) -> list[str]:
    """Split on paragraph, then line, then hard boundary, always under ``limit``."""

    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return [chunk for chunk in chunks if chunk]


class _Clock:
    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now

    def __call__(self) -> float:
        return self._now()


class StreamEditor:
    """Turn a growing answer into as few Telegram API calls as possible."""

    def __init__(
        self,
        send: Callable[..., Awaitable[int]],
        edit: Callable[..., Awaitable[None]],
        chat_id: int,
        *,
        thread_id: int = 0,
        reply_to: int | None = None,
        min_interval: float = 1.0,
        now: Callable[[], float] = time.monotonic,
        prefix: str = "",
    ) -> None:
        self._send = send
        self._edit = edit
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._reply_to = reply_to
        self._interval = min_interval
        self._now = _Clock(now)
        self._prefix = prefix
        self._buffer = ""
        self._sent: list[str] = []
        self._message_ids: list[int] = []
        self._last_edit = 0.0
        self._started = False

    @property
    def text(self) -> str:
        return self._buffer

    @property
    def message_ids(self) -> list[int]:
        return list(self._message_ids)

    def append(self, delta: str) -> None:
        self._buffer += delta

    def _compose(self, index: int) -> str:
        chunks = split_message(self._buffer)
        if not chunks:
            return ""
        chunk = chunks[min(index, len(chunks) - 1)]
        if index == 0 and self._prefix:
            return f"{self._prefix}\n{chunk}"
        return chunk

    def _due(self) -> bool:
        return self._now() - self._last_edit >= self._interval

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        text = self._compose(0) or "…"
        message_id = await self._send(
            self._chat_id, text, thread_id=self._thread_id, reply_to=self._reply_to
        )
        self._message_ids.append(message_id)
        self._sent.append(text)
        self._last_edit = self._now()

    async def flush(self, *, force: bool = False) -> None:
        if not self._started:
            await self.start()
            if not force:
                return
        if not force and not self._due():
            return

        chunks = split_message(self._buffer) or ["…"]
        for index, chunk in enumerate(chunks):
            rendered = f"{self._prefix}\n{chunk}" if index == 0 and self._prefix else chunk
            if index < len(self._message_ids):
                if index < len(self._sent) and self._sent[index] == rendered:
                    continue
                await self._edit(self._chat_id, self._message_ids[index], rendered)
                self._sent[index] = rendered
            else:
                message_id = await self._send(
                    self._chat_id, rendered, thread_id=self._thread_id, reply_to=self._reply_to
                )
                self._message_ids.append(message_id)
                self._sent.append(rendered)
        self._last_edit = self._now()

    async def finish(self, footer: str = "") -> None:
        if footer:
            self._buffer = f"{self._buffer.rstrip()}\n\n{footer}" if self._buffer.strip() else footer
        await self.flush(force=True)
