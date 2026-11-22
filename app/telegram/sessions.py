"""Pure helpers for /sessions: parse, resolve and format.

No I/O lives here, so the whole command surface is testable without Telegram,
a store or a harness. The store returns :class:`SessionEntry` rows; this module
decides what the user reads and which session a reference points at.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.store import SessionEntry

MAX_TITLE = 60
MIN_SUFFIX = 6
MAX_ROWS = 10


@dataclass(frozen=True, slots=True)
class Args:
    all_chats: bool = False
    search: str | None = None
    target: str = ""

    @property
    def empty(self) -> bool:
        return not self.all_chats and self.search is None and not self.target


@dataclass(frozen=True, slots=True)
class Resolved:
    entry: SessionEntry


@dataclass(frozen=True, slots=True)
class Ambiguous:
    entries: list[SessionEntry]


@dataclass(frozen=True, slots=True)
class OutOfRange:
    index: int


@dataclass(frozen=True, slots=True)
class NotFound:
    target: str


Resolution = Resolved | Ambiguous | OutOfRange | NotFound


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1].strip()
    return text


def parse_args(argument: str) -> Args:
    """Split ``all``, ``search <q>`` (alias ``find``) and a resume target."""

    text = argument.strip()
    if not text:
        return Args()
    head, _, rest = text.partition(" ")
    keyword = head.lower()
    if keyword in ("all", "--all"):
        tail = parse_args(rest)
        return Args(all_chats=True, search=tail.search, target=tail.target)
    if keyword in ("search", "find"):
        return Args(search=_unquote(rest))
    return Args(target=_unquote(text))


def clean_title(text: str) -> str | None:
    """Trim and collapse whitespace; ``None`` means "no usable title"."""

    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    return collapsed[:MAX_TITLE]


def _matches(title: str | None, session_id: str, needle: str) -> bool:
    lowered = needle.casefold()
    if title and lowered in title.casefold():
        return True
    return lowered in session_id.casefold()


def resolve_target(entries: list[SessionEntry], target: str) -> Resolution:
    """Resolve what the human typed against the entries they were shown."""

    text = _unquote(target)
    if not text:
        return NotFound(target)

    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(entries):
            return Resolved(entries[index - 1])
        if len(text) < MIN_SUFFIX:
            return OutOfRange(index)
        # Long digit strings are more likely a session-id suffix than an
        # ordinal nobody could reach; fall through to the suffix match.

    exact = [entry for entry in entries if entry.session_id == text]
    if exact:
        return Resolved(exact[0])

    if len(text) >= MIN_SUFFIX:
        suffix = [entry for entry in entries if entry.session_id.endswith(text)]
        if len(suffix) == 1:
            return Resolved(suffix[0])
        if len(suffix) > 1:
            return Ambiguous(suffix)

    lowered = text.casefold()
    by_title = [
        entry for entry in entries if (entry.title or "").casefold() == lowered
    ]
    if len(by_title) == 1:
        return Resolved(by_title[0])
    if len(by_title) > 1:
        return Ambiguous(by_title)

    partial = [entry for entry in entries if _matches(entry.title, entry.session_id, text)]
    if len(partial) == 1:
        return Resolved(partial[0])
    if len(partial) > 1:
        return Ambiguous(partial)
    return NotFound(target)


def short_id(session_id: str) -> str:
    return session_id[-MIN_SUFFIX:]


def ago(epoch: int, now: float | None = None) -> str:
    seconds = max(0, int((now if now is not None else time.time()) - epoch))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 365:
        return f"{days}d ago"
    return f"{days // 365}y ago"


def format_row(index: int, entry: SessionEntry, now: float | None = None) -> str:
    marker = "*" if entry.active else " "
    title = entry.title or "untitled"
    current = " (current)" if entry.active else ""
    turns = f"{entry.turn_count} turns" if entry.turn_count != 1 else "1 turn"
    if entry.unassigned:
        origin = " · unassigned"
    elif entry.chat_title:
        origin = f" · {entry.chat_title}"
    else:
        origin = ""
    return (
        f"{marker} {index}. {title}{current} — {short_id(entry.session_id)}"
        f" · {turns} · {ago(entry.last_active, now)}{origin}"
    )


def format_listing(
    entries: list[SessionEntry],
    *,
    search: str | None = None,
    all_chats: bool = False,
    notice: str | None = None,
    now: float | None = None,
) -> str:
    if not entries:
        lines = ["No sessions found."]
        if search:
            lines.append("Usage: /sessions search <query>")
        else:
            lines.append("Send a message and a session is created here.")
        if notice:
            lines.append(notice)
        return "\n".join(lines)

    if search:
        header = f'📋 Sessions matching "{search}"'
    elif all_chats:
        header = "📋 Sessions (all chats)"
    else:
        header = "📋 Sessions in this chat"

    lines = [header, ""]
    stamp = now if now is not None else time.time()
    for index, entry in enumerate(entries[:MAX_ROWS], start=1):
        lines.append(format_row(index, entry, stamp))

    lines.append("")
    if notice:
        lines.append(notice)
    lines.append(
        "Resume: /sessions <number> or /sessions <id>. Rename: /title <name>."
    )
    if not search:
        lines.append("More: /sessions search <query> · /sessions all (admin).")
    else:
        lines.append("More: /sessions to see everything, /sessions all (admin).")
    return "\n".join(lines)
