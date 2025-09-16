#!/usr/bin/env python3
"""
Advanced Bybit Trading Bot Template using Pybit and asyncio.

This script provides a complete and professional-grade trading bot framework.
It leverages asyncio for concurrency and websockets for real-time data,
ensuring high performance and responsiveness. The bot includes:

1.  Comprehensive configuration via a dataclass.
2.  Dynamic precision handling for all trading pairs.
3.  Advanced risk management including fixed-risk position sizing and
    daily loss limits.
4.  Real-time PnL and performance metrics tracking.
5.  Support for different order types (market, limit, conditional) and
    advanced features like trailing stop loss.
6.  Secure API key management via environment variables.
7.  A clean, modular structure with a customizable strategy interface.
8.  Robust error handling and WebSocket reconnection logic.

Instructions for Termux (ARM64):
1. Install dependencies:
   `pip install pybit pandas numpy python-dotenv pytz`
2. Create a file named `.env` in the same directory and add your API keys:
   `BYBIT_API_KEY="your_api_key"`
   `BYBIT_API_SECRET="your_api_secret"`
3. Update the `Config` class with your desired settings.
4. Run the bot:
   `python3 your_script_name.py`
"""

import asyncio
import json
import logging
import sys
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import pytz
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Set decimal precision for accurate financial calculations
getcontext().prec = 28

# Load environment variables from a .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bybit_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =====================================================================
# ENUMS AND DATACLASSES
# =====================================================================
class OrderType(Enum):
    """Order types supported by Bybit"""
    MARKET = "Market"
    LIMIT = "Limit"
    LIMIT_MAKER = "Limit Maker"
    STOP_MARKET = "StopMarket"
    STOP_LIMIT = "StopLimit"


class OrderSide(Enum):
    """Order sides"""
    BUY = "Buy"
    SELL = "Sell"


class TimeInForce(Enum):
    """Time in force options"""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    POST_ONLY = "PostOnly"


@dataclass
class MarketInfo:
    """Stores market information including precision settings"""
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    lot_size: Decimal
    status: str

    def format_price(self, price: float) -> Decimal:
        """Format price according to market precision"""
        price_decimal = Decimal(str(price))
        return price_decimal.quantize(self.tick_size, rounding=ROUND_DOWN)

    def format_quantity(self, quantity: float) -> Decimal:
        """Format quantity according to market precision"""
        qty_decimal = Decimal(str(quantity))
        return qty_decimal.quantize(self.lot_size, rounding=ROUND_DOWN)


@dataclass
class Position:
    """Position information"""
    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    mark_price: Decimal
    leverage: int
    position_value: Decimal
    timestamp: datetime


@dataclass
class Order:
    """Order information"""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    status: str
    created_time: datetime
    updated_time: datetime
    time_in_force: TimeInForce
    reduce_only: bool = False
    close_on_trigger: bool = False
    take_profit: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None


@dataclass
class Config:
    """Trading bot configuration"""
    api_key: str = os.getenv("BYBIT_API_KEY")
    api_secret: str = os.getenv("BYBIT_API_SECRET")
    testnet: bool = True
    
    # Trading parameters
    symbol: str = "BTCUSDT"
    category: str = "linear"
    
    # Risk management
    risk_per_trade: float = 0.02  # 2% risk
    leverage: int = 5
    max_drawdown: float = 0.15  # 15% max drawdown
    max_daily_loss: float = 0.10  # 10% max daily loss
    
    # Precision settings
    price_precision: int = 2
    qty_precision: int = 3
    
    # WebSocket settings
    reconnect_attempts: int = 5
    
    # Strategy parameters
    timeframe: str = "15"  # Kline interval (e.g., "1", "5", "60", "D")
    lookback_periods: int = 200  # Number of historical candles
    
    # Timezone
    timezone: str = "UTC"


# =====================================================================
# CORE COMPONENTS
# =====================================================================
class PrecisionHandler:
    """Handle decimal precision for different markets"""
    
    def __init__(self):
        self.markets: Dict[str, MarketInfo] = {}

    def add_market(self, market_info: MarketInfo):
        """Add market information for precision handling"""
        self.markets[market_info.symbol] = market_info
    
    def format_for_market(self, symbol: str, price: Optional[float] = None,
                         quantity: Optional[float] = None) -> Dict[str, Decimal]:
        """Format price and quantity for specific market"""
        if symbol not in self.markets:
            raise ValueError(f"Market {symbol} not found in precision handler")
        
        market = self.markets[symbol]
        result = {}
        
        if price is not None:
            result['price'] = market.format_price(price)
        if quantity is not None:
            result['quantity'] = market.format_quantity(quantity)
            
        return result


class TimezoneManager:
    """Manage timezone conversions for international trading"""
    
    def __init__(self, local_tz: str = 'UTC', exchange_tz: str = 'UTC'):
        self.local_tz = pytz.timezone(local_tz)
        self.exchange_tz = pytz.timezone(exchange_tz)
    
    def to_exchange_time(self, dt: datetime) -> datetime:
        """Convert local time to exchange timezone"""
        if dt.tzinfo is None:
            dt = self.local_tz.localize(dt)
        return dt.astimezone(self.exchange_tz)
    
    def to_local_time(self, dt: datetime) -> datetime:
        """Convert exchange time to local timezone"""
        if dt.tzinfo is None:
            dt = self.exchange_tz.localize(dt)
        return dt.astimezone(self.local_tz)
    
    def parse_timestamp(self, timestamp_ms: int) -> datetime:
        """Parse millisecond timestamp to datetime"""
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        return self.to_local_time(dt)


class RiskManager:
    """Risk management component"""
    
    def __init__(self, config: Config):
        self.config = config
        self.daily_pnl = Decimal('0')
        self.peak_balance = Decimal('0')
        self.current_balance = Decimal('0')
        self.start_of_day_balance = Decimal('0')
        
    def check_position_size(self, size: float, price: float) -> bool:
        """Check if position size is within limits"""
        return Decimal(str(size)) * Decimal(str(price)) <= self.config.max_position_size
    
    def check_drawdown(self) -> bool:
        """Check if current drawdown is within limits"""
        if self.peak_balance == 0:
            return True
        drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
        return drawdown <= self.config.max_drawdown
    
    def check_daily_loss(self) -> bool:
        """Check if daily loss is within limits"""
        daily_loss = (self.start_of_day_balance - self.current_balance) / self.start_of_day_balance
        return daily_loss <= self.config.max_daily_loss
    
    def update_balance(self, balance: float):
        """Update current balance and peak balance"""
        self.current_balance = Decimal(str(balance))
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    def __init__(self, symbol: str, timeframe: str):
        self.symbol = symbol
        self.timeframe = timeframe
        self.indicators = {}
        self.signals = []
        
    @abstractmethod
    def calculate_indicators(self, data: pd.DataFrame):
        """Calculate technical indicators"""
        pass
    
    @abstractmethod
    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Generate trading signal"""
        pass
    
    @abstractmethod
    def calculate_position_size(self, balance: float, price: float) -> float:
        """Calculate position size based on strategy rules"""
        pass


class SimpleMovingAverageStrategy(BaseStrategy):
    """Example strategy using simple moving averages"""
    
    def __init__(self, symbol: str, timeframe: str, fast_period: int = 20,
                 slow_period: int = 50, risk_per_trade: float = 0.02):
        super().__init__(symbol, timeframe)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.risk_per_trade = risk_per_trade
        
    def calculate_indicators(self, data: pd.DataFrame):
        """Calculate SMA indicators"""
        data['SMA_fast'] = data['close'].rolling(window=self.fast_period).mean()
        data['SMA_slow'] = data['close'].rolling(window=self.slow_period).mean()
        self.indicators = data
        
    def generate_signal(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Generate buy/sell signals based on SMA crossover"""
        self.calculate_indicators(data)
        
        if len(data) < self.slow_period:
            return None
            
        current = data.iloc[-1]
        previous = data.iloc[-2]
        
        # Golden cross - buy signal
        if (previous['SMA_fast'] <= previous['SMA_slow'] and
                current['SMA_fast'] > current['SMA_slow']):
            return {
                'action': 'BUY',
                'confidence': 0.7,
                'stop_loss': float(current['close'] * 0.98),
                'take_profit': float(current['close'] * 1.03)
            }
        
        # Death cross - sell signal
        elif (previous['SMA_fast'] >= previous['SMA_slow'] and
              current['SMA_fast'] < current['SMA_slow']):
            return {
                'action': 'SELL',
                'confidence': 0.7,
                'stop_loss': float(current['close'] * 1.02),
                'take_profit': float(current['close'] * 0.97)
            }
            
        return None
    
    def calculate_position_size(self, balance: float, price: float) -> float:
        """Calculate position size based on risk percentage"""
        risk_amount = balance * self.risk_per_trade
        return risk_amount / price


# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================
class BybitTradingBot:
    """Main trading bot class with WebSocket integration"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True,
                 strategy: BaseStrategy = None, risk_manager: RiskManager = None,
                 timezone: str = 'UTC'):
        
        # Initialize connections
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Initialize HTTP session for REST API calls
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret
        )
        
        # Initialize WebSocket connection
        self.ws = WebSocket(
            testnet=testnet,
            channel_type="linear",
            api_key=api_key,
            api_secret=api_secret
        )
        
        # Components
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.precision_handler = PrecisionHandler()
        self.timezone_manager = TimezoneManager(local_tz=timezone)
        
        # State management
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.balance = Decimal('0')
        self.is_running = False
        
        # Callbacks storage
        self.callbacks: Dict[str, List[Callable]] = {
            'kline': [],
            'order': [],
            'position': [],
            'execution': [],
            'wallet': []
        }
        
        logger.info(f"BybitTradingBot initialized for {'testnet' if testnet else 'mainnet'}")
    
    async def load_market_info(self, symbol: str):
        """Load and store market information for a symbol"""
        try:
            response = self.session.get_instruments_info(
                category="linear",
                symbol=symbol
            )
            
            if response['retCode'] == 0:
                instrument = response['result']['list'][0]
                
                market_info = MarketInfo(
                    symbol=symbol,
                    base_asset=instrument['baseCoin'],
                    quote_asset=instrument['quoteCoin'],
                    price_precision=len(str(instrument['priceFilter']['tickSize']).split('.')[-1]),
                    quantity_precision=len(str(instrument['lotSizeFilter']['qtyStep']).split('.')[-1]),
                    min_order_qty=Decimal(str(instrument['lotSizeFilter']['minOrderQty'])),
                    max_order_qty=Decimal(str(instrument['lotSizeFilter']['maxOrderQty'])),
                    min_price=Decimal(str(instrument['priceFilter']['minPrice'])),
                    max_price=Decimal(str(instrument['priceFilter']['maxPrice'])),
                    tick_size=Decimal(str(instrument['priceFilter']['tickSize'])),
                    lot_size=Decimal(str(instrument['lotSizeFilter']['qtyStep'])),
                    status=instrument['status']
                )
                
                self.precision_handler.add_market(market_info)
                logger.info(f"Market info loaded for {symbol}")
                return market_info
            
        except Exception as e:
            logger.error(f"Error loading market info for {symbol}: {e}")
            return None
    
    async def place_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                          quantity: float, price: Optional[float] = None,
                          time_in_force: TimeInForce = TimeInForce.GTC,
                          reduce_only: bool = False, take_profit: Optional[float] = None,
                          stop_loss: Optional[float] = None) -> Optional[str]:
        """Place an order with proper precision handling"""
        
        try:
            # Format values according to market precision
            formatted = self.precision_handler.format_for_market(
                symbol, 
                price=price, 
                quantity=quantity
            )
            
            # Build order parameters
            params = {
                "category": "linear",
                "symbol": symbol,
                "side": side.value,
                "orderType": order_type.value,
                "qty": str(formatted['quantity']),
                "timeInForce": time_in_force.value,
                "reduceOnly": reduce_only,
                "closeOnTrigger": False,
                "positionIdx": 0  # One-way mode
            }
            
            if price and order_type != OrderType.MARKET:
                params["price"] = str(formatted['price'])
            
            # Add TP/SL if provided
            if take_profit:
                tp_formatted = self.precision_handler.format_for_market(
                    symbol, price=take_profit
                )
                params["takeProfit"] = str(tp_formatted['price'])
                params["tpTriggerBy"] = "LastPrice"
            
            if stop_loss:
                sl_formatted = self.precision_handler.format_for_market(
                    symbol, price=stop_loss
                )
                params["stopLoss"] = str(sl_formatted['price'])
                params["slTriggerBy"] = "LastPrice"
            
            # Place the order
            response = self.session.place_order(**params)
            
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logger.info(f"Order placed successfully: {order_id}")
                
                # Store order information
                order = Order(
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    price=formatted.get('price', Decimal('0')),
                    quantity=formatted['quantity'],
                    status="New",
                    created_time=self.timezone_manager.to_local_time(datetime.fromtimestamp(response['time'] / 1000)),
                    updated_time=self.timezone_manager.to_local_time(datetime.fromtimestamp(response['time'] / 1000)),
                    time_in_force=time_in_force,
                    reduce_only=reduce_only,
                    take_profit=tp_formatted.get('price') if take_profit else None,
                    stop_loss=sl_formatted.get('price') if stop_loss else None
                )
                self.orders[order_id] = order
                
                return order_id
            else:
                logger.error(f"Failed to place order: {response['retMsg']}")
                return None
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an existing order"""
        try:
            response = self.session.cancel_order(
                category="linear",
                symbol=symbol,
                orderId=order_id
            )
            
            if response['retCode'] == 0:
                logger.info(f"Order {order_id} cancelled successfully")
                if order_id in self.orders:
                    del self.orders[order_id]
                return True
            else:
                logger.error(f"Failed to cancel order: {response['retMsg']}")
                return False
                
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol"""
        try:
            response = self.session.get_positions(
                category="linear",
                symbol=symbol
            )
            
            if response['retCode'] == 0 and response['result']['list']:
                pos_data = response['result']['list'][0]
                
                position = Position(
                    symbol=symbol,
                    side=pos_data['side'],
                    size=Decimal(str(pos_data['size'])),
                    avg_price=Decimal(str(pos_data['avgPrice'])),
                    unrealized_pnl=Decimal(str(pos_data['unrealisedPnl'])),
                    realized_pnl=Decimal(str(pos_data.get('cumRealisedPnl', '0'))),
                    mark_price=Decimal(str(pos_data['markPrice'])),
                    leverage=int(pos_data.get('leverage', 1)),
                    position_value=Decimal(str(pos_data['positionValue'])),
                    timestamp=self.timezone_manager.parse_timestamp(
                        int(pos_data['updatedTime'])
                    )
                )
                
                self.positions[symbol] = position
                return position
            
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None

    async def update_account_balance(self):
        """Update account balance"""
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED"
            )
            
            if response['retCode'] == 0:
                balance_data = response['result']['list'][0]
                self.balance = Decimal(str(balance_data['totalEquity']))
                
                if self.risk_manager:
                    self.risk_manager.update_balance(float(self.balance))
                    
                logger.info(f"Account balance updated: {self.balance}")
                return self.balance
            
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            return None

    def setup_websocket_streams(self):
        """Setup WebSocket streams with proper callbacks"""
        
        # Handle kline/candlestick data
        def handle_kline(message):
            """Process kline data for strategy"""
            try:
                if 'data' in message:
                    kline_data = message['data']
                    
                    df = pd.DataFrame(kline_data)
                    df['time'] = df['time'].astype(int)
                    df[['open', 'high', 'low', 'close', 'volume', 'turnover']] = df[['open', 'high', 'low', 'close', 'volume', 'turnover']].astype(float)
                    df['time'] = df['time'].apply(self.timezone_manager.parse_timestamp)
                    
                    symbol = message['topic'].split('.')[-1]
                    
                    if symbol not in self.market_data:
                        self.market_data[symbol] = pd.DataFrame()
                    
                    self.market_data[symbol] = pd.concat([self.market_data[symbol], df]).drop_duplicates(subset=['time']).tail(self.strategy.lookback_periods if self.strategy else 200).reset_index(drop=True)
                    
                    # Generate trading signal if strategy is set
                    if self.strategy and self.strategy.symbol == symbol:
                        signal = self.strategy.generate_signal(self.market_data[symbol])
                        if signal:
                            asyncio.run(self.process_signal(signal, symbol))
                    
                    # Execute callbacks
                    for callback in self.callbacks['kline']:
                        callback(message)
                        
            except Exception as e:
                logger.error(f"Error handling kline data: {e}")
        
        # Handle order updates
        def handle_order(message):
            """Process order updates"""
            try:
                if 'data' in message:
                    for order_data in message['data']:
                        order_id = order_data['orderId']
                        
                        # Update order status
                        if order_id in self.orders:
                            self.orders[order_id].status = order_data['orderStatus']
                            self.orders[order_id].updated_time = self.timezone_manager.parse_timestamp(
                                int(order_data['updatedTime'])
                            )
                        
                        # Execute callbacks
                        for callback in self.callbacks['order']:
                            callback(order_data)
                            
            except Exception as e:
                logger.error(f"Error handling order update: {e}")
        
        # Handle position updates
        def handle_position(message):
            """Process position updates"""
            try:
                if 'data' in message:
                    for pos_data in message['data']:
                        symbol = pos_data['symbol']
                        
                        position = Position(
                            symbol=symbol,
                            side=pos_data['side'],
                            size=Decimal(pos_data['size']),
                            avg_price=Decimal(pos_data['avgPrice']),
                            unrealized_pnl=Decimal(pos_data['unrealisedPnl']),
                            realized_pnl=Decimal(pos_data.get('cumRealisedPnl', '0')),
                            mark_price=Decimal(pos_data['markPrice']),
                            leverage=int(pos_data.get('leverage', 1)),
                            position_value=Decimal(pos_data['positionValue']),
                            timestamp=self.timezone_manager.parse_timestamp(
                                int(pos_data['updatedTime'])
                            )
                        )
                        
                        self.positions[symbol] = position
                        
                        # Execute callbacks
                        for callback in self.callbacks['position']:
                            callback(position)
                        
            except Exception as e:
                logger.error(f"Error handling position update: {e}")

        # Handle wallet updates
        def handle_wallet(message):
            try:
                if 'data' in message:
                    for wallet_data in message['data']:
                        self.balance = Decimal(wallet_data['walletBalance'])
                        self.risk_manager.update_balance(float(self.balance))
                        self.risk_manager.daily_pnl = Decimal(wallet_data.get('realisedPnl', '0'))
                        logger.info(f"Wallet balance updated: {self.balance}")
            except Exception as e:
                logger.error(f"Error handling wallet update: {e}")
    
        # Set up the handlers
        self.ws.kline_stream(
            callback=handle_kline,
            symbol=self.strategy.symbol if self.strategy else "BTCUSDT",
            interval=self.strategy.timeframe if self.strategy else "5"
        )
        
        # Subscribe to private streams for account updates
        self.ws.order_stream(callback=handle_order)
        self.ws.position_stream(callback=handle_position)
        self.ws.wallet_stream(callback=handle_wallet)
        
        logger.info("WebSocket streams configured")

    def maintain_websocket_connection(self):
        """Maintain WebSocket connection with heartbeat"""
        """Implements ping-pong mechanism as recommended by Bybit"""
        import threading
        
        def send_ping():
            """Send ping every 20 seconds to maintain connection"""
            while self.is_running:
                try:
                    # Send ping message as per Bybit documentation
                    self.ws.send(json.dumps({"op": "ping"}))
                    logger.debug("Ping sent to maintain connection")
                except Exception as e:
                    logger.error(f"Error sending ping: {e}")
                
                time.sleep(20)  # Bybit recommends 20 seconds
        
        # Start ping thread
        ping_thread = threading.Thread(target=send_ping, daemon=True)
        ping_thread.start()
        logger.info("WebSocket heartbeat started")

    async def process_signal(self, signal: Dict[str, Any], symbol: str):
        """Process trading signal from strategy"""
        try:
            # Check risk management
            if not self.risk_manager:
                logger.warning("No risk manager configured")
                return
            
            # Get current price
            current_price = float(self.market_data[symbol].iloc[-1]['close'])
            
            # Calculate position size
            position_size = self.strategy.calculate_position_size(
                float(self.balance),
                current_price
            )
            
            # Check if we can trade
            if not self.risk_manager.can_trade(position_size):
                logger.warning("Risk check failed, skipping trade")
                return
            
            # Check existing position
            current_position = await self.get_position(symbol)
            
            if signal['action'] == 'BUY':
                if current_position and current_position.side == 'Sell':
                    # Close short position first
                    await self.place_order(
                        symbol=symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=float(current_position.size),
                        reduce_only=True
                    )
                
                # Open long position
                order_id = await self.place_order(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=position_size,
                    take_profit=signal.get('take_profit'),
                    stop_loss=signal.get('stop_loss')
                )
                
                if order_id:
                    logger.info(f"Buy order placed: {order_id}")
                    
            elif signal['action'] == 'SELL':
                if current_position and current_position.side == 'Buy':
                    # Close long position first
                    await self.place_order(
                        symbol=symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=float(current_position.size),
                        reduce_only=True
                    )
                
                # Open short position
                order_id = await self.place_order(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=position_size,
                    take_profit=signal.get('take_profit'),
                    stop_loss=signal.get('stop_loss')
                )
                
                if order_id:
                    logger.info(f"Sell order placed: {order_id}")
                    
        except Exception as e:
            logger.error(f"Error processing signal: {e}")

    async def start(self):
        """Start the trading bot"""
        try:
            self.is_running = True
            
            # Load market information
            if self.strategy:
                await self.load_market_info(self.strategy.symbol)
            
            # Update initial balance
            await self.update_account_balance()
            
            # Setup WebSocket streams
            self.setup_websocket_streams()
            
            # Maintain connection
            self.maintain_websocket_connection()
            
            logger.info("Trading bot started successfully")
            
            # Keep the bot running
            while self.is_running:
                await asyncio.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            await self.stop()
        except Exception as e:
            logger.error(f"Error in bot main loop: {e}")
            await self.stop()

    async def stop(self):
        """Stop the trading bot"""
        self.is_running = False
        
        # Close all open positions
        for symbol, position in self.positions.items():
            if position.size > 0:
                side = OrderSide.SELL if position.side == 'Buy' else OrderSide.BUY
                await self.place_order(
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=float(position.size),
                    reduce_only=True
                )
        
        # Cancel all open orders
        for order_id, order in self.orders.items():
            if order.status in ['New', 'PartiallyFilled']:
                await self.cancel_order(order.symbol, order_id)
        
        self.ws.exit()
        logger.info("Trading bot stopped")

    def add_callback(self, event_type: str, callback: Callable):
        """Add custom callback for events"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            logger.info(f"Callback added for {event_type}")

# Example usage
if __name__ == '__main__':
    # Configuration
    API_KEY = "your_api_key"
    API_SECRET = "your_api_secret"
    
    # Initialize strategy
    strategy = SimpleMovingAverageStrategy(
        symbol="BTCUSDT",
        timeframe="5",  # 5 minute candles
        fast_period=20,
        slow_period=50,
        risk_per_trade=0.02
    )
    
    # Initialize risk manager
    risk_manager = RiskManager(
        max_position_size=10000,  # Max $10,000 per position
        max_drawdown=0.2,  # 20% max drawdown
        max_daily_loss=1000,  # $1,000 max daily loss
        leverage=5
    )
    
    # Initialize bot
    bot = BybitTradingBot(
        api_key=API_KEY,
        api_secret=API_SECRET,
        testnet=True,  # Use testnet for testing
        strategy=strategy,
        risk_manager=risk_manager,
        timezone='America/New_York'
    )
    
    # Add custom callbacks if needed
    def on_position_update(position):
        print(f"Position updated: {position.symbol} - Size: {position.size}")
    
    bot.add_callback('position', on_position_update)
    
    # Start the bot
    asyncio.run(bot.start())

#!/usr/bin/env python3
"""
Advanced Bybit Trading Bot Template v2.0 with Enhanced Features

This enhanced version includes:
- Proper async/await implementation throughout
- Advanced order management with trailing stops
- Performance metrics and trade analytics
- Database support for trade history
- Backtesting capabilities
- Advanced risk management with position sizing algorithms
- Multi-strategy support
- WebSocket reconnection with exponential backoff
- State persistence and recovery
- Real-time performance dashboard
- Telegram notifications support
"""

import asyncio
import json
import logging
import sys
import os
import time
import sqlite3
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Union, Tuple
from collections import deque
import aiofiles
import pytz
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# Set decimal precision for accurate financial calculations
getcontext().prec = 28

# Load environment variables
load_dotenv()

