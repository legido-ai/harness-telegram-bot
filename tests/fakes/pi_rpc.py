#!/usr/bin/env python3
"""A stand-in for ``pi --mode rpc`` so adapter tests are offline and fast.

Behaves like the real agent for the commands the backend uses: it reports a
session file, streams two text deltas, settles the turn, and answers the
catalogue/stat commands. Prompts and images are appended to ``--fake-log`` so a
test can assert what crossed the wire.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULTS = {
    "cost": 0.0125,
    "contextWindow": 200_000,
    "contextTokens": 42_000,
    "provider": "fake-provider",
    "model": "fake-model",
}


def _arg(argv: list[str], name: str) -> str | None:
    for index, value in enumerate(argv):
        if value == name and index + 1 < len(argv):
            return argv[index + 1]
    return None


def main() -> int:
    argv = sys.argv[1:]
    session_dir = Path(_arg(argv, "--session-dir") or "/tmp")
    session = _arg(argv, "--session")
    log_path = _arg(argv, "--fake-log")
    if session:
        path = Path(session)
    else:
        session_dir.mkdir(parents=True, exist_ok=True)
        path = session_dir / f"fake-{int(__import__('time').time() * 1000)}.jsonl"
        path.write_text("", encoding="utf-8")

    def emit(payload: dict) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def respond(request_id: str, command: str, data: dict | None = None) -> None:
        emit(
            {
                "type": "response",
                "id": request_id,
                "command": command,
                "success": True,
                "data": data or {},
            }
        )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = command.get("type")
        request_id = str(command.get("id") or "")

        if log_path:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(command) + "\n")

        if kind == "get_state":
            respond(
                request_id,
                kind,
                {
                    "sessionFile": str(path),
                    "sessionId": path.stem,
                    "messageCount": 2,
                    "isStreaming": False,
                    "model": {"id": DEFAULTS["model"], "provider": DEFAULTS["provider"]},
                },
            )
        elif kind == "get_session_stats":
            respond(
                request_id,
                kind,
                {
                    "sessionId": path.stem,
                    "cost": DEFAULTS["cost"],
                    "contextUsage": {
                        "tokens": DEFAULTS["contextTokens"],
                        "contextWindow": DEFAULTS["contextWindow"],
                        "percent": 21,
                    },
                },
            )
        elif kind == "get_available_models":
            respond(
                request_id,
                kind,
                {
                    "models": [
                        {
                            "id": DEFAULTS["model"],
                            "name": "Fake model",
                            "provider": DEFAULTS["provider"],
                            "contextWindow": DEFAULTS["contextWindow"],
                        },
                        {
                            "id": "second-model",
                            "name": "Second",
                            "provider": DEFAULTS["provider"],
                            "contextWindow": 100_000,
                        },
                    ]
                },
            )
        elif kind in {"set_model", "set_session_name", "switch_session", "abort", "new_session"}:
            respond(request_id, kind, {})
            if kind == "abort":
                emit({"type": "agent_settled"})
        elif kind == "prompt":
            respond(request_id, kind, {"disposition": "started"})
            emit(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": "Hello "},
                }
            )
            emit(
                {
                    "type": "message_update",
                    "assistantMessageEvent": {"type": "text_delta", "delta": "from Pi"},
                }
            )
            emit({"type": "message_end", "message": {"role": "assistant"}})
            emit({"type": "agent_settled"})
        else:
            respond(request_id, kind, {})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
