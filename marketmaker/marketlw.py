import asyncio
import json
import logging
import os
import random
import sqlite3
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

# --- Enhanced Configuration ---
from logging.handlers import RotatingFileHandler
from typing import Any, Generic, TypeVar

from pybit.exceptions import InvalidRequestError

# Import pybit clients
from pybit.unified_trading import HTTP, WebSocket


# Configure enhanced logging with rotation
def setup_logging(log_level=logging.INFO, log_file='bybit_mm_bot.log'):
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(log_level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger

logger = setup_logging()

# --- Enhanced Configuration Classes ---
@dataclass
class TradingConfig:
    """Enhanced trading configuration with validation"""
    symbol: str
    category: str = 'linear'
    leverage: int = 10
    base_order_size: float = 0.001
    min_order_size: float = 0.0001
    max_order_size: float = 0.01
    base_spread_bps: float = 5.0  # basis points
    min_spread_bps: float = 2.0
    max_spread_bps: float = 20.0
    max_position_size: float = 0.01
    max_open_orders_per_side: int = 3
    order_refresh_seconds: float = 30.0
    order_reprice_threshold_bps: float = 2.0
    position_skew_factor: float = 0.5  # How much to adjust spread based on position
    volatility_window: int = 100  # Number of ticks for volatility calculation
    inventory_target: float = 0.0  # Target inventory (0 = neutral)
    max_drawdown_pct: float = 5.0  # Maximum allowed drawdown
    stop_loss_pct: float = 2.0  # Stop loss percentage
    take_profit_pct: float = 1.0  # Take profit percentage

    def __post_init__(self):
        # Validation
        assert self.min_order_size <= self.base_order_size <= self.max_order_size
        assert self.min_spread_bps <= self.base_spread_bps <= self.max_spread_bps
        assert 0 <= self.position_skew_factor <= 1
        assert self.max_drawdown_pct > 0
        assert self.leverage >= 1

@dataclass
class MarketState:
    """Current market state and metrics"""
    best_bid: float | None = None
    best_ask: float | None = None
    mid_price: float | None = None
    spread: float | None = None
    spread_bps: float | None = None
    order_flow_imbalance: float = 0.0
    volatility: float = 0.0
    volume_24h: float = 0.0
    trades_per_minute: float = 0.0
    last_trade_price: float | None = None
    last_update: float = field(default_factory=time.time)

@dataclass
class PositionState:
    """Current position state and P&L tracking"""
    size: float = 0.0
    side: str = 'None'  # 'Buy', 'Sell', 'None'
    avg_entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_pnl: float = 0.0
    peak_pnl: float = 0.0
    drawdown: float = 0.0
    position_value: float = 0.0
    margin_used: float = 0.0
    free_margin: float = 0.0
    last_update: float = field(default_factory=time.time)

@dataclass
class OrderInfo:
    """Enhanced order information"""
    order_id: str
    client_order_id: str
    side: str
    price: float
    quantity: float
    order_type: str
    status: str
    created_at: float
    updated_at: float
    filled_qty: float = 0.0
    avg_fill_price: float = 0.0
    is_post_only: bool = True
    time_in_force: str = 'GTC'

# --- Advanced Data Structures (from original code) ---
KT = TypeVar("KT")
VT = TypeVar("VT")

@dataclass(slots=True)
class PriceLevel:
    """Price level with metadata, optimized for memory with slots."""
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1

    def __lt__(self, other: 'PriceLevel') -> bool:
        return self.price < other.price

    def __eq__(self, other: 'PriceLevel') -> bool:
        return abs(self.price - other.price) < 1e-8

class OptimizedSkipList(Generic[KT, VT]):
    """Enhanced Skip List implementation with O(log n) operations"""
    class Node(Generic[KT, VT]):
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            self.forward: list[OptimizedSkipList.Node | None] = [None] * (level + 1)
            self.level = level

    def __init__(self, max_level: int = 16, p: float = 0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = self.Node(None, None, max_level)
        self._size = 0

    def _random_level(self) -> int:
        level = 0
        while level < self.max_level and random.random() < self.p:
            level += 1
        return level

    def insert(self, key: KT, value: VT) -> None:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and
                   current.forward[i].key is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]

        if current and current.key == key:
            current.value = value
            return

        new_level = self._random_level()
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level

        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node
        self._size += 1

    def delete(self, key: KT) -> bool:
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and
                   current.forward[i].key is not None and
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if not current or current.key != key:
            return False

        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break
            update[i].forward[i] = current.forward[i]
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1
        self._size -= 1
        return True

    def get_sorted_items(self, reverse: bool = False) -> list[tuple[KT, VT]]:
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None:
                items.append((current.key, current.value))
            current = current.forward[0]
        return list(reversed(items)) if reverse else items

    def peek_top(self, reverse: bool = False) -> VT | None:
        items = self.get_sorted_items(reverse=reverse)
        return items[0][1] if items else None

    @property
    def size(self) -> int:
        return self._size

# --- Enhanced Orderbook Manager ---
class AdvancedOrderbookManager:
    """Enhanced orderbook manager with advanced analytics"""
    def __init__(self, symbol: str, use_skip_list: bool = True):
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self._lock = asyncio.Lock()

        # Initialize data structures
        self.bids_ds = OptimizedSkipList[float, PriceLevel]()
        self.asks_ds = OptimizedSkipList[float, PriceLevel]()

        self.last_update_id: int = 0
        self.last_update_time: float = time.time()

        # Analytics
        self.trade_history: deque = deque(maxlen=1000)  # Recent trades
        self.spread_history: deque = deque(maxlen=1000)  # Spread history
        self.update_latencies: deque = deque(maxlen=100)  # WebSocket latencies

    @asynccontextmanager
    async def _lock_context(self):
        async with self._lock:
            yield

    async def update_snapshot(self, data: dict[str, Any]) -> None:
        """Processes orderbook snapshot with timing"""
        start_time = time.time()

        async with self._lock_context():
            if not isinstance(data, dict) or 'b' not in data or 'a' not in data:
                logger.error(f"Invalid snapshot data format for {self.symbol}")
                return

            # Clear existing data
            self.bids_ds = OptimizedSkipList[float, PriceLevel]()
            self.asks_ds = OptimizedSkipList[float, PriceLevel]()

            # Process bids
            for price_str, qty_str in data.get('b', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if price > 0 and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.bids_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse bid: {e}")

            # Process asks
            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)
                    if price > 0 and quantity > 0:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.asks_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse ask: {e}")

            self.last_update_id = data.get('u', 0)
            self.last_update_time = time.time()

            # Record latency
            latency = (time.time() - start_time) * 1000  # ms
            self.update_latencies.append(latency)

            logger.info(f"Orderbook snapshot processed in {latency:.2f}ms")

    async def update_delta(self, data: dict[str, Any]) -> None:
        """Applies incremental updates with validation"""
        async with self._lock_context():
            current_update_id = data.get('u', 0)
            if current_update_id <= self.last_update_id:
                return

            # Process bid deltas
            for price_str, qty_str in data.get('b', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)

                    if quantity == 0.0:
                        self.bids_ds.delete(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.bids_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse bid delta: {e}")

            # Process ask deltas
            for price_str, qty_str in data.get('a', []):
                try:
                    price = float(price_str)
                    quantity = float(qty_str)

                    if quantity == 0.0:
                        self.asks_ds.delete(price)
                    else:
                        level = PriceLevel(price, quantity, int(time.time() * 1000))
                        self.asks_ds.insert(price, level)
                except (ValueError, TypeError) as e:
                    logger.error(f"Failed to parse ask delta: {e}")

            self.last_update_id = current_update_id
            self.last_update_time = time.time()

    async def get_best_bid_ask(self) -> tuple[float | None, float | None]:
        """Returns current best bid and ask with spread tracking"""
        async with self._lock_context():
            best_bid_level = self.bids_ds.peek_top(reverse=True)
            best_ask_level = self.asks_ds.peek_top(reverse=False)

            best_bid = best_bid_level.price if best_bid_level else None
            best_ask = best_ask_level.price if best_ask_level else None

            # Track spread
            if best_bid and best_ask:
                spread = best_ask - best_bid
                self.spread_history.append((time.time(), spread, (best_bid + best_ask) / 2))

            return best_bid, best_ask

    async def get_orderbook_imbalance(self, depth: int = 5) -> float:
        """Calculates order flow imbalance"""
        async with self._lock_context():
            bids = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]]
            asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]

            bid_volume = sum(level.quantity * level.price for level in bids)
            ask_volume = sum(level.quantity * level.price for level in asks)

            if bid_volume + ask_volume == 0:
                return 0.0

            return (bid_volume - ask_volume) / (bid_volume + ask_volume)

    async def get_microprice(self, depth: int = 5) -> float | None:
        """Calculates microprice for better fair value estimation"""
        async with self._lock_context():
            bids = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:depth]]
            asks = [item[1] for item in self.asks_ds.get_sorted_items()[:depth]]

            if not bids or not asks:
                return None

            bid_value = sum(b.price * b.quantity for b in bids)
            bid_qty = sum(b.quantity for b in bids)
            ask_value = sum(a.price * a.quantity for a in asks)
            ask_qty = sum(a.quantity for a in asks)

            if bid_qty + ask_qty == 0:
                return None

            # Weighted average by opposite side quantity
            return (bids[0].price * ask_qty + asks[0].price * bid_qty) / (bid_qty + ask_qty)

    async def estimate_market_impact(self, size: float, side: str) -> dict[str, float]:
        """Estimates slippage for a given order size"""
        async with self._lock_context():
            if side.upper() == "BUY":
                levels = [item[1] for item in self.asks_ds.get_sorted_items()[:100]]
            else:
                levels = [item[1] for item in self.bids_ds.get_sorted_items(reverse=True)[:100]]

            if not levels:
                return {"error": "No liquidity"}

            remaining = size
            total_cost = 0.0
            executed = 0.0
            worst_price = levels[0].price

            for level in levels:
                if remaining <= 0:
                    break

                fill = min(remaining, level.quantity)
                total_cost += fill * level.price
                executed += fill
                remaining -= fill
                worst_price = level.price

            if executed == 0:
                return {"error": "No execution possible"}

            avg_price = total_cost / executed
            best_price = levels[0].price
            slippage_pct = abs(avg_price - best_price) / best_price * 100

            return {
                "avg_price": avg_price,
                "best_price": best_price,
                "worst_price": worst_price,
                "slippage_pct": slippage_pct,
                "executed_qty": executed,
                "total_cost": total_cost
            }

