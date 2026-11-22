# Feature Specification: Sessions browse and resume

**Feature Branch**: `004-sessions-browse-resume`

**Created**: 2026-11-22

**Status**: Draft

**Input**: User description: "Improve multi-harness telegram bot (so far supporting pi and OpenCode) to have same /sessions features as Hermes native one."

## Context

Hermes (the third harness in the same box) ships a native `/sessions`
command described in its own command menu as **"Browse and resume previous
sessions"**: it lists the chat's previous sessions with the current one marked,
numbers them, resolves a number, id or title back to one session, filters with
`search`, and widens to every chat with `all` for admins. The multi-harness bot
already has `/sessions`, but it only prints the bindings of the current
conversation as bare ids plus buttons, with no current marker, no resume by
number/id/title, no search, no cross-chat listing and no way to name a session.
This specification brings that command to parity across both backends
(OpenCode and Pi), because the command surface is backend-neutral.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse this conversation's sessions (Priority: P1)

An allowlisted human opens `/sessions` in a chat or topic and sees that
conversation's previous sessions, most recently active first, each with a
number, a title, a short id, its activity and a `(current)` marker on the one
the next message will continue. The message ends with the two ways to resume.

**Why this priority**: This is the whole reason people type the command. Without
a readable list the rest of the feature has nothing to act on.

**Independent Test**: Seed three bindings for one chat with different last
activity, send `/sessions`, and assert the text contains three numbered entries,
the current one marked, ordered by last activity, plus both resume hints.

**Acceptance Scenarios**:

1. **Given** a conversation with one active session, **When** the human sends
   `/sessions`, **Then** exactly one entry lists that session and it is marked
   `(current)`.
2. **Given** a conversation that has switched between three sessions, **When**
   the human sends `/sessions`, **Then** each session appears once (no duplicate
   rows for repeated switches), ordered by last activity.
3. **Given** a conversation with no session yet, **When** the human sends
   `/sessions`, **Then** the reply says no sessions exist yet and how to start
   one.

---

### User Story 2 - Resume by number, id or title (Priority: P1)

The human reads the list and answers with the same command: `/sessions 2`,
`/sessions 2026-11-13T07-02-10-123Z_111-0` or `/sessions "Nightly build"`.
The next message in that conversation continues the chosen session, and the
bot confirms with the title and how many turns the session holds.

**Why this priority**: Browsing without resuming is a read-only report. This is
the action the list exists for.

**Independent Test**: With three bindings, send `/sessions 2` and assert the
conversation's active session becomes the second entry and a follow-up prompt
runs in it.

**Acceptance Scenarios**:

1. **Given** a listing of N sessions, **When** the human sends
   `/sessions <k>` with `1 <= k <= N`, **Then** session k becomes active and the
   confirmation names its title.
2. **Given** a session in the list, **When** the human sends `/sessions <full
   session id>` or `/sessions <last 6 characters>`, **Then** that session
   becomes active.
3. **Given** a session named through `/title`, **When** the human sends
   `/resume <title>`, **Then** that session becomes active.
4. **Given** a number outside the list, **When** the human sends it, **Then**
   the bot explains the range and tells them to run `/sessions` again.
5. **Given** a title that matches more than one session, **When** the human
   sends it, **Then** the bot lists the matching numbers instead of guessing.

---

### User Story 3 - Search the list (Priority: P2)

With dozens of sessions the human narrows the list: `/sessions search deploy`
returns only sessions whose title or id contains `deploy`, still numbered and
still resumable by number.

**Why this priority**: It keeps the same command usable after the chat has a
long history, without a second command to learn.

**Independent Test**: Seed sessions titled "deploy staging" and "write docs",
send `/sessions search deploy`, assert one entry in the same numbered format, and
resume it by `1`.

**Acceptance Scenarios**:

1. **Given** mixed titles, **When** the human sends `/sessions search <query>`,
   **Then** only entries whose title or id contains the query (case-insensitive)
   are listed.
