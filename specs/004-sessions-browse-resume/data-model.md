# Data model: sessions browse and resume

## SessionEntry (read model)

| Field | Type | Meaning |
|---|---|---|
| `session_id` | `str` | Opaque backend ref (OpenCode id or Pi file path) |
| `title` | `str \| None` | Binding title, set at creation and editable with `/title` |
| `active` | `bool` | This conversation's active binding |
| `turn_count` | `int` | Turns recorded for the session (user messages) |
| `last_active` | `int` | `MAX(turns.created_at)`, falling back to `bound_at` |
| `chat_id` | `int` | Origin conversation (only meaningful for the `all` view) |
| `thread_id` | `int` | Origin topic (only for `all`) |
| `chat_title` | `str \| None` | Origin chat title (only for `all`; `None` when unassigned) |

`SessionEntry` is a frozen dataclass in `app/store.py`. The Telegram layer
never sees SQL.

## Queries

Chat-scoped:

```sql
SELECT b.chat_id, b.thread_id, b.session_id, b.title, b.active,
       COALESCE((SELECT MAX(t.created_at) FROM turns t
                 WHERE t.session_id = b.session_id), b.bound_at) AS last_active,
       (SELECT COUNT(*) FROM turns t WHERE t.session_id = b.session_id) AS turn_count
FROM session_bindings b
WHERE b.chat_id = ? AND b.thread_id = ?
ORDER BY last_active DESC, b.id DESC
LIMIT ?
```

Search adds, before the limit:

```sql
AND (instr(lower(COALESCE(b.title, '')), lower(?)) > 0
     OR instr(lower(b.session_id), lower(?)) > 0)
```

All (admin):

```sql
... FROM session_bindings b
LEFT JOIN conversations c ON c.chat_id = b.chat_id AND c.thread_id = b.thread_id
ORDER BY last_active DESC, b.id DESC LIMIT ?
```

## Mutations

- `bind_session(chat_id, thread_id, session_id, title, bound_by)` — unchanged
  signature; after v6 it replaces the row for that session instead of adding
  one, and clears `active` on the others.
- `set_binding_title(chat_id, thread_id, session_id, title)` — new; updates the
  row's title, no new row, does not touch `active`.
- `binding_title(chat_id, thread_id, session_id)` — new; used by `/title` with
  no argument.

## Migration v5 → v6

```sql
-- keep the newest row for each (chat, thread, session)
DELETE FROM session_bindings
WHERE id NOT IN (
  SELECT MAX(id) FROM session_bindings
  GROUP BY chat_id, thread_id, session_id
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_session_bindings_session
  ON session_bindings(chat_id, thread_id, session_id);
```

The surviving row keeps its `active` value. `SCHEMA_VERSION` becomes 6; the
migration runs inside the existing `if current < N` chain, so a fresh database
creates the index on an empty table and an existing one is collapsed.

## Invariants

- At most one binding per `(chat_id, thread_id, session_id)`.
- At most one `active=1` row per `(chat_id, thread_id)`; `bind_session` and
  `clear_session` own that transition.
- A title is `1..60` characters after whitespace collapsing, or `NULL`.
- A binding always belongs to exactly one conversation; the `all` view never
  changes ownership of an existing binding, it only reads it.
