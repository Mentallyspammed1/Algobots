#!/usr/bin/env python3

import datetime
import json
import logging
import os
import pickle
import smtplib
import sqlite3
import uuid
import warnings
from dataclasses import asdict, dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import optuna
import pandas as pd
import pandas_ta as ta
from sklearn.model_selection import TimeSeriesSplit

# --- Suppress common warnings for cleaner output ---
warnings.filterwarnings("ignore", category=FutureWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)

# --- Dynamic Imports for Optional Components ---
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# Import BOT_CONFIG from the new config file
# Import necessary components from ehlerssupertrend.py
from ehlerssupertrend import (
    Bybit,
    ColoredFormatter,
    calculate_ehl_supertrend_indicators,
    calculate_pnl,
    generate_ehl_supertrend_signals,
    send_termux_toast,
)

from config import BOT_CONFIG


# --- Enhanced Logging Setup ---
class OptimizationLogger:
    def __init__(self, name="optimizer", log_dir="optimization_logs"):
        self.logger = logging.getLogger(name)
        if not self.logger.hasHandlers():
            self.logger.setLevel(logging.DEBUG)
            os.makedirs(log_dir, exist_ok=True)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColoredFormatter())
            console_handler.setLevel(
                getattr(logging, BOT_CONFIG.get("LOG_LEVEL", "INFO"))
            )
            from logging.handlers import RotatingFileHandler

            file_handler = RotatingFileHandler(
                os.path.join(log_dir, f"optimization_{datetime.date.today()}.log"),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
            )
            file_formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)

    def get_logger(self):
        return self.logger


opt_logger = OptimizationLogger().get_logger()


# --- 1. Performance Metrics Dataclass ---
@dataclass
class PerformanceMetrics:
    total_pnl: float
    num_trades: int
    win_rate: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    calmar_ratio: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    consecutive_wins: int
    consecutive_losses: int
    recovery_factor: float
    risk_reward_ratio: float
    expectancy: float
    var_95: float
    cvar_95: float
    kelly_criterion: float
    annual_return: float
    annual_volatility: float
    skewness: float
    kurtosis: float


# --- Helper functions to replace scipy.stats ---
def _calculate_skewness(data: np.ndarray) -> float:
    """Calculate skewness using numpy."""
    if len(data) < 3:
        return 0.0
    mean = np.mean(data)
    std = np.std(data, ddof=0)
    if std == 0:
        return 0.0
    third_moment = np.mean((data - mean) ** 3)
    return third_moment / (std**3)


def _calculate_kurtosis(data: np.ndarray) -> float:
    """Calculate excess kurtosis (Fisher's definition) using numpy."""
    if len(data) < 4:
        return 0.0
    mean = np.mean(data)
    std = np.std(data, ddof=0)
    if std == 0:
        return 0.0
    fourth_moment = np.mean((data - mean) ** 4)
    return fourth_moment / (std**4) - 3


# --- 2. Market Regime Detector ---
class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"


class MarketRegimeDetector:
    @staticmethod
    def detect_regime(df: pd.DataFrame, lookback: int = 50) -> MarketRegime:
        if len(df) < lookback:
            return MarketRegime.RANGING
        recent = df.tail(lookback)
        adx = ta.adx(recent["High"], recent["Low"], recent["Close"], length=14)
        adx_val = adx.iloc[-1, 0] if adx is not None and not adx.empty else 0
        if adx_val > 25:
            sma_short = ta.sma(recent["Close"], 10).iloc[-1]
            sma_long = ta.sma(recent["Close"], 30).iloc[-1]
            return (
                MarketRegime.TRENDING_UP
                if sma_short > sma_long
                else MarketRegime.TRENDING_DOWN
            )
        return MarketRegime.RANGING


