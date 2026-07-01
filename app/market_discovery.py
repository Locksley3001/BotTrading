from __future__ import annotations

import asyncio
from collections.abc import Iterable

from app.config import Settings
from app.deriv_adapter import (
    DerivAPIError,
    DerivPublicClient,
    callput_contract_types,
    duration_offered,
    market_candidate,
    symbol_from_active,
    verify_longcode_mapping,
)
from app.models import DerivSymbol, SignalDirection, TradeEvent, TradeEventType


class MarketDiscoveryService:
    def __init__(self, settings: Settings, client: DerivPublicClient):
        self.settings = settings
        self.client = client

    async def discover(self, symbols: Iterable[str] | None = None) -> tuple[list[DerivSymbol], list[TradeEvent]]:
        active = await self.client.active_symbols()
        requested = set(symbols or self.settings.markets or self.settings.deriv_primary_markets)
        catalog = [symbol_from_active(item) for item in active]
        if requested:
            catalog = [item for item in catalog if item.symbol in requested]

        events: list[TradeEvent] = []
        verified: list[DerivSymbol] = []
        for symbol in catalog:
            allowed, reason = market_candidate(symbol, self.settings)
            if not allowed:
                symbol.enabled = False
                symbol.blocked_reason = reason
                events.append(_market_event(symbol, TradeEventType.MARKET_BLOCKED, reason or "blocked"))
                verified.append(symbol)
                continue
            duration, duration_unit = self.settings.duration_for_market(symbol.market, symbol.symbol)
            symbol.duration = duration
            symbol.duration_unit = duration_unit
            try:
                await self._verify_contracts(symbol)
                events.append(_market_event(symbol, TradeEventType.MARKET_DISCOVERED, "enabled"))
            except DerivAPIError as exc:
                symbol.enabled = False
                symbol.blocked_reason = exc.code or str(exc)
                events.append(_market_event(symbol, TradeEventType.MARKET_BLOCKED, symbol.blocked_reason))
            except Exception as exc:
                symbol.enabled = False
                symbol.blocked_reason = type(exc).__name__
                events.append(_market_event(symbol, TradeEventType.MARKET_BLOCKED, symbol.blocked_reason))
            verified.append(symbol)
        return verified, events

    async def _verify_contracts(self, symbol: DerivSymbol) -> None:
        contracts = await self.client.contracts_for(symbol.symbol)
        types = callput_contract_types(contracts)
        symbol.call_available = self.settings.deriv_rise_contract_type in types
        symbol.put_available = self.settings.deriv_fall_contract_type in types
        symbol.has_rise_fall = symbol.call_available and symbol.put_available
        if not symbol.has_rise_fall:
            raise DerivAPIError("Rise/Fall CALL/PUT not available", code="callput_not_available")

        assert symbol.duration is not None
        assert symbol.duration_unit is not None
        for contract_type in (self.settings.deriv_rise_contract_type, self.settings.deriv_fall_contract_type):
            if not duration_offered(contracts, contract_type, symbol.duration, symbol.duration_unit):
                raise DerivAPIError(
                    f"Duration {symbol.duration}{symbol.duration_unit} not offered for {contract_type}",
                    code="duration_not_offered",
                )

        if self.settings.deriv_verify_contract_mapping_on_start:
            call, put = await asyncio.gather(
                self.client.proposal(
                    symbol=symbol.symbol,
                    contract_type=self.settings.deriv_rise_contract_type,
                    amount=max(1, self.settings.deriv_min_stake),
                    duration=symbol.duration,
                    duration_unit=symbol.duration_unit,
                ),
                self.client.proposal(
                    symbol=symbol.symbol,
                    contract_type=self.settings.deriv_fall_contract_type,
                    amount=max(1, self.settings.deriv_min_stake),
                    duration=symbol.duration,
                    duration_unit=symbol.duration_unit,
                ),
            )
            call_mapping = verify_longcode_mapping(SignalDirection.RISE, call.contract_type, call.longcode)
            put_mapping = verify_longcode_mapping(SignalDirection.FALL, put.contract_type, put.longcode)
            symbol.payout_rate_call = call.payout_rate
            symbol.payout_rate_put = put.payout_rate
            symbol.mapping_verified = call_mapping.verified and put_mapping.verified
            if not symbol.mapping_verified:
                raise DerivAPIError("Proposal longcode does not confirm Rise/Fall mapping", code="mapping_failed")
        symbol.enabled = True


def _market_event(symbol: DerivSymbol, event_type: TradeEventType, reason: str) -> TradeEvent:
    return TradeEvent(
        event_type=event_type,
        idempotency_key=f"{event_type}:{symbol.symbol}:{reason}",
        asset=symbol.symbol,
        market=symbol.market,
        payload={
            "symbol": symbol.symbol,
            "display_name": symbol.display_name,
            "market": symbol.market,
            "submarket": symbol.submarket,
            "enabled": symbol.enabled,
            "blocked_reason": symbol.blocked_reason,
            "duration": symbol.duration,
            "duration_unit": symbol.duration_unit,
            "has_rise_fall": symbol.has_rise_fall,
            "mapping_verified": symbol.mapping_verified,
        },
    )
