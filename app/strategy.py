from __future__ import annotations

from statistics import mean

from app.models import Candle, Outcome, SignalDirection


def normalize_ticks_to_candles(symbol: str, ticks: list[tuple[int, float]], granularity: int) -> list[Candle]:
    buckets: dict[int, list[float]] = {}
    for epoch, quote in ticks:
        bucket = epoch - (epoch % granularity)
        buckets.setdefault(bucket, []).append(float(quote))
    candles: list[Candle] = []
    for bucket in sorted(buckets):
        prices = buckets[bucket]
        candles.append(
            Candle(
                symbol=symbol,
                epoch=bucket,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                granularity=granularity,
                closed=True,
            )
        )
    return candles


def cci(candles: list[Candle], period: int = 20) -> list[float | None]:
    values: list[float | None] = []
    typical_prices = [(c.high + c.low + c.close) / 3 for c in candles]
    for index, typical in enumerate(typical_prices):
        if index + 1 < period:
            values.append(None)
            continue
        window = typical_prices[index + 1 - period : index + 1]
        sma = mean(window)
        mean_deviation = mean(abs(value - sma) for value in window)
        if mean_deviation == 0:
            values.append(0.0)
            continue
        values.append((typical - sma) / (0.015 * mean_deviation))
    return values


def decide_continuation_or_reversal(candles: list[Candle]) -> tuple[SignalDirection | None, int, int, str]:
    if len(candles) < 25:
        return None, 0, 0, "not_enough_candles"
    latest = candles[-1]
    previous = candles[-4:-1]
    cci_values = cci(candles)
    latest_cci = cci_values[-1]
    if latest_cci is None:
        return None, 0, 0, "not_enough_cci"

    body = abs(latest.close - latest.open)
    range_size = max(latest.high - latest.low, 1e-12)
    body_ratio = body / range_size
    bullish_pressure = sum(1 for c in previous if c.close > c.open)
    bearish_pressure = sum(1 for c in previous if c.close < c.open)
    upper_wick = latest.high - max(latest.open, latest.close)
    lower_wick = min(latest.open, latest.close) - latest.low

    factor_score = 0
    if abs(latest_cci) >= 100:
        factor_score += 1
    if body_ratio >= 0.55:
        factor_score += 1
    if bullish_pressure >= 2 or bearish_pressure >= 2:
        factor_score += 1
    if upper_wick > body * 0.8 or lower_wick > body * 0.8:
        factor_score += 1

    if latest_cci > 100 and upper_wick > body and latest.close < latest.open:
        return SignalDirection.FALL, min(10, 6 + factor_score), factor_score, "overbought_rejection"
    if latest_cci < -100 and lower_wick > body and latest.close > latest.open:
        return SignalDirection.RISE, min(10, 6 + factor_score), factor_score, "oversold_rejection"
    if bullish_pressure >= 3 and latest.close > latest.open and body_ratio >= 0.55:
        return SignalDirection.RISE, min(10, 5 + factor_score), factor_score, "bullish_continuation"
    if bearish_pressure >= 3 and latest.close < latest.open and body_ratio >= 0.55:
        return SignalDirection.FALL, min(10, 5 + factor_score), factor_score, "bearish_continuation"
    recent_mean = mean(c.close for c in candles[-6:-1])
    if latest.close > recent_mean and latest_cci > 35 and latest.close > latest.open:
        return SignalDirection.RISE, min(10, 6 + factor_score), max(3, factor_score), "moderate_bullish_pressure"
    if latest.close < recent_mean and latest_cci < -35 and latest.close < latest.open:
        return SignalDirection.FALL, min(10, 6 + factor_score), max(3, factor_score), "moderate_bearish_pressure"
    return None, factor_score, factor_score, "no_edge"


def resolve_strict_rise_fall(direction: SignalDirection, entry_spot: float, exit_spot: float) -> Outcome:
    if direction == SignalDirection.RISE:
        if exit_spot > entry_spot:
            return Outcome.WIN
        if exit_spot == entry_spot:
            return Outcome.EQUAL_LOSS
        return Outcome.LOSS
    if exit_spot < entry_spot:
        return Outcome.WIN
    if exit_spot == entry_spot:
        return Outcome.EQUAL_LOSS
    return Outcome.LOSS


def virtual_balance_after(balance: float, stake: float, payout: float, outcome: Outcome) -> float:
    if outcome == Outcome.WIN:
        return balance - stake + payout
    if outcome in {Outcome.LOSS, Outcome.EQUAL_LOSS}:
        return balance - stake
    return balance
