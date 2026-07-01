# Prompt maestro para crear el bot nuevo en Deriv Rise/Fall

Usa este prompt con una IA/agente de desarrollo para crear desde cero una nueva version del bot, migrada a Deriv, usando Rise/Fall sobre mercados no sinteticos. El proyecto puede usar el mismo proyecto Supabase existente como infraestructura, pero debe crear tablas/schema nuevos para Deriv; la base actual de IQ Option debe quedar solo como historico legacy o fuente opcional de consulta/migracion.

Fecha de investigacion tecnica: 2026-07-01, America/Bogota.

Importante sobre secretos:
- No escribas credenciales reales, correos, contrasenas, tokens de Telegram, access tokens de Deriv ni claves de Supabase dentro del codigo, commits, README, logs ni respuestas.
- Usa las mismas variables de entorno existentes y lee valores desde `.env`, Render o el gestor seguro de secretos.
- Si el entorno ya contiene `.env`, puedes usarlo para ejecutar pruebas, pero debes enmascarar valores sensibles en toda salida.
- Donde haga falta un valor sensible, usa placeholders como `<DERIV_ACCESS_TOKEN_REAL>`, `<DERIV_CLIENT_ID_REAL>`, `<TELEGRAM_BOT_TOKEN_REAL>` y `<SUPABASE_SERVICE_ROLE_KEY_REAL>`.

---

## Rol

Actua como arquitecto senior, desarrollador backend async, integrador de brokers y lider tecnico de QA. Crea un proyecto nuevo desde cero para operar opciones digitales Rise/Fall en Deriv, con FastAPI/Python, frontend operativo, Telegram y Supabase.

No reutilices la arquitectura defectuosa actual. Puedes reutilizar la idea de negocio, la tecnica base y las variables de entorno, pero el diseno interno debe ser nuevo, event-sourced, idempotente y probado desde el inicio. La informacion historica de IQ Option puede conservarse como archivo legacy, pero no debe mezclarse con Deriv como base operativa ni como aprendizaje equivalente.

Objetivo central:
- El sistema debe operar en Deriv con ejecucion inmediata y medible entre senal, propuesta, compra y confirmacion.
- Las operaciones virtuales, las ordenes de Deriv, el historial del proyecto, Telegram y Supabase deben salir del mismo evento canonico.
- No puede haber historiales paralelos que se contradigan.
- Si Deriv no puede ejecutar exactamente la operacion esperada por mercado cerrado, contrato no disponible, duracion invalida, payout insuficiente, token vencido, saldo insuficiente, latencia, rechazo o desconexion, el sistema debe registrarlo como discrepancia explicita y no inventar un resultado virtual equivalente.
- El nuevo proyecto debe crear una base logica nueva para Deriv: tablas nuevas, indices nuevos, constraints nuevas y politicas de retencion nuevas. Los JSON/tablas legacy de IQ Option no se borran, pero quedan fuera del nucleo operativo.

---

## Diferencia critica frente a IQ Option

No hagas una migracion mecanica de "CALL/PUT IQ Option" a "Rise/Fall Deriv".

En Deriv:
- El contrato Rise/Fall se obtiene mediante `contract_category=callput`.
- Los tipos tecnicos principales son `CALL` y `PUT`, pero la UI y el dominio deben hablar en terminos `RISE` y `FALL`.
- La semantica correcta debe verificarse siempre con `proposal.longcode` antes de operar:
  - `CALL` debe significar que gana si el precio de salida es estrictamente mayor que el precio de entrada.
  - `PUT` debe significar que gana si el precio de salida es estrictamente menor que el precio de entrada.
- No codifiques esta equivalencia a ciegas. La documentacion legacy de Deriv tiene texto contradictorio en una seccion de Rise/Fall; por eso el sistema debe ejecutar una prueba viva de mapping al arrancar y fallar cerrado si el longcode no confirma la direccion.
- En Rise/Fall estricto, si salida es igual a entrada, no debe tratarse como `push` salvo que el broker lo confirme o se use explicitamente `callputequal` (`CALLE`/`PUTE`). Por defecto usa `callput` estricto y deja que el resultado canonico venga de Deriv.

Regla de direccion interna:

```text
SignalDirection.RISE -> Deriv contract_type CALL -> gana si exit_spot > entry_spot
SignalDirection.FALL -> Deriv contract_type PUT  -> gana si exit_spot < entry_spot
```

Mantener compatibilidad de lectura con senales antiguas:

```text
CALL antiguo -> RISE
PUT antiguo  -> FALL
```

Pero en codigo nuevo, modelos, UI, Telegram y documentacion de Deriv deben usar `RISE`/`FALL`, no "sube/baja" ni nombres ambiguos.

---

## Hallazgos verificados sobre Deriv al 2026-07-01

La API publica actual de Deriv respondio correctamente en:

```text
wss://api.derivws.com/trading/v1/options/ws/public
```

Consultas realizadas:
- `ping`
- `active_symbols`
- `contracts_for`
- `proposal`
- `ticks_history`

Resultado de mercado:
- Total de simbolos activos reportados: 78.
- Simbolos no sinteticos detectados: 43.
- Mercados no sinteticos detectados: `forex`, `commodities`, `indices`, `cryptocurrency`.
- Simbolos no sinteticos con `contract_category=callput` y ambos `CALL`/`PUT`: 41.
- Criptomonedas detectadas (`cryBTCUSD`, `cryETHUSD`) solo devolvieron `MULTUP`/`MULTDOWN`, no Rise/Fall `CALL`/`PUT`; no deben usarse para este bot hasta que `contracts_for` confirme lo contrario.
- `ticks_history` con velas acepta granularidad oficial desde 60 segundos. Las granularidades 30 y 45 segundos fueron rechazadas. Si se requieren velas de 30s/45s, deben agregarse internamente desde ticks, pero no deben usarse como duracion de contrato si `proposal` las rechaza.

Resultado de duraciones Rise/Fall en mercados no sinteticos:
- Forex: Rise/Fall intradia minimo `15m`, maximo `1d`.
- Indices: Rise/Fall intradia minimo `15m`, maximo `1h`.
- Oro y plata: Rise/Fall intradia minimo `5m`, maximo `1d`.
- Palladium y Platinum: solo diario en la consulta realizada.
- 1 minuto fue rechazado por `proposal` para `frxEURUSD`, `frxXAUUSD` y `OTC_SPC` con error "Trading is not offered for this duration."

Esto significa:
- El bot actual de 30s/1m no puede trasladarse tal cual a Deriv si se excluyen sinteticos.
- La estrategia debe adaptarse desde el inicio a 5m para metales y 15m para forex/indices.
- Si el usuario insiste en 30s/1m en Deriv, solo puede habilitarse despues de una prueba `contracts_for` + `proposal` que lo permita en mercados no sinteticos. Al 2026-07-01 la API publica no lo permitio en los mercados reales probados.

---

## Mercados Deriv recomendados para este bot

El sistema nunca debe operar `market=synthetic_index`.

Modo inicial recomendado:

1. Metales liquidos para expiracion 5m:
   - `frxXAUUSD` - Gold/USD - minimo intradia `5m`.
   - `frxXAGUSD` - Silver/USD - minimo intradia `5m`.

