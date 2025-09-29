import asyncio
import logging
import os
import pickle
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Context, Decimal, getcontext
from enum import Enum
from logging.handlers import RotatingFileHandler
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

DECIMAL_CONTEXT = Context(prec=50)
getcontext().prec = 28

load_dotenv()


class NeonColors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_WHITE = "\033[97m"


class NeonFormatter(logging.Formatter):
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
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def setup_logging():
    log = logging.getLogger()
    log.setLevel(logging.INFO)

    detailed_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    neon_formatter = NeonFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(neon_formatter)

    file_handler = RotatingFileHandler(
        "supertrend_bot.log", maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    log.addHandler(console_handler)
    log.addHandler(file_handler)

    return log


logger = setup_logging()


class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"


class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"


@dataclass
class MarketInfo:
    symbol: str
    tick_size: Decimal
    lot_size: Decimal

    def format_price(self, price: float) -> str:
        return str(
            Decimal(str(price), DECIMAL_CONTEXT).quantize(
                self.tick_size, rounding=ROUND_DOWN
            )
        )

    def format_quantity(self, quantity: float) -> str:
        return str(
            Decimal(str(quantity), DECIMAL_CONTEXT).quantize(
                self.lot_size, rounding=ROUND_DOWN
            )
        )


@dataclass
class Position:
    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal
    leverage: int
    entry_signal_price: Decimal | None = None
    initial_stop_loss: Decimal | None = None
    trailing_stop_loss: Decimal | None = None
    take_profit: Decimal | None = None


@dataclass
class StrategySignal:
    action: str
    symbol: str
    strength: float = 1.0
    stop_loss: float | None = None
    take_profit: float | None = None
    signal_price: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = False

    symbols: list[str] = field(
        default_factory=lambda: ["XLMUSDT", "LINKUSDT", "DOTUSDT", "TRUMPUSDT"]
    )
    category: str = "linear"

    risk_per_trade_pct: float = 0.005
    leverage: int = 20

    reconnect_attempts: int = 5

    strategy_name: str = "EhlersSupertrendCross"
    timeframe: str = "1"
    lookback_periods: int = 200

    strategy_params: dict[str, Any] = field(
        default_factory=lambda: {
            "supertrend_period": 7,
            "supertrend_multiplier": 2.5,
            "atr_period": 10,
            "ehlers_fast_supertrend_period": 3,
            "ehlers_fast_supertrend_multiplier": 1.0,
            "ehlers_slow_supertrend_period": 7,
            "ehlers_slow_supertrend_multiplier": 2.0,
            "ehlers_filter_alpha": 0.5,
            "ehlers_filter_poles": 1,
            "signal_confirmation_candles": 0,
            "take_profit_atr_multiplier": 0.75,
            "trailing_stop_loss_atr_multiplier": 0.6,
            "trailing_stop_loss_activation_atr_multiplier": 0.3,
            "break_even_profit_atr_multiplier": 0.2,
        }
    )


class BaseStrategy(ABC):
    def __init__(self, symbol: str, config: Config):
        self.symbol = symbol
        self.config = config
        self.indicators = {}
        self.primary_timeframe = config.timeframe
        self.last_signal: StrategySignal | None = None
        self.signal_confirmed = False
        self.signal_candle_time: datetime | None = None

        self.atr_period = self.config.strategy_params.get("atr_period", 14)

    @abstractmethod
    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        pass

    @abstractmethod
    async def generate_signal(
        self, data: dict[str, pd.DataFrame]
    ) -> StrategySignal | None:
        pass

    async def _confirm_signal(self, current_candle_time: datetime) -> bool:
        confirmation_candles_needed = self.config.strategy_params.get(
            "signal_confirmation_candles", 1
        )
        if confirmation_candles_needed == 0:
            self.signal_confirmed = True
            return True

        if self.last_signal and not self.signal_confirmed and self.signal_candle_time:
            df = self.indicators.get(self.primary_timeframe)
            if df is None or df.empty or self.signal_candle_time not in df.index:
                logger.debug(
                    f"DataFrame for {self.primary_timeframe} is empty or signal_candle_time {self.signal_candle_time} not in index for confirmation."
                )
                return False

            try:
                signal_idx = df.index.get_loc(self.signal_candle_time, method="bfill")
                current_idx = df.index.get_loc(current_candle_time, method="bfill")
            except KeyError:
                logger.warning(
                    f"Could not find signal_candle_time {self.signal_candle_time} or current_candle_time {current_candle_time} in DataFrame index for signal confirmation."
                )
                return False

            if current_idx - signal_idx >= confirmation_candles_needed:
                self.signal_confirmed = True
                logger.info(
                    f"Signal for {self.last_signal.action} confirmed after {confirmation_candles_needed} candles."
                )
                return True
        return False


class SupertrendStrategy(BaseStrategy):
    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, config)
        self.supertrend_period = self.config.strategy_params.get(
            "supertrend_period", 10
        )
        self.supertrend_multiplier = self.config.strategy_params.get(
            "supertrend_multiplier", 3.0
        )

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        df = data.get(self.primary_timeframe)
        min_data_needed = max(self.supertrend_period, self.atr_period)
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(
                f"Insufficient data for Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles)."
            )
            return

        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.ewm(span=self.atr_period, adjust=False).mean()

        hl2 = (df["high"] + df["low"]) / 2
        df["upperband"] = hl2 + (self.supertrend_multiplier * df["atr"])
        df["lowerband"] = hl2 - (self.supertrend_multiplier * df["atr"])
        df["in_uptrend"] = True

        for current in range(1, len(df.index)):
            previous = current - 1
            if (
                df.loc[df.index[current], "close"]
                > df.loc[df.index[previous], "upperband"]
            ):
                df.loc[df.index[current], "in_uptrend"] = True
            elif (
                df.loc[df.index[current], "close"]
                < df.loc[df.index[previous], "lowerband"]
            ):
                df.loc[df.index[current], "in_uptrend"] = False
            else:
                df.loc[df.index[current], "in_uptrend"] = df.loc[
                    df.index[previous], "in_uptrend"
                ]

                if (
                    df.loc[df.index[current], "in_uptrend"]
                    and df.loc[df.index[current], "lowerband"]
                    < df.loc[df.index[previous], "lowerband"]
                ):
                    df.loc[df.index[current], "lowerband"] = df.loc[
                        df.index[previous], "lowerband"
                    ]

                if (
                    not df.loc[df.index[current], "in_uptrend"]
                    and df.loc[df.index[current], "upperband"]
                    > df.loc[df.index[previous], "upperband"]
                ):
                    df.loc[df.index[current], "upperband"] = df.loc[
                        df.index[previous], "upperband"
                    ]

        df["supertrend"] = np.where(df["in_uptrend"], df["lowerband"], df["upperband"])
        self.indicators[self.primary_timeframe] = df.copy()

    async def generate_signal(
        self, data: dict[str, pd.DataFrame]
    ) -> StrategySignal | None:
        await self.calculate_indicators(data)

        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            return None

        df_cleaned = df.dropna(subset=["supertrend", "atr"]).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug(
                "DataFrame too small after dropping NaNs for signal generation."
            )
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        if self.last_signal:
            if (self.last_signal.action == "BUY" and not current["in_uptrend"]) or (
                self.last_signal.action == "SELL" and current["in_uptrend"]
            ):
                logger.info(
                    f"Trend changed opposite to pending signal ({self.last_signal.action}), resetting pending signal."
                )
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None

            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(
                        f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}."
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
                stop_loss=float(current["supertrend"]),
                signal_price=float(current["close"]),
                metadata={"reason": "Supertrend flipped to UP"},
            )
        elif previous["in_uptrend"] and not current["in_uptrend"]:
            signal_to_generate = StrategySignal(
                action="SELL",
                symbol=self.symbol,
                strength=1.0,
                stop_loss=float(current["supertrend"]),
                signal_price=float(current["close"]),
                metadata={"reason": "Supertrend flipped to DOWN"},
            )

        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(
                f"PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}. Waiting for confirmation (0 for immediate)."
            )
            return None

        return None


