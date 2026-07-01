from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ROOT_DIR, get_settings
from app.deriv_adapter import DerivAPIError, DerivPublicClient, callput_contract_types, duration_offered, verify_longcode_mapping
from app.models import SignalDirection


def line(items: list[str]) -> str:
    return "| " + " | ".join(items) + " |"


async def main() -> int:
    settings = get_settings()
    client = DerivPublicClient(settings)
    report_dir = ROOT_DIR
    timestamp = datetime.now(UTC).isoformat()
    connectivity: list[str] = [f"# Deriv public connectivity report\n\nGenerated: {timestamp}\n"]
    research: list[str] = [f"# Deriv market research\n\nGenerated: {timestamp}\n"]
    mapping: list[str] = [f"# Deriv contract mapping report\n\nGenerated: {timestamp}\n"]

    failures: list[str] = []

    try:
        ping = await client.ping()
        connectivity.append(f"- Ping: OK ({ping.latency_ms:.2f} ms)")
    except Exception as exc:
        connectivity.append(f"- Ping: FAILED ({type(exc).__name__})")
        failures.append("ping")

    try:
        server_time = await client.server_time()
        connectivity.append(f"- Time: OK (`{server_time.response.get('time')}`)")
    except Exception as exc:
        connectivity.append(f"- Time: FAILED ({type(exc).__name__})")
        failures.append("time")

    active: list[dict[str, Any]] = []
    try:
        active = await client.active_symbols()
        markets = sorted({item.get("market") for item in active if item.get("market")})
        non_synthetic = [item for item in active if item.get("market") != "synthetic_index"]
        connectivity.append(f"- Active symbols: OK ({len(active)} total, {len(non_synthetic)} non synthetic)")
        research.append(f"- Active symbols total: {len(active)}")
        research.append(f"- Non synthetic active symbols: {len(non_synthetic)}")
        research.append(f"- Markets seen: {', '.join(markets)}")
    except Exception as exc:
        connectivity.append(f"- Active symbols: FAILED ({type(exc).__name__})")
        failures.append("active_symbols")

    try:
        contracts_list = await client.contracts_list()
        connectivity.append(f"- Contracts list: OK ({len(str(contracts_list))} chars)")
    except Exception as exc:
        connectivity.append(f"- Contracts list: FAILED ({type(exc).__name__})")
        failures.append("contracts_list")

    research.append("\n## Configured markets\n")
    research.append(line(["Symbol", "Market", "Open", "CALL/PUT", "Duration", "1m rejected"]))
    research.append(line(["---", "---", "---", "---", "---", "---"]))
    mapping.append("\n## Proposal longcode verification\n")
    mapping.append(line(["Symbol", "Direction", "Contract", "Verified", "Payout rate", "Longcode sample"]))
    mapping.append(line(["---", "---", "---", "---", "---", "---"]))

    active_by_symbol = {item.get("symbol") or item.get("underlying_symbol"): item for item in active}
    test_symbols = settings.live_test_markets or settings.markets
    for symbol in test_symbols:
        raw_symbol = active_by_symbol.get(symbol, {})
        market = str(raw_symbol.get("market") or "")
        duration, duration_unit = settings.duration_for_market(market, symbol)
        one_minute_rejected = "not_tested"
        try:
            contracts = await client.contracts_for(symbol)
            types = callput_contract_types(contracts)
            call_put = "yes" if {"CALL", "PUT"}.issubset(types) else "no"
            duration_ok = all(
                duration_offered(contracts, contract_type, duration, duration_unit)
                for contract_type in ("CALL", "PUT")
            )
            try:
                await client.proposal(
                    symbol=symbol,
                    contract_type="CALL",
                    amount=settings.live_test_max_stake,
                    duration=1,
                    duration_unit="m",
                )
                one_minute_rejected = "accepted"
            except DerivAPIError:
                one_minute_rejected = "rejected"
            research.append(
                line(
                    [
                        symbol,
                        market or "-",
                        str(raw_symbol.get("exchange_is_open", "-")),
                        call_put,
                        f"{duration}{duration_unit} {'ok' if duration_ok else 'blocked'}",
                        one_minute_rejected,
                    ]
                )
            )
            if call_put == "yes" and duration_ok:
                for direction, contract_type in ((SignalDirection.RISE, "CALL"), (SignalDirection.FALL, "PUT")):
                    proposal = await client.proposal(
                        symbol=symbol,
                        contract_type=contract_type,
                        amount=settings.live_test_max_stake,
                        duration=duration,
                        duration_unit=duration_unit,
                    )
                    check = verify_longcode_mapping(direction, contract_type, proposal.longcode)
                    mapping.append(
                        line(
                            [
                                symbol,
                                direction.value,
                                contract_type,
                                "yes" if check.verified else "no",
                                f"{proposal.payout_rate:.4f}",
                                proposal.longcode[:120].replace("|", "/"),
                            ]
                        )
                    )
        except Exception as exc:
            research.append(line([symbol, market or "-", "-", f"failed:{type(exc).__name__}", "-", "-"]))
            failures.append(f"market:{symbol}")

    if test_symbols:
        symbol = test_symbols[0]
        try:
            candles = await client.ticks_history(symbol, count=20, granularity=60)
            connectivity.append(f"- ticks_history 60s `{symbol}`: OK ({len(candles)} candles)")
        except Exception as exc:
            connectivity.append(f"- ticks_history 60s `{symbol}`: FAILED ({type(exc).__name__})")
            failures.append("ticks_history")
        tick_success = False
        tick_errors: list[str] = []
        for tick_symbol in test_symbols:
            await asyncio.sleep(0.5)
            try:
                ticks = await client.stream_ticks(tick_symbol, seconds=15)
                if ticks:
                    connectivity.append(f"- realtime ticks `{tick_symbol}`: OK ({len(ticks)} ticks in 15s)")
                    tick_success = True
                    break
                tick_errors.append(f"{tick_symbol}:empty")
            except Exception as exc:
                tick_errors.append(f"{tick_symbol}:{type(exc).__name__}")
        if not tick_success:
            connectivity.append(f"- realtime ticks: FAILED ({', '.join(tick_errors)})")
            failures.append("ticks")

    connectivity.append(f"\nOverall: {'FAILED' if failures else 'PASSED'}")
    if failures:
        connectivity.append(f"\nFailures: {', '.join(failures)}")

    (report_dir / "DERIV_PUBLIC_CONNECTIVITY_REPORT.md").write_text("\n".join(connectivity) + "\n", encoding="utf-8")
    (report_dir / "DERIV_MARKET_RESEARCH.md").write_text("\n".join(research) + "\n", encoding="utf-8")
    (report_dir / "DERIV_CONTRACT_MAPPING_REPORT.md").write_text("\n".join(mapping) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
