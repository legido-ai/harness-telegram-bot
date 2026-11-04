from __future__ import annotations

from app.telegram.render import render_markdown, strip_html


def test_bold_and_inline_code_are_converted() -> None:
    assert render_markdown("a **bold** and `code`") == "a <b>bold</b> and <code>code</code>"


def test_fenced_code_keeps_its_body_verbatim() -> None:
    source = "before\n```python\nx = 1 < 2 and 'quotes'\n```\nafter"
    rendered = render_markdown(source)
    assert '<pre><code class="language-python">' in rendered
    assert "x = 1 &lt; 2 and 'quotes'" in rendered
    assert "before" in rendered and "after" in rendered


def test_headings_and_links() -> None:
    rendered = render_markdown("### Result\nsee [docs](https://example.com/x)")
    assert "<b>Result</b>" in rendered
    assert '<a href="https://example.com/x">docs</a>' in rendered


def test_unknown_markup_is_escaped_not_dropped() -> None:
    rendered = render_markdown("5 < 6 & 7 > 3")
    assert "5 &lt; 6 &amp; 7 &gt; 3" in rendered


def test_empty_answer_stays_empty() -> None:
    assert render_markdown("") == ""
    assert render_markdown("   ") == "   "


def test_strip_html_returns_what_a_user_reads() -> None:
    rendered = render_markdown("**bold** and `code`")
    assert strip_html(rendered) == "bold and code"


def test_keyboard_is_one_row_with_two_blocks() -> None:
    from app.telegram.keyboards import main_menu

    markup = main_menu("📊 6K / 1.0M (1%)")
    assert len(markup.keyboard) == 1
    assert [button.text for button in markup.keyboard[0]] == ["🧠 Model", "📊 6K / 1.0M (1%)"]


def test_context_button_label_shows_usage() -> None:
    from app.telegram.keyboards import context_label

    assert context_label(6000, 1_000_000) == "📊 6K / 1.0M (1%)"
    assert context_label(None, None) == "📊 0"
    assert context_label(6000, None) == "📊 6K"


def test_buttons_match_by_icon_after_relabelling() -> None:
    from app.telegram.keyboards import menu_command

    assert menu_command("📊 6K / 1.0M (1%)") == "/context"
    assert menu_command("🧠 Model") == "/model"
    assert menu_command("hello") is None