2. Forex majors para expiracion 15m:
   - `frxEURUSD` - EUR/USD.
   - `frxGBPUSD` - GBP/USD.
   - `frxUSDJPY` - USD/JPY.
   - `frxAUDUSD` - AUD/USD.
   - `frxUSDCAD` - USD/CAD.
   - `frxUSDCHF` - USD/CHF.
   - `frxEURJPY` - EUR/JPY.
   - `frxGBPJPY` - GBP/JPY.

3. Forex minors solo despues de backtest y paper/live demo:
   - `frxAUDCAD`, `frxAUDCHF`, `frxAUDJPY`, `frxAUDNZD`.
   - `frxEURAUD`, `frxEURCAD`, `frxEURCHF`, `frxEURGBP`, `frxEURNZD`.
   - `frxGBPAUD`, `frxGBPCAD`, `frxGBPCHF`, `frxGBPNZD`.
   - `frxNZDJPY`, `frxNZDUSD`, `frxUSDMXN`, `frxUSDPLN`.

4. Indices con cautela y apagados por defecto:
   - `OTC_SPC` - US 500.
   - `OTC_NDX` - US Tech 100.
   - `OTC_DJI` - Wall Street 30.
   - `OTC_GDAXI` - Germany 40.
   - `OTC_FTSE` - UK 100.
   - `OTC_N225` - Japan 225.
   - `OTC_FCHI`, `OTC_SX5E`, `OTC_AEX`, `OTC_SSMI`, `OTC_AS51`, `OTC_HSI`.

Notas sobre indices:
- En la consulta publica aparecen como `market=indices`, no como `synthetic_index`.
- Sin embargo sus simbolos y submarkets contienen `OTC`. Por prudencia, no deben habilitarse como "mercados reales principales" hasta que el equipo confirme producto, horarios, calidad de ticks y condiciones de Deriv para la cuenta usada.
- Si el usuario quiere maxima pureza de "no sinteticos/no derivados internos", el modo conservador debe operar solo `forex` y `commodities`.

Mercados excluidos por defecto:
- Todo simbolo con `market=synthetic_index`.
- Todo subgrupo `synthetics`, `baskets`, `forex_basket`.
- Todo submarket `random_index`, `crash_index`, `jump_index`, `step_indices`, `range_break`, `derived_index`, `forex_basket`.
- Volatility, Boom, Crash, Jump, Step, Range Break, DEX, baskets.
- Criptomonedas para Rise/Fall mientras `contracts_for` no devuelva `contract_category=callput` con `CALL` y `PUT`.

El proyecto debe descubrir mercados dinamicamente en cada arranque. La lista anterior es una semilla, no una verdad fija.

---

## Stack tecnico obligatorio

Backend:
- Python 3.12.8.
- FastAPI.
- Uvicorn/Gunicorn para produccion.
- `pydantic-settings` para configuracion.
- `python-dotenv` para desarrollo local.
- AsyncIO real de punta a punta.
- `httpx` para REST OAuth/OTP de Deriv.
- `websockets` para WebSocket directo con Deriv.
- `python-telegram-bot` version moderna y fijada, o `aiogram` si se justifica.
- `supabase-py` oficial para operaciones normales de Supabase.
- SQL/RPC transaccional en Postgres para append de eventos criticos.
- `pytest`, `pytest-asyncio`, `respx`/mocks HTTP y mocks WebSocket.

Broker Deriv:
- Libreria recomendada principal: usar WebSocket directo con `websockets` y REST con `httpx`, siguiendo la API oficial actual de Deriv.
- No depender como nucleo de `python_deriv_api`, porque el repositorio `deriv-com/python-deriv-api` aparece archivado desde 2026-03-26. Puede revisarse solo como referencia o fallback legacy, pero el adaptador productivo debe hablar con la API oficial directamente.
- Crear `DerivBrokerAdapter` aislado, testeable y reemplazable.
- Soportar dos perfiles de API:
  - `DERIV_API_PROFILE=current_oauth`: perfil recomendado, usa `api.derivws.com`, OAuth2 PKCE y OTP.
  - `DERIV_API_PROFILE=legacy_token`: fallback controlado, usa `wss://ws.derivws.com/websockets/v3?app_id=...` y `authorize` con token legacy, solo si el equipo decide usarlo.

Supabase:
- Puedes usar el mismo proyecto Supabase existente, pero no reutilices las tablas operativas actuales como fuente principal de Deriv.
- Crear tablas nuevas desde cero para Deriv, preferiblemente en schema separado `deriv` o con prefijo claro `deriv_`.
- Mantener tablas legacy de IQ Option en modo historico/read-only salvo migracion controlada.
- Usar `create_client(SUPABASE_URL, SUPABASE_KEY)` para lecturas/escrituras normales.
- El backend puede usar service role/secret solo del lado servidor.
- Nunca exponer service role/secret al frontend.
- Mantener compatibilidad con `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_KEY`, `SUPABASE_ANON_KEY`.
- Sugerir `SUPABASE_SECRET_KEY` como nuevo nombre preferido para servidor.

Frontend:
- React/Vite + TypeScript recomendado, o frontend estatico moderno si el equipo lo prefiere.
- Debe ser dashboard operativo, no landing page.
- Debe usar UTF-8 real.
- Debe separar visualmente: mercado, timeframe, contrato Deriv, mapping Rise/Fall, payout, latency, broker status, Supabase, Telegram, aprendizaje real y sombra.

No usar:
- TradingView, Twelve Data, Binance u otra fuente externa como fuente principal de velas.
- Telegram como fuente para ejecutar operaciones.
- Archivos JSON gigantes como fuente principal de verdad en produccion.
- Mercados sinteticos de Deriv.

---

## Variables de entorno que se deben conservar

Mantener compatibilidad con estas variables existentes aunque el broker cambie:

```env
IQ_OPTION_EMAIL=<IQ_OPTION_EMAIL_REAL_LEGACY>
IQ_OPTION_PASSWORD=<IQ_OPTION_PASSWORD_REAL_LEGACY>
IQ_OPTION_2FA_CODE=
IQ_OPTION_BALANCE_MODE=PRACTICE

TELEGRAM_BOT_TOKEN=<TELEGRAM_BOT_TOKEN_REAL>
TELEGRAM_CHAT_ID=<TELEGRAM_CHAT_ID_REAL>

MARKETS=frxXAUUSD,frxXAGUSD,frxEURUSD,frxGBPUSD,frxUSDJPY,frxAUDUSD
DISABLED_MARKETS=OTC_HSI,cryBTCUSD,cryETHUSD
DEFAULT_TIMEFRAME=300
POLL_INTERVAL_SECONDS=0.75
CANDLE_COUNT=120
SIGNAL_COOLDOWN_SECONDS=300

DATA_DIR=data
SIGNAL_HISTORY_LIMIT=500
API_SIGNAL_LIMIT=500

LEARNING_ENABLED=true
LEARNING_UPDATE_ENABLED=true
LEARNING_MIN_HISTORY=30
LEARNING_MIN_WIN_RATE=58
LEARNING_MIN_RULE_SAMPLES=5
LEARNING_MIN_SIMILARITY_SAMPLES=4
LEARNING_EXPLORATION_INTERVAL=20

ADVANTAGE_FILTER_ENABLED=true
ADVANTAGE_FILTER_MIN_WIN_RATE=60
ADVANTAGE_FILTER_MIN_SAMPLES=30
ADVANTAGE_FILTER_MIN_FACTOR_SCORE=4

VIRTUAL_INITIAL_BALANCE=50000
VIRTUAL_TARGET_BALANCE=500000
VIRTUAL_CAUTIOUS_STAKE=10000
VIRTUAL_SAFE_STAKE=20000
VIRTUAL_PAYOUT_RATE=0.85

BROKER_TRADING_ENABLED=false
BROKER_TRADE_ENTRY_WINDOW_SECONDS=3

SUPABASE_URL=https://kwbqjullmtrankjpmwfs.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<SUPABASE_SERVICE_ROLE_KEY_REAL>
SUPABASE_SERVICE_KEY=
SUPABASE_KEY=
SUPABASE_ANON_KEY=
SUPABASE_STATE_ENABLED=true
SUPABASE_STATE_TABLE=bot_state_files
SUPABASE_VERSIONS_TABLE=bot_state_file_versions
SUPABASE_BOOTSTRAP_LOCAL=false
SUPABASE_TIMEOUT_SECONDS=12
SUPABASE_REMOTE_SAVE_INTERVAL_SECONDS=60
SUPABASE_VERSIONING_ENABLED=false
SUPABASE_VERSION_INTERVAL_SECONDS=3600
```

Mapeo de variables legacy:
- `REMOTE_STATE_ENABLED` esta obsoleta; mapear a `SUPABASE_STATE_ENABLED` solo por compatibilidad y emitir warning.
- `SUPABASE_STATE_BACKUP_TABLE` esta obsoleta; mapear a `SUPABASE_VERSIONS_TABLE` solo por compatibilidad y emitir warning.
- Las variables `IQ_OPTION_*` deben quedar como legacy/read-only; no deben ser necesarias para operar Deriv.

---

## Variables nuevas obligatorias para Deriv

Agregar al `.env.example` y a Render:

```env
PYTHON_VERSION=3.12.8
APP_ENV=production
LOG_LEVEL=INFO

BROKER_PROVIDER=deriv

DERIV_API_PROFILE=current_oauth
DERIV_PUBLIC_WS_URL=wss://api.derivws.com/trading/v1/options/ws/public
DERIV_REST_BASE_URL=https://api.derivws.com
DERIV_AUTH_BASE_URL=https://auth.deriv.com
DERIV_APP_ID=<DERIV_APP_ID_REAL>
DERIV_CLIENT_ID=<DERIV_CLIENT_ID_REAL>
DERIV_REDIRECT_URI=<DERIV_REDIRECT_URI_REAL>
DERIV_ACCOUNT_ID=<DERIV_ACCOUNT_ID_REAL>
DERIV_ACCESS_TOKEN=<DERIV_ACCESS_TOKEN_REAL>
DERIV_REFRESH_TOKEN=
DERIV_LEGACY_API_TOKEN=
DERIV_CURRENCY=USD
DERIV_ACCOUNT_MODE=DEMO

DERIV_ALLOW_SYNTHETIC_MARKETS=false
DERIV_ALLOWED_MARKETS=forex,commodities
DERIV_OPTIONAL_MARKETS=indices
DERIV_EXCLUDED_MARKETS=synthetic_index
DERIV_EXCLUDED_SUBMARKETS=random_index,crash_index,jump_index,step_indices,range_break,forex_basket
DERIV_EXCLUDED_SYMBOL_PATTERNS=R_,1HZ,BOOM,CRASH,JUMP,STEP,WLDAUD,WLDEUR,WLDGBP,WLDUSD
DERIV_MARKET_DISCOVERY_ON_START=true
DERIV_VERIFY_CONTRACTS_ON_START=true
DERIV_VERIFY_CONTRACT_MAPPING_ON_START=true

DERIV_CONTRACT_CATEGORY=callput
DERIV_RISE_CONTRACT_TYPE=CALL
DERIV_FALL_CONTRACT_TYPE=PUT
DERIV_ALLOW_EQUALS=false
DERIV_RISE_EQUAL_CONTRACT_TYPE=CALLE
DERIV_FALL_EQUAL_CONTRACT_TYPE=PUTE

DERIV_PRIMARY_MARKETS=frxXAUUSD,frxXAGUSD,frxEURUSD,frxGBPUSD,frxUSDJPY,frxAUDUSD
DERIV_METALS_DURATION=5
DERIV_METALS_DURATION_UNIT=m
DERIV_FOREX_DURATION=15
DERIV_FOREX_DURATION_UNIT=m
DERIV_INDICES_DURATION=15
DERIV_INDICES_DURATION_UNIT=m
DERIV_DEFAULT_DURATION=15
DERIV_DEFAULT_DURATION_UNIT=m

DERIV_STAKE_BASIS=stake
DERIV_MIN_STAKE=1
DERIV_MAX_STAKE=10000
DERIV_MIN_PAYOUT_RATE=0.65
DERIV_MAX_PRICE_SLIPPAGE_PERCENT=2.0
DERIV_PROPOSAL_SUBSCRIBE=true
DERIV_PROPOSAL_MAX_AGE_MS=1500
DERIV_BUY_DEADLINE_MS=1500
DERIV_CONFIRM_TIMEOUT_SECONDS=10
DERIV_CONTRACT_SETTLE_TIMEOUT_SECONDS=1200
DERIV_BROKER_RECONCILE_INTERVAL_SECONDS=30
DERIV_MAX_CONCURRENT_BUYS=5

BROKER_SYNC_STRICT_MODE=true
BROKER_MIN_LEAD_SECONDS=0
BROKER_ORDER_DEADLINE_MS=1500
BROKER_CONFIRM_TIMEOUT_SECONDS=10
BROKER_RECONCILE_INTERVAL_SECONDS=30
BROKER_MAX_CONCURRENT_ORDERS=5
BROKER_MARKET_OPEN_CHECK_ENABLED=true

SERVER_TIME_SYNC_MAX_DRIFT_MS=750
MARKET_STREAM_WARMUP_SECONDS=10

SUPABASE_SECRET_KEY=
SUPABASE_SCHEMA=public
SUPABASE_DERIV_SCHEMA=deriv
SUPABASE_EVENT_TABLE=trade_events
SUPABASE_SIGNAL_TABLE=signals
SUPABASE_BROKER_ORDER_TABLE=broker_orders
SUPABASE_TELEGRAM_EVENT_TABLE=telegram_events
SUPABASE_MARKET_CATALOG_TABLE=deriv_market_catalog
SUPABASE_LEGACY_MIGRATION_ENABLED=true
SUPABASE_LEGACY_READ_ONLY=true
SUPABASE_LEGACY_SNAPSHOT_INTERVAL_SECONDS=300
SUPABASE_SAVE_TICKS=false
SUPABASE_SAVE_CANDLES=false
SUPABASE_SAVE_ANALYSIS_SNAPSHOTS=false
SUPABASE_ANALYSIS_SNAPSHOT_INTERVAL_SECONDS=300
SUPABASE_EVENT_RETENTION_DAYS=365
SUPABASE_RAW_DATA_RETENTION_HOURS=0

TELEGRAM_ENABLED=true
TELEGRAM_MIN_SCORE=7
TELEGRAM_SUMMARY_BATCH_SIZE=5

RUN_LIVE_DERIV_PUBLIC_TESTS=true
RUN_LIVE_DERIV_DEMO_TESTS=false
RUN_LIVE_DERIV_BUY_TESTS=false
LIVE_TEST_MARKETS=frxXAUUSD,frxXAGUSD,frxEURUSD
LIVE_TEST_MAX_STAKE=1
LIVE_TEST_ALLOW_REAL=false
```

