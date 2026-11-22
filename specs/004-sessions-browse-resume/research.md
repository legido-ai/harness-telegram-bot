# Research: /sessions parity

**Date**: 2026-11-22

## What Hermes actually does

Source read: `NousResearch/hermes-agent`, `gateway/slash_commands_session.py`
(`_handle_sessions_command`, `_resume_listing_reply`),
`hermes_cli/session_listing.py` (`format_gateway_session_listing`), and
`locales/en.yaml` (`gateway.sessions`, `gateway.resume`).

Observed behaviour, which the spec mirrors:

- `/sessions` lists the current chat's sessions, including the current one
  marked `(current)`, newest activity first, ten per page.
- `/sessions <name|id|number>` is a shorthand for `/resume`.
- `/sessions search <query>` filters by title or id; `all` widens to every chat
  and is admin-only; a non-admin gets the scoped list plus an explicit notice.
- `/resume` with no argument lists "Named Sessions"; a number resolves against
  that list.
- Every row renders as `N. **title** (current) — \`id\` — _preview_`.
- A switch confirms with `↻ Resumed session **title** (N messages)`.

## Decisions taken for this repository

| Hermes behaviour | Decision here | Why |
|---|---|---|
| Message preview from the transcript | Turn count + relative activity, no preview | The constitution forbids storing prompt text; the store has no message bodies. |
| Auto-generated session titles from the first message | Title defaults to the chat name; `/title` overrides it | Keeps the existing privacy posture and gives an explicit, user-controlled handle. |
| Titles may repeat; numeric resume resolves a separate "named" list | Numbers always resolve the displayed list; duplicate titles are reported as ambiguous | One list is easier to reason about and to test. |
| `/sessions all` lists all gateway sessions | Bound sessions from all chats + harness-only sessions (admin) | Recovers a session after the bot database is recreated, which Hermes gets from one store. |
| `/resume --cross-room` on Matrix | Not applicable | Telegram ownership is `(chat_id, thread_id)`. |
| Resume while the agent is busy releases live state | Refuse until the run ends or `/abort` | The runner owns per-conversation queues; switching under a queued turn would attach that turn to the wrong session. |

## Storage findings

`session_bindings` has an autoincrement `id` and no unique key over
`(chat_id, thread_id, session_id)`. `bind_session` uses `INSERT OR REPLACE`,
which only replaces when a uniqueness constraint matches the inserted columns,
so every switch back to a session inserts a new row and leaves the old one
inactive. `list_bindings` therefore shows a session as many times as it was
re-entered. The migration must collapse duplicates before adding the index,
otherwise `CREATE UNIQUE INDEX` aborts on existing data.

Ordering by `bound_at` is the time of the switch, not of activity. Hermes orders
by last activity; `turns.created_at` per session id provides that without a new
column.

## Backend findings

`Backend.list_sessions()` already exists on both adapters but is unused by the
Telegram layer (only a unit test calls it). OpenCode returns the server's
sessions, Pi lists `*.jsonl` newest first. That is exactly the catalogue the
admin `all` view needs; no new backend method is required.

`Backend.session_exists()` is already used for the healing path in the runner;
reusing it before a bind prevents persisting a dead session id.

## Alternatives rejected

- **New "recent sessions" table**: duplicates `session_bindings` and still needs
  the same migration for dedupe.
- **Read sessions only from the harness catalogue**: loses the chat origin the
  ownership rule depends on, and Pi session labels are not titles.
- **Store a preview line**: would put user text in SQLite and in the listing,
  contradicting the repository's no-transcript stance.
