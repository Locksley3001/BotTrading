from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[1]


def _load_env_files() -> None:
    """Load local env files without requiring one canonical filename."""
    load_dotenv(ROOT_DIR / ".env", override=False)
    load_dotenv(ROOT_DIR / ".env.txt", override=False)


def _csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item.strip() for item in value if item.strip()]
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=False,
        enable_decoding=False,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    python_version: str = Field(default="3.12.8", alias="PYTHON_VERSION")

    broker_provider: Literal["deriv"] = Field(default="deriv", alias="BROKER_PROVIDER")
    broker_trading_enabled: bool = Field(default=False, alias="BROKER_TRADING_ENABLED")
    broker_sync_strict_mode: bool = Field(default=True, alias="BROKER_SYNC_STRICT_MODE")

    deriv_api_profile: Literal["current_oauth", "legacy_token"] = Field(
        default="current_oauth", alias="DERIV_API_PROFILE"
    )
    deriv_public_ws_url: str = Field(
        default="wss://api.derivws.com/trading/v1/options/ws/public",
        alias="DERIV_PUBLIC_WS_URL",
    )
    deriv_rest_base_url: str = Field(default="https://api.derivws.com", alias="DERIV_REST_BASE_URL")
    deriv_auth_base_url: str = Field(default="https://auth.deriv.com", alias="DERIV_AUTH_BASE_URL")
    deriv_app_id: SecretStr | None = Field(default=None, alias="DERIV_APP_ID")
    deriv_client_id: SecretStr | None = Field(default=None, alias="DERIV_CLIENT_ID")
    deriv_redirect_uri: str | None = Field(default=None, alias="DERIV_REDIRECT_URI")
    deriv_account_id: SecretStr | None = Field(default=None, alias="DERIV_ACCOUNT_ID")
    deriv_access_token: SecretStr | None = Field(default=None, alias="DERIV_ACCESS_TOKEN")
    deriv_refresh_token: SecretStr | None = Field(default=None, alias="DERIV_REFRESH_TOKEN")
    deriv_legacy_api_token: SecretStr | None = Field(default=None, alias="DERIV_LEGACY_API_TOKEN")
    deriv_currency: str = Field(default="USD", alias="DERIV_CURRENCY")
    deriv_account_mode: Literal["DEMO", "REAL"] = Field(default="DEMO", alias="DERIV_ACCOUNT_MODE")

    deriv_allow_synthetic_markets: bool = Field(default=False, alias="DERIV_ALLOW_SYNTHETIC_MARKETS")
    deriv_allowed_markets: list[str] = Field(default_factory=lambda: ["forex", "commodities"], alias="DERIV_ALLOWED_MARKETS")
    deriv_optional_markets: list[str] = Field(default_factory=lambda: ["indices"], alias="DERIV_OPTIONAL_MARKETS")
    deriv_excluded_markets: list[str] = Field(default_factory=lambda: ["synthetic_index"], alias="DERIV_EXCLUDED_MARKETS")
    deriv_excluded_submarkets: list[str] = Field(
        default_factory=lambda: ["random_index", "crash_index", "jump_index", "step_indices", "range_break", "forex_basket"],
        alias="DERIV_EXCLUDED_SUBMARKETS",
    )
    deriv_excluded_symbol_patterns: list[str] = Field(
        default_factory=lambda: ["R_", "1HZ", "BOOM", "CRASH", "JUMP", "STEP", "WLDAUD", "WLDEUR", "WLDGBP", "WLDUSD"],
        alias="DERIV_EXCLUDED_SYMBOL_PATTERNS",
    )
    deriv_market_discovery_on_start: bool = Field(default=True, alias="DERIV_MARKET_DISCOVERY_ON_START")
    deriv_verify_contracts_on_start: bool = Field(default=True, alias="DERIV_VERIFY_CONTRACTS_ON_START")
    deriv_verify_contract_mapping_on_start: bool = Field(default=True, alias="DERIV_VERIFY_CONTRACT_MAPPING_ON_START")

    deriv_contract_category: str = Field(default="callput", alias="DERIV_CONTRACT_CATEGORY")
    deriv_rise_contract_type: str = Field(default="CALL", alias="DERIV_RISE_CONTRACT_TYPE")
    deriv_fall_contract_type: str = Field(default="PUT", alias="DERIV_FALL_CONTRACT_TYPE")
    deriv_allow_equals: bool = Field(default=False, alias="DERIV_ALLOW_EQUALS")
    deriv_primary_markets: list[str] = Field(
        default_factory=lambda: ["frxXAUUSD", "frxXAGUSD", "frxEURUSD", "frxGBPUSD", "frxUSDJPY", "frxAUDUSD"],
        alias="DERIV_PRIMARY_MARKETS",
    )
    deriv_default_duration: int = Field(default=15, alias="DERIV_DEFAULT_DURATION")
    deriv_default_duration_unit: str = Field(default="m", alias="DERIV_DEFAULT_DURATION_UNIT")
    deriv_metals_duration: int = Field(default=5, alias="DERIV_METALS_DURATION")
    deriv_metals_duration_unit: str = Field(default="m", alias="DERIV_METALS_DURATION_UNIT")
    deriv_forex_duration: int = Field(default=15, alias="DERIV_FOREX_DURATION")
    deriv_forex_duration_unit: str = Field(default="m", alias="DERIV_FOREX_DURATION_UNIT")
    deriv_indices_duration: int = Field(default=15, alias="DERIV_INDICES_DURATION")
    deriv_indices_duration_unit: str = Field(default="m", alias="DERIV_INDICES_DURATION_UNIT")
    deriv_stake_basis: str = Field(default="stake", alias="DERIV_STAKE_BASIS")
    deriv_min_stake: float = Field(default=1.0, alias="DERIV_MIN_STAKE")
    deriv_max_stake: float = Field(default=10000.0, alias="DERIV_MAX_STAKE")
    deriv_min_payout_rate: float = Field(default=0.65, alias="DERIV_MIN_PAYOUT_RATE")
    deriv_proposal_max_age_ms: int = Field(default=1500, alias="DERIV_PROPOSAL_MAX_AGE_MS")

    markets: list[str] = Field(
        default_factory=lambda: ["frxXAUUSD", "frxXAGUSD", "frxEURUSD", "frxGBPUSD", "frxUSDJPY", "frxAUDUSD"],
        alias="MARKETS",
    )
    disabled_markets: list[str] = Field(default_factory=list, alias="DISABLED_MARKETS")
    default_timeframe: int = Field(default=300, alias="DEFAULT_TIMEFRAME")
    candle_count: int = Field(default=120, alias="CANDLE_COUNT")
    poll_interval_seconds: float = Field(default=0.75, alias="POLL_INTERVAL_SECONDS")
    signal_cooldown_seconds: int = Field(default=300, alias="SIGNAL_COOLDOWN_SECONDS")
    market_scan_interval_seconds: float = Field(default=30.0, alias="MARKET_SCAN_INTERVAL_SECONDS")

    virtual_initial_balance: float = Field(default=100.0, alias="VIRTUAL_INITIAL_BALANCE")
    virtual_target_balance: float = Field(default=150.0, alias="VIRTUAL_TARGET_BALANCE")
    virtual_cautious_stake: float = Field(default=10.0, alias="VIRTUAL_CAUTIOUS_STAKE")
    virtual_safe_stake: float = Field(default=10.0, alias="VIRTUAL_SAFE_STAKE")
    virtual_payout_rate: float = Field(default=0.85, alias="VIRTUAL_PAYOUT_RATE")
    virtual_max_concurrent_trades: int = Field(default=5, alias="VIRTUAL_MAX_CONCURRENT_TRADES")

    telegram_enabled: bool = Field(default=True, alias="TELEGRAM_ENABLED")
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: SecretStr | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_min_score: int = Field(default=7, alias="TELEGRAM_MIN_SCORE")
    telegram_summary_batch_size: int = Field(default=5, alias="TELEGRAM_SUMMARY_BATCH_SIZE")

    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_secret_key: SecretStr | None = Field(default=None, alias="SUPABASE_SECRET_KEY")
    supabase_service_role_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_service_key: SecretStr | None = Field(default=None, alias="SUPABASE_SERVICE_KEY")
    supabase_key: SecretStr | None = Field(default=None, alias="SUPABASE_KEY")
    supabase_anon_key: SecretStr | None = Field(default=None, alias="SUPABASE_ANON_KEY")
    supabase_schema: str = Field(default="public", alias="SUPABASE_SCHEMA")
    supabase_deriv_schema: str = Field(default="deriv", alias="SUPABASE_DERIV_SCHEMA")
    supabase_event_table: str = Field(default="trade_events", alias="SUPABASE_EVENT_TABLE")
    supabase_signal_table: str = Field(default="signals", alias="SUPABASE_SIGNAL_TABLE")
    supabase_broker_order_table: str = Field(default="broker_orders", alias="SUPABASE_BROKER_ORDER_TABLE")
    supabase_telegram_event_table: str = Field(default="telegram_events", alias="SUPABASE_TELEGRAM_EVENT_TABLE")
    supabase_market_catalog_table: str = Field(default="deriv_market_catalog", alias="SUPABASE_MARKET_CATALOG_TABLE")
    supabase_state_enabled: bool = Field(default=True, alias="SUPABASE_STATE_ENABLED")
    supabase_state_table: str = Field(default="bot_state_files", alias="SUPABASE_STATE_TABLE")
    supabase_versions_table: str = Field(default="bot_state_file_versions", alias="SUPABASE_VERSIONS_TABLE")
    supabase_timeout_seconds: float = Field(default=12.0, alias="SUPABASE_TIMEOUT_SECONDS")
    supabase_legacy_migration_enabled: bool = Field(default=True, alias="SUPABASE_LEGACY_MIGRATION_ENABLED")
    supabase_legacy_read_only: bool = Field(default=True, alias="SUPABASE_LEGACY_READ_ONLY")
    supabase_save_ticks: bool = Field(default=False, alias="SUPABASE_SAVE_TICKS")
    supabase_save_candles: bool = Field(default=False, alias="SUPABASE_SAVE_CANDLES")
    supabase_save_analysis_snapshots: bool = Field(default=False, alias="SUPABASE_SAVE_ANALYSIS_SNAPSHOTS")

    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    run_live_deriv_public_tests: bool = Field(default=True, alias="RUN_LIVE_DERIV_PUBLIC_TESTS")
    run_live_deriv_demo_tests: bool = Field(default=False, alias="RUN_LIVE_DERIV_DEMO_TESTS")
    run_live_deriv_buy_tests: bool = Field(default=False, alias="RUN_LIVE_DERIV_BUY_TESTS")
    live_test_markets: list[str] = Field(default_factory=lambda: ["frxXAUUSD", "frxXAGUSD", "frxEURUSD"], alias="LIVE_TEST_MARKETS")
    live_test_max_stake: float = Field(default=1.0, alias="LIVE_TEST_MAX_STAKE")
    live_test_allow_real: bool = Field(default=False, alias="LIVE_TEST_ALLOW_REAL")

    @field_validator(
        "deriv_allowed_markets",
        "deriv_optional_markets",
        "deriv_excluded_markets",
        "deriv_excluded_submarkets",
        "deriv_excluded_symbol_patterns",
        "deriv_primary_markets",
        "markets",
        "disabled_markets",
        "live_test_markets",
        mode="before",
    )
    @classmethod
    def parse_csv(cls, value: str | list[str] | None) -> list[str]:
        return _csv(value)

    @property
    def supabase_server_key(self) -> SecretStr | None:
        return (
            self.supabase_secret_key
            or self.supabase_service_role_key
            or self.supabase_service_key
            or self.supabase_key
            or self.supabase_anon_key
        )

    @property
    def auth_configured(self) -> bool:
        if self.deriv_api_profile == "legacy_token":
            return bool(self.deriv_app_id and self.deriv_legacy_api_token)
        return bool(self.deriv_app_id and self.deriv_access_token and self.deriv_account_id)

    @property
    def demo_buy_tests_allowed(self) -> bool:
        return (
            self.run_live_deriv_demo_tests
            and self.run_live_deriv_buy_tests
            and self.deriv_account_mode == "DEMO"
            and not self.live_test_allow_real
            and self.live_test_max_stake <= 1
        )

    def duration_for_market(self, market: str, symbol: str) -> tuple[int, str]:
        if market == "commodities" or symbol in {"frxXAUUSD", "frxXAGUSD"}:
            return self.deriv_metals_duration, self.deriv_metals_duration_unit
        if market == "indices":
            return self.deriv_indices_duration, self.deriv_indices_duration_unit
        if market == "forex":
            return self.deriv_forex_duration, self.deriv_forex_duration_unit
        return self.deriv_default_duration, self.deriv_default_duration_unit

    def safe_status(self) -> dict[str, object]:
        return {
            "app_env": self.app_env,
            "broker_provider": self.broker_provider,
            "broker_trading_enabled": self.broker_trading_enabled,
            "deriv_api_profile": self.deriv_api_profile,
            "deriv_account_mode": self.deriv_account_mode,
            "deriv_public_ws_url_configured": bool(self.deriv_public_ws_url),
            "deriv_auth_configured": self.auth_configured,
            "supabase_configured": bool(self.supabase_url and self.supabase_server_key),
            "telegram_configured": bool(self.telegram_bot_token and self.telegram_chat_id),
        }


@lru_cache
def get_settings() -> Settings:
    _load_env_files()
    settings = Settings()
    settings.data_dir = (ROOT_DIR / settings.data_dir).resolve()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
