"""Inline keyboards and their compact callback payloads (contract T5)."""

from __future__ import annotations

from typing import Any

from app.telegram.footer import format_tokens


def _markup(rows: list[list[tuple[str, str]]]) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows]
    )


MODEL_LABEL = "🧠 Model"
CONTEXT_EMPTY = "📊 0"


def context_label(used: int | None, limit: int | None) -> str:
    """The context button *shows* the usage: 📊 6K / 1.0M (1%)."""

    if limit:
        percent = round((used or 0) / limit * 100)
        return f"📊 {format_tokens(used or 0)} / {format_tokens(limit)} ({percent}%)"
    if used:
        return f"📊 {format_tokens(used)}"
    return CONTEXT_EMPTY


def main_menu(context: str | None = None) -> Any:
    """One row, two blocks: model picker and live context usage."""

    from telegram import KeyboardButton, ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [[KeyboardButton(MODEL_LABEL), KeyboardButton(context or CONTEXT_EMPTY)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_command(text: str) -> str | None:
    """Buttons are matched by icon: the context label changes every run."""

    stripped = text.strip()
    if stripped.startswith("🧠"):
        return "/model"
    if stripped.startswith("📊"):
        return "/context"
    return None


def permission_keyboard(session_id: str, request_id: str) -> Any:
    return _markup(
        [
            [
                ("Allow once", f"p:{session_id}:{request_id}:once"),
                ("Always", f"p:{session_id}:{request_id}:always"),
            ],
            [("Deny", f"p:{session_id}:{request_id}:reject")],
        ]
    )


def form_keyboard(session_id: str, form_id: str, options: list[str]) -> Any:
    rows = [
        [(option[:40], f"f:{session_id}:{form_id}:{index}")]
        for index, option in enumerate(options[:8])
    ]
    return _markup(rows)


def model_keyboard(session_id: str, models: list[tuple[str, str, str]]) -> Any:
    """``models`` items are (provider, model_id, label)."""

    rows = [
        [(label[:40], f"m:{session_id}:{provider}:{model_id}")]
        for provider, model_id, label in models[:10]
    ]
    return _markup(rows)


def agent_keyboard(session_id: str, agents: list[str]) -> Any:
    return _markup([[(name[:40], f"a:{session_id}:{name}")] for name in agents[:10]])


def sessions_keyboard(chat_id: int, thread_id: int, sessions: list[tuple[str, str]]) -> Any:
    return _markup(
        [[(title[:40], f"s:{chat_id}:{thread_id}:{session_id}")] for session_id, title in sessions[:10]]
    )


def parse_callback(data: str) -> tuple[str, list[str]]:
    parts = data.split(":")
    if not parts or not parts[0]:
        return "", []
    return parts[0], parts[1:]
