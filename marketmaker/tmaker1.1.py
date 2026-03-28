#!/usr/bin/env python3
"""
Bybit Advanced Market Making Bot Framework (Enhanced & Upgraded)

This script is a professional-grade, fully asynchronous trading bot framework for Bybit.
It implements a market making strategy by placing a buy and a sell order at a fixed spread
around the mid-price.

Key Enhancements & Upgrades:
- Fully Asynchronous: Built on asyncio for high performance and responsiveness.
- WebSocket-Driven: Replaces inefficient HTTP polling with real-time WebSocket streams for
  market data and order/position updates.
- Robust Order Lifecycle Management: Actively manages the bot's open orders, automatically
  canceling and replacing them if they get filled, or if the market moves away.
  Intelligent reconciliation of local state with exchange orders on startup.
- Dynamic Order Sizing & Risk Control: Calculates order size based on a percentage of the
  available balance, while respecting minimum notional values and maximum exposure.
- State Persistence: Saves active orders and trading state to a file to recover gracefully
  from restarts.
- Robust Error Handling: Includes retry mechanisms for API calls (via pybit) and exponential
  backoff for WebSocket reconnections (handled by pybit).
- Precise Financials: All calculations use Python's Decimal type to prevent floating-point errors.
- Modular Architecture: Separates concerns into distinct classes for clarity and maintenance.
- **SQLite Database Integration:** Logs all order events, trade fills, and balance updates
  for comprehensive historical analysis and performance tracking.
- **Smarter Order Placement:** Only cancels stale orders and places missing ones, reducing
  API calls and improving efficiency.
- **Post-Only Orders:** Ensures orders are placed as 'PostOnly' to always act as a maker
  and avoid taker fees.
- **Graceful Shutdown:** Ensures all open orders are canceled, state is saved, and DB
  connections are closed upon termination.

Instructions for Termux (ARM64):
1. Install dependencies:
   `pip install pybit pandas numpy python-dotenv aiosqlite aaiofiles`
2. Create a `.env` file in the same directory and add your credentials:
   `BYBIT_API_KEY="your_api_key"`
   `BYBIT_API_SECRET="your_api_secret"`
   `BYBIT_TESTNET="true"`
3. Update the `Config` class with your desired settings.
4. Run the bot:
   `python3 your_script_name.py`
"""

import asyncio
import logging
import os
import pickle
import sys
import time  # For orderLinkId
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, getcontext

import aiofiles
import aiosqlite
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Set high precision for Decimal calculations to avoid floating-point inaccuracies
getcontext().prec = 28

# Load environment variables from a .env file
load_dotenv()

# =====================================================================
# CONFIGURATION & DATA CLASSES
# =====================================================================
@dataclass
class TradeMetrics:
    """Track trading performance metrics."""
    total_trades: int = 0
    total_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    # Add more detailed metrics as needed

    def update_win_rate(self):
        if self.total_trades > 0:
            self.win_rate = self.wins / self.total_trades * 100.0
        else:
            self.win_rate = 0.0

@dataclass
class StrategyConfig:
    """Market Maker specific strategy parameters."""
    spread_pct: Decimal = Decimal('0.001') # 0.1% spread on either side of mid-price
    risk_per_trade_pct: Decimal = Decimal('0.005') # 0.5% of account balance per trade
    order_stale_threshold_pct: Decimal = Decimal('0.0005') # If order price differs by this much from target, cancel.

