"""Inline keyboards and their compact callback payloads (contract T5)."""

from __future__ import annotations

from typing import Any


def _markup(rows: list[list[tuple[str, str]]]) -> Any:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=label, callback_data=data) for label, data in row] for row in rows]
    )


MENU = (
    ("📊 Status", "/status"),
    ("🆕 New", "/new"),
    ("📚 Sessions", "/sessions"),
    ("⏹ Abort", "/abort"),
)


def main_menu() -> Any:
    """Persistent bottom keyboard, so the common actions need no typing."""

    from telegram import KeyboardButton, ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [[KeyboardButton(label)] for label, _ in MENU],
        resize_keyboard=True,
        is_persistent=True,
    )


def menu_command(text: str) -> str | None:
    for label, command in MENU:
        if text.strip() == label:
            return command
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