# --- Risk Management Module ---
class RiskManager:
    """Advanced risk management system"""
    def __init__(self, config: TradingConfig):
        self.config = config
        self.trade_history: deque = deque(maxlen=1000)
        self.pnl_history: deque = deque(maxlen=1000)
        self.exposure_history: deque = deque(maxlen=100)
        self.max_historical_drawdown: float = 0.0
        self.daily_pnl: float = 0.0
        self.daily_volume: float = 0.0
        self.last_reset: datetime = datetime.now()

    def check_position_limit(self, current_position: float, order_side: str, order_size: float) -> bool:
        """Checks if order would exceed position limits"""
        if order_side == "Buy":
            new_position = current_position + order_size
        else:
            new_position = current_position - order_size

        return abs(new_position) <= self.config.max_position_size

    def check_drawdown_limit(self, current_pnl: float, peak_pnl: float) -> bool:
        """Checks if current drawdown exceeds limit"""
        if peak_pnl <= 0:
            return True

        drawdown = (peak_pnl - current_pnl) / peak_pnl * 100
        return drawdown < self.config.max_drawdown_pct

    def calculate_order_size(self, base_size: float, position: float, volatility: float) -> float:
        """Dynamically adjusts order size based on risk factors"""
        # Reduce size when position is large
        position_factor = 1.0 - (abs(position) / self.config.max_position_size) * 0.5

        # Reduce size in high volatility
        vol_factor = 1.0 / (1.0 + volatility * 10)

        # Apply factors
        adjusted_size = base_size * position_factor * vol_factor

        # Ensure within bounds
        return max(self.config.min_order_size,
                  min(adjusted_size, self.config.max_order_size))

    def calculate_dynamic_spread(self, base_spread_bps: float, position: float,
                               volatility: float, imbalance: float) -> tuple[float, float]:
        """Calculates dynamic bid/ask spreads based on market conditions"""
        # Base spread adjustment for volatility
        vol_adjustment = volatility * 100  # Convert to basis points

        # Position skew adjustment
        position_ratio = position / self.config.max_position_size if self.config.max_position_size > 0 else 0
        skew_adjustment = abs(position_ratio) * self.config.position_skew_factor * base_spread_bps

        # Imbalance adjustment
        imbalance_adjustment = abs(imbalance) * base_spread_bps * 0.5

        # Calculate bid and ask spreads
        if position > 0:  # Long position - widen ask, tighten bid
            bid_spread_bps = base_spread_bps + vol_adjustment - skew_adjustment * 0.5
            ask_spread_bps = base_spread_bps + vol_adjustment + skew_adjustment * 1.5
        elif position < 0:  # Short position - widen bid, tighten ask
            bid_spread_bps = base_spread_bps + vol_adjustment + skew_adjustment * 1.5
            ask_spread_bps = base_spread_bps + vol_adjustment - skew_adjustment * 0.5
        else:  # Neutral position
            bid_spread_bps = base_spread_bps + vol_adjustment + imbalance_adjustment
            ask_spread_bps = base_spread_bps + vol_adjustment + imbalance_adjustment

        # Apply bounds
        bid_spread_bps = max(self.config.min_spread_bps, min(bid_spread_bps, self.config.max_spread_bps))
        ask_spread_bps = max(self.config.min_spread_bps, min(ask_spread_bps, self.config.max_spread_bps))

        return bid_spread_bps, ask_spread_bps

    def should_stop_trading(self, position_state: PositionState) -> tuple[bool, str]:
        """Determines if trading should stop based on risk limits"""
        # Check drawdown
        if position_state.peak_pnl > 0:
            drawdown_pct = (position_state.peak_pnl - position_state.total_pnl) / position_state.peak_pnl * 100
            if drawdown_pct > self.config.max_drawdown_pct:
                return True, f"Max drawdown exceeded: {drawdown_pct:.2f}%"

        # Check daily loss limit (if implemented)
        if hasattr(self.config, 'daily_loss_limit') and self.daily_pnl < -self.config.daily_loss_limit:
            return True, f"Daily loss limit exceeded: {self.daily_pnl:.2f}"

        # Check position stop loss
        if position_state.unrealized_pnl < 0:
            loss_pct = abs(position_state.unrealized_pnl / position_state.position_value) * 100
            if loss_pct > self.config.stop_loss_pct:
                return True, f"Position stop loss triggered: {loss_pct:.2f}%"

        return False, ""