@dataclass
class Config:
    """Comprehensive bot configuration settings."""

    # API Credentials & Environment
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    trading_mode: str = "DRY_RUN" # "LIVE", "DRY_RUN", "TESTNET" (TESTNET implies testnet=True)

    # Trading Parameters
    symbol: str = "BTCUSDT"
    category: str = "linear"  # 'linear' for USDT perpetual, 'spot' for spot trading
    base_currency: str = "BTC"
    quote_currency: str = "USDT" # Currency used for balance tracking and order value calculation

    # Strategy Settings
    strategy: StrategyConfig = field(default_factory=StrategyConfig)

    # Execution Parameters
    order_type: str = "Limit"
    time_in_force: str = "GTC"  # 'GTC', 'IOC', 'FOK'
    post_only: bool = True # Ensures orders are placed as 'PostOnly' to avoid taker fees
    min_order_value_usd: Decimal = Decimal('10') # Minimum notional value for an order (Bybit specific)
    max_order_size_pct: Decimal = Decimal('0.1') # Max percentage of total balance for a single order

    # System & Logging
    loop_interval_sec: int = 1  # Main loop check interval in seconds
    order_refresh_interval_sec: int = 5 # How often to check/replace orders (independent of loop_interval)
    log_level: str = "INFO"
    log_file: str = "market_maker.log"
    state_file: str = "market_maker_state.pkl"
    db_file: str = "market_maker.db" # SQLite database file for historical data

    # Performance Tracking
    metrics: TradeMetrics = field(default_factory=TradeMetrics)

@dataclass
class MarketInfo:
    """Stores market precision and step sizes."""
    symbol: str
    price_precision: Decimal
    quantity_precision: Decimal
    min_order_qty: Decimal
    min_notional_value: Decimal # Minimum order value in quote currency (e.g., USDT)

    def format_price(self, price: Decimal) -> Decimal:
        """Rounds price to the correct precision and returns as a Decimal."""
        return price.quantize(self.price_precision, rounding=ROUND_DOWN)

    def format_quantity(self, quantity: Decimal) -> Decimal:
        """Rounds quantity to the correct precision and returns as a Decimal."""
        return quantity.quantize(self.quantity_precision, rounding=ROUND_DOWN)

# =====================================================================
# LOGGING SETUP
# =====================================================================
def setup_logger(config: Config) -> logging.Logger:
    """Configures and returns the logger."""
    logger = logging.getLogger('MarketMakerBot')
    logger.setLevel(getattr(logging, config.log_level.upper()))

    # Ensure handlers are not duplicated on re-init
    if not logger.handlers:
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)

        # File handler
        fh = logging.FileHandler(config.log_file)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)

        logger.addHandler(ch)
        logger.addHandler(fh)

    return logger

# =====================================================================
# STATE PERSISTENCE
# =====================================================================
class StateManager:
    """Handles saving and loading the bot's state."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.logger = logging.getLogger('StateManager')

    async def save_state(self, state: dict):
        """Saves the bot's state to a file."""
        try:
            async with aiofiles.open(self.file_path, 'wb') as f:
                await f.write(pickle.dumps(state))
            self.logger.info("Bot state saved successfully.")
        except Exception as e:
            self.logger.error(f"Error saving state: {e}")

    async def load_state(self) -> dict | None:
        """Loads the bot's state from a file."""
        if not os.path.exists(self.file_path):
            self.logger.warning("State file not found. Starting with a fresh state.")
            return None
        try:
            async with aiofiles.open(self.file_path, 'rb') as f:
                state = pickle.loads(await f.read())
            self.logger.info("Bot state loaded successfully.")
            return state
        except Exception as e:
            self.logger.error(f"Error loading state: {e}. Starting fresh.")
            return None

