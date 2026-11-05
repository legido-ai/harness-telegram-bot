# Phase 0 Research: OpenCode Telegram Bot

All decisions below were checked against the current sources on 2026-11-03:
OpenCode V2 documentation and the OpenAPI document served at
`https://opencode.ai/v2/openapi.json`, the Telegram Bot API feature notes, and
the behaviour of the bridge currently deployed in OC2
(`@grinev/opencode-telegram-bot` 0.26.6).

## R1. Telegram framework

**Decision**: `python-telegram-bot` 22.x with `Application.run_polling`.

**Rationale**: it ships a maintained async Bot API client, typed `Update`
objects with `message.entities`, first-class `CallbackQuery` handling, forum
topic fields (`is_topic_message`, `message_thread_id`), and a conflict error type
for the double-poller case. `aiogram` would work equally well; PTB is chosen
because it keeps the wiring explicit (no dispatcher magic) which makes the
trigger rules auditable and easy to fake in tests.

**Alternatives rejected**: `aiogram` (more magic in routing, heavier for one
bot), `pyTelegramBotAPI` (sync-first), MTProto userbot (violates ToS for bot
behaviour and needs a phone session).

## R2. Long polling, not webhook

**Decision**: long polling only.

**Rationale**: the constitution forbids inbound exposure, and OC2 already runs
this way. Telegram returns `409 Conflict` to a second `getUpdates` consumer, so
the bot treats `telegram.error.Conflict` as a fatal startup/runtime condition
and reports it on `/healthz` instead of retrying silently.

## R3. Group trigger detection

**Decision**: decide from message entities, not regex.

- `MessageEntity.MENTION` (`@name`) and `MessageEntity.TEXT_MENTION` (user link)
  are compared against the bot's own username from `get_me()`, case-insensitively.
- `Message.reply_to_message.from_user.id == bot.id` counts as a reply trigger.
- `MessageEntity.BOT_COMMAND` counts only when addressed to this bot
  (`/cmd@this_bot`) or when the chat is a private chat.
- Mentions that appear only inside `reply_to_message` text or entities are
  ignored: they are quoted context, not address (FR-008).
- The trigger mention/command is removed from the text using entity offsets
  before the prompt is built; if nothing remains, the bot asks for a request.

**Rationale**: entity offsets are exact, survive unusual usernames, and avoid
the classic bug of matching `@bot` inside a quoted block or a URL.

**Telegram facts behind the rule**: with privacy mode enabled (the default) a
bot receives only commands, mentions, replies and service messages; with privacy
mode disabled or admin rights it receives everything. Either way the bot applies
its own trigger policy, so behaviour is identical in both configurations (spec
US2 scenario 5).

## R4. Bot-to-bot

**Decision**: ignore updates authored by bots (`from.is_bot`), count them, and
never feed them to the agent.

**Rationale**: Telegram's Bot-to-Bot Communication Mode lets bots receive each
other's group messages when the mode is enabled plus admin rights or privacy
disabled. Without an explicit guard, two agents in one room can loop; the spec
requires ignoring them (Edge Cases) and Telegram itself asks for loop
prevention.

## R5. Streaming answers

**Decision**: consume the OpenCode SSE stream (`GET /api/event`) and coalesce.

- Accumulate `session.text.delta` per assistant message.
- Flush to Telegram at most once per second per message and only when the text
  changed materially (>=40 chars or 1 s elapsed).
- On `session.text.ended` / `session.execution.succeeded|failed`, do a final
  flush.
- Split output below 4096 characters on paragraph boundaries, escape HTML before
  joining, and use one message per part.

**Rationale**: Telegram rate limits per chat make per-token editing unusable;
coalescing keeps the UX live without hitting limits. SSE is the only push
mechanism the V2 server offers (`/api/event`), so no polling loop is needed.

**Alternative rejected**: polling `GET /api/session/{id}/message` every second
(loses ordering, burns quota, duplicates content).

## R6. Conversation and session binding

**Decision**: one active session per `(chat_id, thread_id)`; identity is
separate.

- Conversation key: `chat_id` plus `thread_id` (0 when the chat is not a forum
  topic). This is the isolation boundary required by FR-004.
- Session creation happens lazily on the first prompt of a conversation, and is
  persisted immediately so a restart reuses it.
- `/new` creates a new session and rebinds; `/switch` rebinds to a listed
  session; `/sessions` lists the last N sessions with titles and ages.

**Rationale**: two topics must not share history, and a shared group must not
inherit a private chat's session.

