# Implementation Plan: One Telegram bridge for OpenCode and Pi

**Branch**: `003-unified-backend` | **Date**: 2026-11-13 | **Spec**: `specs/003-unified-backend/spec.md`

## Summary

Take the tested OpenCode bridge as the base (history preserved), lift the parts that are not
OpenCode-specific into a backend-agnostic core, and add a Pi adapter behind the same Telegram
surface. One image, one code path, `BACKEND=opencode|pi` at runtime.

## Technical Context

**Language/Version**: Python 3.12
**Primary dependencies**: `python-telegram-bot==22.5`, `httpx==0.28.1`, `fastapi`, `uvicorn`,
`edge-tts`; node 22 + `@earendil-works/pi-coding-agent` in the image for the Pi backend.
**Storage**: SQLite on `/data` (existing schema) plus an opaque session reference per binding.
**Testing**: pytest, offline; the existing 24 files stay as the regression baseline and gain a fake
RPC harness for the Pi adapter.
**Target platform**: linux/amd64 + linux/arm64 container, Compose on oci2.
**Constraints**: no behaviour change for OpenCode; Pi must not need a second bot token scheme; no
network or credentials in tests.

## Constitution Check

The project inherits the constitution in `.specify/memory/constitution.md`.

- Spec-driven: this plan follows the approved spec; no code before the tasks list.
- Single HTTP module: OpenCode URLs stay confined to `app/backends/opencode/client.py`.
- No secrets in logs/tests: backends receive credentials from settings only; the Pi adapter never
  logs prompt text or keys.
- Test-first where behaviour is new: Pi adapter tests come with the adapter.

## Architecture

```
app/
  config.py            BACKEND + per-backend settings, validated for the selected backend
  main.py              builds the backend, wires store/runner/app/health
  backends/
    base.py            Backend protocol + value objects (SessionRef, ModelOption, RunResult)
    errors.py          shared error taxonomy (Unavailable, Busy, SessionGone, AuthError, …)
    opencode/          client.py (moved), events.py (moved), backend.py (adapter)
    pi/                rpc.py (JSONL child process), backend.py (adapter), sessions.py (directory)
  telegram/            unchanged UX modules; runner talks to Backend, not to a client
  speech/              unchanged
  store.py             unchanged schema + `meta` row pinning the backend that owns the bindings
```

### Backend boundary

The runner stops importing OpenCode types. It receives a `Backend` and calls:

- `name`, `supports_agents`, `supports_permissions`, `supports_forms`, `supports_images`
- `create_session(title, agent, model) -> session_ref`
- `session_exists(ref) -> bool`
- `run(ref, prompt, *, files, metadata, on_delta, on_interaction) -> RunOutcome`
  (the adapter owns its transport: SSE or child-process stdout, so the runner has no event loop)
- `interrupt(ref) -> bool`
- `models() -> list[ModelOption]`, `agents() -> list[AgentOption]`
- `default_model()`, `set_model(ref, provider, model)`, `set_agent(ref, agent)`
- `stats(ref) -> RunStats` (used tokens, limit, cost, model, session label)
- `generate(ref, prompt) -> str` (transient text; Pi falls back to the last answer)
- `reply_permission(...)`, `reply_form(...)` — raise `Unsupported` on Pi and the app answers with a
  plain message instead of a dead button

Interaction events (permission asked, form created) reach the runner as callbacks so the app can
render the same keyboards it renders today.

### Pi adapter specifics

- One `pi --mode rpc` child per conversation, spawned lazily with `--session <path>` when a binding
  exists, otherwise fresh; `get_state` after `new_session` yields the new `sessionFile`.
- Runs pump stdout JSONL: `message_update` text deltas → `on_delta`; `agent_settled` ends the run;
  `response` resolves the pending command; `extension_ui_request` becomes a message in the chat
  (no buttons until an extension needs them).
- Idle reaping: a task closes children idle beyond `PI_IDLE_MINUTES` (default 30); the binding keeps
  the file path so the next prompt resumes it.
- Sessions: list `*.jsonl` in `PI_SESSION_DIR`, newest first, label from the file name; switching
  uses `switch_session {sessionPath}` in the live process.
