
import asyncio
import logging
from market_maker import MarketMaker
from websocket_handler import WebSocketHandler

logger = logging.getLogger(__name__)

class EnhancedMarketMaker(MarketMaker):
    def __init__(self):
        super().__init__()
        self.ws_handler = WebSocketHandler(self.handle_ws_message)
        self.last_update_time = 0
        self.order_fill_history = []
        
    def handle_ws_message(self, msg_type: str, data):
        """Process WebSocket messages"""
        try:
            if msg_type == 'orderbook':
                self.process_orderbook_update(data)
            elif msg_type == 'trades':
                self.process_trade_update(data)
            elif msg_type == 'position':
                self.process_position_update(data)
            elif msg_type == 'order':
                self.process_order_update(data)
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
    
    def process_orderbook_update(self, data):
        """Process real-time orderbook updates"""
        if 'b' in data and 'a' in data:
            self.orderbook['bid'] = [(float(b), float(b)) for b in data['b'][:10]]
            self.orderbook['ask'] = [(float(a), float(a)) for a in data['a'][:10]]
            
            if self.orderbook['bid'] and self.orderbook['ask']:
                self.mid_price = (self.orderbook['bid'] + self.orderbook['ask']) / 2
    
    def process_trade_update(self, data):
        """Process trade updates"""
        for trade in data:
            price = float(trade['p'])
            self.last_price = price
            self.price_history.append(price)
            if len(self.price_history) > 100:
                self.price_history.pop(0)
    
    def process_position_update(self, data):
        """Process position updates"""
        for pos in data:
            if pos['symbol'] == self.config.SYMBOL:
                self.position = float(pos['size']) * (1 if pos['side'] == 'Buy' else -1)
                self.avg_entry_price = float(pos['avgPrice']) if pos['avgPrice'] else 0
                self.unrealized_pnl = float(pos['unrealisedPnl']) if pos['unrealisedPnl'] else 0
    
    def process_order_update(self, data):
        """Process order updates"""
        for order in data:
            order_id = order['orderId']
            status = order['orderStatus']
            
            if status == 'Filled':
                self.order_fill_history.append({
                    'order_id': order_id,
                    'side': order['side'],
                    'price': float(order['avgPrice']),
                    'qty': float(order['cumExecQty']),
                    'timestamp': order['updatedTime']
                })
                logger.info(f"Order filled: {order['side']} {order['cumExecQty']} @ {order['avgPrice']}")
                
                # Remove from active orders
                if order_id in self.active_orders.get('buy', []):
                    self.active_orders['buy'].remove(order_id)
                elif order_id in self.active_orders.get('sell', []):
                    self.active_orders['sell'].remove(order_id)
                    
            elif status == 'Cancelled':
                # Remove from active orders
                if order_id in self.active_orders.get('buy', []):
                    self.active_orders['buy'].remove(order_id)
                elif order_id in self.active_orders.get('sell', []):
                    self.active_orders['sell'].remove(order_id)
    
    async def run_with_websocket(self):
        """Run bot with WebSocket support"""
        logger.info("Starting Enhanced Market Maker with WebSocket...")
        
        # Connect WebSocket
        if not self.ws_handler.connect():
            logger.error("Failed to connect WebSocket")
            return
        
        self.running = True
        
        try:
            while self.running:
                # Update orders based on WebSocket data
                current_time = asyncio.get_event_loop().time()
                if current_time - self.last_update_time > self.config.UPDATE_INTERVAL:
                    self.update_orders()
                    self.last_update_time = current_time
                
                await asyncio.sleep(0.1)  # Small delay to prevent CPU overload
                
        except KeyboardInterrupt:
            logger.info("Shutting down bot...")
        finally:
            self.shutdown()
            self.ws_handler.disconnect()
