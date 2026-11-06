# Changelog

All notable changes to this project are documented here. Format follows
Keep a Changelog; versions use semantic versioning.

## [0.2.0] — 2026-11-06

Voice notes and spoken replies, matching the bridge currently running in OC2
(`@grinev/opencode-telegram-bot`): local Whisper STT plus Edge TTS.

### Added

- Voice/audio intake: download the note, transcribe it through a
  Whisper-compatible API (multipart or JSON `input_audio`), post
  `🎤 Recognized: …`, then answer it through the normal prompt path. The
  transcript keeps speaker attribution and quoted context.
- Group trigger parity for voice: a voice note needs a mention, a reply to the
  bot, or `/trigger all`; a caption-less note stays silent otherwise.
- `/tts off|all|auto` per chat/topic. `auto` reads only answers to voice notes
  and is the default, so a spoken question gets a spoken answer without extra
  setup; `/tts off` keeps a chat silent. Spoken replies are sent as an audio
  file after the text answer; synthesis failures never lose the answer.
- TTS providers: Microsoft Edge Read Aloud (no key, default), OpenAI-compatible
  `/audio/speech`, and ElevenLabs. Markdown is stripped and answers over 4000
  characters are skipped.
- `/status` now reports `audio replies: <mode>`.
- Schema v4 adds `tts_mode` to conversations with `auto` as the default;
  existing databases migrate in place and the old implicit `off` becomes
  `auto` (a later `/tts off` is explicit and sticks).

### Changed

- `deploy/sandbox-compose.yml` joins `box_default` and points at
  `http://opencode-stt:9000/v1` with `TTS_PROVIDER=edge`, matching OC2.
- Version bumped to 0.2.0; new dependency `edge-tts==7.3.1`.

## [0.1.1] — 2026-11-05

Validated end to end in a real Telegram group (two allowlisted humans + bot,
agent running against a sandbox OpenCode V2 server).

### Added

- Group onboarding for plain `@bot …` mentions, plus bare commands in groups
  (`/new`, `/status`, `/model`, …), while another bot's commands stay ignored.
- Typing indicator while the agent works; the answer appears only when the first
  token lands, so no empty bubble is left behind.
- Provider-first model menu: pick `OpenCode`, `OpenCode Go (Headroom)` or
  `OpenCode Go (direct)`, then the model, labelled `provider/model`.
- Context counter that matches the TUI: `used/limit (percent)` on the keyboard
  button and on the pinned card, with `0/1.0M (0%)` before the first turn.

### Changed

- **One message per answer.** The `✅ I'm done` line is appended to the answer
  text instead of being a second bubble; the separate bubble only existed to
  carry the keyboard and created the reply context clients attached to it.
- The pinned card is a single editable message; a recreated card deletes the old
  one instead of accumulating duplicates.
- Running as a plain group member is supported: pinning is optional and a pinned
  card is not required for anything else.

### Fixed

- `POST /api/session/{id}/model` and session creation now send `Model.Ref`
  (`{"model": {"providerID", "id"}}`); the previous flat payload made every model
  button report "agent server unreachable" and broke `/new` once a model was set.
- Callback data is a short token instead of embedding session id, provider and
  model, which exceeded Telegram's 64-byte limit (`Button_data_invalid`).
- Health reflects the live updater; a poller killed by a 409 Conflict used to
  report `ok` while receiving nothing.
- Agent failures surface as `⚠️ <reason>` instead of an empty answer, and a stale
  session binding is healed instead of failing the turn.

### Known limits

- Plain `@mention` delivery requires **Group Privacy off** for this bot; with it
  on, Telegram delivered commands and replies but silently dropped mentions.
- The keyboard label refreshes on commands (`/new`, `📊 Context`, model
  selection), not after every run: a reply keyboard can only travel on a message,
  and we chose one message per answer.
- Model menus list the first 20 models of a provider; `OpenCode Go` has 31.

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
