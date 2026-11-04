# Changelog

All notable changes to this project are documented here. Format follows
Keep a Changelog; versions use semantic versioning.

## [0.1.0] — 2026-11-03

First release: the bot runs against an OpenCode V2 server and serves one or more
allowlisted humans, including a shared group conversation.

### Added

- Private-chat loop: prompt → streamed answer → `/abort`, with the session kept
  across restarts.
- Group conversations: entity-based mention detection, reply-to-bot triggering,
  mention stripping, and silence on human-to-human chatter.
- Attribution: every prompt carries speaker name and numeric id; answers in
  multi-human conversations are prefixed with the asker's name.
- Conversation isolation by chat and forum topic, with lazy session creation and
  persistent bindings (`/new`, `/sessions`, `/switch`).
- Model and agent selection from inline menus (`/model`, `/agent`), stored per
  conversation and applied to the session.
- Permission requests and agent questions delivered as buttons; the first
  allowlisted human to answer decides, and the message records who.
- Attachment intake for images, PDF and text under a configurable size limit.
- Per-run footer with the model, context consumption (`42K/200K (21%)`), cost
  and duration, read from `Session.Info` and the model catalogue.
- `/status` and `/id` for operators and newcomers.
- `GET /healthz` (poller + agent state), `GET /readyz`, and `GET /audit` (who
  asked, when, outcome — never message bodies).
- Offline test suite: unit, contract and integration layers with fake Telegram
  and fake OpenCode servers, plus a redaction test for secrets.
- Docker image running as uid 10001 with a named volume for state.

### Design notes

- OpenCode V2 only; the adapter pins the endpoints and payload shapes it uses.
- One queue per conversation keeps two humans in one room ordered without
  blocking other chats.
- Single poller policy: Telegram `409 Conflict` is surfaced as a hard error.
