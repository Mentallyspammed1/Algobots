



## WebSocket Implementation

WebSocket connections in Bybit V5 API are divided into public and private streams, with specific endpoints for different data types. The updated endpoints for V5 are:

**Main WebSocket Endpoints**

```javascript
// Public streams
Mainnet: wss://stream.bybit.com/v5/public/linear
Testnet: wss://stream-testnet.bybit.com/v5/public/linear

// Private streams (updated in 2025)
Mainnet: wss://stream.bybit.com/v5/private
Testnet: wss://stream-testnet.bybit.com/v5/private
```

## WebSocket Client Setup

**JavaScript/Node.js Implementation**

```javascript
const { WebsocketClient } = require('bybit-api');

const wsConfig = {
    // API credentials for private topics
    key: 'yourAPIKeyHere',
    secret: 'yourAPISecretHere',
    
    // Optional parameters
    testnet: false,  // Set to true for testnet
    demoTrading: false,  // Set to true for demo trading
    recvWindow: 5000,  // Authentication window for high latency connections
    pingInterval: 10000,  // Connection alive check interval (ms)
    pongTimeout: 1000,  // Heartbeat reply timeout (ms)
    reconnectTimeout: 500  // Delay before respawning connection (ms)
};

const ws = new WebsocketClient(wsConfig);
```

## Orderbook Functions

**WebSocket Orderbook Subscription**

The orderbook can be accessed through both WebSocket streams and REST API calls.

```javascript
// Subscribe to orderbook depth 50 for multiple symbols
ws.subscribeV5(['orderbook.50.BTCUSDT', 'orderbook.50.ETHUSDT'], 'linear');

// Subscribe to different orderbook depths
ws.subscribeV5('orderbook.1.BTCUSDT', 'linear');   // Top bid/ask only
ws.subscribeV5('orderbook.25.BTCUSDT', 'linear');  // 25 levels
ws.subscribeV5('orderbook.50.BTCUSDT', 'linear');  // 50 levels
ws.subscribeV5('orderbook.100.BTCUSDT', 'linear'); // 100 levels
ws.subscribeV5('orderbook.200.BTCUSDT', 'linear'); // 200 levels
```

**REST API Orderbook Function**

```javascript
async function getOrderbook(exchange, options) {
    try {
        let result = await exchange.getOrderbook(options);
        console.log(result);
    } catch (error) {
        console.log(error.message);
    }
}

// Usage example
const result = await getOrderbook(myByBitAccount, {
    category: 'linear',
    symbol: 'BTCUSD',
    limit: 50  // Number of orderbook levels
});
```

## Complete WebSocket Channels

**Public Market Data Subscriptions**

```javascript
// Orderbook streams
ws.subscribeV5('orderbook.50.BTCUSDT', 'linear');

// Trade streams
ws.subscribeV5('publicTrade.BTCUSDT', 'linear');

// Kline/Candlestick data
ws.subscribeV5('kline.5.BTCUSDT', 'linear');  // 5-minute candles
ws.subscribeV5('kline.15.BTCUSDT', 'linear'); // 15-minute candles
ws.subscribeV5('kline.60.BTCUSDT', 'linear'); // 1-hour candles

// Ticker stream
ws.subscribeV5('tickers.BTCUSDT', 'linear');

// Liquidation stream
ws.subscribeV5('liquidation.BTCUSDT', 'linear');

// Multiple subscriptions at once
ws.subscribeV5([
    'orderbook.50.BTCUSDT',
    'publicTrade.BTCUSDT',
    'kline.5.BTCUSDT'
], 'linear');
```

**Private Account Subscriptions**

```javascript
// Position updates
ws.subscribeV5('position', 'linear');

// Order updates
ws.subscribeV5('order', 'linear');

// Execution/Fill updates
ws.subscribeV5('execution', 'linear');

// Wallet updates
ws.subscribeV5('wallet', 'unified');

// Greeks data (options)
ws.subscribeV5('greeks', 'option');

// For spot trading
ws.subscribeV5('order', 'spot');
ws.subscribeV5('stopOrder', 'spot');
ws.subscribeV5('execution', 'spot');
ws.subscribeV5('wallet', 'spot');
```

