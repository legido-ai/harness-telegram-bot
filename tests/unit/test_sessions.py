from __future__ import annotations

from app.store import SessionEntry
from app.telegram import sessions


def entry(
    session_id: str,
    title: str | None = "Nightly build",
    *,
    active: bool = False,
    turns: int = 0,
    when: int = 1_700_000_000,
    chat_id: int = -100,
    thread_id: int = 0,
    chat_title: str | None = None,
    unassigned: bool = False,
) -> SessionEntry:
    return SessionEntry(
        session_id=session_id,
        title=title,
        active=active,
        turn_count=turns,
        last_active=when,
        chat_id=chat_id,
        thread_id=thread_id,
        chat_title=chat_title,
        unassigned=unassigned,
    )


# -- parsing -------------------------------------------------------------


def test_empty_argument_lists() -> None:
    args = sessions.parse_args("")
    assert args.empty
    assert args.search is None


def test_all_flag_is_recognised_with_the_rest() -> None:
    args = sessions.parse_args("all")
    assert args.all_chats and not args.search and not args.target
    assert sessions.parse_args("ALL 3").target == "3"


def test_search_keeps_the_rest_of_the_line() -> None:
    args = sessions.parse_args("search deploy staging")
    assert args.search == "deploy staging"
    assert args.target == ""
    assert sessions.parse_args("FIND daily").search == "daily"


def test_empty_search_is_flagged_for_usage() -> None:
    assert sessions.parse_args("search").search == ""


def test_quotes_are_stripped_from_a_title() -> None:
    assert sessions.parse_args('"Nightly build"').target == "Nightly build"
    assert sessions.parse_args("'Nightly build'").target == "Nightly build"


# -- resolution ----------------------------------------------------------

ROWS = [
    entry("ses_aaaaaa111111", "Nightly build", active=True, turns=12),
    entry("ses_bbbbbb222222", "Write docs", turns=3),
    entry("ses_cccccc333333", None, turns=0),
]


def test_number_resolves_the_listed_row() -> None:
    resolved = sessions.resolve_target(ROWS, "2")
    assert isinstance(resolved, sessions.Resolved)
    assert resolved.entry.session_id == "ses_bbbbbb222222"


def test_number_outside_the_list_is_out_of_range() -> None:
    resolved = sessions.resolve_target(ROWS, "9")
    assert isinstance(resolved, sessions.OutOfRange) and resolved.index == 9


def test_exact_id_and_suffix_resolve() -> None:
    exact = sessions.resolve_target(ROWS, "ses_cccccc333333")
    suffix = sessions.resolve_target(ROWS, "222222")
    assert isinstance(exact, sessions.Resolved) and exact.entry.session_id == "ses_cccccc333333"
    assert isinstance(suffix, sessions.Resolved) and suffix.entry.session_id == "ses_bbbbbb222222"


def test_title_match_is_case_insensitive() -> None:
    resolved = sessions.resolve_target(ROWS, "nightly BUILD")
    assert isinstance(resolved, sessions.Resolved)
    assert resolved.entry.session_id == "ses_aaaaaa111111"


def test_unique_title_substring_resolves() -> None:
    resolved = sessions.resolve_target(ROWS, "docs")
    assert isinstance(resolved, sessions.Resolved)
    assert resolved.entry.session_id == "ses_bbbbbb222222"


def test_ambiguous_title_is_reported_not_guessed() -> None:
    rows = [entry("ses_a1", "Nightly build"), entry("ses_b2", "Nightly build")]
    resolved = sessions.resolve_target(rows, "Nightly build")
    assert isinstance(resolved, sessions.Ambiguous)
    assert len(resolved.entries) == 2


def test_ambiguous_suffix_is_reported() -> None:
    rows = [entry("ses_a_shared6"), entry("ses_b_shared6")]
    resolved = sessions.resolve_target(rows, "shared6")
    assert isinstance(resolved, sessions.Ambiguous)


def test_unknown_target_is_not_found() -> None:
    resolved = sessions.resolve_target(ROWS, "does-not-exist")
    assert isinstance(resolved, sessions.NotFound)


# -- formatting ----------------------------------------------------------


def test_listing_marks_current_and_counts_turns() -> None:
    text = sessions.format_listing(ROWS, now=1_700_003_600)
    assert text.startswith("📋 Sessions in this chat")
    assert "* 1. Nightly build (current)" in text
    assert "12 turns" in text
    assert "1 turn" not in text
    assert "3 turns" in text
    assert "0 turns" in text
    assert "1h ago" in text
    assert "/sessions <number>" in text


def test_singular_turn_is_written_as_one_turn() -> None:
    text = sessions.format_listing([entry("ses_x", "Solo", turns=1)], now=1_700_000_010)
    assert "1 turn" in text and "1 turns" not in text


def test_empty_listing_explains_how_to_start() -> None:
    text = sessions.format_listing([])
    assert "No sessions found." in text
    assert "Send a message" in text


def test_search_listing_has_its_own_header() -> None:
    text = sessions.format_listing(ROWS[:1], search="nightly", now=1_700_000_000)
    assert text.startswith('📋 Sessions matching "nightly"')


def test_admin_listing_labels_origin_and_unassigned() -> None:
    rows = [
        entry("ses_a", "Deploy", chat_id=1, chat_title="ops"),
        entry("ses_b", "Lost", chat_id=0, unassigned=True),
    ]
    text = sessions.format_listing(rows, all_chats=True, now=1_700_000_000)
    assert "📋 Sessions (all chats)" in text
    assert "· ops" in text
    assert "· unassigned" in text


def test_notice_is_rendered() -> None:
    text = sessions.format_listing(ROWS[:1], notice="admin only", now=1_700_000_000)
    assert "admin only" in text


def test_relative_time_buckets() -> None:
    assert sessions.ago(100, now=130) == "just now"
    assert sessions.ago(100, now=100 + 120) == "2m ago"
    assert sessions.ago(100, now=100 + 7200) == "2h ago"
    assert sessions.ago(100, now=100 + 3 * 86400) == "3d ago"


# -- titles -------------------------------------------------------------


def test_clean_title_collapses_whitespace_and_caps_length() -> None:
    assert sessions.clean_title("  Nightly   build \n") == "Nightly build"
    assert sessions.clean_title("   ") is None
    assert len(sessions.clean_title("x" * 200) or "") == sessions.MAX_TITLE
