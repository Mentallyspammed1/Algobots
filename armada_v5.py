# ArmadaV5EternalSupreme - Enhanced Version
# -----------------------------------------
# This module implements the ArmadaV5EternalSupreme trading bot, a sophisticated
# automated cryptocurrency trading system for the Bybit exchange.
#
# Enhancements in this version:
#   - Refactored for modularity, readability, and maintainability.
#   - Centralized configuration for easy tuning.
#   - Standardized Wilder's ADX implementation for improved accuracy.
#   - Added "Exit on Counter-Signal" logic to protect profits and cut losses.
#   - Corrected bugs and improved error handling for greater stability.
#   - Enhanced dashboard for better real-time monitoring.
#
# Requirements:
#   - pybit
#   - rich
#   - colorama
#   - python-dotenv
#
# To install:
#   pip install pybit rich colorama python-dotenv
#
# --- The Termux Coding Wizard (ARM64) ---

import math
import os
import threading
import time
import json
import signal
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Dict, List, Optional
from subprocess import Popen

from colorama import Fore, Style, init
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---- Eternal Sanctum of Decimal Purity ----
getcontext().prec = 30
init(autoreset=True)
load_dotenv()

# ---- Constants ----
D0 = Decimal("0")
D1 = Decimal("1")
D2 = Decimal("2")
D100 = Decimal("100")
MAX_KLINE_LENGTH = 300


# ---- Utility Functions ----
def to_decimal(value: any) -> Decimal:
    """Converts a value to a Decimal, returning D0 if conversion fails or value is None."""
    try:
        return Decimal(str(value)) if value is not None else D0
    except Exception:
        return D0


def px_up(price: Decimal, tick_size: Decimal) -> Decimal:
    """Rounds a price up to the nearest tick size."""
    if tick_size <= D0:
        return price
    return (price / tick_size).to_integral_value(rounding="ROUND_UP") * tick_size


def px_down(price: Decimal, tick_size: Decimal) -> Decimal:
    """Rounds a price down to the nearest tick size."""
    if tick_size <= D0:
        return price
    return (price / tick_size).to_integral_value(rounding="ROUND_DOWN") * tick_size


def qty_down(quantity: Decimal, step_size: Decimal) -> Decimal:
    """Rounds a quantity down to the nearest step size."""
    if step_size <= D0:
        return quantity
    return (quantity / step_size).to_integral_value(rounding="ROUND_DOWN") * step_size


def format_currency(value: Decimal) -> str:
    """Formats a Decimal value as a currency string with a sign."""
    sign = "+" if value >= D0 else ""
    return f"{sign}{value:,.2f}"


# ---- Configuration & Data Models ----
@dataclass
class Position:
    """Represents an open trading position."""
    qty: Decimal = D0
    entry: Decimal = D0
    sl_price: Decimal = D0
    tp_price: Decimal = D0
    side: str = ""
    breakeven: bool = False
    partial_taken: bool = False
    second_partial_taken: bool = False
    unrealized_pnl: Decimal = D0
    size_usd: Decimal = D0


@dataclass
class TradingParams:
    """Parameters for trading configuration."""
    symbols: List[str] = field(default_factory=lambda: [
        "DOGEUSDT", "ADAUSDT", "TRXUSDT", "SHIB1000USDT",
        "TONUSDT", "SUIUSDT", "HBARUSDT", "XLMUSDT", "VETUSDT", "NOTUSDT"
    ])
    category: str = "linear"
    interval: str = "1"


@dataclass
class RiskManagementParams:
    """Parameters for risk management."""
    risk_per_trade_equity_pct: Decimal = to_decimal(
        "0.005")  # 0.5% of equity per trade
    daily_loss_limit_usd: Decimal = to_decimal("-50")
    cooldown_seconds: int = 60


@dataclass
class IndicatorParams:
    """Parameters for technical indicators."""
    high_volume_threshold: Decimal = to_decimal("5000000")  # 5M USDT daily volume
    smoother_period: int = 10
    roc_period: int = 10
    mom_ema_period: int = 5
    adx_period: int = 14
    base_adx_threshold: Decimal = to_decimal("20")
    adx_volatility_mult: Decimal = to_decimal("10")
    atr_period: int = 14
    volume_spike_multiplier: Decimal = to_decimal("2.0")
    chandelier_period: int = 22
    chandelier_mult: Decimal = to_decimal("3.0")


@dataclass
class ProfitManagementParams:
    """Parameters for profit management."""
    tp_atr_mult: Decimal = to_decimal("1.0")
    partial_profit_atr: Decimal = to_decimal("0.5")
    partial_profit_qty_pct: Decimal = to_decimal("0.5")
    second_partial_profit_atr: Decimal = to_decimal("1.0")
    second_partial_profit_qty_pct: Decimal = to_decimal("0.5")
    trailing_tp_atr_mult: Decimal = to_decimal("3.0")
    trailing_tp_step: Decimal = to_decimal("0.5")


@dataclass
class Config:
    """Main configuration container for the bot."""
    trading: TradingParams = field(default_factory=TradingParams)
    risk: RiskManagementParams = field(default_factory=RiskManagementParams)
    indicators: IndicatorParams = field(default_factory=IndicatorParams)
    profit: ProfitManagementParams = field(
        default_factory=ProfitManagementParams)
    pnl_file_path: str = "/data/data/com.termux/files/home/.armada_pnl.json"


