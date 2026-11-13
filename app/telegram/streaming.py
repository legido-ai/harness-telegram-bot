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
        markdown: bool = False,
        defer_until_finish: bool = False,
    ) -> None:
        self._send = send
        self._edit = edit
        self._chat_id = chat_id
        self._thread_id = thread_id
        self._reply_to = reply_to
        self._interval = min_interval
        self._now = _Clock(now)
        self._prefix = prefix
        self._markdown = markdown
        self._defer = defer_until_finish
        self._buffer = ""
        self._status = ""
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

    def replace(self, text: str) -> None:
        """Swap the buffered answer before the final flush (used by filters)."""

        self._buffer = text

    def set_status(self, text: str) -> None:
        """Hold a live status line to show with the answer (``""`` clears it)."""

        self._status = text

    def _body(self) -> str:
        """The answer plus the live status line, as one edit would show it.

        The status rides *under* the answer rather than in a second bubble: a
        turn that spends minutes in tool calls keeps the one message it already
        has and still visibly moves.
        """

        body = self._buffer.strip()
        if not self._status:
            return body
        return f"{body}\n\n{self._status}" if body else self._status

    def _compose(self, index: int) -> str:
        chunks = split_message(self._body())
        if not chunks:
            return ""
        chunk = chunks[min(index, len(chunks) - 1)]
        if index == 0 and self._prefix:
            return f"{self._prefix}\n{chunk}"
        return chunk

    def _due(self) -> bool:
        return self._now() - self._last_edit >= self._interval

    async def start(self) -> None:
        """Mark the answer as open.

        Nothing is sent yet: while the agent is thinking the chat shows the
        typing indicator, not an empty bubble. The first flush creates the
        message.
        """

        self._started = True
        self._last_edit = self._now()

    async def status(self, text: str) -> None:
        """Keep a live status line in the answer's own message.

        Before any text exists the bubble *is* the status. Afterwards the same
        message keeps the streamed answer and the status becomes a trailing
        line, so a long tool-heavy turn is never indistinguishable from a dead
        bot. ``finish()`` clears it.
        """

        if self._defer:
            return
        self.set_status(text)
        if not self._message_ids:
            rendered = self._compose(0)
            if not rendered:
                return
            message_id = await self._send(
                self._chat_id,
                rendered,
                thread_id=self._thread_id,
                reply_to=self._reply_to,
                markdown=self._markdown,
            )
            self._message_ids.append(message_id)
            self._sent.append(rendered)
        else:
            # A long answer spans several messages; the status belongs to the
            # last one, where the reader is looking.
            last = len(self._message_ids) - 1
            rendered = self._compose(last)
            if not rendered or self._sent[last] == rendered:
                return
            if not self._due():
                return
            await self._edit(
                self._chat_id, self._message_ids[last], rendered, markdown=self._markdown
            )
            self._sent[last] = rendered
        self._last_edit = self._now()

    async def flush(self, *, force: bool = False) -> None:
        # Audio-request answers are held back until the filter has removed the
        # model's capability disclaimer; nothing false reaches the screen.
        if self._defer and not force:
            return
        # The very first send is never gated: until something is on screen there
        # is nothing to coalesce.
        if not force and self._message_ids and not self._due():
            return
        body = self._body()
        if not body.strip() and not self._message_ids:
            return

        chunks = split_message(body) or [""]
        for index, chunk in enumerate(chunks):
            rendered = f"{self._prefix}\n{chunk}" if index == 0 and self._prefix else chunk
            if index < len(self._message_ids):
                if index < len(self._sent) and self._sent[index] == rendered:
                    continue
                await self._edit(
                    self._chat_id, self._message_ids[index], rendered, markdown=self._markdown
                )
                self._sent[index] = rendered
            else:
                message_id = await self._send(
                    self._chat_id,
                    rendered,
                    thread_id=self._thread_id,
                    reply_to=self._reply_to,
                    markdown=self._markdown,
                )
                self._message_ids.append(message_id)
                self._sent.append(rendered)
        self._last_edit = self._now()

    async def finish(self, footer: str = "") -> None:
        self._status = ""
        if not self._message_ids and not self._buffer.strip():
            self._buffer = "…"
        if footer:
            self._buffer = f"{self._buffer.rstrip()}\n\n{footer}" if self._buffer.strip() else footer
        await self.flush(force=True)