2. **Given** a search with no match, **When** the human sends it, **Then** the
   bot says nothing matched and shows the usage form.
3. **Given** a search result list, **When** the human sends `/sessions 1`,
   **Then** the first result becomes active.

---

### User Story 4 - Name the current session (Priority: P2)

The human sends `/title Nightly build` and later finds that session by that name
in `/sessions` and `/resume`. `/title` with no argument shows the current title.

**Why this priority**: Titles are the only human-meaningful handle a session has;
without them every entry looks like the chat's name.

**Independent Test**: Send `/title Nightly build`, assert the binding title
changed, then send `/sessions search nightly`, assert the entry is found.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the human sends `/title <text>`,
   **Then** the title is stored for that session in this conversation and the
   bot confirms it.
2. **Given** no session yet, **When** the human sends `/title <text>`, **Then**
   the bot explains that a session starts with the first message.
3. **Given** an empty argument, **When** the human sends `/title`, **Then** the
   bot prints the current title (or says it is untitled).

---

### User Story 5 - Admin cross-chat listing and recovery (Priority: P3)

The operator sends `/sessions all` and sees sessions from every conversation the
bot knows, plus sessions the harness holds that no conversation is bound to
(for example after the bot's database was recreated). Choosing one resumes it in
the current chat. A non-admin who sends `all` gets the chat-scoped list and a
one-line note that cross-chat listing is admin-only.

**Why this priority**: It is the recovery path for the operator, not the daily
flow, and it exposes other conversations' ids, so it must stay restricted.

**Independent Test**: Seed bindings in two chats and one harness-only session;
send `/sessions all` as the admin and assert all three appear with their origin;
send it as a non-admin and assert only the current chat's sessions plus the
admin-only note.

**Acceptance Scenarios**:

1. **Given** bindings in two conversations, **When** the admin sends
   `/sessions all`, **Then** entries from both appear and each names its chat.
2. **Given** a harness session with no binding, **When** the admin lists `all`,
   **Then** it appears marked as unassigned and can be resumed here.
3. **Given** a non-admin, **When** they send `/sessions all`, **Then** they see
   only their chat's sessions and a note that `all` requires an admin.

---

### Edge Cases

- A session id in the list no longer exists in the harness (server recreated,
  file deleted): resuming it MUST NOT bind it; the bot says it is gone and
  suggests `/new`.
- The conversation has a run in progress when a switch is requested: the bot
  refuses the switch, says the current run must finish or be stopped with
  `/abort`, and leaves the binding unchanged.
- Two sessions in one conversation share the same title: resume by title lists
  the matching numbers; resume by number or id always resolves one session.
- The harness is unreachable while listing `all`: the chat-scoped part still
  renders and the unassigned part is omitted with a one-line warning.
- A session id is longer than Telegram's callback payload limit: the button
  keeps using a short token, never the raw id.
- Repeated switching back and forth between two sessions: the list shows each
  session once.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `/sessions` MUST list the sessions bound to the current
  conversation, most recently active first, at most ten, each with an ordinal,
  its title (or `untitled`), its short id, its number of turns and a relative
  last-activity time.
- **FR-002**: The list MUST mark exactly the active session `(current)` and MUST
  list each session at most once, even when the conversation has switched to it
  more than once.
- **FR-003**: `/sessions <number>` MUST resolve the number against the same
  ordered, chat-scoped list and activate that session.
- **FR-004**: `/sessions <id>` MUST match a full session id, and a unique suffix
  of at least six characters, within the caller's visible scope.
- **FR-005**: `/sessions <title>` and `/resume <title>` MUST match a stored
  title case-insensitively; an ambiguous title MUST produce the matching
  numbered entries rather than a switch.
- **FR-006**: `/sessions search <query>` (alias `find`) MUST filter the
  chat-scoped list by case-insensitive substring of title or session id and MUST
  keep the numbered format.
- **FR-007**: `/sessions` with no argument and `/resume` with no argument MUST
  both produce the listing; `/switch` MUST keep working as an alias.
- **FR-008**: `/sessions all` MUST be available only to the configured admin
  (the first allowlisted user). For anyone else it MUST render the chat-scoped
  list with a one-line notice that `all` requires an admin.
- **FR-009**: The admin listing MUST include sessions bound to other
  conversations (naming the chat) and, when the harness can enumerate them,
  sessions the harness holds that no conversation is bound to, marked
  `unassigned`. An unreachable harness MUST degrade to the bound entries with a
  one-line warning.
- **FR-010**: Resuming a session MUST persist the binding for this
  conversation, refresh the pinned dashboard and reply with the session title
  and its number of turns.
- **FR-011**: Before binding, the bot MUST confirm the session still exists in
  the harness; if it does not, the bot MUST leave the binding unchanged and say
  the session is gone.
- **FR-012**: The bot MUST refuse a switch while a run or queued message is in
  progress in that conversation, naming `/abort`, and MUST leave the binding
  unchanged.
- **FR-013**: `/title <text>` MUST set the title of the active session in the
  current conversation (trimmed, 1–60 characters); `/title` alone MUST show it;
  with no active session it MUST explain that the first message starts one.
- **FR-014**: Non-admins MUST NOT be able to activate a session bound to a
  different conversation, by any form of argument.
- **FR-015**: Both backends MUST behave identically for every requirement above;
  no command may require an OpenCode- or Pi-specific code path in the Telegram
  layer.
- **FR-016**: The inline keyboard of `/sessions` MUST keep offering one button
  per listed session, and choosing a button MUST perform the same existence,
  busy and ownership checks as the typed command.
- **FR-017**: The `/help` card and `README.md` MUST document the new argument
  forms.
- **FR-018**: The state schema MUST tolerate an existing database that already
  contains duplicate bindings, migrating it forward without operator action.

### Key Entities

- **Session binding**: a conversation (`chat_id`, `thread_id`) linked to one
  harness session id, with a title, the user who bound it, when, and whether it
  is active.
- **Session entry**: what the list renders for one binding: ordinal, title,
  short id, turn count, last activity, current flag, and (for `all`) origin chat.
- **Harness session**: a session the backend holds (OpenCode server session or
  Pi session file) which may or may not have a binding.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A human can go from `/sessions` to a resumed session in at most
  two messages (list, then number).
- **SC-002**: 100% of sessions shown by the list can be resumed by their
  displayed number in the same conversation, without copy-pasting an id.
- **SC-003**: A conversation with 50 sessions still answers `/sessions`,
  `/sessions search` and `/sessions <n>` in under one second locally, without
  sending more than ten entries.
- **SC-004**: Zero cross-conversation session activations by a non-admin,
  covered by an automated test.
- **SC-005**: The offline suite (`make test`) passes with no network, no bot
  token and no live harness.

## Assumptions

- The "admin" is the first id in the allowlist, as the rest of the bot already
  defines it. No new role configuration is introduced.
- Session ownership is the conversation, not the Telegram user: every
  allowlisted human in a chat shares its sessions, consistent with the
  constitution's per-conversation ownership rule.
- The bot does not store prompt text, so the list shows titles, turn counts and
  activity instead of a message preview. `/title` is the human-provided
  substitute for a preview.
- Numbered resolution uses the last list rendered in the conversation (default
  listing or search results), and falls back to a fresh chat-scoped list after a
  restart. A session created between the listing and the reply may shift the
  fallback numbering; ids remain the exact handle.
- The harness catalogue for `all` is best-effort; the bound list is the source
  of truth for resuming.
- Telegram command-menu descriptions (the text in the screenshot) are set in
  BotFather, outside this repository; this change makes the behaviour match that
  description.
