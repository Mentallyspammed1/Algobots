# Bybit API Functions and WebSockets Complete Guide

Bybit provides comprehensive programmatic interfaces through REST APIs, WebSocket connections, and WebSocket APIs for automated trading, data retrieval, and real-time market monitoring. The platform offers three main API interfaces: REST API for standard HTTP requests, WebSocket API for real-time data streaming, and a Testnet environment for risk-free testing.

## REST API Functions (V5)

### Market Data Endpoints

**Public endpoints** (no authentication required):
- `getKline()` - Historical candlestick data
- `getMarkPriceKline()` - Mark price candlestick data
- `getIndexPriceKline()` - Index price candlestick data
- `getPremiumIndexPriceKline()` - Premium index price candlestick data
- `getOrderbook()` - Current order book depth
- `getTickers()` - Latest price snapshots and 24hr volume
- `getFundingRateHistory()` - Funding rate history
- `getPublicTradingHistory()` - Recent trade execution data
- `getOpenInterest()` - Open interest data
- `getHistoricalVolatility()` - Historical volatility data
- `getInsurance()` - Insurance fund data
- `getRiskLimit()` - Risk limit tiers
- `getDeliveryPrice()` - Delivery price for futures
- `getLongShortRatio()` - Long/short account ratio

### Trading Endpoints

**Private endpoints** (authentication required):
- `submitOrder()` - Place new orders
- `amendOrder()` - Modify existing orders
- `cancelOrder()` - Cancel active orders
- `getActiveOrders()` - View active orders
- `cancelAllOrders()` - Cancel all orders
- `getHistoricOrders()` - Query historical orders
- `getExecutionList()` - Get execution history
- `batchSubmitOrders()` - Batch order creation
- `batchAmendOrders()` - Batch order modification
- `batchCancelOrders()` - Batch order cancellation
- `preCheckOrder()` - Pre-check order feasibility

### Position Management

- `getPositionInfo()` - View all open positions
- `setLeverage()` - Change position leverage
- `switchIsolatedMargin()` - Switch margin mode
- `setTPSLMode()` - Set take profit/stop loss mode
- `switchPositionMode()` - Switch position mode
- `setRiskLimit()` - Set risk limit
- `setTradingStop()` - Set TP/SL levels
- `setAutoAddMargin()` - Configure auto-add margin
- `addOrReduceMargin()` - Adjust position margin
- `getClosedPnL()` - Get closed P&L history
- `movePosition()` - Move positions between accounts

### Account & Wallet

- `getWalletBalance()` - Check wallet balance
- `getFeeRate()` - View trading fee rates
- `getAccountInfo()` - Get account information
- `getTransactionLog()` - Transaction history
- `getBorrowHistory()` - Borrowing history
- `repayLiability()` - Quick repayment
- `setCollateralCoin()` - Set collateral preferences
- `setMarginMode()` - Set margin mode
- `setMMP()` - Market maker protection settings

### Asset Management

- `getCoinInfo()` - Coin specifications
- `getAllCoinsBalance()` - All coins balance
- `createInternalTransfer()` - Internal transfers
- `createUniversalTransfer()` - Universal transfers
- `getDepositRecords()` - Deposit history
- `getWithdrawalRecords()` - Withdrawal history
- `submitWithdrawal()` - Create withdrawal
- `cancelWithdrawal()` - Cancel withdrawal

### Spot & Margin Trading

- `getSpotBorrowCheck()` - Check borrowing eligibility
- `toggleSpotMarginTrade()` - Enable/disable margin trading
- `setSpotMarginLeverage()` - Set spot margin leverage
- `getSpotMarginState()` - Get margin trading status
- `spotMarginBorrow()` - Borrow funds
- `spotMarginRepay()` - Repay borrowed funds

### Advanced Features

**Spread Trading**:
- `getSpreadInstrumentsInfo()` - Spread instrument info
- `submitSpreadOrder()` - Create spread orders
- `amendSpreadOrder()` - Modify spread orders
- `cancelSpreadOrder()` - Cancel spread orders

**Institutional & Crypto Loans**:
- `getInstitutionalLendingProductInfo()` - Loan products
- `borrowCryptoLoan()` - Borrow crypto
- `repayCryptoLoan()` - Repay loans
- `adjustCollateralAmount()` - Adjust collateral

## WebSocket API Functions

The WebSocket API provides faster interactions through persistent connections. Available functions include:

