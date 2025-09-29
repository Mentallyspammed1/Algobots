import asyncio
import json
import logging
import math
import os
import random
import sqlite3
import statistics
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

# --- UPGRADE: Import load_dotenv ---
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# --- Enhanced Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(symbol)s] - %(message)s",
)
logger = logging.getLogger(__name__)


class ContextFilter(logging.Filter):
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def filter(self, record):
        record.symbol = self.symbol
        return True


# --- Data Structures & State Management ---
@dataclass(slots=True)
class PriceLevel:
    price: float
    quantity: float


@dataclass
class InstrumentInfo:
    tick_size: float
    step_size: float
    min_order_size: float
    price_precision: int = field(init=False)
    qty_precision: int = field(init=False)

    def __post_init__(self):
        self.price_precision = (
            abs(int(math.log10(self.tick_size))) if self.tick_size > 0 else 0
        )
        self.qty_precision = (
            abs(int(math.log10(self.step_size))) if self.step_size > 0 else 0
        )


@dataclass
class BotState:
    instrument_info: InstrumentInfo | None = None
    recent_prices: deque = field(default_factory=lambda: deque(maxlen=240))


# --- Database Manager for Persistence ---
class DatabaseManager:
    def __init__(self, db_path="trading_log.db"):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, timestamp REAL, order_id TEXT, side TEXT, price REAL, qty REAL, pnl REAL, fee REAL, exec_id TEXT UNIQUE)"
        )
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS pnl (id INTEGER PRIMARY KEY, timestamp REAL, unrealized_pnl REAL, realized_pnl REAL, total_pnl REAL, position_size REAL)"
        )
        self.conn.commit()

    def log_trade(self, trade_data: dict):
        try:
            self.cursor.execute(
                "INSERT INTO trades VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.time(),
                    trade_data["orderId"],
                    trade_data["side"],
                    float(trade_data["execPrice"]),
                    float(trade_data["execQty"]),
                    self._safe_float(trade_data.get("closedPnl")),
                    float(trade_data["execFee"]),
                    trade_data["execId"],
                ),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass
        except Exception as e:
            logger.error(f"DB Error logging trade: {e}")

    def log_pnl(
        self, unrealized: float, realized: float, total: float, position: float
    ):
        try:
            self.cursor.execute(
                "INSERT INTO pnl VALUES (NULL, ?, ?, ?, ?, ?)",
                (time.time(), unrealized, realized, total, position),
            )
            self.conn.commit()
        except Exception as e:
            logger.error(f"DB Error logging PNL: {e}")

    def _safe_float(self, val):
        return float(val) if val not in [None, ""] else 0.0


# --- High-Performance Data Structures ---
KT = TypeVar("KT")
VT = TypeVar("VT")