# Configure logging with rotating file handler
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Setup comprehensive logging configuration"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # File handler for all logs
    file_handler = RotatingFileHandler(
        'bybit_bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # File handler for trades only
    trade_handler = RotatingFileHandler(
        'trades.log',
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10
    )
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(simple_formatter)
    trade_handler.addFilter(lambda record: 'TRADE' in str(record.msg))
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(trade_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# =====================================================================
# ENHANCED ENUMS AND DATACLASSES
# =====================================================================

class OrderType(Enum):
    """Order types supported by Bybit"""
    MARKET = "Market"
    LIMIT = "Limit"
    LIMIT_MAKER = "Limit Maker"
    STOP_MARKET = "StopMarket"
    STOP_LIMIT = "StopLimit"
    TAKE_PROFIT_MARKET = "TakeProfitMarket"
    TAKE_PROFIT_LIMIT = "TakeProfitLimit"

class OrderStatus(Enum):
    """Order status types"""
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    TRIGGERED = "Triggered"
    DEACTIVATED = "Deactivated"

class PositionMode(Enum):
    """Position modes"""
    ONE_WAY = 0
    HEDGE_MODE = 3

@dataclass
class TradeMetrics:
    """Track trading performance metrics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    max_drawdown: Decimal = Decimal('0')
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    average_win: Decimal = Decimal('0')
    average_loss: Decimal = Decimal('0')
    largest_win: Decimal = Decimal('0')
    largest_loss: Decimal = Decimal('0')
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    def update_metrics(self, pnl: Decimal, is_win: bool):
        """Update metrics with new trade result"""
        self.total_trades += 1
        self.total_pnl += pnl
        
        if is_win:
            self.winning_trades += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
            self.average_win = ((self.average_win * (self.winning_trades - 1) + pnl) / 
                               self.winning_trades)
            self.largest_win = max(self.largest_win, pnl)
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
            self.average_loss = ((self.average_loss * (self.losing_trades - 1) + abs(pnl)) / 
                                self.losing_trades)
            self.largest_loss = min(self.largest_loss, pnl)
        
        # Calculate win rate
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        
        # Calculate profit factor
        if self.average_loss > 0:
            self.profit_factor = float(self.average_win / self.average_loss)

@dataclass
class Config:
    """Enhanced trading bot configuration"""
    # API Configuration
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = True
    
    # Trading parameters
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    category: str = "linear"
    
    # Risk management
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_positions: int = 3
    leverage: int = 5
    max_drawdown: float = 0.15  # 15% max drawdown
    max_daily_loss: float = 0.10  # 10% max daily loss
    position_sizing_method: str = "kelly"  # fixed, kelly, optimal_f
    
    # Order management
    use_trailing_stop: bool = True
    trailing_stop_percentage: float = 0.02  # 2%
    partial_take_profit: bool = True
    partial_tp_levels: List[Tuple[float, float]] = field(
        default_factory=lambda: [(0.01, 0.25), (0.02, 0.5), (0.03, 0.25)]
    )  # (price_change, position_percentage)
    
    # WebSocket settings
    reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    heartbeat_interval: int = 20
    
    # Strategy parameters
    timeframes: List[str] = field(default_factory=lambda: ["5", "15", "60"])
    lookback_periods: int = 200
    
    # Performance tracking
    save_metrics_interval: int = 300  # Save metrics every 5 minutes
    
    # Database
    database_path: str = "trading_bot.db"
    
    # Notifications
    enable_notifications: bool = True
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    
    # Backtesting
    backtest_start_date: str = "2023-01-01"
    backtest_end_date: str = "2024-01-01"
    backtest_initial_balance: float = 10000.0
    
    # Timezone
    timezone: str = "UTC"

# =====================================================================
# DATABASE MANAGER
# =====================================================================

class DatabaseManager:
    """Manage database operations for trade history and metrics"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    pnl REAL,
                    fees REAL,
                    strategy TEXT,
                    notes TEXT
                )
            ''')
            
            # Metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_balance REAL,
                    total_pnl REAL,
                    win_rate REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    metrics_json TEXT
                )
            ''')
            
            # Orders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL,
                    status TEXT,
                    filled_qty REAL,
                    avg_fill_price REAL
                )
            ''')
            
            conn.commit()
    
    async def save_trade(self, trade: Dict[str, Any]):
        """Save trade to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (symbol, side, quantity, entry_price, exit_price, 
                                  pnl, fees, strategy, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade['symbol'], trade['side'], trade['quantity'],
                trade['entry_price'], trade.get('exit_price'),
                trade.get('pnl'), trade.get('fees'),
                trade.get('strategy'), trade.get('notes')
            ))
            conn.commit()
    
    async def save_metrics(self, metrics: TradeMetrics, balance: float):
        """Save performance metrics to database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO metrics (total_balance, total_pnl, win_rate, 
                                   sharpe_ratio, max_drawdown, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                balance, float(metrics.total_pnl), metrics.win_rate,
                metrics.sharpe_ratio, float(metrics.max_drawdown),
                json.dumps(asdict(metrics))
            ))
            conn.commit()
    
    async def get_trade_history(self, symbol: Optional[str] = None, 
                               days: int = 30) -> pd.DataFrame:
        """Get trade history from database"""
        with sqlite3.connect(self.db_path) as conn:
            query = '''
                SELECT * FROM trades 
                WHERE timestamp > datetime('now', '-{} days')
            '''.format(days)
            
            if symbol:
                query += f" AND symbol = '{symbol}'"
            
            return pd.read_sql_query(query, conn)

# =====================================================================
# ENHANCED RISK MANAGER
# =====================================================================

class EnhancedRiskManager:
    """Advanced risk management with multiple position sizing algorithms"""
    
    def __init__(self, config: Config, db_manager: DatabaseManager):
        self.config = config
        self.db_manager = db_manager
        self.daily_pnl = Decimal('0')
        self.peak_balance = Decimal('0')
        self.current_balance = Decimal('0')
        self.start_of_day_balance = Decimal('0')
        self.open_positions: Dict[str, Position] = {}
        self.trade_history = deque(maxlen=100)  # Keep last 100 trades
        
    def calculate_position_size(self, symbol: str, signal_strength: float,
                              current_price: float) -> float:
        """Calculate position size using configured method"""
        if self.config.position_sizing_method == "fixed":
            return self._fixed_position_size(current_price)
        elif self.config.position_sizing_method == "kelly":
            return self._kelly_criterion_size(symbol, signal_strength, current_price)
        elif self.config.position_sizing_method == "optimal_f":
            return self._optimal_f_size(symbol, current_price)
        else:
            return self._fixed_position_size(current_price)
    
    def _fixed_position_size(self, current_price: float) -> float:
        """Fixed percentage risk position sizing"""
        risk_amount = float(self.current_balance) * self.config.risk_per_trade
        return risk_amount / current_price
    
    def _kelly_criterion_size(self, symbol: str, signal_strength: float,
                            current_price: float) -> float:
        """Kelly Criterion position sizing"""
        # Get historical win rate and average win/loss for this symbol
        history = [t for t in self.trade_history if t.get('symbol') == symbol]
        
        if len(history) < 10:  # Not enough history, use fixed sizing
            return self._fixed_position_size(current_price)
        
        wins = [t for t in history if t['pnl'] > 0]
        losses = [t for t in history if t['pnl'] < 0]
        
        if not wins or not losses:
            return self._fixed_position_size(current_price)
        
        win_rate = len(wins) / len(history)
        avg_win = sum(t['pnl'] for t in wins) / len(wins)
        avg_loss = abs(sum(t['pnl'] for t in losses) / len(losses))
        
        # Kelly percentage = (p * b - q) / b
        # where p = win rate, q = loss rate, b = avg win / avg loss
        b = avg_win / avg_loss
        kelly_percentage = (win_rate * b - (1 - win_rate)) / b
        
        # Apply Kelly fraction with safety factor
        kelly_fraction = max(0, min(kelly_percentage * 0.25, 0.25))  # Max 25% of Kelly
        
        # Adjust by signal strength
        adjusted_fraction = kelly_fraction * signal_strength
        
        position_value = float(self.current_balance) * adjusted_fraction
        return position_value / current_price
    
    def _optimal_f_size(self, symbol: str, current_price: float) -> float:
        """Optimal f position sizing (Ralph Vince method)"""
        history = [t for t in self.trade_history if t.get('symbol') == symbol]
        
        if len(history) < 20:  # Not enough history
            return self._fixed_position_size(current_price)
        
        # Find the f value that maximizes terminal wealth
        returns = [t['pnl'] / t['position_value'] for t in history]
        
        best_f = 0.01
        best_twr = 0
        
        for f in np.arange(0.01, 0.5, 0.01):
            twr = 1.0  # Terminal Wealth Relative
            for ret in returns:
                twr *= (1 + f * ret)
            
            if twr > best_twr:
                best_twr = twr
                best_f = f
        
        # Apply safety factor
        safe_f = best_f * 0.25  # Use 25% of optimal f
        
        position_value = float(self.current_balance) * safe_f
        return position_value / current_price
    
    def check_risk_limits(self, symbol: str, position_size: float,
                         current_price: float) -> Tuple[bool, str]:
        """Comprehensive risk checks"""
        position_value = position_size * current_price
        
        # Check maximum positions
        if len(self.open_positions) >= self.config.max_positions:
            return False, "Maximum number of positions reached"
        
        # Check position size limit
        max_position_value = float(self.current_balance) * 0.3  # Max 30% per position
        if position_value > max_position_value:
            return False, f"Position size exceeds limit: {position_value} > {max_position_value}"
        
        # Check total exposure
        total_exposure = sum(float(p.size * p.mark_price) for p in self.open_positions.values())
        if total_exposure + position_value > float(self.current_balance) * self.config.leverage:
            return False, "Total exposure exceeds leverage limit"
        
        # Check drawdown
        if self.peak_balance > 0:
            current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
            if current_drawdown > Decimal(str(self.config.max_drawdown)):
                return False, f"Maximum drawdown exceeded: {current_drawdown:.2%}"
        
        # Check daily loss
        if self.start_of_day_balance > 0:
            daily_loss = (self.start_of_day_balance - self.current_balance) / self.start_of_day_balance
            if daily_loss > Decimal(str(self.config.max_daily_loss)):
                return False, f"Maximum daily loss exceeded: {daily_loss:.2%}"
        
        return True, "Risk checks passed"
    
    def update_balance(self, balance: float):
        """Update balance and track peaks"""
        self.current_balance = Decimal(str(balance))
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        # Reset daily tracking at midnight UTC
        now = datetime.now(timezone.utc)
        if hasattr(self, 'last_update_date'):
            if now.date() > self.last_update_date:
                self.start_of_day_balance = self.current_balance
                self.daily_pnl = Decimal('0')
        else:
            self.start_of_day_balance = self.current_balance
        
        self.last_update_date = now.date()
    
    def add_trade_result(self, trade: Dict[str, Any]):
        """Add trade to history for position sizing calculations"""
        self.trade_history.append(trade)
        self.daily_pnl += Decimal(str(trade.get('pnl', 0)))

# =====================================================================
# ENHANCED STRATEGIES
# =====================================================================

class StrategySignal:
    """Standardized strategy signal"""
    def __init__(self, action: str, symbol: str, strength: float = 1.0,
                 stop_loss: Optional[float] = None, 
                 take_profit: Optional[float] = None,
                 trailing_stop: Optional[float] = None,
                 entry_price: Optional[float] = None,
                 metadata: Optional[Dict] = None):
        self.action = action  # BUY, SELL, CLOSE
        self.symbol = symbol
        self.strength = max(0.0, min(1.0, strength))  # Clamp between 0 and 1
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.trailing_stop = trailing_stop
        self.entry_price = entry_price
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc)

class EnhancedBaseStrategy(ABC):
    """Enhanced base strategy with more features"""
    
    def __init__(self, symbol: str, timeframes: List[str], config: Config):
        self.symbol = symbol
        self.timeframes = timeframes
        self.config = config
        self.indicators = {}
        self.signals_history = deque(maxlen=100)
        self.is_initialized = False
        
    @abstractmethod
    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]):
        """Calculate indicators for multiple timeframes"""
        pass
    
    @abstractmethod
    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Generate trading signal"""
        pass
    
    @abstractmethod
    async def on_position_update(self, position: Position):
        """Handle position updates (for dynamic strategy adjustments)"""
        pass
    
    def calculate_signal_strength(self, confirmations: List[bool]) -> float:
        """Calculate signal strength based on confirmations"""
        if not confirmations:
            return 0.0
        return sum(confirmations) / len(confirmations)

class MultiTimeframeStrategy(EnhancedBaseStrategy):
    """Advanced multi-timeframe strategy with multiple indicators"""
    
    def __init__(self, symbol: str, config: Config):
        super().__init__(symbol, ["5", "15", "60"], config)
        self.rsi_period = 14
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.bb_period = 20
        self.bb_std = 2
        self.volume_ma_period = 20
        
    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]):
        """Calculate comprehensive technical indicators"""
        for timeframe, df in data.items():
            if len(df) < 50:
                continue
            
            # Price action
            df['sma_20'] = df['close'].rolling(20).mean()
            df['sma_50'] = df['close'].rolling(50).mean()
            df['ema_20'] = df['close'].ewm(span=20).mean()
            
            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD
            exp1 = df['close'].ewm(span=self.macd_fast).mean()
            exp2 = df['close'].ewm(span=self.macd_slow).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=self.macd_signal).mean()
            df['macd_hist'] = df['macd'] - df['macd_signal']
            
            # Bollinger Bands
            df['bb_middle'] = df['close'].rolling(self.bb_period).mean()
            bb_std = df['close'].rolling(self.bb_period).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * self.bb_std)
            df['bb_lower'] = df['bb_middle'] - (bb_std * self.bb_std)
            df['bb_width'] = df['bb_upper'] - df['bb_lower']
            df['bb_percent'] = (df['close'] - df['bb_lower']) / df['bb_width']
            
            # Volume indicators
            df['volume_sma'] = df['volume'].rolling(self.volume_ma_period).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            
            # ATR for stop loss calculation
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            df['atr'] = true_range.rolling(14).mean()
            
            self.indicators[timeframe] = df
    
    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        """Generate signal based on multiple timeframe analysis"""
        await self.calculate_indicators(data)
        
        if not all(tf in self.indicators for tf in self.timeframes):
            return None
        
        # Get current values from each timeframe
        signals = []
        
        for tf in self.timeframes:
            df = self.indicators[tf]
            if len(df) < 50:
                continue
            
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Trend confirmation
            trend_up = current['ema_20'] > current['sma_50']
            trend_strength = abs(current['ema_20'] - current['sma_50']) / current['close']
            
            # Momentum signals
            rsi_oversold = current['rsi'] < 30 and prev['rsi'] < 30
            rsi_overbought = current['rsi'] > 70 and prev['rsi'] > 70
            
            # MACD signals
            macd_cross_up = (prev['macd'] <= prev['macd_signal'] and 
                           current['macd'] > current['macd_signal'])
            macd_cross_down = (prev['macd'] >= prev['macd_signal'] and 
                              current['macd'] < current['macd_signal'])
            
            # Bollinger Band signals
            bb_squeeze = current['bb_width'] < df['bb_width'].rolling(50).mean().iloc[-1]
            price_at_lower_bb = current['bb_percent'] < 0.1
            price_at_upper_bb = current['bb_percent'] > 0.9
            
            # Volume confirmation
            volume_surge = current['volume_ratio'] > 1.5
            
            # Compile signals for this timeframe
            tf_signal = {
                'timeframe': tf,
                'trend_up': trend_up,
                'trend_strength': trend_strength,
                'buy_signals': [
                    trend_up,
                    rsi_oversold,
                    macd_cross_up,
                    price_at_lower_bb,
                    volume_surge
                ],
                'sell_signals': [
                    not trend_up,
                    rsi_overbought,
                    macd_cross_down,
                    price_at_upper_bb,
                    volume_surge
                ]
            }
            signals.append(tf_signal)
        
        # Analyze signals across timeframes
        buy_confirmations = []
        sell_confirmations = []
        
        # Weight signals by timeframe (higher timeframes have more weight)
        weights = {'5': 0.2, '15': 0.3, '60': 0.5}
        
        for signal in signals:
            weight = weights.get(signal['timeframe'], 0.33)
            buy_score = sum(signal['buy_signals']) / len(signal['buy_signals']) * weight
            sell_score = sum(signal['sell_signals']) / len(signal['sell_signals']) * weight
            
            buy_confirmations.append(buy_score)
            sell_confirmations.append(sell_score)
        
        total_buy_score = sum(buy_confirmations)
        total_sell_score = sum(sell_confirmations)
        
        # Generate signal if score is strong enough
        min_score_threshold = 0.6
        current_price = float(data['5'].iloc[-1]['close'])
        atr = float(self.indicators['15'].iloc[-1]['atr'])
        
        if total_buy_score > min_score_threshold and total_buy_score > total_sell_score:
            return StrategySignal(
                action='BUY',
                symbol=self.symbol,
                strength=min(1.0, total_buy_score),
                stop_loss=current_price - (atr * 2),
                take_profit=current_price + (atr * 3),
                trailing_stop=atr * 1.5,
                entry_price=current_price,
                metadata={
                    'strategy': 'MultiTimeframe',
                    'buy_score': total_buy_score,
                    'signals': signals
                }
            )
        
        elif total_sell_score > min_score_threshold and total_sell_score > total_buy_score:
            return StrategySignal(
                action='SELL',
                symbol=self.symbol,
                strength=min(1.0, total_sell_score),
                stop_loss=current_price + (atr * 2),
                take_profit=current_price - (atr * 3),
                trailing_stop=atr * 1.5,
                entry_price=current_price,
                metadata={
                    'strategy': 'MultiTimeframe',
                    'sell_score': total_sell_score,
                    'signals': signals
                }
            )
        
        return None
    
    async def on_position_update(self, position: Position):
        """Handle position updates for dynamic adjustments"""
        # Could implement dynamic stop loss adjustments based on position performance
        pass

# =====================================================================
# WEBSOCKET MANAGER
# =====================================================================

class WebSocketManager:
    """Manage WebSocket connections with reconnection logic"""
    
    def __init__(self, config: Config, api_key: str, api_secret: str):
        self.config = config
        self.api_key = api_key
        self.api_secret = api_secret
        self.ws = None
        self.reconnect_count = 0
        self.subscriptions = {}
        self.is_connected = False
        self.connection_lock = asyncio.Lock()
        
    async def connect(self):
        """Establish WebSocket connection"""
        async with self.connection_lock:
            try:
                self.ws = WebSocket(
                    testnet=self.config.testnet,
                    channel_type="linear",
                    api_key=self.api_key,
                    api_secret=self.api_secret
                )
                self.is_connected = True
                self.reconnect_count = 0
                logger.info("WebSocket connected successfully")
                
                # Resubscribe to previous channels
                await self._resubscribe()
                
            except Exception as e:
                logger.error(f"WebSocket connection failed: {e}")
                self.is_connected = False
                raise
    
    async def disconnect(self):
        """Disconnect WebSocket"""
        if self.ws:
            self.ws.exit()
            self.is_connected = False
            logger.info("WebSocket disconnected")
    
    async def reconnect(self):
        """Reconnect with exponential backoff"""
        while self.reconnect_count < self.config.reconnect_attempts:
            delay = min(
                self.config.reconnect_delay * (2 ** self.reconnect_count),
                self.config.max_reconnect_delay
            )
            
            logger.info(f"Reconnecting in {delay} seconds... (attempt {self.reconnect_count + 1})")
            await asyncio.sleep(delay)
            
            try:
                await self.connect()
                return True
            except Exception as e:
                logger.error(f"Reconnection attempt {self.reconnect_count + 1} failed: {e}")
                self.reconnect_count += 1
        
        logger.error("Max reconnection attempts reached")
        return False
    
    async def subscribe_kline(self, symbol: str, interval: str, callback: Callable):
        """Subscribe to kline stream"""
        subscription_key = f"kline.{interval}.{symbol}"
        self.subscriptions[subscription_key] = callback
        
        if self.is_connected:
            self.ws.kline_stream(
                callback=self._wrap_callback(callback),
                symbol=symbol,
                interval=interval
            )
            logger.info(f"Subscribed to {subscription_key}")
    
    async def subscribe_orderbook(self, symbol: str, depth: int, callback: Callable):
        """Subscribe to orderbook stream"""
        subscription_key = f"orderbook.{depth}.{symbol}"
        self.subscriptions[subscription_key] = callback
        
        if self.is_connected:
            self.ws.orderbook_stream(
                depth=depth,
                symbol=symbol,
                callback=self._wrap_callback(callback)
            )
            logger.info(f"Subscribed to {subscription_key}")
    
    async def subscribe_trades(self, symbol: str, callback: Callable):
        """Subscribe to trades stream"""
        subscription_key = f"trades.{symbol}"
        self.subscriptions[subscription_key] = callback
        
        if self.is_connected:
            self.ws.trade_stream(
                symbol=symbol,
                callback=self._wrap_callback(callback)
            )
            logger.info(f"Subscribed to {subscription_key}")
    
    async def subscribe_private_streams(self, callbacks: Dict[str, Callable]):
        """Subscribe to private account streams"""
        if self.is_connected:
            if 'order' in callbacks:
                self.ws.order_stream(callback=self._wrap_callback(callbacks['order']))
                self.subscriptions['order'] = callbacks['order']
            
            if 'position' in callbacks:
                self.ws.position_stream(callback=self._wrap_callback(callbacks['position']))
                self.subscriptions['position'] = callbacks['position']
            
            if 'wallet' in callbacks:
                self.ws.wallet_stream(callback=self._wrap_callback(callbacks['wallet']))
                self.subscriptions['wallet'] = callbacks['wallet']
            
            logger.info("Subscribed to private streams")
    
    def _wrap_callback(self, callback: Callable) -> Callable:
        """Wrap callback with error handling"""
        def wrapped_callback(message):
            try:
                # Handle connection errors
                if isinstance(message, dict) and message.get('ret_code') != 0:
                    logger.error(f"WebSocket error: {message}")
                    if message.get('ret_code') in [10001, 10002, 10003]:  # Auth errors
                        asyncio.create_task(self.reconnect())
                    return
                
                callback(message)
            except Exception as e:
                logger.error(f"Error in WebSocket callback: {e}", exc_info=True)
        
        return wrapped_callback
    
    async def _resubscribe(self):
        """Resubscribe to all previous subscriptions after reconnection"""
        # Re-subscribe to public streams
        for key, callback in self.subscriptions.items():
            parts = key.split('.')
            
            if parts[0] == 'kline' and len(parts) == 3:
                interval, symbol = parts[1], parts[2]
                self.ws.kline_stream(
                    callback=self._wrap_callback(callback),
                    symbol=symbol,
                    interval=interval
                )
            elif parts[0] == 'orderbook' and len(parts) == 3:
                depth, symbol = int(parts[1]), parts[2]
                self.ws.orderbook_stream(
                    depth=depth,
                    symbol=symbol,
                    callback=self._wrap_callback(callback)
                )
            elif parts[0] == 'trades' and len(parts) == 2:
                symbol = parts[1]
                self.ws.trade_stream(
                    symbol=symbol,
                    callback=self._wrap_callback(callback)
                )
            elif parts[0] in ['order', 'position', 'wallet']:
                # Private streams
                getattr(self.ws, 
#!/usr/bin/env python3
"""
Bybit Advanced Trading Bot Framework v3.0

This script is a professional-grade, fully asynchronous trading bot framework for Bybit.
It combines the best features of the provided examples and introduces significant enhancements
for robustness, performance, and functionality.

Key Features:
1.  **Fully Asynchronous:** Built entirely on asyncio for high performance. All I/O
    (network, database, file) is non-blocking.
2.  **Modular Architecture:** Cleanly separated components for risk management, order
    execution, state persistence, notifications, and strategy.
3.  **State Persistence & Recovery:** Saves critical state to a file, allowing the bot
    to be stopped and restarted without losing performance metrics or position context.
4.  **Integrated Backtesting Engine:** A complete backtester to evaluate strategies on
    historical data before going live.
5.  **Advanced Risk Management:** Features multiple position sizing algorithms (e.g., fixed-risk)
    and persistent tracking of drawdown and daily loss limits.
6.  **Advanced Order Management:** Supports market/limit orders, native trailing stops,
    and multi-level partial take-profits.
7.  **Robust WebSocket Handling:** A dedicated manager for WebSocket connections with
    automatic reconnection and exponential backoff.
8.  **Real-time Notifications:** Integrated, non-blocking Telegram alerts for trades,
    errors, and status updates.
9.  **Dynamic Precision Handling:** Fetches and uses market-specific precision for
    price and quantity, avoiding exchange rejections.
10. **Multi-Symbol/Multi-Strategy Ready:** The architecture is designed to be extended
    to handle multiple trading pairs and strategies concurrently.

Instructions for Use:
1.  Install dependencies:
    `pip install pybit pandas numpy python-dotenv pytz aiosqlite aiofiles aiohttp`
2.  Create a `.env` file in the same directory with your credentials:
    BYBIT_API_KEY="YOUR_API_KEY"
    BYBIT_API_SECRET="YOUR_API_SECRET"
    TELEGRAM_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
    TELEGRAM_CHAT_ID="YOUR_TELEGRAM_CHAT_ID"
3.  Configure the `Config` class below with your desired settings (symbols, strategy, etc.).
4.  Run the bot:
    - For live trading: `python3 your_script_name.py live`
    - For backtesting: `python3 your_script_name.py backtest`
"""

import asyncio
import json
import logging
import sys
import os
import time
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN, getcontext
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple
from logging.handlers import RotatingFileHandler

import aiofiles
import aiohttp
import aiosqlite
import numpy as np
import pandas as pd
import pytz
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# --- INITIAL SETUP ---

# Set decimal precision for accurate financial calculations
getcontext().prec = 28

# Load environment variables from .env file
load_dotenv()

# --- LOGGING CONFIGURATION ---

def setup_logging():
    """Setup comprehensive logging configuration."""
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    
    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # File Handler (for all logs)
    file_handler = RotatingFileHandler('bybit_bot.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Trade Handler (for trade-specific logs)
    trade_handler = RotatingFileHandler('trades.log', maxBytes=5*1024*1024, backupCount=10)
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(simple_formatter)
    trade_handler.addFilter(lambda record: "TRADE" in record.getMessage())

    log.addHandler(console_handler)
    log.addHandler(file_handler)
    log.addHandler(trade_handler)
    
    return log

logger = setup_logging()


# =====================================================================
# ENUMS AND DATACLASSES
# =====================================================================

class OrderType(Enum):
    MARKET = "Market"
    LIMIT = "Limit"

class OrderSide(Enum):
    BUY = "Buy"
    SELL = "Sell"

class OrderStatus(Enum):
    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

@dataclass
class MarketInfo:
    """Stores market information including precision settings."""
    symbol: str
    tick_size: Decimal
    lot_size: Decimal

    def format_price(self, price: float) -> str:
        return str(Decimal(str(price)).quantize(self.tick_size, rounding=ROUND_DOWN))

    def format_quantity(self, quantity: float) -> str:
        return str(Decimal(str(quantity)).quantize(self.lot_size, rounding=ROUND_DOWN))

@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    mark_price: Decimal
    leverage: int

@dataclass
class Order:
    """Represents an order."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    status: str

@dataclass
class StrategySignal:
    """Standardized object for strategy signals."""
    action: str  # 'BUY', 'SELL', 'CLOSE'
    symbol: str
    strength: float = 1.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_distance: Optional[float] = None
    metadata: Dict = field(default_factory=dict)

@dataclass
class Config:
    """Enhanced trading bot configuration."""
    # API Configuration
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = True
    
    # Trading Parameters
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    category: str = "linear"
    timeframes: List[str] = field(default_factory=lambda: ["5", "15"])
    lookback_periods: int = 200
    
    # Risk Management
    leverage: int = 5
    risk_per_trade: float = 0.01  # 1% of equity per trade
    max_daily_loss_percent: float = 0.05  # 5% max daily loss
    max_drawdown_percent: float = 0.15  # 15% max drawdown from peak equity
    
    # Order Management
    use_trailing_stop: bool = True
    partial_tp_levels: List[Tuple[float, float]] = field(
        default_factory=lambda: [(0.01, 0.50), (0.02, 0.50)]
    )  # (price_change_%, position_size_%)
    
    # System Settings
    database_path: str = "trading_bot.db"
    state_file_path: str = "bot_state.pkl"
    
    # Notifications
    enable_notifications: bool = True
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    
    # Backtesting
    backtest_initial_balance: float = 10000.0
    backtest_start_date: str = "2023-01-01"
    backtest_end_date: str = "2024-01-01"

# =====================================================================
# CORE COMPONENTS
# =====================================================================

class NotificationManager:
    """Handles sending notifications via Telegram."""
    def __init__(self, config: Config):
        self.config = config
        self.session = aiohttp.ClientSession() if config.enable_notifications else None

    async def send_message(self, message: str):
        if not self.config.enable_notifications or not self.session:
            return
        
        url = f"https://api.telegram.org/bot{self.config.telegram_token}/sendMessage"
        payload = {
            'chat_id': self.config.telegram_chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        try:
            async with self.session.post(url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send Telegram message: {await response.text()}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

    async def close(self):
        if self.session:
            await self.session.close()

class DatabaseManager:
    """Manages asynchronous database operations for trade history."""
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT NOT NULL, side TEXT NOT NULL,
                    quantity REAL NOT NULL, entry_price REAL NOT NULL,
                    exit_price REAL, pnl REAL, fees REAL, notes TEXT
                )
            ''')
            await db.commit()

    async def save_trade(self, trade: Dict[str, Any]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO trades (symbol, side, quantity, entry_price, exit_price, pnl, fees, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade['symbol'], trade['side'], trade['quantity'], trade['entry_price'],
                trade.get('exit_price'), trade.get('pnl'), trade.get('fees'),
                json.dumps(trade.get('notes'))
            ))
            await db.commit()

