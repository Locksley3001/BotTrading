# Prompt maestro para reconstruir el proyecto desde cero

Usa este prompt con una IA/agente de desarrollo para crear un nuevo proyecto desde cero.

Importante sobre secretos:
- escribe credenciales reales, correos, contrasenas, tokens de Telegram, claves de Supabase dentro del codigo, commits, README, logs y respuestas.
- Usa las mismas variables de entorno existentes y lee los valores desde `.env` o desde Render.
- Si el entorno ya contiene `.env`, la IA puede usarlo para ejecutar pruebas, pero debe enmascarar valores sensibles en toda salida.
- Donde haga falta un valor sensible y no esten este texto, usa placeholders como `<IQ_OPTION_EMAIL_REAL>`, `<IQ_OPTION_PASSWORD_REAL>`, `<TELEGRAM_BOT_TOKEN_REAL>` y `<SUPABASE_SERVICE_ROLE_KEY_REAL>`.

---

## Rol

Actua como arquitecto senior y desarrollador full-stack. Crea desde cero un sistema profesional de senales y ejecucion para opciones binarias de corto plazo en IQ Option, con FastAPI/Python, frontend web, Telegram y Supabase.

No reutilices la arquitectura defectuosa actual. Puedes reutilizar conceptos de negocio, variables de entorno y datos existentes de Supabase, pero el diseno interno debe ser nuevo, probado e idempotente desde el inicio.

Objetivo central:
- Las operaciones virtuales, broker real, historial del proyecto, historial de Telegram y base de datos deben salir del mismo evento canonico.
- No puede haber historiales paralelos que se contradigan.
- Si el broker no puede ejecutar exactamente la misma operacion virtual por activo cerrado, saldo insuficiente, latencia, 2FA, desconexion o rechazo de IQ Option, el sistema debe registrarlo como discrepancia explicita, no ocultarlo ni inventar equivalencias.
- La prioridad es evitar desde el inicio los desfases que ya ocurrieron entre historial virtual, broker real y Telegram.

---

## Contexto de errores que debes eliminar desde el diseno

El proyecto anterior tuvo estos problemas o riesgos:

1. El broker real no siempre ejecuto las mismas operaciones del saldo virtual.
2. Hubo operaciones virtuales validas que no llegaron al broker.
3. Hubo operaciones enviadas al broker cuyo registro virtual termino `aborted`.
4. Hubo multiples rutas de ejecucion para una misma senal: tarea por senal, barrido por ciclo y watchdog, con deduplicacion parcial.
5. La ventana documentada `BROKER_TRADE_ENTRY_WINDOW_SECONDS=3` se convertia internamente en minimo 8 segundos sin ser claro para el usuario.
6. Algunas senales nacian cuando la vela de entrada ya habia empezado, haciendo imposible ejecutarlas al mismo tiempo en IQ Option.
7. El `placed_at` registrado podia quedar muchos segundos despues del `entry_at`, sin separar hora de envio local, hora de servidor broker y hora de confirmacion.
8. `broker_trades.json`, `performance.json`, `signals.json` y `telegram_notifications.json` funcionaban como historiales separados.
9. Se detectaron `signal_id` de broker que ya no existian en `performance.json`.
10. Telegram guardaba IDs propios y podia quedar desalineado del historial principal.
11. Supabase guardaba JSON grandes completos, generando timeouts y presion de Disk IO.
12. El estado local podia quedar detras del estado remoto en Supabase.
13. La UI tuvo texto con encoding roto, por ejemplo `Â·`, `seÃ±ales`, `direcciÃ³n`.
14. El dashboard confundio aprendizaje real con aprendizaje sombra.
15. El historial visual se reiniciaba o se limitaba de forma confusa.
16. El boton de broker llego a indicar conexion aunque no duplicara bien las operaciones.
17. USDJPY-OTC dio muchos rechazos o errores por alias/activo no disponible.
18. Hubo fallos por saldo insuficiente en broker que no estaban reconciliados con el saldo virtual.
19. Supabase tenia variables antiguas o no usadas: `REMOTE_STATE_ENABLED`, `SUPABASE_STATE_BACKUP_TABLE`.
20. El `.env` real no contenia varias variables soportadas por el codigo, dejando defaults ocultos.

El nuevo proyecto debe resolver todo esto en arquitectura, no con parches.

---

