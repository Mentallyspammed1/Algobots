
pybit/_websocket_stream.py



Based on my comprehensive search through the Bybit Python SDK (`pybit`) repository, I cannot find any specific implementation of an "advanced market making bot" with "25 improvements and integrations" as a single cohesive system. 

However, the `pybit` library provides numerous components and features that would be essential for building advanced market making bots:

## Key Market Making Components Available:

**WebSocket Trading Support**: The library added WebSocket trading functionality which enables low-latency order execution critical for market making [1](#14-0) 

**Batch Order Operations**: The library supports batch WebSocket order methods including `place_batch_order`, `amend_batch_order`, and `cancel_batch_order` for efficient bulk order management [2](#14-1) 

**Market Maker Protection (MMP)**: The repository includes Market Maker Protection functionality which is essential for risk management in market making operations, though I cannot access the specific implementation details in the current search results.

**Spread Trading Support**: Recent versions added comprehensive spread trading functionality with both HTTP API methods and WebSocket support [3](#14-2) 

**Fast Execution Stream**: The library includes a `fast_execution_stream` WebSocket feature for high-speed trade execution [4](#14-3) 

## Library Evolution:

The pybit library has evolved significantly, with version 5.0.0 representing a major upgrade to support Bybit's v5 APIs and Unified Trading Accounts [5](#14-4) 

## Notes:

The pybit library appears to be a comprehensive SDK that provides the building blocks for creating advanced market making systems, rather than containing a pre-built "advanced market making bot" with specifically "25 improvements." The various features and improvements across multiple versions would allow developers to construct sophisticated market making strategies, but there is no single bot implementation visible in the repository structure I can access.

If you're looking for a specific market making bot implementation or tutorial, you may need to look for example files or documentation that might not be accessible through my current search capabilities, or this might refer to external implementations that use the pybit library rather than being part of the library itself.

Looking at your request for a "Signal generation and execution walkthrough", I need to clarify that the pybit library is primarily a client library for interacting with Bybit's trading APIs, not a signal generation system. However, I can walk you through how you would implement a complete trading workflow using pybit's components.

## Signal Generation and Execution Architecture

Based on the codebase, here's how you would structure a signal-based trading system using pybit:

### 1. Market Data Collection (Signal Input)

You would use the WebSocket streams to collect real-time market data for signal generation [1](#2-0) . The key data streams include:

- **Price data**: `ticker_stream()` for current prices [2](#2-1) 
- **Order book data**: `orderbook_stream()` for depth analysis [1](#2-0) 
- **Trade data**: `trade_stream()` for volume analysis [3](#2-2) 
- **Kline data**: `kline_stream()` for technical analysis [4](#2-3) 

### 2. Signal Processing

The WebSocket infrastructure processes incoming messages through callback functions [5](#2-4) . Your signal generation logic would be implemented in these callback functions:

```python
def signal_callback(message):
    # Your signal generation logic here
    # Process the incoming market data
    # Generate buy/sell signals
    pass
```

### 3. Order Execution

Once signals are generated, you have two execution options:

#### HTTP-based Execution
For non-latency-critical signals, use the HTTP order placement functions. The main HTTP class provides access to all trading operations through multiple inheritance [6](#2-5) .

#### WebSocket-based Execution  
For low-latency execution, use the WebSocket trading operations [7](#2-6) . The `WebSocketTrading` class provides real-time order operations:

- `place_order()` for immediate execution
- `amend_order()` for order modifications  
- `cancel_order()` for order cancellations

### 4. Position Monitoring

Monitor your positions in real-time using the private WebSocket streams [8](#2-7) :

- `position_stream()` for position updates
- `execution_stream()` for fill notifications [9](#2-8) 
- `order_stream()` for order status changes [10](#2-9) 

### 5. Connection Management

The WebSocket infrastructure handles connection management automatically [11](#2-10) , including:

- Automatic reconnection on disconnects
- Authentication for private channels [12](#2-11) 
- Subscription management and resubscription after reconnects

## Example Workflow Structure

```python
from pybit.unified_trading import HTTP, WebSocket, WebSocketTrading

# Initialize clients
http_session = HTTP(api_key="...", api_secret="...")
ws_public = WebSocket(channel_type="linear")  
ws_private = WebSocket(channel_type="private", api_key="...", api_secret="...")
ws_trading = WebSocketTrading(api_key="...", api_secret="...")

# Set up market data streams for signal generation
ws_public.ticker_stream("BTCUSDT", signal_callback)
ws_public.orderbook_stream(50, "BTCUSDT", depth_callback)

# Monitor positions and executions
ws_private.position_stream(position_callback)
ws_private.execution_stream(execution_callback)
```

## Notes

The pybit library provides the infrastructure for building trading systems but doesn't include signal generation algorithms. You would need to implement your own technical analysis, machine learning models, or other signal generation logic within the callback functions. The library's strength is in providing reliable, low-latency connectivity to Bybit's trading infrastructure [13](#2-12) .

<cite/>

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Core Components (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)Looking at your request for "All websockets functions .json format", I understand you're asking about the WebSocket functionality in the pybit library and want to see the JSON message formats used by these functions.

## WebSocket Classes and Functions

The pybit library provides three main WebSocket classes in `pybit/unified_trading.py`:

### 1. WebSocket Class (Public/Private Streams) [1](#0-0) 

**Private Stream Functions:**
- `position_stream(callback)` [2](#0-1) 
- `order_stream(callback)` [3](#0-2) 
- `execution_stream(callback)` [4](#0-3) 
- `fast_execution_stream(callback, categorised_topic="")` [5](#0-4) 
- `wallet_stream(callback)` [6](#0-5) 
- `greek_stream(callback)` [7](#0-6) 
- `spread_order_stream(callback)` [8](#0-7) 
- `spread_execution_stream(callback)` [9](#0-8) 

**Public Stream Functions:**
- `orderbook_stream(depth, symbol, callback)` [10](#0-9) 
- `trade_stream(symbol, callback)` [11](#0-10) 
- `ticker_stream(symbol, callback)` [12](#0-11) 
- `kline_stream(interval, symbol, callback)` [13](#0-12) 
- `liquidation_stream(symbol, callback)` [14](#0-13) 
- `all_liquidation_stream(symbol, callback)` [15](#0-14) 
- `lt_kline_stream(interval, symbol, callback)` [16](#0-15) 

### 2. WebSocketTrading Class (Order Operations) [17](#0-16) 

**Trading Functions:**
- `place_order(callback, **kwargs)`
- `amend_order(callback, **kwargs)`
- `cancel_order(callback, **kwargs)`
- `place_batch_order(callback, **kwargs)`
- `amend_batch_order(callback, **kwargs)`
- `cancel_batch_order(callback, **kwargs)`

### 3. WebsocketSpreadTrading Class [18](#0-17) 

## JSON Message Formats

### Subscription Messages

The underlying subscription mechanism uses this JSON format [19](#0-18) :

```json
{
  "op": "subscribe",
  "req_id": "uuid4-generated-id",
  "args": ["topic.symbol"]
}
```

### Authentication Messages

For private channels, authentication uses [20](#0-19) :

```json
{
  "op": "auth",
  "args": ["api_key", expires_timestamp, "signature"]
}
```

### Trading Operation Messages

WebSocket trading operations use this format [21](#0-20) :

```json
{
  "reqId": "uuid4-generated-id",
  "header": {
    "X-BAPI-TIMESTAMP": timestamp
  },
  "op": "order.create",
  "args": [request_parameters]
}
```

### Ping Messages

The system sends custom ping messages [22](#0-21) :

```json
{"op": "ping"}
```

## Notes

All WebSocket functions in pybit use callback-based message handling rather than returning JSON directly. The JSON formats shown above are the internal message structures used for communication with Bybit's WebSocket API. The actual data received in your callback functions will be the parsed response messages from Bybit's servers.

<cite />

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [WebSocket Communication Infrastructure (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.4)
- [WebSocket Trading Operations (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.5)

Looking at your request for "All order placement functions", you're asking about the order placement functionality in the pybit library. Based on the codebase context, there are two main ways to place orders: through HTTP REST API calls and through WebSocket trading operations.

## HTTP Order Placement Functions

The primary HTTP order placement functions are located in the `TradeHTTP` class [1](#1-0) :

### Individual Order Functions
- `place_order(**kwargs)` - Creates single orders for spot, spot margin, linear perpetual, inverse futures and options [2](#1-1) 
- `amend_order(**kwargs)` - Modifies existing orders [3](#1-2) 
- `cancel_order(**kwargs)` - Cancels existing orders [4](#1-3) 

### Batch Order Functions
- `place_batch_order(**kwargs)` - Creates multiple orders in a single request (currently supports options only) [5](#1-4) 
- `amend_batch_order(**kwargs)` - Modifies multiple orders in a single request [6](#1-5) 

## WebSocket Order Placement Functions

The WebSocket trading functions are available through the `WebSocketTrading` class [7](#1-6) :

### Individual WebSocket Order Functions
- `place_order(callback, **kwargs)` - Places orders via WebSocket [8](#1-7) 
- `amend_order(callback, **kwargs)` - Amends orders via WebSocket [9](#1-8) 
- `cancel_order(callback, **kwargs)` - Cancels orders via WebSocket [10](#1-9) 

### Batch WebSocket Order Functions
- `place_batch_order(callback, **kwargs)` - Places multiple orders via WebSocket [11](#1-10) 
- `amend_batch_order(callback, **kwargs)` - Amends multiple orders via WebSocket [12](#1-11) 
- `cancel_batch_order(callback, **kwargs)` - Cancels multiple orders via WebSocket [13](#1-12) 

## Implementation Details

The WebSocket trading functions use the underlying `_send_order_operation` method which constructs JSON messages with operations like "order.create", "order.amend", "order.cancel", etc. [14](#1-13) 

All these functions are accessible through the unified trading interface by importing from `pybit.unified_trading` [15](#1-14) .

## Notes

The batch order functionality was added in version 5.10.0 and currently only supports options trading for HTTP requests [16](#1-15) . WebSocket trading support was introduced in version 5.8.0 [17](#1-16) .

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
Looking at your request for a "Signal generation and execution walkthrough", I need to clarify that the pybit library is primarily a client library for interacting with Bybit's trading APIs, not a signal generation system. However, I can walk you through how you would implement a complete trading workflow using pybit's components.

## Signal Generation and Execution Architecture

Based on the codebase, here's how you would structure a signal-based trading system using pybit:

### 1. Market Data Collection (Signal Input)

You would use the WebSocket streams to collect real-time market data for signal generation [1](#2-0) . The key data streams include:

- **Price data**: `ticker_stream()` for current prices [2](#2-1) 
- **Order book data**: `orderbook_stream()` for depth analysis [1](#2-0) 
- **Trade data**: `trade_stream()` for volume analysis [3](#2-2) 
- **Kline data**: `kline_stream()` for technical analysis [4](#2-3) 

### 2. Signal Processing

The WebSocket infrastructure processes incoming messages through callback functions [5](#2-4) . Your signal generation logic would be implemented in these callback functions:

```python
def signal_callback(message):
    # Your signal generation logic here
    # Process the incoming market data
    # Generate buy/sell signals
    pass
```

### 3. Order Execution

Once signals are generated, you have two execution options:

#### HTTP-based Execution
For non-latency-critical signals, use the HTTP order placement functions. The main HTTP class provides access to all trading operations through multiple inheritance [6](#2-5) .

#### WebSocket-based Execution  
For low-latency execution, use the WebSocket trading operations [7](#2-6) . The `WebSocketTrading` class provides real-time order operations:

- `place_order()` for immediate execution
- `amend_order()` for order modifications  
- `cancel_order()` for order cancellations

### 4. Position Monitoring

Monitor your positions in real-time using the private WebSocket streams [8](#2-7) :

- `position_stream()` for position updates
- `execution_stream()` for fill notifications [9](#2-8) 
- `order_stream()` for order status changes [10](#2-9) 

### 5. Connection Management

The WebSocket infrastructure handles connection management automatically [11](#2-10) , including:

- Automatic reconnection on disconnects
- Authentication for private channels [12](#2-11) 
- Subscription management and resubscription after reconnects

## Example Workflow Structure

```python
from pybit.unified_trading import HTTP, WebSocket, WebSocketTrading

# Initialize clients
http_session = HTTP(api_key="...", api_secret="...")
ws_public = WebSocket(channel_type="linear")  
ws_private = WebSocket(channel_type="private", api_key="...", api_secret="...")
ws_trading = WebSocketTrading(api_key="...", api_secret="...")

# Set up market data streams for signal generation
ws_public.ticker_stream("BTCUSDT", signal_callback)
ws_public.orderbook_stream(50, "BTCUSDT", depth_callback)

# Monitor positions and executions
ws_private.position_stream(position_callback)
ws_private.execution_stream(execution_callback)
```

## Notes

The pybit library provides the infrastructure for building trading systems but doesn't include signal generation algorithms. You would need to implement your own technical analysis, machine learning models, or other signal generation logic within the callback functions. The library's strength is in providing reliable, low-latency connectivity to Bybit's trading infrastructure [13](#2-12) .

<cite/>

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Core Components (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)
Based on the codebase context, you're asking about leverage setting and account balance management in the Bybit Python SDK (`pybit`). This involves two main API modules: **Position Management** for leverage configuration and **Account Management** for balance queries.

## Leverage Setting

Leverage configuration is handled through the Position Management API in `PositionHTTP` class [1](#0-0) . The `set_leverage()` method allows you to configure buy and sell leverage for trading positions.

**Key requirements for leverage setting:**
- Must specify `category` (product type: `linear`, `inverse`, or `option`)
- Must provide `symbol` (trading pair)
- Must set both `buyLeverage` and `sellLeverage` (in one-way mode, these must be equal)
- Leverage range is 0 to maximum allowed for the risk limit [2](#0-1) 

The API endpoint mapping is defined in the Position enum [3](#0-2) .

## Account Balance Queries

Account balance information is managed through the Account Management API in `AccountHTTP` class [4](#0-3) . The `get_wallet_balance()` method retrieves comprehensive wallet information including asset balances and risk metrics.

**Account types supported:**
- **Unified Account**: `accountType="UNIFIED"` - provides cross-margin and portfolio margin features
- **Classic Account**: `accountType="CONTRACT"` - traditional isolated margin accounts [5](#0-4) 

For specific coin balance queries, you can use `get_coin_balance()` [6](#0-5)  from the Asset Management API, which supports querying individual coin balances across different account types.

## Integration Pattern

Both leverage and balance operations integrate through the unified HTTP client architecture, where all API modules inherit from `_V5HTTPManager` and use the `_submit_request()` method for authenticated API calls [7](#0-6) [8](#0-7) .

**Notes**

The codebase also includes spot margin trading leverage through `SpotMarginTradeHTTP` [9](#0-8) , but this is specifically for spot margin trading (leverage range 2-5x) rather than derivatives position leverage. The Position Management API handles derivatives leverage while Account Management handles balance queries across all account types.

Wiki pages you might want to explore:
- [Account Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.2)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)

You're asking about order management functions in the Bybit Python SDK (`pybit`). The order management functionality is primarily handled through the **Trade API** module, which provides comprehensive order lifecycle management capabilities.

## Core Order Management Functions

The main order management functions are implemented in the `TradeHTTP` class [1](#1-0) , which provides the following core operations:

### Basic Order Operations

- **`place_order()`** - Creates new orders for spot, spot margin, linear perpetual, inverse futures and options [2](#1-1) 
- **`amend_order()`** - Modifies existing orders for linear contracts and options [3](#1-2) 
- **`cancel_order()`** - Cancels individual orders across all supported product types [4](#1-3) 
- **`cancel_all_orders()`** - Cancels all open orders for a given category [5](#1-4) 

### Batch Order Operations

For options trading, the API supports batch operations:

- **`place_batch_order()`** - Creates multiple orders in a single request (options only) [6](#1-5) 
- **`amend_batch_order()`** - Modifies multiple orders simultaneously [7](#1-6) 
- **`cancel_batch_order()`** - Cancels multiple orders in one request [8](#1-7) 

### Order Query Functions

- **`get_open_orders()`** - Retrieves unfilled or partially filled orders in real-time [9](#1-8) 
- **`get_order_history()`** - Queries historical order data [10](#1-9) 

## WebSocket Order Management

The library also provides real-time order management through WebSocket connections:

### WebSocket Trading Operations

The `WebSocketTrading` class [11](#1-10)  enables real-time order operations:

- **`place_order()`** - Real-time order placement via WebSocket [12](#1-11) 
- **`amend_order()`** - Real-time order modification [13](#1-12) 
- **`cancel_order()`** - Real-time order cancellation [14](#1-13) 

### WebSocket Order Monitoring

The `WebSocket` class provides real-time order status monitoring:

- **`order_stream()`** - Subscribe to real-time order updates [15](#1-14) 
- **`execution_stream()`** - Monitor trade executions in real-time [16](#1-15) 

## Specialized Order Management

### Spread Trading Orders

For spread trading, there's a separate set of order management functions in `SpreadHTTP` [17](#1-16) :

- **`place_order()`** - Create spread trading orders [18](#1-17) 
- **`amend_order()`** - Modify spread orders [19](#1-18) 
- **`cancel_order()`** and **`cancel_all_orders()`** - Cancel spread orders [20](#1-19) 

## Integration Architecture

All order management functions integrate through the unified HTTP client architecture [21](#1-20) , where the main `HTTP` class inherits from `TradeHTTP` and other specialized modules. This provides a single entry point for all order management operations while maintaining the underlying modular structure.

**Notes**

The order management system supports both Unified Trading Accounts (UTA) and traditional account types, with different product categories (`spot`, `linear`, `inverse`, `option`) requiring different parameter sets. The WebSocket trading functionality was introduced in version 5.8.0 [22](#1-21)  and provides lower-latency order operations compared to REST API calls.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)
You're asking about advanced order types in the Bybit Python SDK (`pybit`), specifically limit orders with conditional take-profit/stop-loss, trailing stops, and profit checking functionality. These features are primarily handled through the **Position Management API** and **Trade Management API**.

## Conditional TP/SL Orders

The Position Management API provides conditional take-profit and stop-loss functionality through the `set_trading_stop()` method [1](#2-0) . This method allows you to set take-profit, stop-loss, or trailing stop orders for existing positions.

The API supports different TP/SL modes through `set_tp_sl_mode()` [2](#2-1) , which lets you configure whether stops should close the full position or only partial amounts:

- **Full Mode**: Complete position closure when triggered
- **Partial Mode**: Partial position closure when triggered

## Limit Order Placement

Basic limit orders are created using the `place_order()` method in the Trade API [3](#2-2) . This method supports creating limit orders across all product types (spot, linear, inverse, options) with the `orderType` parameter set to "Limit".

## Trailing Stop Implementation

Trailing stops are configured through the same `set_trading_stop()` method [1](#2-0) . The method accepts parameters for trailing stop configuration, allowing the stop price to automatically adjust as the position moves in your favor.

## Profit Checking and Execution Monitoring

For profit checking and monitoring order executions, the API provides several methods:

### Real-time Execution Monitoring
- `get_executions()` - Query execution records sorted by execution time [4](#2-3) 
- `get_closed_pnl()` - Query closed profit and loss records [5](#2-4) 

### WebSocket Streams for Real-time Updates
The WebSocket API provides real-time monitoring capabilities:
- `execution_stream()` - Subscribe to execution updates in real-time [6](#2-5) 
- `order_stream()` - Monitor order status changes [7](#2-6) 

## Integration Architecture

All these order management functions integrate through the unified HTTP client architecture [8](#2-7) , where the main `HTTP` class inherits from both `TradeHTTP` and `PositionHTTP` modules, providing a single entry point for complex order strategies.

**Notes**

The conditional TP/SL and trailing stop functionality requires existing positions and works across unified accounts (linear, option) and normal accounts (linear, inverse). The WebSocket trading functionality introduced in version 5.8.0 [9](#2-8)  provides lower-latency operations for time-sensitive profit checking and order management.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
You're asking about orderbook management and liquidation levels functionality in the Bybit Python SDK (`pybit`). This involves **orderbook data streaming**, **liquidation monitoring**, and **market data management** through the WebSocket and Market Data APIs.

## Orderbook Management

The orderbook functionality is handled through both REST API and WebSocket streaming:

### REST API Orderbook Access
The `MarketHTTP` class provides orderbook snapshots through the `get_orderbook()` method [1](#3-0) . This method supports all product categories (spot, linear, inverse, option) and returns current market depth data.

### Real-time Orderbook Streaming
For real-time orderbook updates, the `WebSocket` class provides the `orderbook_stream()` method [2](#3-1) . This supports different depth levels with varying push frequencies:

- **Linear & Inverse**: Level 1 (10ms), Level 50 (20ms), Level 200/500 (100ms)
- **Spot**: Level 1 (10ms), Level 50 (20ms) 
- **Options**: Level 25 (20ms), Level 100 (100ms)

The WebSocket manager processes orderbook delta updates through `_process_delta_orderbook()` [3](#3-2) , which handles snapshot initialization and incremental updates for bid/ask levels.

### Spread Trading Orderbook
For spread trading, there's specialized orderbook access through `WebsocketSpreadTrading` [4](#3-3)  and `SpreadHTTP` [5](#3-4) .

## Liquidation Levels Monitoring

The SDK provides comprehensive liquidation monitoring capabilities:

### Liquidation Streams
Two WebSocket methods handle liquidation data:

1. **`liquidation_stream()`** (deprecated) [6](#3-5)  - Pushes at most one liquidation per second per symbol
2. **`all_liquidation_stream()`** (recommended) [7](#3-6)  - Pushes all liquidations with 500ms frequency

The deprecation was introduced in version 5.10.0 [8](#3-7) , with the new method providing more comprehensive liquidation coverage.

### Risk Management Integration
Liquidation levels connect to position risk management through the `PositionHTTP` class, which includes `set_risk_limit()` functionality [9](#3-8) . This method controls maximum position values under different margin requirements, directly affecting liquidation thresholds.

## Integration Architecture

All orderbook and liquidation functionality integrates through the unified trading interface [10](#3-9) , where the main `HTTP` class inherits from `MarketHTTP` and other specialized modules, while WebSocket classes provide real-time streaming capabilities.

**Notes**

The orderbook management system supports both public market data access and private account-specific data. Liquidation monitoring works across linear and inverse perpetual contracts, with spread trading having its own specialized endpoints. The WebSocket infrastructure handles delta processing for efficient real-time updates, maintaining local orderbook state through snapshot and incremental update mechanisms.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)
You're asking about indicators and market data fetching functionality in the Bybit Python SDK (`pybit`). This involves the **Market Data API** module, which provides comprehensive access to price data, technical indicators, and market statistics.

## Market Data Fetching

The core market data functionality is implemented in the `MarketHTTP` class [1](#4-0) , which provides methods for retrieving various types of market information.

### Price and Kline Data

The primary data fetching methods include:

- **`get_kline()`** - Retrieves candlestick/kline data for technical analysis [2](#4-1) 
- **`get_mark_price_kline()`** - Gets mark price kline data for derivatives [3](#4-2) 
- **`get_index_price_kline()`** - Fetches index price kline data [4](#4-3) 
- **`get_premium_index_price_kline()`** - Retrieves premium index price data for linear contracts [5](#4-4) 

### Market Statistics and Indicators

For market analysis and indicator calculation:

- **`get_tickers()`** - Provides 24h ticker statistics including price changes and volume [6](#4-5) 
- **`get_open_interest()`** - Retrieves open interest data for sentiment analysis [7](#4-6) 
- **`get_long_short_ratio()`** - Gets long/short ratio for market sentiment indicators [8](#4-7) 
- **`get_historical_volatility()`** - Fetches historical volatility data for options [9](#4-8) 

### Real-time Data Streaming

For real-time indicator updates, the `WebSocket` class provides streaming capabilities:

- **`kline_stream()`** - Real-time kline data for live indicator calculation [10](#4-9) 
- **`ticker_stream()`** - Live ticker updates for price-based indicators [11](#4-10) 

## API Endpoint Structure

All market data endpoints are defined in the `Market` enum [12](#4-11) , which maps method names to their corresponding API paths. The methods follow a consistent pattern where they call `_submit_request()` with GET method and pass query parameters [13](#4-12) .

## Integration Architecture

The market data functionality integrates through the unified trading interface [14](#4-13) , where the main `HTTP` class inherits from `MarketHTTP` along with other specialized modules, providing a single entry point for all market data operations.

**Notes**

The market data API supports different product categories (`spot`, `linear`, `inverse`, `option`) with varying method availability. Most methods are public and don't require authentication, making them suitable for building technical indicators and market analysis tools. The WebSocket streaming provides real-time updates essential for live indicator calculations and algorithmic trading strategies.

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)

You're asking about decimal and precision handling in the Bybit Python SDK (`pybit`). This involves how the library manages numerical precision for trading operations, particularly in order quantities, prices, and financial calculations.

## Decimal Precision in HTTP Request Processing

The core decimal handling occurs in the HTTP manager's request processing. [1](#5-0)  The `_submit_request()` method includes specific logic to handle floating-point precision issues by converting floating whole numbers to integers to prevent authentication signature errors.

This precision handling is critical because Bybit's API authentication requires exact parameter matching, and floating-point representation errors could cause signature mismatches.

## String-Based Parameter Requirements

Throughout the API, all numerical parameters that require precision are handled as strings rather than native Python numbers. This pattern is consistent across all trading operations:

### Order Management [2](#5-1)  The `place_order()` method requires `qty` (quantity) as a string parameter, ensuring precise decimal representation without floating-point errors.

### Position Management [3](#5-2)  Leverage settings use string parameters for `buyLeverage` and `sellLeverage` to maintain exact decimal precision within the specified range.

### Spot Margin Trading [4](#5-3)  Leverage configuration requires string format with specific decimal constraints (leverage range 2-5).

## Market Maker Protection Precision Requirements [5](#5-4)  The MMP (Market Maker Protection) system explicitly requires decimal precision with "up to 2 decimal places" for `qtyLimit` and `deltaLimit` parameters, demonstrating the importance of precise decimal handling in risk management.

## WebSocket Orderbook Precision [6](#5-5)  The WebSocket orderbook processing uses `float()` conversion for quantity comparisons, but this is specifically for delta processing logic rather than API parameter transmission.

## Integration Pattern

All precision-sensitive operations follow the same pattern: accept string parameters from users, process them through the HTTP manager's precision handling logic, and transmit them to Bybit's API without floating-point conversion errors. [7](#5-6)  This ensures that decimal precision is maintained throughout the entire request lifecycle.

**Notes**

The string-based approach for all financial parameters is a deliberate design choice to avoid floating-point precision issues common in financial applications. This pattern is consistent across all API modules (Trade, Position, Account, Asset) and ensures reliable communication with Bybit's precision-sensitive endpoints.

Wiki pages you might want to explore:
- [Account Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.2)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)

You're asking about timezone handling in the Bybit Python SDK (`pybit`). The library handles timezone-related functionality primarily through **timestamp generation** and **authentication expiration** mechanisms.

## Timestamp Generation and UTC Handling

The core timezone handling occurs in the HTTP manager's authentication system. [1](#6-0)  The library imports `datetime` with timezone support, specifically using UTC for all timestamp operations.

For WebSocket authentication, the system generates timestamps with timezone awareness. [2](#6-1)  The authentication process uses `_helpers.generate_timestamp()` to create UTC-based timestamps for signature generation.

## Authentication Expiration Timing

The WebSocket manager handles timezone-sensitive authentication expiration through the `private_auth_expire` parameter. [3](#6-2)  This parameter controls the delta time for private authentication expiration in seconds, ensuring consistent timing regardless of local timezone.

The authentication signature generation process combines the current UTC timestamp with the expiration delta. [4](#6-3)  This creates a time-bounded authentication token that works consistently across different timezone environments.

## Rate Limit Reset Timing

The HTTP manager handles timezone-aware rate limit resets. [5](#6-4)  When encountering rate limit errors (code 10006), the system calculates sleep duration based on the `X-Bapi-Limit-Reset-Timestamp` header, converting the timestamp to local time for logging while maintaining UTC-based calculations.

## Error Response Timestamps

Error responses include timezone-aware timestamps for debugging purposes. [6](#6-5)  The system uses `dt.now(timezone.utc).strftime("%H:%M:%S")` to provide consistent UTC timestamps in error messages, ensuring log entries are timezone-independent.

## Integration Pattern

All timezone handling follows a consistent UTC-first approach where the library generates UTC timestamps internally and handles timezone conversions only for user-facing logging and display purposes. This ensures that API authentication and rate limiting work correctly regardless of the local system timezone.

**Notes**

The timezone handling is primarily focused on authentication and rate limiting rather than market data timestamps, which are handled by Bybit's servers. The library ensures consistent behavior across different deployment environments by standardizing on UTC for all internal timing operations while providing human-readable local time formatting for error messages and logs.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [WebSocket Communication Infrastructure (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.4)
You're asking about one-way and hedge mode functions in the Bybit Python SDK (`pybit`). This functionality is handled through the **Position Management API**, specifically the `switch_position_mode()` method.

## Position Mode Switching

The position mode functionality is implemented in the `PositionHTTP` class through the `switch_position_mode()` method [1](#7-0) . This method allows you to switch between two distinct position modes:

- **One-way Mode**: You can only open one position on Buy OR Sell side for a symbol
- **Hedge Mode**: You can open both Buy AND Sell side positions simultaneously for the same symbol

## API Implementation Details

The position mode switching is mapped to the `/v5/position/switch-mode` endpoint [2](#7-1) . The method supports both linear (USDT perpetual) and inverse futures contracts [3](#7-2) .

**Important limitations:**
- This functionality is **not applicable for unified accounts** [4](#7-3) 
- Only works with `category` values of `linear` and `inverse` [5](#7-4) 

## Integration with Leverage Settings

The position mode directly affects leverage configuration. When using the `set_leverage()` method [6](#7-5) , the behavior differs based on position mode:

- **One-way Mode**: `buyLeverage` must equal `sellLeverage` [7](#7-6) 
- **Hedge Mode**: You can set different leverage values for buy and sell positions

## Usage Pattern

The method follows the standard HTTP request pattern used throughout the Position Management API, requiring authentication and using POST method [8](#7-7) . It integrates with the unified trading interface through the same inheritance structure as other position management functions.

**Notes**

The position mode switching functionality was part of the major API restructuring that occurred in version 2.0.0 [9](#7-8) , which introduced the modular class inheritance system. This feature is specifically designed for derivatives trading and doesn't apply to spot trading or unified account structures.

Wiki pages you might want to explore:
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)

Wiki pages you might want to explore:
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
- [Miscellaneous API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.8)

You're asking about timezone handling in the Bybit Python SDK (`pybit`). The library handles timezone-related functionality primarily through **timestamp generation** and **authentication expiration** mechanisms.

## Timestamp Generation and UTC Handling

The core timezone handling occurs in the HTTP manager's authentication system. [1](#6-0)  The library imports `datetime` with timezone support, specifically using UTC for all timestamp operations.

For WebSocket authentication, the system generates timestamps with timezone awareness. [2](#6-1)  The authentication process uses `_helpers.generate_timestamp()` to create UTC-based timestamps for signature generation.

## Authentication Expiration Timing

The WebSocket manager handles timezone-sensitive authentication expiration through the `private_auth_expire` parameter. [3](#6-2)  This parameter controls the delta time for private authentication expiration in seconds, ensuring consistent timing regardless of local timezone.

The authentication signature generation process combines the current UTC timestamp with the expiration delta. [4](#6-3)  This creates a time-bounded authentication token that works consistently across different timezone environments.

## Rate Limit Reset Timing

The HTTP manager handles timezone-aware rate limit resets. [5](#6-4)  When encountering rate limit errors (code 10006), the system calculates sleep duration based on the `X-Bapi-Limit-Reset-Timestamp` header, converting the timestamp to local time for logging while maintaining UTC-based calculations.

## Error Response Timestamps

Error responses include timezone-aware timestamps for debugging purposes. [6](#6-5)  The system uses `dt.now(timezone.utc).strftime("%H:%M:%S")` to provide consistent UTC timestamps in error messages, ensuring log entries are timezone-independent.

## Integration Pattern

All timezone handling follows a consistent UTC-first approach where the library generates UTC timestamps internally and handles timezone conversions only for user-facing logging and display purposes. This ensures that API authentication and rate limiting work correctly regardless of the local system timezone.

**Notes**

The timezone handling is primarily focused on authentication and rate limiting rather than market data timestamps, which are handled by Bybit's servers. The library ensures consistent behavior across different deployment environments by standardizing on UTC for all internal timing operations while providing human-readable local time formatting for error messages and logs.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [WebSocket Communication Infrastructure (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.4)You're asking about leverage setting functionality in the Bybit Python SDK (`pybit`). This is handled through the **Position Management API**, specifically the `set_leverage()` method in the `PositionHTTP` class.

## Leverage Setting Implementation

The leverage setting functionality is implemented in [1](#8-0) . This method allows you to configure buy and sell leverage for trading positions.

**Key requirements:**
- `category` (string): Product type - Unified account supports `linear`, Normal account supports `linear` and `inverse` [2](#8-1) 
- `symbol` (string): Symbol name [3](#8-2) 
- `buyLeverage` (string): Leverage value from 0 to max leverage of corresponding risk limit [4](#8-3) 
- `sellLeverage` (string): Leverage value from 0 to max leverage of corresponding risk limit [5](#8-4) 

**Important constraint:** In one-way mode, `buyLeverage` must equal `sellLeverage` [6](#8-5) .

## API Endpoint Mapping

The leverage setting uses the `/v5/position/set-leverage` endpoint, which is defined in [7](#8-6)  and referenced in the method implementation [8](#8-7) .

## Alternative: Spot Margin Leverage

For spot margin trading, there's a separate leverage setting method in the Spot Margin Trading API: [9](#8-8) . This method is UTA-only and supports leverage values between 2 and 5 [10](#8-9) .

## Integration Architecture

Both leverage setting methods integrate through the unified HTTP client architecture, where the main `HTTP` class inherits from `PositionHTTP` and `SpotMarginTradeHTTP` [11](#8-10) , providing access to all leverage configuration methods through a single interface.

**Notes**

The Position Management API handles derivatives leverage for linear and inverse contracts, while the Spot Margin Trading API handles spot margin leverage with different constraints and account type requirements. All leverage values must be passed as strings to maintain decimal precision.

Wiki pages you might want to explore:
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
- [Spot Margin Trading API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.6)
- [Miscellaneous API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.8)I understand you want a comprehensive JSON-formatted summary of our conversation about the Bybit Python SDK (`pybit`). However, I need to clarify my current capabilities.

I can only answer questions about your current codebase based on the code snippets and context provided to me. I don't have access to the full codebase or the ability to generate complete code snippets that weren't shown in our conversation context.

From the limited code context provided (primarily from `pybit/_websocket_stream.py` and `CHANGELOG.md`), I can see this is about the Bybit Python SDK's WebSocket communication infrastructure [1](#9-0) , but I don't have access to the specific API implementation details that were discussed in our conversation (like the `PositionHTTP`, `TradeHTTP`, `MarketHTTP` classes and their methods).

To provide you with a detailed JSON summary with full code snippets, I would need:

1. Access to the actual implementation files containing the API classes and methods discussed
2. The specific code snippets for functions like `set_leverage()`, `place_order()`, `get_wallet_balance()`, etc.
3. The complete API endpoint definitions and parameter structures

Would you be able to provide the relevant source files containing the API implementations we discussed, or would you prefer a different type of summary based on the limited context I currently have access to?

<cite/>

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [WebSocket Communication Infrastructure (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.4)

You're asking about all HTTP methods available in the Bybit Python SDK (`pybit`). Based on the codebase context, the HTTP methods are implemented across multiple specialized API modules that inherit from the `_V5HTTPManager` base class and are unified through the `HTTP` class in `unified_trading.py`.

## HTTP Class Architecture

The main `HTTP` class uses multiple inheritance to combine all API functionality into a single interface [1](#10-0) . This unified approach provides access to all HTTP methods through one import.

## Core HTTP Method Categories

### Account Management Methods
The `AccountHTTP` class provides account-related operations:

- **`get_wallet_balance()`** - Retrieves wallet balance and risk information [2](#10-1) 
- **`get_transferable_amount()`** - Queries transferable coin amounts [3](#10-2) 
- **`upgrade_to_unified_trading_account()`** - Upgrades to unified account [4](#10-3) 
- **`get_borrow_history()`** - Retrieves interest records [5](#10-4) 
- **`repay_liability()`** - Manual liability repayment [6](#10-5) 
- **`get_collateral_info()`** - Collateral information queries [7](#10-6) 
- **`get_coin_greeks()`** - Current account Greeks information [8](#10-7) 
- **`get_fee_rates()`** - Trading fee rates for derivatives [9](#10-8) 
- **`get_contract_transaction_log()`** - Transaction logs for Classic accounts [10](#10-9) 
- **`set_margin_mode()`** - Configure margin mode (regular/portfolio) [11](#10-10) 

### Position Management Methods
The `PositionHTTP` class handles position-related operations:

- **`get_positions()`** - Query real-time position data [12](#10-11) 
- **`set_leverage()`** - Configure buy/sell leverage [13](#10-12) 
- **`switch_margin_mode()`** - Switch between cross/isolated margin [14](#10-13) 
- **`set_tp_sl_mode()`** - Configure TP/SL mode (Full/Partial) [15](#10-14) 
- **`switch_position_mode()`** - Switch between one-way/hedge mode [16](#10-15) 
- **`set_risk_limit()`** - Configure position risk limits [17](#10-16) 
- **`add_or_reduce_margin()`** - Manual margin adjustment [18](#10-17) 
- **`get_executions()`** - Query execution records [19](#10-18) 
- **`get_closed_pnl()`** - Query closed P&L records [20](#10-19) 

### Spot Margin Trading Methods
The `SpotMarginTradeHTTP` class provides spot margin functionality:

- **`spot_margin_trade_set_leverage()`** - Set spot margin leverage (2-5x) [21](#10-20) 
- **`spot_margin_trade_toggle_margin_trade()`** - Enable/disable margin trading [22](#10-21) 
- **`spot_margin_trade_get_status_and_leverage()`** - Get current status [23](#10-22) 
- **`spot_margin_trade_normal_borrow()`** - Borrow coins (non-UTA) [24](#10-23) 
- **`spot_margin_trade_normal_repay()`** - Repay borrowed coins [25](#10-24) 

### Spread Trading Methods
The `SpreadHTTP` class handles spread trading operations:

- **`place_order()`** - Create spread trading orders [26](#10-25) 
- **`amend_order()`** - Modify spread orders [27](#10-26) 
- **`cancel_order()`** - Cancel individual spread orders [28](#10-27) 
- **`cancel_all_orders()`** - Cancel all spread orders [29](#10-28) 
- **`get_open_orders()`** - Query open spread orders [30](#10-29) 
- **`get_order_history()`** - Query spread order history [31](#10-30) 
- **`get_trade_history()`** - Query spread trade history [32](#10-31) 

### Market Data Methods
The `MarketHTTP` class provides market data access:

- **`get_long_short_ratio()`** - Market sentiment indicators [33](#10-32) 
- **`get_option_delivery_price()`** - Option delivery prices [34](#10-33) 

### Trade Management Methods
The `TradeHTTP` class handles order operations:

- **`cancel_all_orders()`** - Cancel all open orders by category [35](#10-34) 
- **`get_order_history()`** - Query historical order data [36](#10-35) 

## HTTP Request Infrastructure

All HTTP methods use the unified request infrastructure provided by `_V5HTTPManager` [37](#10-36) . The `_submit_request()` method handles authentication, error handling, and retry logic for all API calls.

The system supports both HMAC and RSA authentication methods [38](#10-37)  and includes comprehensive error handling with configurable retry codes [39](#10-38) .

**Notes**

The HTTP methods are organized by functional domain (Account, Position, Trade, Market, etc.) but unified through multiple inheritance in the main `HTTP` class. All methods follow consistent patterns for parameter handling, authentication, and error management. The architecture supports both Unified Trading Accounts (UTA) and traditional account types across different product categories (spot, linear, inverse, option).

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [HTTP Communication Infrastructure (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#3.3)
You're asking me to create a trading bot template using the Bybit Python SDK (`pybit`) that you can apply trading strategies to. Based on the codebase context, I can see this involves the unified trading interface from [1](#11-0) , which provides comprehensive HTTP and WebSocket functionality for trading operations.

## Trading Bot Template

Here's a fully functional trading bot template that leverages the pybit SDK's capabilities:

```python
import logging
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable
from pybit.unified_trading import HTTP, WebSocket, WebSocketTrading

class TradingBot:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        category: str = "linear",
        symbol: str = "BTCUSDT"
    ):
        """
        Initialize the trading bot with Bybit API credentials and configuration.
        
        Args:
            api_key: Your Bybit API key
            api_secret: Your Bybit API secret
            testnet: Whether to use testnet (default: True for safety)
            category: Product category (linear, spot, inverse, option)
            symbol: Trading symbol
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category
        self.symbol = symbol
        
        # Initialize HTTP client for REST API operations
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            log_requests=True
        )
        
        # Initialize WebSocket for real-time data
        self.ws_public = None
        self.ws_private = None
        self.ws_trading = None
        
        # Bot state
        self.is_running = False
        self.positions = {}
        self.orders = {}
        self.market_data = {}
        
        # Strategy configuration
        self.strategy_func: Optional[Callable] = None
        self.risk_params = {
            'max_position_size': 0.1,  # Maximum position size
            'stop_loss_pct': 0.02,     # 2% stop loss
            'take_profit_pct': 0.04,   # 4% take profit
            'max_leverage': 10
        }
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

    def initialize_websockets(self):
        """Initialize WebSocket connections for real-time data and trading."""
        try:
            # Public WebSocket for market data
            self.ws_public = WebSocket(
                channel_type="linear",
                testnet=self.testnet
            )
            
            # Private WebSocket for account updates
            self.ws_private = WebSocket(
                channel_type="private",
                testnet=self.testnet,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            # WebSocket Trading for order operations
            self.ws_trading = WebSocketTrading(
                testnet=self.testnet,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            # Subscribe to market data streams
            self.ws_public.kline_stream(
                interval=1,
                symbol=self.symbol,
                callback=self._handle_kline_data
            )
            
            self.ws_public.ticker_stream(
                symbol=self.symbol,
                callback=self._handle_ticker_data
            )
            
            # Subscribe to private streams
            self.ws_private.position_stream(self._handle_position_update)
            self.ws_private.order_stream(self._handle_order_update)
            self.ws_private.execution_stream(self._handle_execution_update)
            
            self.logger.info("WebSocket connections initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize WebSockets: {e}")
            raise

    def _handle_kline_data(self, message):
        """Handle incoming kline/candlestick data."""
        try:
            if 'data' in message:
                for kline in message['data']:
                    self.market_data['kline'] = {
                        'symbol': kline.get('symbol'),
                        'open': float(kline.get('open', 0)),
                        'high': float(kline.get('high', 0)),
                        'low': float(kline.get('low', 0)),
                        'close': float(kline.get('close', 0)),
                        'volume': float(kline.get('volume', 0)),
                        'timestamp': kline.get('start')
                    }
                    
                    # Trigger strategy evaluation
                    if self.strategy_func and self.is_running:
                        threading.Thread(
                            target=self._execute_strategy,
                            daemon=True
                        ).start()
                        
        except Exception as e:
            self.logger.error(f"Error handling kline data: {e}")

    def _handle_ticker_data(self, message):
        """Handle incoming ticker data."""
        try:
            if 'data' in message:
                ticker = message['data']
                self.market_data['ticker'] = {
                    'symbol': ticker.get('symbol'),
                    'last_price': float(ticker.get('lastPrice', 0)),
                    'bid_price': float(ticker.get('bid1Price', 0)),
                    'ask_price': float(ticker.get('ask1Price', 0)),
                    'volume_24h': float(ticker.get('volume24h', 0)),
                    'price_change_24h': float(ticker.get('price24hPcnt', 0))
                }
                
        except Exception as e:
            self.logger.error(f"Error handling ticker data: {e}")

    def _handle_position_update(self, message):
        """Handle position updates."""
        try:
            if 'data' in message:
                for position in message['data']:
                    symbol = position.get('symbol')
                    self.positions[symbol] = {
                        'size': float(position.get('size', 0)),
                        'side': position.get('side'),
                        'avg_price': float(position.get('avgPrice', 0)),
                        'unrealized_pnl': float(position.get('unrealisedPnl', 0)),
                        'leverage': float(position.get('leverage', 0))
                    }
                    
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")

    def _handle_order_update(self, message):
        """Handle order updates."""
        try:
            if 'data' in message:
                for order in message['data']:
                    order_id = order.get('orderId')
                    self.orders[order_id] = {
                        'symbol': order.get('symbol'),
                        'side': order.get('side'),
                        'order_type': order.get('orderType'),
                        'qty': float(order.get('qty', 0)),
                        'price': float(order.get('price', 0)),
                        'order_status': order.get('orderStatus'),
                        'cum_exec_qty': float(order.get('cumExecQty', 0))
                    }
                    
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")

    def _handle_execution_update(self, message):
        """Handle execution updates."""
        try:
            if 'data' in message:
                for execution in message['data']:
                    self.logger.info(f"Execution: {execution}")
                    
        except Exception as e:
            self.logger.error(f"Error handling execution update: {e}")

    def get_account_balance(self) -> Dict:
        """Get current account balance."""
        try:
            response = self.session.get_wallet_balance(
                accountType="UNIFIED" if self.category in ["linear", "option"] else "CONTRACT"
            )
            return response.get('result', {})
        except Exception as e:
            self.logger.error(f"Error getting account balance: {e}")
            return {}

    def get_current_position(self, symbol: str = None) -> Dict:
        """Get current position for symbol."""
        symbol = symbol or self.symbol
        try:
            response = self.session.get_positions(
                category=self.category,
                symbol=symbol
            )
            positions = response.get('result', {}).get('list', [])
            return positions[0] if positions else {}
        except Exception as e:
            self.logger.error(f"Error getting position: {e}")
            return {}

    def place_market_order(
        self,
        side: str,
        qty: str,
        symbol: str = None,
        reduce_only: bool = False
    ) -> Dict:
        """Place a market order."""
        symbol = symbol or self.symbol
        try:
            response = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=qty,
                reduceOnly=reduce_only
            )
            self.logger.info(f"Market order placed: {side} {qty} {symbol}")
            return response
        except Exception as e:
            self.logger.error(f"Error placing market order: {e}")
            return {}

    def place_limit_order(
        self,
        side: str,
        qty: str,
        price: str,
        symbol: str = None,
        time_in_force: str = "GTC"
    ) -> Dict:
        """Place a limit order."""
        symbol = symbol or self.symbol
        try:
            response = self.session.place_order(
                category=self.category,
                symbol=symbol,
                side=side,
                orderType="Limit",
                qty=qty,
                price=price,
                timeInForce=time_in_force
            )
            self.logger.info(f"Limit order placed: {side} {qty} {symbol} @ {price}")
            return response
        except Exception as e:
            self.logger.error(f"Error placing limit order: {e}")
            return {}

    def set_stop_loss_take_profit(
        self,
        symbol: str = None,
        stop_loss: str = None,
        take_profit: str = None
    ) -> Dict:
        """Set stop loss and take profit for existing position."""
        symbol = symbol or self.symbol
        try:
            response = self.session.set_trading_stop(
                category=self.category,
                symbol=symbol,
                stopLoss=stop_loss,
                takeProfit=take_profit
            )
            self.logger.info(f"Stop loss/take profit set for {symbol}")
            return response
        except Exception as e:
            self.logger.error(f"Error setting stop loss/take profit: {e}")
            return {}

    def cancel_all_orders(self, symbol: str = None) -> Dict:
        """Cancel all open orders for symbol."""
        symbol = symbol or self.symbol
        try:
            response = self.session.cancel_all_orders(
                category=self.category,
                symbol=symbol
            )
            self.logger.info(f"All orders cancelled for {symbol}")
            return response
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {e}")
            return {}

    def set_leverage(self, leverage: str, symbol: str = None) -> Dict:
        """Set leverage for symbol."""
        symbol = symbol or self.symbol
        try:
            response = self.session.set_leverage(
                category=self.category,
                symbol=symbol,
                buyLeverage=leverage,
                sellLeverage=leverage
            )
            self.logger.info(f"Leverage set to {leverage}x for {symbol}")
            return response
        except Exception as e:
            self.logger.error(f"Error setting leverage: {e}")
            return {}

    def set_strategy(self, strategy_function: Callable):
        """Set the trading strategy function."""
        self.strategy_func = strategy_function
        self.logger.info("Trading strategy set")

    def _execute_strategy(self):
        """Execute the trading strategy."""
        try:
            if self.strategy_func:
                # Pass bot instance to strategy function
                self.strategy_func(self)
        except Exception as e:
            self.logger.error(f"Error executing strategy: {e}")

    def start(self):
        """Start the trading bot."""
        try:
            self.logger.info("Starting trading bot...")
            
            # Initialize WebSocket connections
            self.initialize_websockets()
            
            # Set initial leverage
            self.set_leverage(str(self.risk_params['max_leverage']))
            
            # Start the bot
            self.is_running = True
            self.logger.info("Trading bot started successfully")
            
            # Keep the bot running
            while self.is_running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            self.stop()
        except Exception as e:
            self.logger.error(f"Error starting bot: {e}")
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        self.logger.info("Stopping trading bot...")
        self.is_running = False
        
        # Close WebSocket connections
        if self.ws_public:
            self.ws_public.exit()
        if self.ws_private:
            self.ws_private.exit()
        if self.ws_trading:
            self.ws_trading.exit()
            
        self.logger.info("Trading bot stopped")

# Example Strategy Implementation
def simple_momentum_strategy(bot: TradingBot):
    """
    Example momentum strategy that buys on upward price movement
    and sells on downward movement.
    """
    try:
        # Get current market data
        if 'ticker' not in bot.market_data:
            return
            
        ticker = bot.market_data['ticker']
        current_price = ticker['last_price']
        price_change_24h = ticker['price_change_24h']
        
        # Get current position
        position = bot.get_current_position()
        current_size = float(position.get('size', 0))
        
        # Strategy logic
        if price_change_24h > 0.02 and current_size == 0:  # 2% positive change, no position
            # Enter long position
            qty = str(bot.risk_params['max_position_size'])
            bot.place_market_order("Buy", qty)
            
            # Set stop loss and take profit
            stop_loss_price = str(current_price * (1 - bot.risk_params['stop_loss_pct']))
            take_profit_price = str(current_price * (1 + bot.risk_params['take_profit_pct']))
            bot.set_stop_loss_take_profit(
                stop_loss=stop_loss_price,
                take_profit=take_profit_price
            )
            
        elif price_change_24h < -0.02 and current_size > 0:  # 2% negative change, have position
            # Close position
            bot.place_market_order("Sell", str(current_size), reduce_only=True)
            
    except Exception as e:
        bot.logger.error(f"Error in momentum strategy: {e}")

# Usage Example
if __name__ == "__

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
