from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from app.models import BrokerOrder, DerivSymbol, Signal, TelegramEvent, TradeEvent, VirtualTrade


class EventSink(Protocol):
    async def append_event(self, event: TradeEvent) -> TradeEvent:
        ...

    async def upsert_signal(self, signal: Signal) -> Signal:
        ...

    async def upsert_broker_order(self, order: BrokerOrder) -> BrokerOrder:
        ...

    async def upsert_market(self, market: DerivSymbol) -> DerivSymbol:
        ...

    async def upsert_telegram_event(self, event: TelegramEvent) -> TelegramEvent:
        ...

    async def upsert_virtual_trade(self, trade: VirtualTrade) -> VirtualTrade:
        ...


class LocalJsonlEventStore:
    """Durable local event queue and compact projections for offline/dev operation."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = self.data_dir / "deriv_trade_events.jsonl"
        self.signals_file = self.data_dir / "deriv_signals.jsonl"
        self.orders_file = self.data_dir / "deriv_broker_orders.jsonl"
        self.markets_file = self.data_dir / "deriv_market_catalog.jsonl"
        self.telegram_file = self.data_dir / "deriv_telegram_events.jsonl"
        self.virtual_trades_file = self.data_dir / "deriv_virtual_trades.jsonl"
        self._event_keys: set[str] = self._load_keys(self.events_file, "idempotency_key")
        self._signal_keys: set[str] = self._load_keys(self.signals_file, "signal_id")
        self._order_keys: set[str] = self._load_keys(self.orders_file, "signal_id")
        self._market_keys: set[str] = self._load_keys(self.markets_file, "symbol")
        self._telegram_keys: set[str] = self._load_composite_keys(self.telegram_file, ["signal_id", "message_type"])
        self._virtual_trade_keys: set[str] = self._load_keys(self.virtual_trades_file, "signal_id")

    @staticmethod
    def _load_keys(path: Path, field: str) -> set[str]:
        if not path.exists():
            return set()
        keys: set[str] = set()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                value = payload.get(field)
                if value is not None:
                    keys.add(str(value))
        return keys

    @staticmethod
    def _load_composite_keys(path: Path, fields: list[str]) -> set[str]:
        if not path.exists():
            return set()
        keys: set[str] = set()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                keys.add(":".join(str(payload.get(field, "")) for field in fields))
        return keys

    @staticmethod
    def _append(path: Path, payload: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")

    async def append_event(self, event: TradeEvent) -> TradeEvent:
        if event.idempotency_key not in self._event_keys:
            self._append(self.events_file, event.model_dump(mode="json"))
            self._event_keys.add(event.idempotency_key)
        return event

    async def upsert_signal(self, signal: Signal) -> Signal:
        if signal.signal_id not in self._signal_keys:
            self._append(self.signals_file, signal.model_dump(mode="json"))
            self._signal_keys.add(signal.signal_id)
        return signal

    async def upsert_broker_order(self, order: BrokerOrder) -> BrokerOrder:
        if order.signal_id not in self._order_keys:
            self._append(self.orders_file, order.model_dump(mode="json"))
            self._order_keys.add(order.signal_id)
        return order

    async def upsert_market(self, market: DerivSymbol) -> DerivSymbol:
        if market.symbol not in self._market_keys:
            self._append(self.markets_file, market.model_dump(mode="json"))
            self._market_keys.add(market.symbol)
        return market

    async def upsert_telegram_event(self, event: TelegramEvent) -> TelegramEvent:
        key = f"{event.signal_id}:{event.message_type}"
        if key not in self._telegram_keys:
            self._append(self.telegram_file, event.model_dump(mode="json"))
            self._telegram_keys.add(key)
        return event

    async def upsert_virtual_trade(self, trade: VirtualTrade) -> VirtualTrade:
        # Append-only projection. Later rows with the same signal_id supersede older rows when read.
        self._append(self.virtual_trades_file, trade.model_dump(mode="json"))
        self._virtual_trade_keys.add(trade.signal_id)
        return trade

    def read_events(self, signal_id: str | None = None, limit: int = 500) -> list[dict]:
        return self._read_jsonl(self.events_file, signal_id=signal_id, limit=limit)

    def read_signals(self, limit: int = 500) -> list[dict]:
        return self._read_jsonl(self.signals_file, limit=limit)

    def read_markets(self, limit: int = 500) -> list[dict]:
        return self._read_jsonl(self.markets_file, limit=limit)

    def read_virtual_trades(self, limit: int = 500) -> list[dict]:
        rows = self._read_jsonl(self.virtual_trades_file, limit=5000)
        latest: dict[str, dict] = {}
        for row in rows:
            signal_id = row.get("signal_id")
            if signal_id:
                latest[str(signal_id)] = row
        return list(latest.values())[-limit:]

    def read_telegram_events(self, limit: int = 500) -> list[dict]:
        return self._read_jsonl(self.telegram_file, limit=limit)

    @staticmethod
    def _read_jsonl(path: Path, signal_id: str | None = None, limit: int = 500) -> list[dict]:
        if not path.exists():
            return []
        rows: list[dict] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if signal_id and payload.get("signal_id") != signal_id:
                    continue
                rows.append(payload)
        return rows[-limit:]
