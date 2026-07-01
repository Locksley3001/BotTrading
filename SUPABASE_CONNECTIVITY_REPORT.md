# Supabase connectivity report

Generated: 2026-07-01T19:54:31.184884+00:00

- Project reachable/auth accepted: OK
- Legacy table `bot_state_files` HTTP status: 404
- Exposed legacy table `bot_state_file` write probe: OK
- Deriv table `deriv.trade_events` HTTP status: 406
- Deriv schema ready for REST writes: PENDING
- Deriv REST reason: `{"code":"PGRST106","details":null,"hint":"Only the following schemas are exposed: public, graphql_public","message":"Invalid schema: deriv"}`
- Deriv write probe: SKIPPED because schema/table is not ready through REST.
- DDL note: Deriv schema creation must be applied from `supabase/migrations/001_deriv_schema.sql`; service role REST cannot safely run arbitrary SQL.