## Stack tecnico obligatorio

Backend:
- Python 3.12.8.
- FastAPI.
- Uvicorn/Gunicorn para produccion.
- Pydantic Settings para configuracion.
- `python-dotenv` para desarrollo local.
- `python-telegram-bot` o `aiogram` para Telegram, con preferencia por una version moderna y fijada.
- `supabase-py` oficial para operaciones normales de Supabase.
- REST/PostgREST solo como fallback controlado o para compatibilidad con tablas existentes.

Broker IQ Option:
- Libreria obligatoria: `iqoptionapi` de la comunidad.
- Import principal: `from iqoptionapi.stable_api import IQ_Option`.
- Instalacion recomendada:
  - `websocket-client==0.56` o `websocket-client==0.56.0`.
  - `iqoptionapi @ https://github.com/iqoptionapi/iqoptionapi/archive/refs/heads/master.zip`
- Mejor practica: si las pruebas pasan, fijar un commit exacto de GitHub en `requirements.txt` para evitar cambios inesperados en master.
- Debes documentar que `iqoptionapi` no es oficial y que IQ Option puede cambiar/bloquear comportamiento.

Supabase:
- Usar `supabase-py` con `create_client(SUPABASE_URL, SUPABASE_KEY)` para lecturas/escrituras de app.
- Las operaciones criticas deben usar transacciones atomicas mediante SQL/RPC en Postgres cuando sea necesario.
- El backend debe usar clave elevada solo del lado servidor. Nunca exponer service_role/secret keys al frontend.
- Soportar las claves legacy actuales (`SUPABASE_SERVICE_ROLE_KEY`) y sugerir soporte adicional para claves nuevas tipo `SUPABASE_SECRET_KEY`.

Frontend:
- Puede ser React/Vite + TypeScript o frontend estatico moderno, pero debe tener pruebas visuales.
- Debe usar UTF-8 real de punta a punta.
- Debe ser un dashboard operativo, no landing page.

No usar:
- TradingView, Twelve Data, Binance u otra fuente externa para velas principales.
- Telegram como fuente para ejecutar operaciones.
- Archivos JSON gigantes como fuente principal de verdad en produccion.

---

## Variables de entorno que se deben conservar

Mantener compatibilidad con estas variables existentes:

```env
IQ_OPTION_EMAIL=<IQ_OPTION_EMAIL_REAL>
IQ_OPTION_PASSWORD=<IQ_OPTION_PASSWORD_REAL>
IQ_OPTION_2FA_CODE=
IQ_OPTION_BALANCE_MODE=PRACTICE

TELEGRAM_BOT_TOKEN=<TELEGRAM_BOT_TOKEN_REAL>
TELEGRAM_CHAT_ID=<TELEGRAM_CHAT_ID_REAL>

MARKETS=EURUSD-OTC,GBPUSD-OTC,BTCUSD-OTC,ETHUSD-OTC,NVDA/AMD-OTC,SOLUSD-OTC
DISABLED_MARKETS=USDJPY-OTC
DEFAULT_TIMEFRAME=60
POLL_INTERVAL_SECONDS=0.75
CANDLE_COUNT=80
SIGNAL_COOLDOWN_SECONDS=45

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

Debes detectar variables antiguas y avisar:
- `REMOTE_STATE_ENABLED` esta obsoleta; mapear a `SUPABASE_STATE_ENABLED` solo por compatibilidad y emitir warning.
- `SUPABASE_STATE_BACKUP_TABLE` esta obsoleta; mapear a `SUPABASE_VERSIONS_TABLE` solo por compatibilidad y emitir warning.

Variables nuevas sugeridas:

```env
PYTHON_VERSION=3.12.8
APP_ENV=production
LOG_LEVEL=INFO

SUPABASE_SECRET_KEY=
SUPABASE_SCHEMA=public
SUPABASE_EVENT_TABLE=trade_events
SUPABASE_SIGNAL_TABLE=signals
SUPABASE_BROKER_ORDER_TABLE=broker_orders
SUPABASE_TELEGRAM_EVENT_TABLE=telegram_events
SUPABASE_LEGACY_MIGRATION_ENABLED=true
SUPABASE_LEGACY_READ_ONLY=false
SUPABASE_LEGACY_SNAPSHOT_INTERVAL_SECONDS=300

