# Render deploy

## Build command

```bash
pip install -r requirements.txt
```

## Start command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Required environment

Use `.env.example` as the source of truth. Keep these defaults unless you are deliberately enabling a gated test:

- `DERIV_ACCOUNT_MODE=DEMO`
- `BROKER_TRADING_ENABLED=false`
- `RUN_LIVE_DERIV_BUY_TESTS=false`
- `LIVE_TEST_ALLOW_REAL=false`

Never expose `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SECRET_KEY`, Deriv tokens, or Telegram tokens to browser code.
