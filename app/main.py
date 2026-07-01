from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from pydantic import BaseModel

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import ROOT_DIR, Settings, get_settings
from app.deriv_adapter import DerivAPIError, DerivPublicClient
from app.event_store import EventSink, LocalJsonlEventStore
from app.learning import LearningService
from app.live_engine import LiveMarketEngine
from app.market_discovery import MarketDiscoveryService
from app.models import Signal, SignalDirection, TradeEvent, TradeEventType
from app.supabase_store import make_event_store
from app.telegram_notifier import TelegramNotifier
from app.virtual_account import VirtualAccountService


class AppState:
    settings: Settings
    store: EventSink
    local_store: LocalJsonlEventStore
    deriv: DerivPublicClient
    telegram: TelegramNotifier
    virtual_account: VirtualAccountService
    learning: LearningService
    engine: LiveMarketEngine
    last_error: str | None = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    state.settings = settings
    state.local_store = LocalJsonlEventStore(settings.data_dir)
    state.store = await make_event_store(settings)
    state.deriv = DerivPublicClient(settings)
    state.telegram = TelegramNotifier(settings, state.store)
    state.virtual_account = VirtualAccountService(settings, state.store)
    state.learning = LearningService(settings, state.local_store, state.store)
    if not state.virtual_account.path.exists():
        await state.virtual_account.configure(
            initial_balance=settings.virtual_initial_balance,
            balance=settings.virtual_initial_balance,
            stake=settings.virtual_safe_stake,
            target_balance=settings.virtual_target_balance,
        )
    state.engine = LiveMarketEngine(
        settings=settings,
        client=state.deriv,
        store=state.store,
        local_store=state.local_store,
        virtual_account=state.virtual_account,
        telegram=state.telegram,
        learning=state.learning,
    )
    state.engine.broker_trading_enabled = settings.broker_trading_enabled
    state.engine.start()
    yield
    await state.engine.stop()


app = FastAPI(title="Deriv Rise/Fall Bot", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")


def settings_dep() -> Settings:
    return state.settings


class BrokerTradingRequest(BaseModel):
    enabled: bool


class VirtualAccountConfigRequest(BaseModel):
    initial_balance: float | None = None
    balance: float | None = None
    stake: float | None = None
    target_balance: float | None = None


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(ROOT_DIR / "static" / "index.html")


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(settings_dep)]) -> dict[str, object]:
    public_ok = False
    public_latency_ms: float | None = None
    supabase_connected = state.store.__class__.__name__ == "SupabaseEventStore"
    try:
        ping = await state.deriv.ping()
        public_ok = bool(ping.response.get("ping"))
        public_latency_ms = round(ping.latency_ms, 2)
    except Exception as exc:
        state.last_error = type(exc).__name__
    return {
        "ok": public_ok,
        "version": __version__,
        "strategy_version": "cci20-price-action-deriv-0.1",
        "migration_version": "001_deriv_schema",
        "public_ws": {"connected": public_ok, "latency_ms": public_latency_ms},
        "auth_ws": {"connected": False, "configured": settings.auth_configured},
        "supabase": {
            "configured": bool(settings.supabase_url and settings.supabase_server_key),
            "connected": supabase_connected,
            "mode": "remote" if supabase_connected else "local_fallback",
        },
        "telegram": {"configured": bool(settings.telegram_bot_token and settings.telegram_chat_id)},
        "live_engine": state.engine.status(),
        "virtual_account": state.virtual_account.state.model_dump(mode="json"),
        "last_error": state.last_error,
        **settings.safe_status(),
        "broker_trading_enabled": state.engine.broker_trading_enabled,
    }


@app.get("/api/state")
async def api_state(settings: Annotated[Settings, Depends(settings_dep)]) -> dict[str, object]:
    return {
        "settings": settings.safe_status(),
        "markets": state.local_store.read_markets(limit=200),
        "signals": state.local_store.read_signals(limit=50),
        "events": state.local_store.read_events(limit=50),
        "virtual_account": state.virtual_account.state.model_dump(mode="json"),
        "virtual_trades": state.local_store.read_virtual_trades(limit=100),
        "learning": state.learning.read(),
        "live_engine": state.engine.status(),
    }


