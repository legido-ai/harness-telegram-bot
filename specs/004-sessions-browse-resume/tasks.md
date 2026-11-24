# Tasks: Sessions browse and resume

**Input**: `specs/004-sessions-browse-resume/spec.md`, `plan.md`
**Tests**: required for every behaviour (constitution II).

## Phase 1 — Store (blocking)

- [x] T001 [US1] Add `SessionEntry` frozen dataclass to `app/store.py` with
      `session_id, title, active, turn_count, last_active, chat_id, thread_id,
      chat_title`.
- [x] T002 [US1] Add `Store.list_session_entries(chat_id, thread_id, limit=10,
      search=None)` ordered by effective last activity (FR-001, FR-002, FR-006).
- [x] T003 [US5] Add `Store.list_all_session_entries(limit=50, search=None)`
      joining `conversations` for the origin title (FR-009, FR-014).
- [x] T004 [US4] Add `Store.set_binding_title()` and `Store.binding_title()`
      (FR-013).
- [x] T005 [US1] Bump `SCHEMA_VERSION` to 6, collapse duplicate bindings and
      add `ux_session_bindings_session`; make `bind_session` replace, not
      duplicate (FR-002, FR-018). Test seeds a v5-shaped table with duplicates.

## Phase 2 — Pure command module

- [x] T006 [US2] `app/telegram/sessions.py`: `parse_args()` for `all`,
      `search`/`find`, target (FR-003..FR-008).
- [x] T007 [US1] `format_listing(entries, *, query, include_source, notice,
      now)` with current marker, turn count, relative activity, empty state,
      and footers (FR-001, FR-006, FR-009).
- [x] T008 [US2] `resolve_target(entries, target)` → `Resolved`,
      `Ambiguous`, `OutOfRange`, `NotFound`; numeric, exact id, unique suffix
      ≥6, exact title, unique title substring (FR-003..FR-005).
- [x] T009 [US4] `clean_title()`: strip, collapse whitespace, 1–60 characters
      (FR-013).

## Phase 3 — Telegram wiring

- [x] T010 [US2] `Runner.busy(key)` (active run or queue depth) (FR-012).
- [x] T011 [US2] `BotApp._activate_session()`: busy check, ownership check for
      non-admins, `session_exists`, bind, refresh dashboard, reply
      (FR-010..FR-012, FR-014).
- [x] T012 [US1] `_cmd_sessions` uses the store query and the formatter; keeps
      one keyboard button per entry (FR-001, FR-016).
- [x] T013 [US2] `_cmd_resume` and `_cmd_switch` route to the same handler
      (FR-007).
- [x] T014 [US5] `_cmd_sessions all`: admin list merges bindings and
      `backend.list_sessions()`, drops unassigned half on `HarnessError`; a
      non-admin gets the scoped list plus the notice (FR-008, FR-009).
- [x] T015 [US4] `_cmd_title` show/set (FR-013).
- [x] T016 [US2] `_callback_switch` calls `_activate_session` and reports its
      error through `answer_callback` (FR-016).
- [x] T017 [US1] `/help` copy and README command table (FR-017).

## Phase 4 — Tests

- [x] T018 `tests/unit/test_sessions.py`: parse table, format (current,
      ordering, empty, search, all, relative time), resolution (ordinal, exact
      id, suffix, title, ambiguity, out of range, not found), title cleaning.
- [x] T019 `tests/unit/test_store.py`: binding dedupe migration, activity
      ordering, search by title/id, rename.
- [x] T020 `tests/integration/test_sessions_command.py`: list, resume by
      number/id/title, `/resume`, `/switch`, search, `/title`, non-admin `all`
      notice, admin `all` with two chats and a harness-only session, gone
      session, busy refusal, repeated switch shows one row, callback switch.

## Phase 5 — Convergence

- [x] T021 `make test` (full suite) and `make lint` clean.
- [x] T022 Peer review (`peer-review` skill); answer every finding.
- [x] T023 Commit on `004-sessions-browse-resume`, push, verify
      `git rev-parse HEAD` equals `origin/main` after merge.

## Phase 6 — Named sessions (2026-11-24)

- [x] T024 [US1] `app/telegram/titles.py`: `derive_title()` from the opening
      message, Hermes rules (FR-019).
- [x] T025 [US1] `Runner.new_session` stops using chat/display name; the first
      recorded turn names the session once (FR-019, FR-020).
- [x] T026 [US1] Schema v7 clears author/chat-shaped titles (FR-021).
- [x] T027 [US1] Listing rows become `N. Title (current) — id`; header and
      footer match Hermes (FR-001).
- [x] T028 Tests: titles unit, naming integration, migration, formatting.

## Traceability

| FR | Tasks |
|---|---|
| FR-001 | T002, T007, T012, T018 |
| FR-002 | T002, T005, T019, T020 |
| FR-003 | T006, T008, T011, T020 |
| FR-004 | T008, T018, T020 |
| FR-005 | T006, T008, T020 |
| FR-006 | T002, T006, T007, T018, T019 |
| FR-007 | T013, T020 |
| FR-008 | T014, T020 |
| FR-009 | T003, T007, T014, T020 |
| FR-010 | T011, T020 |
| FR-011 | T011, T020 |
| FR-012 | T010, T011, T020 |
| FR-013 | T004, T009, T015, T018, T020 |
| FR-014 | T003, T011, T020 |
| FR-015 | all Telegram tasks (no backend branch) |
| FR-016 | T012, T016, T020 |
| FR-017 | T017 |
| FR-018 | T005, T019 |
| FR-019 | T024, T025, T028 |
| FR-020 | T025, T028 |
| FR-021 | T026, T028 |
