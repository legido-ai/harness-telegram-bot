from __future__ import annotations

from app.telegram.auth import Authorizer
from tests.factories import inbound


def test_allows_listed_user_in_allowed_chat(settings, store) -> None:
    authorizer = Authorizer(settings, store)
    assert authorizer.allow(inbound(user_id=111)) is True
    assert authorizer.rejections == 0


def test_rejects_stranger_without_side_effects(settings, store) -> None:
    authorizer = Authorizer(settings, store)
    assert authorizer.allow(inbound(user_id=999)) is False
    assert authorizer.rejections == 1
    assert store.counts()["turns"] == 0


def test_admin_is_first_configured_user(settings, store) -> None:
    authorizer = Authorizer(settings, store)
    assert authorizer.is_admin(inbound(user_id=111)) is True
    assert authorizer.is_admin(inbound(user_id=222)) is False


def test_registers_participant(settings, store) -> None:
    authorizer = Authorizer(settings, store)
    authorizer.register(inbound(user_id=111, display_name="Ana"))
    assert store.roster() == ["Ana"]
