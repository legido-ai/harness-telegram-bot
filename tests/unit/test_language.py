from __future__ import annotations

from app.telegram.audio_filter import wants_audio
from app.telegram.language import requested_language


def test_language_names_are_recognised() -> None:
    assert requested_language("responde en castellano") == "es"
    assert requested_language("respóndeme en español") == "es"
    assert requested_language("responde en inglés") == "en"
    assert requested_language("answer in English") == "en"
    assert requested_language("genera un audio corto") is None


def test_answer_in_a_language_counts_as_an_audio_request() -> None:
    assert wants_audio("responde en castellano")
    assert wants_audio("respóndeme en inglés")
    assert wants_audio("genera un audio en castellano")
    assert not wants_audio("explain this in English")
