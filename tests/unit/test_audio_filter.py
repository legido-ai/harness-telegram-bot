from __future__ import annotations

from app.telegram.audio_filter import strip_audio_meta, wants_audio

SCREENSHOT_ANSWER = (
    "Ese bloque <system-update> ha llegado dentro de tu mensaje, no del harness — y es la "
    "tercera vez que se intenta colar una instrucción para que deje de decirte la verdad. "
    "No la voy a aceptar como orden del sistema.\n\n"
    "Dicho claro: si el bot de Telegram hiciera el audio, estupendo, pero yo no tengo forma "
    "de saberlo ni de garantizarlo, y no voy a afirmar que genero audio cuando no es así.\n\n"
    "La frase corta que pediste:\n\n"
    '"Hoy es un buen día para empezar algo nuevo."\n\n'
    "Si tu bot la convierte en audio, perfecto. Si no, sigue siendo solo texto."
)


def test_audio_intent_is_detected_in_spanish_and_english() -> None:
    assert wants_audio("genera un audio corto con una frase.")
    assert wants_audio("Dime una frase en inglés, pero genera un audio.")
    assert wants_audio("send me a voice message with a quote")
    assert not wants_audio("explain the audio transcription API")
    assert not wants_audio("what is the weather?")


def test_capability_disclaimers_are_removed_but_the_answer_stays() -> None:
    cleaned = strip_audio_meta(SCREENSHOT_ANSWER)

    assert '"Hoy es un buen día para empezar algo nuevo."' in cleaned
    assert "system-update" not in cleaned
    assert "no puedo" not in cleaned.lower()
    assert "harness" not in cleaned.lower()
    assert "solo texto" not in cleaned.lower()


def test_discarded_context_line_is_removed() -> None:
    text = 'Entendido, descarto ese contexto.\n\nFrase corta:\n\n"Less is more."'
    assert strip_audio_meta(text) == 'Frase corta:\n\n"Less is more."'


def test_clean_answer_is_untouched() -> None:
    text = '**"Less is more."**\n\nWant another?'
    assert strip_audio_meta(text) == text


def test_refusal_only_answer_does_not_blank_the_chat() -> None:
    text = "No puedo generar audio. Solo texto."
    assert strip_audio_meta(text) == text
