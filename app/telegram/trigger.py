"""When does the bot answer? Entity-based, so quoting and usernames behave.

Rules live in ``contracts/telegram-interaction.md`` (T2). Offsets from Telegram
count UTF-16 code units, which is why slicing goes through UTF-16 bytes.
"""

from __future__ import annotations

from app.telegram.types import Entity, Inbound, Quoted, Trigger

DEFAULT_TRIGGER_POLICY = "mention"

# Commands this bot owns. In a group a bare /new is accepted for these, because
# privacy is off and the alternative is typing /new@bot every time.
OWN_COMMANDS = frozenset(
    {
        "start",
        "help",
        "id",
        "new",
        "sessions",
        "switch",
        "abort",
        "status",
        "context",
        "model",
        "agent",
        "trigger",
    }
)


def _u16_map(text: str) -> list[int]:
    """Map each UTF-16 code unit index to a Python character index."""

    mapping: list[int] = []
    for index, char in enumerate(text):
        mapping.extend([index] * (len(char.encode("utf-16-le")) // 2))
    mapping.append(len(text))
    return mapping


def slice_entities(text: str, entities: tuple[Entity, ...]) -> str:
    """Return ``text`` with every entity range removed."""

    if not entities:
        return text
    mapping = _u16_map(text)
    drop = [False] * len(text)
    for entity in entities:
        start = mapping[min(entity.offset, len(mapping) - 1)]
        end = mapping[min(entity.offset + entity.length, len(mapping) - 1)]
        for index in range(start, end):
            drop[index] = True
    kept = "".join(char for char, removed in zip(text, drop, strict=True) if not removed)
    return " ".join(kept.split())


def _entity_text(text: str, entity: Entity) -> str:
    mapping = _u16_map(text)
    start = mapping[min(entity.offset, len(mapping) - 1)]
    end = mapping[min(entity.offset + entity.length, len(mapping) - 1)]
    return text[start:end]


def _has_mention(text: str, entities: tuple[Entity, ...], bot_username: str, bot_id: int) -> bool:
    target = f"@{bot_username.lstrip('@').lower()}"
    for entity in entities:
        if entity.type in ("mention", "text_mention"):
            if entity.user_id is not None and entity.user_id == bot_id:
                return True
            if entity.type == "mention" and _entity_text(text, entity).lower() == target:
                return True
            if entity.type == "text_mention" and entity.user_id == bot_id:
                return True
    return False


def _command_targets_bot(
    text: str, entities: tuple[Entity, ...], bot_username: str, is_private: bool
) -> tuple[bool, str | None]:
    """Return (addressed_to_this_bot, command_name)."""

    for entity in entities:
        if entity.type != "bot_command":
            continue
        raw = _entity_text(text, entity)
        name, _, target = raw.partition("@")
        command = name.lstrip("/").split(" ")[0].lower()
        if target:
            if target.lower() == bot_username.lstrip("@").lower():
                return True, command
            continue
        if is_private or command in OWN_COMMANDS:
            return True, command
    return False, None


def detect(
    message: Inbound,
    *,
    bot_id: int,
    bot_username: str,
    policy: str = DEFAULT_TRIGGER_POLICY,
) -> Trigger | None:
    """Decide whether this message is addressed to the bot.

    Returns ``None`` when the bot must stay silent, which includes every case
    where a quote of someone else's mention is the only "mention" present.
    """

    if message.is_bot:
        return None

    text = message.text or ""
    entities = tuple(e for e in message.entities)

    addressed, command = _command_targets_bot(
        text, entities, bot_username, message.is_private
    )
    # A slash command is never a prompt. It only runs when it is addressed to
    # this bot: unaddressed commands belong to other bots in the room.
    if any(entity.type == "bot_command" for entity in entities):
        if not addressed:
            return None
        return Trigger(kind="command", text=cleaned_command(text, entities), quote=message.quote)

    if message.is_private:
        cleaned = (
            slice_entities(text, entities)
            if _has_mention(text, entities, bot_username, bot_id)
            else text.strip()
        )
        return Trigger(kind="private", text=cleaned, quote=message.quote)

    mentioned = _has_mention(text, entities, bot_username, bot_id)
    replied = message.quote is not None and message.quote.author_id == bot_id

    if mentioned or replied:
        kind = "mention" if mentioned else "reply"
        cleaned = slice_entities(text, entities) if mentioned else text.strip()
        if not cleaned:
            return Trigger(kind="empty", text="", quote=message.quote)
        return Trigger(kind=kind, text=cleaned, quote=message.quote)

    if policy == "all" and text.strip():
        return Trigger(kind="policy_all", text=text.strip(), quote=message.quote)

    return None


def cleaned_command(text: str, entities: tuple[Entity, ...]) -> str:
    """Return ``/cmd@bot arg`` with the addressee removed and args kept."""

    mapping = _u16_map(text)
    for entity in entities:
        if entity.type != "bot_command":
            continue
        start = mapping[min(entity.offset, len(mapping) - 1)]
        end = mapping[min(entity.offset + entity.length, len(mapping) - 1)]
        raw = text[start:end]
        if "@" in raw:
            name, _, _target = raw.partition("@")
            return " ".join((text[:start] + name + text[end:]).split())
        return " ".join(text.split())
    return text.strip()


def quoted_block(quote: Quoted | None, limit: int = 1500) -> str:
    if quote is None or not quote.text:
        return ""
    body = quote.text.strip()
    if len(body) > limit:
        body = body[: limit - 1] + "…"
    return body