@app.get("/api/events")
async def api_events(signal_id: str | None = None, limit: int = Query(default=500, le=1000)) -> dict[str, object]:
    return {"items": state.local_store.read_events(signal_id=signal_id, limit=limit)}


@app.get("/api/signals")
async def api_signals(limit: int = Query(default=500, le=1000)) -> dict[str, object]:
    return {"items": state.local_store.read_signals(limit=limit)}


@app.get("/api/performance")
async def api_performance() -> dict[str, object]:
    signals = state.local_store.read_signals(limit=1000)
    events = state.local_store.read_events(limit=2000)
    settled = [e for e in events if e.get("event_type") in {"contract_settled", TradeEventType.CONTRACT_SETTLED}]
    return {
        "signals_count": len(signals),
        "settled_count": len(settled),
        "virtual_balance_source": "events",
    }


@app.get("/api/deriv/market-catalog")
async def market_catalog(limit: int = Query(default=500, le=1000)) -> dict[str, object]:
    return {"items": state.local_store.read_markets(limit=limit)}


@app.get("/api/markets/{asset}/candles")
async def market_candles(asset: str, granularity: int = 60, count: int = Query(default=120, le=500)) -> dict[str, object]:
    candles = state.engine.candles_by_symbol.get(asset)
    if candles is None:
        raw = await state.deriv.ticks_history(asset, count=count, granularity=granularity)
        candles = [
            {
                "symbol": asset,
                "epoch": int(item["epoch"]),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "granularity": granularity,
                "closed": True,
            }
            for item in raw
        ]
        return {"asset": asset, "items": candles}
    return {"asset": asset, "items": [candle.model_dump(mode="json") for candle in candles[-count:]]}


@app.post("/api/deriv/market-discovery")
async def market_discovery() -> dict[str, object]:
    service = MarketDiscoveryService(state.settings, state.deriv)
    markets, events = await service.discover()
    for market in markets:
        await state.store.upsert_market(market)
    for event in events:
        await state.store.append_event(event)
    return {"items": [market.model_dump(mode="json") for market in markets], "events": len(events)}


@app.post("/api/deriv/verify-contracts")
async def verify_contracts() -> dict[str, object]:
    return await market_discovery()


@app.get("/api/live/status")
async def live_status() -> dict[str, object]:
    return state.engine.status()


@app.post("/api/live/scan-once")
async def live_scan_once() -> dict[str, object]:
    return await state.engine.scan_once()


@app.post("/api/live/settle-due")
async def live_settle_due() -> dict[str, object]:
    settled = await state.engine.settle_due_virtual_trades()
    return {"settled": [trade.model_dump(mode="json") for trade in settled]}


@app.get("/api/learning")
async def learning_state() -> dict[str, object]:
    return state.learning.read()


@app.post("/api/learning/rebuild")
async def learning_rebuild() -> dict[str, object]:
    return await state.learning.rebuild_from_virtual_trades()


@app.get("/api/virtual-account")
async def virtual_account() -> dict[str, object]:
    return {
        "account": state.virtual_account.state.model_dump(mode="json"),
        "trades": state.local_store.read_virtual_trades(limit=250),
    }


@app.post("/api/virtual-account/config")
async def virtual_account_config(request: VirtualAccountConfigRequest) -> dict[str, object]:
    account = await state.virtual_account.configure(**request.model_dump())
    return {"account": account.model_dump(mode="json")}


@app.get("/api/broker/orders")
async def broker_orders() -> dict[str, object]:
    return {"items": []}


