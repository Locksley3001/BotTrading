# Aprendizaje actual del proyecto Deriv

Este documento explica cómo funciona hoy el aprendizaje del bot, qué está aprendiendo realmente, cómo se calcula y qué falta para que ese aprendizaje empiece a bloquear o favorecer operaciones de forma automática.

## Estado actual

El proyecto ya está generando una proyección de aprendizaje en:

```text
data/deriv_learning.json
```

También se puede consultar por API:

```text
GET /api/learning
POST /api/learning/rebuild
```

El aprendizaje actual se construye desde operaciones virtuales liquidadas de Deriv, no desde IQ Option ni desde datos legacy.

## Qué datos usa

La fuente principal son las operaciones virtuales cerradas en:

```text
data/deriv_virtual_trades.jsonl
```

Solo cuenta operaciones con:

```text
status = settled
outcome = win / loss / equal_loss
```

Para enriquecer esas operaciones, cruza cada `signal_id` contra:

```text
data/deriv_signals.jsonl
```

De ahí toma datos como:

- Mercado: `frxXAUUSD`, `frxXAGUSD`, `frxEURUSD`, etc.
- Dirección: `RISE` o `FALL`.
- Contrato Deriv: `CALL` o `PUT`.
- Razón técnica: por ejemplo `moderate_bearish_pressure`, `bullish_continuation`.
- Score.
- Factor score.
- Resultado final.
- Payout.
- Stake.
- Ganancia o pérdida neta.

## Qué no usa

El aprendizaje actual no usa:

- Datos de IQ Option.
- Tablas legacy como fuente equivalente.
- Ticks crudos.
- Cada vela individual.
- Telegram como fuente de verdad.
- Operaciones abiertas.
- Señales sin resultado.

Esto es intencional: el aprendizaje debe salir de resultados cerrados y auditables.

## Cómo calcula ganancia o pérdida

Para cada operación cerrada:

Si gana:

```text
profit = payout - stake
```

Ejemplo:

```text
stake = 10.00
payout = 18.18
profit = +8.18
```

Si pierde:

```text
profit = -stake
```

Ejemplo:

```text
stake = 10.00
profit = -10.00
```

Si queda igual en Rise/Fall estricto:

```text
profit = -stake
```

Por defecto el proyecto trata `equal_loss` como pérdida, porque Rise/Fall estricto no es `Allow Equals`.

## Qué reglas crea

Por cada operación cerrada, el sistema actualiza varias reglas al mismo tiempo. Una misma operación alimenta múltiples grupos de aprendizaje.

Ejemplos de reglas:

```text
global
asset:frxXAGUSD
direction:FALL
asset_direction:frxXAGUSD:FALL
contract:PUT
reason:moderate_bearish_pressure
score_band:8-9
factor_score:3
asset_reason:frxXAGUSD:moderate_bearish_pressure
```

Esto permite responder preguntas como:

- ¿Cómo va el bot globalmente?
- ¿Qué tal funciona Gold/USD?
- ¿Qué tal funcionan las operaciones FALL?
- ¿Qué tal funciona Silver/USD en FALL?
- ¿Qué tal funciona el contrato PUT?
- ¿Qué tal funciona una razón técnica específica?
- ¿Qué tal funcionan señales con score 8-9?

## Qué métricas guarda cada regla

Cada regla guarda:

```json
{
  "samples": 72,
  "wins": 39,
  "losses": 33,
  "equal_losses": 0,
  "net_profit": -8.22,
  "win_rate": 54.17,
  "avg_profit": -0.11416667,
  "last_signal_id": "sig_..."
}
```

Significado:

- `samples`: cuántas operaciones cerradas alimentan esa regla.
- `wins`: cuántas ganaron.
- `losses`: cuántas perdieron.
- `equal_losses`: cuántas quedaron iguales y se trataron como pérdida.
- `net_profit`: suma neta de ganancias y pérdidas.
- `win_rate`: porcentaje de acierto.
- `avg_profit`: ganancia o pérdida promedio por operación.
- `last_signal_id`: última operación que actualizó esa regla.

## Ejemplo real de interpretación

Si una regla dice:

```text
asset_direction:frxXAGUSD:FALL
samples: 15
wins: 11
losses: 4
win_rate: 73.33
net_profit: +48.52
```

Eso significa:

> Las operaciones FALL en Silver/USD han funcionado bien hasta ahora. Tienen 15 muestras, 73.33% de acierto y ganancia neta positiva.

