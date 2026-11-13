# Feature Specification: One Telegram bridge for OpenCode and Pi

**Feature Branch**: `003-unified-backend`

**Created**: 2026-11-13

**Status**: Draft

**Input**: "I want single project. Name it harness-telegram-bot, implement it for both, pi and opencode. Features: same as current opencode bot plus the minutes seconds you implemented for pi. Then recreate oci2 images so we can test it in opencode2 and pi."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - OpenCode conversations keep working, byte for byte (Priority: P1)

A person in the `opencode2` chat drives the OpenCode harness exactly as today: mention or
reply to the bot, watch the answer stream in, pick a model or agent from the menus, approve a
tool call, switch sessions, ask for an audio reply.

**Why this priority**: this is the bot in daily use. If unification changes any of it, the
project is a regression, not a merge.

**Independent Test**: deploy the new image with `BACKEND=opencode` against the same OpenCode
server, run the existing test suite, then repeat one real conversation with a model switch and
one permission approval.

**Acceptance Scenarios**:

1. **Given** the new image with `BACKEND=opencode`, **When** a message is mentioned or replied to,
   **Then** the answer streams with the same formatting, sign-off line and dashboard refresh as
   version 0.2.1.
2. **Given** a tool permission request, **When** the first allowlisted human presses Allow,
   **Then** the run continues and the message records who approved it.
3. **Given** an existing conversation volume, **When** the container starts, **Then** sessions,
   bindings and the pinned card id survive and no duplicate session is created.

### User Story 2 - Pi conversations get the same interface (Priority: P1)

A person in the Pi chat gets the menu keyboard, dashboard card, session switching, sign-off
numbers and elapsed time in minutes and seconds, instead of a bare placeholder message.

**Why this priority**: the point of the merge is that Pi stops being the poor relation.

**Independent Test**: run the new image with `BACKEND=pi` and the Pi token, then: send a prompt,
watch the typed keyboard and context label update, open `/model`, open `/sessions`, switch to an
old session, `/context`, `/new`, `/abort`.

**Acceptance Scenarios**:

1. **Given** `BACKEND=pi`, **When** a run takes longer than 60 seconds with no streamed text,
   **Then** the status bubble shows `⏳ Working… 1m 05s`, and `2m 40s` after that.
2. **Given** a finished run, **When** the sign-off arrives, **Then** it reads
   `✅ I'm done · 42K/200K (21%) · 12s` and the keyboard's context button matches.
3. **Given** `/sessions`, **When** a session is chosen, **Then** the following prompt continues that
   session file and the dashboard shows its id.
4. **Given** the Pi backend, **When** the user sends `/agent`, **Then** the bot says the agent picker
   does not exist on Pi rather than showing a dead button.

### User Story 3 - One image, two services (Priority: P2)

The operator builds one image, runs two services from it and picks the harness with one variable.

**Why this priority**: without it the merge only moved files around.

**Independent Test**: `docker run -e BACKEND=…` for both values against the same image; health
reports which backend is live; an unknown value fails fast with a readable error.

**Acceptance Scenarios**:

1. **Given** `BACKEND` unset or unknown, **When** the container starts, **Then** it exits with a
   message naming the accepted values.
2. **Given** `BACKEND=pi` and no Pi credentials, **When** it starts, **Then** it fails with a
   message naming the missing variable, not a stack trace at the first prompt.

### User Story 4 - Testing on oci2 without losing the working bots (Priority: P2)

The operator recreates the `opencode2` bot and the `pi` container from the new image, keeps the old
image tag for rollback, and can go back with one command.

**Why this priority**: the merge is only real once it runs where it is used.

**Independent Test**: recreate both containers, confirm `/healthz` and one prompt each, then
confirm the previous image tags are still present locally.

**Acceptance Scenarios**:

1. **Given** the new image, **When** both containers are recreated, **Then** both report healthy and
   answer a prompt in their own chat.
