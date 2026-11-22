# Verification: sessions browse and resume

**Date**: 2026-11-22
**Branch**: `004-sessions-browse-resume`
**Environment**: dev container (Python 3.12.16, no Docker, no network to the box)

## Offline gate

```
$ make test
235 passed, 1 warning in 8.82s

$ make lint
All checks passed!
```

Baseline before the change: 184 passed. New tests: 51.

What they cover, by requirement:

| Area | Tests |
|---|---|
| Numbered list, current marker, ordering, empty state | `tests/unit/test_sessions.py`, `tests/integration/test_sessions_command.py` |
| Resume by number / id / 6-char suffix / title | `tests/integration/test_sessions_command.py` |
| Ambiguity, out of range, unknown, expired ordinal | unit + integration |
| Search by title and id, non-ASCII casefold | unit, `tests/unit/test_store.py` |
| Admin `all` with other chats and `unassigned`; non-admin notice | integration |
| Non-admin cannot cross chats, by command or by callback token | integration |
| Gone session, removed binding, busy conversation | integration |
| Duplicate bindings collapsed by v6; active/title preserved | `tests/unit/test_store.py` |
| Re-bind keeps the title | `tests/unit/test_store.py` |

## Not verified here

This container has no Docker, no SSH to the box and no Telegram token. The
following are therefore **not observed**, only documented:

- a real Telegram conversation against `@legido_pi_bot` or
  `@legido_opencode_bot`;
- the image build and the GHCR publish (CI runs on `main`);
- the migration against the live `/data/state.db` volume.

The migration is exercised with a fixture that reproduces the pre-v6 table
(duplicates, mixed `active`, NULL title) and is safe to re-run.

## Live test procedure (operator, on oci2)

1. Build and publish: merge this branch to `main` and let
   `.github/workflows/publish.yml` finish, or build the image locally:

   ```bash
   docker build -t harness-telegram-bot:0.4.0 .
   ```

2. Recreate the bot service with that image (Compose project `box`, service
   `pi` or `opencode-telegram-bot`), keeping its `/data` volume. The schema
   migrates on start.

3. Health: `docker logs --tail 50 <service>` must show the poller started, and
   `GET http://127.0.0.1:8080/healthz` inside the container must report
   `"status":"ok"`.

4. In a chat that already has history:

   - `/sessions` → numbered list, current row marked `(current)`.
   - `/sessions 2` → `↻ Resumed session "…"`.
   - send a short message → it continues that session (the sign-off context
     size is consistent with it).
   - `/sessions` again → the same session appears once, at the top.
   - `/title Nightly build`, `/sessions search nightly` → one hit.
   - `/sessions 1` right after the search → resumes that hit.
   - during a long run, `/sessions 2` → refused with `/abort` advice.

5. As the operator: `/sessions all` shows other chats and `unassigned` rows.
   As a second allowlisted human: `/sessions all` shows only that chat plus the
   admin-only note.

## Peer review

One `consult` pass (sonnet55). Findings and disposition:

| # | Finding | Disposition |
|---|---|---|
| 1 | Search `OR` could escape the chat filter without parentheses | Rejected — the query already has `AND (… OR …)`; added a cross-chat search test |
| 2 | `INSERT OR REPLACE` would drop the title once the unique index exists | Fixed — replaced with `ON CONFLICT … DO UPDATE` and `COALESCE` on title; test added |
| 3 | NULL `thread_id` would defeat the unique index | Not applicable — column is `NOT NULL DEFAULT 0` |
| 4 | Migration should preserve `active`/title from duplicates; re-run safety | Fixed — the migration inherits `active` and the newest non-NULL title before deleting; `CREATE INDEX IF NOT EXISTS`; fixture covers it |
| 5 | Listing cache keyed per chat, not per human | Fixed — key is `(chat, thread, user_id)`, entries expire after an hour; test added |
| 6 | Ordinal after restart can silently resolve elsewhere | Fixed — a numeric 1–10 without a remembered listing is refused; test added |
| 7 | `len<6` guard could block short titles | Rejected — it only runs inside the digit-only branch |
| 8 | SQLite `lower()` folds ASCII only | Fixed — a Python `casefold` SQL function is registered and used on both sides; non-ASCII test added |
| 9 | `chat_id=0` sentinel | Fixed — explicit `SessionEntry.unassigned` flag |
| 10 | Callback must re-check ownership; stale entry; busy race | Fixed — callbacks never synthesise an entry, activation re-reads the binding for non-admins, and busy is re-checked after `session_exists` |

Remaining accepted risk: the admin `all` view over-fetches 50 bound rows and
then shows 10; sessions beyond the first ten are reachable by id/title, not by
number. The footer says `/sessions <id>` for exactly that case.
