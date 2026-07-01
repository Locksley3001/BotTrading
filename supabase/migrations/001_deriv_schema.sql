create schema if not exists deriv;

create table if not exists deriv.trade_events (
    id text primary key,
    signal_id text,
    event_type text not null,
    idempotency_key text not null unique,
    asset text,
    market text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    source text not null default 'deriv_bot',
    created_at timestamptz not null default now()
);

create table if not exists deriv.signals (
    signal_id text primary key,
    asset text not null,
    display_name text,
    market text not null,
    direction text not null check (direction in ('RISE', 'FALL')),
    contract_type text not null,
    duration integer not null,
    duration_unit text not null,
    timeframe integer not null,
    score integer not null,
    factor_score integer not null,
    stake numeric(18, 8) not null,
    status text not null,
    reason text,
    created_at timestamptz not null default now()
);

create table if not exists deriv.broker_orders (
    signal_id text primary key references deriv.signals(signal_id) on delete restrict,
    deriv_contract_id text unique not null,
    transaction_id text,
    symbol text not null,
    direction text not null check (direction in ('RISE', 'FALL')),
    contract_type text not null,
    buy_price numeric(18, 8) not null,
    payout numeric(18, 8) not null,
    currency text not null,
    purchase_time bigint,
    start_time bigint,
    raw jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists deriv.telegram_events (
    signal_id text not null,
    message_type text not null,
    chat_id_hash text not null,
    sent_at timestamptz not null default now(),
    telegram_message_id text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    primary key (signal_id, message_type)
);

create table if not exists deriv.virtual_trades (
    signal_id text primary key references deriv.signals(signal_id) on delete restrict,
    asset text not null,
    market text not null,
    direction text not null check (direction in ('RISE', 'FALL')),
    contract_type text not null,
    stake numeric(18, 8) not null,
    payout numeric(18, 8) not null,
    payout_rate numeric(18, 8) not null,
    entry_spot numeric(24, 10) not null,
    entry_epoch bigint not null,
    expiry_epoch bigint not null,
    status text not null,
    outcome text,
    exit_spot numeric(24, 10),
    opened_at timestamptz not null default now(),
    settled_at timestamptz,
    resolution_source text not null default 'virtual_tick_replay',
    broker_contract_id text,
    updated_at timestamptz not null default now()
);

create table if not exists deriv.deriv_market_catalog (
    symbol text primary key,
    display_name text not null,
    market text not null,
    submarket text,
    exchange_is_open boolean not null default false,
    is_trading_suspended boolean not null default false,
    enabled boolean not null default false,
    blocked_reason text,
    duration integer,
    duration_unit text,
    has_rise_fall boolean not null default false,
    call_available boolean not null default false,
    put_available boolean not null default false,
    mapping_verified boolean not null default false,
    payout_rate_call numeric(18, 8),
    payout_rate_put numeric(18, 8),
    last_verified_at timestamptz,
    updated_at timestamptz not null default now()
);

create index if not exists trade_events_signal_id_idx on deriv.trade_events(signal_id);
create index if not exists trade_events_asset_idx on deriv.trade_events(asset);
create index if not exists trade_events_market_idx on deriv.trade_events(market);
create index if not exists trade_events_event_type_idx on deriv.trade_events(event_type);
create index if not exists trade_events_occurred_at_idx on deriv.trade_events(occurred_at);
create index if not exists signals_asset_idx on deriv.signals(asset);
create index if not exists signals_market_idx on deriv.signals(market);
create index if not exists signals_status_idx on deriv.signals(status);
create index if not exists signals_created_at_idx on deriv.signals(created_at);
create index if not exists broker_orders_contract_id_idx on deriv.broker_orders(deriv_contract_id);
create index if not exists broker_orders_created_at_idx on deriv.broker_orders(created_at);
create index if not exists virtual_trades_asset_idx on deriv.virtual_trades(asset);
create index if not exists virtual_trades_status_idx on deriv.virtual_trades(status);
create index if not exists virtual_trades_expiry_epoch_idx on deriv.virtual_trades(expiry_epoch);
create index if not exists market_catalog_enabled_idx on deriv.deriv_market_catalog(enabled);
create index if not exists market_catalog_market_idx on deriv.deriv_market_catalog(market);

create or replace function deriv.append_trade_event(
    p_id text,
    p_signal_id text,
    p_event_type text,
    p_idempotency_key text,
    p_asset text,
    p_market text,
    p_occurred_at timestamptz,
    p_payload jsonb,
    p_source text default 'deriv_bot'
) returns deriv.trade_events
language plpgsql
security definer
as $$
declare
    inserted deriv.trade_events;
begin
    insert into deriv.trade_events (
        id, signal_id, event_type, idempotency_key, asset, market, occurred_at, payload, source
    )
    values (
        p_id, p_signal_id, p_event_type, p_idempotency_key, p_asset, p_market, p_occurred_at, coalesce(p_payload, '{}'::jsonb), p_source
    )
    on conflict (idempotency_key) do update
      set idempotency_key = excluded.idempotency_key
    returning * into inserted;

    return inserted;
end;
$$;

comment on schema deriv is 'Deriv Rise/Fall event-sourced operational schema. Legacy IQ Option JSON tables remain outside this schema.';
comment on table deriv.trade_events is 'Canonical event stream. No raw ticks, candles or repeated analysis cycles are stored here.';
