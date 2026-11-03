"""The only module allowed to speak HTTP to the OpenCode V2 server.

Every endpoint, payload shape and auth detail from
``specs/001-telegram-group-bot/contracts/opencode-api.md`` lives here; handlers
call these methods and never build URLs themselves (constitution Principle VIII).
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import httpx

from app.opencode.errors import AuthError, Busy, SessionGone, Unavailable

PERMISSION_DECISIONS = ("once", "always", "reject")


def _data(payload: Any) -> Any:
    """Unwrap the ``{"data": ...}`` envelope used by the V2 API."""

    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


class OpenCodeClient:
    def __init__(
        self,
        base_url: str,
        password: str,
        *,
        username: str = "opencode",
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            auth=(username, password),
            timeout=httpx.Timeout(timeout, connect=10.0),
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "opencode-telegram-bot/0.1"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def stream(self, method: str, path: str, **kwargs: Any) -> Any:
        """Context-manager passthrough used by the SSE consumer (C9)."""

        return self._client.stream(method, path, **kwargs)

    # -- plumbing --------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise Unavailable() from exc
        except httpx.HTTPError as exc:
            raise Unavailable() from exc

        if response.status_code == 401:
            raise AuthError()
        if response.status_code == 409:
            raise Busy()
        if response.status_code == 404:
            body = response.text.lower()
            if "session" in body:
                raise SessionGone()
        if response.status_code >= 500:
            raise Unavailable()
        if response.status_code >= 400:
            raise Unavailable()
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        return _data(response.json())

    # -- C1 liveness -----------------------------------------------------

    async def info(self) -> dict[str, Any]:
        return await self._json("GET", "/api/info") or {}

    # -- C2 create session ----------------------------------------------

    async def create_session(
        self,
        title: str | None = None,
        *,
        agent: str | None = None,
        model: dict[str, str] | None = None,
    ) -> str:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if agent:
            body["agent"] = agent
        if model:
            body["model"] = model
        data = await self._json("POST", "/api/session", json=body)
        session_id = (data or {}).get("id")
        if not session_id:
            raise Unavailable()
        return str(session_id)

    # -- C3 list sessions ------------------------------------------------

    async def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        data = await self._json("GET", "/api/session", params={"limit": limit, "order": "desc"})
        if isinstance(data, dict):
            data = data.get("sessions") or data.get("items") or []
        return list(data or [])

    # -- C4 prompt -------------------------------------------------------

    async def prompt(
        self,
        session_id: str,
        text: str,
        *,
        files: Sequence[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if files:
            body["files"] = list(files)
        if metadata:
            body["metadata"] = metadata
        return await self._json("POST", f"/api/session/{session_id}/prompt", json=body) or {}

    # -- C5 interrupt ----------------------------------------------------

    async def interrupt(self, session_id: str) -> bool:
        data = await self._json(
            "POST", f"/api/session/{session_id}/interrupt", params={"resume": "false"}
        )
        return bool((data or {}).get("interrupted")) if isinstance(data, dict) else False

    # -- C6 permission ---------------------------------------------------

    async def reply_permission(
        self, session_id: str, request_id: str, decision: str, message: str | None = None
    ) -> None:
        if decision not in PERMISSION_DECISIONS:
            raise ValueError(f"invalid permission decision: {decision}")
        body: dict[str, Any] = {"decision": decision}
        if message:
            body["message"] = message
        await self._request(
            "POST", f"/api/session/{session_id}/permission/{request_id}/reply", json=body
        )

    # -- C7 form ---------------------------------------------------------

    async def reply_form(self, session_id: str, form_id: str, answer: dict[str, Any]) -> None:
        await self._request(
            "POST", f"/api/session/{session_id}/form/{form_id}/reply", json=answer
        )

    # -- C8 model and agent ----------------------------------------------

    async def set_model(self, session_id: str, provider_id: str, model_id: str) -> None:
        await self._request(
            "POST",
            f"/api/session/{session_id}/model",
            json={"providerID": provider_id, "modelID": model_id},
        )

    async def set_agent(self, session_id: str, agent: str) -> None:
        await self._request("POST", f"/api/session/{session_id}/agent", json={"agent": agent})

    async def models(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/api/model")
        if isinstance(data, dict):
            data = data.get("models") or data.get("items") or []
        return list(data or [])

    async def agents(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/api/agent")
        if isinstance(data, dict):
            data = data.get("agents") or data.get("items") or []
        return list(data or [])


def basic_auth_header(username: str, password: str) -> str:
    """Helper for tests and for documenting the exact header shape."""

    raw = f"{username}:{password}".encode()
    return "Basic " + base64.b64encode(raw).decode()
