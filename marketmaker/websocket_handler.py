
import json
import logging
from typing import Callable
from pybit.unified_trading import WebSocket
from config import Config

logger = logging.getLogger(__name__)

class WebSocketHandler:
    def __init__(self, on_message_callback: Callable):
        self.config = Config()
        self.ws = None
        self.on_message = on_message_callback
        self.subscribed_topics = set()
        
    def connect(self):
        """Establish WebSocket connection"""
        try:
            self.ws = WebSocket(
                testnet=self.config.TESTNET,
                channel_type="linear",
                api_key=self.config.API_KEY,
                api_secret=self.config.API_SECRET
            )
            
            # Subscribe to channels
            self.subscribe_orderbook()
            self.subscribe_trades()
            self.subscribe_positions()
            self.subscribe_orders()
            
            logger.info("WebSocket connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            return False
    
    def subscribe_orderbook(self):
        """Subscribe to orderbook updates"""
        def handle_orderbook(message):
            try:
                if 'data' in message:
                    self.on_message('orderbook', message['data'])
            except Exception as e:
                logger.error(f"Error handling orderbook message: {e}")
        
        self.ws.orderbook_stream(
            depth=50,
            symbol=self.config.SYMBOL,
            callback=handle_orderbook
        )
        self.subscribed_topics.add('orderbook')
    
    def subscribe_trades(self):
        """Subscribe to trade updates"""
        def handle_trades(message):
            try:
                if 'data' in message:
                    self.on_message('trades', message['data'])
            except Exception as e:
                logger.error(f"Error handling trades message: {e}")
        
        self.ws.trade_stream(
            symbol=self.config.SYMBOL,
            callback=handle_trades
        )
        self.subscribed_topics.add('trades')
    
    def subscribe_positions(self):
        """Subscribe to position updates"""
        def handle_position(message):
            try:
                if 'data' in message:
                    self.on_message('position', message['data'])
            except Exception as e:
                logger.error(f"Error handling position message: {e}")
        
        self.ws.position_stream(callback=handle_position)
        self.subscribed_topics.add('positions')
    
    def subscribe_orders(self):
        """Subscribe to order updates"""
        def handle_order(message):
            try:
                if 'data' in message:
                    self.on_message('order', message['data'])
            except Exception as e:
                logger.error(f"Error handling order message: {e}")
        
        self.ws.order_stream(callback=handle_order)
        self.subscribed_topics.add('orders')
    
    def disconnect(self):
        """Close WebSocket connection"""
        if self.ws:
            self.ws.exit()
            logger.info("WebSocket disconnected")
