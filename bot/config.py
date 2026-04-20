from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    alpaca_api_key: str
    alpaca_api_secret: str
    alpaca_base_url: str
    schedule_cron: str
    lookback_days: int
    top_n_members: int
    max_notional_per_run: float
    notional_per_trade: float
    max_positions_per_run: int
    symbol_allowlist: set[str]
    symbol_blocklist: set[str]
    capitol_trades_api_url: str
    capitol_page_size: int


def _csv_set(value: str) -> set[str]:
    return {s.strip().upper() for s in value.split(",") if s.strip()}


def load_settings() -> Settings:
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    api_secret = os.getenv("ALPACA_API_SECRET", "").strip()

    if not api_key or not api_secret:
        raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET are required")

    return Settings(
        alpaca_api_key=api_key,
        alpaca_api_secret=api_secret,
        alpaca_base_url=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        schedule_cron=os.getenv("SCHEDULE_CRON", "*/30 * * * *"),
        lookback_days=int(os.getenv("LOOKBACK_DAYS", "90")),
        top_n_members=int(os.getenv("TOP_N_MEMBERS", "5")),
        max_notional_per_run=float(os.getenv("MAX_NOTIONAL_PER_RUN", "3000")),
        notional_per_trade=float(os.getenv("NOTIONAL_PER_TRADE", "500")),
        max_positions_per_run=int(os.getenv("MAX_POSITIONS_PER_RUN", "6")),
        symbol_allowlist=_csv_set(os.getenv("SYMBOL_ALLOWLIST", "")),
        symbol_blocklist=_csv_set(os.getenv("SYMBOL_BLOCKLIST", "")),
        capitol_trades_api_url=os.getenv("CAPITOL_TRADES_API_URL", "https://www.capitoltrades.com/trades"),
        capitol_page_size=int(os.getenv("CAPITOL_PAGE_SIZE", "96")),
    )