Reglas de seguridad:
- `DERIV_ACCOUNT_MODE=DEMO` por defecto.
- `BROKER_TRADING_ENABLED=false` por defecto.
- `RUN_LIVE_DERIV_BUY_TESTS=false` por defecto.
- Nunca ejecutar compras en REAL salvo que existan simultaneamente:
  - `DERIV_ACCOUNT_MODE=REAL`
  - `LIVE_TEST_ALLOW_REAL=true`
  - confirmacion explicita en UI o CLI
  - registro de auditoria `real_trade_user_confirmation`

---

## Conexion con Deriv

Implementa `DerivBrokerAdapter` con WebSocket directo y REST.

### Public market data

Conectar sin autenticacion:

```python
import json
import websockets

PUBLIC_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"

async with websockets.connect(PUBLIC_WS_URL, ping_interval=20, close_timeout=5) as ws:
    await ws.send(json.dumps({"ping": 1, "req_id": 1}))
    response = json.loads(await ws.recv())
```

Usar el socket publico para:
- `ping`
- `time`
- `active_symbols`
- `contracts_for`
- `contracts_list`
- `ticks`
- `ticks_history`
- `proposal` sin compra, para validar disponibilidad y mapping

### OAuth2 actual recomendado

Usar OAuth 2.0 Authorization Code + PKCE:

1. Generar `code_verifier`, `code_challenge` S256 y `state`.
2. Redirigir usuario a:

```text
https://auth.deriv.com/oauth2/auth
```

con:

```text
response_type=code
client_id=<DERIV_CLIENT_ID>
redirect_uri=<DERIV_REDIRECT_URI>
scope=trade
state=<RANDOM_STATE>
code_challenge=<PKCE_CHALLENGE>
code_challenge_method=S256
```

3. En callback backend, validar `state`.
4. Intercambiar `code` por token usando `httpx`:

```text
POST https://auth.deriv.com/oauth2/token
Content-Type: application/x-www-form-urlencoded
```

5. Guardar token de forma segura. No loggear token.
6. Obtener cuentas:

```text
GET https://api.derivws.com/trading/v1/options/accounts
Authorization: Bearer <DERIV_ACCESS_TOKEN>
```

7. Obtener OTP para WebSocket autenticado:

```text
POST https://api.derivws.com/trading/v1/options/accounts/{account_id}/otp
Authorization: Bearer <DERIV_ACCESS_TOKEN>
Deriv-App-ID: <DERIV_APP_ID>
```

8. Conectar al `url` devuelto por OTP, por ejemplo:

```text
wss://api.derivws.com/trading/v1/options/ws/demo?otp=...
```

Usar socket autenticado para:
- `balance`
- `portfolio`
- `profit_table`
- `statement`
- `transaction`
- `buy`
- `proposal_open_contract`
- `sell` si se implementa cierre temprano

### Perfil legacy opcional

Si el equipo usa tokens legacy de Deriv:
- Encapsularlo en otro adapter o transport.
- Usar endpoint:

```text
wss://ws.derivws.com/websockets/v3?app_id=<DERIV_APP_ID>
```

- Autorizar con:

```json
{"authorize": "<DERIV_LEGACY_API_TOKEN>", "req_id": 1}
```

No mezclar respuestas de current/legacy sin normalizarlas.

---

## Descubrimiento obligatorio de mercados y contratos

No hardcodear mercados como unica fuente.

Al arrancar:

1. Llamar:

```json
{"active_symbols": "brief", "req_id": 1}
```

2. Filtrar:

```text
exchange_is_open == 1
is_trading_suspended == 0
market in DERIV_ALLOWED_MARKETS + DERIV_OPTIONAL_MARKETS
market != synthetic_index
submarket not in DERIV_EXCLUDED_SUBMARKETS
symbol no coincide con DERIV_EXCLUDED_SYMBOL_PATTERNS
```

3. Por cada simbolo candidato llamar:

```json
{"contracts_for": "<underlying_symbol>", "req_id": 2}
```

4. Mantener solo simbolos con:

```text
contract_category == callput
contract_type CALL disponible
contract_type PUT disponible
duracion configurada aceptada por min_contract_duration/max_contract_duration
```

5. Confirmar con `proposal` para ambas direcciones:

```json
{
  "proposal": 1,
  "amount": 10,
  "basis": "stake",
  "contract_type": "CALL",
  "currency": "USD",
  "duration": 15,
  "duration_unit": "m",
  "underlying_symbol": "frxEURUSD",
  "req_id": 3
}
```

6. Verificar `proposal.longcode`:
- Para `CALL`, debe contener idea de "strictly higher".
- Para `PUT`, debe contener idea de "strictly lower".
- Si no se cumple, bloquear trading real y marcar `contract_mapping_failed`.

7. Persistir resultado en tabla `deriv_market_catalog`.

Campos minimos `deriv_market_catalog`:
- `symbol` unique.
- `display_name`.
- `market`.
- `submarket`.
- `subgroup`.
- `pip_size`.
- `exchange_is_open`.
- `is_trading_suspended`.
- `supports_rise_fall`.
- `rise_contract_type`.
- `fall_contract_type`.
- `min_intraday_duration`.
- `max_intraday_duration`.
- `min_daily_duration`.
- `max_daily_duration`.
- `last_contracts_for_json`.
- `last_proposal_check_json`.
- `last_verified_at`.
- `verification_status`.
- `blocked_reason`.

El dashboard debe mostrar este catalogo y explicar por que un mercado esta habilitado o bloqueado.

---

## Arquitectura de datos obligatoria

No uses varios JSON independientes como fuente principal.

Crea un modelo event-sourced o una maquina de estados atomica en Supabase, pero con tablas nuevas para Deriv. No construyas Deriv sobre las tablas operativas antiguas de IQ Option.

Regla de volumen de datos:
- No guardar cada tick en Supabase.
- No guardar cada vela en Supabase.
- No guardar cada ciclo de analisis en Supabase.
- No guardar snapshots repetitivos del dashboard en cada polling.
- Supabase debe guardar solo eventos de negocio, decisiones, ordenes, resultados, catalogo de mercados, reglas de aprendizaje agregadas y snapshots compactos con retencion.
- Los ticks y velas viven en memoria, cache local temporal o archivos rotados fuera de Supabase si hace falta diagnostico.
- Si algun dia se requiere almacenar ticks/velas historicas, debe hacerse en almacenamiento especializado con particiones, TTL/retencion y agregacion, no en tablas operativas normales de Supabase.
- El diseno debe evitar repetir el problema anterior de crecimiento insostenible, donde se llegaron a guardar decenas de miles de registros en una semana por persistir informacion demasiado granular.

