# Render deploy

## Build command

```bash
python -m pip install --upgrade pip && pip install -r requirements.txt
```

## Start command

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Required environment

Set Python explicitly. Render otherwise can pick a newer runtime that forces
`pydantic-core` to compile from source.

- `PYTHON_VERSION=3.12.8`

Use `.env.example` as the source of truth. Keep these defaults unless you are deliberately enabling a gated test:

- `DERIV_ACCOUNT_MODE=DEMO`
- `BROKER_TRADING_ENABLED=false`
- `RUN_LIVE_DERIV_BUY_TESTS=false`
- `LIVE_TEST_ALLOW_REAL=false`

Never expose `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SECRET_KEY`, Deriv tokens, or Telegram tokens to browser code.
