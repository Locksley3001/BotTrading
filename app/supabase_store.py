from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import Settings
from app.event_store import EventSink, LocalJsonlEventStore
from app.models import BrokerOrder, DerivSymbol, Signal, TelegramEvent, TradeEvent, VirtualTrade
from app.security import scrub


class SupabaseUnavailable(RuntimeError):
    pass


class SupabaseEventStore(EventSink):
    """PostgREST-backed event store with local fallback queue.

    DDL is intentionally delivered as SQL migrations because Supabase service role
    keys do not grant arbitrary SQL execution through PostgREST.
    """

    def __init__(self, settings: Settings, fallback: LocalJsonlEventStore):
        self.settings = settings
        self.fallback = fallback
        if not settings.supabase_url or not settings.supabase_server_key:
            raise SupabaseUnavailable("Supabase URL/key not configured")
        self.base_url = settings.supabase_url.rstrip("/")
        self.key = settings.supabase_server_key.get_secret_value()
        self.base_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        self.timeout = httpx.Timeout(settings.supabase_timeout_seconds)

    async def append_event(self, event: TradeEvent) -> TradeEvent:
        await self._upsert(self.settings.supabase_event_table, event.model_dump(mode="json"), "idempotency_key")
        await self.fallback.append_event(event)
        return event

    async def upsert_signal(self, signal: Signal) -> Signal:
        await self._upsert(self.settings.supabase_signal_table, signal.model_dump(mode="json"), "signal_id")
        await self.fallback.upsert_signal(signal)
        return signal

    async def upsert_broker_order(self, order: BrokerOrder) -> BrokerOrder:
        await self._upsert(self.settings.supabase_broker_order_table, order.model_dump(mode="json"), "signal_id")
        await self.fallback.upsert_broker_order(order)
        return order

    async def upsert_market(self, market: DerivSymbol) -> DerivSymbol:
        await self._upsert(self.settings.supabase_market_catalog_table, market.model_dump(mode="json"), "symbol")
        await self.fallback.upsert_market(market)
        return market

    async def upsert_telegram_event(self, event: TelegramEvent) -> TelegramEvent:
        await self._upsert(
            self.settings.supabase_telegram_event_table,
            event.model_dump(mode="json"),
            "signal_id,message_type",
        )
        await self.fallback.upsert_telegram_event(event)
        return event

    async def upsert_virtual_trade(self, trade: VirtualTrade) -> VirtualTrade:
        # Virtual trades are currently kept in the canonical event stream plus local projection.
        await self.fallback.upsert_virtual_trade(trade)
        return trade

    async def _upsert(self, table: str, payload: dict[str, Any], on_conflict: str) -> None:
        url = f"{self.base_url}/rest/v1/{table}?on_conflict={on_conflict}"
        headers = self._headers_for_schema(self.settings.supabase_deriv_schema)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, headers=headers, json=scrub(payload))
        if response.status_code >= 400:
            raise SupabaseUnavailable(f"Supabase upsert failed: {response.status_code} {response.text[:300]}")

    async def healthcheck(self) -> dict[str, Any]:
        legacy_url = f"{self.base_url}/rest/v1/{self.settings.supabase_state_table}?select=*&limit=1"
        deriv_url = f"{self.base_url}/rest/v1/{self.settings.supabase_event_table}?select=id&limit=1"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            legacy_response = await client.get(legacy_url, headers=self.base_headers)
            deriv_response = await client.get(
                deriv_url,
                headers=self._headers_for_schema(self.settings.supabase_deriv_schema, write=False),
            )
        auth_failed = legacy_response.status_code in {401, 403} or deriv_response.status_code in {401, 403}
        return {
            "ok": not auth_failed and legacy_response.status_code < 500 and deriv_response.status_code < 500,
            "project_reachable": not auth_failed,
            "legacy_table_status": legacy_response.status_code,
            "deriv_table_status": deriv_response.status_code,
            "deriv_ready": deriv_response.status_code == 200,
            "deriv_error": deriv_response.text[:300] if deriv_response.status_code >= 400 else "",
            "legacy_table": self.settings.supabase_state_table,
            "deriv_schema": self.settings.supabase_deriv_schema,
            "deriv_event_table": self.settings.supabase_event_table,
        }

    def _headers_for_schema(self, schema: str, *, write: bool = True) -> dict[str, str]:
        headers = dict(self.base_headers)
        headers["Accept-Profile"] = schema
        if write:
            headers["Content-Profile"] = schema
        return headers


async def make_event_store(settings: Settings) -> EventSink:
    local = LocalJsonlEventStore(settings.data_dir)
    if not settings.supabase_url or not settings.supabase_server_key:
        return local
    try:
        store = SupabaseEventStore(settings, local)
        health = await asyncio.wait_for(store.healthcheck(), timeout=settings.supabase_timeout_seconds + 2)
        if not health.get("deriv_ready"):
            return local
        return store
    except Exception:
        return local
