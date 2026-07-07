from app.config import Settings
from app.deriv_adapter import callput_contract_types, duration_offered, market_candidate, verify_longcode_mapping
from app.models import DerivSymbol, SignalDirection


def test_rise_call_longcode_must_confirm_higher() -> None:
    mapping = verify_longcode_mapping(
        SignalDirection.RISE,
        "CALL",
        "Win payout if the exit spot is higher than the entry spot.",
    )
    assert mapping.verified


def test_fall_put_longcode_must_confirm_lower() -> None:
    mapping = verify_longcode_mapping(
        SignalDirection.FALL,
        "PUT",
        "Win payout if the exit spot is lower than the entry spot.",
    )
    assert mapping.verified


def test_wrong_longcode_blocks_mapping() -> None:
    mapping = verify_longcode_mapping(SignalDirection.RISE, "CALL", "Win if the exit spot is lower.")
    assert not mapping.verified
    assert mapping.reason == "longcode_does_not_confirm_direction"


def test_contract_types_filter_callput_only() -> None:
    contracts = {
        "available": [
            {"contract_category": "callput", "contract_type": "CALL"},
            {"contract_category": "callput", "contract_type": "PUT"},
            {"contract_category": "multiplier", "contract_type": "MULTUP"},
        ]
    }
    assert callput_contract_types(contracts) == {"CALL", "PUT"}


def test_duration_validation_uses_contract_range() -> None:
    contracts = {
        "available": [
            {
                "contract_category": "callput",
                "contract_type": "CALL",
                "min_contract_duration": "5m",
                "max_contract_duration": "1d",
            }
        ]
    }
    assert duration_offered(contracts, "CALL", 5, "m")
    assert duration_offered(contracts, "CALL", 15, "m")
    assert not duration_offered(contracts, "CALL", 1, "m")


def test_synthetic_market_is_blocked_by_default() -> None:
    settings = Settings(DERIV_ALLOW_SYNTHETIC_MARKETS=False, DERIV_EXCLUDED_MARKETS="synthetic_index")
    symbol = DerivSymbol(
        symbol="R_100",
        display_name="Volatility 100",
        market="synthetic_index",
        exchange_is_open=True,
    )
    allowed, reason = market_candidate(symbol, settings)
    assert not allowed
    assert reason == "synthetic_index_blocked"
