
import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP, WebSocket
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MarketMaker:
    def __init__(self):
        self.config = Config()
        self.session = self._init_session()
        self.ws = None
        self.running = False
        
        # Market data
        self.orderbook = {'bid': [], 'ask': []}
        self.last_price = 0
        self.mid_price = 0
        self.spread = self.config.BASE_SPREAD
        
        # Position tracking
        self.position = 0
        self.avg_entry_price = 0
        self.unrealized_pnl = 0
        
        # Order tracking
        self.active_orders = {'buy': {}, 'sell': {}}
        
        # Volatility tracking
        self.price_history = []
        self.current_volatility = 1.0
        
    def _init_session(self) -> Optional[HTTP]:
        """Initialize HTTP session for REST API calls"""
        if self.config.API_KEY and self.config.API_SECRET:
            return HTTP(
                testnet=self.config.TESTNET,
                api_key=self.config.API_KEY,
                api_secret=self.config.API_SECRET,
                recv_window=5000
            )
        return None
    
    def get_account_balance(self) -> Dict:
        """Get account balance information"""
        if not self.session:
            return {}
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED",
                coin="USDT"
            )
            if response['retCode'] == 0:
                return response['result']['list']
            else:
                logger.error(f"Failed to get balance: {response['retMsg']}")
                return {}
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {}
    
    def get_position(self) -> Dict:
        """Get current position information"""
        if not self.session:
            return {}
        try:
            response = self.session.get_positions(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL
            )
            if response['retCode'] == 0 and response['result']['list']:
                for position_data in response['result']['list']:
                    if position_data['symbol'] == self.config.SYMBOL:
                        self.position = float(position_data['size']) * (1 if position_data['side'] == 'Buy' else -1)
                        self.avg_entry_price = float(position_data['avgPrice']) if position_data['avgPrice'] else 0
                        self.unrealized_pnl = float(position_data['unrealisedPnl']) if position_data['unrealisedPnl'] else 0
                        return position_data
            return {}
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return {}
    
    def get_orderbook(self) -> Dict:
        """Fetch current orderbook"""
        if not self.session:
            return {}
        try:
            response = self.session.get_orderbook(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                limit=50
            )
            if response['retCode'] == 0:
                result = response['result']
                self.orderbook['bid'] = [(float(b[0]), float(b[1])) for b in result['b']]
                self.orderbook['ask'] = [(float(a[0]), float(a[1])) for a in result['a']]
                
                if self.orderbook['bid'] and self.orderbook['ask']:
                    best_bid = self.orderbook['bid'][0][0]
                    best_ask = self.orderbook['ask'][0][0]
                    self.mid_price = (best_bid + best_ask) / 2
                    self.last_price = self.mid_price
                    
                return self.orderbook
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {}
    
    def calculate_volatility(self) -> float:
        """Calculate current market volatility using Bollinger Bands"""
        if len(self.price_history) < self.config.VOLATILITY_WINDOW:
            return 1.0
        
        prices = pd.Series(self.price_history[-self.config.VOLATILITY_WINDOW:])
        sma = prices.rolling(window=self.config.VOLATILITY_WINDOW).mean().iloc[-1]
        std = prices.rolling(window=self.config.VOLATILITY_WINDOW).std().iloc[-1]
        
        if std == 0:
            return 1.0

        upper_band = sma + (self.config.VOLATILITY_STD * std)
        lower_band = sma - (self.config.VOLATILITY_STD * std)
        band_width = (upper_band - lower_band) / sma
        
        # Normalize volatility (1.0 = normal, >1 = high volatility)
        volatility = band_width / 0.02  # 2% is considered normal
        return max(0.5, min(3.0, volatility))  # Cap between 0.5 and 3.0
    
    def calculate_spread(self) -> float:
        """Calculate dynamic spread based on volatility and inventory"""
        base_spread = self.config.BASE_SPREAD
        
        # Adjust for volatility
        volatility_adj = self.current_volatility
        
        # Adjust for inventory risk
        inventory_ratio = abs(self.position) / self.config.MAX_POSITION if self.config.MAX_POSITION > 0 else 0
        inventory_adj = 1 + (inventory_ratio * 0.5)
        
        spread = base_spread * volatility_adj * inventory_adj
        return max(self.config.MIN_SPREAD, min(self.config.MAX_SPREAD, spread))
    
    def calculate_order_prices(self) -> Tuple[List[float], List[float]]:
        """Calculate order prices for multiple levels"""
        if not self.mid_price:
            return [], []
        
        spread = self.calculate_spread()
        bid_prices = []
        ask_prices = []
        
        for i in range(self.config.ORDER_LEVELS):
            level_spread = spread * (1 + i * 0.2)  # Increase spread by 20% per level
            bid_price = self.mid_price * (1 - level_spread)
            ask_price = self.mid_price * (1 + level_spread)
            
            bid_prices.append(round(bid_price, 2))
            ask_prices.append(round(ask_price, 2))
        
        return bid_prices, ask_prices
    
    def calculate_order_sizes(self) -> Tuple[List[float], List[float]]:
        """Calculate order sizes with inventory management"""
        base_size = self.config.MIN_ORDER_SIZE
        increment = self.config.ORDER_SIZE_INCREMENT
        
        buy_sizes = []
        sell_sizes = []
        
        # Inventory skew factor
        inventory_ratio = self.position / self.config.MAX_POSITION if self.config.MAX_POSITION > 0 else 0
        
        for i in range(self.config.ORDER_LEVELS):
            size = base_size + (i * increment)
            
            # Reduce buy size if long, reduce sell size if short
            buy_size = size * (1 - max(0, inventory_ratio))
            sell_size = size * (1 + min(0, inventory_ratio))
            
            buy_sizes.append(round(buy_size, 4))
            sell_sizes.append(round(sell_size, 4))
        
        return buy_sizes, sell_sizes
    
    def place_order(self, side: str, price: float, size: float) -> Optional[str]:
        """Place a single limit order"""
        if not self.session:
            # For backtesting
            order_id = str(uuid.uuid4())
            self.active_orders[side.lower()][order_id] = {'price': price, 'size': size}
            return order_id

        try:
            response = self.session.place_order(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                side=side,
                orderType="Limit",
                qty=str(size),
                price=str(price),
                timeInForce="PostOnly",
                reduceOnly=False
            )
            
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logger.info(f"Placed {side} order: {size} @ {price}, ID: {order_id}")
                self.active_orders[side.lower()][order_id] = {'price': price, 'size': size}
                return order_id
            else:
                logger.error(f"Failed to place order: {response['retMsg']}")
                return None
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_order(self, order_id: str, side: str) -> bool:
        """Cancel a single order"""
        if not self.session:
            if order_id in self.active_orders[side.lower()]:
                del self.active_orders[side.lower()][order_id]
            return True

        try:
            response = self.session.cancel_order(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL,
                orderId=order_id
            )
            if response['retCode'] == 0:
                if order_id in self.active_orders[side.lower()]:
                    del self.active_orders[side.lower()][order_id]
                return True
            return False
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return False
    
    def cancel_all_orders(self) -> bool:
        """Cancel all active orders"""
        if not self.session:
            self.active_orders = {'buy': {}, 'sell': {}}
            return True
        try:
            response = self.session.cancel_all_orders(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL
            )
            if response['retCode'] == 0:
                self.active_orders = {'buy': {}, 'sell': {}}
                logger.info("Cancelled all orders")
                return True
            return False
        except Exception as e:
            logger.error(f"Error canceling all orders: {e}")
            return False
    
    def get_active_orders(self) -> Dict:
        """Get all active orders"""
        if not self.session:
            return self.active_orders
        try:
            response = self.session.get_open_orders(
                category=self.config.CATEGORY,
                symbol=self.config.SYMBOL
            )
            if response['retCode'] == 0:
                self.active_orders = {'buy': {}, 'sell': {}}
                for order in response['result']['list']:
                    side = order['side'].lower()
                    self.active_orders[side][order['orderId']] = {'price': float(order['price']), 'size': float(order['qty'])}
                return self.active_orders
            return {}
        except Exception as e:
            logger.error(f"Error getting active orders: {e}")
            return {}
    
    def update_orders(self):
        """Main order update logic"""
        # For backtesting, we don't need to get data from the exchange
        if self.session:
            self.get_orderbook()
            self.get_position()
        
        if self.last_price:
            self.price_history.append(self.last_price)
            if len(self.price_history) > 100:
                self.price_history.pop(0)
            self.current_volatility = self.calculate_volatility()
        
        if abs(self.position) >= self.config.MAX_POSITION * self.config.INVENTORY_EXTREME:
            logger.warning(f"Inventory extreme reached: {self.position}")
            self.cancel_all_orders()
            self.place_hedge_orders()
            return
        
        self.cancel_all_orders()
        
        bid_prices, ask_prices = self.calculate_order_prices()
        buy_sizes, sell_sizes = self.calculate_order_sizes()
        
        for i in range(self.config.ORDER_LEVELS):
            if i < len(bid_prices) and i < len(buy_sizes) and buy_sizes[i] > 0:
                self.place_order("Buy", bid_prices[i], buy_sizes[i])
            
            if i < len(ask_prices) and i < len(sell_sizes) and sell_sizes[i] > 0:
                self.place_order("Sell", ask_prices[i], sell_sizes[i])
        
        if self.session and abs(self.position) > 0:
            self.place_risk_management_orders()
                
    def place_hedge_orders(self):
        """Place orders to reduce position when inventory is extreme"""
        if self.position > 0:
            hedge_price = self.mid_price * (1 - self.config.MIN_SPREAD)
            hedge_size = min(abs(self.position) * 0.5, self.config.MAX_ORDER_SIZE)
            self.place_order("Sell", hedge_price, hedge_size)
        elif self.position < 0:
            hedge_price = self.mid_price * (1 + self.config.MIN_SPREAD)
            hedge_size = min(abs(self.position) * 0.5, self.config.MAX_ORDER_SIZE)
            self.place_order("Buy", hedge_price, hedge_size)
    
    def place_risk_management_orders(self):
        """Place stop loss and take profit orders"""
        if not self.session or not self.avg_entry_price or self.position == 0:
            return
        
        try:
            if self.position > 0:
                stop_price = self.avg_entry_price * (1 - self.config.STOP_LOSS_PCT)
                tp_price = self.avg_entry_price * (1 + self.config.TAKE_PROFIT_PCT)
                
                self.session.place_order(
                    category=self.config.CATEGORY, symbol=self.config.SYMBOL, side="Sell",
                    orderType="Market", qty=str(abs(self.position)), triggerPrice=str(stop_price),
                    triggerBy="LastPrice", reduceOnly=True
                )
                self.session.place_order(
                    category=self.config.CATEGORY, symbol=self.config.SYMBOL, side="Sell",
                    orderType="Limit", qty=str(abs(self.position)), price=str(tp_price),
                    reduceOnly=True
                )
            else:
                stop_price = self.avg_entry_price * (1 + self.config.STOP_LOSS_PCT)
                tp_price = self.avg_entry_price * (1 - self.config.TAKE_PROFIT_PCT)
                
                self.session.place_order(
                    category=self.config.CATEGORY, symbol=self.config.SYMBOL, side="Buy",
                    orderType="Market", qty=str(abs(self.position)), triggerPrice=str(stop_price),
                    triggerBy="LastPrice", reduceOnly=True
                )
                self.session.place_order(
                    category=self.config.CATEGORY, symbol=self.config.SYMBOL, side="Buy",
                    orderType="Limit", qty=str(abs(self.position)), price=str(tp_price),
                    reduceOnly=True
                )
        except Exception as e:
            logger.error(f"Error placing risk management orders: {e}")
    
    async def run(self):
        """Main bot loop"""
        logger.info("Starting Market Maker Bot...")
        self.running = True
        
        if self.session:
            balance = self.get_account_balance()
            logger.info(f"Account balance: {balance}")
        
        while self.running:
            try:
                self.update_orders()
                await asyncio.sleep(self.config.UPDATE_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Shutting down bot...")
                self.shutdown()
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(self.config.RECONNECT_DELAY)
    
    def shutdown(self):
        """Clean shutdown"""
        self.running = False
        if self.session:
            self.cancel_all_orders()
        logger.info("Bot shutdown complete")
