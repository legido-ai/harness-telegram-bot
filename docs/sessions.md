# `/sessions` on the dev box: deploy and verify

Live copy of this page is for the operator. The behaviour it checks is
specified in `specs/004-sessions-browse-resume/`.

## What changed in 0.4.0

`/sessions` browses this chat's sessions and resumes one by number, id or
title, for both backends. The database moves from schema v5 to v6: duplicate
`session_bindings` rows are collapsed and a unique index is added. The migration
runs on start and is safe to re-run.

## Deploy on oci2

The bot is two Compose services in project `box` from
`agentic-architecture/box/compose.yml`: `opencode-telegram-bot` (OpenCode) and
`pi` (Pi). Both use `ghcr.io/legido-ai/harness-telegram-bot`, so one image
covers both.

1. CI publishes after the merge to `main`
   (`.github/workflows/publish.yml`, tags `latest`, `0.4.0`, `sha-<commit>`).
   Confirm the run is green before pulling; this container cannot observe it.

2. Back up the bot state first. The migration deletes duplicate rows, so keep a
   copy of the SQLite file:

   ```bash
   cd /home/ubuntu/git/agentic-architecture
   sudo docker exec -i --env-file .env sysbox \
     docker compose -p box -f - stop pi opencode-telegram-bot < box/compose.yml
   sudo docker run --rm -v pi-data:/data -v /tmp:/backup alpine \
     sh -c 'cp /data/state.db /backup/pi-state-$(date +%s).db'
   sudo docker run --rm -v opencode-telegram-bot-data:/data -v /tmp:/backup alpine \
     sh -c 'cp /data/state.db /backup/opencode-state-$(date +%s).db'
   ```

3. Pull and recreate only these two services:

   ```bash
   sudo docker exec -i --env-file .env sysbox \
     docker compose -p box -f - pull pi opencode-telegram-bot < box/compose.yml
   sudo docker exec -i --env-file .env sysbox \
     docker compose -p box -f - up -d --no-deps pi opencode-telegram-bot < box/compose.yml
   ```

4. Health:

   ```bash
   sudo docker ps --filter name=pi --filter name=opencode-telegram-bot
   sudo docker logs --tail 50 pi
   sudo docker logs --tail 50 opencode-telegram-bot
   sudo docker exec pi python -c \
     "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).read().decode())"
   ```

   `"status":"ok"` and a live poller; HTTP 409 in the log means a second poller
   is running and must be stopped instead of retried.

## Verify in Telegram

Chats: `@legido_pi_bot` for Pi, `@legido_opencode_bot` for OpenCode. Do it once
per bot, in a chat that already has more than one session.

1. `/sessions` → numbered list, the current session marked `(current)`, turn
   count and relative time on every row.
2. `/sessions 2` → `↻ Resumed session "…"`. Send a short message; the answer
   continues that session.
3. `/sessions` → that session is now first and appears exactly once.
4. `/title Nightly build`, then `/sessions search nightly` → one hit, numbered.
5. `/sessions 1` right after the search → resumes the hit you just saw.
6. Send a slow prompt, then `/sessions 2` while it runs → refused, `/abort`
   suggested; the dashboard still shows the old session.
7. As the operator: `/sessions all` → other chats plus `unassigned` rows. As the
   second allowlisted human: same command → this chat only plus the admin-only
   note.
8. `/resume` with no argument lists like `/sessions`; `/switch 2` still works.

If a session was deleted in the harness, resuming it says so and leaves the
binding alone.

## Rollback

Tag swap and recreate: point both services back at the previous image tag
(`0.3.3` or the last known-good `sha-…`) and run step 3 again. The v6 schema is
forward-compatible with the older code (the extra index is harmless), so no
database restore is needed unless the state file itself is suspect; the backups
from step 2 are the fallback.

## Telegram command menu

The one-line description in the command menu ("Browse and resume previous
sessions") is BotFather state, not repository state. Set it once with
`/setcommands` for each bot; the bot's behaviour is what this change delivers.

## Why the agent container cannot run this deploy

Checked on 2026-11-22, from the agent container (`uid 1000 david`):

- `docker ps` → `permission denied ... /var/run/docker.sock` (socket is
  `root:997`, the user is not in group 997 and there is no `sudo`).
- `ssh ubuntu@82.70.92.83` → connection timed out; no key or `~/.ssh/config`.
- `gh` and `kubectl` are not installed; the repository and its Actions runs are
  private, so CI status cannot be read either.

The binaries being present is not access. To let the agent deploy, one of these
has to change on the operator side: add `david` to the docker group / expose a
socket the user owns, provide an SSH key and host for `oci2`, or run the two
Compose commands from `Deploy on oci2` above. Until then, merging to `main`
publishes the image and the recreate step stays manual.
