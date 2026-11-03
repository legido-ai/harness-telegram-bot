"""Health and operator endpoints (FR-020, FR-021)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Response

from app.config import Settings
from app.store import Store

STALE_AFTER = 300.0


@dataclass
class HealthState:
    started_at: float = field(default_factory=time.time)
    poller_alive: bool = False
    last_update_at: float | None = None
    sse_connected: bool = False
    last_sse_at: float | None = None
    agent_ok: bool = False
    rejections: int = 0

    def note_update(self) -> None:
        self.last_update_at = time.time()

    def note_sse(self, connected: bool) -> None:
        self.sse_connected = connected
        if connected:
            self.last_sse_at = time.time()

    def payload(self) -> tuple[dict[str, Any], bool]:
        now = time.time()
        silent_for = now - self.last_update_at if self.last_update_at else None
        healthy = bool(self.poller_alive) and (silent_for is None or silent_for < STALE_AFTER)
        return (
            {
                "status": "ok" if healthy else "degraded",
                "uptime_s": int(now - self.started_at),
                "poller_alive": self.poller_alive,
                "last_update_age_s": int(silent_for) if silent_for is not None else None,
                "sse_connected": self.sse_connected,
                "agent_ok": self.agent_ok,
                "rejections": self.rejections,
            },
            healthy,
        )


def create_app(settings: Settings, store: Store, state: HealthState) -> FastAPI:
    app = FastAPI(title="opencode-telegram-bot", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def healthz(response: Response) -> dict[str, Any]:
        payload, healthy = state.payload()
        response.status_code = 200 if healthy else 503
        return payload

    @app.get("/readyz")
    async def readyz(response: Response) -> dict[str, Any]:
        ready = store.schema_version() > 0
        response.status_code = 200 if ready else 503
        return {"ready": ready, "schema_version": store.schema_version()}

    @app.get("/audit")
    async def audit(limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(limit, 200))
        return {"turns": store.audit(limit)}

    return app
