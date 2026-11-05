"""Run footer: model, context consumption, cost and duration.

Ported in spirit from the bridge we replaced (``@grinev/opencode-telegram-bot``):
the numbers are the same ones it shows — ``input + cache.read`` against the
model's ``limit.context``, plus session cost — but computed here from the V2
session payload instead of a pinned status card.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RunStats:
    provider: str | None = None
    model: str | None = None
    used_tokens: int | None = None
    limit_tokens: int | None = None
    cost_usd: float | None = None
    seconds: float | None = None
    session_id: str | None = None
    created: bool = False

    @property
    def percent(self) -> int | None:
        if not self.used_tokens or not self.limit_tokens:
            return None
        return round(self.used_tokens / self.limit_tokens * 100)


def format_tokens(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count // 1_000}K"
    return str(count)


def format_cost(cost_usd: float) -> str:
    if cost_usd and cost_usd < 0.01:
        return f"${cost_usd:.3f}"
    return f"${cost_usd:.2f}"


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m{rest:02d}s"


def _short_session(session_id: str) -> str:
    tail = session_id.split("_")[-1]
    return tail[:6]


def format_footer(stats: RunStats) -> str:
    """Build the ``— model · 42K/200K (21%) · $0.03 · 12s`` line.

    Missing pieces are dropped rather than shown as placeholders; if nothing at
    all is known the session id keeps the footer useful.
    """

    parts: list[str] = []

    model = "/".join(part for part in (stats.provider, stats.model) if part)
    if model:
        parts.append(stats.model or model)

    if stats.used_tokens is not None and stats.limit_tokens:
        percent = stats.percent
        parts.append(
            f"{format_tokens(stats.used_tokens)}/{format_tokens(stats.limit_tokens)}"
            + (f" ({percent}%)" if percent is not None else "")
        )
    elif stats.used_tokens:
        parts.append(f"{format_tokens(stats.used_tokens)} tok")

    if stats.cost_usd:
        parts.append(format_cost(stats.cost_usd))

    if stats.seconds is not None:
        parts.append(format_duration(stats.seconds))

    if stats.session_id and not parts:
        parts.append(f"session {_short_session(stats.session_id)}")

    if not parts:
        return ""

    line = "— " + " · ".join(parts)
    if stats.created and stats.session_id:
        line += f" · new session {_short_session(stats.session_id)}"
    return line
