# Contract: `/sessions` command surface

The command is backend-neutral: every form below behaves the same with
`BACKEND=opencode` and `BACKEND=pi`. Only the admin `all` catalogue differs in
where the harness-only ids come from.

## Grammar

```text
/sessions                        list this conversation (max 10)
/sessions <n>                     resume entry n from that list
/sessions <id|suffix|title>       resume by exact id, unique suffix >= 6 chars, or title
/sessions search <query>          list, filtered by title or id substring
/sessions find <query>            alias of search
/sessions all [<target>|search …] admin: list/resume across conversations
/sessions --all …                 alias of all
/resume [<target>]                same as /sessions, bare form lists
/switch [<target>]                legacy alias of /sessions
/title [<text>]                   show or set the active session title
```

Parsing is case-insensitive for the keywords (`ALL`, `Search`, `FIND`). The
target is the rest of the line, so titles with spaces do not need quotes, but
quotes are stripped if present.

## Listing format (plain text, no parse mode)

```text
📋 Sessions in this chat

* 1. Nightly build — 1a2b3c · 12 turns · 2h ago
  2. OC3 build — 9f8e7d · 3 turns · 1d ago
  3. untitled — 55aa11 · 0 turns · 5d ago

Resume: /sessions <number> or /sessions <id>. Rename: /title <name>.
More: /sessions search <query> · /sessions all (admin).
```

- `*` marks the current session; the text also carries `(current)` so the marker
  survives a client that drops the prefix.
- Empty: `No sessions yet. Send a message and one is created.`
- Search header: `📋 Sessions matching "deploy"`.
- All header: `📋 Sessions (all chats)`; rows append ` · <chat title>` and
  harness-only rows append ` · unassigned`.
- Admin refusal note (non-admin sending `all`):
  `all (cross-chat listing) is admin-only; showing this chat's sessions.`

## Replies

| Outcome | Reply |
|---|---|
| Switched | `↻ Resumed session "<title>" (<n> turns). The next message continues it.` |
| Already active | `📌 Already on session "<title>".` |
| Out of range | `There is no session <n> in this list. Run /sessions to see the current numbering.` |
| Not found | `No session here matches "<target>". Run /sessions to see the list.` |
| Ambiguous | `"<target>" matches several sessions:` + numbered rows + `Use the number or the id.` |
| Gone | `That session no longer exists in the harness. /new starts a fresh one.` |
| Busy | `A run is still in progress here. Wait for it to finish or /abort, then switch.` |
| Not owner (non-admin) | `No session here matches "<target>". Run /sessions to see the list.` (no disclosure) |
| Title set | `Session titled "<title>".` |
| No active session for `/title` | `This conversation has no session yet. Send a message and one is created.` |

## Guarantees

- A non-admin can never activate a session whose binding has a different
  `(chat_id, thread_id)`; the check happens before `session_exists` so the
  reply does not disclose existence.
- A failed check never changes the binding and never refreshes the dashboard.
- Every successful switch refreshes the pinned dashboard once.
- Buttons carry `s:<chat>:<thread>:<token>`; the token resolves to the session
  id server-side, so a session id longer than 64 bytes never reaches
  `callback_data`. Buttons perform the same checks as the typed form.
- The listing is a single store query; no backend call except `all`.