- `submitNewOrder()` - Create orders via WebSocket
- `amendOrder()` - Modify orders via WebSocket
- `cancelOrder()` - Cancel orders via WebSocket
- `batchSubmitOrders()` - Batch create orders
- `batchAmendOrder()` - Batch modify orders
- `batchCancelOrder()` - Batch cancel orders

## WebSocket Topics (Real-time Streams)

### Public Topics

**Market Data**:
- **Orderbook**: Real-time order book updates
- **Trade**: Real-time trade executions
- **Ticker**: 24hr rolling ticker data
- **Kline**: Candlestick/chart data
- **Liquidation**: Liquidation orders (full feed available)
- **LT Kline**: Leveraged token candlesticks
- **LT Ticker**: Leveraged token tickers
- **LT Nav**: Leveraged token NAV updates

### Private Topics

**Account Updates**:
- **Position**: Real-time position updates
- **Execution**: Trade execution notifications
- **Order**: Order status updates
- **Wallet**: Balance changes
- **Greek**: Options Greeks updates
- **DCP**: Dynamic close position info

### WebSocket Endpoints

**Public Streams**:
- Linear/Futures: `wss://stream.bybit.com/v5/public/linear`
- Spot: `wss://stream.bybit.com/v5/public/spot`
- Option: `wss://stream.bybit.com/v5/public/option`

**Private Streams**:
- All products: `wss://stream.bybit.com/v5/private`

**Testnet**:
- Public: `wss://stream-testnet.bybit.com/v5/public/{product}`
- Private: `wss://stream-testnet.bybit.com/v5/private`



### Authentication & Connection

WebSocket connections require authentication for private topics using API key and HMAC SHA256 signatures. The system supports:
- Heartbeat/ping-pong mechanism (recommended every 20 seconds)
- Automatic reconnection handling
- Timestamp synchronization (within 5 seconds)
- Rate limits: 120 requests/minute for market data, 60 requests/minute for orders

### Topic Subscription Types

Bybit offers two subscription patterns:
- **All-In-One Topics**: Subscribe to updates across all product categories (spot, linear, inverse, option)
- **Categorized Topics**: Subscribe to specific product category updates only

Example categorized topics include `execution.spot`, `execution.linear`, `execution.inverse`, and `execution.option`.

## SDK Support

Multiple SDKs are available for easy integration:
- **Node.js/JavaScript/TypeScript**: Full support with promise-driven interface
- **Python**: pybit library with comprehensive coverage
- **.NET/C#**: Bybit.Net library for V5 API
- **Go**: Native Go client libraries
- **Java**: Complete API integration support

The Node.js SDK notably provides exclusive benefits including higher API rate limits (400 requests/second) and lower minimum order values ($1 instead of $5).
I'll search for comprehensive documentation on all bybit-api functions and websockets.Let me search for more specific documentation on bybit-api functions and websocket methods:Based on my research, here's a comprehensive guide to all bybit-api functions and websockets:

# Complete Bybit-API Functions & WebSockets Guide

## Installation
```bash
npm install bybit-api
```

## REST API Client (RestClientV5)

### Account Management
- `setSpotMarginMode()` - Turn spot margin trade on/off in your NORMAL account
- `setSpotMarginModeV5()` - Turn spot margin trade on/off in your UTA account
- `setMarginMode()` - Select cross margin mode or isolated margin mode (0: cross, 1: isolated)
- `switchPositionMode()` - Switch position mode for USDT perpetual and Inverse futures
- `getApiKeyInfo()` - Get the information of the api key

### Market Data
- `getKline()` - Query the kline data
- `getTickers()` - Get ticker information
- `getPublicTradingHistory()` - Query recent public trading data
- `getLeveragedTokenInfo()` - Get leverage token market information
- `getInsurancePool()` - Query Bybit insurance pool data (updated every 24 hours)

### Trading
- `getActiveOrders()` - Query unfilled or partially filled orders in real-time
- `getHistoricOrders()` - Query older order records
- `submitOrder()` - Place an order
- `modifyOrder()` - Modify an order
- `cancelOrder()` - Cancel an order
- `cancelAllOrders()` - Cancel all orders
- `batchSubmitOrders()` - Place multiple orders
- `batchCancelOrders()` - Cancel multiple orders
- `batchAmendOrders()` - Amend multiple orders

### Wallet & Asset Management
- `getAllCoinsBalance()` - Query all coin balances of all account types
- `getBorrowableCoinInfo()` - Query qty and amount of borrowable coins in spot account
- `getDepositRecords()` - Get deposit records
- `getSubAccountDepositRecords()` - Query subaccount's deposit records
- `getInternalDepositRecords()` - Get internal deposit records across Bybit
- `getInternalTransferRecords()` - Query internal transfer records between account types
- `getAllowedDepositCoinInfo()` - Query allowed deposit coin information
- `getAssetInfo()` - Query asset information (SPOT only)
- `getBorrowHistory()` - Get interest records
- `getClosedPnl()` - Query user's closed profit and loss records

