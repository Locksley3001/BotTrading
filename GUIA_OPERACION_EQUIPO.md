# Guía de operación

1. Verificar `/health`.
2. Ejecutar `POST /api/deriv/market-discovery`.
3. Revisar que los mercados habilitados tengan `mapping_verified=true`.
4. Confirmar que `BROKER_TRADING_ENABLED=false` mientras no exista autenticación Deriv segura.
5. Aplicar migración Supabase antes de usar el store remoto de Deriv.
6. Usar `/api/telegram/test` solo para validar conectividad; Telegram no dispara operaciones.
7. Para DEMO autenticado, configurar tokens oficiales Deriv. Email y contraseña no bastan para comprar por API de forma segura.