class StateManager:
    """Manages saving and loading the bot's state."""
    def __init__(self, file_path: str):
        self.file_path = file_path

    async def save_state(self, state: Dict):
        try:
            async with aiofiles.open(self.file_path, 'wb') as f:
                await f.write(pickle.dumps(state))
            logger.info(f"Bot state saved to {self.file_path}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")

    async def load_state(self) -> Optional[Dict]:
        if not os.path.exists(self.file_path):
            logger.warning("State file not found. Starting with a fresh state.")
            return None
        try:
            async with aiofiles.open(self.file_path, 'rb') as f:
                state = pickle.loads(await f.read())
            logger.info(f"Bot state loaded from {self.file_path}")
            return state
        except Exception as e:
            logger.error(f"Error loading state: {e}. Starting fresh.")
            return None

class EnhancedRiskManager:
    """Manages risk, including equity tracking and position sizing."""
    def __init__(self, config: Config):
        self.config = config
        self.equity = Decimal(str(config.backtest_initial_balance))
        self.peak_equity = self.equity
        self.daily_start_equity = self.equity
        self.last_trade_date = datetime.now(timezone.utc).date()

    def update_equity(self, new_equity: Decimal):
        self.equity = new_equity
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        
        today = datetime.now(timezone.utc).date()
        if today > self.last_trade_date:
            self.daily_start_equity = self.equity
            self.last_trade_date = today

    def check_risk_limits(self) -> Tuple[bool, str]:
        """Checks if any risk limits have been breached."""
        # Check max drawdown
        drawdown = (self.peak_equity - self.equity) / self.peak_equity
        if drawdown > Decimal(str(self.config.max_drawdown_percent)):
            return False, f"Max drawdown limit of {self.config.max_drawdown_percent:.2%} breached."

        # Check daily loss
        daily_loss = (self.daily_start_equity - self.equity) / self.daily_start_equity
        if daily_loss > Decimal(str(self.config.max_daily_loss_percent)):
            return False, f"Max daily loss limit of {self.config.max_daily_loss_percent:.2%} breached."
        
        return True, "Risk limits OK."

    def calculate_position_size(self, stop_loss_price: float, current_price: float) -> float:
        """Calculates position size based on fixed fractional risk."""
        risk_amount = self.equity * Decimal(str(self.config.risk_per_trade))
        price_risk = abs(Decimal(str(current_price)) - Decimal(str(stop_loss_price)))
        if price_risk == 0: return 0.0
        
        position_size = risk_amount / price_risk
        return float(position_size)

    def get_state(self) -> Dict:
        return {
            'equity': self.equity,
            'peak_equity': self.peak_equity,
            'daily_start_equity': self.daily_start_equity,
            'last_trade_date': self.last_trade_date
        }

    def set_state(self, state: Dict):
        self.equity = state.get('equity', self.equity)
        self.peak_equity = state.get('peak_equity', self.peak_equity)
        self.daily_start_equity = state.get('daily_start_equity', self.daily_start_equity)
        self.last_trade_date = state.get('last_trade_date', self.last_trade_date)
        logger.info("RiskManager state restored.")

