"""Backend factory: the only place that knows which adapters exist."""

from __future__ import annotations

from app.backends.base import Backend
from app.backends.opencode.backend import OpenCodeBackend
from app.backends.opencode.client import OpenCodeClient
from app.backends.pi.backend import PiBackend
from app.backends.pi.rpc import PiRpc
from app.config import ConfigError, Settings

BACKENDS = ("opencode", "pi")


def build_backend(settings: Settings) -> Backend:
    if settings.backend == "opencode":
        return OpenCodeBackend(
            OpenCodeClient(
                settings.opencode_url,
                settings.opencode_password,
                username=settings.opencode_username,
            ),
            run_timeout=settings.run_timeout,
        )
    if settings.backend == "pi":
        rpc = PiRpc(
            binary=settings.pi_bin,
            provider=settings.pi_provider,
            model=settings.pi_model,
            session_dir=settings.pi_session_dir,
            workspace=settings.workspace_dir,
            thinking=settings.pi_thinking,
        )
        return PiBackend(
            rpc,
            session_dir=settings.pi_session_dir,
            run_timeout=float(settings.run_timeout),
            idle_minutes=settings.pi_idle_minutes,
        )
    raise ConfigError("BACKEND must be one of: " + ", ".join(BACKENDS))


__all__ = ["BACKENDS", "Backend", "build_backend"]
