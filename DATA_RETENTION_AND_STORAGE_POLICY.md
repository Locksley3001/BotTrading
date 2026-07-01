# Data retention and storage policy

Stored by default:

- Canonical trade events.
- Approved or shadow signals.
- Broker orders.
- Telegram projection receipts.
- Compact Deriv market catalog snapshots.

Not stored by default:

- Raw ticks.
- Every candle.
- Every polling analysis cycle.
- Large mutable JSON state files.

Retention:

- `SUPABASE_EVENT_RETENTION_DAYS=365` for canonical events.
- `SUPABASE_RAW_DATA_RETENTION_HOURS=0` because raw market data is disabled by default.
- Legacy IQ Option JSON remains read-only unless an explicit migration is approved.

Growth control:

- Row growth follows actual decisions and broker events, not tick frequency.
- Local JSONL files are an offline queue and audit trail, not the production source of truth.
