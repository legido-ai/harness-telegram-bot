# Changelog

All notable changes to this project are documented here. Format follows
Keep a Changelog; versions use semantic versioning.

## [0.3.1] — 2026-11-13

A tool-heavy turn no longer looks dead. Previously the only sign of life was the
first sentence the agent streamed; after that the chat sat on a frozen message
while `docker pull`, a deploy or a long `grep` ran for minutes, and the only way
to tell work from a hang was to ask — which steers and closes the turn.

### Fixed

- The elapsed-time line is now a trailing line **inside** the answer's own
  message and keeps updating for the whole turn (`⏳ Working… 2m 10s · shell`),
  instead of only until the first text arrived. `finish()` removes it, so the
  finished answer stays clean.
- The status line names the tool the agent is using (`shell`, `edit`, …), read
  from `session.tool.input.started`, and clears between tools.
- The chat action ("typing…") is refreshed for the full turn rather than stopping
  at the first bubble, so clients that animate it keep animating.
- `status()` renders through the same Markdown→HTML path as the answer, so an
  annotated edit no longer drops the formatting of the text it sits under.

### Added

- `on_activity` hook on the backend `run()` seam; the OpenCode adapter feeds it
  `session.tool.*` events. The Pi adapter accepts it for contract parity.
- The model button names the model the turn will actually use (`🧠 go/flash`)
  instead of the generic `🧠 Model` when no explicit pick was made.

Validated 2026-11-13 on `@legido_opencode2_bot` from Telegram Web.

## [0.3.0] — 2026-11-13

The project becomes `harness-telegram-bot`: one Telegram surface for two coding
harnesses. The OpenCode bridge (history and behaviour) is the base; the Pi
bridge was merged in as a second backend instead of a second bot.

### Added

- `BACKEND=opencode|pi` selects the adapter at startup; an unknown value fails
  fast with the accepted list, and only the selected backend's credentials are
  required.
- `app/backends/`: `Backend` protocol plus `opencode/` (HTTP + SSE, unchanged
  behaviour) and `pi/` (JSONL child process per session file).
- Pi gains the OpenCode interface: menu keyboard with model and context, pinned
  dashboard, sign-off bubble with tokens/limit/percent/duration, `/sessions` and
  `/switch`, `/context`, `/model`, `/abort`, attachments (images), per-chat
  trigger policy, dedupe and participant attribution.
- Pi model catalogue and switching from the agent itself
  (`get_available_models`, `set_model`), context/cost from `get_session_stats`.
- Pi idle reaping (`PI_IDLE_MINUTES`): an idle child is closed, the session file
  stays bound and the next prompt resumes it.
- Elapsed time in chat reads `42s`, then `1m 05s`, then `1h 02m 05s`, in both the
  status bubble and the sign-off.
- `store.bind_backend()` pins which harness owns the session bindings and clears
  them when a database is reused across backends.
- Health reports the backend name; `/healthz` stays loopback-only.

### Changed

- One image (python + node + Pi CLI) serves both services; the Pi Compose
  service pins uid 10001, the OpenCode service keeps running as root.
- `/agent`, permissions and forms on the Pi backend answer with a sentence
  instead of showing buttons that cannot work.
- Pi audio requests answer normally and are spoken afterwards, because the Pi
  RPC has no transient text endpoint.

### Compatibility

- The OpenCode command surface, database schema and pinned-card behaviour are
  unchanged; the previous image tag remains valid as a rollback.