# --- 3. Cache System ---
class CacheManager:
    def __init__(self):
        self.use_redis = REDIS_AVAILABLE and BOT_CONFIG.get("USE_REDIS_CACHE", False)
        if self.use_redis:
            try:
                self.cache = redis.Redis(
                    host="localhost", port=6379, db=0, decode_responses=False
                )
                self.cache.ping()
                opt_logger.info("Connected to Redis cache.")
            except Exception:
                opt_logger.warning("Redis unavailable, falling back to memory cache.")
                self.use_redis = False
                self.cache = {}
        else:
            self.cache = {}
            opt_logger.info("Using in-memory cache.")

    def get(self, key: str):
        return pickle.loads(self.cache.get(key)) if self.cache.get(key) else None

    def set(self, key: str, value: Any, expire: int = 3600):
        if self.use_redis:
            self.cache.setex(key, expire, pickle.dumps(value))
        else:
            self.cache[key] = value


# --- 4. Database Manager ---
class OptimizationDatabase:
    def __init__(self, db_path: str = "optimization_results.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        with self.conn:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, symbol TEXT, timeframe TEXT, start TEXT, end TEXT, params TEXT, metrics TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS backtests (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, params TEXT, metrics TEXT, FOREIGN KEY (run_id) REFERENCES runs (id))"
            )

    def save_run(self, data: dict) -> str:
        run_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute(
                "INSERT INTO runs (id, symbol, timeframe, start, end, params, metrics) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    data["symbol"],
                    data["timeframe"],
                    data["start_date"],
                    data["end_date"],
                    json.dumps(data["best_params"]),
                    json.dumps(asdict(data["best_metrics"])),
                ),
            )
        return run_id


