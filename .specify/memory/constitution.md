# OpenCode Telegram Bot Constitution

This document governs all development on this project. It is the supreme
authority for process, quality, security, and governance decisions.
Specifications are the source of truth. No implementation proceeds without an
approved specification. No merge or acceptance occurs without completing all
compliance and checklist requirements.

## Core Principles

### I. Spec-Driven Development (NON-NEGOTIABLE)

- Every feature, change, or bug fix begins as a written specification produced
  with the project's Spec Kit workflow (`.specify/`, `specs/NNN-feature/`).
- The workflow order is fixed: constitution -> specification -> plan -> tasks ->
  implementation. Stages are not skipped or reordered.
- Specification artifacts (`spec.md`, `plan.md`, `research.md`, `data-model.md`,
  `contracts/`, `quickstart.md`, `tasks.md`) are committed with the code they
  describe and remain the authoritative record of requirements and scope.
- Work on a feature happens on its Spec Kit feature branch
  (`NNN-feature-name`); the default branch is never used for feature work.
- Implementation tasks are traceable to at least one specification requirement
  (`FR-*`) or user story (`US*`).

### II. Test-First Development (NON-NEGOTIABLE)

- TDD is mandatory: tests are written before or alongside implementation, and a
  new test that fails without the change is required for every behavior change.
- `make test` is the canonical, offline, hermetic test command. It MUST run the
  full suite and MUST pass with zero failures before any merge or acceptance.
- Tests MUST NOT require network access, live credentials, a running container,
  a real Telegram bot token, or a live OpenCode server. The Telegram Bot API and
  the OpenCode HTTP API are faked through injected transports
  (`tests/fakes/`), never through live calls.
- Tests live under `tests/` (`tests/unit`, `tests/contract`,
  `tests/integration`) and follow the path conventions in `plan.md`.
- Any failing test is a hard blocker. No exceptions without documented
  justification in the plan's Complexity Tracking section.

### III. Container-Only, Non-Root Runtime

- The application is delivered as a Docker image built from the repository
  `Dockerfile`; the container is the only supported runtime.
- The image MUST build from a pinned, minimal base, run as a non-root user with
  a fixed numeric UID, and start the service through a single documented
  entrypoint, with no build tooling in the runtime layer.
- Configuration is supplied at runtime through environment variables, never
  baked into the image.
- A health endpoint (`/healthz`) MUST exist and MUST report both process
  liveness and Telegram polling state, so the container healthcheck fails when
  the bot is running but no longer receiving updates.

### IV. Secret Hygiene

- The Telegram bot token, the OpenCode server password, and any provider key
  come from the environment at runtime only; none are committed, logged,
  embedded in images, echoed in errors, or included in test fixtures.
- A committed `.env.example` documents every supported variable with
  placeholder values; the real `.env` is git-ignored and never committed.
- In production the values come from OCI Vault through `oci-env`; the bot MUST
  NOT read a secret store of its own.
- Startup MUST validate required configuration and fail fast with a clear,
  secret-free message.
- Logs, exception traces, and health payloads MUST redact the bot token, the
  server password, and message bodies from allowlisted users. An automated test
  MUST assert that redaction.

### V. Single-Poller Telegram Discipline

- Exactly one process polls a given bot token. Telegram answers a second
  `getUpdates` consumer with HTTP 409, so the bot MUST detect a conflict and
  fail loudly instead of spinning silently.
- Updates are processed idempotently: `update_id` is de-duplicated so a restart
  or a retried delivery does not run a prompt twice.
- Outbound traffic respects Telegram limits: messages are split below the
  4096-character cap, HTML is escaped after splitting, and streamed edits are
  coalesced so the bot never exceeds roughly one edit per second per message.
- Long-running agent work MUST NOT block update handling; the poller stays
  responsive while a session streams.

### VI. Persistent State in Volumes