- Stats from `get_session_stats`: `contextUsage.tokens` / `contextWindow` for the footer, `cost` for
  the price, `sessionId` for the label.
- Attachments: images travel as `{type:"image", data, mimeType}`; PDF/text are refused with an
  explicit message (RPC has no file attachment channel).
- Audio requests: `generate()` has no Pi equivalent, so the spoken text is derived from the answer
  the adapter already produced (`strip_audio_meta`), never by prompting the agent again.

### Elapsed time

One helper (`format_elapsed`) used by the status bubble and the footer copy: `42s`, `1m 05s`,
`1h 02m 05s`. It replaces OpenCode's `format_duration` (`4m58s`) so both backends read the same.

## Data model

No new tables. `store.meta` gains `backend`; on startup a mismatch clears session bindings (keeps
conversations, policies and pinned cards) so an OpenCode id is never fed to Pi or the reverse.
Bindings stay opaque strings: OpenCode session id, Pi session file path.

## Configuration

| Variable | Meaning |
|---|---|
| `BACKEND` | `opencode` (default) or `pi` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, `TELEGRAM_TRIGGER` | unchanged |
| `OPENCODE_API_URL`, `OPENCODE_SERVER_PASSWORD`, `OPENCODE_SERVER_USERNAME` | OpenCode backend only |
| `PI_BIN`, `PI_PROVIDER`, `PI_MODEL`, `PI_THINKING`, `PI_SESSION_DIR`, `WORKSPACE_DIR`, `PI_IDLE_MINUTES` | Pi backend only |
| `PI_BASE_URL`, `PI_API_KEY_ENV`, `PI_MODEL_CONTEXT`, `PI_MODEL_MAX_TOKENS` | consumed by `entrypoint.sh` to write `models.json` |
| `STT_*`, `TTS_*` | unchanged |

Validation runs only for the selected backend, so the Pi service does not need an OpenCode password
and the OpenCode service does not need a Pi key.

## Image and CI

One Dockerfile: python 3.12 + node 22 + `pi` CLI + both dependency sets, `USER root` (the OpenCode
service keeps today's behaviour) and the Pi Compose service pins `user: "10001:10001"` with the
Docker socket group. `entrypoint.sh` writes `models.json` only when `PI_PROVIDER` is set, then execs
the configured command. `.github/workflows/publish.yml` publishes
`ghcr.io/legido-ai/harness-telegram-bot` (`latest`, version, `sha-<commit>`) as multi-arch.

## Testing strategy

- Port the existing suite unchanged in intent: unit (trigger, keyboards, footer, streaming, store),
  contract (OpenCode client against a fake transport), integration (runner with a fake client).
- Fake `pi` executable in `tests/fakes/pi_rpc.py`: reads JSONL commands, answers `get_state`,
  `get_session_stats`, `get_available_models`, `switch_session`, emits deltas and `agent_settled`.
- Contract test for the backend protocol: both adapters satisfy the same scripted conversation.
- No network, no tokens; `BACKEND` validation tested for both values and one bad value.

## Risks

- **Regression in the OpenCode path** → mitigated by keeping its modules and tests intact and by
  deploying behind a rollback tag.
- **Pi process leaks** → idle reaping plus a test that asserts a reaped child is gone.
- **Feature promises** → approvals and forms are declared unsupported on Pi and surfaced as text.
- **Image size** (node + pi CLI in every service) → accepted for one-image simplicity; the OpenCode
  service pays disk, not runtime.

## Rollout

1. Push the branch, let CI publish the image.
2. Tag the images currently in use as rollback (`opencode-telegram-bot:0.2.1`,
   `pi:current` snapshot).
3. Recreate `opencode2-telegram-bot` with `BACKEND=opencode` and `pi` with `BACKEND=pi`, same env and
   volumes.
4. Verify `/healthz`, one prompt each, and the elapsed bubble past a minute on Pi.
5. Rollback: retag the previous images and recreate the containers.

## Out of scope

Tool permissions on Pi, PDF/document attachments on Pi, scheduled tasks, worktree switching, a file
browser, and any change to the speech services.
