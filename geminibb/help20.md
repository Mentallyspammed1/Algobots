Here are 20 improvement code snippets, targeting various aspects of the trading bot, from robustness and precision to better configuration and error handling. Each snippet includes an explanation of the improvement and where it should be applied.

---

### Snippet 1: Configurable API Environment (Testnet/Mainnet)

**File:** `src/config.js`, `src/api/bybit_api.js`, `src/api/bybit_websocket.js`

**Improvement:** Allows easy switching between Bybit's mainnet and testnet environments by adding a `testnet` flag in the configuration. This is crucial for development and testing without risking real capital.

**`src/config.js` update:**

```javascript
// src/config.js
export const config = {
    // ... other configs
    bybit: {
        restUrl: 'https://api.bybit.com',
        wsUrl: 'wss://stream.bybit.com/v5/public/linear',
        privateWsUrl: 'wss://stream.bybit.com/v5/private', // New: Private WS URL
        testnet: false, // NEW: Set to true for testnet
        pricePrecision: 2, // NEW: For BTCUSDT, typically 2 decimal places for price
        qtyPrecision: 3,   // NEW: For BTCUSDT, typically 3 decimal places for quantity
    },
    // ...
};
```

**`src/api/bybit_api.js` constructor update:**

```javascript
// src/api/bybit_api.js
import crypto from 'crypto';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import Decimal from 'decimal.js'; // Ensure Decimal.js is imported

class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        // NEW: Dynamically set base URL based on testnet flag
        this.baseUrl = config.bybit.testnet ? 'https://api-testnet.bybit.com' : config.bybit.restUrl;
        logger.info(`Bybit API configured for ${config.bybit.testnet ? 'TESTNET' : 'MAINNET'}`);
    }
    // ...
}
```

**`src/api/bybit_websocket.js` constructor update:**

```javascript
// src/api/bybit_websocket.js
import WebSocket from 'ws';
import { config } from '../config.js';
import logger from '../utils/logger.js';

class BybitWebSocket {
    constructor(onNewCandleCallback, onPrivateMessageCallback) { // New: onPrivateMessageCallback
        // NEW: Dynamically set public and private WS URLs based on testnet flag
        this.url = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/public/linear' : config.bybit.wsUrl;
        this.privateUrl = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/private' : config.bybit.privateWsUrl;
        this.onNewCandle = onNewCandleCallback;
        this.onPrivateMessage = onPrivateMessageCallback; // NEW: Callback for private messages
        this.ws = null;
        this.privateWs = null; // NEW: Separate WS for private topics
        this.apiKey = process.env.BYBIT_API_KEY; // NEW: Needed for private WS auth
        this.apiSecret = process.env.BYBIT_API_SECRET; // NEW: Needed for private WS auth
        this.pingInterval = null; // NEW: To manage public WS pings
        this.privatePingInterval = null; // NEW: To manage private WS pings
    }
    // ...
}
```

---

### Snippet 2: Robust Signature Generation for All Request Types

**File:** `src/api/bybit_api.js`

**Improvement:** The original `generateSignature` was primarily for POST bodies. This update enhances `sendRequest` to correctly handle signature generation for both GET requests with query parameters and POST requests with JSON bodies, adhering to Bybit's v5 API specifications.

**`src/api/bybit_api.js` update:**

```javascript
// src/api/bybit_api.js
// ...
class BybitAPI {
    // ...
    generateSignature(timestamp, recvWindow, params = '') { // Params can be body string or query string
        const paramStr = timestamp + this.apiKey + recvWindow + params;
        return crypto.createHmac('sha256', this.apiSecret).update(paramStr).digest('hex');
    }

    async sendRequest(path, method, body = null, queryParams = null, isPrivate = true, retries = 3) { // NEW: queryParams, isPrivate, retries
        let attempt = 0;
        while (attempt < retries) {
            try {
                const timestamp = Date.now().toString();
                const recvWindow = '5000'; // Default, can be configurable
                let paramForSignature = '';
                let requestUrl = this.baseUrl + path;

                if (method === 'GET' && queryParams) {
                    const queryString = new URLSearchParams(queryParams).toString();
                    requestUrl += `?${queryString}`;
                    paramForSignature = queryString; // Query string for signature
                } else if (body) {
                    paramForSignature = JSON.stringify(body); // Body for signature
                }

                const headers = {
                    'Content-Type': 'application/json',
                };

                if (isPrivate) { // Only add signature headers for private endpoints
                    Object.assign(headers, {
                        'X-BAPI-API-KEY': this.apiKey,
                        'X-BAPI-TIMESTAMP': timestamp,
                        'X-BAPI-SIGN': this.generateSignature(timestamp, recvWindow, paramForSignature),
                        'X-BAPI-RECV-WINDOW': recvWindow,
                    });
                }

                const response = await fetch(requestUrl, { method, headers, body: body ? paramForSignature : null });
                const data = await response.json();

                if (data.retCode !== 0) {
                    // NEW: Basic retry logic for rate limits or temporary errors
                    if ([10006, 10007, 10016].includes(data.retCode) && attempt < retries - 1) {
                        logger.warn(`Bybit API rate limit hit or temporary error (${data.retCode}): ${data.retMsg}. Retrying in ${2 ** attempt * 1000}ms...`);
                        await new Promise(resolve => setTimeout(resolve, 2 ** attempt * 1000)); // Exponential backoff
                        attempt++;
                        continue; // Retry
                    }
                    throw new Error(`Bybit API Error (${path}): ${data.retMsg} (Code: ${data.retCode})`);
                }
                return data.result;

            } catch (error) {
                logger.exception(`Bybit API request failed (Attempt ${attempt + 1}/${retries}): ${error.message}`);
                // If it's not a recoverable error or max retries reached, re-throw or return null
                if (attempt === retries - 1) return null;
                await new Promise(resolve => setTimeout(resolve, 2 ** attempt * 1000)); // Exponential backoff for other errors too
                attempt++;
            }
        }
        logger.error(`Bybit API call failed after ${retries} attempts: ${path}`);
        return null;
    }

    // Existing methods need to be updated to use the new sendRequest signature
    async getHistoricalMarketData(symbol, interval, limit = 200) {
        // Public endpoint, no signature headers needed. Use direct fetch for simplicity.
        const path = `/v5/market/kline`;
        const queryParams = { category: 'linear', symbol, interval, limit: String(limit) };
        const queryString = new URLSearchParams(queryParams).toString();
        try {
            const response = await fetch(`${this.baseUrl}${path}?${queryString}`);
            const data = await response.json();
            if (data.retCode !== 0) throw new Error(data.retMsg);
            return data.result.list;
        } catch (error) {
            logger.exception(error);
            return null;
        }
    }

    async getAccountBalance(coin = 'USDT') {
        const path = `/v5/account/wallet-balance`;
        const queryParams = { accountType: 'UNIFIED', coin };
        // NEW: Pass queryParams for GET request
        const result = await this.sendRequest(path, 'GET', null, queryParams, true);
        if (result && result.list && result.list.length > 0) {
            return parseFloat(result.list[0].totalEquity);
        }
        return null;
    }

    async placeOrder({ symbol, side, qty, takeProfit, stopLoss }) {
        const path = '/v5/order/create';
        const body = {
            category: 'linear',
            symbol,
            side,
            orderType: 'Market',
            qty: String(qty), // Convert to string as per API
            takeProfit: takeProfit ? String(takeProfit) : undefined,
            stopLoss: stopLoss ? String(stopLoss) : undefined,
        };
        logger.info(`Placing order: ${JSON.stringify(body)}`);
        // NEW: Pass body for POST request
        return this.sendRequest(path, 'POST', body, null, true);
    }

    async getOpenPosition(symbol) {
        const path = `/v5/position/list`;
        const queryParams = { category: 'linear', symbol };
        // NEW: Pass queryParams for GET request
        const result = await this.sendRequest(path, 'GET', null, queryParams, true);
        if (result && result.list && result.list.length > 0) {
            return result.list[0]; // Assuming one position per symbol
        }
        return null;
    }

    // NEW: Helper to get live ticker price, more accurate for order entry
    async getTickerPrice(symbol) {
        const path = `/v5/market/tickers`;
        const queryParams = { category: 'linear', symbol };
        try {
            // Public endpoint, use direct fetch
            const queryString = new URLSearchParams(queryParams).toString();
            const response = await fetch(`${this.baseUrl}${path}?${queryString}`);
            const data = await response.json();
            if (data.retCode !== 0) throw new Error(data.retMsg);
            if (data.result.list && data.result.list.length > 0) {
                return {
                    lastPrice: parseFloat(data.result.list[0].lastPrice),
                    ask1Price: parseFloat(data.result.list[0].ask1Price),
                    bid1Price: parseFloat(data.result.list[0].bid1Price),
                };
            }
            return null;
        } catch (error) {
            logger.exception(`Failed to get ticker price for ${symbol}: ${error.message}`);
            return null;
        }
    }
}
export default BybitAPI;
```

