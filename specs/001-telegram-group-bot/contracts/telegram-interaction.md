# Contract: Telegram interaction

Defines exactly when the bot acts, what it sends, and how a human's identity
travels into the agent. Anything not stated here is silent by default.

## T1. Update intake

| Update kind | Action |
|---|---|
| `message` from a bot (`from.is_bot`) | ignored, counted as `bot_message` |
| `message` from a non-allowlisted user | ignored, logged with numeric id only |
| `message` in a chat not allowlisted | ignored; groups must be allowlisted by id |
| `message` already in the delivery ledger | ignored (FR-016) |
| `callback_query` from non-allowlisted user | answer `not allowed`, no state change |
| `edited_message` | ignored (no silent prompt rewrite) |
| `channel_post` | ignored |

Allowlist configuration:

```text
TELEGRAM_ALLOWED_USER_IDS=11111111,22222222     # humans
TELEGRAM_ALLOWED_CHAT_IDS=-1001234567890        # optional group allowlist
TELEGRAM_TRIGGER=mention|all                    # default mention (groups only)
```

A private chat is implicitly allowed once its user is allowlisted.

## T2. Trigger rules (groups)

The bot answers if **all** of these hold:

1. the author is allowlisted;
2. the chat is allowlisted (or the allowlist is empty, meaning "any chat the
   allowlisted humans use");
3. at least one trigger is present:
   - `@<bot_username>` entity in `message.entities`, or a `TEXT_MENTION` entity
     pointing at the bot;
   - `message.reply_to_message.from_user.id == bot.id`;
   - `/command@<bot_username>` addressed to the bot;
4. the remaining text is non-empty after removing the trigger.

`TELEGRAM_TRIGGER=all` relaxes rule 3 per chat, and is only settable through an
explicit operator command (`/trigger all`), which is audited.

## T3. Prompt construction

```text
[speaker] name: {display_name} | telegram_id: {user_id}
[conversation] {kind}: "{chat_title}" | topic: "{thread_title or none}" | participants: {names}
[quoted] author: {quoted_display_name} (telegram_id: {quoted_user_id})
{quoted_text, truncated to 1500 chars}

{user_text}
```

Rules:

- The trigger mention and the `/command@bot` token are removed.
- `[speaker]` is always present, including private chats (FR-003).
- `[quoted]` appears only for replies; quoted text is context, and any mention
  inside it never triggers anything (FR-008).
- The block is at most 2000 characters; quoted text is truncated first, then the
  participant list.

## T4. Outbound messages

| Case | Shape |
|---|---|
| streaming answer | one message, edited at most once per second |
| final answer | same message, plus a footer `— {session title} · {model}` |
| long answer | split at paragraph boundaries under 4096 chars, HTML-escaped |
| attribution of a finished run | first line: `{display_name}:` when the conversation has >1 participant |
| errors | plain text, no stack traces, no tokens |
| permission ask | tool name, target, and `Allow once / Always / Deny` buttons |
| agent question | question text plus option buttons, or a "reply with text" prompt |

## T5. Callback payloads

Compact, stable, and self-describing:

```text
p:{session_id}:{request_id}:{once|always|reject}   permission decision
f:{session_id}:{form_id}:{option_index}            form option
m:{session_id}:{provider}:{model}                  model choice
a:{session_id}:{agent}                             agent choice
s:{chat_id}:{thread_id}:{session_id}               session switch
n:{chat_id}:{thread_id}                            new session confirm
```

Prefix `-` is invalid; unknown payloads answer "this control has expired".
Every callback is validated against the allowlist and the conversation the
message was sent in.

## T6. Commands

| Command | Behaviour | Who |
|---|---|---|
| `/start`, `/help` | short usage card, group trigger explained | allowlisted |
| `/new` | create session, rebind conversation | allowlisted |
| `/sessions` | last 10 sessions with inline switch buttons | allowlisted |
| `/switch` | same as `/sessions` | allowlisted |
| `/abort` | interrupt the active run | allowlisted |
| `/status` | conversation, session, model, agent, queue depth | allowlisted |
| `/model` | inline model menu | allowlisted |
| `/agent` | inline agent menu | allowlisted |
| `/trigger` | show or set `mention`/`all` for this chat | allowlisted, audited |
| `/id` | show the caller's numeric id and the chat id | anyone in an allowed chat |

In groups, commands must be addressed (`/new@bot`) to avoid stealing other bots'
commands; unaddressed commands are ignored.

## T7. Attribution in answers

When a conversation has more than one human participant, the answer's first line
is `{display_name}:` (or `@{username}` when no display name exists). The same
rule applies to permission decisions: the message is edited to
`Allowed by {display_name}`.

## T8. Limits

- text prompt: 8000 characters after cleanup, otherwise the bot asks to split;
- attachments: 20 MB per file, images, PDF and UTF-8 text only, max 5 per prompt;
- streamed edits: `>= 1 s` apart per message;
- messages per run: no hard cap, but the first 3 parts are sent as edits and the
  rest as new messages.
