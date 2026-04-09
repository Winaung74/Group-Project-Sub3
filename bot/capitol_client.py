from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from bot.models import CapitolTrade


class CapitolTradesClient:
    """
    Minimal client for Capitol Trades data.

    This uses an undocumented endpoint pattern and may break if the site changes.
    """

    def __init__(self, base_url: str, page_size: int = 96) -> None:
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size

    def fetch_recent_trades(self, pages: int = 3) -> list[CapitolTrade]:
        trades: list[CapitolTrade] = []

        for page in range(1, pages + 1):
            params = {"page": page, "pageSize": self.page_size}
            resp = requests.get(self.base_url, params=params, timeout=20)
            resp.raise_for_status()

            payload = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
            raw_trades = self._extract_items(payload)
            if not raw_trades:
                break

            for item in raw_trades:
                parsed = self._parse_trade(item)
                if parsed:
                    trades.append(parsed)

        return trades

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("items", "results", "data", "trades"):
            value = payload.get(key)
            if isinstance(value, list):
                return [v for v in value if isinstance(v, dict)]
        return []

    @staticmethod
    def _parse_trade(item: dict[str, Any]) -> CapitolTrade | None:
        action = str(item.get("txType") or item.get("action") or "").upper().strip()
        symbol = str(item.get("ticker") or item.get("symbol") or "").upper().strip()
        member = str(item.get("politician") or item.get("memberName") or item.get("member") or "").strip()

        if action not in {"BUY", "SELL"} or not symbol or not member:
            return None

        traded_at_raw = item.get("traded") or item.get("tradeDate") or item.get("date")
        traded_at = CapitolTradesClient._parse_datetime(traded_at_raw)
        if not traded_at:
            return None

        low, high = CapitolTradesClient._parse_amount_range(item)
        trade_id = str(item.get("id") or f"{member}:{symbol}:{action}:{traded_at.isoformat()}")

        return CapitolTrade(
            trade_id=trade_id,
            traded_at=traded_at,
            member_name=member,
            symbol=symbol,
            action=action,
            amount_low=low,
            amount_high=high,
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    @staticmethod
    def _parse_amount_range(item: dict[str, Any]) -> tuple[float | None, float | None]:
        low = item.get("amount_low") or item.get("amountLow")
        high = item.get("amount_high") or item.get("amountHigh")
        try:
            low_f = float(low) if low is not None else None
            high_f = float(high) if high is not None else None
            return low_f, high_f
        except (TypeError, ValueError):
            return None, None