---

### Snippet 3: Use `Decimal.js` for All Monetary/Quantity Calculations

**File:** `src/api/bybit_api.js`, `src/core/trading_logic.js`

**Improvement:** JavaScript's floating-point arithmetic can lead to precision errors in financial calculations. `Decimal.js` ensures all price, quantity, and P&L calculations are accurate.

**`src/api/bybit_api.js` (within `placeOrder`):**

```javascript
// src/api/bybit_api.js
// ... (ensure Decimal is imported)
    async placeOrder({ symbol, side, qty, takeProfit, stopLoss }) {
        // NEW: Use Decimal.js for precise conversion and formatting
        const dQty = new Decimal(qty);
        const dTakeProfit = takeProfit ? new Decimal(takeProfit) : undefined;
        const dStopLoss = stopLoss ? new Decimal(stopLoss) : undefined;

        const path = '/v5/order/create';
        const body = {
            category: 'linear',
            symbol,
            side,
            orderType: 'Market',
            qty: dQty.toFixed(config.bybit.qtyPrecision), // Use config for precision
            takeProfit: dTakeProfit ? dTakeProfit.toFixed(config.bybit.pricePrecision) : undefined,
            stopLoss: dStopLoss ? dStopLoss.toFixed(config.bybit.pricePrecision) : undefined,
        };
        logger.info(`Placing order: ${JSON.stringify(body)}`);
        return this.sendRequest(path, 'POST', body, null, true);
    }
// ...
```

**`src/core/trading_logic.js` (within `calculatePositionSize`, `determineExitPrices`):**

```javascript
// src/core/trading_logic.js
import { RSI, SMA, MACD, ATR } from 'technicalindicators';
import { DataFrame } from 'danfojs-node';
import { config } from '../config.js';
import Decimal from 'decimal.js'; // NEW: Import Decimal.js
import logger from '../utils/logger.js'; // NEW: Import logger for debug

// ... existing calculateIndicators and formatMarketContext

export function calculatePositionSize(balance, currentPrice, stopLossPrice) {
    // NEW: All calculations use Decimal.js for precision
    const dBalance = new Decimal(balance);
    const dCurrentPrice = new Decimal(currentPrice);
    const dStopLossPrice = new Decimal(stopLossPrice);

    const riskAmount = dBalance.times(new Decimal(config.riskManagement.riskPercentage).div(100)); // Use riskManagement config
    const riskPerShare = Decimal.abs(dCurrentPrice.minus(dStopLossPrice));

    if (riskPerShare.isZero()) return new Decimal(0); // Return Decimal(0)
    
    let quantity = riskAmount.div(riskPerShare);
    // Round down to avoid over-ordering, and apply configured precision
    return quantity.toDecimalPlaces(config.bybit.qtyPrecision, Decimal.ROUND_DOWN);
}

// NEW: Pass ATR for dynamic SL
export function determineExitPrices(entryPrice, side, atr) {
    const dEntryPrice = new Decimal(entryPrice);
    let slDistance;

    if (config.riskManagement.useAtrForStopLoss && atr > 0) { // NEW: Use ATR if configured
        slDistance = new Decimal(atr).times(config.riskManagement.atrMultiplier);
        logger.debug(`Using ATR for stop loss: ${atr.toFixed(4)} * ${config.riskManagement.atrMultiplier} = ${slDistance.toFixed(4)}`);
    } else {
        const dSlPercentage = new Decimal(config.riskManagement.stopLossPercentage).div(100);
        slDistance = dEntryPrice.times(dSlPercentage);
        logger.debug(`Using percentage for stop loss: ${config.riskManagement.stopLossPercentage}% = ${slDistance.toFixed(4)}`);
    }

    const tpDistance = slDistance.times(config.riskManagement.riskToRewardRatio);

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = dEntryPrice.minus(slDistance);
        takeProfit = dEntryPrice.plus(tpDistance);
    } else { // Sell
        stopLoss = dEntryPrice.plus(slDistance);
        takeProfit = dEntryPrice.minus(tpDistance);
    }
    
    // NEW: Ensure SL/TP are valid (e.g., SL is not below 0, TP is not same as entry)
    stopLoss = Decimal.max(0, stopLoss);
    // Ensure TP is at least slightly away from entry to avoid zero distance
    if (side === 'Buy') takeProfit = Decimal.max(dEntryPrice.plus(slDistance.times(0.1)), takeProfit);
    else takeProfit = Decimal.min(dEntryPrice.minus(slDistance.times(0.1)), takeProfit);

    return { 
        stopLoss: stopLoss.toDecimalPlaces(config.bybit.pricePrecision).toNumber(), // Convert back to number for API
        takeProfit: takeProfit.toDecimalPlaces(config.bybit.pricePrecision).toNumber()
    };
}
```

---

### Snippet 4: Enhanced WebSocket Subscriptions (Private Channel)

**File:** `src/api/bybit_websocket.js`, `src/trading_ai_system.js`

**Improvement:** Subscribes to private WebSocket channels (orders, positions) to get real-time updates directly from the exchange. This is critical for accurate state management (e.g., knowing when a TP/SL order is executed) and reducing reliance on polling REST API endpoints.

**`src/api/bybit_websocket.js` update:**

