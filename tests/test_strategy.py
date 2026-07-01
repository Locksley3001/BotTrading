from app.models import Candle, Outcome, SignalDirection
from app.strategy import cci, normalize_ticks_to_candles, resolve_strict_rise_fall, virtual_balance_after


def test_normalize_ticks_to_candles() -> None:
    candles = normalize_ticks_to_candles("frxEURUSD", [(0, 1.0), (10, 1.2), (61, 1.1)], 60)
    assert len(candles) == 2
    assert candles[0].open == 1.0
    assert candles[0].high == 1.2
    assert candles[0].close == 1.2
    assert candles[1].epoch == 60


def test_cci_returns_values_after_period() -> None:
    candles = [
        Candle(symbol="x", epoch=i * 60, open=i, high=i + 1, low=i - 1, close=i + 0.5, granularity=60)
        for i in range(25)
    ]
    values = cci(candles, period=20)
    assert values[18] is None
    assert values[-1] is not None


def test_strict_rise_fall_equal_is_equal_loss() -> None:
    assert resolve_strict_rise_fall(SignalDirection.RISE, 100, 101) == Outcome.WIN
    assert resolve_strict_rise_fall(SignalDirection.RISE, 100, 99) == Outcome.LOSS
    assert resolve_strict_rise_fall(SignalDirection.RISE, 100, 100) == Outcome.EQUAL_LOSS
    assert resolve_strict_rise_fall(SignalDirection.FALL, 100, 99) == Outcome.WIN
    assert resolve_strict_rise_fall(SignalDirection.FALL, 100, 101) == Outcome.LOSS
    assert resolve_strict_rise_fall(SignalDirection.FALL, 100, 100) == Outcome.EQUAL_LOSS


def test_virtual_balance_uses_real_payout() -> None:
    assert virtual_balance_after(100, 10, 18.5, Outcome.WIN) == 108.5
    assert virtual_balance_after(100, 10, 18.5, Outcome.LOSS) == 90
