import time
from datetime import datetime

from order_manager import OrderManager
from pybit.unified_trading import HTTP
from risk_manager import RiskManager
from websocket_manager import WebSocketManager

from utils import (
    PerformanceTracker,
    calculate_order_sizes,
    calculate_order_step,
    calculate_spread,
    calculate_volatility,
    format_price,
    format_quantity,
    setup_logger,
)


class MarketMaker:
    """Advanced Market Maker Bot for Bybit"""

    def __init__(self, config: dict, env_config: dict):
        self.config = config
        self.env_config = env_config
        self.symbol = config["trading"]["symbol"]
        self.running = False

        # Setup logger
        self.logger = setup_logger(
            "MarketMaker", self.env_config["log_file"], self.env_config["log_level"]
        )

        # Initialize Bybit client
        self._init_client()

        # Initialize components
        self.risk_manager = RiskManager(config, self.logger)
        self.order_manager = OrderManager(self.client, config, self.logger)
        self.performance_tracker = PerformanceTracker()
        self.ws_manager = None

        # Market data
        self.last_price = 0
        self.bid_price = 0
        self.ask_price = 0
        self.mid_price = 0
        self.price_history = []
        self.volatility = 0
        self.spread = 0

        # Position tracking
        self.position = {"size": 0, "side": None, "avg_price": 0}
        self.inventory_ratio = 0.5

        # Performance metrics
        self.last_balance_check = datetime.now()
        self.last_performance_log = datetime.now()

    def _init_client(self):
        """Initialize Bybit API client"""
        if self.env_config["environment"] == "testnet":
            self.client = HTTP(
                testnet=True,
                api_key=self.env_config["api_key"],
                api_secret=self.env_config["api_secret"],
            )
        else:
            self.client = HTTP(
                testnet=False,
                api_key=self.env_config["api_key"],
                api_secret=self.env_config["api_secret"],
            )

        self.logger.info(
            f"Initialized Bybit client for {self.env_config['environment']}"
        )
        if self.config["advanced"]["enable_websocket"]:
            self.ws_manager = WebSocketManager(
                self.env_config["api_key"],
                self.env_config["api_secret"],
                self._on_ws_message,
            )

    def _on_ws_message(self, message):
        """Handle incoming WebSocket messages."""
        topic = message.get("topic", "")
        data = message.get("data", [])

        if topic.startswith("tickers"):
            if data:
                self.last_price = float(data.get("lastPrice"))

        elif topic == "order":
            for order in data:
                self.order_manager.update_order_from_ws(order)

        elif topic == "position":
            for position in data:
                if position["symbol"] == self.symbol:
                    self.position = {
                        "size": float(position["size"]),
                        "side": position["side"],
                        "avg_price": float(position["avgPrice"])
                        if position["avgPrice"]
                        else 0,
                        "mark_price": float(position["markPrice"])
                        if position["markPrice"]
                        else 0,
                        "unrealized_pnl": float(position["unrealisedPnl"])
                        if position["unrealisedPnl"]
                        else 0,
                    }
                    self._calculate_inventory_ratio()

    def get_market_data(self) -> dict:
        """Fetch current market data"""
        if (
            self.config["advanced"]["enable_websocket"]
            and self.ws_manager
            and self.ws_manager.is_connected
        ):
            return {
                "bid": self.bid_price,
                "ask": self.ask_price,
                "mid": self.mid_price,
                "spread": self.spread,
            }
        else:
            try:
                # Get orderbook
                orderbook = self.client.get_orderbook(
                    category=self.config["trading"]["market_type"],
                    symbol=self.symbol,
                    limit=1,
                )

                if orderbook["retCode"] == 0:
                    bids = orderbook["result"]["b"]
                    asks = orderbook["result"]["a"]

                    if bids and asks:
                        self.bid_price = float(bids[0][0])
                        self.ask_price = float(asks[0][0])
                        self.mid_price = (self.bid_price + self.ask_price) / 2
                        self.spread = (self.ask_price - self.bid_price) / self.mid_price

                        # Update price history
                        self.price_history.append(self.mid_price)
                        if (
                            len(self.price_history)
                            > self.config["advanced"]["price_history_length"]
                        ):
                            self.price_history = self.price_history[
                                -self.config["advanced"]["price_history_length"] :
                            ]

                        return {
                            "bid": self.bid_price,
                            "ask": self.ask_price,
                            "mid": self.mid_price,
                            "spread": self.spread,
                        }

            except Exception as e:
                self.logger.error(f"Error fetching market data: {e!s}")

        return {}

    def _calculate_inventory_ratio(self):
        """Calculate inventory ratio based on current position"""
        max_position = self.config["trading"]["max_position"]
        if self.position["side"] == "Buy":
            self.inventory_ratio = 0.5 + (self.position["size"] / (2 * max_position))
        elif self.position["side"] == "Sell":
            self.inventory_ratio = 0.5 - (self.position["size"] / (2 * max_position))
        else:
            self.inventory_ratio = 0.5

    def get_position(self) -> dict:
        """Get current position"""
        if (
            self.config["advanced"]["enable_websocket"]
            and self.ws_manager
            and self.ws_manager.is_connected
        ):
            return self.position
        else:
            try:
                response = self.client.get_positions(
                    category=self.config["trading"]["market_type"], symbol=self.symbol
                )

                if response["retCode"] == 0 and response["result"]["list"]:
                    position_data = response["result"]["list"][0]
                    self.position = {
                        "size": float(position_data["size"]),
                        "side": position_data["side"],
                        "avg_price": float(position_data["avgPrice"])
                        if position_data["avgPrice"]
                        else 0,
                        "mark_price": float(position_data["markPrice"])
                        if position_data["markPrice"]
                        else 0,
                        "unrealized_pnl": float(position_data["unrealisedPnl"])
                        if position_data["unrealisedPnl"]
                        else 0,
                    }

                    self._calculate_inventory_ratio()
                    return self.position

                self.position = {"size": 0, "side": None, "avg_price": 0}
                self.inventory_ratio = 0.5
                return self.position

            except Exception as e:
                self.logger.error(f"Error fetching position: {e!s}")
                return self.position

    def get_account_balance(self) -> float:
        """Get account balance"""
        try:
            response = self.client.get_wallet_balance(
                accountType="UNIFIED"
                if self.config["trading"]["market_type"] == "linear"
                else "SPOT"
            )

            if response["retCode"] == 0:
                balances = response["result"]["list"][0]["coin"]

                # Find USDT balance for linear, or base currency for spot
                for balance in balances:
                    if (
                        self.config["trading"]["market_type"] == "linear"
                        and balance["coin"] == "USDT"
                    ) or (
                        self.config["trading"]["market_type"] == "spot"
                        and balance["coin"] == self.symbol.replace("USDT", "")
                    ):
                        return float(balance["walletBalance"])

        except Exception as e:
            self.logger.error(f"Error fetching balance: {e!s}")

        return 0

    def calculate_order_prices_and_sizes(self) -> tuple[list[dict], list[dict]]:
        """Calculate order prices and sizes for both sides"""
        market_data = self.get_market_data()
        if not market_data:
            return [], []

        # Calculate volatility
        volatility = calculate_volatility(self.price_history)
        if volatility is not None:
            self.volatility = volatility

        strategy = self.config["advanced"]["strategy_type"]

        # Calculate dynamic spreads
        bid_spread, ask_spread = calculate_spread(
            self.config["trading"]["base_spread"],
            self.volatility,
            self.inventory_ratio,
            self.config,
            strategy,
        )

        # Calculate dynamic order step
        order_step = calculate_order_step(
            self.config["trading"]["order_step"],
            self.volatility,
            self.config,
            strategy,
        )

        # Calculate order sizes
        buy_sizes = calculate_order_sizes(
            self.config["trading"]["order_amount"],
            self.config["trading"]["num_orders"],
            self.inventory_ratio,
            "Buy",
            strategy,
        )

        sell_sizes = calculate_order_sizes(
            self.config["trading"]["order_amount"],
            self.config["trading"]["num_orders"],
            self.inventory_ratio,
            "Sell",
            strategy,
        )

        # Create order ladders
        buy_orders = []
        sell_orders = []

        for i in range(self.config["trading"]["num_orders"]):
            # Buy orders
            buy_price = self.mid_price * (1 - bid_spread - i * order_step)
            buy_orders.append(
                {
                    "side": "Buy",
                    "price": format_price(buy_price),
                    "qty": format_quantity(buy_sizes[i]),
                }
            )

            # Sell orders
            sell_price = self.mid_price * (1 + ask_spread + i * order_step)
            sell_orders.append(
                {
                    "side": "Sell",
                    "price": format_price(sell_price),
                    "qty": format_quantity(sell_sizes[i]),
                }
            )

        return buy_orders, sell_orders

    def execute_market_making_cycle(self):
        """Execute one market making cycle"""
        try:
            # Update market data and position
            market_data = self.get_market_data()
            position = self.get_position()

            if not market_data or not market_data.get("mid"):
                self.logger.warning("No market data available")
                return

            # Check risk limits
            balance = self.get_account_balance()
            risk_ok, risk_msg = self.risk_manager.check_risk_limits(balance, position)

            if not risk_ok:
                self.logger.warning(f"Risk limit breached: {risk_msg}")
                self.order_manager.cancel_all_orders(self.symbol)
                return

            # Check if position should be closed
            if position and position["size"] > 0:
                should_close, reason = self.risk_manager.should_close_position(
                    position, market_data["mid"]
                )

                if should_close:
                    self.logger.info(f"Closing position due to {reason}")
                    self.close_position(position)
                    return

            # Update orders if needed
            if self.order_manager.should_refresh_orders():
                self.logger.info("Refreshing orders...")

                # Cancel existing orders
                self.order_manager.cancel_all_orders(self.symbol)
                time.sleep(0.5)  # Wait for cancellations

                # Calculate new orders
                buy_orders, sell_orders = self.calculate_order_prices_and_sizes()

                # Place new orders
                all_orders = []
                for order in buy_orders + sell_orders:
                    all_orders.append(
                        {
                            "symbol": self.symbol,
                            "side": order["side"],
                            "order_type": self.config["execution"]["order_type"],
                            "qty": order["qty"],
                            "price": order["price"],
                            "time_in_force": self.config["execution"]["time_in_force"],
                            "reduce_only": False,
                            "close_on_trigger": False,
                        }
                    )

                placed_orders = self.order_manager.place_orders(all_orders)
                self.logger.info(f"Placed {len(placed_orders)} orders")

            # Update order tracking
            if not self.config["advanced"]["enable_websocket"]:
                self.order_manager.update_orders(self.symbol)

            # Log performance periodically
            if (datetime.now() - self.last_performance_log).seconds > self.config[
                "monitoring"
            ]["performance_log_interval"]:
                self.log_performance()
                self.last_performance_log = datetime.now()

        except Exception as e:
            self.logger.error(f"Error in market making cycle: {e!s}")

    def close_position(self, position: dict):
        """Close current position"""
        try:
            if position["size"] == 0:
                return

            side = "Sell" if position["side"] == "Buy" else "Buy"

            response = self.client.place_order(
                category=self.config["trading"]["market_type"],
                symbol=self.symbol,
                side=side,
                orderType="Market",
                qty=str(position["size"]),
                reduceOnly=True,
            )

            if response["retCode"] == 0:
                self.logger.info(
                    f"Position closed: {side} {position['size']} {self.symbol}"
                )
            else:
                self.logger.error(f"Failed to close position: {response['retMsg']}")

        except Exception as e:
            self.logger.error(f"Error closing position: {e!s}")

    def log_performance(self):
        """Log performance metrics"""
        try:
            balance = self.get_account_balance()
            self.performance_tracker.update_balance(balance)

            stats = self.performance_tracker.get_statistics()
            risk_metrics = self.risk_manager.get_risk_metrics()
            order_summary = self.order_manager.get_active_orders_summary()

            self.logger.info("=" * 50)
            self.logger.info("PERFORMANCE METRICS")
            self.logger.info("-" * 50)
            self.logger.info(f"Balance: ${balance:.2f}")
            self.logger.info(
                f"P&L: ${stats.get('total_pnl', 0):.2f} ({stats.get('roi', 0):.2f}%)"
            )
            self.logger.info(
                f"Trades: {stats.get('total_trades', 0)} (Win Rate: {stats.get('win_rate', 0):.1f}%)"
            )
            self.logger.info(f"Sharpe Ratio: {stats.get('sharpe_ratio', 0):.2f}")
            self.logger.info("-" * 50)
            self.logger.info("RISK METRICS")
            self.logger.info(f"Drawdown: {risk_metrics['current_drawdown']:.2%}")
            self.logger.info(f"Daily P&L: ${risk_metrics['daily_pnl']:.2f}")
            self.logger.info(f"Risk Score: {risk_metrics['risk_score']:.1f}/100")
            self.logger.info("-" * 50)
            self.logger.info("MARKET STATUS")
            self.logger.info(f"Mid Price: ${self.mid_price:.2f}")
            self.logger.info(f"Spread: {self.spread:.4%}")
            self.logger.info(f"Volatility: {self.volatility:.4%}")
            self.logger.info(
                f"Position: {self.position['size']} @ ${self.position['avg_price']:.2f}"
            )
            self.logger.info(f"Inventory Ratio: {self.inventory_ratio:.2%}")
            self.logger.info("-" * 50)
            self.logger.info("ORDER STATUS")
            self.logger.info(
                f"Active Orders: {order_summary['total_orders']} (Buy: {order_summary['buy_orders']}, Sell: {order_summary['sell_orders']})"
            )
            self.logger.info(f"Order Value: ${order_summary['total_value']:.2f}")
            self.logger.info("=" * 50)

        except Exception as e:
            self.logger.error(f"Error logging performance: {e!s}")

    def run(self):
        """Main bot loop"""
        self.logger.info("Starting Market Maker Bot...")
        self.logger.info(
            f"Trading {self.symbol} on {self.config['trading']['market_type']} market"
        )
        self.running = True

        if self.ws_manager:
            self.ws_manager.connect()

        try:
            while self.running:
                if self.config["advanced"]["enable_websocket"]:
                    # In WebSocket mode, the main loop just waits for messages
                    # and the trading logic is triggered by the _on_ws_message method
                    if self.mid_price > 0:  # wait for market data
                        self.execute_market_making_cycle()
                    time.sleep(1)
                else:
                    self.execute_market_making_cycle()
                    time.sleep(1)  # Main loop interval

        except KeyboardInterrupt:
            self.logger.info("Shutting down bot...")
            self.shutdown()
        except Exception as e:
            self.logger.error(f"Fatal error: {e!s}")
            self.shutdown()

    def shutdown(self):
        """Graceful shutdown"""
        self.running = False
        if self.ws_manager:
            self.ws_manager.disconnect()

        self.logger.info("Cancelling all orders...")
        self.order_manager.cancel_all_orders(self.symbol)

        # Close position if configured
        if self.position["size"] > 0:
            self.logger.info("Closing position...")
            self.close_position(self.position)

        # Final performance log
        self.log_performance()
        self.logger.info("Bot shutdown complete")
