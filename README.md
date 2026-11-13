# harness-telegram-bot

One Telegram bridge for two coding harnesses: **OpenCode** (a server the bot
talks to over HTTP + SSE) and **Pi** (an agent the bot runs as a child process).
Same commands, same keyboards, same dashboard, same sign-off — one image,
`BACKEND` picks the adapter.

The project started as `opencode-telegram-bot` (history preserved). The Pi
bridge (`pi-telegram-bot`) was merged in as a backend in 0.3.0.

## What the user sees

Private chat: write what you want done. Group: mention the bot or reply to one of
its messages; human-to-human chatter costs nothing.

- **Two buttons under the input** — `🧠 provider/model` and `📊 used/limit (%)`.
- **Streamed answers** with coalesced edits, so Telegram rate limits stay quiet.
- **Sign-off bubble** — `✅ I'm done · 42K/200K (21%) · 12s`, which also relabels
  the context button (Telegram only relabels a keyboard from a fresh send).
- **Pinned dashboard** — session, model, context, cost, queue depth; edited in
  place, never duplicated.
- **Sessions** — `/new`, `/sessions`, `/switch`; one queue per chat/topic so two
  humans are answered in order and sessions never interleave.
- **Voice** — notes are transcribed (Whisper-compatible); `/tts off|auto|all`.
- **Status bubble** — a slow turn shows `⏳ Working… 1m 05s` instead of silence.

Commands: `/start /help /id /new /context /status /abort /trigger /tts /sessions
/switch /model /agent /say`

## The two backends

| | OpenCode | Pi |
|---|---|---|
| Transport | HTTP + SSE to an OpenCode V2 server | `pi --mode rpc` child process per session |
| Sessions | server session ids | JSONL files under `PI_SESSION_DIR` |
| Models | server catalogue | agent catalogue (`get_available_models`) |
| Agent modes | `/agent` picker | not available — `/agent` says so |
| Approvals / forms | Allow / Always / Deny, option buttons | not available — Pi runs tools autonomously |
| Attachments | images, PDF, text | images only |
| Audio request | transient text endpoint | answers first, then speaks |
| Idle cost | none | child reaped after `PI_IDLE_MINUTES` |

The single image contains Python 3.12, node 22 and the `@earendil-works/pi-coding-agent`
CLI. The OpenCode service never spawns Pi; the Pi service is the same image.

## Configuration

See `.env.example`. The pieces that matter:

**Both**: `BACKEND`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`,
`TELEGRAM_TRIGGER`, `DATA_DIR`, `HEALTH_*`, `STT_*`, `TTS_*`, `RUN_TIMEOUT`.

**OpenCode**: `OPENCODE_API_URL`, `OPENCODE_SERVER_USERNAME`,
`OPENCODE_SERVER_PASSWORD`.

**Pi**: `PI_BIN`, `PI_PROVIDER`, `PI_MODEL`, `PI_THINKING`, `PI_BASE_URL`,
`PI_API_KEY_ENV`, `PI_MODEL_CONTEXT`, `PI_MODEL_MAX_TOKENS`, `PI_SESSION_DIR`,
`WORKSPACE_DIR`, `PI_IDLE_MINUTES`.

Validation only runs for the selected backend.

## Running it

```bash
cp .env.example .env
make test                      # 175 offline tests
docker build -t harness-telegram-bot:local .
docker run --rm -e BACKEND=pi --env-file .env -v bot-data:/data harness-telegram-bot:local
```

Compose, two services, one image:

```yaml
services:
  bot-opencode:
    image: ghcr.io/legido-ai/harness-telegram-bot:latest
    environment:
      BACKEND: opencode
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN_OPENCODE:?}
      TELEGRAM_ALLOWED_USER_IDS: ${TELEGRAM_ALLOWED_USER_ID:?}
      OPENCODE_API_URL: http://opencode:49374
      OPENCODE_SERVER_PASSWORD: ${OPENCODE_SERVER_PASSWORD:?}
      DATA_DIR: /data
    volumes: [opencode-bot-data:/data]

  bot-pi:
    image: ghcr.io/legido-ai/harness-telegram-bot:latest
    user: "10001:10001"
    environment:
      BACKEND: pi
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN_PI:?}
      TELEGRAM_ALLOWED_USER_IDS: ${TELEGRAM_ALLOWED_USER_ID:?}
      PI_PROVIDER: opencode-go
      PI_MODEL: deepseek-v4.1-flash
      PI_API_KEY_ENV: OPENCODE_GO_API_KEY
      OPENCODE_GO_API_KEY: ${OPENCODE_GO_API_KEY:?}
      DATA_DIR: /data
      WORKSPACE_DIR: /workspace
    volumes: [pi-data:/data, pi-workspace:/workspace]
```

`entrypoint.sh` writes Pi's `models.json` from those variables when
`PI_PROVIDER` is set and does nothing otherwise.

## Health and operations

- `GET /healthz` — `status`, `backend`, poller state, agent reachability.
- `GET /readyz` — schema version.
- `GET /audit` — recent turns (who, session, cost, status; never message text).
- Logs never carry tokens, prompt text or attachment contents.

## Images and rollback

CI publishes `ghcr.io/legido-ai/harness-telegram-bot` for `linux/amd64` and
`linux/arm64` with `latest`, the `pyproject.toml` version and `sha-<commit>`.

Rollback is a tag swap: keep the previous image tags on the host, point the
service back at them and recreate. No schema change is involved; the database
only pins which backend owns its bindings, and it clears them if that changes.

## Layout

```
app/backends/        Backend protocol, opencode/ (HTTP+SSE), pi/ (RPC child)
app/telegram/        intake, triggers, keyboards, dashboard, runner, streaming
app/speech/          STT and TTS clients
app/store.py         SQLite: conversations, bindings, turns, pending approvals
specs/003-unified-backend/   this merge: spec, plan, contract, tasks
```

## Tests

```bash
make test     # 175 tests, offline: fake OpenCode server, fake `pi --mode rpc`
make lint     # ruff
```
