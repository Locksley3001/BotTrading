from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.event_store import EventSink
from app.models import Outcome, Signal, TelegramEvent, TradeEvent, TradeEventType, VirtualAccountState, VirtualTrade
from app.security import stable_hash


class TelegramNotifier:
    def __init__(self, settings: Settings, store: EventSink):
        self.settings = settings
        self.store = store

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def send_test_message(self) -> dict[str, object]:
        text = f"🧪 Deriv bot smoke test\n⏱️ {datetime.now(UTC).isoformat()}"
        return await self._send_text(text)

    async def project_signal(self, signal: Signal, proposal_status: str = "proposal_received") -> None:
        if not self.settings.telegram_enabled or not self.configured:
            return
        if signal.score < self.settings.telegram_min_score:
            return
        market_name = signal.display_name or format_market_name(signal.asset)
        direction_icon = "🟢⬆️" if signal.direction.value == "RISE" else "🔴⬇️"
        text = (
            f"🚀 Nueva operación virtual Deriv ({self.settings.deriv_account_mode})\n\n"
            f"🆔 Signal ID: {signal.signal_id}\n"
            f"📊 Mercado: {market_name} ({signal.asset})\n"
            f"🎯 Dirección: {direction_icon} {signal.direction.value}\n"
            f"🧾 Contrato Deriv: {signal.contract_type}\n"
            f"⏱️ Duración: {signal.duration}{signal.duration_unit}\n"
            f"💵 Stake: {signal.stake:.2f} {self.settings.deriv_currency}\n"
            f"⭐ Score: {signal.score}/10 | Factor: {signal.factor_score}\n"
            f"📌 Estado: {proposal_status}"
        )
        result = await self._send_text(text)
        await self.store.upsert_telegram_event(
            TelegramEvent(
                signal_id=signal.signal_id,
                message_type="signal",
                chat_id_hash=stable_hash(self.settings.telegram_chat_id.get_secret_value() if self.settings.telegram_chat_id else ""),
                telegram_message_id=str(result.get("message_id") or ""),
                payload={"proposal_status": proposal_status},
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=signal.signal_id,
                event_type=TradeEventType.TELEGRAM_PROJECTED,
                idempotency_key=f"telegram:signal:{signal.signal_id}",
                asset=signal.asset,
                market=signal.market,
                payload={"message_type": "signal"},
            )
        )

    async def project_virtual_result(self, trade: VirtualTrade, *, balance_after: float | None = None) -> None:
        if not self.settings.telegram_enabled or not self.configured:
            return
        pnl = trade_profit(trade)
        result_icon = "✅" if trade.outcome == Outcome.WIN else "❌"
        result_text = "GANADA" if trade.outcome == Outcome.WIN else "PERDIDA"
        market_name = format_market_name(trade.asset)
        direction_icon = "🟢⬆️" if trade.direction.value == "RISE" else "🔴⬇️"
        balance_line = (
            f"\n🏦 Saldo virtual: {balance_after:.2f} {self.settings.deriv_currency}"
            if balance_after is not None
            else ""
        )
        text = (
            f"{result_icon} Resultado operación Deriv ({self.settings.deriv_account_mode})\n\n"
            f"🆔 Signal ID: {trade.signal_id}\n"
            f"📊 Mercado: {market_name} ({trade.asset})\n"
            f"🎯 Dirección: {direction_icon} {trade.direction.value}\n"
            f"🧾 Contrato: {trade.contract_type}\n"
            f"📍 Entrada: {trade.entry_spot}\n"
            f"🏁 Salida: {trade.exit_spot}\n"
            f"📌 Resultado: {result_text}\n"
            f"💰 P/L: {format_signed_money(pnl)} {self.settings.deriv_currency}"
            f"{balance_line}"
        )
        result = await self._send_text(text)
        await self.store.upsert_telegram_event(
            TelegramEvent(
                signal_id=trade.signal_id,
                message_type="result",
                chat_id_hash=stable_hash(self.settings.telegram_chat_id.get_secret_value() if self.settings.telegram_chat_id else ""),
                telegram_message_id=str(result.get("message_id") or ""),
                payload={
                    "outcome": trade.outcome,
                    "profit": pnl,
                    "balance_after": balance_after,
                    "resolution_source": trade.resolution_source,
                },
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=trade.signal_id,
                event_type=TradeEventType.TELEGRAM_PROJECTED,
                idempotency_key=f"telegram:result:{trade.signal_id}",
                asset=trade.asset,
                market=trade.market,
                payload={"message_type": "result"},
            )
        )

    async def project_five_trade_summary(
        self,
        *,
        batch_number: int,
        trades: list[VirtualTrade],
        balance_after: float,
    ) -> None:
        if not self.settings.telegram_enabled or not self.configured or not trades:
            return
        lines = [
            f"📊 Resumen de 5 operaciones Deriv ({self.settings.deriv_account_mode})",
            "",
        ]
        total = 0.0
        wins = 0
        for index, trade in enumerate(trades, start=1):
            pnl = trade_profit(trade)
            total += pnl
            if trade.outcome == Outcome.WIN:
                wins += 1
            outcome = "ganada ✅" if trade.outcome == Outcome.WIN else "perdida ❌"
            lines.append(
                f"Operación {index}: {format_market_name(trade.asset)} {outcome} {format_signed_money(pnl)} {self.settings.deriv_currency}"
            )
        losses = len(trades) - wins
        lines.extend(
            [
                "",
                f"✅ Ganadas: {wins} | ❌ Perdidas: {losses}",
                f"💰 Resultado neto: {format_signed_money(total)} {self.settings.deriv_currency}",
                f"🏦 Saldo virtual: {balance_after:.2f} {self.settings.deriv_currency}",
            ]
        )
        result = await self._send_text("\n".join(lines))
        summary_id = f"summary_batch_{batch_number}"
        await self.store.upsert_telegram_event(
            TelegramEvent(
                signal_id=summary_id,
                message_type="summary_5",
                chat_id_hash=stable_hash(self.settings.telegram_chat_id.get_secret_value() if self.settings.telegram_chat_id else ""),
                telegram_message_id=str(result.get("message_id") or ""),
                payload={
                    "batch_number": batch_number,
                    "trade_signal_ids": [trade.signal_id for trade in trades],
                    "balance_after": balance_after,
                    "net_profit": total,
                },
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=summary_id,
                event_type=TradeEventType.TELEGRAM_PROJECTED,
                idempotency_key=f"telegram:summary_5:{batch_number}",
                payload={"message_type": "summary_5", "batch_number": batch_number},
            )
        )

    async def project_account_reset_alert(
        self,
        *,
        reason: str,
        account: VirtualAccountState,
        balance_before_reset: float | None = None,
        triggering_signal_id: str | None = None,
    ) -> None:
        if not self.settings.telegram_enabled or not self.configured:
            return
        is_target = reason == "target_reached"
        message_type = "target_alert" if is_target else "bankruptcy_alert"
        reset_number = account.resets
        signal_id = f"virtual_account_reset_{reset_number}"
        if is_target:
            title = "🎯 META ALCANZADA"
            reason_line = "El saldo virtual llegó a la meta configurada."
            counter_line = f"🏆 Metas logradas: {account.target_hits}"
        else:
            title = "🚨 ALERTA DE QUIEBRA"
            reason_line = (
                "No había saldo suficiente para continuar operando."
                if reason == "insufficient_virtual_balance"
                else "El saldo virtual cayó por debajo del stake mínimo."
            )
            counter_line = f"🧯 Quiebras acumuladas: {account.bankruptcies}"
        before_line = (
            f"\n💼 Saldo antes del reinicio: {balance_before_reset:.2f} {self.settings.deriv_currency}"
            if balance_before_reset is not None
            else ""
        )
        trigger_line = f"\n🆔 Operación relacionada: {triggering_signal_id}" if triggering_signal_id else ""
        text = (
            f"{title}\n\n"
            f"📌 Motivo: {reason_line}"
            f"{trigger_line}"
            f"{before_line}\n"
            f"🔄 Saldo reiniciado a: {account.balance:.2f} {self.settings.deriv_currency}\n"
            f"{counter_line}\n"
            f"📊 Meta actual: {account.target_balance:.2f} {self.settings.deriv_currency}\n"
            f"💵 Stake actual: {account.stake:.2f} {self.settings.deriv_currency}"
        )
        result = await self._send_text(text)
        await self.store.upsert_telegram_event(
            TelegramEvent(
                signal_id=signal_id,
                message_type=message_type,
                chat_id_hash=stable_hash(self.settings.telegram_chat_id.get_secret_value() if self.settings.telegram_chat_id else ""),
                telegram_message_id=str(result.get("message_id") or ""),
                payload={
                    "reason": reason,
                    "reset_number": reset_number,
                    "balance_before_reset": balance_before_reset,
                    "balance_after_reset": account.balance,
                    "triggering_signal_id": triggering_signal_id,
                },
            )
        )
        await self.store.append_event(
            TradeEvent(
                signal_id=signal_id,
                event_type=TradeEventType.TELEGRAM_PROJECTED,
                idempotency_key=f"telegram:{message_type}:{reset_number}",
                payload={"message_type": message_type, "reason": reason, "reset_number": reset_number},
            )
        )

    async def _send_text(self, text: str) -> dict[str, object]:
        if not self.configured:
            return {"ok": False, "reason": "telegram_not_configured"}
        token = self.settings.telegram_bot_token.get_secret_value()  # type: ignore[union-attr]
        chat_id = self.settings.telegram_chat_id.get_secret_value()  # type: ignore[union-attr]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") or {}
        return {"ok": bool(payload.get("ok")), "message_id": result.get("message_id")}


def format_market_name(asset: str) -> str:
    known = {
        "frxXAUUSD": "Gold/USD",
        "frxXAGUSD": "Silver/USD",
    }
    if asset in known:
        return known[asset]
    if asset.startswith("frx") and len(asset) == 9:
        pair = asset[3:]
        return f"{pair[:3]}/{pair[3:]}"
    return asset


def trade_profit(trade: VirtualTrade) -> float:
    if trade.outcome == Outcome.WIN:
        return round(trade.payout - trade.stake, 8)
    if trade.outcome in {Outcome.LOSS, Outcome.EQUAL_LOSS}:
        return round(-trade.stake, 8)
    return 0.0


def format_signed_money(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value):.2f}"
