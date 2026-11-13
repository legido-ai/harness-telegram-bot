"""The seam between the Telegram surface and a coding harness.

Everything in this package implements :class:`Backend`. The Telegram modules
import only this file, never a concrete adapter, so adding a harness means
adding one directory here and one branch in the factory.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.backends.errors import (
    AuthError,
    Busy,
    HarnessError,
    InvalidRequest,
    SessionGone,
    Unavailable,
    Unsupported,
)

PERMISSION_ASKED = "permission.asked"
FORM_CREATED = "form.created"


@dataclass(slots=True)
class Interaction:
    """A question the harness needs a human to answer, rendered as buttons."""

    kind: str
    session_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass(slots=True)
class RunOutcome:
    """Result of one turn, after the stream has already been delivered."""

    text: str | None = None
    error: str | None = None


DeltaSink = Callable[[str], Awaitable[None]]
InteractionHook = Callable[[str, Interaction], Awaitable[None]]


@runtime_checkable
class Backend(Protocol):
    """What the Telegram layer needs from a harness."""

    name: str
    supports_agents: bool
    supports_permissions: bool
    supports_forms: bool
    supports_images: bool

    async def start(self) -> None: ...

    async def aclose(self) -> None: ...

    async def ping(self) -> bool: ...

    async def background(self, stop: asyncio.Event, state: Any) -> None: ...

    async def create_session(
        self,
        title: str | None,
        *,
        agent: str | None = None,
        model: dict[str, str] | None = None,
    ) -> str: ...

    async def session_exists(self, ref: str) -> bool: ...

    async def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]: ...

    async def describe(self, ref: str) -> str: ...

    async def run(
        self,
        ref: str,
        prompt: str,
        *,
        files: Sequence[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
        on_delta: DeltaSink | None = None,
        on_interaction: InteractionHook | None = None,
    ) -> RunOutcome: ...

    async def interrupt(self, ref: str) -> bool: ...

    async def models(self) -> list[dict[str, Any]]: ...

    async def providers(self) -> list[dict[str, Any]]: ...

    async def agents(self) -> list[dict[str, Any]]: ...

    async def default_model(self) -> dict[str, Any]: ...

    async def set_model(self, ref: str, provider: str, model: str) -> None: ...

    async def set_agent(self, ref: str, agent: str) -> None: ...

    async def session(self, ref: str) -> dict[str, Any]: ...

    async def context_usage(self, ref: str) -> dict[str, Any]: ...

    async def context_limit(self, provider: str | None, model: str | None) -> int | None: ...

    async def generate(self, ref: str, prompt: str) -> str: ...

    async def reply_permission(self, ref: str, request_id: str, decision: str) -> None: ...

    async def reply_form(self, ref: str, form_id: str, answer: dict[str, Any]) -> None: ...


__all__ = [
    "AuthError",
    "Backend",
    "Busy",
    "DeltaSink",
    "FORM_CREATED",
    "HarnessError",
    "Interaction",
    "InteractionHook",
    "InvalidRequest",
    "PERMISSION_ASKED",
    "RunOutcome",
    "SessionGone",
    "Unavailable",
    "Unsupported",
]
