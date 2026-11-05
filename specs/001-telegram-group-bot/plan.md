# Implementation Plan: OpenCode Telegram Bot for Shared Conversations

**Branch**: `001-telegram-group-bot` | **Date**: 2026-11-03 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-telegram-group-bot/spec.md`

## Summary

Deliver a Python service that drives an OpenCode V2 server from Telegram, with
first-class support for a group where several allowlisted humans talk to one
agent. One asyncio process runs three cooperating parts: a Telegram long-poller,
a per-conversation run queue, and a health endpoint. An OpenCode adapter owns all
HTTP and SSE traffic to the agent server; a SQLite store owns conversation,
session, dedupe and audit state. Attribution is structural: every prompt is
tagged with the Telegram author, and every conversation is keyed by chat plus
topic.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: `python-telegram-bot` 22.x (async, long polling),
`httpx` (OpenCode HTTP + SSE), `sqlite3` (stdlib state), `fastapi` + `uvicorn`
(health and operator surface only), `pytest` + `pytest-asyncio` + `respx`
(hermetic tests)
**Storage**: SQLite file under `DATA_DIR` on a named volume
**Testing**: `pytest`; `make test` runs unit, contract and integration suites
fully offline against fakes for both Telegram and OpenCode
**Target Platform**: Linux container, non-root UID 10001, amd64/arm64
**Project Type**: single service (long-running bot + health endpoint)
**Performance Goals**: first progress visible within 3 s of a prompt; streamed
edits coalesced to <=1 per second per message; 5 concurrent conversations
without blocking the poller
**Constraints**: no inbound network exposure except loopback health; no
webhook; single poller per token; findings from Telegram stay under the 4096
character cap; no message bodies in logs
**Scale/Scope**: 1-10 conversations, 2-5 humans per group, thousands of turns

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|---|---|---|
| I. Spec-Driven Development | Spec `001` committed on its own branch before code | PASS |
| II. Test-First | Every FR maps to a test in `tasks.md`; `make test` offline | PASS (planned) |
| III. Non-root container | `Dockerfile` with uid 10001, `/healthz` reporting poller state | PASS (planned) |
| IV. Secret hygiene | Token and server password from env only; redaction test | PASS (planned) |
| V. Single poller | 409 detection surfaced as hard error; `update_id` dedupe | PASS (planned) |
| VI. Persistent state | SQLite in `DATA_DIR`, forward migration on start | PASS (planned) |
| VII. Multi-human attribution | Author stamped in prompt, conversation scoping, group triggers | PASS (planned) |
| VIII. OpenCode V2 fidelity | Single adapter, contract tests pinned to OpenAPI shapes | PASS (planned) |

No violations; Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-telegram-group-bot/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── opencode-api.md
│   └── telegram-interaction.md
├── checklists/
│   └── requirements.md
└── tasks.md            # created by /speckit.tasks
```

### Source Code (repository root)

```text
app/
├── __init__.py
├── main.py              # wiring: config, store, adapter, poller, health server
├── config.py            # env parsing, validation, secret handling
├── logging.py           # structured logging + redaction filter
├── store.py             # SQLite schema, migrations, repositories
├── health.py            # FastAPI app: /healthz, /readyz, /audit (operator)
├── opencode/
│   ├── __init__.py
│   ├── client.py        # sessions, prompt, interrupt, permissions, forms, models
│   └── events.py        # SSE stream consumer and event decoding
└── telegram/
    ├── __init__.py
    ├── app.py           # Application factory and handler registration
    ├── auth.py          # allowlist gate
    ├── trigger.py       # mention / reply / command detection, prompt cleanup
    ├── identity.py      # speaker attribution block for the prompt
    ├── streaming.py     # coalesced edits, message splitting, HTML escaping
    ├── keyboards.py     # inline keyboards and callback payloads
    ├── commands.py      # /new /sessions /switch /abort /status /model /agent /help
    └── runner.py        # per-conversation queue, run lifecycle, approvals
tests/
├── conftest.py
├── fakes/
│   ├── telegram.py      # fake Bot API surface used by handlers
│   └── opencode.py      # fake agent server with scripted events
├── unit/                # config, trigger, identity, streaming, store
├── contract/            # adapter payloads vs OpenAPI shapes
└── integration/         # two-human group scenarios end to end
```

**Structure Decision**: single Python service. The adapter, the store and the
Telegram layer are separate packages because the constitution forbids handlers
touching HTTP directly (Principle VIII) and forbids state outside the volume
(Principle VI). No `backend/` + `frontend/` split: the only web surface is the
health/operator endpoint.

## Phase 0 — Research

Recorded in [research.md](./research.md). Open questions resolved there:
Telegram framework choice, group trigger detection, streaming strategy, OpenCode
event consumption, queue semantics, dedupe strategy, secret redaction.

## Phase 1 — Design

- Data model: [data-model.md](./data-model.md)
- OpenCode adapter contract: [contracts/opencode-api.md](./contracts/opencode-api.md)
- Telegram interaction contract: [contracts/telegram-interaction.md](./contracts/telegram-interaction.md)
- Local quickstart: [quickstart.md](./quickstart.md)

## Phase 2 — Task planning

`tasks.md` is generated by `/speckit.tasks` from this plan and the spec, ordered
so that each user story is independently deliverable.

## Complexity Tracking

No constitutional violations. Deliberate non-obvious choices, all inside the
rules: SSE consumption over an async generator rather than a second library, and
a hand-written coalescing editor instead of a streaming helper package (both keep
the dependency surface at four runtime packages).
