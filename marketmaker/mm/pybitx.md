{
  "pybit_enhanced_full_guide": {
    "overview": "Comprehensive API functions for account, market data, trading, WebSocket, hedge mode, risk management, and utility.",
    "auth": {
      "api_key": "your_api_key",
      "api_secret": "your_api_secret",
      "testnet": true
    },

    "core_functions": {
      "account_and_balance": {
        "get_wallet_balance": {
          "code": "session.get_wallet_balance(accountType='UNIFIED')",
          "endpoint": "/v5/account/wallet-balance",
          "auth_required": true,
          "description": "Retrieve wallet balances and risk metrics."
        },
        "get_transferable_amount": {
          "code": "session.get_transferable_amount(coinName='USDT')",
          "endpoint": "/v5/account/withdrawal",
          "auth_required": true,
          "description": "Query available transfer amount."
        },
        "get_borrow_history": {
          "code": "session.get_borrow_history(currency='USDT')",
          "endpoint": "/v5/account/borrow-history",
          "auth_required": true,
          "description": "Get borrowing/interest history."
        }
      },

      "market_data": {
        "get_server_time": {
          "code": "session.get_server_time()",
          "endpoint": "/v5/market/time",
          "auth_required": false
        },
        "get_orderbook": {
          "code": "session.get_orderbook(category='linear', symbol='BTCUSDT')",
          "endpoint": "/v5/market/orderbook",
          "required_params": ["category", "symbol"],
          "description": "Fetch current orderbook snapshot."
        },
        "get_tickers": {
          "code": "session.get_tickers(category='linear')",
          "endpoint": "/v5/market/tickers"
        },
        "get_kline": {
          "code": "session.get_kline(category='linear', symbol='BTCUSDT', interval='1h')",
          "endpoint": "/v5/market/kline"
        },
        "get_instruments_info": {
          "code": "session.get_instruments_info(category='linear')",
          "endpoint": "/v5/market/instruments-info"
        }
      },

      "order_management": {
        "place_order": {
          "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000', timeInForce='GoodTillCancel')",
          "optional_params": ["price", "timeInForce", "orderLinkId"]
        },
        "amend_order": {
          "code": "session.amend_order(category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')"
        },
        "cancel_order": {
          "code": "session.cancel_order(category='linear', symbol='BTCUSDT', orderId='order_id')"
        },
        "cancel_all_orders": {
          "code": "session.cancel_all_orders(category='linear', symbol='BTCUSDT')"
        },
        "get_open_orders": {
          "code": "session.get_open_orders(category='linear', symbol='BTCUSDT')"
        }
      },

      "position_management": {
        "get_positions": {
          "code": "session.get_positions(category='linear', symbol='BTCUSDT')"
        },
        "set_leverage": {
          "code": "session.set_leverage(category='linear', symbol='BTCUSDT', buyLeverage='10', sellLeverage='10')"
        },
        "switch_position_mode": {
          "code": "session.switch_position_mode(category='linear', mode='3')",
          "description": "Enable hedge mode (mode='3')."
        },
        "set_trading_stop": {
          "code": "session.set_trading_stop(category='linear', symbol='BTCUSDT', stopLoss='49000', takeProfit='51000')"
        }
      },

      "risk_management": {
        "set_mmp": {
          "code": "session.set_mmp(baseCoin='BTC', window='5000', frozenPeriod='10000', qtyLimit='1.00', deltaLimit='0.50')"
        },
        "reset_mmp": {
          "code": "session.reset_mmp(baseCoin='BTC')"
        }
      },

      "websocket_public": {
        "orderbook": {
          "code": "ws.orderbook_stream(depth=50, symbol='BTCUSDT', callback=handle_orderbook)"
        },
        "ticker": {
          "code": "ws.ticker_stream(symbol='BTCUSDT', callback=handle_ticker)"
        },
        "trade": {
          "code": "ws.trade_stream(symbol='BTCUSDT', callback=handle_trades)"
        }
      },

      "websocket_private": {
        "position": {
          "code": "ws.position_stream(callback=handle_position)"
        },
        "order": {
          "code": "ws.order_stream(callback=handle_orders)"
        },
        "execution": {
          "code": "ws.execution_stream(callback=handle_executions)"
        },
        "wallet": {
          "code": "ws.wallet_stream(callback=handle_wallet)"
        }
      },

      "websocket_trading": {
        "place_order": {
          "code": "ws_trading.place_order(callback=handle_response, category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')"
        },
        "amend_order": {
          "code": "ws_trading.amend_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')"
        },
        "cancel_order": {
          "code": "ws_trading.cancel_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id')"
        },
        "place_batch_order": {
          "code": "ws_trading.place_batch_order(callback=handle_response, category='linear', request=[{...}])"
        },
        "cancel_batch_order": {
          "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{...}])"
        }
      },

      "hedge_mode": {
        "switch_position_mode": {
          "code": "session.switch_position_mode(category='linear', mode='3')"
        },
        "place_hedge_orders": {
          "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000', positionIdx=1)"
        }
      }
    },

    "utilities": {
      "calculate_spread": "spread = (sell_price - buy_price) / buy_price",
      "calculate_position_size": "size = account_balance * risk_percentage / stop_loss_distance"
    },

    "notes": "Replace placeholders with your actual API keys, symbols, and parameters. Use try-except blocks for robust error handling. Monitor rate limits and reconnect WebSocket streams as needed."
  }
}
import threading
import time
import random
import logging
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from functools import cached_property
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Data classes for orderbook levels ---
@dataclass(slots=True)
class PriceLevel:
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1