## R7. Concurrency and queueing

**Decision**: one `asyncio.Queue` per conversation, drained by a worker task.

- The poller never awaits agent work; it enqueues and returns.
- Ordering is per conversation, so two humans in one room are answered in
  arrival order and each answer is prefixed with the requester's name.
- A run sends the prompt, then streams until the session goes idle or fails.
- `/abort` calls `POST /api/session/{id}/interrupt` and drains the queue for that
  conversation only after confirmation.

**Rationale**: satisfies FR-010 and FR-017 without a global lock, and keeps one
slow session from blocking another conversation.

## R8. Approvals and questions

**Decision**: map both to inline keyboards.

- `permission.asked` events → `POST /api/session/{id}/permission/{requestID}/reply`
  with `decision` in `once | always | reject` (exact schema from OpenAPI).
- `form.created` events → `POST /api/session/{id}/form/{formID}/reply`.
- Buttons carry `(session, request, kind)`; the first allowlisted human to press
  records the decision and edits the message to show who decided; later presses
  answer "already decided".

**Rationale**: FR-013 and the two-humans-press-the-same-button edge case.

## R9. De-duplication

**Decision**: a `delivery` table keyed by `update_id`, written in the same
transaction that records the turn, with a bounded retention (last 5000 ids).

**Rationale**: Telegram redelivers updates after a crashed long-poll; both
restart-mid-stream and duplicate-delivery scenarios require one execution per
update.

## R10. Identity block in prompts

**Decision**: wrap each prompt in a small, fixed preamble:

```text
[speaker] name: Ana Pérez | telegram_id: 123456 | role: human
[conversation] group: "OC3 build" | topic: "deploy" | participants: Ana, Luis
```

then the user's text. Quoted messages are appended after a `[quoted]` marker
with the quoted author recorded, so the model can tell instructions from
context.

**Rationale**: FR-003 requires the model to distinguish humans; a structured
preamble is more reliable than natural-language hints and is cheap in tokens.
Privacy note: Telegram numeric IDs are included, display names only — no
usernames from unrelated users.

## R11. Attachments

**Decision**: fetch files through the Bot API, cap at 20 MB, allow images, PDF,
and UTF-8 text; pass to OpenCode as `files` on the prompt request.

**Rationale**: matches documented defaults in the spec Assumptions and the
prompt schema's `PromptInput.FileAttachment`. Temp files live under
`DATA_DIR/tmp` and are deleted after the prompt is admitted.

## R12. Health and operator surface

**Decision**: FastAPI app on `127.0.0.1:8080` inside the container.

- `/healthz`: process alive, poller connected, last update age, agent server
  reachable. Non-200 when polling has been silent beyond a threshold.
- `/readyz`: configuration validated and store migrated.
- `/audit?limit=`: recent turns with conversation, user, session, timestamps and
  outcome — never message bodies.

**Rationale**: FR-020 and FR-021; the container healthcheck reads `/healthz`.

## R13. OpenCode API surface used

Pinned from the OpenAPI document (see `contracts/opencode-api.md`):

| Purpose | Endpoint |
|---|---|
| liveness | `GET /api/info` |
| create session | `POST /api/session` |
| list sessions | `GET /api/session` |
| prompt | `POST /api/session/{id}/prompt` |
| interrupt | `POST /api/session/{id}/interrupt` |
| messages | `GET /api/session/{id}/message` |
| permission | `POST /api/session/{id}/permission/{requestID}/reply` |
| form | `POST /api/session/{id}/form/{formID}/reply` |
| model / agent | `POST /api/session/{id}/model`, `POST /api/session/{id}/agent` |
| catalogues | `GET /api/model`, `GET /api/agent` |
| live events | `GET /api/event` (SSE) |

Auth: HTTP Basic with username `opencode` and the server password from the
environment, matching the documented server behaviour.

## R14. Testing approach

**Decision**: three layers, all offline.

- `tests/unit`: pure functions (trigger detection, identity block, splitting,
  redaction, config validation, store queries).
- `tests/contract`: adapter calls asserted against handler-style fakes generated
  from the OpenAPI shapes; failing on shape drift is the point.
- `tests/integration`: `fakes/opencode.py` plays a scripted server (admission,
  deltas, permission ask, form ask); `fakes/telegram.py` records outgoing API
  calls. The two-human group scenario is an integration test.

**Rationale**: Principle II forbids live credentials or a live server; the
integration fake is the only way to prove attribution and triggering end to end.