Crear preferiblemente:
- schema `deriv` con tablas nuevas; o
- tablas con prefijo `deriv_` si no se usa schema separado.

No mezclar directamente:
- `iq_option_legacy`
- `deriv_real_market`
- `deriv_shadow`
- `deriv_demo`
- `deriv_real`

Cada origen debe quedar etiquetado y separado para analisis.

### `signals`

- `signal_id` unique.
- `broker_provider`: `deriv`.
- `broker_source`: `deriv_real_market`.
- `asset`: simbolo Deriv, por ejemplo `frxXAUUSD`.
- `asset_display_name`.
- `market`.
- `submarket`.
- `direction`: `RISE` o `FALL`.
- `legacy_direction`: `CALL` o `PUT` solo para compatibilidad.
- `deriv_contract_type`: `CALL` o `PUT`.
- `contract_category`: `callput`.
- `timeframe`.
- `contract_duration`.
- `contract_duration_unit`.
- `created_at`.
- `analysis_candle_ts`.
- `entry_policy`: `immediate` o `next_candle_boundary`.
- `entry_at_planned`.
- `expires_at_planned`.
- `score`.
- `factor_score`.
- `confidence`.
- `stake_amount`.
- `status`.
- `is_shadow`.
- `blocked_reason`.
- `strategy_version`.
- `features_json`.
- `market_catalog_version`.

### `trade_events`

- `event_id` uuid.
- `signal_id`.
- `event_type`.
- `event_at`.
- `source`: `engine`, `deriv_public_ws`, `deriv_auth_ws`, `telegram`, `supabase`, `reconciler`, `ui`.
- `payload`.
- `idempotency_key` unique.

Ejemplos de `event_type`:
- `market_catalog_verified`.
- `signal_decided`.
- `signal_blocked`.
- `entry_validated`.
- `proposal_requested`.
- `proposal_received`.
- `proposal_rejected`.
- `buy_requested`.
- `buy_confirmed`.
- `buy_rejected`.
- `contract_opened`.
- `contract_settled`.
- `broker_reconciled`.
- `virtual_outcome_resolved`.
- `telegram_signal_sent`.
- `telegram_result_sent`.
- `discrepancy_detected`.

### `broker_orders`

- `signal_id` unique.
- `broker_provider`: `deriv`.
- `account_mode`: `DEMO` o `REAL`.
- `deriv_account_id`.
- `proposal_id`.
- `deriv_contract_id`.
- `transaction_id`.
- `status`: `proposal_requested`, `proposal_received`, `buy_requested`, `placed`, `rejected`, `expired_before_buy`, `stale_proposal`, `insufficient_funds`, `market_closed`, `duration_not_offered`, `payout_too_low`, `unknown`.
- `asset_sent`.
- `direction_sent`.
- `contract_type_sent`.
- `contract_category`.
- `stake_amount`.
- `basis`.
- `currency`.
- `duration`.
- `duration_unit`.
- `ask_price`.
- `payout`.
- `payout_rate`.
- `proposal_spot`.
- `proposal_spot_time`.
- `proposal_longcode`.
- `send_started_at`.
- `proposal_received_at`.
- `buy_started_at`.
- `confirmed_at`.
- `purchase_time`.
- `start_time`.
- `date_expiry`.
- `entry_tick`.
- `entry_tick_time`.
- `exit_tick`.
- `exit_tick_time`.
- `profit`.
- `sell_price`.
- `broker_result`.
- `error_code`.
- `error_message`.
- `latency_ms`.

### `virtual_outcomes`

- `signal_id` unique.
- `entry_price`.
- `entry_at`.
- `result_price`.
- `result_at`.
- `status`: `waiting_entry`, `pending`, `win`, `loss`, `equal_loss`, `push`, `aborted`, `broker_rejected`, `discrepancy`.
- `abort_reason`.
- `resolved_at`.
- `stake_amount`.
- `payout_rate`.
- `profit_amount`.
- `balance_after`.
- `resolution_source`: `deriv_proposal_open_contract`, `deriv_profit_table`, `virtual_tick_replay`, `manual_reconciliation`.

Regla:
- Cuando hay compra real en Deriv, el resultado canonico debe venir de Deriv (`proposal_open_contract`, `transaction`, `profit_table` o `statement`), no de una simulacion local.
- La simulacion local solo sirve para shadow, backtest y discrepancias.

### `telegram_events`

- unique `(signal_id, message_type)`.
- `message_type`: `signal`, `broker_sent`, `broker_rejected`, `result`, `summary`, `bankruptcy`, `target`, `discrepancy`.
- `sent_at`.
- `telegram_message_id`.
- `status`.
- `error`.

### `learning_rules` / `learning_examples`

- Separar aprendizaje por `broker_provider`.
- Separar ejemplos `iq_option_otc`, `deriv_real_market`, `shadow`.
- No mezclar metricas antiguas de IQ Option OTC como si fueran Deriv real.
- El aprendizaje legacy puede importarse como referencia de estrategia, pero debe tener peso bajo o modo sombra hasta acumular datos Deriv.

### Compatibilidad legacy

La base existente tiene `bot_state_files` con filas como:
- `performance.json`
- `learning.json`
- `signals.json`
- `telegram_notifications.json`
- `broker_trades.json`

El nuevo proyecto debe:
1. No depender de esas filas para operar Deriv.
2. Leer esas filas solo si `SUPABASE_LEGACY_MIGRATION_ENABLED=true`.
3. Mantenerlas por defecto en modo read-only.
4. Migrar solo datos utiles de resumen/aprendizaje si el equipo lo autoriza.
5. Validar conteos antes/despues si hay migracion.
6. Marcar todo origen antiguo como `iq_option_legacy`.
7. No usar datos IQ Option OTC como aprendizaje equivalente para Deriv real.
8. Mantener snapshot legacy opcional temporal.
9. No reescribir JSON multi-MB en cada tick.
10. Escribir eventos pequenos y atomicos en las tablas nuevas de Deriv.

---

## Regla principal de sincronizacion

Debe existir una sola fuente canonica:

```text
market_tick -> signal_decision -> entry_validation -> proposal -> buy -> contract_status -> outcome -> telegram_projection -> dashboard_projection
```

Cada paso debe registrar evento con el mismo `signal_id`.

Reglas duras:

1. Una senal operable no puede crearse si el mercado no paso `contracts_for` + `proposal`.
2. Una senal operable no puede crearse si la duracion configurada no esta ofrecida por Deriv.
3. La validacion de entrada debe ocurrir antes de `buy`.
4. Si `proposal` falla, no hay operacion virtual real; registrar `proposal_rejected`.
5. Si `proposal` es viejo, no comprar; registrar `stale_proposal`.
6. Si `payout_rate` es menor que `DERIV_MIN_PAYOUT_RATE`, no comprar; registrar `payout_too_low`.
7. Si se compra en Deriv, esa senal ya no puede terminar como `aborted`; debe resolver como win/loss/equal_loss o como discrepancia reconciliada.
8. Telegram no decide ni dispara operaciones. Solo observa eventos canonicos.
9. Dashboard no lee historiales paralelos. Lee proyecciones de eventos canonicos.
10. Si Supabase falla, usar cola local duradera e idempotente y reintentar sin duplicar eventos.
11. Si local y remoto divergen, registrar `discrepancy_detected` y resolver por reglas explicitas, no por sobrescritura silenciosa.