Si otra regla dice:

```text
asset_direction:frxXAUUSD:RISE
samples: 8
wins: 1
losses: 7
win_rate: 12.5
net_profit: -62.61
```

Eso significa:

> Las operaciones RISE en Gold/USD han funcionado mal. El bot debería ser muy cauteloso con esa combinación.

## Cuándo se actualiza

El aprendizaje se reconstruye cuando una operación virtual se liquida.

Flujo:

```text
operación virtual abierta
-> llega expiración
-> se consulta tick/cierre de Deriv
-> se decide win/loss/equal_loss
-> se actualiza saldo virtual
-> se guarda resultado
-> se reconstruye aprendizaje
```

También puede reconstruirse manualmente:

```text
POST /api/learning/rebuild
```

Esto vuelve a leer todas las operaciones liquidadas y reconstruye `deriv_learning.json` desde cero.

## Cómo se supone que va a mejorar

La idea es que el bot deje de tratar todas las señales iguales.

Por ejemplo, si la técnica detecta una señal:

```text
frxXAUUSD
RISE
reason: moderate_bullish_pressure
score: 8
```

El motor debería consultar reglas como:

```text
asset:frxXAUUSD
direction:RISE
asset_direction:frxXAUUSD:RISE
reason:moderate_bullish_pressure
asset_reason:frxXAUUSD:moderate_bullish_pressure
score_band:8-9
```

Después debería comparar:

- cantidad mínima de muestras.
- win rate.
- profit neto.
- profit promedio.
- coincidencia entre reglas.

Si varias reglas parecidas son malas, el bot debería bloquear o degradar la señal.

Si varias reglas parecidas son buenas, el bot puede permitirla con más confianza.

## Qué hace hoy y qué falta

Hoy el proyecto ya hace esto:

- Guarda operaciones virtuales cerradas.
- Calcula win/loss.
- Calcula profit real usando payout de Deriv.
- Reconstruye reglas de aprendizaje.
- Separa el aprendizaje Deriv del legacy IQ Option.
- Expone aprendizaje por API.
- Guarda el archivo `data/deriv_learning.json`.

Todavía falta esto:

- Usar el aprendizaje como filtro antes de abrir operaciones.
- Bloquear combinaciones con bajo rendimiento.
- Favorecer combinaciones con rendimiento positivo.
- Mostrar el aprendizaje en el dashboard.
- Separar aprendizaje por sesión/horario si se desea.
- Registrar operaciones sombra bloqueadas por aprendizaje.

## Próximo paso recomendado

El siguiente paso lógico es agregar un filtro antes de abrir una operación.

Ejemplo de regla inicial:

```text
Si asset_direction tiene al menos 10 muestras
y win_rate < 50
y net_profit < 0
entonces bloquear la operación.
```

Otra regla:

```text
Si asset_reason tiene al menos 8 muestras
y win_rate >= 60
y net_profit > 0
entonces permitir la operación aunque otras reglas sean neutras.
```

Y una regla de seguridad:

```text
Si no hay suficientes muestras, no bloquear todavía.
Solo observar y aprender.
```

## Resumen simple

El aprendizaje actual funciona como una memoria estadística de operaciones cerradas.

No aprende con inteligencia artificial compleja todavía. Aprende por reglas medibles:

```text
esta combinación ganó X veces,
perdió Y veces,
dejó Z dólares,
y tiene N muestras.
```

Eso ya permite saber qué mercados, direcciones y patrones están funcionando mejor en Deriv.

La mejora real vendrá cuando esas reglas empiecen a influir en la decisión de abrir o bloquear nuevas operaciones.

## Actualizacion aplicada: aprendizaje como filtro real

Lo que faltaba para que el aprendizaje funcionara de verdad era que dejara de ser solo un reporte y entrara en el flujo vivo antes de abrir una operacion. Ya se agrego ese paso:

```text
estrategia detecta senal
-> se calculan las llaves de aprendizaje
-> se revisan reglas con suficientes muestras
-> se ponderan reglas buenas y malas
-> se permite, favorece, advierte o bloquea
-> si bloquea, se registra una sombra para medir si el bloqueo fue correcto
```

El filtro ahora evalua estas familias:

- `global`
- `asset`
- `direction`
- `asset_direction`
- `contract`
- `reason`
- `score_band`
- `factor_score`
- `asset_reason`

