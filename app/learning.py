from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.event_store import EventSink, LocalJsonlEventStore
from app.models import Outcome, TradeEvent, TradeEventType, VirtualTradeStatus


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

    def evaluate_signal(
        self,
        *,
        asset: str,
        direction: str,
        contract_type: str,
        reason: str | None,
        score: int,
        factor_score: int,
    ) -> dict[str, Any]:
        base_score = max(1, min(10, int(score or 0)))
        if not self.settings.learning_filter_enabled:
            return self._decision(
                action="allow",
                verdict="disabled",
                reason="learning_filter_disabled",
                base_score=base_score,
                score_delta=0,
            )

        learning = self.read()
        rules = learning.get("rules") or {}
        settled_samples = int(learning.get("settled_samples") or rules.get("global", {}).get("samples") or 0)
        keys = learning_keys_from_values(
            asset=asset,
            direction=direction,
            contract_type=contract_type,
            reason=reason,
            score=score,
            factor_score=factor_score,
        )
        if settled_samples < self.settings.learning_warmup_samples:
            return self._decision(
                action="allow",
                verdict="observe",
                reason="learning_warmup",
                base_score=base_score,
                score_delta=0,
                settled_samples=settled_samples,
                required_samples=self.settings.learning_warmup_samples,
                keys=keys,
            )

        bad_weight = 0.0
        critical_bad_weight = 0.0
        good_weight = 0.0
        eligible_rules = 0
        evaluated_rules: list[dict[str, Any]] = []

        for key in keys:
            rule = rules.get(key)
            if not rule:
                evaluated_rules.append({"key": key, "verdict": "missing", "weight": self._rule_weight(key)})
                continue
            samples = int(rule.get("samples") or 0)
            weight = self._rule_weight(key)
            row = {
                "key": key,
                "samples": samples,
                "wins": int(rule.get("wins") or 0),
                "losses": int(rule.get("losses") or 0),
                "win_rate": float(rule.get("win_rate") or 0.0),
                "net_profit": float(rule.get("net_profit") or 0.0),
                "avg_profit": float(rule.get("avg_profit") or 0.0),
                "weight": weight,
            }
            if samples < self.settings.learning_min_rule_samples:
                row["verdict"] = "insufficient_samples"
                evaluated_rules.append(row)
                continue

            eligible_rules += 1
            is_bad = (
                row["win_rate"] < self.settings.learning_block_win_rate_below
                and row["avg_profit"] < self.settings.learning_block_avg_profit_below
                and row["net_profit"] < self.settings.learning_block_net_profit_below
            )
            is_critical_bad = (
                samples >= self.settings.learning_strong_rule_samples
                and row["win_rate"] < self.settings.learning_critical_win_rate_below
                and row["avg_profit"] < self.settings.learning_block_avg_profit_below
                and row["net_profit"] < self.settings.learning_block_net_profit_below
            )
            is_good = (
                row["win_rate"] >= self.settings.learning_allow_win_rate_at_least
                and row["avg_profit"] > self.settings.learning_allow_min_avg_profit
                and row["net_profit"] > 0
            )

            if is_critical_bad:
                critical_bad_weight = round(critical_bad_weight + weight, 4)
                bad_weight = round(bad_weight + weight, 4)
                row["verdict"] = "critical_bad"
            elif is_bad:
                bad_weight = round(bad_weight + weight, 4)
                row["verdict"] = "bad"
            elif is_good:
                good_weight = round(good_weight + weight, 4)
                row["verdict"] = "good"
            else:
                row["verdict"] = "neutral"
            evaluated_rules.append(row)

        if eligible_rules == 0:
            return self._decision(
                action="allow",
                verdict="observe",
                reason="no_learning_rules_with_enough_samples",
                base_score=base_score,
                score_delta=0,
                settled_samples=settled_samples,
                keys=keys,
                evaluated_rules=evaluated_rules,
            )

        should_block = (
            critical_bad_weight >= self.settings.learning_critical_bad_weight
            or bad_weight >= self.settings.learning_block_bad_weight
        ) and good_weight < self.settings.learning_allow_good_weight
        if should_block:
            return self._decision(
                action="block",
                verdict="blocked",
                reason="negative_learning_edge",
                base_score=base_score,
                score_delta=-abs(self.settings.learning_score_penalty),
                settled_samples=settled_samples,
                keys=keys,
                evaluated_rules=evaluated_rules,
                bad_weight=bad_weight,
                critical_bad_weight=critical_bad_weight,
                good_weight=good_weight,
            )

        if good_weight >= self.settings.learning_allow_good_weight and bad_weight < self.settings.learning_warning_bad_weight:
            return self._decision(
                action="allow",
                verdict="favored",
                reason="positive_learning_edge",
                base_score=base_score,
                score_delta=abs(self.settings.learning_score_boost),
                settled_samples=settled_samples,
                keys=keys,
                evaluated_rules=evaluated_rules,
                bad_weight=bad_weight,
                critical_bad_weight=critical_bad_weight,
                good_weight=good_weight,
            )

        if bad_weight >= self.settings.learning_warning_bad_weight:
            return self._decision(
                action="allow",
                verdict="caution",
                reason="weak_negative_learning_edge",
                base_score=base_score,
                score_delta=-abs(self.settings.learning_score_penalty),
                settled_samples=settled_samples,
                keys=keys,
                evaluated_rules=evaluated_rules,
                bad_weight=bad_weight,
                critical_bad_weight=critical_bad_weight,
                good_weight=good_weight,
            )

        return self._decision(
            action="allow",
            verdict="neutral",
            reason="learning_rules_neutral",
            base_score=base_score,
            score_delta=0,
            settled_samples=settled_samples,
            keys=keys,
            evaluated_rules=evaluated_rules,
            bad_weight=bad_weight,
            critical_bad_weight=critical_bad_weight,
            good_weight=good_weight,
        )

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

    def summary(self) -> dict[str, Any]:
        learning = self.read()
        rules = learning.get("rules") or {}
        trades = self.local_store.read_virtual_trades(limit=5000)
        events = self.local_store.read_events(limit=5000)
        main_open = [row for row in trades if row.get("status") == VirtualTradeStatus.OPEN]
        main_settled = [
            row
            for row in trades
            if row.get("status") == VirtualTradeStatus.SETTLED and row.get("outcome")
        ]
        shadow_open = [row for row in trades if row.get("status") == VirtualTradeStatus.SHADOW_OPEN]
        shadow_settled = [
            row
            for row in trades
            if row.get("status") == VirtualTradeStatus.SHADOW_SETTLED and row.get("outcome")
        ]
        allowed = _count_events(events, TradeEventType.LEARNING_FILTER_ALLOWED)
        blocked = _count_events(events, TradeEventType.LEARNING_FILTER_BLOCKED)
        shadow_opened = _count_events(events, TradeEventType.LEARNING_SHADOW_OPENED)
        shadow_closed = _count_events(events, TradeEventType.LEARNING_SHADOW_SETTLED)
        decisions_total = allowed + blocked
        return {
            "updated_at": learning.get("updated_at"),
            "settled_samples": int(learning.get("settled_samples") or 0),
            "rules_count": len(rules),
            "global_rule": rules.get("global") or _empty_rule(),
            "operations": {
                **_outcome_metrics(main_settled),
                "open": len(main_open),
            },
            "learning_decisions": {
                "total": decisions_total,
                "allowed": allowed,
                "blocked": blocked,
                "block_rate": round((blocked / decisions_total) * 100, 2) if decisions_total else 0.0,
            },
            "shadows": {
                **_outcome_metrics(shadow_settled),
                "open": len(shadow_open),
                "opened_by_learning_block": shadow_opened,
                "settled_by_learning_block": shadow_closed,
            },
            "config": self.filter_config(),
        }

    def filter_config(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.learning_filter_enabled,
            "shadow_enabled": self.settings.learning_shadow_enabled,
            "warmup_samples": self.settings.learning_warmup_samples,
            "min_rule_samples": self.settings.learning_min_rule_samples,
            "strong_rule_samples": self.settings.learning_strong_rule_samples,
            "block_win_rate_below": self.settings.learning_block_win_rate_below,
            "block_avg_profit_below": self.settings.learning_block_avg_profit_below,
            "block_net_profit_below": self.settings.learning_block_net_profit_below,
            "block_bad_weight": self.settings.learning_block_bad_weight,
            "critical_win_rate_below": self.settings.learning_critical_win_rate_below,
            "critical_bad_weight": self.settings.learning_critical_bad_weight,
            "allow_win_rate_at_least": self.settings.learning_allow_win_rate_at_least,
            "allow_min_avg_profit": self.settings.learning_allow_min_avg_profit,
            "allow_good_weight": self.settings.learning_allow_good_weight,
            "warning_bad_weight": self.settings.learning_warning_bad_weight,
            "score_boost": self.settings.learning_score_boost,
            "score_penalty": self.settings.learning_score_penalty,
            "weights": {
                "global": self.settings.learning_weight_global,
                "asset": self.settings.learning_weight_asset,
                "direction": self.settings.learning_weight_direction,
                "asset_direction": self.settings.learning_weight_asset_direction,
                "contract": self.settings.learning_weight_contract,
                "reason": self.settings.learning_weight_reason,
                "score_band": self.settings.learning_weight_score_band,
                "factor_score": self.settings.learning_weight_factor_score,
                "asset_reason": self.settings.learning_weight_asset_reason,
            },
        }

    def _rule_weight(self, key: str) -> float:
        family = key.split(":", 1)[0]
        return float(
            {
                "global": self.settings.learning_weight_global,
                "asset": self.settings.learning_weight_asset,
                "direction": self.settings.learning_weight_direction,
                "asset_direction": self.settings.learning_weight_asset_direction,
                "contract": self.settings.learning_weight_contract,
                "reason": self.settings.learning_weight_reason,
                "score_band": self.settings.learning_weight_score_band,
                "factor_score": self.settings.learning_weight_factor_score,
                "asset_reason": self.settings.learning_weight_asset_reason,
            }.get(family, 0.5)
        )

    @staticmethod
    def _decision(
        *,
        action: str,
        verdict: str,
        reason: str,
        base_score: int,
        score_delta: int,
        **payload: Any,
    ) -> dict[str, Any]:
        adjusted_score = max(1, min(10, base_score + int(score_delta)))
        evaluated_rules = payload.pop("evaluated_rules", [])
        ranked_rules = sorted(
            evaluated_rules,
            key=lambda row: (row.get("verdict") not in {"critical_bad", "bad", "good"}, -float(row.get("weight") or 0)),
        )
        return {
            "action": action,
            "verdict": verdict,
            "reason": reason,
            "base_score": base_score,
            "score_delta": int(score_delta),
            "adjusted_score": adjusted_score,
            "evaluated_rules": ranked_rules[:12],
            **payload,
        }


