from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.event_store import EventSink, LocalJsonlEventStore
from app.models import Outcome, TradeEvent, TradeEventType


def _empty_rule() -> dict[str, Any]:
    return {
        "samples": 0,
        "wins": 0,
        "losses": 0,
        "equal_losses": 0,
        "net_profit": 0.0,
        "win_rate": 0.0,
        "avg_profit": 0.0,
        "last_signal_id": None,
    }


class LearningService:
    """Compact learning projection from settled Deriv virtual/real outcomes."""

    def __init__(self, settings: Settings, local_store: LocalJsonlEventStore, event_store: EventSink):
        self.settings = settings
        self.local_store = local_store
        self.event_store = event_store
        self.path = settings.data_dir / "deriv_learning.json"

    async def rebuild_from_virtual_trades(self) -> dict[str, Any]:
        signals = {row.get("signal_id"): row for row in self.local_store.read_signals(limit=5000)}
        latest_trades: dict[str, dict[str, Any]] = {}
        for row in self.local_store.read_virtual_trades(limit=5000):
            signal_id = row.get("signal_id")
            if signal_id:
                latest_trades[str(signal_id)] = row

        rules: dict[str, dict[str, Any]] = defaultdict(_empty_rule)
        settled_count = 0
        for trade in latest_trades.values():
            if trade.get("status") != "settled" or not trade.get("outcome"):
                continue
            signal = signals.get(trade.get("signal_id"), {})
            profit = trade_profit_from_row(trade)
            keys = learning_keys(trade, signal)
            for key in keys:
                update_rule(rules[key], trade, profit)
            settled_count += 1

        payload = {
            "version": 1,
            "source": "deriv_virtual_outcomes",
            "updated_at": datetime.now(UTC).isoformat(),
            "settled_samples": settled_count,
            "rules": dict(sorted(rules.items())),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        await self.event_store.append_event(
            TradeEvent(
                event_type=TradeEventType.LEARNING_UPDATED,
                idempotency_key=f"learning_updated:{payload['updated_at']}",
                payload={
                    "source": payload["source"],
                    "settled_samples": settled_count,
                    "rule_count": len(rules),
                },
            )
        )
        return payload

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": 1,
                "source": "deriv_virtual_outcomes",
                "updated_at": None,
                "settled_samples": 0,
                "rules": {},
            }
        return json.loads(self.path.read_text(encoding="utf-8"))


def learning_keys(trade: dict[str, Any], signal: dict[str, Any]) -> list[str]:
    asset = str(trade.get("asset") or "unknown")
    direction = str(trade.get("direction") or "unknown")
    contract_type = str(trade.get("contract_type") or "unknown")
    reason = str(signal.get("reason") or "unknown_reason")
    score = int(signal.get("score") or 0)
    factor_score = int(signal.get("factor_score") or 0)
    score_band = f"{(score // 2) * 2}-{((score // 2) * 2) + 1}"
    return [
        "global",
        f"asset:{asset}",
        f"direction:{direction}",
        f"asset_direction:{asset}:{direction}",
        f"contract:{contract_type}",
        f"reason:{reason}",
        f"score_band:{score_band}",
        f"factor_score:{factor_score}",
        f"asset_reason:{asset}:{reason}",
    ]


def update_rule(rule: dict[str, Any], trade: dict[str, Any], profit: float) -> None:
    outcome = trade.get("outcome")
    rule["samples"] += 1
    if outcome == Outcome.WIN or outcome == Outcome.WIN.value:
        rule["wins"] += 1
    elif outcome == Outcome.EQUAL_LOSS or outcome == Outcome.EQUAL_LOSS.value:
        rule["equal_losses"] += 1
        rule["losses"] += 1
    else:
        rule["losses"] += 1
    rule["net_profit"] = round(float(rule["net_profit"]) + profit, 8)
    rule["win_rate"] = round((rule["wins"] / rule["samples"]) * 100, 2) if rule["samples"] else 0.0
    rule["avg_profit"] = round(rule["net_profit"] / rule["samples"], 8) if rule["samples"] else 0.0
    rule["last_signal_id"] = trade.get("signal_id")


def trade_profit_from_row(trade: dict[str, Any]) -> float:
    stake = float(trade.get("stake") or 0)
    payout = float(trade.get("payout") or 0)
    outcome = trade.get("outcome")
    if outcome == Outcome.WIN or outcome == Outcome.WIN.value:
        return round(payout - stake, 8)
    if outcome in {Outcome.LOSS, Outcome.LOSS.value, Outcome.EQUAL_LOSS, Outcome.EQUAL_LOSS.value}:
        return round(-stake, 8)
    return 0.0