No todas pesan igual. Las reglas mas especificas, como `asset_direction` y `asset_reason`, pesan mas que reglas generales como `global`.

## Variables para endurecer o aflojar

Estas variables se pueden ajustar desde `.env` sin tocar codigo:

```text
LEARNING_FILTER_ENABLED=true
LEARNING_SHADOW_ENABLED=true
LEARNING_WARMUP_SAMPLES=18
LEARNING_MIN_RULE_SAMPLES=8
LEARNING_STRONG_RULE_SAMPLES=12
LEARNING_BLOCK_WIN_RATE_BELOW=49
LEARNING_BLOCK_AVG_PROFIT_BELOW=0
LEARNING_BLOCK_NET_PROFIT_BELOW=0
LEARNING_BLOCK_BAD_WEIGHT=2.35
LEARNING_CRITICAL_WIN_RATE_BELOW=42
LEARNING_CRITICAL_BAD_WEIGHT=1.25
LEARNING_ALLOW_WIN_RATE_AT_LEAST=57
LEARNING_ALLOW_MIN_AVG_PROFIT=0
LEARNING_ALLOW_GOOD_WEIGHT=1.45
LEARNING_WARNING_BAD_WEIGHT=1.25
LEARNING_SCORE_BOOST=1
LEARNING_SCORE_PENALTY=1
```

Pesos por tipo de regla:

```text
LEARNING_WEIGHT_GLOBAL=0.35
LEARNING_WEIGHT_ASSET=0.75
LEARNING_WEIGHT_DIRECTION=0.45
LEARNING_WEIGHT_ASSET_DIRECTION=1.35
LEARNING_WEIGHT_CONTRACT=0.45
LEARNING_WEIGHT_REASON=0.85
LEARNING_WEIGHT_SCORE_BAND=0.65
LEARNING_WEIGHT_FACTOR_SCORE=0.35
LEARNING_WEIGHT_ASSET_REASON=1.25
```

Para endurecer el filtro:

- Subir `LEARNING_MIN_RULE_SAMPLES`.
- Subir `LEARNING_BLOCK_BAD_WEIGHT` si quieres bloquear menos, o bajarlo si quieres bloquear mas.
- Subir `LEARNING_ALLOW_WIN_RATE_AT_LEAST` para exigir mas calidad antes de favorecer.
- Bajar `LEARNING_BLOCK_WIN_RATE_BELOW` bloquea solo casos mas evidentemente malos.
- Subir pesos de `ASSET_DIRECTION` y `ASSET_REASON` hace que combinaciones especificas manden mas.

Para aflojarlo:

- Bajar `LEARNING_MIN_RULE_SAMPLES`.
- Subir `LEARNING_BLOCK_WIN_RATE_BELOW` detecta reglas malas antes.
- Bajar `LEARNING_BLOCK_BAD_WEIGHT` hace que menos evidencia mala baste para bloquear.
- Bajar `LEARNING_ALLOW_WIN_RATE_AT_LEAST` permite favorecer reglas buenas con menos exigencia.

El punto inicial queda equilibrado: no bloquea en frio, espera 18 operaciones liquidadas globales, exige al menos 8 muestras por regla y solo bloquea cuando varias reglas con rendimiento negativo coinciden o cuando una regla especifica es criticamente mala.

## Dashboard agregado

El dashboard ahora muestra tarjetas de aprendizaje con:

- Total de operaciones liquidadas.
- Total de operaciones ganadas.
- Total de operaciones perdidas.
- Porcentaje de acierto general.
- Operaciones permitidas por aprendizaje.
- Operaciones bloqueadas por aprendizaje.
- Reglas activas.
- Sombras totales.
- Sombras ganadas.
- Sombras perdidas.
- Porcentaje de acierto de sombras.
- Sombras abiertas.
- Sombras creadas por bloqueo de aprendizaje.

## Como interpretar las sombras

Cuando el aprendizaje bloquea una senal, el bot no descuenta saldo ni abre la operacion virtual normal. En cambio registra una operacion sombra con la misma direccion, entrada aproximada y expiracion.

Despues, cuando llega la expiracion, la sombra se liquida como `shadow_settled`. Eso permite responder:

```text
Si el aprendizaje bloqueo esta operacion, habria ganado o perdido?
```

Si las sombras bloqueadas pierden con frecuencia, el filtro esta aportando valor. Si muchas sombras bloqueadas ganan, hay que aflojar los umbrales o revisar pesos.