class OrderManager:
    """Handles placing, tracking, and managing orders."""
    def __init__(self, config: Config, session: HTTP, precision_handler: Dict[str, MarketInfo]):
        self.config = config
        self.session = session
        self.precision = precision_handler

    async def place_order(self, symbol: str, side: OrderSide, order_type: OrderType,
                          quantity: float, price: Optional[float] = None,
                          stop_loss: Optional[float] = None,
                          trailing_stop_distance: Optional[float] = None) -> Optional[Dict]:
        market_info = self.precision[symbol]
        formatted_qty = market_info.format_quantity(quantity)

        params = {
            "category": self.config.category,
            "symbol": symbol,
            "side": side.value,
            "orderType": order_type.value,
            "qty": formatted_qty,
            "positionIdx": 0  # One-way mode
        }

        if order_type == OrderType.LIMIT and price:
            params["price"] = market_info.format_price(price)
        
        if stop_loss:
            params["stopLoss"] = market_info.format_price(stop_loss)
        
        if self.config.use_trailing_stop and trailing_stop_distance:
            params["tpslMode"] = "Partial"
            params["trailingStop"] = market_info.format_price(trailing_stop_distance)

        try:
            response = self.session.place_order(**params)
            if response['retCode'] == 0:
                order_id = response['result']['orderId']
                logger.info(f"TRADE: Order placed for {symbol}: {side.value} {formatted_qty} @ {order_type.value}. OrderID: {order_id}")
                return response['result']
            else:
                logger.error(f"Failed to place order: {response['retMsg']}")
                return None
        except Exception as e:
            logger.error(f"Exception placing order: {e}")
            return None

    async def close_position(self, position: Position):
        """Closes an entire position with a market order."""
        side = OrderSide.SELL if position.side == 'Buy' else OrderSide.BUY
        market_info = self.precision[position.symbol]
        
        params = {
            "category": self.config.category,
            "symbol": position.symbol,
            "side": side.value,
            "orderType": OrderType.MARKET.value,
            "qty": str(position.size),
            "reduceOnly": True,
            "positionIdx": 0
        }
        try:
            response = self.session.place_order(**params)
            if response['retCode'] == 0:
                logger.info(f"TRADE: Closing position for {position.symbol} with size {position.size}")
                return response['result']
            else:
                logger.error(f"Failed to close position {position.symbol}: {response['retMsg']}")
                return None
        except Exception as e:
            logger.error(f"Exception closing position: {e}")
            return None

# =====================================================================
# STRATEGY
# =====================================================================

class BaseStrategy(ABC):
    """Abstract base class for trading strategies."""
    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        pass

class SMACrossoverStrategy(BaseStrategy):
    """A simple multi-timeframe SMA Crossover strategy."""
    def __init__(self, config: Config, fast_period: int = 20, slow_period: int = 50):
        super().__init__(config)
        self.fast_period = fast_period
        self.slow_period = slow_period

    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[StrategySignal]:
        symbol = self.config.symbols[0]  # Assuming single symbol for this strategy
        primary_tf = self.config.timeframes[0]
        
        if primary_tf not in data or len(data[primary_tf]) < self.slow_period:
            return None

        df = data[primary_tf]
        df['SMA_fast'] = df['close'].rolling(window=self.fast_period).mean()
        df['SMA_slow'] = df['close'].rolling(window=self.slow_period).mean()

        current = df.iloc[-1]
        previous = df.iloc[-2]

        # Golden Cross (Buy Signal)
        if previous['SMA_fast'] <= previous['SMA_slow'] and current['SMA_fast'] > current['SMA_slow']:
            stop_loss = float(current['low'] * Decimal('0.995'))
            return StrategySignal(
                action='BUY',
                symbol=symbol,
                stop_loss=stop_loss,
                trailing_stop_distance=float(current['close'] - stop_loss)
            )

        # Death Cross (Sell Signal)
        elif previous['SMA_fast'] >= previous['SMA_slow'] and current['SMA_fast'] < current['SMA_slow']:
            stop_loss = float(current['high'] * Decimal('1.005'))
            return StrategySignal(
                action='SELL',
                symbol=symbol,
                stop_loss=stop_loss,
                trailing_stop_distance=float(stop_loss - current['close'])
            )
            
        return None

# =====================================================================
# BACKTESTER
# =====================================================================