### Positions
- `getPositionInfo()` - Get position information
- `setTradingStop()` - Set trading stop (TP/SL)
- `setLeverage()` - Set leverage
- `switchTpslMode()` - Switch TP/SL mode
- `confirmNewRiskLimit()` - Confirm new risk limit
- `addOrReduceMargin()` - Add or reduce margin

### Server Time
- `getServerTime()` - Query & resolve server time
- `fetchServerTime()` - Time synchronization with latency calculation

## WebSocket Client

### Basic Setup
```javascript
const { WebsocketClient } = require('bybit-api');

const ws = new WebsocketClient({
  key: API_KEY,
  secret: API_SECRET,
  market: 'v5', // 'v5' for unified trading
  testnet: false, // true for testnet
});
```

### WebSocket Streams

#### Public Streams (No Authentication Required)
- **Spot**: `wss://stream.bybit.com/v5/public/spot`
- **USDT/USDC Perpetual**: `wss://stream.bybit.com/v5/public/linear`
- **Inverse Contract**: `wss://stream.bybit.com/v5/public/inverse`
- **Options**: `wss://stream.bybit.com/v5/public/option`

#### Private Streams (Authentication Required)
- Order updates
- Position updates
- Execution updates
- Wallet updates

### WebSocket Events & Methods

#### Connection Management
- `on('open')` - Connection established
- `on('close')` - Connection closed
- `on('error')` - Error occurred
- `on('update')` - Data update received
- `on('response')` - Response to subscription

#### Subscription Methods
- `subscribe(topics)` - Subscribe to one or multiple topics
- `unsubscribe(topics)` - Unsubscribe from topics
- `close()` - Close the connection

### Available Topics

#### Public Topics
- `orderbook.{depth}.{symbol}` - Order book (1, 50, 200, 500)
- `publicTrade.{symbol}` - Recent trades
- `tickers.{symbol}` - 24hr ticker
- `kline.{interval}.{symbol}` - Kline/candlestick data
- `liquidation.{symbol}` - Liquidation orders

#### Private Topics
- `position` - Position updates
- `execution` - Order execution updates
- `order` - Order updates
- `wallet` - Wallet balance updates
- `greeks` - Options greeks updates

### WebSocket API Client

The WebsocketAPIClient allows you to use WebSocket like a REST API:

```javascript
const { WebsocketAPIClient } = require('bybit-api');

const wsAPI = new WebsocketAPIClient({
  key: API_KEY,
  secret: API_SECRET,
});

// Use it like REST API with await
const ticker = await wsAPI.getTicker({ symbol: 'BTCUSDT' });
```

### Advanced Features

#### Authentication
```javascript
// Authentication happens automatically, but manual auth looks like:
ws.send(json.dumps({
  "op": "auth",
  "args": [api_key, expires, signature]
}))
```

#### Heartbeat & Connection Management
- Send ping heartbeat every 20 seconds to maintain connection
- Automatic reconnection on disconnect
- Configurable connection timeout (30s to 600s)

#### Rate Limits
- SDK automatically gets 400 requests/second (higher than VIP tier)
- WebSocket requests don't count against rate limits

#### Order Management via WebSocket
```javascript
// Place order via WebSocket
ws.sendWSAPIRequest('order.create', {
  category: 'linear',
  symbol: 'BTCUSDT',
  side: 'Buy',
  orderType: 'Limit',
  qty: '0.001',
  price: '30000'
});
```

### Configuration Options
```javascript
const client = new RestClientV5({
  key: API_KEY,
  secret: API_SECRET,
  testnet: false,
  recv_window: 5000,
  enable_time_sync: true,
  keepAlive: true,
  keepAliveMsecs: 1000,
  apiRegion: 'default', // 'default' | 'bytick' | 'NL' | 'HK' | 'TK'
  parseAPIRateLimits: true,
  customSignMessageFn: customFunction // Optional custom signing
});
```

### Example: Complete Trading Bot Structure

