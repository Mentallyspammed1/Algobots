import asyncio
import logging
import os
import pickle
import sys
from abc import ABC
from abc import abstractmethod
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from decimal import ROUND_DOWN
from decimal import Context
from decimal import Decimal
from decimal import getcontext
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pybit.exceptions import FailedRequestError
from pybit.unified_trading import HTTP
from pybit.unified_trading import WebSocket

# --- INITIAL SETUP ---

# Set decimal precision for accurate financial calculations
# Using a higher precision context to avoid intermediate rounding errors
DECIMAL_CONTEXT = Context(prec=50)
getcontext().prec = 28  # Default precision for display/storage

# Load environment variables from .env file
load_dotenv()


# --- HELPER FOR DECIMAL CONVERSION ---
def to_decimal(value: Any) -> Decimal:
    """Converts a value to a Decimal, handling None and ensuring DECIMAL_CONTEXT."""
    if value is None:
        return Decimal("0", DECIMAL_CONTEXT)  # Or raise error, depending on context
    return Decimal(str(value), DECIMAL_CONTEXT)


# --- LOGGING CONFIGURATION ---


# ANSI color codes for NEW "neon" style logging
class NeonColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"

    # Bright/Intense colors for a more "neon" feel
    BRIGHT_GREEN = "\033[92m"  # INFO
    BRIGHT_YELLOW = "\033[93m"  # WARNING
    BRIGHT_RED = "\033[91m"  # ERROR
    BRIGHT_MAGENTA = "\033[95m"  # CRITICAL (vibrant pink/purple)
    BRIGHT_CYAN = "\033[96m"  # DEBUG
    BRIGHT_BLUE = "\033[94m"  # General/Other
    BRIGHT_WHITE = "\033[97m"  # Default/Subtle