class Backtester:
    """Runs a strategy against historical data."""
    def __init__(self, config: Config, strategy: BaseStrategy, notifier: NotificationManager):
        self.config = config
        self.strategy = strategy
        self.notifier = notifier
        self.balance = config.backtest_initial_balance
        self.trades = []
        self.position = None

    async def _get_historical_data(self, symbol: str, timeframe: str) -> pd.DataFrame:
        session = HTTP(testnet=self.config.testnet)
        all_data = []
        start_time = int(datetime.strptime(self.config.backtest_start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_time = int(datetime.strptime(self.config.backtest_end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
        
        while start_time < end_time:
            response = session.get_kline(
                category=self.config.category,
                symbol=symbol,
                interval=timeframe,
                start=start_time,
                limit=1000
            )
            if response['retCode'] == 0 and response['result']['list']:
                data = response['result']['list']
                all_data.extend(data)
                start_time = int(data[0][0]) + 1
            else:
                break
            await asyncio.sleep(0.2) # Rate limit
        
        df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        df = df.apply(pd.to_numeric)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df

    async def run(self):
        logger.info("--- Starting Backtest ---")
        await self.notifier.send_message("🚀 *Backtest Started*")
        
        historical_data = {}
        for symbol in self.config.symbols:
            historical_data[symbol] = {}
            for tf in self.config.timeframes:
                logger.info(f"Fetching historical data for {symbol} on {tf}m timeframe...")
                historical_data[symbol][tf] = await self._get_historical_data(symbol, tf)

        primary_df = historical_data[self.config.symbols[0]][self.config.timeframes[0]]
        
        for i in range(self.config.lookback_periods, len(primary_df)):
            current_data = {}
            for symbol in self.config.symbols:
                current_data[symbol] = {}
                for tf in self.config.timeframes:
                    # This is a simplification; proper multi-TF backtesting requires aligning timestamps
                    current_data[symbol][tf] = historical_data[symbol][tf].iloc[:i]

            signal = await self.strategy.generate_signal({s: d for s, d in current_data.items() for tf, d in d.items()})
            current_price = primary_df.iloc[i]['close']

            # Simulate position management
            if self.position and signal and signal.action == 'CLOSE':
                self._close_position(current_price)

            if not self.position and signal and signal.action in ['BUY', 'SELL']:
                self._open_position(signal, current_price)
        
        self._generate_report()
        await self.notifier.send_message("✅ *Backtest Finished*. Check logs for report.")

    def _open_position(self, signal: StrategySignal, price: float):
        # Simplified position sizing for backtest
        size = (self.balance * 0.1) / price
        self.position = {
            'side': signal.action,
            'entry_price': price,
            'size': size,
            'symbol': signal.symbol
        }
        logger.info(f"Backtest: Opened {signal.action} position for {size:.4f} {signal.symbol} at {price}")

    def _close_position(self, price: float):
        pnl = (price - self.position['entry_price']) * self.position['size']
        if self.position['side'] == 'SELL':
            pnl = -pnl
        
        self.balance += pnl
        self.trades.append({
            'pnl': pnl,
            'entry_price': self.position['entry_price'],
            'exit_price': price,
            'side': self.position['side']
        })
        logger.info(f"Backtest: Closed position. PnL: {pnl:.2f}, New Balance: {self.balance:.2f}")
        self.position = None

    def _generate_report(self):
        logger.info("--- Backtest Report ---")
        if not self.trades:
            logger.info("No trades were executed.")
            return

        total_trades = len(self.trades)
        wins = [t for t in self.trades if t['pnl'] > 0]
        losses = [t for t in self.trades if t['pnl'] <= 0]
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        total_pnl = sum(t['pnl'] for t in self.trades)
        
        report = f"""
        Total Trades: {total_trades}
        Final Balance: {self.balance:.2f}
        Total PnL: {total_pnl:.2f}
        Win Rate: {win_rate:.2%}
        Profit Factor: {abs(sum(t['pnl'] for t in wins) / sum(t['pnl'] for t in losses)) if losses else 'inf'}
        """
        logger.info(report)

# =====================================================================
# MAIN TRADING BOT CLASS
# =====================================================================

class BybitAdvancedBot:
    def __init__(self, config: Config):
        self.config = config
        self.is_running = False
        self.session = HTTP(testnet=config.testnet, api_key=config.api_key, api_secret=config.api_secret)
        self.ws = WebSocket(testnet=config.testnet, channel_type=config.category, api_key=config.api_key, api_secret=config.api_secret)
        
        self.notifier = NotificationManager(config)
        self.db_manager = DatabaseManager(config.database_path)
        self.state_manager = StateManager(config.state_file_path)
        self.risk_manager = EnhancedRiskManager(config)
        self.strategy = SMACrossoverStrategy(config) # Replace with your desired strategy
        
        self.precision_handler: Dict[str, MarketInfo] = {}
        self.market_data: Dict[str, Dict[str, pd.DataFrame]] = {}
        self.positions: Dict[str, Position] = {}
        self.order_manager: Optional[OrderManager] = None

    async def start(self):
        self.is_running = True
        try:
            await self.initialize()
            await self.notifier.send_message(f"🚀 *Bot Started* on {'Testnet' if self.config.testnet else 'Mainnet'}")
            
            self.setup_websocket_streams()
            
            while self.is_running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Bot start cancelled.")
        except Exception as e:
            logger.error(f"Critical error in bot start: {e}", exc_info=True)
            await self.notifier.send_message(f"🚨 *CRITICAL ERROR*: Bot shutting down. Reason: {e}")
        finally:
            await self.stop()

    async def initialize(self):
        """Prepare the bot for trading."""
        logger.info("Initializing bot...")
        await self.db_manager.initialize()
        
        # Load market precision info
        for symbol in self.config.symbols:
            await self._load_market_info(symbol)
        self.order_manager = OrderManager(self.config, self.session, self.precision_handler)

        # Load state
        state = await self.state_manager.load_state()
        if state and 'risk_manager' in state:
            self.risk_manager.set_state(state['risk_manager'])

        # Set leverage
        for symbol in self.config.symbols:
            self._set_leverage(symbol)

        # Fetch initial data and positions
        await asyncio.gather(
            self._fetch_initial_data(),
            self._update_wallet_balance(),
            self._update_positions()
        )
        logger.info("Initialization complete.")

    async def _load_market_info(self, symbol: str):
        response = self.session.get_instruments_info(category=self.config.category, symbol=symbol)
        if response['retCode'] == 0:
            info = response['result']['list'][0]
            self.precision_handler[symbol] = MarketInfo(
                symbol=symbol,
                tick_size=Decimal(info['priceFilter']['tickSize']),
                lot_size=Decimal(info['lotSizeFilter']['qtyStep'])
            )
            logger.info(f"Loaded market info for {symbol}")
        else:
            raise Exception(f"Could not load market info for {symbol}: {response['retMsg']}")

    def _set_leverage(self, symbol: str):
        try:
            self.session.set_leverage(
                category=self.config.category,
                symbol=symbol,
                buyLeverage=str(self.config.leverage),
                sellLeverage=str(self.config.leverage)
            )
            logger.info(f"Set leverage for {symbol} to {self.config.leverage}x")
        except Exception as e:
            logger.error(f"Failed to set leverage for {symbol}: {e}")

    async def _fetch_initial_data(self):
        """Fetch historical data to warm up indicators."""
        for symbol in self.config.symbols:
            self.market_data[symbol] = {}
            for tf in self.config.timeframes:
                response = self.session.get_kline(
                    category=self.config.category,
                    symbol=symbol,
                    interval=tf,
                    limit=self.config.lookback_periods
                )
                if response['retCode'] == 0 and response['result']['list']:
                    df = pd.DataFrame(response['result']['list'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
                    df = df.apply(pd.to_numeric)
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    self.market_data[symbol][tf] = df.sort_values('timestamp').reset_index(drop=True)
                    logger.info(f"Fetched initial {len(df)} candles for {symbol} on {tf}m timeframe.")
                else:
                    logger.error(f"Could not fetch initial kline for {symbol} {tf}m: {response['retMsg']}")

    def setup_websocket_streams(self):
        """Configure and subscribe to WebSocket streams."""
        for symbol in self.config.symbols:
            for tf in self.config.timeframes:
                self.ws.kline_stream(symbol=symbol, interval=tf, callback=self._handle_kline)
        
        self.ws.position_stream(callback=self._handle_position)
        self.ws.wallet_stream(callback=self._handle_wallet)
        logger.info("WebSocket streams configured.")

    def _handle_kline(self, msg):
        """Callback for kline updates."""
        try:
            data = msg['data'][0]
            if not data['confirm']: return # Process only confirmed candles

            symbol = msg['topic'].split('.')[-1]
            tf = msg['topic'].split('.')[-2]
            
            new_candle = pd.DataFrame([{
                'timestamp': pd.to_datetime(int(data['start']), unit='ms'),
                'open': float(data['open']), 'high': float(data['high']),
                'low': float(data['low']), 'close': float(data['close']),
                'volume': float(data['volume']), 'turnover': float(data['turnover'])
            }])
            
            df = self.market_data[symbol][tf]
            df = pd.concat([df, new_candle]).drop_duplicates(subset=['timestamp'], keep='last')
            self.market_data[symbol][tf] = df.tail(self.config.lookback_periods).reset_index(drop=True)
            
            # On the primary timeframe, trigger signal generation
            if tf == self.config.timeframes[0]:
                asyncio.create_task(self._process_strategy_tick())
        except Exception as e:
            logger.error(f"Error in kline handler: {e}", exc_info=True)

    async def _process_strategy_tick(self):
        """Generate and process signal from the strategy."""
        can_trade, reason = self.risk_manager.check_risk_limits()
        if not can_trade:
            logger.warning(f"Trading halted: {reason}")
            return

        signal = await self.strategy.generate_signal(self.market_data[self.config.symbols[0]])
        if not signal:
            return

        current_position = self.positions.get(signal.symbol)
        
        if signal.action == 'CLOSE' and current_position:
            logger.info(f"Strategy signaled to CLOSE position for {signal.symbol}")
            await self.order_manager.close_position(current_position)
            return

        if signal.action == 'BUY' and (not current_position or current_position.side == 'Sell'):
            if current_position: await self.order_manager.close_position(current_position)
            await self._execute_trade(signal)
        
        elif signal.action == 'SELL' and (not current_position or current_position.side == 'Buy'):
            if current_position: await self.order_manager.close_position(current_position)
            await self._execute_trade(signal)

    async def _execute_trade(self, signal: StrategySignal):
        """Validate risk and execute a trade signal."""
        current_price = self.market_data[signal.symbol][self.config.timeframes[0]].iloc[-1]['close']
        
        size = self.risk_manager.calculate_position_size(signal.stop_loss, current_price)
        if size <= 0:
            logger.warning("Calculated position size is zero or negative. Skipping trade.")
            return

        side = OrderSide.BUY if signal.action == 'BUY' else OrderSide.SELL
        order_result = await self.order_manager.place_order(
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=size,
            stop_loss=signal.stop_loss,
            trailing_stop_distance=signal.trailing_stop_distance
        )
        if order_result:
            await self.notifier.send_message(f"✅ *TRADE EXECUTED*: {signal.action} {size:.4f} {signal.symbol}")

    def _handle_position(self, msg):
        """Callback for position updates."""
        for pos_data in msg['data']:
            if pos_data['symbol'] in self.config.symbols:
                size = Decimal(pos_data['size'])
                if size > 0:
                    self.positions[pos_data['symbol']] = Position(
                        symbol=pos_data['symbol'], side=pos_data['side'], size=size,
                        avg_price=Decimal(pos_data['avgPrice']),
                        unrealized_pnl=Decimal(pos_data['unrealisedPnl']),
                        mark_price=Decimal(pos_data['markPrice']),
                        leverage=int(pos_data['leverage'])
                    )
                elif pos_data['symbol'] in self.positions:
                    del self.positions[pos_data['symbol']]
                    logger.info(f"Position for {pos_data['symbol']} is now closed.")

    def _handle_wallet(self, msg):
        """Callback for wallet updates."""
        balance = msg['data'][0]['coin'][0]['equity']
        self.risk_manager.update_equity(Decimal(balance))

    async def _update_wallet_balance(self):
        response = self.session.get_wallet_balance(accountType="UNIFIED")
        if response['retCode'] == 0:
            balance = response['result']['list'][0]['totalEquity']
            self.risk_manager.update_equity(Decimal(balance))
            logger.info(f"Wallet balance updated: {balance}")

    async def _update_positions(self):
        response = self.session.get_positions(category=self.config.category, symbol=self.config.symbols[0])
        if response['retCode'] == 0:
            self._handle_position(response['result'])

    async def stop(self):
        """Gracefully stop the bot."""
        if not self.is_running: return
        self.is_running = False
        logger.info("Stopping bot...")
        
        # Save final state
        current_state = {'risk_manager': self.risk_manager.get_state()}
        await self.state_manager.save_state(current_state)
        
        self.ws.exit()
        await self.notifier.close()
        logger.info("Bot stopped.")
        await self.notifier.send_message("🛑 *Bot Stopped*")

# =====================================================================
# SCRIPT ENTRYPOINT
# =====================================================================

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ['live', 'backtest']:
        print("Usage: python your_script_name.py [live|backtest]")
        sys.exit(1)

    mode = sys.argv[1]
    config = Config()
    
    if mode == 'live':
        bot = BybitAdvancedBot(config)
        loop = asyncio.get_event_loop()
        try:
            # Register signal handlers for graceful shutdown
            # import signal
            # for sig in (signal.SIGINT, signal.SIGTERM):
            #     loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
            
            loop.run_until_complete(bot.start())
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Stopping bot...")
            loop.run_until_complete(bot.stop())
        finally:
            loop.close()

    elif mode == 'backtest':
        strategy = SMACrossoverStrategy(config)
        notifier = NotificationManager(config)
        backtester = Backtester(config, strategy, notifier)
        asyncio.run(backtester.run())
        #!/usr/bin/env python3
"""
Bybit Advanced Trading Bot Framework v3.1

This script is a professional-grade, fully asynchronous trading bot framework for Bybit.
It combines the best features of the provided examples and introduces significant enhancements
for robustness, performance, and functionality.
"""

import asyncio
import json
import logging
import sys
import os
import time
import pickle
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP, getcontext
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, Tuple, Deque
from logging.handlers import RotatingFileHandler
from collections import deque
import aiofiles
import aiohttp
import aiosqlite
import numpy as np
import pandas as pd
import pytz
from dotenv import load_dotenv
from pybit.unified_trading import HTTP, WebSocket

# --- INITIAL SETUP ---

# Set decimal precision for accurate financial calculations
getcontext().prec = 28

# Load environment variables from .env file
load_dotenv()

# --- LOGGING CONFIGURATION ---

def setup_logging():
    """Setup comprehensive logging configuration."""
    log = logging.getLogger()
    log.setLevel(logging.INFO)
    
    # Formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    simple_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    
    # File Handler (for all logs)
    file_handler = RotatingFileHandler('bybit_bot.log', maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    
    # Trade Handler (for trade-specific logs)
    trade_handler = RotatingFileHandler('trades.log', maxBytes=5*1024*1024, backupCount=10)
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(simple_formatter)
    trade_handler.addFilter(lambda record: "TRADE" in record.getMessage())
    
    # Error Handler (for errors only)
    error_handler = RotatingFileHandler('errors.log', maxBytes=5*1024*1024, backupCount=5)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    
    # Add handlers to logger
    log.addHandler(console_handler)
    log.addHandler(file_handler)
    log.addHandler(trade_handler)
    log.addHandler(error_handler)

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
@dataclass
class Config:
    """Enhanced trading bot configuration"""
    
    # API Configuration
    api_key: str = field(default_factory=lambda: os.getenv("BYBIT_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("BYBIT_API_SECRET", ""))
    testnet: bool = True
    
    # Trading parameters
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    category: str = "linear"
    timeframe: str = "5"  # Primary timeframe for strategy
    timeframes: List[str] = field(default_factory=lambda: ["5", "15", "60"])
    lookback_periods: int = 200
    leverage: int = 5
    
    # Risk management
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_positions: int = 3
    max_drawdown: float = 0.15  # 15% max drawdown
    max_daily_loss: float = 0.10  # 10% max daily loss
    position_sizing_method: str = "fixed"  # fixed, kelly, optimal_f
    
    # Order management
    use_trailing_stop: bool = True
    trailing_stop_percentage: float = 0.02  # 2%
    use_partial_tp: bool = True
    partial_tp_levels: List[Tuple[float, float]] = field(
        default_factory=lambda: [(0.01, 0.25), (0.02, 0.5), (0.03, 0.25)]
    )  # (price_change, position_percentage)
    
    # WebSocket settings
    reconnect_attempts: int = 5
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    heartbeat_interval: int = 20
    
    # Strategy parameters
    strategy_name: str = "SMACrossover"  # Strategy class name to load
    
    # Performance tracking
    save_metrics_interval: int = 300  # Save metrics every 5 minutes
    track_trade_metrics: bool = True
    
    # Database
    database_path: str = "trading_bot.db"
    state_file_path: str = "bot_state.pkl"
    
    # Notifications
    enable_notifications: bool = True
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    
    # Backtesting
    backtest: bool = False
    backtest_start_date: str = "2023-01-01"
    backtest_end_date: str = "2024-01-01"
    backtest_initial_balance: float = 10000.0
    
    # Timezone
    timezone: str = "UTC"
    
    # Advanced settings
    use_ema: bool = True
    ema_short: int = 20
    ema_long: int = 50
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    bb_period: int = 20
    bb_std: float = 2.0
    volume_ma_period: int = 20
    atr_period: int = 14

# --- DATA CLASSES ---
@dataclass
class MarketInfo:
    """Stores market information including precision settings"""
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_order_qty: Decimal
    max_order_qty: Decimal
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    lot_size: Decimal
    status: str

    def format_price(self, price: float) -> Decimal:
        """Format price according to market precision"""
        price_decimal = Decimal(str(price))
        return price_decimal.quantize(self.tick_size, rounding=ROUND_DOWN)

    def format_quantity(self, quantity: float) -> Decimal:
        """Format quantity according to market precision"""
        qty_decimal = Decimal(str(quantity))
        return qty_decimal.quantize(self.lot_size, rounding=ROUND_DOWN)

@dataclass
class Position:
    """Position information"""
    symbol: str
    side: str
    size: Decimal
    avg_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    mark_price: Decimal
    leverage: int
    position_value: Decimal
    timestamp: datetime

@dataclass
class Order:
    """Order information"""
    id: str
    symbol: str
    side: str
    type: str
    status: str
    quantity: Decimal
    price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    trailing_stop: Optional[Decimal] = None
    created_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class TradeResult:
    """Trade result information"""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    side: str
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal
    fees: Decimal
    win: bool
    duration: int

@dataclass
class TradeMetrics:
    """Track trading performance metrics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    max_drawdown: Decimal = Decimal('0')
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    average_win: Decimal = Decimal('0')
    average_loss: Decimal = Decimal('0')
    largest_win: Decimal = Decimal('0')
    largest_loss: Decimal = Decimal('0')
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    
    def update_metrics(self, pnl: Decimal, is_win: bool):
        """Update metrics with new trade result"""
        self.total_trades += 1
        self.total_pnl += pnl
        
        if is_win:
            self.winning_trades += 1
            self.consecutive_wins += 1
            self.consecutive_losses = 0
            self.max_consecutive_wins = max(self.max_consecutive_wins, self.consecutive_wins)
            self.average_win = ((self.average_win * (self.winning_trades - 1) + pnl) / 
                               self.winning_trades)
            self.largest_win = max(self.largest_win, pnl)
        else:
            self.losing_trades += 1
            self.consecutive_losses += 1
            self.consecutive_wins = 0
            self.max_consecutive_losses = max(self.max_consecutive_losses, self.consecutive_losses)
            self.average_loss = ((self.average_loss * (self.losing_trades - 1) + abs(pnl)) / 
                                self.losing_trades)
            self.largest_loss = min(self.largest_loss, pnl)
        
        # Calculate win rate
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        
        # Calculate profit factor
        if self.average_loss > 0:
            self.profit_factor = float(self.average_win / self.average_loss)

# --- STRATEGY BASE CLASSES ---
class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    def __init__(self, config: Config):
        self.config = config
        self.symbol = config.symbols[0]
        self.indicators = {}
        self.signals = deque(maxlen=100)
        
    @abstractmethod
    async def calculate_indicators(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Calculate technical indicators for all available timeframes"""
        pass
    
    @abstractmethod
    async def generate_signal(self, data: Dict[str, pd.DataFrame]) -> Optional[Dict[str, Any]]:
        """Generate trading signal"""
        pass
    
    def calculate_signal_strength(self, confirmations: List[bool]) -> float:
        """Calculate signal strength based on confirmations"""
        if not confirmations:
            return 0.0
        return sum(confirmations) / len(confirmations)

class StrategyFactory:
    """Factory for creating strategy instances"""
    
    @staticmethod
    def create_strategy(strategy_name: str, config: Config):
        """Create and return a strategy instance by name"""
        strategies = {
            "SMACrossover": SMACrossoverStrategy,
            "RSIStrategy": RSIStrategy,
            "BollingerBands": BollingerBandsStrategy,
            "ATRStrategy": ATRStrategy,
            "MultiTimeframe": MultiTimeframeStrategy
        }
        
        if strategy_name in strategies:
            return strategies<!--citation:1-->
        else:
            raise ValueError(f"Strategy {strategy_name} not found. Available: {list(strategies.keys())}")

# --- STRATEGIES ---
class SMACrossoverStrategy(BaseStrategy):
    """Simple Moving Average Crossover Strategy"""
    
    def __init__(self, config: Config):
        super().__init__(config)
        self.fast_period = 20
        self.slow_period = 50
        
    async def calculate_indicators(self, data: [
  {
    "id": 1,
    "description": "Add comprehensive error handling to API calls with retry mechanism for transient errors.",
    "code": "async def place_order(self, params):\n    retries = 3\n    while retries > 0:\n        try:\n            response = self.session.place_order(**params)\n            if response['retCode'] == 0:\n                return response['result']\n            else:\n                raise ValueError(response['retMsg'])\n        except Exception as e:\n            logger.error(f'Order placement error: {e}')\n            retries -= 1\n            await asyncio.sleep(1)\n    raise Exception('Max retries exceeded for order placement')"
  },
  {
    "id": 2,
    "description": "Implement rate limiting to prevent API rate limit violations.",
    "code": "from ratelimit import limits\n\n@limits(calls=10, period=60)\nasync def fetch_kline(self, symbol, interval, limit):\n    response = self.session.get_kline(category='linear', symbol=symbol, interval=interval, limit=limit)\n    return response"
  },
  {
    "id": 3,
    "description": "Enhance logging with structured JSON logging for better analysis.",
    "code": "import json_log_formatter\nformatter = json_log_formatter.JSONFormatter()\njson_handler = logging.FileHandler('bot.json.log')\njson_handler.setFormatter(formatter)\nlogger.addHandler(json_handler)"
  },
  {
    "id": 4,
    "description": "Add type hints to all methods and variables for better code quality.",
    "code": "from typing import Dict, Optional\ndef update_balance(self, balance: float) -> None:\n    self.current_balance: Decimal = Decimal(str(balance))\n    if self.current_balance > self.peak_balance:\n        self.peak_balance = self.current_balance"
  },
  {
    "id": 5,
    "description": "Modularize strategy classes into separate files for better organization.",
    "code": "# strategies/sma_strategy.py\nclass SimpleMovingAverageStrategy(BaseStrategy):\n    def __init__(self, symbol: str, timeframe: str):\n        super().__init__(symbol, timeframe)\n\n# main.py\nimport strategies.sma_strategy"
  },
  {
    "id": 6,
    "description": "Implement unit tests for risk management calculations.",
    "code": "import unittest\nclass TestRiskManager(unittest.TestCase):\n    def test_position_size(self):\n        rm = RiskManager(Config())\n        size = rm.calculate_position_size(10000, 50000)\n        self.assertEqual(size, 0.2)"
  },
  {
    "id": 7,
    "description": "Improve risk management with volatility-adjusted position sizing.",
    "code": "def calculate_position_size(self, balance: float, price: float, volatility: float) -> float:\n    risk_amount = balance * self.config.risk_per_trade\n    adjusted_risk = risk_amount / (1 + volatility)\n    return adjusted_risk / price"
  },
  {
    "id": 8,
    "description": "Add support for multiple trading strategies with dynamic switching.",
    "code": "self.strategies = {'sma': SimpleMovingAverageStrategy(...), 'rsi': RSIStrategy(...)}\nself.current_strategy = self.strategies['sma']\nsignal = self.current_strategy.generate_signal(data)"
  },
  {
    "id": 9,
    "description": "Implement position hedging mode for advanced risk management.",
    "code": "self.session.set_trading_mode(category='linear', symbol=symbol, mode=PositionMode.HEDGE_MODE.value)"
  },
  {
    "id": 10,
    "description": "Add multi-symbol support with concurrent data handling.",
    "code": "async def load_all_markets(self):\n    tasks = [self.load_market_info(symbol) for symbol in self.config.symbols]\n    await asyncio.gather(*tasks)"
  },
  {
    "id": 11,
    "description": "Integrate email notifications in addition to Telegram.",
    "code": "import smtplib\nasync def send_email(self, message: str):\n    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:\n        server.login('user', 'pass')\n        server.sendmail('from', 'to', message)"
  },
  {
    "id": 12,
    "description": "Add persistent storage for trade metrics using SQLite.",
    "code": "async def save_metrics(self):\n    async with aiosqlite.connect(self.db_path) as db:\n        await db.execute('INSERT INTO metrics (...) VALUES (...)', (...))\n        await db.commit()"
  },
  {
    "id": 13,
    "description": "Implement exponential backoff for WebSocket reconnections.",
    "code": "async def reconnect(self):\n    delay = self.config.reconnect_delay * (2 ** self.reconnect_count)\n    delay = min(delay, self.config.max_reconnect_delay)\n    await asyncio.sleep(delay)"
  },
  {
    "id": 14,
    "description": "Add real-time performance dashboard using Flask.",
    "code": "from flask import Flask\napp = Flask(__name__)\n@app.route('/metrics')\ndef metrics():\n    return json.dumps(asdict(self.trade_metrics))"
  },
  {
    "id": 15,
    "description": "Enhance backtesting with Monte Carlo simulations.",
    "code": "def monte_carlo_simulation(self, returns: List[float], simulations: int = 1000):\n    for _ in range(simulations):\n        shuffled = np.random.shuffle(returns)\n        # calculate equity curve"
  },
  {
    "id": 16,
    "description": "Implement Kelly Criterion for position sizing.",
    "code": "def kelly_position_size(self, win_rate: float, win_loss_ratio: float) -> float:\n    return (win_rate * win_loss_ratio - (1 - win_rate)) / win_loss_ratio"
  },
  {
    "id": 17,
    "description": "Add support for trailing stop loss adjustments.",
    "code": "async def adjust_trailing_stop(self, position: Position, new_stop: float):\n    params = {'symbol': position.symbol, 'stopLoss': str(new_stop)}\n    await self.session.set_trading_stop(**params)"
  },
  {
    "id": 18,
    "description": "Integrate sentiment analysis from news API.",
    "code": "async def get_sentiment(self):\n    async with aiohttp.ClientSession() as session:\n        async with session.get('news_api_url') as resp:\n            data = await resp.json()\n            # process sentiment"
  },
  {
    "id": 19,
    "description": "Add auto-leverage adjustment based on market volatility.",
    "code": "def adjust_leverage(self, volatility: float):\n    if volatility > 0.05:\n        self.config.leverage = 3\n    else:\n        self.config.leverage = 5"
  },
  {
    "id": 20,
    "description": "Implement order batching for efficiency.",
    "code": "def place_batch_orders(self, orders: List[Dict]):\n    response = self.session.place_batch_order(orders)\n    return response"
  },
  {
    "id": 21,
    "description": "Add data validation for incoming WebSocket messages.",
    "code": "def validate_message(self, message: Dict) -> bool:\n    required_keys = ['topic', 'data']\n    return all(key in message for key in required_keys)"
  },
  {
    "id": 22,
    "description": "Enhance timezone management with automatic DST handling.",
    "code": "import pytz\ndef to_local_time(self, dt: datetime) -> datetime:\n    tz = pytz.timezone(self.config.timezone)\n    return dt.astimezone(tz)"
  },
  {
    "id": 23,
    "description": "Implement trade journaling with screenshots.",
    "code": "# Requires additional libraries like playwright\nasync def capture_chart(self):\n    async with async_playwright() as p:\n        browser = await p.chromium.launch()\n        page = await browser.new_page()\n        await page.goto('chart_url')\n        await page.screenshot(path='trade.png')"
  },
  {
    "id": 24,
    "description": "Add machine learning-based signal filtering.",
    "code": "from sklearn.ensemble import RandomForestClassifier\nself.model = RandomForestClassifier()\n# Train on historical signals\nprediction = self.model.predict(features)"
  },
  {
    "id": 25,
    "description": "Implement graceful shutdown with position closing.",
    "code": "async def shutdown(self):\n    for pos in self.positions.values():\n        await self.close_position(pos)\n    self.ws.exit()\n    logger.info('Bot shutdown complete')"
  }
]


#### Bybit WebSocket Endpoints

Bybit's **WebSocket** endpoints are organized under the `wss://stream.bybit.com/v5` host, with separate paths for public and private data streams .

| Stream Type | WebSocket URL | Authentication | Description |
|-------------|---------------|----------------|-------------|
| Public Market Data | `wss://stream.bybit.com/v5/public` | Not required | Real-time market data such as orderbooks, tickers, and trades |
| Unified Trading (Private) | `wss://stream.bybit.com/v5/public/linear` | API Key required | Private user data including wallet balances, positions, and orders |


#### pybit Unified Trading Module Functions

The **pybit** Python SDK, maintained by Bybit, provides a `unified_trading` module for interacting with both REST and WebSocket endpoints .

##### Wallet and Account Functions

| Function | Description | Example Use Case |
|--------|-------------|------------------|
| `get_wallet_balance()` | Retrieves account balances across all coins and accounts | Check available funds for trading |
| `get_wallet_balance_info()` | Provides detailed wallet information including available and used margin | Monitor margin usage per coin |
| `get_transfer_history()` | Fetches deposit, withdrawal, and inter-account transfer history | Audit fund movements |
| `transfer()` | Transfers assets between spot, derivatives, and unified accounts | Move funds between account types |
 

##### WebSocket Subscription Functions

The `WebsocketClient` in pybit supports both event-driven and promise-driven patterns for WebSocket interactions .

| Function | Description | Example Use Case |
|--------|-------------|------------------|
| `subscribe()` | Subscribes to one or more WebSocket topics | Receive real-time orderbook updates |
| `unsubscribe()` | Stops receiving updates for a subscribed topic | Reduce bandwidth usage |
| `on_message()` | Event handler for incoming WebSocket messages | Process tickers or trades as they arrive |
| `on_error()` | Event handler for WebSocket connection errors | Log or retry failed connections |
| `send_auth()` | Sends authenticated messages using API credentials | Place orders via WebSocket |
 

#### Example: Subscribing to Wallet Updates via WebSocket

```python
from pybit import WebSocket

# Initialize WebSocket client
ws = WebSocket("wss://stream.bybit.com/v5/public", api_key="YOUR_API_KEY", api_secret="YOUR_API_SECRET")

# Subscribe to wallet balance updates
def on_wallet_message(msg):
    print("Wallet update:", msg)

ws.subscribe(
    channels=["wallet"],
    callback=on_wallet_message
)
```

This setup allows developers to build low-latency trading bots that react instantly to balance changes or position updates .

#### Authentication Requirements



#### pybit Orderbook Functions

The **pybit** Python SDK provides functions to access and stream **orderbook** data via both REST and WebSocket endpoints. These functions support multiple product types: **Spot**, **USDT Perpetual (linear)**, **USDC Perpetual**, **Inverse Perpetual**, and **Option** contracts.

| Function | Description | Parameters | Source |
|--------|-------------|------------|--------|
| `get_orderbook()` | Fetches a snapshot of the orderbook in REST mode. Returns bid/ask arrays with prices and sizes. | `category` (str), `symbol` (str), `limit` (int, optional) |  |
| `orderbook()` | WebSocket subscription function for real-time orderbook updates. Streams depth data as it changes. | `symbol` (str), `limit` (int, optional), `callback` (function), `api_key`/`api_secret` (optional for authenticated streams) |  |

##### REST Function: `get_orderbook()`

This function retrieves a full snapshot of the orderbook:

```python
from pybit.unified_trading import HTTP

session = HTTP(testnet=True)
orderbook = session.get_orderbook(
    category="linear",
    symbol="BTCUSDT"
)
```

- `category`: Product type — `"spot"`, `"linear"`, `"inverse"`, `"option"`
- `symbol`: Trading pair, e.g., `"BTCUSDT"`
- `limit`: Number of levels returned per side — max 200 for spot, 500 for linear/inverse, 25 for option

Response includes:
- `b`: Bid side (buyers), sorted descending by price
- `a`: Ask side (sellers), sorted ascending by price
- `ts`: Timestamp (ms) of data generation
- `u`: Update ID
- `seq`: Sequence number for cross-checking updates
- `cts`: Matching engine timestamp

> "The response is in the snapshot format." 

##### WebSocket Function: `orderbook()`

Used to subscribe to live orderbook streams:

```python
from pybit.unified_trading import WebSocket

ws = WebSocket(
    endpoint="wss://stream.bybit.com/v5/public",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

def on_message(msg):
    print("Orderbook update:", msg)

ws.orderbook(
    symbol="BTCUSDT",
    limit=25,
    callback=on_message
)
```

- `limit`: Depth level — up to 500 for linear/inverse, 200 for spot
- `callback`: Function to handle incoming messages
- Authentication optional for public streams

> "Subscribe to the orderbook stream. Supports different depths." 

#### Supported Product Types and Depth Limits

| Product Type | Max Orderbook Levels | Source |
|-------------|----------------------|--------|
| Spot | 200 |  |
| USDT Perpetual | 500 |  |
| USDC Perpetual | 500 |  |
| Inverse Perpetual | 500 |  |
| Option | 25 |  |

All 


#### Order Placement Functions in pybit

The **pybit** Python SDK provides comprehensive functions for placing orders on **Bybit** across multiple product types, including Spot, USDT Perpetual, USDC Perpetual, Inverse Perpetual, and Options. Order placement is handled through the `place_active_order()` method for linear (USDT/USDC) contracts and `place_spot_order()` for Spot trading.

| Function | Product Type | Description |
|--------|------------|-------------|
| `place_active_order()` | USDT/USDC Perpetual, Inverse Perpetual | Places market, limit, stop, take profit, and conditional orders |
| `place_spot_order()` | Spot | Executes spot market and limit orders |
| `place_active_order_bulk()` | USDT/USDC Perpetual, Inverse Perpetual | Submits multiple active orders in a single request |
| `place_conditional_order()` | USDT/USDC Perpetual, Inverse Perpetual | Places stop-loss, take-profit, or trailing-stop orders |
| `place_conditional_order_bulk()` | USDT/USDC Perpetual, Inverse Perpetual | Places multiple conditional orders at once |

> "This endpoint supports to create the order for Spot, Margin trading, USDT perpetual, USDT futures, USDC perpetual, USDC futures, Inverse Futures and Options." 

Order parameters include:
- `category`: `"spot"`, `"linear"`, `"inverse"`, `"option"`
- `symbol`: Trading pair (e.g., `"BTCUSDT"`)
- `side`: `"Buy"` or `"Sell"`
- `orderType`: `"Limit"`, `"Market"`, `"Stop"`, `"TakeProfit"`, etc.
- `qty`: Order size
- `price`: Price for limit orders
- `timeInForce`: `"GTC"`, `"FOK"`, `"IOC"`



#### Signal Generation with pybit

Signal generation in **pybit**-based trading bots involves retrieving market data (e.g., klines, orderbook) and applying technical logic to generate buy/sell signals. Common indicators include RSI, MACD, and moving average crossovers.

Example signal logic using RSI:
> "Buy signals occur when the RSI crosses above 30%, while sell signals arise when it crosses below 70%." 

Signal generation workflow:
1. Fetch historical kline data using `query_kline()`
2. Calculate indicator values (e.g., RSI)
3. Apply crossover or threshold logic to generate signal
4. Execute order via `place_active_order()` if condition met

Common signal-generation patterns:
- RSI divergence
- MACD histogram crossover
- Bollinger Band touches
- Volume spike detection

> "The system is running correctly but no trades are being placed as the signal is always 0. It should generate a buy or sell signal and then place an order." 

Signal bots can post alerts to platforms like **Discord** using webhooks after signal confirmation .

#### Order Execution Example

```python
from pybit import inverse_perpetual

# Initialize session
session = inverse_perpetual.HTTP(endpoint="https://api.bybit.com", api_key="YOUR_KEY", api_secret="YOUR_SECRET")

# Place a limit buy order
response = session.place_active_order(
    category="linear",
    symbol="BTCUSDT",
    side="Buy",
    orderType="Limit",
    qty=1,
    price=30000,
    timeInForce="GoodTillCancel"
)
```

#### Conditional Order Example

```python
# Place a stop-loss conditional order
session.place_conditional_order(
    category="linear",
    symbol="BTCUSDT",
    side="Sell",
    orderType="Stop",
    qty=1,
    stopPrice=29000,
    reduceOnly=True
)
```

#### Batch Order Placement

> "This endpoint allows you to place more than one order in a single request." 

```
#### Order Placement Functions in pybit

The **pybit** Python SDK provides comprehensive functions for placing orders on **Bybit** across multiple product types, including **Spot**, **USDT Perpetual (linear)**, **USDC Perpetual**, **Inverse Perpetual**, and **Option** contracts. These functions are part of the `unified_trading` module and support both REST and WebSocket interactions.

| Function | Product Type | Description |
|--------|------------|-------------|
| `place_active_order()` | USDT/USDC Perpetual, Inverse Perpetual | Places market, limit, stop, take profit, and conditional orders |
| `place_spot_order()` | Spot | Executes spot market and limit orders |
| `place_active_order_bulk()` | USDT/USDC Perpetual, Inverse Perpetual | Submits multiple active orders in a single request |
| `place_conditional_order()` | USDT/USDC Perpetual, Inverse Perpetual | Places stop-loss, take-profit, or trailing-stop orders |
| `place_conditional_order_bulk()` | USDT/USDC Perpetual, Inverse Perpetual | Places multiple conditional orders at once |

> "This endpoint supports to create the order for Spot, Margin trading, USDT perpetual, USDT futures, USDC perpetual, USDC futures, Inverse Futures and Options." 

Order parameters include:
- `category`: `"spot"`, `"linear"`, `"inverse"`, `"option"`
- `symbol`: Trading pair (e.g., `"BTCUSDT"`)
- `side`: `"Buy"` or `"Sell"`
- `orderType`: `"Limit"`, `"Market"`, `"Stop"`, `"TakeProfit"`, etc.
- `qty`: Order size
- `price`: Price for limit orders
- `timeInForce`: `"GTC"`, `"FOK"`, `"IOC"`

#### Signal Generation Logic

Signal generation in **pybit**-based trading bots involves retrieving market data (e.g., klines, orderbook) and applying technical logic to generate buy/sell signals. Common indicators include **RSI**, **MACD**, and **moving average crossovers**.

Example signal logic using RSI:
> "Buy signals occur when the RSI crosses above 30%, while sell signals arise when it crosses below 70%." 

Signal generation workflow:
1. Fetch historical kline data using `query_kline()`
2. Calculate indicator values (e.g., RSI)
3. Apply crossover or threshold logic to generate signal
4. Execute order via `place_active_order()` if condition met

Common signal-generation patterns:
- RSI divergence
- MACD histogram crossover
- Bollinger Band touches
- Volume spike detection

> "The system is running correctly but no trades are being placed as the signal is always 0. It should generate a buy or sell signal and then place an order." 

Signal bots can post alerts to platforms like **Discord** using webhooks after signal confirmation 

#### Real-Time Order Streaming

The `WebSocket` client in pybit allows real-time monitoring of order status changes via the `order_stream()` function.

| WebSocket Topic | Description |
|-----------------|-------------|
| `order` | All-in-one topic for real-time order updates across all categories |
| `order.spot`, `order.linear`, `order.inverse`, `order.option` | Categorized topics for specific product types |

> "Subscribe to the order stream to see changes to your orders in real-time." 

```python
from pybit.unified_trading import WebSocket

ws = WebSocket(
    endpoint="wss://stream.bybit.com/v5/public",
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

def handle_order_message(msg):
    print("Order update:", msg)

ws.order_stream(callback=handle_order_message)
```

The **Order** stream includes detailed fields such as `orderId`, `orderStatus`, `cumExecQty`, `avgPrice`, and `rejectReason`, enabling precise tracking of order lifecycle events .

#### Batch Order Placement

> "This endpoint allows you to place more than one order in a single request." 

```python
response = session.place_active_order_bulk(
    category="linear",
    request_list=[
        {
            "symbol": "BTCUSDT",
            "side": "Buy",
            "orderType": "Limit",
            "qty": "0.001",
            "price": "30000",
            "timeInForce": "GTC"
        },
        {
            "symbol": "ETHUSDT",
            "side": "Sell",
            "orderType": "Market",
            "qty": "0.01"
        }
    ]
)
```

#### Official SDK and Integration

**pybit** is the official lightweight one-stop-shop module for the Bybit HTTP and WebSocket APIs 
#### Orderbook Processing Logic

The **Bybit WebSocket** API delivers orderbook data in two formats: `snapshot` and `delta`. Upon subscription, you receive an initial `snapshot` containing the full orderbook state. Subsequent updates are sent as `delta` messages that reflect only changes to the book.

| Parameter | Type | Comments |
|---------|------|--------|
| topic | string | Topic name |
| type | string | Data type: `snapshot`, `delta` |
| ts | number | Timestamp (ms) when the system generated the data |
| data.s | string | Symbol name |
| data.b | array | Bids (price-size pairs), sorted descending |
| data.a | array | Asks (price-size pairs), sorted ascending |
| data.u | integer | Update ID |
| data.seq | integer | Cross sequence number |
| cts | number | Matching engine timestamp |



To maintain an accurate local orderbook:
- On `snapshot`: overwrite your entire local book
- On `delta`: 
  - If size is `0`, remove the price level
  - If price doesn't exist, insert it
  - If price exists, update the size

> "If you receive a new snapshot message, you will have to reset your local orderbook. If there is a problem on Bybit's end, a snapshot will be re-sent, which is guaranteed to contain the latest data."  
> "To apply delta updates: - If you receive an amount that is `0`, delete the entry"



#### Orderbook Depth and Update Frequency

| Product Type | Depth | Push Frequency |
|-------------|-------|----------------|
| Linear & Inverse Perpetual | Level 1 | 10ms |
| | Level 50 | 20ms |
| | Level 200 | 100ms |
| | Level 500 | 100ms |
| Spot | Level 1 | 10ms |
| | Level 50 | 20ms |
| | Level 200 | 200ms |
| | Level 1000 | 300ms |
| Option | Level 25 | 20ms |
| | Level 100 | 100ms |



#### Trailing Stop Order Setup

A **trailing stop order** is a conditional order that triggers when the price moves a specified distance against your position.

Example: Set a trailing stop with 500 USDT retracement from an activation price of 30,000 USDT.
- When last price reaches 30,000 USDT, the order activates
- Trigger price set to 29,500 USDT (30,000 - 500)
- Order type: Stop Market (for sells) or Stop Limit

> "The trader can set a Trailing Stop with 500 USDT of retracement distance and an activation price of 30,000 USDT. When the last traded price reaches 30,000 USDT, the Trailing Stop order will be placed, with a trigger price of 29,500 USDT (30,000 USDT - 500 USDT)."  
> "A trailing stop order is a conditional order that uses a trailing amount set away from the current market price to determine the trigger for execution."

 

#### API Rate Limits for Institutional Accounts

Starting August 13, 2025, **Bybit** is rolling out a new institutional API rate limit framework designed for high-frequency traders.

| Feature | Detail |
|--------|--------|
| Release Date | August 13, 2025 |
| Target Users | Institutional, HFT traders |
| Purpose | Enhance performance and reduce latency |
| Framework Name | Institutional API Rate Limit Framework |



#### WebSocket Connection Best Practices

The **WebSocketClient** inherits from `EventEmitter` and automatically handles heartbeats and reconnections.

> "After establishing a connection, the client sends heartbeats in regular intervals, and reconnects to the..."  
> "The WebSocket will keep pushing delta messages every time the orderbook changes. If you receive a new snapshot message, you will have to reset your local orderbook."

 

#### Authentication Domain Matching

API key validation requires matching the domain used in the request:

| Testnet Mode | API Key Source | Endpoint |
|-------------|----------------|---------|
| Testnet | Created on  | `api-testnet.bybit.com` |
| Demo Trading | Created on production, in Demo mode | `api-demo.bybit.com` |
| Production | Created on  | `api.bybit.com` |

> "When requesting `api-testnet.bybit.com` or `stream-testnet.bybit.com`, make sure the API key is created from  – while outside of Demo Trading mode."



#### Order Size Based on Account Balance

Use `get_wallet_balance()` to retrieve available funds and calculate position size based on risk tolerance.

> "Using pybit you can query your free balance in USDT then calculate the amount of coin you want to enter a position with based on your risk tolerances."



#### Example: Trailing Stop via pybit

```python
from pybit import HTTP

session = HTTP(
    testnet=True,
    api_key="YOUR_API_KEY",
    api_secret="YOUR_API_SECRET"
)

response = session.place_active_order(
    category="linear",
    symbol="BTCUSDT",
    side="Buy",
    orderType="Stop",
    stopLoss=29500,  # Trigger price
    reduceOnly=True,
    takeProfit=30500  # Optional take profit
)
```

This sets a stop-loss at 29,500 USDT to close a long position, functioning as a trailing stop when combined with dynamic updates.

![](https://llm.diffbot.com/img/1zuDny4f.jpg)  
*Trading Bot interface on Bybit App *
orders =  and private account functions require API key authentication, using HMAC SHA256 signatures with timestamp and receive window headers .