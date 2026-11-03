# Quickstart: OpenCode Telegram Bot

## 1. Requirements

- OpenCode V2 running on the same host or reachable over the network, with its
  server password at hand (`opencode service get password`).
- A Telegram bot token from @BotFather, and your numeric Telegram user id (ask
  the bot `/id`, or @userinfobot).

## 2. Configure

```bash
cp .env.example .env
$EDITOR .env
```

Minimum:

```text
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ALLOWED_USER_IDS=11111111,22222222
OPENCODE_API_URL=http://host.docker.internal:49374
OPENCODE_SERVER_PASSWORD=...
```

In production the first three values come from OCI Vault through `oci-env`; the
`.env` file is only for local runs.

## 3. Run locally

```bash
make install
make test          # offline suite, no token or server needed
make run           # health on 127.0.0.1:8080
```

## 4. Run in Docker

```bash
make build
make up
docker compose logs -f bot
curl -s localhost:8080/healthz | jq
```

## 5. Wire the group

1. Add the bot to the group.
2. Keep privacy mode as is (default on). The bot only answers mentions and
   replies either way, so nothing changes if you later disable it.
3. Post `/id@your_bot` in the group to confirm the allowlisted chat id, and add
   it to `TELEGRAM_ALLOWED_CHAT_IDS` if you set that variable.
4. Mention the bot: `@your_bot summarise what we just decided` — the answer
   arrives in the same topic and starts with the asker's name.
5. Reply to any bot message for a follow-up: the quoted answer becomes context.

### Two humans, one conversation

- Forum group with one topic per workstream keeps sessions separate.
- `/status` shows which session the topic is using.
- `/new` starts clean; the previous session stays in `/sessions`.
- Both humans can approve permissions; the first decision wins and the message
  shows who decided.

## 6. Operator checks

```bash
curl -s localhost:8080/healthz        # poller + agent server state
curl -s localhost:8080/audit?limit=20 # who asked what, when, outcome
```

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `409 Conflict` at start | another process polls the same token | stop the other poller |
| bot silent in a group | not mentioned / not allowlisted / chat not allowlisted | mention it, check `/id` |
| `401` from agent server | wrong `OPENCODE_SERVER_PASSWORD` | fix the secret, restart |
| health `degraded` | SSE stream lost | check network to the agent server |
| answers not attributed | conversation has a single participant | expected: attribution appears with 2+ humans |