```javascript
// src/api/bybit_websocket.js
// ... (ensure crypto, config, logger are imported)
class BybitWebSocket {
    // ... constructor updated in Snippet 1

    generatePrivateSignature(expires) { // NEW: Signature for private WS authentication
        const paramStr = 'GET/realtime' + expires;
        return crypto.createHmac('sha256', this.apiSecret).update(paramStr).digest('hex');
    }

    connectPublic() { // NEW: Dedicated method for public WS
        this.ws = new WebSocket(this.url);

        this.ws.on('open', () => {
            logger.info("Public WebSocket connection established. Subscribing to candles.");
            const subscription = { op: "subscribe", args: [`kline.${config.interval}.${config.symbol}`] };
            this.ws.send(JSON.stringify(subscription));
            this.pingInterval = setInterval(() => this.ws.ping(), 20000); // Keep connection alive
        });

        this.ws.on('message', (data) => {
            const message = JSON.parse(data.toString());
            if (message.topic && message.topic.startsWith('kline')) {
                const candle = message.data && message.data[0];
                if (candle && candle.confirm === true) { // Make sure candle data exists and is confirmed
                    logger.info(`New confirmed ${config.interval}m candle for ${config.symbol}. Close: ${candle.close}`);
                    this.onNewCandle(); // Trigger the main analysis logic
                }
            }
        });

        this.ws.on('close', () => {
            logger.warn("Public WebSocket connection closed. Attempting to reconnect in 10 seconds...");
            if (this.pingInterval) clearInterval(this.pingInterval);
            setTimeout(() => this.connectPublic(), 10000);
        });

        this.ws.on('error', (err) => logger.exception(`Public WS Error: ${err.message}`));
    }

    connectPrivate() { // NEW: Dedicated method for private WS
        this.privateWs = new WebSocket(this.privateUrl);

        this.privateWs.on('open', () => {
            logger.info("Private WebSocket connection established. Authenticating and subscribing.");
            const expires = (Date.now() + 10000).toString(); // Expire in 10 seconds
            const signature = this.generatePrivateSignature(expires);
            const authMessage = {
                op: "auth",
                args: [this.apiKey, expires, signature]
            };
            this.privateWs.send(JSON.stringify(authMessage));

            // Subscribe to private topics AFTER authentication
            setTimeout(() => {
                const subscription = { op: "subscribe", args: ["order", "position"] }; // Order and Position updates
                this.privateWs.send(JSON.stringify(subscription));
                logger.info("Subscribed to private order and position updates.");
            }, 1000); // Wait a bit for auth to go through

            this.privatePingInterval = setInterval(() => this.privateWs.ping(), 20000);
        });

        this.privateWs.on('message', (data) => {
            try {
                const message = JSON.parse(data.toString());
                if (message.op === 'auth') {
                    if (message.success) {
                        logger.info("Private WebSocket authenticated successfully.");
                    } else {
                        logger.error(`Private WebSocket authentication failed: ${message.retMsg}`);
                    }
                } else if (message.topic === 'order' || message.topic === 'position') {
                    this.onPrivateMessage(message); // Pass private messages to handler
                }
            } catch (err) {
                logger.exception(`Failed to parse private WS message: ${err.message}`);
            }
        });

        this.privateWs.on('close', () => {
            logger.warn("Private WebSocket connection closed. Attempting to reconnect in 10 seconds...");
            if (this.privatePingInterval) clearInterval(this.privatePingInterval);
            setTimeout(() => this.connectPrivate(), 10000);
        });

        this.privateWs.on('error', (err) => logger.exception(`Private WS Error: ${err.message}`));
    }

    // NEW: Combined connect method to start both
    connect() {
        this.connectPublic();
        this.connectPrivate();
    }
}
export default BybitWebSocket;
```

**`src/trading_ai_system.js` update:**

```javascript
// src/trading_ai_system.js
// ...
class TradingAiSystem {
    constructor() {
        // ...
        // Initialize WebSocket with both callbacks
        this.bybitWs = new BybitWebSocket(
            () => this.handleNewCandle(),
            (message) => this.handlePrivateWsMessage(message) // NEW: Handler for private messages
        );
        this.isProcessing = false;
    }

    // NEW: Handler for private WebSocket messages
    async handlePrivateWsMessage(message) {
        logger.debug(`Private WS Message: ${JSON.stringify(message).substring(0, 100)}...`);
        // Example: If a position is closed by TP/SL, update the bot's state
        if (message.topic === 'position' && message.data && message.data.length > 0) {
            const position = message.data[0];
            // Check if position is closed and has PnL (meaning it was closed by the exchange)
            if (position.size === '0' && position.closedPnl !== '0' && position.closedPnl !== undefined) {
                logger.info(`Position for ${position.symbol} was closed by exchange (TP/SL). Realized PnL: ${position.closedPnl}`);
                let state = await loadState();
                
                // Update trade history and daily PnL
                const closedTradeIndex = state.tradeHistory.findIndex(t => t.symbol === position.symbol && t.status === 'OPEN');
                if (closedTradeIndex !== -1) {
                    const closedTrade = { ...state.tradeHistory[closedTradeIndex] };
                    closedTrade.status = 'CLOSED_EXCHANGE';
                    closedTrade.closeTimestamp = new Date().toISOString();
                    closedTrade.exitPrice = parseFloat(position.markPrice); // Use mark price at close
                    closedTrade.pnl = parseFloat(position.closedPnl);
                    state.tradeHistory[closedTradeIndex] = closedTrade;
                }
                
                state.dailyPnl = new Decimal(state.dailyPnl).plus(position.closedPnl).toNumber();
                state.inPosition = false; // Reset bot's position state
                state.positionSide = null;
                state.entryPrice = 0;
                state.quantity = 0;
                state.orderId = null;

                await saveState(state);
                notifier.send(`🔔 EXCH-CLOSED Alert: Position for ${position.symbol} closed by exchange. PnL: ${parseFloat(position.closedPnl).toFixed(2)} USDT.`);
            }
        }
        // More sophisticated logic needed here for robust state sync, including order updates
    }

    start() {
        logger.info("Starting Trading AI System...");
        this.initialize().then(() => { // Initialize moved to snippet 17
            this.bybitWs.connect(); // NEW: Call combined connect method
            // Optional: run once on startup without waiting for the first candle
            setTimeout(() => this.handleNewCandle(), 5000); // Give WS some time to connect and auth
        }).catch(error => {
            logger.exception(`System initialization failed: ${error.message}`);
            process.exit(1); // Exit if initialization fails
        });
        // ... (graceful shutdown)
    }
}
// ...
```

---

### Snippet 5: Centralized Price & Quantity Rounding / Precision

**File:** `src/core/trading_logic.js`

**Improvement:** Ensures all prices and quantities conform to exchange-specific tick and lot sizes, preventing API errors due to invalid precision. This leverages `Decimal.js` and the `config.bybit` precision settings.

**`src/core/trading_logic.js` update:**

```javascript
// src/core/trading_logic.js
import { RSI, SMA, MACD, ATR } from 'technicalindicators';
import { DataFrame } from 'danfojs-node';
import { config } from '../config.js';
import Decimal from 'decimal.js';
import logger from '../utils/logger.js'; // Ensure logger is imported

// NEW: Utility functions for rounding (can be used elsewhere if needed)
export function roundPrice(price) {
    return new Decimal(price).toDecimalPlaces(config.bybit.pricePrecision, Decimal.ROUND_HALF_UP).toNumber();
}

export function roundQuantity(qty) {
    // For BTCUSDT, lot size is often 0.001. We round down to prevent over-ordering.
    return new Decimal(qty).toDecimalPlaces(config.bybit.qtyPrecision, Decimal.ROUND_DOWN).toNumber();
}

// ... existing calculateIndicators and formatMarketContext

// Existing functions (calculatePositionSize, determineExitPrices) already use Decimal.js and toDecimalPlaces,
// effectively implementing this rounding, so no explicit call to roundPrice/roundQuantity is strictly needed
// if those functions return Decimals which are then stringified with toFixed() for API.
// However, if any numeric result is passed around, these functions ensure correctness.
```

---

### Snippet 6: Advanced Market Context for Gemini

**File:** `src/core/trading_logic.js`, `src/trading_ai_system.js`

**Improvement:** Provides Gemini with richer, more contextual market information, including recent price action summary, enabling more informed decision-making.

**`src/core/trading_logic.js` update:**

