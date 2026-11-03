"""Allowlist gates. Silent to strangers, numeric ids only in logs."""

from __future__ import annotations

import logging

from app.config import Settings
from app.store import Store
from app.telegram.types import Inbound

log = logging.getLogger("bot.auth")


class Authorizer:
    def __init__(self, settings: Settings, store: Store) -> None:
        self._settings = settings
        self._store = store
        self.rejections = 0

    def allow(self, message: Inbound) -> bool:
        allowed = self._settings.is_user_allowed(message.user_id) and self._settings.is_chat_allowed(
            message.chat_id
        )
        if not allowed:
            self.rejections += 1
            log.warning(
                "unauthorized access attempt",
                extra={"user_id": message.user_id, "chat_id": message.chat_id},
            )
        return allowed

    def is_admin(self, message: Inbound) -> bool:
        admins = sorted(self._settings.allowed_user_ids)
        return bool(admins) and message.user_id == admins[0]

    def register(self, message: Inbound) -> None:
        self._store.touch_participant(
            message.user_id,
            message.display_name,
            message.username,
            allowlisted=self._settings.is_user_allowed(message.user_id),
        )
