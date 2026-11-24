"""Session names derived from the opening message.

Hermes titles a session from the first user message: the first meaningful line,
whitespace collapsed, cut at a word boundary to 48 characters with an ellipsis.
No model call, no author name, no chat name. ``/title`` still overrides it.
"""

from __future__ import annotations

MAX_DERIVED_TITLE_CHARS = 48

# Openers Hermes never titles: machine-written handoffs and notes. Our prompt
# builder puts these on separate lines after the user text, but a pasted brief
# can still start with one.
_MACHINE_PREFIXES = (
    "[CONTEXT COMPACTION",
    "[Runtime note:",
    "[System note:",
    "[SYSTEM]",
)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def derive_title(text: str | None) -> str | None:
    """Return a short session name, or ``None`` when the text has no topic."""

    if not text or not text.strip():
        return None
    if text.lstrip().startswith(_MACHINE_PREFIXES):
        return None
    line = " ".join(_first_line(text).split())
    if not line:
        return None
    if len(line) > MAX_DERIVED_TITLE_CHARS:
        cut = line[:MAX_DERIVED_TITLE_CHARS]
        space = cut.rfind(" ")
        line = (cut[:space] if space > MAX_DERIVED_TITLE_CHARS // 2 else cut).rstrip(
            " ,.;:—-"
        ) + "…"
    return line or None
