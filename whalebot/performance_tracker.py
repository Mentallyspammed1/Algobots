import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

# Assuming these are defined in a common constants file or main script
# For now, defining them here for self-containment
NEON_RED = "\033[91m" # Example, replace with actual colorama codes if used
NEON_CYAN = "\033[96m" # Example
RESET = "\033[0m" # Example
TIMEZONE = timezone.utc # Example, replace with actual timezone if needed

class PerformanceTracker:
    """Tracks and reports trading performance. Trades are saved to a file."""

    def __init__(self, logger: logging.Logger, config_file: str = "trades.json"):
        """Initializes the PerformanceTracker."""
        self.logger = logger
        self.config_file = Path(config_file)
        self.trades: list[dict] = self._load_trades()
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self._recalculate_summary() # Recalculate summary from loaded trades

    def _load_trades(self) -> list[dict]:
        """Load trade history from file."""
        if self.config_file.exists():
            try:
                with self.config_file.open("r", encoding="utf-8") as f:
                    raw_trades = json.load(f)
                    # Convert Decimal/datetime from string after loading
                    loaded_trades = []
                    for trade in raw_trades:
                        for key in ["pnl", "entry_price", "exit_price", "qty"]:
                            if key in trade:
                                trade[key] = Decimal(str(trade[key]))
                        for key in ["entry_time", "exit_time"]:
                            if key in trade:
                                trade[key] = datetime.fromisoformat(trade[key])
                        loaded_trades.append(trade)
                    return loaded_trades
            except (json.JSONDecodeError, OSError) as e:
                self.logger.error(f"{NEON_RED}Error loading trades from {self.config_file}: {e}{RESET}")
        return []

    def _save_trades(self) -> None:
        """Save trade history to file."""
        try:
            with self.config_file.open("w", encoding="utf-8") as f:
                # Convert Decimal/datetime to string for JSON serialization
                serializable_trades = []
                for trade in self.trades:
                    s_trade = trade.copy()
                    for key in ["pnl", "entry_price", "exit_price", "qty"]:
                        if key in s_trade:
                            s_trade[key] = str(s_trade[key])
                    for key in ["entry_time", "exit_time"]:
                        if key in s_trade:
                            s_trade[key] = s_trade[key].isoformat()
                    serializable_trades.append(s_trade)
                json.dump(serializable_trades, f, indent=4)
        except OSError as e:
            self.logger.error(f"{NEON_RED}Error saving trades to {self.config_file}: {e}{RESET}")

    def _recalculate_summary(self) -> None:
        """Recalculate summary metrics from the list of trades."""
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        for trade in self.trades:
            self.total_pnl += trade["pnl"]
            if trade["pnl"] > 0:
                self.wins += 1
            else:
                self.losses += 1

    def record_trade(self, position: dict, pnl: Decimal) -> None:
        """Record a completed trade."""
        trade_record = {
            "entry_time": position.get("entry_time", datetime.now(TIMEZONE)),
            "exit_time": position.get("exit_time", datetime.now(TIMEZONE)),
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": position["exit_price"],
            "qty": position["qty"],
            "pnl": pnl,
            "closed_by": position.get("closed_by", "UNKNOWN"),
        }
        self.trades.append(trade_record)
        self._recalculate_summary() # Update summary immediately
        self._save_trades() # Save to file
        self.logger.info(
            f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
        )

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
