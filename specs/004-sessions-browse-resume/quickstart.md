# Quickstart: verifying /sessions parity

## Offline

```bash
cd /workspace/harness-telegram-bot
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-dev.txt
make test
make lint
```

The new tests:

```bash
.venv/bin/python -m pytest -q tests/unit/test_sessions.py
.venv/bin/python -m pytest -q tests/unit/test_store.py -k binding
.venv/bin/python -m pytest -q tests/integration/test_sessions_command.py
```

## In a chat (after the image is deployed)

1. `/sessions` in a chat with history: numbered list, current marked.
2. `/sessions 2`: `↻ Resumed …`; the next message continues that session.
3. `/sessions 1` immediately after: switches back; `/sessions` shows entry 1
   once, not twice.
4. `/title Nightly build`, then `/sessions search nightly`: one hit, numbered.
5. `/sessions bogus-name`: "No session here matches …".
6. As the operator: `/sessions all` shows other chats and `unassigned` rows.
   As a second allowlisted human: the same command returns the chat list plus
   the admin-only note.
7. Send a prompt, then `/sessions 2` while it runs: refused with `/abort`
   advice; the dashboard still shows the old session.

## What proves the migration

Use a copy of a v5 database that has switched between two sessions several
times. Start the bot. `/sessions` must show each session once. Inspecting the
database is not required; the list is the observable.

## Platform note

The screenshot's command description ("Browse and resume previous sessions")
lives in BotFather's command menu, not in this repository. Set it there once;
the behaviour above is what this change delivers.