# --- Utility functions ---
def is_valid_price_quantity(price: float, quantity: float) -> bool:
    return isinstance(price, (int, float)) and isinstance(quantity, (int, float)) and price >= 0 and quantity >= 0

# --- Skip List Implementation ---
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
        self.size = 0

    def random_level(self):
        lvl = 0
        while random.random() < self.p and lvl < self.max_level:
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
            return
        lvl = self.random_level()
        if lvl > self.level:
            for i in range(self.level + 1, lvl + 1):
                update[i] = self.header
            self.level = lvl
        node = SkipListNode(key, value, lvl)
        for i in range(lvl + 1):
            node.forward[i] = update[i].forward[i]
            update[i].forward[i] = node
        self.size += 1

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
            self.size -= 1
            return True
        return False

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
        # Traverse from lowest to highest, then reverse if needed
        current = self.header.forward[0]
        items = []
        while current:
            items.append((current.key, current.value))
            current = current.forward[0]
        return list(reversed(items)) if reverse else items

# --- Heap with position tracking ---
class EnhancedHeap:
    def __init__(self, max_heap=True):
        self.heap: List[PriceLevel] = []
        self.position_map: Dict[float, int] = {}
        self.max_heap = max_heap

    def _compare(self, a, b):
        return a.price > b.price if self.max_heap else a.price < b.price

    def _swap(self, i, j):
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]

    def insert(self, level: PriceLevel):
        if level.price in self.position_map:
            idx = self.position_map[level.price]
            self.heap[idx] = level
            self._heapify_up(idx)
            self._heapify_down(idx)
        else:
            self.heap.append(level)
            idx = len(self.heap) - 1
            self.position_map[level.price] = idx
            self._heapify_up(idx)

    def _heapify_up(self, i):
        while i > 0:
            parent = (i - 1) // 2
            if self._compare(self.heap[i], self.heap[parent]):
                self._swap(i, parent)
                i = parent
            else:
                break

    def _heapify_down(self, i):
        size = len(self.heap)
        while True:
            left = 2 * i + 1
            right = 2 * i + 2
            target = i

            if left < size and self._compare(self.heap[left], self.heap[target]):
                target = left
            if right < size and self._compare(self.heap[right], self.heap[target]):
                target = right
            if target == i:
                break
            self._swap(i, target)
            i = target

    def extract_top(self):
        if not self.heap:
            return None
        top = self.heap[0]
        last = self.heap.pop()
        if self.heap:
            self.heap[0] = last
            self._heapify_down(0)
        del self.position_map[top.price]
        return top

    def remove(self, price):
        idx = self.position_map.get(price)
        if idx is None:
            return False
        last = self.heap.pop()
        if idx < len(self.heap):
            self.heap[idx] = last
            self._heapify_up(idx)
            self._heapify_down(idx)
        del self.position_map[price]
        return True