BROKER_SYNC_STRICT_MODE=true
BROKER_MIN_LEAD_SECONDS=5
BROKER_ORDER_DEADLINE_MS=900
BROKER_CONFIRM_TIMEOUT_SECONDS=15
BROKER_RECONCILE_INTERVAL_SECONDS=30
BROKER_MAX_CONCURRENT_ORDERS=10
BROKER_MARKET_OPEN_CHECK_ENABLED=true

SERVER_TIME_SYNC_MAX_DRIFT_MS=750
MARKET_STREAM_WARMUP_SECONDS=5

TELEGRAM_ENABLED=true
TELEGRAM_MIN_SCORE=7
TELEGRAM_SUMMARY_BATCH_SIZE=5

RUN_LIVE_BROKER_TESTS=false
LIVE_TEST_MARKETS=EURUSD-OTC,GBPUSD-OTC,NVDA/AMD-OTC,BTCUSD-OTC,ETHUSD-OTC,SOLUSD-OTC
LIVE_TEST_MAX_STAKE=10000
LIVE_TEST_ALLOW_REAL=false
```

---

## Arquitectura de datos obligatoria

No uses cinco JSON independientes como fuente principal.

Crea un modelo event-sourced o una maquina de estados atomica con estas tablas en la misma base Supabase existente:

### `signals`
- `signal_id` unique.
- `asset`.
- `direction`.
- `timeframe`.
- `created_at`.
- `analysis_candle_ts`.
- `entry_at`.
- `expires_at`.
- `score`.
- `factor_score`.
- `confidence`.
- `stake_amount`.
- `status`.
- `is_shadow`.
- `blocked_reason`.
- `strategy_version`.
- `features_json`.

### `trade_events`
- `event_id` uuid.
- `signal_id`.
- `event_type`.
- `event_at`.
- `source`: `engine`, `broker`, `telegram`, `supabase`, `reconciler`.
- `payload`.
- unique idempotency key.

### `broker_orders`
- `signal_id` unique.
- `broker_order_id`.
- `status`: `scheduled`, `sent`, `placed`, `rejected`, `expired_before_send`, `insufficient_funds`, `asset_closed`, `unknown`.
- `asset_sent`.
- `direction_sent`.
- `stake_amount`.
- `expiration_seconds`.
- `balance_mode`.
- `entry_at`.
- `send_started_at`.
- `broker_server_time_at_send`.
- `confirmed_at`.
- `broker_open_time`.
- `broker_close_time`.
- `broker_result`.
- `error_code`.
- `error_message`.

### `virtual_outcomes`
- `signal_id` unique.
- `entry_price`.
- `result_price`.
- `status`: `waiting_entry`, `pending`, `win`, `loss`, `push`, `aborted`.
- `abort_reason`.
- `resolved_at`.
- `balance_after`.

### `telegram_events`
- unique `(signal_id, message_type)`.
- `message_type`: `signal`, `broker_sent`, `result`, `summary`, `bankruptcy`, `target`.
- `sent_at`.
- `telegram_message_id`.
- `status`.
- `error`.

### `learning_snapshots` / `learning_rules`
- Separar aprendizaje real y sombra.
- No mezclar metricas en el dashboard.

### Compatibilidad legacy

La base existente tiene la tabla `bot_state_files` con filas:
- `performance.json`
- `learning.json`
- `signals.json`
- `telegram_notifications.json`
- `broker_trades.json`

El nuevo proyecto debe:
1. Leer esas filas al primer arranque.
2. Migrar sin borrar datos.
3. Validar conteos antes/despues.
4. Mantener un snapshot legacy opcional para compatibilidad temporal.
5. No reescribir JSON multi-MB en cada tick.
6. Escribir eventos pequenos y atomicos.

---

## Regla principal de sincronizacion broker/virtual/Telegram

Debe existir una sola fuente canonica:

`signal_decision -> entry_validation -> broker_order -> virtual_outcome -> telegram_projection -> dashboard_projection`

Cada paso debe registrar un evento con el mismo `signal_id`.

Reglas duras:

1. Una operacion virtual real no puede crearse si ya es imposible enviarla al broker a tiempo cuando `BROKER_SYNC_STRICT_MODE=true`.
2. Si una senal se detecta tarde, guardarla como `skipped_late_signal`, no como operacion virtual.
3. La senal debe nacer con al menos `BROKER_MIN_LEAD_SECONDS` antes de `entry_at`.
4. La compra debe iniciar entre `entry_at` y `entry_at + BROKER_ORDER_DEADLINE_MS`.
5. El sistema debe registrar `send_started_at` separado de `confirmed_at`.
6. La validacion de aborto debe ocurrir antes de `client.buy`.
7. Si se compra en broker, esa senal ya no puede terminar como `aborted` en virtual; debe resolver como win/loss/push o como discrepancia reconciliada.
8. Telegram no decide ni dispara operaciones. Solo observa eventos canonicos.
9. El dashboard no lee historiales paralelos. Lee proyecciones de los eventos canonicos.
10. Si Supabase falla, se usa cola local duradera y se reintenta sin duplicar eventos.

---

## Conexion con IQ Option

Implementa `IQOptionBroker` como adaptador aislado.

Login:
```python
from iqoptionapi.stable_api import IQ_Option