## WebSocket Event Handlers

**Implementing Message Handlers**

```javascript
// Handle orderbook updates
ws.on('update', (data) => {
    if (data.topic && data.topic.includes('orderbook')) {
        const orderbook = data.data;
        console.log('Orderbook update:', {
            symbol: orderbook.s,
            bids: orderbook.b,  // Array of [price, size]
            asks: orderbook.a,  // Array of [price, size]
            updateId: orderbook.u,
            timestamp: data.ts
        });
    }
});

// Handle trade updates
ws.on('update', (data) => {
    if (data.topic && data.topic.includes('publicTrade')) {
        const trades = data.data;
        trades.forEach(trade => {
            console.log('Trade:', {
                symbol: trade.s,
                price: trade.p,
                size: trade.v,
                side: trade.S,
                timestamp: trade.T
            });
        });
    }
});

// Handle position updates
ws.on('update', (data) => {
    if (data.topic === 'position') {
        const positions = data.data;
        positions.forEach(position => {
            console.log('Position update:', {
                symbol: position.symbol,
                side: position.side,
                size: position.size,
                avgPrice: position.avgPrice,
                unrealisedPnl: position.unrealisedPnl
            });
        });
    }
});
```

## Python Implementation with pybit

**WebSocket Setup for Python**

```python
from pybit.unified_trading import WebSocket

# Initialize WebSocket client
ws = WebSocket(
    testnet=False,
    channel_type="public"  # or "private" for authenticated streams
)

# Subscribe to orderbook
def handle_orderbook(message):
    """Process orderbook updates"""
    data = message.get("data", {})
    symbol = data.get("s")
    bids = data.get("b", [])
    asks = data.get("a", [])
    print(f"Orderbook for {symbol}: Bids: {bids[:5]}, Asks: {asks[:5]}")

# Subscribe to different orderbook depths
ws.orderbook_stream(
    depth=50,  # Can be 1, 25, 50, 100, or 200
    symbol="BTCUSDT",
    callback=handle_orderbook
)

# Subscribe to trades
def handle_trades(message):
    """Process trade updates"""
    trades = message.get("data", [])
    for trade in trades:
        print(f"Trade: {trade}")

ws.trade_stream(
    symbol="BTCUSDT",
    callback=handle_trades
)
```

## Advanced WebSocket Features

**Connection Management**

```javascript
// Custom alive duration (30s to 600s)
ws.subscribeV5('orderbook.50.BTCUSDT', 'linear', {
    max_active_time: 300  // 5 minutes
});

// Connection state monitoring
ws.on('open', () => {
    console.log('WebSocket connection opened');
});

ws.on('close', () => {
    console.log('WebSocket connection closed');
});

ws.on('error', (error) => {
    console.error('WebSocket error:', error);
});

// Manual heartbeat
setInterval(() => {
    ws.ping();
}, 30000);
```

**Batch Subscriptions**

```javascript
// Subscribe to multiple orderbook levels for different symbols
const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'AVAXUSDT'];
const subscriptions = [];

symbols.forEach(symbol => {
    subscriptions.push(`orderbook.50.${symbol}`);
    subscriptions.push(`publicTrade.${symbol}`);
    subscriptions.push(`kline.5.${symbol}`);
});

ws.subscribeV5(subscriptions, 'linear');
```

## REST API Orderbook Functions

The REST API provides several orderbook-related endpoints:

```javascript
// Get orderbook snapshot
const orderbook = await client.getOrderbook({
    category: 'linear',
    symbol: 'BTCUSDT',
    limit: 200  // Max 200 levels
});

// Get spread orderbook (for spread trading)
const spreadOrderbook = await client.getSpreadOrderbook({
    symbol: 'BTC-29DEC23-80000-C',
    category: 'option'
});

// Get order price limits
const priceLimits = await client.getOrderPriceLimit({
    category: 'linear',
    symbol: 'BTCUSDT'
});
```