2. **Given** a failed validation, **When** the operator restores the previous tag, **Then** both
   containers come back on 0.2.1 and the pi bridge image without code changes.

### Edge Cases

- Pi process dies mid-run: the bot reports the failure in the chat and the binding survives, so the
  next message resumes the same session file.
- Pi session file is deleted while bound: the next prompt starts a new session and says so.
- OpenCode server restarts and forgets sessions: unchanged healing path (clear binding, create new).
- Two humans in one group topic on either backend: answers stay ordered, attribution is kept.
- The image has no Pi binary but `BACKEND=opencode`: no startup cost, no missing-Pi error.
- `BACKEND=pi` and an attachment the RPC cannot carry (PDF, doc): a clear refusal, never a silent drop.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `BACKEND` MUST accept exactly `opencode` and `pi`; any other value MUST abort startup
  with a message that lists the accepted values.
- **FR-002**: The OpenCode backend MUST preserve the 0.2.1 command surface, keyboards, dashboard,
  approvals, forms, trigger policies, attachments, attribution, dedupe and speech behaviour.
- **FR-003**: The Pi backend MUST expose the same commands, keyboards, dashboard, sign-off and
  session switching, and MUST replace unsupported features with an explicit message.
- **FR-004**: The Pi backend MUST source models from `get_available_models`, switch with `set_model`
  and show context from `get_session_stats` (`contextUsage`, `cost`).
- **FR-005**: The Pi backend MUST list sessions from the session directory and switch with
  `switch_session`, storing the session file path as the conversation binding.
- **FR-006**: The elapsed-time status bubble MUST render seconds below one minute and minutes and
  seconds from one minute on (`42s`, `1m 05s`, `1h 02m 05s`).
- **FR-007**: Both backends MUST produce the same sign-off format and the same keyboard labels.
- **FR-008**: The Pi backend MUST accept images as prompt attachments and MUST refuse other types
  with a user-facing explanation.
- **FR-009**: The Pi backend MUST keep one child process per conversation, MUST reap it after an
  idle period, and MUST resume the bound session file when a prompt arrives after a reap.
- **FR-010**: Health MUST report the backend name and the backend's own reachability.
- **FR-011**: The existing test suite MUST stay green; new backend tests MUST run offline against a
  fake RPC process, with no network and no real credentials.
- **FR-012**: CI MUST publish one multi-arch image with `latest`, version and `sha-<commit>` tags.

### Key Entities

- **Conversation**: `(chat_id, thread_id)` plus trigger policy, TTS mode, model, agent, pinned card
  id. Unchanged.
- **Binding**: conversation → active session. For OpenCode a server session id; for Pi the session
  file path. Must be opaque to the store.
- **Run**: one prompt. Records status, cost, tokens, session and duration for `/audit` and health.
- **Backend**: the harness adapter. Declares its name, whether it supports agents, permissions and
  forms, and implements the run interface.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The existing suite (24 files) passes on the merged project with no skipped tests.
- **SC-002**: A real conversation on each backend produces an answer, a sign-off line and a dashboard
  refresh; the OpenCode one is indistinguishable from 0.2.1.
- **SC-003**: A 90-second Pi run shows `1m 30s`, not `90s`.
- **SC-004**: Both containers run from the same image digest and report healthy from `/healthz`.
- **SC-005**: Rollback to the previous tags takes one command and no code change.
- **SC-006**: Pi memory stays bounded: an idle conversation's child process is gone from `ps` after
  the idle window while its session file survives.

## Assumptions

- Pi's RPC mode (1.5.x) supports `prompt`, `abort`, `new_session`, `get_state`,
  `get_session_stats`, `get_available_models`, `set_model`, `switch_session`,
  `get_available_thinking_levels`, `set_thinking_level`.
- Pi has no tool-permission protocol; approvals and forms stay OpenCode-only by design.
- One bot token per chat identity is available per deployment, as today.
- Speech services (`speech-to-text`, `text-to-speech`) stay shared and unchanged.
