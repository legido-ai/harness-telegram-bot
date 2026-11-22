# Implementation Plan: Sessions browse and resume

**Branch**: `004-sessions-browse-resume` | **Date**: 2026-11-22 | **Spec**: `specs/004-sessions-browse-resume/spec.md`

## Summary

Teach the existing `/sessions` command the argument surface Hermes has: a
numbered, chat-scoped list with the current session marked; resume by number,
id or title; `search`; admin-only `all` including harness-only sessions; and a
`/title` command so a session has a human name. The work is confined to the
Telegram layer plus one store migration; both backends use the same path, and
the harness catalogue is only consulted for the admin `all` listing.

## Technical Context

**Language/Version**: Python 3.12

**Primary dependencies**: `python-telegram-bot==22.5`, `httpx`, `sqlite3`; no new dependency.

**Storage**: SQLite on `/data`. Schema moves from v5 to v6: duplicate
`session_bindings` rows are collapsed and a unique index on
`(chat_id, thread_id, session_id)` makes repeated switches idempotent.

**Testing**: pytest, offline. New unit tests for parsing/formatting/resolution,
store tests for ordering/dedup/search, integration tests through `BotApp` for
every command form, including admin vs non-admin `all` and the busy refusal.

**Target Platform**: the existing linux container; no runtime change.

**Project Type**: Telegram bridge (single service, two backends).

**Performance Goals**: the listing is one SQL query; 50 sessions answer in
under a second locally. `all` adds one harness call and degrades on failure.

**Constraints**: no prompt text stored; no new secret; no backend-specific code
in `app/telegram/`; ten entries per page as today.

**Scale/Scope**: one operator, several chats/topics, tens of sessions per chat.

## Constitution Check

| Gate | Status |
|---|---|
| Spec committed before code | Pass — `specs/004-sessions-browse-resume/spec.md` |
| Every FR maps to a test | Pass — see tasks.md traceability |
| Full suite offline (`make test`) | Pass target; no live bot or harness in tests |
| No secret in code/tests/logs | Pass — no new configuration |
| Redaction test unaffected | Pass — no new logging of message bodies |
| Schema migrates forward in place | Pass — v6 migration is idempotent |
| Conversation ownership | Pass — non-admin resolution is scoped to `(chat_id, thread_id)`; cross-chat only for the configured admin |
| One code path for both backends | Pass — the Telegram layer only calls `Backend.list_sessions`/`session_exists` |

No violation to justify.

## Architecture

```text
app/store.py                     SessionEntry, list_session_entries(),
                                 list_all_session_entries(), set_binding_title(),
                                 v6 migration (dedupe + unique index)
app/telegram/sessions.py         pure: parse_args(), format_listing(),
                                 resolve_target() — no I/O
app/telegram/commands.py         HELP gains the new forms
app/telegram/app.py              _cmd_sessions, _cmd_resume, _cmd_title,
                                 _activate_session(), callback uses it
app/telegram/runner.py           busy(key) helper (active run or queued job)
```

### Listing

`Store.list_session_entries(chat_id, thread_id, limit=10, search=None)` returns
one row per distinct session id, ordered by
`COALESCE(MAX(turns.created_at), bound_at) DESC`, with `title`, `active`,
`turn_count`, `last_active`. `list_all_session_entries` drops the chat filter,
joins `conversations` for the origin title, and returns the same dataclass plus
`chat_id`, `thread_id`, `chat_title`.

### Parsing and resolution

`sessions.parse_args(argument)` returns `(scope_all, search, target)`:

- empty → list
- `all` / `--all` (first token) → `scope_all=True`, rest parsed as usual
- `search <q>` / `find <q>` → search; empty query is a usage error
- anything else → target

`sessions.resolve_target(entries, target)` returns one of `Resolved(id)`,
`Ambiguous([entries])`, `OutOfRange`, `NotFound`. Matching order: all-digit
target is an ordinal; exact id; unique suffix of ≥6 chars; exact
case-insensitive title; unique title substring. Ambiguity is reported, never
guessed.

### Activation

One method on `BotApp` owns every switch (typed command and button):

1. refuse when the runner is busy in this conversation (FR-012);
2. for a non-admin, require the session to be bound to this conversation
   (FR-014);
3. `backend.session_exists(id)`; refuse when gone (FR-011);
4. `store.bind_session(...)` with the resolved title, `runner.refresh_dashboard`,
   reply with title and turn count (FR-010).

Numbers are resolved against the last listing rendered in that conversation (the
default list or a search result), falling back to a fresh chat-scoped query when
none was shown since the process started. The reply documents that `/sessions`
shows the numbering again.

### Admin `all`

Bound entries come from the database. Harness-only entries come from
`backend.list_sessions(limit=50)`, filtered to ids with no binding; their title
is the backend title or short id. A `HarnessError` drops that half and appends
one warning line. Activating an unassigned id is allowed for the admin because
step 2 exempts admins; it creates a normal binding.

### `/title`

`Store.set_binding_title(chat_id, thread_id, session_id, title)` updates every
row for that binding (there is at most one after v6). Empty argument prints the
active title; no active session explains that the first message creates one.
Validation: strip, collapse inner whitespace, 1–60 characters.

## Testing strategy

- `tests/unit/test_sessions.py`: parsing table, formatting (current marker,
  ordering, empty, search header, relative time), resolution (ordinal, id,
  suffix, title, ambiguity, out of range, not found).
- `tests/unit/test_store.py`: v5→v6 migration with duplicate rows keeps the
  newest and sets one active; ordering by turn activity; search title/id;
  rename.
- `tests/integration/test_sessions_command.py`: list/switch by number/id/title,
  `/resume` alias, `/switch` alias, search, `/title`, non-admin `all` notice,
  admin `all` with a second chat and a harness-only session (fake server),
  gone session, busy refusal, idempotent repeated switches.
- Existing tests stay untouched except where the help copy is asserted.

## Risks

- **Duplicate rows in existing deployments** → the v6 migration collapses them
  before creating the unique index; the test seeds duplicates.
- **Number drift between listing and reply** → documented in the copy and in
  the spec assumptions; ids remain exact.
- **Busy refusal feels restrictive** → it is the honest behaviour while a
  queue exists; `/abort` then `/sessions` is one extra message.

## Out of scope

`/branch`, `/undo`, `/retry`, `/compress`, session deletion, previews built
from prompt text, and any BotFather command-menu change (not in this repo).
