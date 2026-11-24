# Changelog

All notable changes to this project are documented here. Format follows
Keep a Changelog; versions use semantic versioning.

## [0.4.1] — 2026-11-24

Sessions are named, not labelled with the speaker. `/sessions` used to show
`Javier — MSwMVt` because a new session was titled with the chat or speaker
name; two sessions in the same chat were indistinguishable.

### Added

- A session is named from its opening message, as Hermes does: the first
  non-empty line, whitespace collapsed, cut at a word boundary to 48 characters
  with `…`. Later messages do not rename it; `/title` still overrides it.
- `/sessions` rows now read `1. Fix the login button (current) — 1a2b3c`, and
  the footer resumes with `/resume <number>`, matching the native Hermes list.

### Fixed

- Schema v7 clears stored titles that equal the conversation title or a
  participant's display name, so existing sessions stop showing the author.
  Other titles survive.

## [0.4.0] — 2026-11-22

`/sessions` now matches Hermes' native command: it browses previous sessions and
resumes one without copy-pasting an id, on both backends.

### Added

- `/sessions` is a numbered list of this conversation's sessions, most recently
  active first, with the current one marked `(current)`, its turn count and a
  relative last-activity time.
- Resume by number (`/sessions 2`, resolved against the list just shown,
  including search results), by full id, by a unique six-character suffix, or by
  title. `/resume` is an alias; `/switch` keeps working.
- `/sessions search <query>` (alias `find`) filters titles and ids.
- `/sessions all` for the configured admin: every chat's sessions plus harness
  sessions with no binding, marked `unassigned`. Non-admins get the chat list
  and a one-line admin-only notice.
- `/title [name]` names the current session so it can be found and resumed
  later.
- Before a switch the bot checks that the session still exists in the harness,
  and refuses while a run or queued message is in progress (`/abort` first).

### Fixed

- Switching back and forth between sessions no longer lists the same session
  more than once. `session_bindings` had no unique key over
  `(chat_id, thread_id, session_id)`, so every switch inserted a duplicate row;
  schema v6 collapses existing duplicates and adds the index.

## [0.3.3] — 2026-11-22

Attachments reached the agent and were rejected. The OpenCode prompt body requires
`files[i].uri` (`PromptInput.FileAttachment`, and the schema is `additionalProperties:
false`); the bot sent `{"type": "file", "path": …}`, so the server answered
`400 InvalidRequestError: Missing key at ["files"][0]["uri"]` and the chat reported that the
agent server had rejected the request. Supplying only the missing key would not have been
enough: the bot and the agent run in separate containers with no shared mount, so a path
cannot resolve on the server side.

### Fixed

- Attachments are sent as a self-contained `data:<mime>;base64,…` URI plus the file name. The
  bytes travel in the request and no shared filesystem is assumed. Confirmed against the live
  server (200) before shipping.
- The tests pinned the bug rather than the contract: the integration test asserted
  `files[0]["path"]`, the contract test passed `path` through verbatim, and the fake server
  accepted any body. Both now assert the real shape, and the integration test decodes the
  base64 back to the original bytes.

## [0.3.2] — 2026-11-19

A brief that mentions a slash path is a prompt again. Telegram marks every
`/word` token as a `bot_command` wherever it sits, so a pasted spec containing
`/internal/outlook/send` or `/healthz` reached the bot as a command, matched no
handler, and came back as `Unknown command. Try /help.` — the request was never
sent to the agent.

### Fixed

- Only a `bot_command` that opens the message (or follows this bot's own
  @mention) is treated as a command; the same entity in the middle of the text
  is prose. Bare `@bot /new` and `/new@bot` still run as before, and `/deploy`
  in a group is still left to its owner.

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