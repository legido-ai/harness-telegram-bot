"""Session files on disk: the Pi backend's session catalogue.

A Pi session is a JSONL file under ``PI_SESSION_DIR``; there is no server to ask.
The file path is the opaque binding the store keeps, so nothing here has to be
parsed twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionFile:
    path: Path
    label: str
    updated: float


def label_for(path: Path) -> str:
    """``2026-11-13T07-02-10-123Z_21442158-0.jsonl`` → ``21442158-0``.

    The timestamp prefix is noise in a chat; the trailing part is the name the
    bridge gave the session, or the id the agent generated.
    """

    stem = path.stem
    if "_" in stem:
        tail = stem.split("_", 1)[1]
        if tail:
            return tail[:40]
    return stem[:40]


def list_sessions(directory: Path, limit: int = 10) -> list[SessionFile]:
    if not directory.exists():
        return []
    found: list[SessionFile] = []
    for path in directory.glob("*.jsonl"):
        try:
            updated = path.stat().st_mtime
        except OSError:
            continue
        found.append(SessionFile(path=path, label=label_for(path), updated=updated))
    found.sort(key=lambda item: item.updated, reverse=True)
    return found[:limit]


def resolve(directory: Path, ref: str) -> Path:
    """Accept a path or a bare file name; return the path we will bind."""

    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate
    return directory / ref
