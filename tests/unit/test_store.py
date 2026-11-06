from __future__ import annotations

from app.store import Store


def test_migration_is_idempotent(store: Store) -> None:
    assert store.schema_version() == 4
    store.migrate()
    assert store.schema_version() == 4


def test_delivery_ledger_dedupes_updates(store: Store) -> None:
    assert store.mark_seen(42) is True
    assert store.mark_seen(42) is False


def test_turn_recording_is_unique_per_update(store: Store) -> None:
    kwargs = dict(
        chat_id=-100,
        thread_id=0,
        session_id="ses_1",
        user_id=111,
        update_id=7,
        trigger="mention",
    )
    first = store.record_turn(**kwargs)
    second = store.record_turn(**kwargs)
    assert first is not None
    assert second is None


def test_binding_is_isolated_per_topic(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.touch_conversation(-100, 5, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)
    store.bind_session(-100, 5, "ses_b", "beta", bound_by=222)

    assert store.get_conversation(-100, 0).active_session_id == "ses_a"
    assert store.get_conversation(-100, 5).active_session_id == "ses_b"


def test_rebinding_keeps_history(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)
    store.bind_session(-100, 0, "ses_b", "beta", bound_by=222)
    bindings = store.list_bindings(-100, 0)
    assert [b.session_id for b in bindings] == ["ses_b", "ses_a"]
    assert bindings[0].active and not bindings[1].active


def test_first_permission_decision_wins(store: Store) -> None:
    store.create_pending(
        pending_id="permission:req1",
        kind="permission",
        session_id="ses_a",
        chat_id=-100,
        thread_id=0,
        telegram_message_id=5,
        payload={"tool": "bash"},
    )
    accepted, pending = store.decide_pending("permission:req1", 111, "allowed")
    assert accepted and pending is not None and pending.decided_by == 111

    accepted_again, pending_again = store.decide_pending("permission:req1", 222, "denied")
    assert accepted_again is False
    assert pending_again.state == "allowed"
    assert pending_again.decided_by == 111


def test_touch_conversation_preserves_title(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "OC3")
    store.touch_conversation(-100, 0, "supergroup", None)
    assert store.get_conversation(-100, 0).title == "OC3"


def test_audit_contains_identity_but_no_message_body(store: Store) -> None:
    store.touch_participant(111, "Ana", "ana", allowlisted=True)
    store.record_turn(
        chat_id=-100,
        thread_id=0,
        session_id="ses_a",
        user_id=111,
        update_id=15,
        trigger="mention",
    )
    entries = store.audit()
    assert entries[0]["user"] == "Ana"
    assert entries[0]["user_id"] == 111
    assert "text" not in entries[0]
