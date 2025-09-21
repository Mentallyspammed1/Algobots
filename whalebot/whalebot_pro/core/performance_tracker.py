import logging
from decimal import Decimal
from colorama import Fore, Style

# Color Scheme
NEON_CYAN = Fore.CYAN
RESET = Style.RESET_ALL

class PerformanceTracker:
    """Tracks and reports trading performance."""

    def __init__(self, logger: logging.Logger, config: dict):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.config = config
        self.trades: list[dict] = []
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.trading_fee_percent = Decimal(str(config["trade_management"].get("trading_fee_percent", 0.0)))

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position["entry_time"],
            "exit_time": position["exit_time"],
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position["closed_by"],
        }
        self.trades.append(trade_record)
        self.total_pnl += pnl

        # Deduct fees for both entry and exit
        entry_fee = position["entry_price"] * position["qty"] * self.trading_fee_percent
        exit_fee = position["exit_price"] * position["qty"] * self.trading_fee_percent
        total_fees = entry_fee + exit_fee
        self.total_pnl -= total_fees

        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. PnL (before fees): {pnl.normalize():.2f}, Total Fees: {total_fees.normalize():.2f}, Current Total PnL (after fees): {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )
        # self.logger.info("Trade recorded", extra=trade_record) # This requires a logger configured to handle 'extra'

    def get_summary(self) -> dict:
        """Return a summary of all recorded trades."""
        total_trades = len(self.trades)
        win_rate = (self.wins / total_trades) * 100 if total_trades > 0 else 0

        return {
            "total_trades": total_trades,
            "total_pnl": self.total_pnl,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{win_rate:.2f}%",
        }