# Deriv Rise/Fall Bot

Proyecto nuevo para operar y auditar contratos Rise/Fall de Deriv sobre mercados no sintéticos. La arquitectura parte de un evento canónico por `signal_id`, de modo que broker, saldo virtual, Telegram, Supabase y dashboard sean proyecciones del mismo hecho.

## Estado de seguridad

- Trading real y compras DEMO están apagados por defecto.
- La cuenta virtual arranca en `100 USD`, opera `10 USD` por señal y reinicia al llegar a `150 USD` o si queda sin saldo suficiente.
- El archivo `.env.txt` local puede contener secretos, pero `.gitignore` impide versionarlo.
- El código no contiene credenciales reales.
- Supabase legacy (`bot_state_files`) se lee solo para compatibilidad; Deriv usa tablas nuevas en el schema `deriv`.

## Arranque local

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Abrir `http://127.0.0.1:8000`.

## Pruebas

```bash
pytest
python scripts/run_live_deriv_public_tests.py
python scripts/test_supabase_connection.py
python scripts/test_telegram.py
python scripts/run_live_deriv_demo_tests.py
```

Las pruebas públicas de Deriv no compran. Las pruebas autenticadas quedan bloqueadas hasta configurar `DERIV_APP_ID`, `DERIV_ACCOUNT_ID` y `DERIV_ACCESS_TOKEN`, o el perfil legacy con token API.

## Migración Supabase

Aplicar `supabase/migrations/001_deriv_schema.sql` en el SQL editor de Supabase o mediante la CLI del proyecto. Después, exponer el schema `deriv` en Supabase API settings para que PostgREST acepte `Accept-Profile: deriv`. La service role key permite operar por REST, pero no debe usarse desde el frontend ni para intentar DDL arbitrario desde el backend.

## Endpoints principales

- `GET /health`
- `GET /api/state`
- `GET /api/events?signal_id=...`
- `GET /api/signals`
- `GET /api/performance`
- `GET /api/deriv/market-catalog`
- `POST /api/deriv/market-discovery`
- `POST /api/deriv/verify-contracts`
- `POST /api/telegram/test`
- `WS /ws`