@dataclass
class BotState:
    """Holds the dynamic state of the trading bot."""
    daily_realized_pnl: Decimal = D0
    equity: Decimal = D0
    emergency_stop: bool = False
    is_running: bool = True
    symbol_states: Dict[str, dict] = field(default_factory=dict)


@dataclass
class ApiSession:
    """Container for API session and keys."""
    http: HTTP
    key: str
    secret: str


@dataclass
class UIManager:
    """Manages UI components like console and logs."""
    console: Console = field(default_factory=Console)
    logs: List[str] = field(default_factory=list)


class Indicators:
    """
    A static class for calculating technical indicators using a hybrid approach:
    - A full historical calculation for accurate initialization.
    - Efficient incremental calculations for real-time updates.
    """

    @staticmethod
    def _wilder_smooth_incremental(
            prev_smooth: Decimal,
            current_val: Decimal,
            period: int) -> Decimal:
        """Applies one step of Wilder's Smoothing (RMA)."""
        return (prev_smooth * (period - 1) + current_val) / period

    @staticmethod
    def _wilder_smooth_series(
            series: List[Decimal],
            period: int) -> List[Decimal]:
        """Applies Wilder's Smoothing (RMA) to a full series."""
        if not series or len(series) < period:
            return []

        smoothed = [sum(series[:period]) / period]
        for i in range(period, len(series)):
            next_val = (smoothed[-1] * (period - 1) + series[i]) / period
            smoothed.append(next_val)
        return smoothed

    @staticmethod
    def calculate_all_historical(state: dict, config: Config) -> None:
        """Performs a full calculation on kline history to initialize all indicators."""
        klines = state["klines"]
        params = config.indicators
        closes = [k[3] for k in klines]

        required_len = params.adx_period * 2
        if len(klines) < required_len:
            return

        # ATR and ADX Base Calculations
        tr_list, plus_dm_list, minus_dm_list = [], [], []
        for i in range(1, len(klines)):
            h, l, c, ph, pl, pc = klines[i][1], klines[i][2], klines[i][3], klines[i-1][1], klines[i-1][2], klines[i-1][3]
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))
            up, down = h - ph, pl - l
            plus_dm_list.append(up if up > down and up > D0 else D0)
            minus_dm_list.append(down if down > up and down > D0 else D0)

        atr_series = Indicators._wilder_smooth_series(tr_list, params.atr_period)
        state["atr"] = atr_series[-1] if atr_series else D0

        pdm_series = Indicators._wilder_smooth_series(plus_dm_list, params.adx_period)
        mdm_series = Indicators._wilder_smooth_series(minus_dm_list, params.adx_period)

        if atr_series and pdm_series and mdm_series:
            dx_series = []
            start_idx = len(tr_list) - len(atr_series)

            for i in range(len(pdm_series)):
                atr_val = atr_series[start_idx + i]
                plus_di = (pdm_series[i] / atr_val * D100) if atr_val > D0 else D0
                minus_di = (mdm_series[i] / atr_val * D100) if atr_val > D0 else D0
                dx = (abs(plus_di - minus_di) / (plus_di + minus_di) * D100) if (plus_di + minus_di) > D0 else D0
                dx_series.append(dx)

            adx_series = Indicators._wilder_smooth_series(dx_series, params.adx_period)
            state["adx"] = adx_series[-1] if adx_series else D0
            state["smooth_plus_dm"] = pdm_series[-1]
            state["smooth_minus_dm"] = mdm_series[-1]

        # Calculate other indicators by iterating and using the incremental logic
        temp_state = {}
        for i in range(len(klines)):
            # Create a shallow copy for incremental calculation
            loop_state = temp_state.copy()
            loop_state['klines'] = klines[:i+1]
            Indicators.calculate_incremental(loop_state, config)
            temp_state = loop_state

        # Merge final calculated state back
        for key, value in temp_state.items():
            if key != 'klines':
                state[key] = value

    @staticmethod
    def calculate_incremental(state: dict, config: Config) -> None:
        """Calculates indicators for the latest kline using previous state."""
        klines = state["klines"]
        params = config.indicators

        if len(klines) < 2: return

        price, prev_price = klines[-1][3], klines[-2][3]
        state["price"] = price

        # SuperSmoother
        arg = Decimal("1.414") * Decimal(math.pi) / Decimal(params.smoother_period)
        a1 = Decimal(math.exp(float(-arg)))
        b1 = D2 * a1 * Decimal(math.cos(float(arg)))
        c1, c2, c3 = D1 - b1 - (-a1 * a1), b1, -a1 * a1

        prev_smooth1 = state.get("prev_smooth1", prev_price)
        prev_smooth2 = state.get("prev_smooth2", prev_price)
        filt = c1 * price + c2 * prev_smooth1 + c3 * prev_smooth2
        state["prev_smooth2"], state["prev_smooth1"] = prev_smooth1, filt
        state["super_smooth"] = filt
        state["prev_trend_up"], state["trend_up"] = state.get("trend_up", False), price > filt

        # Momentum
        if len(klines) > params.roc_period:
            roc_price = klines[-params.roc_period - 1][3]
            state["roc"] = (price / roc_price - D1) * D100 if roc_price > D0 else D0

        mom_ema = state.get("mom_ema", state.get("roc", D0))
        alpha = D2 / (params.mom_ema_period + 1)
        state["mom_ema"] = state.get("roc", D0) * alpha + mom_ema * (D1 - alpha)

        prev_roc, prev_mom = state.get("prev_roc", state.get("roc", D0)), state.get("prev_mom_ema", state.get("mom_ema", D0))
        state["mom_cross_up"] = state["mom_ema"] < state["roc"] and prev_mom >= prev_roc
        state["mom_cross_down"] = state["mom_ema"] > state["roc"] and prev_mom <= prev_roc
        state["prev_roc"], state["prev_mom_ema"] = state.get("roc", D0), state.get("mom_ema", D0)

        # Volume Spike
        if len(klines) >= 21:
            volumes = [k[4] for k in klines[-21:-1]]
            avg_vol = sum(volumes) / 20
            state["volume_spike"] = klines[-1][4] > avg_vol * params.volume_spike_multiplier

        # ATR and ADX
        h, l, pc = klines[-1][1], klines[-1][2], klines[-2][3]
        ph, pl = klines[-2][1], klines[-2][2]

        tr = max(h - l, abs(h - pc), abs(l - pc))
        state["atr"] = Indicators._wilder_smooth_incremental(state.get("atr", tr), tr, params.atr_period)

        up, down = h - ph, pl - l
        plus_dm = up if up > down and up > D0 else D0
        minus_dm = down if down > up and down > D0 else D0

        state["smooth_plus_dm"] = Indicators._wilder_smooth_incremental(state.get("smooth_plus_dm", plus_dm), plus_dm, params.adx_period)
        state["smooth_minus_dm"] = Indicators._wilder_smooth_incremental(state.get("smooth_minus_dm", minus_dm), minus_dm, params.adx_period)

        if state["atr"] > D0:
            plus_di = (state["smooth_plus_dm"] / state["atr"]) * D100
            minus_di = (state["smooth_minus_dm"] / state["atr"]) * D100
            dx = (abs(plus_di - minus_di) / (plus_di + minus_di) * D100) if (plus_di + minus_di) > D0 else D0
            state["adx"] = Indicators._wilder_smooth_incremental(state.get("adx", dx), dx, params.adx_period)

        # Chandelier
        if state["atr"] > D0 and len(klines) >= params.chandelier_period:
            highs = [k[1] for k in klines[-params.chandelier_period:]]
            lows = [k[2] for k in klines[-params.chandelier_period:]]
            state["chand_long"] = max(highs) - state["atr"] * params.chandelier_mult
            state["chand_short"] = min(lows) + state["atr"] * params.chandelier_mult

        # Dynamic ADX
        if state["price"] > D0 and state.get("adx", D0) > D0:
            atr_ratio = state["atr"] / state["price"]
            dynamic_thr = params.base_adx_threshold * (D1 + (atr_ratio - Decimal("0.001")) * params.adx_volatility_mult)
            state["dynamic_adx_ok"] = state["adx"] > max(dynamic_thr, params.base_adx_threshold)
        else:
            state["dynamic_adx_ok"] = False

        # EMA
        ema_period = 10
        ema_key = f"ema_{ema_period}"
        alpha_ema = D2 / (ema_period + 1)
        state[ema_key] = price * alpha_ema + state.get(ema_key, price) * (D1 - alpha_ema)

        # RSI
        rsi_period = 14
        rsi_key = f"rsi_{rsi_period}"
        avg_gain_key = f"avg_gain_{rsi_period}"
        avg_loss_key = f"avg_loss_{rsi_period}"

        change = price - prev_price
        gain = change if change > 0 else D0
        loss = abs(change) if change < 0 else D0

        state[avg_gain_key] = Indicators._wilder_smooth_incremental(state.get(avg_gain_key, gain), gain, rsi_period)
        state[avg_loss_key] = Indicators._wilder_smooth_incremental(state.get(avg_loss_key, loss), loss, rsi_period)

        if state.get(avg_loss_key, D0) == 0:
            state[rsi_key] = D100
        else:
            rs = state[avg_gain_key] / state[avg_loss_key]
            state[rsi_key] = D100 - (D100 / (D1 + rs))

        Indicators._update_pnl(state)

    @staticmethod
    def _update_pnl(state: dict) -> None:
        pos = state.get("position", Position())
        if pos.qty > D0:
            pnl_mult = D1 if pos.side == "Buy" else -D1
            pos.unrealized_pnl = (state["price"] - pos.entry) * pos.qty * pnl_mult
            pos.size_usd = pos.qty * state["price"]


