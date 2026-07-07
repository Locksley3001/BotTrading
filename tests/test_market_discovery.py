import pytest

from app.config import Settings
from app.market_discovery import MarketDiscoveryService


class FakeClient:
    async def active_symbols(self):
        return [
            {
                "symbol": "frxXAUUSD",
                "display_name": "Gold/USD",
                "market": "commodities",
                "submarket": "metals",
                "exchange_is_open": 1,
                "is_trading_suspended": 0,
            },
            {
                "symbol": "R_100",
                "display_name": "Volatility 100",
                "market": "synthetic_index",
                "exchange_is_open": 1,
                "is_trading_suspended": 0,
            },
        ]

    async def contracts_for(self, symbol):
        return {
            "available": [
                {
                    "contract_category": "callput",
                    "contract_type": "CALL",
                    "min_contract_duration": "5m",
                    "max_contract_duration": "1d",
                },
                {
                    "contract_category": "callput",
                    "contract_type": "PUT",
                    "min_contract_duration": "5m",
                    "max_contract_duration": "1d",
                },
            ]
        }

    async def proposal(self, *, symbol, contract_type, amount, duration, duration_unit):
        from app.models import Proposal, SignalDirection

        longcode = (
            "Win payout if the exit spot is higher than the entry spot."
            if contract_type == "CALL"
            else "Win payout if the exit spot is lower than the entry spot."
        )
        return Proposal(
            proposal_id=f"{symbol}-{contract_type}",
            symbol=symbol,
            direction=SignalDirection.RISE if contract_type == "CALL" else SignalDirection.FALL,
            contract_type=contract_type,
            ask_price=1,
            payout=1.8,
            payout_rate=0.8,
            longcode=longcode,
        )


@pytest.mark.asyncio
async def test_market_discovery_enables_only_verified_non_synthetic() -> None:
    settings = Settings(
        MARKETS="frxXAUUSD,R_100",
        DERIV_ALLOW_SYNTHETIC_MARKETS=False,
        DERIV_EXCLUDED_MARKETS="synthetic_index",
    )
    service = MarketDiscoveryService(settings, FakeClient())
    markets, events = await service.discover()
    by_symbol = {market.symbol: market for market in markets}
    assert by_symbol["frxXAUUSD"].enabled
    assert by_symbol["frxXAUUSD"].mapping_verified
    assert not by_symbol["R_100"].enabled
    assert by_symbol["R_100"].blocked_reason == "synthetic_index_blocked"
    assert len(events) == 2