```javascript
// src/core/trading_logic.js
// ...
export function formatMarketContext(state, indicators, historicalKlines) { // NEW: historicalKlines
    const { price, rsi, smaShort, smaLong, macd, atr } = indicators;
    let context = `Market Snapshot for ${config.symbol} (Interval: ${config.interval} mins):\n`;
    context += `Current Price: ${price.toFixed(config.bybit.pricePrecision)}\n`;
    context += `RSI(${config.indicators.rsiPeriod}): ${rsi.toFixed(2)}\n`;
    context += `SMA_Short(${config.indicators.smaShortPeriod}): ${smaShort.toFixed(2)}\n`;
    context += `SMA_Long(${config.indicators.smaLongPeriod}): ${smaLong.toFixed(2)}\n`;
    context += `MACD Line: ${macd.MACD.toFixed(4)}, Signal Line: ${macd.signal.toFixed(4)}, Histogram: ${macd.histogram.toFixed(4)}\n`;
    context += `ATR(${config.indicators.atrPeriod}): ${atr.toFixed(4)} (Volatility Measure)\n`;

    // NEW: Add recent price action summary
    if (historicalKlines && historicalKlines.length >= 5) { // Last 5 confirmed candles
        const recentCloses = historicalKlines.slice(-5).map(c => parseFloat(c[4]));
        const recentHighs = historicalKlines.slice(-5).map(c => parseFloat(c[2]));
        const recentLows = historicalKlines.slice(-5).map(c => parseFloat(c[3]));
        
        context += `\nRecent Price Action (last 5 confirmed candles):\n`;
        context += `- Last 5 closes: [${recentCloses.map(p => p.toFixed(config.bybit.pricePrecision)).join(', ')}]\n`;
        context += `- 5-candle high: ${Math.max(...recentHighs).toFixed(config.bybit.pricePrecision)}\n`;
        context += `- 5-candle low: ${Math.min(...recentLows).toFixed(config.bybit.pricePrecision)}\n`;
        
        const lastCandle = historicalKlines[historicalKlines.length - 1];
        const prevCandle = historicalKlines[historicalKlines.length - 2];
        if (lastCandle && prevCandle) {
            const lastClose = parseFloat(lastCandle[4]);
            const prevClose = parseFloat(prevCandle[4]);
            const change = (lastClose - prevClose) / prevClose * 100;
            context += `- Last candle close change: ${change.toFixed(2)}%\n`;
        }
    }

    if (state.inPosition) {
        const pnl = new Decimal(price).minus(state.entryPrice).times(state.quantity).times(state.positionSide === 'Buy' ? 1 : -1);
        context += `\nCURRENTLY IN POSITION:
        - Side: ${state.positionSide}
        - Entry Price: ${new Decimal(state.entryPrice).toFixed(config.bybit.pricePrecision)}
        - Quantity: ${new Decimal(state.quantity).toFixed(config.bybit.qtyPrecision)}
        - Unrealized P/L: ${pnl.toFixed(2)} USDT`;
        if (state.takeProfit && state.stopLoss) {
             context += `\n- TP: ${state.takeProfit.toFixed(config.bybit.pricePrecision)}, SL: ${state.stopLoss.toFixed(config.bybit.pricePrecision)}`;
        }
    } else {
        context += "\nCURRENTLY FLAT (No open position).";
    }
    return context;
}
```

**`src/trading_ai_system.js` (within `handleNewCandle`):**

```javascript
// src/trading_ai_system.js
// ...
    async handleNewCandle() {
        // ...
        try {
            // ...
            const klines = await this.bybitApi.getHistoricalMarketData(config.symbol, config.interval);
            if (!klines || klines.length === 0) throw new Error("Failed to fetch market data.");
            
            // ... (lastProcessedCandleTimestamp check from snippet 20)

            // 2. Calculate Indicators & Format Context
            const { latest: indicatorsLatest } = calculateIndicators(klines);
            // NEW: Pass klines to formatMarketContext for historical price action
            const marketContext = formatMarketContext(state, indicatorsLatest, klines);
            // ...
        } // ...
    }
// ...
```

---

### Snippet 7: Gemini API Error Handling and Retries

**File:** `src/api/gemini_api.js`

**Improvement:** Implements a retry mechanism with exponential backoff for Gemini API calls, improving the bot's resilience to temporary network issues or API rate limits.

**`src/api/gemini_api.js` update:**

```javascript
// src/api/gemini_api.js
import { GoogleGenerativeAI } from '@google/generative-ai';
import { config } from '../config.js';
import logger from '../utils/logger.js';

class GeminiAPI {
    constructor(apiKey) {
        this.genAI = new GoogleGenerativeAI(apiKey);
        // NEW: Initialize model with tools directly in constructor
        this.model = this.genAI.getGenerativeModel({ model: config.ai.model, tools: this.getTools() });
    }

    getTools() { // Moved tools definition to a method for cleaner code
        return [{
            functionDeclarations: [
                {
                    name: "proposeTrade",
                    description: "Proposes a trade entry (Buy or Sell) based on market analysis. Only use when confidence is high.",
                    parameters: {
                        type: "OBJECT",
                        properties: {
                            side: { type: "STRING", enum: ["Buy", "Sell"] },
                            reasoning: { type: "STRING", description: "Detailed reasoning for the trade proposal." },
                            confidence: { type: "NUMBER", description: "Confidence score from 0.0 to 1.0." }
                        },
                        required: ["side", "reasoning", "confidence"]
                    }
                },
                {
                    name: "proposeExit",
                    description: "Proposes to close the current open position. Use if analysis suggests the trend is reversing or profit target is met.",
                    parameters: {
                        type: "OBJECT",
                        properties: {
                            reasoning: { type: "STRING", description: "Detailed reasoning for closing the position." }
                        },
                        required: ["reasoning"]
                    }
                }
            ]
        }];
    }

    async getTradeDecision(marketContext, retries = 3) { // NEW: retries parameter
        const prompt = `You are an expert trading analyst. Analyze the provided market data.
        - If you are NOT in a position and see a high-probability opportunity, call 'proposeTrade'.
        - If you ARE in a position, analyze the P/L and current data to decide if you should call 'proposeExit' or continue holding.
        - If no action is warranted, simply respond with your analysis on why you are holding.

        Market Data:
        ---
        ${marketContext}
        ---`;

        for (let i = 0; i < retries; i++) {
            try {
                const result = await this.model.generateContent(prompt);
                const functionCalls = result.response.functionCalls();

                if (functionCalls && functionCalls.length > 0) {
                    const call = functionCalls[0];
                    logger.info(`Gemini proposed function call: ${call.name}`);
                    return { name: call.name, args: call.args };
                }
                
                logger.info("Gemini recommends HOLD. Reason: " + result.response.text());
                return null; // Hold
            } catch (error) {
                logger.exception(`Gemini API call failed (Attempt ${i + 1}/${retries}): ${error.message}`);
                if (i < retries - 1) { // If not the last attempt, wait and retry
                    await new Promise(resolve => setTimeout(resolve, 2000 * (i + 1))); // Exponential backoff
                } else {
                    logger.error("Gemini API call failed after multiple retries. Defaulting to HOLD.");
                }
            }
        }
        return null; // Default to hold if all retries fail
    }
}

export default GeminiAPI;
```

---

### Snippet 8: Expanded Risk Policy: Max Daily Loss

**File:** `src/config.js`, `src/utils/state_manager.js`, `src/core/risk_policy.js`, `src/trading_ai_system.js`

**Improvement:** Adds a critical risk management layer to prevent catastrophic losses by stopping trading for the day if a predefined maximum daily loss percentage is hit.

**`src/config.js` update:**