class NeonFormatter(logging.Formatter):
    """A custom formatter for neon-style colored console output with new scheme."""

    FORMATS = {
        logging.DEBUG: NeonColors.BRIGHT_CYAN
        + "%(asctime)s - "
        + NeonColors.BOLD
        + "%(levelname)s"
        + NeonColors.RESET
        + NeonColors.BRIGHT_CYAN
        + " - %(name)s - %(funcName)s:%(lineno)d - %(message)s"
        + NeonColors.RESET,
        logging.INFO: NeonColors.BRIGHT_GREEN
        + "%(asctime)s - "
        + NeonColors.BOLD
        + "%(levelname)s"
        + NeonColors.RESET
        + NeonColors.BRIGHT_GREEN
        + " - %(message)s"
        + NeonColors.RESET,
        logging.WARNING: NeonColors.BRIGHT_YELLOW
        + "%(asctime)s - "
        + NeonColors.BOLD
        + "%(levelname)s"
        + NeonColors.RESET
        + NeonColors.BRIGHT_YELLOW
        + " - %(message)s"
        + NeonColors.RESET,
        logging.ERROR: NeonColors.BRIGHT_RED
        + "%(asctime)s - "
        + NeonColors.BOLD
        + "%(levelname)s"
        + NeonColors.RESET
        + NeonColors.BRIGHT_RED
        + " - %(funcName)s:%(lineno)d - %(message)s"
        + NeonColors.RESET,
        logging.CRITICAL: NeonColors.BOLD
        + NeonColors.BRIGHT_MAGENTA
        + "%(asctime)s - "
        + NeonColors.BOLD
        + "%(levelname)s"
        + NeonColors.RESET
        + NeonColors.BRIGHT_MAGENTA
        + " - %(funcName)s:%(lineno)d - %(message)s"
        + NeonColors.RESET,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        # We need to re-create the formatter each time because the format string changes based on level
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup_logging():
    """Setup comprehensive logging configuration with neon console output."""
    log = logging.getLogger()
    log.setLevel(logging.INFO)  # Default level, can be overridden per handler

    # Formatters
    detailed_formatter = logging.Formatter(  # For file logs (no colors)
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    neon_formatter = NeonFormatter()  # For console logs (with colors)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(neon_formatter)  # Use neon formatter for console

    # File Handler (for all logs, no colors)
    file_handler = RotatingFileHandler(
        "supertrend_bot.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)  # Log all levels to file
    file_handler.setFormatter(detailed_formatter)

    log.addHandler(console_handler)
    log.addHandler(file_handler)

    return log


logger = setup_logging()


# =====================================================================
# ENUMS AND DATACLASSES
# =====================================================================


class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class MarketInfo:
    """Stores market information including precision settings for a specific symbol."""

    symbol: str
    tick_size: Decimal
    lot_size: Decimal

    def format_price(self, price: float) -> str:
        """Formats a price to the market's tick size precision."""
        return str(to_decimal(price).quantize(self.tick_size, rounding=ROUND_DOWN))

    def format_quantity(self, quantity: float) -> str:
        """Formats a quantity to the market's lot size precision."""
        return str(to_decimal(quantity).quantize(self.lot_size, rounding=ROUND_DOWN))


@dataclass
class Position:
    """Represents an open position for a specific symbol."""

    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal
    leverage: int
    entry_signal_price: Decimal | None = (
        None  # Price at which strategy generated the signal to enter
    )
    initial_stop_loss: Decimal | None = (
        None  # Original strategy SL for risk calculation
    )
    trailing_stop_loss: Decimal | None = (
        None  # Current active trailing stop loss on exchange
    )
    take_profit: Decimal | None = None  # Current active take profit on exchange


@dataclass
class StrategySignal:
    """Standardized object for strategy signals."""

    action: str  # 'BUY', 'SELL', 'CLOSE', 'HOLD'
    symbol: str
    strength: float = 1.0
    stop_loss: float | None = None  # Suggested initial stop loss price
    take_profit: float | None = None  # Suggested initial take profit price
    signal_price: float | None = (
        None  # Price at which the signal was generated (current close)
    )
    metadata: dict = field(default_factory=dict)


@dataclass
class Config:
    """Trading bot configuration."""

    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = False

    # Trading Parameters (Multi-symbol support)
    symbols: list[str] = field(
        default_factory=lambda: ["XLMUSDT", "LINKUSDT"]
    )  # List of symbols to trade
    category: str = (
        "linear"  # "linear" for USDT Perpetuals, "inverse" for Inverse Perpetuals, etc.
    )
    min_order_value_usdt: float = 5.0  # Minimum order value in USDT for Bybit (absolute minimum might be higher on Bybit)

    # Risk Management (Tuned for Scalping)
    risk_per_trade_pct: float = (
        0.005  # 0.5% of equity risked per trade (smaller for scalping)
    )
    leverage: int = 20  # Higher leverage for scalping to magnify small moves

    # WebSocket settings
    reconnect_attempts: int = 5

    # Strategy Parameters (Tuned for Scalping)
    strategy_name: str = "EhlersSupertrendCross"  # Configures strategy for all symbols, or could be per-symbol
    timeframe: str = "1"  # Shorter timeframe for scalping (e.g., "1", "3", "5")
    lookback_periods: int = (
        200  # Reduced lookback to minimize data processing per candle
    )

    # Common Strategy Params
    strategy_params: dict[str, Any] = field(
        default_factory=lambda: {
            # Classic Supertrend Specific Params (if used)
            "supertrend_period": 7,  # Shorter period
            "supertrend_multiplier": 2.5,  # Tighter multiplier
            "atr_period": 10,  # Shorter ATR period
            # Ehlers Supertrend Specific Params (Scalping Tuned)
            "ehlers_fast_supertrend_period": 3,  # Very fast
            "ehlers_fast_supertrend_multiplier": 1.0,  # Very tight
            "ehlers_slow_supertrend_period": 7,  # Still relatively fast
            "ehlers_slow_supertrend_multiplier": 2.0,  # Tighter
            "ehlers_filter_alpha": 0.5,  # Increased alpha for less smoothing / more responsiveness
            "ehlers_filter_poles": 1,  # Reduced poles for less lag (more EMA-like)
            # Advanced Entry/Exit & Risk Management (Scalping Tuned)
            "signal_confirmation_candles": 0,  # Immediate entry for scalping (0 for no confirmation)
            "take_profit_atr_multiplier": 0.75,  # Smaller TP targets
            "trailing_stop_loss_atr_multiplier": 0.6,  # Tighter trailing stops
            "trailing_stop_loss_activation_atr_multiplier": 0.3,  # Activate trailing SL very quickly
            "break_even_profit_atr_multiplier": 0.2,  # Move to break-even almost immediately (within this ATR range)
        }
    )


# =====================================================================
# STRATEGY INTERFACE & IMPLEMENTATION
# =====================================================================


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    def __init__(self, symbol: str, config: Config):
        self.symbol = symbol
        self.config = config
        self.indicators = {}  # Stores pandas DataFrames with calculated indicators per timeframe for *this* symbol
        self.primary_timeframe = config.timeframe
        self.last_signal: StrategySignal | None = None
        self.signal_confirmed = False
        self.signal_candle_time: datetime | None = None

        # Determine strategy-specific ATR period for consistent access
        self.atr_period = self.config.strategy_params.get("atr_period", 14)

    @abstractmethod
    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculate technical indicators for the strategy.
        Updates self.indicators with the results.
        `data` parameter is the raw market data for this symbol (timeframe -> DataFrame).
        """

    @abstractmethod
    async def generate_signal(self) -> StrategySignal | None:
        """Generate a trading signal based on indicator data stored in self.indicators.
        Assumes calculate_indicators has already been called and self.indicators is up-to-date.
        """

    async def _confirm_signal(self, current_candle_time: datetime) -> bool:
        """Confirms a signal after a specified number of candles.
        Returns True if confirmed, False otherwise.
        """
        confirmation_candles_needed = self.config.strategy_params.get(
            "signal_confirmation_candles", 1
        )
        if confirmation_candles_needed == 0:  # No confirmation needed, immediate action
            self.signal_confirmed = True
            return True

        if self.last_signal and not self.signal_confirmed and self.signal_candle_time:
            df = self.indicators.get(self.primary_timeframe)
            if df is None or df.empty or self.signal_candle_time not in df.index:
                logger.debug(
                    f"[{self.symbol}] DataFrame for {self.primary_timeframe} is empty or signal_candle_time {self.signal_candle_time} not in index for confirmation."
                )
                return False

            try:
                # Find the index of the signal candle and current candle
                # 'bfill' ensures we get an index even if the time isn't exact,
                # picking the next available candle.
                signal_idx = df.index.get_loc(self.signal_candle_time, method="bfill")
                current_idx = df.index.get_loc(current_candle_time, method="bfill")
            except KeyError:
                logger.warning(
                    f"[{self.symbol}] Could not find signal_candle_time {self.signal_candle_time} or current_candle_time {current_candle_time} in DataFrame index for signal confirmation."
                )
                return False

            if current_idx - signal_idx >= confirmation_candles_needed:
                self.signal_confirmed = True
                logger.info(
                    f"[{self.symbol}] Signal for {self.last_signal.action} confirmed after {confirmation_candles_needed} candles."
                )
                return True
        return False  # Still waiting for confirmation or conditions not met


class SupertrendStrategy(BaseStrategy):
    """A strategy based on the Classic Supertrend indicator."""

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.supertrend_period = self.config.strategy_params.get(
            "supertrend_period", 10
        )
        self.supertrend_multiplier = self.config.strategy_params.get(
            "supertrend_multiplier", 3.0
        )
        # atr_period is inherited from BaseStrategy

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculates ATR and Supertrend. Updates self.indicators."""
        df = data.get(
            self.primary_timeframe
        )  # Get raw market data for this strategy's symbol and timeframe
        min_data_needed = max(self.supertrend_period, self.atr_period)
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(
                f"[{self.symbol}] Insufficient data for Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles)."
            )
            return

        df_copy = df.copy()  # Work on a copy to prevent SettingWithCopyWarning

        # Calculate ATR
        high_low = df_copy["high"] - df_copy["low"]
        high_close = np.abs(df_copy["high"] - df_copy["close"].shift())
        low_close = np.abs(df_copy["low"] - df_copy["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df_copy["atr"] = tr.ewm(span=self.atr_period, adjust=False).mean()

        # Calculate Supertrend
        hl2 = (df_copy["high"] + df_copy["low"]) / 2
        df_copy["upperband"] = hl2 + (self.supertrend_multiplier * df_copy["atr"])
        df_copy["lowerband"] = hl2 - (self.supertrend_multiplier * df_copy["atr"])
        df_copy["in_uptrend"] = True  # Initialize, will be set correctly in loop

        # Core Supertrend logic, corrected for trailing behavior
        df_copy["supertrend_line"] = np.nan  # Initialize Supertrend line
        for current in range(1, len(df_copy.index)):
            previous = current - 1

            # If current close crosses above previous upperband, trend flips up
            if (
                df_copy.loc[df_copy.index[current], "close"]
                > df_copy.loc[df_copy.index[previous], "upperband"]
            ):
                df_copy.loc[df_copy.index[current], "in_uptrend"] = True
            # If current close crosses below previous lowerband, trend flips down
            elif (
                df_copy.loc[df_copy.index[current], "close"]
                < df_copy.loc[df_copy.index[previous], "lowerband"]
            ):
                df_copy.loc[df_copy.index[current], "in_uptrend"] = False
            # Otherwise, maintain previous trend direction
            else:
                df_copy.loc[df_copy.index[current], "in_uptrend"] = df_copy.loc[
                    df_copy.index[previous], "in_uptrend"
                ]

            # Now, set the Supertrend line based on trend and previous Supertrend value
            if df_copy.loc[df_copy.index[current], "in_uptrend"]:
                # If in uptrend, Supertrend is max of current lowerband and previous Supertrend (if still in uptrend)
                # It trails by staying at or above previous ST, or following current lowerband
                prev_supertrend = (
                    df_copy.loc[df_copy.index[previous], "supertrend_line"]
                    if not np.isnan(
                        df_copy.loc[df_copy.index[previous], "supertrend_line"]
                    )
                    else df_copy.loc[df_copy.index[current], "lowerband"]
                )
                df_copy.loc[df_copy.index[current], "supertrend_line"] = max(
                    df_copy.loc[df_copy.index[current], "lowerband"], prev_supertrend
                )
            else:
                # If in downtrend, Supertrend is min of current upperband and previous Supertrend (if still in downtrend)
                # It trails by staying at or below previous ST, or following current upperband
                prev_supertrend = (
                    df_copy.loc[df_copy.index[previous], "supertrend_line"]
                    if not np.isnan(
                        df_copy.loc[df_copy.index[previous], "supertrend_line"]
                    )
                    else df_copy.loc[df_copy.index[current], "upperband"]
                )
                df_copy.loc[df_copy.index[current], "supertrend_line"] = min(
                    df_copy.loc[df_copy.index[current], "upperband"], prev_supertrend
                )

        df_copy["supertrend"] = df_copy["supertrend_line"]  # The final Supertrend value
        self.indicators[self.primary_timeframe] = (
            df_copy  # Store the processed DataFrame
        )

    async def generate_signal(self) -> StrategySignal | None:
        """Generate signal based on Supertrend crossover with confirmation."""
        df_indicators = self.indicators.get(self.primary_timeframe)
        if df_indicators is None or df_indicators.empty or len(df_indicators) < 2:
            logger.debug(
                f"[{self.symbol}] Insufficient indicator data for signal generation."
            )
            return None

        df_cleaned = df_indicators.dropna(
            subset=["supertrend", "atr", "in_uptrend"]
        ).copy()  # Include 'in_uptrend'
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug(
                f"[{self.symbol}] DataFrame too small after dropping NaNs for signal generation from indicators."
            )
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        if self.last_signal:
            if (self.last_signal.action == "BUY" and not current["in_uptrend"]) or (
                self.last_signal.action == "SELL" and current["in_uptrend"]
            ):
                logger.info(
                    f"[{self.symbol}] Trend changed opposite to pending signal ({self.last_signal.action}), resetting pending signal."
                )
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None

            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(
                        f"[{self.symbol}] Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}."
                    )
                    temp_signal = self.last_signal
                    self.last_signal = None
                    self.signal_confirmed = False
                    self.signal_candle_time = None
                    return temp_signal
                return None
            return None

        signal_to_generate = None
        if not previous["in_uptrend"] and current["in_uptrend"]:
            signal_to_generate = StrategySignal(
                action="BUY",
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(
                    current["supertrend"]
                ),  # Current supertrend is the new SL
                signal_price=float(current["close"]),
                metadata={"reason": "Supertrend flipped to UP"},
            )
        elif previous["in_uptrend"] and not current["in_uptrend"]:
            signal_to_generate = StrategySignal(
                action="SELL",
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(
                    current["supertrend"]
                ),  # Current supertrend is the new SL
                signal_price=float(current["close"]),
                metadata={"reason": "Supertrend flipped to DOWN"},
            )

        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(
                f"[{self.symbol}] PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}. Waiting for confirmation (0 for immediate)."
            )
            return None

        return None


class EhlersSupertrendCrossStrategy(BaseStrategy):
    """A strategy based on the cross of two Ehlers Supertrend indicators
    (fast and slow), incorporating a recursive low-pass filter for smoothing.
    This version replaces scipy with a custom filter implementation and is tuned for scalping.
    """

    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.fast_st_period = self.config.strategy_params.get(
            "ehlers_fast_supertrend_period", 5
        )
        self.fast_st_multiplier = self.config.strategy_params.get(
            "ehlers_fast_supertrend_multiplier", 1.5
        )
        self.slow_st_period = self.config.strategy_params.get(
            "ehlers_slow_supertrend_period", 10
        )
        self.slow_st_multiplier = self.config.strategy_params.get(
            "ehlers_slow_supertrend_multiplier", 2.5
        )
        self.filter_alpha = self.config.strategy_params.get("ehlers_filter_alpha", 0.35)
        self.filter_poles = self.config.strategy_params.get("ehlers_filter_poles", 1)
        # atr_period is inherited from BaseStrategy

    def _recursive_low_pass_filter(self, data: pd.Series) -> pd.Series:
        """Implements a simple recursive low-pass filter by applying an EMA multiple times.
        This approximates a higher-order filter but is not a true Butterworth filter.
        The 'filter_alpha' (smoothing factor) and 'filter_poles' (number of EMA applications)
        control the smoothing and lag. For scalping, higher alpha and fewer poles for less lag.
        """
        if data.empty:
            return pd.Series(dtype=float)

        filtered_data = data.copy()

        for _ in range(self.filter_poles):
            # The adjust=False parameter makes it a true recursive EMA
            filtered_data = filtered_data.ewm(
                alpha=self.filter_alpha, adjust=False
            ).mean()

        return filtered_data

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        """Calculates ATR and Ehlers Supertrend for fast and slow periods using recursive filter. Updates self.indicators."""
        df = data.get(
            self.primary_timeframe
        )  # Get raw market data for this strategy's symbol and timeframe
        # Determine minimum data needed based on all relevant periods and filter requirements
        min_data_needed = max(
            self.fast_st_period,
            self.slow_st_period,
            self.atr_period,
            (self.filter_poles * 2),  # Conservative estimate for filter warm-up
        )
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(
                f"[{self.symbol}] Insufficient data for Ehlers Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles)."
            )
            return

        # Apply custom recursive filter to price data
        df_filtered = (
            df.copy()
        )  # Work on a copy to avoid modifying original df directly
        df_filtered["filtered_close"] = self._recursive_low_pass_filter(
            df_filtered["close"]
        )
        df_filtered["filtered_high"] = self._recursive_low_pass_filter(
            df_filtered["high"]
        )
        df_filtered["filtered_low"] = self._recursive_low_pass_filter(
            df_filtered["low"]
        )

        # Drop NaNs introduced by filtering (especially at the beginning of the series)
        df_filtered.dropna(
            subset=["filtered_close", "filtered_high", "filtered_low"], inplace=True
        )

        if (
            df_filtered.empty or len(df_filtered) < self.atr_period
        ):  # Ensure enough data for ATR after filtering
            logger.debug(
                f"[{self.symbol}] DataFrame too small after filtering for Ehlers Supertrend calculation ({len(df_filtered)} < {self.atr_period} candles)."
            )
            return

        # Calculate ATR on filtered prices
        high_low_filtered = df_filtered["filtered_high"] - df_filtered["filtered_low"]
        high_close_filtered = np.abs(
            df_filtered["filtered_high"] - df_filtered["filtered_close"].shift()
        )
        low_close_filtered = np.abs(
            df_filtered["filtered_low"] - df_filtered["filtered_close"].shift()
        )
        tr_filtered = pd.concat(
            [high_low_filtered, high_close_filtered, low_close_filtered], axis=1
        ).max(axis=1)
        df_filtered["atr_filtered"] = tr_filtered.ewm(
            span=self.atr_period, adjust=False
        ).mean()

        # Ensure 'atr_filtered' has enough non-NaN values for Supertrend calculation
        if df_filtered["atr_filtered"].isnull().all() or (
            not df_filtered["atr_filtered"].empty
            and df_filtered["atr_filtered"].iloc[-1] == 0
        ):
            logger.debug(
                f"[{self.symbol}] ATR filtered values are all NaN or last ATR is zero, cannot calculate Supertrend."
            )
            return

        # --- Calculate Fast Ehlers Supertrend ---
        hl2_filtered_fast = (
            df_filtered["filtered_high"] + df_filtered["filtered_low"]
        ) / 2
        df_filtered["upperband_fast"] = hl2_filtered_fast + (
            self.fast_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["lowerband_fast"] = hl2_filtered_fast - (
            self.fast_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["in_uptrend_fast"] = True  # Initialize

        df_filtered["supertrend_fast_line"] = np.nan
        for current in range(1, len(df_filtered.index)):
            previous = current - 1
            if (
                df_filtered.loc[df_filtered.index[current], "filtered_close"]
                > df_filtered.loc[df_filtered.index[previous], "upperband_fast"]
            ):
                df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"] = True
            elif (
                df_filtered.loc[df_filtered.index[current], "filtered_close"]
                < df_filtered.loc[df_filtered.index[previous], "lowerband_fast"]
            ):
                df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"] = False
            else:
                df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"] = (
                    df_filtered.loc[df_filtered.index[previous], "in_uptrend_fast"]
                )

            if df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"]:
                prev_supertrend = (
                    df_filtered.loc[df_filtered.index[previous], "supertrend_fast_line"]
                    if not np.isnan(
                        df_filtered.loc[
                            df_filtered.index[previous], "supertrend_fast_line"
                        ]
                    )
                    else df_filtered.loc[df_filtered.index[current], "lowerband_fast"]
                )
                df_filtered.loc[df_filtered.index[current], "supertrend_fast_line"] = (
                    max(
                        df_filtered.loc[df_filtered.index[current], "lowerband_fast"],
                        prev_supertrend,
                    )
                )
            else:
                prev_supertrend = (
                    df_filtered.loc[df_filtered.index[previous], "supertrend_fast_line"]
                    if not np.isnan(
                        df_filtered.loc[
                            df_filtered.index[previous], "supertrend_fast_line"
                        ]
                    )
                    else df_filtered.loc[df_filtered.index[current], "upperband_fast"]
                )
                df_filtered.loc[df_filtered.index[current], "supertrend_fast_line"] = (
                    min(
                        df_filtered.loc[df_filtered.index[current], "upperband_fast"],
                        prev_supertrend,
                    )
                )

        df_filtered["supertrend_fast"] = df_filtered["supertrend_fast_line"]

        # --- Calculate Slow Ehlers Supertrend ---
        hl2_filtered_slow = (
            df_filtered["filtered_high"] + df_filtered["filtered_low"]
        ) / 2
        df_filtered["upperband_slow"] = hl2_filtered_slow + (
            self.slow_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["lowerband_slow"] = hl2_filtered_slow - (
            self.slow_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["in_uptrend_slow"] = True  # Initialize

        df_filtered["supertrend_slow_line"] = np.nan
        for current in range(1, len(df_filtered.index)):
            previous = current - 1
            if (
                df_filtered.loc[df_filtered.index[current], "filtered_close"]
                > df_filtered.loc[df_filtered.index[previous], "upperband_slow"]
            ):
                df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"] = True
            elif (
                df_filtered.loc[df_filtered.index[current], "filtered_close"]
                < df_filtered.loc[df_filtered.index[previous], "lowerband_slow"]
            ):
                df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"] = False
            else:
                df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"] = (
                    df_filtered.loc[df_filtered.index[previous], "in_uptrend_slow"]
                )

            if df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"]:
                prev_supertrend = (
                    df_filtered.loc[df_filtered.index[previous], "supertrend_slow_line"]
                    if not np.isnan(
                        df_filtered.loc[
                            df_filtered.index[previous], "supertrend_slow_line"
                        ]
                    )
                    else df_filtered.loc[df_filtered.index[current], "lowerband_slow"]
                )
                df_filtered.loc[df_filtered.index[current], "supertrend_slow_line"] = (
                    max(
                        df_filtered.loc[df_filtered.index[current], "lowerband_slow"],
                        prev_supertrend,
                    )
                )
            else:
                prev_supertrend = (
                    df_filtered.loc[df_filtered.index[previous], "supertrend_slow_line"]
                    if not np.isnan(
                        df_filtered.loc[
                            df_filtered.index[previous], "supertrend_slow_line"
                        ]
                    )
                    else df_filtered.loc[df_filtered.index[current], "upperband_slow"]
                )
                df_filtered.loc[df_filtered.index[current], "supertrend_slow_line"] = (
                    min(
                        df_filtered.loc[df_filtered.index[current], "upperband_slow"],
                        prev_supertrend,
                    )
                )

        df_filtered["supertrend_slow"] = df_filtered["supertrend_slow_line"]

        self.indicators[self.primary_timeframe] = df_filtered.copy()  # Store a copy

    async def generate_signal(self) -> StrategySignal | None:
        """Generate signal based on Ehlers Supertrend cross with confirmation."""
        df_indicators = self.indicators.get(self.primary_timeframe)
        if df_indicators is None or df_indicators.empty or len(df_indicators) < 2:
            logger.debug(
                f"[{self.symbol}] Insufficient indicator data for Ehlers Supertrend Cross signal generation."
            )
            return None

        # Drop any NaN rows that might result from indicator calculation to get clean data for signal
        df_cleaned = df_indicators.dropna(
            subset=[
                "supertrend_fast",
                "supertrend_slow",
                "atr_filtered",
                "filtered_close",
                "in_uptrend_slow",
            ]
        ).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug(
                f"[{self.symbol}] DataFrame too small after dropping NaNs for Ehlers Supertrend Cross signal generation from indicators."
            )
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        # Determine overall trend based on slow Supertrend
        in_uptrend_overall = current["in_uptrend_slow"]

        if self.last_signal:
            if (self.last_signal.action == "BUY" and not in_uptrend_overall) or (
                self.last_signal.action == "SELL" and in_uptrend_overall
            ):
                logger.info(
                    f"[{self.symbol}] Overall trend based on slow ST changed opposite to pending signal ({self.last_signal.action}), resetting pending signal."
                )
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None

            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(
                        f"[{self.symbol}] Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}."
                    )
                    temp_signal = self.last_signal
                    self.last_signal = None
                    self.signal_confirmed = False
                    self.signal_candle_time = None
                    return temp_signal
                return None
            return None

        signal_to_generate = None
        current_atr = float(current.get("atr_filtered", 0.0))
        take_profit_multiplier = self.config.strategy_params.get(
            "take_profit_atr_multiplier", 1.0
        )  # Scalping tuned

        # Buy signal: Fast ST crosses above Slow ST and overall trend is up
        if (
            previous["supertrend_fast"] <= previous["supertrend_slow"]
            and current["supertrend_fast"] > current["supertrend_slow"]
            and in_uptrend_overall
        ):
            take_profit_val = (
                (float(current["close"]) + current_atr * take_profit_multiplier)
                if current_atr > 0
                else None
            )

            signal_to_generate = StrategySignal(
                action="BUY",
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(
                    current["supertrend_slow"]
                ),  # Use slow ST for initial SL
                take_profit=take_profit_val,
                signal_price=float(current["close"]),
                metadata={"reason": "Ehlers Fast ST Crosses Above Slow ST (Uptrend)"},
            )

        # Sell signal: Fast ST crosses below Slow ST and overall trend is down
        elif (
            previous["supertrend_fast"] >= previous["supertrend_slow"]
            and current["supertrend_fast"] < current["supertrend_slow"]
            and not in_uptrend_overall
        ):
            take_profit_val = (
                (float(current["close"]) - current_atr * take_profit_multiplier)
                if current_atr > 0
                else None
            )

            signal_to_generate = StrategySignal(
                action="SELL",
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(
                    current["supertrend_slow"]
                ),  # Use slow ST for initial SL
                take_profit=take_profit_val,
                signal_price=float(current["close"]),
                metadata={"reason": "Ehlers Fast ST Crosses Below Slow ST (Downtrend)"},
            )

        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(
                f"[{self.symbol}] PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}, TP: {signal_to_generate.take_profit if signal_to_generate.take_profit else 'N/A':.5f}. Waiting for confirmation (0 for immediate)."
            )
            return None

        return None


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================


class BybitTradingBot:
    """Main trading bot class with WebSocket integration."""

    def __init__(
        self,
        config: Config,
        strategies: dict[str, BaseStrategy],
        session: HTTP | None = None,
    ):
        self.config = config
        self.strategies = strategies  # Now a dictionary of strategies, one per symbol

        self.session = session or HTTP(
            testnet=config.testnet, api_key=config.api_key, api_secret=config.api_secret
        )
        # Public WebSocket for kline data (can subscribe to multiple symbols)
        self.public_ws = WebSocket(
            testnet=config.testnet,
            channel_type=config.category,
            api_key=config.api_key,  # Public data can generally be fetched without API keys for kline, but auth is often good practice
            api_secret=config.api_secret,
        )
        # Private WebSocket for account-specific data (positions, orders, wallet)
        self.private_ws = WebSocket(
            testnet=config.testnet,
            channel_type="private",
            api_key=config.api_key,
            api_secret=config.api_secret,
        )

        self.market_info: dict[str, MarketInfo] = {}  # Market info per symbol
        self.market_data: dict[str, dict[str, pd.DataFrame]] = {
            symbol: {} for symbol in config.symbols
        }  # Raw kline data per symbol and timeframe
        self.positions: dict[str, Position | None] = dict.fromkeys(
            config.symbols
        )  # Position per symbol
        self.balance: Decimal = to_decimal(0)  # Initialize balance with Decimal context
        self.is_running = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.last_processed_candle_time: dict[str, datetime | None] = dict.fromkeys(
            config.symbols
        )  # Last candle time per symbol
        self.order_tasks: dict[
            str, asyncio.Task
        ] = {}  # To track open order tasks (not fully implemented for robustness)

        self._load_state()  # Load state at initialization

    async def initialize(self):
        """Load market info, historical data, and initial balance for all configured symbols."""
        logger.info("Initializing bot for multiple symbols...")
        for symbol in self.config.symbols:
            logger.info(f"Initializing for symbol: {symbol}")
            await self._load_market_info(symbol)
            await self._load_historical_data(
                symbol
            )  # Load historical for primary timeframe for each symbol

        await self.update_account_balance()
        await self.get_positions()  # Get all current positions
        logger.info("Bot initialization complete.")

    async def _load_market_info(self, symbol: str):
        """Load and store market information for a specific symbol."""
        try:
            response = self.session.get_instruments_info(
                category=self.config.category, symbol=symbol
            )
            if response and response["retCode"] == 0:
                instrument = response["result"]["list"][0]
                self.market_info[symbol] = MarketInfo(
                    symbol=symbol,
                    tick_size=to_decimal(instrument["priceFilter"]["tickSize"]),
                    lot_size=to_decimal(instrument["lotSizeFilter"]["qtyStep"]),
                )
                logger.info(
                    f"[{symbol}] Market info loaded: Tick Size {self.market_info[symbol].tick_size}, Lot Size {self.market_info[symbol].lot_size}"
                )
            else:
                raise Exception(
                    f"Failed to get instrument info for {symbol}: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.critical(
                f"[{symbol}] Critical Error loading market info: {e}", exc_info=True
            )
            sys.exit(1)  # Exit if critical info cannot be loaded

    async def _load_historical_data(self, symbol: str):
        """Load historical kline data to warm up the strategy for a specific symbol."""
        logger.info(
            f"[{symbol}] Loading historical data for {self.config.timeframe} timeframe..."
        )
        try:
            response = self.session.get_kline(
                category=self.config.category,
                symbol=symbol,
                interval=self.config.timeframe,
                limit=self.config.lookback_periods,
            )
            if response and response["retCode"] == 0:
                data = response["result"]["list"]
                df = pd.DataFrame(
                    data,
                    columns=[
                        "time",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "turnover",
                    ],
                )
                df["time"] = pd.to_datetime(
                    df["time"].astype(int), unit="ms", utc=True
                )  # Ensure 'time' is int before unit='ms'
                df.set_index("time", inplace=True)
                df = df.astype(float)
                df.sort_index(inplace=True)

                # Store data under symbol -> timeframe
                if (
                    symbol not in self.market_data
                ):  # Defensive check, should be initialized in __init__
                    self.market_data[symbol] = {}
                self.market_data[symbol][self.config.timeframe] = df

                if not df.empty:
                    self.last_processed_candle_time[symbol] = df.index[-1]
                logger.info(
                    f"[{symbol}] Loaded {len(df)} historical candles. Last candle: {self.last_processed_candle_time.get(symbol)}"
                )
            else:
                raise Exception(
                    f"Failed to get kline data for {symbol}: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.critical(
                f"[{symbol}] Critical Error loading historical data: {e}", exc_info=True
            )
            sys.exit(1)  # Exit if critical data cannot be loaded

    async def _place_single_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> str | None:
        """Internal helper to place a single order for a specific symbol with proper precision and error handling.
        Includes retry logic with exponential backoff for rate limit errors.
        """
        if symbol not in self.market_info:
            logger.error(f"[{symbol}] Cannot place order, market info not loaded.")
            return None

        market_info = self.market_info[
            symbol
        ]  # Get market info for the specific symbol

        formatted_qty = market_info.format_quantity(quantity)
        if float(formatted_qty) <= float(
            market_info.lot_size
        ):  # Ensure quantity is not zero or too small after precision formatting
            logger.warning(
                f"[{symbol}] Formatted quantity for order is too small ({formatted_qty}), skipping. Original: {quantity}. Minimum lot size: {market_info.lot_size}"
            )
            return None

        params = {
            "category": self.config.category,
            "symbol": symbol,  # Use the specific symbol
            "side": side.value,
            "orderType": order_type.value,
            "qty": formatted_qty,
            "isLeverage": 1,  # Always use leverage for derivatives
            "tpslMode": "Full",  # Ensure SL/TP are attached to the position
        }

        if order_type == OrderType.LIMIT and price is not None:
            params["price"] = market_info.format_price(
                price
            )  # Use specific market_info for formatting

        if stop_loss is not None:
            params["stopLoss"] = market_info.format_price(stop_loss)
            params["slTriggerBy"] = (
                "MarkPrice"  # Using MarkPrice for consistent triggering
            )

        if take_profit is not None:
            params["takeProfit"] = market_info.format_price(take_profit)
            params["tpTriggerBy"] = "MarkPrice"

        retries = 5
        delay = 5  # Initial delay in seconds

        for i in range(retries):
            try:
                logger.debug(
                    f"[{symbol}] Attempting to place order (attempt {i + 1}/{retries}) with params: {params}"
                )
                response = self.session.place_order(**params)

                if response and response["retCode"] == 0:
                    order_id = response["result"]["orderId"]
                    logger.info(
                        f"[{symbol}] TRADE: Order placed successfully: ID {order_id}, Side {side.value}, Qty {formatted_qty}, SL: {stop_loss}, TP: {take_profit}"
                    )
                    return order_id
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response from API"
                )
                ret_code = response.get("retCode", "N/A")
                # Bybit's specific rate limit error code is 10006.
                if ret_code == 10006 or "rate limit" in error_msg:
                    logger.warning(
                        f"[{symbol}] Rate limit hit on attempt {i + 1}/{retries}: {error_msg}. Retrying in {delay}s."
                    )
                    if i < retries - 1:
                        await asyncio.sleep(delay)
                        delay *= 2  # Exponential backoff
                        continue

                logger.error(
                    f"[{symbol}] Failed to place order with non-retriable error: {error_msg} (Code: {ret_code})"
                )
                return None

            except FailedRequestError as e:
                # This catches HTTP errors like 403 Forbidden, which Bybit uses for IP-based rate limits or region blocks.
                if "rate limit" in str(e) or "403" in str(e):
                    if i < retries - 1:
                        logger.warning(
                            f"[{symbol}] Rate limit HTTP error on attempt {i + 1}/{retries}: {e}. Retrying in {delay}s. If this persists, your IP may be blocked (e.g., from USA)."
                        )
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        logger.error(
                            f"[{symbol}] Final attempt failed due to rate limit error: {e}",
                            exc_info=True,
                        )
                        return None
                else:
                    logger.error(
                        f"[{symbol}] Non-retriable HTTP error placing order: {e}",
                        exc_info=True,
                    )
                    return None  # Don't retry for other HTTP errors
            except Exception as e:
                logger.error(
                    f"[{symbol}] An unexpected error occurred placing order: {e}",
                    exc_info=True,
                )
                return None  # Don't retry for unexpected errors

        logger.error(f"[{symbol}] Failed to place order after {retries} attempts.")
        return None

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> str | None:
        """Place a market order for a specific symbol."""
        return await self._place_single_order(
            symbol,
            side,
            quantity,
            OrderType.MARKET,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> str | None:
        """Place a limit order for a specific symbol."""
        return await self._place_single_order(
            symbol,
            side,
            quantity,
            OrderType.LIMIT,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    async def update_stop_loss_and_take_profit(
        self,
        symbol: str,
        position_side: str,
        new_stop_loss: Decimal | None = None,
        new_take_profit: Decimal | None = None,
    ):
        """Updates the stop-loss or take-profit of an existing position for a specific symbol."""
        current_position = self.positions.get(symbol)
        if current_position is None or current_position.side != position_side:
            logger.warning(
                f"[{symbol}] No active {position_side} position found for SL/TP update. Current position: {current_position}"
            )
            return

        if symbol not in self.market_info:
            logger.error(f"[{symbol}] Market info not loaded, cannot update SL/TP.")
            return

        market_info = self.market_info[symbol]
        params = {
            "category": self.config.category,
            "symbol": symbol,
        }
        updated_any = False  # Flag to check if any parameter actually changed

        # Check and update Stop Loss
        if new_stop_loss is not None:
            # Only update if the new SL is different from the current effective (trailing) SL on record
            if (
                current_position.trailing_stop_loss is None
                or new_stop_loss != current_position.trailing_stop_loss
            ):
                params["stopLoss"] = market_info.format_price(float(new_stop_loss))
                params["slTriggerBy"] = "MarkPrice"
                logger.info(
                    f"[{symbol}] Updating stop loss for {current_position.side} position from {current_position.trailing_stop_loss:.5f if current_position.trailing_stop_loss else 'N/A'} to {new_stop_loss:.5f}"
                )
                current_position.trailing_stop_loss = (
                    new_stop_loss  # Update internal state immediately
                )
                updated_any = True
            else:
                logger.debug(
                    f"[{symbol}] New stop loss {new_stop_loss:.5f} is same as current {current_position.trailing_stop_loss:.5f}, skipping SL update."
                )

        # Check and update Take Profit
        if new_take_profit is not None:
            # Only update if the new TP is different from the current effective TP on record
            if (
                current_position.take_profit is None
                or new_take_profit != current_position.take_profit
            ):
                params["takeProfit"] = market_info.format_price(float(new_take_profit))
                params["tpTriggerBy"] = "MarkPrice"
                logger.info(
                    f"[{symbol}] Updating take profit for {current_position.side} position from {current_position.take_profit:.5f if current_position.take_profit else 'N/A'} to {new_take_profit:.5f}"
                )
                current_position.take_profit = (
                    new_take_profit  # Update internal state immediately
                )
                updated_any = True
            else:
                logger.debug(
                    f"[{symbol}] New take profit {new_take_profit:.5f} is same as current {current_position.take_profit:.5f}, skipping TP update."
                )

        if not updated_any:
            logger.debug(
                f"[{symbol}] No changes in stop loss or take profit requested, skipping API call."
            )
            return

        try:
            response = self.session.set_trading_stop(**params)
            if response and response["retCode"] == 0:
                logger.info(
                    f"[{symbol}] Successfully sent SL/TP update request for {current_position.symbol} {current_position.side} position."
                )
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response from API"
                )
                logger.error(
                    f"[{symbol}] Failed to update SL/TP: {error_msg} (Code: {response.get('retCode', 'N/A')})"
                )
        except Exception as e:
            logger.error(f"[{symbol}] Error updating SL/TP: {e}", exc_info=True)
        finally:
            self._save_state()  # Always save state after trying to update position parameters

    async def get_positions(self):
        """Get current positions for all symbols and update internal state."""
        try:
            response = self.session.get_positions(
                category=self.config.category,
                accountType="UNIFIED",  # Explicitly request unified account positions to get all
                settleCoin="USDT",  # Explicitly filter by USDT to avoid broad requests if possible and adhere to API requirement
            )
            if response and response["retCode"] == 0 and response["result"]["list"]:
                active_symbols_from_api = set()
                for pos_data in response["result"]["list"]:
                    symbol = pos_data["symbol"]
                    size = to_decimal(pos_data["size"])
                    active_symbols_from_api.add(symbol)

                    if symbol not in self.config.symbols:
                        logger.warning(
                            f"[{symbol}] Found open position for {symbol} which is not in configured symbols. Ignoring."
                        )
                        continue  # Skip positions for unconfigured symbols

                    if size > 0:
                        current_position_side = pos_data["side"]

                        # Try to preserve existing initial_stop_loss and entry_signal_price from internal state
                        # if position is the same. These are fixed at entry time and not usually returned by API.
                        existing_pos_state = self.positions.get(symbol)
                        existing_initial_sl = (
                            existing_pos_state.initial_stop_loss
                            if existing_pos_state
                            and existing_pos_state.side == current_position_side
                            else None
                        )
                        existing_entry_signal_price = (
                            existing_pos_state.entry_signal_price
                            if existing_pos_state
                            and existing_pos_state.side == current_position_side
                            else None
                        )

                        # Use Bybit API's reported SL/TP if available, otherwise fall back to saved internal state.
                        bybit_sl = (
                            to_decimal(pos_data["stopLoss"])
                            if pos_data.get("stopLoss")
                            else None
                        )
                        bybit_tp = (
                            to_decimal(pos_data["takeProfit"])
                            if pos_data.get("takeProfit")
                            else None
                        )

                        final_trailing_sl = (
                            bybit_sl
                            if bybit_sl is not None
                            else (
                                existing_pos_state.trailing_stop_loss
                                if existing_pos_state
                                and existing_pos_state.side == current_position_side
                                else None
                            )
                        )
                        final_take_profit = (
                            bybit_tp
                            if bybit_tp is not None
                            else (
                                existing_pos_state.take_profit
                                if existing_pos_state
                                and existing_pos_state.side == current_position_side
                                else None
                            )
                        )

                        self.positions[symbol] = Position(
                            symbol=symbol,
                            side=current_position_side,
                            size=size,
                            avg_price=to_decimal(pos_data["avgPrice"]),
                            unrealized_pnl=to_decimal(pos_data["unrealisedPnl"]),
                            mark_price=to_decimal(pos_data["markPrice"]),
                            leverage=int(pos_data.get("leverage", 1)),
                            entry_signal_price=existing_entry_signal_price,
                            initial_stop_loss=existing_initial_sl,
                            trailing_stop_loss=final_trailing_sl,
                            take_profit=final_take_profit,
                        )
                        logger.debug(
                            f"[{symbol}] Position updated from API: {self.positions[symbol]}"
                        )
                    else:
                        self.positions[symbol] = (
                            None  # No open position for this symbol from API
                        )
                        logger.debug(
                            f"[{symbol}] No active position found for {symbol} via API response (size zero)."
                        )

                # For any configured symbols that were NOT in the API response, ensure they are set to None
                for symbol_in_config in self.config.symbols:
                    if (
                        symbol_in_config not in active_symbols_from_api
                        and self.positions.get(symbol_in_config) is not None
                    ):
                        logger.info(
                            f"[{symbol_in_config}] Position closed on exchange, updating internal state to None."
                        )
                        self.positions[symbol_in_config] = None

            else:
                # If API returns no list or an error, assume no positions for any configured symbols
                logger.info(
                    "No active positions reported by API for any symbols, resetting all internal states to None."
                )
                self.positions = dict.fromkeys(
                    self.config.symbols
                )  # Reset all positions
            self._save_state()  # Save state after updating all positions
        except Exception as e:
            logger.error(f"Error getting positions: {e}", exc_info=True)

    async def update_account_balance(self):
        """Update account balance."""
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            if response and response["retCode"] == 0:
                balance_data = response["result"]["list"][0]
                self.balance = to_decimal(balance_data["totalEquity"])
                logger.info(f"Account balance updated: {self.balance:.2f} USDT")
            else:
                logger.error(
                    f"Failed to update balance: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"Error updating balance: {e}", exc_info=True)

    def _calculate_position_size(self, signal: StrategySignal) -> float:
        """Calculates position size based on fixed risk percentage and stop-loss distance for a specific symbol.
        Returns the quantity in asset units (e.g., XLM amount).
        """
        symbol = signal.symbol
        if signal.stop_loss is None or signal.signal_price is None:
            logger.error(
                f"[{symbol}] Cannot calculate position size without a valid stop-loss and signal price from the strategy."
            )
            return 0.0

        if symbol not in self.market_info:
            logger.error(
                f"[{symbol}] Market info not loaded for {symbol}, cannot calculate position size."
            )
            return 0.0

        market_info = self.market_info[symbol]

        risk_amount_usdt = self.balance * to_decimal(self.config.risk_per_trade_pct)

        # Calculate distance to stop loss in price
        signal_price_dec = to_decimal(signal.signal_price)
        stop_loss_dec = to_decimal(signal.stop_loss)

        stop_loss_distance_raw = to_decimal(0)
        if signal.action == "BUY":
            stop_loss_distance_raw = signal_price_dec - stop_loss_dec
        elif signal.action == "SELL":
            stop_loss_distance_raw = stop_loss_dec - signal_price_dec

        # Ensure stop_loss_distance_raw is sufficiently positive to avoid division by zero or negative risk
        if (
            stop_loss_distance_raw <= to_decimal(0)
            or stop_loss_distance_raw < market_info.tick_size
        ):
            logger.warning(
                f"[{symbol}] Stop loss distance is non-positive or too small ({stop_loss_distance_raw:.5f} < {market_info.tick_size}), cannot calculate position size safely. Returning 0.0."
            )
            return 0.0

        # Position size in asset units, accounting for leverage
        position_size_asset_unleveraged = risk_amount_usdt / stop_loss_distance_raw

        # Apply configured leverage
        leveraged_position_size_asset = position_size_asset_unleveraged * to_decimal(
            self.config.leverage
        )

        # Format to market's lot size precision
        formatted_position_size = to_decimal(
            market_info.format_quantity(float(leveraged_position_size_asset))
        )

        # Calculate order value in USDT to check against minimum
        order_value_usdt = formatted_position_size * signal_price_dec

        if order_value_usdt < to_decimal(self.config.min_order_value_usdt):
            logger.warning(
                f"[{symbol}] Calculated order value ({order_value_usdt:.2f} USDT) is below minimum required ({self.config.min_order_value_usdt} USDT). Skipping trade."
            )
            return 0.0

        logger.info(
            f"[{symbol}] Risk Amount: {risk_amount_usdt:.2f} USDT, SL Distance: {stop_loss_distance_raw:.5f} USDT, "
            f"Calculated Position Size (Leveraged & Formatted): {formatted_position_size:.5f} {symbol}, "
            f"Order Value: {order_value_usdt:.2f} USDT"
        )

        return float(formatted_position_size)

    async def process_signal(self, signal: StrategySignal):
        """Processes a trading signal from the strategy, managing orders and positions for the specific symbol."""
        symbol = signal.symbol
        logger.info(
            f"[{symbol}] Processing signal: {signal.action} {symbol} (Reason: {signal.metadata.get('reason', 'N/A')})"
        )

        # Access market data for the specific symbol and timeframe
        symbol_market_data_for_timeframe = self.market_data.get(symbol, {}).get(
            self.config.timeframe
        )
        if (
            symbol_market_data_for_timeframe is None
            or symbol_market_data_for_timeframe.empty
        ):
            logger.warning(
                f"[{symbol}] No market data available for signal processing, skipping."
            )
            return

        current_close_price = symbol_market_data_for_timeframe.iloc[-1]["close"]
        current_position = self.positions.get(symbol)
        current_strategy = self.strategies.get(
            symbol
        )  # Ensure current_strategy is fetched for this symbol

        if current_strategy is None:
            logger.error(
                f"[{symbol}] No strategy instance found for this symbol, cannot process signal."
            )
            return

        # Dynamically set/refine Take Profit if not provided by strategy or if ATR changes
        df_indicators = current_strategy.indicators.get(
            self.config.timeframe
        )  # Get indicators for THIS symbol's strategy
        current_atr = (
            float(
                df_indicators.iloc[-1].get(
                    "atr_filtered", df_indicators.iloc[-1].get("atr", 0.0)
                )
            )
            if df_indicators is not None and not df_indicators.empty
            else 0.0
        )

        if (
            signal.take_profit is None
            and signal.signal_price is not None
            and current_atr > 0
        ):
            tp_multiplier = to_decimal(
                self.config.strategy_params.get("take_profit_atr_multiplier", 1.0)
            )  # Scalping tuned default
            signal_price_dec = to_decimal(signal.signal_price)
            current_atr_dec = to_decimal(current_atr)

            if signal.action == "BUY":
                signal.take_profit = float(
                    signal_price_dec + current_atr_dec * tp_multiplier
                )
            elif signal.action == "SELL":
                signal.take_profit = float(
                    signal_price_dec - current_atr_dec * tp_multiplier
                )
            logger.info(
                f"[{symbol}] Dynamically calculated Take Profit: {signal.take_profit:.5f}"
            )

        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            logger.warning(
                f"[{symbol}] Calculated position size is zero or too small, aborting trade."
            )
            return

        # --- Position Management Logic ---
        if current_position:
            # Scenario 1: Signal is in the opposite direction of the current position (REVERSE)
            if (signal.action == "BUY" and current_position.side == "Sell") or (
                signal.action == "SELL" and current_position.side == "Buy"
            ):
                logger.info(
                    f"[{symbol}] Reversing position: Closing existing {current_position.side} ({current_position.size:.5f}) to open {signal.action} ({position_size:.5f})."
                )

                # Close existing position first
                close_side = (
                    OrderSide.BUY if current_position.side == "Sell" else OrderSide.SELL
                )
                close_order_id = await self.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    quantity=float(current_position.size),
                )

                if close_order_id:
                    logger.info(
                        f"[{symbol}] Close order {close_order_id} placed. Waiting for position to settle before opening new one..."
                    )
                    await asyncio.sleep(5)  # Give exchange time to process closure
                    await self.get_positions()  # Update all positions state
                    await self.update_account_balance()  # Update balance

                    if (
                        self.positions.get(symbol) is None
                    ):  # Successfully closed, now open new one
                        logger.info(
                            f"[{symbol}] Existing position successfully closed. Proceeding to open new one."
                        )
                        new_order_id = await self.place_market_order(
                            symbol=symbol,
                            side=OrderSide.BUY
                            if signal.action == "BUY"
                            else OrderSide.SELL,
                            quantity=position_size,
                            stop_loss=signal.stop_loss,
                            take_profit=signal.take_profit,
                        )
                        if new_order_id:
                            # Temporarily update internal position state. Actual values will be pulled from API via get_positions later
                            self.positions[symbol] = Position(
                                symbol=symbol,
                                side=signal.action,
                                size=to_decimal(position_size),
                                avg_price=to_decimal(current_close_price),
                                unrealized_pnl=to_decimal("0"),
                                mark_price=to_decimal(current_close_price),
                                leverage=self.config.leverage,
                                entry_signal_price=to_decimal(signal.signal_price)
                                if signal.signal_price
                                else None,
                                initial_stop_loss=to_decimal(signal.stop_loss)
                                if signal.stop_loss
                                else None,
                                trailing_stop_loss=to_decimal(signal.stop_loss)
                                if signal.stop_loss
                                else None,  # Initial trailing SL is the provided SL
                                take_profit=to_decimal(signal.take_profit)
                                if signal.take_profit
                                else None,
                            )
                            self._save_state()
                        else:
                            logger.error(
                                f"[{symbol}] Failed to open new position after closing existing one. Check logs for details."
                            )
                    else:
                        logger.error(
                            f"[{symbol}] Failed to confirm closure of existing position. Aborting new trade to prevent conflicting positions."
                        )
                else:
                    logger.error(
                        f"[{symbol}] Failed to place order to close existing position. Aborting new trade."
                    )
                return  # Handled reversing position

            # Scenario 2: Signal is in the same direction as the current position (ADJUST SL/TP)
            if (signal.action == "BUY" and current_position.side == "Buy") or (
                signal.action == "SELL" and current_position.side == "Sell"
            ):
                logger.info(
                    f"[{symbol}] Signal to {signal.action} received, but already in a {current_position.side} position. Considering updating SL/TP."
                )

                new_sl_to_set: Decimal | None = None
                new_tp_to_set: Decimal | None = None

                # Update initial_stop_loss if the new signal suggests a tighter (more favorable) SL
                if signal.stop_loss is not None:
                    new_signal_sl = to_decimal(signal.stop_loss)

                    # For BUY: new SL must be higher than existing initial SL (tighter)
                    # For SELL: new SL must be lower than existing initial SL (tighter)
                    should_update_initial_sl = False
                    if (
                        current_position.initial_stop_loss is None
                        or (
                            current_position.side == "Buy"
                            and new_signal_sl > current_position.initial_stop_loss
                        )
                        or (
                            current_position.side == "Sell"
                            and new_signal_sl < current_position.initial_stop_loss
                        )
                    ):
                        should_update_initial_sl = True

                    if should_update_initial_sl:
                        current_position.initial_stop_loss = new_signal_sl
                        logger.info(
                            f"[{symbol}] Internal initial stop loss updated to new strategy SL: {new_signal_sl:.5f}"
                        )

                        # Also check if the new initial SL is tighter than the current trailing SL.
                        # If so, the trailing SL on the exchange should be moved to this new initial SL.
                        if (
                            current_position.trailing_stop_loss is None
                            or (
                                current_position.side == "Buy"
                                and new_signal_sl > current_position.trailing_stop_loss
                            )
                            or (
                                current_position.side == "Sell"
                                and new_signal_sl < current_position.trailing_stop_loss
                            )
                        ):
                            new_sl_to_set = new_signal_sl
                            logger.info(
                                f"[{symbol}] Trailing stop loss on exchange will be set to new initial SL: {new_sl_to_set:.5f}"
                            )

                # Update take_profit if new signal suggests a better TP
                if signal.take_profit is not None:
                    new_signal_tp = to_decimal(signal.take_profit)

                    # For BUY: new TP must be higher than existing TP (more profitable)
                    # For SELL: new TP must be lower than existing TP (more profitable)
                    should_update_tp = False
                    if (
                        current_position.take_profit is None
                        or (
                            current_position.side == "Buy"
                            and new_signal_tp > current_position.take_profit
                        )
                        or (
                            current_position.side == "Sell"
                            and new_signal_tp < current_position.take_profit
                        )
                    ):
                        should_update_tp = True

                    if should_update_tp:
                        new_tp_to_set = new_signal_tp
                        logger.info(
                            f"[{symbol}] Take profit updated to a more favorable level: {new_tp_to_set:.5f}"
                        )

                if new_sl_to_set or new_tp_to_set:
                    await self.update_stop_loss_and_take_profit(
                        symbol, current_position.side, new_sl_to_set, new_tp_to_set
                    )
                else:
                    logger.debug(
                        f"[{symbol}] No beneficial SL/TP updates from current signal, skipping API call."
                    )
                return  # Handled adjusting position

        # Scenario 3: No current position, open a new one
        if not current_position:
            logger.info(
                f"[{symbol}] Opening new {signal.action} position with size {position_size:.5f}."
            )
            order_id = await self.place_market_order(
                symbol=symbol,
                side=OrderSide.BUY if signal.action == "BUY" else OrderSide.SELL,
                quantity=position_size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            if order_id:
                # Temporarily update internal position state. Actual values will be pulled from API via get_positions later
                self.positions[symbol] = Position(
                    symbol=symbol,
                    side=signal.action,
                    size=to_decimal(position_size),
                    avg_price=to_decimal(current_close_price),
                    unrealized_pnl=to_decimal("0"),
                    mark_price=to_decimal(current_close_price),
                    leverage=self.config.leverage,
                    entry_signal_price=to_decimal(signal.signal_price)
                    if signal.signal_price
                    else None,
                    initial_stop_loss=to_decimal(signal.stop_loss)
                    if signal.stop_loss
                    else None,
                    trailing_stop_loss=to_decimal(signal.stop_loss)
                    if signal.stop_loss
                    else None,  # Initial trailing SL is the provided SL
                    take_profit=to_decimal(signal.take_profit)
                    if signal.take_profit
                    else None,
                )
                self._save_state()
            else:
                logger.error(
                    f"[{symbol}] Failed to open new position. Check logs for details."
                )
            return  # Handled opening new position

    async def _update_trailing_stop_loss(self, symbol: str):
        """Updates the trailing stop loss for an open position for a specific symbol.
        Activates when profit reaches 'break_even_profit_atr_multiplier' * ATR (to break-even)
        or 'trailing_stop_loss_activation_atr_multiplier' * ATR (to trail more aggressively).
        Moves by 'trailing_stop_loss_atr_multiplier' * ATR.
        """
        current_position = self.positions.get(symbol)
        current_strategy = self.strategies.get(symbol)

        if (
            current_position is None
            or current_position.entry_signal_price is None
            or current_position.initial_stop_loss is None
            or current_strategy is None
            or current_strategy.indicators.get(self.config.timeframe) is None
            or current_strategy.indicators[self.config.timeframe].empty
        ):
            logger.debug(
                f"[{symbol}] Cannot update trailing stop: no position, no entry price/initial SL, or no indicators."
            )
            return

        current_df_indicators = current_strategy.indicators[self.config.timeframe]
        current_price = to_decimal(current_df_indicators.iloc[-1]["close"])

        current_atr = to_decimal(
            current_df_indicators.iloc[-1].get(
                "atr_filtered", current_df_indicators.iloc[-1].get("atr", 0.0)
            )
        )
        if current_atr <= to_decimal(0):
            logger.warning(
                f"[{symbol}] ATR not available or non-positive for trailing stop calculation ({current_atr})."
            )
            return

        activation_multiplier = to_decimal(
            self.config.strategy_params.get(
                "trailing_stop_loss_activation_atr_multiplier", 0.5
            )
        )  # Scalping tuned
        trailing_multiplier = to_decimal(
            self.config.strategy_params.get("trailing_stop_loss_atr_multiplier", 0.75)
        )  # Scalping tuned
        break_even_profit_multiplier = to_decimal(
            self.config.strategy_params.get("break_even_profit_atr_multiplier", 0.2)
        )  # Scalping tuned

        # Calculate current profit in USD and ATR units
        profit_in_usd = to_decimal(0)
        if current_position.side == "Buy":
            profit_in_usd = current_price - current_position.entry_signal_price
        elif current_position.side == "Sell":
            profit_in_usd = (
                current_position.entry_signal_price - current_price
            )  # Corrected: profit for sell is entry - current

        profit_in_atr = (
            profit_in_usd / current_atr
            if current_atr > to_decimal(0)
            else to_decimal(0)
        )

        # Determine potential new trailing stop price
        potential_new_stop_price: Decimal | None = None
        current_trailing_sl = (
            current_position.trailing_stop_loss
        )  # The last SL value we set on the exchange
        initial_sl = (
            current_position.initial_stop_loss
        )  # The initial SL from the strategy signal

        # For BUY position
        if current_position.side == "Buy":
            # 1. Move to break-even + a small buffer if profit condition is met
            if profit_in_atr >= break_even_profit_multiplier:
                # Calculate break-even SL with a small buffer (e.g., 0.05 ATR above entry)
                calculated_be_sl = current_position.entry_signal_price + (
                    current_atr * to_decimal("0.05")
                )
                # The new potential SL should be at least the initial SL, and higher than the current trailing SL (if set)
                if (
                    current_trailing_sl is None
                    or calculated_be_sl > current_trailing_sl
                ):
                    potential_new_stop_price = max(calculated_be_sl, initial_sl)

            # 2. Aggressively trail if a higher profit condition is met
            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price - (current_atr * trailing_multiplier)
                # If this trailing point is higher than the current best potential SL, use it
                if (
                    potential_new_stop_price is None
                    or trailing_point_sl > potential_new_stop_price
                ):
                    potential_new_stop_price = max(trailing_point_sl, initial_sl)

            # Final safety check: ensure potential_new_stop_price is never below initial_sl
            if potential_new_stop_price and potential_new_stop_price < initial_sl:
                potential_new_stop_price = initial_sl

        # For SELL position
        elif current_position.side == "Sell":
            # 1. Move to break-even + a small buffer if profit condition is met
            if profit_in_atr >= break_even_profit_multiplier:
                # Calculate break-even SL with a small buffer (e.g., 0.05 ATR below entry)
                calculated_be_sl = current_position.entry_signal_price - (
                    current_atr * to_decimal("0.05")
                )
                # The new potential SL should be at most the initial SL, and lower than the current trailing SL (if set)
                if (
                    current_trailing_sl is None
                    or calculated_be_sl < current_trailing_sl
                ):
                    potential_new_stop_price = min(calculated_be_sl, initial_sl)

            # 2. Aggressively trail if a higher profit condition is met
            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price + (current_atr * trailing_multiplier)
                # If this trailing point is lower than the current best potential SL, use it
                if (
                    potential_new_stop_price is None
                    or trailing_point_sl < potential_new_stop_price
                ):
                    potential_new_stop_price = min(trailing_point_sl, initial_sl)

            # Final safety check: ensure potential_new_stop_price is never above initial_sl
            if potential_new_stop_price and potential_new_stop_price > initial_sl:
                potential_new_stop_price = initial_sl

        # Now, compare the determined `potential_new_stop_price` with the `current_trailing_sl` on the exchange
        if potential_new_stop_price is not None:
            should_update_exchange = False
            if current_trailing_sl is None:  # No current trailing SL set on exchange
                should_update_exchange = True
            elif (
                current_trailing_sl == potential_new_stop_price
            ):  # No actual change, no need to update
                should_update_exchange = False
            elif (
                current_position.side == "Buy"
                and potential_new_stop_price > current_trailing_sl
            ) or (
                current_position.side == "Sell"
                and potential_new_stop_price < current_trailing_sl
            ):  # Move SL up for a Buy
                should_update_exchange = True

            if should_update_exchange:
                # Call update_stop_loss_and_take_profit, which will also update self.positions[symbol].trailing_stop_loss and save state
                logger.info(
                    f"[{symbol}] Trailing SL update triggered for {current_position.side} position. Old: {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, New: {potential_new_stop_price:.5f}"
                )
                await self.update_stop_loss_and_take_profit(
                    symbol,
                    current_position.side,
                    new_stop_loss=potential_new_stop_price,
                )
            else:
                logger.debug(
                    f"[{symbol}] Calculated trailing stop {potential_new_stop_price:.5f} is not better than current {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, skipping update."
                )
        else:
            logger.debug(
                f"[{symbol}] Profit {profit_in_atr:.2f} ATR. Trailing stop conditions not met yet or no beneficial move calculated."
            )

    def _handle_kline_message(self, message):
        """Callback for processing real-time kline data. Dispatches to correct symbol's data."""
        try:
            # Extract symbol from WebSocket message
            topic = message.get("topic", "")
            parts = topic.split(".")  # e.g., "kline.3.XLMUSDT"
            if len(parts) < 3:
                logger.warning(f"Malformed kline topic received: {topic}. Skipping.")
                return

            symbol = parts[2]
            if symbol not in self.config.symbols:
                logger.debug(
                    f"Received kline for unconfigured symbol {symbol}. Ignoring."
                )
                return

            data = message["data"][0]  # Assuming only one candle per message
            candle_time_ms = int(data["start"])
            current_candle_time = pd.to_datetime(candle_time_ms, unit="ms", utc=True)

            # Ensure market_data for this symbol and timeframe is initialized
            if (
                symbol not in self.market_data
            ):  # This should be initialized in __init__, but defensive check
                self.market_data[symbol] = {}
            if self.config.timeframe not in self.market_data[symbol]:
                # As a fallback if historical load somehow missed it or happened out of order
                logger.warning(
                    f"[{symbol}] Market data DataFrame for timeframe {self.config.timeframe} not found. Initializing empty DataFrame for WS. Indicators might produce NaNs initially."
                )
                self.market_data[symbol][self.config.timeframe] = pd.DataFrame(
                    columns=["open", "high", "low", "close", "volume", "turnover"],
                    index=pd.to_datetime([], utc=True),
                )  # Empty DF with correct columns and index type

            df = self.market_data[symbol][self.config.timeframe]

            # Important: Check if the candle is already processed or is older (re-connection/late message)
            if (
                self.last_processed_candle_time.get(symbol)
                and current_candle_time < self.last_processed_candle_time[symbol]
            ):
                logger.debug(
                    f"[{symbol}] Skipping older/already processed kline message for {current_candle_time} (last processed: {self.last_processed_candle_time[symbol]})"
                )
                return

            new_candle_data = {
                "open": float(data["open"]),
                "high": float(data["high"]),
                "low": float(data["low"]),
                "close": float(data["close"]),
                "volume": float(data["volume"]),
                "turnover": float(data["turnover"]),
            }
            new_candle = pd.DataFrame([new_candle_data], index=[current_candle_time])

            # Update or append candle
            if current_candle_time in df.index:
                # Update existing row if it's the current (unclosed) candle
                df.loc[current_candle_time, new_candle.columns] = new_candle.iloc[0]
                logger.debug(
                    f"[{symbol}] Updated existing candle data for {current_candle_time}."
                )
            else:
                # Append new row (newly closed candle)
                df = pd.concat([df, new_candle]).sort_index()
                # Ensure we don't grow the DataFrame indefinitely
                # We need enough lookback for the strategy's indicators + any filter warm-up
                current_strategy = self.strategies.get(symbol)
                required_lookback = self.config.lookback_periods  # Default fallback
                if current_strategy:
                    required_lookback = max(
                        self.config.lookback_periods,
                        current_strategy.atr_period,  # Ensure ATR period is covered
                        getattr(
                            current_strategy, "fast_st_period", 0
                        ),  # Safe access for Ehlers
                        getattr(
                            current_strategy, "slow_st_period", 0
                        ),  # Safe access for Ehlers
                        (
                            getattr(current_strategy, "filter_poles", 0) * 2
                        ),  # For recursive filter warm-up (0 if not Ehlers)
                    )
                else:
                    logger.warning(
                        f"[{symbol}] Strategy not found for dynamic lookback calculation, using default config lookback."
                    )

                df = df.iloc[-required_lookback:].copy()
                self.last_processed_candle_time[symbol] = (
                    current_candle_time  # Update last processed time for new candles
                )
                logger.debug(
                    f"[{symbol}] Appended new candle: {current_candle_time}. DataFrame size: {len(df)}"
                )

            self.market_data[symbol][self.config.timeframe] = df

            # Schedule strategy cycle and trailing stop update for THIS symbol as a task thread-safely
            self.loop.call_soon_threadsafe(
                asyncio.create_task, self._async_kline_processing(symbol)
            )

        except Exception as e:
            logger.error(
                f"Error handling kline message for {symbol}: {e}", exc_info=True
            )

    async def _async_kline_processing(self, symbol: str):
        """Asynchronous part of kline message processing (runs strategy, updates trailing stop) for a specific symbol."""
        current_strategy = self.strategies.get(symbol)
        # Ensure strategy and market data are available for this symbol before processing
        symbol_market_data_for_timeframe = self.market_data.get(symbol, {}).get(
            self.config.timeframe
        )

        if (
            current_strategy
            and symbol_market_data_for_timeframe is not None
            and not symbol_market_data_for_timeframe.empty
        ):
            # 1. Calculate indicators for this symbol's strategy using the latest raw market data
            await current_strategy.calculate_indicators(self.market_data[symbol])

            # 2. Generate signal for this symbol using the *updated internal indicators* of the strategy
            signal = await current_strategy.generate_signal()
            if signal and signal.action != "HOLD":
                await self.process_signal(signal)
            else:
                logger.debug(
                    f"[{symbol}] No actionable signal generated or signal to HOLD."
                )

            # 3. Update trailing stop for this symbol if a position is open
            if self.positions.get(symbol):
                await self._update_trailing_stop_loss(symbol)

            # 4. Display current price and indicator values for monitoring
            df_indicators = current_strategy.indicators.get(self.config.timeframe)
            if df_indicators is not None and not df_indicators.empty:
                current_close = df_indicators.iloc[-1]["close"]

                # Check for specific strategy type to log relevant indicators
                if current_strategy.__class__.__name__ == "SupertrendStrategy":
                    supertrend_value = df_indicators.iloc[-1].get("supertrend", np.nan)
                    logger.info(
                        f"[{symbol}] Current Price: {current_close:.5f}, Supertrend: {supertrend_value:.5f}"
                    )
                elif (
                    current_strategy.__class__.__name__
                    == "EhlersSupertrendCrossStrategy"
                ):
                    fast_st = df_indicators.iloc[-1].get("supertrend_fast", np.nan)
                    slow_st = df_indicators.iloc[-1].get("supertrend_slow", np.nan)
                    logger.info(
                        f"[{symbol}] Current Price: {current_close:.5f}, Fast ST: {fast_st:.5f}, Slow ST: {slow_st:.5f}"
                    )
            else:
                logger.debug(
                    f"[{symbol}] No indicators available yet for {self.config.timeframe} after calculation. Raw data size: {len(self.market_data[symbol].get(self.config.timeframe, {}).get(self.config.timeframe, []))}"
                )
        else:
            logger.debug(
                f"[{symbol}] Skipping _async_kline_processing: strategy or sufficient market data not available."
            )

    def _handle_private_message(self, message):
        """Callback for private websocket messages (positions, orders, wallet)."""
        try:
            topic = message.get("topic")
            # Private streams typically carry account-wide updates or symbol-specific within data
            if topic == "position":
                # Position updates may be for one or all symbols. Best to refresh all positions for accuracy.
                self.loop.call_soon_threadsafe(
                    asyncio.create_task, self.get_positions()
                )
            elif topic == "order":
                # Order updates usually include symbol, but refreshing all positions and potentially balance covers fills.
                logger.info(f"Order update received: {message['data']}")
                # For advanced order book integration, this would parse order IDs and update local order status.
            elif topic == "wallet":
                self.loop.call_soon_threadsafe(
                    asyncio.create_task, self.update_account_balance()
                )
        except Exception as e:
            logger.error(f"Error handling private message: {e}", exc_info=True)

    async def run_strategies_cycle(self):
        """This method is deprecated as kline messages now directly trigger per-symbol processing.
        Kept for structural compatibility but no longer actively used in the main loop.
        """
        logger.debug(
            "`run_strategies_cycle` called. This method is deprecated; kline messages directly trigger strategy processing."
        )
        # Previously, this would iterate through strategies and call _run_single_strategy_cycle.
        # Now, _async_kline_processing (triggered by WS) takes over this role per symbol.
        # This function could be repurposed for slower, less frequent global checks if needed.

    def _save_state(self):
        """Persists the bot's critical state to a file."""
        state = {
            "positions": {
                s: asdict(p) if p else None for s, p in self.positions.items()
            },
            "balance": str(self.balance),  # Convert Decimal to string for serialization
            "strategies_state": {
                symbol: {
                    "last_signal": asdict(s.last_signal) if s.last_signal else None,
                    "signal_confirmed": s.signal_confirmed,
                    "signal_candle_time": s.signal_candle_time.isoformat()
                    if s.signal_candle_time
                    else None,
                }
                for symbol, s in self.strategies.items()
            },
            "last_processed_candle_time": {
                s: t.isoformat() if t else None
                for s, t in self.last_processed_candle_time.items()
            },
        }
        try:
            with open("bot_state.pkl", "wb") as f:
                pickle.dump(state, f)
            logger.debug("Bot state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save bot state: {e}", exc_info=True)

    def _load_state(self):
        """Loads the bot's critical state from a file."""
        try:
            if os.path.exists("bot_state.pkl"):
                with open("bot_state.pkl", "rb") as f:
                    state = pickle.load(f)

                    # Load positions
                    loaded_positions = state.get("positions", {})
                    if not isinstance(
                        loaded_positions, dict
                    ):  # Defensive check for malformed state
                        logger.warning(
                            f"Unexpected type for 'positions' in state file: {type(loaded_positions)}. Resetting."
                        )
                        loaded_positions = {}

                    for (
                        symbol
                    ) in self.config.symbols:  # Iterate over configured symbols
                        pos_data = loaded_positions.get(symbol)
                        if pos_data:
                            try:
                                # Ensure Decimal conversions are robust and handle None from potential missing keys
                                self.positions[symbol] = Position(
                                    symbol=pos_data["symbol"],
                                    side=pos_data["side"],
                                    size=to_decimal(pos_data["size"]),
                                    avg_price=to_decimal(pos_data["avg_price"]),
                                    unrealized_pnl=to_decimal(
                                        pos_data["unrealized_pnl"]
                                    ),
                                    mark_price=to_decimal(pos_data["mark_price"]),
                                    leverage=pos_data["leverage"],
                                    entry_signal_price=to_decimal(
                                        pos_data["entry_signal_price"]
                                    )
                                    if pos_data.get("entry_signal_price")
                                    else None,
                                    initial_stop_loss=to_decimal(
                                        pos_data["initial_stop_loss"]
                                    )
                                    if pos_data.get("initial_stop_loss")
                                    else None,
                                    trailing_stop_loss=to_decimal(
                                        pos_data["trailing_stop_loss"]
                                    )
                                    if pos_data.get("trailing_stop_loss")
                                    else None,
                                    take_profit=to_decimal(pos_data["take_profit"])
                                    if pos_data.get("take_profit")
                                    else None,
                                )
                            except Exception as e:
                                logger.error(
                                    f"[{symbol}] Error loading position data from state: {e}. Resetting position for this symbol.",
                                    exc_info=True,
                                )
                                self.positions[symbol] = None
                        else:
                            self.positions[symbol] = None

                    self.balance = to_decimal(state.get("balance", "0"))

                    # Load strategy-specific states
                    loaded_strategies_state = state.get("strategies_state", {})
                    if not isinstance(loaded_strategies_state, dict):  # Defensive check
                        logger.warning(
                            f"Unexpected type for 'strategies_state' in state file: {type(loaded_strategies_state)}. Resetting."
                        )
                        loaded_strategies_state = {}

                    for symbol, strat_state in loaded_strategies_state.items():
                        if (
                            symbol in self.strategies
                        ):  # Only load for actively configured strategies
                            try:
                                # Access strategy instance and load its state
                                strategy_instance = self.strategies[symbol]
                                if strat_state.get("last_signal"):
                                    strategy_instance.last_signal = StrategySignal(
                                        **strat_state["last_signal"]
                                    )
                                strategy_instance.signal_confirmed = strat_state.get(
                                    "signal_confirmed", False
                                )
                                if strat_state.get("signal_candle_time"):
                                    strategy_instance.signal_candle_time = (
                                        datetime.fromisoformat(
                                            strat_state["signal_candle_time"]
                                        )
                                    )
                            except Exception as e:
                                logger.error(
                                    f"[{symbol}] Error loading strategy state: {e}. Resetting state for this strategy.",
                                    exc_info=True,
                                )
                                strategy_instance.last_signal = None
                                strategy_instance.signal_confirmed = False
                                strategy_instance.signal_candle_time = None
                        else:
                            logger.warning(
                                f"Strategy state for unconfigured symbol {symbol} found in state file. Skipping."
                            )

                    # Load last processed candle times
                    loaded_last_processed_times = state.get(
                        "last_processed_candle_time", {}
                    )
                    # Ensure loaded_last_processed_times is a dict, not a string (Fix for AttributeError)
                    if isinstance(loaded_last_processed_times, dict):
                        for (
                            symbol
                        ) in self.config.symbols:  # Iterate over configured symbols
                            time_str = loaded_last_processed_times.get(symbol)
                            if time_str:
                                try:
                                    self.last_processed_candle_time[symbol] = (
                                        datetime.fromisoformat(time_str)
                                    )
                                except ValueError:
                                    logger.error(
                                        f"[{symbol}] Invalid datetime format for last_processed_candle_time: '{time_str}'. Resetting to None.",
                                        exc_info=True,
                                    )
                                    self.last_processed_candle_time[symbol] = None
                            else:
                                self.last_processed_candle_time[symbol] = (
                                    None  # Explicitly set None if string was None
                                )
                    else:
                        logger.warning(
                            f"Unexpected type for last_processed_candle_time in state file: {type(loaded_last_processed_times)}. Resetting to fresh."
                        )
                        self.last_processed_candle_time = dict.fromkeys(
                            self.config.symbols
                        )

                    logger.info("Bot state loaded successfully.")
            else:
                logger.info("No saved bot state found, starting fresh.")
        except Exception as e:
            logger.critical(
                f"Failed to load bot state: {e}. Starting fresh and resetting all state variables.",
                exc_info=True,
            )
            # If state loading fails, ensure all critical variables are reset to defaults for all symbols
            self.positions = dict.fromkeys(self.config.symbols)
            self.balance = to_decimal("0")
            for strategy_instance in self.strategies.values():
                strategy_instance.last_signal = None
                strategy_instance.signal_confirmed = False
                strategy_instance.signal_candle_time = None
            self.last_processed_candle_time = dict.fromkeys(self.config.symbols)

    async def start(self):
        """Starts the trading bot, initializes connections, and begins the trading loop."""
        self.is_running = True
        self.loop = asyncio.get_running_loop()  # Store the event loop
        await self.initialize()

        # Subscribe to kline streams for all configured symbols
        for symbol in self.config.symbols:
            self.public_ws.kline_stream(
                callback=self._handle_kline_message,
                symbol=symbol,
                interval=self.config.timeframe,
            )
            logger.info(
                f"Subscribed to kline stream for {symbol} on {self.config.timeframe}."
            )

        # Private streams (position, order, wallet) are typically global for the account
        self.private_ws.position_stream(callback=self._handle_private_message)
        self.private_ws.order_stream(callback=self._handle_private_message)
        self.private_ws.wallet_stream(callback=self._handle_private_message)
        logger.info("Subscribed to private streams (position, order, wallet).")

        logger.info(
            "Trading bot started successfully. Waiting for market data and signals (driven by kline updates)..."
        )

        # Keep the main task alive. Core logic is now event-driven by WebSocket kline messages.
        while self.is_running:
            await asyncio.sleep(
                1
            )  # Sleep to prevent busy-waiting, can add other high-level checks here

    async def stop(self):
        """Stops the trading bot, closes connections, and saves final state."""
        self.is_running = False
        logger.info("Stopping trading bot...")

        # Close WebSocket connections gracefully
        if self.public_ws:
            self.public_ws.exit()
            logger.info("Public WebSocket disconnected.")
        if self.private_ws:
            self.private_ws.exit()
            logger.info("Private WebSocket disconnected.")

        self._save_state()  # Save final state on graceful shutdown
        logger.info("Trading bot stopped and state saved.")


# --- MAIN EXECUTION BLOCK ---

if __name__ == "__main__":
    if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
        logger.critical(
            "API keys are not set. Please create a .env file with BYBIT_API_KEY and BYBIT_API_SECRET."
        )
        sys.exit(1)

    bot_config = Config()

    # Instantiate strategies for each symbol
    all_strategies: dict[str, BaseStrategy] = {}
    for symbol in bot_config.symbols:
        if bot_config.strategy_name == "Supertrend":
            all_strategies[symbol] = SupertrendStrategy(
                symbol=symbol, config=bot_config
            )
        elif bot_config.strategy_name == "EhlersSupertrendCross":
            all_strategies[symbol] = EhlersSupertrendCrossStrategy(
                symbol=symbol, config=bot_config
            )
        else:
            logger.critical(
                f"Unknown strategy specified in config: {bot_config.strategy_name}. Exiting."
            )
            sys.exit(1)

    bot = BybitTradingBot(
        config=bot_config, strategies=all_strategies
    )  # Pass the dictionary of strategies

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot gracefully stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"An unhandled critical exception occurred: {e}", exc_info=True)
    finally:
        # Ensure stop is called even if an exception occurs
        if bot.is_running:  # Only try to stop if it was running (i.e., not already stopped due to an error)
            asyncio.run(bot.stop())
        else:
            logger.info(
                "Bot was not actively running when finally block executed, skipping explicit stop."
            )
