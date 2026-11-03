"""Structured logging with a hard redaction filter.

Constitution Principle IV: tokens, server passwords and user message bodies must
never reach a log line, an exception trace or a health payload.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable

REDACTED = "***"

# Fields whose values are message content and must never be logged verbatim.
BODY_FIELDS = ("text", "prompt", "message", "body", "answer", "content")


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every secret occurrence in ``text`` with ``***``."""

    if not isinstance(text, str):
        text = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, REDACTED)
    return text


class RedactionFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - defensive, formatting must not break logging
            rendered = str(record.msg)
        record.msg = redact(rendered, self._secrets)
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("chat_id", "thread_id", "user_id", "session_id", "update_id", "event"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str, secrets: Iterable[str]) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter(secrets))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Third-party noise: PTB logs full update payloads at DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    return logging.getLogger("bot")


def safe_exception(exc: BaseException, secrets: Iterable[str]) -> str:
    """Render an exception for the user without leaking secrets or bodies."""

    return redact(f"{type(exc).__name__}: {exc}", secrets)
