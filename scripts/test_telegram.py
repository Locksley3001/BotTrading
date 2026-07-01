from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT_DIR, get_settings
from app.event_store import LocalJsonlEventStore
from app.telegram_notifier import TelegramNotifier


async def main() -> int:
    settings = get_settings()
    lines = [f"# Telegram test report\n\nGenerated: {datetime.now(UTC).isoformat()}\n"]
    notifier = TelegramNotifier(settings, LocalJsonlEventStore(settings.data_dir))
    if not notifier.configured:
        lines.append("- Status: BLOCKED, Telegram token/chat id missing.")
        (ROOT_DIR / "TELEGRAM_TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    try:
        result = await notifier.send_test_message()
        lines.append(f"- Status: {'OK' if result.get('ok') else 'FAILED'}")
        lines.append(f"- Message id present: {bool(result.get('message_id'))}")
        code = 0 if result.get("ok") else 1
    except Exception as exc:
        lines.append(f"- Status: FAILED ({type(exc).__name__})")
        code = 1
    (ROOT_DIR / "TELEGRAM_TEST_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
