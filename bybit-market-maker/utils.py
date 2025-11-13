import logging
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yaml
from colorama import Fore
from colorama import Style
from colorama import init
from dotenv import load_dotenv

# Initialize colorama
init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""

    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{log_color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(
    name: str, log_file: str = None, level: str = "INFO"
) -> logging.Logger:
    """Setup logger with file and console handlers"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    with open(config_path) as file:
        return yaml.safe_load(file)


def load_env_variables():
    """Load environment variables from .env file"""
    load_dotenv()
    return {
        "api_key": os.getenv("BYBIT_API_KEY"),
        "api_secret": os.getenv("BYBIT_API_SECRET"),
        "environment": os.getenv("ENVIRONMENT", "testnet"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "log_file": os.getenv("LOG_FILE", "market_maker.log"),
    }


def calculate_volatility(prices: list[float], window: int = 20) -> float | None:
    """Calculate price volatility using standard deviation of returns"""
    if len(prices) < window:
        return None

    returns = pd.Series(prices).pct_change().dropna()
    return float(returns.rolling(window).std().iloc[-1])


def calculate_spread(
    base_spread: float,
    volatility: float,
    inventory_ratio: float,
    config: dict,
    strategy: str,
) -> tuple[float, float]:
    """Calculate dynamic bid/ask spreads based on market conditions"""
    volatility_adjustment = volatility * config["trading"]["volatility_factor"]
    inventory_adjustment = (
        abs(inventory_ratio - 0.5) * config["trading"]["inventory_factor"]
    )

    adjusted_spread = base_spread + volatility_adjustment + inventory_adjustment

    # Apply min/max constraints
    adjusted_spread = max(
        config["trading"]["min_spread"],
        min(adjusted_spread, config["trading"]["max_spread"]),
    )

    if strategy == "skewed":
        if inventory_ratio > 0.5:
            # More inventory, widen ask spread
            ask_spread = adjusted_spread * (1 + (inventory_ratio - 0.5))
            bid_spread = adjusted_spread * (1 - (inventory_ratio - 0.5) * 0.5)
        else:
            # Less inventory, widen bid spread
            bid_spread = adjusted_spread * (1 + (0.5 - inventory_ratio))
            ask_spread = adjusted_spread * (1 - (0.5 - inventory_ratio) * 0.5)
    elif strategy == "adaptive":
        # Adaptive strategy can have more complex logic, for now, same as skewed
        if inventory_ratio > 0.5:
            ask_spread = adjusted_spread * (1 + (inventory_ratio - 0.5))
            bid_spread = adjusted_spread * (1 - (inventory_ratio - 0.5) * 0.5)
        else:
            bid_spread = adjusted_spread * (1 + (0.5 - inventory_ratio))
            ask_spread = adjusted_spread * (1 - (0.5 - inventory_ratio) * 0.5)
    else:  # symmetric
        bid_spread = adjusted_spread
        ask_spread = adjusted_spread

    return bid_spread, ask_spread


def calculate_order_step(
    base_order_step: float,
    volatility: float,
    config: dict,
    strategy: str,
) -> float:
    """Calculate dynamic order step based on market conditions"""
    volatility_adjustment = volatility * config["trading"]["volatility_factor"]

    adjusted_order_step = base_order_step + volatility_adjustment

    # Apply min/max constraints (assuming min/max order step in config)
    # For now, just return the adjusted step
    return adjusted_order_step


def calculate_order_sizes(
    base_size: float,
    num_orders: int,
    inventory_ratio: float,
    side: str,
    strategy: str,
) -> list[float]:
    """Calculate order sizes with inventory-based adjustments"""
    sizes = []

    for i in range(num_orders):
        size_multiplier = 1.0 + (i * 0.2)  # Increase size for further orders

        if strategy == "skewed":
            if side == "Buy" and inventory_ratio < 0.5:
                size_multiplier *= 1 + (0.5 - inventory_ratio)
            elif side == "Sell" and inventory_ratio > 0.5:
                size_multiplier *= 1 + (inventory_ratio - 0.5)
        elif strategy == "adaptive":
            # Adaptive strategy can have more complex logic, for now, same as skewed
            if side == "Buy" and inventory_ratio < 0.5:
                size_multiplier *= 1 + (0.5 - inventory_ratio)
            elif side == "Sell" and inventory_ratio > 0.5:
                size_multiplier *= 1 + (inventory_ratio - 0.5)

        sizes.append(base_size * size_multiplier)

    return sizes


def format_price(price: float, tick_size: float = 0.01) -> float:
    """Format price according to tick size"""
    return round(price / tick_size) * tick_size


def format_quantity(quantity: float, lot_size: float = 0.001) -> float:
    """Format quantity according to lot size"""
    return round(quantity / lot_size) * lot_size


class PerformanceTracker:
    """Track bot performance metrics"""

    def __init__(self):
        self.trades = []
        self.pnl_history = []
        self.start_balance = 0
        self.current_balance = 0
        self.total_volume = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.start_time = datetime.now()

    def add_trade(self, trade: dict):
        """Add trade to history"""
        self.trades.append(trade)
        if trade["pnl"] > 0:
            self.winning_trades += 1
        elif trade["pnl"] < 0:
            self.losing_trades += 1
        self.total_volume += trade["quantity"] * trade["price"]

    def update_balance(self, balance: float):
        """Update current balance"""
        if self.start_balance == 0:
            self.start_balance = balance
        self.current_balance = balance
        self.pnl_history.append(
            {
                "timestamp": datetime.now(),
                "balance": balance,
                "pnl": balance - self.start_balance,
            }
        )

    def get_statistics(self) -> dict:
        """Calculate performance statistics"""
        if not self.trades:
            return {}

        total_pnl = self.current_balance - self.start_balance
        roi = (total_pnl / self.start_balance * 100) if self.start_balance > 0 else 0
        win_rate = (self.winning_trades / len(self.trades) * 100) if self.trades else 0

        # Calculate Sharpe ratio
        if len(self.pnl_history) > 1:
            returns = (
                pd.Series([p["pnl"] for p in self.pnl_history]).pct_change().dropna()
            )
            sharpe = (
                (returns.mean() / returns.std() * np.sqrt(365))
                if returns.std() > 0
                else 0
            )
        else:
            sharpe = 0

        runtime = datetime.now() - self.start_time

        return {
            "total_pnl": total_pnl,
            "roi": roi,
            "total_trades": len(self.trades),
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": win_rate,
            "total_volume": self.total_volume,
            "sharpe_ratio": sharpe,
            "runtime": str(runtime),
            "avg_trade_size": self.total_volume / len(self.trades)
            if self.trades
            else 0,
        }