# --- Orderbook Manager ---
class OrderbookManager:
    def __init__(self, symbol, use_skip_list=True, max_depth=100):
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self.max_depth = max_depth
        self._lock = threading.RLock()
        # Initialize data structures
        if use_skip_list:
            self.bids = SkipList()
            self.asks = SkipList()
        else:
            self.bids = EnhancedHeap(max_heap=True)
            self.asks = EnhancedHeap(max_heap=False)
        # Metadata
        self.last_update_id = 0
        self.last_sequence = 0
        self.timestamp = 0
        # Performance metrics
        self.update_count = 0
        self.total_update_time = 0
        # Cache for top levels
        self._best_bid = None
        self._best_ask = None

    @contextmanager
    def _safe_lock(self):
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()

    def process_snapshot(self, snapshot: Dict):
        try:
            with self._safe_lock():
                start = time.perf_counter()
                # Validation
                if not isinstance(snapshot, dict):
                    raise ValueError("Snapshot must be a dict.")
                bids_raw = snapshot.get("b", [])
                asks_raw = snapshot.get("a", [])
                update_id = snapshot.get("u")
                sequence = snapshot.get("seq", 0)
                ts = snapshot.get("ts", int(time.time() * 1000))
                # Clear existing
                self.bids = SkipList() if self.use_skip_list else EnhancedHeap(max_heap=True)
                self.asks = SkipList() if self.use_skip_list else EnhancedHeap(max_heap=False)
                # Insert bids
                for price_str, qty_str in bids_raw:
                    try:
                        p = float(price_str)
                        q = float(qty_str)
                        if not is_valid_price_quantity(p, q):
                            continue
                        level = PriceLevel(p, q, ts)
                        if self.use_skip_list:
                            self.bids.insert(p, level)
                        else:
                            self.bids.insert(level)
                    except Exception:
                        continue
                # Insert asks
                for price_str, qty_str in asks_raw:
                    try:
                        p = float(price_str)
                        q = float(qty_str)
                        if not is_valid_price_quantity(p, q):
                            continue
                        level = PriceLevel(p, q, ts)
                        if self.use_skip_list:
                            self.asks.insert(p, level)
                        else:
                            self.asks.insert(level)
                    except Exception:
                        continue
                # Update metadata
                self.last_update_id = update_id
                self.last_sequence = sequence
                self.timestamp = ts
                # Reset cache
                self._best_bid = None
                self._best_ask = None
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start
        except Exception as e:
            logging.exception(f"Error in process_snapshot for {self.symbol}: {e}")

    def process_delta(self, delta: Dict):
        try:
            with self._safe_lock():
                start = time.perf_counter()
                seq = delta.get("seq", self.last_sequence + 1)
                if seq <= self.last_sequence:
                    # Out of order, ignore or trigger resync
                    return
                # Process bids
                for price_str, qty_str in delta.get("b", []):
                    try:
                        p = float(price_str)
                        q = float(qty_str)
                        if not is_valid_price_quantity(p, q):
                            continue
                        if q == 0:
                            self.bids.remove(p)
                        else:
                            level = PriceLevel(p, q, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(p, level)
                            else:
                                self.bids.insert(level)
                    except:
                        continue
                # Process asks
                for price_str, qty_str in delta.get("a", []):
                    try:
                        p = float(price_str)
                        q = float(qty_str)
                        if not is_valid_price_quantity(p, q):
                            continue
                        if q == 0:
                            self.asks.remove(p)
                        else:
                            level = PriceLevel(p, q, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(p, level)
                            else:
                                self.asks.insert(level)
                    except:
                        continue
                # Update metadata
                self.last_sequence = seq
                self.last_update_id = delta.get("u", self.last_update_id)
                self.timestamp = delta.get("ts", int(time.time() * 1000))
                # Reset cache
                self._best_bid = None
                self._best_ask = None
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start
        except Exception as e:
            logging.exception(f"Error in process_delta for {self.symbol}: {e}")

    @cached_property
    def best_bid(self):
        if self._best_bid is None:
            with self._lock:
                if self.use_skip_list:
                    items = self.bids.get_sorted_items(reverse=True)
                    self._best_bid = items[0][1] if items else None
                else:
                    self._best_bid = self.bids.extract_top()
                    if self._best_bid:
                        self.bids.insert(self._best_bid)
        return self._best_bid

    @cached_property
    def best_ask(self):
        if self._best_ask is None:
            with self._lock:
                if self.use_skip_list:
                    items = self.asks.get_sorted_items()
                    self._best_ask = items[0][1] if items else None
                else:
                    self._best_ask = self.asks.extract_top()
                    if self._best_ask:
                        self.asks.insert(self._best_ask)
        return self._best_ask

    def get_top_levels(self, depth=10):
        with self._lock:
            bids = []
            asks = []
            if self.use_skip_list:
                bids = [item[1] for item in self.bids.get_sorted_items(reverse=True)[:depth]]
                asks = [item[1] for item in self.asks.get_sorted_items()[:depth]]
            else:
                # For heaps, extract top N and reinsert
                for _ in range(min(depth, len(self.bids.heap))):
                    lvl = self.bids.extract_top()
                    if lvl:
                        bids.append(lvl)
                        self.bids.insert(lvl)
                for _ in range(min(depth, len(self.asks.heap))):
                    lvl = self.asks.extract_top()
                    if lvl:
                        asks.append(lvl)
                        self.asks.insert(lvl)
            return bids, asks

    def validate_orderbook(self):
        try:
            with self._lock:
                if self.use_skip_list:
                    bid_items = self.bids.get_sorted_items(reverse=True)
                    ask_items = self.asks.get_sorted_items()
                    # Check for duplicate prices
                    bid_prices = {item[0] for item in bid_items}
                    ask_prices = {item[0] for item in ask_items}
                    if len(bid_prices) != len(bid_items) or len(ask_prices) != len(ask_items):
                        return False
                    # Check spread
                    if bid_items and ask_items and bid_items[0][0] >= ask_items[0][0]:
                        return False
                # For heaps, more complex validation could be added
                return True
        except:
            return False

# --- Usage example ---
if __name__ == "__main__":
    # Instantiate for a symbol
    ob = OrderbookManager("BTCUSDT", use_skip_list=True)

    # Mock snapshot
    snapshot = {
        "u": 1001,
        "seq": 10,
        "ts": int(time.time() * 1000),
        "b": [["50000", "1.2"], ["49999", "0.8"]],
        "a": [["50001", "1.0"], ["50002", "0.5"]]
    }
    ob.process_snapshot(snapshot)

    # Mock delta
    delta = {
        "u": 1002,
        "seq": 11,
        "ts": int(time.time() * 1000),
        "b": [["50000", "1.3"], ["49998", "0.1"]],
        "a": [["50001", "0"], ["50003", "0.4"]]
    }
    ob.process_delta(delta)

    print("Best Bid:", ob.best_bid)
    print("Best Ask:", ob.best_ask)

    # Get top levels
    bids, asks = ob.get_top_levels(3)
    print("Top Bids:", bids)
    print("Top Asks:", asks)

    print("Orderbook valid:", ob.validate_orderbook())

# --- Notes ---
# 1. Replace mock data with real API calls and WebSocket handlers.
# 2. Implement reconnection, heartbeat, rate limiting as needed.
# 3. Wrap API calls with try-except, handle exceptions gracefully.
# 4. Use async/await if integrating with asyncio event loop.
{
  "pybit_bybit_full": [
    {
      "category": "Authentication",
      "description": "API keys and environment setup",
      "items": [
        {
          "name": "api_key",
          "type": "string",
          "required": true,
          "description": "Your API key for bybit"
        },
        {
          "name": "api_secret",
          "type": "string",
          "required": true,
          "description": "Your API secret for bybit"
        },
        {
          "name": "testnet",
          "type": "boolean",
          "default": false,
          "description": "Use testnet environment"
        }
      ]
    },
    {
      "category": "Account & Wallet",
      "description": "Account info, balances, and transfers",
      "items": [
        {
          "name": "get_wallet_balance",
          "endpoint": "/v2/private/wallet/balance",
          "method": "GET",
          "auth_required": true,
          "params": [
            {
              "name": "coin",
              "type": "string",
              "description": "Coin symbol, e.g., USDT"
            }
          ],
          "description": "Retrieve wallet balance for specified coin"
        },
        {
          "name": "get_position_list",
          "endpoint": "/v2/private/position/list",
          "method": "GET",
          "auth_required": true,
          "description": "Get list of open positions"
        },
        {
          "name": "transfer",
          "endpoint": "/v2/private/transfer",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "coin", "type": "string"},
            {"name": "amount", "type": "number"},
            {"name": "from_account_type", "type": "string", "description": "TRANSFER_IN or TRANSFER_OUT"},
            {"name": "to_account_type", "type": "string"}
          ],
          "description": "Transfer funds between accounts"
        }
      ]
    },
    {
      "category": "Market Data",
      "description": "Market information and recent trades",
      "items": [
        {
          "name": "get_instrument_info",
          "endpoint": "/v2/public/symbols",
          "method": "GET",
          "auth_required": false,
          "description": "Get details of trading symbols"
        },
        {
          "name": "get_orderbook",
          "endpoint": "/v2/public/orderBook/L2",
          "method": "GET",
          "auth_required": false,
          "params": [
            {"name": "symbol", "type": "string"}
          ],
          "description": "Get order book depth"
        },
        {
          "name": "get_recent_trades",
          "endpoint": "/v2/public/recent-trades",
          "method": "GET",
          "auth_required": false,
          "params": [
            {"name": "symbol", "type": "string"}
          ],
          "description": "Get recent trades"
        },
        {
          "name": "get_kline",
          "endpoint": "/v2/public/kline",
          "method": "GET",
          "auth_required": false,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "interval", "type": "string", "description": "e.g., 1m, 5m, 1h"},
            {"name": "from", "type": "int", "description": "Start timestamp"},
            {"name": "to", "type": "int", "description": "End timestamp"}
          ],
          "description": "Get historical candlestick data"
        }
      ]
    },
    {
      "category": "Order Management",
      "description": "Create, amend, cancel, and query orders",
      "items": [
        {
          "name": "place_order",
          "endpoint": "/v2/private/order/create",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "side", "type": "string", "enum": ["Buy", "Sell"]},
            {"name": "order_type", "type": "string", "enum": ["Limit", "Market", "StopLimit", "StopMarket"]},
            {"name": "qty", "type": "number"},
            {"name": "price", "type": "number", "optional": true},
            {"name": "stop_px", "type": "number", "optional": true},
            {"name": "time_in_force", "type": "string", "enum": ["GoodTillCancel", "ImmediateOrCancel", "FillOrKill"], "optional": true},
            {"name": "order_link_id", "type": "string", "optional": true}
          ],
          "description": "Place new order"
        },
        {
          "name": "amend_order",
          "endpoint": "/v2/private/order/amend",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "order_id", "type": "string"},
            {"name": "price", "type": "number", "optional": true},
            {"name": "qty", "type": "number", "optional": true}
          ],
          "description": "Amend existing order"
        },
        {
          "name": "cancel_order",
          "endpoint": "/v2/private/order/cancel",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "order_id", "type": "string"}
          ],
          "description": "Cancel specific order"
        },
        {
          "name": "cancel_all_orders",
          "endpoint": "/v2/private/order/cancelAll",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string", "optional": true}
          ],
          "description": "Cancel all open orders for symbol"
        },
        {
          "name": "get_open_orders",
          "endpoint": "/v2/private/order/list",
          "method": "GET",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string", "optional": true}
          ],
          "description": "Query open orders"
        }
      ]
    },
    {
      "category": "Positions",
      "description": "Open position info and management",
      "items": [
        {
          "name": "get_position_list",
          "endpoint": "/v2/private/position/list",
          "method": "GET",
          "auth_required": true,
          "description": "List current open positions"
        },
        {
          "name": "set_leverage",
          "endpoint": "/v2/private/position/leverage",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "leverage", "type": "int"}
          ],
          "description": "Set leverage for a symbol"
        },
        {
          "name": "close_position",
          "endpoint": "/v2/private/order/create",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "side", "type": "string", "enum": ["Buy", "Sell"]},
            {"name": "order_type", "type": "string", "enum": ["Market"]},
            {"name": "qty", "type": "number"}
          ],
          "description": "Close position with a market order"
        }
      ]
    },
    {
      "category": "WebSocket Data Streams",
      "description": "Real-time data via WebSocket",
      "items": [
        {
          "name": "subscribe_orderbook",
          "endpoint": "wss://stream.bybit.com/v5/public/spot-orderbook",
          "description": "Orderbook updates"
        },
        {
          "name": "subscribe_trades",
          "endpoint": "wss://stream.bybit.com/v5/public/spot-trades",
          "description": "Trade updates"
        },
        {
          "name": "subscribe_tickers",
          "endpoint": "wss://stream.bybit.com/v5/public/spot-tickers",
          "description": "Ticker updates"
        },
        {
          "name": "subscribe_account",
          "endpoint": "wss://stream.bybit.com/v5/private",
          "description": "Account and order updates (requires auth)"
        }
      ]
    },
    {
      "category": "Advanced Trading",
      "description": "Order types and strategies",
      "items": [
        {
          "name": "OCO orders",
          "description": "One Cancels the Other orders (limit + stop)"
        },
        {
          "name": "Trailing Stop",
          "description": "Set trailing stop orders"
        },
        {
          "name": "Conditional Orders",
          "description": "Stop loss, take profit, and other conditional orders"
        }
      ]
    },
    {
      "category": "Risk and Margin Management",
      "description": "Manage leverage, margin, and risk controls",
      "items": [
        {
          "name": "set_mmp",
          "endpoint": "/v2/private/mmp",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "qty_limit", "type": "number"},
            {"name": "delta_limit", "type": "number"}
          ],
          "description": "Set maximum market position limits"
        },
        {
          "name": "switch_position_mode",
          "endpoint": "/v2/private/position/switch-mode",
          "method": "POST",
          "auth_required": true,
          "params": [
            {"name": "symbol", "type": "string"},
            {"name": "mode", "type": "string", "enum": ["OneWay", "Hedge"]}
          ],
          "description": "Switch position mode"
        }
      ]
    },
    {
      "category": "Utilities & Misc",
      "description": "Helpful functions and info",
      "items": [
        {
          "name": "calculate_spread",
          "description": "Calculate bid-ask spread"
        },
        {
          "name": "calculate_position_size",
          "description": "Calculate position size based on risk parameters"
        }
      ]
    }
  ],
  "notes": [
    "Replace placeholders with your actual API keys and parameters.",
    "Implement rate limiting to avoid API bans.",
    "Use WebSocket heartbeat/ping to keep streams alive.",
    "Handle reconnections gracefully.",
    "Securely store API keys.",
    "Use try-except to handle API errors."
  ]
}
```json
{
  "pybit_bybit_bot_functions": {
    "overview": "A comprehensive list of typical functions used in a PyBit/Bybit trading bot, structured in JSON format.",
    "functions": [
      {
        "name": "connect_websocket",
        "description": "Establishes websocket connection to Bybit for real-time data streaming.",
        "parameters": [
          "endpoint: str",
          "on_message: callable",
          "on_error: callable",
          "on_close: callable"
        ],
        "returns": "WebSocket connection object"
      },
      {
        "name": "subscribe_to_channel",
        "description": "Subscribes to a specific data channel (e.g., order book, trades).",
        "parameters": [
          "ws: websocket object",
          "channel: str"
        ],
        "returns": "None"
      },
      {
        "name": "send_order",
        "description": "Places a new order (market, limit, stop, etc.) on Bybit.",
        "parameters": [
          "symbol: str",
          "side: str ('Buy' or 'Sell')",
          "order_type: str ('Market', 'Limit', etc.)",
          "quantity: float",
          "price: float (optional for market orders)",
          "params: dict (additional optional params)"
        ],
        "returns": "order response dict"
      },
      {
        "name": "cancel_order",
        "description": "Cancels an existing order by order ID.",
        "parameters": [
          "symbol: str",
          "order_id: str"
        ],
        "returns": "cancel response dict"
      },
      {
        "name": "get_open_orders",
        "description": "Retrieves all open orders for a symbol.",
        "parameters": [
          "symbol: str"
        ],
        "returns": "list of open order dicts"
      },
      {
        "name": "get_account_balance",
        "description": "Fetches account balance and margin info.",
        "parameters": [],
        "returns": "balance dict"
      },
      {
        "name": "get_market_price",
        "description": "Gets the latest market price for a symbol.",
        "parameters": [
          "symbol: str"
        ],
        "returns": "price: float"
      },
      {
        "name": "websocket_listener",
        "description": "Main loop to listen and process websocket messages.",
        "parameters": [
          "ws: websocket object"
        ],
        "returns": "None"
      },
      {
        "name": "process_incoming_data",
        "description": "Processes incoming data messages from websocket.",
        "parameters": [
          "message: dict"
        ],
        "returns": "None"
      },
      {
        "name": "initialize_bot",
        "description": "Sets up API keys, parameters, and initial state.",
        "parameters": [
          "api_key: str",
          "api_secret: str",
          "symbol: str",
          "leverage: int"
        ],
        "returns": "None"
      },
      {
        "name": "run_trading_loop",
        "description": "Main trading loop executing strategy logic periodically.",
        "parameters": [
          "interval: float"
        ],
        "returns": "None"
      },
      {
        "name": "stop_bot",
        "description": "Gracefully stops trading, closes websocket, and saves state.",
        "parameters": [],
        "returns": "None"
      }
    ]
  }
}
```
```json
{
  "improvements_and_updates": [
    "Implement detailed logging with different levels (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    "Add exception handling with try-except blocks around API calls and websocket events.",
    "Use environment variables or config files for API keys and sensitive info.",
    "Implement reconnection logic for websocket drops with exponential backoff.",
    "Add rate limiting and request throttling to avoid API bans.",
    "Integrate a configuration management system for dynamic parameter updates.",
    "Use asyncio or threading for non-blocking websocket handling and trading logic.",
    "Add a heartbeat or ping system to ensure websocket connection health.",
    "Implement a comprehensive order management system with order status tracking.",
    "Add position management with safeguards against over-leverage and margin calls.",
    "Incorporate a strategy backtesting module for parameter optimization.",
    "Develop a notification system (email, Telegram, Discord) for critical events.",
    "Implement a GUI or dashboard for real-time monitoring of bot status and metrics.",
    "Add unit tests and integration tests for core functions.",
    "Use a database or persistent storage for logging trades and state for recovery.",
    "Implement a graceful shutdown procedure to close open orders and save state.",
    "Add support for multiple symbols and simultaneous trading pairs.",
    "Optimize API call frequency and data handling for performance.",
    "Include a risk management module to set stop-loss and take-profit levels.",
    "Implement a sliding window or moving average strategy for decision making.",
    "Add parameter validation and input sanitization to prevent errors.",
    "Incorporate version control metadata and logging for deployment tracking.",
    "Use decorators or context managers to handle repetitive setup and teardown tasks.",
    "Add a configuration reload feature to update parameters without restarting.",
    "Implement a multi-threaded or asynchronous architecture for scalability.",
    "Regularly update the API endpoints and handle deprecations."
  ],
  "integration": "The following is an integrated, high-level pseudocode outline demonstrating how to incorporate some of these improvements into a PyBit/Bybit trading bot architecture."
}
```