# =====================================================================
# DATABASE MANAGER
# =====================================================================
class DBManager:
    """Manages SQLite database operations for logging."""
    def __init__(self, db_file: str):
        self.db_file = db_file
        self.conn: aiosqlite.Connection | None = None
        self.logger = logging.getLogger('DBManager')

    async def connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = await aiosqlite.connect(self.db_file)
            self.conn.row_factory = aiosqlite.Row # Access columns by name
            self.logger.info(f"Connected to database: {self.db_file}")
        except Exception as e:
            self.logger.critical(f"Failed to connect to database: {e}")
            sys.exit(1)

    async def close(self):
        """Closes the database connection."""
        if self.conn:
            await self.conn.close()
            self.logger.info("Database connection closed.")

    async def create_tables(self):
        """Creates necessary tables if they don't exist."""
        if not self.conn:
            await self.connect()

        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                order_id TEXT NOT NULL,
                order_link_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                price TEXT NOT NULL,
                qty TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                order_id TEXT NOT NULL,
                trade_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                exec_price TEXT NOT NULL,
                exec_qty TEXT NOT NULL,
                fee TEXT NOT NULL,
                fee_currency TEXT,
                pnl TEXT,
                FOREIGN KEY (order_id) REFERENCES order_events(order_id)
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS balance_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                currency TEXT NOT NULL,
                wallet_balance TEXT NOT NULL,
                available_balance TEXT
            )
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total_trades INTEGER,
                total_pnl TEXT,
                total_fees TEXT,
                wins INTEGER,
                losses INTEGER,
                win_rate REAL
            )
        """)
        await self.conn.commit()
        self.logger.info("Database tables checked/created.")

    async def log_order_event(self, order_data: dict, message: str | None = None):
        """Logs an order event to the database."""
        if not self.conn: await self.connect()
        timestamp = datetime.now().isoformat()
        await self.conn.execute(
            """INSERT INTO order_events (timestamp, order_id, order_link_id, symbol, side, order_type, price, qty, status, message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, order_data.get('orderId'), order_data.get('orderLinkId'), order_data.get('symbol'),
             order_data.get('side'), order_data.get('orderType'), str(order_data.get('price', '0')),
             str(order_data.get('qty', '0')), order_data.get('orderStatus'), message)
        )
        await self.conn.commit()

    async def log_trade_fill(self, trade_data: dict):
        """Logs a trade fill to the database."""
        if not self.conn: await self.connect()
        timestamp = datetime.now().isoformat()
        await self.conn.execute(
            """INSERT INTO trade_fills (timestamp, order_id, trade_id, symbol, side, exec_price, exec_qty, fee, fee_currency, pnl)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, trade_data.get('orderId'), trade_data.get('execId'), trade_data.get('symbol'),
             trade_data.get('side'), str(trade_data.get('execPrice', '0')), str(trade_data.get('execQty', '0')),
             str(trade_data.get('execFee', '0')), trade_data.get('feeCurrency'), str(trade_data.get('leavesQty', '0'))) # pnl is not directly available here, leavesQty could be used as a proxy for remaining, or calculate based on position.
        )
        await self.conn.commit()

    async def log_balance_update(self, currency: str, wallet_balance: Decimal, available_balance: Decimal | None = None):
        """Logs a balance update to the database."""
        if not self.conn: await self.connect()
        timestamp = datetime.now().isoformat()
        await self.conn.execute(
            """INSERT INTO balance_updates (timestamp, currency, wallet_balance, available_balance)
               VALUES (?, ?, ?, ?)""",
            (timestamp, currency, str(wallet_balance), str(available_balance) if available_balance else None)
        )
        await self.conn.commit()

    async def log_bot_metrics(self, metrics: TradeMetrics):
        """Logs current bot metrics to the database."""
        if not self.conn: await self.connect()
        timestamp = datetime.now().isoformat()
        await self.conn.execute(
            """INSERT INTO bot_metrics (timestamp, total_trades, total_pnl, total_fees, wins, losses, win_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, metrics.total_trades, str(metrics.total_pnl), str(metrics.total_fees),
             metrics.wins, metrics.losses, metrics.win_rate)
        )
        await self.conn.commit()