# --- 5. Advanced Backtesting Engine ---
class AdvancedBacktester:
    def __init__(
        self,
        initial_capital: float = 10000,
        commission_rate: float = 0.0006,
        slippage_pct: float = 0.0005,
    ):
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_pct = slippage_pct

    def calculate_metrics(
        self, trades: list[dict], equity_curve: list[float]
    ) -> PerformanceMetrics:
        if not trades:
            return PerformanceMetrics(*[0] * 25)
        pnls = np.array([t["pnl"] for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        num_trades = len(trades)
        win_rate = len(wins) / num_trades if num_trades > 0 else 0
        equity_array = np.array(equity_curve)
        returns = np.diff(equity_array) / equity_array[:-1]
        returns = returns[np.isfinite(returns)]
        sharpe = (
            np.sqrt(252) * np.mean(returns) / np.std(returns)
            if len(returns) > 1 and np.std(returns) > 0
            else 0
        )
        down_returns = returns[returns < 0]
        down_dev = np.std(down_returns)
        sortino = (
            np.sqrt(252) * np.mean(returns) / down_dev
            if len(down_returns) > 1 and down_dev > 0
            else 0
        )
        peak = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak) / peak
        max_dd = np.min(drawdown) if len(drawdown) > 0 else 0
        annual_return = (
            (equity_array[-1] / equity_array[0]) ** (252 / len(equity_array)) - 1
            if len(equity_array) > 1
            else 0
        )
        calmar = annual_return / abs(max_dd) if max_dd != 0 else 0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        avg_win = np.mean(wins) if len(wins) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss))
        kelly = (
            (win_rate * risk_reward - (1 - win_rate)) / risk_reward
            if risk_reward > 0
            else 0
        )
        return PerformanceMetrics(
            total_pnl=np.sum(pnls),
            num_trades=num_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=0,
            calmar_ratio=calmar,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=np.max(wins) if len(wins) > 0 else 0,
            largest_loss=np.min(losses) if len(losses) > 0 else 0,
            consecutive_wins=0,
            consecutive_losses=0,
            recovery_factor=np.sum(pnls) / (abs(max_dd) * self.initial_capital)
            if max_dd != 0
            else 0,
            risk_reward_ratio=risk_reward,
            expectancy=expectancy,
            var_95=np.percentile(returns, 5) if len(returns) > 0 else 0,
            cvar_95=np.mean(returns[returns <= np.percentile(returns, 5)])
            if len(returns) > 0
            else 0,
            kelly_criterion=kelly,
            annual_return=annual_return,
            annual_volatility=np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0,
            skewness=_calculate_skewness(returns),
            kurtosis=_calculate_kurtosis(returns),
        )

    def run_backtest(
        self,
        df: pd.DataFrame,
        params: dict,
        symbol: str,
        price_precision: int,
        qty_precision: int,
    ) -> tuple[PerformanceMetrics, list[dict], list[float]]:
        capital = self.initial_capital
        equity_curve = [capital]
        active_trades = {}
        closed_trades = []
        temp_config = {**BOT_CONFIG, **params}
        min_candles = max(100, temp_config.get("EST_SLOW_LENGTH", 50))
        if len(df) < min_candles:
            return self.calculate_metrics([], [capital]), [], [capital]
        df_indicators = calculate_ehl_supertrend_indicators(df.copy(), temp_config)
        for i in range(min_candles, len(df_indicators)):
            current_candle = df_indicators.iloc[i]
            current_price = current_candle["Close"]
            # Manage existing trades (SL/TP checks)
            for trade_symbol in list(active_trades.keys()):
                trade = active_trades[trade_symbol]
                exit_price, exit_reason = None, None
                if (
                    trade["side"] == "Buy" and current_candle["Low"] <= trade["sl"]
                ) or (
                    trade["side"] == "Sell" and current_candle["High"] >= trade["sl"]
                ):
                    exit_price, exit_reason = trade["sl"], "SL"
                elif trade["tp"] and (
                    (trade["side"] == "Buy" and current_candle["High"] >= trade["tp"])
                    or (
                        trade["side"] == "Sell" and current_candle["Low"] <= trade["tp"]
                    )
                ):
                    exit_price, exit_reason = trade["tp"], "TP"
                if exit_price:
                    slipped_exit = (
                        exit_price * (1 - self.slippage_pct)
                        if trade["side"] == "Buy"
                        else exit_price * (1 + self.slippage_pct)
                    )
                    pnl = calculate_pnl(
                        trade["side"], trade["entry_price"], slipped_exit, trade["qty"]
                    )
                    commission = (
                        trade["qty"] * trade["entry_price"] * self.commission_rate
                    ) + (trade["qty"] * slipped_exit * self.commission_rate)
                    net_pnl = pnl - commission
                    capital += net_pnl
                    closed_trades.append(
                        {**trade, "pnl": net_pnl, "exit_reason": exit_reason}
                    )
                    del active_trades[trade_symbol]
            # Generate new trade signals
            if symbol not in active_trades:
                signal, risk, tp, sl, _, _ = generate_ehl_supertrend_signals(
                    df_indicators.iloc[: i + 1],
                    current_price,
                    0,
                    0,
                    price_precision,
                    qty_precision,
                    temp_config,
                )
                if signal != "none" and risk and risk > 0:
                    entry_price = (
                        current_price * (1 + self.slippage_pct)
                        if signal == "Buy"
                        else current_price * (1 - self.slippage_pct)
                    )
                    qty = round(
                        (capital * temp_config.get("RISK_PER_TRADE_PCT", 0.01)) / risk,
                        qty_precision,
                    )
                    if qty > 0:
                        active_trades[symbol] = {
                            "side": signal,
                            "entry_price": entry_price,
                            "qty": qty,
                            "sl": sl,
                            "tp": tp,
                        }
            equity_curve.append(
                capital
                + sum(
                    calculate_pnl(t["side"], t["entry_price"], current_price, t["qty"])
                    for t in active_trades.values()
                )
            )
        return (
            self.calculate_metrics(closed_trades, equity_curve),
            closed_trades,
            equity_curve,
        )


# --- 6. Optimization Algorithms ---
class OptimizationEngine:
    def __init__(self, backtester: AdvancedBacktester):
        self.backtester = backtester

    def _run_single(self, args):
        return self.backtester.run_backtest(*args)

    def bayesian(
        self, df, space, symbol, pp, qp, objective="sharpe_ratio", n_trials=100
    ) -> tuple[dict, PerformanceMetrics, list[dict]]:
        def objective_func(trial):
            params = {
                p: trial.suggest_int(p, v[0], v[1])
                if isinstance(v[0], int)
                else trial.suggest_float(p, v[0], v[1])
                for p, v in space.items()
            }
            metrics, _, _ = self.backtester.run_backtest(df, params, symbol, pp, qp)
            return (
                getattr(metrics, objective)
                if not np.isnan(getattr(metrics, objective))
                else -1
            )

        study = optuna.create_study(direction="maximize")
        study.optimize(objective_func, n_trials=n_trials)
        best_params = study.best_params
        metrics, trades, _ = self.backtester.run_backtest(
            df, best_params, symbol, pp, qp
        )
        return best_params, metrics, trades


