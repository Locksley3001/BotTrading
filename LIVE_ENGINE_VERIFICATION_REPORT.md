# Live engine verification report

Generated: 2026-07-01 12:25 America/Bogota.

## Result

- Live Deriv public market study: OK.
- Real candle endpoint by market: OK.
- Chart switching backend support: OK.
- Virtual account: OK, configured as `initial=100`, `stake=10`, `target=150`.
- Virtual operations from live signals: OK.
- Telegram signal projection: OK.
- Broker real/demo buy: BLOCKED, missing official Deriv API credentials.

## Deriv API credentials

Current environment status:

- `DERIV_APP_ID`: missing.
- `DERIV_ACCOUNT_ID`: missing.
- `DERIV_ACCESS_TOKEN`: missing.
- `DERIV_LEGACY_API_TOKEN`: missing.
- `DERIV_ACCOUNT_MODE`: `DEMO`.

The project has `DERIV_EMAIL` and `DERIV_PASSWORD`, but those are not enough for safe Deriv API buys. The broker toggle correctly rejects activation with `missing_deriv_api_credentials`.

## Live signal observed

First live signal opened by the engine:

- `signal_id`: `sig_445dee5793b449b3bf3974f158143af0`
- Market: `frxXAGUSD` / Silver/USD.
- Direction: `FALL`.
- Deriv contract type: `PUT`.
- Duration: `5m`.
- Stake: `10`.
- Payout: `17.39`.
- Entry spot: `59.9955`.
- Exit spot: `59.9765`.
- Virtual outcome: `win`.
- Telegram signal message: recorded in `data/deriv_telegram_events.jsonl`.

## Virtual account status during test

The live engine opened multiple market-derived virtual trades while running. At verification time:

- Settled virtual trades: `4`.
- Open virtual trades: `5`.
- Balance: `37.39`.

The engine now blocks duplicate open trades on the same market and limits concurrent virtual trades with `VIRTUAL_MAX_CONCURRENT_TRADES=5`.

## Chart switching check

The endpoint below returns real 1-minute Deriv candles for each selected market:

- `/api/markets/frxXAUUSD/candles`
- `/api/markets/frxXAGUSD/candles`
- `/api/markets/frxEURUSD/candles`

The frontend now binds clicks on `.market-item` to `loadCandlesForSelected()`, updates `#chartTitle`, and redraws the chart with candles from the selected symbol.
