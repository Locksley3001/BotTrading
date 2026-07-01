-- Optional fallback for Supabase projects where only the `public` schema is exposed
-- through PostgREST. If you use this migration, set:
--
-- SUPABASE_DERIV_SCHEMA=public
-- SUPABASE_EVENT_TABLE=deriv_trade_events
-- SUPABASE_SIGNAL_TABLE=deriv_signals
-- SUPABASE_BROKER_ORDER_TABLE=deriv_broker_orders
-- SUPABASE_TELEGRAM_EVENT_TABLE=deriv_telegram_events
-- SUPABASE_MARKET_CATALOG_TABLE=deriv_market_catalog

create table if not exists public.deriv_trade_events (
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

create table if not exists public.deriv_signals (
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

create table if not exists public.deriv_broker_orders (
    signal_id text primary key references public.deriv_signals(signal_id) on delete restrict,
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

create table if not exists public.deriv_telegram_events (
    signal_id text not null,
    message_type text not null,
    chat_id_hash text not null,
    sent_at timestamptz not null default now(),
    telegram_message_id text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    primary key (signal_id, message_type)
);

create table if not exists public.deriv_virtual_trades (
    signal_id text primary key references public.deriv_signals(signal_id) on delete restrict,
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

create table if not exists public.deriv_market_catalog (
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

create index if not exists public_deriv_trade_events_signal_id_idx on public.deriv_trade_events(signal_id);
create index if not exists public_deriv_trade_events_asset_idx on public.deriv_trade_events(asset);
create index if not exists public_deriv_trade_events_event_type_idx on public.deriv_trade_events(event_type);
create index if not exists public_deriv_signals_asset_idx on public.deriv_signals(asset);
create index if not exists public_deriv_signals_status_idx on public.deriv_signals(status);
create index if not exists public_deriv_virtual_trades_status_idx on public.deriv_virtual_trades(status);
create index if not exists public_deriv_market_catalog_enabled_idx on public.deriv_market_catalog(enabled);
