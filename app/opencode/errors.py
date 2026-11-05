"""Errors raised by the OpenCode adapter (contract C10)."""

from __future__ import annotations


class OpenCodeError(RuntimeError):
    """Base class for adapter failures."""

    user_message = "the agent server returned an unexpected response"


class AuthError(OpenCodeError):
    user_message = "I cannot authenticate against the agent server. Check the server password."


class SessionGone(OpenCodeError):
    user_message = "that session no longer exists on the agent server."


class Busy(OpenCodeError):
    user_message = "the agent is still working on the previous request."


class InvalidRequest(OpenCodeError):
    user_message = "the agent server rejected that choice."


class Unavailable(OpenCodeError):
    user_message = "the agent server is unreachable right now."
