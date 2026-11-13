# Tasks: One Telegram bridge for OpenCode and Pi

**Branch**: `003-unified-backend` | **Spec**: `specs/003-unified-backend/spec.md`
**Plan**: `specs/003-unified-backend/plan.md`

Legend: `[P]` can run in parallel with siblings in the same phase.

## Phase 1 — Setup

- [x] T001 Create `legido-ai/harness-telegram-bot` and seed `main` from `opencode-telegram-bot` history
- [x] T002 Create the feature branch and spec directory (`003-unified-backend`)
- [x] T003 Write `spec.md`, `plan.md`, `contracts/backend.md`, `tasks.md`
- [ ] T004 Rewrite `README.md`, `CHANGELOG.md`, `.env.example` and `pyproject.toml` for the merged project

## Phase 2 — Foundational (blocks both backends)

- [ ] T005 `app/backends/base.py`: `Backend` protocol, `SessionRef`, `ModelOption`, `AgentOption`, `RunOutcome`
- [ ] T006 `app/backends/errors.py`: move the shared taxonomy out of `app/opencode/errors.py`
- [ ] T007 `app/backends/__init__.py`: `build_backend(settings)` factory with `BACKEND` validation
- [ ] T008 `app/config.py`: add `backend`, Pi settings, per-backend validation, `entrypoint` model vars
- [ ] T009 `app/store.py`: `meta` table with the owning backend; clear bindings on mismatch
- [ ] T010 `app/main.py`: build the backend, wire health, stop cleanly on shutdown
- [ ] T011 `app/health.py`: report backend name and backend reachability

## Phase 3 — US1: OpenCode parity (P1)

- [ ] T012 Move `app/opencode/{client,events,errors}.py` → `app/backends/opencode/`
- [ ] T013 `app/backends/opencode/backend.py`: implement `Backend` over the existing client + SSE bus
- [ ] T014 Refactor `app/telegram/runner.py` to call `Backend.run(...)` with delta/interaction callbacks
- [ ] T015 Refactor `app/telegram/app.py` to use the backend for sessions, models, agents, permissions, forms
- [ ] T016 Keep the OpenCode behaviour identical: keyboards, dashboard, sign-off, trigger, attachments, speech
- [ ] T017 Update imports across `app/telegram/*` and `app/speech/*` so nothing references `app.opencode`
- [ ] T018 Port the existing 24 test files to the new module paths and confirm they pass

## Phase 4 — US2: Pi backend (P1)

- [ ] T019 `app/backends/pi/rpc.py`: JSONL child-process client (spawn, command, stdout pump, abort, close)
- [ ] T020 `app/backends/pi/sessions.py`: list, label and resolve session files in `PI_SESSION_DIR`
- [ ] T021 `app/backends/pi/backend.py`: `create_session`, `run`, `interrupt`, `stats`, `models`, `sessions`, switching
- [ ] T022 Idle reaping with `PI_IDLE_MINUTES`; resume the bound file after a reap
- [ ] T023 `format_elapsed` in `app/telegram/footer.py`; status bubble and sign-off both use it
- [ ] T024 Pi feature gates: `/agent`, approvals and forms reply "not available on the Pi backend"
- [ ] T025 Pi attachments: images forwarded, other types refused with a clear message
- [ ] T026 Pi audio: spoken text derived from the answer, never a second prompt

## Phase 5 — US3: one image, two services (P2)

- [ ] T027 Dockerfile: python 3.12 + node 22 + pi CLI + both dependency sets + healthcheck
- [ ] T028 `entrypoint.sh`: write `models.json` only when `PI_PROVIDER` is set, then exec
- [ ] T029 `.github/workflows/publish.yml`: one multi-arch image, `latest`/version/`sha-*` tags
- [ ] T030 `deploy/`: Compose snippets for both services (OpenCode and Pi) from the same image

## Phase 6 — Tests

- [ ] T031 `tests/fakes/pi_rpc.py`: fake Pi executable for offline adapter tests
- [ ] T032 `tests/unit/test_pi_backend.py`: prompt, stats, models, switch, abort, reap, attachment refusal
- [ ] T033 `tests/contract/test_backend_protocol.py`: both adapters satisfy the same scripted run
- [ ] T034 `tests/unit/test_elapsed.py`: 59s, 60s, 90s, 3600s formatting
- [ ] T035 Full suite offline: `pytest -q` green, no network, no credentials

## Phase 7 — US4: deploy on oci2 (P2)

- [ ] T036 Tag rollback images for the current `opencode2` bot and `pi`
- [ ] T037 Recreate `opencode2-telegram-bot` (`BACKEND=opencode`) and `pi` (`BACKEND=pi`) from the new image
- [ ] T038 Verify `/healthz`, one prompt each, and a >60 s Pi bubble showing `m ss`
- [ ] T039 Record the deployed digest, the rollback commands and the validation in `verification.md`

## Phase 8 — Polish

- [ ] T040 Update `README.md` (both backends, env matrix, deploy, rollback) and `CHANGELOG.md`
- [ ] T041 Update `specs/003-unified-backend/verification.md` with the validated results
- [ ] T042 Merge `003-unified-backend` into `main` and push
