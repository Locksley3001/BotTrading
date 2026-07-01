import pytest

from app.config import Settings
from app.event_store import LocalJsonlEventStore
from app.learning import LearningService
from app.models import Outcome, Signal, SignalDirection, VirtualTrade, VirtualTradeStatus


@pytest.mark.asyncio
async def test_learning_rebuilds_rules_from_settled_virtual_trades(tmp_path) -> None:
    settings = Settings(DATA_DIR=str(tmp_path))
    store = LocalJsonlEventStore(tmp_path)
    signal = Signal(
        asset="frxAUDUSD",
        display_name="AUD/USD",
        market="forex",
        direction=SignalDirection.RISE,
        contract_type="CALL",
        duration=15,
        duration_unit="m",
        timeframe=300,
        score=8,
        factor_score=3,
        stake=10,
        reason="moderate_bullish_pressure",
    )
    await store.upsert_signal(signal)
    trade = VirtualTrade(
        signal_id=signal.signal_id,
        asset=signal.asset,
        market=signal.market,
        direction=signal.direction,
        contract_type=signal.contract_type,
        stake=10,
        payout=18.18,
        payout_rate=0.818,
        entry_spot=1.0,
        entry_epoch=1,
        expiry_epoch=2,
        status=VirtualTradeStatus.SETTLED,
        outcome=Outcome.WIN,
        exit_spot=1.1,
    )
    await store.upsert_virtual_trade(trade)

    learning = await LearningService(settings, store, store).rebuild_from_virtual_trades()

    assert learning["settled_samples"] == 1
    assert learning["rules"]["global"]["wins"] == 1
    assert learning["rules"]["asset_direction:frxAUDUSD:RISE"]["win_rate"] == 100.0