```javascript
// src/config.js
export const config = {
    // ...
    riskManagement: { // NEW: Consolidated risk management settings
        riskPercentage: 1.5, // Risk 1.5% of equity per trade
        riskToRewardRatio: 2, // Aim for a 2:1 reward/risk ratio
        stopLossPercentage: 2, // The maximum percentage of price movement for the stop-loss
        maxDailyLossPercentage: 5, // NEW: Max 5% loss of starting daily equity
        useAtrForStopLoss: true, // NEW: Use ATR for dynamic SL distance
        atrMultiplier: 1.5, // NEW: How many ATRs for stop loss
    },
    // ...
};
```

**`src/utils/state_manager.js` `defaultState` update:**

```javascript
// src/utils/state_manager.js
// ...
export const defaultState = {
    inPosition: false,
    positionSide: null,
    entryPrice: 0,
    quantity: 0,
    orderId: null,
    takeProfit: null, // NEW: Store TP/SL in state
    stopLoss: null,   // NEW: Store TP/SL in state
    dailyPnl: 0, // NEW: Track PnL for the current day
    dailyEquityStart: 0, // NEW: Equity at the start of the current day
    lastActivityDate: null, // NEW: To reset daily stats (YYYY-MM-DD string)
    tradeHistory: [], // NEW: For tracking past trades
    lastProcessedCandleTimestamp: 0, // NEW: To avoid reprocessing old candles
    version: '2.1.0', // NEW: Version of the state structure
};
// ...
```

**`src/core/risk_policy.js` update:**

```javascript
// src/core/risk_policy.js
import { config } from '../config.js';
import logger from '../utils/logger.js';
import Decimal from 'decimal.js'; // Ensure Decimal.js is imported

export function applyRiskPolicy(proposedTrade, indicators, state) { // NEW: state parameter
    if (!proposedTrade) {
        return { decision: 'HOLD', reason: 'No trade proposed by AI.' };
    }

    // NEW: Daily Loss Check
    if (state.dailyEquityStart > 0 && new Decimal(state.dailyPnl).isNegative()) {
        const currentLossPercentage = Decimal.abs(new Decimal(state.dailyPnl)).div(state.dailyEquityStart).times(100);
        if (currentLossPercentage.greaterThanOrEqualTo(config.riskManagement.maxDailyLossPercentage)) {
            return { decision: 'HOLD', reason: `Max daily loss (${config.riskManagement.maxDailyLossPercentage}%) reached. Current loss: ${currentLossPercentage.toFixed(2)}%. Trading suspended for the day.` };
        }
    }

    if (proposedTrade.name === 'proposeTrade') {
        const { confidence } = proposedTrade.args;
        if (confidence < config.ai.confidenceThreshold) {
            return { decision: 'HOLD', reason: `AI confidence (${confidence}) is below threshold (${config.ai.confidenceThreshold}).` };
        }
        // Add more checks here, e.g., volatility check with ATR
        // if (indicators.atr / indicators.price > config.riskManagement.maxAllowedATRRatio) {
        //     return { decision: 'HOLD', reason: 'Market volatility is too high.' };
        // }
    }

    logger.info(`Risk policy approved the proposed action: ${proposedTrade.name}`);
    return { decision: 'PROCEED', trade: proposedTrade };
}
```

**`src/trading_ai_system.js` (within `handleNewCandle` and `initialize`):**

```javascript
// src/trading_ai_system.js
// ...
    async handleNewCandle() {
        // ...
        try {
            let state = await loadState(); // Use 'let' to allow reassigning updated state
            const klines = await this.bybitApi.getHistoricalMarketData(config.symbol, config.interval);
            if (!klines || klines.length === 0) throw new Error("Failed to fetch market data.");

            // NEW: Last processed candle timestamp check
            const latestCandleTimestamp = parseInt(klines[klines.length - 1][0]);
            if (latestCandleTimestamp <= state.lastProcessedCandleTimestamp) {
                logger.info("Latest candle already processed or not new. Skipping cycle.");
                this.isProcessing = false;
                return;
            }
            state.lastProcessedCandleTimestamp = latestCandleTimestamp; // Update processed timestamp

            // NEW: Daily reset for PnL and equity (moved before other logic to ensure correct daily stats for risk policy)
            const today = new Date().toISOString().split('T')[0];
            if (state.lastActivityDate !== today) {
                logger.info("New day detected. Resetting daily PnL and equity.");
                const balance = await this.bybitApi.getAccountBalance();
                if (balance) {
                    state.dailyEquityStart = balance;
                    state.dailyPnl = 0;
                    state.lastActivityDate = today;
                    // Will be saved at the end of the handleNewCandle cycle
                } else {
                    logger.warn("Could not get account balance for daily reset.");
                }
            }

            // ... (rest of handleNewCandle)

            // 4. Apply Risk Policy (pass updated state)
            const policyResult = applyRiskPolicy(aiDecision, indicatorsLatest, state); // NEW: Pass state here
            // ...

            // Ensure state is saved at the end of the cycle with all updates
            await saveState(state);
        } catch (error) {
            // ...
        } // ...
    }

    // ... initialize method (see Snippet 17)
```

---

### Snippet 9: State Management: Store Trade History

**File:** `src/utils/state_manager.js`, `src/trading_ai_system.js`

**Improvement:** Augments the bot's state to include a detailed history of all executed trades, which is crucial for performance analysis, auditing, and debugging.

**`src/utils/state_manager.js` `defaultState` update:** (Already included in Snippet 8)

**`src/trading_ai_system.js` (within `executeEntry` and `executeExit`):**