## WebSocket vs REST Comparison

**When to Use WebSocket:**
- Real-time orderbook updates
- Live trade streaming
- Position and order monitoring
- Low-latency requirements

**When to Use REST:**
- Initial orderbook snapshot
- Periodic data polling
- One-time queries
- Historical data retrieval

The combination of WebSocket streams for real-time updates and REST API for snapshots provides a complete orderbook management solution for trading applications.

To effectively utilize Bybit's v5 API for real-time data and order book management, it's essential to understand the WebSocket functionalities and how to interact with the order book. Below is a comprehensive guide on subscribing to various WebSocket streams and managing order book data using the `pybit` library.

**1. WebSocket Streams**

Bybit's WebSocket API provides real-time data streams for both public and private topics. Public topics include market data such as order book updates, trades, and tickers, while private topics pertain to user-specific data like order updates and account information.

**a. Public Topics**

To subscribe to public topics, such as the order book for a specific trading pair:

```python
from pybit.unified_trading import WebSocket
import time

# Initialize WebSocket client
ws = WebSocket(
    testnet=True,  # Set to False for live trading
    api_key='your_api_key',
    api_secret='your_api_secret'
)

# Define a callback function to handle incoming messages
def handle_message(message):
    print(message)

# Subscribe to the order book for BTC/USDT
ws.subscribe_public_topic(
    topic='orderbook.1.BTCUSDT',  # '1' denotes the depth level
    callback=handle_message
)

# Keep the WebSocket connection open
while True:
    time.sleep
```

In this example:

- `orderbook.1.BTCUSDT` subscribes to the order book for the BTC/USDT pair with a depth of 1.
- The `handle_message` function processes incoming messages.

**b. Private Topics**

To receive real-time updates on your orders and account information:

```python
# Subscribe to order updates
ws.subscribe_private_topic(
    topic='order',
    callback=handle_message
)

# Subscribe to position updates
ws.subscribe_private_topic(
    topic='position',
    callback=handle_message
)
```

Ensure that your API key has the necessary permissions to access private topics.

**2. Order Book Management**

Managing the order book involves subscribing to the order book stream and processing the incoming data to maintain an up-to-date local copy.

**a. Subscribing to the Order Book Stream**

As shown earlier, subscribe to the order book stream for the desired trading pair.

**b. Processing Order Book Data**

The order book data received from the WebSocket stream includes updates to the bids and asks. To maintain an accurate local order book:

```python
import json

# Initialize local order book
order_book = {'bids': {}, 'asks': {}}

def handle_message(message):
    data = json.loads(message)
    if 'topic' in data and To interact with Bybit's v5 API using Python, the `pybit` library is a convenient tool. This guide will walk you through setting up `pybit`, connecting to Bybit's WebSocket streams, and executing various trading functions, including placing limit orders, setting stop-loss and take-profit orders, and executing batch orders.

**1. Installation**

First, install the `pybit` library:


```bash
pip install pybit
```


**2. Initialization**

Import the necessary modules and initialize the REST and WebSocket clients:


```python
from pybit.unified_trading import HTTP, WebSocket
import time

# Initialize REST client
session = HTTP(
    testnet=True,  # Set to False for live trading
    api_key='your_api_key',
    api_secret='your_api_secret'
)

# Initialize WebSocket client
ws = WebSocket(
    testnet=True,  # Set to False for live trading
    api_key='your_api_key',
    api_secret='your_api_secret'
)
```


**3. WebSocket Streams**

To subscribe to WebSocket streams for real-time data:


```python
# Define a callback function to handle incoming messages
def handle_message(message):
    print(message)

