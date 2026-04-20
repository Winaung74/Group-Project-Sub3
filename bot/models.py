from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CapitolTrade:
    trade_id: str
    traded_at: datetime
    member_name: str
    symbol: str
    action: str  # BUY or SELL
    amount_low: float | None = None
    amount_high: float | None = None


@dataclass(frozen=True)
class MemberScore:
    member_name: str
    roi: float
    realized_pnl: float
    invested_capital: float
