# Synchronization contract

Canonical flow:

```text
market_tick -> signal_decision -> entry_validation -> proposal -> buy -> contract_status -> outcome -> telegram_projection -> dashboard_projection
```

Rules:

- Every operable signal has exactly one `signal_id`.
- `trade_events.idempotency_key` prevents duplicate critical events.
- Telegram only projects canonical events and deduplicates by `(signal_id, message_type)`.
- A signal with a rejected proposal cannot become a real virtual win/loss.
- A bought Deriv contract cannot later become `aborted`; it must settle or reconcile as a discrepancy.
- Supabase stores compact decision/order/outcome events. Raw ticks, individual candles and polling analysis snapshots are off by default.