# Subscribe to public topics (e.g., order book, trades)
ws.subscribe_public_topic(
    topic='orderbook.1.BTCUSDT',  # Order book for BTC/USDT
    callback=handle_message
)

# Subscribe to private topics (e.g., order updates)
ws.subscribe_private_topic(
    topic='order',
    callback=handle_message
)

# Keep the WebSocket connection open
while True:
    time.sleep
```


**4. Placing Orders**

To place a limit order:


```python
order = session.place_order(
    category='linear',
    symbol='BTCUSDT',
    side='Buy',
    order_type='Limit',
    qty=0.01,
    price=30000,
    time_in_force='GoodTillCancel'
)
print(order)
```


To place a stop-loss and take-profit order:


```python
# Place a limit order with stop-loss and take-profit
order = session.place_order(
    category='linear',
    symbol='BTCUSDT',
    side='Buy',
    order_type='Limit',
    qty=0.01,
    price=30000,
    time_in_force='GoodTillCancel',
    stop_loss=29000,
    take_profit=31000
)
print(order)
```


**5. Batch Orders**

To place multiple orders simultaneously:


```python
orders =

Building a comprehensive Bybit trading bot with the V5 API requires understanding both the HTTP REST endpoints and WebSocket connections for real-time data. The pybit library provides an official Python connector that simplifies interaction with Bybit's trading infrastructure.

## Installation and Setup

First, install the pybit library using pip. The library requires Python 3.9.1 or higher and uses minimal external dependencies:

```python
pip install pybit
```

## Authentication and API Configuration

To interact with Bybit's API, you'll need to generate API credentials from your Bybit account. The API uses HMAC SHA256 signatures for authentication with a timestamp synchronization requirement within 5 seconds of server time.

```python
from pybit.unified_trading import HTTP
import time
import json
from datetime import datetime

# API Configuration
API_KEY = "your_api_key_here"
API_SECRET = "your_api_secret_here"

# Initialize HTTP session for V5 unified trading
session = HTTP(
    testnet=True,  # Set to False for mainnet
    api_key=API_KEY,
    api_secret=API_SECRET,
    recv_window=5000  # Request window in milliseconds
)
```

## Core Trading Functions

**Market Data Retrieval**

The V5 API provides unified endpoints for accessing market data across different product types:

```python
def get_market_data(symbol="BTCUSDT", category="linear"):
    """Retrieve current market data for a symbol"""
    try:
        # Get orderbook data
        orderbook = session.get_orderbook(
            category=category,
            symbol=symbol
        )
        
        # Get ticker information
        ticker = session.get_tickers(
            category=category,
            symbol=symbol
        )
        
        # Get recent trades
        trades = session.get_public_trading_records(
            category=category,
            symbol=symbol,
            limit=20
        )
        
        return {
            "orderbook": orderbook,
            "ticker": ticker,
            "trades": trades
        }
    except Exception as e:
        print(f"Error fetching market data: {e}")
        return None
```

**Position Management**

Managing positions is crucial for any trading bot. The API allows you to query and monitor your current positions:

```python
def get_position_info(symbol="BTCUSDT", category="linear"):
    """Get current position information"""
    try:
        positions = session.get_positions(
            category=category,
            symbol=symbol
        )
        return positions
    except Exception as e:
        print(f"Error fetching position: {e}")
        return None

def get_account_balance():
    """Retrieve account balance information"""
    try:
        balance = session.get_wallet_balance(
            accountType="UNIFIED"  # or "CONTRACT" for derivatives
        )
        return balance
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return None
```

## Order Placement Functions

**Single Order Placement with Stop Loss and Take Profit**

Placing orders with risk management is essential. The V5 API requires separate calls to set stop loss and take profit after the initial order placement:

```python
def place_limit_order_with_sl_tp(symbol, side, qty, price, tp_price, sl_price, category="linear"):
    """Place a limit order with stop loss and take profit"""
    try:
        # Place the main order
        order_response = session.place_order(
            category=category,
            symbol=symbol,
            side=side,  # "Buy" or "Sell"
            orderType="Limit",
            qty=str(qty),
            price=str(price),
            timeInForce="GTC",  # Good Till Cancel
            positionIdx=0,  # 0 for one-way mode
            orderLinkId=f"order_{int(time.time()*1000)}"
        )
        
        # Set trading stop (TP/SL) - requires separate API call for derivatives
        if category in ["linear", "inverse"]:
            session.set_trading_stop(
                category=category,
                symbol=symbol,
                takeProfit=str(tp_price),
                stopLoss=str(sl_price),
                tpTriggerBy="LastPrice",
                slTriggerBy="LastPrice",
                positionIdx=0
            )
        
        return order_response
    except Exception as e:
        print(f"Error placing order: {e}")
        return None

def place_market_order(symbol, side, qty, category="linear"):
    """Place a market order"""
    try:
        order_response = session.place_order(
            category=category,
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            timeInForce="IOC",  # Immediate or Cancel for market orders
            positionIdx=0
        )
        return order_response
    except Exception as e:
        print(f"Error placing market order: {e}")
        return None
```

**Batch Order Placement**

The V5 API supports batch order placement for more efficient order management. Currently, spot and USDC options support batch ordering:

```python
def place_batch_orders(orders_data, category="spot"):
    """Place multiple orders in a single request"""
    try:
        # Format orders for batch submission
        request_payload = {
            "category": category,
            "request": orders_data
        }
        
        response = session.place_batch_order(request_payload)
        return response
    except Exception as e:
        print(f"Error placing batch orders: {e}")
        return None

# Example batch order structure
batch_orders_example = [
    {
        "symbol": "BTCUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": "0.05",
        "price": "30000",
        "timeInForce": "GTC",
        "orderLinkId": f"batch_order_1_{int(time.time()*1000)}"
    },
    {
        "symbol": "ETHUSDT",
        "side": "Buy",
        "orderType": "Limit",
        "qty": "0.1",
        "price": "2000",
        "timeInForce": "GTC",
        "orderLinkId": f"batch_order_2_{int(time.time()*1000)}"
    }
]
```

## Order Management Functions

**Modifying and Canceling Orders**

```python
def amend_order(symbol, orderId=None, orderLinkId=None, new_qty=None, new_price=None, category="linear"):
    """Modify an existing order"""
    try:
        params = {
            "category": category,
            "symbol": symbol
        }
        
        if orderId:
            params["orderId"] = orderId
        elif orderLinkId:
            params["orderLinkId"] = orderLinkId
            
        if new_qty:
            params["qty"] = str(new_qty)
        if new_price:
            params["price"] = str(new_price)
            
        response = session.amend_order(**params)
        return response
    except Exception as e:
        print(f"Error amending order: {e}")
        return None

def cancel_order(symbol, orderId=None, orderLinkId=None, category="linear"):
    """Cancel a specific order"""
    try:
        params = {
            "category": category,
            "symbol": symbol
        }
        
        if orderId:
            params["orderId"] = orderId
        elif orderLinkId:
            params["orderLinkId"] = orderLinkId
            
        response = session.cancel_order(**params)
        return response
    except Exception as e:
        print(f"Error canceling order: {e}")
        return None

def cancel_all_orders(symbol=None, category="linear"):
    """Cancel all open orders"""
    try:
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
            
        response = session.cancel_all_orders(**params)
        return response
    except Exception as e:
        print(f"Error canceling all orders: {e}")
        return None
```

## WebSocket Implementation

WebSocket connections provide real-time data streaming for market updates and account changes:

