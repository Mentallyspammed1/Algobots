# backtester.py
import concurrent.futures
import json
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from itertools import product
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Import your existing indicators module
try:
    from indicators import calculate_indicators
except ImportError:
    print("Warning: Could not import indicators module. Using dummy function.")

    def calculate_indicators(klines, config):
        # Dummy function for testing
        return {
            "supertrend": {"direction": 1, "supertrend": klines[-1]["close"] * 0.99},
            "rsi": 50,
            "fisher": 0,
            "macd": {"macd_line": 0, "signal_line": 0, "histogram": 0},
            "bollinger_bands": {
                "middle_band": klines[-1]["close"],
                "upper_band": 0,
                "lower_band": 0,
            },
        }


# Load environment variables
load_dotenv()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =====================================================================
# DATA STRUCTURES
# =====================================================================


@dataclass
class Trade:
    """Represents a single trade in the backtest"""

    entry_time: datetime
    exit_time: datetime | None
    side: str  # 'Buy' or 'Sell'
    entry_price: float
    exit_price: float | None
    quantity: float
    stop_loss: float
    take_profit: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""  # 'TP', 'SL', 'Signal', 'TrailingStop'
    peak_price: float = 0.0


@dataclass
class BacktestResult:
    """Contains backtest results and statistics"""

    trades: list[Trade]
    initial_balance: float
    final_balance: float
    total_return: float
    total_return_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    recovery_factor: float
    expectancy: float
    avg_trade_duration: float
    best_trade: Trade | None
    worst_trade: Trade | None
    equity_curve: list[float]
    drawdown_curve: list[float]
    timestamps: list[datetime]
    config: dict[str, Any]


# =====================================================================
# DATA FETCHER
# =====================================================================


class HistoricalDataFetcher:
    """Fetches historical kline data from Bybit"""

    def __init__(self, api_key: str, api_secret: str):
        self.session = HTTP(testnet=False, api_key=api_key, api_secret=api_secret)

    def fetch_historical_klines(
        self, symbol: str, interval: str, start_time: datetime, end_time: datetime
    ) -> pd.DataFrame:
        """Fetch historical klines from Bybit

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            interval: Kline interval ('1', '5', '15', '30', '60', '240', 'D')
            start_time: Start datetime
            end_time: End datetime

        Returns:
            DataFrame with OHLCV data

        """
        all_klines = []
        current_end = end_time

        # Convert interval to minutes for calculation
        interval_minutes = self._interval_to_minutes(interval)

        while current_end > start_time:
            # Bybit returns max 1000 klines per request
            current_start = max(
                start_time, current_end - timedelta(minutes=interval_minutes * 1000)
            )

            # Convert to milliseconds timestamp
            start_ms = int(current_start.timestamp() * 1000)
            end_ms = int(current_end.timestamp() * 1000)

            try:
                response = self.session.get_kline(
                    category="linear",
                    symbol=symbol,
                    interval=interval,
                    start=start_ms,
                    end=end_ms,
                    limit=1000,
                )

                if response["retCode"] == 0:
                    klines = response["result"]["list"]
                    if not klines:
                        break

                    # Convert to list of dicts
                    for k in klines:
                        all_klines.append(
                            {
                                "timestamp": int(k[0]),
                                "open": float(k[1]),
                                "high": float(k[2]),
                                "low": float(k[3]),
                                "close": float(k[4]),
                                "volume": float(k[5]),
                            }
                        )

                    # Update current_end for next iteration
                    oldest_timestamp = min(int(k[0]) for k in klines)
                    current_end = datetime.fromtimestamp(oldest_timestamp / 1000)

                    logger.info(f"Fetched {len(klines)} klines ending at {current_end}")
                    time.sleep(0.1)  # Rate limiting
                else:
                    logger.error(f"API Error: {response['retMsg']}")
                    break

            except Exception as e:
                logger.error(f"Error fetching klines: {e}")
                break

        if not all_klines:
            return pd.DataFrame()

        # Create DataFrame and sort by timestamp
        df = pd.DataFrame(all_klines)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Remove duplicates if any
        df = df.drop_duplicates(subset=["timestamp"], keep="first")

        logger.info(f"Total klines fetched: {len(df)}")
        return df

    def _interval_to_minutes(self, interval: str) -> int:
        """Convert interval string to minutes"""
        interval_map = {
            "1": 1,
            "3": 3,
            "5": 5,
            "15": 15,
            "30": 30,
            "60": 60,
            "120": 120,
            "240": 240,
            "360": 360,
            "720": 720,
            "D": 1440,
            "W": 10080,
            "M": 43200,
        }
        return interval_map.get(interval, 60)


