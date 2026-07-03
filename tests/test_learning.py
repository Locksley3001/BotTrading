import pytest

from app.config import Settings
from app.event_store import LocalJsonlEventStore
from app.learning import LearningService
from app.models import Outcome, Signal, SignalDirection, TradeEvent, TradeEventType, VirtualTrade, VirtualTradeStatus


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


@pytest.mark.asyncio
async def test_learning_filter_blocks_negative_specific_edge(tmp_path) -> None:
    settings = Settings(
        DATA_DIR=str(tmp_path),
        LEARNING_WARMUP_SAMPLES=1,
        LEARNING_MIN_RULE_SAMPLES=2,
        LEARNING_STRONG_RULE_SAMPLES=2,
    )
    store = LocalJsonlEventStore(tmp_path)
    for index in range(3):
        signal = Signal(
            asset="frxAUDUSD",
            display_name="AUD/USD",
            market="forex",
            direction=SignalDirection.FALL,
            contract_type="PUT",
            duration=15,
            duration_unit="m",
            timeframe=300,
            score=8,
            factor_score=3,
            stake=10,
            reason="bad_edge",
        )
        await store.upsert_signal(signal)
        await store.upsert_virtual_trade(
            VirtualTrade(
                signal_id=signal.signal_id,
                asset=signal.asset,
                market=signal.market,
                direction=signal.direction,
                contract_type=signal.contract_type,
                stake=10,
                payout=18,
                payout_rate=0.8,
                entry_spot=1.0,
                entry_epoch=index,
                expiry_epoch=index + 1,
                status=VirtualTradeStatus.SETTLED,
                outcome=Outcome.LOSS,
                exit_spot=1.1,
            )
        )

    service = LearningService(settings, store, store)
    await service.rebuild_from_virtual_trades()

    decision = service.evaluate_signal(
        asset="frxAUDUSD",
        direction="FALL",
        contract_type="PUT",
        reason="bad_edge",
        score=8,
        factor_score=3,
    )

    assert decision["action"] == "block"
    assert decision["reason"] == "negative_learning_edge"


@pytest.mark.asyncio
async def test_learning_summary_counts_decisions_and_shadows(tmp_path) -> None:
    settings = Settings(DATA_DIR=str(tmp_path))
    store = LocalJsonlEventStore(tmp_path)
    await store.append_event(
        TradeEvent(event_type=TradeEventType.LEARNING_FILTER_ALLOWED, idempotency_key="allowed:1")
    )
    await store.append_event(
        TradeEvent(event_type=TradeEventType.LEARNING_FILTER_BLOCKED, idempotency_key="blocked:1")
    )
    await store.append_event(
        TradeEvent(event_type=TradeEventType.LEARNING_SHADOW_OPENED, idempotency_key="shadow:1")
    )
    await store.upsert_virtual_trade(
        VirtualTrade(
            signal_id="shadow_sig_1",
            asset="frxAUDUSD",
            market="forex",
            direction=SignalDirection.RISE,
            contract_type="CALL",
            stake=10,
            payout=18,
            payout_rate=0.8,
            entry_spot=1.0,
            entry_epoch=1,
            expiry_epoch=2,
            status=VirtualTradeStatus.SHADOW_SETTLED,
            outcome=Outcome.WIN,
            exit_spot=1.1,
        )
    )

    summary = LearningService(settings, store, store).summary()

    assert summary["learning_decisions"]["allowed"] == 1
    assert summary["learning_decisions"]["blocked"] == 1
    assert summary["shadows"]["total"] == 1
    assert summary["shadows"]["wins"] == 1
