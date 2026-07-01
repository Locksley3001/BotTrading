from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT_DIR, get_settings


def main() -> int:
    settings = get_settings()
    lines = [f"# Deriv DEMO authenticated test report\n\nGenerated: {datetime.now(UTC).isoformat()}\n"]
    lines.append(f"- RUN_LIVE_DERIV_DEMO_TESTS: {settings.run_live_deriv_demo_tests}")
    lines.append(f"- RUN_LIVE_DERIV_BUY_TESTS: {settings.run_live_deriv_buy_tests}")
    lines.append(f"- DERIV_ACCOUNT_MODE: {settings.deriv_account_mode}")
    lines.append(f"- Auth configured without exposing secrets: {settings.auth_configured}")
    if not settings.run_live_deriv_demo_tests:
        lines.append("- Status: SKIPPED. Demo authenticated tests are disabled by env gate.")
        code = 0
    elif not settings.auth_configured:
        lines.append("- Status: BLOCKED. Official Deriv app/account/token or legacy API token is required; email/password is not enough for safe API trading.")
        code = 1
    elif settings.run_live_deriv_buy_tests and not settings.demo_buy_tests_allowed:
        lines.append("- Status: BLOCKED. Buy test gates are not all safe for DEMO stake <= 1.")
        code = 1
    else:
        lines.append("- Status: READY. Authenticated socket implementation is gated for the next development pass.")
        code = 0
    (ROOT_DIR / "DERIV_DEMO_AUTH_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
