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
/sessions       browse this chat's sessions and resume one
/resume         same as /sessions: list, or resume by number/id/title
/title          show or set the current session's name
/abort          stop the run that is in progress
/status         session, model, agent and queue depth
/model          pick the model for this conversation
/agent          pick the agent mode
/tts            audio replies: off|all|auto
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


def id_text(message: Inbound) -> str:
    thread = f"\ntopic: {message.thread_id}" if message.thread_id else ""
    return f"your id: {message.user_id}\nchat id: {message.chat_id}{thread}"