---

## Flujo de ejecucion Deriv

### Flujo sin compra real

1. Recibir ticks/candles Deriv.
2. Construir velas normalizadas.
3. Analizar estrategia.
4. Si hay senal, validar:
   - mercado abierto.
   - contrato Rise/Fall disponible.
   - duracion ofrecida.
   - mapping CALL/PUT verificado.
   - cooldown.
   - aprendizaje.
   - filtro de ventaja.
5. Registrar `signal_decided`.
6. Si `BROKER_TRADING_ENABLED=false`, resolver en modo virtual/shadow segun ticks y marcar `resolution_source=virtual_tick_replay`.

### Flujo con compra real DEMO/REAL

1. Recibir senal aprobada.
2. Validar entrada inmediatamente.
3. Solicitar `proposal`.
4. Verificar:
   - `proposal.id` presente.
   - `ask_price` dentro de stake esperado.
   - `payout_rate` aceptable.
   - `spot_time` reciente.
   - `longcode` confirma direccion.
   - `date_expiry` coincide con duracion.
5. Comprar:

```json
{"buy": "<proposal_id>", "price": <ask_price>, "req_id": 100}
```

6. Guardar respuesta `buy`:
   - `contract_id`
   - `transaction_id`
   - `purchase_time`
   - `start_time`
   - `buy_price`
   - `payout`
   - `balance_after`
7. Suscribirse a:

```json
{"proposal_open_contract": 1, "contract_id": <contract_id>, "subscribe": 1, "req_id": 101}
```

8. Resolver solo con datos canonicos de Deriv.
9. Comparar con historial local, Telegram y Supabase.

---

## Estrategia tecnica adaptada a Deriv

Mantener la filosofia original:
- Price action de corto plazo.
- CCI(20).
- Sobrecompra: `+100`.
- Sobreventa: `-100`.
- Fuerza.
- Continuidad.
- Cansancio.
- Rechazo.
- Cuerpo de vela.
- Mechas.
- Tendencia contextual.
- Decision entre continuacion y retroceso.

Pero adaptar duraciones:
- No asumir 30s/1m para Deriv real.
- Para metales (`frxXAUUSD`, `frxXAGUSD`): contrato 5m por defecto.
- Para forex: contrato 15m por defecto.
- Para indices opcionales: contrato 15m por defecto.

Timeframes recomendados:
- Metales 5m:
  - Analizar velas 1m y 5m.
  - CCI(20) principal en 1m o 5m, comparado con contexto 5m.
  - Entrada inmediata cuando el setup este confirmado y el payout sea aceptable.
- Forex 15m:
  - Analizar velas 5m y 15m.
  - CCI(20) principal en 5m, contexto 15m.
  - Evitar entradas en noticias y cambios de sesion.
- Indices 15m:
  - Analizar 5m y 15m.
  - Evitar aperturas, cierres, gaps y sesiones con baja liquidez.

Reglas:
- No generar RISE y FALL contradictorios para el mismo activo/ventana.
- No generar operacion si `proposal` no valida la duracion.
- No depender de un cruce CCI que casi nunca ocurre.
- Aprender de operaciones ganadas, perdidas y sombras, pero separar metricas por origen.
- Registrar sombras sin enviarlas al broker ni Telegram como senales operables.
- No usar aprendizaje de IQ Option OTC como permiso automatico para Deriv real.

---

## Reglas cuando gana, pierde o queda igual

Rise/Fall Deriv estricto:
- RISE gana si `exit_spot > entry_spot`.
- FALL gana si `exit_spot < entry_spot`.
- Si `exit_spot == entry_spot`, no marcar como win. Para `callput` estricto debe resolverse segun Deriv; por defecto tratar como `equal_loss` salvo que Deriv devuelva otra cosa.

Cuando gana:
1. Registrar `contract_settled`.
2. Guardar profit real de Deriv.
3. Actualizar saldo virtual con payout real, no solo con `VIRTUAL_PAYOUT_RATE`.
4. Reiniciar racha de perdidas.
5. Alimentar aprendizaje Deriv real.
6. Enviar resultado Telegram una sola vez.
7. Si alcanza meta, emitir evento `target`.

Cuando pierde:
1. Registrar `contract_settled`.
2. Guardar perdida real de Deriv.
3. Restar stake al saldo virtual o usar profit real.
4. Aumentar racha de perdidas.
5. Alimentar aprendizaje Deriv real.
6. Aplicar modo conservador si corresponde.
7. Enviar resultado Telegram una sola vez.
8. Si ocurre quiebra virtual, emitir evento `bankruptcy`.

Cuando la compra no se ejecuta:
- No convertirlo en win/loss virtual real.
- Registrar el motivo:
  - `proposal_rejected`
  - `buy_rejected`
  - `market_closed`
  - `duration_not_offered`
  - `insufficient_funds`
  - `token_expired`
  - `stale_proposal`
  - `payout_too_low`
  - `network_timeout`

Cuando se aborta:
- El aborto solo puede ocurrir antes de comprar.
- Si ya hay `contract_id`, no puede pasar a `aborted`.
- Si el setup se invalida despues de comprar, se registra como resultado de broker o como gestion de salida temprana si `sell` esta implementado y probado.

---

## Saldo virtual

Mantener variables:
- `VIRTUAL_INITIAL_BALANCE`
- `VIRTUAL_TARGET_BALANCE`
- `VIRTUAL_CAUTIOUS_STAKE`
- `VIRTUAL_SAFE_STAKE`
- `VIRTUAL_PAYOUT_RATE`

Pero en operaciones Deriv:
- Usar `proposal.payout` y `buy.buy_price` para calcular payout real.
- `VIRTUAL_PAYOUT_RATE` queda como fallback para modo offline/backtest.
- Guardar `payout_rate = (payout - ask_price) / ask_price`.

Reglas:
- Saldo virtual debe salir de eventos resueltos, no de recalculos ambiguos.
- Toda operacion debe tener `signal_id`.
- Quiebras y metas deben ser eventos propios.
- Telegram debe notificar quiebra/meta una sola vez.
- El dashboard debe mostrar saldo por evento, no por JSON paralelo.

---

## Telegram

Variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Requisitos:
- Enviar senales solo si `TELEGRAM_ENABLED=true` y score >= `TELEGRAM_MIN_SCORE`.
- Mensaje de senal debe mostrar:
  - `signal_id`
  - broker `Deriv`
  - cuenta `DEMO` o `REAL`
  - simbolo Deriv
  - nombre visible
  - direccion `RISE`/`FALL`
  - `contract_type` real `CALL`/`PUT`
  - duracion
  - stake
  - payout esperado
  - estado `proposal_received` o `buy_confirmed`