```python
from pybit.unified_trading import WebSocket
from time import sleep
import threading

class BybitWebSocketManager:
    def __init__(self, api_key, api_secret, testnet=True):
        self.ws_public = WebSocket(
            testnet=testnet,
            channel_type="public"
        )
        
        self.ws_private = WebSocket(
            testnet=testnet,
            channel_type="private",
            api_key=api_key,
            api_secret=api_secret
        )
        
        self.market_data = {}
        self.positions = {}
        self.orders = {}
        
    def handle_orderbook(self, message):
        """Process orderbook updates"""
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data[symbol] = {
                    "orderbook": data,
                    "timestamp": message.get("ts")
                }
        except Exception as e:
            print(f"Error handling orderbook: {e}")
    
    def handle_trades(self, message):
        """Process trade updates"""
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s")
                if symbol:
                    if symbol not in self.market_data:
                        self.market_data[symbol] = {}
                    self.market_data[symbol]["last_trade"] = trade
        except Exception as e:
            print(f"Error handling trades: {e}")
    
    def handle_position(self, message):
        """Process position updates"""
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
        except Exception as e:
            print(f"Error handling position: {e}")
    
    def handle_order(self, message):
        """Process order updates"""
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
        except Exception as e:
            print(f"Error handling order: {e}")
    
    def subscribe_public_channels(self, symbols, channels=["orderbook", "trade"]):
        """Subscribe to public market data channels"""
        for symbol in symbols:
            if "orderbook" in channels:
                self.ws_public.orderbook_stream(
                    depth=50,
                    symbol=symbol,
                    callback=self.handle_orderbook
                )
            if "trade" in channels:
                self.ws_public.trade_stream(
                    symbol=symbol,
                    callback=self.handle_trades
                )
    
    def subscribe_private_channels(self):
        """Subscribe to private account channels"""
        self.ws_private.position_stream(callback=self.handle_position)
        self.ws_private.order_stream(callback=self.handle_order)
        self.ws_private.execution_stream(callback=self.handle_order)
        self.ws_private.wallet_stream(callback=self.handle_position)
```

## Complete Trading Bot Template

Here's a comprehensive trading bot template that combines all the components:

