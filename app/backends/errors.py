"""Errors shared by every harness adapter (see ``contracts/backend.md``)."""

from __future__ import annotations


class HarnessError(RuntimeError):
    """Base class for adapter failures. ``user_message`` is safe to send to chat."""

    user_message = "the harness returned an unexpected response"


class AuthError(HarnessError):
    user_message = "I cannot authenticate against the harness. Check its credentials."


class SessionGone(HarnessError):
    user_message = "that session no longer exists."


class Busy(HarnessError):
    user_message = "the harness is still working on the previous request."


class InvalidRequest(HarnessError):
    user_message = "the harness rejected that choice."


class Unavailable(HarnessError):
    user_message = "the harness is unreachable right now."


class Unsupported(HarnessError):
    """A capability this harness does not have. Never a crash, always a sentence."""

    user_message = "that feature is not available on this harness."