class ArmadaV5EternalSupreme:
    """The main class for the ArmadaV5EternalSupreme trading bot."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.bot_state = BotState()
        self.ui = UIManager()
        self.lock = threading.Lock()

        self.log("Awakening Eternal Armada V5 Supreme...", "INFO")

        self.api = self._setup_api_session()
        self._initialize_symbols()
        time.sleep(1) # Prevent rate limit
        self._sync_equity()
        self._filter_active_symbols()

        if os.path.exists(self.config.pnl_file_path):
            try:
                with open(self.config.pnl_file_path) as f:
                    data = json.load(f)
                    if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                        self.bot_state.daily_realized_pnl = to_decimal(data["pnl"])
            except Exception:
                pass

        self._prime_data()
        self.log(
            "Supreme Armada V5 is operational. Full ADX glows upon the fleet.",
            "SUCCESS")

    def _notify(self, title: str, message: str) -> None:
        """Summons a Termux toast notification upon sacred events."""
        try:
            Popen(["termux-toast", "-s", title, message])
        except Exception:
            pass  # Silent if termux-api not installed

    def log(self, msg: str, level: str = "INFO") -> None:
        """Logs a message to the console and internal log list."""
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{ts}] "
        self.ui.logs.append(f"{prefix}{msg}")
        if len(self.ui.logs) > 20:
            self.ui.logs.pop(0)

        color_map = {
            "SUCCESS": Fore.GREEN,
            "WARNING": Fore.YELLOW,
            "ERROR": Fore.RED,
            "ENTRY": Fore.MAGENTA,
            "EXIT": Fore.BLUE}
        color = color_map.get(level, Fore.CYAN) + Style.BRIGHT
        print(color + prefix + msg + Style.RESET_ALL)

    def _setup_api_session(self) -> ApiSession:
        """Initializes the Bybit API session."""
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError(
                "BYBIT_API_KEY and BYBIT_API_SECRET must be set in .env")
        session = HTTP(
            testnet=False,
            api_key=api_key,
            api_secret=api_secret)
        return ApiSession(http=session, key=api_key, secret=api_secret)

    def _initialize_symbols(self) -> None:
        """Fetches instrument info, sets position mode, and initializes state for each symbol."""
        valid_symbols = []
        for sym in self.config.trading.symbols:
            try:
                info = self.api.http.get_instruments_info(
                    category=self.config.trading.category,
                    symbol=sym)["result"]["list"][0]
                try:
                    self.api.http.switch_position_mode(
                        category=self.config.trading.category, symbol=sym, mode=0)
                except Exception as e:
                    if "110025" not in str(
                            e):  # Ignore "Position mode not modified" error
                        self.log(
                            f"Could not set One-Way mode for {sym}: {e}", "WARNING")

                self.bot_state.symbol_states[sym] = {
                    "price": D0,
                    "atr": D0,
                    "adx": D0,
                    "smooth_plus_dm": D0,
                    "smooth_minus_dm": D0,
                    "super_smooth": D0,
                    "prev_smooth1": D0,
                    "prev_smooth2": D0,
                    "trend_up": False,
                    "prev_trend_up": False,
                    "klines": [],
                    "position": Position(),
                    "tick": to_decimal(
                        info["priceFilter"]["tickSize"]),
                    "step": to_decimal(
                        info["lotSizeFilter"]["qtyStep"]),
                    "last_loss_ts": None,
                    "roc": D0,
                    "mom_ema": D0,
                    "prev_roc": D0,
                    "prev_mom_ema": D0,
                    "mom_cross_up": False,
                    "mom_cross_down": False,
                    "volume_spike": False,
                    "chand_long": D0,
                    "chand_short": D0,
                    "dynamic_adx_ok": False}
                valid_symbols.append(sym)
                self.log(f"{sym} realm forged in One-Way harmony.", "INFO")
            except Exception as error:
                self.log(
                    f"Failed to initialize symbol {sym}, it will be banished: {error}",
                    "ERROR")

        self.config.trading.symbols = valid_symbols

    def _sync_equity(self) -> None:
        """Synchronizes the bot's equity with the exchange."""
        try:
            bal = self.api.http.get_wallet_balance(
                accountType="UNIFIED", coin="USDT")["result"]["list"][0]
            self.bot_state.equity = to_decimal(
                bal.get("totalAvailableBalance", "0"))
        except Exception as e:
            self.log(f"Failed to sync equity: {e}", "ERROR")
            self.bot_state.equity = D0

    def _filter_active_symbols(self) -> None:
        """Filters symbols based on 24h trading volume."""
        self.log("Filtering symbols by 24h volume...", "INFO")
        try:
            tickers = self.api.http.get_tickers(category=self.config.trading.category)["result"]["list"]
            high_vol_symbols = {
                t["symbol"] for t in tickers
                if to_decimal(t.get("turnover24h", "0")) > self.config.indicators.high_volume_threshold
            }

            original_symbols = set(self.config.trading.symbols)
            symbols_to_keep = original_symbols.intersection(high_vol_symbols)
            symbols_to_remove = original_symbols - symbols_to_keep

            if symbols_to_remove:
                self.log(f"Filtering out low-volume symbols: {', '.join(symbols_to_remove)}", "WARNING")
                self.config.trading.symbols = list(symbols_to_keep)
                for sym in symbols_to_remove:
                    self.bot_state.symbol_states.pop(sym, None)

            self.log(f"Found {len(self.config.trading.symbols)} high-volume symbols to trade.", "SUCCESS")

        except Exception as e:
            self.log(f"Could not filter symbols by volume, using initial list: {e}", "ERROR")

    def _prime_data(self) -> None:
        """Fetches initial klines data and calculates indicators for all symbols."""
        for sym in self.config.trading.symbols:
            try:
                res = self.api.http.get_kline(
                    category=self.config.trading.category,
                    symbol=sym,
                    interval=self.config.trading.interval,
                    limit=MAX_KLINE_LENGTH
                )
                raw_klines = res["result"]["list"]
                klines = [[to_decimal(k[1]), to_decimal(k[2]), to_decimal(k[3]), to_decimal(
                    k[4]), to_decimal(k[5])] for k in reversed(raw_klines)]
                self.bot_state.symbol_states[sym]["klines"] = klines
                Indicators.calculate_all_historical(
                    self.bot_state.symbol_states[sym], self.config)
            except Exception as error:
                self.log(
                    f"Failed to prime klines for {sym}: {error}",
                    "WARNING")
        self.log("Ancient klines summoned. Full ADX awakened.", "SUCCESS")

    def _enter_position(self, sym: str, side: str) -> None:
        """Calculates position details and places a market order."""
        if self.bot_state.emergency_stop or self.bot_state.equity <= D0:
            return
        state = self.bot_state.symbol_states[sym]
        if state["position"].qty > D0 or state["atr"] <= D0:
            return

        risk_dist = state["atr"] * self.config.indicators.chandelier_mult
        if risk_dist <= D0:
            return

        current_equity = self.bot_state.equity
        base_risk = Decimal("0.005")
        scaled_risk = base_risk * (D1 + self.bot_state.daily_realized_pnl / current_equity * Decimal("0.5"))
        scaled_risk = min(scaled_risk, Decimal("0.015"))

        raw_qty = (current_equity * scaled_risk) / risk_dist
        qty = qty_down(raw_qty, state["step"])
        if qty <= D0:
            return

        recent = state["klines"][-5:]
        weights = [to_decimal(k[4]) for k in recent]
        prices = [k[3] for k in recent]
        total_vol = sum(weights)
        entry_price = sum(p * v for p, v in zip(prices, weights)) / total_vol if total_vol > D0 else state["price"]
        sl_price = px_down(
            entry_price - risk_dist,
            state["tick"]) if side == "Buy" else px_up(
            entry_price + risk_dist,
            state["tick"])
        tp_price = px_up(
            entry_price +
            state["atr"] *
            self.config.profit.tp_atr_mult,
            state["tick"]) if side == "Buy" else px_down(
            entry_price -
            state["atr"] *
            self.config.profit.tp_atr_mult,
            state["tick"])

        try:
            self.api.http.place_order(
                category=self.config.trading.category,
                symbol=sym, side=side, orderType="Market", qty=str(qty),
                takeProfit=str(tp_price), stopLoss=str(sl_price)
            )
            state["position"] = Position(
                qty=qty,
                entry=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                side=side)
            self.log(
                f"{sym} {side} ENTRY @ {entry_price:.4f} | Qty: {qty} | SL: {sl_price:.4f} | TP: {tp_price:.4f}",
                "ENTRY")
            self._notify("⚔️ ENTRY", f"{sym} {side} @ {entry_price:.4f}")
        except Exception as error:
            self.log(f"{sym} entry failed: {error}", "ERROR")

    def _notify_exit(self, sym: str, reason: str) -> None:
        self._notify("⚔️ EXIT", f"{sym} {reason}")

    def _exit_position(self, sym: str, reason: str) -> None:
        """Exits the position for a given symbol."""
        pos = self.bot_state.symbol_states[sym]["position"]
        if pos.qty <= D0:
            return

        close_side = "Sell" if pos.side == "Buy" else "Buy"
        try:
            self.api.http.place_order(
                category=self.config.trading.category, symbol=sym,
                side=close_side, orderType="Market", qty=str(pos.qty),
                reduceOnly=True
            )
            self.log(
                f"{sym} EXIT triggered due to {reason}. Closing {pos.qty} {pos.side}.",
                "EXIT")
            self._notify("⚔️ EXIT", f"{sym} {reason}")
        except Exception as e:
            self.log(f"{sym} failed to exit position: {e}", "ERROR")

    def _adjust_protection(
            self,
            sym: str,
            sl: Optional[Decimal] = None,
            tp: Optional[Decimal] = None) -> None:
        """Sets or updates the stop loss and take profit for a symbol."""
        try:
            params = {"category": self.config.trading.category, "symbol": sym, "positionIdx": 0}
            if sl is not None:
                params["stopLoss"] = str(sl)
            if tp is not None:
                params["takeProfit"] = str(tp)
            if len(params) > 3:
                self.api.http.set_trading_stop(**params)
        except Exception as e:
            self.log(f"Failed to adjust protection for {sym}: {e}", "WARNING")

    def _evaluate_signals(self, sym: str) -> None:
        """Evaluates entry signals based on indicator confluence."""
        state = self.bot_state.symbol_states[sym]
        if state["position"].qty > D0:
            return

        if state["last_loss_ts"] and (
                datetime.now() -
                state["last_loss_ts"]).total_seconds() < self.config.risk.cooldown_seconds:
            return

        long_ready = (
            state["trend_up"] and
            state["mom_cross_up"] and
            state["dynamic_adx_ok"] and
            state["volume_spike"]
        )
        short_ready = (
            not state["trend_up"] and
            state["mom_cross_down"] and
            state["dynamic_adx_ok"] and
            state["volume_spike"]
        )

        if long_ready:
            self._enter_position(sym, "Buy")
        elif short_ready:
            self._enter_position(sym, "Sell")

    def _manage_open_positions(self, sym: str) -> None:
        """Manages all aspects of an open position: partials, breakeven, and trailing SL."""
        state = self.bot_state.symbol_states[sym]
        pos = state["position"]
        if pos.qty <= D0:
            return

        # New: Exit on counter-signal
        confluence_check = state["dynamic_adx_ok"] and state["volume_spike"]
        rsi14 = state.get("rsi_14", Decimal("50"))

        counter_long_signal = (
            not state["trend_up"] and state["prev_trend_up"] and
            state["mom_cross_down"] and confluence_check and
            rsi14 > Decimal("65")  # Overbought confirmation
        )

        counter_short_signal = (
            state["trend_up"] and not state["prev_trend_up"] and
            state["mom_cross_up"] and confluence_check and
            rsi14 < Decimal("35")  # Oversold confirmation
        )

        if (pos.side == "Buy" and counter_long_signal) or (
                pos.side == "Sell" and counter_short_signal):
            self._exit_position(sym, "Counter-Signal")
            return

        self._manage_partials(sym, state, pos)
        self._manage_breakeven(sym, state, pos)
        self._manage_trailing_stop(sym, state, pos)

    def _manage_partials(self, sym: str, state: dict, pos: Position) -> None:
        """Handles first and second partial profit taking."""
        profit_cfg = self.config.profit
        # Partial 1
        if not pos.partial_taken and pos.unrealized_pnl >= state["atr"] * \
                profit_cfg.partial_profit_atr:
            close_qty = qty_down(
                pos.qty *
                profit_cfg.partial_profit_qty_pct,
                state["step"])
            if close_qty > D0:
                self._place_partial_exit(sym, pos, close_qty, 1)

        # Partial 2
        if pos.partial_taken and not pos.second_partial_taken and pos.unrealized_pnl >= state[
                "atr"] * profit_cfg.second_partial_profit_atr:
            close_qty = qty_down(
                pos.qty *
                profit_cfg.second_partial_profit_qty_pct,
                state["step"])
            if close_qty > D0:
                self._place_partial_exit(sym, pos, close_qty, 2)

    def _place_partial_exit(
            self,
            sym: str,
            pos: Position,
            qty: Decimal,
            level: int) -> None:
        """Places a market order for a partial exit."""
        close_side = "Sell" if pos.side == "Buy" else "Buy"
        try:
            self.api.http.place_order(
                category=self.config.trading.category,
                symbol=sym,
                side=close_side,
                orderType="Market",
                qty=str(qty),
                reduceOnly=True)

            if level == 1:
                pos.partial_taken = True
            elif level == 2:
                pos.second_partial_taken = True

            self.log(
                f"{sym} PARTIAL {level} requested | Target close qty: {qty}", "SUCCESS")
            self._notify("💰 PARTIAL", f"{sym} Partial {level}")
        except Exception as e:
            self.log(f"{sym} Partial {level} exit failed: {e}", "ERROR")

    def _manage_breakeven(self, sym: str, state: dict, pos: Position) -> None:
        """Moves stop loss to breakeven after the first partial profit."""
        if pos.partial_taken and not pos.breakeven:
            self._adjust_protection(sym, sl=pos.entry)
            pos.sl_price = pos.entry
            pos.breakeven = True
            self.log(
                f"{sym} Breakeven shield raised to {pos.entry:.4f}", "INFO")

    def _manage_trailing_stop(
            self,
            sym: str,
            state: dict,
            pos: Position) -> None:
        """Manages the Chandelier-based trailing stop loss."""
        if pos.breakeven and state["chand_long"] > D0 and state["chand_short"] > D0:
            new_sl = (
                px_down(
                    state["chand_long"],
                    state["tick"]) if pos.side == "Buy" else px_up(
                    state["chand_short"],
                    state["tick"]))

            is_new_sl_profitable = (
                new_sl > pos.entry) if pos.side == "Buy" else (
                new_sl < pos.entry)
            should_trail = (
                new_sl > pos.sl_price) if pos.side == "Buy" else (
                new_sl < pos.sl_price)

            if is_new_sl_profitable and should_trail:
                self._adjust_protection(sym, sl=new_sl)
                pos.sl_price = new_sl
                self.log(
                    f"{sym} Chandelier trail advanced to {new_sl:.4f}", "INFO")

    def _handle_kline(self, msg: dict) -> None:
        """Handles incoming kline websocket messages."""
        try:
            topic_parts = msg.get("topic", "").split('.')
            if not (len(topic_parts) > 2 and topic_parts[0] == 'kline'):
                return

            sym = topic_parts[-1]
            if sym not in self.bot_state.symbol_states:
                return

            for data in msg.get("data", []):
                if data.get("confirm"):
                    kline = [
                        to_decimal(
                            data[k]) for k in [
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume"]]

                    with self.lock:
                        state = self.bot_state.symbol_states[sym]
                        state["klines"].append(kline)
                        if len(state["klines"]) > MAX_KLINE_LENGTH:
                            state["klines"].pop(0)

                        Indicators.calculate_incremental(state, self.config)

                    # Actions with I/O are called outside the lock
                    self._evaluate_signals(sym)
                    self._manage_open_positions(sym)
        except Exception as e:
            self.log(f"Error in kline handler: {e}", "ERROR")

    def _handle_execution(self, msg: dict) -> None:
        """Handles incoming execution (fill) messages."""
        try:
            with self.lock:
                for exec_data in msg.get("data", []):
                    sym = exec_data.get("symbol")
                    if sym not in self.bot_state.symbol_states:
                        continue

                    pos = self.bot_state.symbol_states[sym]["position"]
                    exec_qty = to_decimal(exec_data.get("execQty", "0"))

                    if exec_qty > 0 and pos.qty > 0:
                        # An order has been filled, update position quantity
                        pos.qty -= exec_qty
                        pnl = to_decimal(exec_data.get("closedPnl", "0"))

                        if pnl != D0:
                            self.bot_state.daily_realized_pnl += pnl
                            self._save_daily_pnl()
                            if pnl < D0:
                                self.bot_state.symbol_states[sym]["last_loss_ts"] = datetime.now()
                            # Store the PnL for session stats
                            self.bot_state.symbol_states[sym]["last_trade_pnl"] = pnl

                        if pos.qty <= 0:
                            # Full exit
                            self.bot_state.symbol_states[sym]["position"] = Position()
                            level = "WARNING" if pnl < D0 else "SUCCESS"
                            self.log(f"{sym} CLOSED trade. PnL: {format_currency(pnl)}", level)
                        else:
                            # Partial exit, but the logic was flawed.
                            # The 'pos.qty -= exec_qty' above is the source of truth.
                            self.log(f"{sym} PARTIALLY CLOSED. Remaining qty: {pos.qty}", "INFO")

        except Exception as e:
            self.log(f"Error in execution handler: {e}", "ERROR")

    def _save_daily_pnl(self) -> None:
        data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "pnl": str(self.bot_state.daily_realized_pnl)
        }
        try:
            with open(self.config.pnl_file_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _emergency_close_all(self) -> None:
        """Closes all open positions in an emergency."""
        self.log(
            "EMERGENCY: Daily loss limit hit. Harvesting all open positions.",
            "ERROR")
        for sym in self.config.trading.symbols:
            if self.bot_state.symbol_states[sym]["position"].qty > D0:
                self._exit_position(sym, "Emergency Stop")

    def _generate_dashboard(self) -> Layout:
        """Generates the rich-text dashboard layout."""
        with self.lock:
            layout = Layout()
            layout.split(
                Layout(name="header", size=5),
                Layout(ratio=1, name="main"),
                Layout(size=10, name="footer"),
            )
            layout["main"].split_row(Layout(name="side"), Layout(name="body", ratio=2))

            total_unrealized = sum(st["position"].unrealized_pnl for st in self.bot_state.symbol_states.values())
            total_exposure = sum(st["position"].size_usd for st in self.bot_state.symbol_states.values())
            exposure_pct = (total_exposure / self.bot_state.equity * D100) if self.bot_state.equity > D0 else D0
            status = "EMERGENCY" if self.bot_state.emergency_stop else "ACTIVE"
            status_style = "bold red" if self.bot_state.emergency_stop else "bold green"

            header_text = Text(justify="center")
            header_text.append(f"ARMADA V5 SUPREME – {len(self.config.trading.symbols)} REALMS [{status}]\n", style=status_style)
            header_text.append(f"Equity: {self.bot_state.equity:,.2f} USDT │ Realized PnL: {format_currency(self.bot_state.daily_realized_pnl)}\n", style="cyan")
            win_trades = sum(1 for sym_state in self.bot_state.symbol_states.values() if sym_state.get("last_trade_pnl", D0) > D0)
            total_trades = sum(1 for sym_state in self.bot_state.symbol_states.values() if sym_state.get("last_trade_pnl") is not None)
            win_rate = (win_trades / total_trades * D100) if total_trades > 0 else D0
            active_positions = sum(1 for s in self.bot_state.symbol_states.values() if s['position'].qty > D0)
            header_text.append(f"Unrealized PnL: {format_currency(total_unrealized)} │ Exposure: {exposure_pct:.1f}% │ Active: {active_positions}\n", style="cyan")
            header_text.append(f"Trades: {total_trades} │ Win Rate: {win_rate:.1f}%", style="cyan")
        layout["header"].update(Panel(header_text, box=box.DOUBLE, border_style="bright_cyan", title="[bold white]Strategy Status[/]"))

        tbl = Table(box=box.SIMPLE_HEAVY, header_style="bold magenta")
        tbl.add_column("Realm", style="bold cyan", width=12)
        tbl.add_column("Price", justify="right")
        tbl.add_column("Trend", justify="center")
        tbl.add_column("ADX", justify="right")
        tbl.add_column("Signal", justify="center")
        tbl.add_column("Position", justify="center")
        tbl.add_column("uPnL", justify="right")
        tbl.add_column("Entry | SL", justify="right")
        tbl.add_column("Status", justify="center")

        for sym, st in self.bot_state.symbol_states.items():
            pos = st.get("position", Position())
            trend_str = "[green]▲ UP[/]" if st.get("trend_up") else "[red]▼ DOWN[/]"
            adx_color = "green" if st.get("dynamic_adx_ok") else "dim"
            pos_str = f"[green]{pos.side}[/]" if pos.side == "Buy" else f"[red]{pos.side}[/]" if pos.side else "—"
            upnl_str = f"[{'green' if pos.unrealized_pnl >= 0 else 'red'}]{format_currency(pos.unrealized_pnl)}[/]" if pos.qty > D0 else "—"

            entry_sl_str = "—"
            if pos.qty > D0:
                entry_sl_str = f"{pos.entry:.4f}\n{pos.sl_price:.4f}"

            status_parts = []
            if pos.breakeven: status_parts.append("[cyan]BE[/]")
            if pos.partial_taken: status_parts.append("[yellow]P1[/]")
            if pos.second_partial_taken: status_parts.append("[magenta]P2[/]")
            status_str = " ".join(status_parts) if status_parts else "—"

            long_ready = st.get("trend_up") and st.get("mom_cross_up") and st.get("dynamic_adx_ok") and st.get("volume_spike")
            short_ready = not st.get("trend_up") and st.get("mom_cross_down") and st.get("dynamic_adx_ok") and st.get("volume_spike")
            signal = "[bold green]Long[/]" if long_ready else "[bold red]Short[/]" if short_ready else "[dim]Neutral[/]"

            tbl.add_row(sym, f"{st.get('price', D0):.5f}", trend_str, f"[{adx_color}]{st.get('adx', D0):.1f}[/]",
                        signal, pos_str, upnl_str, entry_sl_str, status_str)

        info_text = Text()
        info_text.append("[bold]Risk:[/] ", style="white")
        info_text.append(f"{self.config.risk.risk_per_trade_equity_pct:.2%} per trade\n")
        info_text.append("[bold]Daily Loss Limit:[/]", style="white")
        info_text.append(f" {self.config.risk.daily_loss_limit_usd} USD\n")
        info_text.append("\n[bold]Indicators:[/]\n", style="white")
        info_text.append(f"  SuperSmoother: {self.config.indicators.smoother_period}\n")
        info_text.append(f"  ADX/ATR Period: {self.config.indicators.adx_period}\n")
        info_text.append(f"  Chandelier: {self.config.indicators.chandelier_period}p, {self.config.indicators.chandelier_mult}x\n")


        layout["side"].update(Panel(info_text, title="[bold green]Configuration[/]", border_style="green"))
        layout["body"].update(Panel(tbl, title="[bold magenta]Fleet Vigilance[/]", border_style="magenta"))
        layout["footer"].update(Panel("\n".join(self.ui.logs), title="[bold yellow]Chronicle of the Ether[/]", border_style="yellow"))
        return layout

    def run(self) -> None:
        """Starts the trading bot and its main loop."""
        if not self.config.trading.symbols:
            self.log(
                "No valid realms to forge. Armada cannot launch.",
                "ERROR")
            return

        pub_ws = WebSocket(testnet=False, channel_type="linear")
        pub_ws.kline_stream(
            self.config.trading.interval,
            self.config.trading.symbols,
            self._handle_kline)

        priv_ws = WebSocket(
            testnet=False,
            channel_type="private",
            api_key=self.api.key,
            api_secret=self.api.secret)
        priv_ws.execution_stream(self._handle_execution)

        threading.Thread(target=self._periodic_sync, daemon=True).start()

        def signal_handler(signum, frame):
            """Gracefully handles Ctrl+C interrupts."""
            self.log("Manual override received. Closing all positions gracefully...", "WARNING")
            self.bot_state.is_running = False
            for sym in self.config.trading.symbols:
                if self.bot_state.symbol_states[sym]["position"].qty > D0:
                    self._exit_position(sym, "Manual Shutdown")

        signal.signal(signal.SIGINT, signal_handler)

        with Live(self._generate_dashboard(), refresh_per_second=4, console=self.ui.console) as live:
            while self.bot_state.is_running:
                if self.bot_state.daily_realized_pnl <= self.config.risk.daily_loss_limit_usd and not self.bot_state.emergency_stop:
                    self.bot_state.emergency_stop = True
                    self._emergency_close_all()
                live.update(self._generate_dashboard())
                time.sleep(0.25)

    def _periodic_sync(self) -> None:
        """Periodically synchronizes equity."""
        while self.bot_state.is_running:
            time.sleep(60)
            self._sync_equity()


if __name__ == "__main__":
    try:
        bot_config = Config()
        armada = ArmadaV5EternalSupreme(bot_config)
        armada.run()
    except ValueError as e:
        print(Fore.RED + Style.BRIGHT + f"Configuration Error: {e}")
    except KeyboardInterrupt:
        print(
            Fore.YELLOW +
            Style.BRIGHT +
            "\n# Manual override detected. Armada returns to silence.")
    except Exception as e:
        print(Fore.RED + Style.BRIGHT + f"\n# A critical error occurred: {e}")
    finally:
        print(Style.RESET_ALL)