# --- 7. Walk-Forward Analysis ---
class WalkForwardAnalyzer:
    def __init__(self, optimizer: OptimizationEngine):
        self.optimizer = optimizer

    def analyze(self, df, param_grid, symbol, pp, qp, n_splits=5) -> list[dict]:
        results = []
        tscv = TimeSeriesSplit(n_splits=n_splits)
        for fold, (train_idx, test_idx) in enumerate(tscv.split(df)):
            opt_logger.info(f"Walk-forward fold {fold + 1}/{n_splits}")
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]
            best_params, _, _ = self.optimizer.bayesian(
                train_df, param_grid, symbol, pp, qp, n_trials=50
            )
            test_metrics, test_trades, _ = self.optimizer.backtester.run_backtest(
                test_df, best_params, symbol, pp, qp
            )
            results.append(
                {
                    "fold": fold,
                    "best_params": best_params,
                    "test_metrics": asdict(test_metrics),
                }
            )
        return results


# --- 8. Notification Manager ---
class NotificationManager:
    def format_html_report(self, run_data: dict) -> str:
        metrics = run_data["best_metrics"]
        params = run_data["best_params"]
        metrics_html = "".join(
            [
                f"<tr><td style='padding: 5px; font-weight: bold;'>{k.replace('_', ' ').title()}</td><td style='padding: 5px;'>{v:.4f}</td></tr>"
                for k, v in asdict(metrics).items()
            ]
        )
        params_html = (
            json.dumps(params, indent=2).replace("\n", "<br>").replace(" ", "&nbsp;")
        )
        return f"""
        <html><body>
        <h2 style="color: #08F7FE;">Optimization Complete: {run_data["symbol"]}</h2>
        <h3 style="color: #FE53BB;">Best Parameters Found:</h3><pre style="background-color: #333; color: #fff; padding: 10px; border-radius: 5px;">{params_html}</pre>
        <h3 style="color: #FE53BB;">Performance Metrics:</h3>
        <table border="1" style="border-collapse: collapse; width: 100%; color: #fff; background-color: #212946;">{metrics_html}</table>
        </body></html>"""

    def send_email(self, subject: str, html_content: str):
        cfg = BOT_CONFIG.get("EMAIL_CONFIG")
        if not cfg:
            opt_logger.warning("Email config not found.")
            return
        msg = MIMEMultipart()
        msg["From"] = cfg["sender"]
        msg["To"] = cfg["recipient"]
        msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))
        try:
            with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
                server.starttls()
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
            opt_logger.info("Email notification sent successfully.")
        except Exception as e:
            opt_logger.error(f"Failed to send email: {e}")


# --- 9. Visualization Suite ---
class VisualizationSuite:
    def __init__(self, report_dir="optimization_reports"):
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)

    def generate_report(
        self, run_data: dict, equity_curve: list[float], trades: list[dict]
    ):
        plt.style.use("cyberpunk")
        fig, axes = plt.subplots(
            2, 1, figsize=(15, 12), gridspec_kw={"height_ratios": [3, 1]}
        )
        # Equity Curve
        axes[0].plot(equity_curve, color="#08F7FE", lw=2)
        axes[0].set_title(f"Equity Curve for {run_data['symbol']}", fontsize=18)
        # Drawdown
        equity = pd.Series(equity_curve)
        peak = equity.expanding(min_periods=1).max()
        drawdown = (equity - peak) / peak
        axes[1].fill_between(
            drawdown.index, drawdown * 100, 0, color="#FE53BB", alpha=0.6
        )
        axes[1].set_title("Drawdown (%)", fontsize=14)
        report_path = os.path.join(
            self.report_dir, f"report_{run_data['symbol']}_{datetime.date.today()}.png"
        )
        plt.savefig(report_path, dpi=150, bbox_inches="tight")
        plt.close()
        opt_logger.info(f"Visual report saved to {report_path}")


