"""SQLite persistence for conversations, bindings, turns and approvals.

All durable state lives in one file under ``DATA_DIR`` (constitution Principle
VI). Calls are synchronous and short; they run on the event loop deliberately so
ordering is obvious and tests stay free of threads.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3
TTS_MODES = ("off", "all", "auto")

DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    chat_id           INTEGER NOT NULL,
    thread_id         INTEGER NOT NULL DEFAULT 0,
    kind              TEXT NOT NULL,
    title             TEXT,
    trigger_policy    TEXT NOT NULL DEFAULT 'mention',
    tts_mode          TEXT NOT NULL DEFAULT 'off',
    model_json        TEXT,
    agent             TEXT,
    active_session_id TEXT,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    PRIMARY KEY (chat_id, thread_id)
);

CREATE TABLE IF NOT EXISTS participants (
    user_id        INTEGER PRIMARY KEY,
    display_name   TEXT NOT NULL,
    username       TEXT,
    is_allowlisted INTEGER NOT NULL DEFAULT 0,
    first_seen     INTEGER NOT NULL,
    last_seen      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS session_bindings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    thread_id  INTEGER NOT NULL DEFAULT 0,
    session_id TEXT NOT NULL,
    title      TEXT,
    bound_by   INTEGER NOT NULL,
    bound_at   INTEGER NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    thread_id   INTEGER NOT NULL DEFAULT 0,
    session_id  TEXT,
    user_id     INTEGER NOT NULL,
    update_id   INTEGER NOT NULL UNIQUE,
    trigger     TEXT NOT NULL,
    quote_of    INTEGER,
    status      TEXT NOT NULL,
    started_at  INTEGER,
    ended_at    INTEGER,
    cost_usd    REAL,
    tokens      INTEGER,
    error_kind  TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_interactions (
    id                  TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    chat_id             INTEGER NOT NULL,
    thread_id           INTEGER NOT NULL DEFAULT 0,
    telegram_message_id INTEGER,
    payload_json        TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'pending',
    decided_by          INTEGER,
    decided_at          INTEGER,
    created_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery (
    update_id INTEGER PRIMARY KEY,
    seen_at   INTEGER NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class Conversation:
    chat_id: int
    thread_id: int
    kind: str
    title: str | None
    trigger_policy: str
    tts_mode: str
    model_json: str | None
    agent: str | None
    active_session_id: str | None

    @property
    def model(self) -> dict[str, str] | None:
        return json.loads(self.model_json) if self.model_json else None


@dataclass(frozen=True, slots=True)
class Binding:
    session_id: str
    title: str | None
    bound_by: int
    bound_at: int
    active: bool


@dataclass(frozen=True, slots=True)
class Turn:
    id: int
    chat_id: int
    thread_id: int
    session_id: str | None
    user_id: int
    update_id: int
    trigger: str
    quote_of: int | None
    status: str
    created_at: int
    ended_at: int | None
    cost_usd: float | None
    tokens: int | None


@dataclass(frozen=True, slots=True)
class Pending:
    id: str
    kind: str
    session_id: str
    chat_id: int
    thread_id: int
    telegram_message_id: int | None
    payload: dict[str, Any]
    state: str
    decided_by: int | None


def _now() -> int:
    return int(time.time())


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        self._conn.close()

    # -- schema ---------------------------------------------------------

    def migrate(self) -> int:
        with self._conn:
            self._conn.executescript(DDL)
            row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            current = int(row["value"]) if row else 0
            if current < 2:
                columns = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(conversations)").fetchall()
                }
                if "pinned_message_id" not in columns:
                    self._conn.execute(
                        "ALTER TABLE conversations ADD COLUMN pinned_message_id INTEGER"
                    )
            if current < 3:
                columns = {
                    row["name"]
                    for row in self._conn.execute("PRAGMA table_info(conversations)").fetchall()
                }
                if "tts_mode" not in columns:
                    self._conn.execute(
                        "ALTER TABLE conversations ADD COLUMN tts_mode TEXT NOT NULL DEFAULT 'off'"
                    )
            if current < SCHEMA_VERSION:
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('started_at', ?)", (str(_now()),)
            )
        return SCHEMA_VERSION

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row["value"]) if row else 0

    # -- delivery ledger -------------------------------------------------

    def mark_seen(self, update_id: int) -> bool:
        """Return True when this update is new, False when already processed."""

        with self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO delivery(update_id, seen_at) VALUES(?, ?)",
                (update_id, _now()),
            )
        return cur.rowcount == 1

    def prune_delivery(self, keep: int = 5000) -> None:
        with self._conn:
            self._conn.execute(
                "DELETE FROM delivery WHERE update_id NOT IN "
                "(SELECT update_id FROM delivery ORDER BY update_id DESC LIMIT ?)",
                (keep,),
            )

    # -- conversations ---------------------------------------------------

    def touch_conversation(
        self, chat_id: int, thread_id: int, kind: str, title: str | None
    ) -> Conversation:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO conversations(chat_id, thread_id, kind, title, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, thread_id) DO UPDATE SET
                    title = COALESCE(excluded.title, conversations.title),
                    updated_at = excluded.updated_at
                """,
                (chat_id, thread_id, kind, title, now, now),
            )
        conversation = self.get_conversation(chat_id, thread_id)
        assert conversation is not None
        return conversation

    def get_conversation(self, chat_id: int, thread_id: int = 0) -> Conversation | None:
        row = self._conn.execute(
            "SELECT * FROM conversations WHERE chat_id=? AND thread_id=?", (chat_id, thread_id)
        ).fetchone()
        return self._conversation(row)

    @staticmethod
    def _conversation(row: sqlite3.Row | None) -> Conversation | None:
        if row is None:
            return None
        return Conversation(
            chat_id=row["chat_id"],
            thread_id=row["thread_id"],
            kind=row["kind"],
            title=row["title"],
            trigger_policy=row["trigger_policy"],
            tts_mode=row["tts_mode"],
            model_json=row["model_json"],
            agent=row["agent"],
            active_session_id=row["active_session_id"],
        )

    def _set_column(self, chat_id: int, thread_id: int, column: str, value: Any) -> None:
        allowed = {"trigger_policy", "tts_mode", "model_json", "agent", "active_session_id", "title"}
        if column not in allowed:
            raise ValueError(f"column not settable: {column}")
        with self._conn:
            self._conn.execute(
                f"UPDATE conversations SET {column}=?, updated_at=? WHERE chat_id=? AND thread_id=?",
                (value, _now(), chat_id, thread_id),
            )

    def pinned_message_id(self, chat_id: int, thread_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT pinned_message_id FROM conversations WHERE chat_id=? AND thread_id=?",
            (chat_id, thread_id),
        ).fetchone()
        return row["pinned_message_id"] if row and row["pinned_message_id"] else None

    def set_pinned_message_id(self, chat_id: int, thread_id: int, message_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET pinned_message_id=?, updated_at=? "
                "WHERE chat_id=? AND thread_id=?",
                (message_id, _now(), chat_id, thread_id),
            )

    def set_trigger_policy(self, chat_id: int, thread_id: int, policy: str) -> None:
        if policy not in ("mention", "all"):
            raise ValueError("invalid trigger policy")
        self._set_column(chat_id, thread_id, "trigger_policy", policy)

    def set_tts_mode(self, chat_id: int, thread_id: int, mode: str) -> None:
        if mode not in TTS_MODES:
            raise ValueError("invalid tts mode")
        self._set_column(chat_id, thread_id, "tts_mode", mode)

    def set_model(self, chat_id: int, thread_id: int, model: dict[str, str] | None) -> None:
        self._set_column(chat_id, thread_id, "model_json", json.dumps(model) if model else None)

    def set_agent(self, chat_id: int, thread_id: int, agent: str | None) -> None:
        self._set_column(chat_id, thread_id, "agent", agent)

    # -- participants ----------------------------------------------------

    def touch_participant(
        self, user_id: int, display_name: str, username: str | None, allowlisted: bool
    ) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO participants(user_id, display_name, username, is_allowlisted, first_seen, last_seen)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    username = excluded.username,
                    is_allowlisted = excluded.is_allowlisted,
                    last_seen = excluded.last_seen
                """,
                (user_id, display_name, username, 1 if allowlisted else 0, now, now),
            )

    def roster(self, limit: int = 10) -> list[str]:
        rows = self._conn.execute(
            "SELECT display_name FROM participants WHERE is_allowlisted=1 "
            "ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [row["display_name"] for row in rows]

    def participant_name(self, user_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT display_name FROM participants WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["display_name"] if row else None

    # -- session bindings ------------------------------------------------

    def bind_session(
        self, chat_id: int, thread_id: int, session_id: str, title: str | None, bound_by: int
    ) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                "UPDATE session_bindings SET active=0 WHERE chat_id=? AND thread_id=?",
                (chat_id, thread_id),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO session_bindings"
                "(chat_id, thread_id, session_id, title, bound_by, bound_at, active) "
                "VALUES(?, ?, ?, ?, ?, ?, 1)",
                (chat_id, thread_id, session_id, title, bound_by, now),
            )
            self._conn.execute(
                "UPDATE conversations SET active_session_id=?, updated_at=? "
                "WHERE chat_id=? AND thread_id=?",
                (session_id, now, chat_id, thread_id),
            )

    def clear_session(self, chat_id: int, thread_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE session_bindings SET active=0 WHERE chat_id=? AND thread_id=?",
                (chat_id, thread_id),
            )
            self._conn.execute(
                "UPDATE conversations SET active_session_id=NULL, updated_at=? "
                "WHERE chat_id=? AND thread_id=?",
                (_now(), chat_id, thread_id),
            )

    def list_bindings(self, chat_id: int, thread_id: int, limit: int = 10) -> list[Binding]:
        rows = self._conn.execute(
            "SELECT session_id, title, bound_by, bound_at, active FROM session_bindings "
            "WHERE chat_id=? AND thread_id=? ORDER BY id DESC LIMIT ?",
            (chat_id, thread_id, limit),
        ).fetchall()
        return [
            Binding(
                session_id=row["session_id"],
                title=row["title"],
                bound_by=row["bound_by"],
                bound_at=row["bound_at"],
                active=bool(row["active"]),
            )
            for row in rows
        ]

    # -- turns -----------------------------------------------------------

    def record_turn(
        self,
        *,
        chat_id: int,
        thread_id: int,
        session_id: str | None,
        user_id: int,
        update_id: int,
        trigger: str,
        quote_of: int | None = None,
        status: str = "queued",
    ) -> int | None:
        """Insert a turn. Returns None when this update was already recorded."""

        try:
            with self._conn:
                cur = self._conn.execute(
                    "INSERT INTO turns(chat_id, thread_id, session_id, user_id, update_id, trigger,"
                    " quote_of, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chat_id,
                        thread_id,
                        session_id,
                        user_id,
                        update_id,
                        trigger,
                        quote_of,
                        status,
                        _now(),
                    ),
                )
        except sqlite3.IntegrityError:
            return None
        return int(cur.lastrowid)

    def attach_turn_session(self, turn_id: int, session_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE turns SET session_id=? WHERE id=? AND session_id IS NULL",
                (session_id, turn_id),
            )

    def start_turn(self, turn_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE turns SET status='running', started_at=? WHERE id=?", (_now(), turn_id)
            )

    def finish_turn(
        self,
        turn_id: int,
        status: str,
        *,
        error_kind: str | None = None,
        cost_usd: float | None = None,
        tokens: int | None = None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE turns SET status=?, ended_at=?, error_kind=?, cost_usd=COALESCE(?, cost_usd),"
                " tokens=COALESCE(?, tokens) WHERE id=?",
                (status, _now(), error_kind, cost_usd, tokens, turn_id),
            )

    def turns_for_session(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM turns WHERE session_id=?", (session_id,)
        ).fetchone()
        return int(row["n"])

    def recent_turns(self, limit: int = 20) -> list[Turn]:
        rows = self._conn.execute(
            "SELECT * FROM turns ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            Turn(
                id=row["id"],
                chat_id=row["chat_id"],
                thread_id=row["thread_id"],
                session_id=row["session_id"],
                user_id=row["user_id"],
                update_id=row["update_id"],
                trigger=row["trigger"],
                quote_of=row["quote_of"],
                status=row["status"],
                created_at=row["created_at"],
                ended_at=row["ended_at"],
                cost_usd=row["cost_usd"],
                tokens=row["tokens"],
            )
            for row in rows
        ]

    # -- pending interactions -------------------------------------------

    def create_pending(
        self,
        *,
        pending_id: str,
        kind: str,
        session_id: str,
        chat_id: int,
        thread_id: int,
        telegram_message_id: int | None,
        payload: dict[str, Any],
    ) -> tuple[Pending | None, bool]:
        """Insert a pending interaction. Returns (existing_or_new, created)."""

        existing = self.get_pending(pending_id)
        if existing is not None and existing.state == "pending":
            return existing, False
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_interactions(id, kind, session_id, chat_id, thread_id,"
                " telegram_message_id, payload_json, state, created_at)"
                " VALUES(?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    pending_id,
                    kind,
                    session_id,
                    chat_id,
                    thread_id,
                    telegram_message_id,
                    json.dumps(payload),
                    _now(),
                ),
            )
        return self.get_pending(pending_id), True

    def set_pending_message(self, pending_id: str, message_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE pending_interactions SET telegram_message_id=? WHERE id=?",
                (message_id, pending_id),
            )

    def get_pending(self, pending_id: str) -> Pending | None:
        row = self._conn.execute(
            "SELECT * FROM pending_interactions WHERE id=?", (pending_id,)
        ).fetchone()
        if row is None:
            return None
        return Pending(
            id=row["id"],
            kind=row["kind"],
            session_id=row["session_id"],
            chat_id=row["chat_id"],
            thread_id=row["thread_id"],
            telegram_message_id=row["telegram_message_id"],
            payload=json.loads(row["payload_json"]),
            state=row["state"],
            decided_by=row["decided_by"],
        )

    def decide_pending(self, pending_id: str, user_id: int, state: str) -> tuple[bool, Pending | None]:
        """First decision wins. Returns (accepted, current)."""

        with self._conn:
            cur = self._conn.execute(
                "UPDATE pending_interactions SET state=?, decided_by=?, decided_at=? "
                "WHERE id=? AND state='pending'",
                (state, user_id, _now(), pending_id),
            )
        return cur.rowcount == 1, self.get_pending(pending_id)

    def cancel_pending_for_session(self, session_id: str) -> int:
        with self._conn:
            cur = self._conn.execute(
                "UPDATE pending_interactions SET state='cancelled', decided_at=? "
                "WHERE session_id=? AND state='pending'",
                (_now(), session_id),
            )
        return cur.rowcount

    def pending_for_session(self, session_id: str) -> list[Pending]:
        rows = self._conn.execute(
            "SELECT id FROM pending_interactions WHERE session_id=? AND state='pending'", (session_id,)
        ).fetchall()
        result: list[Pending] = []
        for row in rows:
            pending = self.get_pending(row["id"])
            if pending:
                result.append(pending)
        return result

    # -- audit -----------------------------------------------------------

    def audit(self, limit: int = 20) -> list[dict[str, Any]]:
        turns = self.recent_turns(limit)
        names = {row["user_id"]: row["display_name"] for row in self._conn.execute(
            "SELECT user_id, display_name FROM participants"
        ).fetchall()}
        return [
            {
                "turn_id": t.id,
                "chat_id": t.chat_id,
                "thread_id": t.thread_id,
                "session_id": t.session_id,
                "user_id": t.user_id,
                "user": names.get(t.user_id, "unknown"),
                "trigger": t.trigger,
                "status": t.status,
                "created_at": t.created_at,
                "ended_at": t.ended_at,
                "cost_usd": t.cost_usd,
                "tokens": t.tokens,
            }
            for t in turns
        ]

    def counts(self) -> dict[str, int]:
        def scalar(sql: str) -> int:
            row = self._conn.execute(sql).fetchone()
            return int(row[0]) if row else 0

        return {
            "conversations": scalar("SELECT COUNT(*) FROM conversations"),
            "turns": scalar("SELECT COUNT(*) FROM turns"),
            "pending": scalar("SELECT COUNT(*) FROM pending_interactions WHERE state='pending'"),
        }

    def sessions_for_chat(self, chat_id: int) -> Iterable[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT session_id FROM session_bindings WHERE chat_id=?", (chat_id,)
        ).fetchall()
        return [row["session_id"] for row in rows]