- Enviar resultado despues de `contract_settled`.
- Enviar resumen cada `TELEGRAM_SUMMARY_BATCH_SIZE` operaciones reales.
- Enviar quiebra/meta una sola vez.
- Deduplicar en Supabase con unique constraints.
- Si Telegram falla, registrar error y reintentar; no bloquear broker ni motor.
- Endpoint `/api/telegram/test` debe enviar mensaje de prueba sin crear senal falsa.

---

## Supabase

Puedes usar el mismo proyecto Supabase existente como infraestructura:

```env
SUPABASE_URL=https://kwbqjullmtrankjpmwfs.supabase.co
```

Pero Deriv debe tener tablas nuevas desde cero. No uses las tablas legacy actuales como fuente operativa principal.

Tablas legacy actuales de IQ Option:
- `bot_state_files`
- `bot_state_file_versions`

Requisitos:
- Conectar con `supabase-py`.
- Crear migraciones SQL.
- Crear schema `deriv` o tablas con prefijo `deriv_`.
- Crear indices por `signal_id`, `asset`, `market`, `entry_at`, `created_at`, `status`, `deriv_contract_id`.
- Crear constraints unicas:
  - `signals.signal_id`
  - `broker_orders.signal_id`
  - `broker_orders.deriv_contract_id`
  - `telegram_events(signal_id, message_type)`
  - `trade_events.idempotency_key`
  - `deriv_market_catalog.symbol`
- Crear RPC transaccional para append de eventos criticos.
- Evitar reescritura constante de JSON grandes.
- No guardar ticks, velas ni analisis repetitivos en Supabase.
- Guardar solo decisiones, eventos, ordenes, resultados, reglas agregadas, catalogo de mercado y snapshots compactos de baja frecuencia.
- Mantener compatibilidad con `bot_state_files` solo como historico, migracion opcional o snapshot temporal.
- Loggear tamanos y tiempos de escritura sin imprimir payloads sensibles.
- Si Supabase timeout, usar cola local duradera y flush posterior.
- Si local y remoto divergen, registrar discrepancia y resolver por regla explicita.

---

## UI/UX

Crear dashboard operativo con:
- Panel de mercados Deriv.
- Catalogo de mercados con filtros: habilitado, bloqueado, sintetico, sin Rise/Fall, duracion no soportada.
- Buscador/agregar/eliminar/activar/desactivar mercado.
- Selector de contrato: Rise/Fall estricto, Allow Equals apagado por defecto.
- Selector de duracion por mercado.
- Grafico de velas reales de Deriv.
- Estado WebSocket publico.
- Estado WebSocket autenticado.
- Estado OAuth/token/OTP sin revelar secretos.
- Estado Supabase.
- Estado Telegram.
- Boton conectar/desconectar broker.
- Modo DEMO/REAL muy visible.
- Historial canonico de senales.
- Historial de resultados Deriv.
- Latencia por etapa: tick -> signal -> proposal -> buy -> confirm.
- Broker en vivo.
- Saldo virtual y eventos.
- Aprendizaje real Deriv separado de IQ legacy y sombra.

Requisitos visuales:
- No texto mojibake.
- Todo UTF-8.
- No scroll jumps.
- Chart estable y no blanco.
- Mobile y desktop probados.
- Textos no deben solaparse.
- Dashboard denso, sobrio y utilitario.
- No landing page.
- No confundir Deriv con IQ Option ni con `PO`.

Pruebas visuales:
- Playwright desktop 1440x900.
- Playwright mobile 390x844.
- Verificar grafico no blanco con datos mock.
- Verificar panel de catalogo Deriv.
- Verificar boton de broker, Telegram y Supabase.
- Verificar que no aparezcan `Ã`, `Â`, `ï¿½` ni mojibake visible.

---

## Pruebas obligatorias

No entregar hasta que existan y pasen estas pruebas.

### Unitarias

- Normalizacion de ticks Deriv.
- Construccion de velas desde `ticks_history`.
- Agregacion interna de ticks si se usan velas no soportadas por API.
- Deteccion de vela cerrada/en formacion.
- Calculo CCI(20).
- Decision continuidad vs retroceso.
- Mapeo `RISE` -> `CALL`, `FALL` -> `PUT`.
- Bloqueo si mapping longcode no coincide.
- Bloqueo de `synthetic_index`.
- Bloqueo de criptos sin `callput`.
- Validacion de duracion por `contracts_for`.
- Validacion de rechazo por `proposal`.
- Saldo virtual con payout real.
- Aprendizaje real vs sombra vs IQ legacy.
- Deduplicacion por `signal_id`.
- Idempotencia de eventos.

### Integracion con Deriv fake

- `active_symbols` con mercados mixtos filtra sinteticos.
- `contracts_for` con `CALL`/`PUT` habilita mercado.
- `contracts_for` sin `CALL`/`PUT` bloquea mercado.
- `proposal` exitoso genera `proposal_received`.
- `proposal` con duracion invalida genera `duration_not_offered`.
- `proposal.longcode` incorrecto bloquea trading.
- `buy` exitoso genera exactamente una orden broker.
- `buy` rechazado no crea win/loss virtual.
- `proposal_open_contract` resuelve win/loss.
- Reconexion no duplica compra.
- Varias senales simultaneas se envian concurrentemente dentro del deadline.
- Telegram se proyecta desde eventos.

### Integracion Supabase

- Creacion limpia de schema/tablas nuevas para Deriv.
- Migracion legacy desde `bot_state_files` solo si esta habilitada.
- Legacy queda read-only por defecto.
- Insert idempotente de eventos.
- RPC transaccional.
- Reintento tras timeout.
- No reescritura de JSON gigante por cada tick.
- No insercion de ticks crudos en Supabase.
- No insercion de cada vela en Supabase.
- No insercion de cada ciclo de analisis en Supabase.
- Prueba de carga simulada de 7 dias que demuestre que el numero de filas crece por senales/eventos reales, no por polling/ticks.
- Remote-first al arranque.
- Divergencia local/remota detectada y reportada.

### Telegram

- Senal enviada una vez.
- Resultado enviado una vez.
- Rechazo broker enviado una vez si aplica.
- Resumen cada 5 operaciones reales.
- Quiebra/meta enviadas una vez.
- Fallo Telegram no bloquea broker.

### End-to-end local sin credenciales reales

- Deriv fake + Supabase local/mock + Telegram mock.
- Verificar que dashboard, broker, virtual, aprendizaje y Telegram leen el mismo `signal_id`.

### Pruebas live publicas sin credenciales

Estas pueden correr por defecto porque no compran:

```env
RUN_LIVE_DERIV_PUBLIC_TESTS=true
```

Pruebas:
- Conectar a `wss://api.derivws.com/trading/v1/options/ws/public`.
- `ping`.
- `time`.
- `active_symbols`.
- `contracts_list`.
- `contracts_for` para mercados configurados.
- Confirmar que no hay `synthetic_index`.
- `proposal` para `CALL` y `PUT` con stake bajo en mercados configurados.
- Confirmar longcode:
  - `CALL` estrictamente mayor.
  - `PUT` estrictamente menor.
