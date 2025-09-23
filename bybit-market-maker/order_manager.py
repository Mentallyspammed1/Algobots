import time
from datetime import datetime


class OrderManager:
    """Advanced order management system"""

    def __init__(self, client, config: dict, logger):
        self.client = client
        self.config = config
        self.logger = logger
        self.active_orders = {}
        self.order_history = []
        self.last_order_update = datetime.now()
        self.order_tracking = {}

    def place_orders(self, orders: list[dict]) -> list[dict]:
        """Place multiple orders with error handling"""
        placed_orders = []

        for order in orders:
            try:
                response = self.client.place_order(
                    category=self.config['trading']['market_type'],
                    symbol=order['symbol'],
                    side=order['side'],
                    orderType=order['order_type'],
                    qty=str(order['qty']),
                    price=str(order['price']),
                    timeInForce=order['time_in_force']
                )

                if response['retCode'] == 0:
                    order_data = response['result']
                    self.active_orders[order_data['orderId']] = {
                        **order,
                        'order_id': order_data['orderId'],
                        'created_at': datetime.now(),
                        'status': 'active'
                    }
                    placed_orders.append(order_data)
                    self.logger.info(f"Order placed: {order_data['orderId']} - {order['side']} {order['qty']} @ {order['price']}")
                else:
                    self.logger.error(f"Failed to place order: {response['retMsg']}")

            except Exception as e:
                self.logger.error(f"Error placing order: {e!s}")

            time.sleep(0.1)  # Rate limiting

        return placed_orders

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all active orders for a symbol"""
        try:
            response = self.client.cancel_all_orders(
                category=self.config['trading']['market_type'],
                symbol=symbol
            )

            if response['retCode'] == 0:
                self.logger.info(f"All orders cancelled for {symbol}")
                # Clear active orders
                self.active_orders = {
                    oid: order for oid, order in self.active_orders.items()
                    if order['symbol'] != symbol
                }
                return True
            self.logger.error(f"Failed to cancel orders: {response['retMsg']}")
            return False

        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e!s}")
            return False

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel a specific order"""
        try:
            response = self.client.cancel_order(
                category=self.config['trading']['market_type'],
                symbol=symbol,
                orderId=order_id
            )

            if response['retCode'] == 0:
                self.logger.info(f"Order cancelled: {order_id}")
                if order_id in self.active_orders:
                    self.active_orders[order_id]['status'] = 'cancelled'
                    del self.active_orders[order_id]
                return True
            self.logger.error(f"Failed to cancel order {order_id}: {response['retMsg']}")
            return False

        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id}: {e!s}")
            return False

    def update_order_from_ws(self, order_data: dict):
        """Update order status from WebSocket data."""
        order_id = order_data.get("orderId")
        if not order_id:
            return

        status = order_data.get("orderStatus")
        if order_id in self.active_orders:
            self.active_orders[order_id]["status"] = status
            if status in ["Filled", "Cancelled", "Rejected"]:
                self.order_history.append(self.active_orders[order_id])
                del self.active_orders[order_id]

    def update_orders(self, symbol: str):
        """Update active orders from exchange"""
        try:
            response = self.client.get_open_orders(
                category=self.config['trading']['market_type'],
                symbol=symbol
            )

            if response['retCode'] == 0:
                exchange_orders = {order['orderId']: order for order in response['result']['list']}

                # Update local order tracking
                for order_id in list(self.active_orders.keys()):
                    if order_id not in exchange_orders:
                        # Order was filled or cancelled
                        if order_id in self.active_orders:
                            self.order_history.append(self.active_orders[order_id])
                            del self.active_orders[order_id]

                # Add new orders not in local tracking
                for order_id, order in exchange_orders.items():
                    if order_id not in self.active_orders:
                        self.active_orders[order_id] = {
                            'order_id': order_id,
                            'symbol': order['symbol'],
                            'side': order['side'],
                            'qty': float(order['qty']),
                            'price': float(order['price']),
                            'status': order['orderStatus'],
                            'created_at': datetime.fromtimestamp(int(order['createdTime']) / 1000)
                        }

                self.last_order_update = datetime.now()

        except Exception as e:
            self.logger.error(f"Error updating orders: {e!s}")

    def should_refresh_orders(self) -> bool:
        """Check if orders need refreshing"""
        if not self.active_orders:
            return True

        # Check if refresh interval has passed
        if (datetime.now() - self.last_order_update).seconds > self.config['trading']['order_refresh_time']:
            return True

        # Check if orders are stale
        for order in self.active_orders.values():
            order_age = (datetime.now() - order['created_at']).seconds
            if order_age > self.config['trading']['order_ttl']:
                return True

        return False

    def get_order_imbalance(self) -> dict:
        """Calculate order book imbalance"""
        buy_volume = sum(order['qty'] for order in self.active_orders.values() if order['side'] == 'Buy')
        sell_volume = sum(order['qty'] for order in self.active_orders.values() if order['side'] == 'Sell')
        total_volume = buy_volume + sell_volume

        if total_volume > 0:
            imbalance = (buy_volume - sell_volume) / total_volume
        else:
            imbalance = 0

        return {
            'buy_volume': buy_volume,
            'sell_volume': sell_volume,
            'total_volume': total_volume,
            'imbalance': imbalance,
            'buy_orders': len([o for o in self.active_orders.values() if o['side'] == 'Buy']),
            'sell_orders': len([o for o in self.active_orders.values() if o['side'] == 'Sell'])
        }

    def get_active_orders_summary(self) -> dict:
        """Get summary of active orders"""
        return {
            'total_orders': len(self.active_orders),
            'buy_orders': len([o for o in self.active_orders.values() if o['side'] == 'Buy']),
            'sell_orders': len([o for o in self.active_orders.values() if o['side'] == 'Sell']),
            'total_value': sum(o['qty'] * o['price'] for o in self.active_orders.values()),
            'oldest_order': min((o['created_at'] for o in self.active_orders.values()), default=None)
        }