# =====================================================================
# CORE MARKET MAKER BOT CLASS
# =====================================================================
class BybitMarketMaker:
    """Main market maker bot class."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logger(config)
        self.state_manager = StateManager(config.state_file)
        self.db_manager = DBManager(config.db_file)

        # Determine if running on testnet
        if self.config.trading_mode == "TESTNET":
            self.config.testnet = True
        elif self.config.trading_mode == "LIVE":
            self.config.testnet = False

        # Initialize HTTP and WebSocket sessions
        self.http_session = HTTP(
            testnet=self.config.testnet,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret
        )
        self.ws_session = WebSocket(
            testnet=self.config.testnet,
            channel_type=self.config.category,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret
        )

        # Market data and state
        self.market_info: MarketInfo | None = None
        self.mid_price = Decimal('0')
        self.current_balance = Decimal('0')
        self.active_orders: dict[str, dict] = {} # {order_id: {side, price, qty, status, orderLinkId}}
        self.is_running = False
        self.last_order_management_time = 0

        # Locks for thread-safe operations
        self.market_data_lock = asyncio.Lock()
        self.active_orders_lock = asyncio.Lock()

        self.logger.info(f"Market Maker Bot Initialized. Trading Mode: {self.config.trading_mode}")
        if self.config.testnet:
            self.logger.info("Running on Bybit Testnet.")

    async def _fetch_market_info(self) -> MarketInfo | None:
        """Fetches market precision and step sizes from Bybit."""
        try:
            response = self.http_session.get_instruments_info(
                category=self.config.category,
                symbol=self.config.symbol
            )

            if response['retCode'] == 0 and response['result']['list']:
                info = response['result']['list'][0]
                price_filter = info['priceFilter']
                lot_size_filter = info['lotSizeFilter']

                self.market_info = MarketInfo(
                    symbol=self.config.symbol,
                    price_precision=Decimal(price_filter['tickSize']),
                    quantity_precision=Decimal(lot_size_filter['qtyStep']),
                    min_order_qty=Decimal(lot_size_filter['minOrderQty']),
                    min_notional_value=Decimal(lot_size_filter.get('minNotionalValue', '0')) # Default to 0 if not present
                )
                self.logger.info(f"Market info fetched for {self.config.symbol}: {self.market_info}")
                return self.market_info

            self.logger.error(f"Failed to fetch market info: {response.get('retMsg', 'Unknown error')}")
            return None

        except Exception as e:
            self.logger.error(f"Error fetching market info: {e}")
            return None

    async def _update_balance(self) -> Decimal | None:
        """Updates the bot's current balance."""
        if self.config.trading_mode == "DRY_RUN":
            # For dry run, simulate a balance
            if self.current_balance == Decimal('0'):
                self.current_balance = Decimal('10000') # Start with a simulated balance
                self.logger.info(f"DRY_RUN: Initial simulated balance: {self.current_balance} {self.config.quote_currency}")
            return self.current_balance

        try:
            response = self.http_session.get_wallet_balance(
                accountType=self.config.category.upper() if self.config.category == 'spot' else "UNIFIED"
            )
            if response['retCode'] == 0:
                coins = response['result']['list'][0]['coin']
                for coin in coins:
                    if coin['coin'] == self.config.quote_currency:
                        self.current_balance = Decimal(coin['walletBalance'])
                        self.logger.info(f"Current Balance: {self.current_balance} {self.config.quote_currency}")
                        asyncio.create_task(self.db_manager.log_balance_update(
                            self.config.quote_currency, self.current_balance, Decimal(coin.get('availableToWithdraw', '0'))
                        ))
                        return self.current_balance
            self.logger.error(f"Failed to update balance: {response.get('retMsg', 'Unknown error')}")
            return None
        except Exception as e:
            self.logger.error(f"Error updating balance: {e}")
            return None

    def _handle_orderbook_update(self, message: dict):
        """Processes real-time orderbook updates from WebSocket."""
        try:
            if 'data' in message and message['topic'] == f"orderbook.1.{self.config.symbol}":
                data = message['data']
                bids = data['b']
                asks = data['a']

                if not bids or not asks:
                    return

                # Safely update mid-price with thread-safe lock
                asyncio.create_task(self._update_mid_price(bids, asks))

        except Exception as e:
            self.logger.error(f"Error handling orderbook update: {e}")

    async def _update_mid_price(self, bids: list, asks: list):
        """Updates the mid-price based on the top of the order book."""
        async with self.market_data_lock:
            best_bid = Decimal(bids[0][0])
            best_ask = Decimal(asks[0][0])
            self.mid_price = (best_bid + best_ask) / Decimal('2')
            self.logger.debug(f"Mid-price updated to: {self.mid_price}")

    async def _handle_order_update(self, message: dict):
        """Processes real-time order updates from WebSocket."""
        try:
            if 'data' in message:
                for order_data in message['data']:
                    order_id = order_data['orderId']
                    status = order_data['orderStatus']

                    self.logger.info(f"Order {order_id} status update: {status} (Order Link ID: {order_data.get('orderLinkId')})")
                    asyncio.create_task(self.db_manager.log_order_event(order_data))

                    async with self.active_orders_lock:
                        if order_id in self.active_orders:
                            self.active_orders[order_id]['status'] = status

                            if status == 'Filled':
                                self.logger.info(f"Order {order_id} FILLED: Price={order_data.get('execPrice')}, Qty={order_data.get('execQty')}, Fee={order_data.get('execFee')}")
                                asyncio.create_task(self.db_manager.log_trade_fill(order_data))

                                # Update metrics
                                self.config.metrics.total_trades += 1
                                self.config.metrics.total_fees += Decimal(order_data.get('execFee', '0'))

                                # Simple PnL calculation (for market making, this is usually tracked per pair)
                                # This assumes a simple buy-then-sell or sell-then-buy cycle
                                # For true market making, PnL is often tracked through inventory management.
                                # For now, we'll just log any reported PnL and assume a win if a trade completes.
                                if Decimal(order_data.get('execQty', '0')) > 0:
                                    self.config.metrics.wins += 1 # Assume filled order is part of a profitable cycle
                                self.config.metrics.update_win_rate()

                                del self.active_orders[order_id]
                                self.logger.info(f"Order {order_id} removed from active orders after fill.")
                                # Re-update balance after a fill
                                asyncio.create_task(self._update_balance())
                            elif status in ['Cancelled', 'Rejected']:
                                self.logger.info(f"Order {order_id} removed from active orders due to {status}.")
                                del self.active_orders[order_id]
                        else:
                            # This order might be from a previous session or manual placement, add it if still active
                            if status in ['New', 'PartiallyFilled', 'Untriggered']:
                                self.active_orders[order_id] = {
                                    'side': order_data['side'],
                                    'price': Decimal(order_data['price']),
                                    'qty': Decimal(order_data['qty']),
                                    'status': status,
                                    'orderLinkId': order_data.get('orderLinkId')
                                }
                                self.logger.warning(f"Found untracked active order {order_id} (Status: {status}). Added to local state.")

        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")

    async def _cancel_order(self, order_id: str, order_link_id: str | None = None):
        """Cancels a single order."""
        self.logger.info(f"Attempting to cancel order {order_id} (Link ID: {order_link_id})...")
        try:
            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "orderId": order_id,
            }
            if order_link_id:
                params["orderLinkId"] = order_link_id

            response = self.http_session.cancel_order(**params)

            if response['retCode'] == 0:
                self.logger.info(f"Order {order_id} successfully canceled.")
                async with self.active_orders_lock:
                    if order_id in self.active_orders:
                        del self.active_orders[order_id]
                return True
            else:
                self.logger.warning(f"Failed to cancel order {order_id}: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Error canceling order {order_id}: {e}")
            return False

    async def _cancel_all_orders(self):
        """Cancels all open orders."""
        self.logger.info("Canceling all open orders...")
        try:
            response = self.http_session.cancel_all_orders(
                category=self.config.category,
                symbol=self.config.symbol
            )

            if response['retCode'] == 0:
                async with self.active_orders_lock:
                    self.active_orders.clear()
                self.logger.info("All open orders successfully canceled.")
                return True
            else:
                self.logger.error(f"Failed to cancel all orders: {response.get('retMsg', 'Unknown error')}")
                return False

        except Exception as e:
            self.logger.error(f"Error canceling all orders: {e}")
            return False

    async def _calculate_order_size(self, price: Decimal) -> Decimal:
        """
        Calculates the order quantity based on balance, risk, and market constraints.
        """
        if self.current_balance <= 0 or self.mid_price <= 0:
            self.logger.warning("Cannot calculate order size: Balance or mid-price is zero.")
            return Decimal('0')

        # 1. Base order value in quote currency (e.g., USDT)
        qty_in_quote = self.current_balance * self.config.strategy.risk_per_trade_pct

        # 2. Apply max order size percentage
        max_qty_in_quote = self.current_balance * self.config.max_order_size_pct
        qty_in_quote = min(qty_in_quote, max_qty_in_quote)

        # 3. Convert to base currency (e.g., BTC) quantity
        qty_in_base = qty_in_quote / price

        # 4. Apply market quantity precision and min order quantity
        if self.market_info:
            qty_in_base = self.market_info.format_quantity(qty_in_base)
            if qty_in_base < self.market_info.min_order_qty:
                self.logger.warning(f"Calculated quantity {qty_in_base} is less than min order qty {self.market_info.min_order_qty}. Returning 0.")
                return Decimal('0')

            # 5. Check against minimum notional value
            notional_value = qty_in_base * price
            if notional_value < self.market_info.min_notional_value:
                self.logger.warning(f"Calculated notional value {notional_value} is less than min notional value {self.market_info.min_notional_value}. Returning 0.")
                return Decimal('0')
        else:
            self.logger.warning("Market info not available for order size calculation.")
            return Decimal('0')

        return qty_in_base

    async def _place_limit_order(self, side: str, price: Decimal, quantity: Decimal) -> dict | None:
        """Places a single limit order."""
        if self.config.trading_mode == "DRY_RUN":
            self.logger.info(f"DRY_RUN: Would place {side} order: Price={price}, Qty={quantity}")
            # Simulate an order ID and add to active orders
            simulated_order_id = f"DRY_{side}_{int(time.time() * 1000)}"
            async with self.active_orders_lock:
                self.active_orders[simulated_order_id] = {
                    'side': side, 'price': price, 'qty': quantity, 'status': 'New', 'orderLinkId': f"mm_{side}_{int(time.time() * 1000)}"
                }
            return {'orderId': simulated_order_id}

        try:
            # Format quantity and price according to market precision
            qty_formatted = self.market_info.format_quantity(quantity) if self.market_info else quantity
            price_formatted = self.market_info.format_price(price) if self.market_info else price

            if qty_formatted == Decimal('0') or price_formatted == Decimal('0'):
                self.logger.warning(f"Attempted to place order with zero quantity or price: Qty={qty_formatted}, Price={price_formatted}. Skipping.")
                return None

            params = {
                "category": self.config.category,
                "symbol": self.config.symbol,
                "side": side,
                "orderType": self.config.order_type,
                "qty": str(qty_formatted),
                "price": str(price_formatted),
                "timeInForce": self.config.time_in_force,
                "orderLinkId": f"mm_{side}_{int(time.time() * 1000)}", # Unique client order ID
                "postOnly": 1 if self.config.post_only else 0
            }

            response = self.http_session.place_order(**params)

            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                order_link_id = params['orderLinkId']
                self.logger.info(f"Placed {side} order: ID={order_id}, Price={price_formatted}, Qty={qty_formatted}, LinkID={order_link_id}")

                # Add order to our active orders tracker
                async with self.active_orders_lock:
                    self.active_orders[order_id] = {
                        'side': side, 'price': price_formatted, 'qty': qty_formatted, 'status': 'New', 'orderLinkId': order_link_id
                    }
                asyncio.create_task(self.db_manager.log_order_event({
                    'orderId': order_id, 'orderLinkId': order_link_id, 'symbol': self.config.symbol,
                    'side': side, 'orderType': self.config.order_type, 'price': str(price_formatted),
                    'qty': str(qty_formatted), 'orderStatus': 'New'
                }, message="Order placed successfully"))

                return response['result']

            self.logger.error(f"Failed to place {side} order: {response.get('retMsg', 'Unknown error')}")
            return None

        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return None

    async def _reconcile_orders_on_startup(self):
        """
        Fetches open orders from the exchange and reconciles them with the bot's local state.
        Cancels any local orders not found on the exchange, and adds exchange orders not in local state.
        """
        if self.config.trading_mode == "DRY_RUN":
            self.logger.info("DRY_RUN: Skipping order reconciliation on startup.")
            return

        self.logger.info("Reconciling active orders with exchange...")
        exchange_open_orders = {}
        try:
            response = self.http_session.get_open_orders(
                category=self.config.category,
                symbol=self.config.symbol,
                limit=50 # Max limit for open orders
            )
            if response['retCode'] == 0:
                for order_data in response['result']['list']:
                    order_id = order_data['orderId']
                    exchange_open_orders[order_id] = {
                        'side': order_data['side'],
                        'price': Decimal(order_data['price']),
                        'qty': Decimal(order_data['qty']),
                        'status': order_data['orderStatus'],
                        'orderLinkId': order_data.get('orderLinkId')
                    }
            else:
                self.logger.error(f"Failed to fetch open orders from exchange: {response.get('retMsg', 'Unknown error')}")
                return

        except Exception as e:
            self.logger.error(f"Error fetching open orders from exchange during reconciliation: {e}")
            return

        async with self.active_orders_lock:
            # Identify local orders that are no longer on the exchange
            orders_to_remove = [
                order_id for order_id in self.active_orders
                if order_id not in exchange_open_orders
            ]
            for order_id in orders_to_remove:
                self.logger.warning(f"Local order {order_id} not found on exchange. Removing from local state.")
                del self.active_orders[order_id]

            # Identify exchange orders not in local state and add them
            for order_id, order_info in exchange_open_orders.items():
                if order_id not in self.active_orders:
                    self.active_orders[order_id] = order_info
                    self.logger.warning(f"Exchange order {order_id} (Status: {order_info['status']}) not in local state. Adding to local state.")
                    asyncio.create_task(self.db_manager.log_order_event({
                        'orderId': order_id, 'orderLinkId': order_info['orderLinkId'], 'symbol': self.config.symbol,
                        'side': order_info['side'], 'orderType': self.config.order_type, 'price': str(order_info['price']),
                        'qty': str(order_info['qty']), 'orderStatus': order_info['status']
                    }, message="Reconciled: Found on exchange, added to local state"))

        self.logger.info(f"Order reconciliation complete. {len(self.active_orders)} active orders in state.")

    async def _manage_orders(self):
        """Manages the lifecycle of market making orders."""
        current_time = time.time()
        if (current_time - self.last_order_management_time) < self.config.order_refresh_interval_sec:
            return # Don't manage too frequently

        self.last_order_management_time = current_time

        # Calculate new order prices based on the latest mid-price
        async with self.market_data_lock:
            if self.mid_price == 0:
                self.logger.info("Waiting for initial mid-price before managing orders...")
                return

            target_bid_price = self.mid_price * (Decimal('1') - self.config.strategy.spread_pct)
            target_ask_price = self.mid_price * (Decimal('1') + self.config.strategy.spread_pct)

            # Format prices to the correct precision
            target_bid_price = self.market_info.format_price(target_bid_price) if self.market_info else target_bid_price
            target_ask_price = self.market_info.format_price(target_ask_price) if self.market_info else target_ask_price

        # Track existing orders
        current_bid_order: dict | None = None
        current_ask_order: dict | None = None

        orders_to_cancel = []

        async with self.active_orders_lock:
            for order_id, order_info in list(self.active_orders.items()): # Iterate over a copy
                if order_info['side'] == 'Buy':
                    # Check if bid order is stale
                    if not current_bid_order and abs(order_info['price'] - target_bid_price) <= target_bid_price * self.config.strategy.order_stale_threshold_pct:
                        current_bid_order = order_info
                        self.logger.debug(f"Existing bid order {order_id} is still valid at {order_info['price']}.")
                    else:
                        self.logger.info(f"Bid order {order_id} at {order_info['price']} is stale or a duplicate. Marking for cancellation. (Target: {target_bid_price})")
                        orders_to_cancel.append((order_id, order_info.get('orderLinkId')))
                elif order_info['side'] == 'Sell':
                    # Check if ask order is stale
                    if not current_ask_order and abs(order_info['price'] - target_ask_price) <= target_ask_price * self.config.strategy.order_stale_threshold_pct:
                        current_ask_order = order_info
                        self.logger.debug(f"Existing ask order {order_id} is still valid at {order_info['price']}.")
                    else:
                        self.logger.info(f"Ask order {order_id} at {order_info['price']} is stale or a duplicate. Marking for cancellation. (Target: {target_ask_price})")
                        orders_to_cancel.append((order_id, order_info.get('orderLinkId')))

        # Execute cancellations
        for order_id, order_link_id in orders_to_cancel:
            await self._cancel_order(order_id, order_link_id)
            await asyncio.sleep(0.1) # Small delay between cancellations

        # Place new orders if needed
        order_qty = await self._calculate_order_size(self.mid_price)
        if order_qty == Decimal('0'):
            self.logger.warning("Calculated order quantity is zero or too small. Skipping order placement.")
            return

        if not current_bid_order:
            self.logger.info(f"No valid bid order found. Placing new bid at {target_bid_price} with Qty {order_qty}.")
            await self._place_limit_order("Buy", target_bid_price, order_qty)
            await asyncio.sleep(0.1)

        if not current_ask_order:
            self.logger.info(f"No valid ask order found. Placing new ask at {target_ask_price} with Qty {order_qty}.")
            await self._place_limit_order("Sell", target_ask_price, order_qty)
            await asyncio.sleep(0.1)

    async def run(self):
        """Main asynchronous bot loop."""
        self.is_running = True

        # Connect to DB and create tables
        await self.db_manager.connect()
        await self.db_manager.create_tables()

        # Initial setup
        if not await self._fetch_market_info():
            self.logger.critical("Failed to fetch market info. Shutting down.")
            await self.stop()
            return

        # Fetch initial balance
        if not await self._update_balance():
            self.logger.critical("Failed to fetch initial balance. Shutting down.")
            await self.stop()
            return

        # Load any previous state
        state = await self.state_manager.load_state()
        if state:
            self.active_orders = state.get('active_orders', {})
            self.config.metrics = state.get('metrics', self.config.metrics)
            self.logger.info(f"Loaded state with {len(self.active_orders)} active orders.")

        # Reconcile local orders with exchange orders
        await self._reconcile_orders_on_startup()

        # Subscribe to WebSocket streams
        self.ws_session.orderbook_stream(
            symbol=self.config.symbol,
            depth=1,  # Level 1 for top of book
            callback=self._handle_orderbook_update
        )
        self.ws_session.order_stream(
            callback=self._handle_order_update
        )
        self.logger.info("Subscribed to orderbook and order streams.")

        try:
            # Main loop
            while self.is_running:
                await self._manage_orders()
                await asyncio.sleep(self.config.loop_interval_sec)

        except (asyncio.CancelledError, KeyboardInterrupt):
            self.logger.info("Bot execution cancelled by user (Ctrl+C).")
        except Exception as e:
            self.logger.critical(f"An unhandled error occurred in the main loop: {e}", exc_info=True)
        finally:
            await self.stop()

    async def stop(self):
        """Performs graceful shutdown procedures."""
        if not self.is_running:
            return

        self.is_running = False
        self.logger.info("Initiating graceful shutdown...")

        if self.config.trading_mode != "DRY_RUN":
            self.logger.info("Cancelling all active orders on the exchange...")
            await self._cancel_all_orders()
        else:
            self.logger.info("DRY_RUN: Skipping order cancellation on shutdown.")

        self.logger.info("Saving bot state...")
        state = {
            'active_orders': self.active_orders,
            'metrics': self.config.metrics
        }
        await self.state_manager.save_state(state)

        self.logger.info("Logging final metrics to database...")
        await self.db_manager.log_bot_metrics(self.config.metrics)

        self.logger.info("Closing WebSocket connection...")
        self.ws_session.exit()

        self.logger.info("Closing database connection...")
        await self.db_manager.close()

        self.logger.info("Bot shut down successfully.")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    config = Config()

    # Create and run the bot instance
    bot = BybitMarketMaker(config)

    # Run the main asynchronous loop
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        # This block catches Ctrl+C if it happens before bot.run() starts
        # or if asyncio.run doesn't propagate it cleanly.
        # The bot.stop() method is designed to handle this within the run() method's finally block.
        print("\nBot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        print(f"An unexpected error occurred during bot execution: {e}")


