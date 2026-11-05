"""Markdown to Telegram HTML, with a plain-text escape hatch.

Agents answer in Markdown. Telegram shows it raw unless we convert it, so
``**bold**`` and code fences arrive as literal asterisks — the first thing
anyone notices next to a polished bot. Conversion is deliberately small: fenced
code, inline code, bold, italic, headings and links. Everything else is escaped
and left alone.
"""

from __future__ import annotations

import html
import re

_FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_TAG = re.compile(r"<[^>]+>")


def render_markdown(text: str) -> str:
    """Convert a Markdown-ish answer into Telegram-safe HTML."""

    if not text:
        return ""

    # Code fences are lifted out first so their contents are never transformed.
    blocks: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        language = match.group(1).strip()
        body = html.escape(match.group(2).rstrip("\n"), quote=False)
        attr = f' class="language-{html.escape(language)}"' if language else ""
        blocks.append(f"<pre><code{attr}>{body}</code></pre>")
        return f"\x00{len(blocks) - 1}\x00"

    stashed = _FENCE.sub(_stash, text)
    escaped = html.escape(stashed, quote=False)

    escaped = _INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<i>{m.group(1)}</i>", escaped)
    escaped = _HEADING.sub(lambda m: f"<b>{m.group(1)}</b>", escaped)
    escaped = _LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped)

    def _restore(match: re.Match[str]) -> str:
        return blocks[int(match.group(1))]

    return re.sub(r"\x00(\d+)\x00", _restore, escaped)


def strip_html(text: str) -> str:
    """Plain-text fallback used when Telegram rejects our markup."""

    return html.unescape(_TAG.sub("", text))