```javascript
const { RestClientV5, WebsocketClient } = require('bybit-api');

// Initialize clients
const rest = new RestClientV5({
  key: API_KEY,
  secret: API_SECRET
});

const ws = new WebsocketClient({
  key: API_KEY,
  secret: API_SECRET,
  market: 'v5'
});

// Subscribe to market data
ws.subscribe(['orderbook.50.BTCUSDT', 'publicTrade.BTCUSDT']);

// Handle updates
ws.on('update', (data) => {
  console.log('Update:', data);
});

// Place order
async function placeOrder() {
  const order = await rest.submitOrder({
    category: 'linear',
    symbol: 'BTCUSDT',
    side: 'Buy',
    orderType: 'Limit',
    qty: '0.001',
    price: '30000'
  });
  console.log('Order placed:', order);
}

// Get positions
async function getPositions() {
  const positions = await rest.getPositionInfo({
    category: 'linear',
    settleCoin: 'USDT'
  });
  console.log('Positions:', positions);
}
```

### Notes
- As of January 2025, demo trading environment doesn't support WebSocket API
- WebSocket API accepts same parameters as REST API endpoints
- Regional users should use specific domains:
  - Turkey: `api.bybit-tr.com` and `stream.bybit-tr.com`
  - Kazakhstan: `api.bybit.kz` and `stream.bybit.kz`

This comprehensive guide covers all the major functions and WebSocket capabilities of the bybit-api package. The library is actively maintained and provides complete integration with Bybit's V5 unified API.I'll search for compatible technical indicator libraries that work well with bybit-api on Android/Termux.Let me search for more specific examples of technical indicators working with bybit-api:Based on my research, here's a comprehensive guide for compatible indicator libraries and setup with bybit-api on Android/Termux:

# Compatible Technical Indicator Libraries for Bybit Trading Bot on Android/Termux

## 1. **technicalindicators** (RECOMMENDED)
The `technicalindicators` npm package provides a pure JavaScript implementation that doesn't require native dependencies, making it perfect for Termux.

### Installation:
```bash
npm install technicalindicators
```

### Features:
- Over 40+ indicators (SMA, EMA, RSI, MACD, Bollinger Bands, etc.)
- Pure JavaScript - no native dependencies
- Works perfectly on Android/Termux
- Active maintenance

### Example Setup with Bybit:
```javascript
const { RestClientV5, WebsocketClient } = require('bybit-api');
const { SMA, EMA, RSI, MACD, BollingerBands } = require('technicalindicators');

// Initialize Bybit clients
const client = new RestClientV5({
    key: 'YOUR_API_KEY',
    secret: 'YOUR_API_SECRET',
    testnet: true
});

const ws = new WebsocketClient({
    key: 'YOUR_API_KEY',
    secret: 'YOUR_API_SECRET',
    market: 'v5'
});

// Store candle data
let candleData = {
    open: [],
    high: [],
    low: [],
    close: [],
    volume: []
};

// Calculate indicators
function calculateIndicators() {
    const closePrices = candleData.close;
    
    // Simple Moving Average
    const sma20 = SMA.calculate({
        period: 20,
        values: closePrices
    });
    
    // RSI
    const rsi = RSI.calculate({
        period: 14,
        values: closePrices
    });
    
    // MACD
    const macd = MACD.calculate({
        values: closePrices,
        fastPeriod: 12,
        slowPeriod: 26,
        signalPeriod: 9,
        SimpleMAOscillator: false,
        SimpleMASignal: false
    });
    
    return { sma20, rsi, macd };
}
```

## 2. **tulind** (Alternative - May Have Compatibility Issues)
Tulip Indicators provides over 100 technical analysis functions, but it's written in C99 and requires compilation, which might be problematic on Termux.

### Installation Attempt:
```bash
npm install tulind
```

**Note**: This may fail on Termux due to native compilation requirements.

## 3. **Lightweight Custom Implementation**
For maximum compatibility, create your own lightweight indicators:

```javascript
// Custom lightweight indicators
class SimpleIndicators {
    static SMA(values, period) {
        const result = [];
        for (let i = period - 1; i < values.length; i++) {
            const sum = values.slice(i - period + 1, i + 1)
                .reduce((a, b) => a + b, 0);
            result.push(sum / period);
        }
        return result;
    }
    
    static EMA(values, period) {
        const k = 2 / (period + 1);
        const ema = [values[0]];
        
        for (let i = 1; i < values.length; i++) {
            ema.push(values[i] * k + ema[i - 1] * (1 - k));
        }
        return ema;
    }
    
    static RSI(values, period = 14) {
        const gains = [];
        const losses = [];
        
        for (let i = 1; i < values.length; i++) {
            const diff = values[i] - values[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? -diff : 0);
        }
        
        const avgGain = this.SMA(gains, period);
        const avgLoss = this.SMA(losses, period);
        
        return avgGain.map((gain, i) => {
            if (avgLoss[i] === 0) return 100;
            const rs = gain / avgLoss[i];
            return 100 - (100 / (1 + rs));
        });
    }
}
```

