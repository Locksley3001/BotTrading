from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class SignalDirection(StrEnum):
    RISE = "RISE"
    FALL = "FALL"


class TradeEventType(StrEnum):
    MARKET_DISCOVERED = "market_discovered"
    MARKET_BLOCKED = "market_blocked"
    CONTRACT_MAPPING_VERIFIED = "contract_mapping_verified"
    CONTRACT_MAPPING_FAILED = "contract_mapping_failed"
    SIGNAL_DECIDED = "signal_decided"
    ENTRY_VALIDATED = "entry_validated"
    PROPOSAL_RECEIVED = "proposal_received"
    PROPOSAL_REJECTED = "proposal_rejected"
    STALE_PROPOSAL = "stale_proposal"
    PAYOUT_TOO_LOW = "payout_too_low"
    BUY_CONFIRMED = "buy_confirmed"
    BUY_REJECTED = "buy_rejected"
    CONTRACT_SETTLED = "contract_settled"
    TELEGRAM_PROJECTED = "telegram_projected"
    DISCREPANCY_DETECTED = "discrepancy_detected"
    VIRTUAL_OUTCOME = "virtual_outcome"
    LIVE_ANALYSIS_CYCLE = "live_analysis_cycle"
    VIRTUAL_ACCOUNT_CONFIGURED = "virtual_account_configured"
    VIRTUAL_ACCOUNT_RESET = "virtual_account_reset"
    VIRTUAL_TRADE_OPENED = "virtual_trade_opened"
    VIRTUAL_TRADE_SETTLED = "virtual_trade_settled"
    BROKER_TRADING_UPDATED = "broker_trading_updated"
    BROKER_TRADING_REJECTED = "broker_trading_rejected"
    ERROR = "error"


class SignalStatus(StrEnum):
    SHADOW = "shadow"
    APPROVED = "approved"
    PROPOSAL_REJECTED = "proposal_rejected"
    BUY_CONFIRMED = "buy_confirmed"
    SETTLED = "settled"
    ABORTED = "aborted"
    DISCREPANCY = "discrepancy"


class Outcome(StrEnum):
    WIN = "win"
    LOSS = "loss"
    EQUAL_LOSS = "equal_loss"
    UNKNOWN = "unknown"


class ContractMapping(BaseModel):
    model_config = ConfigDict(extra="allow")

    direction: SignalDirection
    contract_type: str
    expected_phrase: str
    longcode: str
    verified: bool
    reason: str | None = None


class DerivSymbol(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    display_name: str
    market: str
    submarket: str | None = None
    exchange_is_open: bool = False
    is_trading_suspended: bool = False
    enabled: bool = False
    blocked_reason: str | None = None
    duration: int | None = None
    duration_unit: str | None = None
    has_rise_fall: bool = False
    call_available: bool = False
    put_available: bool = False
    mapping_verified: bool = False
    payout_rate_call: float | None = None
    payout_rate_put: float | None = None
    last_verified_at: datetime | None = None


class Tick(BaseModel):
    symbol: str
    epoch: int
    quote: float


class Candle(BaseModel):
    symbol: str
    epoch: int
    open: float
    high: float
    low: float
    close: float
    granularity: int
    closed: bool = True


class Signal(BaseModel):
    signal_id: str = Field(default_factory=lambda: f"sig_{uuid4().hex}")
    asset: str
    display_name: str | None = None
    market: str
    direction: SignalDirection
    contract_type: str
    duration: int
    duration_unit: str
    timeframe: int
    score: int
    factor_score: int
    stake: float
    status: SignalStatus = SignalStatus.APPROVED
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Proposal(BaseModel):
    proposal_id: str
    symbol: str
    direction: SignalDirection
    contract_type: str
    ask_price: float
    payout: float
    payout_rate: float
    spot: float | None = None
    spot_time: int | None = None
    date_start: int | None = None
    date_expiry: int | None = None
    longcode: str
    raw: dict[str, Any] = Field(default_factory=dict)


class BrokerOrder(BaseModel):
    signal_id: str
    deriv_contract_id: str
    transaction_id: str | None = None
    symbol: str
    direction: SignalDirection
    contract_type: str
    buy_price: float
    payout: float
    currency: str
    purchase_time: int | None = None
    start_time: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    raw: dict[str, Any] = Field(default_factory=dict)


class TradeEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    signal_id: str | None = None
    event_type: TradeEventType
    idempotency_key: str
    asset: str | None = None
    market: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = "deriv_bot"


class VirtualTradeStatus(StrEnum):
    OPEN = "open"
    SETTLED = "settled"
    SKIPPED = "skipped"


class VirtualAccountState(BaseModel):
    balance: float = 100.0
    initial_balance: float = 100.0
    target_balance: float = 150.0
    stake: float = 10.0
    currency: str = "USD"
    resets: int = 0
    target_hits: int = 0
    bankruptcies: int = 0
    updated_at: datetime = Field(default_factory=utc_now)


class VirtualTrade(BaseModel):
    signal_id: str
    asset: str
    market: str
    direction: SignalDirection
    contract_type: str
    stake: float
    payout: float
    payout_rate: float
    entry_spot: float
    entry_epoch: int
    expiry_epoch: int
    status: VirtualTradeStatus = VirtualTradeStatus.OPEN
    outcome: Outcome | None = None
    exit_spot: float | None = None
    opened_at: datetime = Field(default_factory=utc_now)
    settled_at: datetime | None = None
    resolution_source: str = "virtual_tick_replay"
    broker_contract_id: str | None = None


class TelegramEvent(BaseModel):
    signal_id: str
    message_type: str
    chat_id_hash: str
    sent_at: datetime = Field(default_factory=utc_now)
    telegram_message_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
