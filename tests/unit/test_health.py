from __future__ import annotations

from fastapi.testclient import TestClient

from app.health import HealthState, create_app


def test_healthz_is_degraded_before_polling(settings, store) -> None:
    state = HealthState()
    client = TestClient(create_app(settings, store, state))
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


def test_healthz_is_ok_when_polling(settings, store) -> None:
    state = HealthState(poller_alive=True)
    state.note_update()
    client = TestClient(create_app(settings, store, state))
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["agent_ok"] in (True, False)


def test_health_payload_never_contains_secrets(settings, store) -> None:
    state = HealthState(poller_alive=True)
    client = TestClient(create_app(settings, store, state))
    body = client.get("/healthz").text
    assert settings.bot_token not in body
    assert settings.opencode_password not in body


def test_readyz_reports_schema(settings, store) -> None:
    client = TestClient(create_app(settings, store, HealthState()))
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["schema_version"] == 1


def test_audit_endpoint_returns_turns_without_bodies(settings, store) -> None:
    store.record_turn(
        chat_id=-100,
        thread_id=0,
        session_id="ses_a",
        user_id=111,
        update_id=3,
        trigger="mention",
    )
    client = TestClient(create_app(settings, store, HealthState()))
    payload = client.get("/audit?limit=5").json()
    assert payload["turns"][0]["user_id"] == 111
    assert "text" not in payload["turns"][0]