# --- Performance Monitoring ---
class PerformanceMonitor:
    """Tracks and analyzes bot performance metrics"""
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.start_time = time.time()
        self.trades_count = 0
        self.orders_placed = 0
        self.orders_cancelled = 0
        self.orders_filled = 0
        self.total_volume = 0.0
        self.total_fees = 0.0
        self.ws_messages_received = 0
        self.api_calls_made = 0
        self.errors_count = 0
        self.last_metrics_log = time.time()

        # Performance metrics
        self.fill_rates: deque = deque(maxlen=1000)
        self.spreads: deque = deque(maxlen=1000)
        self.latencies: deque = deque(maxlen=1000)

    def record_order_placed(self):
        self.orders_placed += 1
        self.api_calls_made += 1

    def record_order_filled(self, size: float, price: float, fee: float = 0.0):
        self.orders_filled += 1
        self.trades_count += 1
        self.total_volume += size * price
        self.total_fees += fee
        self.fill_rates.append(time.time())

    def record_order_cancelled(self):
        self.orders_cancelled += 1
        self.api_calls_made += 1

    def record_ws_message(self):
        self.ws_messages_received += 1

    def record_error(self):
        self.errors_count += 1

    def get_metrics(self) -> dict[str, Any]:
        """Returns comprehensive performance metrics"""
        uptime = time.time() - self.start_time

        # Calculate rates
        orders_per_minute = self.orders_placed / (uptime / 60) if uptime > 0 else 0
        fills_per_minute = self.orders_filled / (uptime / 60) if uptime > 0 else 0
        fill_rate = self.orders_filled / self.orders_placed if self.orders_placed > 0 else 0

        # Recent fill rate (last 100 orders)
        recent_fills = len([t for t in self.fill_rates if t > time.time() - 300])  # Last 5 minutes

        return {
            "symbol": self.symbol,
            "uptime_seconds": uptime,
            "uptime_hours": uptime / 3600,
            "orders_placed": self.orders_placed,
            "orders_filled": self.orders_filled,
            "orders_cancelled": self.orders_cancelled,
            "fill_rate": fill_rate,
            "recent_fill_rate": recent_fills / 100 if recent_fills > 0 else 0,
            "trades_count": self.trades_count,
            "total_volume": self.total_volume,
            "total_fees": self.total_fees,
            "orders_per_minute": orders_per_minute,
            "fills_per_minute": fills_per_minute,
            "ws_messages_received": self.ws_messages_received,
            "api_calls_made": self.api_calls_made,
            "errors_count": self.errors_count,
            "error_rate": self.errors_count / self.api_calls_made if self.api_calls_made > 0 else 0
        }

    def log_metrics(self, position_state: PositionState, market_state: MarketState):
        """Logs performance metrics periodically"""
        if time.time() - self.last_metrics_log > 300:  # Every 5 minutes
            metrics = self.get_metrics()
            metrics.update({
                "position_size": position_state.size,
                "unrealized_pnl": position_state.unrealized_pnl,
                "total_pnl": position_state.total_pnl,
                "current_spread_bps": market_state.spread_bps if market_state.spread_bps else 0
            })
            logger.info(f"Performance metrics: {json.dumps(metrics, indent=2)}")
            self.last_metrics_log = time.time()

