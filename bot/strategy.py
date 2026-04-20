from __future__ import annotations

from dataclasses import dataclass

from bot.alpaca_client import AlpacaPaperBroker
from bot.capitol_client import CapitolTradesClient
from bot.config import Settings
from bot.ledger import TradeLedger
from bot.models import CapitolTrade


@dataclass
class RunStats:
    considered: int = 0
    submitted: int = 0
    skipped_seen: int = 0
    skipped_filter: int = 0
    skipped_budget: int = 0


class MirrorStrategy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.capitol = CapitolTradesClient(settings.capitol_trades_api_url, settings.capitol_page_size)
        self.ledger = TradeLedger()
        self.broker = AlpacaPaperBroker(settings.alpaca_api_key, settings.alpaca_api_secret, paper=True)

    def run(self) -> RunStats:
        stats = RunStats()
        top_members = {
            s.member_name for s in self.ledger.top_members_by_roi(self.settings.lookback_days, self.settings.top_n_members)
        }

        if not top_members:
            # bootstrap mode: if no history, use newest trades from all members
            trades = self.capitol.fetch_recent_trades(pages=2)
        else:
            trades = [
                t
                for t in self.capitol.fetch_recent_trades(pages=3)
                if t.member_name in top_members
            ]

        budget_left = self.settings.max_notional_per_run
        positions_left = self.settings.max_positions_per_run

        for trade in trades:
            stats.considered += 1
            if self.ledger.is_seen(trade.trade_id):
                stats.skipped_seen += 1
                continue
            if not self._passes_symbol_filters(trade):
                stats.skipped_filter += 1
                continue
            if positions_left <= 0 or budget_left < self.settings.notional_per_trade:
                stats.skipped_budget += 1
                continue

            order = self.broker.submit_notional_market_order(
                symbol=trade.symbol,
                side=trade.action,
                notional=self.settings.notional_per_trade,
            )
            filled_price = float(getattr(order, "filled_avg_price", 0.0) or 0.0)
            qty = float(getattr(order, "filled_qty", 0.0) or 0.0)

            # If order is accepted but not filled yet, approximate quantity from notional.
            if qty <= 0:
                qty = self.settings.notional_per_trade / max(filled_price, 1.0)

            self.ledger.record_trade(trade=trade, qty=qty, fill_price=max(filled_price, 1.0))
            budget_left -= self.settings.notional_per_trade
            positions_left -= 1
            stats.submitted += 1

        return stats

    def _passes_symbol_filters(self, trade: CapitolTrade) -> bool:
        symbol = trade.symbol.upper()

        if self.settings.symbol_allowlist and symbol not in self.settings.symbol_allowlist:
            return False

        if symbol in self.settings.symbol_blocklist:
            return False

        return True
