import hashlib
import hmac
import json
import logging
import os
import smtplib
import sqlite3
import statistics
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, getcontext
from email.mime.text import MIMEText
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from logger_config import setup_custom_logger

warnings.filterwarnings("ignore")

# Set Decimal precision for financial calculations to avoid floating point errors
getcontext().prec = 10

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()


# --- Enums and Data Classes ---
class SignalType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class MarketCondition(Enum):
    LOW_VOLATILITY = "low_volatility"
    HIGH_VOLATILITY = "high_volatility"
    TRENDING = "trending"
    RANGING = "ranging"


class MarketRegime(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class TradingSignal:
    signal_type: SignalType | None
    confidence: float
    conditions_met: list[str]
    stop_loss: Decimal | None
    take_profit: Decimal | None
    timestamp: float
    symbol: str
    timeframe: str
    position_size: float | None = None
    risk_reward_ratio: float | None = None


@dataclass
class IndicatorResult:
    name: str
    value: Any
    interpretation: str


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    total_profit: Decimal = Decimal("0")
    total_loss: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    average_win: Decimal = Decimal("0")
    average_loss: Decimal = Decimal("0")


@dataclass
class SignalHistory:
    timestamp: float
    symbol: str
    timeframe: str
    signal_type: SignalType
    confidence: float
    entry_price: Decimal
    exit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    profit_loss: Decimal | None = None
    exit_reason: str | None = None
    market_regime: MarketRegime | None = None


# --- Color Codex ---
NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_CYAN = Fore.CYAN  # Added NEON_CYAN definition
RESET = Style.RESET_ALL

# --- Configuration & Constants ---
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
BASE_URL = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")
CONFIG_FILE = "config.json"
LOG_DIRECTORY = "bot_logs"
DATA_DIRECTORY = "bot_data"
DATABASE_FILE = os.path.join(DATA_DIRECTORY, "trading_bot.db")
TIMEZONE = ZoneInfo("America/Chicago")
MAX_API_RETRIES = 3
RETRY_DELAY_SECONDS = 5
VALID_INTERVALS = ["1", "3", "5", "15", "30", "60", "120", "240", "D", "W", "M"]
RETRY_ERROR_CODES = [429, 500, 502, 503, 504]
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 5
MAX_SIGNAL_HISTORY = 1000

# Ensure directories exist
os.makedirs(LOG_DIRECTORY, exist_ok=True)
os.makedirs(DATA_DIRECTORY, exist_ok=True)

# Setup the main application logger with rotation
logger = setup_custom_logger("whalebot_main")


# --- Database Setup ---
def setup_database():
    # This function initializes the SQLite database and creates the necessary tables.
    """Set up the SQLite database for storing signal history and performance metrics."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Create signal_history table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS signal_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        confidence REAL NOT NULL,
        entry_price TEXT NOT NULL,
        exit_price TEXT,
        stop_loss TEXT,
        take_profit TEXT,
        profit_loss TEXT,
        exit_reason TEXT,
        market_regime TEXT
    )
    """)

    # Create performance_metrics table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS performance_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL NOT NULL,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        total_trades INTEGER NOT NULL,
        winning_trades INTEGER NOT NULL,
        losing_trades INTEGER NOT NULL,
        win_rate REAL NOT NULL,
        profit_factor REAL NOT NULL,
        max_drawdown REAL NOT NULL,
        sharpe_ratio REAL NOT NULL,
        total_profit TEXT NOT NULL,
        total_loss TEXT NOT NULL,
        net_profit TEXT NOT NULL,
        average_win TEXT NOT NULL,
        average_loss TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


# --- Notification System ---
class NotificationSystem:
    """Handles sending notifications via email or webhooks."""

    def __init__(self, config: dict):
        self.config = config.get("notifications", {})
        self.enabled = self.config.get("enabled", False)
        self.email_config = self.config.get("email", {})
        self.webhook_config = self.config.get("webhook", {})

    def send_email(self, subject: str, message: str) -> bool:
        """Send an email notification."""
        if not self.enabled or not self.email_config.get("enabled", False):
            return False

        try:
            msg = MIMEText(message)
            msg["Subject"] = subject
            msg["From"] = self.email_config.get("from")
            msg["To"] = self.email_config.get("to")

            with smtplib.SMTP(
                self.email_config.get("smtp_server"), self.email_config.get("smtp_port")
            ) as server:
                if self.email_config.get("use_tls", True):
                    server.starttls()
                server.login(
                    self.email_config.get("username"), self.email_config.get("password")
                )
                server.send_message(msg)

            logger.info(f"{NEON_GREEN}Email notification sent: {subject}{RESET}")
            return True
        except Exception as e:
            logger.error(f"{NEON_RED}Failed to send email notification: {e}{RESET}")
            return False

    def send_webhook(self, payload: dict) -> bool:
        """Send a webhook notification."""
        if not self.enabled or not self.webhook_config.get("enabled", False):
            return False

        try:
            response = requests.post(
                self.webhook_config.get("url"), json=payload, timeout=10
            )
            response.raise_for_status()
            logger.info(f"{NEON_GREEN}Webhook notification sent successfully{RESET}")
            return True
        except Exception as e:
            logger.error(f"{NEON_RED}Failed to send webhook notification: {e}{RESET}")
            return False

    def send_signal_notification(self, signal: TradingSignal) -> None:
        """Send a notification for a trading signal."""
        subject = (
            f"Trading Signal: {signal.signal_type.value.upper()} for {signal.symbol}"
        )
        message = f"""
Signal: {signal.signal_type.value.upper()}
Symbol: {signal.symbol}
Timeframe: {signal.timeframe}
Confidence: {signal.confidence:.2f}
Conditions: {", ".join(signal.conditions_met)}
Stop Loss: {signal.stop_loss}
Take Profit: {signal.take_profit}
Timestamp: {datetime.fromtimestamp(signal.timestamp).strftime("%Y-%m-%d %H:%M:%S")}
"""

        payload = {
            "signal_type": signal.signal_type.value,
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "confidence": signal.confidence,
            "conditions_met": signal.conditions_met,
            "stop_loss": str(signal.stop_loss) if signal.stop_loss else None,
            "take_profit": str(signal.take_profit) if signal.take_profit else None,
            "timestamp": signal.timestamp,
        }

        self.send_email(subject, message)
        self.send_webhook(payload)


# --- Configuration Management ---
def load_config(filepath: str) -> dict:
    """Loads configuration from a JSON file, merging with default values.
    If the file is not found or is invalid, it creates one with default settings.
    """
    default_config = {
        "interval": "15",
        "analysis_interval": 30,  # Time in seconds between main analysis cycles
        "retry_delay": 5,  # Delay in seconds for API retries
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
        "volume_ma_period": 20,
        "atr_period": 14,
        "trend_strength_threshold": 0.4,
        "sideways_atr_multiplier": 1.5,
        "signal_score_threshold": 1.0,  # Minimum combined weight for a signal to be valid
        "indicators": {
            "ema_alignment": True,
            "momentum": True,
            "volume_confirmation": True,
            "divergence": True,
            "stoch_rsi": True,
            "rsi": True,
            "macd": True,
            "vwap": False,
            "obv": True,
            "adi": True,
            "cci": True,
            "wr": True,
            "adx": True,
            "psar": True,
            "fve": True,
            "sma_10": False,
            "mfi": True,
            "stochastic_oscillator": True,
        },
        "weight_sets": {
            "low_volatility": {  # Weights for a low volatility market environment
                "ema_alignment": 0.3,
                "momentum": 0.2,
                "volume_confirmation": 0.2,
                "divergence": 0.1,
                "stoch_rsi": 0.5,
                "rsi": 0.3,
                "macd": 0.3,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.2,
                "sma_10": 0.0,
                "mfi": 0.3,
                "stochastic_oscillator": 0.4,
            },
            "high_volatility": {  # Weights for a high volatility market environment
                "ema_alignment": 0.1,
                "momentum": 0.4,
                "volume_confirmation": 0.1,
                "divergence": 0.2,
                "stoch_rsi": 0.4,
                "rsi": 0.4,
                "macd": 0.4,
                "vwap": 0.0,
                "obv": 0.1,
                "adi": 0.1,
                "cci": 0.1,
                "wr": 0.1,
                "adx": 0.1,
                "psar": 0.1,
                "fve": 0.3,
                "sma_10": 0.0,
                "mfi": 0.4,
                "stochastic_oscillator": 0.3,
            },
        },
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stoch_rsi_confidence_boost": 5,  # Additional boost for strong Stoch RSI signals
        "stoch_rsi_mandatory": False,  # If true, Stoch RSI must be a confirming factor
        "rsi_confidence_boost": 2,
        "mfi_confidence_boost": 2,
        "order_book_support_confidence_boost": 3,
        "order_book_resistance_confidence_boost": 3,
        "stop_loss_multiple": 1.5,  # Multiplier for ATR to determine stop loss distance
        "take_profit_multiple": 1.0,  # Multiplier for ATR to determine take profit distance
        "order_book_wall_threshold_multiplier": 2.0,  # Multiplier for average volume to identify a "wall"
        "order_book_depth_to_check": 10,  # Number of order book levels to check for walls
        "price_change_threshold": 0.005,  # % change in price to consider significant
        "atr_change_threshold": 0.005,  # % change in ATR to consider significant volatility change
        "signal_cooldown_s": 60,  # Seconds to wait before generating another signal
        "order_book_debounce_s": 10,  # Seconds to wait between order book API calls
        "ema_short_period": 12,
        "ema_long_period": 26,
        "volume_confirmation_multiplier": 1.5,  # Volume must be this many times average volume for confirmation
        "indicator_periods": {
            "rsi": 14,
            "mfi": 14,
            "cci": 20,
            "williams_r": 14,
            "adx": 14,
            "stoch_rsi_period": 14,  # Period for RSI calculation within Stoch RSI
            "stoch_rsi_k_period": 3,  # Smoothing period for %K line
            "stoch_rsi_d_period": 3,  # Smoothing period for %D line (signal line)
            "momentum": 10,
            "momentum_ma_short": 12,
            "momentum_ma_long": 26,
            "volume_ma": 20,
            "atr": 14,
            "sma_10": 10,
            "fve_price_ema": 10,  # EMA period for FVE price component
            "fve_obv_sma": 20,  # SMA period for OBV normalization
            "fve_atr_sma": 20,  # SMA period for ATR normalization
            "stoch_osc_k": 14,  # Stochastic Oscillator K period
            "stoch_osc_d": 3,  # Stochastic Oscillator D period
        },
        "order_book_analysis": {
            "enabled": True,
            "wall_threshold_multiplier": 2.0,
            "depth_to_check": 10,
            "support_boost": 3,
            "resistance_boost": 3,
        },
        "trailing_stop_loss": {
            "enabled": False,  # Disabled by default
            "initial_activation_percent": 0.5,  # Activate trailing stop after price moves X% in favor
            "trailing_stop_multiple_atr": 1.5,  # Trail stop based on ATR multiple
        },
        "take_profit_scaling": {
            "enabled": False,  # Disabled by default
            "targets": [
                {
                    "level": 1.5,
                    "percentage": 0.25,
                },  # Sell 25% when price hits 1.5x ATR TP
                {
                    "level": 2.0,
                    "percentage": 0.50,
                },  # Sell 50% of remaining when price hits 2.0x ATR TP
            ],
        },
        "risk_management": {
            "max_position_size": 0.1,  # Maximum position size as a percentage of portfolio
            "max_daily_loss": 0.05,  # Maximum daily loss as a percentage of portfolio
            "max_drawdown": 0.15,  # Maximum drawdown before stopping trading
            "risk_per_trade": 0.02,  # Risk percentage per trade
            "portfolio_value": 10000,  # Total portfolio value
            "circuit_breaker": {
                "enabled": True,
                "max_consecutive_losses": 5,
                "cooldown_period_minutes": 60,
            },
        },
        "data_validation": {
            "min_data_points": 50,  # Minimum data points required for analysis
            "max_data_age_minutes": 60,  # Maximum age of data before considering it stale
            "price_deviation_threshold": 0.1,  # Maximum allowed price deviation (%)
        },
        "notifications": {
            "enabled": False,
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "use_tls": True,
                "username": "",
                "password": "",
                "from": "",
                "to": "",
            },
            "webhook": {"enabled": False, "url": ""},
        },
        "multi_timeframe": {
            "enabled": False,
            "timeframes": ["5", "15", "60"],
            "weighting": {"5": 0.2, "15": 0.5, "60": 0.3},
        },
        "backtesting": {
            "enabled": False,
            "start_date": "",
            "end_date": "",
            "initial_balance": 10000,
        },
        "logging": {
            "level": "INFO",
            "max_file_size": 10485760,  # 10MB
            "backup_count": 5,
        },
        "database": {
            "enabled": True,
            "path": DATABASE_FILE,
            "backup_enabled": True,
            "backup_interval_hours": 24,
        },
    }

    try:
        with open(filepath, encoding="utf-8") as f:
            config = json.load(f)
            # Merge loaded config with defaults. Prioritize loaded values, but ensure all default keys exist.
            merged_config = {**default_config, **config}
            # Basic validation for interval and analysis_interval
            if merged_config.get("interval") not in VALID_INTERVALS:
                logger.warning(
                    f"{NEON_YELLOW}Invalid 'interval' in config, using default: {default_config['interval']}{RESET}"
                )
                merged_config["interval"] = default_config["interval"]
            if (
                not isinstance(merged_config.get("analysis_interval"), int)
                or merged_config.get("analysis_interval") <= 0
            ):
                logger.warning(
                    f"{NEON_YELLOW}Invalid 'analysis_interval' in config, using default: {default_config['analysis_interval']}{RESET}"
                )
                merged_config["analysis_interval"] = default_config["analysis_interval"]
            return merged_config
    except FileNotFoundError:
        logger.warning(
            f"{NEON_YELLOW}Config file not found, loading defaults and creating {filepath}{RESET}"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config
    except json.JSONDecodeError:
        logger.error(f"{NEON_RED}Invalid JSON in config file, loading defaults.{RESET}")
        # Optionally, back up the corrupt file before overwriting
        try:
            os.rename(filepath, f"{filepath}.bak_{int(time.time())}")
            logger.info(
                f"{NEON_YELLOW}Backed up corrupt config file to {filepath}.bak_{int(time.time())}{RESET}"
            )
        except OSError as e:
            logger.error(f"{NEON_RED}Failed to backup corrupt config file: {e}{RESET}")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4)
        return default_config


# Load the configuration
CONFIG = load_config(CONFIG_FILE)


