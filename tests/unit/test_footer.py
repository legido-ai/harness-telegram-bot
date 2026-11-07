from __future__ import annotations

from app.telegram.footer import (
    RunStats,
    format_cost,
    format_duration,
    format_footer,
    format_sign_off,
    format_tokens,
    percent_text,
)
from app.telegram.keyboards import CONTEXT_EMPTY, context_label


def test_token_counts_are_compact() -> None:
    assert format_tokens(900) == "900"
    assert format_tokens(42_000) == "42K"
    assert format_tokens(1_200_000) == "1.2M"


def test_cost_precision_scales_with_size() -> None:
    assert format_cost(0.03) == "$0.03"
    assert format_cost(1.5) == "$1.50"
    assert format_cost(0.004) == "$0.004"


def test_duration_is_human() -> None:
    assert format_duration(12.4) == "12s"
    assert format_duration(75) == "1m15s"


def test_full_footer_matches_the_shape_we_promised() -> None:
    stats = RunStats(
        provider="go",
        model="flash",
        used_tokens=42_000,
        limit_tokens=200_000,
        cost_usd=0.03,
        seconds=12,
        session_id="ses_abc123",
    )
    assert format_footer(stats) == "— flash · 42K/200K (21%) · $0.03 · 12s"


def test_footer_degrades_when_numbers_are_missing() -> None:
    stats = RunStats(model="flash", used_tokens=42_000, seconds=3)
    assert format_footer(stats) == "— flash · 42K tok · 3s"


def test_footer_falls_back_to_the_session_id() -> None:
    assert format_footer(RunStats(session_id="ses_abc123")) == "— session abc123"


def test_new_session_is_marked() -> None:
    stats = RunStats(model="flash", seconds=1, session_id="ses_abc123", created=True)
    assert format_footer(stats).endswith("new session abc123")


def test_free_model_does_not_print_a_zero_cost() -> None:
    stats = RunStats(model="flash", used_tokens=100, limit_tokens=1000, cost_usd=0.0, seconds=2)
    assert "$" not in format_footer(stats)


def test_a_started_session_never_reads_as_zero() -> None:
    assert percent_text(1_000, 1_000_000) == "<1%"
    assert percent_text(55_000, 1_000_000) == "6%"
    assert percent_text(0, 1_000_000) is None
    assert percent_text(42_000, None) is None


def test_sign_off_carries_the_numbers_and_nothing_else() -> None:
    stats = RunStats(
        provider="go", model="flash", used_tokens=42_000, limit_tokens=200_000, seconds=12
    )
    assert format_sign_off(stats) == "✅ I'm done · 42K/200K (21%) · 12s"
    assert format_sign_off(RunStats(seconds=3)) == "✅ I'm done · 3s"
    assert format_sign_off(None) == "✅ I'm done"


def test_keyboard_label_marks_a_tiny_session() -> None:
    assert context_label(1_000, 1_000_000) == "📊 1K / 1.0M (<1%)"
    assert context_label(None, 1_000_000) == "📊 0 / 1.0M (0%)"
    assert context_label(None, None) == CONTEXT_EMPTY
