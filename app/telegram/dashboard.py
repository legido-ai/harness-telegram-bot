"""Pinned status card: the at-a-glance state of the conversation.

Mirrors the dashboard the previous bridge pinned in the chat: session, model,
context consumption, cost and queue depth, refreshed after every run. It is one
message per conversation, edited in place, pinned once.
"""

from __future__ import annotations

from app.telegram.footer import RunStats, format_cost, format_tokens, percent_text


def _short(session_id: str | None) -> str:
    if not session_id:
        return "none"
    return session_id.split("_")[-1][:6]


def dashboard_text(
    *,
    title: str,
    stats: RunStats | None,
    queue_depth: int,
    last_user: str | None = None,
    status: str = "idle",
) -> str:
    lines = [f"📊 {title}"]
    if stats is None:
        lines.append("no run yet")
        return "\n".join(lines)

    lines.append(f"session {_short(stats.session_id)} · {stats.model or 'server default'}")

    used = stats.used_tokens or 0
    if stats.limit_tokens:
        percent = percent_text(stats.used_tokens, stats.limit_tokens) or "0%"
        lines.append(
            f"context {format_tokens(used)}/{format_tokens(stats.limit_tokens)} ({percent})"
        )
    elif used:
        lines.append(f"context {format_tokens(used)} tokens")

    tail = []
    if stats.cost_usd:
        tail.append(f"cost {format_cost(stats.cost_usd)}")
    tail.append(f"queued {queue_depth}")
    lines.append(" · ".join(tail))

    if last_user:
        lines.append(f"last {last_user} · {status}")
    return "\n".join(lines)
