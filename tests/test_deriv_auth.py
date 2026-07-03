from app.config import Settings
from app.deriv_adapter import DerivAuthenticatedClient


def test_empty_deriv_auth_secrets_do_not_count_as_configured(tmp_path) -> None:
    settings = Settings(DATA_DIR=str(tmp_path), DERIV_APP_ID="", DERIV_ACCESS_TOKEN="", DERIV_LEGACY_API_TOKEN="")

    requirements = settings.deriv_auth_requirements()

    assert not requirements["ready_for_authorize"]
    assert "DERIV_APP_ID" in requirements["missing"]
    assert "DERIV_ACCESS_TOKEN or DERIV_LEGACY_API_TOKEN" in requirements["missing"]


def test_deriv_auth_requirements_reject_email_password_only(tmp_path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path),
        DERIV_EMAIL="user@example.com",
        DERIV_PASSWORD="secret",
    )

    requirements = settings.deriv_auth_requirements()

    assert requirements["email_password_present"]
    assert not requirements["email_password_supported_for_api"]
    assert not requirements["ready_for_authorize"]


def test_authenticated_websocket_url_uses_app_id(tmp_path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path),
        DERIV_APP_ID="1234",
        DERIV_ACCESS_TOKEN="token",
        DERIV_ACCOUNT_ID="VRTC123456",
    )

    assert DerivAuthenticatedClient(settings).websocket_url().endswith("?app_id=1234")
    assert settings.deriv_auth_ready_for_authorize
