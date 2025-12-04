from abc import ABC, abstractmethod
from typing import Any

# Assuming logger is available via the client or globally
# from utils.logger import logger # If logger is needed directly here


class StrategyBase(ABC):
    """Abstract Base Class for all trading strategies.
    Defines the interface that all concrete strategies must implement.
    """

    def __init__(self, client, state: dict[str, Any], params: dict[str, Any]):
        """Initializes the strategy.

        Args:
            client: An instance of the BybitClient.
            state: A dictionary to hold the bot's shared state (e.g., positions, orders).
            params: A dictionary of strategy-specific parameters.

        """
        self.client = client
        self.state = state
        self.params = params
        self.logger = self.client.logger  # Access logger from the client instance

        self.symbol = params.get("symbol", "BTCUSDT")  # Default symbol
        self.interval = params.get("interval", "1")  # Default interval

        self.logger.info(
            f"StrategyBase initialized for {self.symbol} ({self.interval})",
        )

    @abstractmethod
    async def on_kline(self, kline_data: dict[str, Any]):
        """Callback method executed when new kline data is received via WebSocket.
        Implement trading logic here based on kline updates.

        Args:
            kline_data: A dictionary containing the latest kline data.
                        Expected format might include:
                        {'timestamp': '...', 'open': '...', 'high': '...', 'low': '...', 'close': '...', ...}

        """

    @abstractmethod
    async def on_position_update(self, position_data: dict[str, Any]):
        """Callback method executed when position data is updated via WebSocket.
        Update internal state and potentially manage TP/SL orders.

        Args:
            position_data: A dictionary containing the latest position data.
                           Expected format might include:
                           {'symbol': '...', 'side': '...', 'size': '...', 'entryPrice': '...', 'unrealisedPnl': '...', ...}

        """

    async def on_order_update(self, order_data: dict[str, Any]):
        """Callback method executed when an order status changes (e.g., filled, cancelled).
        This method can be overridden by strategies that need to react to order events.

        Args:
            order_data: A dictionary containing the order update information.

        """
        self.logger.debug(
            f"Order update received (default handler): {order_data.get('orderId', 'N/A')}",
        )
        # Default implementation does nothing, can be overridden by specific strategies.

    async def generate_signals(self):
        """This method is intended for strategies that generate signals based on
        pre-calculated indicators or other state information, rather than directly
        reacting to kline/position updates. It might be called periodically.
        """
        self.logger.debug("generate_signals called (default handler).")

    async def manage_tp_sl(self, position_data: dict[str, Any]):
        """Manages Take Profit and Stop Loss orders for the current position.
        This is a common task that strategies might need to perform.
        """
        self.logger.debug(f"Managing TP/SL for position: {position_data.get('symbol')}")
        # Placeholder for TP/SL management logic.
        # This might involve checking current price against TP/SL levels
        # and potentially placing/modifying orders via self.client.

    async def enter_position(self, side: str, price: float, qty: str):
        """Helper method to enter a position with TP/SL.
        This can be a common utility for strategies.
        """
        self.logger.info(
            f"Attempting to enter {side} position for {self.symbol} at {price} with qty {qty}",
        )

        # Basic check to avoid entering if already in a position (can be more sophisticated)
        current_pos = self.state.get("current_position")
        if current_pos and current_pos.get("symbol") == self.symbol:
            self.logger.warning(
                f"Already in a position for {self.symbol}. Skipping entry.",
            )
            return

        try:
            # Set leverage (assuming it's managed by the client or strategy)
            leverage = self.params.get("leverage", 10)
            await self.client.set_leverage(symbol=self.symbol, leverage=leverage)

            # Calculate TP/SL based on parameters
            stop_loss_pct = self.params.get("stop_loss_pct", 0.01)
            take_profit_pct = self.params.get("take_profit_pct", 0.02)

            stop_loss_price = str(
                price * (1 - stop_loss_pct)
                if side == "Buy"
                else price * (1 + stop_loss_pct),
            )
            take_profit_price = str(
                price * (1 + take_profit_pct)
                if side == "Buy"
                else price * (1 - take_profit_pct),
            )

            # Place the order (using Market order for simplicity in this helper)
            order_result = await self.client.create_order(
                symbol=self.symbol,
                side=side,
                order_type="Market",
                qty=qty,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
            )

            if order_result and order_result.get("retCode") == 0:
                self.logger.success(
                    f"Successfully placed {side} Market order for {self.symbol}. Order ID: {order_result.get('result', {}).get('orderId')}",
                )
                # Note: Actual state update should ideally happen upon receiving position update
            else:
                self.logger.error(
                    f"Failed to place {side} Market order: {order_result}",
                )

        except Exception as e:
            self.logger.error(f"Error entering position: {e}")

    async def exit_position(self, side: str, price: float):
        """Helper method to exit the current position."""
        self.logger.info(
            f"Attempting to exit {side} position for {self.symbol} at {price}",
        )

        current_pos = self.state.get("current_position")
        if not current_pos or current_pos.get("symbol") != self.symbol:
            self.logger.warning(f"No active position found for {self.symbol} to exit.")
            return

        try:
            # Determine the side to close the position
            exit_side = "Sell" if current_pos.get("side") == "Buy" else "Buy"

            # Place an order to close the position (e.g., Market order)
            order_result = await self.client.create_order(
                symbol=self.symbol,
                side=exit_side,
                order_type="Market",
                qty=str(
                    abs(float(current_pos.get("size"))),
                ),  # Use the size of the current position
                reduce_only=True,  # Ensure this order only closes the position
            )

            if order_result and order_result.get("retCode") == 0:
                self.logger.success(
                    f"Successfully placed exit order for {self.symbol}. Order ID: {order_result.get('result', {}).get('orderId')}",
                )
            else:
                self.logger.error(
                    f"Failed to place exit order for {self.symbol}: {order_result}",
                )

        except Exception as e:
            self.logger.error(f"Error exiting position: {e}")

    # Add other common strategy utilities here, e.g.,
    # async def get_historical_klines(self, symbol, interval, limit): ...
    # async def calculate_indicators(self, kline_data): ...
    # async def check_market_conditions(self): ...