class OptimizedSkipList(Generic[KT, VT]):
    class Node(Generic[KT, VT]):
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            self.forward: list[OptimizedSkipList.Node | None] = [None] * (level + 1)

    def __init__(self, max_level: int = 16, p: float = 0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = self.Node(None, None, max_level)

    def _random_level(self) -> int:
        lvl = 0
        while lvl < self.max_level and random.random() < self.p:
            lvl += 1
        return lvl

    def insert(self, key: KT, value: VT):
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
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

    def delete(self, key: KT):
        update = [None] * (self.max_level + 1)
        current = self.header
        for i in range(self.level, -1, -1):
            while current.forward[i] and current.forward[i].key < key:
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current and current.key == key:
            for i in range(self.level + 1):
                if update[i].forward[i] != current:
                    break
                update[i].forward[i] = current.forward[i]
            while self.level > 0 and not self.header.forward[self.level]:
                self.level -= 1

    def get_sorted_items(self, reverse: bool = False) -> list[tuple[KT, VT]]:
        items = []
        current = self.header.forward[0]
        while current:
            items.append((current.key, current.value))
            current = current.forward[0]
        return list(reversed(items)) if reverse else items


# --- Order Book Manager & Analyzer ---
class OrderbookAnalyzer:
    def __init__(self, config):
        self._lock = asyncio.Lock()
        self.bids = OptimizedSkipList[float, PriceLevel]()
        self.asks = OptimizedSkipList[float, PriceLevel]()
        self.config = config

    @asynccontextmanager
    async def _lock_context(self):
        async with self._lock:
            yield

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    async def process_snapshot(self, data: dict):
        async with self._lock_context():
            self.bids = OptimizedSkipList[float, PriceLevel]()
            self.asks = OptimizedSkipList[float, PriceLevel]()
            for p, q in data.get("b", []):
                self.bids.insert(
                    self._safe_float(p),
                    PriceLevel(price=self._safe_float(p), quantity=self._safe_float(q)),
                )
            for p, q in data.get("a", []):
                self.asks.insert(
                    self._safe_float(p),
                    PriceLevel(price=self._safe_float(p), quantity=self._safe_float(q)),
                )

    async def process_delta(self, data: dict):
        async with self._lock_context():
            for p, q in data.get("b", []):
                price, qty = self._safe_float(p), self._safe_float(q)
                if qty == 0:
                    self.bids.delete(price)
                else:
                    self.bids.insert(price, PriceLevel(price=price, quantity=qty))
            for p, q in data.get("a", []):
                price, qty = self._safe_float(p), self._safe_float(q)
                if qty == 0:
                    self.asks.delete(price)
                else:
                    self.asks.insert(price, PriceLevel(price=price, quantity=qty))

    async def get_depth(self, depth: int) -> tuple[list[PriceLevel], list[PriceLevel]]:
        async with self._lock_context():
            bids = [
                level for _, level in self.bids.get_sorted_items(reverse=True)[:depth]
            ]
            asks = [level for _, level in self.asks.get_sorted_items()[:depth]]
            return bids, asks

    async def get_best_bid_ask(self) -> tuple[float, float] | None:
        async with self._lock_context():
            best_bid_item = self.bids.get_sorted_items(reverse=True)
            best_ask_item = self.asks.get_sorted_items()
            if not best_bid_item or not best_ask_item:
                return None, None
            return best_bid_item[0][0], best_ask_item[0][0]

    async def calculate_ofi(self) -> float:
        bids, asks = await self.get_depth(self.config["analysis"]["depth"])
        bid_volume = sum(level.quantity * level.price for level in bids)
        ask_volume = sum(level.quantity * level.price for level in asks)
        if bid_volume + ask_volume == 0:
            return 0.0
        return (bid_volume - ask_volume) / (bid_volume + ask_volume)

    async def calculate_microprice(self) -> float | None:
        bids, asks = await self.get_depth(self.config["analysis"]["depth"])
        if not bids or not asks:
            return None
        total_bid_qty = sum(b.quantity for b in bids)
        total_ask_qty = sum(a.quantity for a in asks)
        if total_bid_qty + total_ask_qty == 0:
            return (bids[0].price + asks[0].price) / 2
        return (bids[0].price * total_ask_qty + asks[0].price * total_bid_qty) / (
            total_bid_qty + total_ask_qty
        )

    async def detect_large_orders(self) -> dict[str, list[dict]]:
        bids, asks = await self.get_depth(50)
        multiplier = self.config["analysis"]["large_order_multiplier"]
        results = {"bids": [], "asks": []}
        for side, levels in [("bids", bids), ("asks", asks)]:
            if len(levels) < 5:
                continue
            for i in range(2, len(levels) - 2):
                surrounding = [
                    levels[j].quantity for j in range(i - 2, i + 3) if j != i
                ]
                avg_surrounding = (
                    sum(surrounding) / len(surrounding) if surrounding else 0
                )
                if (
                    avg_surrounding > 0
                    and levels[i].quantity > avg_surrounding * multiplier
                ):
                    results[side].append(
                        {
                            "price": levels[i].price,
                            "quantity": levels[i].quantity,
                            "ratio": levels[i].quantity / avg_surrounding,
                        }
                    )
        return results


# --- Position Manager ---
class PositionManager:
    def __init__(self, config, api, db_manager):
        self.config = config
        self.api = api
        self.db = db_manager
        self.size = 0.0
        self.avg_entry_price = 0.0
        self.unrealized_pnl = 0.0
        self.realized_pnl = 0.0

    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def update_position(self, data: dict):
        self.size = self._safe_float(data.get("size"))
        self.avg_entry_price = self._safe_float(data.get("avgPrice"))
        self.unrealized_pnl = self._safe_float(data.get("unrealisedPnl"))

    def process_fill(self, trade: dict):
        closed_pnl = self._safe_float(trade.get("closedPnl"))
        if closed_pnl != 0:
            self.realized_pnl += closed_pnl
        self.db.log_trade(trade)

    async def check_and_manage_risk(self, state: BotState):
        if self.size == 0:
            return False
        pnl_pct = (
            self.unrealized_pnl / (abs(self.size) * self.avg_entry_price)
            if self.avg_entry_price > 0
            else 0
        )
        should_close, reason = False, ""
        if pnl_pct >= self.config["risk_management"]["take_profit_pct"]:
            should_close, reason = True, f"Take Profit ({pnl_pct:.2%})"
        elif pnl_pct <= -self.config["risk_management"]["stop_loss_pct"]:
            should_close, reason = True, f"Stop Loss ({pnl_pct:.2%})"
        if should_close:
            logger.warning(
                f"Closing position due to: {reason}. Position Size: {self.size}"
            )
            side_to_close = "Buy" if self.size < 0 else "Sell"
            qty_to_close = state.instrument_info.step_size * round(
                abs(self.size) / state.instrument_info.step_size
            )
            await self.api.close_position(side_to_close, qty_to_close)
            return True
        return False


# --- Core Bot Class ---
class BybitMarketMakingBot:
    def __init__(self, config):
        self.config = config
        self.state = BotState()
        # --- UPGRADE: API keys loaded from .env file via os.getenv ---
        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "API credentials not found. Ensure they are in your .env file."
            )
        self.session = HTTP(
            testnet=config["testnet"], api_key=self.api_key, api_secret=self.api_secret
        )
        self.api = self
        self.db = DatabaseManager()
        self.orderbook_analyzer = OrderbookAnalyzer(config)
        self.position_manager = PositionManager(config, self, self.db)
        self.active_orders = {}
        self.last_reprice_time = 0
        self.last_analysis_time = 0
        logger.addFilter(ContextFilter(config["symbol"]))

    async def _api_call(self, method, **kwargs):
        for attempt in range(self.config["technical"]["api_max_retries"]):
            try:
                response = method(**kwargs)
                if response.get("retCode") == 0:
                    return response["result"]
                else:
                    logger.error(f"API Error: {response}")
            except Exception as e:
                logger.error(f"API request failed: {e}. Retrying...")
            await asyncio.sleep(
                self.config["technical"]["api_retry_delay_seconds"] * (2**attempt)
            )
        return None

    async def fetch_instrument_info(self):
        result = await self._api_call(
            self.session.get_instruments_info,
            category="linear",
            symbol=self.config["symbol"],
        )
        if result and result.get("list"):
            info = result["list"][0]
            self.state.instrument_info = InstrumentInfo(
                tick_size=float(info["priceFilter"]["tickSize"]),
                step_size=float(info["lotSizeFilter"]["qtyStep"]),
                min_order_size=float(info["lotSizeFilter"]["minOrderQty"]),
            )

    async def place_and_cancel_orders_batch(self, orders_to_place, orders_to_cancel):
        if orders_to_cancel:
            await self._api_call(
                self.session.cancel_batch_order,
                category="linear",
                request=[
                    {"symbol": self.config["symbol"], "orderId": oid}
                    for oid in orders_to_cancel
                ],
            )
        if orders_to_place:
            await self._api_call(
                self.session.place_batch_order,
                category="linear",
                request=[
                    {
                        "symbol": self.config["symbol"],
                        "side": o["side"],
                        "orderType": "Limit",
                        "qty": str(o["qty"]),
                        "price": str(o["price"]),
                        "orderLinkId": f"mm_{uuid.uuid4().hex[:8]}",
                        "timeInForce": "PostOnly",
                    }
                    for o in orders_to_place
                ],
            )

    async def close_position(self, side, qty):
        await self._api_call(
            self.session.place_order,
            category="linear",
            symbol=self.config["symbol"],
            side=side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
        )

    async def cancel_all_orders(self):
        await self._api_call(
            self.session.cancel_all_orders,
            category="linear",
            symbol=self.config["symbol"],
        )

    async def _handle_message(self, msg):
        topic = msg.get("topic", "")
        data = msg.get("data")
        if topic.startswith("orderbook"):
            await self.orderbook_analyzer.process_snapshot(data) if msg.get(
                "type"
            ) == "snapshot" else await self.orderbook_analyzer.process_delta(data)
        elif topic.startswith("tickers"):
            self.state.recent_prices.append(float(data["midPrice"]))
        elif topic == "position":
            for pos_data in msg.get("data", []):
                if pos_data.get("symbol") == self.config["symbol"]:
                    self.position_manager.update_position(pos_data)
        elif topic == "order":
            for order in msg.get("data", []):
                oid = order["orderId"]
                if order["orderStatus"] in ["New", "PartiallyFilled"]:
                    self.active_orders[oid] = {"createdTime": int(order["createdTime"])}
                elif oid in self.active_orders:
                    del self.active_orders[oid]
        elif topic == "execution":
            for trade in msg.get("data", []):
                self.position_manager.process_fill(trade)

    def _calculate_quotes(self, ofi, microprice):
        volatility = (
            statistics.stdev(self.state.recent_prices) / microprice
            if len(self.state.recent_prices) > 50
            else 0
        )
        volatility_spread = (
            volatility * self.config["strategy"]["volatility_spread_multiplier"]
        )
        inventory_skew = (
            self.position_manager.size
            / self.config["risk_management"]["max_position_size"]
        ) * self.config["strategy"]["inventory_skew_intensity"]
        imbalance_skew = ofi * self.config["strategy"]["imbalance_skew_intensity"]
        total_spread = (
            self.config["strategy"]["base_spread_percentage"] + volatility_spread
        )
        skew = microprice * (inventory_skew - imbalance_skew)
        return microprice * (1 - total_spread) - skew, microprice * (
            1 + total_spread
        ) - skew

    def _format_price(self, p):
        i = self.state.instrument_info
        return round(round(p / i.tick_size) * i.tick_size, i.price_precision)

    def _format_qty(self, q):
        i = self.state.instrument_info
        return round(round(q / i.step_size) * i.step_size, i.qty_precision)

    async def run(self):
        logger.info(
            f"Starting bot for {self.config['symbol']} on {'Testnet' if self.config['testnet'] else 'MAINNET'}"
        )
        await self.fetch_instrument_info()
        assert self.state.instrument_info
        await self.cancel_all_orders()
        loop = asyncio.get_running_loop()
        ws_public = WebSocket(testnet=self.config["testnet"], channel_type="linear")
        ws_private = WebSocket(testnet=self.config["testnet"], channel_type="private")
        public_topics = [
            f"orderbook.{self.config['technical']['orderbook_depth']}.{self.config['symbol']}",
            f"tickers.{self.config['symbol']}",
        ]
        private_topics = ["position", "order", "execution"]

        def cb(m):
            asyncio.run_coroutine_threadsafe(self._handle_message(m), loop)

        loop.run_in_executor(None, lambda: ws_public.subscribe(public_topics, cb))
        loop.run_in_executor(None, lambda: ws_private.subscribe(private_topics, cb))
        await asyncio.sleep(5)
        while True:
            try:
                if await self.position_manager.check_and_manage_risk(self.state):
                    await self.cancel_all_orders()
                    logger.warning("Position closed by risk manager. Pausing 60s.")
                    await asyncio.sleep(60)
                    continue
                now = time.time()
                if (
                    now - self.last_reprice_time
                    < self.config["order_management"]["order_reprice_delay_seconds"]
                ):
                    await asyncio.sleep(0.1)
                    continue
                microprice = await self.orderbook_analyzer.calculate_microprice()
                ofi = await self.orderbook_analyzer.calculate_ofi()
                if not microprice:
                    await asyncio.sleep(0.5)
                    continue
                our_bid, our_ask = self._calculate_quotes(ofi, microprice)
                volatility = (
                    statistics.stdev(self.state.recent_prices) / microprice
                    if len(self.state.recent_prices) > 50
                    else 0
                )
                size_multiplier = max(0.5, 1 - volatility * 20)
                order_size = (
                    self.config["order_management"]["base_order_size"] * size_multiplier
                )
                orders_to_place, orders_to_cancel = [], []
                if (
                    self.position_manager.size + order_size
                    <= self.config["risk_management"]["max_position_size"]
                ):
                    orders_to_place.append(
                        {
                            "side": "Buy",
                            "price": self._format_price(our_bid),
                            "qty": self._format_qty(order_size),
                        }
                    )
                if (
                    abs(self.position_manager.size - order_size)
                    <= self.config["risk_management"]["max_position_size"]
                ):
                    orders_to_place.append(
                        {
                            "side": "Sell",
                            "price": self._format_price(our_ask),
                            "qty": self._format_qty(order_size),
                        }
                    )
                if self.active_orders:
                    orders_to_cancel.extend(list(self.active_orders.keys()))
                for oid, o in self.active_orders.items():
                    if (
                        now * 1000 - o["createdTime"]
                        > self.config["order_management"]["stale_order_timeout_seconds"]
                        * 1000
                    ):
                        if oid not in orders_to_cancel:
                            orders_to_cancel.append(oid)
                await self.place_and_cancel_orders_batch(
                    orders_to_place, orders_to_cancel
                )
                self.last_reprice_time = now
                if now - self.last_analysis_time > 300:
                    large_orders = await self.orderbook_analyzer.detect_large_orders()
                    if large_orders["bids"] or large_orders["asks"]:
                        logger.info(
                            f"Deep Analysis - Large Orders Detected: {large_orders}"
                        )
                    self.last_analysis_time = now
                if int(now) % 60 == 0:
                    pnl_total = (
                        self.position_manager.realized_pnl
                        + self.position_manager.unrealized_pnl
                    )
                    logger.info(
                        f"STATUS | Pos: {self.position_manager.size:.4f} | uPNL: {self.position_manager.unrealized_pnl:.4f} | rPNL: {self.position_manager.realized_pnl:.4f} | Total: {pnl_total:.4f}"
                    )
                    self.db.log_pnl(
                        self.position_manager.unrealized_pnl,
                        self.position_manager.realized_pnl,
                        pnl_total,
                        self.position_manager.size,
                    )
            except asyncio.CancelledError:
                logger.info("Main loop cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(5)


async def main():
    # --- UPGRADE: Load .env file ---
    load_dotenv()

    try:
        with open("config.json") as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error("CRITICAL: config.json not found.")
        return

    bot = BybitMarketMakingBot(config)
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(bot.run())
    for sig in [asyncio.signal.SIGINT, asyncio.signal.SIGTERM]:
        loop.add_signal_handler(sig, lambda: main_task.cancel())
    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Cleaning up...")
        await bot.cancel_all_orders()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user.")