client = IQ_Option(email, password)
status, reason = client.connect()
if not status and str(reason).upper() == "2FA":
    status, reason = client.connect_2fa(two_factor_code)
client.change_balance("PRACTICE" or "REAL")
```

Requisitos:
- No iniciar si faltan `IQ_OPTION_EMAIL` o `IQ_OPTION_PASSWORD`.
- Manejar 2FA con `IQ_OPTION_2FA_CODE` temporal.
- Usar `client.check_connect()` y reconexion automatica.
- Usar locks o un worker dedicado porque `iqoptionapi` es bloqueante.
- Exponer health sin revelar credenciales.

Velas:
- Usar `start_candles_stream(asset, timeframe, CANDLE_COUNT)` al iniciar cada mercado.
- Leer con `get_realtime_candles(asset, timeframe)`.
- Usar `get_candles(asset, timeframe, count, time.time())` solo para backfill o fallback.
- Normalizar timestamp, open, high, low, close, volume, `is_closed`.
- No analizar velas desordenadas o con timestamp ambiguo.
- Comparar reloj local, reloj UTC y si esta disponible `client.api.timesync.server_timestamp`.

Activos:
- Implementar normalizador de activos y alias:
  - `EURUSD-OTC`
  - `GBPUSD-OTC`
  - `BTCUSD-OTC` y posible `BTCUSD-OTC-op`
  - `ETHUSD-OTC`
  - `SOLUSD-OTC`
  - `NVDA/AMD-OTC`
- Consultar activos abiertos antes de generar operacion real.
- Si un activo no esta disponible, marcar `asset_closed` y no intentar infinitamente.

Compra:
```python
success, order_id = client.buy(
    float(amount),
    asset_name,
    "call" or "put",
    duration_minutes,
)
```

Requisitos de compra:
- `duration_minutes = ceil(expiration_seconds / 60)`.
- Iniciar compra con deadline duro.
- Registrar intento antes de llamar a `buy`.
- Registrar resultado despues de respuesta.
- Si hay error `Insufficient funds for this transaction.`, marcar `insufficient_funds`.
- Si hay error `Cannot purchase an option...`, marcar `asset_closed` o `broker_rejected`.
- Si hay error `Time for purchasing options is over...`, marcar `expired_before_send` o `broker_cutoff_missed`.
- No convertir rechazos en operaciones virtuales ganadas/perdidas.
- Reconciliar luego con historial/estado del broker si la API lo permite.

---

## Estrategia de senales

Mantener la filosofia:
- CCI periodo 20.
- Sobrecompra: `+100`.
- Sobreventa: `-100`.
- Operaciones de corto plazo: 30s, 45s, 1m, 2m, 3m, 5m.
- Prioridad actual: 1 minuto.

La logica debe evaluar:
- Fuerza.
- Continuidad.
- Cansancio.
- Rechazo.
- Cuerpo de vela.
- Mechas.
- Tendencia contextual.
- Extremos CCI.
- Si conviene continuidad a favor del movimiento o retroceso contra el movimiento.

Reglas:
- No generar CALL y PUT contradictorios para el mismo activo/vela.
- No generar operacion si la entrada ya no puede programarse a tiempo.
- No depender de un cruce CCI que casi nunca ocurre.
- Aprender de operaciones ganadas, perdidas y sombras, pero separar metricas.
- Evitar que el aprendizaje bloquee todo: usar exploracion controlada.
- Registrar sombras sin enviarlas al broker ni Telegram como senales operables.

---

## Saldo virtual

Variables:
- `VIRTUAL_INITIAL_BALANCE`
- `VIRTUAL_TARGET_BALANCE`
- `VIRTUAL_CAUTIOUS_STAKE`
- `VIRTUAL_SAFE_STAKE`
- `VIRTUAL_PAYOUT_RATE`

Requisitos:
- Saldo virtual debe salir de eventos resueltos, no de recalculos ambiguos.
- Toda operacion virtual debe tener `signal_id`.
- Quiebras y metas deben ser eventos propios.
- Telegram debe notificar quiebra/meta una sola vez por evento.
- El dashboard debe mostrar historial de saldo sin depender de `signals.json`.

---

## Telegram

Variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Requisitos:
- Enviar senales solo si `TELEGRAM_ENABLED=true` y score >= `TELEGRAM_MIN_SCORE`.
- Enviar resultado despues de resolver.
- Enviar resumen cada `TELEGRAM_SUMMARY_BATCH_SIZE` operaciones reales.
- Enviar quiebra/meta una sola vez.
- Deduplicar en Supabase con unique constraints, no con listas JSON gigantes.
- Si Telegram falla, registrar error y reintentar; no bloquear broker ni motor.
- Endpoint `/api/telegram/test` debe enviar mensaje de prueba sin crear senal falsa.

---

## Supabase

Usa la base existente:
- `SUPABASE_URL=https://kwbqjullmtrankjpmwfs.supabase.co`
- Tablas legacy actuales: `bot_state_files`, `bot_state_file_versions`.