# --- Database Manager ---
class DatabaseManager:
    """Manages trade history and analytics data"""
    def __init__(self, db_path: str = "bybit_mm_bot.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initializes database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    side TEXT,
                    price REAL,
                    quantity REAL,
                    fee REAL,
                    pnl REAL,
                    position_after REAL,
                    order_id TEXT,
                    UNIQUE(order_id)
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS performance_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    symbol TEXT,
                    position_size REAL,
                    unrealized_pnl REAL,
                    realized_pnl REAL,
                    total_pnl REAL,
                    spread_bps REAL,
                    volatility REAL,
                    order_flow_imbalance REAL,
                    orders_placed INTEGER,
                    orders_filled INTEGER,
                    fill_rate REAL
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    error_type TEXT,
                    error_message TEXT,
                    context TEXT
                )
            ''')

    async def record_trade(self, trade_data: dict[str, Any]):
        """Records a trade asynchronously"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR IGNORE INTO trades
                    (timestamp, symbol, side, price, quantity, fee, pnl, position_after, order_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade_data['timestamp'],
                    trade_data['symbol'],
                    trade_data['side'],
                    trade_data['price'],
                    trade_data['quantity'],
                    trade_data.get('fee', 0),
                    trade_data.get('pnl', 0),
                    trade_data.get('position_after', 0),
                    trade_data['order_id']
                ))
        except Exception as e:
            logger.error(f"Failed to record trade: {e}")

    async def record_performance_snapshot(self, snapshot: dict[str, Any]):
        """Records performance snapshot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO performance_snapshots
                    (timestamp, symbol, position_size, unrealized_pnl, realized_pnl,
                     total_pnl, spread_bps, volatility, order_flow_imbalance,
                     orders_placed, orders_filled, fill_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    snapshot['timestamp'],
                    snapshot['symbol'],
                    snapshot['position_size'],
                    snapshot['unrealized_pnl'],
                    snapshot['realized_pnl'],
                    snapshot['total_pnl'],
                    snapshot['spread_bps'],
                    snapshot['volatility'],
                    snapshot['order_flow_imbalance'],
                    snapshot['orders_placed'],
                    snapshot['orders_filled'],
                    snapshot['fill_rate']
                ))
        except Exception as e:
            logger.error(f"Failed to record performance snapshot: {e}")

# --- Main Enhanced Trading Bot ---
class EnhancedBybitMarketMaker:
    """Enhanced market making bot with advanced features"""

    def __init__(self, config: TradingConfig, testnet: bool = True):
        self.config = config
        self.testnet = testnet

        # Validate API credentials
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials missing")

        # Initialize clients
        self.http_session = HTTP(
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret
        )

        self.ws_public = WebSocket(
            channel_type=self.config.category,
            testnet=self.testnet
        )

        self.ws_private = WebSocket(
            channel_type='private',
            testnet=self.testnet,
            api_key=self.api_key,
            api_secret=self.api_secret
        )

        # Initialize components
        self.orderbook_manager = AdvancedOrderbookManager(self.config.symbol)
        self.risk_manager = RiskManager(self.config)
        self.performance_monitor = PerformanceMonitor(self.config.symbol)
        self.db_manager = DatabaseManager()

        # State management
        self.market_state = MarketState()
        self.position_state = PositionState()
        self.active_orders: dict[str, OrderInfo] = {}
        self.pending_orders: set[str] = set()  # Track orders being placed

        # Control flags
        self.is_running = True
        self.trading_enabled = True
        self.emergency_stop = False

        # Price history for volatility calculation
        self.price_history: deque = deque(maxlen=self.config.volatility_window)

        # Tasks
        self.tasks: list[asyncio.Task] = []

        logger.info(f"Enhanced bot initialized for {self.config.symbol}")

    async def setup(self):
        """Performs initial setup and configuration"""
        logger.info("Starting bot setup...")

        try:
            # Set leverage
            try:
                logger.info(f"Attempting to set leverage to {self.config.leverage} for {self.config.symbol}")
                response = self.http_session.set_leverage(
                    category=self.config.category,
                    symbol=self.config.symbol,
                    buyLeverage=str(self.config.leverage),
                    sellLeverage=str(self.config.leverage)
                )
                if response['retCode'] == 0:
                    logger.info(f"Leverage successfully set to {self.config.leverage}")
                else:
                    logger.warning(f"Could not set leverage, but no exception. Response: {response}")
            except InvalidRequestError as e:
                if "110043" in str(e):  # Leverage not modified
                    logger.warning(f"Leverage already set to {self.config.leverage}. Continuing.")
                else:
                    logger.error(f"Setup failed: Could not set leverage: {e}", exc_info=True)
                    raise

            # Get initial wallet balance
            wallet_resp = self.http_session.get_wallet_balance(accountType='UNIFIED')
            if wallet_resp['retCode'] == 0 and wallet_resp['result']['list']:
                wallet_data = wallet_resp['result']['list'][0]
                total_equity = float(wallet_data.get('totalEquity', 0))
                logger.info(f"Initial wallet balance: {total_equity:.2f}")

            # Get initial position
            position_resp = self.http_session.get_positions(
                category=self.config.category,
                symbol=self.config.symbol
            )
            if position_resp['retCode'] == 0 and position_resp['result']['list']:
                pos_data = position_resp['result']['list'][0]
                self.position_state.size = self._safe_float(pos_data.get('size'))
                self.position_state.avg_entry_price = self._safe_float(pos_data.get('avgPrice'))
                self.position_state.unrealized_pnl = self._safe_float(pos_data.get('unrealisedPnl'))
                self.position_state.side = pos_data.get('side', 'None')
                logger.info(f"Initial position: {self.position_state}")

            # Cancel any existing orders
            await self.cancel_all_orders()

            # Get initial market data
            ticker_resp = self.http_session.get_tickers(
                category=self.config.category,
                symbol=self.config.symbol
            )
            if ticker_resp['retCode'] == 0 and ticker_resp['result']['list']:
                ticker = ticker_resp['result']['list'][0]
                self.market_state.last_trade_price = float(ticker.get('lastPrice', 0))
                self.market_state.volume_24h = float(ticker.get('volume24h', 0))

            logger.info("Bot setup complete")

        except Exception as e:
            logger.error(f"Setup failed: {e}", exc_info=True)
            raise

    async def _handle_public_ws_message(self, message: str):
        """Handles public WebSocket messages"""
        try:
            data = json.loads(message)
            topic = data.get('topic', '')

            self.performance_monitor.record_ws_message()

            if 'orderbook' in topic:
                if data.get('type') == 'snapshot':
                    await self.orderbook_manager.update_snapshot(data['data'])
                elif data.get('type') == 'delta':
                    await self.orderbook_manager.update_delta(data['data'])

                # Update market state
                best_bid, best_ask = await self.orderbook_manager.get_best_bid_ask()
                if best_bid and best_ask:
                    self.market_state.best_bid = best_bid
                    self.market_state.best_ask = best_ask
                    self.market_state.mid_price = (best_bid + best_ask) / 2
                    self.market_state.spread = best_ask - best_bid
                    self.market_state.spread_bps = (self.market_state.spread / self.market_state.mid_price) * 10000
                    self.market_state.last_update = time.time()

                    # Update price history for volatility
                    self.price_history.append(self.market_state.mid_price)

                    # Calculate order flow imbalance
                    self.market_state.order_flow_imbalance = await self.orderbook_manager.get_orderbook_imbalance()

            elif 'trade' in topic:
                trade_data = data.get('data', [])
                if trade_data:
                    self.market_state.last_trade_price = float(trade_data[0].get('p', 0))

            elif 'ticker' in topic:
                ticker_data = data.get('data', {})
                if ticker_data:
                    self.market_state.volume_24h = float(ticker_data.get('volume24h', 0))

        except Exception as e:
            logger.error(f"Error handling public WS message: {e}")
            self.performance_monitor.record_error()

    async def _handle_private_ws_message(self, message: str):
        """Handles private WebSocket messages"""
        try:
            data = json.loads(message)
            topic = data.get('topic', '')

            self.performance_monitor.record_ws_message()

            if topic == 'position':
                for pos_data in data.get('data', []):
                    if pos_data.get('symbol') == self.config.symbol:
                        # Update position state
                        old_size = self.position_state.size
                        self.position_state.size = float(pos_data.get('size', 0))
                        self.position_state.side = pos_data.get('side', 'None')
                        self.position_state.avg_entry_price = float(pos_data.get('avgPrice', 0))
                        self.position_state.unrealized_pnl = float(pos_data.get('unrealisedPnl', 0))
                        self.position_state.position_value = float(pos_data.get('positionValue', 0))
                        self.position_state.last_update = time.time()

                        # Check if position changed
                        if abs(old_size - self.position_state.size) > 1e-8:
                            logger.info(f"Position updated: {self.position_state}")

            elif topic == 'order':
                for order_data in data.get('data', []):
                    if order_data.get('symbol') == self.config.symbol:
                        order_id = order_data.get('orderId')
                        order_status = order_data.get('orderStatus')

                        # Create or update order info
                        order_info = OrderInfo(
                            order_id=order_id,
                            client_order_id=order_data.get('orderLinkId', ''),
                            side=order_data.get('side'),
                            price=float(order_data.get('price', 0)),
                            quantity=float(order_data.get('qty', 0)),
                            order_type=order_data.get('orderType'),
                            status=order_status,
                            created_at=float(order_data.get('createdTime', 0)) / 1000,
                            updated_at=float(order_data.get('updatedTime', 0)) / 1000,
                            filled_qty=float(order_data.get('cumExecQty', 0)),
                            avg_fill_price=float(order_data.get('avgPrice', 0))
                        )

                        if order_status in ['New', 'PartiallyFilled']:
                            self.active_orders[order_id] = order_info
                            self.pending_orders.discard(order_info.client_order_id)
                        elif order_status in ['Filled', 'Cancelled', 'Rejected']:
                            self.active_orders.pop(order_id, None)
                            self.pending_orders.discard(order_info.client_order_id)

                            if order_status == 'Filled':
                                self.performance_monitor.record_order_filled(
                                    order_info.filled_qty,
                                    order_info.avg_fill_price
                                )

                                # Record trade
                                await self.db_manager.record_trade({
                                    'timestamp': time.time(),
                                    'symbol': self.config.symbol,
                                    'side': order_info.side,
                                    'price': order_info.avg_fill_price,
                                    'quantity': order_info.filled_qty,
                                    'position_after': self.position_state.size,
                                    'order_id': order_id
                                })

                        logger.info(f"Order {order_id} status: {order_status}")

            elif topic == 'execution':
                for exec_data in data.get('data', []):
                    if exec_data.get('symbol') == self.config.symbol:
                        # Update realized PnL if available
                        realized_pnl = float(exec_data.get('closedPnl', 0))
                        if realized_pnl != 0:
                            self.position_state.realized_pnl += realized_pnl
                            self.position_state.total_pnl = (
                                self.position_state.realized_pnl +
                                self.position_state.unrealized_pnl
                            )

                            # Update peak PnL for drawdown calculation
                            if self.position_state.total_pnl > self.position_state.peak_pnl:
                                self.position_state.peak_pnl = self.position_state.total_pnl

            elif topic == 'wallet':
                for wallet_data in data.get('data', []):
                    if wallet_data.get('accountType') == 'UNIFIED':
                        # Update margin info
                        self.position_state.free_margin = float(wallet_data.get('availableBalance', 0))

        except Exception as e:
            logger.error(f"Error handling private WS message: {e}")
            self.performance_monitor.record_error()

    async def _calculate_volatility(self) -> float:
        """Calculates recent price volatility"""
        if len(self.price_history) < 10:
            return 0.0

        prices = list(self.price_history)
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]

        if not returns:
            return 0.0

        # Calculate standard deviation of returns
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        volatility = variance ** 0.5

        return volatility

    async def place_order(self, side: str, price: float, quantity: float,
                         post_only: bool = True) -> str | None:
        """Places an order with enhanced error handling"""
        client_order_id = f"MM-{uuid.uuid4().hex[:8]}"

        # Check if we're already placing this order
        if client_order_id in self.pending_orders:
            logger.warning(f"Order {client_order_id} already pending")
            return None

        self.pending_orders.add(client_order_id)

        try:
            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "side": side,
                "orderType": "Limit",
                "qty": str(round(quantity, 8)),
                "price": str(round(price, 2)),
                "timeInForce": "PostOnly" if post_only else "GTC",
                "orderLinkId": client_order_id,
                "reduceOnly": False,
                "closeOnTrigger": False
            }

            response = self.http_session.place_order(**params)
            self.performance_monitor.record_order_placed()

            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logger.info(f"Placed {side} order {order_id} @ {price:.2f} for {quantity:.4f}")
                return order_id
            else:
                logger.error(f"Failed to place order: {response}")
                self.pending_orders.discard(client_order_id)
                return None

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            self.performance_monitor.record_error()
            self.pending_orders.discard(client_order_id)
            return None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancels an order"""
        try:
            response = self.http_session.cancel_order(
                category=self.config.category,
                symbol=self.config.symbol,
                orderId=order_id
            )

            if response['retCode'] == 0:
                logger.info(f"Cancelled order {order_id}")
                self.performance_monitor.record_order_cancelled()
                return True
            else:
                logger.error(f"Failed to cancel order {order_id}: {response}")
                return False

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            self.performance_monitor.record_error()
            return False

    async def cancel_all_orders(self) -> int:
        """Cancels all active orders"""
        try:
            response = self.http_session.cancel_all_orders(
                category=self.config.category,
                symbol=self.config.symbol
            )

            if response['retCode'] == 0:
                count = len(response['result']['list'])
                logger.info(f"Cancelled {count} orders")
                self.active_orders.clear()
                return count
            else:
                logger.error(f"Failed to cancel all orders: {response}")
                return 0

        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            self.performance_monitor.record_error()
            return 0

    async def update_quotes(self):
        """Main market making logic - updates quotes based on market conditions"""
        # Check if we should be trading
        if not self.trading_enabled or self.emergency_stop:
            return

        # Check market state
        if not self.market_state.best_bid or not self.market_state.best_ask:
            logger.warning("Market data not ready")
            return

        # Calculate volatility
        self.market_state.volatility = await self._calculate_volatility()

        # Check risk limits
        should_stop, reason = self.risk_manager.should_stop_trading(self.position_state)
        if should_stop:
            logger.error(f"Risk limit triggered: {reason}")
            self.emergency_stop = True
            await self.cancel_all_orders()
            return

        # Calculate dynamic spreads
        bid_spread_bps, ask_spread_bps = self.risk_manager.calculate_dynamic_spread(
            self.config.base_spread_bps,
            self.position_state.size,
            self.market_state.volatility,
            self.market_state.order_flow_imbalance
        )

        # Calculate order sizes
        base_size = self.risk_manager.calculate_order_size(
            self.config.base_order_size,
            self.position_state.size,
            self.market_state.volatility
        )

        # Get microprice for better fair value
        microprice = await self.orderbook_manager.get_microprice()
        fair_price = microprice if microprice else self.market_state.mid_price

        # Calculate target prices
        bid_price = fair_price * (1 - bid_spread_bps / 10000)
        ask_price = fair_price * (1 + ask_spread_bps / 10000)

        # Round prices to tick size (assuming 0.01 for now)
        bid_price = round(bid_price, 2)
        ask_price = round(ask_price, 2)

        # Check existing orders
        buy_orders = [o for o in self.active_orders.values() if o.side == 'Buy']
        sell_orders = [o for o in self.active_orders.values() if o.side == 'Sell']

        # Update buy orders
        if len(buy_orders) < self.config.max_open_orders_per_side:
            # Check if we need to place new order
            if self.risk_manager.check_position_limit(
                self.position_state.size, 'Buy', base_size
            ):
                # Check for existing order at similar price
                existing_at_price = any(
                    abs(o.price - bid_price) / bid_price < 0.0001
                    for o in buy_orders
                )

                if not existing_at_price:
                    await self.place_order('Buy', bid_price, base_size)

        # Check if we need to reprice buy orders
        for order in buy_orders:
            price_diff_bps = abs(order.price - bid_price) / bid_price * 10000
            if price_diff_bps > self.config.order_reprice_threshold_bps:
                await self.cancel_order(order.order_id)

        # Update sell orders
        if len(sell_orders) < self.config.max_open_orders_per_side:
            # Check if we need to place new order
            if self.risk_manager.check_position_limit(
                self.position_state.size, 'Sell', base_size
            ):
                # Check for existing order at similar price
                existing_at_price = any(
                    abs(o.price - ask_price) / ask_price < 0.0001
                    for o in sell_orders
                )

                if not existing_at_price:
                    await self.place_order('Sell', ask_price, base_size)

        # Check if we need to reprice sell orders
        for order in sell_orders:
            price_diff_bps = abs(order.price - ask_price) / ask_price * 10000
            if price_diff_bps > self.config.order_reprice_threshold_bps:
                await self.cancel_order(order.order_id)

        # Log current state
        logger.debug(
            f"Quotes updated - Bid: {bid_price:.2f} ({bid_spread_bps:.1f}bps), "
            f"Ask: {ask_price:.2f} ({ask_spread_bps:.1f}bps), "
            f"Position: {self.position_state.size:.4f}, "
            f"PnL: {self.position_state.total_pnl:.2f}"
        )

    async def _quote_update_loop(self):
        """Continuous quote update loop"""
        last_update = 0

        while self.is_running:
            try:
                current_time = time.time()

                # Update quotes at regular intervals
                if current_time - last_update > 1.0:  # Update every second
                    await self.update_quotes()
                    last_update = current_time

                # Log metrics periodically
                self.performance_monitor.log_metrics(
                    self.position_state,
                    self.market_state
                )

                # Save performance snapshot periodically
                if int(current_time) % 300 == 0:  # Every 5 minutes
                    await self.db_manager.record_performance_snapshot({
                        'timestamp': current_time,
                        'symbol': self.config.symbol,
                        'position_size': self.position_state.size,
                        'unrealized_pnl': self.position_state.unrealized_pnl,
                        'realized_pnl': self.position_state.realized_pnl,
                        'total_pnl': self.position_state.total_pnl,
                        'spread_bps': self.market_state.spread_bps or 0,
                        'volatility': self.market_state.volatility,
                        'order_flow_imbalance': self.market_state.order_flow_imbalance,
                        'orders_placed': self.performance_monitor.orders_placed,
                        'orders_filled': self.performance_monitor.orders_filled,
                        'fill_rate': self.performance_monitor.orders_filled / max(1, self.performance_monitor.orders_placed)
                    })

                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in quote update loop: {e}", exc_info=True)
                self.performance_monitor.record_error()
                await asyncio.sleep(1)

    async def _websocket_handler(self, ws_client, handler_func, ws_type: str):
        """Generic WebSocket handler with reconnection"""
        while self.is_running:
            try:
                logger.info(f"Connecting to {ws_type} WebSocket...")

                if ws_type == 'private':
                    ws_client.position_stream(callback=handler_func)
                    ws_client.order_stream(callback=handler_func)
                    ws_client.execution_stream(callback=handler_func)
                    ws_client.wallet_stream(callback=handler_func)
                else:  # public
                    ws_client.orderbook_stream(
                        depth=25,
                        symbol=self.config.symbol,
                        callback=handler_func
                    )
                    ws_client.trade_stream(
                        symbol=self.config.symbol,
                        callback=handler_func
                    )
                    ws_client.ticker_stream(
                        symbol=self.config.symbol,
                        callback=handler_func
                    )

                while self.is_running and ws_client.is_connected():
                    await asyncio.sleep(1)

                logger.warning(f"{ws_type} WebSocket disconnected")

            except Exception as e:
                logger.error(f"Error in {ws_type} WebSocket: {e}")
                self.performance_monitor.record_error()

            if self.is_running:
                await asyncio.sleep(5)  # Reconnect delay

    async def start(self):
        """Starts the enhanced market making bot"""
        try:
            # Perform initial setup
            await self.setup()

            # Start WebSocket handlers
            self.tasks.append(
                asyncio.create_task(
                    self._websocket_handler(
                        self.ws_public,
                        self._handle_public_ws_message,
                        'public'
                    )
                )
            )

            self.tasks.append(
                asyncio.create_task(
                    self._websocket_handler(
                        self.ws_private,
                        self._handle_private_ws_message,
                        'private'
                    )
                )
            )

            # Wait for initial market data
            logger.info("Waiting for market data...")
            for _ in range(50):  # Wait up to 5 seconds
                if self.market_state.best_bid and self.market_state.best_ask:
                    break
                await asyncio.sleep(0.1)

            if not self.market_state.best_bid or not self.market_state.best_ask:
                raise RuntimeError("Failed to receive market data")

            logger.info("Market data received, starting quote updates")

            # Start quote update loop
            self.tasks.append(
                asyncio.create_task(self._quote_update_loop())
            )

            # Wait for tasks
            await asyncio.gather(*self.tasks)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shuts down the bot"""
        logger.info("Shutting down bot...")
        self.is_running = False

        # Cancel all orders
        await self.cancel_all_orders()

        # Cancel tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # Close WebSocket connections
        if self.ws_public and self.ws_public.is_connected():
            self.ws_public.exit()
        if self.ws_private and self.ws_private.is_connected():
            self.ws_private.exit()

        # Final metrics log
        metrics = self.performance_monitor.get_metrics()
        logger.info(f"Final performance metrics: {json.dumps(metrics, indent=2)}")

        logger.info("Bot shutdown complete")

# --- Main Entry Point ---
async def main():
    """Main entry point with configuration"""
    # Load configuration (could be from file/env/args)
    config = TradingConfig(
        symbol='XLMUSDT',
        category='linear',
        leverage=15,
        base_order_size=10,
        min_order_size=8,
        max_order_size=100,
        base_spread_bps=5.0,
        min_spread_bps=2.0,
        max_spread_bps=20.0,
        max_position_size=0.01,
        max_open_orders_per_side=3,
        order_refresh_seconds=30.0,
        order_reprice_threshold_bps=2.0,
        position_skew_factor=0.5,
        volatility_window=100,
        inventory_target=0.0,
        max_drawdown_pct=5.0,
        stop_loss_pct=2.0,
        take_profit_pct=1.0
    )

    # Check environment variables
    if not os.getenv('BYBIT_API_KEY') or not os.getenv('BYBIT_API_SECRET'):
        logger.error("Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables")
        return

    # Create and start bot
    bot = EnhancedBybitMarketMaker(config, testnet=False)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
"Please set BYBIT_API_KEY and BYBIT_API_SECRET environment variables")
        return

    # Create and start bot
    bot = EnhancedBybitMarketMaker(config, testnet=False)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
