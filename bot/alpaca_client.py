from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


class AlpacaPaperBroker:
    def __init__(self, api_key: str, api_secret: str, paper: bool = True) -> None:
        self.client = TradingClient(api_key=api_key, secret_key=api_secret, paper=paper)

    def submit_notional_market_order(self, symbol: str, side: str, notional: float):
        order = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        return self.client.submit_order(order_data=order)

    def latest_trade_price(self, symbol: str) -> float | None:
        """
        Best-effort fill-price approximation.
        """
        try:
            # alpaca-py currently exposes latest quote through data clients, but to avoid
            # hard dependency here we return None and let caller store 0 if unavailable.
            _ = symbol
            return None
        except Exception:
            return None
