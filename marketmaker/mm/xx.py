import asyncio
import os
import signal
import time
from decimal import Decimal

from pydantic import BaseModel, Field, PositiveFloat, PositiveInt
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


# --- Configuration Classes ---
class DynamicSpreadConfig(BaseModel):
    enabled: bool = True
    volatility_window_sec: PositiveInt = 60
    volatility_multiplier: PositiveFloat = 2.0
    min_spread_pct: PositiveFloat = 0.0005
    max_spread_pct: PositiveFloat = 0.01
    price_change_smoothing_factor: PositiveFloat = 0.2
    atr_update_interval_sec: PositiveInt = 300


class InventorySkewConfig(BaseModel):
    enabled: bool = True
    skew_intensity: PositiveFloat = 0.5
    max_inventory_ratio: PositiveFloat = 0.5
    inventory_sizing_factor: PositiveFloat = 0.5


class OrderLayer(BaseModel):
    spread_offset_pct: PositiveFloat = 0.0
    quantity_multiplier: PositiveFloat = 1.0
    cancel_threshold_pct: PositiveFloat = 0.01


class CircuitBreakerConfig(BaseModel):
    enabled: bool = True
    pause_threshold_pct: PositiveFloat = 0.02
    check_window_sec: PositiveInt = 10
    pause_duration_sec: PositiveInt = 60
    cool_down_after_trip_sec: PositiveInt = 300
    max_daily_loss_pct: PositiveFloat = None


class StrategyConfig(BaseModel):
    base_spread_pct: PositiveFloat = 0.001
    base_order_size_pct_of_balance: PositiveFloat = 0.005
    order_stale_threshold_pct: PositiveFloat = 0.0005
    min_profit_spread_after_fees_pct: PositiveFloat = 0.0002
    max_outstanding_orders: PositiveInt = 2
    market_data_stale_timeout_seconds: PositiveInt = 30
    enable_auto_sl_tp: bool = False
    take_profit_target_pct: PositiveFloat = 0.005
    stop_loss_trigger_pct: PositiveFloat = 0.005
    stale_order_max_age_seconds: PositiveInt = 300
    dynamic_spread: DynamicSpreadConfig = Field(default_factory=DynamicSpreadConfig)
    inventory_skew: InventorySkewConfig = Field(default_factory=InventorySkewConfig)
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    order_layers: list[OrderLayer] = Field(default_factory=lambda: [OrderLayer()])


class SystemConfig(BaseModel):
    loop_interval_sec: PositiveFloat = 0.5
    order_refresh_interval_sec: PositiveFloat = 5.0
    ws_heartbeat_sec: PositiveInt = 30
    cancellation_rate_limit_sec: PositiveFloat = 0.2
    status_report_interval_sec: PositiveInt = 30
    ws_reconnect_attempts: PositiveInt = 5
    ws_reconnect_initial_delay_sec: PositiveInt = 5
    ws_reconnect_max_delay_sec: PositiveInt = 60
    api_retry_attempts: PositiveInt = 5
    api_retry_initial_delay_sec: PositiveFloat = 0.5
    api_retry_max_delay_sec: PositiveFloat = 10
    health_check_interval_sec: PositiveInt = 10
    config_refresh_interval_sec: PositiveInt = 60


class FilesConfig(BaseModel):
    log_level: str = "INFO"
    log_file: str = "pyrmethus.log"
    state_file: str = "pyrmethus_state.json"
    db_file: str = "pyrmethus.db"
    symbol_config_file: str = "symbols.json"
    log_format: str = "plain"
    pybit_log_level: str = "WARNING"


class GlobalConfig(BaseModel):
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True
    trading_mode: str = "DRY_RUN"
    category: str = "linear"
    main_quote_currency: str = "USDT"
    system: SystemConfig = SystemConfig()
    files: FilesConfig = FilesConfig()
    initial_dry_run_capital: Decimal = Decimal("10000")
    dry_run_price_drift_mu: float = 0.0
    dry_run_price_volatility_sigma: float = 0.0001
    dry_run_time_step_dt: float = 1.0

    @classmethod
    def load_from_env(cls):
        return cls(
            api_key=os.getenv("BYBIT_API_KEY", ""),
            api_secret=os.getenv("BYBIT_API_SECRET", ""),
            testnet=os.getenv("BYBIT_TESTNET", "true").lower() == "true",
        )