```python
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional
import json

class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize the Bybit trading bot"""
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=5000
        )
        
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet)
        
        # Trading parameters
        self.active_positions = {}
        self.pending_orders = {}
        self.max_position_size = 1000  # USD value
        self.risk_per_trade = 0.02  # 2% risk per trade
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
    def calculate_position_size(self, account_balance: float, stop_loss_percentage: float) -> float:
        """Calculate position size based on risk management"""
        risk_amount = account_balance * self.risk_per_trade
        position_size = risk_amount / stop_loss_percentage
        return min(position_size, self.max_position_size)
    
    def check_rate_limits(self) -> bool:
        """Monitor API rate limits"""
        # Rate limits: 120 req/min for market data, 60 req/min for orders
        return True  # Implement rate limit tracking
    
    def execute_trading_strategy(self, symbol: str, category: str = "linear"):
        """Main trading strategy execution"""
        try:
            # Get current market data
            market_data = self.get_market_data(symbol, category)
            if not market_data:
                return
            
            # Get account balance
            balance_info = self.get_account_balance()
            if not balance_info:
                return
            
            # Check existing positions
            positions = self.get_position_info(symbol, category)
            
            # Implement your trading logic here
            # Example: Simple momentum strategy
            ticker = market_data.get("ticker", {})
            if ticker.get("result", {}).get("list", []):
                ticker_data = ticker["result"]["list"]
                last_price = float(ticker_data.get("lastPrice", 0))
                
                # Calculate technical indicators
                # Add your strategy logic here
                
                # Example entry condition
                if self.should_enter_trade(ticker_data):
                    # Calculate position size
                    position_size = self.calculate_position_size(
                        account_balance=1000,  # Get from balance_info
                        stop_loss_percentage=0.02
                    )
                    
                    # Place order with TP/SL
                    tp_price = last_price * 1.02  # 2% take profit
                    sl_price = last_price * 0.98  # 2% stop loss
                    
                    order = self.place_limit_order_with_sl_tp(
                        symbol=symbol,
                        side="Buy",
                        qty=position_size / last_price,
                        price=last_price * 0.999,  # Slightly below market
                        tp_price=tp_price,
                        sl_price=sl_price,
                        category=category
                    )
                    
                    if order:
                        self.logger.info(f"Order placed: {order}")
                        
        except Exception as e:
            self.logger.error(f"Strategy execution error: {e}")
    
    def should_enter_trade(self, ticker_data: Dict) -> bool:
        """Determine if entry conditions are met"""
        # Implement your entry logic
        return False
    
    def manage_open_positions(self):
        """Monitor and manage open positions"""
        try:
            positions = self.session.get_positions(category="linear")
            
            for position in positions.get("result", {}).get("list", []):
                symbol = position.get("symbol")
                side = position.get("side")
                size = float(position.get("size", 0))
                unrealized_pnl = float(position.get("unrealisedPnl", 0))
                
                # Implement position management logic
                # Example: Trailing stop loss
                if unrealized_pnl > 0:
                    # Update stop loss to break even or trail
                    pass
                    
        except Exception as e:
            self.logger.error(f"Position management error: {e}")
    
    def run(self, symbols: List[str], interval: int = 60):
        """Main bot execution loop"""
        self.logger.info("Starting Bybit Trading Bot")
        
        # Subscribe to WebSocket channels
        self.ws_manager.subscribe_public_channels(symbols)
        self.ws_manager.subscribe_private_channels()
        
        # Main trading loop
        while True:
            try:
                for symbol in symbols:
                    self.execute_trading_strategy(symbol)
                    self.manage_open_positions()
                    
                time.sleep(interval)
                
            except KeyboardInterrupt:
                self.logger.info("Bot stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Bot error: {e}")
                time.sleep(10)
                
# Initialize and run the bot
if __name__ == "__main__":
    bot = BybitTradingBot(
        api_key="your_api_key",
        api_secret="your_api_secret",
        testnet=True
    )
    
    # Run bot for specific symbols
    bot.run(symbols=["BTCUSDT", "ETHUSDT"], interval=30)
```

## Advanced Features

**Stop Order Management**

```python
def place_stop_order(symbol, side, qty, stop_price, trigger_price, category="linear"):
    """Place a stop order (stop loss or stop entry)"""
    try:
        order = session.place_order(
            category=category,
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            triggerPrice=str(trigger_price),
            triggerBy="LastPrice",
            orderFilter="StopOrder",
            timeInForce="IOC",
            positionIdx=0
        )
        return order
    except Exception as e:
        print(f"Error placing stop order: {e}")
        return None
```

**Conditional Orders**

```python
def place_conditional_order(symbol, side, qty, price, trigger_price, category="linear"):
    """Place a conditional limit order"""
    try:
        order = session.place_order(
            category=category,
            symbol=symbol,
            side=side,
            orderType="Limit",
            qty=str(qty),
            price=str(price),
            triggerPrice=str(trigger_price),
            triggerBy="LastPrice",
            orderFilter="StopOrder",
            timeInForce="GTC",
            positionIdx=0
        )
        return order
    except Exception as e:
        print(f"Error placing conditional order: {e}")
        return None
```

## Error Handling and Best Practices

**Robust Error Handling**

```python
class BybitAPIError(Exception):
    """Custom exception for Bybit API errors"""
    pass

def safe_api_call(func, *args, **kwargs):
    """Wrapper for safe API calls with retry logic"""
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            response = func(*args, **kwargs)
            
            if response.get("retCode") == 0:
                return response
            else:
                error_msg = response.get("retMsg", "Unknown error")
                raise BybitAPIError(f"API Error: {error_msg}")
                
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(retry_delay * (attempt + 1))
    
    return None
```

The V5 API consolidates multiple product types into a unified interface, making it easier to trade across different markets. When implementing your bot, always test thoroughly in the testnet environment before deploying to mainnet, and ensure proper risk management and position sizing are in place
