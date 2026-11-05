# Data Model: OpenCode Telegram Bot

State is small, relational, and lives in one SQLite file (`$DATA_DIR/state.db`).
Schema version is tracked in `meta` and migrated forward on start (Principle VI).

## Conversation

A room the bot serves: a Telegram chat plus, for forum groups, a topic.

| Field | Type | Notes |
|---|---|---|
| `chat_id` | INTEGER | primary key part; negative for groups |
| `thread_id` | INTEGER | primary key part; `0` when the chat has no topics |
| `kind` | TEXT | `private`, `group`, `supergroup` |
| `title` | TEXT NULL | chat title at first sight |
| `trigger_policy` | TEXT | `mention` (default) or `all` |
| `model_json` | TEXT NULL | `{"providerID":..., "modelID":...}` override |
| `agent` | TEXT NULL | agent id override |
| `active_session_id` | TEXT NULL | current binding |
| `created_at` | INTEGER | unix seconds |
| `updated_at` | INTEGER | unix seconds |

Index: `(active_session_id)` for reverse lookup on events.

Rule: `active_session_id` is the only session a conversation may prompt
(FR-004). Rebinding is an explicit, audited action.

## Participant

An allowlisted Telegram identity. Allowlist itself comes from configuration; this
table is the observed roster used for attribution and the audit trail.

| Field | Type | Notes |
|---|---|---|
| `user_id` | INTEGER | primary key |
| `display_name` | TEXT | first + last name as seen |
| `username` | TEXT NULL | `@name` without the @ |
| `is_allowlisted` | INTEGER | `1` for configured humans |
| `first_seen` | INTEGER | unix seconds |
| `last_seen` | INTEGER | unix seconds |

## SessionBinding

History of which session belonged to which conversation, so `/sessions` and
`/switch` are possible and so a rebinding is traceable.

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | primary key, autoincrement |
| `chat_id` | INTEGER | FK conversation |
| `thread_id` | INTEGER | FK conversation |
| `session_id` | TEXT | agent session id |
| `title` | TEXT NULL | copied at bind time |
| `bound_by` | INTEGER | Telegram user id that bound it |
| `bound_at` | INTEGER | unix seconds |
| `active` | INTEGER | `1` for the current binding |

Unique index: one `active = 1` row per `(chat_id, thread_id)`.

## Turn

One request/answer cycle. Message bodies are never stored here (FR-021).

| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER | primary key, autoincrement |
| `chat_id` | INTEGER | conversation |
| `thread_id` | INTEGER | conversation |
| `session_id` | TEXT | agent session |
| `user_id` | INTEGER | author (FR-002) |
| `update_id` | INTEGER | Telegram update, unique (FR-016) |
| `trigger` | TEXT | `mention`, `reply`, `command`, `private`, `policy_all` |
| `quote_of` | INTEGER NULL | Telegram message id quoted, if any |
| `status` | TEXT | `queued`, `running`, `succeeded`, `failed`, `interrupted`, `rejected` |
| `started_at` | INTEGER NULL | |
| `ended_at` | INTEGER NULL | |
| `cost_usd` | REAL NULL | from session usage when available |
| `tokens` | INTEGER NULL | total tokens when available |
| `error_kind` | TEXT NULL | redacted error category, no message body |

Indexes: `(chat_id, thread_id, id)`, unique `(update_id)`.

## PendingInteraction

A permission request or agent question awaiting a human decision.

| Field | Type | Notes |
|---|---|---|
| `id` | TEXT | primary key; `permission:{requestID}` or `form:{formID}` |
| `kind` | TEXT | `permission` or `form` |
| `session_id` | TEXT | agent session |
| `chat_id` | INTEGER | conversation to answer in |
| `thread_id` | INTEGER | |
| `telegram_message_id` | INTEGER | message holding the buttons |
| `payload_json` | TEXT | what the user must see (tool, question) |
| `state` | TEXT | `pending`, `allowed`, `denied`, `answered`, `cancelled` |
| `decided_by` | INTEGER NULL | Telegram user id (FR-013) |
| `decided_at` | INTEGER NULL | |
| `created_at` | INTEGER | |

Unique index on `(state = 'pending', session_id, id)` enforced in code: the first
decision wins, later presses read the stored state.

## Delivery

De-duplication ledger.

| Field | Type | Notes |
|---|---|---|
| `update_id` | INTEGER | primary key |
| `seen_at` | INTEGER | unix seconds |

Retention: keep the newest 5000 rows, pruned on start and every 500 inserts.

## Meta

| Key | Value |
|---|---|
| `schema_version` | integer |
| `bot_username` | text, cached from `get_me()` |
| `started_at` | integer |

## Relationships

```text
Conversation 1 ── * SessionBinding ── 1 (agent) Session
Conversation 1 ── * Turn ── 1 Participant
Conversation 1 ── * PendingInteraction
Delivery      (independent ledger)
```

## Validation rules

- `trigger_policy` ∈ {`mention`, `all`}; `all` requires an explicit operator
  action and is recorded in the audit trail.
- `thread_id = 0` means "no topic"; forum topics always store their real id.
- A turn may only be created for an allowlisted participant; otherwise it is
  counted in a rejection counter, not stored as a turn.
- `PendingInteraction.decided_by` must be an allowlisted user of that
  conversation's chat.
- Deleting a conversation cascades its bindings, turns and pending interactions;
  the delivery ledger is never cascaded.
