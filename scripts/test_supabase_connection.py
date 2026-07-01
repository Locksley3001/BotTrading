from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT_DIR, get_settings
from app.event_store import LocalJsonlEventStore
from app.supabase_store import SupabaseEventStore


async def main() -> int:
    settings = get_settings()
    lines = [f"# Supabase connectivity report\n\nGenerated: {datetime.now(UTC).isoformat()}\n"]
    if not settings.supabase_url or not settings.supabase_server_key:
        lines.append("- Status: BLOCKED, missing Supabase URL or key.")
        (ROOT_DIR / "SUPABASE_CONNECTIVITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    store = SupabaseEventStore(settings, LocalJsonlEventStore(settings.data_dir))
    try:
        health = await store.healthcheck()
        lines.append(f"- Project reachable/auth accepted: {'OK' if health['project_reachable'] else 'FAILED'}")
        lines.append(f"- Legacy table `{health['legacy_table']}` HTTP status: {health['legacy_table_status']}")
        lines.append(f"- Deriv table `{health['deriv_schema']}.{health['deriv_event_table']}` HTTP status: {health['deriv_table_status']}")
        lines.append(f"- Deriv schema ready for REST writes: {'OK' if health['deriv_ready'] else 'PENDING'}")
        if health.get("deriv_error"):
            lines.append(f"- Deriv REST reason: `{health['deriv_error']}`")
        if health["deriv_ready"]:
            probe_id = f"evt_probe_{uuid4().hex}"
            probe = {
                "id": probe_id,
                "signal_id": None,
                "event_type": "supabase_write_probe",
                "idempotency_key": f"supabase_write_probe:{probe_id}",
                "asset": None,
                "market": None,
                "occurred_at": datetime.now(UTC).isoformat(),
                "payload": {"probe": True},
                "source": "deriv_bot_probe",
            }
            headers = store._headers_for_schema(settings.supabase_deriv_schema)
            url = f"{settings.supabase_url.rstrip()}/rest/v1/{settings.supabase_event_table}?on_conflict=idempotency_key"
            async with httpx.AsyncClient(timeout=settings.supabase_timeout_seconds) as client:
                write = await client.post(url, headers=headers, json=probe)
                read = await client.get(
                    f"{settings.supabase_url.rstrip()}/rest/v1/{settings.supabase_event_table}?select=id,event_type&id=eq.{probe_id}",
                    headers=store._headers_for_schema(settings.supabase_deriv_schema, write=False),
                )
            lines.append(f"- Deriv write probe HTTP status: {write.status_code}")
            lines.append(f"- Deriv readback probe HTTP status: {read.status_code}")
            lines.append(f"- Deriv write/readback: {'OK' if write.status_code < 400 and read.status_code == 200 and probe_id in read.text else 'FAILED'}")
        else:
            lines.append("- Deriv write probe: SKIPPED because schema/table is not ready through REST.")
        lines.append("- DDL note: Deriv schema creation must be applied from `supabase/migrations/001_deriv_schema.sql`; service role REST cannot safely run arbitrary SQL.")
        code = 0 if health["project_reachable"] else 1
    except Exception as exc:
        lines.append(f"- Status: FAILED ({type(exc).__name__})")
        code = 1
    (ROOT_DIR / "SUPABASE_CONNECTIVITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