# --- Database Operations ---
class DatabaseManager:
    """Manages database operations for signal history and performance metrics."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Ensure the database and tables exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create signal_history table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            confidence REAL NOT NULL,
            entry_price TEXT NOT NULL,
            exit_price TEXT,
            stop_loss TEXT,
            take_profit TEXT,
            profit_loss TEXT,
            exit_reason TEXT,
            market_regime TEXT
        )
        """)

        # Create performance_metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS performance_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            total_trades INTEGER NOT NULL,
            winning_trades INTEGER NOT NULL,
            losing_trades INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            profit_factor REAL NOT NULL,
            max_drawdown REAL NOT NULL,
            sharpe_ratio REAL NOT NULL,
            total_profit TEXT NOT NULL,
            total_loss TEXT NOT NULL,
            net_profit TEXT NOT NULL,
            average_win TEXT NOT NULL,
            average_loss TEXT NOT NULL
        )
        """)

        conn.commit()
        conn.close()

    def save_signal(self, signal: SignalHistory) -> int:
        """Save a signal to the database and return its ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        INSERT INTO signal_history (
            timestamp, symbol, timeframe, signal_type, confidence, 
            entry_price, exit_price, stop_loss, take_profit, 
            profit_loss, exit_reason, market_regime
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                signal.timestamp,
                signal.symbol,
                signal.timeframe,
                signal.signal_type.value,
                signal.confidence,
                str(signal.entry_price),
                str(signal.exit_price) if signal.exit_price else None,
                str(signal.stop_loss) if signal.stop_loss else None,
                str(signal.take_profit) if signal.take_profit else None,
                str(signal.profit_loss) if signal.profit_loss else None,
                signal.exit_reason,
                signal.market_regime.value if signal.market_regime else None,
            ),
        )

        signal_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return signal_id

    def update_signal(
        self,
        signal_id: int,
        exit_price: Decimal,
        profit_loss: Decimal,
        exit_reason: str,
    ) -> bool:
        """Update a signal with exit information."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        UPDATE signal_history 
        SET exit_price = ?, profit_loss = ?, exit_reason = ?
        WHERE id = ?
        """,
            (str(exit_price), str(profit_loss), exit_reason, signal_id),
        )

        success = cursor.rowcount > 0
        conn.commit()
        conn.close()

        return success

    def get_signal_history(
        self, symbol: str = None, timeframe: str = None, limit: int = 100
    ) -> list[SignalHistory]:
        """Retrieve signal history from the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM signal_history"
        params = []

        if symbol or timeframe:
            query += " WHERE"
            conditions = []

            if symbol:
                conditions.append(" symbol = ?")
                params.append(symbol)

            if timeframe:
                if conditions:
                    query += " AND"
                conditions.append(" timeframe = ?")
                params.append(timeframe)

            query += " AND".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        signals = []
        for row in rows:
            signals.append(
                SignalHistory(
                    timestamp=row[1],
                    symbol=row[2],
                    timeframe=row[3],
                    signal_type=SignalType(row[4]),
                    confidence=row[5],
                    entry_price=Decimal(row[6]),
                    exit_price=Decimal(row[7]) if row[7] else None,
                    stop_loss=Decimal(row[8]) if row[8] else None,
                    take_profit=Decimal(row[9]) if row[9] else None,
                    profit_loss=Decimal(row[10]) if row[10] else None,
                    exit_reason=row[11],
                    market_regime=MarketRegime(row[12]) if row[12] else None,
                )
            )

        return signals

    def save_performance_metrics(
        self, metrics: PerformanceMetrics, symbol: str, timeframe: str
    ) -> int:
        """Save performance metrics to the database and return its ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        INSERT INTO performance_metrics (
            timestamp, symbol, timeframe, total_trades, winning_trades, 
            losing_trades, win_rate, profit_factor, max_drawdown, 
            sharpe_ratio, total_profit, total_loss, net_profit, 
            average_win, average_loss
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                time.time(),
                symbol,
                timeframe,
                metrics.total_trades,
                metrics.winning_trades,
                metrics.losing_trades,
                metrics.win_rate,
                metrics.profit_factor,
                metrics.max_drawdown,
                metrics.sharpe_ratio,
                str(metrics.total_profit),
                str(metrics.total_loss),
                str(metrics.net_profit),
                str(metrics.average_win),
                str(metrics.average_loss),
            ),
        )

        metrics_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return metrics_id

    def get_latest_performance_metrics(
        self, symbol: str, timeframe: str
    ) -> PerformanceMetrics | None:
        """Retrieve the latest performance metrics for a symbol and timeframe."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        SELECT * FROM performance_metrics 
        WHERE symbol = ? AND timeframe = ? 
        ORDER BY timestamp DESC LIMIT 1
        """,
            (symbol, timeframe),
        )

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return PerformanceMetrics(
            total_trades=row[3],
            winning_trades=row[4],
            losing_trades=row[5],
            win_rate=row[6],
            profit_factor=row[7],
            max_drawdown=row[8],
            sharpe_ratio=row[9],
            total_profit=Decimal(row[10]),
            total_loss=Decimal(row[11]),
            net_profit=Decimal(row[12]),
            average_win=Decimal(row[13]),
            average_loss=Decimal(row[14]),
        )

    def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database."""
        try:
            import shutil

            shutil.copy2(self.db_path, backup_path)
            logger.info(f"{NEON_GREEN}Database backed up to {backup_path}{RESET}")
            return True
        except Exception as e:
            logger.error(f"{NEON_RED}Failed to backup database: {e}{RESET}")
            return False


# --- Performance Calculator ---
class PerformanceCalculator:
    """Calculates performance metrics from signal history."""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def calculate_metrics(self, symbol: str, timeframe: str) -> PerformanceMetrics:
        """Calculate performance metrics for a symbol and timeframe."""
        signals = self.db_manager.get_signal_history(
            symbol, timeframe, limit=MAX_SIGNAL_HISTORY
        )

        # Filter completed signals (with exit price)
        completed_signals = [s for s in signals if s.exit_price is not None]

        if not completed_signals:
            return PerformanceMetrics()

        # Calculate basic metrics
        total_trades = len(completed_signals)
        winning_trades = sum(
            1 for s in completed_signals if s.profit_loss and s.profit_loss > 0
        )
        losing_trades = total_trades - winning_trades

        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # Calculate profit metrics
        total_profit = sum(
            s.profit_loss
            for s in completed_signals
            if s.profit_loss and s.profit_loss > 0
        )
        total_loss = abs(
            sum(
                s.profit_loss
                for s in completed_signals
                if s.profit_loss and s.profit_loss < 0
            )
        )

        net_profit = total_profit - total_loss

        average_win = (
            total_profit / winning_trades if winning_trades > 0 else Decimal("0")
        )
        average_loss = total_loss / losing_trades if losing_trades > 0 else Decimal("0")

        profit_factor = float(total_profit / total_loss) if total_loss > 0 else 0.0

        # Calculate max drawdown
        cumulative_pl = [Decimal("0")]
        for s in completed_signals:
            if s.profit_loss is not None:
                cumulative_pl.append(cumulative_pl[-1] + s.profit_loss)

        peak = cumulative_pl[0]
        max_drawdown = Decimal("0")
        for value in cumulative_pl[1:]:
            if value > peak:
                peak = value
            else:
                drawdown = (peak - value) / peak if peak > 0 else Decimal("0")
                max_drawdown = max(max_drawdown, drawdown)

        # Calculate Sharpe ratio (simplified, using daily returns)
        if len(completed_signals) > 1:
            returns = [
                float(s.profit_loss)
                for s in completed_signals
                if s.profit_loss is not None
            ]
            avg_return = statistics.mean(returns)
            std_return = statistics.stdev(returns) if len(returns) > 1 else 0.001
            sharpe_ratio = avg_return / std_return if std_return > 0 else 0.0
        else:
            sharpe_ratio = 0.0

        return PerformanceMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=float(max_drawdown),
            sharpe_ratio=sharpe_ratio,
            total_profit=total_profit,
            total_loss=total_loss,
            net_profit=net_profit,
            average_win=average_win,
            average_loss=average_loss,
        )


# --- Data Validator ---
class DataValidator:
    """Validates market data before analysis."""

    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.validation_config = config.get("data_validation", {})

    def validate_dataframe(self, df: pd.DataFrame, symbol: str, interval: str) -> bool:
        """Validate a DataFrame of market data."""
        if df.empty:
            self.logger.error(
                f"{NEON_RED}Empty DataFrame for {symbol} {interval}{RESET}"
            )
            return False

        # Check minimum data points
        min_data_points = self.validation_config.get("min_data_points", 50)
        if len(df) < min_data_points:
            self.logger.error(
                f"{NEON_RED}Insufficient data points for {symbol} {interval}: {len(df)} < {min_data_points}{RESET}"
            )
            return False

        # Check required columns
        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            self.logger.error(
                f"{NEON_RED}Missing required columns for {symbol} {interval}: {missing_columns}{RESET}"
            )
            return False

        # Check for NaN values
        if df[required_columns].isnull().any().any():
            self.logger.warning(
                f"{NEON_YELLOW}NaN values found in {symbol} {interval} data{RESET}"
            )
            # Fill NaN values with previous values
            df.fillna(method="ffill", inplace=True)
            # If there are still NaN values (at the beginning), drop those rows
            df.dropna(inplace=True)

        # Check data age - Fixed timezone issue
        max_data_age_minutes = self.validation_config.get("max_data_age_minutes", 60)
        if "start_time" in df.columns:
            latest_timestamp = df["start_time"].max()

            # Make both timestamps timezone-aware or both timezone-naive
            now = datetime.now(TIMEZONE)

            # If latest_timestamp is naive, localize it to the same timezone
            if latest_timestamp.tzinfo is None:
                latest_timestamp = latest_timestamp.tz_localize(TIMEZONE)

            data_age = (now - latest_timestamp).total_seconds() / 60
            if data_age > max_data_age_minutes:
                self.logger.warning(
                    f"{NEON_YELLOW}Data for {symbol} {interval} is stale: {data_age:.1f} minutes old{RESET}"
                )

        # Check for price anomalies
        price_deviation_threshold = self.validation_config.get(
            "price_deviation_threshold", 0.1
        )
        if "close" in df.columns:
            prices = df["close"].values
            price_changes = np.abs(np.diff(prices) / prices[:-1])
            max_deviation = np.max(price_changes)
            if max_deviation > price_deviation_threshold:
                self.logger.warning(
                    f"{NEON_YELLOW}Large price deviation detected in {symbol} {interval}: {max_deviation:.2%}{RESET}"
                )

        return True


# --- Market Regime Detector ---
class MarketRegimeDetector:
    """Detects market regimes (bullish, bearish, sideways, volatile)."""

    def __init__(self, df: pd.DataFrame, config: dict, logger: logging.Logger):
        self.df = df.copy()
        self.config = config
        self.logger = logger
        self.atr_period = config.get("atr_period", 14)
        self.regime_window = config.get("regime_window", 20)

    def detect_regime(self) -> MarketRegime:
        """Detect the current market regime."""
        if len(self.df) < self.regime_window:
            return MarketRegime.UNKNOWN

        # Calculate indicators for regime detection
        close_prices = self.df["close"].values
        atr = self._calculate_atr()

        # Calculate price change over the window
        price_change = (
            close_prices[-1] - close_prices[-self.regime_window]
        ) / close_prices[-self.regime_window]

        # Calculate volatility (normalized ATR)
        volatility = atr / close_prices[-1] if close_prices[-1] > 0 else 0

        # Determine regime based on price change and volatility
        volatility_threshold = self.config.get("volatility_threshold", 0.02)
        trend_threshold = self.config.get("trend_threshold", 0.05)

        if volatility > volatility_threshold:
            return MarketRegime.VOLATILE
        if price_change > trend_threshold:
            return MarketRegime.BULLISH
        if price_change < -trend_threshold:
            return MarketRegime.BEARISH
        return MarketRegime.SIDEWAYS

    def _calculate_atr(self) -> float:
        """Calculate Average True Range."""
        high = self.df["high"].values
        low = self.df["low"].values
        close = self.df["close"].values

        tr1 = high[1:] - low[1:]
        tr2 = np.abs(high[1:] - close[:-1])
        tr3 = np.abs(low[1:] - close[:-1])

        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        atr = (
            np.mean(tr[-self.atr_period :])
            if len(tr) >= self.atr_period
            else np.mean(tr)
        )

        return atr


# --- Risk Manager ---
class RiskManager:
    """Manages trading risk and position sizing."""

    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.risk_config = config.get("risk_management", {})
        self.circuit_breaker_config = self.risk_config.get("circuit_breaker", {})
        self.consecutive_losses = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_end_time = None

    def calculate_position_size(
        self, price: Decimal, stop_loss: Decimal, account_balance: Decimal
    ) -> float:
        """Calculate position size based on risk management rules."""
        risk_per_trade = self.risk_config.get(
            "risk_per_trade", 0.02
        )  # 2% risk per trade
        max_position_size = self.risk_config.get(
            "max_position_size", 0.1
        )  # 10% max position size

        # Calculate risk amount
        risk_amount = account_balance * Decimal(str(risk_per_trade))

        # Calculate risk per unit
        risk_per_unit = abs(price - stop_loss)

        if risk_per_unit == 0:
            self.logger.warning(
                f"{NEON_YELLOW}Risk per unit is zero, using minimum position size{RESET}"
            )
            return 0.01  # Minimum position size

        # Calculate position size
        position_size = float(risk_amount / risk_per_unit)

        # Apply maximum position size limit
        max_position_value = float(account_balance * Decimal(str(max_position_size)))
        position_size = min(position_size, max_position_value / float(price))

        self.logger.info(
            f"{NEON_BLUE}Calculated position size: {position_size:.4f} (Risk: {float(risk_amount):.2f}){RESET}"
        )
        return position_size

    def check_circuit_breaker(self) -> bool:
        """Check if circuit breaker should be activated."""
        if not self.circuit_breaker_config.get("enabled", False):
            return False

        # Check if circuit breaker is already active
        if self.circuit_breaker_active:
            if (
                self.circuit_breaker_end_time
                and time.time() > self.circuit_breaker_end_time
            ):
                self.circuit_breaker_active = False
                self.logger.info(f"{NEON_GREEN}Circuit breaker deactivated{RESET}")
                return False
            return True

        # Check consecutive losses
        max_consecutive_losses = self.circuit_breaker_config.get(
            "max_consecutive_losses", 5
        )
        if self.consecutive_losses >= max_consecutive_losses:
            self.circuit_breaker_active = True
            cooldown_minutes = self.circuit_breaker_config.get(
                "cooldown_period_minutes", 60
            )
            self.circuit_breaker_end_time = time.time() + (cooldown_minutes * 60)
            self.logger.warning(
                f"{NEON_RED}Circuit breaker activated due to {self.consecutive_losses} consecutive losses. Cooldown for {cooldown_minutes} minutes.{RESET}"
            )
            return True

        return False

    def update_trade_result(self, profit_loss: Decimal) -> None:
        """Update consecutive losses counter based on trade result."""
        if profit_loss < 0:
            self.consecutive_losses += 1
            self.logger.warning(
                f"{NEON_YELLOW}Consecutive losses: {self.consecutive_losses}{RESET}"
            )
        else:
            self.consecutive_losses = 0

    def check_daily_loss_limit(
        self, current_loss: Decimal, account_balance: Decimal
    ) -> bool:
        """Check if daily loss limit has been exceeded."""
        max_daily_loss = self.risk_config.get(
            "max_daily_loss", 0.05
        )  # 5% max daily loss
        loss_limit = account_balance * Decimal(str(max_daily_loss))

        if abs(current_loss) >= loss_limit:
            self.logger.error(
                f"{NEON_RED}Daily loss limit exceeded: {float(current_loss):.2f} >= {float(loss_limit):.2f}{RESET}"
            )
            return True

        return False

    def check_drawdown_limit(self, current_drawdown: float) -> bool:
        """Check if maximum drawdown limit has been exceeded."""
        max_drawdown = self.risk_config.get("max_drawdown", 0.15)  # 15% max drawdown

        if current_drawdown >= max_drawdown:
            self.logger.error(
                f"{NEON_RED}Maximum drawdown exceeded: {current_drawdown:.2%} >= {max_drawdown:.2%}{RESET}"
            )
            return True

        return False


# --- API Client ---
class APIClient:
    """Handles all API communication with Bybit."""

    def __init__(
        self, api_key: str, api_secret: str, base_url: str, logger: logging.Logger
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "X-BAPI-API-KEY": api_key}
        )
        self.rate_limiter = RateLimiter(logger)

    def generate_signature(self, params: dict) -> str:
        """Generates the HMAC SHA256 signature for Bybit API requests."""
        # Ensure params are sorted by key for consistent signature generation
        param_str = "&".join(
            [f"{key}={value}" for key, value in sorted(params.items())]
        )
        return hmac.new(
            self.api_secret.encode(), param_str.encode(), hashlib.sha256
        ).hexdigest()

    def handle_api_error(self, response: requests.Response) -> None:
        """Logs detailed API error responses."""
        self.logger.error(
            f"{NEON_RED}API request failed with status code: {response.status_code}{RESET}"
        )
        try:
            error_json = response.json()
            self.logger.error(f"{NEON_RED}Error details: {error_json}{RESET}")
        except json.JSONDecodeError:
            self.logger.error(f"{NEON_RED}Response text: {response.text}{RESET}")

    def make_request(
        self, method: str, endpoint: str, params: dict[str, Any] = None
    ) -> dict | None:
        """Sends a signed request to the Bybit API with retry logic.

        Args:
            method (str): HTTP method (e.g., "GET", "POST").
            endpoint (str): API endpoint path.
            params (Dict[str, Any], optional): Dictionary of request parameters. Defaults to None.

        Returns:
            Union[dict, None]: JSON response data if successful, None otherwise.

        """
        # Apply rate limiting
        self.rate_limiter.wait_if_needed()

        params = params or {}
        params["timestamp"] = str(
            int(time.time() * 1000)
        )  # Current timestamp in milliseconds
        signature = self.generate_signature(params)
        headers = {"X-BAPI-SIGN": signature, "X-BAPI-TIMESTAMP": params["timestamp"]}
        url = f"{self.base_url}{endpoint}"

        for retry in range(MAX_API_RETRIES):
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params if method == "GET" else None,
                    json=params if method == "POST" else None,
                    timeout=10,  # Set a timeout for requests
                )
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in RETRY_ERROR_CODES:
                    self.logger.warning(
                        f"{NEON_YELLOW}API Error {e.response.status_code} ({e.response.reason}), retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}"
                    )
                    time.sleep(RETRY_DELAY_SECONDS * (2**retry))  # Exponential backoff
                else:
                    self.handle_api_error(e.response)
                    return None
            except requests.exceptions.RequestException as e:
                self.logger.error(
                    f"{NEON_RED}Request exception: {e}, retrying {retry + 1}/{MAX_API_RETRIES}...{RESET}"
                )
                time.sleep(RETRY_DELAY_SECONDS * (2**retry))

        self.logger.error(
            f"{NEON_RED}Max retries reached for {method} {endpoint}{RESET}"
        )
        return None

    def fetch_current_price(self, symbol: str) -> Decimal | None:
        """Fetches the current last traded price for a given symbol."""
        endpoint = "/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        response_data = self.make_request("GET", endpoint, params)

        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
        ):
            tickers = response_data["result"].get("list")
            if tickers:
                for ticker in tickers:
                    if ticker.get("symbol") == symbol:
                        last_price = ticker.get("lastPrice")
                        return Decimal(last_price) if last_price else None

        self.logger.error(
            f"{NEON_RED}Could not fetch current price for {symbol}. Response: {response_data}{RESET}"
        )
        return None

    def fetch_klines(
        self, symbol: str, interval: str, limit: int = 200
    ) -> pd.DataFrame:
        """Fetches historical K-line (candlestick) data for a given symbol and interval."""
        endpoint = "/v5/market/kline"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "category": "linear",
        }
        response_data = self.make_request("GET", endpoint, params)

        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
            and response_data["result"].get("list")
        ):
            data = response_data["result"]["list"]
            # Bybit's kline list order is: [timestamp, open, high, low, close, volume, turnover]
            columns = [
                "start_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ]
            df = pd.DataFrame(data, columns=columns)
            df["start_time"] = pd.to_datetime(
                pd.to_numeric(df["start_time"]), unit="ms"
            )
            # Convert numeric columns, coercing errors to NaN
            for col in df.columns[1:]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            # Drop any rows that resulted in all NaNs after conversion (shouldn't happen with valid data)
            df.dropna(subset=df.columns[1:], inplace=True)
            return df.sort_values(by="start_time", ascending=True).reset_index(
                drop=True
            )  # Ensure chronological order

        self.logger.error(
            f"{NEON_RED}Failed to fetch Kline data for {symbol}, interval {interval}. Response: {response_data}{RESET}"
        )
        return pd.DataFrame()

    def fetch_order_book(self, symbol: str, limit: int = 50) -> dict | None:
        """Fetches the order book (bids and asks) for a given symbol."""
        endpoint = "/v5/market/orderbook"
        params = {"symbol": symbol, "limit": limit, "category": "linear"}
        response_data = self.make_request("GET", endpoint, params)

        if (
            response_data
            and response_data.get("retCode") == 0
            and response_data.get("result")
        ):
            return response_data["result"]

        self.logger.warning(
            f"{NEON_YELLOW}Could not fetch order book for {symbol}. Response: {response_data}{RESET}"
        )
        return None


# --- Rate Limiter ---
class RateLimiter:
    """Implements rate limiting for API requests."""

    def __init__(self, logger: logging.Logger, max_requests_per_minute: int = 100):
        self.logger = logger
        self.max_requests_per_minute = max_requests_per_minute
        self.requests = []
        self.lock = threading.Lock()

    def wait_if_needed(self) -> None:
        """Wait if the rate limit would be exceeded."""
        with self.lock:
            now = time.time()
            # Remove requests older than 1 minute
            self.requests = [
                req_time for req_time in self.requests if now - req_time < 60
            ]

            if len(self.requests) >= self.max_requests_per_minute:
                # Calculate how long to wait
                oldest_request = min(self.requests)
                wait_time = 60 - (now - oldest_request)
                if wait_time > 0:
                    self.logger.warning(
                        f"{NEON_YELLOW}Rate limit reached, waiting {wait_time:.1f} seconds{RESET}"
                    )
                    time.sleep(wait_time)
                    # Clear the requests after waiting
                    self.requests = []

            # Record this request
            self.requests.append(now)


# --- Indicator Calculator ---
class IndicatorCalculator:
    """Handles all technical indicator calculations."""

    def __init__(self, df: pd.DataFrame, config: dict, logger: logging.Logger):
        self.df = df.copy()  # Work on a copy to avoid modifying original DataFrame
        self.config = config
        self.logger = logger
        self.indicator_values: dict[str, Any] = {}
        self.atr_value: float = 0.0
        self._validate_data()

    def _validate_data(self) -> None:
        """Validates the input data for calculations."""
        if self.df.empty:
            raise ValueError("DataFrame is empty")

        min_data_points = self.config.get("data_validation", {}).get(
            "min_data_points", 50
        )
        if len(self.df) < min_data_points:
            self.logger.warning(
                f"{NEON_YELLOW}Insufficient data points: {len(self.df)} < {min_data_points}{RESET}"
            )

        # Check for required columns
        required_columns = ["open", "high", "low", "close", "volume"]
        missing_columns = [
            col for col in required_columns if col not in self.df.columns
        ]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")

        # Check for NaN values
        if self.df[required_columns].isnull().any().any():
            self.logger.warning(
                f"{NEON_YELLOW}DataFrame contains NaN values in required columns{RESET}"
            )

    def _safe_series_operation(
        self, column: str, operation: str, window: int = None, series: pd.Series = None
    ) -> pd.Series:
        """Helper to safely perform operations on DataFrame columns or provided series."""
        if series is not None:
            data_series = series
        elif column in self.df.columns:
            data_series = self.df[column]
        else:
            self.logger.error(
                f"{NEON_RED}Missing '{column}' column for {operation} calculation.{RESET}"
            )
            return pd.Series(dtype=float)

        if data_series.empty:
            return pd.Series(dtype=float)

        try:
            if operation == "sma":
                return data_series.rolling(window=window).mean()
            if operation == "ema":
                return data_series.ewm(span=window, adjust=False).mean()
            if operation == "max":
                return data_series.rolling(window=window).max()
            if operation == "min":
                return data_series.rolling(window=window).min()
            if operation == "diff":
                return data_series.diff(window)
            if operation == "abs_diff_mean":
                return data_series.rolling(window=window).apply(
                    lambda x: np.abs(x - x.mean()).mean(), raw=True
                )
            if operation == "cumsum":
                return data_series.cumsum()
            self.logger.error(
                f"{NEON_RED}Unsupported series operation: {operation}{RESET}"
            )
            return pd.Series(dtype=float)
        except Exception as e:
            self.logger.error(
                f"{NEON_RED}Error during {operation} calculation on {column}: {e}{RESET}"
            )
            return pd.Series(dtype=float)

    def calculate_sma(self, window: int, series: pd.Series = None) -> pd.Series:
        """Calculates Simple Moving Average (SMA). Can operate on a specified series or 'close' price."""
        return self._safe_series_operation("close", "sma", window, series)

    def calculate_ema(self, window: int, series: pd.Series = None) -> pd.Series:
        """Calculates Exponential Moving Average (EMA). Can operate on a specified series or 'close' price."""
        return self._safe_series_operation("close", "ema", window, series)

    def calculate_atr(self, window: int = 14) -> pd.Series:
        """Calculates the Average True Range (ATR)."""
        high_low = self.df["high"] - self.df["low"]
        high_close = abs(self.df["high"] - self.df["close"].shift())
        low_close = abs(self.df["low"] - self.df["close"].shift())

        # True Range is the maximum of the three
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return self._safe_series_operation(
            None, "ema", window, tr
        )  # Use EMA for ATR for smoothing

    def calculate_rsi(self, window: int = 14) -> pd.Series:
        """Calculates the Relative Strength Index (RSI)."""
        delta = self.df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = self._safe_series_operation(None, "ema", window, gain)
        avg_loss = self._safe_series_operation(None, "ema", window, loss)

        # Avoid division by zero
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Fill NaN from division by zero with 0

    def calculate_stoch_rsi(
        self,
        rsi_window: int = 14,
        stoch_window: int = 14,
        k_window: int = 3,
        d_window: int = 3,
    ) -> pd.DataFrame:
        """Calculates Stochastic RSI (%K and %D lines)."""
        rsi = self.calculate_rsi(window=rsi_window)
        if rsi.empty:
            return pd.DataFrame()

        # Calculate StochRSI
        stoch_rsi = (
            rsi - self._safe_series_operation(None, "min", stoch_window, rsi)
        ) / (
            self._safe_series_operation(None, "max", stoch_window, rsi)
            - self._safe_series_operation(None, "min", stoch_window, rsi)
        )

        # Handle division by zero for StochRSI (if max == min)
        stoch_rsi = stoch_rsi.replace([np.inf, -np.inf], np.nan).fillna(0)
        k_line = (
            self._safe_series_operation(None, "sma", k_window, stoch_rsi) * 100
        )  # Scale to 0-100
        d_line = self._safe_series_operation(
            None, "sma", d_window, k_line
        )  # Signal line for %K

        return pd.DataFrame(
            {"stoch_rsi": stoch_rsi * 100, "k": k_line, "d": d_line}
        )  # Return StochRSI also scaled

    def calculate_stochastic_oscillator(self) -> pd.DataFrame:
        """Calculates the Stochastic Oscillator (%K and %D lines)."""
        k_period = self.config["indicator_periods"]["stoch_osc_k"]
        d_period = self.config["indicator_periods"]["stoch_osc_d"]

        highest_high = self._safe_series_operation("high", "max", k_period)
        lowest_low = self._safe_series_operation("low", "min", k_period)

        # Calculate %K
        k_line = (self.df["close"] - lowest_low) / (highest_high - lowest_low) * 100
        k_line = k_line.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Handle division by zero

        # Calculate %D (SMA of %K)
        d_line = self._safe_series_operation(None, "sma", d_period, k_line)

        return pd.DataFrame({"k": k_line, "d": d_line})

    def calculate_macd(self) -> pd.DataFrame:
        """Calculates Moving Average Convergence Divergence (MACD)."""
        ma_short = self._safe_series_operation("close", "ema", 12)
        ma_long = self._safe_series_operation("close", "ema", 26)
        macd = ma_short - ma_long
        signal = self._safe_series_operation(None, "ema", 9, macd)
        histogram = macd - signal

        return pd.DataFrame({"macd": macd, "signal": signal, "histogram": histogram})

    def calculate_cci(self, window: int = 20, constant: float = 0.015) -> pd.Series:
        """Calculates the Commodity Channel Index (CCI)."""
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        sma_typical_price = self._safe_series_operation(
            None, "sma", window, typical_price
        )
        mean_deviation = self._safe_series_operation(
            None, "abs_diff_mean", window, typical_price
        )

        # Avoid division by zero
        cci = (typical_price - sma_typical_price) / (constant * mean_deviation)
        return cci.replace([np.inf, -np.inf], np.nan)

    def calculate_williams_r(self, window: int = 14) -> pd.Series:
        """Calculates the Williams %R indicator."""
        highest_high = self._safe_series_operation("high", "max", window)
        lowest_low = self._safe_series_operation("low", "min", window)

        # Avoid division by zero
        denominator = highest_high - lowest_low
        wr = ((highest_high - self.df["close"]) / denominator) * -100
        return wr.replace([np.inf, -np.inf], np.nan)

    def calculate_mfi(self, window: int = 14) -> pd.Series:
        """Calculates the Money Flow Index (MFI)."""
        typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        raw_money_flow = typical_price * self.df["volume"]

        # Calculate positive and negative money flow
        money_flow_direction = typical_price.diff()
        positive_flow = raw_money_flow.where(money_flow_direction > 0, 0)
        negative_flow = raw_money_flow.where(money_flow_direction < 0, 0)

        # Calculate sums over the window
        positive_mf = (
            self._safe_series_operation(None, "sma", window, positive_flow) * window
        )  # sum not mean
        negative_mf = (
            self._safe_series_operation(None, "sma", window, negative_flow) * window
        )  # sum not mean

        # Avoid division by zero
        money_ratio = positive_mf / negative_mf.replace(
            0, np.nan
        )  # Replace 0 with NaN to handle division by zero
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi.replace([np.inf, -np.inf], np.nan).fillna(
            0
        )  # Fill NaN from division by zero with 0

    def calculate_adx(self, window: int = 14) -> float:
        """Calculates the Average Directional Index (ADX)."""
        # True Range
        tr = pd.concat(
            [
                self.df["high"] - self.df["low"],
                abs(self.df["high"] - self.df["close"].shift()),
                abs(self.df["low"] - self.df["close"].shift()),
            ],
            axis=1,
        ).max(axis=1)

        # Directional Movement
        df_adx = pd.DataFrame(index=self.df.index)
        df_adx["+DM"] = np.where(
            (self.df["high"] - self.df["high"].shift())
            > (self.df["low"].shift() - self.df["low"]),
            np.maximum(self.df["high"] - self.df["high"].shift(), 0),
            0,
        )
        df_adx["-DM"] = np.where(
            (self.df["low"].shift() - self.df["low"])
            > (self.df["high"] - self.df["high"].shift()),
            np.maximum(self.df["low"].shift() - self.df["low"], 0),
            0,
        )

        # Smoothed True Range and Directional Movement (using EMA)
        df_adx["TR_ema"] = self._safe_series_operation(None, "ema", window, tr)
        df_adx["+DM_ema"] = self._safe_series_operation(
            None, "ema", window, df_adx["+DM"]
        )
        df_adx["-DM_ema"] = self._safe_series_operation(
            None, "ema", window, df_adx["-DM"]
        )

        # Directional Indicators
        df_adx["+DI"] = 100 * (df_adx["+DM_ema"] / df_adx["TR_ema"].replace(0, np.nan))
        df_adx["-DI"] = 100 * (df_adx["-DM_ema"] / df_adx["TR_ema"].replace(0, np.nan))

        # Directional Movement Index (DX)
        df_adx["DX"] = (
            100
            * abs(df_adx["+DI"] - df_adx["-DI"])
            / (df_adx["+DI"] + df_adx["-DI"]).replace(0, np.nan)
        )

        # Average Directional Index (ADX)
        adx_value = self._safe_series_operation(None, "ema", window, df_adx["DX"]).iloc[
            -1
        ]
        return adx_value if not pd.isna(adx_value) else 0.0

    def calculate_obv(self) -> pd.Series:
        """Calculates On-Balance Volume (OBV)."""
        obv = pd.Series(0, index=self.df.index, dtype=float)
        obv.iloc[0] = self.df["volume"].iloc[0]  # Initialize with first volume

        for i in range(1, len(self.df)):
            if self.df["close"].iloc[i] > self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + self.df["volume"].iloc[i]
            elif self.df["close"].iloc[i] < self.df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - self.df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]  # No change if close price is the same

        return obv

    def calculate_adi(self) -> pd.Series:
        """Calculates Accumulation/Distribution Index (ADI)."""
        # Money Flow Multiplier (MFM)
        mfm_denominator = self.df["high"] - self.df["low"]
        mfm = (
            (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
        ) / mfm_denominator.replace(0, np.nan)
        mfm.fillna(0, inplace=True)  # If high == low, MFM is 0

        # Money Flow Volume (MFV)
        money_flow_volume = mfm * self.df["volume"]

        # Accumulation/Distribution Line (ADL) is the cumulative sum of MFV
        return self._safe_series_operation(None, "cumsum", series=money_flow_volume)

    def calculate_psar(
        self, acceleration: float = 0.02, max_acceleration: float = 0.2
    ) -> pd.Series:
        """Calculates Parabolic SAR (PSAR)."""
        psar = pd.Series(index=self.df.index, dtype="float64")
        if self.df.empty or len(self.df) < 2:  # Need at least two bars to start
            return psar

        # Initial values
        psar.iloc[0] = self.df["close"].iloc[0]  # Start PSAR at first close

        # Determine initial trend based on first two bars
        if self.df["close"].iloc[1] > self.df["close"].iloc[0]:
            trend = 1  # Uptrend
            ep = self.df["high"].iloc[0]  # Extreme Point
        else:
            trend = -1  # Downtrend
            ep = self.df["low"].iloc[0]  # Extreme Point

        af = acceleration  # Acceleration Factor

        for i in range(1, len(self.df)):
            current_high = self.df["high"].iloc[i]
            current_low = self.df["low"].iloc[i]
            prev_psar = psar.iloc[i - 1]

            if trend == 1:  # Uptrend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Check if PSAR should be below current low
                psar.iloc[i] = min(
                    psar.iloc[i],
                    current_low,
                    self.df["low"].iloc[i - 1] if i > 1 else current_low,
                )

                if current_high > ep:  # New extreme high
                    ep = current_high
                    af = min(af + acceleration, max_acceleration)

                if current_low < psar.iloc[i]:  # Trend reversal
                    trend = -1
                    psar.iloc[i] = ep  # PSAR jumps to old EP
                    ep = current_low
                    af = acceleration

            elif trend == -1:  # Downtrend
                psar.iloc[i] = prev_psar + af * (ep - prev_psar)
                # Check if PSAR should be above current high
                psar.iloc[i] = max(
                    psar.iloc[i],
                    current_high,
                    self.df["high"].iloc[i - 1] if i > 1 else current_high,
                )

                if current_low < ep:  # New extreme low
                    ep = current_low
                    af = min(af + acceleration, max_acceleration)

                if current_high > psar.iloc[i]:  # Trend reversal
                    trend = 1
                    psar.iloc[i] = ep  # PSAR jumps to old EP
                    ep = current_high
                    af = acceleration

        return psar

    def calculate_fve(self) -> pd.Series:
        """Calculates a "Fictional Value Estimate" (FVE) by combining price, volume, and volatility.
        This is a custom composite indicator for demonstrative purposes.
        """
        try:
            # Ensure enough data for calculations
            min_data_points = max(20, self.config["atr_period"])
            if len(self.df) < min_data_points:
                self.logger.warning(
                    f"{NEON_YELLOW}Insufficient data for FVE calculation. Need at least {min_data_points} bars.{RESET}"
                )
                return pd.Series([np.nan] * len(self.df), index=self.df.index)

            # Components calculation, ensuring Decimal usage where appropriate
            price_component = self.calculate_ema(
                window=self.config["indicator_periods"]["fve_price_ema"]
            )  # Short term price trend
            obv_component = self.calculate_obv()
            atr_component = self.calculate_atr(
                window=self.config["indicator_periods"]["atr"]
            )

            # Convert components to Decimal for calculations if they are not already
            price_component_dec = pd.Series(
                [
                    Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
                    for x in price_component
                ],
                index=price_component.index,
            )
            obv_component_dec = pd.Series(
                [
                    Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
                    for x in obv_component
                ],
                index=obv_component.index,
            )
            atr_component_dec = pd.Series(
                [
                    Decimal(str(x)) if pd.notna(x) else Decimal("NaN")
                    for x in atr_component
                ],
                index=atr_component.index,
            )

            # Normalize components to prevent one from dominating excessively
            price_mean = (
                Decimal(str(price_component_dec.mean()))
                if pd.notna(price_component_dec.mean())
                else Decimal("NaN")
            )
            price_std = (
                Decimal(str(price_component_dec.std()))
                if pd.notna(price_component_dec.std())
                else Decimal("NaN")
            )
            obv_mean = (
                Decimal(str(obv_component_dec.mean()))
                if pd.notna(obv_component_dec.mean())
                else Decimal("NaN")
            )
            obv_std = (
                Decimal(str(obv_component_dec.std()))
                if pd.notna(obv_component_dec.std())
                else Decimal("NaN")
            )
            atr_mean = (
                Decimal(str(atr_component_dec.mean()))
                if pd.notna(atr_component_dec.mean())
                else Decimal("NaN")
            )
            atr_std = (
                Decimal(str(atr_component_dec.std()))
                if pd.notna(atr_component_dec.std())
                else Decimal("NaN")
            )

            # Handle potential division by zero for std dev
            price_norm = (
                (price_component_dec - price_mean) / price_std
                if price_std != 0
                else pd.Series(Decimal("0"), index=self.df.index)
            )
            obv_norm = (
                (obv_component_dec - obv_mean) / obv_std
                if obv_std != 0
                else pd.Series(Decimal("0"), index=self.df.index)
            )

            # Inverse of ATR: lower ATR means higher stability/less volatility, which can be seen as positive for trend following
            atr_inverse = pd.Series(
                [
                    Decimal("1.0") / Decimal(str(x)) if x and x != 0 else Decimal("NaN")
                    for x in atr_component_dec
                ],
                index=self.df.index,
            )
            atr_inverse = atr_inverse.replace(
                [Decimal("Infinity"), Decimal("-Infinity")], Decimal("NaN")
            )
            atr_inverse_mean = (
                Decimal(str(atr_inverse.mean()))
                if pd.notna(atr_inverse.mean())
                else Decimal("NaN")
            )
            atr_inverse_std = (
                Decimal(str(atr_inverse.std()))
                if pd.notna(atr_inverse.std())
                else Decimal("NaN")
            )
            atr_inverse_norm = (
                (atr_inverse - atr_inverse_mean) / atr_inverse_std
                if atr_inverse_std != 0
                else pd.Series(Decimal("0"), index=self.df.index)
            )

            # Combine them - this formula is illustrative and should be fine-tuned
            fve = (
                price_norm.fillna(Decimal("0"))
                + obv_norm.fillna(Decimal("0"))
                + atr_inverse_norm.fillna(Decimal("0"))
            )

            # Convert back to float Series for compatibility with later operations if needed
            return pd.Series(
                [float(x) if x != Decimal("NaN") else np.nan for x in fve],
                index=self.df.index,
            )
        except Exception as e:
            self.logger.error(f"{NEON_RED}Error calculating FVE: {e}{RESET}")
            return pd.Series([np.nan] * len(self.df), index=self.df.index)

    def calculate_all_indicators(self) -> dict[str, Any]:
        """Calculates all enabled indicators and returns their values."""
        results = {}

        # Pre-calculate ATR for volatility assessment
        atr_series = self.calculate_atr(window=self.config["atr_period"])
        if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
            self.atr_value = atr_series.iloc[-1]
            results["atr"] = self.atr_value
        else:
            self.atr_value = 0.0
            results["atr"] = 0.0

        # Calculate momentum and its moving averages
        self.df["momentum"] = self._safe_series_operation(
            "close", "diff", self.config["momentum_period"]
        )
        self.df["momentum_ma_short"] = self._safe_series_operation(
            None, "sma", self.config["momentum_ma_short"], self.df["momentum"]
        )
        self.df["momentum_ma_long"] = self._safe_series_operation(
            None, "sma", self.config["momentum_ma_long"], self.df["momentum"]
        )
        self.df["volume_ma"] = self._safe_series_operation(
            "volume", "sma", self.config["volume_ma_period"]
        )

        # Calculate each enabled indicator
        if self.config["indicators"].get("rsi"):
            rsi_series = self.calculate_rsi(
                window=self.config["indicator_periods"]["rsi"]
            )
            results["rsi"] = (
                rsi_series.iloc[-3:].tolist() if not rsi_series.empty else []
            )

        if self.config["indicators"].get("mfi"):
            mfi_series = self.calculate_mfi(
                window=self.config["indicator_periods"]["mfi"]
            )
            results["mfi"] = (
                mfi_series.iloc[-3:].tolist() if not mfi_series.empty else []
            )

        if self.config["indicators"].get("cci"):
            cci_series = self.calculate_cci(
                window=self.config["indicator_periods"]["cci"]
            )
            results["cci"] = (
                cci_series.iloc[-3:].tolist() if not cci_series.empty else []
            )

        if self.config["indicators"].get("wr"):
            wr_series = self.calculate_williams_r(
                window=self.config["indicator_periods"]["williams_r"]
            )
            results["wr"] = wr_series.iloc[-3:].tolist() if not wr_series.empty else []

        if self.config["indicators"].get("adx"):
            adx_value = self.calculate_adx(
                window=self.config["indicator_periods"]["adx"]
            )
            results["adx"] = [adx_value]  # ADX is a single value

        if self.config["indicators"].get("obv"):
            obv_series = self.calculate_obv()
            results["obv"] = (
                obv_series.iloc[-3:].tolist() if not obv_series.empty else []
            )

        if self.config["indicators"].get("adi"):
            adi_series = self.calculate_adi()
            results["adi"] = (
                adi_series.iloc[-3:].tolist() if not adi_series.empty else []
            )

        if self.config["indicators"].get("sma_10"):
            sma_series = self.calculate_sma(10)
            results["sma_10"] = [sma_series.iloc[-1]] if not sma_series.empty else []

        if self.config["indicators"].get("psar"):
            psar_series = self.calculate_psar()
            results["psar"] = (
                psar_series.iloc[-3:].tolist() if not psar_series.empty else []
            )

        if self.config["indicators"].get("fve"):
            fve_series = self.calculate_fve()
            if not fve_series.empty and not fve_series.isnull().all():
                results["fve"] = fve_series.iloc[-3:].tolist()
            else:
                results["fve"] = []

        if self.config["indicators"].get("macd"):
            macd_df = self.calculate_macd()
            results["macd"] = (
                macd_df.iloc[-3:].values.tolist() if not macd_df.empty else []
            )

        if self.config["indicators"].get("stoch_rsi"):
            stoch_rsi_df = self.calculate_stoch_rsi(
                rsi_window=self.config["indicator_periods"]["stoch_rsi_period"],
                stoch_window=self.config["indicator_periods"]["stoch_rsi_period"],
                k_window=self.config["indicator_periods"]["stoch_rsi_k_period"],
                d_window=self.config["indicator_periods"]["stoch_rsi_d_period"],
            )
            results["stoch_rsi_vals"] = stoch_rsi_df
            if not stoch_rsi_df.empty:
                results["stoch_rsi"] = stoch_rsi_df.iloc[-1].tolist()

        if self.config["indicators"].get("stochastic_oscillator"):
            stoch_osc_df = self.calculate_stochastic_oscillator()
            results["stoch_osc_vals"] = stoch_osc_df
            if not stoch_osc_df.empty:
                results["stoch_osc"] = stoch_osc_df.iloc[-1].tolist()

        # Store momentum trend data
        if self.config["indicators"].get("momentum"):
            trend_data = self.determine_trend_momentum()
            results["mom"] = trend_data

        # Calculate EMA alignment
        if self.config["indicators"].get("ema_alignment"):
            ema_alignment_score = self.calculate_ema_alignment()
            results["ema_alignment"] = ema_alignment_score

        return results

    def determine_trend_momentum(self) -> dict[str, str | float]:
        """Determines the current trend and its strength based on momentum MAs and ATR."""
        if self.df.empty or len(self.df) < max(
            self.config["momentum_ma_long"], self.config["atr_period"]
        ):
            return {"trend": "Insufficient Data", "strength": 0.0}

        # Ensure momentum_ma_short, momentum_ma_long, and atr_value are calculated
        if (
            self.df["momentum_ma_short"].empty
            or self.df["momentum_ma_long"].empty
            or self.atr_value == 0
        ):
            self.logger.warning(
                f"{NEON_YELLOW}Momentum MAs or ATR not available for trend calculation.{RESET}"
            )
            return {"trend": "Neutral", "strength": 0.0}

        latest_short_ma = self.df["momentum_ma_short"].iloc[-1]
        latest_long_ma = self.df["momentum_ma_long"].iloc[-1]

        trend = "Neutral"
        if latest_short_ma > latest_long_ma:
            trend = "Uptrend"
        elif latest_short_ma < latest_long_ma:
            trend = "Downtrend"

        # Strength is normalized by ATR to make it comparable across symbols/timeframes
        strength = abs(latest_short_ma - latest_long_ma) / self.atr_value
        return {"trend": trend, "strength": strength}

    def calculate_ema_alignment(self) -> float:
        """Calculates an EMA alignment score.
        Score is 1.0 for strong bullish alignment, -1.0 for strong bearish, 0.0 for neutral.
        """
        ema_short = self.calculate_ema(self.config["ema_short_period"])
        ema_long = self.calculate_ema(self.config["ema_long_period"])

        if (
            ema_short.empty
            or ema_long.empty
            or len(self.df)
            < max(self.config["ema_short_period"], self.config["ema_long_period"])
        ):
            return 0.0

        latest_short_ema = Decimal(str(ema_short.iloc[-1]))
        latest_long_ema = Decimal(str(ema_long.iloc[-1]))
        current_price = Decimal(str(self.df["close"].iloc[-1]))

        # Check for consistent alignment over the last few bars (e.g., 3 bars)
        alignment_period = 3
        if len(ema_short) < alignment_period or len(ema_long) < alignment_period:
            return 0.0

        bullish_aligned_count = 0
        bearish_aligned_count = 0

        for i in range(1, alignment_period + 1):
            if (
                ema_short.iloc[-i] > ema_long.iloc[-i]
                and self.df["close"].iloc[-i] > ema_short.iloc[-i]
            ):
                bullish_aligned_count += 1
            elif (
                ema_short.iloc[-i] < ema_long.iloc[-i]
                and self.df["close"].iloc[-i] < ema_short.iloc[-i]
            ):
                bearish_aligned_count += 1

        if (
            bullish_aligned_count >= alignment_period - 1
        ):  # At least (period-1) bars are aligned
            return 1.0  # Strong bullish alignment
        if bearish_aligned_count >= alignment_period - 1:
            return -1.0  # Strong bearish alignment
        # Check for recent crossover as a weaker signal
        if latest_short_ema > latest_long_ema and ema_short.iloc[-2] <= latest_long_ema:
            return 0.5  # Recent bullish crossover
        if latest_short_ema < latest_long_ema and ema_short.iloc[-2] >= latest_long_ema:
            return -0.5  # Recent bearish crossover
        return 0.0  # Neutral

    def detect_macd_divergence(self) -> str | None:
        """Detects bullish or bearish MACD divergence."""
        macd_df = self.calculate_macd()
        if (
            macd_df.empty or len(self.df) < 30
        ):  # Need sufficient data for reliable divergence
            return None

        prices = self.df["close"]
        macd_histogram = macd_df["histogram"]

        # Simple divergence check on last two bars (can be expanded for more robust detection)
        if (
            prices.iloc[-2] > prices.iloc[-1]
            and macd_histogram.iloc[-2] < macd_histogram.iloc[-1]
        ):
            self.logger.info(f"{NEON_GREEN}Detected Bullish MACD Divergence.{RESET}")
            return "bullish"
        if (
            prices.iloc[-2] < prices.iloc[-1]
            and macd_histogram.iloc[-2] > macd_histogram.iloc[-1]
        ):
            self.logger.info(f"{NEON_RED}Detected Bearish MACD Divergence.{RESET}")
            return "bearish"
        return None

    def calculate_volume_confirmation(self) -> bool:
        """Checks if the current volume confirms a trend (e.g., significant spike).
        Returns True if current volume is significantly higher than average.
        """
        if "volume" not in self.df.columns or "volume_ma" not in self.df.columns:
            self.logger.error(
                f"{NEON_RED}Missing 'volume' or 'volume_ma' column for Volume Confirmation.{RESET}"
            )
            return False

        if self.df["volume"].empty or self.df["volume_ma"].empty:
            return False

        current_volume = self.df["volume"].iloc[-1]
        average_volume = self.df["volume_ma"].iloc[-1]

        if average_volume <= 0:  # Avoid division by zero or nonsensical average
            return False

        return (
            current_volume
            > average_volume * self.config["volume_confirmation_multiplier"]
        )


# --- Support/Resistance Analyzer ---
class SupportResistanceAnalyzer:
    """Analyzes support and resistance levels using Fibonacci retracements and pivot points."""

    def __init__(self, df: pd.DataFrame, config: dict, logger: logging.Logger):
        self.df = df
        self.config = config
        self.logger = logger
        self.levels: dict[str, Any] = {}
        self.fib_levels: dict[str, float] = {}

    def calculate_fibonacci_retracement(
        self, high: Decimal, low: Decimal, current_price: Decimal
    ) -> dict[str, Decimal]:
        """Calculates Fibonacci retracement levels based on a given high and low."""
        diff = high - low
        if diff <= 0:  # Handle cases where high <= low
            self.logger.warning(
                f"{NEON_YELLOW}Cannot calculate Fibonacci retracement: High ({high}) <= Low ({low}).{RESET}"
            )
            self.fib_levels = {}
            self.levels = {"Support": {}, "Resistance": {}}
            return {}

        # Standard Fibonacci ratios
        fib_ratios = {
            "23.6%": Decimal("0.236"),
            "38.2%": Decimal("0.382"),
            "50.0%": Decimal("0.500"),
            "61.8%": Decimal("0.618"),
            "78.6%": Decimal("0.786"),
            "88.6%": Decimal("0.886"),
            "94.1%": Decimal("0.941"),
        }

        fib_levels_calculated: dict[str, Decimal] = {}

        # Assuming an uptrend (retracement from high to low)
        # Levels are calculated from the high, moving down
        for label, ratio in fib_ratios.items():
            level = high - (diff * ratio)
            fib_levels_calculated[f"Fib {label}"] = level.quantize(
                Decimal("0.00001")
            )  # Quantize for consistent precision

        self.fib_levels = fib_levels_calculated
        self.levels = {"Support": {}, "Resistance": {}}

        # Categorize levels as support or resistance relative to current price
        for label, value in self.fib_levels.items():
            if value < current_price:
                self.levels["Support"][label] = value
            elif value > current_price:
                self.levels["Resistance"][label] = value

        return self.fib_levels

    def calculate_pivot_points(self, high: Decimal, low: Decimal, close: Decimal):
        """Calculates standard Pivot Points."""
        pivot = (high + low + close) / 3
        r1 = (2 * pivot) - low
        s1 = (2 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)

        # Quantize all pivot points for consistent precision
        precision = Decimal("0.00001")
        self.levels.update(
            {
                "Pivot": pivot.quantize(precision),
                "R1": r1.quantize(precision),
                "S1": s1.quantize(precision),
                "R2": r2.quantize(precision),
                "S2": s2.quantize(precision),
                "R3": r3.quantize(precision),
                "S3": s3.quantize(precision),
            }
        )

    def find_nearest_levels(
        self, current_price: Decimal, num_levels: int = 5
    ) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
        """Finds the nearest support and resistance levels from calculated Fibonacci and Pivot Points."""
        all_support_levels: list[tuple[str, Decimal]] = []
        all_resistance_levels: list[tuple[str, Decimal]] = []

        def process_level(label: str, value: Decimal):
            if value < current_price:
                all_support_levels.append((label, value))
            elif value > current_price:
                all_resistance_levels.append((label, value))

        # Process all levels stored in self.levels (from Fibonacci and Pivot)
        for label, value in self.levels.items():
            if isinstance(
                value, dict
            ):  # For nested levels like "Support": {"Fib 23.6%": ...}
                for sub_label, sub_value in value.items():
                    if isinstance(sub_value, Decimal):
                        process_level(f"{label} ({sub_label})", sub_value)
            elif isinstance(value, Decimal):  # For direct levels like "Pivot"
                process_level(label, value)

        # Sort by distance to current price and select the 'num_levels' closest
        nearest_supports = sorted(
            all_support_levels, key=lambda x: current_price - x[1]
        )[:num_levels]
        nearest_resistances = sorted(
            all_resistance_levels, key=lambda x: x[1] - current_price
        )[:num_levels]

        return nearest_supports, nearest_resistances


# --- Order Book Analyzer ---
class OrderBookAnalyzer:
    """Analyzes order book data for support/resistance walls and liquidity."""

    def __init__(self, config: dict, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def analyze_order_book_walls(
        self, order_book: dict[str, Any], current_price: Decimal
    ) -> tuple[bool, bool, dict[str, Decimal], dict[str, Decimal]]:
        """Analyzes order book for significant bid (support) and ask (resistance) walls.
        Returns whether bullish/bearish walls are found and the wall details.
        """
        has_bullish_wall = False
        has_bearish_wall = False
        bullish_wall_details: dict[str, Decimal] = {}
        bearish_wall_details: dict[str, Decimal] = {}

        if not self.config["order_book_analysis"]["enabled"]:
            return False, False, {}, {}

        if not order_book or not order_book.get("bids") or not order_book.get("asks"):
            self.logger.warning(
                f"{NEON_YELLOW}Order book data incomplete for wall analysis.{RESET}"
            )
            return False, False, {}, {}

        bids = [
            (Decimal(price), Decimal(qty))
            for price, qty in order_book["bids"][
                : self.config["order_book_analysis"]["depth_to_check"]
            ]
        ]
        asks = [
            (Decimal(price), Decimal(qty))
            for price, qty in order_book["asks"][
                : self.config["order_book_analysis"]["depth_to_check"]
            ]
        ]

        # Calculate average quantity across relevant depth
        all_quantities = [qty for _, qty in bids + asks]
        if not all_quantities:
            return False, False, {}, {}

        avg_qty = Decimal(
            str(np.mean([float(q) for q in all_quantities]))
        )  # Convert to float for numpy, then back to Decimal
        wall_threshold = avg_qty * Decimal(
            str(self.config["order_book_analysis"]["wall_threshold_multiplier"])
        )

        # Check for bullish walls (large bids below current price)
        for bid_price, bid_qty in bids:
            if bid_qty >= wall_threshold and bid_price < current_price:
                has_bullish_wall = True
                bullish_wall_details[f"Bid@{bid_price}"] = bid_qty
                self.logger.info(
                    f"{NEON_GREEN}Detected Bullish Order Book Wall: Bid {bid_qty:.2f} at {bid_price:.2f}{RESET}"
                )
                break  # Only need to find one significant wall

        # Check for bearish walls (large asks above current price)
        for ask_price, ask_qty in asks:
            if ask_qty >= wall_threshold and ask_price > current_price:
                has_bearish_wall = True
                bearish_wall_details[f"Ask@{ask_price}"] = ask_qty
                self.logger.info(
                    f"{NEON_RED}Detected Bearish Order Book Wall: Ask {ask_qty:.2f} at {ask_price:.2f}{RESET}"
                )
                break  # Only need to find one significant wall

        return (
            has_bullish_wall,
            has_bearish_wall,
            bullish_wall_details,
            bearish_wall_details,
        )


# --- Multi-Timeframe Analyzer ---
class MultiTimeframeAnalyzer:
    """Analyzes multiple timeframes to generate consensus signals."""

    def __init__(self, api_client: APIClient, config: dict, logger: logging.Logger):
        self.api_client = api_client
        self.config = config
        self.logger = logger
        self.timeframes = config.get("multi_timeframe", {}).get(
            "timeframes", ["5", "15", "60"]
        )
        self.weighting = config.get("multi_timeframe", {}).get(
            "weighting", {"5": 0.2, "15": 0.5, "60": 0.3}
        )

    def analyze_timeframes(self, symbol: str) -> dict[str, TradingSignal]:
        """Analyze multiple timeframes and return signals for each."""
        signals = {}

        for timeframe in self.timeframes:
            try:
                # Fetch data for this timeframe
                df = self.api_client.fetch_klines(symbol, timeframe, limit=200)
                if df.empty:
                    self.logger.warning(
                        f"{NEON_YELLOW}No data for {symbol} {timeframe}{RESET}"
                    )
                    continue

                # Create analyzer for this timeframe
                analyzer = TradingAnalyzer(
                    df, self.config, self.logger, symbol, timeframe
                )

                # Get current price
                current_price = self.api_client.fetch_current_price(symbol)
                if current_price is None:
                    self.logger.warning(
                        f"{NEON_YELLOW}No price for {symbol} {timeframe}{RESET}"
                    )
                    continue

                # Generate signal
                signal = analyzer.generate_trading_signal(current_price)
                signals[timeframe] = signal

            except Exception as e:
                self.logger.error(
                    f"{NEON_RED}Error analyzing {symbol} {timeframe}: {e}{RESET}"
                )

        return signals

    def generate_consensus_signal(self, symbol: str) -> TradingSignal:
        """Generate a consensus signal from multiple timeframes."""
        timeframe_signals = self.analyze_timeframes(symbol)

        if not timeframe_signals:
            return TradingSignal(
                signal_type=SignalType.HOLD,
                confidence=0.0,
                conditions_met=["No signals from any timeframe"],
                stop_loss=None,
                take_profit=None,
                timestamp=time.time(),
                symbol=symbol,
                timeframe="multi",
            )

        # Calculate weighted scores
        buy_score = 0.0
        sell_score = 0.0

        buy_conditions = []
        sell_conditions = []

        for timeframe, signal in timeframe_signals.items():
            weight = self.weighting.get(timeframe, 1.0 / len(timeframe_signals))

            if signal.signal_type == SignalType.BUY:
                buy_score += signal.confidence * weight
                buy_conditions.extend(
                    [f"{timeframe}: {cond}" for cond in signal.conditions_met]
                )
            elif signal.signal_type == SignalType.SELL:
                sell_score += signal.confidence * weight
                sell_conditions.extend(
                    [f"{timeframe}: {cond}" for cond in signal.conditions_met]
                )

        # Determine consensus signal
        if buy_score > sell_score and buy_score >= self.config.get(
            "signal_score_threshold", 1.0
        ):
            return TradingSignal(
                signal_type=SignalType.BUY,
                confidence=buy_score,
                conditions_met=buy_conditions,
                stop_loss=None,  # Would need to determine from multiple timeframes
                take_profit=None,  # Would need to determine from multiple timeframes
                timestamp=time.time(),
                symbol=symbol,
                timeframe="multi",
            )
        if sell_score > buy_score and sell_score >= self.config.get(
            "signal_score_threshold", 1.0
        ):
            return TradingSignal(
                signal_type=SignalType.SELL,
                confidence=sell_score,
                conditions_met=sell_conditions,
                stop_loss=None,  # Would need to determine from multiple timeframes
                take_profit=None,  # Would need to determine from multiple timeframes
                timestamp=time.time(),
                symbol=symbol,
                timeframe="multi",
            )
        return TradingSignal(
            signal_type=SignalType.HOLD,
            confidence=0.0,
            conditions_met=["No clear consensus"],
            stop_loss=None,
            take_profit=None,
            timestamp=time.time(),
            symbol=symbol,
            timeframe="multi",
        )


# --- Trading Analyzer ---
class TradingAnalyzer:
    """Performs technical analysis on candlestick data and generates trading signals."""

    def __init__(
        self,
        df: pd.DataFrame,
        config: dict,
        symbol_logger: logging.Logger,
        symbol: str,
        interval: str,
    ):
        self.df = df.copy()  # Work on a copy to avoid modifying original DataFrame
        self.config = config
        self.logger = symbol_logger
        self.symbol = symbol
        self.interval = interval
        self.weight_sets = config["weight_sets"]
        self.indicator_values: dict[str, Any] = {}  # Stores calculated indicator values
        self.atr_value: float = 0.0  # Stores the latest ATR value

        # Initialize component analyzers
        self.indicator_calc = IndicatorCalculator(df, config, symbol_logger)
        self.sr_analyzer = SupportResistanceAnalyzer(df, config, symbol_logger)
        self.order_book_analyzer = OrderBookAnalyzer(config, symbol_logger)
        self.market_regime_detector = MarketRegimeDetector(df, config, symbol_logger)
        self.data_validator = DataValidator(config, symbol_logger)

        # Pre-calculate common indicators needed for others or for weight selection
        self._pre_calculate_indicators()

        # Now that ATR is potentially calculated, select the weight set
        self.user_defined_weights = (
            self._select_weight_set()
        )  # Dynamically selected weights

        # Detect market regime
        self.market_regime = self.market_regime_detector.detect_regime()

    def _pre_calculate_indicators(self):
        """Pre-calculates indicators necessary for weight selection or other calculations."""
        if not self.df.empty:
            # Calculate ATR once for volatility assessment
            atr_series = self.indicator_calc.calculate_atr(
                window=self.config["atr_period"]
            )
            if not atr_series.empty and not pd.isna(atr_series.iloc[-1]):
                self.atr_value = atr_series.iloc[-1]
            else:
                self.atr_value = 0.0  # Default ATR to 0 if calculation fails or is NaN

            self.indicator_values["atr"] = (
                self.atr_value
            )  # Store ATR for logging/analysis

            # Calculate momentum MAs for trend determination
            self.indicator_calc.df["momentum"] = (
                self.indicator_calc._safe_series_operation(
                    "close", "diff", self.config["momentum_period"]
                )
            )
            self.indicator_calc.df["momentum_ma_short"] = (
                self.indicator_calc._safe_series_operation(
                    None,
                    "sma",
                    self.config["momentum_ma_short"],
                    self.indicator_calc.df["momentum"],
                )
            )
            self.indicator_calc.df["momentum_ma_long"] = (
                self.indicator_calc._safe_series_operation(
                    None,
                    "sma",
                    self.config["momentum_ma_long"],
                    self.indicator_calc.df["momentum"],
                )
            )

    def _select_weight_set(self) -> dict[str, float]:
        """Selects a weight set (e.g., low_volatility, high_volatility) based on current ATR."""
        # Use the atr_value that was pre-calculated in _pre_calculate_indicators
        if self.atr_value > self.config["atr_change_threshold"]:
            self.logger.info(
                f"{NEON_YELLOW}Market detected as HIGH VOLATILITY (ATR: {self.atr_value:.4f}). Using 'high_volatility' weights.{RESET}"
            )
            return self.weight_sets.get(
                "high_volatility", self.weight_sets["low_volatility"]
            )

        self.logger.info(
            f"{NEON_BLUE}Market detected as LOW VOLATILITY (ATR: {self.atr_value:.4f}). Using 'low_volatility' weights.{RESET}"
        )
        return self.weight_sets["low_volatility"]

    def analyze(
        self, current_price: Decimal, timestamp: str, order_book: dict[str, Any]
    ):
        """Performs comprehensive analysis, calculates indicators, and logs the findings.
        This method populates `self.indicator_values` and generates the output string.
        It does NOT generate the final signal; that is done by `generate_trading_signal`.
        """
        # Ensure Decimal type for price calculations
        current_price_dec = Decimal(str(current_price))
        high_dec = Decimal(str(self.df["high"].max()))
        low_dec = Decimal(str(self.df["low"].min()))
        close_dec = Decimal(str(self.df["close"].iloc[-1]))

        # Calculate Support/Resistance Levels
        self.sr_analyzer.calculate_fibonacci_retracement(
            high_dec, low_dec, current_price_dec
        )
        self.sr_analyzer.calculate_pivot_points(high_dec, low_dec, close_dec)
        nearest_supports, nearest_resistances = self.sr_analyzer.find_nearest_levels(
            current_price_dec
        )

        # Calculate all indicators
        self.indicator_values = self.indicator_calc.calculate_all_indicators()

        # Order Book Analysis
        (
            has_bullish_wall,
            has_bearish_wall,
            bullish_wall_details,
            bearish_wall_details,
        ) = self.order_book_analyzer.analyze_order_book_walls(
            order_book, current_price_dec
        )

        self.indicator_values["order_book_walls"] = {
            "bullish": has_bullish_wall,
            "bearish": has_bearish_wall,
            "bullish_details": bullish_wall_details,
            "bearish_details": bearish_wall_details,
        }

        # Prepare output string
        output = f"""
{NEON_BLUE}Exchange:{RESET} Bybit
{NEON_BLUE}Symbol:{RESET} {self.symbol}
{NEON_BLUE}Interval:{RESET} {self.interval}
{NEON_BLUE}Market Regime:{RESET} {self.market_regime.value.upper()}
{NEON_BLUE}Timestamp:{RESET} {timestamp}
{NEON_BLUE}Price History:{RESET} {self.df["close"].iloc[-3]:.2f} | {self.df["close"].iloc[-2]:.2f} | {self.df["close"].iloc[-1]:.2f}
{NEON_BLUE}Volume History:{RESET} {self.df["volume"].iloc[-3]:,.0f} | {self.df["volume"].iloc[-2]:,.0f} | {self.df["volume"].iloc[-1]:,.0f}
{NEON_BLUE}Current Price:{RESET} {current_price_dec:.5f}
{NEON_BLUE}ATR ({self.config["atr_period"]}):{RESET} {self.atr_value:.5f}
{NEON_BLUE}Trend:{RESET} {self.indicator_values.get("mom", {}).get("trend", "N/A")} (Strength: {self.indicator_values.get("mom", {}).get("strength", 0.0):.2f})
"""

        # Append indicator interpretations
        for indicator_name, values in self.indicator_values.items():
            # Skip indicators that are already logged in a custom format or are internal
            if indicator_name in [
                "mom",
                "atr",
                "stoch_rsi_vals",
                "ema_alignment",
                "order_book_walls",
                "stoch_osc_vals",
            ]:
                continue

            interpreted_line = interpret_indicator(self.logger, indicator_name, values)
            if interpreted_line:
                output += interpreted_line + "\n"

        # Custom logging for specific indicators
        if self.config["indicators"].get("ema_alignment"):
            ema_alignment_score = self.indicator_values.get("ema_alignment", 0.0)
            status = (
                "Bullish"
                if ema_alignment_score > 0
                else "Bearish"
                if ema_alignment_score < 0
                else "Neutral"
            )
            output += f"{NEON_PURPLE}EMA Alignment:{RESET} Score={ema_alignment_score:.2f} ({status})\n"

        if (
            self.config["indicators"].get("stoch_rsi")
            and self.indicator_values.get("stoch_rsi_vals") is not None
            and not self.indicator_values["stoch_rsi_vals"].empty
        ):
            stoch_rsi_vals = self.indicator_values.get("stoch_rsi_vals")
            if (
                stoch_rsi_vals is not None
                and not stoch_rsi_vals.empty
                and len(stoch_rsi_vals) >= 3
            ):  # Ensure we have K, D, and Stoch RSI values
                output += f"{NEON_GREEN}Stoch RSI:{RESET} K={stoch_rsi_vals['k'].iloc[-1]:.2f}, D={stoch_rsi_vals['d'].iloc[-1]:.2f}, Stoch_RSI={stoch_rsi_vals['stoch_rsi'].iloc[-1]:.2f}\n"

        if (
            self.config["indicators"].get("stochastic_oscillator")
            and self.indicator_values.get("stoch_osc_vals") is not None
            and not self.indicator_values["stoch_osc_vals"].empty
        ):
            stoch_osc_vals = self.indicator_values.get("stoch_osc_vals")
            if (
                stoch_osc_vals is not None
                and not stoch_osc_vals.empty
                and len(stoch_osc_vals) >= 2
            ):  # Ensure we have K and D values
                output += f"{NEON_CYAN}Stochastic Oscillator:{RESET} K={stoch_osc_vals['k'].iloc[-1]:.2f}, D={stoch_osc_vals['d'].iloc[-1]:.2f}\n"

        # Order Book Wall Logging
        output += f"\n{NEON_BLUE}Order Book Walls:{RESET}\n"
        if has_bullish_wall:
            output += f"{NEON_GREEN}  Bullish Walls Found: {', '.join([f'{k}:{v:.2f}' for k, v in bullish_wall_details.items()])}{RESET}\n"
        if has_bearish_wall:
            output += f"{NEON_RED}  Bearish Walls Found: {', '.join([f'{k}:{v:.2f}' for k, v in bearish_wall_details.items()])}{RESET}\n"
        if not has_bullish_wall and not has_bearish_wall:
            output += "  No significant walls detected.\n"

        output += f"""
{NEON_BLUE}Support and Resistance Levels:{RESET}
"""
        for s_label, s_val in nearest_supports:
            output += f"S: {s_label} ${s_val:.5f}\n"
        for r_label, r_val in nearest_resistances:
            output += f"R: {r_label} ${r_val:.5f}\n"

        self.logger.info(output)

    def generate_trading_signal(self, current_price: Decimal) -> TradingSignal:
        """Generates a trading signal (buy/sell) based on indicator values and configuration.
        Returns a TradingSignal object with all relevant information.
        """
        signal_score = Decimal("0.0")
        signal_type = SignalType.HOLD
        conditions_met: list[str] = []
        stop_loss = None
        take_profit = None

        # --- Bullish Signal Logic ---
        # Sum weights of bullish conditions met
        if (
            self.config["indicators"].get("stoch_rsi")
            and self.indicator_values.get("stoch_rsi_vals") is not None
            and not self.indicator_values["stoch_rsi_vals"].empty
        ):
            stoch_rsi_k = Decimal(
                str(self.indicator_values["stoch_rsi_vals"]["k"].iloc[-1])
            )
            stoch_rsi_d = Decimal(
                str(self.indicator_values["stoch_rsi_vals"]["d"].iloc[-1])
            )
            if (
                stoch_rsi_k < self.config["stoch_rsi_oversold_threshold"]
                and stoch_rsi_k > stoch_rsi_d
            ):
                signal_score += Decimal(str(self.user_defined_weights["stoch_rsi"]))
                conditions_met.append("Stoch RSI Oversold Crossover")

        if (
            self.config["indicators"].get("rsi")
            and self.indicator_values.get("rsi")
            and self.indicator_values["rsi"][-1] < 30
        ):
            signal_score += Decimal(str(self.user_defined_weights["rsi"]))
            conditions_met.append("RSI Oversold")

        if (
            self.config["indicators"].get("mfi")
            and self.indicator_values.get("mfi")
            and self.indicator_values["mfi"][-1] < 20
        ):
            signal_score += Decimal(str(self.user_defined_weights["mfi"]))
            conditions_met.append("MFI Oversold")

        if (
            self.config["indicators"].get("ema_alignment")
            and self.indicator_values.get("ema_alignment", 0.0) > 0
        ):
            signal_score += Decimal(
                str(self.user_defined_weights["ema_alignment"])
            ) * Decimal(
                str(abs(self.indicator_values["ema_alignment"]))
            )  # Scale by score
            conditions_met.append("Bullish EMA Alignment")

        if (
            self.config["indicators"].get("volume_confirmation")
            and self.indicator_calc.calculate_volume_confirmation()
        ):
            signal_score += Decimal(
                str(self.user_defined_weights["volume_confirmation"])
            )
            conditions_met.append("Volume Confirmation")

        if (
            self.config["indicators"].get("divergence")
            and self.indicator_calc.detect_macd_divergence() == "bullish"
        ):
            signal_score += Decimal(str(self.user_defined_weights["divergence"]))
            conditions_met.append("Bullish MACD Divergence")

        if self.indicator_values["order_book_walls"].get("bullish"):
            signal_score += Decimal(
                str(self.config["order_book_support_confidence_boost"] / 10.0)
            )  # Boost score for order book wall
            conditions_met.append("Bullish Order Book Wall")

        # Stochastic Oscillator Bullish Signal
        if (
            self.config["indicators"].get("stochastic_oscillator")
            and self.indicator_values.get("stoch_osc_vals") is not None
            and not self.indicator_values["stoch_osc_vals"].empty
        ):
            stoch_k = Decimal(
                str(self.indicator_values["stoch_osc_vals"]["k"].iloc[-1])
            )
            stoch_d = Decimal(
                str(self.indicator_values["stoch_osc_vals"]["d"].iloc[-1])
            )
            if stoch_k < 20 and stoch_k > stoch_d:  # Oversold and K crossing above D
                signal_score += Decimal(
                    str(self.user_defined_weights["stochastic_oscillator"])
                )
                conditions_met.append("Stoch Oscillator Oversold Crossover")

        # Final check for Bullish signal
        if signal_score >= Decimal(str(self.config["signal_score_threshold"])):
            signal_type = SignalType.BUY
            # Calculate Stop Loss and Take Profit
            if self.atr_value > 0:
                stop_loss = current_price - (
                    Decimal(str(self.atr_value))
                    * Decimal(str(self.config["stop_loss_multiple"]))
                )
                take_profit = current_price + (
                    Decimal(str(self.atr_value))
                    * Decimal(str(self.config["take_profit_multiple"]))
                )

        # --- Bearish Signal Logic (similar structure) ---
        bearish_score = Decimal("0.0")
        bearish_conditions: list[str] = []

        if (
            self.config["indicators"].get("stoch_rsi")
            and self.indicator_values.get("stoch_rsi_vals") is not None
            and not self.indicator_values["stoch_rsi_vals"].empty
        ):
            stoch_rsi_k = Decimal(
                str(self.indicator_values["stoch_rsi_vals"]["k"].iloc[-1])
            )
            stoch_rsi_d = Decimal(
                str(self.indicator_values["stoch_rsi_vals"]["d"].iloc[-1])
            )
            if (
                stoch_rsi_k > self.config["stoch_rsi_overbought_threshold"]
                and stoch_rsi_k < stoch_rsi_d
            ):
                bearish_score += Decimal(str(self.user_defined_weights["stoch_rsi"]))
                bearish_conditions.append("Stoch RSI Overbought Crossover")

        if (
            self.config["indicators"].get("rsi")
            and self.indicator_values.get("rsi")
            and self.indicator_values["rsi"][-1] > 70
        ):
            bearish_score += Decimal(str(self.user_defined_weights["rsi"]))
            bearish_conditions.append("RSI Overbought")

        if (
            self.config["indicators"].get("mfi")
            and self.indicator_values.get("mfi")
            and self.indicator_values["mfi"][-1] > 80
        ):
            bearish_score += Decimal(str(self.user_defined_weights["mfi"]))
            bearish_conditions.append("MFI Overbought")

        if (
            self.config["indicators"].get("ema_alignment")
            and self.indicator_values.get("ema_alignment", 0.0) < 0
        ):
            bearish_score += Decimal(
                str(self.user_defined_weights["ema_alignment"])
            ) * Decimal(str(abs(self.indicator_values["ema_alignment"])))
            bearish_conditions.append("Bearish EMA Alignment")

        if (
            self.config["indicators"].get("divergence")
            and self.indicator_calc.detect_macd_divergence() == "bearish"
        ):
            bearish_score += Decimal(str(self.user_defined_weights["divergence"]))
            bearish_conditions.append("Bearish MACD Divergence")

        if self.indicator_values["order_book_walls"].get("bearish"):
            bearish_score += Decimal(
                str(self.config["order_book_resistance_confidence_boost"] / 10.0)
            )
            bearish_conditions.append("Bearish Order Book Wall")

        # Stochastic Oscillator Bearish Signal
        if (
            self.config["indicators"].get("stochastic_oscillator")
            and self.indicator_values.get("stoch_osc_vals") is not None
            and not self.indicator_values["stoch_osc_vals"].empty
        ):
            stoch_k = Decimal(
                str(self.indicator_values["stoch_osc_vals"]["k"].iloc[-1])
            )
            stoch_d = Decimal(
                str(self.indicator_values["stoch_osc_vals"]["d"].iloc[-1])
            )
            if stoch_k > 80 and stoch_k < stoch_d:  # Overbought and K crossing below D
                bearish_score += Decimal(
                    str(self.user_defined_weights["stochastic_oscillator"])
                )
                bearish_conditions.append("Stoch Oscillator Overbought Crossover")

        # Final check for Bearish signal (only if no bullish signal already)
        if signal_type == SignalType.HOLD and bearish_score >= Decimal(
            str(self.config["signal_score_threshold"])
        ):
            signal_type = SignalType.SELL
            signal_score = bearish_score  # Use bearish score if it's the chosen signal
            conditions_met = bearish_conditions  # Use bearish conditions

            # Calculate Stop Loss and Take Profit for sell signal
            if self.atr_value > 0:
                stop_loss = current_price + (
                    Decimal(str(self.atr_value))
                    * Decimal(str(self.config["stop_loss_multiple"]))
                )
                take_profit = current_price - (
                    Decimal(str(self.atr_value))
                    * Decimal(str(self.config["take_profit_multiple"]))
                )

        # Calculate risk/reward ratio
        risk_reward_ratio = None
        if stop_loss and take_profit and signal_type != SignalType.HOLD:
            if signal_type == SignalType.BUY:
                risk = float(current_price - stop_loss)
                reward = float(take_profit - current_price)
            else:  # SELL
                risk = float(stop_loss - current_price)
                reward = float(current_price - take_profit)

            risk_reward_ratio = reward / risk if risk > 0 else None

        return TradingSignal(
            signal_type=signal_type,
            confidence=float(signal_score),
            conditions_met=conditions_met,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=time.time(),
            symbol=self.symbol,
            timeframe=self.interval,
            risk_reward_ratio=risk_reward_ratio,
        )


# --- Signal History Tracker ---
class SignalHistoryTracker:
    """Tracks and analyzes signal history for performance evaluation."""

    def __init__(
        self, db_manager: DatabaseManager, config: dict, logger: logging.Logger
    ):
        self.db_manager = db_manager
        self.config = config
        self.logger = logger
        self.performance_calculator = PerformanceCalculator(db_manager)
        self.active_signals = {}  # signal_id -> SignalHistory

    def add_signal(self, signal: TradingSignal, entry_price: Decimal) -> int | None:
        """Add a new signal to the history."""
        signal_history = SignalHistory(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            signal_type=signal.signal_type,
            confidence=signal.confidence,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            market_regime=None,  # Would need to pass this in
        )

        signal_id = self.db_manager.save_signal(signal_history)
        if signal_id:
            self.active_signals[signal_id] = signal_history
            self.logger.info(f"{NEON_GREEN}Added signal {signal_id} to history{RESET}")

        return signal_id

    def update_signal(
        self, signal_id: int, exit_price: Decimal, exit_reason: str
    ) -> bool:
        """Update a signal with exit information."""
        if signal_id not in self.active_signals:
            self.logger.error(
                f"{NEON_RED}Signal {signal_id} not found in active signals{RESET}"
            )
            return False

        signal = self.active_signals[signal_id]

        # Calculate profit/loss
        if signal.signal_type == SignalType.BUY:
            profit_loss = exit_price - signal.entry_price
        else:  # SELL
            profit_loss = signal.entry_price - exit_price

        # Update in database
        success = self.db_manager.update_signal(
            signal_id, exit_price, profit_loss, exit_reason
        )

        if success:
            # Update local copy
            signal.exit_price = exit_price
            signal.profit_loss = profit_loss
            signal.exit_reason = exit_reason

            # Remove from active signals
            del self.active_signals[signal_id]

            self.logger.info(
                f"{NEON_GREEN}Updated signal {signal_id} with P&L: {float(profit_loss):.2f}{RESET}"
            )

            # Update performance metrics
            self.update_performance_metrics(signal.symbol, signal.timeframe)

        return success

    def update_performance_metrics(self, symbol: str, timeframe: str) -> None:
        """Update performance metrics for a symbol and timeframe."""
        metrics = self.performance_calculator.calculate_metrics(symbol, timeframe)
        self.db_manager.save_performance_metrics(metrics, symbol, timeframe)

        self.logger.info(
            f"{NEON_BLUE}Updated performance metrics for {symbol} {timeframe}:{RESET}"
        )
        self.logger.info(f"  Win Rate: {metrics.win_rate:.2%}")
        self.logger.info(f"  Profit Factor: {metrics.profit_factor:.2f}")
        self.logger.info(f"  Net Profit: {float(metrics.net_profit):.2f}")
        self.logger.info(f"  Max Drawdown: {metrics.max_drawdown:.2%}")

    def check_exit_conditions(
        self, current_price: Decimal, symbol: str, timeframe: str
    ) -> list[tuple[int, str]]:
        """Check if any active signals should be exited."""
        signals_to_exit = []

        for signal_id, signal in self.active_signals.items():
            if signal.symbol != symbol or signal.timeframe != timeframe:
                continue

            exit_reason = None

            # Check stop loss
            if signal.stop_loss and (
                (
                    signal.signal_type == SignalType.BUY
                    and current_price <= signal.stop_loss
                )
                or (
                    signal.signal_type == SignalType.SELL
                    and current_price >= signal.stop_loss
                )
            ):
                exit_reason = "Stop Loss"

            # Check take profit
            elif signal.take_profit and (
                (
                    signal.signal_type == SignalType.BUY
                    and current_price >= signal.take_profit
                )
                or (
                    signal.signal_type == SignalType.SELL
                    and current_price <= signal.take_profit
                )
            ):
                exit_reason = "Take Profit"

            # Check trailing stop if enabled
            elif self.config.get("trailing_stop_loss", {}).get("enabled", False):
                # This would require tracking the highest/lowest price since entry
                # For simplicity, we'll skip this implementation
                pass

            if exit_reason:
                signals_to_exit.append((signal_id, exit_reason))

        return signals_to_exit


# --- Backtesting Engine ---
class BacktestingEngine:
    """Engine for backtesting trading strategies."""

    def __init__(self, api_client: APIClient, config: dict, logger: logging.Logger):
        self.api_client = api_client
        self.config = config
        self.logger = logger
        self.backtest_config = config.get("backtesting", {})
        self.db_manager = DatabaseManager(
            config.get("database", {}).get("path", DATABASE_FILE)
        )
        self.signal_tracker = SignalHistoryTracker(self.db_manager, config, logger)

    def run_backtest(
        self, symbol: str, timeframe: str, start_date: str, end_date: str
    ) -> PerformanceMetrics:
        """Run a backtest for the specified symbol and timeframe."""
        self.logger.info(
            f"{NEON_BLUE}Starting backtest for {symbol} {timeframe} from {start_date} to {end_date}{RESET}"
        )

        # Convert dates to timestamps
        start_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        end_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

        # Fetch historical data
        df = self.api_client.fetch_klines(symbol, timeframe, limit=1000)
        if df.empty:
            self.logger.error(f"{NEON_RED}No data available for backtesting{RESET}")
            return PerformanceMetrics()

        # Filter data to the specified date range
        df = df[
            (df["start_time"].astype(int) / 1000 >= start_timestamp)
            & (df["start_time"].astype(int) / 1000 <= end_timestamp)
        ]

        if df.empty:
            self.logger.error(
                f"{NEON_RED}No data available for the specified date range{RESET}"
            )
            return PerformanceMetrics()

        # Initialize backtest variables
        initial_balance = Decimal(
            str(self.backtest_config.get("initial_balance", 10000))
        )
        current_balance = initial_balance
        position = None  # (signal_type, entry_price, quantity)

        # Process each candle
        for i, (_, row) in enumerate(df.iterrows()):
            current_price = Decimal(str(row["close"]))
            timestamp = row["start_time"]

            # Skip the first few candles to ensure we have enough data for indicators
            if i < 50:
                continue

            # Get data up to this point
            current_df = df.iloc[: i + 1]

            # Create analyzer
            analyzer = TradingAnalyzer(
                current_df, self.config, self.logger, symbol, timeframe
            )

            # Generate signal
            signal = analyzer.generate_trading_signal(current_price)

            # Check if we need to exit a position
            if position:
                signal_type, entry_price, quantity = position

                # Check stop loss
                if signal.stop_loss and (
                    (
                        signal_type == SignalType.BUY
                        and current_price <= signal.stop_loss
                    )
                    or (
                        signal_type == SignalType.SELL
                        and current_price >= signal.stop_loss
                    )
                ):
                    # Exit position
                    if signal_type == SignalType.BUY:
                        profit_loss = (current_price - entry_price) * quantity
                    else:
                        profit_loss = (entry_price - current_price) * quantity

                    current_balance += profit_loss

                    # Record the trade
                    signal_history = SignalHistory(
                        timestamp=timestamp.timestamp()
                        if hasattr(timestamp, "timestamp")
                        else time.time(),
                        symbol=symbol,
                        timeframe=timeframe,
                        signal_type=signal_type,
                        confidence=0,  # Not relevant for backtest
                        entry_price=entry_price,
                        exit_price=current_price,
                        profit_loss=profit_loss,
                        exit_reason="Stop Loss",
                    )
                    self.db_manager.save_signal(signal_history)

                    position = None
                    self.logger.info(
                        f"{NEON_YELLOW}Exited position at {current_price} (Stop Loss), P&L: {float(profit_loss):.2f}{RESET}"
                    )

                # Check take profit
                elif signal.take_profit and (
                    (
                        signal_type == SignalType.BUY
                        and current_price >= signal.take_profit
                    )
                    or (
                        signal_type == SignalType.SELL
                        and current_price <= signal.take_profit
                    )
                ):
                    # Exit position
                    if signal_type == SignalType.BUY:
                        profit_loss = (current_price - entry_price) * quantity
                    else:
                        profit_loss = (entry_price - current_price) * quantity

                    current_balance += profit_loss

                    # Record the trade
                    signal_history = SignalHistory(
                        timestamp=timestamp.timestamp()
                        if hasattr(timestamp, "timestamp")
                        else time.time(),
                        symbol=symbol,
                        timeframe=timeframe,
                        signal_type=signal_type,
                        confidence=0,  # Not relevant for backtest
                        entry_price=entry_price,
                        exit_price=current_price,
                        profit_loss=profit_loss,
                        exit_reason="Take Profit",
                    )
                    self.db_manager.save_signal(signal_history)

                    position = None
                    self.logger.info(
                        f"{NEON_YELLOW}Exited position at {current_price} (Take Profit), P&L: {float(profit_loss):.2f}{RESET}"
                    )

            # Enter a new position if we have a signal and no open position
            elif signal.signal_type != SignalType.HOLD and not position:
                # Calculate position size
                risk_per_trade = Decimal(
                    str(
                        self.config.get("risk_management", {}).get(
                            "risk_per_trade", 0.02
                        )
                    )
                )
                risk_amount = current_balance * risk_per_trade

                if signal.stop_loss:
                    if signal.signal_type == SignalType.BUY:
                        risk_per_unit = current_price - signal.stop_loss
                    else:
                        risk_per_unit = signal.stop_loss - current_price

                    if risk_per_unit > 0:
                        quantity = risk_amount / risk_per_unit
                        position = (signal.signal_type, current_price, quantity)

                        self.logger.info(
                            f"{NEON_GREEN}Entered {signal.signal_type.value} position at {current_price}, quantity: {float(quantity):.4f}{RESET}"
                        )

        # Calculate performance metrics
        metrics = self.performance_calculator.calculate_metrics(symbol, timeframe)
        metrics.total_profit = current_balance - initial_balance
        metrics.net_profit = current_balance - initial_balance

        self.logger.info(
            f"{NEON_BLUE}Backtest completed for {symbol} {timeframe}{RESET}"
        )
        self.logger.info(f"  Initial Balance: {float(initial_balance):.2f}")
        self.logger.info(f"  Final Balance: {float(current_balance):.2f}")
        self.logger.info(f"  Net Profit: {float(metrics.net_profit):.2f}")
        self.logger.info(f"  Win Rate: {metrics.win_rate:.2%}")
        self.logger.info(f"  Profit Factor: {metrics.profit_factor:.2f}")
        self.logger.info(f"  Max Drawdown: {metrics.max_drawdown:.2%}")

        return metrics


# --- Interpret Indicator Function ---
def interpret_indicator(
    logger: logging.Logger,
    indicator_name: str,
    values: list[float] | float | dict[str, Any],
) -> str | None:
    """Provides a human-readable interpretation of indicator values."""
    if (
        values is None
        or (isinstance(values, list) and not values)
        or (isinstance(values, pd.DataFrame) and values.empty)
    ):
        return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} No data available."

    try:
        # Convert single float values to list for consistent indexing if needed
        if isinstance(values, (float, int)):
            values = [values]
        elif isinstance(values, dict):  # For 'mom' which is a dict
            if indicator_name == "mom":
                trend = values.get("trend", "N/A")
                strength = values.get("strength", 0.0)
                return f"{NEON_PURPLE}Momentum Trend:{RESET} {trend} (Strength: {strength:.2f})"
            return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} Dictionary format not specifically interpreted."
        elif isinstance(
            values, pd.DataFrame
        ):  # For stoch_rsi_vals which is a DataFrame
            if indicator_name == "stoch_rsi_vals":
                # Stoch RSI interpretation is handled directly in analyze function
                return None
            return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} DataFrame format not specifically interpreted."

        # Interpret based on indicator name
        last_value = (
            values[-1]
            if isinstance(values, list) and values
            else values[0]
            if isinstance(values, list)
            else values
        )  # Handles single value lists too

        if indicator_name == "rsi":
            if last_value > 70:
                return f"{NEON_RED}RSI:{RESET} Overbought ({last_value:.2f})"
            if last_value < 30:
                return f"{NEON_GREEN}RSI:{RESET} Oversold ({last_value:.2f})"
            return f"{NEON_YELLOW}RSI:{RESET} Neutral ({last_value:.2f})"

        if indicator_name == "mfi":
            if last_value > 80:
                return f"{NEON_RED}MFI:{RESET} Overbought ({last_value:.2f})"
            if last_value < 20:
                return f"{NEON_GREEN}MFI:{RESET} Oversold ({last_value:.2f})"
            return f"{NEON_YELLOW}MFI:{RESET} Neutral ({last_value:.2f})"

        if indicator_name == "cci":
            if last_value > 100:
                return f"{NEON_RED}CCI:{RESET} Overbought ({last_value:.2f})"
            if last_value < -100:
                return f"{NEON_GREEN}CCI:{RESET} Oversold ({last_value:.2f})"
            return f"{NEON_YELLOW}CCI:{RESET} Neutral ({last_value:.2f})"

        if indicator_name == "wr":
            if last_value < -80:
                return f"{NEON_GREEN}Williams %R:{RESET} Oversold ({last_value:.2f})"
            if last_value > -20:
                return f"{NEON_RED}Williams %R:{RESET} Overbought ({last_value:.2f})"
            return f"{NEON_YELLOW}Williams %R:{RESET} Neutral ({last_value:.2f})"

        if indicator_name == "adx":
            if last_value > 25:
                return f"{NEON_GREEN}ADX:{RESET} Trending ({last_value:.2f})"
            return f"{NEON_YELLOW}ADX:{RESET} Ranging ({last_value:.2f})"

        if indicator_name == "obv":
            if len(values) >= 2:
                return f"{NEON_BLUE}OBV:{RESET} {'Bullish' if values[-1] > values[-2] else 'Bearish' if values[-1] < values[-2] else 'Neutral'}"
            return f"{NEON_BLUE}OBV:{RESET} {last_value:.2f} (Insufficient history for trend)"

        if indicator_name == "adi":
            if len(values) >= 2:
                return f"{NEON_BLUE}ADI:{RESET} {'Accumulation' if values[-1] > values[-2] else 'Distribution' if values[-1] < values[-2] else 'Neutral'}"
            return f"{NEON_BLUE}ADI:{RESET} {last_value:.2f} (Insufficient history for trend)"

        if indicator_name == "sma_10":
            return f"{NEON_YELLOW}SMA (10):{RESET} {last_value:.2f}"

        if indicator_name == "psar":
            return f"{NEON_BLUE}PSAR:{RESET} {last_value:.4f} (Last Value)"

        if indicator_name == "fve":
            return f"{NEON_BLUE}FVE:{RESET} {last_value:.2f} (Last Value)"

        if indicator_name == "macd":
            # values for MACD are [macd_line, signal_line, histogram]
            if len(values[-1]) == 3:
                macd_line, signal_line, histogram = (
                    values[-1][0],
                    values[-1][1],
                    values[-1][2],
                )
                return f"{NEON_GREEN}MACD:{RESET} MACD={macd_line:.2f}, Signal={signal_line:.2f}, Histogram={histogram:.2f}"
            return f"{NEON_RED}MACD:{RESET} Calculation issue."

        return f"{NEON_YELLOW}{indicator_name.upper()}:{RESET} No specific interpretation available."

    except (TypeError, IndexError, KeyError, ValueError) as e:
        logger.error(
            f"{NEON_RED}Error interpreting {indicator_name}: {e}. Values: {values}{RESET}"
        )
        return f"{NEON_RED}{indicator_name.upper()}:{RESET} Interpretation error."


# --- Main Function ---
def main():
    """Main function to run the trading analysis bot.
    Handles user input, data fetching, analysis, and signal generation loop.
    """
    if not API_KEY or not API_SECRET:
        logger.error(
            f"{NEON_RED}BYBIT_API_KEY and BYBIT_API_SECRET must be set in your .env file.{RESET}"
        )
        return

    # Setup database
    setup_database()

    # Initialize components
    db_manager = DatabaseManager(CONFIG.get("database", {}).get("path", DATABASE_FILE))
    notification_system = NotificationSystem(CONFIG)
    risk_manager = RiskManager(CONFIG, logger)
    signal_tracker = SignalHistoryTracker(db_manager, CONFIG, logger)

    # Get user input
    symbol_input = (
        input(f"{NEON_BLUE}Enter trading symbol (e.g., BTCUSDT): {RESET}")
        .upper()
        .strip()
    )
    symbol = symbol_input if symbol_input else "BTCUSDT"

    interval_input = input(
        f"{NEON_BLUE}Enter timeframe (e.g., {', '.join(VALID_INTERVALS)} or press Enter for default {CONFIG['interval']}): {RESET}"
    ).strip()
    interval = (
        interval_input
        if interval_input and interval_input in VALID_INTERVALS
        else CONFIG["interval"]
    )

    # Check if backtesting is enabled
    if CONFIG.get("backtesting", {}).get("enabled", False):
        start_date = CONFIG.get("backtesting", {}).get("start_date", "")
        end_date = CONFIG.get("backtesting", {}).get("end_date", "")

        if not start_date or not end_date:
            start_date = input(
                f"{NEON_BLUE}Enter start date (YYYY-MM-DD): {RESET}"
            ).strip()
            end_date = input(f"{NEON_BLUE}Enter end date (YYYY-MM-DD): {RESET}").strip()

        # Run backtest
        api_client = APIClient(API_KEY, API_SECRET, BASE_URL, logger)
        backtesting_engine = BacktestingEngine(api_client, CONFIG, logger)
        backtesting_engine.run_backtest(symbol, interval, start_date, end_date)
        return

    # Setup a dedicated logger for this symbol's activities
    symbol_logger = setup_custom_logger(symbol)
    symbol_logger.info(
        f"{NEON_BLUE}Starting analysis for {symbol} with interval {interval}{RESET}"
    )

    # Initialize API client
    api_client = APIClient(API_KEY, API_SECRET, BASE_URL, symbol_logger)

    # Initialize multi-timeframe analyzer if enabled
    multi_tf_analyzer = None
    if CONFIG.get("multi_timeframe", {}).get("enabled", False):
        multi_tf_analyzer = MultiTimeframeAnalyzer(api_client, CONFIG, symbol_logger)

    # Initialize account balance
    account_balance = Decimal(
        str(CONFIG.get("risk_management", {}).get("portfolio_value", 10000))
    )
    daily_loss = Decimal("0")
    peak_balance = account_balance

    last_signal_time = 0.0  # Tracks the last time a signal was triggered for cooldown
    last_order_book_fetch_time = 0.0  # Tracks last order book fetch time for debouncing
    last_db_backup_time = time.time()

    # Main loop
    while True:
        try:
            # Check circuit breaker
            if risk_manager.check_circuit_breaker():
                symbol_logger.warning(
                    f"{NEON_RED}Circuit breaker is active. Pausing trading.{RESET}"
                )
                time.sleep(CONFIG["analysis_interval"])
                continue

            # Fetch current price
            current_price = api_client.fetch_current_price(symbol)
            if current_price is None:
                symbol_logger.error(
                    f"{NEON_RED}Failed to fetch current price for {symbol}. Skipping cycle.{RESET}"
                )
                time.sleep(CONFIG["retry_delay"])
                continue

            # Fetch kline data
            df = api_client.fetch_klines(symbol, interval, limit=200)
            if df.empty:
                symbol_logger.error(
                    f"{NEON_RED}Failed to fetch Kline data for {symbol}. Skipping cycle.{RESET}"
                )
                time.sleep(CONFIG["retry_delay"])
                continue

            # Validate data
            data_validator = DataValidator(CONFIG, symbol_logger)
            if not data_validator.validate_dataframe(df, symbol, interval):
                symbol_logger.error(
                    f"{NEON_RED}Data validation failed for {symbol} {interval}. Skipping cycle.{RESET}"
                )
                time.sleep(CONFIG["retry_delay"])
                continue

            # Debounce order book fetching to reduce API calls
            order_book_data = None
            if (
                time.time() - last_order_book_fetch_time
                >= CONFIG["order_book_debounce_s"]
            ):
                order_book_data = api_client.fetch_order_book(
                    symbol, limit=CONFIG["order_book_depth_to_check"]
                )
                last_order_book_fetch_time = time.time()
            else:
                symbol_logger.debug(
                    f"{NEON_YELLOW}Order book fetch debounced. Next fetch in {CONFIG['order_book_debounce_s'] - (time.time() - last_order_book_fetch_time):.1f}s{RESET}"
                )

            # Generate trading signal
            if multi_tf_analyzer:
                # Use multi-timeframe analysis
                trading_signal = multi_tf_analyzer.generate_consensus_signal(symbol)
            else:
                # Use single timeframe analysis
                analyzer = TradingAnalyzer(df, CONFIG, symbol_logger, symbol, interval)
                timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S %Z")

                # Perform analysis and log the current state of indicators
                analyzer.analyze(current_price, timestamp, order_book_data)

                # Generate trading signal based on the analysis
                trading_signal = analyzer.generate_trading_signal(current_price)

            # Check for exit conditions on active signals
            signals_to_exit = signal_tracker.check_exit_conditions(
                current_price, symbol, interval
            )
            for signal_id, exit_reason in signals_to_exit:
                signal_tracker.update_signal(signal_id, current_price, exit_reason)

                # Update risk manager with trade result
                signal = signal_tracker.active_signals.get(signal_id)
                if signal and signal.profit_loss:
                    risk_manager.update_trade_result(signal.profit_loss)
                    daily_loss += signal.profit_loss

                    # Update account balance
                    account_balance += signal.profit_loss

                    # Check daily loss limit
                    if risk_manager.check_daily_loss_limit(daily_loss, account_balance):
                        symbol_logger.error(
                            f"{NEON_RED}Daily loss limit reached. Stopping trading for today.{RESET}"
                        )
                        return

                    # Check drawdown limit
                    current_drawdown = float(
                        (peak_balance - account_balance) / peak_balance
                    )
                    if risk_manager.check_drawdown_limit(current_drawdown):
                        symbol_logger.error(
                            f"{NEON_RED}Maximum drawdown reached. Stopping trading.{RESET}"
                        )
                        return

                    # Update peak balance
                    peak_balance = max(peak_balance, account_balance)

            # Process new signal
            current_time_seconds = time.time()
            if trading_signal.signal_type != SignalType.HOLD and (
                current_time_seconds - last_signal_time >= CONFIG["signal_cooldown_s"]
            ):
                symbol_logger.info(
                    f"\n{NEON_PURPLE}--- TRADING SIGNAL TRIGGERED ---{RESET}"
                )
                symbol_logger.info(
                    f"{NEON_BLUE}Signal:{RESET} {trading_signal.signal_type.value.upper()} (Confidence: {trading_signal.confidence:.2f})"
                )
                symbol_logger.info(
                    f"{NEON_BLUE}Conditions Met:{RESET} {', '.join(trading_signal.conditions_met) if trading_signal.conditions_met else 'None'}"
                )

                if trading_signal.stop_loss and trading_signal.take_profit:
                    symbol_logger.info(
                        f"{NEON_GREEN}Suggested Stop Loss:{RESET} {trading_signal.stop_loss:.5f}"
                    )
                    symbol_logger.info(
                        f"{NEON_GREEN}Suggested Take Profit:{RESET} {trading_signal.take_profit:.5f}"
                    )

                    if trading_signal.risk_reward_ratio:
                        symbol_logger.info(
                            f"{NEON_BLUE}Risk/Reward Ratio:{RESET} {trading_signal.risk_reward_ratio:.2f}"
                        )

                # Calculate position size
                if trading_signal.stop_loss:
                    position_size = risk_manager.calculate_position_size(
                        current_price, trading_signal.stop_loss, account_balance
                    )
                    trading_signal.position_size = position_size
                    symbol_logger.info(
                        f"{NEON_BLUE}Position Size:{RESET} {position_size:.4f}"
                    )

                # Add signal to history
                signal_id = signal_tracker.add_signal(trading_signal, current_price)

                # Send notification
                if CONFIG.get("notifications", {}).get("enabled", False):
                    notification_system.send_signal_notification(trading_signal)

                symbol_logger.info(
                    f"{NEON_YELLOW}--- Placeholder: Order placement logic would be here for {trading_signal.signal_type.value.upper()} signal ---{RESET}"
                )
                last_signal_time = current_time_seconds  # Update last signal time

            # Backup database periodically
            if CONFIG.get("database", {}).get("backup_enabled", True):
                backup_interval = (
                    CONFIG.get("database", {}).get("backup_interval_hours", 24) * 3600
                )
                if time.time() - last_db_backup_time >= backup_interval:
                    backup_path = f"{DATABASE_FILE}.bak_{int(time.time())}"
                    if db_manager.backup_database(backup_path):
                        last_db_backup_time = time.time()

            time.sleep(CONFIG["analysis_interval"])

        except requests.exceptions.RequestException as e:
            symbol_logger.error(
                f"{NEON_RED}Network or API communication error: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}"
            )
            time.sleep(CONFIG["retry_delay"])

        except KeyboardInterrupt:
            symbol_logger.info(f"{NEON_YELLOW}Analysis stopped by user.{RESET}")
            break

        except Exception as e:
            symbol_logger.exception(
                f"{NEON_RED}An unexpected error occurred: {e}. Retrying in {CONFIG['retry_delay']} seconds...{RESET}"
            )
            time.sleep(CONFIG["retry_delay"])


if __name__ == "__main__":
    main()
