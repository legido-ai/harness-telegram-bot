# Feature Specification: OpenCode Telegram Bot for Shared Conversations

**Feature Branch**: `001-telegram-group-bot`
**Created**: 2026-11-03
**Status**: Draft
**Input**: User description: "Our own OpenCode Telegram bot with the capabilities of the bridge we run today, plus real support for a group where two humans and the agent talk together: quote a message and the bot answers, mention it and it answers, and it knows which human is speaking."

## Context

Today a single-owner bridge drives OpenCode from Telegram private chats. The
next company (OC3) needs a different shape: **one agent, two or more humans, one
conversation**. This specification covers the first release of a bot that keeps
the useful capabilities of the current bridge and adds first-class support for
shared group conversations with attribution.

Parity reference: the feature list of the bridge currently deployed
(`@grinev/opencode-telegram-bot` 0.26.6). Capabilities deliberately deferred to
later releases are listed under Out of Scope so the boundary is explicit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One human drives the agent from a private chat (Priority: P1)

A single allowlisted person opens the bot in a private chat, sends a request in
natural language, and watches the agent work: the answer arrives incrementally,
shows which files changed, and survives a bot restart. They can start a fresh
session, stop a runaway task, and check what the agent is doing.

**Why this priority**: every other scenario is an extension of this loop. If the
private-chat loop is not solid, nothing else matters.

**Independent Test**: with no group configured, one person can send a prompt,
see a streamed answer, abort it, and find the same session again after a restart.

**Acceptance Scenarios**:

1. **Given** an allowlisted user in a private chat, **When** they send a plain
   text request, **Then** the bot acknowledges within two seconds, shows live
   progress, and finishes with the agent's answer in the same chat.
2. **Given** a request is running, **When** the user sends `/abort`, **Then** the
   run stops and the chat confirms it stopped.
3. **Given** the bot restarts while a session exists, **When** the user sends a
   new message, **Then** it continues the same session instead of creating a new
   one.
4. **Given** a non-allowlisted Telegram account, **When** it messages the bot,
   **Then** nothing runs, nothing is answered, and the attempt is recorded with
   the numeric ID only.

---

### User Story 2 - Two humans and the agent in one group (Priority: P1)

Two people add the bot to a group. Each writes normally to each other; when one
of them wants the agent, they either **reply to a bot message** or **mention the
bot** in their message. The bot answers in the same thread, and its answer makes
clear who asked. The model itself can tell which human is speaking and addresses
them by name when needed.

**Why this priority**: this is the reason the project exists. It is the OC3
working model: two humans plus one agent sharing a room.

**Independent Test**: in a group with the bot and two allowlisted humans, one
human mentions the bot, the other replies to a bot message; both get answers,
each answer is attributed, and human-to-human chatter triggers nothing.

**Acceptance Scenarios**:

1. **Given** a group with two allowlisted humans and the bot, **When** human A
   writes `@bot please summarise this thread`, **Then** the bot answers without
   the mention text being treated as part of the request and records A as the
   author of that turn.
2. **Given** the bot has answered, **When** human B replies to that specific
   answer with a follow-up, **Then** the bot continues the same conversation and
   treats the quoted answer as context, not as instructions.
3. **Given** the two humans are talking to each other with no mention and no
   reply to the bot, **Then** the bot stays silent and cheap (no model call).
4. **Given** both humans send a request within a few seconds, **Then** both are
   queued and answered in arrival order, and the answer states who each result
   belongs to.
5. **Given** a group where the bot is an administrator or privacy is disabled,
   **Then** the bot still only acts on mentions and replies, because trigger
   policy is the bot's decision, not Telegram's.

---

### User Story 3 - Conversations are addressable and switchable (Priority: P2)

A conversation is a chat plus, in forum groups, a topic. Each conversation owns
one active session. Users can list sessions, switch the conversation to a
different existing session, start a new one, and rename it.

**Why this priority**: without it, two topics or two teams fight over one
session, and there is no way back to earlier work.

**Independent Test**: in a forum group with two topics, each topic keeps its own
session; switching in one topic does not disturb the other.

**Acceptance Scenarios**:

1. **Given** a forum group with topics `alpha` and `beta`, **When** each topic
   sends a prompt, **Then** each gets a different session and neither sees the
   other's history.
2. **Given** a conversation with several sessions, **When** a user runs
   `/sessions` and picks one, **Then** subsequent prompts in that conversation
   go to the chosen session.
3. **Given** any conversation, **When** a user runs `/new`, **Then** a fresh
   session is bound to that conversation and the previous one stays available.

---

### User Story 4 - Control the agent without leaving the chat (Priority: P2)

Users pick the model and the agent mode (for example plan vs build) with inline
buttons, see the current choice, and get a clear error when a choice is no longer
available.

