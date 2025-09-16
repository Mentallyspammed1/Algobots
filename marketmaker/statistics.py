from datetime import datetime

import pandas as pd


class Statistics:
    def __init__(self, market_maker):
        self.mm = market_maker
        self.start_time = datetime.now()
        self.trades = []
        self.pnl_history = []

    def calculate_statistics(self) -> dict:
        """Calculate trading statistics"""
        runtime = (datetime.now() - self.start_time).total_seconds() / 3600

        stats = {
            "runtime_hours": runtime,
            "total_trades": len(self.mm.order_fill_history),
            "current_position": self.mm.position,
            "unrealized_pnl": self.mm.unrealized_pnl,
            "avg_spread": self.mm.spread,
            "current_volatility": self.mm.current_volatility,
            "active_buy_orders": len(self.mm.active_orders.get("buy", [])),
            "active_sell_orders": len(self.mm.active_orders.get("sell", [])),
        }

        # Calculate realized PnL from fill history
        if self.mm.order_fill_history:
            df = pd.DataFrame(self.mm.order_fill_history)
            buy_trades = df[df["side"] == "Buy"]
            sell_trades = df[df["side"] == "Sell"]

            if not buy_trades.empty and not sell_trades.empty:
                avg_buy_price = (
                    buy_trades["price"] * buy_trades["qty"]
                ).sum() / buy_trades["qty"].sum()
                avg_sell_price = (
                    sell_trades["price"] * sell_trades["qty"]
                ).sum() / sell_trades["qty"].sum()
                matched_volume = min(buy_trades["qty"].sum(), sell_trades["qty"].sum())
                stats["realized_pnl"] = (
                    avg_sell_price - avg_buy_price
                ) * matched_volume
            else:
                stats["realized_pnl"] = 0

            # Trade frequency
            stats["trades_per_hour"] = (
                len(self.mm.order_fill_history) / runtime if runtime > 0 else 0
            )

            # Volume statistics
            stats["total_volume"] = df["qty"].sum()
            stats["avg_trade_size"] = df["qty"].mean()
        else:
            stats["realized_pnl"] = 0
            stats["trades_per_hour"] = 0
            stats["total_volume"] = 0
            stats["avg_trade_size"] = 0

        return stats

    def print_statistics(self):
        """Print formatted statistics"""
        stats = self.calculate_statistics()

        print("\n" + "=" * 50)
        print("MARKET MAKER STATISTICS")
        print("=" * 50)
        print(f"Runtime: {stats['runtime_hours']:.2f} hours")
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Trades/Hour: {stats['trades_per_hour']:.2f}")
        print(f"Total Volume: {stats['total_volume']:.4f}")
        print(f"Avg Trade Size: {stats['avg_trade_size']:.4f}")
        print("-" * 50)
