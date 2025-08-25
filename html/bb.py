import collections
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any, Optional

import numpy as np
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pybit.unified_trading import HTTP

# Optional system metrics
try:
    import psutil  # type: ignore
    PSUTIL_AVAILABLE = True
except Exception:
    PSUTIL_AVAILABLE = False

import google.generativeai as genai

# =====================================================================
# CONFIGURATION & UTILITIES
# =====================================================================

# --- Environment Variables ---
load_dotenv()
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)

# --- Market Conditions Enum ---
class MarketCondition(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"
    BREAKOUT = "breakout"
    CONSOLIDATION = "consolidation"

# --- Enhanced Trade Analytics ---
@dataclass
class TradeAnalytics:
    """Enhanced trade analytics and statistics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_trade_duration: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    current_streak: int = 0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    trade_returns: list[float] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def update_metrics(self, trade_result: dict[str, Any]):
        """Update analytics with new trade result"""
        pnl = float(trade_result.get('pnl', 0.0))
        fees = float(trade_result.get('fees', 0.0))
        duration = float(trade_result.get('duration_hours', 0.0))
        self.total_trades += 1
        self.total_pnl += pnl
        self.total_fees += fees
        net = pnl - fees
        self.trade_returns.append(net)

        # Update equity curve
        if self.equity_curve:
            self.equity_curve.append(self.equity_curve[-1] + net)
        else:
            self.equity_curve.append(net)

        # Streaks and extremes
        if pnl > 0:
            self.winning_trades += 1
            self.current_streak = self.current_streak + 1 if self.current_streak >= 0 else 1
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.current_streak)
            self.best_trade = max(self.best_trade, pnl)
        else:
            self.losing_trades += 1
            self.current_streak = self.current_streak - 1 if self.current_streak <= 0 else -1
            self.max_consecutive_losses = max(self.max_consecutive_losses, abs(self.current_streak))
            self.worst_trade = min(self.worst_trade, pnl)

        # Totals for wins/losses
        wins = [r for r in self.trade_returns if r > 0]
        losses = [-r for r in self.trade_returns if r < 0]
        total_wins = sum(wins)
        total_losses = sum(losses)

        # Averages
        if self.winning_trades > 0:
            self.avg_win = total_wins / self.winning_trades
        if self.losing_trades > 0:
            self.avg_loss = total_losses / self.losing_trades

        # Metrics
        self.win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades else 0.0
        self.profit_factor = (total_wins / total_losses) if total_losses > 0 else float('inf') if total_wins > 0 else 0.0
        self.expectancy = (self.win_rate / 100.0) * self.avg_win - (1 - self.win_rate / 100.0) * self.avg_loss

        # Sharpe (per-trade; annualize by sqrt(252) if desired)
        if len(self.trade_returns) > 1:
            arr = np.array(self.trade_returns, dtype=float)
            std = arr.std(ddof=1)
            if std > 0:
                self.sharpe_ratio = arr.mean() / std

        # Max drawdown
        self._update_max_drawdown()

        # Avg duration
        self.avg_trade_duration = ((self.avg_trade_duration * (self.total_trades - 1)) + duration) / self.total_trades

        # Recovery factor
        if self.max_drawdown > 0:
            self.recovery_factor = self.total_pnl / self.max_drawdown

    def _update_max_drawdown(self):
        if not self.equity_curve:
            return
        peak = -float('inf')
        max_dd = 0.0
        for v in self.equity_curve:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd:
                max_dd = dd
        self.max_drawdown = max_dd
        if peak > 0:
            self.max_drawdown_pct = (max_dd / peak) * 100.0

# --- Performance Monitor ---
@dataclass
class PerformanceMonitor:
    """Monitor system and trading performance"""
    start_time: datetime = field(default_factory=datetime.now)
    api_calls_count: int = 0
    api_errors_count: int = 0
    last_api_error: str | None = None
    signal_count: int = 0
    false_signals: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_pct: float = 0.0
    uptime_hours: float = 0.0
    last_health_check: datetime = field(default_factory=datetime.now)
    avg_api_response_ms: float = 0.0
    _response_times: collections.deque = field(default_factory=lambda: collections.deque(maxlen=200))

    def update_uptime(self):
        self.uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600.0

    def capture_response_time(self, ms: float):
        self._response_times.append(ms)
        if self._response_times:
            self.avg_api_response_ms = sum(self._response_times) / len(self._response_times)

    def update_system_metrics(self):
        if PSUTIL_AVAILABLE:
            try:
                p = psutil.Process()
                self.memory_usage_mb = p.memory_info().rss / (1024 * 1024)
                self.cpu_usage_pct = psutil.cpu_percent(interval=0.1)
            except Exception:
                pass

    def get_health_status(self) -> dict[str, Any]:
        self.update_uptime()
        self.update_system_metrics()
        error_rate = (self.api_errors_count / self.api_calls_count * 100.0) if self.api_calls_count else 0.0
        status = "healthy"
        if error_rate >= 10 or self.cpu_usage_pct > 85 or self.memory_usage_mb > 800:
            status = "degraded"
        if error_rate >= 25:
            status = "unhealthy"
        return {
            "status": status,
            "uptime_hours": round(self.uptime_hours, 2),
            "api_calls": self.api_calls_count,
            "api_error_rate": round(error_rate, 2),
            "avg_api_response_ms": round(self.avg_api_response_ms, 2),
            "last_error": self.last_api_error,
            "memory_usage_mb": round(self.memory_usage_mb, 2),
            "cpu_usage_pct": round(self.cpu_usage_pct, 2)
        }

# --- Risk Manager ---
@dataclass
class RiskManager:
    """Enhanced risk management system"""
    max_daily_loss_pct: float = 5.0
    max_weekly_loss_pct: float = 10.0
    max_daily_trades: int = 20
    max_position_size_pct: float = 10.0
    max_correlation_positions: int = 3
    position_timeout_hours: float = 24.0
    emergency_stop_loss_pct: float = 15.0

    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    daily_trades: int = 0
    daily_reset_time: datetime = field(default_factory=datetime.now)
    weekly_reset_time: datetime = field(default_factory=datetime.now)
    positions_opened_today: list[dict] = field(default_factory=list)
    consecutive_losses: int = 0
    risk_multiplier: float = 1.0

    def check_daily_limits(self, account_balance: float) -> tuple[bool, str]:
        """Check if daily/weekly trading limits are exceeded"""
        # Reset daily counters if new day
        if datetime.now().date() > self.daily_reset_time.date():
            self.daily_loss = 0.0
            self.daily_trades = 0
            self.positions_opened_today = []
            self.daily_reset_time = datetime.now()

        # Reset weekly counters if new week number changed
        if datetime.now().isocalendar()[1] != self.weekly_reset_time.isocalendar()[1]:
            self.weekly_loss = 0.0
            self.weekly_reset_time = datetime.now()

        daily_loss_pct = abs(self.daily_loss / account_balance * 100) if account_balance > 0 else 0
        weekly_loss_pct = abs(self.weekly_loss / account_balance * 100) if account_balance > 0 else 0

        if daily_loss_pct >= self.max_daily_loss_pct:
            return False, f"Daily loss limit reached: {daily_loss_pct:.2f}%"
        if weekly_loss_pct >= self.max_weekly_loss_pct:
            return False, f"Weekly loss limit reached: {weekly_loss_pct:.2f}%"
        if self.daily_trades >= self.max_daily_trades:
            return False, f"Daily trade limit reached: {self.daily_trades}/{self.max_daily_trades}"
        return True, "Within limits"

    def check_position_timeout(self, entry_time: datetime) -> bool:
        hours_open = (datetime.now() - entry_time).total_seconds() / 3600.0
        return hours_open > self.position_timeout_hours

    def calculate_position_size(self, account_balance: float, risk_pct: float, stop_distance_pct: float, volatility_pct: float = 1.0) -> float:
        """Calculate safe position size with volatility and max cap"""
        # Dynamic risk: reduce if volatility is high
        vol_adjust = max(0.5, min(1.5, 1.0 / max(volatility_pct, 0.001)))  # between 0.5x and 1.5x
        adjusted_risk_pct = max(0.25, min(2.0, (risk_pct * self.risk_multiplier * vol_adjust)))
        base_position_size = (account_balance * adjusted_risk_pct / 100.0) / (max(1e-9, stop_distance_pct) / 100.0)
        max_position_size = account_balance * self.max_position_size_pct / 100.0
        return min(base_position_size, max_position_size)

    def update_trade_result(self, pnl: float):
        """Update risk stats after a trade closes"""
        self.daily_trades += 1
        if pnl < 0:
            self.daily_loss += pnl
            self.weekly_loss += pnl
            self.consecutive_losses += 1
            # Reduce risk after losses
            self.risk_multiplier = max(0.5, self.risk_multiplier - 0.1)
        else:
            self.consecutive_losses = 0
            # Slowly increase risk after wins (capped)
            self.risk_multiplier = min(1.5, self.risk_multiplier + 0.05)

# --- Market Analyzer ---
class MarketAnalyzer:
    """Lightweight market analysis for volatility and condition detection"""
    @staticmethod
    def atr_volatility_pct(klines: list[dict], period: int = 14) -> float:
        if len(klines) < period + 1:
            return 1.0
        trs = []
        for i in range(1, len(klines)):
            high = klines[i]['high']
            low = klines[i]['low']
            prev_close = klines[i-1]['close']
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        atr = sum(trs[-period:]) / float(period)
        last_close = klines[-1]['close']
        return (atr / last_close) * 100.0 if last_close > 0 else 1.0

    @staticmethod
    def detect_condition(klines: list[dict], rsi: float) -> MarketCondition:
        if len(klines) < 50:
            return MarketCondition.RANGING
        change_pct = (klines[-1]['close'] - klines[-50]['close']) / klines[-50]['close'] * 100.0
        vol = MarketAnalyzer.atr_volatility_pct(klines)
        if vol > 3.0 and abs(change_pct) > 5.0:
            return MarketCondition.BREAKOUT
        if vol > 3.0:
            return MarketCondition.VOLATILE
        if vol < 1.0:
            return MarketCondition.CONSOLIDATION
        if change_pct > 3.0 and rsi > 55:
            return MarketCondition.TRENDING_UP
        if change_pct < -3.0 and rsi < 45:
            return MarketCondition.TRENDING_DOWN
        return MarketCondition.RANGING

# --- Global Bot State (Enhanced) ---
@dataclass
class BotState:
    """Centralized state for the trading bot with enhanced features."""
    running: bool = False
    thread: threading.Thread | None = None
    config: dict[str, Any] = field(default_factory=dict)
    bybit_session: HTTP | None = None
    precision_manager: Optional['PrecisionManager'] = None
    logs: collections.deque = field(default_factory=lambda: collections.deque(maxlen=500))
    trade_history: dict[str, int | list] = field(default_factory=lambda: {"wins": 0, "losses": 0, "history": []})
    dashboard: dict[str, Any] = field(default_factory=lambda: {
        "currentPrice": "---",
        "priceChange": "---",
        "priceChange24h": "---",
        "volume24h": "---",
        "stDirection": "---",
        "stValue": "---",
        "rsiValue": "---",
        "rsiStatus": "---",
        "fisherValue": "---",
        "macdLine": "---",
        "macdSignal": "---",
        "macdHistogram": "---",
        "bbMiddle": "---",
        "bbUpper": "---",
        "bbLower": "---",
        "currentPosition": "None",
        "positionPnL": "---",
        "positionPnLPct": "---",
        "accountBalance": "---",
        "availableBalance": "---",
        "totalTrades": 0,
        "winRate": "0%",
        "profitFactor": "0.00",
        "expectancy": "0.00",
        "botStatus": "Idle",
        "marketCondition": "---",
        "signalStrength": "---",
        "nextCandle": "---",
        "healthStatus": "---"
    })
    last_supertrend: dict[str, int | float] = field(default_factory=lambda: {"direction": 0, "value": 0})
    current_position_info: dict[str, str | float | int | None] = field(default_factory=lambda: {
        "order_id": None,
        "entry_price": None,
        "side": None,
        "peak_price": None,
        "entry_time": None,
        "trailing_activated": False,
        "size": None
    })

    # Enhanced components
    trade_analytics: TradeAnalytics = field(default_factory=TradeAnalytics)
    performance_monitor: PerformanceMonitor = field(default_factory=PerformanceMonitor)
    risk_manager: RiskManager = field(default_factory=RiskManager)
    market_condition: MarketCondition = MarketCondition.RANGING
    emergency_stop: bool = False
    last_signal_strength: float = 0.0
    price_history: collections.deque = field(default_factory=lambda: collections.deque(maxlen=100))

BOT_STATE = BotState()

# --- Enhanced Logging Utility ---
def log_message(message: str, level: str = 'info', category: str = 'general'):
    """Enhanced logging with categories and structured data."""
    timestamp = datetime.now()
    log_entry = {
        "timestamp": timestamp.strftime("%H:%M:%S"),
        "date": timestamp.strftime("%Y-%m-%d"),
        "level": level,
        "category": category,
        "message": message
    }
    BOT_STATE.logs.append(log_entry)
    if level == 'error':
        logger.error(f"[{category}] {message}")
    elif level == 'warning':
        logger.warning(f"[{category}] {message}")
    elif level == 'success':
        logger.info(f"SUCCESS [{category}] {message}")
    elif level == 'signal':
        logger.info(f"SIGNAL [{category}] {message}")
    else:
        logger.info(f"[{category}] {message}")

# --- Instrument Specifications & Precision Management ---
@dataclass
class InstrumentSpecs:
    """Store instrument specifications from Bybit"""
    symbol: str
    category: str
    base_currency: str
    quote_currency: str
    status: str

    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal  # Price precision

    min_order_qty: Decimal
    max_order_qty: Decimal
    qty_step: Decimal  # Quantity precision

    min_leverage: Decimal
    max_leverage: Decimal
    leverage_step: Decimal

    max_position_value: Decimal
    min_position_value: Decimal

    contract_value: Decimal = Decimal('1')
    is_inverse: bool = False

    maker_fee: Decimal = Decimal('0.0001')
    taker_fee: Decimal = Decimal('0.0006')

class PrecisionManager:
    """Manage decimal precision for different trading pairs"""

    def __init__(self, session: HTTP, logger: logging.Logger):
        self.session = session
        self.logger = logger
        self.instruments: dict[str, InstrumentSpecs] = {}
        self.load_all_instruments()

    def load_all_instruments(self):
        """Load all instrument specifications from Bybit"""
        categories = ['linear', 'inverse', 'spot', 'option']
        for category in categories:
            try:
                response = self._make_api_call('get', 'get_instruments_info', params={'category': category})
                if response and response['retCode'] == 0:
                    for inst in response['result']['list']:
                        symbol = inst['symbol']
                        try:
                            if category in ['linear', 'inverse']:
                                specs = self._parse_derivatives_specs(inst, category)
                            elif category == 'spot':
                                specs = self._parse_spot_specs(inst, category)
                            else:  # option
                                specs = self._parse_option_specs(inst, category)
                            self.instruments[symbol] = specs
                        except Exception as parse_e:
                            self.logger.warning(f"Could not parse specs for {symbol} ({category}): {parse_e}")
            except Exception as e:
                self.logger.error(f"Error loading {category} instruments: {e}")

    def _make_api_call(self, method: str, endpoint: str, params: dict | None = None, max_retries: int = 3, initial_delay: int = 1) -> dict | None:
        """Internal helper for API calls with retry logic."""
        BOT_STATE.performance_monitor.api_calls_count += 1
        start = time.time()
        for attempt in range(max_retries):
            try:
                if method == 'get':
                    response = getattr(self.session, endpoint)(**params) if params else getattr(self.session, endpoint)()
                elif method == 'post' or method == 'amend':
                    response = getattr(self.session, endpoint)(**params)
                else:
                    self.logger.error(f"Invalid method '{method}' for API call.")
                    return {"retCode": 1, "retMsg": "Invalid method"}
                # Track response time for performance monitor
                elapsed_ms = (time.time() - start) * 1000.0
                BOT_STATE.performance_monitor.capture_response_time(elapsed_ms)

                if response.get('retCode') == 0:
                    return response
                else:
                    ret_code = response.get('retCode')
                    ret_msg = response.get('retMsg', 'Unknown Error')
                    BOT_STATE.performance_monitor.api_errors_count += 1
                    BOT_STATE.performance_monitor.last_api_error = ret_msg
                    self.logger.warning(f"Bybit API Error ({ret_code}): {ret_msg} for {endpoint}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
                    time.sleep(initial_delay * (2**attempt))
            except Exception as e:
                BOT_STATE.performance_monitor.api_errors_count += 1
                BOT_STATE.performance_monitor.last_api_error = str(e)
                self.logger.error(f"API call error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})")
                time.sleep(initial_delay * (2**attempt))
        self.logger.error(f"Failed to complete API call to {endpoint} after {max_retries} attempts.")
        return None

    def _parse_derivatives_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parse derivatives instrument specifications"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        leverage = inst.get('leverageFilter', {})
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.00000001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
            min_leverage=Decimal(leverage.get('minLeverage', '1')),
            max_leverage=Decimal(leverage.get('maxLeverage', '10')),
            leverage_step=Decimal(leverage.get('leverageStep', '0.01')),
            max_position_value=Decimal(lot_size.get('maxMktOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal(inst.get('contractValue', '1')),
            is_inverse=(category == 'inverse')
        )

    def _parse_spot_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parse spot instrument specifications"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
            min_leverage=Decimal('1'),
            max_leverage=Decimal('1'),
            leverage_step=Decimal('1'),
            max_position_value=Decimal(lot_size.get('maxOrderAmt', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderAmt', '1')),
            contract_value=Decimal('1'),
            is_inverse=False
        )

    def _parse_option_specs(self, inst: dict, category: str) -> InstrumentSpecs:
        """Parse option instrument specifications"""
        lot_size = inst.get('lotSizeFilter', {})
        price_filter = inst.get('priceFilter', {})
        return InstrumentSpecs(
            symbol=inst['symbol'],
            category=category,
            base_currency=inst['baseCoin'],
            quote_currency=inst['quoteCoin'],
            status=inst['status'],
            min_price=Decimal(price_filter.get('minPrice', '0')),
            max_price=Decimal(price_filter.get('maxPrice', '100000000')),
            tick_size=Decimal(price_filter.get('tickSize', '0.0001')),
            min_order_qty=Decimal(lot_size.get('minOrderQty', '0.001')),
            max_order_qty=Decimal(lot_size.get('maxOrderQty', '1000000')),
            qty_step=Decimal(lot_size.get('qtyStep', '0.001')),
            min_leverage=Decimal('1'),
            max_leverage=Decimal('1'),
            leverage_step=Decimal('1'),
            max_position_value=Decimal(lot_size.get('maxOrderQty', '1000000')),
            min_position_value=Decimal(lot_size.get('minOrderQty', '1')),
            contract_value=Decimal('1'),
            is_inverse=False
        )

    def round_price(self, symbol: str, price: float | Decimal) -> Decimal:
        """Round price to correct tick size and within bounds."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default price precision (0.01).")
            return Decimal(str(price)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        specs = self.instruments[symbol]
        price_decimal = Decimal(str(price))
        tick_size = specs.tick_size
        rounded = (price_decimal / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
        rounded = max(specs.min_price, min(rounded, specs.max_price))
        return rounded

    def round_quantity(self, symbol: str, quantity: float | Decimal) -> Decimal:
        """Round quantity to correct step size and within bounds."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found, using default quantity precision (0.001).")
            return Decimal(str(quantity)).quantize(Decimal('0.001'), rounding=ROUND_DOWN)
        specs = self.instruments[symbol]
        qty_decimal = Decimal(str(quantity))
        qty_step = specs.qty_step
        rounded = (qty_decimal / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
        rounded = max(specs.min_order_qty, min(rounded, specs.max_order_qty))
        return rounded

    def get_decimal_places(self, symbol: str) -> tuple[int, int]:
        """Get decimal places for price and quantity."""
        if symbol not in self.instruments:
            self.logger.warning(f"Symbol {symbol} not found for decimal places, returning defaults (2, 3).")
            return 2, 3
        specs = self.instruments[symbol]
        price_decimals = abs(specs.tick_size.as_tuple().exponent) if specs.tick_size != 0 else 2
        qty_decimals = abs(specs.qty_step.as_tuple().exponent) if specs.qty_step != 0 else 3
        return price_decimals, qty_decimals

# --- Indicator Calculation (with fallback) ---
try:
    from indicators import calculate_indicators
except ImportError:
    logger.error("Could not import 'calculate_indicators' from 'indicators.py'. Using a dummy fallback.")
    def calculate_indicators(klines, config):
        # Minimal fallback to keep bot running
        close = klines[-1]['close'] if klines else 0
        return {
            'supertrend': {'direction': 1 if len(klines) % 2 else -1, 'supertrend': close * 0.99},
            'rsi': 50.0,
            'fisher': 0.0,
            'macd': {'macd_line': 0.0, 'signal_line': 0.0, 'histogram': 0.0},
            'bollinger_bands': {'middle_band': close, 'upper_band': close * 1.01, 'lower_band': close * 0.99}
        }

# =====================================================================
# TRADING BOT LOGIC
# =====================================================================
def trading_bot_loop():
    """The main loop for the trading bot, running in a separate thread."""
    log_message("Trading bot thread started.", "success")
    market_analyzer = MarketAnalyzer()

    while BOT_STATE.running:
        try:
            config = BOT_STATE.config
            session = BOT_STATE.bybit_session
            precision_mgr = BOT_STATE.precision_manager
            dashboard = BOT_STATE.dashboard

            if not session or not precision_mgr:
                log_message("Session or Precision Manager not initialized. Stopping bot thread.", "error")
                BOT_STATE.running = False
                break

            dashboard["botStatus"] = "Scanning"

            # 1. Fetch Kline Data
            interval = config["interval"]
            symbol = config["symbol"]
            kline_limit = max(200, config.get("kline_limit", 200))
            klines_res = _make_api_call(session, 'get', 'get_kline', params={
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": kline_limit
            })
            if not klines_res or klines_res.get('retCode') != 0:
                msg = klines_res.get('retMsg', 'Unknown API error') if klines_res else 'No response'
                log_message(f"Failed to fetch klines: {msg}", "error")
                dashboard["botStatus"] = "API Error"
                time.sleep(config.get('api_error_retry_delay', 60))
                continue

            # Normalize klines
            klines = sorted([{
                "timestamp": int(k[0]), "open": float(k[1]), "high": float(k[2]),
                "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])
            } for k in klines_res['result']['list']], key=lambda x: x['timestamp'])

            if not klines:
                log_message("No kline data received. Waiting for data.", "warning")
                dashboard["botStatus"] = "Waiting for Data"
                time.sleep(config.get('indicator_wait_delay', 60))
                continue

            current_price = klines[-1]['close']
            # Price change (last candle vs prev) and 24h (if enough data)
            if len(klines) >= 2:
                dashboard['priceChange'] = f"{((klines[-1]['close'] - klines[-2]['close']) / klines[-2]['close'] * 100):.2f}%"
            if len(klines) >= 1440 // max(1, int(interval) if str(interval).isdigit() else 60):
                start_idx = max(0, len(klines) - (1440 // max(1, int(interval) if str(interval).isdigit() else 60)))
                first = klines[start_idx]['close']
                dashboard['priceChange24h'] = f"{((current_price - first) / first * 100):.2f}%"
                dashboard['volume24h'] = f"{sum(k['volume'] for k in klines[start_idx:]):.2f}"

            # 2. Calculate Indicators
            indicators = calculate_indicators(klines, config)
            if not indicators:
                log_message("Indicator calculation failed or returned no data. Waiting.", "warning")
                dashboard["botStatus"] = "Indicator Error"
                time.sleep(config.get('indicator_wait_delay', 60))
                continue

            # 3. Fetch Position and Balance
            position_res = _make_api_call(session, 'get', 'get_positions', params={"category": "linear", "symbol": symbol})
            balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})

            current_position = None
            open_position_size = 0.0
            pos_side = None
            entry_price = None
            if position_res and position_res.get('retCode') == 0:
                # Filter for open positions with size > 0
                pos_list = [p for p in position_res['result']['list'] if float(p.get('size', 0)) > 0]
                if pos_list:
                    current_position = pos_list[0]
                    open_position_size = float(current_position.get('size', 0))
                    pos_side = current_position.get('side')
                    entry_price = float(current_position.get('avgPrice', 0) or 0)
            else:
                msg = position_res.get('retMsg', 'Unknown API error') if position_res else 'No response'
                log_message(f"Failed to fetch positions: {msg}", "error")

            account_balance = 0.0
            available_balance = 0.0
            if balance_res and balance_res.get('retCode') == 0 and balance_res.get('result', {}).get('list'):
                usdt_entry = balance_res['result']['list'][0]
                account_balance = float(usdt_entry.get('totalWalletBalance') or usdt_entry.get('totalEquity') or 0)
                available_balance = float(usdt_entry.get('availableBalance') or 0)
            else:
                msg = balance_res.get('retMsg', 'Unknown API error') if balance_res else 'No response'
                log_message(f"Failed to fetch balance: {msg}", "error")

            # 4. Update Dashboard (indicators + balances)
            price_prec = config['price_precision']
            dashboard['currentPrice'] = f"${current_price:.{price_prec}f}"
            st = indicators.get('supertrend', {})
            st_dir = st.get('direction', 0)
            st_val = st.get('supertrend', None)
            dashboard['stDirection'] = "UP" if st_dir == 1 else "DOWN" if st_dir == -1 else "SIDEWAYS"
            dashboard['stValue'] = f"{st_val:.{price_prec}f}" if st_val is not None else "---"
            rsi = float(indicators.get('rsi', 50.0))
            dashboard['rsiValue'] = f"{rsi:.2f}"
            fisher = float(indicators.get('fisher', 0.0))
            dashboard['fisherValue'] = f"{fisher:.2f}"
            macd = indicators.get('macd', {})
            dashboard['macdLine'] = f"{macd.get('macd_line', 0.0):.2f}" if 'macd_line' in macd else "---"
            dashboard['macdSignal'] = f"{macd.get('signal_line', 0.0):.2f}" if 'signal_line' in macd else "---"
            dashboard['macdHistogram'] = f"{macd.get('histogram', 0.0):.2f}" if 'histogram' in macd else "---"
            bb = indicators.get('bollinger_bands', {})
            dashboard['bbMiddle'] = f"{bb.get('middle_band', 0.0):.{price_prec}f}" if 'middle_band' in bb else "---"
            dashboard['bbUpper'] = f"{bb.get('upper_band', 0.0):.{price_prec}f}" if 'upper_band' in bb else "---"
            dashboard['bbLower'] = f"{bb.get('lower_band', 0.0):.{price_prec}f}" if 'lower_band' in bb else "---"
            dashboard['accountBalance'] = f"${account_balance:.2f}"
            dashboard['availableBalance'] = f"${available_balance:.2f}"

            # Market analysis
            vol_pct = market_analyzer.atr_volatility_pct(klines)
            BOT_STATE.market_condition = market_analyzer.detect_condition(klines, rsi)
            dashboard['marketCondition'] = BOT_STATE.market_condition.value
            dashboard['signalStrength'] = "N/A"  # placeholder for custom scoring if needed
            dashboard['healthStatus'] = BOT_STATE.performance_monitor.get_health_status().get('status', 'unknown')
            dashboard['volatility'] = f"{vol_pct:.2f}%"

            if current_position:
                pnl_unreal = (current_price - entry_price) * open_position_size if pos_side == 'Buy' else (entry_price - current_price) * open_position_size
                pnl_pct = ((current_price - entry_price) / entry_price * 100.0) if entry_price else 0.0
                dashboard['currentPosition'] = f"{pos_side} {open_position_size} @ {entry_price}"
                dashboard['positionPnL'] = f"{pnl_unreal:.2f} USDT"
                dashboard['positionPnLPct'] = f"{pnl_pct:.2f}%"
            else:
                dashboard['currentPosition'] = "None"
                dashboard['positionPnL'] = "---"
                dashboard['positionPnLPct'] = "---"

            # 5. Trailing Stop Loss Logic + Position Timeout
            if BOT_STATE.current_position_info["order_id"] and current_position:
                pos_info = BOT_STATE.current_position_info
                # Update peak
                if pos_info["side"] == "Buy":
                    pos_info["peak_price"] = max(pos_info.get("peak_price", current_price), current_price)
                else:
                    pos_info["peak_price"] = min(pos_info.get("peak_price", current_price), current_price)

                trailing_stop_pct = config.get('trailingStopPct', 0.5) / 100.0
                new_sl = 0.0
                if pos_info["side"] == "Buy":
                    new_sl = pos_info["peak_price"] * (1 - trailing_stop_pct)
                else:
                    new_sl = pos_info["peak_price"] * (1 + trailing_stop_pct)
                new_sl = float(precision_mgr.round_price(symbol, new_sl))

                # current SL from position (if available)
                current_sl_on_exchange = float(current_position.get('stopLoss', 0) or 0.0)

                amend_sl = False
                if (pos_info["side"] == "Buy" and new_sl > current_sl_on_exchange and new_sl > pos_info["entry_price"]) or (pos_info["side"] == "Sell" and (current_sl_on_exchange == 0.0 or new_sl < current_sl_on_exchange) and new_sl < pos_info["entry_price"]):
                    amend_sl = True

                # Position timeout handling (convert to market close)
                entry_time = pos_info.get("entry_time")
                if entry_time and BOT_STATE.risk_manager.check_position_timeout(entry_time):
                    log_message(f"Position timeout reached. Closing position {pos_side}.", "warning")
                    close_res = _make_api_call(session, 'post', 'place_order', params={
                        "category": "linear",
                        "symbol": symbol,
                        "side": "Sell" if pos_side == "Buy" else "Buy",
                        "orderType": "Market",
                        "qty": current_position['size'],
                        "reduceOnly": True,
                        "tpslMode": "Full"
                    })
                    if close_res and close_res.get('retCode') == 0:
                        # Approximate realized pnl on timeout
                        closed_pnl = (current_price - entry_price) * open_position_size if pos_side == 'Buy' else (entry_price - current_price) * open_position_size
                        BOT_STATE.trade_analytics.update_metrics({"pnl": closed_pnl, "fees": 0.0, "duration_hours": (datetime.now() - entry_time).total_seconds()/3600.0})
                        BOT_STATE.risk_manager.update_trade_result(closed_pnl)
                        log_message("Position closed due to timeout.", "success")
                        BOT_STATE.current_position_info = {"order_id": None, "entry_price": None, "side": None, "peak_price": None, "entry_time": None, "trailing_activated": False, "size": None}
                        time.sleep(2)
                        continue
                    else:
                        log_message(f"Failed to close position on timeout: {close_res.get('retMsg', 'Unknown API error') if close_res else 'No response'}", "error")

                if amend_sl:
                    log_message(f"Amending trailing stop for {pos_info['side']} from {current_sl_on_exchange:.{price_prec}f} to {new_sl:.{price_prec}f}", "info")
                    amend_res = _make_api_call(session, 'post', 'amend_order', params={
                        "category": "linear",
                        "symbol": symbol,
                        "orderId": pos_info["order_id"],
                        "stopLoss": f"{new_sl:.{price_prec}}"
                    })
                    if amend_res and amend_res.get('retCode') == 0:
                        log_message("Trailing stop amended successfully.", "success")
                    else:
                        msg = amend_res.get('retMsg', 'Unknown API error') if amend_res else 'No response'
                        log_message(f"Failed to amend trailing stop: {msg}", "error")

            # 6. Core Trading Logic
            fisher_thr = float(config.get('fisher_threshold', 0.0))
            buy_signal = (st_dir == 1 and BOT_STATE.last_supertrend.get('direction', 0) == -1 and rsi < config.get('rsi_overbought', 70) and fisher > fisher_thr)
            sell_signal = (st_dir == -1 and BOT_STATE.last_supertrend.get('direction', 0) == 1 and rsi > config.get('rsi_oversold', 30) and fisher < -fisher_thr)

            # Risk gate checks before acting on signals
            within_limits, reason = BOT_STATE.risk_manager.check_daily_limits(account_balance)
            if not within_limits:
                log_message(f"Risk limits prevent trading: {reason}", "warning")
                dashboard["botStatus"] = "Risk-Limited"
            else:
                if buy_signal or sell_signal:
                    side = "Buy" if buy_signal else "Sell"
                    log_message(f"{side.upper()} SIGNAL DETECTED!", "signal")

                    # Close existing opposite position first
                    if current_position and pos_side != side:
                        log_message(f"Closing opposite {pos_side} position.", "warning")
                        close_res = _make_api_call(session, 'post', 'place_order', params={
                            "category": "linear",
                            "symbol": symbol,
                            "side": "Sell" if pos_side == "Buy" else "Buy",
                            "orderType": "Market",
                            "qty": current_position['size'],
                            "reduceOnly": True,
                            "tpslMode": "Full"
                        })
                        if close_res and close_res.get('retCode') == 0:
                            closed_pnl = (current_price - entry_price) * open_position_size if pos_side == 'Buy' else (entry_price - current_price) * open_position_size
                            BOT_STATE.trade_analytics.update_metrics({"pnl": closed_pnl, "fees": 0.0, "duration_hours": (datetime.now() - (BOT_STATE.current_position_info.get("entry_time") or datetime.now())).total_seconds()/3600.0})
                            BOT_STATE.risk_manager.update_trade_result(closed_pnl)
                            log_message("Opposite position closed successfully.", "success")
                            time.sleep(2)
                            BOT_STATE.current_position_info = {"order_id": None, "entry_price": None, "side": None, "peak_price": None, "entry_time": None, "trailing_activated": False, "size": None}
                            # Refresh balance post-close
                            balance_res = _make_api_call(session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})
                            if balance_res and balance_res.get('retCode') == 0 and balance_res.get('result', {}).get('list'):
                                usdt_entry = balance_res['result']['list'][0]
                                account_balance = float(usdt_entry.get('totalWalletBalance') or usdt_entry.get('totalEquity') or 0)
                        else:
                            msg = close_res.get('retMsg', 'Unknown API error') if close_res else 'No response'
                            log_message(f"Failed to close opposite position: {msg}", "error")
                            continue

                    # --- Place New Order ---
                    sl_pct = float(config.get('stopLossPct', 1.0)) / 100.0
                    tp_pct = float(config.get('takeProfitPct', 2.0)) / 100.0

                    sl_price = current_price * (1 - sl_pct) if side == 'Buy' else current_price * (1 + sl_pct)
                    tp_price = current_price * (1 + tp_pct) if side == 'Buy' else current_price * (1 - tp_pct)

                    sl_price = float(precision_mgr.round_price(symbol, sl_price))
                    tp_price = float(precision_mgr.round_price(symbol, tp_price))

                    stop_distance = abs(current_price - sl_price)
                    if stop_distance <= 0:
                        log_message("Stop loss distance is zero or negative. Cannot place order.", "error")
                        continue

                    stop_distance_pct = (stop_distance / current_price) * 100.0 if current_price > 0 else 0.0
                    risk_pct = float(config.get('riskPct', 1.0))
                    position_value_usdt = BOT_STATE.risk_manager.calculate_position_size(account_balance, risk_pct, stop_distance_pct, vol_pct)

                    MIN_ORDER_VALUE_USDT = float(config.get('minOrderValueUSDT', 10.0))
                    if position_value_usdt < MIN_ORDER_VALUE_USDT or current_price <= 0:
                        log_message(f"Position value {position_value_usdt:.2f} USDT below min {MIN_ORDER_VALUE_USDT} or invalid price. Skipping.", "warning")
                        continue

                    qty_in_base_currency = position_value_usdt / current_price
                    rounded_qty = precision_mgr.round_quantity(symbol, qty_in_base_currency)
                    if rounded_qty <= 0:
                        log_message("Rounded quantity is zero after precision adjustment. Skipping order.", "warning")
                        continue

                    log_message(f"Calculated position: {position_value_usdt:.2f} USDT -> {rounded_qty:.{config['qty_precision']}f} {symbol}", "info")

                    order_res = _make_api_call(session, 'post', 'place_order', params={
                        "category": "linear",
                        "symbol": symbol,
                        "side": side,
                        "orderType": "Market",
                        "qty": f"{rounded_qty:.{config['qty_precision']}f}",
                        "takeProfit": f"{tp_price:.{price_prec}f}",
                        "stopLoss": f"{sl_price:.{price_prec}f}",
                        "tpslMode": "Full"
                    })

                    if order_res and order_res.get('retCode') == 0:
                        log_message("Order placed successfully.", "success")
                        # Store position info for trailing stop
                        BOT_STATE.current_position_info = {
                            "order_id": order_res['result']['orderId'],
                            "entry_price": current_price,
                            "side": side,
                            "peak_price": current_price,
                            "entry_time": datetime.now(),
                            "trailing_activated": True,
                            "size": float(rounded_qty)
                        }
                        dashboard["totalTrades"] += 1
                        # Update analytics (trade opened; PnL recorded on close)
                    else:
                        msg = order_res.get('retMsg', 'Unknown API error') if order_res else 'No response'
                        log_message(f"Order failed: {msg}", "error")

            # Update last Supertrend state after processing signals
            if st:
                BOT_STATE.last_supertrend = st

            # Refresh high-level analytics on dashboard
            ta = BOT_STATE.trade_analytics
            dashboard['winRate'] = f"{ta.win_rate:.1f}%"
            dashboard['profitFactor'] = "∞" if ta.profit_factor == float('inf') else f"{ta.profit_factor:.2f}"
            dashboard['expectancy'] = f"{ta.expectancy:.4f}"

            dashboard["botStatus"] = "Idle"

        except Exception as e:
            log_message(f"An unexpected error occurred in the trading loop: {e}", "error")
            dashboard = BOT_STATE.dashboard
            dashboard["botStatus"] = "Error"
            time.sleep(30)

        # --- Interval Sleep Logic ---
        # Align sleep to next candle start
        now = time.time()
        last_kline_ts_sec = klines[-1]['timestamp'] / 1000 if klines else now
        interval_str = str(BOT_STATE.config.get("interval", "60"))

        # Derive seconds
        if interval_str.isdigit():
            interval_seconds = int(interval_str) * 60
        elif interval_str.lower() in ['1', '1m', 'm']:
            interval_seconds = 60
        elif interval_str == '1h':
            interval_seconds = 3600
        elif interval_str == '12h':
            interval_seconds = 12 * 3600
        elif interval_str == 'D':
            interval_seconds = 86400
        elif interval_str == '15':
            interval_seconds = 15 * 60
        elif interval_str == '30':
            interval_seconds = 30 * 60
        else:
            log_message(f"Unsupported interval format: '{interval_str}'. Defaulting to 60s.", "warning")
            interval_seconds = 60

        next_kline_start_ts = (last_kline_ts_sec // interval_seconds + 1) * interval_seconds
        sleep_duration = next_kline_start_ts - now
        BOT_STATE.dashboard['nextCandle'] = datetime.utcfromtimestamp(next_kline_start_ts).strftime('%Y-%m-%d %H:%M:%S UTC')

        if sleep_duration > 0:
            log_message(f"Waiting for {sleep_duration:.2f} seconds until next candle.", "info")
            time.sleep(sleep_duration)
        else:
            log_message(f"Processing took longer than interval ({abs(sleep_duration):.2f}s over). Continuing immediately.", "warning")
            time.sleep(1)

    log_message("Trading bot thread stopped.", "warning")


# --- Helper for API Calls (used by endpoints) ---
def _make_api_call(api_client: HTTP, method: str, endpoint: str, params: dict | None = None, max_retries: int = 3, initial_delay: int = 1) -> dict | None:
    """Generic function to make Bybit API calls with retry logic and error handling."""
    BOT_STATE.performance_monitor.api_calls_count += 1
    start = time.time()
    for attempt in range(max_retries):
        try:
            if method == 'get' or method == 'post' or method == 'amend':
                response = getattr(api_client, endpoint)(**(params or {}))
            else:
                log_message(f"Invalid method '{method}' for API call.", "error")
                return {"retCode": 1, "retMsg": "Invalid method"}
            elapsed_ms = (time.time() - start) * 1000.0
            BOT_STATE.performance_monitor.capture_response_time(elapsed_ms)

            if response.get('retCode') == 0:
                return response
            else:
                ret_code = response.get('retCode')
                ret_msg = response.get('retMsg', 'Unknown Error')
                BOT_STATE.performance_monitor.api_errors_count += 1
                BOT_STATE.performance_monitor.last_api_error = ret_msg
                log_message(f"Bybit API Error ({ret_code}): {ret_msg}. Retrying {endpoint} in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "warning")
                time.sleep(initial_delay * (2**attempt))
        except Exception as e:
            BOT_STATE.performance_monitor.api_errors_count += 1
            BOT_STATE.performance_monitor.last_api_error = str(e)
            log_message(f"API call error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s... (Attempt {attempt + 1})", "error")
            time.sleep(initial_delay * (2**attempt))
    log_message(f"Failed to complete API call to {endpoint} after {max_retries} attempts.", "error")
    return {"retCode": 1, "retMsg": f"Failed after {max_retries} attempts: {endpoint}"}


# =====================================================================
# FLASK API ENDPOINTS
# =====================================================================
@app.route('/')
def index():
    """Serves the main HTML page."""
    return send_from_directory('.', 'supertrend.html')


@app.route('/api/start', methods=['POST'])
def start_bot():
    """Starts the trading bot."""
    if BOT_STATE.running:
        return jsonify({"status": "error", "message": "Bot is already running."}), 400

    config = request.json or {}

    # Validate essential config parameters
    required_params = ['symbol', 'interval', 'leverage', 'riskPct', 'stopLossPct', 'takeProfitPct', 'rsi_overbought', 'rsi_oversold', 'trailingStopPct', 'api_error_retry_delay', 'indicator_wait_delay']
    if not all(param in config for param in required_params):
        missing = [param for param in required_params if param not in config]
        return jsonify({"status": "error", "message": f"Missing required configuration parameters: {', '.join(missing)}"}), 400

    # API keys are loaded from .env file on the backend for security
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        log_message("CRITICAL: Bybit API Key or Secret not found in backend .env file.", "error")
        return jsonify({"status": "error", "message": "Bybit API Key or Secret not found in backend .env file."}), 500

    # Optional: testnet flag in config
    testnet = bool(config.get('testnet', False))

    # Clamp and sanity-check some values
    config['riskPct'] = max(0.1, min(5.0, float(config.get('riskPct', 1.0))))
    config['stopLossPct'] = max(0.1, min(10.0, float(config.get('stopLossPct', 1.0))))
    config['takeProfitPct'] = max(0.1, min(20.0, float(config.get('takeProfitPct', 2.0))))
    config['trailingStopPct'] = max(0.1, min(5.0, float(config.get('trailingStopPct', 0.5))))

    BOT_STATE.config = config
    # Set default indicator parameters if not provided
    BOT_STATE.config['ef_period'] = config.get('ef_period', 10)
    BOT_STATE.config['fisher_threshold'] = config.get('fisher_threshold', 0.5)  # Add Fisher threshold
    BOT_STATE.config['macd_fast_period'] = config.get('macd_fast_period', 12)
    BOT_STATE.config['macd_slow_period'] = config.get('macd_slow_period', 26)
    BOT_STATE.config['macd_signal_period'] = config.get('macd_signal_period', 9)
    BOT_STATE.config['bb_period'] = config.get('bb_period', 20)
    BOT_STATE.config['bb_std_dev'] = config.get('bb_std_dev', 2.0)
    BOT_STATE.config['kline_limit'] = config.get('kline_limit', 200)

    try:
        BOT_STATE.bybit_session = HTTP(testnet=testnet, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
        BOT_STATE.precision_manager = PrecisionManager(BOT_STATE.bybit_session, logger)

        # Verify API connection by fetching balance
        balance_check = _make_api_call(BOT_STATE.bybit_session, 'get', 'get_wallet_balance', params={"accountType": "UNIFIED", "coin": "USDT"})
        if not balance_check or balance_check.get("retCode") != 0:
            log_message(f"API connection failed: {balance_check.get('retMsg', 'Unknown API error') if balance_check else 'No response'}", "error")
            BOT_STATE.bybit_session = None
            return jsonify({"status": "error", "message": f"API connection failed: {balance_check.get('retMsg', 'Unknown API error') if balance_check else 'No response'}"}), 400

        log_message("API connection successful.", "success")

        # Fetch instrument info for precision
        precision_mgr = BOT_STATE.precision_manager
        price_precision, qty_precision = precision_mgr.get_decimal_places(config['symbol'])

        BOT_STATE.config["price_precision"] = price_precision
        BOT_STATE.config["qty_precision"] = qty_precision
        log_message(f"Fetched instrument info: Price Precision={price_precision}, Quantity Precision={qty_precision}", "info")

        # Set leverage when possible
        leverage = int(config.get('leverage', 10))
        # Clamp leverage based on symbol specs if available
        symbol_specs = precision_mgr.instruments.get(config['symbol'])
        if symbol_specs:
            min_lev = int(symbol_specs.min_leverage)
            max_lev = int(symbol_specs.max_leverage)
            leverage = max(min_lev, min(leverage, max_lev))
            log_message(f"Adjusted leverage to {leverage}x based on instrument specs.", "info")

        lev_res = _make_api_call(BOT_STATE.bybit_session, 'post', 'set_leverage', params={
            "category": "linear",
            "symbol": config['symbol'],
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        })
        if lev_res and lev_res.get('retCode') == 0:
            log_message(f"Leverage set to {leverage}x for {config['symbol']}", "success")
        else:
            log_message(f"Failed to set leverage: {lev_res.get('retMsg', 'Unknown API error') if lev_res else 'No response'}", "warning")

        BOT_STATE.running = True
        BOT_STATE.thread = threading.Thread(target=trading_bot_loop, daemon=True)
        BOT_STATE.thread.start()

        return jsonify({"status": "success", "message": "Bot started successfully.", "testnet": testnet})

    except Exception as e:
        log_message(f"Error starting bot: {e}", "error")
        BOT_STATE.bybit_session = None
        BOT_STATE.precision_manager = None
        return jsonify({"status": "error", "message": f"Failed to start bot: {e!s}"}), 500


@app.route('/api/stop', methods=['POST'])
def stop_bot():
    """Stops the trading bot."""
    if not BOT_STATE.running:
        return jsonify({"status": "error", "message": "Bot is not running."}), 400

    BOT_STATE.running = False
    if BOT_STATE.thread and BOT_STATE.thread.is_alive():
        BOT_STATE.thread.join(timeout=5)

    BOT_STATE.thread = None
    BOT_STATE.bybit_session = None
    BOT_STATE.precision_manager = None
    BOT_STATE.dashboard["botStatus"] = "Idle"
    BOT_STATE.current_position_info = {"order_id": None, "entry_price": None, "side": None, "peak_price": None, "entry_time": None, "trailing_activated": False, "size": None}
    log_message("Bot has been stopped by user.", "warning")

    return jsonify({"status": "success", "message": "Bot stopped."})

@app.route('/api/status', methods=['GET'])
def get_status():
    """Returns the current status of the bot."""
    return jsonify({
        "running": BOT_STATE.running,
        "dashboard": BOT_STATE.dashboard,
        "config": BOT_STATE.config if BOT_STATE.running else {},
        "logs": list(BOT_STATE.logs),
        "analytics": asdict(BOT_STATE.trade_analytics)
    })

@app.route('/api/health', methods=['GET'])
def get_health():
    """Returns system and bot health details."""
    return jsonify({
        "status": BOT_STATE.performance_monitor.get_health_status(),
        "running": BOT_STATE.running
    })

@app.route('/api/gemini-insight', methods=['POST'])
def get_gemini_insight():
    """Fetches insights from Gemini AI."""
    if not GEMINI_API_KEY:
        log_message("Gemini API key not configured on server.", "error")
        return jsonify({"status": "error", "message": "Gemini API key not configured on server."}), 503

    data = request.json or {}
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required."}), 400

    try:
        # Use Gemini 1.5 Flash for faster responses
        model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction="You are a helpful trading assistant. Provide concise and actionable insights.")
        response = model.generate_content(prompt)
        if not getattr(response, "text", None):
            return jsonify({"status": "error", "message": "Gemini returned an empty response. Please try again or rephrase your prompt."}), 500
        return jsonify({"status": "success", "insight": response.text})
    except Exception as e:
        log_message(f"Gemini API error: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/symbols', methods=['GET'])
def get_symbols():
    """Fetches available trading symbols from Bybit."""
    try:
        # Initialize PrecisionManager if not already done (e.g., before bot start)
        if not BOT_STATE.precision_manager:
            if not BYBIT_API_KEY or not BYBIT_API_SECRET:
                 return jsonify({"status": "error", "message": "Bybit API Key/Secret not configured. Cannot fetch symbols."}), 500
            session = HTTP(testnet=False, api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)
            BOT_STATE.precision_manager = PrecisionManager(session, logger)

        precision_mgr = BOT_STATE.precision_manager

        # Filter for linear category and 'trading' status
        linear_symbols = sorted([
            s for s, specs in precision_mgr.instruments.items()
            if specs.category == 'linear' and specs.status == 'trading'
        ])
        return jsonify({"status": "success", "symbols": linear_symbols})
    except Exception as e:
        log_message(f"Error fetching symbols: {e}", "error")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Main Execution ---
if __name__ == '__main__':
    # Basic checks on startup
    if not BYBIT_API_KEY or not BYBIT_API_SECRET:
        logger.critical("CRITICAL: Bybit API Key or Secret not found. Please check your .env file.")
    if not GEMINI_API_KEY:
        logger.warning("Gemini API Key not found. The insight feature will be disabled.")
    else:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("Gemini API configured.")
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")

    # Run the Flask app
    logger.info("Starting Flask server on port 5000...")
    app.run(debug=False, host='0.0.0.0', port=5002)
