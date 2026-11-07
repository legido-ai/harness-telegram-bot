"""Language hints for explicit audio requests.

TTS does not translate: this module only recognises which language the user
asked the spoken answer to be in, so the bot can generate the text and pick the
matching voice.
"""

from __future__ import annotations

import re

_SPANISH = re.compile(r"\b(castellano|español|espanol|spanish)\b", re.IGNORECASE)
_ENGLISH = re.compile(r"\b(inglés|ingles|english)\b", re.IGNORECASE)


def requested_language(text: str) -> str | None:
    """Return ``"es"``, ``"en"`` or ``None`` when the request is ambiguous."""

    spanish = bool(_SPANISH.search(text))
    english = bool(_ENGLISH.search(text))
    if spanish and not english:
        return "es"
    if english and not spanish:
        return "en"
    return None
