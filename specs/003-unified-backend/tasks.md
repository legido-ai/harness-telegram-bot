# Tasks: One Telegram bridge for OpenCode and Pi

**Branch**: `003-unified-backend` | **Spec**: `specs/003-unified-backend/spec.md`
**Plan**: `specs/003-unified-backend/plan.md`

Legend: `[P]` can run in parallel with siblings in the same phase.

## Phase 1 — Setup

- [x] T001 Create `legido-ai/harness-telegram-bot` and seed `main` from `opencode-telegram-bot` history
- [x] T002 Create the feature branch and spec directory (`003-unified-backend`)
- [x] T003 Write `spec.md`, `plan.md`, `contracts/backend.md`, `tasks.md`
- [x] T004 Rewrite `README.md`, `CHANGELOG.md`, `.env.example` and `pyproject.toml` for the merged project

## Phase 2 — Foundational (blocks both backends)

- [x] T005 `app/backends/base.py`: `Backend` protocol, `SessionRef`, `ModelOption`, `AgentOption`, `RunOutcome`
- [x] T006 `app/backends/errors.py`: move the shared taxonomy out of `app/opencode/errors.py`
- [x] T007 `app/backends/__init__.py`: `build_backend(settings)` factory with `BACKEND` validation
- [x] T008 `app/config.py`: add `backend`, Pi settings, per-backend validation, `entrypoint` model vars
- [x] T009 `app/store.py`: `meta` table with the owning backend; clear bindings on mismatch
- [x] T010 `app/main.py`: build the backend, wire health, stop cleanly on shutdown
- [x] T011 `app/health.py`: report backend name and backend reachability

## Phase 3 — US1: OpenCode parity (P1)

- [x] T012 Move `app/opencode/{client,events,errors}.py` → `app/backends/opencode/`
- [x] T013 `app/backends/opencode/backend.py`: implement `Backend` over the existing client + SSE bus
- [x] T014 Refactor `app/telegram/runner.py` to call `Backend.run(...)` with delta/interaction callbacks
- [x] T015 Refactor `app/telegram/app.py` to use the backend for sessions, models, agents, permissions, forms
- [x] T016 Keep the OpenCode behaviour identical: keyboards, dashboard, sign-off, trigger, attachments, speech
- [x] T017 Update imports across `app/telegram/*` and `app/speech/*` so nothing references `app.opencode`
- [x] T018 Port the existing 24 test files to the new module paths and confirm they pass

## Phase 4 — US2: Pi backend (P1)

- [x] T019 `app/backends/pi/rpc.py`: JSONL child-process client (spawn, command, stdout pump, abort, close)
- [x] T020 `app/backends/pi/sessions.py`: list, label and resolve session files in `PI_SESSION_DIR`
- [x] T021 `app/backends/pi/backend.py`: `create_session`, `run`, `interrupt`, `stats`, `models`, `sessions`, switching
- [x] T022 Idle reaping with `PI_IDLE_MINUTES`; resume the bound file after a reap
- [x] T023 `format_elapsed` in `app/telegram/footer.py`; status bubble and sign-off both use it
- [x] T024 Pi feature gates: `/agent`, approvals and forms reply "not available on the Pi backend"
- [x] T025 Pi attachments: images forwarded, other types refused with a clear message
- [x] T026 Pi audio: spoken text derived from the answer, never a second prompt

## Phase 5 — US3: one image, two services (P2)

- [x] T027 Dockerfile: python 3.12 + node 22 + pi CLI + both dependency sets + healthcheck
- [x] T028 `entrypoint.sh`: write `models.json` only when `PI_PROVIDER` is set, then exec
- [x] T029 `.github/workflows/publish.yml`: one multi-arch image, `latest`/version/`sha-*` tags
- [x] T030 `deploy/`: Compose snippets for both services (OpenCode and Pi) from the same image

## Phase 6 — Tests

- [x] T031 `tests/fakes/pi_rpc.py`: fake Pi executable for offline adapter tests
- [x] T032 `tests/unit/test_pi_backend.py`: prompt, stats, models, switch, abort, reap, attachment refusal
- [x] T033 `tests/contract/test_backend_protocol.py`: both adapters satisfy the same scripted run
- [x] T034 `tests/unit/test_elapsed.py`: 59s, 60s, 90s, 3600s formatting
- [x] T035 Full suite offline: `pytest -q` green, no network, no credentials

## Phase 7 — US4: deploy on oci2 (P2)

- [x] T036 Tag rollback images for the current `opencode2` bot and `pi`
- [x] T037 Recreate `opencode2-telegram-bot` (`BACKEND=opencode`) and `pi` (`BACKEND=pi`) from the new image
- [x] T038 Verify `/healthz`, one prompt each, and a >60 s Pi bubble showing `m ss`
- [x] T039 Record the deployed digest, the rollback commands and the validation in `verification.md`

## Phase 8 — Polish

- [x] T040 Update `README.md` (both backends, env matrix, deploy, rollback) and `CHANGELOG.md`
- [x] T041 Update `specs/003-unified-backend/verification.md` with the validated results
- [x] T042 Merge `003-unified-backend` into `main` and push