Requisitos:
- Conectar con `supabase-py`.
- Crear migraciones SQL.
- Crear indices por `signal_id`, `asset`, `entry_at`, `created_at`, `status`.
- Crear constraints unicas para idempotencia.
- Crear RPC transaccional para append de eventos criticos.
- Evitar reescritura constante de JSON grandes.
- Mantener compatibilidad con `bot_state_files` solo como migracion/snapshot.
- Loggear tamanos y tiempos de escritura sin imprimir payloads ni claves.
- Si Supabase timeout, cola local duradera y flush posterior.
- Si local y remoto divergen, remoto gana salvo que exista migracion pendiente verificada.

---

## UI/UX

Crear dashboard operativo con:
- Panel de mercados.
- Buscador/agregar/eliminar/activar/desactivar mercado.
- Selector de timeframe.
- Grafico de velas reales de IQ Option.
- Estado de conexion broker.
- Estado Supabase.
- Boton conectar/desconectar broker.
- Modo PRACTICE/REAL visible.
- Historial de senales.
- Historial de resultados.
- Broker en vivo.
- Telegram status/test.
- Saldo virtual y eventos.
- Aprendizaje real separado de aprendizaje sombra.

Requisitos visuales:
- No texto mojibake. Todo UTF-8.
- No scroll jumps.
- El canvas no debe redimensionarse por cada senal.
- Mobile y desktop probados.
- Textos no deben solaparse.
- Dashboard denso, sobrio y utilitario.
- No landing page.
- No confundir marca: si es IQ Option, no usar `PO` como marca.

Pruebas visuales:
- Playwright desktop 1440x900.
- Playwright mobile 390x844.
- Verificar grafico no blanco cuando hay datos mock.
- Verificar botones de sonido, Telegram y broker.
- Verificar que no aparezcan `Â`, `Ã`, `�` en textos visibles.

---

## Pruebas obligatorias

No entregar hasta que existan y pasen estas pruebas:

### Unitarias
- Normalizacion de velas.
- Deteccion de vela cerrada/en formacion.
- Calculo CCI(20).
- Decision continuidad vs retroceso.
- Bloqueo por senal tardia.
- Saldo virtual.
- Aprendizaje real vs sombra.
- Deduplicacion por `signal_id`.
- Alias de activos IQ Option.

### Integracion con broker fake
- Una senal virtual genera exactamente una orden broker.
- Una senal abortada no genera orden.
- Una senal tardia no se registra como operacion.
- Varias senales simultaneas se envian concurrentemente.
- Saldo insuficiente se registra como fallo broker, no como perdida virtual.
- Activo cerrado se registra como fallo broker.
- Reconexion no duplica orden.
- Watchdog/reconciler no duplica orden.