## Complete Trading Bot Example

Here's a complete example integrating bybit-api with technicalindicators:

```javascript
const { RestClientV5, WebsocketClient } = require('bybit-api');
const { RSI, MACD, BollingerBands, EMA } = require('technicalindicators');

class BybitTradingBot {
    constructor(apiKey, apiSecret, testnet = true) {
        this.client = new RestClientV5({
            key: apiKey,
            secret: apiSecret,
            testnet: testnet
        });
        
        this.ws = new WebsocketClient({
            key: apiKey,
            secret: apiSecret,
            market: 'v5',
            testnet: testnet
        });
        
        this.candles = [];
        this.maxCandles = 500;
        this.symbol = 'BTCUSDT';
        this.interval = '5'; // 5 minute candles
    }
    
    async initialize() {
        // Get historical candles
        const klineData = await this.client.getKline({
            category: 'linear',
            symbol: this.symbol,
            interval: this.interval,
            limit: 200
        });
        
        if (klineData.retCode === 0) {
            this.candles = klineData.result.list.map(candle => ({
                time: parseInt(candle[0]),
                open: parseFloat(candle[1]),
                high: parseFloat(candle[2]),
                low: parseFloat(candle[3]),
                close: parseFloat(candle[4]),
                volume: parseFloat(candle[5])
            })).reverse();
        }
        
        // Subscribe to real-time kline updates
        this.ws.subscribe([`kline.${this.interval}.${this.symbol}`]);
        
        this.ws.on('update', (data) => {
            if (data.topic === `kline.${this.interval}.${this.symbol}`) {
                this.updateCandles(data.data);
                this.analyzeAndTrade();
            }
        });
        
        this.ws.on('open', () => {
            console.log('WebSocket connected');
        });
        
        this.ws.on('error', (err) => {
            console.error('WebSocket error:', err);
        });
    }
    
    updateCandles(klineData) {
        const candle = {
            time: klineData[0].start,
            open: parseFloat(klineData[0].open),
            high: parseFloat(klineData[0].high),
            low: parseFloat(klineData[0].low),
            close: parseFloat(klineData[0].close),
            volume: parseFloat(klineData[0].volume)
        };
        
        // Update or add candle
        const existingIndex = this.candles.findIndex(c => c.time === candle.time);
        if (existingIndex >= 0) {
            this.candles[existingIndex] = candle;
        } else {
            this.candles.push(candle);
            if (this.candles.length > this.maxCandles) {
                this.candles.shift();
            }
        }
    }
    
    calculateIndicators() {
        const closePrices = this.candles.map(c => c.close);
        const highPrices = this.candles.map(c => c.high);
        const lowPrices = this.candles.map(c => c.low);
        
        // RSI
        const rsiValues = RSI.calculate({
            values: closePrices,
            period: 14
        });
        
        // MACD
        const macdValues = MACD.calculate({
            values: closePrices,
            fastPeriod: 12,
            slowPeriod: 26,
            signalPeriod: 9,
            SimpleMAOscillator: false,
            SimpleMASignal: false
        });
        
        // Bollinger Bands
        const bbValues = BollingerBands.calculate({
            period: 20,
            values: closePrices,
            stdDev: 2
        });
        
        // EMA
        const ema50 = EMA.calculate({
            period: 50,
            values: closePrices
        });
        
        return {
            rsi: rsiValues[rsiValues.length - 1],
            macd: macdValues[macdValues.length - 1],
            bb: bbValues[bbValues.length - 1],
            ema50: ema50[ema50.length - 1],
            currentPrice: closePrices[closePrices.length - 1]
        };
    }
    
    async analyzeAndTrade() {
        if (this.candles.length < 200) {
            console.log('Not enough data yet...');
            return;
        }
        
        const indicators = this.calculateIndicators();
        
        // Simple trading logic
        if (indicators.rsi < 30 && 
            indicators.macd && indicators.macd.MACD > indicators.macd.signal &&
            indicators.currentPrice < indicators.bb.lower) {
            console.log('BUY Signal detected!');
            await this.placeOrder('Buy', indicators.currentPrice);
        } else if (indicators.rsi > 70 && 
                   indicators.macd && indicators.macd.MACD < indicators.macd.signal &&
                   indicators.currentPrice > indicators.bb.upper) {
            console.log('SELL Signal detected!');
            await this.placeOrder('Sell', indicators.currentPrice);
        }
    }
    
    async placeOrder(side, price) {
        try {
            const orderResult = await this.client.submitOrder({
                category: 'linear',
                symbol: this.symbol,
                side: side,
                orderType: 'Limit',
                qty: '0.001',
                price: price.toFixed(2),
                timeInForce: 'GTC'
            });
            
            console.log('Order placed:', orderResult);
        } catch (error) {
            console.error('Order error:', error);
        }
    }
    
    async getAccountInfo() {
        const balance = await this.client.getWalletBalance({
            accountType: 'UNIFIED'
        });
        console.log('Account balance:', balance);
    }
}

// Usage
const bot = new BybitTradingBot('YOUR_API_KEY', 'YOUR_API_SECRET', true);
bot.initialize().then(() => {
    console.log('Bot initialized and running...');
});
```

