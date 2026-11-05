"""Attachment intake with explicit limits (contract T8, FR-015)."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings

log = logging.getLogger("bot.attachments")

ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
}
MAX_FILES = 5


class AttachmentError(RuntimeError):
    """Carries a user-facing explanation, never a path or a secret."""


def mime_for(name: str, declared: str | None) -> str | None:
    if declared in ALLOWED_MIME:
        return declared
    lower = name.lower()
    for mime, suffix in ALLOWED_MIME.items():
        if lower.endswith(suffix):
            return mime
    return None


def check_size(size: int | None, settings: Settings) -> None:
    if size is not None and size > settings.max_attachment_mb * 1024 * 1024:
        raise AttachmentError(
            f"that file is larger than the {settings.max_attachment_mb} MB limit. Send a smaller one."
        )


def _candidates(message: object) -> list[tuple[object, str, str | None]]:
    """Return (telegram file object, filename, declared mime) for a message."""

    files: list[tuple[object, str, str | None]] = []
    photo = getattr(message, "photo", None)
    if photo:
        largest = max(photo, key=lambda size: size.file_size or 0)
        files.append((largest, "photo.jpg", "image/jpeg"))
    document = getattr(message, "document", None)
    if document is not None:
        files.append(
            (document, document.file_name or "file", getattr(document, "mime_type", None))
        )
    return files


async def collect(bot: object, message: object, settings: Settings) -> list[dict[str, str]]:
    """Download allowed attachments into ``DATA_DIR/tmp`` and return file refs."""

    candidates = _candidates(message)
    if not candidates:
        return []
    if len(candidates) > MAX_FILES:
        raise AttachmentError(f"I can take at most {MAX_FILES} files per message.")

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    refs: list[dict[str, str]] = []
    for index, (file_obj, name, declared) in enumerate(candidates):
        mime = mime_for(name, declared)
        if mime is None:
            raise AttachmentError(
                "I can read images, PDF and text files only. That one is a different type."
            )
        check_size(getattr(file_obj, "file_size", None), settings)
        suffix = ALLOWED_MIME[mime]
        target = settings.tmp_dir / f"{getattr(file_obj, 'file_unique_id', 'file')[:32]}-{index}{suffix}"
        try:
            remote = await bot.get_file(file_obj.file_id)
            await remote.download_to_drive(custom_path=Path(target))
        except Exception as exc:  # network or Telegram refusal
            log.warning("attachment download failed: %s", type(exc).__name__)
            raise AttachmentError("I could not download that file from Telegram.") from exc
        refs.append({"type": "file", "path": str(target), "mime": mime})
    return refs


def cleanup(refs: list[dict[str, str]]) -> None:
    for ref in refs:
        try:
            Path(ref["path"]).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort
            log.debug("could not remove temp attachment")