```javascript
// src/trading_ai_system.js
// ...
    async executeEntry(args, indicators) {
        logger.info(`Executing ENTRY based on AI proposal: ${args.side} - ${args.reasoning}`);
        const { side } = args;

        const ticker = await this.bybitApi.getTickerPrice(config.symbol); // NEW: Use ticker price (from Snippet 2)
        if (!ticker) throw new Error("Failed to get current ticker price for entry.");
        const currentPrice = side === 'Buy' ? ticker.ask1Price : ticker.bid1Price; // Use ask for buy, bid for sell

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance for position sizing.");

        const { stopLoss, takeProfit } = determineExitPrices(currentPrice, side, indicators.atr); // Pass ATR (from Snippet 3)
        const quantity = calculatePositionSize(balance, currentPrice, stopLoss);

        if (quantity.isZero() || quantity.isNegative()) { // NEW: Check Decimal.js quantity
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            notifier.send(`❌ ENTRY Failed: Calculated quantity for ${config.symbol} is invalid (${quantity.toFixed(config.bybit.qtyPrecision)}).`);
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol,
            side,
            qty: quantity.toNumber(), // Convert Decimal to number for API
            takeProfit,
            stopLoss,
        });

        if (orderResult) {
            // Retrieve current state to ensure all fields are preserved
            let state = await loadState(); // Ensure we have the latest state before updating

            const newTrade = { // NEW: Add trade to history
                id: Date.now(), // Unique ID for the trade
                type: 'ENTRY',
                timestamp: new Date().toISOString(),
                symbol: config.symbol,
                side,
                entryPrice: currentPrice,
                quantity: quantity.toNumber(),
                orderId: orderResult.orderId,
                takeProfit: takeProfit,
                stopLoss: stopLoss,
                status: 'OPEN',
                reasoning: args.reasoning,
                confidence: args.confidence,
            };

            const newState = {
                ...state, // Preserve existing daily stats etc.
                inPosition: true,
                positionSide: side,
                entryPrice: currentPrice,
                quantity: quantity.toNumber(),
                orderId: orderResult.orderId,
                takeProfit: takeProfit, // NEW: Store TP/SL
                stopLoss: stopLoss,     // NEW: Store TP/SL
                tradeHistory: [...state.tradeHistory, newTrade] // Add to history
            };
            await saveState(newState);
            logger.info(`Successfully entered ${side} position. Order ID: ${orderResult.orderId}`);
            notifier.send(`🔔 ENTRY Alert: ${side} ${config.symbol} @ ${currentPrice.toFixed(config.bybit.pricePrecision)}.\nTP: ${takeProfit.toFixed(config.bybit.pricePrecision)}, SL: ${stopLoss.toFixed(config.bybit.pricePrecision)}.\nReason: ${args.reasoning}`);
        } else {
             notifier.send(`❌ ENTRY Failed: Failed to place ${side} order for ${config.symbol}.`);
        }
    }

    async executeExit(state, args) { // state is now passed from handleNewCandle
        logger.info(`Executing EXIT based on AI proposal: ${args.reasoning}`);
        const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide);
        
        if (closeResult) {
            // Need to retrieve latest state again as other events might have happened
            state = await loadState(); // Load freshest state

            const closedTradeIndex = state.tradeHistory.findIndex(t => t.orderId === state.orderId && t.status === 'OPEN');
            let updatedTradeHistory = [...state.tradeHistory];
            let realizedPnl = new Decimal(0);

            // Fetch current price for PnL calculation if not from WS
            const ticker = await this.bybitApi.getTickerPrice(config.symbol);
            const currentPrice = ticker ? ticker.lastPrice : state.entryPrice; // Fallback to entry price

            if (closedTradeIndex !== -1) {
                const closedTrade = { ...updatedTradeHistory[closedTradeIndex] };
                closedTrade.status = 'CLOSED_BOT_MANUAL'; // Closed by bot, not exchange TP/SL
                closedTrade.closeTimestamp = new Date().toISOString();
                closedTrade.exitPrice = currentPrice;
                realizedPnl = (new Decimal(closedTrade.exitPrice).minus(closedTrade.entryPrice)).times(closedTrade.quantity).times(closedTrade.side === 'Buy' ? 1 : -1);
                closedTrade.pnl = realizedPnl.toNumber();
                updatedTradeHistory[closedTradeIndex] = closedTrade;
            } else {
                logger.warn("Could not find open trade in history to mark as closed.");
            }
            
            const newState = {
                ...defaultState, // Reset position-related fields, but preserve global defaults
                dailyPnl: new Decimal(state.dailyPnl).plus(realizedPnl).toNumber(), // Add realized PnL to daily total
                dailyEquityStart: state.dailyEquityStart, // Preserve daily stats
                lastActivityDate: state.lastActivityDate, // Preserve daily stats
                tradeHistory: updatedTradeHistory, // Update history
            };
            await saveState(newState);
            logger.info(`Successfully closed position. Realized PnL: ${realizedPnl.toFixed(2)}`);
            notifier.send(`🔔 EXIT Alert: Position for ${config.symbol} closed. PnL: ${realizedPnl.toFixed(2)} USDT.\nReason: ${args.reasoning}`);
        } else {
             notifier.send(`❌ EXIT Failed: Failed to close position for ${config.symbol}.`);
        }
    }
// ...
```

---

### Snippet 10: Graceful Shutdown

**File:** `src/trading_ai_system.js`

**Improvement:** Implements handlers for `SIGINT` (Ctrl+C) and `SIGTERM` signals to ensure that the bot can shut down cleanly, saving its state and closing WebSocket connections, preventing data corruption or resource leaks.

**`src/trading_ai_system.js` update:**

```javascript
// src/trading_ai_system.js
// ...
class TradingAiSystem {
    // ...
    start() {
        logger.info("Starting Trading AI System...");
        this.initialize().then(() => {
            this.bybitWs.connect();
            setTimeout(() => this.handleNewCandle(), 5000);

            // NEW: Handle graceful shutdown signals
            process.on('SIGINT', async () => {
                logger.info("SIGINT received. Shutting down gracefully...");
                await this.shutdown();
                process.exit(0);
            });
            process.on('SIGTERM', async () => {
                logger.info("SIGTERM received. Shutting down gracefully...");
                await this.shutdown();
                process.exit(0);
            });
        }).catch(error => {
            logger.exception(`System initialization failed: ${error.message}`);
            process.exit(1);
        });
    }

    async shutdown() { // NEW: Shutdown method
        // Disconnect WebSockets
        if (this.bybitWs.ws) {
            this.bybitWs.ws.close();
            logger.info("Public WebSocket closed.");
        }
        if (this.bybitWs.privateWs) {
            this.bybitWs.privateWs.close();
            logger.info("Private WebSocket closed.");
        }
        // Ensure state is saved one last time, though it should be saved after each trade
        // await saveState(this.currentState); // If a `currentState` was maintained in memory
        logger.info("Trading AI System shut down.");
        notifier.send("🛑 Trading bot is shutting down.");
    }
}
// ...
```

---

### Snippet 11: Improved Logging with Configurable Levels

**File:** `src/config.js`, `src/utils/logger.js`

**Improvement:** Adds configurable log levels, allowing developers to control the verbosity of logs (e.g., show only errors in production, all debug messages in development).

**`src/config.js` update:**

```javascript
// src/config.js
export const config = {
    // ...
    logger: { // NEW: Logger configuration
        level: 'INFO', // DEBUG, INFO, WARN, ERROR, EXCEPTION
        // fileLoggingEnabled: false, // Optional: for future file logging
        // logFilePath: './logs/bot.log',
    },
    // ...
};
```

**`src/utils/logger.js` update:**

```javascript
// src/utils/logger.js
import { config } from '../config.js'; // NEW: Import config

const RESET = "\x1b[0m";
const NEON_RED = "\x1b[38;5;196m";
const NEON_GREEN = "\x1b[38;5;46m";
const NEON_YELLOW = "\x1b[38;5;226m";
const NEON_BLUE = "\x1b[38;5;39m"; // For debug
const NEON_CYAN = "\x1b[38;5;51m"; // For debug or other levels

const LOG_LEVELS = { // NEW: Define log levels
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3,
    EXCEPTION: 4,
};

// NEW: Get current log level from config, default to INFO
const currentLogLevel = LOG_LEVELS[config.logger.level.toUpperCase()] || LOG_LEVELS.INFO;

const getTimestamp = () => new Date().toISOString();

// NEW: Centralized logging function with level check
const logMessage = (level, color, message) => {
    if (LOG_LEVELS[level] >= currentLogLevel) {
        console.log(`${color}[${level}][${getTimestamp()}] ${message}${RESET}`);
        // Future improvement: Add file logging here if config.logger.fileLoggingEnabled
    }
};

const logger = {
    debug: (message) => logMessage('DEBUG', NEON_BLUE, message),
    info: (message) => logMessage('INFO', NEON_GREEN, message),
    warn: (message) => logMessage('WARN', NEON_YELLOW, message),
    error: (message) => logMessage('ERROR', NEON_RED, message),
    exception: (error) => {
        logMessage('EXCEPTION', NEON_RED, error instanceof Error ? `${error.message}\n${error.stack}` : String(error));
    },
};

export default logger;
```

---

### Snippet 12: Configurable Webhook for Notifications

**File:** `src/config.js`, `src/utils/notifier.js` (new file), `src/trading_ai_system.js`

**Improvement:** Adds a `Notifier` module to send real-time alerts to external services (e.g., Discord, Telegram) about trade executions, errors, or significant events, enhancing monitoring capabilities.

**`src/config.js` update:** (Already included in Snippet 8)

**New file: `src/utils/notifier.js`**