# --- Market Data Structures ---
class PriceLevel:
    def __init__(self, price: float, qty: float):
        self.price = price
        self.qty = qty


# --- Skip List for Orderbook ---
class SkipListNode:
    def __init__(self, key, value, level):
        self.key = key
        self.value = value
        self.forward = [None] * (level + 1)


class SkipList:
    def __init__(self, max_level=16, p=0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = SkipListNode(None, None, max_level)

    def random_level(self):
        lvl = 0
        while np.random.random() < self.p and lvl < self.max_level:
            lvl += 1
        return lvl

    def insert(self, key, value):
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in reversed(range(self.level + 1)):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current and current.key == key:
            current.value = value
        else:
            lvl = self.random_level()
            if lvl > self.level:
                for i in range(self.level + 1, lvl + 1):
                    update[i] = self.header
                self.level = lvl
            new_node = SkipListNode(key, value, lvl)
            for i in range(lvl + 1):
                new_node.forward[i] = update[i].forward[i]
                update[i].forward[i] = new_node

    def delete(self, key):
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in reversed(range(self.level + 1)):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current and current.key == key:
            for i in range(self.level + 1):
                if update[i].forward[i] != current:
                    break
                update[i].forward[i] = current.forward[i]
            while self.level > 0 and self.header.forward[self.level] is None:
                self.level -= 1

    def search(self, key):
        current = self.header
        for i in reversed(range(self.level + 1)):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None

    def get_sorted_items(self, reverse=False):
        # Convert to list
        items = []
        node = self.header.forward[0]
        while node:
            items.append((node.key, node.value))
            node = node.forward[0]
        return sorted(items, key=lambda x: x[0], reverse=reverse)


# --- Orderbook Management ---
class Orderbook:
    def __init__(self, symbol: str, max_depth=50):
        self.symbol = symbol
        self.bids = SkipList()
        self.asks = SkipList()
        self.max_depth = max_depth
        self.lock = asyncio.Lock()

    async def update_snapshot(self, snapshot):
        async with self.lock:
            self.bids = SkipList()
            self.asks = SkipList()
            for lvl in snapshot.get("b", []):
                price, qty = float(lvl[0]), float(lvl[1])
                self.bids.insert(price, qty)
            for lvl in snapshot.get("a", []):
                price, qty = float(lvl[0]), float(lvl[1])
                self.asks.insert(price, qty)

    async def process_delta(self, delta):
        async with self.lock:
            for side in ["b", "a"]:
                for lvl in delta.get(side, []):
                    price, qty = float(lvl[0]), float(lvl[1])
                    if side == "b":
                        self.bids.insert(price, qty)
                    else:
                        self.asks.insert(price, qty)

    def get_best_bid(self):
        node = self.bids.header.forward[0]
        if node:
            return node.key, node.value
        return None, None

    def get_best_ask(self):
        node = self.asks.header.forward[0]
        if node:
            return node.key, node.value
        return None, None


# --- API Client ---
class APIClient:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        # Initialize your API client here, e.g., bybit, binance, etc.

    @retry(stop=stop_after_attempt(5), wait=wait_exponential_jitter(0.5, 10))
    async def place_order(self, **kwargs):
        # Send order to exchange
        pass

    async def get_active_orders(self, symbol):
        # Return list of active orders
        return []

    async def cancel_order(self, symbol, order_id):
        # Cancel order
        pass

    async def get_risk_limit(self, symbol):
        # Fetch risk info
        pass

    async def get_insurance(self):
        # Fetch insurance fund info
        pass


# --- Main Strategy Class ---
class MarketMaker:
    def __init__(self, bot):
        self.bot = bot
        self.config = bot.config.strategy
        self.symbol = bot.config.symbol
        self.order_layers = self.config.order_layers
        self.orderbook = bot.orderbook
        self.position = 0
        self.last_trade_time = 0
        self.last_order_time = 0
        self.atr = None
        self.atr_last_update = 0
        self.atr_period = self.config.dynamic_spread.atr_update_interval_sec

    async def update_market_data(self):
        # Fetch best bid/ask
        bid_price, bid_qty = self.orderbook.get_best_bid()
        ask_price, ask_qty = self.orderbook.get_best_ask()
        # Update ATR if needed (simulate or real data)
        now = time.time()
        if now - self.atr_last_update > self.atr_period:
            await self.compute_atr()

    async def compute_atr(self):
        # For demo, simulate ATR value
        self.atr = 50 + np.random.uniform(0, 50)
        self.atr_last_update = time.time()

    def compute_dynamic_spread(self):
        base_spread = self.config.base_spread_pct
        if self.atr:
            spread = (
                base_spread
                + (self.atr / 100000) * self.config.dynamic_spread.volatility_multiplier
            )
            spread = max(
                self.config.dynamic_spread.min_spread_pct,
                min(spread, self.config.dynamic_spread.max_spread_pct),
            )
            return spread
        return base_spread

    def get_inventory_ratio(self):
        return abs(self.bot.position) / max(1, self.bot.account_balance)

    def compute_order_sizes(self):
        size = self.bot.account_balance * self.config.base_order_size_pct_of_balance
        max_size = (
            self.config.inventory_skew.max_inventory_ratio * self.bot.account_balance
        )
        size = min(size, max_size)
        return max(Decimal("0.0001"), size)

    def compute_order_prices(self):
        spread = self.compute_dynamic_spread()
        bid_price = self.orderbook.get_best_bid()[0]
        ask_price = self.orderbook.get_best_ask()[0]
        # Adjust for inventory skew
        inventory_ratio = self.get_inventory_ratio()
        skew_factor = self.config.inventory_skew.skew_intensity
        skew_adjustment = inventory_ratio * skew_factor
        bid_price *= 1 - skew_adjustment
        ask_price *= 1 + skew_adjustment
        return float(bid_price), float(ask_price)

    async def place_layered_orders(self):
        await self.cancel_old_orders()
        await self.update_market_data()
        bid_price, ask_price = self.compute_order_prices()
        size = self.compute_order_sizes()

        for layer in self.order_layers:
            offset = layer.spread_offset_pct
            bid_layer_price = bid_price * (1 - offset)
            ask_layer_price = ask_price * (1 + offset)
            bid_qty = size * layer.quantity_multiplier
            ask_qty = size * layer.quantity_multiplier
            await self.place_order("Buy", bid_layer_price, bid_qty, layer)
            await self.place_order("Sell", ask_layer_price, ask_qty, layer)

    async def place_order(self, side, price, qty, layer):
        try:
            await self.bot.api_client.place_order(
                symbol=self.symbol,
                side=side,
                price=str(price),
                qty=str(qty),
                order_type="Limit",
            )
            # Log
        except Exception:
            # Log warning
            pass

    async def cancel_old_orders(self):
        orders = await self.bot.api_client.get_active_orders(self.symbol)
        now = time.time()
        for order in orders:
            age = now - order["created_time"]
            if age > self.config.stale_order_max_age_seconds:
                try:
                    await self.bot.api_client.cancel_order(
                        self.symbol, order["order_id"]
                    )
                except Exception:
                    pass

    def update_position(self, current_position):
        self.position = current_position

    async def monitor_and_trade(self):
        while True:
            await self.place_layered_orders()
            await asyncio.sleep(self.bot.config.system.loop_interval_sec)


# --- Main Bot ---
class Pyrmethus:
    def __init__(self):
        self.config = GlobalConfig.load_from_env()
        self.api_client = APIClient(self.config, logger)
        self.orderbook = Orderbook(self.config.symbol)
        self.strategy = None
        self.position = 0
        self.account_balance = self.config.initial_dry_run_capital
        self._stop_event = asyncio.Event()

    async def initialize(self):
        await self.api_client.get_risk_limit(self.config.symbol)
        self.strategy = MarketMaker(self)
        # Signal handlers
        loop = asyncio.get_event_loop()
        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

    async def run(self):
        await self.initialize()
        while not self._stop_event.is_set():
            # Check insurance fund
            insurance = await self.api_client.get_insurance()
            fund = Decimal(str(insurance.get("fund", "0")))
            if fund < Decimal("100"):
                # Notify
                pass
            # Run strategy
            await self.strategy.monitor_and_trade()
            await self.check_risk()
            await asyncio.sleep(self.config.system.loop_interval_sec)

    async def check_risk(self):
        # Implement profit/loss, daily loss, etc.
        pass

    async def shutdown(self):
        # Cancel orders, save state, cleanup
        self._stop_event.set()
        await asyncio.sleep(1)
        os._exit(0)


# --- Main Entry ---
async def main():
    bot = Pyrmethus()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
