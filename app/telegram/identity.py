"""Speaker attribution for prompts (contract T3).

Two humans in one room only stay distinguishable if the model is told, per
message, who is speaking. The block is deliberately structural and short.
"""

from __future__ import annotations

from app.telegram.trigger import quoted_block
from app.telegram.types import Inbound, Trigger

MAX_BLOCK = 2000


def speaker_block(message: Inbound) -> str:
    return f"[speaker] name: {message.display_name} | telegram_id: {message.user_id}"


def conversation_block(message: Inbound, participants: list[str]) -> str:
    kind = "private" if message.is_private else message.chat_type
    topic = message.thread_title or ("none" if not message.thread_id else f"#{message.thread_id}")
    title = message.chat_title or message.display_name
    people = ", ".join(participants[:8]) if participants else message.display_name
    return f'[conversation] {kind}: "{title}" | topic: "{topic}" | participants: {people}'


def build_prompt(
    message: Inbound,
    trigger: Trigger,
    participants: list[str],
    *,
    limit: int = MAX_BLOCK,
) -> str:
    """Compose the text handed to the agent for this turn."""

    body = trigger.text.strip()
    quote = quoted_block(trigger.quote)

    for truncation in (1500, 800, 400, 0):
        parts = [speaker_block(message), conversation_block(message, participants)]
        if quote:
            parts.append(
                f"[quoted] author: {trigger.quote.author_name} "
                f"(telegram_id: {trigger.quote.author_id})"
                if trigger.quote
                else "[quoted]"
            )
            if truncation:
                parts.append(quote[:truncation])
        parts.append(body)
        composed = "\n".join(part for part in parts if part)
        if len(composed) <= limit:
            return composed
    return composed[:limit]


def attribution_prefix(message: Inbound, participant_count: int) -> str:
    """Prefix answers in multi-human conversations so the room knows who asked."""

    if participant_count <= 1:
        return ""
    name = message.display_name or (f"@{message.username}" if message.username else str(message.user_id))
    return f"{name}:"
