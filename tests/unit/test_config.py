from __future__ import annotations

import pytest

from app.config import ConfigError, Settings


def test_missing_variables_are_named_but_values_are_not_echoed() -> None:
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env({})
    message = str(excinfo.value)
    assert "TELEGRAM_BOT_TOKEN" in message
    assert "OPENCODE_SERVER_PASSWORD" in message


def test_parses_allowlists_and_trigger(settings: Settings) -> None:
    assert settings.allowed_user_ids == frozenset({111, 222})
    assert settings.trigger == "mention"
    assert settings.is_user_allowed(111)
    assert not settings.is_user_allowed(999)


def test_private_chat_follows_user_allowlist(settings: Settings) -> None:
    assert settings.is_chat_allowed(111)
    assert not settings.is_chat_allowed(999)


def test_group_chat_allowed_without_chat_allowlist(settings: Settings) -> None:
    assert settings.is_chat_allowed(-100999)


def test_group_chat_requires_explicit_id_when_configured(tmp_path) -> None:
    settings = Settings.from_env(
        {
            "TELEGRAM_BOT_TOKEN": "123456:TESTTOKENVALUE",
            "TELEGRAM_ALLOWED_USER_IDS": "111",
            "TELEGRAM_ALLOWED_CHAT_IDS": "-100777",
            "OPENCODE_SERVER_PASSWORD": "server-secret-value",
            "DATA_DIR": str(tmp_path),
        }
    )
    assert settings.is_chat_allowed(-100777)
    assert not settings.is_chat_allowed(-100888)


def test_rejects_unknown_trigger(tmp_path) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "123456:TESTTOKENVALUE",
                "TELEGRAM_ALLOWED_USER_IDS": "111",
                "TELEGRAM_TRIGGER": "shout",
                "OPENCODE_SERVER_PASSWORD": "server-secret-value",
                "DATA_DIR": str(tmp_path),
            }
        )


def test_rejects_bad_attachment_limit(tmp_path) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "123456:TESTTOKENVALUE",
                "TELEGRAM_ALLOWED_USER_IDS": "111",
                "MAX_ATTACHMENT_MB": "900",
                "OPENCODE_SERVER_PASSWORD": "server-secret-value",
                "DATA_DIR": str(tmp_path),
            }
        )
