from __future__ import annotations

import json
import asyncio
from pathlib import Path

from app.config import Settings
from app.event_store import EventSink
from app.models import (
    Outcome,
    Signal,
    TradeEvent,
    TradeEventType,
    VirtualAccountState,
    VirtualTrade,
    VirtualTradeStatus,
    utc_now,
)


class VirtualAccountService:
    def __init__(self, settings: Settings, store: EventSink):
        self.settings = settings
        self.store = store
        self.path = settings.data_dir / "virtual_account.json"
        self.state = self._load()
        self._lock = asyncio.Lock()

    def _load(self) -> VirtualAccountState:
        if self.path.exists():
            try:
                return VirtualAccountState.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return VirtualAccountState(
            balance=self.settings.virtual_initial_balance,
            initial_balance=self.settings.virtual_initial_balance,
            target_balance=self.settings.virtual_target_balance,
            stake=self.settings.virtual_safe_stake,
            currency=self.settings.deriv_currency,
        )

    def _save(self) -> None:
        self.state.updated_at = utc_now()
        self.path.write_text(self.state.model_dump_json(indent=2), encoding="utf-8")

    async def configure(
        self,
        *,
        initial_balance: float | None = None,
        balance: float | None = None,
        stake: float | None = None,
        target_balance: float | None = None,
    ) -> VirtualAccountState:
        async with self._lock:
            if initial_balance is not None:
                self.state.initial_balance = max(0.01, float(initial_balance))
            if balance is not None:
                self.state.balance = max(0.0, float(balance))
            elif initial_balance is not None:
                self.state.balance = self.state.initial_balance
            if stake is not None:
                self.state.stake = max(0.01, float(stake))
            if target_balance is not None:
                self.state.target_balance = max(self.state.initial_balance, float(target_balance))
            self._save()
        await self.store.append_event(
            TradeEvent(
                event_type=TradeEventType.VIRTUAL_ACCOUNT_CONFIGURED,
                idempotency_key=f"virtual_account_configured:{self.state.updated_at.isoformat()}",
                payload=self.state.model_dump(mode="json"),
            )
        )
        return self.state

    async def ensure_funds(self) -> None:
        if self.state.balance >= self.state.stake:
            return
        await self.reset("insufficient_virtual_balance")

    async def reset(self, reason: str) -> VirtualAccountState:
        async with self._lock:
            self.state.balance = self.state.initial_balance
            self.state.resets += 1
            if reason in {"insufficient_virtual_balance", "bankruptcy"}:
                self.state.bankruptcies += 1
            if reason == "target_reached":
                self.state.target_hits += 1
            self._save()
        await self.store.append_event(
            TradeEvent(
                event_type=TradeEventType.VIRTUAL_ACCOUNT_RESET,
                idempotency_key=f"virtual_account_reset:{reason}:{self.state.resets}",
                payload={"reason": reason, **self.state.model_dump(mode="json")},
            )
        )
        return self.state

    async def open_trade(
        self,
        *,
        signal: Signal,
        payout: float,
        payout_rate: float,
        entry_spot: float,
        entry_epoch: int,
        expiry_epoch: int,
        broker_contract_id: str | None = None,
    ) -> VirtualTrade:
        async with self._lock:
            if self.state.balance < self.state.stake:
                self.state.balance = self.state.initial_balance
                self.state.resets += 1
                self.state.bankruptcies += 1
            self.state.balance = round(self.state.balance - self.state.stake, 8)
            self._save()
        trade = VirtualTrade(
            signal_id=signal.signal_id,
            asset=signal.asset,
            market=signal.market,
            direction=signal.direction,
            contract_type=signal.contract_type,
            stake=self.state.stake,
            payout=payout,
            payout_rate=payout_rate,
            entry_spot=entry_spot,
            entry_epoch=entry_epoch,
            expiry_epoch=expiry_epoch,
            broker_contract_id=broker_contract_id,
        )
        await self.store.upsert_virtual_trade(trade)
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.VIRTUAL_TRADE_OPENED,
                idempotency_key=f"virtual_trade_opened:{signal.signal_id}",
                asset=signal.asset,
                market=signal.market,
                payload={
                    "trade": trade.model_dump(mode="json"),
                    "virtual_balance_after_open": self.state.balance,
                },
            )
        )
        return trade

    async def settle_trade(self, trade: VirtualTrade, *, outcome: Outcome, exit_spot: float) -> VirtualTrade:
        if trade.status != VirtualTradeStatus.OPEN:
            return trade
        trade.status = VirtualTradeStatus.SETTLED
        trade.outcome = outcome
        trade.exit_spot = exit_spot
        trade.settled_at = utc_now()
        async with self._lock:
            if outcome == Outcome.WIN:
                self.state.balance = round(self.state.balance + trade.payout, 8)
            self._save()
        await self.store.upsert_virtual_trade(trade)
        await self.store.append_event(
            TradeEvent(
                signal_id=trade.signal_id,
                event_type=TradeEventType.VIRTUAL_TRADE_SETTLED,
                idempotency_key=f"virtual_trade_settled:{trade.signal_id}",
                asset=trade.asset,
                market=trade.market,
                payload={
                    "trade": trade.model_dump(mode="json"),
                    "virtual_balance_after_settle": self.state.balance,
                },
            )
        )
        if self.state.balance >= self.state.target_balance:
            await self.reset("target_reached")
        elif self.state.balance < self.state.stake:
            await self.reset("bankruptcy")
        return trade


def read_virtual_account(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