## Installation Steps on Termux

1. **Update Termux packages:**
```bash
pkg update && pkg upgrade
```

2. **Install Node.js:**
```bash
pkg install nodejs
```

3. **Create project directory:**
```bash
mkdir bybit-trading-bot
cd bybit-trading-bot
```

4. **Initialize npm project:**
```bash
npm init -y
```

5. **Install dependencies:**
```bash
npm install bybit-api technicalindicators
```

6. **Create your bot file:**
```bash
nano trading-bot.js
```

7. **Run the bot:**
```bash
node trading-bot.js
```

## Key Advantages of This Setup

1. **No Native Dependencies**: Both bybit-api and technicalindicators are pure JavaScript
2. **Lightweight**: Minimal resource usage on Android
3. **Full Feature Set**: Access to all Bybit API features and 40+ technical indicators
4. **Real-time Updates**: WebSocket support for live market data
5. **Android Compatible**: Runs perfectly on Termux without compilation issues

## Tips for Android/Termux

- Use `pm2` for process management: `npm install -g pm2`
- Keep Termux running: Acquire wakelock with termux-wake-lock
- Monitor resources: Use `htop` (install with `pkg install htop`)
- Log to files: Implement proper logging for debugging

This setup provides a robust, Android-compatible trading bot framework without the heavy dependencies that cause issues on Termux.
I'll search for compatible technical indicator libraries that work well with bybit-api on your Android/Termux setup.Let me search more specifically for lightweight indicator libraries that work well on Android/Termux:Now let me search for specific examples of integrating these indicators with bybit-api:Based on my comprehensive research, here's a complete guide for compatible indicator libraries and setup with bybit-api for your Android/Termux environment:

# Compatible Indicator Libraries & Bybit-API Setup Guide

## Best Lightweight Indicator Libraries for Android/Termux

### 1. **@ixjb94/indicators** (Recommended for Android)
Fastest Technical Indicators written in TypeScript with Zero Dependencies and No Internal Function Calls:

```bash
npm install @ixjb94/indicators
```

**Advantages:**
- Zero dependencies (perfect for Termux)
- Fastest performance
- 100+ indicators
- Works in Browser, NodeJS, ES6, CommonJS

**Usage:**
```javascript
const { Indicators } = require("@ixjb94/indicators");
const ta = new Indicators();

// Calculate indicators
ta.sma(closePrices, 20).then(result => console.log(result));
ta.rsi(closePrices, 14).then(result => console.log(result));
```

### 2. **technicalindicators** (Pure JavaScript)
Technical Indicators written in javascript - compatible but may have some build issues:

```bash
npm install technicalindicators
```

**Note**: For nodejs version below 10 use 1.x versions of this library

### 3. **trading-signals** (High Performance)
Technical indicators to run technical analysis with JavaScript / TypeScript:

```bash
npm install trading-signals
```

**Features:**
- Two implementations of each indicator: standard (using big.js) and Faster-prefixed version (using common number types)
- All indicators can be updated over time by streaming data

### 4. **tulind/tulipnode** (C-based, May Have Compilation Issues)
Official node.js wrapper for Tulip Indicators providing 100+ technical analysis indicator functions:

```bash
npm install tulind
```

**Warning**: The tulip library sometimes has issues on npm install because of code compiling. Build from source is not supporting all nodejs version. Versions <= 10 are working

## Complete Trading Bot Setup

Here's a complete example integrating bybit-api with lightweight indicators:

```javascript
// trading-bot.js
const { RestClientV5, WebsocketClient } = require('bybit-api');
const { Indicators } = require('@ixjb94/indicators');
const _ = require('lodash');

// Initialize Bybit clients
const rest = new RestClientV5({
    key: 'YOUR_API_KEY',
    secret: 'YOUR_API_SECRET',
    testnet: true, // Use false for mainnet
});

const ws = new WebsocketClient({
    key: 'YOUR_API_KEY',
    secret: 'YOUR_API_SECRET',
    market: 'v5',
    testnet: true,
});

// Initialize indicators
const indicators = new Indicators();

// Simple data structure to replace DataFrame
class TradingData {
    constructor(maxCandles = 500) {
        this.candles = [];
        this.maxCandles = maxCandles;
    }

    addCandle(candle) {
        this.candles.push({
            timestamp: candle.timestamp,
            open: parseFloat(candle.open),
            high: parseFloat(candle.high),
            low: parseFloat(candle.low),
            close: parseFloat(candle.close),
            volume: parseFloat(candle.volume)
        });
        
        if (this.candles.length > this.maxCandles) {
            this.candles.shift();
        }
    }

    getClosePrices() {
        return this.candles.map(c => c.close);
    }

    getHighPrices() {
        return this.candles.map(c => c.high);
    }

    getLowPrices() {
        return this.candles.map(c => c.low);
    }

    getVolumes() {
        return this.candles.map(c => c.volume);
    }

    getLatest() {
        return this.candles[this.candles.length - 1];
    }
}

// Trading strategy class
class TradingStrategy {
    constructor(symbol, interval = '5m') {
        this.symbol = symbol;
        this.interval = interval;
        this.data = new TradingData();
        this.position = null;
    }

    async calculateIndicators() {
        const closes = this.data.getClosePrices();
        const highs = this.data.getHighPrices();
        const lows = this.data.getLowPrices();

        if (closes.length < 50) return null;

        try {
            // Calculate multiple indicators
            const [sma20, sma50, rsi14, macd] = await Promise.all([
                indicators.sma(closes, 20),
                indicators.sma(closes, 50),
                indicators.rsi(closes, 14),
                indicators.macd(closes, 12, 26, 9)
            ]);

            return {
                sma20: sma20[sma20.length - 1],
                sma50: sma50[sma50.length - 1],
                rsi: rsi14[rsi14.length - 1],
                macd: macd.MACD[macd.MACD.length - 1],
                macdSignal: macd.signal[macd.signal.length - 1],
                macdHistogram: macd.histogram[macd.histogram.length - 1]
            };
        } catch (error) {
            console.error('Error calculating indicators:', error);
            return null;
        }
    }

    async generateSignal() {
        const indicators = await this.calculateIndicators();
        if (!indicators) return null;

        const latest = this.data.getLatest();
        
        // Simple trading logic
        const signal = {
            action: 'HOLD',
            price: latest.close,
            indicators: indicators,
            reason: []
        };

        // Buy signals
        if (indicators.rsi < 30 && indicators.sma20 > indicators.sma50) {
            signal.action = 'BUY';
            signal.reason.push('RSI oversold + SMA bullish cross');
        }

        // Sell signals
        if (indicators.rsi > 70 && indicators.sma20 < indicators.sma50) {
            signal.action = 'SELL';
            signal.reason.push('RSI overbought + SMA bearish cross');
        }

        // MACD signal
        if (indicators.macdHistogram > 0 && signal.action === 'HOLD') {
            signal.action = 'BUY';
            signal.reason.push('MACD bullish');
        } else if (indicators.macdHistogram < 0 && signal.action === 'HOLD') {
            signal.action = 'SELL';
            signal.reason.push('MACD bearish');
        }

        return signal;
    }
}

// Main bot class
class TradingBot {
    constructor() {
        this.strategies = new Map();
        this.isRunning = false;
    }

    async initialize(symbols) {
        console.log('Initializing trading bot...');
        
        // Create strategies for each symbol
        for (const symbol of symbols) {
            this.strategies.set(symbol, new TradingStrategy(symbol));
        }

        // Load historical data
        await this.loadHistoricalData();

        // Subscribe to real-time data
        this.subscribeToMarketData();

        console.log('Bot initialized successfully');
    }

    async loadHistoricalData() {
        for (const [symbol, strategy] of this.strategies) {
            try {
                const response = await rest.getKline({
                    category: 'linear',
                    symbol: symbol,
                    interval: strategy.interval,
                    limit: 200
                });

                if (response.retCode === 0) {
                    // Add candles in chronological order
                    response.result.list.reverse().forEach(candle => {
                        strategy.data.addCandle({
                            timestamp: parseInt(candle[0]),
                            open: candle[1],
                            high: candle[2],
                            low: candle[3],
                            close: candle[4],
                            volume: candle[5]
                        });
                    });
                    console.log(`Loaded ${response.result.list.length} candles for ${symbol}`);
                }
            } catch (error) {
                console.error(`Error loading data for ${symbol}:`, error);
            }
        }
    }

    subscribeToMarketData() {
        // Subscribe to kline updates
        const topics = [];
        for (const [symbol, strategy] of this.strategies) {
            topics.push(`kline.${strategy.interval}.${symbol}`);
        }
        
        ws.subscribe(topics);

        // Handle kline updates
        ws.on('update', (data) => {
            if (data.topic && data.topic.startsWith('kline.')) {
                const parts = data.topic.split('.');
                const symbol = parts[2];
                const strategy = this.strategies.get(symbol);
                
                if (strategy && data.data) {
                    data.data.forEach(candle => {
                        if (candle.confirm) { // Only use confirmed candles
                            strategy.data.addCandle({
                                timestamp: candle.timestamp,
                                open: candle.open,
                                high: candle.high,
                                low: candle.low,
                                close: candle.close,
                                volume: candle.volume
                            });
                            
                            // Check for signals on new candle
                            this.checkForSignals(symbol);
                        }
                    });
                }
            }
        });

        ws.on('error', (error) => {
            console.error('WebSocket error:', error);
        });

        ws.on('close', () => {
            console.log('WebSocket connection closed');
        });
    }

    async checkForSignals(symbol) {
        const strategy = this.strategies.get(symbol);
        if (!strategy) return;

        const signal = await strategy.generateSignal();
        if (signal && signal.action !== 'HOLD') {
            console.log(`\n🚨 Signal for ${symbol}:`);
            console.log(`Action: ${signal.action}`);
            console.log(`Price: ${signal.price}`);
            console.log(`Reasons: ${signal.reason.join(', ')}`);
            console.log(`Indicators:`, signal.indicators);
            
            // Execute trade (if enabled)
            if (this.isRunning) {
                await this.executeTrade(symbol, signal);
            }
        }
    }

    async executeTrade(symbol, signal) {
        try {
            // Get account balance
            const balance = await rest.getAllCoinsBalance({
                accountType: 'UNIFIED'
            });

            // Example order placement
            const orderParams = {
                category: 'linear',
                symbol: symbol,
                side: signal.action === 'BUY' ? 'Buy' : 'Sell',
                orderType: 'Market',
                qty: '0.001', // Minimum order size
                timeInForce: 'GTC'
            };

            console.log('Placing order:', orderParams);
            
            // Uncomment to actually place orders
            // const order = await rest.submitOrder(orderParams);
            // console.log('Order placed:', order);
            
        } catch (error) {
            console.error('Error executing trade:', error);
        }
    }

    start() {
        this.isRunning = true;
        console.log('Trading bot started');
    }

    stop() {
        this.isRunning = false;
        ws.close();
        console.log('Trading bot stopped');
    }
}

// Usage
async function main() {
    const bot = new TradingBot();
    
    // Initialize with symbols
    await bot.initialize(['BTCUSDT', 'ETHUSDT']);
    
    // Start the bot (dry run - won't place real orders)
    bot.start();
    
    // Keep the process running
    process.on('SIGINT', () => {
        console.log('\nShutting down...');
        bot.stop();
        process.exit(0);
    });
}

// Run the bot
main().catch(console.error);
```

## Installation Steps for Android/Termux

```bash
# 1. Update Termux packages
pkg update && pkg upgrade

# 2. Install Node.js
pkg install nodejs

# 3. Create project directory
mkdir bybit-trading-bot && cd bybit-trading-bot

# 4. Initialize npm project
npm init -y

# 5. Install dependencies
npm install bybit-api @ixjb94/indicators lodash

# 6. Create the bot file
nano trading-bot.js

# 7. Add your API credentials
# Edit the file and add your Bybit API key and secret

# 8. Run the bot
node trading-bot.js
```

## Configuration Tips

1. **API Keys**: API Key and Secret pair generation through your Bybit account
2. **Rate Limits**: Rate limits are raised to 400 requests per second, higher than the highest VIP tier when using bybit-api SDK
3. **Minimum Order**: Place orders with a notional value as low as $1. Lower than the default minimum notional order value $5

## Alternative: Use Python Version

If you continue to face issues with JavaScript dependencies, the Python version (`gemini_signal_bot.py`) remains the most compatible option for your Android/Termux environment.

This setup provides a complete, lightweight trading bot that works on Android/Termux without the heavy dependencies like TensorFlow or danfo.js.