- Confirmar que 1m se rechaza si el mercado no lo ofrece.
- Confirmar que duracion configurada se acepta.
- `ticks_history` con granularidades oficiales.
- `ticks` realtime por al menos 10 segundos.

Generar reporte:
- `DERIV_PUBLIC_CONNECTIVITY_REPORT.md`
- `DERIV_MARKET_RESEARCH.md`
- `DERIV_CONTRACT_MAPPING_REPORT.md`

### Pruebas live DEMO autenticadas

Solo si:

```env
RUN_LIVE_DERIV_DEMO_TESTS=true
DERIV_ACCOUNT_MODE=DEMO
LIVE_TEST_ALLOW_REAL=false
```

Pruebas:
- OAuth/token/OTP.
- Conectar WebSocket autenticado.
- Consultar `balance`.
- Consultar `portfolio`.
- Consultar `profit_table`.
- Suscribirse a `transaction`.
- Crear `proposal`.
- Comprar solo si tambien:

```env
RUN_LIVE_DERIV_BUY_TESTS=true
LIVE_TEST_MAX_STAKE=1
```

- Monitorear `proposal_open_contract`.
- Reconciliar resultado contra `profit_table` o `statement`.
- Verificar Telegram y Supabase con el mismo `signal_id`.

Nunca correr pruebas live en REAL salvo confirmacion explicita y variable:

```env
LIVE_TEST_ALLOW_REAL=true
DERIV_ACCOUNT_MODE=REAL
```

---

## Endpoints minimos

Backend:
- `GET /`
- `GET /health`
- `GET /api/state`
- `GET /api/events?signal_id=...`
- `GET /api/signals`
- `GET /api/performance`
- `GET /api/deriv/market-catalog`
- `POST /api/deriv/market-discovery`
- `POST /api/deriv/verify-contracts`
- `GET /api/broker/orders`
- `POST /api/broker/trading`
- `POST /api/telegram/test`
- `POST /api/markets`
- `DELETE /api/markets/{asset}`
- `POST /api/markets/{asset}/enabled`
- `POST /api/timeframe`
- `GET /api/auth/deriv/login-url`
- `GET /api/auth/deriv/callback`
- `WS /ws`

`/health` debe mostrar:
- Broker provider `deriv`.
- Public WS conectado/no conectado.
- Auth WS conectado/no conectado.
- OAuth configurado/no configurado sin mostrar secretos.
- Modo DEMO/REAL.
- Broker trading ON/OFF.
- Supabase conectado/no conectado.
- Telegram conectado/no conectado.
- Ultimo error enmascarado.
- Version de estrategia.
- Version de migracion DB.
- Ultima verificacion de catalogo de mercados.

---

## Entregables

1. Proyecto nuevo completo.
2. `requirements.txt` con versiones fijadas.
3. `.env.example` completo y alineado con codigo.
4. `README.md`.
5. `RENDER_DEPLOY.md`.
6. Migraciones SQL Supabase.
7. Script opcional de migracion/lectura legacy desde `bot_state_files`, apagado por defecto o read-only.
8. `DERIV_MARKET_RESEARCH.md`.
9. `DERIV_CONTRACT_MAPPING_REPORT.md`.
10. `SYNC_CONTRACT.md`.
11. `DATA_RETENTION_AND_STORAGE_POLICY.md`, explicando que se guarda, que no se guarda, retencion, compactacion y limites esperados de crecimiento.
12. Suite de pruebas completa.
13. Reporte de verificacion:
    - Tests unitarios.
    - Tests integracion.
    - Tests visuales.
    - Prueba Supabase.
    - Prueba Deriv fake.
    - Prueba Deriv publica sin credenciales.
    - Prueba Deriv DEMO si fue autorizada.
    - Prueba de volumen Supabase por 7 dias simulados.
14. Dashboard funcional.
15. Guia de operacion para equipo.

---

## Criterios de aceptacion

El proyecto solo se considera listo si:

- No hay secretos hardcodeados.
- Las variables de entorno existentes siguen funcionando o quedan mapeadas con warnings.
- Supabase existente se puede leer si se configura, pero Deriv opera sobre tablas nuevas.
- Los datos legacy no se mezclan con Deriv como aprendizaje equivalente.
- La migracion legacy es opcional, controlada y read-only por defecto.
- Todo mercado operativo fue descubierto por `active_symbols` y verificado por `contracts_for` + `proposal`.
- Ningun simbolo `synthetic_index` puede operarse si `DERIV_ALLOW_SYNTHETIC_MARKETS=false`.
- Criptomonedas no se operan en Rise/Fall mientras no tengan `callput`.
- Cada senal real tiene un solo `signal_id`.
- Broker, virtual, Telegram y dashboard muestran el mismo `signal_id`.
- Una operacion abortada nunca se manda a Deriv.
- Una orden enviada a Deriv nunca cambia despues a `aborted`.
- Una senal con `proposal` fallido no aparece como win/loss virtual.
- Las operaciones simultaneas se envian concurrentemente.
- Los errores de Deriv quedan visibles y clasificados.
- Telegram no crea otro historial paralelo.
- Supabase no recibe JSON gigantes en cada tick.
- Supabase no guarda ticks crudos, velas individuales ni ciclos de analisis repetitivos por defecto.
- Existe politica de retencion/compactacion.
- La prueba de 7 dias simulados demuestra crecimiento controlado de filas.
- Dashboard no tiene mojibake ni saltos de layout.
- Tests pasan antes de entregar.
- Existe reporte que demuestre la latencia entre `signal_decided`, `proposal_received`, `buy_confirmed` y `contract_settled`.
- REAL trading queda bloqueado por defecto.

---

## Fuentes tecnicas usadas

- Deriv API actual: https://developers.deriv.com/llms.txt
- Deriv API docs: https://developers.deriv.com/docs/
- Deriv Code Examples: https://developers.deriv.com/docs/examples/
- Deriv Rise/Fall legacy: https://legacy-docs.deriv.com/docs/risefall
- Python Deriv API GitHub, archivado: https://github.com/deriv-com/python-deriv-api
- Supabase Python client docs: https://supabase.com/docs/reference/python/initializing
- Supabase API docs: https://supabase.com/docs/guides/api
- Supabase API keys docs: https://supabase.com/docs/guides/getting-started/api-keys

---

## Nota final para la IA constructora

No intentes "hacer que parezca que opera" antes de demostrar conexiones.

El orden correcto es:

1. Configuracion y secretos seguros.
2. Conexion Deriv publica.
3. Descubrimiento de mercados no sinteticos.
4. Verificacion Rise/Fall por `contracts_for`.
5. Verificacion de direccion por `proposal.longcode`.
6. Conexion Supabase.
7. Modelo event-sourced.
8. Motor de senales adaptado a 5m/15m.
9. Broker fake.
10. Tests publicos Deriv.
11. Dashboard.
12. Telegram como proyeccion.
13. DEMO autenticado.
14. Compra DEMO minima si el usuario autoriza.
15. Reconciliacion.
16. Solo despues, REAL con confirmacion explicita.

Si algun paso falla, el sistema debe fallar cerrado, registrar el motivo y mostrarlo en dashboard.
