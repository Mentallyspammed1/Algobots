import os
import asyncio
import logging
import orjson as json
import time
import uuid
import signal
import statistics # UPGRADE: Import the statistics module for stdev
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import deque
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

# --- Dependency Imports ---
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.logging import RichHandler
import websockets
import websockets.exceptions

# --- Setup for Rich Logging & UI ---
logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True, rich_tracebacks=True)])
logger = logging.getLogger("rich")
console = Console()

class ContextFilter(logging.Filter):
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol

    def filter(self, record):
        record.symbol = self.symbol
        return True

# --- Data Structures & State Management ---
@dataclass
class InstrumentInfo:
    tick_size: Decimal
    step_size: Decimal
    min_order_size: Decimal
    price_precision: int = field(init=False)
    qty_precision: int = field(init=False)

    def __post_init__(self):
        self.price_precision = abs(self.tick_size.as_tuple().exponent)
        self.qty_precision = abs(self.step_size.as_tuple().exponent)

@dataclass
class BotState:
    instrument_info: Optional[InstrumentInfo] = None
    recent_prices: deque = field(default_factory=lambda: deque(maxlen=240)) # Stores last 4 minutes of 1s prices
    consecutive_api_failures: int = 0
    is_circuit_breaker_active: bool = False

# --- Position Manager with Decimal Precision ---
class PositionManager:
    def __init__(self, config, api):
        self.config = config
        self.api = api
        self.size = Decimal("0")
        self.avg_entry_price = Decimal("0")
        self.unrealized_pnl = Decimal("0")
        self.realized_pnl = Decimal("0")

    def _safe_decimal(self, value: Any, default: str = "0.0") -> Decimal:
        if value is None or value == '':
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def update_position(self, data: Dict):
        """Updates the bot's internal position state based on WebSocket data."""
        self.size = self._safe_decimal(data.get('size'))
        self.avg_entry_price = self._safe_decimal(data.get('avgPrice'))
        self.unrealized_pnl = self._safe_decimal(data.get('unrealisedPnl'))

    def process_real_fill(self, trade: Dict):
        """Processes a filled order from execution WebSocket stream."""
        closed_pnl = self._safe_decimal(trade.get('closedPnl'))
        if closed_pnl != Decimal("0"):
            self.realized_pnl += closed_pnl

    def process_virtual_fill(self, side: str, price: Decimal, qty: Decimal):
        """Simulates a fill for dry run mode."""
        current_value = self.size * self.avg_entry_price if self.size != 0 else Decimal("0")
        fill_value = (Decimal("-1") if side == "Sell" else Decimal("1")) * qty * price
        new_position_size = self.size + (qty if side == "Buy" else -qty)

        if new_position_size.is_zero():
            # Position fully closed
            self.realized_pnl += self.unrealized_pnl # Realize existing unrealized PNL
            self.unrealized_pnl = Decimal("0")
            self.avg_entry_price = Decimal("0")
        else:
            if self.size.copy_sign(new_position_size) == self.size:
                # Adding to existing position (same side)
                new_avg_price = (current_value + fill_value) / new_position_size
                self.avg_entry_price = new_avg_price
            else:
                # Reversing or reducing position (opposite side)
                # For simplicity, if crossing zero or reducing, assume PNL is realized
                # and new average price is the fill price for the remaining position.
                # A more complex model would track multiple fills for weighted average.
                self.realized_pnl += self.unrealized_pnl
                self.avg_entry_price = price

        self.size = new_position_size
        logger.info(f"[DRY RUN] Fill simulated: {side} {qty} @ {price}. New Position: {self.size}")

    async def check_and_manage_risk(self, state: BotState):
        """Checks for take-profit or stop-loss conditions and closes position if triggered."""
        if self.size == Decimal("0"):
            return False

        try:
            # Calculate PNL percentage relative to position value
            pnl_pct = self.unrealized_pnl / (abs(self.size) * self.avg_entry_price)
        except ZeroDivisionError:
            pnl_pct = Decimal("0") # Avoid division by zero if avg_entry_price is 0

        should_close, reason = False, ""
        tp_pct = Decimal(str(self.config['risk_management']['take_profit_pct']))
        sl_pct = Decimal(str(self.config['risk_management']['stop_loss_pct']))

        if pnl_pct >= tp_pct:
            should_close, reason = True, f"Take Profit ({pnl_pct:.2%})"
        elif pnl_pct <= -sl_pct:
            should_close, reason = True, f"Stop Loss ({pnl_pct:.2%})"

        if should_close:
            logger.warning(f"Risk Manager: Closing position due to: {reason}. Position Size: {self.size}")
            side_to_close = "Buy" if self.size < 0 else "Sell"
            qty_to_close = abs(self.size)
            await self.api.close_position(side_to_close, qty_to_close)
            return True
        return False

