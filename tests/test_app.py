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


def test_deriv_callback_direct_visit_is_helpful() -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/deriv/callback")
    assert response.status_code == 200
    assert "Callback Deriv activo" in response.text
    assert "lo abriste directo" in response.text


def test_deriv_callback_extracts_account_and_token() -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/deriv/callback?acct1=VRTC123456&token1=abc123&cur1=USD")
    assert response.status_code == 200
    assert "DERIV_ACCOUNT_ID=VRTC123456" in response.text
    assert "DERIV_ACCESS_TOKEN=abc123" in response.text
