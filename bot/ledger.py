from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.models import CapitolTrade, MemberScore


@dataclass
class Fill:
    qty: float
    price: float


class TradeLedger:
    def __init__(self, db_path: str = "state/trades.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS copied_trades (
                    trade_id TEXT PRIMARY KEY,
                    traded_at TEXT NOT NULL,
                    member_name TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    qty REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    notional REAL NOT NULL
                )
                """
            )

    def is_seen(self, trade_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM copied_trades WHERE trade_id = ?", (trade_id,)).fetchone()
            return row is not None

    def record_trade(self, trade: CapitolTrade, qty: float, fill_price: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO copied_trades
                (trade_id, traded_at, member_name, symbol, action, qty, fill_price, notional)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.traded_at.isoformat(),
                    trade.member_name,
                    trade.symbol,
                    trade.action,
                    qty,
                    fill_price,
                    qty * fill_price,
                ),
            )

    def top_members_by_roi(self, lookback_days: int, top_n: int) -> list[MemberScore]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT traded_at, member_name, symbol, action, qty, fill_price
                FROM copied_trades
                WHERE traded_at >= ?
                ORDER BY traded_at ASC
                """,
                (cutoff,),
            ).fetchall()

        inventory: dict[tuple[str, str], deque[Fill]] = defaultdict(deque)
        invested: dict[str, float] = defaultdict(float)
        realized: dict[str, float] = defaultdict(float)

        for traded_at, member, symbol, action, qty, price in rows:
            _ = traded_at
            key = (member, symbol)
            if action == "BUY":
                inventory[key].append(Fill(qty=qty, price=price))
                invested[member] += qty * price
                continue

            remaining = qty
            while remaining > 0 and inventory[key]:
                lot = inventory[key][0]
                matched = min(remaining, lot.qty)
                pnl = matched * (price - lot.price)
                realized[member] += pnl
                lot.qty -= matched
                remaining -= matched
                if lot.qty <= 1e-9:
                    inventory[key].popleft()

        scores: list[MemberScore] = []
        for member, cap in invested.items():
            if cap <= 0:
                continue
            pnl = realized.get(member, 0.0)
            roi = pnl / cap
            scores.append(
                MemberScore(
                    member_name=member,
                    roi=roi,
                    realized_pnl=pnl,
                    invested_capital=cap,
                )
            )

        scores.sort(key=lambda s: s.roi, reverse=True)
        return scores[:top_n]
