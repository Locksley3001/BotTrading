import pytest

from app.config import Settings
from app.event_store import LocalJsonlEventStore
from app.models import VirtualAccountState
from app.telegram_notifier import TelegramNotifier


@pytest.mark.asyncio
async def test_account_reset_alert_records_telegram_projection(tmp_path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path),
        TELEGRAM_ENABLED="true",
        TELEGRAM_BOT_TOKEN="123:test",
        TELEGRAM_CHAT_ID="456",
    )
    store = LocalJsonlEventStore(tmp_path)
    notifier = TelegramNotifier(settings, store)

    async def fake_send_text(text: str) -> dict[str, object]:
        assert "META ALCANZADA" in text
        assert "Saldo reiniciado" in text
        return {"ok": True, "message_id": 99}

    notifier._send_text = fake_send_text  # type: ignore[method-assign]
    await notifier.project_account_reset_alert(
        reason="target_reached",
        account=VirtualAccountState(
            balance=100,
            initial_balance=100,
            target_balance=150,
            stake=10,
            target_hits=1,
            resets=1,
        ),
        balance_before_reset=151,
        triggering_signal_id="sig_1",
    )

    telegram_events = store.read_telegram_events()
    assert telegram_events[0]["message_type"] == "target_alert"
    assert telegram_events[0]["payload"]["triggering_signal_id"] == "sig_1"
