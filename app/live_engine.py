from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.deriv_adapter import DerivAPIError, DerivPublicClient, verify_longcode_mapping
from app.event_store import EventSink, LocalJsonlEventStore
from app.learning import LearningService
from app.market_discovery import MarketDiscoveryService
from app.models import (
    Candle,
    Outcome,
    Signal,
    SignalDirection,
    SignalStatus,
    TradeEvent,
    TradeEventType,
    VirtualTrade,
    VirtualTradeStatus,
)
from app.strategy import decide_continuation_or_reversal, resolve_strict_rise_fall
from app.telegram_notifier import TelegramNotifier
from app.virtual_account import VirtualAccountService


class LiveMarketEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        client: DerivPublicClient,
        store: EventSink,
        local_store: LocalJsonlEventStore,
        virtual_account: VirtualAccountService,
        telegram: TelegramNotifier,
        learning: LearningService,
    ):
        self.settings = settings
        self.client = client
        self.store = store
        self.local_store = local_store
        self.virtual_account = virtual_account
        self.telegram = telegram
        self.learning = learning
        self.enabled = True
        self.last_scan_at: datetime | None = None
        self.last_error: str | None = None
        self.last_cycle: dict[str, Any] = {}
        self.candles_by_symbol: dict[str, list[Candle]] = {}
        self.last_signal_epoch: dict[str, int] = {}
        self.task: asyncio.Task | None = None
        self.broker_trading_enabled = False
        self._hydrate_cooldowns()

    def start(self) -> None:
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while True:
            try:
                if self.enabled:
                    await self.scan_once()
                    await self.settle_due_virtual_trades()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}"
            await asyncio.sleep(max(5.0, self.settings.market_scan_interval_seconds))

    async def scan_once(self) -> dict[str, Any]:
        markets = await self._enabled_markets()
        cycle = {
            "started_at": datetime.now(UTC).isoformat(),
            "markets_checked": len(markets),
            "signals_created": 0,
            "blocked": [],
            "analyses": [],
        }
        for market in markets:
            analysis = await self._scan_market(market)
            cycle["analyses"].append(analysis)
            if analysis.get("signal_created"):
                cycle["signals_created"] += 1
            if analysis.get("blocked_reason"):
                cycle["blocked"].append({"asset": market["symbol"], "reason": analysis["blocked_reason"]})
        self.last_scan_at = datetime.now(UTC)
        self.last_cycle = cycle
        await self.store.append_event(
            TradeEvent(
                event_type=TradeEventType.LIVE_ANALYSIS_CYCLE,
                idempotency_key=f"live_analysis_cycle:{self.last_scan_at.isoformat()}",
                payload=cycle,
            )
        )
        return cycle

    async def _enabled_markets(self) -> list[dict[str, Any]]:
        markets = [row for row in self.local_store.read_markets(limit=500) if row.get("enabled")]
        if markets:
            return markets
        service = MarketDiscoveryService(self.settings, self.client)
        discovered, events = await service.discover(self.settings.live_test_markets or self.settings.markets)
        for market in discovered:
            await self.store.upsert_market(market)
        for event in events:
            await self.store.append_event(event)
        return [market.model_dump(mode="json") for market in discovered if market.enabled]

    async def _scan_market(self, market: dict[str, Any]) -> dict[str, Any]:
        symbol = str(market["symbol"])
        candles_raw = await self.client.ticks_history(symbol, count=self.settings.candle_count, granularity=60)
        candles = [
            Candle(
                symbol=symbol,
                epoch=int(item["epoch"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                granularity=60,
                closed=True,
            )
            for item in candles_raw
        ]
        self.candles_by_symbol[symbol] = candles
        direction, score, factor_score, reason = decide_continuation_or_reversal(candles)
        latest = candles[-1] if candles else None
        analysis = {
            "asset": symbol,
            "display_name": market.get("display_name"),
            "candles": len(candles),
            "latest_close": latest.close if latest else None,
            "direction": direction.value if direction else None,
            "score": score,
            "factor_score": factor_score,
            "reason": reason,
            "signal_created": False,
        }
        if not direction:
            analysis["blocked_reason"] = reason
            return analysis
        capacity_reason = self._virtual_capacity_block(symbol)
        if capacity_reason:
            analysis["blocked_reason"] = capacity_reason
            return analysis
        if self._cooldown_active(symbol):
            analysis["blocked_reason"] = "signal_cooldown"
            return analysis

        contract_type = (
            self.settings.deriv_rise_contract_type
            if direction == SignalDirection.RISE
            else self.settings.deriv_fall_contract_type
        )
        duration = int(market.get("duration") or self.settings.deriv_default_duration)
        duration_unit = str(market.get("duration_unit") or self.settings.deriv_default_duration_unit)
        base_signal_score = max(7, score)
        learning_decision = self.learning.evaluate_signal(
            asset=symbol,
            direction=direction.value,
            contract_type=contract_type,
            reason=reason,
            score=base_signal_score,
            factor_score=factor_score,
        )
        analysis["learning"] = {
            "action": learning_decision["action"],
            "verdict": learning_decision["verdict"],
            "reason": learning_decision["reason"],
            "score_delta": learning_decision["score_delta"],
            "adjusted_score": learning_decision["adjusted_score"],
        }
        if learning_decision["action"] == "block":
            signal = Signal(
                asset=symbol,
                display_name=market.get("display_name"),
                market=str(market.get("market") or ""),
                direction=direction,
                contract_type=contract_type,
                duration=duration,
                duration_unit=duration_unit,
                timeframe=self.settings.default_timeframe,
                score=int(learning_decision["adjusted_score"]),
                factor_score=factor_score,
                stake=self.virtual_account.state.stake,
                status=SignalStatus.SHADOW,
                reason=reason,
            )
            await self.store.upsert_signal(signal)
            await self.store.append_event(
                TradeEvent(
                    signal_id=signal.signal_id,
                    event_type=TradeEventType.SIGNAL_DECIDED,
                    idempotency_key=f"signal_decided:{signal.signal_id}",
                    asset=signal.asset,
                    market=signal.market,
                    payload={**signal.model_dump(mode="json"), "learning_decision": learning_decision},
                )
            )
            await self.store.append_event(
                TradeEvent(
                    signal_id=signal.signal_id,
                    event_type=TradeEventType.LEARNING_FILTER_BLOCKED,
                    idempotency_key=f"learning_filter_blocked:{signal.signal_id}",
                    asset=signal.asset,
                    market=signal.market,
                    payload=learning_decision,
                )
            )
            if self.settings.learning_shadow_enabled and latest:
                entry_epoch = int(datetime.now(UTC).timestamp())
                await self._open_learning_shadow_trade(
                    signal=signal,
                    entry_spot=latest.close,
                    entry_epoch=entry_epoch,
                    expiry_epoch=entry_epoch + _duration_seconds(duration, duration_unit),
                    learning_decision=learning_decision,
                )
            self.last_signal_epoch[symbol] = int(datetime.now(UTC).timestamp())
            analysis["blocked_reason"] = "learning_filter"
            analysis["signal_id"] = signal.signal_id
            return analysis

        try:
            proposal = await self.client.proposal(
                symbol=symbol,
                contract_type=contract_type,
                amount=self.virtual_account.state.stake,
                duration=duration,
                duration_unit=duration_unit,
            )
        except DerivAPIError as exc:
            await self._proposal_blocked(symbol, market, exc.code or "proposal_rejected", {"message": str(exc)})
            analysis["blocked_reason"] = exc.code or "proposal_rejected"
            return analysis

        mapping = verify_longcode_mapping(direction, proposal.contract_type, proposal.longcode)
        if not mapping.verified:
            await self._proposal_blocked(symbol, market, "mapping_failed", {"longcode": proposal.longcode})
            analysis["blocked_reason"] = "mapping_failed"
            return analysis
        if proposal.payout_rate < self.settings.deriv_min_payout_rate:
            await self._proposal_blocked(
                symbol,
                market,
                "payout_too_low",
                {"payout_rate": proposal.payout_rate, "minimum": self.settings.deriv_min_payout_rate},
            )
            analysis["blocked_reason"] = "payout_too_low"
            return analysis

        signal = Signal(
            asset=symbol,
            display_name=market.get("display_name"),
            market=str(market.get("market") or ""),
            direction=direction,
            contract_type=contract_type,
            duration=duration,
            duration_unit=duration_unit,
            timeframe=self.settings.default_timeframe,
            score=int(learning_decision["adjusted_score"]),
            factor_score=factor_score,
            stake=self.virtual_account.state.stake,
            reason=reason,
        )
        await self.store.upsert_signal(signal)
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.SIGNAL_DECIDED,
                idempotency_key=f"signal_decided:{signal.signal_id}",
                asset=signal.asset,
                market=signal.market,
                payload={**signal.model_dump(mode="json"), "learning_decision": learning_decision},
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.LEARNING_FILTER_ALLOWED,
                idempotency_key=f"learning_filter_allowed:{signal.signal_id}",
                asset=signal.asset,
                market=signal.market,
                payload=learning_decision,
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.PROPOSAL_RECEIVED,
                idempotency_key=f"proposal_received:{signal.signal_id}:{proposal.proposal_id}",
                asset=signal.asset,
                market=signal.market,
                payload={
                    "proposal_id": proposal.proposal_id,
                    "ask_price": proposal.ask_price,
                    "payout": proposal.payout,
                    "payout_rate": proposal.payout_rate,
                    "spot": proposal.spot,
                    "spot_time": proposal.spot_time,
                    "date_expiry": proposal.date_expiry,
                    "longcode": proposal.longcode,
                },
            )
        )
        entry_epoch = int(proposal.spot_time or latest.epoch)
        expiry_epoch = int(proposal.date_expiry or entry_epoch + _duration_seconds(duration, duration_unit))
        bankruptcies_before_open = self.virtual_account.state.bankruptcies
        balance_before_open = self.virtual_account.state.balance
        await self.virtual_account.open_trade(
            signal=signal,
            payout=proposal.payout,
            payout_rate=proposal.payout_rate,
            entry_spot=float(proposal.spot or latest.close),
            entry_epoch=entry_epoch,
            expiry_epoch=expiry_epoch,
        )
        if self.virtual_account.state.bankruptcies > bankruptcies_before_open:
            await self.telegram.project_account_reset_alert(
                reason="insufficient_virtual_balance",
                account=self.virtual_account.state,
                balance_before_reset=balance_before_open,
                triggering_signal_id=signal.signal_id,
            )
        self.last_signal_epoch[symbol] = int(datetime.now(UTC).timestamp())
        await self.telegram.project_signal(signal, proposal_status="virtual_trade_opened")
        if self.broker_trading_enabled:
            await self.store.append_event(
                TradeEvent(
                    signal_id=signal.signal_id,
                    event_type=TradeEventType.BROKER_TRADING_REJECTED,
                    idempotency_key=f"broker_rejected_missing_auth:{signal.signal_id}",
                    asset=signal.asset,
                    market=signal.market,
                    payload={"reason": "authenticated_deriv_buy_not_configured"},
                )
            )
        analysis["signal_created"] = True
        analysis["signal_id"] = signal.signal_id
        return analysis

    async def _open_learning_shadow_trade(
        self,
        *,
        signal: Signal,
        entry_spot: float,
        entry_epoch: int,
        expiry_epoch: int,
        learning_decision: dict[str, Any],
    ) -> VirtualTrade:
        payout_rate = self.settings.virtual_payout_rate
        trade = VirtualTrade(
            signal_id=signal.signal_id,
            asset=signal.asset,
            market=signal.market,
            direction=signal.direction,
            contract_type=signal.contract_type,
            stake=signal.stake,
            payout=round(signal.stake * (1 + payout_rate), 8),
            payout_rate=payout_rate,
            entry_spot=entry_spot,
            entry_epoch=entry_epoch,
            expiry_epoch=expiry_epoch,
            status=VirtualTradeStatus.SHADOW_OPEN,
            resolution_source="learning_shadow_tick_replay",
            shadow_reason="learning_filter",
            learning_decision=learning_decision,
        )
        await self.store.upsert_virtual_trade(trade)
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.LEARNING_SHADOW_OPENED,
                idempotency_key=f"learning_shadow_opened:{signal.signal_id}",
                asset=signal.asset,
                market=signal.market,
                payload={"trade": trade.model_dump(mode="json"), "learning_decision": learning_decision},
            )
        )
        return trade

    async def _proposal_blocked(
        self,
        symbol: str,
        market: dict[str, Any],
        reason: str,
        payload: dict[str, Any],
    ) -> None:
        event_type = TradeEventType.PAYOUT_TOO_LOW if reason == "payout_too_low" else TradeEventType.PROPOSAL_REJECTED
        await self.store.append_event(
            TradeEvent(
                event_type=event_type,
                idempotency_key=f"{event_type}:{symbol}:{reason}:{datetime.now(UTC).isoformat()}",
                asset=symbol,
                market=str(market.get("market") or ""),
                payload={"reason": reason, **payload},
            )
        )

    def _cooldown_active(self, symbol: str) -> bool:
        last = self.last_signal_epoch.get(symbol)
        if not last:
            return False
        now = int(datetime.now(UTC).timestamp())
        return now - last < self.settings.signal_cooldown_seconds

    def _virtual_capacity_block(self, symbol: str) -> str | None:
        open_trades = [
            VirtualTrade.model_validate(row)
            for row in self.local_store.read_virtual_trades(limit=1000)
            if row.get("status") == VirtualTradeStatus.OPEN
        ]
        if any(trade.asset == symbol for trade in open_trades):
            return "open_trade_exists"
        if len(open_trades) >= self.settings.virtual_max_concurrent_trades:
            return "max_virtual_concurrent_trades"
        return None

    def _hydrate_cooldowns(self) -> None:
        for row in self.local_store.read_signals(limit=1000):
            asset = row.get("asset")
            created_at = row.get("created_at")
            if not asset or not created_at:
                continue
            try:
                created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            current = self.last_signal_epoch.get(str(asset), 0)
            self.last_signal_epoch[str(asset)] = max(current, int(created.timestamp()))

    async def settle_due_virtual_trades(self) -> list[VirtualTrade]:
        now_epoch = int(datetime.now(UTC).timestamp())
        rows = self.local_store.read_virtual_trades(limit=500)
        settled: list[VirtualTrade] = []
        for row in rows:
            trade = VirtualTrade.model_validate(row)
            if trade.status not in {VirtualTradeStatus.OPEN, VirtualTradeStatus.SHADOW_OPEN} or trade.expiry_epoch > now_epoch:
                continue
            exit_spot = await self._exit_spot(trade.asset, trade.expiry_epoch)
            outcome = resolve_strict_rise_fall(trade.direction, trade.entry_spot, exit_spot)
            if trade.status == VirtualTradeStatus.SHADOW_OPEN:
                trade.status = VirtualTradeStatus.SHADOW_SETTLED
                trade.outcome = outcome
                trade.exit_spot = exit_spot
                trade.settled_at = datetime.now(UTC)
                await self.store.upsert_virtual_trade(trade)
                await self.store.append_event(
                    TradeEvent(
                        signal_id=trade.signal_id,
                        event_type=TradeEventType.LEARNING_SHADOW_SETTLED,
                        idempotency_key=f"learning_shadow_settled:{trade.signal_id}",
                        asset=trade.asset,
                        market=trade.market,
                        payload={"trade": trade.model_dump(mode="json")},
                    )
                )
                settled.append(trade)
                continue
            target_hits_before = self.virtual_account.state.target_hits
            bankruptcies_before = self.virtual_account.state.bankruptcies
            balance_before_settle = self.virtual_account.state.balance
            balance_after_result = (
                round(balance_before_settle + trade.payout, 8)
                if outcome == Outcome.WIN
                else balance_before_settle
            )
            settled_trade = await self.virtual_account.settle_trade(trade, outcome=outcome, exit_spot=exit_spot)
            await self.telegram.project_virtual_result(
                settled_trade,
                balance_after=balance_after_result,
            )
            if self.virtual_account.state.target_hits > target_hits_before:
                await self.telegram.project_account_reset_alert(
                    reason="target_reached",
                    account=self.virtual_account.state,
                    balance_before_reset=balance_after_result,
                    triggering_signal_id=trade.signal_id,
                )
            elif self.virtual_account.state.bankruptcies > bankruptcies_before:
                await self.telegram.project_account_reset_alert(
                    reason="bankruptcy",
                    account=self.virtual_account.state,
                    balance_before_reset=balance_after_result,
                    triggering_signal_id=trade.signal_id,
                )
            await self.learning.rebuild_from_virtual_trades()
            await self._maybe_send_five_trade_summary()
            settled.append(settled_trade)
        return settled

    async def _maybe_send_five_trade_summary(self) -> None:
        settled = [
            VirtualTrade.model_validate(row)
            for row in self.local_store.read_virtual_trades(limit=1000)
            if row.get("status") == VirtualTradeStatus.SETTLED
        ]
        settled.sort(key=lambda trade: trade.settled_at or datetime.min.replace(tzinfo=UTC))
        if not settled or len(settled) % self.settings.telegram_summary_batch_size != 0:
            return
        batch_number = len(settled) // self.settings.telegram_summary_batch_size
        summary_id = f"summary_batch_{batch_number}"
        already_sent = any(
            row.get("signal_id") == summary_id and row.get("message_type") == "summary_5"
            for row in self.local_store.read_telegram_events(limit=1000)
        )
        if already_sent:
            return
        await self.telegram.project_five_trade_summary(
            batch_number=batch_number,
            trades=settled[-self.settings.telegram_summary_batch_size :],
            balance_after=self.virtual_account.state.balance,
        )

    async def _exit_spot(self, symbol: str, expiry_epoch: int) -> float:
        result = await self.client.request(
            {
                "ticks_history": symbol,
                "style": "ticks",
                "end": expiry_epoch,
                "count": 1,
            }
        )
        history = result.response.get("history") or {}
        prices = history.get("prices") or []
        if not prices:
            candles = self.candles_by_symbol.get(symbol) or []
            if candles:
                return candles[-1].close
            raise RuntimeError("exit_spot_unavailable")
        return float(prices[-1])

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "last_scan_at": self.last_scan_at.isoformat() if self.last_scan_at else None,
            "last_error": self.last_error,
            "last_cycle": self.last_cycle,
            "broker_trading_enabled": self.broker_trading_enabled,
            "markets_with_candles": sorted(self.candles_by_symbol),
        }


def _duration_seconds(duration: int, unit: str) -> int:
    return int(duration) * {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 60)
