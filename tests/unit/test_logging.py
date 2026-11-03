from __future__ import annotations

import logging

from app.logging import JsonFormatter, RedactionFilter, redact, safe_exception

SECRETS = ("123456:TESTTOKENVALUE", "server-secret-value")


def test_redact_replaces_every_secret() -> None:
    text = "token 123456:TESTTOKENVALUE and password server-secret-value"
    cleaned = redact(text, SECRETS)
    assert "TESTTOKENVALUE" not in cleaned
    assert "server-secret-value" not in cleaned
    assert cleaned.count("***") == 2


def test_filter_scrubs_formatted_record() -> None:
    record = logging.LogRecord(
        "bot", logging.INFO, __file__, 1, "auth with %s failed", ("server-secret-value",), None
    )
    RedactionFilter(SECRETS).filter(record)
    assert "server-secret-value" not in record.getMessage()


def test_json_formatter_keeps_identity_fields() -> None:
    record = logging.LogRecord("bot", logging.INFO, __file__, 1, "turn", (), None)
    record.user_id = 111
    record.session_id = "ses_x"
    payload = JsonFormatter().format(record)
    assert '"user_id": 111' in payload
    assert '"session_id": "ses_x"' in payload


def test_safe_exception_hides_secret_from_message() -> None:
    exc = RuntimeError("connect failed for server-secret-value")
    rendered = safe_exception(exc, SECRETS)
    assert "server-secret-value" not in rendered
    assert "RuntimeError" in rendered