**Why this priority**: the agent is only useful if the humans can steer cost and
thoroughness from the room they are already in.

**Independent Test**: change model in a chat, send a prompt, and observe that the
new model is used; change it back.

**Acceptance Scenarios**:

1. **Given** the bot is connected, **When** a user opens the model menu, **Then**
   they see the currently configured favourites first and can pick another.
2. **Given** a model that the server refuses, **When** it is selected, **Then**
   the bot reports the failure in plain language and keeps the previous model.

---

### User Story 5 - Approvals and questions come to the room (Priority: P2)

When the agent needs permission to run a tool or asks a question, the bot posts
it with buttons. Any allowlisted human in that conversation can approve, deny,
or answer, and the outcome records who decided.

**Why this priority**: an unattended agent blocked on a permission prompt is a
dead end; in a two-human room either person must be able to unblock it.

**Independent Test**: trigger a permission request, approve it from a second
human's account, and confirm the run continues and the decision is attributed.

**Acceptance Scenarios**:

1. **Given** a run asks for permission, **When** the request is shown, **Then**
   it appears with approve/deny controls in the conversation that started it.
2. **Given** a request is pending, **When** a second allowlisted human presses
   approve, **Then** the run continues and the audit trail names that human.
3. **Given** a request is pending, **When** the run is aborted, **Then** the
   buttons are retired and pressing them does nothing harmful.

---

### User Story 6 - Send what you are looking at (Priority: P3)

A user attaches a screenshot, a PDF, or a text file to a prompt. The bot accepts
it within documented limits, tells the agent what it is, and refuses oversized or
unsupported files with a clear message instead of failing mid-run.

**Why this priority**: shared debugging needs screenshots, but text-only groups
still deliver the core value.

**Independent Test**: send a PNG with a prompt, confirm the agent receives it as
an image; send a 50 MB file and confirm a clear refusal.

**Acceptance Scenarios**:

1. **Given** a photo with a caption, **When** it is sent to the bot, **Then** the
   caption is the prompt and the photo is passed as an image.
2. **Given** a file above the documented size limit, **Then** the bot refuses it
   with the limit stated and runs nothing.

---

### User Story 7 - Operators can see what happened (Priority: P3)

An operator checks health and history: whether polling is alive, which
conversations exist, who triggered what, and how much each conversation has cost.

**Why this priority**: two humans sharing one agent need an audit trail the
moment something goes wrong, but it is not needed to start using the bot.

**Independent Test**: the health endpoint reports polling state; the audit view
shows the last turns with user identity and timestamps.

**Acceptance Scenarios**:

1. **Given** the bot is running, **When** polling stops receiving updates,
   **Then** the health endpoint reports the bot as unhealthy.
2. **Given** several turns have run, **Then** each is recorded with conversation,
   user, session, and timestamp, and no message body is written to logs.

### Edge Cases

- **Group privacy mode on vs off**: in both cases the bot only acts on mentions
  and replies; the documented setup explains what each mode changes.
- **Message from another bot**: never treated as a human prompt; ignored and
  counted, so a second agent in the room cannot loop with this one.
- **Mention only, no instruction** (`@bot`): bot asks for the request instead of
  sending an empty prompt.
- **Mention of the bot inside a quote of someone else's message**: the mention is
  not addressed to the bot; it is context only.
- **Two humans press the same button**: first decision wins; the second sees that
  it was already decided.
- **Restart mid-stream**: the partial answer stays visible and is marked as
  interrupted; the session is reusable and the prompt is not re-run.
- **Duplicate delivery of the same update**: the prompt runs once.
- **A second poller with the same token**: the bot reports the conflict loudly
  instead of spinning.
- **Very long agent output**: split into readable messages, with formatting kept.
- **Topic deleted or conversation migrated**: binding is dropped safely and the
  next prompt starts clean.
- **Server unreachable**: users get a plain explanation and the run is not
  silently lost.

## Requirements *(mandatory)*

### Functional Requirements

**Access and identity**

- **FR-001**: The bot MUST only act for Telegram user IDs on an explicit
  allowlist; every other user is ignored without side effects.
- **FR-002**: The bot MUST record, for every turn, the Telegram user ID and
  display name of the human who caused it.
- **FR-003**: The bot MUST include the speaker's identity in the context given to
  the agent, so the agent can distinguish two humans in the same conversation.
- **FR-004**: The bot MUST identify a conversation by chat and, where applicable,
  by topic, and MUST NOT let one conversation read or control another's session
  by default.
- **FR-005**: The bot MUST distinguish its own messages and other bots' messages
  from human prompts and MUST never run a prompt from either.

**Triggering in groups**

- **FR-006**: In a group, the bot MUST answer only when mentioned, when a user
  replies to one of its messages, or when a command is addressed to it.