def learning_keys(trade: dict[str, Any], signal: dict[str, Any]) -> list[str]:
    asset = str(trade.get("asset") or "unknown")
    direction = str(trade.get("direction") or "unknown")
    contract_type = str(trade.get("contract_type") or "unknown")
    reason = str(signal.get("reason") or "unknown_reason")
    score = int(signal.get("score") or 0)
    factor_score = int(signal.get("factor_score") or 0)
    return learning_keys_from_values(
        asset=asset,
        direction=direction,
        contract_type=contract_type,
        reason=reason,
        score=score,
        factor_score=factor_score,
    )


def learning_keys_from_values(
    *,
    asset: str,
    direction: str,
    contract_type: str,
    reason: str | None,
    score: int,
    factor_score: int,
) -> list[str]:
    score_band = f"{(score // 2) * 2}-{((score // 2) * 2) + 1}"
    reason_key = str(reason or "unknown_reason")
    return [
        "global",
        f"asset:{asset}",
        f"direction:{direction}",
        f"asset_direction:{asset}:{direction}",
        f"contract:{contract_type}",
        f"reason:{reason_key}",
        f"score_band:{score_band}",
        f"factor_score:{factor_score}",
        f"asset_reason:{asset}:{reason_key}",
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


def _outcome_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for row in rows if row.get("outcome") in {Outcome.WIN, Outcome.WIN.value})
    losses = sum(
        1
        for row in rows
        if row.get("outcome") in {Outcome.LOSS, Outcome.LOSS.value, Outcome.EQUAL_LOSS, Outcome.EQUAL_LOSS.value}
    )
    total = wins + losses
    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / total) * 100, 2) if total else 0.0,
    }


def _count_events(events: list[dict[str, Any]], event_type: TradeEventType) -> int:
    return sum(1 for event in events if event.get("event_type") == event_type.value)
