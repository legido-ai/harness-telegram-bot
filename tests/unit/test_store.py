from __future__ import annotations

from app.store import Store


def test_migration_is_idempotent(store: Store) -> None:
    assert store.schema_version() == 6
    store.migrate()
    assert store.schema_version() == 6


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


def test_binding_rows_are_unique_per_session(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)
    store.bind_session(-100, 0, "ses_b", "beta", bound_by=111)
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)

    entries = store.list_session_entries(-100, 0)
    assert [entry.session_id for entry in entries] == ["ses_a", "ses_b"]
    assert [entry.active for entry in entries] == [True, False]


def test_migration_collapses_existing_duplicate_bindings(tmp_path) -> None:
    path = tmp_path / "old.db"
    store = Store(path)
    store.migrate()
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)
    # Reproduce the pre-v6 shape: no unique index, duplicate rows.
    with store._conn:
        store._conn.execute("DROP INDEX ux_session_bindings_session")
        for _ in range(2):
            store._conn.execute(
                "INSERT INTO session_bindings"
                "(chat_id, thread_id, session_id, title, bound_by, bound_at, active) "
                "VALUES(-100, 0, 'ses_a', 'alpha', 111, 1700000000, 0)"
            )
        store._conn.execute("UPDATE meta SET value='5' WHERE key='schema_version'")
    store.close()

    migrated = Store(path)
    migrated.migrate()
    assert migrated.schema_version() == 6
    assert len(migrated.list_bindings(-100, 0)) == 1
    assert migrated.list_session_entries(-100, 0)[0].session_id == "ses_a"


def test_entries_are_ordered_by_last_activity(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_old", "old", bound_by=111)
    store.bind_session(-100, 0, "ses_new", "new", bound_by=111)
    turn_id = store.record_turn(
        chat_id=-100,
        thread_id=0,
        session_id="ses_old",
        user_id=111,
        update_id=51,
        trigger="mention",
    )
    assert turn_id is not None
    with store._conn:
        store._conn.execute("UPDATE turns SET created_at=1900000000 WHERE id=?", (turn_id,))
        store._conn.execute(
            "UPDATE session_bindings SET bound_at=1800000000 WHERE session_id='ses_old'"
        )
        store._conn.execute(
            "UPDATE session_bindings SET bound_at=1800000001 WHERE session_id='ses_new'"
        )

    entries = store.list_session_entries(-100, 0)
    assert [entry.session_id for entry in entries] == ["ses_old", "ses_new"]
    assert entries[0].turn_count == 1
    assert entries[0].last_active == 1900000000


def test_entries_can_be_searched_by_title_or_id(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_deploy1", "Deploy staging", bound_by=111)
    store.bind_session(-100, 0, "ses_docs22", "Write docs", bound_by=111)

    by_title = store.list_session_entries(-100, 0, search="deploy")
    by_id = store.list_session_entries(-100, 0, search="DOCS22")
    assert [entry.session_id for entry in by_title] == ["ses_deploy1"]
    assert [entry.session_id for entry in by_id] == ["ses_docs22"]


def test_all_entries_carry_the_origin_chat(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "ops")
    store.touch_conversation(200, 0, "private", "javi")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)
    store.bind_session(200, 0, "ses_b", "beta", bound_by=222)

    entries = store.list_all_session_entries()
    assert {entry.session_id for entry in entries} == {"ses_a", "ses_b"}
    assert {entry.chat_title for entry in entries} == {"ops", "javi"}


def test_binding_title_can_be_changed(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "alpha", bound_by=111)

    assert store.set_binding_title(-100, 0, "ses_a", "Nightly build") is True
    assert store.binding_title(-100, 0, "ses_a") == "Nightly build"
    assert store.list_session_entries(-100, 0)[0].title == "Nightly build"
    assert store.set_binding_title(-100, 0, "ses_missing", "x") is False


def test_rebinding_without_a_title_keeps_the_existing_one(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_a", "Nightly build", bound_by=111)
    store.bind_session(-100, 0, "ses_a", None, bound_by=111)
    assert store.binding_title(-100, 0, "ses_a") == "Nightly build"


def test_search_casefolds_non_ascii_titles(store: Store) -> None:
    store.touch_conversation(-100, 0, "supergroup", "room")
    store.bind_session(-100, 0, "ses_nandu", "Ñandú deploy", bound_by=111)
    found = store.list_session_entries(-100, 0, search="ñANDÚ")
    assert [entry.session_id for entry in found] == ["ses_nandu"]


def test_migration_preserves_an_active_duplicate_and_its_title(tmp_path) -> None:
    path = tmp_path / "old.db"
    store = Store(path)
    store.migrate()
    store.touch_conversation(-100, 0, "supergroup", "room")
    with store._conn:
        store._conn.execute("DROP INDEX ux_session_bindings_session")
        store._conn.execute("DELETE FROM session_bindings")
        store._conn.execute(
            "INSERT INTO session_bindings"
            "(id, chat_id, thread_id, session_id, title, bound_by, bound_at, active) "
            "VALUES(1, -100, 0, 'ses_a', 'Old title', 111, 1700000000, 1)"
        )
        store._conn.execute(
            "INSERT INTO session_bindings"
            "(id, chat_id, thread_id, session_id, title, bound_by, bound_at, active) "
            "VALUES(2, -100, 0, 'ses_a', NULL, 111, 1700000001, 0)"
        )
        store._conn.execute("UPDATE meta SET value='5' WHERE key='schema_version'")
    store.close()

    migrated = Store(path)
    migrated.migrate()
    entries = migrated.list_session_entries(-100, 0)
    assert len(entries) == 1
    assert entries[0].active is True
    assert entries[0].title == "Old title"