- Durable state (session-to-chat mapping, dedupe ledger, runtime settings) lives
  in SQLite inside a named Docker volume, declared in `docker-compose.yml` and
  driven by `DATA_DIR`.
- The service MUST tolerate a fresh, empty state directory and MUST NOT write
  durable state inside the image filesystem.
- Container recreation MUST NOT lose data, and the schema MUST migrate forward
  automatically on start.

### VII. Multi-Human Attribution (NON-NEGOTIABLE)

- The bot serves an explicit allowlist of Telegram user IDs. Anyone else is
  ignored without side effects, and the attempt is logged with the numeric ID
  only.
- Every prompt carries the speaker's identity: display name plus numeric ID are
  included in the prompt context the model sees, so the agent can tell two
  humans apart in a shared conversation.
- A conversation is addressed by `(chat_id, message_thread_id)`; identity is
  addressed by `telegram_user_id`. A session is owned by the conversation it was
  created in, and MUST NOT leak into another conversation by default.
- In groups the bot answers only when addressed: an @mention of its own
  username, a reply to one of its messages, or a group command addressed to it.
  Whether it also answers unaddressed messages is a per-chat policy, disabled
  by default.
- Messages authored by the bot itself, and messages from other bots, are never
  treated as human prompts. Quoted messages are context, never instructions from
  the quoted author.
- Authorisation is per action: destructive commands (`/new`, `/abort`, session
  switching) are limited to the allowlisted humans, and the audit trail records
  who triggered what.

### VIII. OpenCode V2 Contract Fidelity

- The bot talks to the OpenCode V2 server API only, through one adapter module
  (`app/opencode/`) that owns endpoints, auth, and payload shapes. No handler
  calls HTTP directly.
- The adapter treats the published OpenAPI document as the contract: contract
  tests pin the request and response shapes it depends on.
- Unsupported or missing capabilities degrade explicitly in the UI (a clear
  message, a disabled button) instead of failing opaquely.
- Parity targets are recorded in the spec; a feature is only claimed when a test
  covers it.

## Operational Constraints

- Runtime: Python 3.12, `python-telegram-bot` for the Telegram side, `httpx` for
  the OpenCode API, `sqlite3` for state, FastAPI/uvicorn only for health and
  operator endpoints.
- Interaction model: long polling. No public webhook, no inbound port except the
  local health endpoint bound to loopback inside the container.
- `docker-compose.yml` plus `.env` is the single supported deployment path;
  startup is `docker compose up -d` on a clean host.
- Make targets are the documented interface: `make test`, `make run`, `make
  build`, `make up`, `make down`.

## Compliance Gate

Before an implementation plan may proceed, verify:

- [ ] The feature has a committed specification on its own feature branch
- [ ] Every requirement maps to at least one test under `tests/`
- [ ] `make test` runs the full suite offline with no failures
- [ ] No secret, credential, or real `.env` is committed
- [ ] Logs and health output are redacted and covered by a test
- [ ] Dockerfile (non-root), `docker-compose.yml`, `.env.example`, Makefile and
      README requirements are satisfied
- [ ] All constitutional rules above are respected

Any exception MUST be documented in the plan's Complexity Tracking section with
justification.

## Governance

- **Supremacy**: This constitution supersedes any conflicting local conventions,
  tool configurations, or ad-hoc practices.
- **Amendment procedure**: Changes follow the project's amendment workflow:
  propose the change, obtain approval, update this document, and record the
  change with a version bump here.
- **Versioning policy**: Semantic versioning. MAJOR for incompatible removals or
  redefinitions of principles, MINOR for added principles or materially expanded
  guidance, PATCH for wording clarifications or non-semantic refinements.
- **Compliance reviews**: Before planning or merging, maintainers verify
  compliance with this constitution and record the verification in the plan's
  Constitution Check section.

**Version**: 1.0.0 | **Ratified**: 2026-11-03 | **Last Amended**: 2026-11-03
