from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    scan_interval_seconds: int = 30
    market_open_hour_et: int = 9
    market_open_minute_et: int = 30
    market_close_hour_et: int = 16

    min_dollar_volume: float = 5_000_000
    min_relative_volume: float = 1.5
    min_reward_to_risk: float = 2.0
    max_active_positions: int = 5
    risk_per_trade: float = 200.0  # Max dollars risked per trade (entry - stop) * qty
    max_position_value: float = 5000.0  # Max dollar value of any single position
    watchlist: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["NVDA", "TSLA", "AMD", "MSFT", "AAPL"]
    )
    dynamic_watchlist_enabled: bool = True
    watchlist_refresh_minutes: int = 15
    watchlist_size: int = 30

    # Universe selector thresholds
    universe_min_price: float = 5.0
    universe_min_rel_vol: float = 1.2
    universe_min_atr_pct: float = 1.5

    # Composite score weights
    weight_rel_vol: float = 3.0
    weight_atr_pct: float = 2.5
    weight_momentum: float = 1.5
    weight_gap: float = 2.0
    weight_dollar_vol: float = 1.0

    @field_validator("watchlist", mode="before")
    @classmethod
    def parse_watchlist(cls, value: object) -> object:
        if isinstance(value, str):
            return [s.strip().upper() for s in value.split(",") if s.strip()]
        return value

    alpaca_paper: bool = True
    alpaca_live_enabled: bool = False
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    polygon_api_key: str = ""
    polygon_base_url: str = "https://api.polygon.io"

    finnhub_api_key: str = ""  # Finnhub free tier: real-time WS trades (50 symbols) + Quote (60/min)

    websocket_exit_enabled: bool = False  # Enable Alpaca IEX WebSocket for real-time exit monitoring

    discord_webhook_url: str = ""

    sqlite_path: str = "./breakoutbolt.db"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
