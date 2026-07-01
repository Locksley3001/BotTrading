from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import websockets

from app.config import Settings
from app.models import ContractMapping, DerivSymbol, Proposal, SignalDirection, Tick


class DerivAPIError(RuntimeError):
    def __init__(self, message: str, *, code: str | None = None, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


@dataclass(frozen=True)
class WSResult:
    request: dict[str, Any]
    response: dict[str, Any]
    latency_ms: float


class DerivPublicClient:
    """Small direct WebSocket client for Deriv public Options API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._req_id = 0

    def next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def request(self, payload: dict[str, Any], timeout: float = 15.0) -> WSResult:
        payload = dict(payload)
        payload.setdefault("req_id", self.next_req_id())
        started = perf_counter()
        async with websockets.connect(
            self.settings.deriv_public_ws_url,
            ping_interval=20,
            close_timeout=5,
            max_size=2**23,
        ) as ws:
            await ws.send(json.dumps(payload))
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        latency_ms = (perf_counter() - started) * 1000
        response = json.loads(raw)
        if "error" in response:
            error = response["error"] or {}
            raise DerivAPIError(
                error.get("message", "Deriv API error"),
                code=error.get("code"),
                payload=response,
            )
        return WSResult(request=payload, response=response, latency_ms=latency_ms)

    async def stream_ticks(self, symbol: str, seconds: float = 10.0) -> list[Tick]:
        payload = {"ticks": symbol, "subscribe": 1, "req_id": self.next_req_id()}
        ticks: list[Tick] = []
        async with websockets.connect(
            self.settings.deriv_public_ws_url,
            ping_interval=20,
            close_timeout=5,
            max_size=2**23,
        ) as ws:
            await ws.send(json.dumps(payload))
            deadline = perf_counter() + seconds
            while perf_counter() < deadline:
                remaining = max(0.1, deadline - perf_counter())
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(5.0, remaining))
                except TimeoutError:
                    continue
                response = json.loads(raw)
                if "error" in response:
                    error = response["error"] or {}
                    raise DerivAPIError(error.get("message", "Deriv API error"), code=error.get("code"), payload=response)
                tick = response.get("tick")
                if tick:
                    ticks.append(Tick(symbol=tick["symbol"], epoch=int(tick["epoch"]), quote=float(tick["quote"])))
        return ticks

    async def ping(self) -> WSResult:
        return await self.request({"ping": 1})

    async def server_time(self) -> WSResult:
        return await self.request({"time": 1})

    async def active_symbols(self) -> list[dict[str, Any]]:
        result = await self.request({"active_symbols": "brief"})
        return result.response.get("active_symbols", [])

    async def contracts_for(self, symbol: str) -> dict[str, Any]:
        result = await self.request({"contracts_for": symbol})
        return result.response.get("contracts_for", {})

    async def contracts_list(self) -> dict[str, Any]:
        result = await self.request({"contracts_list": 1})
        return result.response

    async def proposal(
        self,
        *,
        symbol: str,
        contract_type: str,
        amount: float,
        duration: int,
        duration_unit: str,
        currency: str | None = None,
    ) -> Proposal:
        response = await self.request(
            {
                "proposal": 1,
                "amount": amount,
                "basis": self.settings.deriv_stake_basis,
                "contract_type": contract_type,
                "currency": currency or self.settings.deriv_currency,
                "duration": duration,
                "duration_unit": duration_unit,
                "underlying_symbol": symbol,
            }
        )
        proposal = response.response.get("proposal") or {}
        ask_price = float(proposal.get("ask_price") or amount)
        payout = float(proposal.get("payout") or 0)
        payout_rate = (payout - ask_price) / ask_price if ask_price else 0
        direction = SignalDirection.RISE if contract_type == self.settings.deriv_rise_contract_type else SignalDirection.FALL
        return Proposal(
            proposal_id=str(proposal.get("id")),
            symbol=symbol,
            direction=direction,
            contract_type=contract_type,
            ask_price=ask_price,
            payout=payout,
            payout_rate=payout_rate,
            spot=_float_or_none(proposal.get("spot")),
            spot_time=_int_or_none(proposal.get("spot_time")),
            date_start=_int_or_none(proposal.get("date_start")),
            date_expiry=_int_or_none(proposal.get("date_expiry")),
            longcode=str(proposal.get("longcode", "")),
            raw=proposal,
        )

    async def ticks_history(self, symbol: str, *, count: int, granularity: int) -> list[dict[str, Any]]:
        response = await self.request(
            {
                "ticks_history": symbol,
                "style": "candles",
                "end": "latest",
                "count": count,
                "granularity": granularity,
            }
        )
        return response.response.get("candles", [])


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def symbol_from_active(raw: dict[str, Any]) -> DerivSymbol:
    symbol = str(raw.get("symbol") or raw.get("underlying_symbol") or "")
    display_name = str(raw.get("display_name") or raw.get("underlying_symbol_name") or symbol)
    return DerivSymbol(
        symbol=symbol,
        display_name=display_name,
        market=str(raw.get("market", "")),
        submarket=raw.get("submarket"),
        exchange_is_open=bool(int(raw.get("exchange_is_open") or 0)),
        is_trading_suspended=bool(int(raw.get("is_trading_suspended") or 0)),
    )


def is_excluded_symbol(symbol: str, patterns: Iterable[str]) -> bool:
    upper_symbol = symbol.upper()
    return any(pattern.upper() in upper_symbol for pattern in patterns)


def market_candidate(symbol: DerivSymbol, settings: Settings) -> tuple[bool, str | None]:
    if not symbol.exchange_is_open:
        return False, "market_closed"
    if symbol.is_trading_suspended:
        return False, "trading_suspended"
    if not settings.deriv_allow_synthetic_markets and symbol.market == "synthetic_index":
        return False, "synthetic_index_blocked"
    if symbol.market in settings.deriv_excluded_markets:
        return False, "excluded_market"
    allowed = set(settings.deriv_allowed_markets) | set(settings.deriv_optional_markets)
    if symbol.market not in allowed:
        return False, "market_not_allowed"
    if symbol.submarket in settings.deriv_excluded_submarkets:
        return False, "excluded_submarket"
    if is_excluded_symbol(symbol.symbol, settings.deriv_excluded_symbol_patterns):
        return False, "excluded_symbol_pattern"
    return True, None


def callput_contract_types(contracts_for: dict[str, Any]) -> set[str]:
    types: set[str] = set()
    for available in contracts_for.get("available", []) or []:
        if available.get("contract_category") != "callput":
            continue
        contract_type = available.get("contract_type")
        if contract_type:
            types.add(str(contract_type))
    return types


def duration_offered(contracts_for: dict[str, Any], contract_type: str, duration: int, duration_unit: str) -> bool:
    expected = f"{duration}{duration_unit}"
    for available in contracts_for.get("available", []) or []:
        if available.get("contract_category") != "callput":
            continue
        if available.get("contract_type") != contract_type:
            continue
        if _duration_range_contains(
            str(available.get("min_contract_duration") or ""),
            str(available.get("max_contract_duration") or ""),
            expected,
        ):
            return True
    return False


def _duration_range_contains(min_duration: str, max_duration: str, expected: str) -> bool:
    expected_value = _duration_to_seconds(expected)
    min_value = _duration_to_seconds(min_duration)
    max_value = _duration_to_seconds(max_duration)
    if expected_value is None or min_value is None or max_value is None:
        return False
    return min_value <= expected_value <= max_value


def _duration_to_seconds(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", value)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return amount * multiplier


def verify_longcode_mapping(direction: SignalDirection, contract_type: str, longcode: str) -> ContractMapping:
    normalized = " ".join(longcode.lower().split())
    if direction == SignalDirection.RISE:
        verified = any(
            phrase in normalized
            for phrase in [
                "higher than the entry spot",
                "higher than entry spot",
                "strictly higher",
                "is higher than",
            ]
        )
        expected = "exit_spot > entry_spot"
    else:
        verified = any(
            phrase in normalized
            for phrase in [
                "lower than the entry spot",
                "lower than entry spot",
                "strictly lower",
                "is lower than",
            ]
        )
        expected = "exit_spot < entry_spot"
    return ContractMapping(
        direction=direction,
        contract_type=contract_type,
        expected_phrase=expected,
        longcode=longcode,
        verified=verified,
        reason=None if verified else "longcode_does_not_confirm_direction",
    )