# =====================================================================
# BACKTESTER ENGINE
# =====================================================================


class Backtester:
    """Main backtesting engine"""

    def __init__(self, initial_balance: float = 10000, commission: float = 0.0006):
        self.initial_balance = initial_balance
        self.commission = commission
        self.reset()

    def reset(self):
        """Reset backtester state"""
        self.balance = self.initial_balance
        self.trades = []
        self.current_position = None
        self.equity_curve = []  # Initialize as empty
        self.timestamps = []  # Initialize as empty
        self.last_supertrend = {"direction": 0, "value": 0}

    def run_backtest(
        self, df: pd.DataFrame, config: dict[str, Any], progress_callback=None
    ) -> BacktestResult:
        """Run backtest on historical data

        Args:
            df: DataFrame with OHLCV data
            config: Strategy configuration
            progress_callback: Optional callback for progress updates

        Returns:
            BacktestResult object

        """
        self.reset()

        # Need at least 200 candles for indicators
        lookback = 200

        for i in range(lookback, len(df)):
            # Progress update
            if progress_callback and i % 100 == 0:
                progress_callback(i / len(df))

            # Get current and historical data
            current_candle = df.iloc[i]
            historical_data = df.iloc[max(0, i - lookback) : i + 1]

            # Convert to format expected by indicators
            klines = historical_data.to_dict("records")

            # Calculate indicators
            indicators = calculate_indicators(klines, config)

            # Check for position management (SL, TP, Trailing Stop)
            if self.current_position:
                self._manage_position(current_candle, config)

            # Generate signals
            signal = self._generate_signal(indicators, config)

            # Execute trades
            if signal != 0:
                self._execute_trade(signal, current_candle, config, indicators)

            # Update equity curve
            current_equity = self._calculate_equity(current_candle)
            self.equity_curve.append(current_equity)
            self.timestamps.append(current_candle["datetime"])

            # Update last supertrend
            if "supertrend" in indicators:
                self.last_supertrend = indicators["supertrend"]

        # Close any open position at the end
        if self.current_position:
            self._close_position(df.iloc[-1], "End of Data")

        # Calculate statistics
        return self._calculate_statistics(config)

    def _generate_signal(self, indicators: dict, config: dict) -> int:
        """Generate trading signal based on indicators
        Returns: 1 for buy, -1 for sell, 0 for no signal
        """
        st = indicators.get("supertrend", {})
        rsi = indicators.get("rsi", 50)
        fisher = indicators.get("fisher", 0)

        # Buy signal
        if (
            st.get("direction") == 1
            and self.last_supertrend.get("direction", 0) == -1
            and rsi < config.get("rsi_overbought", 70)
            and fisher > config.get("fisher_threshold", 0)
        ):
            return 1

        # Sell signal
        if (
            st.get("direction") == -1
            and self.last_supertrend.get("direction", 0) == 1
            and rsi > config.get("rsi_oversold", 30)
            and fisher < -config.get("fisher_threshold", 0)
        ):
            return -1

        return 0

    def _execute_trade(
        self, signal: int, candle: pd.Series, config: dict, indicators: dict
    ):
        """Execute a trade based on signal"""
        # Close opposite position if exists
        if self.current_position:
            if (signal == 1 and self.current_position.side == "Sell") or (
                signal == -1 and self.current_position.side == "Buy"
            ):
                self._close_position(candle, "Opposite Signal")

        # Skip if we already have a position in the same direction
        if self.current_position:
            return

        # Calculate position size
        risk_pct = config.get("riskPct", 1.0) / 100
        sl_pct = config.get("stopLossPct", 1.0) / 100
        tp_pct = config.get("takeProfitPct", 2.0) / 100

        side = "Buy" if signal == 1 else "Sell"
        entry_price = candle["close"]

        # Calculate SL and TP
        if side == "Buy":
            stop_loss = entry_price * (1 - sl_pct)
            take_profit = entry_price * (1 + tp_pct)
        else:
            stop_loss = entry_price * (1 + sl_pct)
            take_profit = entry_price * (1 - tp_pct)

        # Calculate position size based on risk
        risk_amount = self.balance * risk_pct
        price_risk = abs(entry_price - stop_loss)

        if price_risk > 0:
            quantity = risk_amount / price_risk
        else:
            quantity = 0

        # Check minimum position value
        position_value = quantity * entry_price
        if position_value < 10:  # Min $10 position
            return

        # Create trade
        trade = Trade(
            entry_time=candle["datetime"],
            exit_time=None,
            side=side,
            entry_price=entry_price,
            exit_price=None,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            peak_price=entry_price,
        )

        # Deduct commission
        commission_cost = position_value * self.commission
        self.balance -= commission_cost

        self.current_position = trade

    def _manage_position(self, candle: pd.Series, config: dict):
        """Manage open position (check SL, TP, trailing stop)"""
        if not self.current_position:
            return

        trade = self.current_position
        current_price = candle["close"]

        # Update peak price for trailing stop
        if trade.side == "Buy":
            trade.peak_price = max(trade.peak_price, candle["high"])
        else:
            trade.peak_price = min(trade.peak_price, candle["low"])

        # Check stop loss
        if (trade.side == "Buy" and candle["low"] <= trade.stop_loss) or (
            trade.side == "Sell" and candle["high"] >= trade.stop_loss
        ):
            self._close_position(candle, "Stop Loss", trade.stop_loss)
            return

        # Check take profit
        if (trade.side == "Buy" and candle["high"] >= trade.take_profit) or (
            trade.side == "Sell" and candle["low"] <= trade.take_profit
        ):
            self._close_position(candle, "Take Profit", trade.take_profit)
            return

        # Trailing stop logic
        trailing_pct = config.get("trailingStopPct", 0.5) / 100

        if trade.side == "Buy":
            new_stop = trade.peak_price * (1 - trailing_pct)
            if new_stop > trade.stop_loss and new_stop > trade.entry_price:
                trade.stop_loss = new_stop

                # Check if trailing stop is hit
                if candle["low"] <= trade.stop_loss:
                    self._close_position(candle, "Trailing Stop", trade.stop_loss)
        else:
            new_stop = trade.peak_price * (1 + trailing_pct)
            if new_stop < trade.stop_loss and new_stop < trade.entry_price:
                trade.stop_loss = new_stop

                # Check if trailing stop is hit
                if candle["high"] >= trade.stop_loss:
                    self._close_position(candle, "Trailing Stop", trade.stop_loss)

    def _close_position(
        self, candle: pd.Series, reason: str, exit_price: float | None = None
    ):
        """Close current position"""
        if not self.current_position:
            return

        trade = self.current_position
        trade.exit_time = candle["datetime"]
        trade.exit_price = exit_price if exit_price else candle["close"]
        trade.exit_reason = reason

        # Calculate PnL
        if trade.side == "Buy":
            price_change = trade.exit_price - trade.entry_price
        else:
            price_change = trade.entry_price - trade.exit_price

        gross_pnl = price_change * trade.quantity

        # Deduct commission for exit
        commission_cost = abs(trade.quantity * trade.exit_price * self.commission)
        net_pnl = gross_pnl - commission_cost

        trade.pnl = net_pnl
        trade.pnl_pct = (net_pnl / (trade.entry_price * trade.quantity)) * 100

        # Update balance
        self.balance += net_pnl

        # Add to trades list
        self.trades.append(trade)
        self.current_position = None

    def _calculate_equity(self, candle: pd.Series) -> float:
        """Calculate current equity including open position"""
        equity = self.balance

        if self.current_position:
            trade = self.current_position
            current_price = candle["close"]

            if trade.side == "Buy":
                unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
            else:
                unrealized_pnl = (trade.entry_price - current_price) * trade.quantity

            equity += unrealized_pnl

        return equity

    def _calculate_statistics(self, config: dict) -> BacktestResult:
        """Calculate backtest statistics"""
        # Basic statistics
        total_trades = len(self.trades)

        # Initialize drawdown and related variables to default values
        # in case no trades are made and the function returns early.
        drawdown = np.array([])
        max_drawdown_value = 0.0
        max_drawdown = 0.0

        if total_trades == 0:
            return BacktestResult(
                trades=self.trades,
                initial_balance=self.initial_balance,
                final_balance=self.balance,
                total_return=0,
                total_return_pct=0,
                win_rate=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_win=0,
                avg_loss=0,
                profit_factor=0,
                max_drawdown=0,
                max_drawdown_pct=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                calmar_ratio=0,
                recovery_factor=0,
                expectancy=0,
                avg_trade_duration=0,
                best_trade=None,
                worst_trade=None,
                equity_curve=self.equity_curve,
                drawdown_curve=drawdown.tolist(),
                timestamps=self.timestamps,
                config=config,
            )

        # Win/Loss statistics
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        win_rate = len(winning_trades) / total_trades * 100 if total_trades > 0 else 0

        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0

        # Profit factor
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Expectancy
        expectancy = (
            (
                avg_win * len(winning_trades) / total_trades
                - abs(avg_loss) * len(losing_trades) / total_trades
            )
            if total_trades > 0
            else 0
        )

        # Drawdown calculation
        equity_array = np.array(self.equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max * 100
        max_drawdown = abs(np.min(drawdown))
        max_drawdown_value = abs(np.min(equity_array - running_max))

        # Returns calculation
        total_return = self.balance - self.initial_balance
        total_return_pct = (total_return / self.initial_balance) * 100

        # Calculate daily returns for Sharpe/Sortino
        if len(self.equity_curve) > 1:
            returns = np.diff(self.equity_curve) / self.equity_curve[:-1]

            # Sharpe Ratio (annualized)
            if np.std(returns) > 0:
                sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
            else:
                sharpe_ratio = 0

            # Sortino Ratio (annualized)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0 and np.std(downside_returns) > 0:
                sortino_ratio = (
                    np.mean(returns) / np.std(downside_returns) * np.sqrt(252)
                )
            else:
                sortino_ratio = 0
        else:
            sharpe_ratio = 0
            sortino_ratio = 0

        # Calmar Ratio
        calmar_ratio = total_return_pct / max_drawdown if max_drawdown > 0 else 0

        # Recovery Factor
        recovery_factor = (
            total_return / max_drawdown_value if max_drawdown_value > 0 else 0
        )

        # Average trade duration
        durations = []
        for trade in self.trades:
            if trade.exit_time and trade.entry_time:
                duration = (
                    trade.exit_time - trade.entry_time
                ).total_seconds() / 3600  # in hours
                durations.append(duration)
        avg_trade_duration = np.mean(durations) if durations else 0

        # Best and worst trades
        best_trade = max(self.trades, key=lambda t: t.pnl) if self.trades else None
        worst_trade = min(self.trades, key=lambda t: t.pnl) if self.trades else None

        return BacktestResult(
            trades=self.trades,
            initial_balance=self.initial_balance,
            final_balance=self.balance,
            total_return=total_return,
            total_return_pct=total_return_pct,
            win_rate=win_rate,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown_value,
            max_drawdown_pct=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            recovery_factor=recovery_factor,
            expectancy=expectancy,
            avg_trade_duration=avg_trade_duration,
            best_trade=best_trade,
            worst_trade=worst_trade,
            equity_curve=self.equity_curve,
            drawdown_curve=drawdown.tolist(),
            timestamps=self.timestamps,
            config=config,
        )


# =====================================================================
# OPTIMIZER
# =====================================================================


class StrategyOptimizer:
    """Optimize strategy parameters using various methods"""

    def __init__(self, data: pd.DataFrame, initial_balance: float = 10000):
        self.data = data
        self.initial_balance = initial_balance
        self.results = []

    def grid_search(
        self,
        param_grid: dict[str, list],
        base_config: dict[str, Any],
        metric: str = "sharpe_ratio",
        n_jobs: int = -1,
    ) -> list[tuple[dict, BacktestResult]]:
        """Perform grid search optimization

        Args:
            param_grid: Dictionary of parameter names and their values to test
            base_config: Base configuration to use
            metric: Metric to optimize ('sharpe_ratio', 'total_return_pct', 'profit_factor', etc.)
            n_jobs: Number of parallel jobs (-1 for all CPUs)

        Returns:
            List of (config, result) tuples sorted by metric

        """
        # Generate all parameter combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        param_combinations = list(product(*param_values))

        total_combinations = len(param_combinations)
        logger.info(f"Testing {total_combinations} parameter combinations")

        # Prepare configs for parallel processing
        configs = []
        for combo in param_combinations:
            config = base_config.copy()
            for name, value in zip(param_names, combo, strict=False):
                config[name] = value
            configs.append(config)

        # Run backtests in parallel
        if n_jobs == -1:
            n_jobs = os.cpu_count()

        with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = []
            for config in configs:
                future = executor.submit(self._run_single_backtest, config)
                futures.append((config, future))

            results = []
            for i, (config, future) in enumerate(futures):
                try:
                    result = future.result(timeout=300)  # 5 minute timeout
                    results.append((config, result))

                    if (i + 1) % 10 == 0:
                        logger.info(f"Completed {i + 1}/{total_combinations} backtests")
                except Exception as e:
                    logger.error(f"Backtest failed for config {config}: {e}")

        # Sort by metric
        results.sort(key=lambda x: getattr(x[1], metric), reverse=True)

        self.results = results
        return results

    def random_search(
        self,
        param_ranges: dict[str, tuple[float, float]],
        base_config: dict[str, Any],
        n_trials: int = 100,
        metric: str = "sharpe_ratio",
        n_jobs: int = -1,
    ) -> list[tuple[dict, BacktestResult]]:
        """Perform random search optimization

        Args:
            param_ranges: Dictionary of parameter names and their (min, max) ranges
            base_config: Base configuration
            n_trials: Number of random trials
            metric: Metric to optimize
            n_jobs: Number of parallel jobs

        Returns:
            List of (config, result) tuples sorted by metric

        """
        configs = []
        for _ in range(n_trials):
            config = base_config.copy()
            for param, (min_val, max_val) in param_ranges.items():
                if isinstance(min_val, int) and isinstance(max_val, int):
                    config[param] = random.randint(min_val, max_val)
                else:
                    config[param] = random.uniform(min_val, max_val)
            configs.append(config)

        logger.info(f"Testing {n_trials} random parameter combinations")

        # Run backtests in parallel
        if n_jobs == -1:
            n_jobs = os.cpu_count()

        with concurrent.futures.ProcessPoolExecutor(max_workers=n_jobs) as executor:
            futures = []
            for config in configs:
                future = executor.submit(self._run_single_backtest, config)
                futures.append((config, future))

            results = []
            for i, (config, future) in enumerate(futures):
                try:
                    result = future.result(timeout=300)
                    results.append((config, result))

                    if (i + 1) % 10 == 0:
                        logger.info(f"Completed {i + 1}/{n_trials} backtests")
                except Exception as e:
                    logger.error(f"Backtest failed for config {config}: {e}")

        # Sort by metric
        results.sort(key=lambda x: getattr(x[1], metric), reverse=True)

        self.results = results
        return results

    def _run_single_backtest(self, config: dict[str, Any]) -> BacktestResult:
        """Run a single backtest with given config"""
        backtester = Backtester(initial_balance=self.initial_balance)
        result = backtester.run_backtest(self.data, config)
        return result

    def get_best_config(
        self, metric: str = "sharpe_ratio"
    ) -> tuple[dict, BacktestResult]:
        """Get the best configuration based on metric"""
        if not self.results:
            raise ValueError(
                "No optimization results available. Run optimization first."
            )

        best = max(self.results, key=lambda x: getattr(x[1], metric))
        return best

    def save_results(self, filepath: str):
        """Save optimization results to JSON file"""
        results_data = []
        for config, result in self.results:
            results_data.append(
                {
                    "config": config,
                    "metrics": {
                        "total_return_pct": result.total_return_pct,
                        "sharpe_ratio": result.sharpe_ratio,
                        "profit_factor": result.profit_factor,
                        "win_rate": result.win_rate,
                        "max_drawdown_pct": result.max_drawdown_pct,
                        "total_trades": result.total_trades,
                    },
                }
            )

        with open(filepath, "w") as f:
            json.dump(results_data, f, indent=2)

        logger.info(f"Results saved to {filepath}")


# =====================================================================
# VISUALIZATION
# =====================================================================


class BacktestVisualizer:
    """Visualize backtest results"""

    @staticmethod
    def plot_equity_curve(result: BacktestResult, save_path: str | None = None):
        """Plot equity curve and drawdown"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        # Equity curve
        ax1.plot(result.timestamps, result.equity_curve, label="Equity", linewidth=2)
        ax1.axhline(
            y=result.initial_balance,
            color="gray",
            linestyle="--",
            label="Initial Balance",
        )
        ax1.set_ylabel("Equity ($)")
        ax1.set_title("Equity Curve")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Drawdown
        ax2.fill_between(
            result.timestamps,
            result.drawdown_curve,
            0,
            color="red",
            alpha=0.3,
            label="Drawdown",
        )
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Date")
        ax2.set_title("Drawdown")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=100)
        plt.show()

    @staticmethod
    def plot_trade_distribution(result: BacktestResult, save_path: str | None = None):
        """Plot trade PnL distribution"""
        if not result.trades:
            logger.warning("No trades to plot")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        # PnL distribution
        pnls = [t.pnl for t in result.trades]
        ax1.hist(pnls, bins=30, edgecolor="black", alpha=0.7)
        ax1.axvline(x=0, color="red", linestyle="--")
        ax1.set_xlabel("PnL ($)")
        ax1.set_ylabel("Frequency")
        ax1.set_title("Trade PnL Distribution")
        ax1.grid(True, alpha=0.3)

        # Win/Loss pie chart
        wins = result.winning_trades
        losses = result.losing_trades
        ax2.pie(
            [wins, losses],
            labels=["Wins", "Losses"],
            autopct="%1.1f%%",
            colors=["green", "red"],
        )
        ax2.set_title(f"Win Rate: {result.win_rate:.1f}%")

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=100)
        plt.show()

    @staticmethod
    def plot_optimization_results(
        optimizer: StrategyOptimizer,
        param1: str,
        param2: str,
        metric: str = "sharpe_ratio",
        save_path: str | None = None,
    ):
        """Plot optimization results as heatmap"""
        if not optimizer.results:
            logger.warning("No optimization results to plot")
            return

        # Extract data for heatmap
        param1_values = []
        param2_values = []
        metric_values = []

        for config, result in optimizer.results:
            param1_values.append(config[param1])
            param2_values.append(config[param2])
            metric_values.append(getattr(result, metric))

        # Create pivot table
        df = pd.DataFrame(
            {param1: param1_values, param2: param2_values, metric: metric_values}
        )

        pivot = df.pivot_table(values=metric, index=param2, columns=param1)

        # Plot heatmap
        plt.figure(figsize=(10, 8))
        sns.heatmap(
            pivot, annot=True, fmt=".2f", cmap="YlOrRd", cbar_kws={"label": metric}
        )
        plt.title(f"Optimization Results: {metric}")
        plt.xlabel(param1)
        plt.ylabel(param2)

        if save_path:
            plt.savefig(save_path, dpi=100)
        plt.show()


# =====================================================================
# MAIN EXECUTION EXAMPLE
# =====================================================================


def main():
    """Example usage of the backtester and optimizer"""
    # Configuration
    symbol = "BTCUSDT"
    interval = "15"  # 15 minute candles
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 12, 1)

    # Base configuration for the strategy
    base_config = {
        "symbol": symbol,
        "interval": interval,
        "leverage": 10,
        "riskPct": 1.0,
        "stopLossPct": 1.0,
        "takeProfitPct": 2.0,
        "trailingStopPct": 0.5,
        "rsi_length": 14,
        "rsi_overbought": 70,
        "rsi_oversold": 30,
        "fisher_threshold": 0.5,
        "ef_period": 10,
        "macd_fast_period": 12,
        "macd_slow_period": 26,
        "macd_signal_period": 9,
        "bb_period": 20,
        "bb_std_dev": 2.0,
        "supertrend_length": 10,
        "supertrend_multiplier": 3.0,
    }

    # Initialize data fetcher
    logger.info("Fetching historical data...")
    fetcher = HistoricalDataFetcher(BYBIT_API_KEY, BYBIT_API_SECRET)
    df = fetcher.fetch_historical_klines(symbol, interval, start_date, end_date)

    if df.empty:
        logger.error("No data fetched. Exiting.")
        return

    logger.info(
        f"Fetched {len(df)} candles from {df['datetime'].min()} to {df['datetime'].max()}"
    )

    # Run single backtest
    logger.info("Running single backtest...")
    backtester = Backtester(initial_balance=10000)
    result = backtester.run_backtest(df, base_config)

    # Print results
    print("\n" + "=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"Initial Balance: ${result.initial_balance:,.2f}")
    print(f"Final Balance: ${result.final_balance:,.2f}")
    print(f"Total Return: ${result.total_return:,.2f} ({result.total_return_pct:.2f}%)")
    print(f"Total Trades: {result.total_trades}")
    print(f"Win Rate: {result.win_rate:.2f}%")
    print(f"Profit Factor: {result.profit_factor:.2f}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown: ${result.max_drawdown:,.2f} ({result.max_drawdown_pct:.2f}%)")
    print(f"Average Win: ${result.avg_win:,.2f}")
    print(f"Average Loss: ${result.avg_loss:,.2f}")
    print(f"Expectancy: ${result.expectancy:,.2f}")

    # Visualize results
    visualizer = BacktestVisualizer()
    if result.total_trades > 0:  # Only plot if there are trades
        visualizer.plot_equity_curve(result)
        visualizer.plot_trade_distribution(result)
    else:
        logger.warning("No trades generated in single backtest, skipping plotting.")

    # Optimization example
    logger.info("Running parameter optimization...")
    optimizer = StrategyOptimizer(df, initial_balance=10000)

    # Define parameter grid for optimization for Supertrend
    param_grid = {
        "supertrend_period": list(range(7, 15)),  # 7 to 14 inclusive
        "supertrend_multiplier": [2.0, 2.5, 3.0, 3.5, 4.0],
    }

    # Run grid search
    optimization_results = optimizer.grid_search(
        param_grid=param_grid,
        base_config=base_config,
        metric="total_return_pct",  # Changed metric to total_return_pct for profit optimization
        n_jobs=4,
    )

    # Get best configuration
    best_config, best_result = optimizer.get_best_config(metric="sharpe_ratio")

    print("\n" + "=" * 60)
    print("BEST CONFIGURATION")
    print("=" * 60)
    for key, value in best_config.items():
        if key in param_grid:
            print(f"{key}: {value}")

    print(f"\nBest Sharpe Ratio: {best_result.sharpe_ratio:.2f}")
    print(f"Total Return: {best_result.total_return_pct:.2f}%")
    print(f"Win Rate: {best_result.win_rate:.2f}%")
    print(f"Max Drawdown: {best_result.max_drawdown_pct:.2f}%")

    # Save results
    optimizer.save_results("optimization_results.json")

    # Plot optimization heatmap
    visualizer.plot_optimization_results(
        optimizer, "stopLossPct", "takeProfitPct", metric="sharpe_ratio"
    )


if __name__ == "__main__":
    main()
