import pytest

from app.event_store import LocalJsonlEventStore
from app.models import TradeEvent, TradeEventType


@pytest.mark.asyncio
async def test_event_store_is_idempotent(tmp_path) -> None:
    store = LocalJsonlEventStore(tmp_path)
    event = TradeEvent(
        event_type=TradeEventType.SIGNAL_DECIDED,
        idempotency_key="signal_decided:sig_1",
        signal_id="sig_1",
    )
    await store.append_event(event)
    await store.append_event(event)
    rows = store.read_events()
    assert len(rows) == 1
    assert rows[0]["idempotency_key"] == "signal_decided:sig_1"
