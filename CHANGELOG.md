# Changelog

All notable changes to this project are documented here. Format follows
Keep a Changelog; versions use semantic versioning.

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
