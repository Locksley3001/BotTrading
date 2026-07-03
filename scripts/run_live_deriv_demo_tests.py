from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT_DIR, get_settings
from app.deriv_adapter import DerivAuthenticatedClient, safe_authorize_payload


async def main() -> int:
    settings = get_settings()
    lines = [f"# Deriv DEMO authenticated test report\n\nGenerated: {datetime.now(UTC).isoformat()}\n"]
    lines.append(f"- RUN_LIVE_DERIV_DEMO_TESTS: {settings.run_live_deriv_demo_tests}")
    lines.append(f"- RUN_LIVE_DERIV_BUY_TESTS: {settings.run_live_deriv_buy_tests}")
    lines.append(f"- DERIV_ACCOUNT_MODE: {settings.deriv_account_mode}")
    lines.append(f"- Auth configured without exposing secrets: {settings.auth_configured}")
    requirements = settings.deriv_auth_requirements()
    lines.append(f"- Ready for authorize: {requirements['ready_for_authorize']}")
    lines.append(f"- Missing config: {', '.join(requirements['missing']) if requirements['missing'] else 'none'}")
    if not settings.run_live_deriv_demo_tests:
        lines.append("- Status: SKIPPED. Demo authenticated tests are disabled by env gate.")
        code = 0
    elif not requirements["ready_for_authorize"]:
        lines.append("- Status: BLOCKED. Official Deriv app id plus authorization token is required; email/password is not enough for safe API trading.")
        code = 1
    elif settings.run_live_deriv_buy_tests and not settings.demo_buy_tests_allowed:
        lines.append("- Status: BLOCKED. Buy test gates are not all safe for DEMO stake <= 1.")
        code = 1
    else:
        try:
            result = await DerivAuthenticatedClient(settings).authorize()
            account = safe_authorize_payload(result.response)
            lines.append(f"- Authorize: OK ({result.latency_ms:.2f} ms)")
            lines.append(f"- Login ID: `{account.get('loginid')}`")
            lines.append(f"- Is virtual: `{account.get('is_virtual')}`")
            lines.append(f"- Currency: `{account.get('currency')}`")
            lines.append(f"- Scopes: `{', '.join(account.get('scopes') or [])}`")
            lines.append("- Status: READY. Authenticated Deriv connection works.")
            code = 0
        except Exception as exc:
            lines.append(f"- Authorize: FAILED ({type(exc).__name__})")
            lines.append("- Status: FAILED. Check DERIV_APP_ID, token permissions, account region, and token validity.")
            code = 1
    (ROOT_DIR / "DERIV_DEMO_AUTH_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