# --- Core Bot Class ---
class EnhancedBybitMarketMaker:
    def __init__(self, config):
        self.config = config
        self.state = BotState()

        load_dotenv()
        self.api_key = os.getenv('BYBIT_API_KEY')
        self.api_secret = os.getenv('BYBIT_API_SECRET')

        if not self.api_key or not self.api_secret:
            raise ValueError("API keys not found. Ensure a .env file exists in the script's directory with BYBIT_API_KEY and BYBIT_API_SECRET.")

        # Initialize pybit HTTP session for REST API calls
        self.session = HTTP(
            testnet=config['testnet'],
            api_key=self.api_key,
            api_secret=self.api_secret,
            recv_window=10000, # Increased recv_window for potential network latency
            timeout=30 # Increased timeout
        )
        self.api = self # Self-reference for PositionManager to call bot's methods
        self.position_manager = PositionManager(config, self)
        self.orderbook = {"bids": {}, "asks": {}} # {price: qty}
        self.active_orders: Dict[str, dict] = {} # {orderId: {price, side, qty}}
        self.virtual_orders: Dict[str, dict] = {} # For dry run simulation
        self.last_reprice_time = 0

        # Add symbol context filter to logger
        logger.addFilter(ContextFilter(config['symbol']))

    async def _api_call(self, method, **kwargs):
        """Wrapper for API calls with circuit breaker and error handling."""
        if self.state.is_circuit_breaker_active:
            logger.warning("API call blocked by circuit breaker.")
            return None
        try:
            # Use asyncio.to_thread to run synchronous pybit HTTP calls in a separate thread
            response = await asyncio.to_thread(method, **kwargs)
            if response and response.get('retCode') == 0:
                self.state.consecutive_api_failures = 0
                return response['result']
            else:
                msg = response.get('retMsg', 'Unknown error') if response else "No response"
                logger.error(f"API Error ({method.__name__}): {msg} (retCode: {response.get('retCode')})")
        except Exception as e:
            logger.error(f"API request failed ({method.__name__}): {e}", exc_info=True)

        self.state.consecutive_api_failures += 1
        await self.check_circuit_breaker()
        return None

    async def check_circuit_breaker(self):
        """Activates circuit breaker if too many API failures occur."""
        if self.state.consecutive_api_failures >= self.config['risk_management']['circuit_breaker_threshold']:
            if not self.state.is_circuit_breaker_active:
                self.state.is_circuit_breaker_active = True
                logger.critical("[bold red]CIRCUIT BREAKER TRIGGERED: Too many consecutive API failures.[/bold red]")
                await self.cancel_all_orders()
                cooldown = self.config['risk_management']['circuit_breaker_cooldown_seconds']
                logger.warning(f"Trading paused for {cooldown} seconds.")
                await asyncio.sleep(cooldown) # Pause execution
                self.state.consecutive_api_failures = 0
                self.state.is_circuit_breaker_active = False
                logger.info("[bold green]Circuit breaker cooldown finished. Resuming trading.[/bold green]")

    async def fetch_instrument_info(self):
        """Fetches and stores instrument details like tick size and step size."""
        result = await self._api_call(self.session.get_instruments_info, category='linear', symbol=self.config['symbol'])
        if result and result.get('list'):
            info = result['list'][0]
            self.state.instrument_info = InstrumentInfo(
                tick_size=Decimal(info['priceFilter']['tickSize']),
                step_size=Decimal(info['lotSizeFilter']['qtyStep']),
                min_order_size=Decimal(info['lotSizeFilter']['minOrderQty'])
            )
            logger.info(f"Instrument info fetched for {self.config['symbol']}: Tick Size={self.state.instrument_info.tick_size}, Step Size={self.state.instrument_info.step_size}")
        else:
            logger.error(f"Failed to fetch instrument info for {self.config['symbol']}")

    async def place_and_cancel_orders_batch(self, orders_to_place, orders_to_cancel):
        """Places new orders and cancels existing ones in batches."""
        if self.config['dry_run']:
            # In dry run, simply update virtual orders
            self.virtual_orders.clear()
            for order in orders_to_place:
                order_id = f"dryrun_{uuid.uuid4().hex[:8]}" # Generate unique ID for virtual orders
                self.virtual_orders[order_id] = order
            if orders_to_place:
                logger.info(f"[DRY RUN] Placed {len(orders_to_place)} virtual orders.")
            if orders_to_cancel:
                logger.info(f"[DRY RUN] Cancelled {len(orders_to_cancel)} virtual orders.")
            return

        # Cancel orders first
        if orders_to_cancel:
            cancel_requests = [{"symbol": self.config['symbol'], "orderId": oid} for oid in orders_to_cancel]
            cancel_result = await self._api_call(self.session.cancel_batch_order, category="linear", request=cancel_requests)
            if cancel_result:
                logger.info(f"Successfully cancelled {len(orders_to_cancel)} orders.")
            else:
                logger.warning(f"Failed to cancel {len(orders_to_cancel)} orders.")

        # Place new orders
        if orders_to_place:
            place_requests = [
                {
                    "symbol": self.config['symbol'],
                    "side": o['side'],
                    "orderType": "Limit",
                    "qty": str(o['qty']),
                    "price": str(o['price']),
                    "orderLinkId": f"mm_{uuid.uuid4().hex[:8]}", # Unique ID for each order
                    "timeInForce": "PostOnly" # Ensures orders don't take liquidity
                } for o in orders_to_place
            ]
            place_result = await self._api_call(self.session.place_batch_order, category="linear", request=place_requests)
            if place_result:
                logger.info(f"Successfully placed {len(orders_to_place)} orders.")
            else:
                logger.warning(f"Failed to place {len(orders_to_place)} orders.")

    async def close_position(self, side, qty):
        """Closes the current position using a market order."""
        if self.config['dry_run']:
            best_ask = min(self.orderbook['asks'].keys()) if self.orderbook['asks'] else self.state.recent_prices[-1] if self.state.recent_prices else Decimal("0")
            best_bid = max(self.orderbook['bids'].keys()) if self.orderbook['bids'] else self.state.recent_prices[-1] if self.state.recent_prices else Decimal("0")
            fill_price = best_bid if side == "Sell" else best_ask
            self.position_manager.process_virtual_fill(side, fill_price, qty)
            self.virtual_orders.clear() # Clear any existing virtual orders when closing position
            logger.info(f"[DRY RUN] Market closed position: {side} {qty} @ {fill_price}")
            return

        formatted_qty = self._format_qty(qty)
        close_result = await self._api_call(
            self.session.place_order,
            category='linear',
            symbol=self.config['symbol'],
            side=side,
            orderType='Market',
            qty=str(formatted_qty),
            reduceOnly=True # Ensures this order only reduces position
        )
        if close_result:
            logger.info(f"Market order placed to close position: {side} {formatted_qty}")
        else:
            logger.error(f"Failed to place market order to close position: {side} {formatted_qty}")

    async def cancel_all_orders(self):
        """Cancels all active orders for the symbol."""
        if self.config['dry_run']:
            if self.virtual_orders:
                logger.info(f"[DRY RUN] Cancelling {len(self.virtual_orders)} virtual orders.")
                self.virtual_orders.clear()
            return

        cancel_result = await self._api_call(self.session.cancel_all_orders, category='linear', symbol=self.config['symbol'])
        if cancel_result:
            logger.info("All active orders cancelled.")
            self.active_orders.clear() # Clear internal tracking of active orders
        else:
            logger.warning("Failed to cancel all orders.")

    async def _handle_message(self, msg):
        """Processes incoming WebSocket messages."""
        topic = msg.get('topic', '')
        data = msg.get('data')

        if topic.startswith("orderbook"):
            book_data = data[0] if isinstance(data, list) else data
            self.orderbook['bids'] = {Decimal(p): Decimal(q) for p, q in book_data.get('b', [])}
            self.orderbook['asks'] = {Decimal(p): Decimal(q) for p, q in book_data.get('a', [])}
        elif topic.startswith("tickers"):
            # Update recent prices with mid-price
            if 'midPrice' in data and data['midPrice'] is not None:
                self.state.recent_prices.append(Decimal(data['midPrice']))
        elif not self.config['dry_run']: # Private topics only for non-dry run
            if topic == "position":
                for pos_data in (data if isinstance(data, list) else [data]):
                    if pos_data.get('symbol') == self.config['symbol']:
                        self.position_manager.update_position(pos_data)
            elif topic == "order":
                for order in data:
                    oid = order['orderId']
                    if order['orderStatus'] in ['New', 'PartiallyFilled', 'Untriggered']:
                        self.active_orders[oid] = {
                            'price': Decimal(order['price']),
                            'side': order['side'],
                            'qty': Decimal(order['qty'])
                        }
                    elif oid in self.active_orders:
                        # Order filled or cancelled, remove from active orders
                        del self.active_orders[oid]
            elif topic == "execution":
                for trade in data:
                    if trade['execType'] == 'Trade' and trade.get('symbol') == self.config['symbol']:
                        self.position_manager.process_real_fill(trade)

    def _calculate_tiered_quotes(self):
        """Calculates buy and sell orders based on market conditions, volatility, and inventory skew."""
        bids = self.orderbook['bids']
        asks = self.orderbook['asks']

        if not bids or not asks or len(self.state.recent_prices) < 2:
            return [], [] # Not enough market data to quote

        best_bid = max(bids.keys())
        best_ask = min(asks.keys())

        if best_bid >= best_ask:
            logger.warning("Market crossed, skipping quote generation.")
            return [], []

        mid_price = (best_bid + best_ask) / Decimal("2")

        # Calculate volatility from recent prices
        volatility = Decimal("0")
        if len(self.state.recent_prices) >= 50: # Require sufficient data for meaningful std dev
            try:
                volatility = Decimal(statistics.stdev(self.state.recent_prices) / mid_price)
            except statistics.StatisticsError:
                volatility = Decimal("0") # Not enough unique values for std dev
        
        # Calculate dynamic spread
        total_spread_pct = Decimal(str(self.config['strategy']['base_spread_percentage'])) + volatility * Decimal(str(self.config['strategy']['volatility_spread_multiplier']))

        # Calculate inventory skew
        max_pos_size = Decimal(self.config['risk_management']['max_position_size'])
        skew_intensity = Decimal(str(self.config['strategy']['inventory_skew_intensity']))

        # Skew factor between -1 and 1
        skew_factor = Decimal("0")
        if max_pos_size > 0:
            skew_factor = (self.position_manager.size / max_pos_size).clamp(Decimal("-1"), Decimal("1"))

        # Adjust fair value based on skew
        # Positive skew (long) shifts fair value down (encourages sells, discourages buys)
        # Negative skew (short) shifts fair value up (encourages buys, discourages sells)
        fair_value = mid_price * (Decimal("1") - skew_factor * skew_intensity)

        base_order_size = Decimal(self.config['order_management']['base_order_size'])
        buy_orders, sell_orders = [], []

        for i in range(self.config['order_management']['order_tiers']):
            tier_spread_adj = Decimal(str(i)) * Decimal(str(self.config['order_management']['tier_spread_increase_bps'])) / Decimal("10000")
            
            # Calculate bid and ask prices
            bid_price = self._format_price(fair_value * (Decimal("1") - total_spread_pct - tier_spread_adj))
            ask_price = self._format_price(fair_value * (Decimal("1") + total_spread_pct + tier_spread_adj))
            
            # Adjust quantity for tiered orders
            qty = self._format_qty(base_order_size * Decimal(str(1 + i * self.config['order_management']['tier_qty_multiplier'])))

            # Only place orders if they don't exceed max position size
            current_pos_abs = abs(self.position_manager.size)
            remaining_buy_capacity = max_pos_size - (current_pos_abs if self.position_manager.size > 0 else Decimal("0"))
            remaining_sell_capacity = max_pos_size - (current_pos_abs if self.position_manager.size < 0 else Decimal("0"))
            
            # Ensure order quantity is above minimum
            if qty < self.state.instrument_info.min_order_size:
                qty = self.state.instrument_info.min_order_size

            # Place buy orders
            if self.position_manager.size + qty <= max_pos_size:
                buy_orders.append({'price': bid_price, 'qty': qty, 'side': 'Buy'})

            # Place sell orders
            if self.position_manager.size - qty >= -max_pos_size:
                sell_orders.append({'price': ask_price, 'qty': qty, 'side': 'Sell'})
        
        # Sort orders to ensure consistent processing, useful for debugging
        buy_orders.sort(key=lambda x: x['price'], reverse=True) # Highest bid first
        sell_orders.sort(key=lambda x: x['price']) # Lowest ask first

        return buy_orders, sell_orders

    async def _simulate_fills(self):
        """Simulates fills for virtual orders in dry run mode."""
        if not self.virtual_orders or not self.orderbook['bids'] or not self.orderbook['asks']:
            return

        best_bid = max(self.orderbook['bids'].keys())
        best_ask = min(self.orderbook['asks'].keys())

        filled_order_ids = []
        for order_id, order in list(self.virtual_orders.items()): # Iterate over a copy
            if order['side'] == 'Buy' and order['price'] >= best_ask:
                # Buy order at or above best ask would be filled
                self.position_manager.process_virtual_fill('Buy', best_ask, order['qty']) # Fill at market price
                filled_order_ids.append(order_id)
            elif order['side'] == 'Sell' and order['price'] <= best_bid:
                # Sell order at or below best bid would be filled
                self.position_manager.process_virtual_fill('Sell', best_bid, order['qty']) # Fill at market price
                filled_order_ids.append(order_id)

        for order_id in filled_order_ids:
            del self.virtual_orders[order_id]

    def _format_price(self, p: Decimal) -> Decimal:
        """Formats price to instrument's tick size precision."""
        if not self.state.instrument_info: return p
        return p.quantize(self.state.instrument_info.tick_size, rounding=ROUND_HALF_UP)

    def _format_qty(self, q: Decimal) -> Decimal:
        """Formats quantity to instrument's step size precision."""
        if not self.state.instrument_info: return q
        return q.quantize(self.state.instrument_info.step_size, rounding=ROUND_HALF_UP)

    def generate_status_table(self) -> Table:
        """Generates a Rich Table for displaying bot status."""
        title = f"Bybit Market Maker Status ({datetime.now().strftime('%H:%M:%S')})"
        if self.config['dry_run']:
            title += " [bold yellow](DRY RUN MODE)[/bold yellow]"
        table = Table(title=title, style="cyan", title_justify="left")
        table.add_column("Metric", style="bold magenta", min_width=20)
        table.add_column("Value", min_width=30)

        if self.state.is_circuit_breaker_active:
            status = "[bold red]CIRCUIT BREAKER ACTIVE[/bold red]"
        else:
            status = "[bold green]Running[/bold green]"
        table.add_row("Bot Status", status)
        table.add_row("Symbol", self.config['symbol'])

        pos_color = "green" if self.position_manager.size > 0 else "red" if self.position_manager.size < 0 else "white"
        table.add_row("Position Size", f"[{pos_color}]{self.position_manager.size}[/{pos_color}]")
        table.add_row("Avg Entry Price", f"{self.position_manager.avg_entry_price}")

        pnl_color = "green" if self.position_manager.unrealized_pnl >= 0 else "red"
        table.add_row("Unrealized PNL", f"[{pnl_color}]{self.position_manager.unrealized_pnl:.4f}[/{pnl_color}]")
        table.add_row("Realized PNL", f"[{pnl_color}]{self.position_manager.realized_pnl:.4f}[/{pnl_color}]") # Added realized PNL

        best_bid = max(self.orderbook['bids'].keys()) if self.orderbook['bids'] else "N/A"
        best_ask = min(self.orderbook['asks'].keys()) if self.orderbook['asks'] else "N/A"
        table.add_row("Market Bid / Ask", f"{best_bid} / {best_ask}")

        open_orders = self.virtual_orders if self.config['dry_run'] else self.active_orders
        table.add_row(
            "Open Orders (Buy / Sell)",
            f"{len([o for o in open_orders.values() if o['side'] == 'Buy'])} / {len([o for o in open_orders.values() if o['side'] == 'Sell'])}"
        )
        return table
    
    async def _websocket_stream_manager(self, ws_client: WebSocket, topics: List[str], stream_name: str):
        """Manages a persistent WebSocket connection, handling reconnections and authentication."""
        url = ws_client.get_ws_url()
        while True:
            try:
                logger.info(f"Connecting to {stream_name} WebSocket at {url}...")
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    logger.info(f"{stream_name} WebSocket connected.")

                    if "private" in stream_name:
                        # Authenticate for private streams
                        expires = int((time.time() + 10) * 1000) # Expiration time for signature
                        signature = ws_client._auth(expires) # Use pybit's internal auth method
                        auth_payload = {"op": "auth", "args": [self.api_key, expires, signature]}
                        await ws.send(json.dumps(auth_payload))
                        auth_response = json.loads(await ws.recv())
                        if auth_response.get('success'):
                            logger.info(f"{stream_name} WebSocket authenticated successfully.")
                        else:
                            logger.error(f"{stream_name} WebSocket authentication failed: {auth_response}")
                            raise websockets.exceptions.ConnectionClosedOK("Auth Failed") # Force reconnect

                    # Subscribe to topics
                    sub_payload = {"op": "subscribe", "args": topics}
                    await ws.send(json.dumps(sub_payload))
                    sub_response = json.loads(await ws.recv())
                    if sub_response.get('success'):
                        logger.info(f"{stream_name} WebSocket subscribed to topics: {topics}")
                    else:
                        logger.error(f"{stream_name} WebSocket subscription failed: {sub_response}")
                        raise websockets.exceptions.ConnectionClosedOK("Subscription Failed")

                    async for message in ws:
                        data = json.loads(message)
                        if 'topic' in data:
                            await self._handle_message(data)
                        elif 'op' in data and data.get('success') == False:
                            logger.error(f"WebSocket operation failed: {data}")
                        elif 'pong' in data: # Handle pong messages
                            pass
                        # else:
                        #     logger.debug(f"Received WS message: {data}") # Uncomment for debugging

            except (websockets.exceptions.ConnectionClosedError, asyncio.TimeoutError, websockets.exceptions.ConnectionClosedOK) as e:
                logger.warning(f"{stream_name} WebSocket connection lost: {e}. Reconnecting in 5s...")
            except Exception as e:
                logger.error(f"An unexpected error occurred in {stream_name} WebSocket manager: {e}", exc_info=True)
            await asyncio.sleep(5) # Wait before attempting to reconnect

    async def run(self):
        """Main entry point for the bot, starts WebSocket streams and the trading loop."""
        mode_text = "[bold yellow]DRY RUN[/bold yellow]" if self.config['dry_run'] else "[bold green]LIVE TRADING[/bold green]"
        env_text = "Testnet" if self.config['testnet'] else "Mainnet"
        logger.info(f"Starting bot for [bold]{self.config['symbol']}[/bold] on {env_text} in {mode_text} mode.")

        # Fetch initial instrument information
        await self.fetch_instrument_info()
        if not self.state.instrument_info:
            raise RuntimeError("Failed to start: Could not fetch instrument info.")

        # Cancel any existing open orders to ensure a clean start
        await self.cancel_all_orders()
        
        # --- Start WebSocket Stream Managers ---
        public_ws_client = WebSocket(testnet=self.config['testnet'], channel_type="linear")
        public_topics = [
            f"orderbook.{self.config['technical']['orderbook_depth']}.{self.config['symbol']}",
            f"tickers.{self.config['symbol']}"
        ]
        websocket_tasks = [
            asyncio.create_task(self._websocket_stream_manager(public_ws_client, public_topics, "public"))
        ]

        if not self.config['dry_run']:
            # For live trading, also start private WebSocket stream for position and order updates
            private_ws_client = WebSocket(testnet=self.config['testnet'], channel_type="private", api_key=self.api_key, api_secret=self.api_secret)
            private_topics = ["position", "order", "execution"]
            websocket_tasks.append(
                asyncio.create_task(self._websocket_stream_manager(private_ws_client, private_topics, "private"))
            )
        
        # Give some time for initial WebSocket connections and data to populate
        logger.info("Waiting for initial WebSocket data...")
        await asyncio.sleep(5) 
        if not self.state.recent_prices:
             logger.warning("No ticker data received yet, strategy might be less effective initially.")
        if not self.orderbook['bids'] or not self.orderbook['asks']:
            logger.warning("No orderbook data received yet, market making will be paused.")

        # --- Main Trading Loop ---
        with Live(self.generate_status_table(), screen=True, redirect_stderr=False, refresh_per_second=4) as live:
            while True:
                try:
                    live.update(self.generate_status_table())

                    # Pause if circuit breaker is active
                    if self.state.is_circuit_breaker_active:
                        await asyncio.sleep(1)
                        continue

                    # Check and manage position risk (TP/SL)
                    if await self.position_manager.check_and_manage_risk(self.state):
                        await self.cancel_all_orders() # Cancel all orders if position closed
                        logger.warning("Position closed by risk manager. Pausing 60s for market to settle.")
                        await asyncio.sleep(60)
                        continue # Restart loop after pause

                    # Simulate fills in dry run mode
                    if self.config['dry_run']:
                        await self._simulate_fills()
                    
                    now = time.time()
                    # Rate limit order repricing
                    if now - self.last_reprice_time < self.config['order_management']['order_reprice_delay_seconds']:
                        await asyncio.sleep(0.1)
                        continue # Continue to next loop iteration

                    # Calculate new orders
                    buy_orders, sell_orders = self._calculate_tiered_quotes()
                    
                    # Determine current open orders for comparison
                    open_orders = self.virtual_orders if self.config['dry_run'] else self.active_orders

                    # If no quotes can be generated (e.g., no orderbook data), cancel existing orders
                    if (not buy_orders and not sell_orders) and open_orders:
                        logger.info("No new quotes generated, cancelling all existing orders.")
                        await self.cancel_all_orders()
                        await asyncio.sleep(0.5) # Small pause before next re-evaluation
                        continue

                    # UPGRADE: Only reprice if quotes have significantly changed OR if there are no open orders
                    # This reduces unnecessary API calls.
                    current_quotes = sorted([(o['price'], o['qty'], o['side']) for o in open_orders.values()])
                    new_quotes = sorted([(o['price'], o['qty'], o['side']) for o in (buy_orders + sell_orders)])

                    if current_quotes != new_quotes or not open_orders:
                        logger.info(f"Repricing: {len(buy_orders)} buys, {len(sell_orders)} sells. Cancelling {len(open_orders)} existing.")
                        await self.place_and_cancel_orders_batch(buy_orders + sell_orders, list(open_orders.keys()))
                        self.last_reprice_time = now
                    else:
                        logger.debug("Quotes have not changed, no order action taken.")
                    
                except asyncio.CancelledError:
                    logger.info("Main loop cancelled.")
                    break # Exit the loop on cancellation
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                    await asyncio.sleep(5) # Pause on error to prevent rapid looping

        logger.info("Main loop finished. Cancelling WebSocket tasks...")
        for task in websocket_tasks:
            task.cancel()
        await asyncio.gather(*websocket_tasks, return_exceptions=True) # Wait for tasks to finish cancelling

