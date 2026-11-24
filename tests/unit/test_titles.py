from __future__ import annotations

from app.telegram.titles import MAX_DERIVED_TITLE_CHARS, derive_title


def test_first_meaningful_line_becomes_the_name() -> None:
    assert derive_title("Fix the login button on mobile") == "Fix the login button on mobile"
    assert derive_title("\n\n  Postgres   pool   exhaustion \nsecond line") == "Postgres pool exhaustion"


def test_long_openers_are_cut_at_a_word_boundary() -> None:
    title = derive_title(
        "Investigate why the nightly deploy keeps timing out after the migration runs"
    )
    assert title is not None
    assert len(title) <= MAX_DERIVED_TITLE_CHARS + 1
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")


def test_a_single_long_word_is_hard_cut() -> None:
    title = derive_title("x" * 200)
    assert title == "x" * MAX_DERIVED_TITLE_CHARS + "…"


def test_empty_and_machine_openers_have_no_name() -> None:
    assert derive_title(None) is None
    assert derive_title("   \n\n ") is None
    assert derive_title("[System note: internal] do not name") is None


def test_no_author_or_chat_is_involved() -> None:
    title = derive_title("Add /sessions named titles")
    assert title == "Add /sessions named titles"
    assert "Javier" not in (title or "")
