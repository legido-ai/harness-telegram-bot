# Contract: OpenCode V2 adapter

Source of truth: `https://opencode.ai/v2/openapi.json` (fetched 2026-11-03) and
the V2 documentation. Only the surface below is used; contract tests pin these
exact shapes so a server change fails loudly instead of silently degrading.

Base URL: `OPENCODE_API_URL` (default `http://127.0.0.1:49374`).
Auth: HTTP Basic, username fixed `opencode`, password `OPENCODE_SERVER_PASSWORD`.
All requests send `Accept: application/json`.

## C1. Liveness

`GET /api/info` → 200 JSON.

Adapter: `OpenCodeClient.info()` → dict. Used by `/healthz` and startup check.

## C2. Create session

`POST /api/session`
Body: `{"title": string|null, "agent": string|null, "model": {"providerID": string, "modelID": string}|null}`
→ 200 `{"data": Session.Info}`

Adapter: `create_session(title, agent, model)` → `session_id` (`Session.Info.id`).
Session ids look like `ses_…`.

## C3. List sessions

`GET /api/session?limit=<n>&order=desc` → 200 `{"data": [Session.Info], ...}`

Adapter: `list_sessions(limit)` → list of `{id, title, updated, cost}`.
Used by `/sessions` and `/switch`.

## C4. Prompt admission

`POST /api/session/{sessionID}/prompt`
Body:
```json
{
  "text": "string",
  "files": [{"type": "file", "path": "string", "mime": "string"}],
  "metadata": {"telegram": {"chat_id": 0, "thread_id": 0, "user_id": 0, "update_id": 0}}
}
```
→ 200 `{"data": Session.Inbox.User}` (admission record)
→ 409 `ConflictError` when the session is busy and the delivery is refused.

Adapter: `prompt(session_id, text, files, metadata)`.
`delivery` is left unset: the conversation queue already serialises runs, and a
409 is surfaced to the user as "the agent is still working on the previous
request".

## C5. Interrupt

`POST /api/session/{sessionID}/interrupt?resume=false`
→ 200 `SessionInterruptResponse` (`interrupted: bool`)

Adapter: `interrupt(session_id)` → bool.

## C6. Permission decision

`POST /api/session/{sessionID}/permission/{requestID}/reply`
Body: `{"decision": "once" | "always" | "reject", "message": string|null}`
→ 204

Adapter: `reply_permission(session_id, request_id, decision, message=None)`.
The enum is taken verbatim from `Permission.Reply`; the adapter must not invent
`allow`/`deny`.

## C7. Form (agent question) answer

`POST /api/session/{sessionID}/form/{formID}/reply`
→ 204 (answer payload follows the `Form.*` shapes in the OpenAPI document).

Adapter: `reply_form(session_id, form_id, answer)`.

## C8. Model and agent selection

- `POST /api/session/{sessionID}/model` with `{"providerID": ..., "modelID": ...}`
- `POST /api/session/{sessionID}/agent` with the agent id
- Catalogues: `GET /api/model`, `GET /api/agent`

Adapter: `set_model`, `set_agent`, `models()`, `agents()`.

## C9. Live events (SSE)

`GET /api/event` with `Accept: text/event-stream`, long-lived.

Events consumed (names are the OpenAPI enum members):

| Event | Use |
|---|---|
| `session.text.started` / `.delta` / `.ended` | stream the answer text |
| `session.tool.called` / `.success` / `.failed` | short progress line |
| `session.execution.started` / `.succeeded` / `.failed` / `.interrupted` | run lifecycle, turn status |
| `session.idle` | end of run |
| `permission.asked` / `permission.replied` | approval keyboards |
| `form.created` / `form.replied` | question keyboards |
| `session.error` (if present) | redacted failure surface |

Adapter: `events()` async iterator yielding `Event(kind, session_id, payload)`.
Reconnects with exponential backoff capped at 30 s; connection loss marks
`/healthz` degraded but never loses the queue.

## C10. Error mapping

| Server response | Adapter error | User-visible message |
|---|---|---|
| 401 | `AuthError` | "the bot cannot authenticate against the agent server" |
| 404 `SessionNotFound` | `SessionGone` | binding dropped, next prompt starts a new session |
| 409 `Conflict` | `Busy` | "still working on the previous request" |
| 5xx / timeout | `Unavailable` | "agent server unreachable", retried once |

The adapter never logs request bodies (they contain user prompts) and never logs
the Authorization header.