# --- 10. Main Orchestrator ---
class MainOrchestrator:
    def __init__(self, symbol, timeframe, data_path):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data_path = data_path
        self.df = pd.read_csv(data_path, index_col=0, parse_dates=True)
        self.db = OptimizationDatabase()
        self.backtester = AdvancedBacktester()
        self.optimizer = OptimizationEngine(self.backtester)
        self.notifier = NotificationManager()
        self.visualizer = VisualizationSuite()
        self.price_prec, self.qty_prec = self._get_precisions()

    def _get_precisions(self):
        try:
            info = Bybit(symbol=self.symbol).get_instrument_info()
            return info["price_scale"], info["qty_step"]
        except:
            opt_logger.warning("Could not fetch precisions, using defaults.")
            return 2, 3

    def run(self, mode: str, param_space: dict, n_trials: int = 100):
        start_time = datetime.datetime.now()
        opt_logger.info(f"Starting {mode} optimization for {self.symbol}...")
        if mode == "bayesian":
            best_params, best_metrics, trades = self.optimizer.bayesian(
                self.df,
                param_space,
                self.symbol,
                self.price_prec,
                self.qty_prec,
                n_trials=n_trials,
            )
            _, _, equity_curve = self.backtester.run_backtest(
                self.df, best_params, self.symbol, self.price_prec, self.qty_prec
            )
        elif mode == "walk_forward":
            wf_analyzer = WalkForwardAnalyzer(self.optimizer)
            results = wf_analyzer.analyze(
                self.df, param_space, self.symbol, self.price_prec, self.qty_prec
            )
            opt_logger.info(f"Walk-forward results:\n{json.dumps(results, indent=2)}")
            return
        else:
            raise ValueError("Invalid mode specified.")

        run_data = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.df.index.min().isoformat(),
            "end_date": self.df.index.max().isoformat(),
            "best_params": best_params,
            "best_metrics": best_metrics,
        }
        self.db.save_run(run_data)
        self.visualizer.generate_report(run_data, equity_curve, trades)
        html_report = self.notifier.format_html_report(run_data)
        self.notifier.send_email(f"Optimization Complete: {self.symbol}", html_report)
        opt_logger.info(
            f"Optimization finished in {datetime.datetime.now() - start_time}."
        )
        send_termux_toast(f"Optimization for {self.symbol} complete!")


# --- Main Execution Block ---
if __name__ == "__main__":
    SYMBOL_TO_OPTIMIZE = "BTCUSDT"
    TIMEFRAME = "1h"
    DATA_FILE_PATH = f"./data/{SYMBOL_TO_OPTIMIZE}_{TIMEFRAME}.csv"

    # Define the parameter space for Bayesian optimization
    PARAMETER_SPACE = {
        "EST_FAST_LENGTH": (5, 20),
        "EST_SLOW_LENGTH": (25, 60),
        "EST_MULTIPLIER": (2.0, 5.0),
        "RSI_PERIOD": (7, 21),
        "EHLERS_FISHER_PERIOD": (5, 15),
        "RISK_REWARD_RATIO": (1.0, 4.0),
    }

    try:
        if not os.path.exists(DATA_FILE_PATH):
            raise FileNotFoundError(
                f"Data file not found at {DATA_FILE_PATH}. Please download data first."
            )

        orchestrator = MainOrchestrator(
            symbol=SYMBOL_TO_OPTIMIZE, timeframe=TIMEFRAME, data_path=DATA_FILE_PATH
        )

        # --- CHOOSE YOUR OPTIMIZATION MODE ---
        # orchestrator.run(mode='bayesian', param_space=PARAMETER_SPACE, n_trials=200)
        orchestrator.run(mode="walk_forward", param_space=PARAMETER_SPACE)

    except Exception as e:
        opt_logger.error(f"A critical error occurred: {e}", exc_info=True)
        send_termux_toast(f"Optimization for {SYMBOL_TO_OPTIMIZE} FAILED!")