@app.post("/api/broker/trading")
async def broker_trading(request: BrokerTradingRequest, settings: Annotated[Settings, Depends(settings_dep)]) -> dict[str, object]:
    if request.enabled:
        reason = None
        if not settings.auth_configured:
            reason = "missing_deriv_api_credentials"
        elif settings.deriv_account_mode == "REAL" and not settings.live_test_allow_real:
            reason = "real_trading_requires_explicit_gate"
        else:
            reason = "authenticated_buy_transport_not_enabled"
        await state.store.append_event(
            TradeEvent(
                event_type=TradeEventType.BROKER_TRADING_REJECTED,
                idempotency_key=f"broker_trading_rejected:{reason}",
                payload={"requested_enabled": True, "reason": reason},
            )
        )
        raise HTTPException(status_code=403, detail=reason)
    state.engine.broker_trading_enabled = False
    await state.store.append_event(
        TradeEvent(
            event_type=TradeEventType.BROKER_TRADING_UPDATED,
            idempotency_key="broker_trading_updated:false",
            payload={"broker_trading_enabled": False},
        )
    )
    return {"broker_trading_enabled": False}


@app.post("/api/telegram/test")
async def telegram_test() -> dict[str, object]:
    try:
        return await state.telegram.send_test_message()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Telegram test failed: {type(exc).__name__}") from exc


@app.post("/api/markets")
async def add_market(asset: str) -> dict[str, object]:
    await state.store.append_event(
        TradeEvent(
            event_type=TradeEventType.MARKET_DISCOVERED,
            idempotency_key=f"market:add:{asset}",
            asset=asset,
            payload={"action": "add_market", "asset": asset},
        )
    )
    return {"asset": asset, "status": "queued_for_discovery"}


@app.delete("/api/markets/{asset}")
async def delete_market(asset: str) -> dict[str, object]:
    await state.store.append_event(
        TradeEvent(
            event_type=TradeEventType.MARKET_BLOCKED,
            idempotency_key=f"market:delete:{asset}",
            asset=asset,
            payload={"action": "delete_market", "asset": asset},
        )
    )
    return {"asset": asset, "status": "disabled"}


@app.post("/api/markets/{asset}/enabled")
async def set_market_enabled(asset: str, enabled: bool) -> dict[str, object]:
    await state.store.append_event(
        TradeEvent(
            event_type=TradeEventType.MARKET_DISCOVERED if enabled else TradeEventType.MARKET_BLOCKED,
            idempotency_key=f"market:enabled:{asset}:{enabled}",
            asset=asset,
            payload={"action": "set_market_enabled", "asset": asset, "enabled": enabled},
        )
    )
    return {"asset": asset, "enabled": enabled}


@app.post("/api/timeframe")
async def set_timeframe(timeframe: int) -> dict[str, object]:
    return {"timeframe": timeframe, "status": "accepted_for_runtime_only"}


@app.get("/api/auth/deriv/login-url")
async def deriv_login_url(settings: Annotated[Settings, Depends(settings_dep)]) -> dict[str, object]:
    if not settings.deriv_client_id or not settings.deriv_redirect_uri:
        return {"configured": False, "reason": "DERIV_CLIENT_ID and DERIV_REDIRECT_URI are required"}
    return {"configured": False, "reason": "PKCE login scaffolding is documented; token exchange is not enabled without explicit OAuth client config."}


@app.get("/api/auth/deriv/callback")
async def deriv_callback() -> dict[str, object]:
    return {"status": "not_configured"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_json({"type": "state", "payload": await api_state(state.settings)})
    except WebSocketDisconnect:
        return


@app.post("/api/dev/create-shadow-signal")
async def create_shadow_signal(asset: str, direction: SignalDirection) -> dict[str, object]:
    signal = Signal(
        asset=asset,
        display_name=asset,
        market="forex",
        direction=direction,
        contract_type=state.settings.deriv_rise_contract_type
        if direction == SignalDirection.RISE
        else state.settings.deriv_fall_contract_type,
        duration=state.settings.deriv_default_duration,
        duration_unit=state.settings.deriv_default_duration_unit,
        timeframe=state.settings.default_timeframe,
        score=7,
        factor_score=4,
        stake=state.settings.deriv_min_stake,
        reason="manual_shadow_signal",
    )
    await state.store.upsert_signal(signal)
    await state.store.append_event(
        TradeEvent(
            signal_id=signal.signal_id,
            event_type=TradeEventType.SIGNAL_DECIDED,
            idempotency_key=f"signal_decided:{signal.signal_id}",
            asset=signal.asset,
            market=signal.market,
            payload=signal.model_dump(mode="json"),
        )
    )
    return signal.model_dump(mode="json")
