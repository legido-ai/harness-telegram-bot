"""Command parsing and the copy the bot sends back."""

from __future__ import annotations

from app.telegram.types import Inbound

HELP = """\
OpenCode bot — how to work with me

Private chat: just write what you want done.
Group: mention me (@{username}) or reply to one of my messages. I ignore
conversation that is not addressed to me.

The two buttons below the input: model picker and context usage.

/new            start a fresh session in this conversation
/sessions       list recent sessions and switch
/abort          stop the run that is in progress
/status         session, model, agent and queue depth
/model          pick the model for this conversation
/agent          pick the agent mode
/trigger        show or set mention|all for this chat
/id             show your numeric id and this chat id
/help           this card
"""


def parse(text: str) -> tuple[str, str]:
    """Return (command, argument) from ``/cmd@bot arg``."""

    if not text.startswith("/"):
        return "", text.strip()
    head, _, tail = text.partition(" ")
    name = head.split("@", 1)[0].lstrip("/").lower()
    return name, tail.strip()


def help_text(username: str) -> str:
    return HELP.format(username=username.lstrip("@"))


def sessions_text(sessions: list[tuple[str, str, bool]]) -> str:
    if not sessions:
        return "No sessions yet. Send a message and one is created."
    lines = ["Recent sessions in this conversation:"]
    for index, (session_id, title, active) in enumerate(sessions, start=1):
        marker = "*" if active else " "
        lines.append(f"{marker} {index}. {title or 'untitled'} — {session_id[-6:]}")
    return "\n".join(lines)


def id_text(message: Inbound) -> str:
    thread = f"\ntopic: {message.thread_id}" if message.thread_id else ""
    return f"your id: {message.user_id}\nchat id: {message.chat_id}{thread}"
