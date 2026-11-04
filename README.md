# OpenCode Telegram Bot

Drive an OpenCode V2 server from Telegram — including from a **group where two
humans and the agent talk together**.

The bot is not a chatbot wrapper: it is a bridge to a real OpenCode server. It
opens sessions, sends prompts, streams the answer back as it is produced, and
shuttles permission requests and agent questions into the chat as buttons.

## Why this one

The bridge we ran before was single-owner and private-chat only: one allowed user
id, one DM, one session. This bot keeps that loop and adds the part a small team
needs:

| Concern | How it works here |
|---|---|
| Two humans, one agent | every conversation is keyed by chat **and topic**, sessions never leak across them |
| Who said what | every prompt carries `[speaker] name + telegram_id`; answers are prefixed with the asker's name |
| When to answer | only on @mention, reply to a bot message, or a command addressed to the bot — human-to-human chatter costs nothing |
| Quoted messages | a reply quotes the previous answer as *context*, and a mention inside a quote never triggers |
| Approvals | the first allowlisted human to press Allow/Deny decides; the message records who |
| Restarts | sessions, bindings, turn history and the dedupe ledger survive in SQLite on a volume |
| Consumption | every answer ends with `— model · 42K/200K (21%) · $0.03 · 12s`: context used, cost and duration |

Deliberately out of scope for 0.1.0: voice, TTS, scheduled tasks, worktree
switching, skills catalogue, file browser and extra languages.

## How it fits together

```text
Telegram ──long poll──► app.telegram.app  ──► trigger + identity ──► runner (queue per chat/topic)
                              │                                            │
                              │  buttons / messages                        ▼
                              └────────────────────────────── app.opencode.client ──► OpenCode V2 server
                                                                     ▲
                                              app.opencode.events ◄──┘  SSE /api/event
```

- `app/opencode/` is the only place that speaks HTTP to OpenCode. Nothing else
  builds a URL.
- `app/telegram/trigger.py` decides whether the message is addressed to the bot.
- `app/telegram/runner.py` owns one queue per conversation, so two humans in a
  room are answered in order and sessions never interleave.
- `app/store.py` is the durable memory; `app/health.py` is the operator view.

## Quickstart

```bash
cp .env.example .env          # set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, OPENCODE_SERVER_PASSWORD
make install
make test                     # offline: no token, no server, no network
make run                      # health on http://127.0.0.1:8080/healthz
```

Docker:

```bash
make build && make up
docker compose logs -f bot
curl -s localhost:8080/healthz
```

Full setup, including the group walkthrough: `specs/001-telegram-group-bot/quickstart.md`.

## Using it with two humans

1. Add the bot to the group. Privacy mode can stay on: the bot applies its own
   mention/reply policy either way.
2. Each person posts `/id@your_bot` once; keep the printed ids in
   `TELEGRAM_ALLOWED_USER_IDS`.
3. Mention it: `@your_bot what did we decide about the deploy?` — the answer
   starts with the asker's name.
4. Reply to any bot message for a follow-up; the quoted answer becomes context.
5. In a forum group, give each workstream its own topic. Each topic gets its own
   session; `/sessions` switches, `/new` starts clean.

Useful commands: `/new`, `/sessions`, `/abort`, `/status`, `/model`, `/agent`,
`/trigger`, `/id`, `/help`.

## Security model

- **Allowlist only.** Unknown users and chats are ignored without side effects;
  attempts are logged with the numeric id and nothing else.
- **Secrets come from the environment.** The bot reads the token and server
  password from its process environment and never from a secret store; they
  never appear in logs, health payloads or error messages (there is a test for
  that).
- **Message bodies are not logged.** `/audit` shows conversation, user, session,
  timestamps, status and cost — never text.
- **Single poller.** A second process on the same token gets Telegram `409
  Conflict`; the bot reports it and exits instead of spinning.
- **No inbound port.** Long polling only; the health endpoint binds to loopback
  inside the container.

Attribution is cooperative, not adversarial: the room is trusted, and the model
is told who is speaking rather than being asked to verify it.

## Configuration

See `.env.example` for the full list. The important ones:

| Variable | Meaning |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token from @BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | comma-separated numeric ids; the first is the operator |
| `TELEGRAM_ALLOWED_CHAT_IDS` | optional group allowlist; empty means "any group an allowlisted human uses" |
| `TELEGRAM_TRIGGER` | `mention` (default) or `all` |
| `OPENCODE_API_URL` | OpenCode V2 server, default `http://127.0.0.1:49374` |
| `OPENCODE_SERVER_PASSWORD` | server password (`opencode service get password`) |
| `DATA_DIR` | SQLite, temp attachments; mount a volume here |
| `MAX_ATTACHMENT_MB` | per-file limit, default 20 |

## Development

```bash
make test          # unit + contract + integration, all offline
make lint
make test-unit
```

Layout:

```text
app/                service code (config, store, health, main)
app/opencode/       adapter: HTTP client + SSE consumer
app/telegram/       intake, triggers, identity, streaming, runner, commands
tests/              unit/, contract/, integration/, fakes/
specs/001-…/        the specification, plan, contracts and task list
```

Tests never touch the network: `tests/fakes/opencode.py` is a scripted agent
server and `tests/fakes/telegram.py` records outgoing calls.

## Roadmap

- Voice prompts and spoken replies (the pieces exist in `agentic-architecture`).
- Scheduled prompts and reminders.
- Worktree switching and skills catalogue for multi-repo work.
- Per-session cost display in `/status`.

## License

Private, internal to legido-ai.
