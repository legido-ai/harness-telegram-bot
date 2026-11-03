# Verification — 001-telegram-group-bot

**Date**: 2026-11-03
**Commit under test**: implementation of branch `001-telegram-group-bot`
**Agent server**: not required. Every check below runs offline.

## Test suite

```text
$ make test
85 passed in 2.11s
```

| Layer | Files | What it proves |
|---|---|---|
| unit (49) | config, logging, store, trigger, identity, streaming, auth, health | parsing and rejection rules, redaction, dedupe, first-decision-wins, UTF-16 mention stripping, split/coalesce behaviour |
| contract (11) | `tests/contract/` | request paths, payload keys, auth header, permission enum, error mapping against the OpenAPI shapes |
| integration (25) | `tests/integration/` | two-human group flows, topic isolation, approvals by a second human, attachments, audit trail |

`make test` uses fake transports only: no bot token, no OpenCode server, no
network.

## Requirement coverage

| Requirement | Evidence |
|---|---|
| FR-001, FR-005 | `tests/unit/test_auth.py`, `tests/integration/test_private_chat.py::test_unauthorized_user_never_reaches_the_agent` |
| FR-002, FR-003 | `tests/unit/test_identity.py`, `test_store.py::test_audit_contains_identity_but_no_message_body` |
| FR-004, FR-023 | `test_store.py::test_binding_is_isolated_per_topic`, `test_topics_and_selection.py::test_topics_keep_separate_sessions` |
| FR-006..FR-009 | `tests/unit/test_trigger.py` (10 cases), `test_group_chat.py::test_chatter_between_humans_stays_silent` |
| FR-010, FR-011 | `test_private_chat.py` (prompt, reuse, abort), `test_streaming.py` |
| FR-012 | `test_topics_and_selection.py::test_model_choice_is_stored_and_applied` |
| FR-013 | `tests/integration/test_approvals.py` (3 cases) |
| FR-014 | `BotApp._cmd_status` covered through `test_private_chat` fixture wiring |
| FR-015 | `test_attachments.py`, `test_attachment_flow.py` |
| FR-016 | `test_store.py::test_turn_recording_is_unique_per_update`, `test_private_chat.py::test_duplicate_update_runs_once` |
| FR-017 | `test_group_chat.py::test_both_humans_are_answered_in_arrival_order` |
| FR-018 | `test_config.py` (5 cases) |
| FR-019 | `app/main.py` conflict handling; manual review (no automated 409 simulation — PTB raises before our code) |
| FR-020 | `tests/unit/test_health.py` |
| FR-021, FR-022 | `test_logging.py`, `test_health.py::test_health_payload_never_contains_secrets`, `test_audit.py` |

## Lint

```text
$ make lint
All checks passed!
```

## Container

```text
$ docker build -t opencode-telegram-bot:dev .
Successfully tagged opencode-telegram-bot:dev

$ docker run … (probe process)
running as uid 10001

$ /healthz (inside the container)
{"status":"ok","uptime_s":5,"poller_alive":true,"last_update_age_s":5,"sse_connected":false,"agent_ok":false,"rejections":0}
```

The image runs as uid 10001, writes only under `/data`, and the health endpoint
answers 200 with a healthy poller state. `agent_ok: false` is expected in the
probe: no OpenCode server was reachable.

## Not verified here

- Real Telegram delivery and real OpenCode streaming: both need an OC3 box with a
  token and a running server. The integration fakes mirror the documented shapes
  but are not a substitute for one live smoke test.
- Group privacy-mode behaviour with a real group: rules are enforced bot-side, so
  the platform mode cannot change the outcome, but a live check is still worth
  doing when OC3 exists.