### Integracion Supabase
- Migracion legacy desde `bot_state_files`.
- Insert idempotente de eventos.
- Reintento tras timeout.
- No reescritura de JSON gigante por cada tick.
- Remote-first al arranque.
- Divergencia local/remota detectada y reportada.

### Telegram
- Senal enviada una vez.
- Resultado enviado una vez.
- Resumen cada 5 operaciones reales.
- Quiebra/meta enviadas una vez.
- Fallo Telegram no bloquea broker.

### End-to-end local sin credenciales reales
- Broker fake + Supabase local/mock + Telegram mock.
- Verificar que dashboard, broker, virtual y Telegram leen el mismo `signal_id`.

### Pruebas live opcionales en PRACTICE
Solo si:
```env
RUN_LIVE_BROKER_TESTS=true
IQ_OPTION_BALANCE_MODE=PRACTICE
LIVE_TEST_ALLOW_REAL=false
```

Pruebas live:
- Conectar a IQ Option.
- Cambiar a PRACTICE.
- Abrir streams de todos los mercados configurados.
- Verificar velas en tiempo real.
- Ejecutar prueba de orden minima solo si el usuario lo habilito.
- Probar un mercado individual.
- Probar multiples mercados simultaneos.
- Medir:
  - `entry_at`.
  - `send_started_at`.
  - `broker_server_time_at_send`.
  - `confirmed_at`.
  - `broker_order_id`.
- Generar reporte de sincronizacion.

Nunca correr pruebas live en REAL salvo confirmacion explicita y variable:
```env
LIVE_TEST_ALLOW_REAL=true
IQ_OPTION_BALANCE_MODE=REAL
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
- `GET /api/broker/orders`
- `POST /api/broker/trading`
- `POST /api/telegram/test`
- `POST /api/markets`
- `DELETE /api/markets/{asset}`
- `POST /api/markets/{asset}/enabled`
- `POST /api/timeframe`
- `WS /ws`

`/health` debe mostrar:
- Broker conectado/no conectado.
- IQ Option configurado sin mostrar credenciales.
- Modo PRACTICE/REAL.
- Broker trading ON/OFF.
- Supabase conectado/no conectado.
- Ultimo error enmascarado.
- Version de estrategia.
- Version de migracion DB.

---

## Entregables

1. Proyecto nuevo completo.
2. `requirements.txt` con versiones fijadas.
3. `.env.example` completo y alineado con codigo.
4. `README.md`.
5. `RENDER_DEPLOY.md`.
6. Migraciones SQL Supabase.
7. Script de migracion desde `bot_state_files`.
8. Suite de pruebas completa.
9. Reporte de verificacion:
   - Tests unitarios.
   - Tests integracion.
   - Tests visuales.
   - Prueba Supabase.
   - Prueba broker fake.
   - Prueba live PRACTICE si fue autorizada.
10. Documento `SYNC_CONTRACT.md` explicando como se garantiza que virtual, broker, Telegram y dashboard usen el mismo evento.

---

## Criterios de aceptacion

El proyecto solo se considera listo si:

- No hay secretos hardcodeados.
- Las variables de entorno existentes siguen funcionando.
- Supabase existente se puede leer.
- Los datos legacy se migran o se consumen sin perder aprendizaje.
- Una senal real tiene un solo `signal_id` en todo el sistema.
- Broker, virtual, Telegram y dashboard muestran el mismo `signal_id`.
- Una operacion abortada nunca se manda al broker.
- Una orden enviada al broker nunca cambia despues a `aborted`.
- Una senal tardia no aparece como operacion virtual.
- Las operaciones simultaneas se envian concurrentemente.
- Los errores del broker quedan visibles y clasificados.
- Telegram no crea otro historial paralelo.
- Supabase no recibe JSON gigantes en cada tick.
- Dashboard no tiene mojibake ni saltos de layout.
- Tests pasan antes de entregar.

---

## Fuentes tecnicas verificadas

- iqoptionapi GitHub: https://github.com/iqoptionapi/iqoptionapi
- iqoptionapi setup.py confirma `websocket-client==0.56`: https://github.com/iqoptionapi/iqoptionapi/blob/master/setup.py
- Supabase Python client docs: https://supabase.com/docs/reference/python/initializing
- Supabase REST/Data API docs: https://supabase.com/docs/guides/api
- Supabase API keys docs: https://supabase.com/docs/guides/getting-started/api-keys