async def main():
    try:
        # --- FIX: Correctly load json with orjson, reading as bytes ---
        with open('config.json', 'rb') as f:
            config = json.loads(f.read())
    except FileNotFoundError:
        logger.critical("CRITICAL: config.json not found. Please create it in the same directory as the script.")
        return
    except json.JSONDecodeError as e:
        logger.critical(f"CRITICAL: Error parsing config.json: {e}. Please check your JSON syntax.")
        return
    
    bot = EnhancedBybitMarketMaker(config)
    loop = asyncio.get_running_loop()
    main_task = asyncio.create_task(bot.run())
    
    # Register signal handlers for graceful shutdown
    if hasattr(signal, 'SIGINT') and hasattr(signal, 'SIGTERM'):
        for sig in [signal.SIGINT, signal.SIGTERM]:
            try:
                loop.add_signal_handler(sig, lambda: main_task.cancel())
                logger.info(f"Registered signal handler for {sig.name}")
            except NotImplementedError:
                logger.warning("Signal handlers not fully supported on this system (e.g., Windows). Use Ctrl+C to stop.")
    else:
        logger.warning("Signal handlers not available on this system. Use Ctrl+C to stop.")

    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Shutdown signal received. Bot is stopping.")
    finally:
        logger.info("Cleaning up resources...")
        await bot.cancel_all_orders() # Ensure all orders are cancelled on exit
        logger.info("Bot stopped gracefully.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user via KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"An unhandled exception occurred during bot execution: {e}", exc_info=True)
