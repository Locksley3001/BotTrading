from fastapi.testclient import TestClient

from app.main import app


def test_root_serves_dashboard() -> None:
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Deriv Rise/Fall" in response.text


def test_state_endpoint_has_canonical_keys() -> None:
    with TestClient(app) as client:
        response = client.get("/api/state")
    assert response.status_code == 200
    payload = response.json()
    assert {"settings", "markets", "signals", "events"}.issubset(payload)
