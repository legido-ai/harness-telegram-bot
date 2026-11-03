# Tasks: OpenCode Telegram Bot for Shared Conversations

**Input**: Design documents from `/specs/001-telegram-group-bot/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: mandatory for this project (constitution Principle II). Every user
story carries its tests first, and `make test` must pass offline.

**Organization**: tasks grouped by user story so each story is independently
implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable (different files, no ordering dependency)
- **[Story]**: US1..US7 from spec.md

## Path Conventions

Single project at repository root: `app/`, `tests/`, `deploy/`.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create the package layout from plan.md: `app/`, `app/opencode/`, `app/telegram/`, `tests/{unit,contract,integration,fakes}/` with `__init__.py`
- [ ] T002 Pin runtime dependencies in `requirements.txt` and test dependencies in `requirements-dev.txt`
- [ ] T003 [P] Add `pyproject.toml` with ruff and pytest configuration (asyncio mode, testpaths)
- [ ] T004 [P] Add `Makefile` targets: `install`, `test`, `test-unit`, `run`, `build`, `up`, `down`
- [ ] T005 [P] Add `.env.example` documenting every variable with placeholders
- [ ] T006 Add `Dockerfile` (python:3.12-slim, non-root uid 10001, healthcheck) and `.dockerignore`
- [ ] T007 [P] Add `docker-compose.yml` with named volume for `DATA_DIR`, env wiring, restart policy, healthcheck

## Phase 2: Foundational (blocking prerequisites)

- [ ] T008 Implement `app/config.py`: env parsing, allowlist parsing, validation with secret-free errors
- [ ] T009 [P] Implement `app/logging.py`: JSON logger plus redaction filter for token, password and message body fields
- [ ] T010 Implement `app/store.py`: schema v1 DDL, forward migration runner, connection helper with WAL
- [ ] T011 [P] Implement store repositories: conversations, participants, session bindings, turns, pending interactions, delivery ledger
- [ ] T012 [P] Unit tests for config parsing and redaction (`tests/unit/test_config.py`, `tests/unit/test_logging.py`)
- [ ] T013 [P] Unit tests for store CRUD, dedupe and migration (`tests/unit/test_store.py`)
- [ ] T014 Implement `app/opencode/client.py`: httpx async client with basic auth, timeouts and error mapping (contract C1-C8)
- [ ] T015 Implement `app/opencode/events.py`: SSE consumer yielding decoded events with reconnect backoff (contract C9)
- [ ] T016 [P] Build `tests/fakes/opencode.py`: scripted agent server (admission, text deltas, permission ask, form ask, interrupt)
- [ ] T017 [P] Contract tests for the adapter against the OpenAPI shapes (`tests/contract/test_opencode_client.py`)
- [ ] T018 Build `tests/fakes/telegram.py`: recording fake of the Bot API calls the handlers make
- [ ] T019 Implement `app/health.py`: `/healthz`, `/readyz`, `/audit` (no message bodies)
- [ ] T020 Unit tests for health payload states (`tests/unit/test_health.py`)

## Phase 3: User Story 1 — one human in a private chat (P1)

- [ ] T021 [US1] Implement `app/telegram/auth.py` allowlist gate and rejection counter with numeric-id-only logging
- [ ] T022 [P] [US1] Unit tests for the auth gate (`tests/unit/test_auth.py`)
- [ ] T023 [US1] Implement `app/telegram/streaming.py`: coalesced edits, 4096-char splitting, HTML escaping
- [ ] T024 [P] [US1] Unit tests for streaming and splitting (`tests/unit/test_streaming.py`)
- [ ] T025 [US1] Implement `app/telegram/runner.py`: per-conversation queue, run lifecycle, turn recording, `/abort` support
- [ ] T026 [US1] Implement `app/telegram/app.py` handler registration for private text prompts and commands
- [ ] T027 [US1] Wire `app/main.py`: config, store, adapter, event consumer, poller and health server in one loop
- [ ] T028 [US1] Integration test: prompt → streamed answer → abort → restart reuse (`tests/integration/test_private_chat.py`)

## Phase 4: User Story 2 — two humans in one group (P1)

- [ ] T029 [US2] Implement `app/telegram/trigger.py`: entity-based mention/reply/command detection, mention stripping, quoted-context extraction
- [ ] T030 [P] [US2] Unit tests for trigger rules including quoted mentions and empty mentions (`tests/unit/test_trigger.py`)
- [ ] T031 [US2] Implement `app/telegram/identity.py`: speaker block, participant roster, quoted-context block with truncation
- [ ] T032 [P] [US2] Unit tests for identity block and truncation (`tests/unit/test_identity.py`)
- [ ] T033 [US2] Group handler path in `app/telegram/app.py`: allowlisted chat + trigger policy, bot-authored and bot-to-bot filtering
- [ ] T034 [US2] Attribution of answers and per-conversation ordering in `app/telegram/runner.py`
- [ ] T035 [US2] Integration test: two humans, mention + reply, chatter stays silent, ordering (`tests/integration/test_group_chat.py`)

## Phase 5: User Story 3 — sessions per conversation (P2)

- [ ] T036 [US3] Implement lazy session binding per `(chat, topic)` with persistence and recovery (`app/telegram/runner.py`, `app/store.py`)
- [ ] T037 [US3] Implement `/new`, `/sessions`, `/switch` with inline keyboards (`app/telegram/commands.py`, `app/telegram/keyboards.py`)
- [ ] T038 [P] [US3] Unit tests for binding isolation and rebinding history (`tests/unit/test_sessions.py`)
- [ ] T039 [US3] Integration test: two topics keep separate sessions (`tests/integration/test_topics.py`)

## Phase 6: User Story 4 — model and agent control (P2)

- [ ] T040 [US4] Implement `/model` and `/agent` menus with catalogue loading and failure fallback (`app/telegram/commands.py`)
- [ ] T041 [P] [US4] Contract tests for model/agent selection payloads (`tests/contract/test_selection.py`)
- [ ] T042 [US4] Integration test: model change applies to the next prompt (`tests/integration/test_model_selection.py`)

## Phase 7: User Story 5 — approvals and questions (P2)

- [ ] T043 [US5] Implement permission and form keyboards with first-decision-wins state (`app/telegram/keyboards.py`, `app/store.py`)
- [ ] T044 [US5] Implement callback handling for permission/form decisions with attribution (`app/telegram/app.py`)
- [ ] T045 [P] [US5] Unit tests for pending interaction state machine (`tests/unit/test_interactions.py`)
- [ ] T046 [US5] Integration test: second human approves, run continues, decision attributed (`tests/integration/test_approvals.py`)

## Phase 8: User Story 6 — attachments (P3)

- [ ] T047 [US6] Implement attachment intake: size/type limits, temp files under `DATA_DIR/tmp`, cleanup (`app/telegram/attachments.py`)
- [ ] T048 [P] [US6] Unit tests for limit enforcement and mime routing (`tests/unit/test_attachments.py`)
- [ ] T049 [US6] Integration test: photo with caption reaches the adapter as a file (`tests/integration/test_attachments.py`)

## Phase 9: User Story 7 — operator visibility (P3)

- [ ] T050 [US7] Implement `/status` and `/id` commands (`app/telegram/commands.py`)
- [ ] T051 [US7] Wire poller health into `/healthz` (last update age, SSE state) and add `/audit` pagination
- [ ] T052 [US7] Integration test: audit trail answers "who asked" without message bodies (`tests/integration/test_audit.py`)

## Phase 10: Polish and delivery

- [ ] T053 [P] Write `README.md`: what it is, two-human setup, privacy mode note, security model
- [ ] T054 [P] Write `CHANGELOG.md` with the 0.1.0 entry
- [ ] T055 Run `make test` and confirm the suite is green and offline
- [ ] T056 Verify the Docker image builds and runs non-root with a healthy `/healthz`
- [ ] T057 Record verification results in `specs/001-telegram-group-bot/verification.md`

---

## Dependencies per story

- US1 after Phase 1 + Phase 2 (needs store, adapter, streaming).
- US2 after US1 (extends the same handler path).
- US3, US4, US5 after US1; independent of each other.
- US6 after US1 (attachments ride the prompt path).
- US7 after US1 (health and audit).

## Coverage map

| Requirement | Tasks |
|---|---|
| FR-001, FR-005 | T021, T022, T033 |
| FR-002, FR-003 | T031, T032, T034 |
| FR-004 | T036, T038, T039 |
| FR-006..FR-009 | T029, T030, T033 |
| FR-010 | T025, T026, T027, T028 |
| FR-011 | T025, T037 |
| FR-012 | T040, T041, T042 |
| FR-013 | T043, T044, T045, T046 |
| FR-014 | T050 |
| FR-015 | T047, T048, T049 |
| FR-016 | T011, T013 |
| FR-017 | T025, T034, T035 |
| FR-018 | T008, T012 |
| FR-019 | T027 |
| FR-020 | T019, T051 |
| FR-021 | T010, T051, T052 |
| FR-022 | T009, T012 |
| FR-023 | T010, T036 |