```javascript
// src/utils/notifier.js
import { config } from '../config.js';
import logger from './logger.js'; // Use the logger for internal errors

class Notifier {
    constructor() {
        this.discordWebhookUrl = config.notifications.discordWebhookUrl;
        this.telegramBotToken = config.notifications.telegramBotToken;
        this.telegramChatId = config.notifications.telegramChatId;
        this.enabled = config.notifications.enabled;
    }

    async sendDiscordMessage(message) {
        if (!this.enabled || !this.discordWebhookUrl) return;
        try {
            await fetch(this.discordWebhookUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content: message }),
            });
        } catch (error) {
            logger.error(`Failed to send Discord notification: ${error.message}`);
        }
    }

    async sendTelegramMessage(message) {
        if (!this.enabled || !this.telegramBotToken || !this.telegramChatId) return;
        const url = `https://api.telegram.org/bot${this.telegramBotToken}/sendMessage`;
        try {
            await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chat_id: this.telegramChatId, text: message, parse_mode: 'Markdown' }),
            });
        } catch (error) {
            logger.error(`Failed to send Telegram notification: ${error.message}`);
        }
    }

    async send(message) {
        if (!this.enabled) return;
        await Promise.allSettled([ // Use allSettled to prevent one failure from blocking others
            this.sendDiscordMessage(message),
            this.sendTelegramMessage(message),
        ]);
    }
}

export default new Notifier(); // Export a singleton instance
```

**`src/trading_ai_system.js` (within `executeEntry` and `executeExit`):** (Already included in Snippet 9)

---

### Snippet 13: Pre-Flight Checks and Initialization

**File:** `src/trading_ai_system.js`

**Improvement:** Adds an `initialize` method to perform essential checks at startup, such as verifying API keys, checking exchange connectivity, and fetching the initial account balance. This prevents the bot from running with invalid configurations.

**`src/trading_ai_system.js` update:**

```javascript
// src/trading_ai_system.js
// ...
class TradingAiSystem {
    constructor() {
        this.bybitApi = new BybitAPI(process.env.BYBIT_API_KEY, process.env.BYBIT_API_SECRET);
        this.geminiApi = new GeminiAPI(process.env.GEMINI_API_KEY);
        this.bybitWs = new BybitWebSocket(
            () => this.handleNewCandle(),
            (message) => this.handlePrivateWsMessage(message)
        );
        this.isProcessing = false;
    }

    async initialize() { // NEW: Initialization method
        logger.info("Performing pre-flight checks...");

        if (!process.env.BYBIT_API_KEY || !process.env.BYBIT_API_SECRET || !process.env.GEMINI_API_KEY) {
            throw new Error("Missing API keys in .env file. Please check BYBIT_API_KEY, BYBIT_API_SECRET, GEMINI_API_KEY.");
        }
        
        // Check Bybit API connectivity and balance
        logger.info("Checking Bybit API connectivity and account balance...");
        const balance = await this.bybitApi.getAccountBalance();
        if (balance === null) {
            throw new Error("Failed to connect to Bybit API or retrieve account balance. Check API keys/permissions.");
        }
        logger.info(`Initial Bybit Account Balance: ${balance.toFixed(2)} USDT.`);

        // Initialize daily equity if not already set or if it's a new day
        let state = await loadState(); // Load state to check daily stats
        const today = new Date().toISOString().split('T')[0];
        if (state.dailyEquityStart === 0 || state.lastActivityDate !== today) {
            state.dailyEquityStart = balance;
            state.dailyPnl = 0;
            state.lastActivityDate = today;
            await saveState(state); // Save this initial state
            logger.info(`Daily equity start initialized to ${balance.toFixed(2)} USDT.`);
        } else {
             logger.info(`Daily equity start already set for today: ${state.dailyEquityStart.toFixed(2)} USDT. Current Daily PnL: ${state.dailyPnl.toFixed(2)}`);
        }
        logger.info("Pre-flight checks passed.");
    }

    start() {
        logger.info("Starting Trading AI System...");
        // NEW: Call initialize before connecting WebSockets
        this.initialize().then(() => {
            this.bybitWs.connect();
            setTimeout(() => this.handleNewCandle(), 5000); // Give WS some time to connect and auth
        }).catch(error => {
            logger.exception(`System initialization failed: ${error.message}`);
            process.exit(1); // Exit if initialization fails
        });

        // ... graceful shutdown (from Snippet 10)
    }
}
// ...
```

---

### Snippet 14: Dynamic Stop-Loss Adjustment (ATR Based)

**File:** `src/config.js`, `src/core/trading_logic.js`, `src/trading_ai_system.js`

**Improvement:** Makes stop-loss calculation more adaptive by incorporating Average True Range (ATR), a volatility indicator. This helps in placing more appropriate stop-losses that react to current market conditions rather than fixed percentages.

**`src/config.js` update:** (Already included in Snippet 8)

**`src/core/trading_logic.js` `determineExitPrices` update:** (Already included in Snippet 3)

**`src/trading_ai_system.js` (within `executeEntry`):**

```javascript
// src/trading_ai_system.js
// ...
    async executeEntry(args, indicators) {
        // ...
        const ticker = await this.bybitApi.getTickerPrice(config.symbol);
        if (!ticker) throw new Error("Failed to get current ticker price for entry.");
        const currentPrice = side === 'Buy' ? ticker.ask1Price : ticker.bid1Price;

        // ...
        // NEW: Pass indicators.atr to determineExitPrices for dynamic SL/TP
        const { stopLoss, takeProfit } = determineExitPrices(currentPrice, side, indicators.atr);
        const quantity = calculatePositionSize(balance, currentPrice, stopLoss);
        // ... (rest of executeEntry)
    }
// ...
```

---

### Snippet 15: More Detailed `defaultState` and State Validation

**File:** `src/utils/state_manager.js`

**Improvement:** Enhances the `defaultState` with more fields for comprehensive tracking and adds basic validation/migration logic during state loading, making the system more robust to state file inconsistencies or version changes.

**`src/utils/state_manager.js` `defaultState` update:** (Already included in Snippet 8)

**`src/utils/state_manager.js` `loadState` update:**

```javascript
// src/utils/state_manager.js
import { promises as fs } from 'fs';
import path from 'path';
import logger from './logger.js';

const stateFilePath = path.resolve('trading_state.json');

// ... defaultState (from Snippet 8)

export async function loadState() {
    try {
        const data = await fs.readFile(stateFilePath, 'utf-8');
        const loadedState = JSON.parse(data);

        // NEW: State validation and simple migration
        const newState = { ...defaultState, ...loadedState };

        // Example migration: if a new field is missing, add its default
        if (newState.lastProcessedCandleTimestamp === undefined) { // Check for undefined, 0 might be a valid value
            newState.lastProcessedCandleTimestamp = defaultState.lastProcessedCandleTimestamp;
            logger.warn("Migrating state: Added 'lastProcessedCandleTimestamp'.");
        }
        if (!newState.version || newState.version !== defaultState.version) {
            logger.warn(`Migrating state from v${loadedState.version || 'unknown'} to v${defaultState.version}`);
            // More complex migration logic could go here if schema changes drastically
            newState.version = defaultState.version;
            // For significant changes, you might need to re-initialize certain parts of the state.
            // For example: if tradeHistory structure changes, re-process or clear.
        }
        
        // Ensure decimal values are stored as numbers if they were strings, or vice versa, based on usage.
        // For simplicity, we assume values are numbers and convert to Decimal.js when used.

        logger.info("Trading state loaded successfully.");
        return newState;
    } catch (error) {
        if (error.code === 'ENOENT') {
            logger.info("No state file found, creating a new one with default state.");
            await saveState(defaultState); // Save default state
            return { ...defaultState };
        }
        logger.exception(`Error loading state: ${error.message}. Returning default state.`);
        return { ...defaultState };
    }
}

