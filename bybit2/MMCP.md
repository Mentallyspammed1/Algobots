I'll implement 25 significant improvements to enhance the market-making bot. Here's the upgraded version:

```python
"""
Enhanced Market Making Bot for Bybit Perpetual Contracts
Features 25 key improvements for performance, robustness, and intelligence.
"""

import asyncio
import os
import signal
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, cast

import aiohttp
import numpy as np
from colorama import Fore, Style
from filelock import FileLock, Timeout
from pydantic import BaseModel, ValidationError, validator
from pydantic.tools import parse_obj_as
from typing_extensions import Literal

# --- Constants ---
getcontext().prec = 8  # Decimal precision for financial calculations
API_KEY = os.getenv("BYBIT_API_KEY", "your_api_key")
API_SECRET = os.getenv("BYBIT_API_SECRET", "your_api_secret")
BASE_URL = "https://api.bybit.com/v5"
WS_URL = "wss://stream.bybit.com/v5/public/spot"
WS_PRIVATE_URL = "wss://stream.bybit.com/v5/private"
STATE_DIR = "bot_state"
HEARTBEAT_INTERVAL = 300  # 5 minutes
STATE_LOCK_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1.5  # seconds (exponential backoff base)

# --- Improved Data Models ---
class OrderStatus(str, Enum):
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    PENDING_CANCEL = "PendingCancel"
    UNTRIGGERED = "Untriggered"

class TradeSide(str, Enum):
    BUY = "Buy"
    SELL = "Sell"

class RiskLevel(str, Enum):
    NORMAL = "Normal"
    ELEVATED = "Elevated"
    HIGH = "High"
    CRITICAL = "Critical"

class MarketData(BaseModel):
    symbol: str
    best_bid: Decimal
    best_ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    mid_price: Decimal
    spread: Decimal
    timestamp: int
    volume_24h: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None
    open_interest: Optional[Decimal] = None
    
    @property
    def spread_bps(self) -> Decimal:
        """Calculate spread in basis points"""
        if self.mid_price <= 0:
            return Decimal('0')
        return (self.spread / self.mid_price) * Decimal('10000')

    @validator('mid_price', pre=True)
    def validate_mid_price(cls, v):
        if v <= 0:
            raise ValueError('Mid price must be positive')
        return Decimal(v)

class OrderData(BaseModel):
    order_id: str
    symbol: str
    side: TradeSide
    price: Decimal
    quantity: Decimal
    status: OrderStatus = OrderStatus.NEW
    filled_qty: Decimal = Decimal('0')
    avg_price: Decimal = Decimal('0')
    timestamp: float
    type: str = "Limit"
    reduce_only: bool = False
    post_only: bool = True
    client_order_id: Optional[str] = None
    last_update: datetime = datetime.now(timezone.utc)
    order_pnl: Decimal = Decimal('0')

    @property
    def remaining_qty(self) -> Decimal:
        return self.quantity - self.filled_qty

class RiskMetrics(BaseModel):
    max_position: Decimal
    initial_equity: Decimal
    current_position: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    daily_pnl: Decimal = Decimal('0')
    max_drawdown: Decimal = Decimal('0')
    var_95: Decimal = Decimal('0')  # Value at Risk (95%)
    avg_win: Decimal = Decimal('0')
    avg_loss: Decimal = Decimal('0')
    win_rate: Decimal = Decimal('0')
    equity: Decimal = Decimal('0')
    last_equity_update: datetime = datetime.now(timezone.utc)
    risk_level: RiskLevel = RiskLevel.NORMAL
    max_daily_loss: Decimal = Decimal('-0.05')  # 5% daily loss limit
    max_drawdown_limit: Decimal = Decimal('-0.10')  # 10% max drawdown

    @validator('equity', pre=True, always=True)
    def initialize_equity(cls, v, values):
        if 'initial_equity' in values and v is None:
            return values['initial_equity']
        return v or Decimal('0')

    def update_trade_stats(self, pnl: Decimal):
        """Update trading performance statistics"""
        if pnl > 0:
            self.avg_win = (self.avg_win * (self.win_count) + pnl) / (self.win_count + 1)
            self.win_count += 1
        elif pnl < 0:
            self.avg_loss = (self.avg_loss * (self.lose_count) + pnl) / (self.lose_count + 1)
            self.lose_count += 1
        
        self.win_rate = (self.win_count / (self.win_count + self.lose_count)) * 100 if (self.win_count + self.lose_count) > 0 else Decimal('0')

    @property
    def win_count(self) -> int:
        return getattr(self, '_win_count', 0)
    
    @win_count.setter
    def win_count(self, value: int):
        self._win_count = value

    @property
    def lose_count(self) -> int:
        return getattr(self, '_lose_count', 0)
    
    @lose_count.setter
    def lose_count(self, value: int):
        self._lose_count = value

    def update_equity_and_drawdown(self, new_equity: Decimal):
        """Update equity and calculate drawdown metrics"""
        self.equity = new_equity
        self.last_equity_update = datetime.now(timezone.utc)
        
        # Calculate daily PnL (simplified)
        if self.last_equity_update.hour == 0 and self.last_equity_update.minute == 0:
            self.daily_pnl = Decimal('0')
        else:
            self.daily_pnl = self.equity - (self.initial_equity + self.realized_pnl)
        
        # Check daily loss limit
        if self.daily_pnl < self.max_daily_loss * self.initial_equity:
            self.risk_level = RiskLevel.CRITICAL
            logger.critical("Daily loss limit breached! Entering CRITICAL risk state.")
        
        # Calculate max drawdown
        if new_equity < self.equity_peak:
            drawdown = (new_equity - self.equity_peak) / self.equity_peak
            self.max_drawdown = min(self.max_drawdown, drawdown)
            
            if self.max_drawdown < self.max_drawdown_limit:
                self.risk_level = RiskLevel.HIGH
        else:
            self.equity_peak = new_equity

    def calculate_var_95(self, returns: List[Decimal]):
        """Calculate Value at Risk (95% confidence)"""
        if not returns:
            return Decimal('0')
        sorted_returns = sorted(returns)
        var_index = int(len(returns) * 0.05)
        self.var_95 = sorted_returns[var_index] if var_index < len(returns) else sorted_returns[-1]

    def calculate_sharpe_ratio(self, risk_free_rate: Decimal = Decimal('0.01'), period: int = 252):
        """Calculate annualized Sharpe ratio"""
        if not hasattr(self, 'returns') or len(self.returns) < 2:
            return Decimal('0')
        excess_returns = [r - risk_free_rate/period for r in self.returns]
        return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(period)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with Decimal handling"""
        return {
            "max_position": str(self.max_position),
            "initial_equity": str(self.initial_equity),
            "current_position": str(self.current_position),
            "realized_pnl": str(self.realized_pnl),
            "unrealized_pnl": str(self.unrealized_pnl),
            "daily_pnl": str(self.daily_pnl),
            "max_drawdown": str(self.max_drawdown),
            "var_95": str(self.var_95),
            "avg_win": str(self.avg_win),
            "avg_loss": str(self.avg_loss),
            "win_rate": str(self.win_rate),
            "equity": str(self.equity),
            "win_count": self.win_count,
            "lose_count": self.lose_count
        }

# --- State Manager with File Locking ---
class StateManager:
    """Thread-safe state management with file locking and periodic snapshots"""
    def __init__(self, base_dir: str = STATE_DIR):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.snapshots_dir = os.path.join(base_dir, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
    def _get_path(self, key: str) -> str:
        return os.path.join(self.base_dir, f"{key}.json")
    
    def _get_snapshot_path(self, key: str, timestamp: datetime) -> str:
        filename = f"{key}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        return os.path.join(self.snapshots_dir, filename)
    
    def save_state(self, key: str, data: Any):
        """Save state with file locking and automatic snapshots"""
        path = self._get_path(key)
        lock_path = f"{path}.lock"
        
        # Create file lock
        lock = FileLock(lock_path, timeout=STATE_LOCK_TIMEOUT)
        with lock:
            # Create snapshot before overwriting
            if os.path.exists(path):
                timestamp = datetime.now(timezone.utc)
                snapshot_path = self._get_snapshot_path(key, timestamp)
                os.rename(path, snapshot_path)
                
            # Save new state
            with open(path, 'w') as f:
                if isinstance(data, BaseModel):
                    f.write(data.json(indent=2))
                else:
                    f.write(str(data))
    
    def load_state(self, key: str, model: Any = None) -> Any:
        """Load state with file locking"""
        path = self._get_path(key)
        lock_path = f"{path}.lock"
        
        lock = FileLock(lock_path, timeout=STATE_LOCK_TIMEOUT)
        with lock:
            if not os.path.exists(path):
                return None
                
            with open(path, 'r') as f:
                content = f.read()
                
            if model and issubclass(model, BaseModel):
                return model.parse_raw(content)
            return content

# --- API Client with Enhanced Features ---
class APIClient:
    """Enhanced API client with retry mechanism, rate limiting, and performance monitoring"""
    def __init__(self, api_key: str, api_secret: str, base_url: str, 
                 ws_url: str, private_ws_url: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.ws_url = ws_url
        self.private_ws_url = private_ws_url
        self.session = None
        self.ws = None
        self.private_ws = None
        self.rate_limit_remaining = 100
        self.rate_limit_reset = time.time()
        self.last_request_time = 0
        self.request_count = 0
        self.latency_metrics = []
        self.symbol_info_cache = {}
        self.performance_monitor = PerformanceMonitor()
        self.bot_instance = None  # Will be set by bot
        self.heartbeat_task = None
        self.is_connected = False
        
    @asynccontextmanager
    async def _get_session(self) -> AsyncGenerator[aiohttp.ClientSession, None]:
        """Context manager for API sessions"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            )
        yield self.session
        
    async def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Core API request method with retry logic, rate limiting, and latency tracking"""
        url = f"{self.base_url}{endpoint}"
        payload = kwargs.get('json', {})
        
        # Add API key and signature for authenticated endpoints
        if endpoint.startswith("/private"):
            timestamp = int(time.time() * 1000)
            payload.update({
                "api_key": self.api_key,
                "timestamp": timestamp,
                "recv_window": 5000
            })
            # Create signature
            sorted_params = "&".join([f"{k}={v}" for k, v in sorted(payload.items())])
            signature = self._generate_signature(f"{timestamp}{sorted_params}")
            payload["sign"] = signature
            
        # Rate limiting
        now = time.monotonic()
        elapsed = now - self.last_request_time
        if elapsed < 0.1:  # 100ms between requests
            await asyncio.sleep(0.1 - elapsed)
            
        # Retry loop with exponential backoff
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.perf_counter()
                
                async with self._get_session() as session:
                    response = await session.request(
                        method, url, json=payload, raise_for_status=True
                    )
                    
                # Record latency
                latency = time.perf_counter() - start_time
                self.latency_metrics.append(latency)
                if len(self.latency_metrics) > 1000:
                    self.latency_metrics.pop(0)
                    
                # Update rate limit tracking (Bybit uses header: 'x-ratelimit-remaining')
                self.rate_limit_remaining = int(response.headers.get('x-ratelimit-remaining', 100))
                self.rate_limit_reset = int(response.headers.get('x-ratelimit-reset', time.time() + 1))
                
                self.request_count += 1
                self.performance_monitor.record_metric('api_requests')
                
                data = await response.json()
                
                if data.get('retCode') != 0:
                    error_msg = data.get('retMsg', 'Unknown API error')
                    logger.warning(f"API error ({attempt+1}/{MAX_RETRIES}): {error_msg}")
                    if "ratelimit" in error_msg.lower():
                        reset_time = max(1, self.rate_limit_reset - time.time())
                        logger.warning(f"Rate limit exceeded. Retrying in {reset_time:.1f}s")
                        await asyncio.sleep(reset_time)
                        continue
                    return None
                return data
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"Network error ({attempt+1}/{MAX_RETRIES}): {str(e)}")
                delay = RETRY_DELAY * (2 ** attempt) + random.uniform(0, 0.1)
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                break
                
        logger.error(f"Request failed after {MAX_RETRIES} attempts: {url}")
        return None

    def _generate_signature(self, data: str) -> str:
        """Generate HMAC signature for authenticated requests"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get symbol information with caching"""
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]
            
        endpoint = f"/public/symbols?category=perpetual&symbol={symbol}"
        data = await self._request("GET", endpoint)
        if data and data.get('retCode') == 0:
            symbol_info = data['result']['list'][0]
            self.symbol_info_cache[symbol] = symbol_info
            return symbol_info
        return None

    async def fetch_market_data(self, symbol: str) -> Optional[MarketData]:
        """Fetch real-time market data"""
        endpoint = f"/public/tickers?category=perpetual&symbol={symbol}"
        data = await self._request("GET", endpoint)
        if data and data.get('retCode') == 0:
            ticker = data['result']['list'][0]
            return MarketData(
                symbol=symbol,
                best_bid=Decimal(ticker['bidPrice']),
                best_ask=Decimal(ticker['askPrice']),
                bid_size=Decimal(ticker['bidSz']),
                ask_size=Decimal(ticker['askSz']),
                mid_price=Decimal(ticker['midPrice']),
                spread=Decimal(ticker['askPrice']) - Decimal(ticker['bidPrice']),
                timestamp=ticker['t']
            )
        return None

    async def create_order(self, symbol: str, side: TradeSide, order_type: str, 
                          qty: Decimal, price: Optional[Decimal] = None, 
                          reduce_only: bool = False, post_only: bool = True) -> Optional[Dict[str, Any]]:
        """Place a new order"""
        endpoint = "/private/order/create"
        payload = {
            "category": "perpetual",
            "symbol": symbol,
            "side": side.value,
            "order_type": order_type,
            "qty": str(qty),
            "time_in_force": "GoodTillCancel",
            "reduce_only": reduce_only,
            "post_only": post_only
        }
        if price is not None:
            payload["price"] = str(price)
            
        return await self._request("POST", endpoint, json=payload)

    async def cancel_order(self, symbol: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Cancel an existing order"""
        endpoint = "/private/order/cancel"
        payload = {
            "category": "perpetual",
            "symbol": symbol,
            "order_id": order_id
        }
        return await self._request("POST", endpoint, json=payload)

    async def get_open_orders(self, symbol: str) -> List[OrderData]:
        """Get all open orders for a symbol"""
        endpoint = "/private/order/list"
        payload = {
            "category": "perpetual",
            "symbol": symbol,
            "order_status": "New"
        }
        data = await self._request("GET", endpoint, json=payload)
        if data and data.get('retCode') == 0:
            orders = []
            for order_data in data['result']['list']:
                try:
                    order = OrderData(
                        order_id=order_data['orderId'],
                        symbol=symbol,
                        side=TradeSide(order_data['side']),
                        price=Decimal(order_data['price']),
                        quantity=Decimal(order_data['qty']),
                        status=OrderStatus(order_data['orderStatus']),
                        filled_qty=Decimal(order_data['cumExecQty']),
                        avg_price=Decimal(order_data['avgPrice']),
                        timestamp=order_data['createTime'],
                        type=order_data['orderType'],
                        reduce_only=order_data['reduceOnly'],
                        post_only=order_data['createType'] == "CreateByUser"
                    )
                    orders.append(order)
                except ValidationError as e:
                    logger.error(f"Error parsing order data: {e}")
            return orders
        return []

    async def get_positions(self, symbol: str) -> List[Dict[str, Any]]:
        """Get current positions"""
        endpoint = "/private/position/list"
        payload = {
            "category": "perpetual",
            "symbol": symbol
        }
        data = await self._request("GET", endpoint, json=payload)
        if data and data.get('retCode') == 0:
            return data['result']['list']
        return []

    async def connect_websockets(self):
        """Connect to public and private WebSocket streams"""
        # Public market data stream
        self.ws = await websockets.connect(
            self.ws_url,
            ping_interval=HEARTBEAT_INTERVAL,
            ping_timeout=30
        )
        await self.ws.send(json.dumps({
            "op": "subscribe",
            "args": [f"tickers.perpetual.{self.bot_instance.symbol}"]
        }))
        
        # Private order/trade updates
        self.private_ws = await websockets.connect(
            self.private_ws_url,
            ping_interval=HEARTBEAT_INTERVAL,
            ping_timeout=30
        )
        await self.private_ws.send(json.dumps({
            "op": "subscribe",
            "args": [
                f"execution:{self.bot_instance.symbol}",
                f"position:{self.bot_instance.symbol}",
                f"order:{self.bot_instance.symbol}"
            ]
        }))
        
        self.is_connected = True
        self.heartbeat_task = asyncio.create_task(self._monitor_heartbeat())

    async def _monitor_heartbeat(self):
        """Monitor WebSocket connections and reconnect if needed"""
        while self.is_connected:
            try:
                # Check public WS
                if self.ws and self.ws.open:
                    pong = await self.ws.ping()
                    await asyncio.wait_for(pong, timeout=10)
                else:
                    logger.warning("Public WebSocket disconnected. Reconnecting...")
                    await self.connect_websockets()
                    continue
                    
                # Check private WS
                if self.private_ws and self.private_ws.open:
                    pong = await self.private_ws.ping()
                    await asyncio.wait_for(pong, timeout=10)
                else:
                    logger.warning("Private WebSocket disconnected. Reconnecting...")
                    await self.connect_websockets()
                    continue
                    
                await asyncio.sleep(HEARTBEAT_INTERVAL // 2)
                
            except (asyncio.TimeoutError, websockets.ConnectionClosed) as e:
                logger.warning(f"Heartbeat check failed: {str(e)}. Reconnecting...")
                await self.connect_websockets()
            except Exception as e:
                logger.error(f"Unexpected error in heartbeat monitor: {str(e)}")
                await asyncio.sleep(5)

    async def listen_for_messages(self):
        """Listen for messages from WebSocket connections"""
        while self.is_connected:
            try:
                # Process public messages
                if self.ws and self.ws.open:
                    message = await self.ws.recv()
                    await self._process_public_message(message)
                
                # Process private messages
                if self.private_ws and self.private_ws.open:
                    message = await self.private_ws.recv()
                    await self._process_private_message(message)
                    
                await asyncio.sleep(0.01)  # Yield control
                
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed. Attempting to reconnect...")
                await self.connect_websockets()
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}")
                await asyncio.sleep(1)

    async def _process_public_message(self, message: str):
        """Process public market data messages"""
        try:
            data = json.loads(message)
            if data.get('topic') == f"tickers.perpetual.{self.bot_instance.symbol}":
                await self.bot_instance.update_market_data_from_ws(data['data'][0])
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error processing public message: {e}")

    async def _process_private_message(self, message: str):
        """Process private order/trade/position messages"""
        try:
            data = json.loads(message)
            topic = data.get('topic', '')
            
            if topic.startswith("execution:"):
                # Trade execution updates
                trade_data = data['data']
                # This would update order status and PnL
                # In a full implementation, we'd match to open orders
                logger.debug(f"Execution update: {trade_data}")
                
            elif topic.startswith("position:"):
                # Position updates
                position_data = data['data']
                # This would update the bot's position state
                logger.debug(f"Position update: {position_data}")
                
            elif topic.startswith("order:"):
                # Order status updates
                order_data = data['data']
                # Add to order update queue
                await self.bot_instance.order_update_queue.put(order_data)
                
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error processing private message: {e}")

# --- Performance Monitoring ---
class PerformanceMonitor:
    """Track and analyze bot performance metrics"""
    def __init__(self):
        self.metrics = {
            'api_requests': deque(maxlen=10000),
            'orders_placed': deque(maxlen=10000),
            'orders_filled': deque(maxlen=10000),
            'orders_cancelled': deque(maxlen=10000),
            'pnl': deque(maxlen=10000),
            'spread': deque(maxlen=10000),
            'latency': deque(maxlen=10000),
            'inventory': deque(maxlen=10000)
        }
        self.start_time = time.time()
        
    def record_metric(self, metric_name: str, value: Any = 1):
        """Record a metric value"""
        if metric_name in self.metrics:
            if isinstance(value, (int, float, Decimal)):
                self.metrics[metric_name].append(value)
            else:
                self.metrics[metric_name].append(1)
    
    def get_metric_stats(self, metric_name: str) -> Dict[str, Any]:
        """Get statistics for a metric"""
        if metric_name not in self.metrics or not self.metrics[metric_name]:
            return {}
        values = list(self.metrics[metric_name])
        return {
            'count': len(values),
            'mean': statistics.mean(values) if values else 0,
            'median': statistics.median(values) if values else 0,
            'min': min(values) if values else 0,
            'max': max(values) if values else 0,
            'stddev': statistics.stdev(values) if len(values) > 1 else 0,
            'last': values[-1] if values else 0
        }
    
    def get_uptime(self) -> str:
        """Get current uptime in human-readable format"""
        uptime = time.time() - self.start_time
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    
    def generate_report(self) -> str:
        """Generate performance report"""
        report = [
            "\n=== Performance Report ===",
            f"Uptime: {self.get_uptime()}",
            f"API Requests: {self.get_metric_stats('api_requests')['count']}",
            f"Orders Placed: {self.get_metric_stats('orders_placed')['count']}",
            f"Orders Filled: {self.get_metric_stats('orders_filled')['count']}",
            f"Orders Cancelled: {self.get_metric_stats('orders_cancelled')['count']}",
            f"Current PnL: ${self.get_metric_stats('pnl')['last']:.2f}",
            f"Avg Spread: {self.get_metric_stats('spread')['mean']:.4f} bps",
            f"Avg Order Latency: {self.get_metric_stats('latency')['mean']*1000:.2f} ms",
            f"Current Inventory: {self.get_metric_stats('inventory')['last']:.6f}",
            "========================="
        ]
        return "\n".join(report)

# --- Circuit Breaker for Risk Management ---
class CircuitBreaker:
    """Prevent trading during extreme conditions"""
    def __init__(self, max_failures: int = 5, reset_timeout: int = 300):
        self.failure_count = 0
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        
    def record_failure(self):
        """Record a system failure"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.max_failures:
            self.state = "OPEN"
            logger.critical("Circuit breaker triggered! Trading halted.")
            
    def record_success(self):
        """Record a successful operation"""
        self.failure_count = 0
        self.state = "CLOSED"
        
    def allow_trading(self) -> bool:
        """Determine if trading should be allowed"""
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            # Check if reset timeout has passed
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
                logger.warning("Circuit breaker in HALF-OPEN state. Limited trading allowed.")
                return True
            return False
        # HALF-OPEN state - allow one order through for testing
        self.state = "CLOSED"
        logger.info("Circuit breaker reset to CLOSED state after successful operation.")
        return True

# --- Main Bot Implementation ---
class MarketMakingBot:
    """Advanced market making bot with improved architecture"""
    def __init__(self, api_client: APIClient, state_manager: StateManager, symbol: str,
                 base_qty: Decimal, order_levels: int = 5, spread_bps: Decimal = Decimal('0.05'),
                 inventory_target_base: Decimal = Decimal('0'), risk_params: Dict[str, Any] = None):
        self.api_client = api_client
        self.state_manager = state_manager
        self.symbol = symbol
        self.base_qty = base_qty
        self.order_levels = order_levels
        self.initial_spread_bps = spread_bps#!/usr/bin/env python3
"""
Bybit v5 Market-Making Bot - Ultra Enhanced Version

This is an advanced market-making bot for Bybit's v5 API, designed for
production-ready trading with comprehensive error handling, risk
management, and performance optimizations.

Enhanced Features:
- Centralized Configuration Management
- Multi-Symbol Support Structure
- Advanced API Client with Robust Error Handling & Rate Limiting
- Smart Order Placement & Management Strategies
- Real-time Performance Analytics and Monitoring
- Multi-threaded order execution (via ThreadPoolExecutor)
- Advanced inventory management with hedging capabilities
- WebSocket support with robust reconnection and message handling
- File-based state persistence with atomic writes and expiration
- Comprehensive risk management metrics and calculations
- Volatility-based order sizing
- Structured JSON logging
- Graceful shutdown procedures
- UVLoop integration for performance
- Improved Decimal precision handling
- Symbol-specific configuration and caching
"""

import os
import time
import json
import asyncio
import aiohttp
import hmac
import hashlib
import urllib.parse
import websockets
from dotenv import load_dotenv
import logging
import logging.handlers
from datetime import datetime, timezone, timedelta
from collections import deque, defaultdict
from dataclasses import dataclass, field, asdict, MISSING
from typing import Dict, Any, List, Optional, Tuple, Set, Union, Callable, Type
import signal
import sys
import gc
import psutil
import statistics
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, InvalidOperation, getcontext
import uuid
import numpy as np
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
# import redis # Removed as per user request
import pandas as pd
from functools import lru_cache
import warnings
import copy

# --- Pyrmethus Enhancements ---
try:
    # Attempt to use uvloop for potential performance gains
    import uvloop
    uvloop.install()
    logger.info("uvloop enabled.")
except ImportError:
    logger.warning("uvloop not found. Falling back to default asyncio event loop. Install with: pip install uvloop")

# --- Colorama Setup ---
try:
    from colorama import init, Fore, Style
    init(autoreset=True) # Initialize colorama for Windows compatibility and auto-reset styles
except ImportError:
    # Define dummy Fore and Style if colorama is not installed
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = DummyColor()
    Style = DummyColor()
    # Logging setup handles the warning later

# --- Constants and Configuration ---
# Set context for Decimal operations (precision, rounding)
getcontext().prec = 30 # Set precision for Decimal calculations
getcontext().rounding = ROUND_HALF_UP

load_dotenv()
API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
STATE_DIR = os.path.join(os.path.expanduser("~"), ".bybit_market_maker_state") # Directory for state files

# Validate essential environment variables
if not API_KEY or not API_SECRET:
    # Use termux-toast for critical errors if available, otherwise log
    try:
        os.system("termux-toast 'Error: BYBIT_API_KEY and BYBIT_API_SECRET must be set.'")
    except Exception:
        pass # Ignore if termux-toast is not available
    raise ValueError("Please set BYBIT_API_KEY and BYBIT_API_SECRET in your .env file.")

# Base URLs for Bybit API (Testnet/Mainnet)
BASE_URL = "https://api-testnet.bybit.com" if IS_TESTNET else "https://api.bybit.com"
WS_URL = "wss://stream-testnet.bybit.com/v5/public/linear" if IS_TESTNET else "wss://stream.bybit.com/v5/public/linear"
WS_PRIVATE_URL = "https://api-testnet.bybit.com/v5/private" if IS_TESTNET else "https://api.bybit.com/v5/private" # Corrected WS Private URL if needed for auth

# --- Logging Setup ---
# Centralized logger instance
logger = logging.getLogger('BybitMMBot')
trade_logger = logging.getLogger('TradeLogger')

def setup_logging():
    """Configures logging for the bot with JSON format, colors, and file output."""
    log_level = logging.DEBUG if os.getenv("DEBUG_MODE", "false").lower() == "true" else logging.INFO
    log_dir = os.path.join(os.path.expanduser("~"), "bybit_bot_logs")
    os.makedirs(log_dir, exist_ok=True)

    # Log formatter using structlog or similar for JSON output
    try:
        from structlog import get_logger as structlog_get_logger
        from structlog.stdlib import ProcessorFormatter
        
        structlog_logger = structlog_get_logger()
        
        # Processors for JSON logging
        json_processors = [
            ProcessorFormatter.wrap_for_formatter,
            ProcessorFormatter.remove_processors_meta,
            ProcessorFormatter.JSONRenderer()
        ]
        
        # Add color support for console handler
        color_processors = [
            ProcessorFormatter.wrap_for_formatter,
            ProcessorFormatter.remove_processors_meta,
            ProcessorFormatter.StackInfoRenderer(),
            ProcessorFormatter.format_exc_info,
            ProcessorFormatter.UnicodeDecoder(),
            ProcessorFormatter.TimeStamper(fmt="iso"),
            ProcessorFormatter.add_log_level,
            ProcessorFormatter.add_logger_name,
            ProcessorFormatter.StackInfoRenderer(),
            ProcessorFormatter.format_exc_info,
            ProcessorFormatter.UnicodeDecoder(),
            ProcessorFormatter.ExceptionRenderer(),
            # Custom processor for coloring log levels
            lambda logger, method_name, event_dict: event_dict.update({
                'level': method_name.upper(),
                'color': Style.RESET_ALL + {
                    'DEBUG': Fore.CYAN,
                    'INFO': Fore.GREEN,
                    'WARNING': Fore.YELLOW,
                    'ERROR': Fore.RED,
                    'CRITICAL': Fore.RED + Style.BRIGHT,
                }.get(method_name.upper(), Fore.RESET)
            }),
            # Render with color codes
            lambda logger, method_name, event_dict: f"{event_dict['color']}[{event_dict['timestamp']}] {event_dict['level']} [{event_dict['logger_name']}]: {event_dict['event']}{Style.RESET_ALL}"
        ]

        formatter = ProcessorFormatter(
            processor=ProcessorFormatter.JSONRenderer(), # Default to JSON for file logging
            foreign_pre_chain=json_processors,
            # Console formatter uses different processors for color
            console_formatter=ProcessorFormatter(
                processor=lambda logger, method_name, event_dict: f"{event_dict['color']}[{event_dict['timestamp']}] {event_dict['level']} [{event_dict['logger_name']}]: {event_dict.get('event', '')}{Style.RESET_ALL}",
                foreign_pre_chain=color_processors
            )
        )
        
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter.wrap_for_formatter) # Apply console specific formatting

        # File Handler (JSON)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(os.path.join(log_dir, f"bot_{timestamp_str}.log"), mode='w')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter) # JSON formatter

        # Trade Log File Handler (CSV-like for easy parsing)
        trade_file_handler = logging.FileHandler(os.path.join(log_dir, f"trades_{timestamp_str}.csv"), mode='w')
        trade_file_handler.setLevel(logging.INFO)
        # CSV formatter for trade logs
        trade_formatter = logging.Formatter('%(asctime)s,%(levelname)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        trade_file_handler.setFormatter(trade_formatter)

        # Get root logger and add handlers
        logger.setLevel(log_level)
        if logger.hasHandlers(): logger.handlers.clear() # Clear existing handlers
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        # Configure TradeLogger
        trade_logger.setLevel(logging.INFO)
        if trade_logger.hasHandlers(): trade_logger.handlers.clear()
        trade_logger.addHandler(trade_file_handler)
        trade_logger.propagate = False # Prevent duplicate logging

        # Log colorama warning if it failed to import
        if 'DummyColor' in globals():
            logger.warning("Colorama not found. Terminal output will not be colored. Install with: pip install colorama")

        logger.info(f"Logging setup complete. Level: {logging.getLevelName(log_level)}. Logs saved to: {log_dir}")

    except ImportError:
        # Fallback to basic logging if structlog is not available
        logger.warning("structlog not found. Using basic logging. Install with: pip install structlog")
        log_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(log_formatter)
        
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_handler = logging.FileHandler(os.path.join(log_dir, f"bot_{timestamp_str}.log"), mode='w')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_formatter)
        
        trade_file_handler = logging.FileHandler(os.path.join(log_dir, f"trades_{timestamp_str}.csv"), mode='w')
        trade_file_handler.setLevel(logging.INFO)
        trade_formatter = logging.Formatter('%(asctime)s,%(levelname)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        trade_file_handler.setFormatter(trade_formatter)

        logger.setLevel(log_level)
        if logger.hasHandlers(): logger.handlers.clear()
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        trade_logger.setLevel(logging.INFO)
        if trade_logger.hasHandlers(): trade_logger.handlers.clear()
        trade_logger.addHandler(trade_file_handler)
        trade_logger.propagate = False

# --- Custom Exceptions ---
class BybitAPIError(Exception):
    """Custom exception for Bybit API errors."""
    def __init__(self, message: str, code: Optional[str] = None, response: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.response = response

class RateLimitExceededError(BybitAPIError):
    """Exception raised when rate limits are exceeded."""
    pass

class InvalidOrderParameterError(BybitAPIError):
    """Exception for invalid order parameters (e.g., quantity, price)."""
    pass

class CircuitBreakerOpenError(Exception):
    """Custom exception for when the circuit breaker is open."""
    pass

# --- Enums for Clarity ---
class OrderStatus(Enum):
    """Order status enumeration for enhanced readability"""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    PENDING = "Pending" # Added for potential intermediate states

class TradeSide(Enum):
    """Trade side enumeration for clarity"""
    BUY = "Buy"
    SELL = "Sell"
    NONE = "None" # Added for neutral state

# --- Data Structures ---
@dataclass
class OrderData:
    """Enhanced order data structure with additional fields for comprehensive tracking"""
    order_id: str
    symbol: str
    side: TradeSide
    price: Decimal
    quantity: Decimal
    status: OrderStatus
    timestamp: float
    type: str = "Limit"
    time_in_force: str = "GTC"
    filled_qty: Decimal = Decimal('0')
    avg_price: Decimal = Decimal('0')
    fee: Decimal = Decimal('0')
    reduce_only: bool = False
    post_only: bool = True
    client_order_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    order_pnl: Decimal = Decimal('0')

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization, ensuring Decimal to str conversion"""
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['price'] = str(self.price)
        data['quantity'] = str(self.quantity)
        data['filled_qty'] = str(self.filled_qty)
        data['avg_price'] = str(self.avg_price)
        data['fee'] = str(self.fee)
        data['order_pnl'] = str(self.order_pnl)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_api(cls, api_data: Dict[str, Any]) -> 'OrderData':
        """Create OrderData object from API response dictionary"""
        try:
            return cls(
                order_id=str(api_data.get("orderId", "")),
                symbol=api_data.get("symbol", ""),
                side=TradeSide(api_data.get("side", "")),
                price=Decimal(api_data.get("price", "0")),
                quantity=Decimal(api_data.get("qty", "0")),
                status=OrderStatus(api_data.get("orderStatus", "")),
                timestamp=float(api_data.get("orderTimestamp", 0) / 1000), # Convert ms to seconds
                filled_qty=Decimal(api_data.get("cumExecQty", "0")),
                avg_price=Decimal(api_data.get("avgPrice", "0")),
                type=api_data.get("orderType", "Limit"),
                time_in_force=api_data.get("timeInForce", "GTC"),
                reduce_only=api_data.get("reduceOnly", False),
                post_only=api_data.get("isLeveraged", 0) == 1 and api_data.get("orderType") == "Limit" and api_data.get("mmp", False) == False,
                client_order_id=api_data.get("clOrdID", ""),
                created_at=datetime.fromisoformat(api_data.get("createdTime")) if api_data.get("createdTime") else None,
                updated_at=datetime.fromisoformat(api_data.get("updatedTime")) if api_data.get("updatedTime") else None,
                order_pnl=Decimal(api_data.get("orderPnl", "0")) # PnL might be available in updates
            )
        except (ValueError, KeyError, TypeError, InvalidOperation) as e:
            logger.error(f"Error creating OrderData from API: {api_data} - {e}")
            raise

@dataclass
class MarketData:
    """Market data structure with enhanced fields for analysis"""
    symbol: str
    best_bid: Decimal
    best_ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    mid_price: Decimal = Decimal('0')
    spread: Decimal = Decimal('0')
    timestamp: float
    volume_24h: Decimal = Decimal('0')
    trades_24h: int = 0
    last_price: Optional[Decimal] = None
    funding_rate: Optional[Decimal] = None

    @property
    def spread_bps(self) -> Decimal:
        """Spread in basis points for precise analysis"""
        if self.mid_price > 0:
            return (self.spread / self.mid_price) * Decimal('10000')
        return Decimal('0')

    def update_from_tick(self, tick_data: Dict[str, Any]):
        """Update market data from a ticker stream or API response"""
        self.best_bid = Decimal(tick_data.get('bid1', '0'))
        self.best_ask = Decimal(tick_data.get('ask1', '0'))
        self.bid_size = Decimal(tick_data.get('bid1Size', '0'))
        self.ask_size = Decimal(tick_data.get('ask1Size', '0'))
        self.last_price = Decimal(tick_data.get('lastPrice', '0')) if 'lastPrice' in tick_data else self.last_price
        self.volume_24h = Decimal(tick_data.get('volume24h', str(self.volume_24h)))
        self.trades_24h = int(tick_data.get('turnover24h', str(self.trades_24h))) # Assuming turnover relates to trades
        self.timestamp = float(tick_data.get('time', time.time())) # Use server time if available

        # Calculate mid-price and spread
        if self.best_bid > 0 and self.best_ask > 0:
            self.mid_price = (self.best_bid + self.best_ask) / Decimal('2')
            self.spread = self.best_ask - self.best_bid
        else:
            self.mid_price = Decimal('0')
            self.spread = Decimal('0')

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['best_bid'] = str(self.best_bid)
        data['best_ask'] = str(self.best_ask)
        data['bid_size'] = str(self.bid_size)
        data['ask_size'] = str(self.ask_size)
        data['mid_price'] = str(self.mid_price)
        data['spread'] = str(self.spread)
        data['volume_24h'] = str(self.volume_24h)
        if self.last_price:
            data['last_price'] = str(self.last_price)
        if self.funding_rate:
            data['funding_rate'] = str(self.funding_rate)
        return data

@dataclass
class RiskMetrics:
    """Comprehensive risk management metrics with enhanced calculations"""
    max_drawdown_pct: Decimal = Decimal('0') # Max drawdown as percentage of initial equity
    max_drawdown_abs: Decimal = Decimal('0') # Max drawdown in absolute value
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0 # Placeholder
    var_95: Decimal = Decimal('0') # Value at Risk (placeholder)

    # Runtime metrics
    initial_equity: Decimal = Decimal('0') # Store initial equity for drawdown calculation
    current_equity: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    current_position_base: Decimal = Decimal('0') # Current position size in base currency
    max_position_base: Decimal = Decimal('0') # Max allowed position size in base currency
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_winning_pnl: Decimal = Decimal('0')
    total_losing_pnl: Decimal = Decimal('0')
    peak_equity: Decimal = Decimal('0') # Track the highest equity reached

    def __post_init__(self):
        """Initialize derived metrics and ensure equity is set"""
        if self.initial_equity == 0:
            logger.warning("Initial equity not set, assuming 0. Setting to a default may be required.")
        self.peak_equity = self.initial_equity # Initialize peak equity
        self.current_equity = self.initial_equity # Initialize current equity

    def update_trade_stats(self, pnl: Decimal):
        """Update trade statistics with more robust calculations"""
        self.trade_count += 1
        if pnl > 0:
            self.winning_trades += 1
            self.total_winning_pnl += pnl
        else:
            self.losing_trades += 1
            self.total_losing_pnl += abs(pnl)

        # Calculate win rate
        if self.trade_count > 0:
            self.win_rate = (self.winning_trades / self.trade_count) * 100.0
        else:
            self.win_rate = 0.0

        # Calculate profit factor, handling division by zero
        if self.total_losing_pnl > 0:
            self.profit_factor = float(self.total_winning_pnl / self.total_losing_pnl)
        elif self.total_winning_pnl > 0:
            self.profit_factor = float('inf') # Handle case with wins but no losses
        else:
            self.profit_factor = 0.0

    def update_equity_and_drawdown(self):
        """Update equity and calculate drawdown"""
        # Calculate current equity based on realized and unrealized PnL
        self.current_equity = self.initial_equity + self.realized_pnl + self.unrealized_pnl
        
        # Update peak equity if current equity is higher
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        # Calculate absolute drawdown
        drawdown_abs = self.peak_equity - self.current_equity
        self.max_drawdown_abs = max(self.max_drawdown_abs, drawdown_abs)

        # Calculate percentage drawdown
        if self.peak_equity > 0:
            self.max_drawdown_pct = (self.max_drawdown_abs / self.peak_equity) * Decimal('100.0')
        else:
            self.max_drawdown_pct = Decimal('0')

    def calculate_performance_ratios(self, risk_free_rate: float = 0.0):
        """Calculate Sharpe Ratio and Calmar Ratio"""
        # Sharpe Ratio calculation (simplified using trade PnLs)
        # A more accurate calculation would involve daily PnL over a longer period.
        trade_pnls = []
        # Placeholder: Ideally, we'd store PnLs per trade or daily PnLs
        # For now, use a simplified approach based on avg win/loss.
        if self.winning_trades > 0: trade_pnls.extend([self.total_winning_pnl / self.winning_trades] * self.winning_trades)
        if self.losing_trades > 0: trade_pnls.extend([-(self.total_losing_pnl / self.losing_trades)] * self.losing_trades)

        if len(trade_pnls) >= 2:
            try:
                # Calculate standard deviation of returns
                std_dev_pnl = Decimal(np.std(trade_pnls))
                # Calculate average PnL per trade (approximate excess return)
                avg_pnl = self.realized_pnl / self.trade_count if self.trade_count > 0 else Decimal('0')
                
                if std_dev_pnl > 0:
                    self.sharpe_ratio = float((avg_pnl - risk_free_rate) / std_dev_pnl)
                else:
                    self.sharpe_ratio = 0.0 # Avoid division by zero
            except Exception as e:
                logger.error(f"Error calculating Sharpe Ratio: {e}")
                self.sharpe_ratio = 0.0
        else:
            self.sharpe_ratio = 0.0

        # Calmar Ratio calculation
        if self.max_drawdown_pct > 0:
            try:
                self.calmar_ratio = float(self.profit_factor / float(self.max_drawdown_pct)) if self.max_drawdown_pct else 0.0
            except Exception as e:
                logger.error(f"Error calculating Calmar Ratio: {e}")
                self.calmar_ratio = 0.0
        else:
            self.calmar_ratio = 0.0 # Avoid division by zero if no drawdown occurred


    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        for key, value in data.items():
            if isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, datetime):
                data[key] = value.isoformat()
        return data

class PerformanceMonitor:
    """Monitor bot performance metrics with enhanced tracking"""
    def __init__(self):
        self.start_time = time.time()
        self.metrics = defaultdict(float) # Use float for counts/values
        self.latencies = deque(maxlen=1000) # General API latencies
        self.order_latencies = deque(maxlen=1000) # Order specific latencies
        self.ws_latencies = deque(maxlen=1000) # WebSocket latencies
        self.api_call_counts = defaultdict(int)
        self.api_error_counts = defaultdict(int)
        self.last_gc_collection = time.time()

    def record_metric(self, metric_name: str, value: float = 1.0):
        """Record a metric, ensuring thread-safety if used concurrently"""
        # Basic thread safety for metrics, consider more robust locking if needed
        self.metrics[metric_name] += value

    def record_latency(self, latency_type: str, latency: float):
        """Record latency measurement, ensuring thread-safety"""
        if latency is not None and latency >= 0: # Only record valid latencies
            if latency_type == 'order':
                self.order_latencies.append(latency)
            elif latency_type == 'ws':
                self.ws_latencies.append(latency)
            else:
                self.latencies.append(latency)

    def record_api_call(self, endpoint: str, success: bool = True):
        """Record API call and its success status"""
        self.api_call_counts[endpoint] += 1
        if not success:
            self.api_error_counts[endpoint] += 1

    def trigger_gc(self):
        """Manually trigger garbage collection if needed"""
        if time.time() - self.last_gc_collection > 600: # Trigger GC every 10 minutes
            collected = gc.collect()
            logger.debug(f"Manual garbage collection triggered. Collected {collected} objects.")
            self.last_gc_collection = time.time()

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics, calculating averages and percentiles"""
        uptime = time.time() - self.start_time

        stats = {
            'uptime_hours': round(uptime / 3600, 2),
            'total_orders_placed': self.metrics.get('orders_placed', 0),
            'total_orders_filled': self.metrics.get('orders_filled', 0),
            'total_orders_cancelled': self.metrics.get('orders_cancelled', 0),
            'total_orders_rejected': self.metrics.get('orders_rejected', 0),
            'ws_messages_processed': self.metrics.get('ws_messages', 0),
            'total_api_errors': sum(self.api_error_counts.values()),
            'memory_usage_mb': round(psutil.Process().memory_info().rss / 1024 / 1024, 2),
            'cpu_usage_percent': psutil.cpu_percent(interval=None),
            'active_threads': threading.active_count(),
            'gc_collections_gen0': gc.get_count()[0], # Number of collections of gen 0
        }

        # Calculate latency stats safely using numpy
        if self.order_latencies:
            stats['avg_order_latency_ms'] = round(np.mean(self.order_latencies) * 1000, 2)
            stats['p99_order_latency_ms'] = round(np.percentile(self.order_latencies, 99) * 1000, 2)
            stats['max_order_latency_ms'] = round(np.max(self.order_latencies) * 1000, 2)
        else:
            stats.update({'avg_order_latency_ms': 0, 'p99_order_latency_ms': 0, 'max_order_latency_ms': 0})

        if self.ws_latencies:
            stats['avg_ws_latency_ms'] = round(np.mean(self.ws_latencies) * 1000, 2)
            stats['p99_ws_latency_ms'] = round(np.percentile(self.ws_latencies, 99) * 1000, 2)
        else:
            stats.update({'avg_ws_latency_ms': 0, 'p99_ws_latency_ms': 0})

        # Include API call stats
        stats['api_call_counts'] = dict(self.api_call_counts)
        stats['api_error_counts'] = dict(self.api_error_counts)

        return stats

class CircuitBreaker:
    """
    Circuit Breaker pattern to prevent repeated calls to failing services.
    Includes exponential backoff for recovery attempts.
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0, expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_failure_time = 0.0
        self.lock = asyncio.Lock()

    async def __aenter__(self):
        async with self.lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF-OPEN"
                    logger.warning("Circuit Breaker: Recovery timeout elapsed. Moving to HALF-OPEN.")
                else:
                    remaining_time = self.recovery_timeout - (time.time() - self.last_failure_time)
                    raise CircuitBreakerOpenError(f"Circuit breaker is OPEN. Try again in {remaining_time:.2f}s")
            elif self.state == "HALF-OPEN":
                # Allow one request to pass through in HALF-OPEN state
                pass
            # If CLOSED, proceed normally
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self.lock:
            if exc_type is not None and issubclass(exc_type, self.expected_exceptions):
                # An error occurred during the operation
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.state == "HALF-OPEN":
                    # If the single allowed request failed, go back to OPEN
                    self.state = "OPEN"
                    logger.error(f"Circuit Breaker: HALF-OPEN request failed ({exc_val}). Re-opening circuit.")
                elif self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error(f"Circuit Breaker: Failure threshold ({self.failure_threshold}) reached. Opening circuit for {self.recovery_timeout}s. Last error: {exc_val}")
                # Log the specific error for debugging
                logger.debug(f"Circuit Breaker caught exception: {exc_val}")
            elif self.state == "HALF-OPEN":
                # If the HALF-OPEN request succeeded (no exception)
                self.state = "CLOSED"
                self.failure_count = 0 # Reset failure count on success
                logger.info("Circuit Breaker: HALF-OPEN request succeeded. Closing circuit.")
            elif self.state == "CLOSED":
                # Successful request in CLOSED state, reset failure count if it was > 0
                if self.failure_count > 0:
                    logger.debug("Circuit Breaker: Successful request in CLOSED state. Resetting failure count.")
                    self.failure_count = 0

class RateLimiter:
    """
    Enhanced rate limiter with multiple tiers, burst handling, and per-endpoint tracking.
    Uses asyncio.Lock for thread-safe operations.
    """
    def __init__(self, limits: Dict[str, Tuple[int, int]], default_limit: Tuple[int, int] = (100, 60), burst_allowance_factor: float = 0.15):
        """
        Initialize rate limiter
        limits: Dict of endpoint_prefix -> (max_requests, window_seconds)
        default_limit: Tuple for endpoints not explicitly defined.
        burst_allowance_factor: Allow requests exceeding the limit temporarily.
        """
        self.limits = {k: v for k, v in limits.items()}
        self.default_limit = default_limit
        self.burst_allowance_factor = burst_allowance_factor
        self.requests = defaultdict(lambda: deque()) # Use lambda for lazy initialization
        self.lock = asyncio.Lock()

    async def acquire(self, endpoint: str):
        """Acquire permission to make a request, applying rate limits and burst allowance"""
        async with self.lock:
            max_requests, window_seconds = self.default_limit
            # Find the most specific limit that matches the endpoint prefix
            for prefix, limit_config in sorted(self.limits.items(), key=lambda item: len(item[0]), reverse=True):
                if endpoint.startswith(prefix):
                    max_requests, window_seconds = limit_config
                    break

            # Calculate effective max requests including burst allowance
            effective_max_requests = int(max_requests * (1 + self.burst_allowance_factor))

            request_times = self.requests[endpoint]
            now = time.time()

            # Remove requests outside the current window
            while request_times and request_times[0] < now - window_seconds:
                request_times.popleft()

            # Check if we've exceeded the effective limit
            if len(request_times) >= effective_max_requests:
                # Calculate time until the oldest request in the window expires
                time_to_wait = window_seconds - (now - request_times[0])
                if time_to_wait > 0:
                    logger.warning(f"Rate limit imminent for {endpoint}. Waiting for {time_to_wait:.2f} seconds.")
                    await asyncio.sleep(time_to_wait)
                    # Re-acquire after waiting to ensure the state is current and accurate
                    return await self.acquire(endpoint) # Recursive call to re-evaluate

            # Record the current request time
            request_times.append(now)
            # logger.debug(f"Acquired for {endpoint}. Current count: {len(request_times)}/{effective_max_requests}") # Debugging line

# --- Configuration Management ---
@dataclass
class SymbolConfig:
    symbol: str
    base_qty: Decimal
    order_levels: int = 5
    spread_bps: Decimal = Decimal('0.05') # Spread in basis points
    inventory_target_base: Decimal = Decimal('0')
    risk_params: Dict[str, Any] = field(default_factory=lambda: {
        "max_position_base": Decimal('0.1'), # Example max position size in base currency
        "max_drawdown_pct": Decimal('10.0'),  # Max 10% drawdown
        "initial_equity": Decimal('10000')     # Example initial equity
    })
    # Add other symbol-specific settings here

@dataclass
class BotConfig:
    api_key: str
    api_secret: str
    is_testnet: bool
    state_directory: str = STATE_DIR
    symbols: List[SymbolConfig] = field(default_factory=list)
    # General bot settings
    log_level: str = "INFO"
    debug_mode: bool = False
    performance_monitoring_interval: int = 60 # seconds
    state_save_interval: int = 300 # seconds
    # API Client settings
    api_timeout_total: int = 45
    api_timeout_connect: int = 10
    api_timeout_sock_read: int = 20
    api_connection_limit: int = 150
    api_connection_limit_per_host: int = 50
    api_keepalive_timeout: int = 60
    # Rate limiter settings
    rate_limits: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        # Specific Bybit V5 rate limits (check Bybit documentation for accuracy)
        '/v5/order': (50, 10),       # Orders: 50 req/10 sec
        '/v5/position': (120, 60),   # Positions: 120 req/60 sec
        '/v5/user/auth': (1, 60),    # Auth: 1 req/60 sec (example)
        '/v5/market/tickers': (100, 1), # Tickers: 100 req/sec
        '/v5/market/kline': (50, 1),  # Kline: 50 req/sec
        '/v5/account/wallet/balance': (20, 60), # Balance: 20 req/60 sec
        '/v5/market/symbol': (100, 1), # Symbol Info: 100 req/sec
        '/v5/order/realtime': (50, 1), # Open Orders: 50 req/sec
        '/v5/public/liq-symbol': (50, 1), # Liquidation data
    })
    rate_limit_default: Tuple[int, int] = (100, 60)
    rate_limit_burst_factor: float = 0.15
    # WebSocket settings
    ws_ping_interval: int = 30
    ws_pong_timeout: int = 10
    # Circuit Breaker settings
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    circuit_breaker_exceptions: Tuple[Type[Exception], ...] = (
        aiohttp.ClientError, asyncio.TimeoutError, CircuitBreakerOpenError, BybitAPIError, ValueError
    )

    @staticmethod
    def load_from_env():
        """Load configuration from environment variables."""
        config = BotConfig(
            api_key=API_KEY,
            api_secret=API_SECRET,
            is_testnet=IS_TESTNET,
            state_directory=STATE_DIR,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true",
            performance_monitoring_interval=int(os.getenv("PERF_MON_INTERVAL", 60)),
            state_save_interval=int(os.getenv("STATE_SAVE_INTERVAL", 300)),
            api_timeout_total=int(os.getenv("API_TIMEOUT_TOTAL", 45)),
            api_timeout_connect=int(os.getenv("API_TIMEOUT_CONNECT", 10)),
            api_timeout_sock_read=int(os.getenv("API_TIMEOUT_SOCK_READ", 20)),
            api_connection_limit=int(os.getenv("API_CONN_LIMIT", 150)),
            api_connection_limit_per_host=int(os.getenv("API_CONN_LIMIT_HOST", 50)),
            api_keepalive_timeout=int(os.getenv("API_KEEPALIVE_TIMEOUT", 60)),
            ws_ping_interval=int(os.getenv("WS_PING_INTERVAL", 30)),
            ws_pong_timeout=int(os.getenv("WS_PONG_TIMEOUT", 10)),
            circuit_breaker_failure_threshold=int(os.getenv("CB_FAIL_THRESHOLD", 5)),
            circuit_breaker_recovery_timeout=float(os.getenv("CB_RECOVERY_TIMEOUT", 60.0)),
        )
        
        # Load symbols from environment variables (e.g., SYMBOL_BTCUSDT_QTY="0.001")
        # This requires a convention, e.g., SYMBOL_<TICKER>_QTY, SYMBOL_<TICKER>_SPREAD_BPS etc.
        # For simplicity now, we'll hardcode one symbol config. Multi-symbol loading can be complex.
        
        # Example hardcoded symbol config - Replace with env var loading if needed
        btc_config = SymbolConfig(
            symbol="BTCUSDT",
            base_qty=Decimal(os.getenv("SYMBOL_BTCUSDT_QTY", "0.001")),
            order_levels=int(os.getenv("SYMBOL_BTCUSDT_LEVELS", 5)),
            spread_bps=Decimal(os.getenv("SYMBOL_BTCUSDT_SPREAD_BPS", "0.05")),
            inventory_target_base=Decimal(os.getenv("SYMBOL_BTCUSDT_INV_TARGET", "0")),
            risk_params={
                "max_position_base": Decimal(os.getenv("SYMBOL_BTCUSDT_MAX_POS", "0.1")),
                "max_drawdown_pct": Decimal(os.getenv("SYMBOL_BTCUSDT_MAX_DD_PCT", "10.0")),
                "initial_equity": Decimal(os.getenv("SYMBOL_BTCUSDT_INIT_EQ", "10000"))
            }
        )
        config.symbols.append(btc_config)

        # Add ETHUSDT symbol if configured
        if os.getenv("SYMBOL_ETHUSDT_QTY"):
             eth_config = SymbolConfig(
                symbol="ETHUSDT",
                base_qty=Decimal(os.getenv("SYMBOL_ETHUSDT_QTY", "0.01")),
                order_levels=int(os.getenv("SYMBOL_ETHUSDT_LEVELS", 5)),
                spread_bps=Decimal(os.getenv("SYMBOL_ETHUSDT_SPREAD_BPS", "0.07")),
                inventory_target_base=Decimal(os.getenv("SYMBOL_ETHUSDT_INV_TARGET", "0")),
                risk_params={
                    "max_position_base": Decimal(os.getenv("SYMBOL_ETHUSDT_MAX_POS", "0.5")),
                    "max_drawdown_pct": Decimal(os.getenv("SYMBOL_ETHUSDT_MAX_DD_PCT", "10.0")),
                    "initial_equity": Decimal(os.getenv("SYMBOL_ETHUSDT_INIT_EQ", "5000"))
                }
            )
             config.symbols.append(eth_config)

        setup_logging() # Setup logging based on loaded config
        
        return config

# --- File State Manager ---
class FileStateManager:
    """Manages bot state persistence using JSON files with atomic writes and expiration."""
    def __init__(self, state_dir: str, default_expiry_seconds: int = 86400): # Default expiry 1 day
        self.state_dir = state_dir
        self.default_expiry_seconds = default_expiry_seconds
        os.makedirs(self.state_dir, exist_ok=True)
        self.cleanup_task = None # Placeholder for cleanup task

    def _get_file_path(self, key: str) -> str:
        """Get the file path for a given state key, sanitized."""
        safe_key = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in key)
        return os.path.join(self.state_dir, f"{safe_key}.json")

    def _serialize(self, value: Any) -> Optional[str]:
        """Serialize complex objects for storage"""
        try:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, (OrderData, RiskMetrics)):
                return json.dumps(value.to_dict())
            if isinstance(value, (list, tuple)):
                # Recursively serialize items in lists/tuples
                return json.dumps([self._serialize(item) for item in value])
            if isinstance(value, dict):
                # Serialize dictionary values, handling Decimals and datetimes
                serialized_dict = {}
                for k, v in value.items():
                    serialized_dict[k] = self._serialize(v)
                return json.dumps(serialized_dict)
            if isinstance(value, (int, float, str, bool)) or value is None:
                return str(value) # Convert basic types to string for consistency
            
            logger.warning(f"Unsupported type for file storage: {type(value)}")
            return None
        except Exception as e:
            logger.error(f"Serialization error for type {type(value)}: {e}")
            return None

    def _deserialize(self, data: str, expected_type: Optional[Type] = None) -> Any:
        """Deserialize data from file, attempting type conversion"""
        if not data: return None
        try:
            parsed_data = json.loads(data)

            # Convert Decimals stored as strings back to Decimal objects
            def convert_decimals(item):
                if isinstance(item, dict):
                    return {k: convert_decimals(v) for k, v in item.items()}
                if isinstance(item, list):
                    return [convert_decimals(elem) for elem in item]
                if isinstance(item, str):
                    try:
                        # Attempt conversion if it looks like a Decimal string
                        if '.' in item or 'E' in item.upper():
                            Decimal(item) # Test if it's a valid Decimal string
                            return Decimal(item)
                    except (InvalidOperation, TypeError):
                        pass # Not a Decimal string
                return item

            converted_data = convert_decimals(parsed_data)

            # Rehydrate specific dataclasses if expected_type is provided
            if expected_type == OrderData and isinstance(converted_data, dict):
                return OrderData(**converted_data)
            if expected_type == RiskMetrics and isinstance(converted_data, dict):
                return RiskMetrics(**converted_data)
            if expected_type == list and isinstance(converted_data, list):
                # Attempt to infer type for list elements if needed, or return as is
                 if converted_data and isinstance(converted_data[0], dict):
                    if 'order_id' in converted_data[0]: # Likely list of orders
                        return [OrderData(**item) if isinstance(item, dict) else item for item in converted_data]
                    if 'symbol' in converted_data[0] and 'best_bid' in converted_data[0]: # Likely list of MarketData
                        return [MarketData(**item) if isinstance(item, dict) else item for item in converted_data]
                 return converted_data # Return list as is if type inference fails

            return converted_data

        except (json.JSONDecodeError, TypeError, ValueError, InvalidOperation) as e:
            logger.error(f"Deserialization error: {e}. Data: '{data[:100]}...'")
            return None # Return None on failure

    def set(self, key: str, value: Any, expiry_seconds: Optional[int] = None) -> bool:
        """Set a value in a file with an expiration time."""
        file_path = self._get_file_path(key)
        serialized_value = self._serialize(value)
        if serialized_value is None:
            logger.error(f"Failed to serialize value for key '{key}'")
            return False

        temp_path = file_path + ".tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(serialized_value)
            
            # Atomic rename: move temp file to final destination
            os.rename(temp_path, file_path)
            
            # Set modification time for expiration simulation
            current_time = time.time()
            effective_expiry = expiry_seconds if expiry_seconds is not None else self.default_expiry_seconds
            os.utime(file_path, (current_time, current_time + effective_expiry))
            
            logger.debug(f"State saved to file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"File state SET error for key '{key}' at {file_path}: {e}")
            # Clean up temp file if rename failed
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except OSError: pass
            return False

    def get(self, key: str, expected_type: Optional[Type] = None) -> Optional[Any]:
        """Get a value from a file, attempting deserialization and checking expiration."""
        file_path = self._get_file_path(key)
        if not os.path.exists(file_path):
            return None
        
        # Check file expiration
        current_time = time.time()
        try:
            mtime = os.path.getmtime(file_path)
            # Check if file's access time + expiry duration has passed
            if current_time > mtime + self.default_expiry_seconds: # Use default expiry if no specific expiry set during save
                logger.warning(f"State file expired for key '{key}': {file_path}")
                self.delete(key) # Clean up expired file
                return None
        except OSError as e:
            logger.error(f"Error accessing file metadata for {file_path}: {e}")
            # Proceed to read if metadata access fails, but log the error
            pass

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = f.read()
            return self._deserialize(data, expected_type)
        except Exception as e:
            logger.error(f"File state GET error for key '{key}' at {file_path}: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete a state file"""
        file_path = self._get_file_path(key)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"State file deleted: {file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"File state DELETE error for key '{key}' at {file_path}: {e}")
            return False

    async def cleanup_expired_files(self, interval: int = 3600):
        """Periodically clean up expired state files."""
        if self.cleanup_task and not self.cleanup_task.done():
            return # Already running
            
        async def cleaner():
            while True:
                await asyncio.sleep(interval)
                logger.info("Running state file cleanup...")
                now = time.time()
                deleted_count = 0
                for filename in os.listdir(self.state_dir):
                    if filename.endswith(".json"):
                        file_path = os.path.join(self.state_dir, filename)
                        try:
                            mtime = os.path.getmtime(file_path)
                            if now > mtime + self.default_expiry_seconds:
                                os.remove(file_path)
                                logger.debug(f"Cleaned up expired file: {file_path}")
                                deleted_count += 1
                        except OSError as e:
                            logger.error(f"Error during file cleanup for {file_path}: {e}")
                logger.info(f"State file cleanup finished. Deleted {deleted_count} expired files.")

        self.cleanup_task = asyncio.create_task(cleaner())
        logger.info(f"Scheduled state file cleanup every {interval} seconds.")


# --- ML/Optimization Components ---
class SpreadOptimizer:
    """
    Placeholder for ML-based spread optimization. Uses statistical analysis.
    """
    def __init__(self, symbol: str, initial_spread_bps: Decimal = Decimal('0.05')):
        self.symbol = symbol
        self.target_spread_bps = initial_spread_bps
        self.historical_spreads_bps = deque(maxlen=100) # Stores spread in bps
        self.historical_volumes = deque(maxlen=100) # Stores volume
        self.historical_volatility = deque(maxlen=50) # Stores volatility estimate (e.g., std dev of spread)
        self.model = None # Placeholder for ML model
        self.update_interval = 60 # Update optimization logic every 60 seconds
        self.last_mid_price = Decimal('0')

    def update_data(self, market_data: MarketData):
        """Update historical data points"""
        if market_data.spread > 0 and market_data.mid_price > 0:
            self.historical_spreads_bps.append(market_data.spread_bps)
            # Estimate volatility based on spread changes
            if self.last_mid_price > 0:
                spread_change = abs(market_data.spread_bps - self.target_spread_bps) # Change from target spread
                self.historical_volatility.append(spread_change)
            else: # First data point
                 self.historical_volatility.append(market_data.spread_bps) # Use spread itself as initial volatility proxy

        if market_data.volume_24h > 0:
            self.historical_volumes.append(market_data.volume_24h)
        
        self.last_mid_price = market_data.mid_price

    def optimize_spread(self, current_market_data: MarketData) -> Decimal:
        """Calculate optimal spread based on historical data and market conditions"""
        if len(self.historical_spreads_bps) < 10: # Need sufficient data points
            return self.target_spread_bps # Return current target if insufficient data

        try:
            avg_spread_bps = Decimal(statistics.mean(self.historical_spreads_bps))
            std_dev_volatility = Decimal(statistics.stdev(self.historical_volatility)) if len(self.historical_volatility) > 1 else Decimal('0')
            avg_volume = Decimal(statistics.mean(self.historical_volumes)) if self.historical_volumes else Decimal('0')

            # --- Adjust spread based on volatility ---
            volatility_factor = Decimal('1.0')
            # Example: Increase spread if volatility is high (e.g., std dev > 1.5x target spread)
            if std_dev_volatility > self.target_spread_bps * Decimal('1.5'):
                volatility_factor = Decimal('1.2')
            # Example: Decrease spread if volatility is low (e.g., std dev < 0.5x target spread)
            elif std_dev_volatility < self.target_spread_bps * Decimal('0.5'):
                volatility_factor = Decimal('0.9')

            # --- Adjust spread based on volume ---
            volume_factor = Decimal('1.0')
            # Example: Widen spread for low volume, narrow for high volume
            if avg_volume < 50000: # Threshold for low volume
                volume_factor = Decimal('1.1')
            elif avg_volume > 200000: # Threshold for high volume
                volume_factor = Decimal('0.95')

            new_spread = self.target_spread_bps * volatility_factor * volume_factor
            
            # --- Clamp spread to reasonable bounds ---
            min_target_spread = Decimal('0.01') # Minimum 1 bps spread
            max_target_spread = self.target_spread_bps * Decimal('2.0') # Max double the initial spread
            new_spread = max(min_target_spread, min(new_spread, max_target_spread))
            
            logger.info(
                f"Optimizing spread for {self.symbol}: AvgSpread={avg_spread_bps:.4f} bps, "
                f"Volatility={std_dev_volatility:.4f} bps, AvgVol={avg_volume:,.0f}. "
                f"New target: {new_spread:.4f} bps"
            )
            self.target_spread_bps = new_spread
            return new_spread

        except Exception as e:
            logger.error(f"Error during spread optimization for {self.symbol}: {e}")
            return self.target_spread_bps # Return current target on error

# --- Core Bot Logic ---
class MarketMakingBot:
    """
    The core market-making bot logic, orchestrating API calls, order management,
    and risk control for a single symbol.
    """
    def __init__(self, config: BotConfig, symbol_config: SymbolConfig, api_client: 'EnhancedAPIClient', state_manager: FileStateManager):
        self.config = config
        self.symbol_config = symbol_config
        self.api_client = api_client
        self.state_manager = state_manager
        self.symbol = symbol_config.symbol
        
        self.base_qty_initial = symbol_config.base_qty # Initial quantity for orders
        self.order_levels = symbol_config.order_levels
        self.spread_bps = symbol_config.spread_bps
        self.inventory_target_base = symbol_config.inventory_target_base
        self.risk_params = symbol_config.risk_params

        self.market_data: Optional[MarketData] = None
        self.open_orders: Dict[str, OrderData] = {} # Store open orders by order ID
        self.positions: Dict[str, Dict[str, Any]] = {} # Store position data (symbol -> details)
        self.risk_metrics = RiskMetrics(
            initial_equity=self.risk_params.get('initial_equity', Decimal('10000')),
            max_position_base=self.risk_params.get('max_position_base', Decimal('0.1')),
            max_drawdown_pct=self.risk_params.get('max_drawdown_pct', Decimal('10.0'))
        )
        self.spread_optimizer = SpreadOptimizer(self.symbol, initial_spread_bps=self.spread_bps)

        self.running = False
        self.tasks = [] # Store asyncio task handles
        self.order_update_queue = asyncio.Queue() # Queue for processing order updates from WS
        self.ws_message_queue = asyncio.Queue() # General queue for WS messages if needed
        self.tracked_symbols = {self.symbol} # Symbols managed by this bot instance

        # Initialize symbol info cache
        self.symbol_info = None
        self.symbol_info_cache_time = 0
        self.symbol_info_cache_ttl = 300 # Cache symbol info for 5 minutes

        # Set the bot instance in the API client for WS message routing
        self.api_client.register_bot_instance(self)

        # Load existing state from files
        self._load_state()

    async def _get_symbol_info(self):
        """Fetch or retrieve cached symbol information."""
        now = time.time()
        if self.symbol_info and (now - self.symbol_info_cache_time < self.symbol_info_cache_ttl):
            return self.symbol_info # Return cached info
        
        logger.debug(f"Fetching symbol info for {self.symbol}...")
        fetched_info = await self.api_client.get_symbol_info(self.symbol)
        if fetched_info:
            self.symbol_info = fetched_info
            self.symbol_info_cache_time = now
            logger.debug(f"Cached symbol info for {self.symbol}: {self.symbol_info}")
        else:
            logger.warning(f"Failed to fetch symbol info for {self.symbol}")
        return self.symbol_info

    def _quantize_price(self, price: Decimal) -> Decimal:
        """Quantize price according to symbol's tick size."""
        info = self._get_symbol_info() # Ensure info is available
        if info and 'tick_size' in info:
            return price.quantize(info['tick_size'], rounding=ROUND_HALF_UP)
        return price # Return original if info unavailable

    def _quantize_quantity(self, quantity: Decimal) -> Decimal:
        """Quantize quantity according to symbol's step size and check min quantity."""
        info = self._get_symbol_info()
        if not info: return quantity # Return original if info unavailable
        
        try:
            step_size = info.get('lot_size_step', Decimal('0.001'))
            min_qty = info.get('min_qty', Decimal('0.001'))
            
            quantized_qty = quantity.quantize(step_size, rounding=ROUND_DOWN)
            
            # Ensure quantity meets minimum requirement
            if quantized_qty < min_qty:
                logger.warning(f"Order quantity {quantized_qty} is below minimum {min_qty} for {self.symbol}. Adjusting to min_qty.")
                return min_qty.quantize(step_size, rounding=ROUND_DOWN) # Quantize min_qty as well
            return quantized_qty
        except (InvalidOperation, KeyError, TypeError) as e:
            logger.error(f"Error quantizing quantity for {self.symbol}: {e}. Original qty: {quantity}")
            return quantity # Return original on error

    def _load_state(self):
        """Load bot state (orders, risk metrics) from files"""
        orders_data = self.state_manager.get(f"{self.symbol}:open_orders", expected_type=list)
        if orders_data:
            for order_dict in orders_data:
                try:
                    # Ensure data is converted correctly before creating OrderData
                    order_dict_processed = {k: Decimal(v) if k in ['price', 'quantity', 'filled_qty', 'avg_price', 'fee', 'order_pnl'] and v is not None else v
                                             for k, v in order_dict.items()}
                    order = OrderData(**order_dict_processed)
                    self.open_orders[order.order_id] = order
                    logger.info(f"Loaded open order from file: {order.order_id} ({order.symbol} {order.side.value} @ {order.price})")
                except Exception as e:
                    logger.error(f"Failed to load order from file: {order_dict} - {e}")

        risk_data = self.state_manager.get(f"{self.symbol}:risk_metrics", expected_type=RiskMetrics)
        if risk_data:
            self.risk_metrics = risk_data
            # Ensure current equity matches initial if only initial was loaded, or recalculate if needed
            if self.risk_metrics.current_equity == 0 and self.risk_metrics.initial_equity > 0:
                self.risk_metrics.current_equity = self.risk_metrics.initial_equity
            elif self.risk_metrics.current_equity == 0 and self.risk_metrics.initial_equity == 0:
                 logger.warning(f"Risk metrics loaded with zero initial and current equity for {self.symbol}.")

            logger.info(f"Loaded risk metrics for {self.symbol}: Equity={self.risk_metrics.current_equity}, MaxDD%={self.risk_metrics.max_drawdown_pct:.2f}%")
        else:
            # If no risk data loaded, ensure initial equity is set correctly
            if self.risk_metrics.initial_equity == 0:
                self.risk_metrics.initial_equity = self.symbol_config.risk_params.get('initial_equity', Decimal('10000'))
                self.risk_metrics.current_equity = self.risk_metrics.initial_equity
                logger.info(f"Using default initial equity for {self.symbol}: {self.risk_metrics.initial_equity}")

    def _save_state(self):
        """Save bot state (orders, risk metrics) to files"""
        # Save open orders (convert OrderData to dicts)
        orders_to_save = [order.to_dict() for order in self.open_orders.values()]
        self.state_manager.set(f"{self.symbol}:open_orders", orders_to_save)
        
        # Save risk metrics
        self.state_manager.set(f"{self.symbol}:risk_metrics", self.risk_metrics)
        logger.debug(f"Bot state saved for {self.symbol}.")

    async def start(self):
        """Start the market-making bot for its configured symbol"""
        logger.info(Fore.MAGENTA + f"Starting market making bot for {self.symbol}..." + Style.RESET_ALL)
        self.running = True

        # Fetch initial market data and positions, update symbol info
        await self._get_symbol_info() # Ensure symbol info is loaded
        await self.update_market_data()
        await self.update_positions()

        # Start background tasks
        self.tasks.append(asyncio.create_task(self._manage_orders()))
        self.tasks.append(asyncio.create_task(self._periodic_market_data_update()))
        self.tasks.append(asyncio.create_task(self._periodic_position_update()))
        self.tasks.append(asyncio.create_task(self._process_ws_messages())) # Unified WS message processing
        self.tasks.append(asyncio.create_task(self._save_state_periodically()))
        self.tasks.append(asyncio.create_task(self._optimize_spread_periodically()))
        self.tasks.append(asyncio.create_task(self.api_client.subscribe_bot_topics(self))) # Subscribe bot specific topics

        logger.info(f"Bot for {self.symbol} started with {len(self.open_orders)} loaded orders.")

    async def stop(self):
        """Stop the market-making bot and clean up resources."""
        if not self.running: return
        logger.info(Fore.YELLOW + f"Stopping market making bot for {self.symbol}..." + Style.RESET_ALL)
        self.running = False

        # Cancel all background tasks associated with this bot instance
        for task in self.tasks:
            if not task.done():
                task.cancel()
        # Wait for tasks to finish cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # Cancel open orders on the exchange before stopping completely
        await self.close_all_orders()

        # Save final state
        self._save_state()
        logger.info(Fore.GREEN + f"Market making bot for {self.symbol} stopped cleanly." + Style.RESET_ALL)

    async def update_market_data(self):
        """Fetch and update market data"""
        self.market_data = await self.api_client.fetch_market_data(self.symbol)
        if self.market_data:
            # Log key market data points
            logger.debug(
                f"Market Data Update [{self.symbol}]: Bid={self.market_data.best_bid}, Ask={self.market_data.best_ask}, "
                f"Spread={self.market_data.spread_bps:.4f} bps, Mid={self.market_data.mid_price}"
            )
            self.spread_optimizer.update_data(self.market_data)
        else:
            logger.warning(f"Failed to update market data for {self.symbol}")

    async def _periodic_market_data_update(self):
        """Periodically fetch market data via API polling."""
        while self.running:
            await self.update_market_data()
            await asyncio.sleep(self.config.performance_monitoring_interval // 2) # Update frequency

    async def update_positions(self):
        """Fetch and update current positions for the bot's symbol."""
        pos_list = await self.api_client.get_positions(self.symbol)
        current_pos_base = Decimal('0')
        found_position = False
        for pos in pos_list:
            if pos.get("symbol") == self.symbol and pos.get("category") == "linear": # Assuming linear perpetuals
                side = TradeSide(pos.get("side", "None"))
                size = Decimal(pos.get("size", "0"))
                avg_entry_price = Decimal(pos.get("avgPrice", "0"))
                unrealized_pnl = Decimal(pos.get("unrealisedPnl", "0"))

                self.positions[self.symbol] = {
                    "size": size, "side": side, "avg_entry_price": avg_entry_price, "unrealized_pnl": unrealized_pnl
                }
                if side == TradeSide.BUY:
                    current_pos_base = size
                elif side == TradeSide.SELL:
                    current_pos_base = -size
                
                found_position = True
                logger.info(f"Position Update [{self.symbol}]: Side={side.value}, Size={size}, AvgEntry={avg_entry_price}, PnL={unrealized_pnl}")
                break # Assuming only one position entry per symbol/category

        if not found_position:
            self.positions[self.symbol] = {"size": Decimal('0'), "side": TradeSide.NONE, "avg_entry_price": Decimal('0'), "unrealized_pnl": Decimal('0')}
            current_pos_base = Decimal('0')
            logger.debug(f"No open position found for {self.symbol}")

        # Update risk metrics
        self.risk_metrics.current_position_base = current_pos_base
        self.risk_metrics.unrealized_pnl = self.positions.get(self.symbol, {}).get("unrealized_pnl", Decimal('0'))
        self.risk_metrics.update_equity_and_drawdown() # Recalculate equity and drawdown

    async def _periodic_position_update(self):
        """Periodically fetch positions via API polling."""
        while self.running:
            await self.update_positions()
            await asyncio.sleep(self.config.performance_monitoring_interval * 2) # Update less frequently than market data

    async def _process_ws_messages(self):
        """Process incoming WebSocket messages (order updates, fills, etc.)"""
        while self.running:
            try:
                # Get message from the shared queue managed by the API client
                message_data = await self.ws_message_queue.get() 
                message_type = message_data.get("type")
                payload = message_data.get("payload")
                
                if message_type == "order":
                    await self._handle_order_update(payload)
                elif message_type == "execution":
                    await self._handle_execution_update(payload)
                elif message_type == "ticker":
                    await self.api_client.update_market_data_from_ws(payload) # Update shared market data
                    self.spread_optimizer.update_data(self.api_client.market_data_cache[self.symbol]) # Update optimizer
                # Add handlers for other relevant WS message types (e.g., liquidation)
                else:
                    logger.debug(f"Received unhandled WS message type '{message_type}' for {self.symbol}")
                
                self.ws_message_queue.task_done()

            except asyncio.CancelledError:
                logger.debug(f"WS message processing task cancelled for {self.symbol}.")
                break
            except Exception as e:
                logger.error(f"Error processing WS message for {self.symbol}: {e}", exc_info=True)
                # Ensure task_done is called even on error to prevent queue blocking
                try: self.ws_message_queue.task_done()
                except ValueError: pass

    async def _handle_order_update(self, order_update: Dict[str, Any]):
        """Process order status updates received via WebSocket."""
        order_id = order_update.get("orderId")
        if not order_id or order_id not in self.open_orders:
            logger.warning(f"Received order update for unknown or stale order ID {order_id} on {self.symbol}")
            return

        order = self.open_orders[order_id]
        
        # Update order fields based on the received update
        new_status = OrderStatus(order_update.get("orderStatus", order.status.value))
        new_filled_qty = Decimal(order_update.get("cumExecQty", str(order.filled_qty)))
        new_avg_price = Decimal(order_update.get("avgPrice", str(order.avg_price)))
        order_pnl = Decimal(order_update.get("orderPnl", str(order.order_pnl))) # PnL specific to this update/order
        updated_time = datetime.now(timezone.utc)

        # Update risk metrics if status or fill quantity changes significantly
        pnl_change = Decimal('0')
        position_change = Decimal('0')

        if new_status != order.status:
            logger.info(f"Order {order_id} status change: {order.status.value} -> {new_status.value}")
            order.status = new_status
            
            # If order is fully filled, cancelled, rejected, or expired, remove it from active orders
            if new_status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED]:
                # Calculate realized PnL upon fill or closure
                if new_status == OrderStatus.FILLED and order.side == TradeSide.BUY:
                    pnl_change = (order.avg_price - order.price) * order.filled_qty # Simplified PnL, needs proper calculation
                elif new_status == OrderStatus.FILLED and order.side == TradeSide.SELL:
                     pnl_change = (order.price - order.avg_price) * order.filled_qty # Simplified PnL
                
                # Update realized PNL and position based on final state
                self.risk_metrics.realized_pnl += pnl_change
                if order.side == TradeSide.BUY:
                    position_change = -order.filled_qty # Buying reduces position if short, increases if long (net effect)
                else: # SELL
                    position_change = order.filled_qty # Selling reduces position if long, increases if short

                del self.open_orders[order_id]
                logger.info(f"Order {order_id} ({order.symbol} {order.side.value}) finalized ({new_status.value}). Removed from active orders.")

        # Update filled quantity and average price if they changed
        if new_filled_qty != order.filled_qty:
            logger.debug(f"Order {order_id} fill update: FilledQty={new_filled_qty}, AvgPrice={new_avg_price}")
            order.filled_qty = new_filled_qty
            order.avg_price = new_avg_price
            
            # If partially filled, update position and potentially realized PnL (though PnL is usually realized on close)
            if order.status == OrderStatus.PARTIALLY_FILLED:
                 # Recalculate position based on partial fills
                if order.side == TradeSide.BUY:
                    position_change = -order.filled_qty # Example: bought 0.01 BTC
                else: # SELL
                    position_change = order.filled_qty # Example: sold 0.01 BTC
                
                # Track PnL on partial fills if available/meaningful
                # order_pnl might reflect PnL of the specific fill event. Add it cautiously.
                if order_pnl != order.order_pnl: # If PnL changed in this update
                     pnl_change = order_pnl - order.order_pnl # Calculate change in PnL
                     order.order_pnl = order_pnl

        order.updated_at = updated_time
        
        # Update overall risk metrics if changes occurred
        if position_change != 0:
            self.risk_metrics.current_position_base += position_change
            logger.debug(f"Position adjusted by {position_change} for {order.symbol}. New position: {self.risk_metrics.current_position_base}")
            
        if pnl_change != 0:
            self.risk_metrics.realized_pnl += pnl_change
            logger.debug(f"Realized PnL updated by {pnl_change} for {order.symbol}. New PnL: {self.risk_metrics.realized_pnl}")
        
        # Update unrealized PnL based on current position and market data
        await self.update_positions() # Re-fetch positions to get latest unrealized PnL

        # Update performance metrics and ratios
        if position_change != 0 or pnl_change != 0:
             self.risk_metrics.update_equity_and_drawdown()
             self.risk_metrics.calculate_performance_ratios()

        # Log trade execution details if an order was filled or partially filled
        if order.status == OrderStatus.FILLED or (order.status == OrderStatus.PARTIALLY_FILLED and order.filled_qty > 0):
             trade_logger.info(f"{order.symbol},{order.side.value},{order.filled_qty},{order.avg_price},{order.order_pnl}")
             self.api_client.performance_monitor.record_metric('orders_filled')


    async def _handle_execution_update(self, execution_update: Dict[str, Any]):
        """Process execution/fill updates received via WebSocket."""
        # This might provide more granular detail than order updates.
        # For now, rely on order updates, but this can be expanded.
        logger.debug(f"Received execution update: {execution_update}")
        pass # Placeholder

    async def _save_state_periodically(self):
        """Periodically save the bot's state"""
        while self.running:
            await asyncio.sleep(self.config.state_save_interval)
            self._save_state()

    async def _optimize_spread_periodically(self):
        """Periodically optimize the spread based on market conditions"""
        while self.running:
            await asyncio.sleep(self.spread_optimizer.update_interval)
            if self.market_data:
                optimal_spread = self.spread_optimizer.optimize_spread(self.market_data)
                # Re-evaluate order placement if spread target changes significantly
                if abs(optimal_spread - self.spread_bps) > Decimal('0.001'): # If spread target changed by more than 0.01 bps
                    await self.rebalance_orders()
                self.spread_bps = optimal_spread # Update internal spread reference

    def _get_current_inventory(self) -> Decimal:
        """Get current inventory based on risk metrics."""
        return self.risk_metrics.current_position_base

    async def place_order(self, price: Decimal, quantity: Decimal, side: TradeSide) -> Optional[OrderData]:
        """
        Place a single order, respecting risk limits, symbol rules, and avoiding duplicates.
        Returns the created OrderData object or None on failure.
        """
        if not self.running: return None
        if not self.market_data:
            logger.warning(f"Cannot place order for {self.symbol}: Market data unavailable.")
            return None

        # Quantize price and quantity based on symbol info
        quantized_price = self._quantize_price(price)
        quantized_quantity = self._quantize_quantity(quantity)

        if quantized_quantity <= 0:
            logger.warning(f"Order quantity for {self.symbol} is zero or invalid after quantization ({quantity} -> {quantized_quantity}). Skipping order.")
            return None

        # Check against symbol's minimum quantity again after quantization
        min_qty = self._get_symbol_info().get('min_qty', Decimal('0.001'))
        if quantized_quantity < min_qty:
            logger.warning(f"Quantized order quantity {quantized_quantity} is still below minimum {min_qty} for {self.symbol}.")
            return None
        
        # Check maximum position limit before placing order
        proposed_position = self.risk_metrics.current_position_base + (quantized_quantity if side == TradeSide.BUY else -quantized_quantity)
        if abs(proposed_position) > self.risk_metrics.max_position_base:
            logger.warning(f"Order placement blocked for {self.symbol}: Exceeds max position limit ({self.risk_metrics.max_position_base}). Proposed: {proposed_position}")
            return None

        # Check if an order at this exact price and side already exists and is active
        existing_order = self.find_open_order(quantized_price, side)
        if existing_order:
            logger.debug(f"Order already exists at {quantized_price} for {side.value} on {self.symbol}. Skipping placement.")
            # Optionally, check if quantity needs adjustment or replace if needed
            return existing_order

        # Determine if order should be reduce-only based on inventory target
        reduce_only = False
        current_inventory = self._get_current_inventory()
        inventory_buffer = self.base_qty_initial * Decimal('0.5') # Buffer to avoid excessive toggling

        if side == TradeSide.BUY and current_inventory > self.inventory_target_base + inventory_buffer:
            reduce_only = True
        elif side == TradeSide.SELL and current_inventory < self.inventory_target_base - inventory_buffer:
            reduce_only = True

        # Place the order using the API client
        try:
            logger.info(f"Placing {side.value} order [{self.symbol}]: Price={quantized_price}, Qty={quantized_quantity}, ReduceOnly={reduce_only}")
            response = await self.api_client.create_order(
                symbol=self.symbol, side=side, order_type="Limit",
                qty=quantized_quantity, price=quantized_price,
                time_in_force="GTC", reduce_only=reduce_only, post_only=True # Default post_only for MM
            )

            if response and response.get("retCode") == 0:
                order_data = response.get("data", {})
                new_order = OrderData(
                    order_id=str(order_data.get("orderId")), symbol=self.symbol, side=side,
                    price=quantized_price, quantity=quantized_quantity, status=OrderStatus.NEW,
                    timestamp=time.time(), type="Limit", reduce_only=reduce_only, post_only=True,
                    client_order_id=order_data.get("orderLinkId"), # Bybit uses orderLinkId as clOrdID
                    created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)
                )
                self.open_orders[new_order.order_id] = new_order
                self.api_client.performance_monitor.record_metric('orders_placed')
                logger.info(Fore.CYAN + f"Successfully placed order [{self.symbol}]: {new_order.order_id} @ {quantized_price} | Qty: {quantized_quantity}" + Style.RESET_ALL)
                return new_order
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to place {side.value} order [{self.symbol}] @ {quantized_price}: {error_msg} (Code: {response.get('retCode')})")
                # Handle specific Bybit errors if necessary (e.g., invalid parameters)
                if response.get("retCode") in ["30031", "30032", "30033", "30034"]: # Quantity related errors
                     raise InvalidOrderParameterError(f"Order parameter issue: {error_msg}", code=str(response.get('retCode')), response=response)
                elif response.get("retCode") == "30027": # Price related errors
                     raise InvalidOrderParameterError(f"Order price issue: {error_msg}", code=str(response.get('retCode')), response=response)
                return None
        except InvalidOrderParameterError as e:
            logger.error(f"Order placement failed due to invalid parameters for {self.symbol}: {e}")
            # Potentially adjust strategy parameters or skip placing orders at this price
            return None
        except Exception as e:
            logger.error(f"Unexpected error placing order [{self.symbol}] @ {quantized_price}: {e}", exc_info=True)
            return None

    def find_open_order(self, price: Decimal, side: TradeSide) -> Optional[OrderData]:
        """Find an existing active order by price and side."""
        for order in self.open_orders.values():
            if order.price == price and order.side == side and order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                return order
        return None

    async def cancel_orders(self, orders_to_cancel: List[OrderData]):
        """Cancel a list of orders asynchronously."""
        if not orders_to_cancel:
            return
        
        logger.info(f"Requesting cancellation for {len(orders_to_cancel)} orders on {self.symbol}...")
        tasks = [self.api_client.cancel_order(self.symbol, order_id=order.order_id) for order in orders_to_cancel]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            order_id = orders_to_cancel[i].order_id
            if isinstance(result, Exception):
                logger.error(f"Exception during cancellation of order {order_id} [{self.symbol}]: {result}")
            elif result and result.get("retCode") == 0:
                logger.info(f"Successfully requested cancellation for order {order_id} [{self.symbol}].")
                # Order status update will be handled by _handle_order_update or polling
            else:
                logger.warning(f"Failed to cancel order {order_id} [{self.symbol}]: {result.get('retMsg', 'No response') if result else 'No response'}")

    async def close_all_orders(self):
        """Cancel all currently open orders managed by this bot instance."""
        if not self.open_orders:
            return
        
        orders_to_cancel = list(self.open_orders.values())
        await self.cancel_orders(orders_to_cancel)
        # Clear local state immediately; WS updates will confirm cancellations later
        self.open_orders.clear()

    async def rebalance_orders(self):
        """
        Rebalance the order book: cancel existing orders and place new ones
        based on current market data, spread target, and inventory levels.
        """
        if not self.running or not self.market_data:
            logger.warning(f"Cannot rebalance orders for {self.symbol}: Bot not running or market data unavailable.")
            return

        logger.info(Fore.CYAN + f"Rebalancing orders for {self.symbol}..." + Style.RESET_ALL)

        # Get current target spread and mid-price
        target_spread = self.spread_optimizer.target_spread_bps
        mid_price = self.market_data.mid_price
        if mid_price <= 0:
            logger.warning(f"Cannot rebalance orders for {self.symbol}: Invalid mid-price ({mid_price}).")
            return

        # Calculate price levels for buy and sell orders
        buy_price = mid_price - (mid_price * target_spread / Decimal('10000'))
        sell_price = mid_price + (mid_price * target_spread / Decimal('10000'))

        # Quantize prices
        quantized_buy_price = self._quantize_price(buy_price)
        quantized_sell_price = self._quantize_price(sell_price)

        # Determine quantity for new orders
        current_inventory = self._get_current_inventory()
        inventory_diff = self.inventory_target_base - current_inventory
        
        # Adjust quantity based on deviation from inventory target
        adjusted_qty = self.base_qty_initial
        inventory_buffer = self.base_qty_initial * Decimal('0.5')
        if abs(inventory_diff) > self.base_qty_initial + inventory_buffer:
            adjusted_qty *= Decimal('1.2') # Increase quantity slightly if inventory deviates significantly

        final_quantity = self._quantize_quantity(adjusted_qty)
        if final_quantity <= 0:
             logger.warning(f"Calculated order quantity is zero or invalid for {self.symbol} during rebalance. Skipping order placement.")
             final_quantity = self.base_qty_initial # Fallback to initial qty if calculation fails

        # --- Place new orders ---
        new_buy_order = await self.place_order(quantized_buy_price, final_quantity, TradeSide.BUY)
        new_sell_order = await self.place_order(quantized_sell_price, final_quantity, TradeSide.SELL)

        # --- Identify orders to cancel ---
        orders_to_cancel = []
        for order_id, order in list(self.open_orders.items()): # Iterate over copy for safe deletion
            if order.symbol == self.symbol:
                is_active = order.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]
                
                # Determine if the order should be kept or cancelled
                should_keep = False
                if order.side == TradeSide.BUY and order.price == quantized_buy_price and is_active:
                    # Check if quantity matches and update if necessary (e.g., if adjusted_qty changed)
                    if order.quantity != final_quantity:
                         # Optional: Cancel and replace with correct quantity
                         logger.warning(f"Order {order_id} quantity mismatch ({order.quantity} vs {final_quantity}). Consider replacing.")
                    should_keep = True
                elif order.side == TradeSide.SELL and order.price == quantized_sell_price and is_active:
                    if order.quantity != final_quantity:
                        logger.warning(f"Order {order_id} quantity mismatch ({order.quantity} vs {final_quantity}). Consider replacing.")
                    should_keep = True
                
                # If the order is not active or doesn't match the new parameters, mark for cancellation
                if not should_keep:
                    orders_to_cancel.append(order)
                    # Remove from local state immediately if inactive
                    if order_id in self.open_orders and not is_active:
                        del self.open_orders[order_id]
                        logger.debug(f"Removed inactive order {order_id} from state before cancellation.")

        # Execute cancellations
        if orders_to_cancel:
            await self.cancel_orders(orders_to_cancel)

        logger.info(Fore.GREEN + f"Order rebalancing complete for {self.symbol}. Active orders: {len(self.open_orders)}." + Style.RESET_ALL)

    async def _manage_orders(self):
        """Main loop for managing orders: reconciling state, rebalancing."""
        while self.running:
            try:
                # Reconcile open orders with the exchange state periodically
                await self.reconcile_orders()

                # Rebalance orders if market conditions (price, spread) have changed significantly
                if self.market_data:
                    # Check price movement threshold
                    price_change_threshold = self.market_data.mid_price * Decimal('0.001') # 0.1% change
                    # Check spread target change threshold
                    spread_change_threshold = self.spread_optimizer.target_spread_bps * Decimal('0.1') # 10% change
                    
                    current_spread_bps = self.market_data.spread_bps
                    
                    if abs(self.market_data.mid_price - self.market_data.last_price) > price_change_threshold or \
                       abs(current_spread_bps - self.spread_optimizer.target_spread_bps) > spread_change_threshold:
                        await self.rebalance_orders()
                
                # Wait before next management cycle
                await asyncio.sleep(5) # Check orders every 5 seconds

            except asyncio.CancelledError:
                logger.debug(f"Order management task cancelled for {self.symbol}.")
                break
            except Exception as e:
                logger.error(f"Error in order management loop for {self.symbol}: {e}", exc_info=True)
                await asyncio.sleep(10) # Wait before retrying after an error

    async def reconcile_orders(self):
        """Sync the bot's internal order state with the actual open orders on the exchange."""
        if not self.running: return

        try:
            # Fetch currently open orders from the exchange
            exchange_open_orders = await self.api_client.get_open_orders(self.symbol)
            
            current_order_ids = set(self.open_orders.keys())
            exchange_order_ids = set()
            
            # Process orders returned from the exchange
            for order_api_data in exchange_open_orders:
                try:
                    order = OrderData.from_api(order_api_data)
                    exchange_order_ids.add(order.order_id)
                    
                    if order.order_id not in self.open_orders:
                        # Order exists on exchange but not locally; add it
                        self.open_orders[order.order_id] = order
                        logger.info(f"Detected externally opened order {order.order_id} [{self.symbol}]. Added to state.")
                    else:
                        # Order exists locally; update its state if changed on exchange
                        local_order = self.open_orders[order.order_id]
                        # Update fields that might change (status, filled qty, avg price, PnL)
                        local_order.status = order.status
                        local_order.filled_qty = order.filled_qty
                        local_order.avg_price = order.avg_price
                        local_order.order_pnl = order.order_pnl # Update PnL if available
                        local_order.updated_at = datetime.now(timezone.utc)
                        
                        # Handle order finalization (filled, cancelled, etc.)
                        if order.status not in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]:
                            if order.order_id in self.open_orders:
                                del self.open_orders[order.order_id]
                                logger.info(f"Order {order.order_id} [{self.symbol}] finalized ({order.status.value}). Removed from state.")
                                # Update risk metrics based on final state (handled in _handle_order_update)

                except Exception as e:
                    logger.error(f"Error processing order data during reconciliation for {self.symbol}: {order_api_data} - {e}")

            # Identify orders that are local but no longer on the exchange (cancelled externally)
            stale_order_ids = current_order_ids - exchange_order_ids
            for order_id in stale_order_ids:
                if order_id in self.open_orders:
                    logger.warning(f"Order {order_id} [{self.symbol}] is no longer open on exchange. Removing from local state.")
                    # Optionally, try to determine the final status if possible (e.g., cancelled)
                    del self.open_orders[order_id]

            # Update risk metrics after reconciliation, especially if positions changed implicitly
            await self.update_positions() # Ensure position data is current
            self.risk_metrics.calculate_performance_ratios() # Recalculate ratios

        except Exception as e:
            logger.error(f"Error during order reconciliation for {self.symbol}: {e}", exc_info=True)


# --- Enhanced API Client ---
class EnhancedAPIClient:
    """
    Advanced API client with connection pooling, circuit breaker, rate limiting,
    WebSocket handling, and enhanced performance monitoring.
    Manages multiple bot instances for WebSocket message routing.
    """
    def __init__(self, config: BotConfig):
        self.config = config
        self.base_url = BASE_URL
        self.ws_private_url = WS_PRIVATE_URL # URL for authenticated private streams
        self.session = None
        self.ws_connection = None
        self.ws_authenticated = False
        
        # Rate Limiter instance based on configuration
        self.rate_limiter = RateLimiter(
            limits=config.rate_limits,
            default_limit=config.rate_limit_default,
            burst_allowance_factor=config.rate_limit_burst_factor
        )
        # Circuit Breaker instance
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
            expected_exceptions=config.circuit_breaker_exceptions
        )
        self.performance_monitor = PerformanceMonitor()
        self.request_id_counter = 0
        self.request_id_lock = asyncio.Lock()
        self.symbol_info_cache = {} # Cache for symbol specific details
        self.market_data_cache = {} # Cache for market data per symbol
        self.bot_instances: Dict[str, MarketMakingBot] = {} # Map symbol -> bot instance for WS routing
        self._ws_reconnect_task = None # Task handle for WebSocket reconnection

    def register_bot_instance(self, bot: MarketMakingBot):
        """Register a bot instance to receive WebSocket messages for its symbol."""
        self.bot_instances[bot.symbol] = bot
        # Update shared market data cache if needed
        if bot.symbol not in self.market_data_cache:
             self.market_data_cache[bot.symbol] = MarketData(symbol=bot.symbol, best_bid=Decimal('0'), best_ask=Decimal('0'), bid_size=Decimal('0'), ask_size=Decimal('0'), timestamp=0)

    async def _get_next_request_id(self) -> int:
        """Generate a unique sequential request ID."""
        async with self.request_id_lock:
            self.request_id_counter += 1
            return self.request_id_counter

    async def __aenter__(self):
        """Initialize session and start WebSocket connection."""
        connector = aiohttp.TCPConnector(
            limit=self.config.api_connection_limit,
            limit_per_host=self.config.api_connection_limit_per_host,
            keepalive_timeout=self.config.api_keepalive_timeout,
            enable_cleanup_closed=True, force_close=True
        )
        timeout = aiohttp.ClientTimeout(
            total=self.config.api_timeout_total, connect=self.config.api_timeout_connect,
            sock_connect=self.config.api_timeout_connect, sock_read=self.config.api_timeout_sock_read
        )
        self.session = aiohttp.ClientSession(
            connector=connector, timeout=timeout,
            headers={'User-Agent': 'BybitMarketMaker/3.1', 'Content-Type': 'application/json'},
        )
        await self._connect_ws()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close WebSocket and session."""
        if self._ws_reconnect_task:
            self._ws_reconnect_task.cancel()
        if self.ws_connection:
            try: await self.ws_connection.close()
            except Exception as e: logger.error(f"Error closing WebSocket: {e}")
        if self.session:
            await self.session.close()
            logger.info("aiohttp session closed.")
            await asyncio.sleep(0.5) # Allow connections to close gracefully

    async def _connect_ws(self):
        """Establish WebSocket connection with reconnection logic."""
        if self._ws_reconnect_task and not self._ws_reconnect_task.done():
            return # Reconnection already in progress

        async def reconnect_logic():
            while True:
                try:
                    logger.info(f"Attempting WebSocket connection to {self.ws_private_url}...")
                    self.ws_connection = await websockets.connect(
                        self.ws_private_url,
                        ping_interval=self.config.ws_ping_interval,
                        ping_timeout=self.config.ws_pong_timeout,
                        open_timeout=self.config.api_timeout_connect,
                        close_timeout=self.config.api_timeout_connect
                    )
                    logger.info(Fore.GREEN + "WebSocket connection established." + Style.RESET_ALL)
                    self.ws_authenticated = False
                    await self._authenticate_ws()
                    await self._subscribe_all_bot_topics() # Subscribe after auth
                    
                    # Start listening task after successful connection and auth
                    asyncio.create_task(self._listen_ws())
                    break # Exit retry loop on success
                
                except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK,
                        aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
                    logger.error(f"WebSocket connection failed: {e}. Retrying in 10 seconds...")
                    self.ws_connection = None
                    self.ws_authenticated = False
                    await asyncio.sleep(10)
        
        self._ws_reconnect_task = asyncio.create_task(reconnect_logic())

    async def _authenticate_ws(self):
        """Authenticate WebSocket connection."""
        if not self.ws_connection or self.ws_connection.closed: return
        
        expires = str(int((time.time() + 60) * 1000)) # Expires in 60s
        signature_str = f"{expires}GET/realtime"
        signature = hmac.new(self.config.api_secret.encode('utf-8'), signature_str.encode('utf-8'), hashlib.sha256).hexdigest()
        
        auth_message = {"op": "auth", "args": [self.config.api_key, expires, signature]}
        try:
            await self.ws_connection.send(json.dumps(auth_message))
            logger.debug("Sent WebSocket authentication message.")
        except Exception as e:
            logger.error(f"Failed to send WebSocket authentication message: {e}")

    async def _listen_ws(self):
        """Listen for messages from WebSocket."""
        while self.ws_connection and not self.ws_connection.closed:
            try:
                message = await self.ws_connection.recv()
                self.performance_monitor.record_metric('ws_messages')
                await self._process_ws_message(message)
            except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.ConnectionClosedOK) as e:
                logger.warning(f"WebSocket connection closed: {e}. Attempting to reconnect...")
                self.ws_connection = None
                self.ws_authenticated = False
                await self._connect_ws() # Trigger reconnection
                break # Exit loop, reconnection task will handle it
            except asyncio.TimeoutError:
                logger.warning("WebSocket receive timed out. Checking connection status.")
                # Optionally send ping if timeout occurs repeatedly
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}", exc_info=True)
                # Consider reconnecting on unexpected errors
                logger.warning("Attempting WebSocket reconnection due to processing error.")
                self.ws_connection = None
                self.ws_authenticated = False
                await self._connect_ws()
                break

    async def _process_ws_message(self, message: str):
        """Process incoming WebSocket messages and route them to relevant bots."""
        try:
            data = json.loads(message)
            op = data.get("op")
            event = data.get("event")

            if op == "auth":
                if data.get("success"):
                    logger.info(Fore.GREEN + "WebSocket authenticated successfully." + Style.RESET_ALL)
                    self.ws_authenticated = True
                else:
                    logger.error(f"WebSocket authentication failed: {data.get('retMsg')}")
            elif event == "pong":
                logger.debug("Received WebSocket pong.")
            elif event == "subscribe":
                logger.info(f"WebSocket subscription confirmation: {data.get('topic')} - Success: {data.get('success')}")
            elif op == "hello": # Handle initial hello message if needed
                 logger.debug(f"Received WS hello message: {data}")
            else:
                # Route message to the correct bot instance based on topic or symbol
                topic = data.get("topic")
                payload = data.get("data", {})

                if topic:
                    # Extract symbol from topic (e.g., "order.BTCUSDT")
                    symbol = None
                    if '.' in topic:
                        parts = topic.split('.')
                        if len(parts) > 1 and parts[0] in ["order", "execution", "tickers", "kline"]:
                             symbol = parts[1] # Assume symbol is the second part

                    if symbol and symbol in self.bot_instances:
                        bot = self.bot_instances[symbol]
                        message_type = None
                        if topic.startswith("order"): message_type = "order"
                        elif topic.startswith("execution"): message_type = "execution"
                        elif topic.startswith("tickers"): message_type = "ticker"
                        
                        if message_type:
                             # Put message into the bot's specific queue
                             await bot.ws_message_queue.put({"type": message_type, "payload": payload[0] if isinstance(payload, list) and payload else payload})
                        else:
                             logger.debug(f"Unhandled topic format: {topic}")
                    else:
                        logger.debug(f"Received message for unknown or unmanaged symbol '{symbol}' via topic '{topic}'")
                else:
                    logger.debug(f"Received WS message without topic: {data}")

        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON message: {message}")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

    async def subscribe_bot_topics(self, bot: MarketMakingBot):
        """Subscribe to topics relevant to a specific bot instance."""
        if not self.ws_connection or self.ws_connection.closed or not self.ws_authenticated:
            logger.warning(f"Cannot subscribe to topics for {bot.symbol}: WebSocket not ready or authenticated.")
            return

        topics_to_subscribe = []
        # Add order and execution updates for the bot's symbol
        topics_to_subscribe.extend([f"order.{bot.symbol}", f"execution.{bot.symbol}"])
        
        # Add tickers if not already subscribed by another bot (or manage subscriptions centrally)
        # For simplicity, let's subscribe tickers for all managed symbols if they aren't already
        # A more robust solution would track active subscriptions.
        if f"tickers.{bot.symbol}" not in self.subscribed_topics: # Assuming self.subscribed_topics exists
             topics_to_subscribe.append(f"tickers.{bot.symbol}")

        if not topics_to_subscribe: return

        subscribe_message = {"op": "subscribe", "args": topics_to_subscribe}
        try:
            await self.ws_connection.send(json.dumps(subscribe_message))
            logger.info(f"Sent subscription request for {bot.symbol}: {topics_to_subscribe}")
            # Add subscribed topics to tracking set
            if not hasattr(self, 'subscribed_topics'): self.subscribed_topics = set()
            self.subscribed_topics.update(topics_to_subscribe)

        except Exception as e:
            logger.error(f"Failed to send WebSocket subscription message for {bot.symbol}: {e}")

    async def _subscribe_all_bot_topics(self):
        """Subscribe to all necessary topics for all registered bots."""
        if not self.ws_connection or self.ws_connection.closed or not self.ws_authenticated:
            logger.warning("Cannot subscribe to all topics: WebSocket not ready or authenticated.")
            return

        all_topics = set()
        for bot in self.bot_instances.values():
            all_topics.add(f"order.{bot.symbol}")
            all_topics.add(f"execution.{bot.symbol}")
            all_topics.add(f"tickers.{bot.symbol}") # Subscribe tickers for all managed symbols
            # Add other topics like kline if needed

        if not all_topics:
            logger.info("No topics to subscribe to.")
            return
            
        subscribe_message = {"op": "subscribe", "args": sorted(list(all_topics))}
        try:
            await self.ws_connection.send(json.dumps(subscribe_message))
            logger.info(f"Sent subscription request for all topics: {subscribe_message['args']}")
            self.subscribed_topics = all_topics # Update tracked subscriptions
        except Exception as e:
            logger.error(f"Failed to send WebSocket subscription message for all topics: {e}")

    async def _ensure_ws_connected_and_subscribed(self):
        """Ensure WebSocket is connected, authenticated, and subscribed."""
        if not self.ws_connection or self.ws_connection.closed or not self.ws_authenticated:
            await self._connect_ws() # Attempt reconnection
            if not self.ws_connection or self.ws_connection.closed or not self.ws_authenticated:
                raise ConnectionError("WebSocket is not connected or authenticated.")
            # Re-subscribe if authentication just succeeded
            await self._subscribe_all_bot_topics()
        elif not hasattr(self, 'subscribed_topics') or len(self.subscribed_topics) < len(self.bot_instances)*3: # Heuristic check if subscriptions might be missing
             logger.warning("WebSocket connection might be missing subscriptions. Re-subscribing.")
             await self._subscribe_all_bot_topics()


    # --- API Request Methods ---
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, signed: bool = True, is_ws: bool = False) -> Dict:
        """Make API requests with rate limiting, circuit breaking, and error handling."""
        if is_ws: raise NotImplementedError("Use WebSocket methods directly.")
        if not self.session or self.session.closed:
            raise ConnectionError("API session is not available or closed.")

        await self._ensure_ws_connected_and_subscribed() # Ensure WS is ready for potential fallback logic
        
        # Apply rate limiting before making the request
        await self.rate_limiter.acquire(endpoint)

        url = self.base_url + endpoint
        headers = {
            'X-BAPI-API-KEY': self.config.api_key,
            'X-BAPI-TIMESTAMP': str(int(time.time() * 1000)),
            'X-BAPI-RECV-WINDOW': '5000', # Standard receive window
            'X-BAPI-SIGN': ''
        }
        
        query_params_str = "" # String for signing GET requests
        request_body = None   # Body for POST/PUT requests

        # Prepare parameters and signing string
        request_params = params.copy() if params else {}
        if signed:
            recv_window = headers['X-BAPI-RECV-WINDOW']
            timestamp = headers['X-BAPI-TIMESTAMP']
            
            if method.upper() == 'GET':
                query_params_sorted = sorted(request_params.items())
                query_params_str = urllib.parse.urlencode(query_params_sorted)
                url = f"{url}?{query_params_str}"
            else: # POST, PUT, etc.
                # Sort keys for consistent signing of JSON bodies
                sorted_params = dict(sorted(request_params.items()))
                query_params_str = urllib.parse.urlencode(sorted_params) # Use params for signing string even if sent as JSON body
                request_body = sorted_params # Send sorted params as JSON body

            headers['X-BAPI-SIGN'] = self._generate_signature(timestamp, recv_window, query_params_str)

        # Add request ID for tracing
        req_id = await self._get_next_request_id()
        headers['X-BAPI-REQUEST-ID'] = str(req_id)

        # Use circuit breaker for the request execution
        start_time = time.time()
        try:
            async with self.circuit_breaker:
                async with self.session.request(method, url, headers=headers, json=request_body, params=request_params if method.upper() == 'GET' else None) as response:
                    elapsed_time = time.time() - start_time
                    self.performance_monitor.record_latency('order', elapsed_time)
                    
                    try:
                        result = await response.json()
                        ret_code = result.get("retCode")
                        ret_msg = result.get("retMsg", f"HTTP Status: {response.status}")

                        # Check for API-level errors or HTTP status errors
                        if response.status != 200 or ret_code != 0:
                            error_details = f"API Error ({endpoint}): {ret_msg} | Code: {ret_code} | Status: {response.status} | ReqID: {req_id}"
                            logger.error(error_details)
                            self.performance_monitor.record_api_call(endpoint, False)

                            # Raise specific exceptions based on Bybit error codes or HTTP status
                            if ret_code in ["30027", "30028", "30029", "30030", "10009"] or response.status >= 500:
                                raise BybitAPIError(ret_msg, code=str(ret_code), response=result)
                            elif ret_code == "-1003": # Rate limit exceeded
                                raise RateLimitExceededError(ret_msg, code=str(ret_code), response=result)
                            elif ret_code == "30031" or ret_code == "30032" or ret_code == "30033" or ret_code == "30034" or ret_code == "30027": # Quantity/Price validation errors
                                raise InvalidOrderParameterError(ret_msg, code=str(ret_code), response=result)
                            else: # Generic API error
                                raise BybitAPIError(ret_msg, code=str(ret_code), response=result)
                        else:
                            # Success
                            logger.debug(f"API Success ({endpoint}): ReqID={req_id}, RespCode={ret_code}")
                            self.performance_monitor.record_api_call(endpoint, True)
                            return result
                            
                    except aiohttp.ContentTypeError:
                        logger.error(f"API Error ({endpoint}): Invalid content type. Status: {response.status}, ReqID: {req_id}")
                        self.performance_monitor.record_api_call(endpoint, False)
                        raise BybitAPIError("Invalid content type received", response=None)
                    except json.JSONDecodeError:
                        logger.error(f"API Error ({endpoint}): Failed to decode JSON response. Status: {response.status}, ReqID: {req_id}")
                        self.performance_monitor.record_api_call(endpoint, False)
                        raise BybitAPIError("JSON decode error", response=None)

        except CircuitBreakerOpenError as e:
            self.performance_monitor.record_api_call(endpoint, False)
            logger.warning(f"API Call Blocked ({endpoint}): {e}")
            raise # Re-raise to be caught by caller or handled by CB exit logic
        except (RateLimitExceededError, InvalidOrderParameterError, BybitAPIError, ConnectionError, asyncio.TimeoutError) as e:
            # Exceptions expected to be handled or trigger CB state change
            self.performance_monitor.record_api_call(endpoint, False)
            raise # Re-raise the specific exception
        except Exception as e:
            # Catch-all for unexpected errors during request execution
            self.performance_monitor.record_api_call(endpoint, False)
            logger.error(f"Unexpected error during API request ({endpoint}): {e}", exc_info=True)
            raise BybitAPIError(f"Unexpected error: {e}")

    def _generate_signature(self, timestamp: str, recv_window: str, params_str: str) -> str:
        """Generate Bybit v5 API signature."""
        param_str_for_signing = f"{timestamp}{self.config.api_key}{recv_window}{params_str}"
        return hmac.new(self.config.api_secret.encode('utf-8'), param_str_for_signing.encode('utf-8'), hashlib.sha256).hexdigest()

    @lru_cache(maxsize=128) # Cache symbol endpoint categories
    def _get_endpoint_category(self, endpoint: str) -> str:
        """Categorize endpoint for rate limiting."""
        if endpoint.startswith('/v5/order'): return '/v5/order'
        if endpoint.startswith('/v5/position'): return '/v5/position'
        if endpoint.startswith('/v5/account'): return '/v5/account'
        if endpoint.startswith('/v5/market'): return '/v5/market'
        if endpoint.startswith('/v5/user'): return '/v5/user'
        return 'default'

    # --- Public API Methods ---
    async def get_server_time(self) -> Dict:
        """Get Bybit server time."""
        try:
            return await self._request("GET", "/v5/time", signed=False)
        except Exception as e:
            logger.error(f"Failed to get server time: {e}")
            return {"retCode": -1, "retMsg": str(e)}

    async def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get detailed information about a trading symbol, with caching."""
        if symbol in self.symbol_info_cache and (time.time() - self.symbol_info_cache[symbol]['timestamp'] < 60): # Cache for 60s
            return self.symbol_info_cache[symbol]['data']

        params = {"category": "linear", "symbol": symbol}
        try:
            response = await self._request("GET", "/v5/market/symbol", params, signed=False)
            if response and response.get("retCode") == 0 and response.get("data", {}).get("list"):
                symbol_data = response["data"]["list"][0]
                # Extract and structure relevant info
                info = {
                    "symbol": symbol_data.get("symbol"),
                    "tick_size": Decimal(symbol_data.get("priceFilter", {}).get("tickSize", "0.01")),
                    "lot_size_step": Decimal(symbol_data.get("lotSizeFilter", {}).get("qtyStep", "0.001")),
                    "min_qty": Decimal(symbol_data.get("lotSizeFilter", {}).get("minQty", "0.001")),
                    "base_coin": symbol_data.get("baseCoin"),
                    "quote_coin": symbol_data.get("quoteCoin"),
                    "price_scale": int(symbol_data.get("priceScale", 6)),
                    "timestamp": time.time() # Store cache timestamp
                }
                self.symbol_info_cache[symbol] = {'data': info, 'timestamp': time.time()}
                logger.debug(f"Cached symbol info for {symbol}: {info}")
                return info
            else:
                logger.warning(f"Could not retrieve symbol info for {symbol}: {response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching symbol info for {symbol}: {e}")
            return None

    async def fetch_market_data(self, symbol: str) -> Optional[MarketData]:
        """Fetch and parse market data (ticker) for a given symbol."""
        # Check cache first
        if symbol in self.market_data_cache and (time.time() - self.market_data_cache[symbol].timestamp < 5): # Cache for 5s
            return self.market_data_cache[symbol]

        params = {"category": "linear", "symbol": symbol}
        try:
            response = await self._request("GET", "/v5/market/tickers", params, signed=False)
            if response and response.get("retCode") == 0 and response.get("data", {}).get("list"):
                ticker_info = response["data"]["list"][0]
                market_data = MarketData(symbol=symbol, best_bid=Decimal('0'), best_ask=Decimal('0'), bid_size=Decimal('0'), ask_size=Decimal('0'), timestamp=0)
                market_data.update_from_tick(ticker_info)
                self.market_data_cache[symbol] = market_data # Update cache
                return market_data
            else:
                logger.warning(f"Could not fetch ticker data for {symbol}: {response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol}: {e}")
            return None

    async def update_market_data_from_ws(self, tick_data: Dict[str, Any]):
        """Update market data directly from WebSocket ticker message."""
        symbol = tick_data.get("symbol")
        if symbol:
            if symbol not in self.market_data_cache:
                 self.market_data_cache[symbol] = MarketData(symbol=symbol, best_bid=Decimal('0'), best_ask=Decimal('0'), bid_size=Decimal('0'), ask_size=Decimal('0'), timestamp=0)
            
            self.market_data_cache[symbol].update_from_tick(tick_data)
            logger.debug(f"Market Data Updated (WS) [{symbol}]: Bid={self.market_data_cache[symbol].best_bid}, Ask={self.market_data_cache[symbol].best_ask}, Spread={self.market_data_cache[symbol].spread_bps:.4f} bps")

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict:
        """Get wallet balance for a specific account type."""
        params = {"accountType": account_type}
        try:
            return await self._request("GET", "/v5/account/wallet/balance", params)
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            return {"retCode": -1, "retMsg": str(e)}

    async def create_order(self, symbol: str, side: TradeSide, order_type: str, qty: Decimal, price: Optional[Decimal] = None, time_in_force: str = "GTC", reduce_only: bool = False, mmp: bool = False, post_only: bool = False) -> Dict:
        """Create a new order with Bybit v5 API."""
        params = {
            "category": "linear", "symbol": symbol, "side": side.value, "orderType": order_type,
            "qty": str(qty), "timeInForce": time_in_force, "reduceOnly": reduce_only,
            "mmp": mmp, "positionIdx": 0, "triggerBy": "LastPrice", # Assuming default values
            "orderIv": str(uuid.uuid4()), "orderFilter": "Normal", # Required fields
            "clOrdID": str(uuid.uuid4()) # Client Order ID for idempotency
        }

        # Add price and other fields based on order type
        if order_type == "Limit":
            if price is None: raise ValueError("Price must be provided for Limit orders.")
            params["price"] = str(price)
            params["postOnly"] = post_only
        elif order_type == "Market":
            params["price"] = "0" # Price is not required/used for Market orders
            params["postOnly"] = False # Cannot be postOnly
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

        # Add baseCoin and quoteCoin (required for limit/market orders in v5)
        symbol_info = await self.get_symbol_info(symbol)
        if not symbol_info:
            raise ValueError(f"Cannot create order: Symbol info unavailable for {symbol}")
        params["baseCoin"] = symbol_info.get("base_coin")
        params["quoteCoin"] = symbol_info.get("quote_coin")

        logger.debug(f"Create Order Params: {params}")
        try:
            response = await self._request("POST", "/v5/order/create", params)
            if response and response.get("retCode") == 0:
                self.performance_monitor.record_metric('orders_placed')
            return response
        except (InvalidOrderParameterError, BybitAPIError) as e:
            logger.error(f"Order creation failed for {symbol} {side.value} {qty}@{price}: {e}")
            self.performance_monitor.record_metric('orders_rejected')
            raise # Re-raise to be handled by caller
        except Exception as e:
            logger.error(f"Unexpected error during order creation for {symbol}: {e}")
            raise

    async def cancel_order(self, symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict:
        """Cancel an order by order ID or client order ID."""
        if not order_id and not client_order_id:
            raise ValueError("Must provide either order_id or client_order_id to cancel order.")

        params = {"category": "linear", "symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["orderFilter"] = "ByClient" # Required for client order ID cancellation
            params["clOrdID"] = client_order_id

        logger.debug(f"Cancel Order Params: {params}")
        try:
            response = await self._request("POST", "/v5/order/cancel", params)
            if response and response.get("retCode") == 0:
                self.performance_monitor.record_metric('orders_cancelled')
            return response
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id or client_order_id} for {symbol}: {e}")
            raise

    async def get_open_orders(self, symbol: str) -> List[OrderData]:
        """Get a list of open orders (New, PartiallyFilled) for a given symbol."""
        params = {
            "category": "linear", "symbol": symbol,
            "orderStatus": "New,PartiallyFilled", "limit": 50 # Fetch active orders
        }
        try:
            response = await self._request("GET", "/v5/order/realtime", params)
            open_orders = []
            if response and response.get("retCode") == 0 and response.get("data", {}).get("list"):
                for order_data in response["data"]["list"]:
                    try:
                        open_orders.append(OrderData.from_api(order_data))
                    except Exception as e:
                        logger.error(f"Error parsing order data from get_open_orders for {symbol}: {order_data} - {e}")
                logger.info(f"Fetched {len(open_orders)} open orders for {symbol}.")
            else:
                logger.warning(f"No open orders found or error fetching for {symbol}: {response.get('retMsg')}")
            return open_orders
        except Exception as e:
            logger.error(f"Error getting open orders for {symbol}: {e}")
            return []

    async def get_positions(self, symbol: str) -> List[Dict]:
        """Get current positions for a specific symbol."""
        params = {"category": "linear", "symbol": symbol}
        try:
            response = await self._request("GET", "/v5/position/list", params)
            if response and response.get("retCode") == 0 and response.get("data", {}).get("list"):
                return response["data"]["list"]
            return []
        except Exception as e:
            logger.error(f"Error getting positions for {symbol}: {e}")
            return []

# --- Main Application Orchestration ---
class MarketMakingManager:
    """Manages multiple MarketMakingBot instances."""
    def __init__(self, config: BotConfig):
        self.config = config
        self.api_client = EnhancedAPIClient(config)
        self.state_manager = FileStateManager(config.state_directory)
        self.bots: Dict[str, MarketMakingBot] = {}
        self.running = False
        self.manager_tasks = []

    async def start(self):
        """Initialize and start all bots based on configuration."""
        logger.info("Starting Market Making Manager...")
        self.running = True
        
        # Start state file cleanup task
        await self.state_manager.cleanup_expired_files()

        # Start API client (initializes session and WS connection)
        async with self.api_client:
            # Create and start bots for each configured symbol
            for symbol_config in self.config.symbols:
                bot = MarketMakingBot(self.config, symbol_config, self.api_client, self.state_manager)
                self.bots[symbol_config.symbol] = bot
                await bot.start()

            logger.info(f"All bots started successfully. Managed symbols: {list(self.bots.keys())}")

            # Keep the manager running until shutdown signal
            while self.running:
                # Periodically report performance stats
                await self.report_performance()
                await asyncio.sleep(self.config.performance_monitoring_interval)

    async def stop(self):
        """Stop all managed bots and cleanup."""
        logger.info("Stopping Market Making Manager...")
        self.running = False

        # Stop all bot instances
        stop_tasks = [bot.stop() for bot in self.bots.values()]
        await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Stop API client (closes session and WS)
        if self.api_client:
            await self.api_client.__aexit__(None, None, None)

        # Cancel any remaining manager tasks
        if self.manager_tasks:
            for task in self.manager_tasks:
                 if not task.done(): task.cancel()
            await asyncio.gather(*self.manager_tasks, return_exceptions=True)

        logger.info("Market Making Manager stopped.")

    async def report_performance(self):
        """Log aggregated performance statistics."""
        total_stats = self.api_client.performance_monitor.get_stats()
        
        # Include stats from individual bots if needed (e.g., bot-specific PnL)
        bot_stats = {}
        for symbol, bot in self.bots.items():
            bot_stats[symbol] = {
                "orders_placed": bot.api_client.performance_monitor.metrics.get('orders_placed', 0),
                "orders_filled": bot.api_client.performance_monitor.metrics.get('orders_filled', 0),
                "risk_metrics": bot.risk_metrics.to_dict()
            }
        total_stats["bot_stats"] = bot_stats
        
        # Log aggregated stats
        log_entry = {
            "level": "INFO",
            "logger_name": "PerformanceMonitor",
            "event": "Aggregated Performance Stats",
            "stats": total_stats
        }
        # Use the setup logger for structured output
        logger.info(json.dumps(log_entry))


async def main():
    """Main function to load config and run the manager."""
    config = BotConfig.load_from_env()

    manager = MarketMakingManager(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            logger.warning(f"Signal handler for {sig} not supported on this platform.")

    try:
        # Start the manager (which starts bots and enters monitoring loop)
        manager_task = asyncio.create_task(manager.start())
        
        # Wait for shutdown signal
        await stop_event.wait()
        
        # Initiate manager shutdown
        await manager.stop()

    except Exception as e:
        logger.critical(f"Manager encountered critical error: {e}", exc_info=True)
        # Attempt graceful shutdown even after critical error
        if manager and manager.running:
            await manager.stop()
        # Ensure process exit code indicates failure
        sys.exit(1)
    finally:
        # Ensure loop cleanup if necessary
        pass


if __name__ == "__main__":
    # Run the main async function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user (KeyboardInterrupt).")
    except Exception as e:
        # Catch any top-level exceptions not handled within the async tasks
        logger.critical(f"Unhandled exception during execution: {e}", exc_info=True)
        try:
            os.system("termux-toast 'Critical Error: Market Making Bot Halted!'")
        except Exception: pass
        sys.exit(1)