class EhlersSupertrendCrossStrategy(BaseStrategy):
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

    def _recursive_low_pass_filter(self, data: pd.Series) -> pd.Series:
        if data.empty:
            return pd.Series(dtype=float)

        filtered_data = data.copy()

        for _ in range(self.filter_poles):
            filtered_data = filtered_data.ewm(
                alpha=self.filter_alpha, adjust=False
            ).mean()

        return filtered_data

    async def calculate_indicators(self, data: dict[str, pd.DataFrame]):
        df = data.get(self.primary_timeframe)
        min_data_needed = max(
            self.fast_st_period,
            self.slow_st_period,
            self.atr_period,
            (self.filter_poles * 2),
        )
        if df is None or df.empty or len(df) < min_data_needed:
            logger.debug(
                f"Insufficient data for Ehlers Supertrend calculation ({len(df) if df is not None else 0} < {min_data_needed} candles)."
            )
            return

        df_filtered = df.copy()
        df_filtered["filtered_close"] = self._recursive_low_pass_filter(
            df_filtered["close"]
        )
        df_filtered["filtered_high"] = self._recursive_low_pass_filter(
            df_filtered["high"]
        )
        df_filtered["filtered_low"] = self._recursive_low_pass_filter(
            df_filtered["low"]
        )

        df_filtered.dropna(
            subset=["filtered_close", "filtered_high", "filtered_low"], inplace=True
        )

        if df_filtered.empty or len(df_filtered) < self.atr_period:
            logger.debug(
                f"DataFrame too small after filtering for Ehlers Supertrend calculation ({len(df_filtered)} < {self.atr_period} candles)."
            )
            return

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

        if df_filtered["atr_filtered"].isnull().all() or (
            not df_filtered["atr_filtered"].empty
            and df_filtered["atr_filtered"].iloc[-1] == 0
        ):
            logger.debug(
                "ATR filtered values are all NaN or last ATR is zero, cannot calculate Supertrend."
            )
            return

        hl2_filtered_fast = (
            df_filtered["filtered_high"] + df_filtered["filtered_low"]
        ) / 2
        df_filtered["upperband_fast"] = hl2_filtered_fast + (
            self.fast_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["lowerband_fast"] = hl2_filtered_fast - (
            self.fast_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["in_uptrend_fast"] = True

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

                if (
                    df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"]
                    and df_filtered.loc[df_filtered.index[current], "lowerband_fast"]
                    < df_filtered.loc[df_filtered.index[previous], "lowerband_fast"]
                ):
                    df_filtered.loc[df_filtered.index[current], "lowerband_fast"] = (
                        df_filtered.loc[df_filtered.index[previous], "lowerband_fast"]
                    )

                if (
                    not df_filtered.loc[df_filtered.index[current], "in_uptrend_fast"]
                    and df_filtered.loc[df_filtered.index[current], "upperband_fast"]
                    > df_filtered.loc[df_filtered.index[previous], "upperband_fast"]
                ):
                    df_filtered.loc[df_filtered.index[current], "upperband_fast"] = (
                        df_filtered.loc[df_filtered.index[previous], "upperband_fast"]
                    )

        df_filtered["supertrend_fast"] = np.where(
            df_filtered["in_uptrend_fast"],
            df_filtered["lowerband_fast"],
            df_filtered["upperband_fast"],
        )

        hl2_filtered_slow = (
            df_filtered["filtered_high"] + df_filtered["filtered_low"]
        ) / 2
        df_filtered["upperband_slow"] = hl2_filtered_slow + (
            self.slow_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["lowerband_slow"] = hl2_filtered_slow - (
            self.slow_st_multiplier * df_filtered["atr_filtered"]
        )
        df_filtered["in_uptrend_slow"] = True

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

                if (
                    df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"]
                    and df_filtered.loc[df_filtered.index[current], "lowerband_slow"]
                    < df_filtered.loc[df_filtered.index[previous], "lowerband_slow"]
                ):
                    df_filtered.loc[df_filtered.index[current], "lowerband_slow"] = (
                        df_filtered.loc[df_filtered.index[previous], "lowerband_slow"]
                    )

                if (
                    not df_filtered.loc[df_filtered.index[current], "in_uptrend_slow"]
                    and df_filtered.loc[df_filtered.index[current], "upperband_slow"]
                    > df_filtered.loc[df_filtered.index[previous], "upperband_slow"]
                ):
                    df_filtered.loc[df_filtered.index[current], "upperband_slow"] = (
                        df_filtered.loc[df_filtered.index[previous], "upperband_slow"]
                    )

        df_filtered["supertrend_slow"] = np.where(
            df_filtered["in_uptrend_slow"],
            df_filtered["lowerband_slow"],
            df_filtered["upperband_slow"],
        )

        self.indicators[self.primary_timeframe] = df_filtered.copy()

    async def generate_signal(
        self, data: dict[str, pd.DataFrame]
    ) -> StrategySignal | None:
        await self.calculate_indicators(data)

        df = self.indicators.get(self.primary_timeframe)
        if df is None or df.empty or len(df) < 2:
            logger.debug(
                "Insufficient data for Ehlers Supertrend Cross signal generation."
            )
            return None

        df_cleaned = df.dropna(
            subset=[
                "supertrend_fast",
                "supertrend_slow",
                "atr_filtered",
                "filtered_close",
            ]
        ).copy()
        if df_cleaned.empty or len(df_cleaned) < 2:
            logger.debug(
                "DataFrame too small after dropping NaNs for Ehlers Supertrend Cross signal generation."
            )
            return None

        current = df_cleaned.iloc[-1]
        previous = df_cleaned.iloc[-2]

        in_uptrend_overall = current["in_uptrend_slow"]

        if self.last_signal:
            if (self.last_signal.action == "BUY" and not in_uptrend_overall) or (
                self.last_signal.action == "SELL" and in_uptrend_overall
            ):
                logger.info(
                    f"Overall trend based on slow ST changed opposite to pending signal ({self.last_signal.action}), resetting pending signal."
                )
                self.last_signal = None
                self.signal_confirmed = False
                self.signal_candle_time = None
                return None

            if not self.signal_confirmed:
                if await self._confirm_signal(current.name):
                    logger.info(
                        f"Confirmed PENDING TRADE SIGNAL: {self.last_signal.action} for {self.symbol}."
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
        )

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
                stop_loss=float(current["supertrend_slow"]),
                take_profit=take_profit_val,
                signal_price=float(current["close"]),
                metadata={"reason": "Ehlers Fast ST Crosses Above Slow ST (Uptrend)"},
            )

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
                stop_loss=float(current["supertrend_slow"]),
                take_profit=take_profit_val,
                signal_price=float(current["close"]),
                metadata={"reason": "Ehlers Fast ST Crosses Below Slow ST (Downtrend)"},
            )

        if signal_to_generate:
            self.last_signal = signal_to_generate
            self.signal_candle_time = current.name
            logger.info(
                f"PENDING TRADE SIGNAL: {signal_to_generate.action} for {self.symbol}. Reason: {signal_to_generate.metadata['reason']}. SL: {signal_to_generate.stop_loss:.5f}, TP: {signal_to_generate.take_profit if signal_to_generate.take_profit else 'N/A':.5f}. Waiting for confirmation (0 for immediate)."
            )
            return None

        return None


class BybitTradingBot:
    def __init__(
        self,
        config: Config,
        strategies: dict[str, BaseStrategy],
        session: HTTP | None = None,
    ):
        self.config = config
        self.strategies = strategies

        self.session = session or HTTP(
            testnet=config.testnet, api_key=config.api_key, api_secret=config.api_secret
        )
        self.public_ws = WebSocket(
            testnet=config.testnet,
            channel_type=config.category,
            api_key=config.api_key,
            api_secret=config.api_secret,
        )
        self.private_ws = WebSocket(
            testnet=config.testnet,
            channel_type="private",
            api_key=config.api_key,
            api_secret=config.api_secret,
        )

        self.market_info: dict[str, MarketInfo] = {}
        self.market_data: dict[str, dict[str, pd.DataFrame]] = {}
        self.positions: dict[str, Position | None] = {}
        self.balance: Decimal = Decimal("0", DECIMAL_CONTEXT)
        self.is_running = False
        self.loop: asyncio.AbstractEventLoop | None = None
        self.last_processed_candle_time: dict[str, datetime | None] = {}
        self.order_tasks: dict[str, asyncio.Task] = {}

        self._load_state()

    async def initialize(self):
        logger.info("Initializing bot...")
        for symbol in self.config.symbols:
            await self._load_market_info(symbol)
            await self._load_historical_data(symbol)
            self.market_data[symbol] = {}
        await self.update_account_balance()
        await self.get_positions()
        logger.info("Bot initialization complete.")

    async def _load_market_info(self, symbol: str):
        try:
            response = self.session.get_instruments_info(
                category=self.config.category, symbol=symbol
            )
            if response and response["retCode"] == 0:
                instrument = response["result"]["list"][0]
                self.market_info[symbol] = MarketInfo(
                    symbol=symbol,
                    tick_size=Decimal(
                        instrument["priceFilter"]["tickSize"], DECIMAL_CONTEXT
                    ),
                    lot_size=Decimal(
                        instrument["lotSizeFilter"]["qtyStep"], DECIMAL_CONTEXT
                    ),
                )
                logger.info(
                    f"Market info loaded for {symbol}: Tick Size {self.market_info[symbol].tick_size}, Lot Size {self.market_info[symbol].lot_size}"
                )
            else:
                raise Exception(
                    f"Failed to get instrument info for {symbol}: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.critical(
                f"Critical Error loading market info for {symbol}: {e}", exc_info=True
            )
            sys.exit(1)

    async def _load_historical_data(self, symbol: str):
        logger.info(
            f"Loading historical data for {symbol} on {self.config.timeframe} timeframe..."
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
                df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
                df.set_index("time", inplace=True)
                df = df.astype(float)
                df.sort_index(inplace=True)
                self.market_data[symbol][self.config.timeframe] = df
                if not df.empty:
                    self.last_processed_candle_time[symbol] = df.index[-1]
                logger.info(
                    f"Loaded {len(df)} historical candles for {symbol}. Last candle: {self.last_processed_candle_time.get(symbol)}"
                )
            else:
                raise Exception(
                    f"Failed to get kline data for {symbol}: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.critical(
                f"Critical Error loading historical data for {symbol}: {e}",
                exc_info=True,
            )
            sys.exit(1)

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
        if symbol not in self.market_info:
            logger.error(f"Cannot place order for {symbol}, market info not loaded.")
            return None

        market_info = self.market_info[symbol]

        try:
            formatted_qty = market_info.format_quantity(quantity)
            if float(formatted_qty) <= float(market_info.lot_size):
                logger.warning(
                    f"Formatted quantity for order is too small ({formatted_qty}), skipping. Original: {quantity}. Minimum lot size: {market_info.lot_size}"
                )
                return None

            params = {
                "category": self.config.category,
                "symbol": symbol,
                "side": side.value,
                "orderType": order_type.value,
                "qty": formatted_qty,
                "isLeverage": 1,
                "tpslMode": "Full",
            }

            if order_type == OrderType.LIMIT and price is not None:
                params["price"] = market_info.format_price(price)

            if stop_loss is not None:
                params["stopLoss"] = market_info.format_price(stop_loss)
                params["slTriggerBy"] = "MarkPrice"

            if take_profit is not None:
                params["takeProfit"] = market_info.format_price(take_profit)
                params["tpTriggerBy"] = "MarkPrice"

            logger.debug(f"Attempting to place order with params: {params}")
            response = self.session.place_order(**params)

            if response and response["retCode"] == 0:
                order_id = response["result"]["orderId"]
                logger.info(
                    f"TRADE: Order placed successfully: ID {order_id}, Side {side.value}, Qty {formatted_qty}, SL: {stop_loss}, TP: {take_profit} for {symbol}"
                )
                return order_id
            error_msg = (
                response.get("retMsg", "Unknown error")
                if response
                else "No response from API"
            )
            logger.error(
                f"Failed to place order for {symbol}: {error_msg} (Code: {response.get('retCode', 'N/A')})"
            )
            return None
        except Exception as e:
            logger.error(f"Error placing order for {symbol}: {e}", exc_info=True)
            return None

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> str | None:
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
        if (
            symbol not in self.positions
            or self.positions[symbol] is None
            or self.positions[symbol].side != position_side
        ):
            logger.warning(
                f"No active {position_side} position found for {symbol} for SL/TP update. Current position: {self.positions.get(symbol)}"
            )
            return

        current_position = self.positions[symbol]
        market_info = self.market_info[symbol]

        params = {
            "category": self.config.category,
            "symbol": symbol,
        }
        updated_any = False

        if new_stop_loss is not None:
            if (
                current_position.trailing_stop_loss is None
                or new_stop_loss != current_position.trailing_stop_loss
            ):
                params["stopLoss"] = market_info.format_price(float(new_stop_loss))
                params["slTriggerBy"] = "MarkPrice"
                logger.info(
                    f"Updating stop loss for {symbol} {current_position.side} position from {current_position.trailing_stop_loss:.5f if current_position.trailing_stop_loss else 'N/A'} to {new_stop_loss:.5f}"
                )
                current_position.trailing_stop_loss = new_stop_loss
                updated_any = True
            else:
                logger.debug(
                    f"New stop loss {new_stop_loss:.5f} is same as current {current_position.trailing_stop_loss:.5f}, skipping SL update for {symbol}."
                )

        if new_take_profit is not None:
            if (
                current_position.take_profit is None
                or new_take_profit != current_position.take_profit
            ):
                params["takeProfit"] = market_info.format_price(float(new_take_profit))
                params["tpTriggerBy"] = "MarkPrice"
                logger.info(
                    f"Updating take profit for {symbol} {current_position.side} position from {current_position.take_profit:.5f if current_position.take_profit else 'N/A'} to {new_take_profit:.5f}"
                )
                current_position.take_profit = new_take_profit
                updated_any = True
            else:
                logger.debug(
                    f"New take profit {new_take_profit:.5f} is same as current {current_position.take_profit:.5f}, skipping TP update for {symbol}."
                )

        if not updated_any:
            logger.debug(
                f"No changes in stop loss or take profit requested for {symbol}, skipping API call."
            )
            return

        try:
            response = self.session.set_trading_stop(**params)
            if response and response["retCode"] == 0:
                logger.info(
                    f"Successfully sent SL/TP update request for {symbol} {current_position.side} position."
                )
            else:
                error_msg = (
                    response.get("retMsg", "Unknown error")
                    if response
                    else "No response from API"
                )
                logger.error(
                    f"Failed to update SL/TP for {symbol}: {error_msg} (Code: {response.get('retCode', 'N/A')})"
                )
        except Exception as e:
            logger.error(f"Error updating SL/TP for {symbol}: {e}", exc_info=True)
        finally:
            self._save_state()

    async def get_positions(self):
        try:
            response = self.session.get_positions(
                category=self.config.category,
            )
            if response and response["retCode"] == 0 and response["result"]["list"]:
                for pos_data in response["result"]["list"]:
                    symbol = pos_data["symbol"]
                    size = Decimal(pos_data["size"], DECIMAL_CONTEXT)
                    if size > 0:
                        current_position_side = pos_data["side"]

                        existing_initial_sl = (
                            self.positions.get(symbol)
                            and self.positions[symbol].initial_stop_loss
                            if self.positions.get(symbol)
                            and self.positions[symbol].side == current_position_side
                            else None
                        )
                        existing_entry_signal_price = (
                            self.positions.get(symbol)
                            and self.positions[symbol].entry_signal_price
                            if self.positions.get(symbol)
                            and self.positions[symbol].side == current_position_side
                            else None
                        )

                        bybit_sl = (
                            Decimal(pos_data["stopLoss"], DECIMAL_CONTEXT)
                            if pos_data.get("stopLoss")
                            else None
                        )
                        bybit_tp = (
                            Decimal(pos_data["takeProfit"], DECIMAL_CONTEXT)
                            if pos_data.get("takeProfit")
                            else None
                        )

                        final_trailing_sl = (
                            bybit_sl
                            if bybit_sl is not None
                            else (
                                self.positions.get(symbol)
                                and self.positions[symbol].trailing_stop_loss
                                if self.positions.get(symbol)
                                and self.positions[symbol].side == current_position_side
                                else None
                            )
                        )
                        final_take_profit = (
                            bybit_tp
                            if bybit_tp is not None
                            else (
                                self.positions.get(symbol)
                                and self.positions[symbol].take_profit
                                if self.positions.get(symbol)
                                and self.positions[symbol].side == current_position_side
                                else None
                            )
                        )

                        self.positions[symbol] = Position(
                            symbol=symbol,
                            side=current_position_side,
                            size=size,
                            avg_price=Decimal(pos_data["avgPrice"], DECIMAL_CONTEXT),
                            unrealized_pnl=Decimal(
                                pos_data["unrealisedPnl"], DECIMAL_CONTEXT
                            ),
                            mark_price=Decimal(pos_data["markPrice"], DECIMAL_CONTEXT),
                            leverage=int(pos_data.get("leverage", 1)),
                            entry_signal_price=existing_entry_signal_price,
                            initial_stop_loss=existing_initial_sl,
                            trailing_stop_loss=final_trailing_sl,
                            take_profit=final_take_profit,
                        )
                        logger.debug(
                            f"Position updated from API for {symbol}: {self.positions[symbol]}"
                        )
                    else:
                        self.positions[symbol] = None
                        logger.debug(
                            f"No active position found for {symbol} via API response."
                        )
            else:
                self.positions = dict.fromkeys(self.config.symbols)
                logger.debug(
                    "No active positions found for any symbol (API response list empty or retCode issue)."
                )
            self._save_state()
        except Exception as e:
            logger.error(f"Error getting positions: {e}", exc_info=True)

    async def update_account_balance(self):
        try:
            response = self.session.get_wallet_balance(accountType="UNIFIED")
            if response and response["retCode"] == 0:
                balance_data = response["result"]["list"][0]
                self.balance = Decimal(balance_data["totalEquity"], DECIMAL_CONTEXT)
                logger.info(f"Account balance updated: {self.balance:.2f} USDT")
            else:
                logger.error(
                    f"Failed to update balance: {response.get('retMsg', 'Unknown error')}"
                )
        except Exception as e:
            logger.error(f"Error updating balance: {e}", exc_info=True)

    def _calculate_position_size(self, signal: StrategySignal) -> float:
        if signal.stop_loss is None or signal.signal_price is None:
            logger.error(
                f"Cannot calculate position size for {signal.symbol} without a valid stop-loss and signal price from the strategy."
            )
            return 0.0

        if signal.symbol not in self.market_info:
            logger.error(
                f"Market info not loaded for {signal.symbol}, cannot calculate position size."
            )
            return 0.0

        market_info = self.market_info[signal.symbol]

        risk_amount_usd = self.balance * Decimal(
            str(self.config.risk_per_trade_pct), DECIMAL_CONTEXT
        )

        stop_loss_distance_raw = Decimal("0", DECIMAL_CONTEXT)
        signal_price_dec = Decimal(str(signal.signal_price), DECIMAL_CONTEXT)
        stop_loss_dec = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)

        if signal.action == "BUY":
            stop_loss_distance_raw = signal_price_dec - stop_loss_dec
        elif signal.action == "SELL":
            stop_loss_distance_raw = stop_loss_dec - signal_price_dec

        if (
            stop_loss_distance_raw <= Decimal("0", DECIMAL_CONTEXT)
            or stop_loss_distance_raw < market_info.tick_size
        ):
            logger.warning(
                f"Stop loss distance for {signal.symbol} is non-positive or too small ({stop_loss_distance_raw:.5f} < {market_info.tick_size}), cannot calculate position size safely. Returning 0."
            )
            return 0.0

        position_size_asset_unleveraged = risk_amount_usd / stop_loss_distance_raw
        leveraged_position_size_asset = position_size_asset_unleveraged * Decimal(
            str(self.config.leverage), DECIMAL_CONTEXT
        )
        formatted_position_size = Decimal(
            market_info.format_quantity(float(leveraged_position_size_asset)),
            DECIMAL_CONTEXT,
        )

        logger.info(
            f"Risk Amount: {risk_amount_usd:.2f} USDT, SL Distance: {stop_loss_distance_raw:.5f} USDT, "
            f"Calculated Position Size (Leveraged & Formatted): {formatted_position_size:.5f} {signal.symbol}"
        )

        return float(formatted_position_size)

    async def process_signal(self, signal: StrategySignal):
        logger.info(
            f"Processing signal: {signal.action} {signal.symbol} (Reason: {signal.metadata.get('reason', 'N/A')})"
        )

        symbol = signal.symbol
        current_position = self.positions.get(symbol)
        current_strategy = self.strategies.get(symbol)

        if current_strategy is None:
            logger.error(
                f"No strategy found for symbol {symbol}, cannot process signal."
            )
            return

        if (
            symbol not in self.market_data
            or self.market_data[symbol].get(self.config.timeframe) is None
            or self.market_data[symbol][self.config.timeframe].empty
        ):
            logger.warning(
                f"No market data available for {symbol} for signal processing, skipping."
            )
            return

        current_close_price = self.market_data[symbol][self.config.timeframe].iloc[-1][
            "close"
        ]

        df_indicators = current_strategy.indicators.get(self.config.timeframe)
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
            tp_multiplier = Decimal(
                str(self.config.strategy_params.get("take_profit_atr_multiplier", 1.0)),
                DECIMAL_CONTEXT,
            )
            signal_price_dec = Decimal(str(signal.signal_price), DECIMAL_CONTEXT)
            current_atr_dec = Decimal(str(current_atr), DECIMAL_CONTEXT)

            if signal.action == "BUY":
                signal.take_profit = float(
                    signal_price_dec + current_atr_dec * tp_multiplier
                )
            elif signal.action == "SELL":
                signal.take_profit = float(
                    signal_price_dec - current_atr_dec * tp_multiplier
                )
            logger.info(
                f"Dynamically calculated Take Profit for {symbol}: {signal.take_profit:.5f}"
            )

        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            logger.warning(
                f"Calculated position size for {symbol} is zero or too small, aborting trade."
            )
            return

        if current_position:
            if (signal.action == "BUY" and current_position.side == "Sell") or (
                signal.action == "SELL" and current_position.side == "Buy"
            ):
                logger.info(
                    f"Reversing position for {symbol}: Closing existing {current_position.side} ({current_position.size:.5f}) to open {signal.action} ({position_size:.5f})."
                )

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
                        f"Close order {close_order_id} placed for {symbol}. Waiting for position to settle before opening new one..."
                    )
                    await asyncio.sleep(5)
                    await self.get_positions()
                    await self.update_account_balance()

                    if not self.positions.get(symbol):
                        logger.info(
                            f"Existing position for {symbol} successfully closed. Proceeding to open new one."
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
                            self.positions[symbol] = Position(
                                symbol=symbol,
                                side=signal.action,
                                size=Decimal(str(position_size), DECIMAL_CONTEXT),
                                avg_price=Decimal(
                                    str(current_close_price), DECIMAL_CONTEXT
                                ),
                                unrealized_pnl=Decimal("0", DECIMAL_CONTEXT),
                                mark_price=Decimal(
                                    str(current_close_price), DECIMAL_CONTEXT
                                ),
                                leverage=self.config.leverage,
                                entry_signal_price=Decimal(
                                    str(signal.signal_price), DECIMAL_CONTEXT
                                )
                                if signal.signal_price
                                else None,
                                initial_stop_loss=Decimal(
                                    str(signal.stop_loss), DECIMAL_CONTEXT
                                )
                                if signal.stop_loss
                                else None,
                                trailing_stop_loss=Decimal(
                                    str(signal.stop_loss), DECIMAL_CONTEXT
                                )
                                if signal.stop_loss
                                else None,
                                take_profit=Decimal(
                                    str(signal.take_profit), DECIMAL_CONTEXT
                                )
                                if signal.take_profit
                                else None,
                            )
                            self._save_state()
                        else:
                            logger.error(
                                f"Failed to open new position for {symbol} after closing existing one. Check logs for details."
                            )
                    else:
                        logger.error(
                            f"Failed to confirm closure of existing position for {symbol}. Aborting new trade to prevent conflicting positions."
                        )
                else:
                    logger.error(
                        f"Failed to place order to close existing position for {symbol}. Aborting new trade."
                    )
                return

            if (signal.action == "BUY" and current_position.side == "Buy") or (
                signal.action == "SELL" and current_position.side == "Sell"
            ):
                logger.info(
                    f"Signal to {signal.action} received for {symbol}, but already in a {current_position.side} position. Considering updating SL/TP."
                )

                new_sl_to_set: Decimal | None = None
                new_tp_to_set: Decimal | None = None

                if signal.stop_loss is not None:
                    new_signal_sl = Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)

                    should_update_initial_sl = False
                    if (
                        self.position.initial_stop_loss is None
                        or (
                            self.position.side == "Buy"
                            and new_signal_sl > self.position.initial_stop_loss
                        )
                        or (
                            self.position.side == "SELL"
                            and new_signal_sl < self.position.initial_stop_loss
                        )
                    ):
                        should_update_initial_sl = True

                    if should_update_initial_sl:
                        self.position.initial_stop_loss = new_signal_sl
                        logger.info(
                            f"Internal initial stop loss updated to new strategy SL: {new_signal_sl:.5f}"
                        )

                        if (
                            self.position.trailing_stop_loss is None
                            or (
                                self.position.side == "Buy"
                                and new_signal_sl > self.position.trailing_stop_loss
                            )
                            or (
                                self.position.side == "Sell"
                                and new_signal_sl < self.position.trailing_stop_loss
                            )
                        ):
                            new_sl_to_set = new_signal_sl
                            logger.info(
                                f"Trailing stop loss on exchange will be moved to new initial SL: {new_signal_sl:.5f}"
                            )

                if signal.take_profit is not None:
                    new_signal_tp = Decimal(str(signal.take_profit), DECIMAL_CONTEXT)

                    should_update_tp = False
                    if (
                        self.position.take_profit is None
                        or (
                            self.position.side == "Buy"
                            and new_signal_tp > self.position.take_profit
                        )
                        or (
                            self.position.side == "Sell"
                            and new_signal_tp < self.position.take_profit
                        )
                    ):
                        should_update_tp = True

                    if should_update_tp:
                        new_tp_to_set = new_signal_tp
                        logger.info(
                            f"Take profit updated to a more favorable level: {new_tp_to_set:.5f}"
                        )

                if new_sl_to_set or new_tp_to_set:
                    await self.update_stop_loss_and_take_profit(
                        self.position.side, new_sl_to_set, new_tp_to_set
                    )
                else:
                    logger.debug(
                        "No beneficial SL/TP updates from current signal, skipping API call."
                    )
                return

        if not self.position:
            logger.info(
                f"Opening new {signal.action} position with size {position_size:.5f}."
            )
            order_id = await self.place_market_order(
                side=OrderSide.BUY if signal.action == "BUY" else OrderSide.SELL,
                quantity=position_size,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            if order_id:
                self.position = Position(
                    symbol=self.config.symbol,
                    side=signal.action,
                    size=Decimal(str(position_size), DECIMAL_CONTEXT),
                    avg_price=Decimal(str(current_close_price), DECIMAL_CONTEXT),
                    unrealized_pnl=Decimal("0", DECIMAL_CONTEXT),
                    mark_price=Decimal(str(current_close_price), DECIMAL_CONTEXT),
                    leverage=self.config.leverage,
                    entry_signal_price=Decimal(
                        str(signal.signal_price), DECIMAL_CONTEXT
                    )
                    if signal.signal_price
                    else None,
                    initial_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)
                    if signal.stop_loss
                    else None,
                    trailing_stop_loss=Decimal(str(signal.stop_loss), DECIMAL_CONTEXT)
                    if signal.stop_loss
                    else None,
                    take_profit=Decimal(str(signal.take_profit), DECIMAL_CONTEXT)
                    if signal.take_profit
                    else None,
                )
                self._save_state()
            else:
                logger.error("Failed to open new position. Check logs for details.")
            return

    async def _update_trailing_stop_loss(self):
        if (
            not self.position
            or self.position.entry_signal_price is None
            or self.position.initial_stop_loss is None
            or self.strategy.indicators.get(self.config.timeframe) is None
            or self.strategy.indicators[self.config.timeframe].empty
        ):
            logger.debug(
                "Cannot update trailing stop: no position, no entry price/initial SL, or no indicators."
            )
            return

        current_df = self.strategy.indicators[self.config.timeframe].iloc[-1]
        current_price = Decimal(str(current_df["close"]), DECIMAL_CONTEXT)

        current_atr = Decimal(
            str(current_df.get("atr_filtered", current_df.get("atr", 0.0))),
            DECIMAL_CONTEXT,
        )
        if current_atr <= 0:
            logger.warning(
                "ATR not available or non-positive for trailing stop calculation."
            )
            return

        activation_multiplier = Decimal(
            str(
                self.config.strategy_params.get(
                    "trailing_stop_loss_activation_atr_multiplier", 0.5
                )
            ),
            DECIMAL_CONTEXT,
        )
        trailing_multiplier = Decimal(
            str(
                self.config.strategy_params.get(
                    "trailing_stop_loss_atr_multiplier", 0.75
                )
            ),
            DECIMAL_CONTEXT,
        )
        break_even_profit_multiplier = Decimal(
            str(
                self.config.strategy_params.get("break_even_profit_atr_multiplier", 0.2)
            ),
            DECIMAL_CONTEXT,
        )

        profit_in_usd = Decimal("0", DECIMAL_CONTEXT)
        if self.position.side == "Buy":
            profit_in_usd = current_price - self.position.entry_signal_price
        elif self.position.side == "Sell":
            profit_in_usd = self.position.entry_signal_price - current_price

        profit_in_atr = (
            profit_in_usd / current_atr
            if current_atr > 0
            else Decimal("0", DECIMAL_CONTEXT)
        )

        potential_new_stop_price: Decimal | None = None
        current_trailing_sl = self.position.trailing_stop_loss
        initial_sl = self.position.initial_stop_loss

        if self.position.side == "Buy":
            if profit_in_atr >= break_even_profit_multiplier:
                calculated_be_sl = self.position.entry_signal_price + (
                    current_atr * Decimal("0.05", DECIMAL_CONTEXT)
                )
                if (
                    current_trailing_sl is None
                    or calculated_be_sl > current_trailing_sl
                ):
                    potential_new_stop_price = max(calculated_be_sl, initial_sl)

            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price - (current_atr * trailing_multiplier)
                if (
                    potential_new_stop_price is None
                    or trailing_point_sl > potential_new_stop_price
                ):
                    potential_new_stop_price = max(trailing_point_sl, initial_sl)

            if potential_new_stop_price and potential_new_stop_price < initial_sl:
                potential_new_stop_price = initial_sl

        elif self.position.side == "Sell":
            if profit_in_atr >= break_even_profit_multiplier:
                calculated_be_sl = self.position.entry_signal_price - (
                    current_atr * Decimal("0.05", DECIMAL_CONTEXT)
                )
                if (
                    current_trailing_sl is None
                    or calculated_be_sl < current_trailing_sl
                ):
                    potential_new_stop_price = min(calculated_be_sl, initial_sl)

            if profit_in_atr >= activation_multiplier:
                trailing_point_sl = current_price + (current_atr * trailing_multiplier)
                if (
                    potential_new_stop_price is None
                    or trailing_point_sl < potential_new_stop_price
                ):
                    potential_new_stop_price = min(trailing_point_sl, initial_sl)

            if potential_new_stop_price and potential_new_stop_price > initial_sl:
                potential_new_stop_price = initial_sl

        if potential_new_stop_price is not None:
            should_update_exchange = False
            if (
                current_trailing_sl is None
                or (
                    self.position.side == "Buy"
                    and potential_new_stop_price > current_trailing_sl
                )
                or (
                    self.position.side == "Sell"
                    and potential_new_stop_price < current_trailing_sl
                )
            ):
                should_update_exchange = True

            if should_update_exchange:
                logger.info(
                    f"Trailing SL update triggered for {self.position.side} position. Old: {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, New: {potential_new_stop_price:.5f}"
                )
                await self.update_stop_loss_and_take_profit(
                    self.position.side, new_stop_loss=potential_new_stop_price
                )
            else:
                logger.debug(
                    f"Calculated trailing stop {potential_new_stop_price:.5f} is not better than current {current_trailing_sl:.5f if current_trailing_sl else 'N/A'}, skipping update."
                )
        else:
            logger.debug(
                f"Profit {profit_in_atr:.2f} ATR. Trailing stop conditions not met yet or no beneficial move calculated."
            )

    def _handle_kline_message(self, message):
        try:
            data = message["data"][0]
            candle_time_ms = int(data["start"])
            current_candle_time = pd.to_datetime(candle_time_ms, unit="ms", utc=True)

            if (
                self.last_processed_candle_time
                and current_candle_time < self.last_processed_candle_time
            ):
                logger.debug(
                    f"Skipping older/already processed kline message for {current_candle_time} (last processed: {self.last_processed_candle_time})"
                )
                return

            df = self.market_data.get(self.config.timeframe)
            if df is None or df.empty:
                logger.warning(
                    f"Market data for {self.config.timeframe} is not initialized or empty. Waiting for more data before processing kline."
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

            if current_candle_time in df.index:
                df.loc[current_candle_time, new_candle.columns] = new_candle.iloc[0]
                logger.debug(f"Updated existing candle data for {current_candle_time}.")
            else:
                df = pd.concat([df, new_candle]).sort_index()
                required_lookback = max(
                    self.config.lookback_periods,
                    self.strategy.atr_period,
                    getattr(self.strategy, "fast_st_period", 0),
                    getattr(self.strategy, "slow_st_period", 0),
                    (getattr(self.strategy, "filter_poles", 0) * 2),
                )
                df = df.iloc[-required_lookback:].copy()
                self.last_processed_candle_time = current_candle_time
                logger.debug(
                    f"Appended new candle: {current_candle_time}. DataFrame size: {len(df)}"
                )

            self.market_data[self.config.timeframe] = df

            self.loop.call_soon_threadsafe(
                asyncio.create_task, self._async_kline_processing()
            )

        except Exception as e:
            logger.error(f"Error handling kline message: {e}", exc_info=True)

    async def _async_kline_processing(self):
        await self.run_strategy_cycle()
        if self.position:
            await self._update_trailing_stop_loss()

        df = self.strategy.indicators.get(self.config.timeframe)
        if df is not None and not df.empty:
            current_close = df.iloc[-1]["close"]

            if self.config.strategy_name == "Supertrend":
                supertrend_value = df.iloc[-1].get("supertrend", np.nan)
                logger.info(
                    f"Current Price: {current_close:.5f}, Supertrend: {supertrend_value:.5f}"
                )
            elif self.config.strategy_name == "EhlersSupertrendCross":
                fast_st = df.iloc[-1].get("supertrend_fast", np.nan)
                slow_st = df.iloc[-1].get("supertrend_slow", np.nan)
                logger.info(
                    f"Current Price: {current_close:.5f}, Fast ST: {fast_st:.5f}, Slow ST: {slow_st:.5f}"
                )
        else:
            logger.debug(
                f"No indicators available yet for {self.config.timeframe}. Raw data size: {len(self.market_data.get(self.config.timeframe, []))}"
            )

    def _handle_private_message(self, message):
        try:
            topic = message.get("topic")
            if topic == "position":
                self.loop.call_soon_threadsafe(asyncio.create_task, self.get_position())
            elif topic == "order":
                logger.info(f"Order update received: {message['data']}")
            elif topic == "wallet":
                self.loop.call_soon_threadsafe(
                    asyncio.create_task, self.update_account_balance()
                )
        except Exception as e:
            logger.error(f"Error handling private message: {e}", exc_info=True)

    async def run_strategy_cycle(self):
        signal = await self.strategy.generate_signal(self.market_data)
        if signal and signal.action != "HOLD":
            await self.process_signal(signal)
        else:
            logger.debug("No actionable signal generated or signal to HOLD.")

    def _save_state(self):
        state = {
            "position": asdict(self.position) if self.position else None,
            "balance": str(self.balance),
            "last_signal": asdict(self.strategy.last_signal)
            if self.strategy.last_signal
            else None,
            "signal_confirmed": self.strategy.signal_confirmed,
            "signal_candle_time": self.strategy.signal_candle_time.isoformat()
            if self.strategy.signal_candle_time
            else None,
            "last_processed_candle_time": self.last_processed_candle_time.isoformat()
            if self.last_processed_candle_time
            else None,
        }
        try:
            with open("bot_state.pkl", "wb") as f:
                pickle.dump(state, f)
            logger.debug("Bot state saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save bot state: {e}", exc_info=True)

    def _load_state(self):
        try:
            if os.path.exists("bot_state.pkl"):
                with open("bot_state.pkl", "rb") as f:
                    state = pickle.load(f)
                    if state.get("position"):
                        pos_data = state["position"]
                        self.position = Position(
                            symbol=pos_data["symbol"],
                            side=pos_data["side"],
                            size=Decimal(str(pos_data["size"]), DECIMAL_CONTEXT),
                            avg_price=Decimal(
                                str(pos_data["avg_price"]), DECIMAL_CONTEXT
                            ),
                            unrealized_pnl=Decimal(
                                str(pos_data["unrealized_pnl"]), DECIMAL_CONTEXT
                            ),
                            mark_price=Decimal(
                                str(pos_data["mark_price"]), DECIMAL_CONTEXT
                            ),
                            leverage=pos_data["leverage"],
                            entry_signal_price=Decimal(
                                str(pos_data["entry_signal_price"]), DECIMAL_CONTEXT
                            )
                            if pos_data["entry_signal_price"]
                            else None,
                            initial_stop_loss=Decimal(
                                str(pos_data["initial_stop_loss"]), DECIMAL_CONTEXT
                            )
                            if pos_data["initial_stop_loss"]
                            else None,
                            trailing_stop_loss=Decimal(
                                str(pos_data["trailing_stop_loss"]), DECIMAL_CONTEXT
                            )
                            if pos_data["trailing_stop_loss"]
                            else None,
                            take_profit=Decimal(
                                str(pos_data["take_profit"]), DECIMAL_CONTEXT
                            )
                            if pos_data["take_profit"]
                            else None,
                        )
                    self.balance = Decimal(state.get("balance", "0"), DECIMAL_CONTEXT)
                    if state.get("last_signal"):
                        self.strategy.last_signal = StrategySignal(
                            **state["last_signal"]
                        )
                    self.strategy.signal_confirmed = state.get(
                        "signal_confirmed", False
                    )
                    if state.get("signal_candle_time"):
                        self.strategy.signal_candle_time = datetime.fromisoformat(
                            state["signal_candle_time"]
                        )
                    if state.get("last_processed_candle_time"):
                        self.last_processed_candle_time = datetime.fromisoformat(
                            state["last_processed_candle_time"]
                        )
                    logger.info("Bot state loaded successfully.")
            else:
                logger.info("No saved bot state found, starting fresh.")
        except Exception as e:
            logger.critical(
                f"Failed to load bot state: {e}. Starting fresh and resetting all state variables.",
                exc_info=True,
            )
            self.position = None
            self.balance = Decimal("0", DECIMAL_CONTEXT)
            self.strategy.last_signal = None
            self.strategy.signal_confirmed = False
            self.strategy.signal_candle_time = None
            self.last_processed_candle_time = None

    async def start(self):
        self.is_running = True
        self.loop = asyncio.get_running_loop()
        await self.initialize()

        self.public_ws.kline_stream(
            callback=self._handle_kline_message,
            symbol=self.config.symbol,
            interval=self.config.timeframe,
        )
        self.private_ws.position_stream(callback=self._handle_private_message)
        self.private_ws.order_stream(callback=self._handle_private_message)
        self.private_ws.wallet_stream(callback=self._handle_private_message)

        logger.info(
            "Trading bot started successfully. Waiting for market data and signals..."
        )

        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self):
        self.is_running = False
        logger.info("Stopping trading bot...")

        if self.public_ws:
            self.public_ws.exit()
            logger.info("Public WebSocket disconnected.")
        if self.private_ws:
            self.private_ws.exit()
            logger.info("Private WebSocket disconnected.")

        self._save_state()
        logger.info("Trading bot stopped and state saved.")


if __name__ == "__main__":
    if not os.getenv("BYBIT_API_KEY") or not os.getenv("BYBIT_API_SECRET"):
        logger.critical(
            "API keys are not set. Please create a .env file with BYBIT_API_KEY and BYBIT_API_SECRET."
        )
        sys.exit(1)

    bot_config = Config()

    bot_strategy: BaseStrategy
    if bot_config.strategy_name == "Supertrend":
        bot_strategy = SupertrendStrategy(symbol=bot_config.symbol, config=bot_config)
    elif bot_config.strategy_name == "EhlersSupertrendCross":
        bot_strategy = EhlersSupertrendCrossStrategy(
            symbol=bot_config.symbol, config=bot_config
        )
    else:
        logger.critical(
            f"Unknown strategy specified in config: {bot_config.strategy_name}. Exiting."
        )
        sys.exit(1)

    bot = BybitTradingBot(config=bot_config, strategy=bot_strategy)

    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot gracefully stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"An unhandled critical exception occurred: {e}", exc_info=True)
    finally:
        if bot.is_running:
            asyncio.run(bot.stop())
        else:
            logger.info(
                "Bot was not actively running when finally block executed, skipping explicit stop."
            )