export async function saveState(state) {
    try {
        // NEW: Ensure state is always clean before saving (e.g., remove temporary fields if any)
        const stateToSave = { ...state };
        // Any specific cleanup before saving can go here
        
        await fs.writeFile(stateFilePath, JSON.stringify(stateToSave, null, 2));
        logger.info("Trading state has been saved.");
    } catch (error) {
        logger.exception(error);
    }
}
```

---

### Snippet 16: Prevent Reprocessing Old Candlestick Data

**File:** `src/utils/state_manager.js`, `src/trading_ai_system.js`

**Improvement:** Adds a `lastProcessedCandleTimestamp` to the bot's state. This prevents the bot from re-running its logic for candlestick data it has already processed, avoiding redundant computations and potential issues with duplicate trade signals.

**`src/utils/state_manager.js` `defaultState` update:** (Already included in Snippet 8)

**`src/trading_ai_system.js` (within `handleNewCandle`):**

```javascript
// src/trading_ai_system.js
// ...
    async handleNewCandle() {
        if (this.isProcessing) {
            logger.warn("Already processing a cycle, skipping new candle trigger.");
            return;
        }
        this.isProcessing = true;
        logger.info("=========================================");
        logger.info("Handling new confirmed candle...");

        try {
            let state = await loadState(); // Ensure freshest state
            const klines = await this.bybitApi.getHistoricalMarketData(config.symbol, config.interval);
            if (!klines || klines.length === 0) {
                 logger.warn("Failed to fetch market data or no klines returned. Skipping cycle.");
                 this.isProcessing = false;
                 return;
            }

            // NEW: Check if this candle has already been processed
            const latestCandleTimestamp = parseInt(klines[kllines.length - 1][0]);
            if (latestCandleTimestamp <= state.lastProcessedCandleTimestamp) {
                logger.info("Latest candle already processed or not new. Skipping cycle.");
                this.isProcessing = false;
                return;
            }
            state.lastProcessedCandleTimestamp = latestCandleTimestamp; // Update processed timestamp

            // NEW: Daily reset for PnL and equity (moved here to use the latest `state`)
            const today = new Date().toISOString().split('T')[0];
            if (state.lastActivityDate !== today) {
                logger.info("New day detected. Resetting daily PnL and equity.");
                const balance = await this.bybitApi.getAccountBalance();
                if (balance) {
                    state.dailyEquityStart = balance;
                    state.dailyPnl = 0;
                    state.lastActivityDate = today;
                } else {
                    logger.warn("Could not get account balance for daily reset.");
                }
            }
            
            // ... (rest of handleNewCandle logic)

            // Ensure state is saved at the end of the cycle with all updates
            await saveState(state);
        } catch (error) {
            // ...
        } finally {
            this.isProcessing = false;
            logger.info("Processing cycle finished.");
            logger.info("=========================================\n");
        }
    }
// ...
```

---

### Snippet 17: Use Live Ticker Price for Order Placement

**File:** `src/api/bybit_api.js`, `src/trading_ai_system.js`

**Improvement:** Instead of relying on the (potentially stale) close price of the last confirmed candle for order placement, this change fetches real-time ticker data (bid/ask prices) to ensure trades are entered at the most current market rates.

**`src/api/bybit_api.js` `getTickerPrice` update:** (Already included in Snippet 2)

**`src/trading_ai_system.js` (within `executeEntry`):** (Already included in Snippet 9)

---

### Snippet 18: Improved Error Handling for External APIs

**File:** `src/api/bybit_api.js`, `src/api/gemini_api.js`

**Improvement:** While retry mechanisms are present, this snippet focuses on improving the error messages and logging for clarity, making it easier to diagnose issues with external API calls.

**`src/api/bybit_api.js` `sendRequest` update:** (Already included in Snippet 2 with added retry logging)

**`src/api/gemini_api.js` `getTradeDecision` update:** (Already included in Snippet 7 with added retry logging)

---

### Snippet 19: Clearer State Management in `executeEntry` and `executeExit`

**File:** `src/trading_ai_system.js`

**Improvement:** Ensures that when `executeEntry` or `executeExit` is called, the bot first loads the *latest* state from the file (or an in-memory representation if one were used) before making any modifications. This prevents race conditions where the `state` object passed might be outdated if the WS `handlePrivateWsMessage` has modified it.

**`src/trading_ai_system.js` (within `executeEntry` and `executeExit`):**

```javascript
// src/trading_ai_system.js
// ...
    async executeEntry(args, indicators) {
        // ...
        const orderResult = await this.bybitApi.placeOrder({ /* ... */ });

        if (orderResult) {
            // NEW: Load freshest state before modification
            let state = await loadState();

            const newTrade = { /* ... */ }; // Trade details
            const newState = {
                ...state, // Preserve existing daily stats etc.
                inPosition: true,
                positionSide: side,
                entryPrice: currentPrice,
                quantity: quantity.toNumber(),
                orderId: orderResult.orderId,
                takeProfit: takeProfit,
                stopLoss: stopLoss,
                tradeHistory: [...state.tradeHistory, newTrade]
            };
            await saveState(newState);
            // ... notifier.send
        }
        // ...
    }

    async executeExit(originalState, args) { // Renamed param to originalState for clarity
        logger.info(`Executing EXIT based on AI proposal: ${args.reasoning}`);
        const closeResult = await this.bybitApi.closePosition(config.symbol, originalState.positionSide);
        
        if (closeResult) {
            // NEW: Load freshest state before modification
            let state = await loadState();

            const closedTradeIndex = state.tradeHistory.findIndex(t => t.orderId === state.orderId && t.status === 'OPEN');
            let updatedTradeHistory = [...state.tradeHistory];
            let realizedPnl = new Decimal(0);

            // ... PnL calculation and trade history update (from Snippet 9)

            const newState = {
                ...defaultState, // Reset position-related fields, but preserve global defaults
                dailyPnl: new Decimal(state.dailyPnl).plus(realizedPnl).toNumber(),
                dailyEquityStart: state.dailyEquityStart,
                lastActivityDate: state.lastActivityDate,
                tradeHistory: updatedTradeHistory,
            };
            await saveState(newState);
            // ... notifier.send
        }
        // ...
    }
// ...
```

---

### Snippet 20: Ensure `Decimal.js` Quantities are Converted to Numbers for API

**File:** `src/trading_ai_system.js`

**Improvement:** While `Decimal.js` is used for internal calculations, most APIs (including Bybit's) expect numeric values or strings representing numbers. This snippet explicitly converts `Decimal` objects to standard JavaScript numbers (or strings via `toFixed`) before passing them to the API.

**`src/trading_ai_system.js` (within `executeEntry`):**

```javascript
// src/trading_ai_system.js
// ...
    async executeEntry(args, indicators) {
        // ...
        const quantity = calculatePositionSize(balance, currentPrice, stopLoss);

        if (quantity.isZero() || quantity.isNegative()) {
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            notifier.send(`❌ ENTRY Failed: Calculated quantity for ${config.symbol} is invalid (${quantity.toFixed(config.bybit.qtyPrecision)}).`);
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol,
            side,
            qty: quantity.toNumber(), // NEW: Convert Decimal quantity to a standard number
            takeProfit,
            stopLoss,
        });

        if (orderResult) {
            let state = await loadState();
            const newTrade = {
                // ...
                quantity: quantity.toNumber(), // NEW: Store as number in state too for consistency
                // ...
            };
            const newState = {
                // ...
                quantity: quantity.toNumber(), // NEW: Update state with number
                // ...
            };
            await saveState(newState);
            // ...
        }
        // ...
    }
// ...
```
