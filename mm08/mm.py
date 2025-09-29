import json
import logging
import os
import signal
import sys
import time
from datetime import UTC
from datetime import datetime as dt

import numpy as np
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP, WebSocket

import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("market_maker.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class MarketMaker:
    """Advanced Bybit Market Making Bot with WebSocket integration and enhanced features"""

    def __init__(self):
        self.session = None
        self.ws = None
        self.running = False
        self.position = None
        self.orders = []
        self.last_prices = []
        self.volatility_history = []
        self.trade_history = []
        self._websocket_connected = False
        self.websocket_reconnect_attempts = 0
        self.websocket_reconnect_delay = 1
        self.fee_rates = {"makerFeeRate": 0.0, "takerFeeRate": 0.0}
        self.performance_metrics = {
            "trades": 0,
            "pnl": 0,
            "fees": 0,
            "win_rate": 0,
            "sharpe_ratio": 0,
            "max_drawdown": 0,
            "winning_trades": 0,
            "losing_trades": 0,
        }
        self.stats_file = "market_maker_stats.json"
        self.load_stats()

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
        sys.exit(0)

    def load_stats(self):
        """Load performance statistics from file"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file) as f:
                    self.performance_metrics = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load stats: {e}")

    def save_stats(self):
        """Save performance statistics to file"""
        try:
            with open(self.stats_file, "w") as f:
                json.dump(self.performance_metrics, f)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def _print(self, message: str, level: str = "info", end: str = "\n") -> None:
        """Enhanced print function with logging and timestamp"""
        timestamp = dt.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        if level == "position":
            print(f"{timestamp} - {message}", end=end, flush=True)
        else:
            print(f"{timestamp} - {level.upper()} - {message}")

        # Log to file
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    def scale_qtys(self, x: float, n: int, scaling_factor: float = 1.0) -> list[float]:
        """Enhanced quantity scaling with adjustable parameters
        Creates a list of qtys that scale additively with optional scaling factor
        [5, 4, 3, 2, 1, -1, -2, -3, -4, -5]

        Args:
            x: How much of your balance to use
            n: Number of orders on each side
            scaling_factor: Multiplier for order sizes

        Returns:
            List of quantities for both long and short sides

        """
        n_ = (x * scaling_factor) / ((n + n**2) / 2)
        long_qtys = [
            round(n_ * i, config.QTY_PRECISION) for i in reversed(range(1, n + 1))
        ]
        short_qtys = [-i for i in long_qtys]
        return long_qtys + short_qtys[::-1]

    def calculate_volatility(self, period: int = 20) -> float:
        """Calculate volatility based on price history

        Args:
            period: Number of recent prices to consider for volatility calculation

        Returns:
            Volatility as percentage

        """
        if len(self.last_prices) < period:
            return 0.0

        prices = self.last_prices[-period:]
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))
        ]
        volatility = np.std(returns) * np.sqrt(
            1440
        )  # Annualized volatility assuming 1-min data

        # Store volatility for adaptive spread calculation
        self.volatility_history.append(volatility)
        if len(self.volatility_history) > 100:
            self.volatility_history.pop(0)

        return volatility

    def calculate_adaptive_spread(self, base_spread: float, volatility: float) -> float:
        """Calculate spread based on market volatility

        Args:
            base_spread: Minimum spread to maintain
            volatility: Current market volatility

        Returns:
            Adjusted spread based on volatility

        """
        if not self.volatility_history:
            return base_spread

        avg_volatility = np.mean(self.volatility_history)
        vol_ratio = volatility / (avg_volatility + 1e-6)  # Avoid division by zero

        # Scale spread based on volatility, with maximum multiplier
        spread_multiplier = min(1 + (vol_ratio - 1) * 0.5, config.MAX_SPREAD_MULTIPLIER)
        return base_spread * spread_multiplier

    def get_account_balance(self) -> dict:
        """Get account balance with error handling

        Returns:
            Dictionary with account balance information

        """
        try:
            wallet_balance = self.session.get_wallet_balance(
                accountType=config.ACCOUNT_TYPE
            )

            if wallet_balance["retCode"] != 0:
                raise FailedRequestError(wallet_balance["retMsg"])

            return wallet_balance["result"]["list"][0]["coin"][0]
        except Exception as e:
            self._print(f"Error getting account balance: {e}", "error")
            return {}

    def initialize_session(self) -> bool:
        """Initialize HTTP session with enhanced configuration

        Returns:
            True if initialization successful, False otherwise

        """
        self._print("Initializing session")

        try:
            self.session = HTTP(
                testnet=config.TESTNET,
                api_key=os.getenv('BYBIT_API_KEY'),
                api_secret=os.getenv('BYBIT_PRIVATE_KEY'),
                logging_level=config.LOGGING_LEVEL,
                retry_codes=config.RETRY_CODES,
                ignore_codes=config.IGNORE_CODES,
                force_retry=config.FORCE_RETRY,
                retry_delay=config.RETRY_DELAY,
                recv_window=config.RECV_WINDOW,
            )

            # Auth sanity test
            wallet_info = self.get_account_balance()
            if not wallet_info:
                raise PermissionError("API key is invalid or account has no balance.")

            self._print("Authentication successful")
            self._print(
                f"Available balance: {wallet_info.get('walletBalance', 'N/A')} {wallet_info.get('coin', 'N/A')}"
            )

            # Set leverage to cross
            try:
                self.session.set_leverage(
                    symbol=config.SYMBOL,
                    leverage=config.LEVERAGE,
                    tradingAccountType=config.ACCOUNT_TYPE,
                )
                self._print(f"Leverage set to {config.LEVERAGE}")
            except InvalidRequestError as e:
                if e.status_code == 34015:
                    self._print("Leverage already set to desired value")
                else:
                    self._print(f"Error setting leverage: {e}", "warning")

            # Set margin mode
            try:
                self.session.set_margin_mode(
                    symbol=config.SYMBOL,
                    buyMarginMode=config.MARGIN_MODE,
                    sellMarginMode=config.MARGIN_MODE,
                    tradingAccountType=config.ACCOUNT_TYPE,
                )
            self._print(f"Margin mode set to {config.MARGIN_MODE}")

            # Fetch and store fee rates
            self.fee_rates = self.get_trading_fee_rate()
            self._print(f"Trading fee rates: Maker={self.fee_rates['makerFeeRate']}, Taker={self.fee_rates['takerFeeRate']}")

            return True

        except Exception as e:
            self._print(f"Failed to initialize session: {e}", "error")
            return False

    def initialize_websocket(self) -> bool:
        """Initialize WebSocket connection for real-time data

        Returns:
            True if initialization successful, False otherwise

        """
        self._print("Initializing WebSocket")

        try:
            self.ws = WebSocket(
                testnet=config.TESTNET,
                api_key=os.getenv('BYBIT_API_KEY'),
                api_secret=os.getenv('BYBIT_PRIVATE_KEY'),
                debug=config.DEBUG_WS,
            )

            # Set up WebSocket callbacks
            self.ws.orderbook_stream_callback = self._handle_orderbook_update
            self.ws.trade_stream_callback = self._handle_trade_update
            self.ws.position_stream_callback = self._handle_position_update
            self.ws.order_stream_callback = self._handle_order_update
            self.ws.on_close = self._handle_websocket_disconnect
            self.ws.on_error = self._handle_websocket_error

            # Subscribe to streams
            self.ws.orderbook_stream(
                symbol=config.SYMBOL,
                category=config.CATEGORY,
                depth=config.ORDERBOOK_DEPTH,
            )

            self.ws.trade_stream(symbol=config.SYMBOL, category=config.CATEGORY)

            self.ws.position_stream(symbol=config.SYMBOL, category=config.CATEGORY)

            self.ws.order_stream(symbol=config.SYMBOL, category=config.CATEGORY)

            self._print("WebSocket initialized and connected")
            self._websocket_connected = True
            return True

        except Exception as e:
            self._print(f"Failed to initialize WebSocket: {e}", "error")
            self._websocket_connected = False
            return False

    def _handle_websocket_disconnect(self) -> None:
        """Handle WebSocket disconnection event"""
        self._print("WebSocket disconnected, attempting to reconnect...", "warning")
        self._websocket_connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                self._print(f"Error closing WebSocket: {e}", "error")
        self.ws = None

    def _handle_websocket_error(self, error: Exception) -> None:
        """Handle WebSocket errors gracefully"""
        self._print(f"WebSocket error: {error}, attempting to reconnect...", "error")
        self._websocket_connected = False
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                self._print(f"Error closing WebSocket after error: {e}", "error")
        self.ws = None

    def get_current_price(self) -> float:
        """Get current market price with multiple sources

        Returns:
            Current market price

        """
        try:
            # Try to get from WebSocket data first
            if self.last_prices:
                return self.last_prices[-1]

            # Fallback to REST API
            ticker = self.session.latest_information_for_symbol(
                symbol=config.SYMBOL, category=config.CATEGORY
            )

            if (
                ticker["retCode"] == 0
                and "result" in ticker
                and len(ticker["result"]) > 0
            ):
                return float(ticker["result"][0]["lastPrice"])

            raise FailedRequestError("Failed to get current price")

        except Exception as e:
            self._print(f"Error getting current price: {e}", "error")
            return 0.0

    def _handle_orderbook_update(self, data: dict) -> None:
        """Handle orderbook updates from WebSocket

        Args:
            data: Orderbook data from WebSocket

        """
        if "result" in data and "b" in data["result"]:
            # Extract bid and ask prices
            bids = [float(b[0]) for b in data["result"]["b"] if float(b[1]) > 0]
            asks = [float(a[0]) for a in data["result"]["a"] if float(a[1]) > 0]

            if bids and asks:
                mid_price = (max(bids) + min(asks)) / 2
                self.last_prices.append(mid_price)

                # Keep only recent prices
                if len(self.last_prices) > 100:
                    self.last_prices.pop(0)

    def _handle_trade_update(self, data: dict) -> None:
        """Handle trade updates from WebSocket

        Args:
            data: Trade data from WebSocket

        """
        if "result" in data and "list" in data["result"]:
            for trade in data["result"]["list"]:
                self.trade_history.append(
                    {
                        "timestamp": trade["T"],
                        "price": float(trade["p"]),
                        "side": trade["S"],
                        "size": float(trade["v"]),
                        "is_maker": trade["m"] == "1",
                    }
                )

                # Keep only recent trades
                if len(self.trade_history) > 1000:
                    self.trade_history.pop(0)

    def _handle_position_update(self, data: dict) -> None:
        """Handle position updates from WebSocket

        Args:
            data: Position data from WebSocket

        """
        if "result" in data and "list" in data["result"]:
            positions = data["result"]["list"]
            for position in positions:
                if position["symbol"] == config.SYMBOL:
                    self.position = {
                        "size": float(position["size"]),
                        "side": position["side"],
                        "entry_price": float(position["entryPrice"]),
                        "mark_price": float(position["markPrice"]),
                        "pnl": float(position["unrealisedPnl"]),
                        "pnl_ratio": float(position["unrealisedPnlRatio"]),
                        "margin": float(position["margin"]),
                    }
                    break

    def _handle_order_update(self, data: dict) -> None:
        """Handle order updates from WebSocket

        Args:
            data: Order data from WebSocket

        """
        if "result" in data and "list" in data["result"]:
            orders = data["result"]["list"]
            for order in orders:
                if order["symbol"] == config.SYMBOL:
                    # Update or add order
                    order_found = False
                    for i, existing_order in enumerate(self.orders):
                        if existing_order["orderId"] == order["orderId"]:
                            self.orders[i] = order
                            order_found = True
                            break

                    if not order_found:
                        self.orders.append(order)

                    # Remove filled or cancelled orders
                    self.orders = [
                        o
                        for o in self.orders
                        if o["orderStatus"] in ["New", "PartiallyFilled"]
                    ]

    def get_current_price(self) -> float:
        """Get current market price with multiple sources

        Returns:
            Current market price

        """
        try:
            # Try to get from WebSocket data first
            if self.last_prices:
                return self.last_prices[-1]

            # Fallback to REST API
            ticker = self.session.latest_information_for_symbol(
                symbol=config.SYMBOL, category=config.CATEGORY
            )

            if (
                ticker["retCode"] == 0
                and "result" in ticker
                and len(ticker["result"]) > 0
            ):
                return float(ticker["result"][0]["lastPrice"])

            raise FailedRequestError("Failed to get current price")

        except Exception as e:
            self._print(f"Error getting current price: {e}", "error")
            return 0.0

    def get_position(self) -> dict | None:
        """Get current position information

        Returns:
            Position information dictionary or None

        """
        try:
            # Try to get from WebSocket data first
            if self.position:
                return self.position

            # Fallback to REST API
            positions = self.session.get_positions(
                symbol=config.SYMBOL,
                category=config.CATEGORY,
                settleAsset=config.SETTLE_ASSET,
            )

            if (
                positions["retCode"] == 0
                and "result" in positions
                and "list" in positions["result"]
            ):
                for pos in positions["result"]["list"]:
                    if float(pos["size"]) != 0:
                        return {
                            "size": float(pos["size"]),
                            "side": pos["side"],
                            "entry_price": float(pos["entryPrice"]),
                            "mark_price": float(pos["markPrice"]),
                            "pnl": float(pos["unrealisedPnl"]),
                            "pnl_ratio": float(pos["unrealisedPnlRatio"]),
                            "margin": float(pos["margin"]),
                        }

            return None

        except Exception as e:
            self._print(f"Error getting position: {e}", "error")
            return None

    def cancel_all_orders(self) -> bool:
        """Cancel all active orders

        Returns:
            True if successful, False otherwise

        """
        try:
            response = self.session.cancel_all_active_orders(
                symbol=config.SYMBOL, category=config.CATEGORY
            )

            if response["retCode"] == 0:
                self._print("All orders cancelled successfully")
                self.orders = []  # Clear local order list
                return True
            self._print(f"Failed to cancel orders: {response['retMsg']}", "error")
            return False

        except Exception as e:
            self._print(f"Error cancelling orders: {e}", "error")
            return False

    def close_position(self) -> bool:
        """Close current position if it exists

        Returns:
            True if successful, False otherwise

        """
        position = self.get_position()
        if not position or float(position["size"]) == 0:
            return True

        try:
            side = "Sell" if position["side"] == "Buy" else "Buy"
            response = self.session.create_order(
                symbol=config.SYMBOL,
                category=config.CATEGORY,
                side=side,
                orderType="Market",
                qty=str(abs(position["size"])),
                reduceOnly=True,
                positionIdx=config.POSITION_IDX,
            )

            if response["retCode"] == 0:
                self._print(
                    f"Position closed successfully: {side} {abs(position['size'])} {config.SYMBOL}"
                )
                # Calculate and add taker fees
                taker_fee_rate = self.fee_rates.get("takerFeeRate", 0.0)
                trade_value = abs(position["size"]) * position["mark_price"]
                fees_incurred = trade_value * taker_fee_rate
                self.performance_metrics["fees"] += fees_incurred
                self._print(f"Fees incurred for closing position: {fees_incurred:.6f}", "info")

                self.position = None  # Clear local position
                return True
            self._print(f"Failed to close position: {response['retMsg']}", "error")
            return False

        except Exception as e:
            self._print(f"Error closing position: {e}", "error")
            return False

    def place_orders(self) -> bool:
        """Place market making orders with enhanced logic

        Returns:
            True if successful, False otherwise

        """
        try:
            # Get current price and volatility
            last_price = self.get_current_price()
            if last_price <= 0:
                self._print(
                    "Invalid current price, skipping order placement", "warning"
                )
                return False

            volatility = self.calculate_volatility()
            spread = self.calculate_adaptive_spread(config.BASE_SPREAD, volatility)

            # Calculate price range
            price_range = config.RANGE * (
                1 + volatility * 0.1
            )  # Adjust range based on volatility

            # Calculate order quantities
            account_balance = self.get_account_balance()
            if not account_balance:
                self._print(
                    "Failed to get account balance, skipping order placement", "warning"
                )
                return False

            available_equity = (
                float(account_balance.get("walletBalance", 0)) * config.EQUITY
            )
            quantities = self.scale_qtys(
                available_equity, config.NUM_ORDERS, config.QTY_SCALING_FACTOR
            )

            # Cancel existing orders
            # self.cancel_all_orders() # Old approach

            # Get current active orders
            existing_orders_response = self.session.get_open_orders(
                symbol=config.SYMBOL, category=config.CATEGORY
            )
            existing_orders = []
            if existing_orders_response["retCode"] == 0 and "list" in existing_orders_response["result"]:
                existing_orders = existing_orders_response["result"]["list"]

            # Generate desired orders
            desired_orders = []
            for i, qty in enumerate(quantities):
                if qty == 0:
                    continue

                # Calculate prices
                if qty > 0:  # Buy order
                    price = last_price * (
                        1 - spread / 2 - (i * price_range / (2 * config.NUM_ORDERS))
                    )
                else:  # Sell order
                    price = last_price * (
                        1 + spread / 2 + (i * price_range / (2 * config.NUM_ORDERS))
                    )

                # Ensure price meets minimum tick size
                price_tick_size = self.get_min_tick_size()
                if price_tick_size:
                    price = round(price / price_tick_size) * price_tick_size

                side = "Buy" if qty > 0 else "Sell"
                desired_orders.append({
                    "orderLinkId": f"mm_{int(time.time())}_{i}",
                    "side": side,
                    "qty": str(abs(qty)),
                    "price": str(price),
                    "orderType": "Limit",
                    "timeInForce": "PostOnly",
                    "positionIdx": config.POSITION_IDX,
                })

            # Compare desired orders with existing orders and execute changes
            orders_to_cancel = []
            orders_to_amend = []
            orders_to_create = []

            # Compare desired orders with existing orders and execute changes
            orders_to_cancel = []
            orders_to_amend = []
            orders_to_create = []

            existing_order_map = {order["orderLinkId"]: order for order in existing_orders if "orderLinkId" in order}
            desired_order_map = {order["orderLinkId"]: order for order in desired_orders}

            # Determine orders to cancel
            for order_link_id, existing_order in existing_order_map.items():
                if order_link_id not in desired_order_map:
                    orders_to_cancel.append(existing_order["orderId"])

            # Determine orders to create and amend
            for order_link_id, desired_order in desired_order_map.items():
                if order_link_id in existing_order_map:
                    existing_order = existing_order_map[order_link_id]
                    # Check if price or quantity needs amendment
                    if (float(existing_order["price"]) != float(desired_order["price"]) or
                            float(existing_order["qty"]) != float(desired_order["qty"])):
                        orders_to_amend.append({
                            "orderId": existing_order["orderId"],
                            "newQty": desired_order["qty"],
                            "newPrice": desired_order["price"],
                        })
                else:
                    orders_to_create.append(desired_order)

            # Logic to determine orders_to_cancel, orders_to_amend, orders_to_create will go here

            # Execute cancellations
            for order_id in orders_to_cancel:
                try:
                    self.session.cancel_order(
                        symbol=config.SYMBOL, category=config.CATEGORY, orderId=order_id
                    )
                    self._print(f"Cancelled order: {order_id}", "position")
                except Exception as e:
                    self._print(f"Failed to cancel order {order_id}: {e}", "error")

            # Execute amendments
            for order_data in orders_to_amend:
                try:
                    self.session.amend_order(
                        symbol=config.SYMBOL, category=config.CATEGORY, **order_data
                    )
                    self._print(f"Amended order: {order_data.get('orderId')}", "position")
                except Exception as e:
                    self._print(f"Failed to amend order {order_data.get('orderId')}: {e}", "error")

            # Execute creations
            orders_placed = []
            for order_data in orders_to_create:
                try:
                    response = self.session.create_order(
                        symbol=config.SYMBOL, category=config.CATEGORY, **order_data
                    )
                    if response["retCode"] == 0:
                        order_id = response["result"]["orderId"]
                        orders_placed.append({"orderId": order_id, **order_data})
                        self._print(
                            f"Placed {order_data.get('side')} order: {order_data.get('qty')} @ {order_data.get('price')}", "position"
                        )
                    else:
                        self._print(
                            f"Failed to place {order_data.get('side')} order: {response['retMsg']}", "error"
                        )
                except Exception as e:
                    self._print(f"Failed to create order: {e}", "error")

            self._print(f"Successfully managed {len(orders_placed)} orders")
            return True

        except Exception as e:
            self._print(f"Error placing orders: {e}", "error")
            return False

    def get_min_tick_size(self) -> float:
        """Get minimum tick size for the symbol

        Returns:
            Minimum tick size or 0.0 if not available

        """
        try:
            response = self.session.get_instruments_info(
                category=config.CATEGORY, symbol=config.SYMBOL
            )

            if (
                response["retCode"] == 0
                and "result" in response
                and "list" in response["result"]
            ):
                for instrument in response["result"]["list"]:
                    if instrument["symbol"] == config.SYMBOL:
                        return float(instrument["priceFilter"]["tickSize"])

            return 0.0

        except Exception as e:
            self._print(f"Error getting tick size: {e}", "error")
            return 0.0

    def get_trading_fee_rate(self) -> dict:
        """Get trading fee rate for the symbol

        Returns:
            Dictionary with maker and taker fee rates

        """
        try:
            response = self.session.get_fee_rate(
                category=config.CATEGORY, symbol=config.SYMBOL
            )

            if (
                response["retCode"] == 0
                and "result" in response
                and "list" in response["result"]
            ):
                for item in response["result"]["list"]:
                    if item["symbol"] == config.SYMBOL:
                        return {
                            "makerFeeRate": float(item["makerFeeRate"]),
                            "takerFeeRate": float(item["takerFeeRate"]),
                        }
            return {"makerFeeRate": 0.0, "takerFeeRate": 0.0}

        except Exception as e:
            self._print(f"Error getting fee rate: {e}", "error")
            return {"makerFeeRate": 0.0, "takerFeeRate": 0.0}

    def check_and_handle_filled_orders(self) -> bool:
        """Check for filled orders and handle take-profit and stop-loss

        Returns:
            True if handled successfully, False otherwise

        """
        try:
            # Get current position
            position = self.get_position()
            if not position or float(position["size"]) == 0:
                return True

            # Calculate current PnL
            current_price = self.get_current_price()
            if current_price <= 0:
                return False

            size = float(position["size"])
            entry_price = float(position["entry_price"])

            if size > 0:  # Long position
                pnl = (current_price - entry_price) * size
                pnl_ratio = (current_price - entry_price) / entry_price
            else:  # Short position
                pnl = (entry_price - current_price) * abs(size)
                pnl_ratio = (entry_price - current_price) / entry_price

            # Update performance metrics
            self.performance_metrics["pnl"] += pnl # Accumulate PnL
            self.performance_metrics["trades"] += 1

            # Determine win/loss and update counts
            if pnl > 0:
                self.performance_metrics["winning_trades"] += 1
            elif pnl < 0:
                self.performance_metrics["losing_trades"] += 1

            # Placeholder for fee calculation (requires actual fee data from API or config)
            # For now, assume a fixed fee per trade or fetch from API if available
            # self.performance_metrics["fees"] += calculated_fee

            # Check take-profit
            if abs(pnl_ratio) >= config.TP_DIST:
                self._print(
                    f"Take-profit triggered at {current_price:.2f}, PnL: {pnl:.2f}"
                )
                return self.close_position()

            # Check stop-loss
            if abs(pnl_ratio) >= config.STOP_DIST:
                self._print(
                    f"Stop-loss triggered at {current_price:.2f}, PnL: {pnl:.2f}"
                )
                return self.close_position()

            return True

        except Exception as e:
            self._print(f"Error checking filled orders: {e}", "error")
            return False

    def update_performance_metrics(self) -> None:
        """Update performance metrics based on trading activity"""
        try:
            # Calculate win rate
            if self.performance_metrics["trades"] > 0:
                self.performance_metrics["win_rate"] = (
                    self.performance_metrics["winning_trades"]
                    / self.performance_metrics["trades"]
                )

            # Calculate Sharpe ratio (simplified)
            if len(self.trade_history) > 0:
                returns = [
                    t["price"] for t in self.trade_history[-100:]
                ]  # Last 100 trades
                if len(returns) > 1:
                    returns_pct = [
                        (returns[i] - returns[i - 1]) / returns[i - 1]
                        for i in range(1, len(returns))
                    ]
                    if returns_pct:
                        avg_return = np.mean(returns_pct)
                        std_return = np.std(returns_pct)
                        if std_return > 0:
                            self.performance_metrics["sharpe_ratio"] = (
                                avg_return / std_return
                            ) * np.sqrt(1440)  # Annualized

            # Save updated metrics
            self.save_stats()

        except Exception as e:
            self._print(f"Error updating performance metrics: {e}", "error")

    def run(self) -> None:
        """Main execution loop with enhanced error handling and recovery"""
        self._print("\n--- ADVANCED MARKET MAKER V3 ---")
        self._print("Enhanced version with WebSocket integration and advanced features")
        self._print("USE AT YOUR OWN RISK!!!\n")

        # Validate configuration
        if not os.getenv('BYBIT_API_KEY') or not os.getenv('BYBIT_PRIVATE_KEY'):
            raise PermissionError(
                "API key and private key are required to run this program."
            )

        # Initialize session
        if not self.initialize_session():
            self._print("Failed to initialize session, exiting", "error")
            return

        # Initialize WebSocket
        if not self.initialize_websocket():
            self._print(
                "Failed to initialize WebSocket, continuing with REST API only",
                "warning",
            )

        self.running = True
        last_order_placement = 0
        last_metrics_update = 0
        last_position_update = 0 # New variable for position update

        self._print("Starting main loop...")

        while self.running:
            try:
                current_time = time.time()

                # Attempt WebSocket reconnection if not connected
                if not self._websocket_connected:
                    self._print(f"Attempting WebSocket reconnection (attempt {self.websocket_reconnect_attempts + 1})...", "warning")
                    time.sleep(self.websocket_reconnect_delay)
                    if self.initialize_websocket():
                        self._print("WebSocket reconnected successfully.", "info")
                        self.websocket_reconnect_attempts = 0
                        self.websocket_reconnect_delay = 1
                    else:
                        self.websocket_reconnect_attempts += 1
                        self.websocket_reconnect_delay = min(self.websocket_reconnect_delay * 2, 60) # Max 60 seconds delay
                        self._print(f"WebSocket reconnection failed. Next attempt in {self.websocket_reconnect_delay} seconds.", "error")
                        continue # Skip other operations until reconnected

                # Check for filled orders and handle TP/SL
                self.check_and_handle_filled_orders()

                # Periodically refresh position from REST API to ensure consistency
                if current_time - last_position_update >= 10: # Refresh every 10 seconds
                    self.get_position() # This will update self.position from REST if needed
                    last_position_update = current_time

                # Place orders at specified intervals
                if current_time - last_order_placement >= 1.0 / config.POLLING_RATE:
                    self.place_orders()
                    last_order_placement = current_time

                # Update performance metrics periodically
                if current_time - last_metrics_update >= 60:  # Every minute
                    self.update_performance_metrics()
                    last_metrics_update = current_time

                # Sleep to control loop speed
                time.sleep(1.0 / config.POLLING_RATE)

            except KeyboardInterrupt:
                self._print("Received keyboard interrupt, shutting down...")
                self.stop()
                break
            except Exception as e:
                self._print(f"Unexpected error in main loop: {e}", "error")
                time.sleep(5)  # Wait before retrying

    def stop(self) -> None:
        """Gracefully stop the market maker"""
        self._print("Stopping market maker...")
        self.running = False

        # Cancel all orders
        self.cancel_all_orders()

        # Close any open positions
        self.close_position()

        # Close WebSocket connection
        if self.ws:
            try:
                self.ws.close()
            except:
                pass

        # Save final performance metrics
        self.update_performance_metrics()

        self._print("Market maker stopped")


def scale_qtys(x: float, n: int, scaling_factor: float = 1.0) -> list[float]:
    """Standalone function for backward compatibility

    Args:
        x: How much of your balance to use
        n: Number of orders on each side
        scaling_factor: Multiplier for order sizes

    Returns:
        List of quantities for both long and short sides

    """
    n_ = (x * scaling_factor) / ((n + n**2) / 2)
    long_qtys = [round(n_ * i, config.QTY_PRECISION) for i in reversed(range(1, n + 1))]
    short_qtys = [-i for i in long_qtys]
    return long_qtys + short_qtys[::-1]


if __name__ == "__main__":
    print("\n--- ADVANCED MARKET MAKER V3 ---")
    print("Enhanced version with WebSocket integration and advanced features")
    print("USE AT YOUR OWN RISK!!!\n")
    time.sleep(1)

    market_maker = MarketMaker()

    try:
        market_maker.run()
    except Exception as e:
        market_maker._print(f"Fatal error: {e}", "error")
        market_maker.stop()
        sys.exit(1)