```python
# Example pseudocode integrating improvements

import os
import logging
import json
import asyncio
import time
from threading import Thread
from bybit import bybit  # Hypothetical library
import websockets

# Setup logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Load configuration from environment variables or config file
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'BTCUSD'
LEVERAGE = 10

# Initialize API client
client = bybit(test=False, api_key=API_KEY, api_secret=API_SECRET)

class MarketMakerBot:
    def __init__(self, symbol, leverage=10):
        self.symbol = symbol
        self.leverage = leverage
        self.ws = None
        self.running = False
        self.order_ids = []
        self.balance = {}
        self.position = 0
        self.setup()

    def setup(self):
        try:
            # Set leverage
            client.set_leverage(symbol=self.symbol, leverage=self.leverage)
            logging.info(f"Leverage set to {self.leverage} for {self.symbol}")
            # Fetch initial balance
            self.balance = client.get_wallet_balance()
            logging.info(f"Initial balance: {self.balance}")
        except Exception as e:
            logging.exception("Error during setup: %s", e)

    async def connect_websocket(self):
        try:
            # Connect to websocket
            self.ws = await websockets.connect('wss://stream.bybit.com/realtime')
            await self.subscribe_channels()
            logging.info("Websocket connected and subscribed.")
        except Exception as e:
            logging.exception("Websocket connection error: %s", e)

    async def subscribe_channels(self):
        try:
            # Subscribe to order book and trades
            subscribe_message = json.dumps({
                "op": "subscribe",
                "args": [f"orderBookL2_25.{self.symbol}", f"trade.{self.symbol}"]
            })
            await self.ws.send(subscribe_message)
            logging.info("Subscribed to channels.")
        except Exception as e:
            logging.exception("Subscription error: %s", e)

    async def websocket_listener(self):
        while self.running:
            try:
                message = await self.ws.recv()
                self.process_incoming_data(json.loads(message))
            except websockets.ConnectionClosed:
                logging.warning("Websocket connection closed, attempting to reconnect...")
                await asyncio.sleep(5)
                await self.connect_websocket()
            except Exception as e:
                logging.exception("Error in websocket listener: %s", e)

    def process_incoming_data(self, data):
        try:
            # Process market data
            if 'data' in data:
                # Example: update order book, trade data
                pass
        except Exception as e:
            logging.exception("Error processing data: %s", e)

    def place_order(self, side, quantity, price=None, order_type='Market'):
        try:
            # Place order with error handling
            order_params = {
                "symbol": self.symbol,
                "side": side,
                "order_type": order_type,
                "qty": quantity
            }
            if price:
                order_params["price"] = price
            response = client.place_active_order(**order_params)
            self.order_ids.append(response['order_id'])
            logging.info(f"Placed {order_type} order: {response}")
        except Exception as e:
            logging.exception("Order placement failed: %s", e)

    def cancel_order(self, order_id):
        try:
            response = client.cancel_active_order(symbol=self.symbol, order_id=order_id)
            logging.info(f"Cancelled order {order_id}: {response}")
        except Exception as e:
            logging.exception("Order cancellation failed: %s", e)

    def get_open_orders(self):
        try:
            return client.get_active_orders(symbol=self.symbol)
        except Exception as e:
            logging.exception("Fetching open orders failed: %s", e)
            return []

    def update_position(self):
        try:
            position_data = client.get_position(symbol=self.symbol)
            self.position = position_data['size']
            logging.info(f"Updated position: {self.position}")
        except Exception as e:
            logging.exception("Updating position failed: %s", e)

    def risk_management(self):
        # Implement stop-loss, take-profit, max position size
        pass

    def trading_strategy(self):
        # Example: moving average crossover or other strategy
        pass

    def run(self):
        self.running = True
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.connect_websocket())
            asyncio.ensure_future(self.websocket_listener())
            # Main trading loop
            while self.running:
                self.update_position()
                self.risk_management()
                self.trading_strategy()
                time.sleep(1)  # Adjust as needed
        except KeyboardInterrupt:
            logging.info("Shutdown signal received.")
        finally:
            self.stop()

    def stop(self):
        self.running = False
        # Close websocket and cleanup
        if self.ws:
            asyncio.ensure_future(self.ws.close())
        # Cancel open orders if needed
        for order_id in self.order_ids:
            self.cancel_order(order_id)
        logging.info("Bot stopped gracefully.")

# Instantiate and run the bot
if __name__ == '__main__':
    bot = MarketMakerBot(SYMBOL, LEVERAGE)
    bot.run()
```

**Summary:**  
This code outline demonstrates a comprehensive, integrated approach with multiple improvements including logging, exception handling, reconnection logic, API key management, order handling, and graceful shutdown. For a full implementation, you'd expand each placeholder with actual trading logic and data processing, following the improvements listed earlier.