- **FR-007**: The bot MUST strip the triggering mention from the prompt text and
  MUST ask for a request when the mention carries no content.
- **FR-008**: A mention that appears inside quoted text MUST NOT trigger the bot.
- **FR-009**: The bot MUST support a per-conversation policy to answer
  unaddressed messages, disabled by default.

**Working with the agent**

- **FR-010**: Users MUST be able to send a request and receive the agent's answer
  progressively in the same conversation, without the bot blocking other chats.
- **FR-011**: Users MUST be able to start a new session, list sessions, switch the
  conversation to another session, and abort a running task.
- **FR-012**: Users MUST be able to see and change the model and the agent mode
  for a conversation.
- **FR-013**: Permission requests and agent questions MUST be delivered as
  actionable controls in the conversation that started the run, and any
  allowlisted human in that conversation MUST be able to resolve them.
- **FR-014**: The bot MUST show, on demand, current session status: conversation,
  session, model, agent mode, and whether a run is active.
- **FR-015**: The bot MUST accept image, PDF, and text attachments within
  documented limits and reject anything else with a clear message.

**Reliability and safety**

- **FR-016**: The bot MUST de-duplicate updates so a retried or replayed delivery
  never runs a prompt twice.
- **FR-017**: The bot MUST queue concurrent requests per conversation and process
  them in arrival order, stating whose request each result answers.
- **FR-018**: The bot MUST fail fast at start when required configuration is
  missing, with a message that contains no secret values.
- **FR-019**: The bot MUST detect that another process is polling the same token
  and report it as a hard error.
- **FR-020**: The bot MUST expose a health signal that reflects both process
  liveness and whether updates are still being received.
- **FR-021**: The bot MUST keep an audit record of turns and decisions with
  conversation, user, session, and timestamp, storing no message bodies in logs.
- **FR-022**: The bot MUST redact the bot token, the agent-server password, and
  user message content from logs, error output, and health payloads.
- **FR-023**: The bot MUST recover conversation-to-session bindings after a
  restart and MUST NOT lose them when the container is recreated.

### Key Entities

- **Conversation**: a chat plus optional topic; owns one active session binding
  and per-conversation settings (trigger policy, model, agent mode).
- **Participant**: a Telegram identity (numeric ID, display name, username) that
  is either allowlisted or rejected; referenced by turns and decisions.
- **Session binding**: the link between a conversation and an agent session,
  including when it was established and by whom.
- **Turn**: one request-to-answer cycle: author, conversation, session, prompt
  reference (not the body in logs), outcome, duration, and cost when available.
- **Pending interaction**: a permission request or agent question awaiting a
  decision, with the conversation, the run it belongs to, and the decision
  author.
- **Delivery ledger**: the set of processed update identifiers used for
  de-duplication.
- **Attachment**: a file or image offered with a request, with its type, size,
  and disposition (accepted or rejected with reason).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can go from adding the bot to a group to a first useful
  answer in under five minutes, following only the README.
- **SC-002**: 100% of turns in the test suite carry the correct authoring user
  ID; zero turns are attributable to the wrong participant.
- **SC-003**: In a two-human group, zero assistant turns are triggered by
  human-to-human chatter without a mention or reply, in the automated scenarios.
- **SC-004**: A mention-triggered request shows visible progress within three
  seconds on a local agent server, and the final answer arrives without the user
  re-sending the prompt.
- **SC-005**: After an abrupt restart mid-run, no prompt is executed twice and
  the affected conversation is usable again within one message.
- **SC-006**: A non-allowlisted user can never start a run: 100% of attempts are
  rejected with no side effects in the automated scenarios.
- **SC-007**: The full automated suite runs offline, with no real token, no real
  agent server, and finishes in under three minutes.
- **SC-008**: Operator audit answers "who asked for this change?" for any turn of
  the last 30 days without reading message bodies from logs.

## Out of Scope (this release)

Voice prompts and speech replies, scheduled and recurring tasks, git worktree
switching, skills catalogue, file browser, TTS, localisation beyond English,
multi-tenant hosting of several bots in one process, and any web management UI
beyond the health endpoint.

## Assumptions

- The agent server is an OpenCode V2 server reachable from the bot over HTTP with
  basic authentication; the bot is not the server.
- Telegram long polling is used; no public webhook and no inbound internet port.
- Exactly one bot token is served by one bot process; a second process is an
  operator error, not a supported topology.
- Two humans is the initial group size; the design must not break at five.
- Users accept that a shared group means the agent sees the shared conversation,
  and that attribution is cooperative, not adversarial.
- Attachment limits are documented defaults (20 MB per file, images, PDF, and
  UTF-8 text) and may be tuned by configuration.
