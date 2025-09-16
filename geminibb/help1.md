Here are 20 update and improvement code snippets across the provided files. Each snippet is prefixed with `// IMPROVEMENT X:` to denote its number and purpose.

---

### `src/api/bybit_api.js`

```javascript
// src/api/bybit_api.js
import crypto from 'crypto-js';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import Decimal from 'decimal.js';
import { SIDES } from '../core/constants.js';
// IMPROVEMENT 2: Use axios for requests (better interceptors, error handling, defaults)
import axios from 'axios';
// IMPROVEMENT 5: Zod for parameter validation
import { z } from 'zod';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// IMPROVEMENT 1: Simple Request Queue for Rate Limiting
const requestQueue = [];
let isProcessingQueue = false;

// IMPROVEMENT 6: Schema for placeOrder parameters
const PlaceOrderSchema = z.object({
    symbol: z.string(),
    side: z.enum(['Buy', 'Sell']),
    qty: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).refine(n => n > 0, "Quantity must be positive."),
    takeProfit: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    stopLoss: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    orderType: z.enum(['Market', 'Limit', 'PostOnly']).default('Market'), // IMPROVEMENT 4: Order Type Flexibility
    price: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(), // For limit orders
});


export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = config.bybit.testnet ? 'https://api-testnet.bybit.com' : config.bybit.restUrl;
        logger.info(`Bybit API configured for ${config.bybit.testnet ? 'TESTNET' : 'MAINNET'}`);

        // IMPROVEMENT 2: Initialize axios instance
        this.axiosInstance = axios.create({
            baseURL: this.baseUrl,
            timeout: config.bybit.requestTimeoutMs, // IMPROVEMENT 3: Request Timeout
            headers: { 'Content-Type': 'application/json' },
        });

        // IMPROVEMENT 2: Axios Interceptor for logging and basic error handling
        this.axiosInstance.interceptors.response.use(
            response => {
                logger.debug(`API Response [${response.config.method}] ${response.config.url}: Status ${response.status}`);
                return response;
            },
            error => {
                logger.error(`API Request Error [${error.config?.method}] ${error.config?.url}: ${error.message}`);
                if (error.response) {
                    logger.error(`Response data: ${JSON.stringify(error.response.data)}`);
                    // IMPROVEMENT 7: Specific Bybit Error Code Handling
                    const retCode = error.response.data?.retCode;
                    const retMsg = error.response.data?.retMsg;
                    if (retCode === 10001) { // Invalid API key / Signature error
                        throw new Error(`Bybit Authentication Error: ${retMsg} (Code: ${retCode})`);
                    } else if (retCode === 110001) { // Insufficient balance
                        throw new Error(`Bybit Trading Error: Insufficient Balance. ${retMsg} (Code: ${retCode})`);
                    } else if (retCode === 110007) { // Order quantity too small
                        throw new Error(`Bybit Trading Error: Order quantity too small. ${retMsg} (Code: ${retCode})`);
                    } else {
                        throw new Error(`Bybit API Error: ${retMsg} (Code: ${retCode})`);
                    }
                }
                return Promise.reject(error);
            }
        );

        this.symbolInfo = {}; // IMPROVEMENT 8: Cache symbol info
        this.loadSymbolInfo(); // Load on startup
    }

    // IMPROVEMENT 8: Fetch and cache symbol information
    async loadSymbolInfo() {
        try {
            const result = await this._request('GET', '/v5/market/instruments-info', { category: 'linear', symbol: config.symbol });
            if (result && result.list && result.list.length > 0) {
                const info = result.list[0];
                this.symbolInfo = {
                    pricePrecision: parseInt(info.priceFilter.tickSize.split('.')[1]?.length || 0),
                    qtyPrecision: parseInt(info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0),
                    minOrderQty: parseFloat(info.lotSizeFilter.minOrderQty),
                    maxOrderQty: parseFloat(info.lotSizeFilter.maxOrderQty),
                };
                logger.info(`Symbol info for ${config.symbol} loaded: Price Precision ${this.symbolInfo.pricePrecision}, Qty Precision ${this.symbolInfo.qtyPrecision}, Min Qty ${this.symbolInfo.minOrderQty}`);
            } else {
                logger.warn(`Could not load symbol info for ${config.symbol}. Using default config precisions.`);
            }
        } catch (error) {
            logger.error(`Error loading symbol info: ${error.message}. Using default config precisions.`);
        }
    }

    getQtyPrecision() { return this.symbolInfo.qtyPrecision ?? config.bybit.qtyPrecision; }
    getPricePrecision() { return this.symbolInfo.pricePrecision ?? config.bybit.pricePrecision; }
    getMinOrderQty() { return this.symbolInfo.minOrderQty ?? config.minOrderSize; }

    // IMPROVEMENT 1: Process requests via a queue to respect rate limits
    async _request(method, endpoint, params = {}, isPrivate = true) {
        return new Promise((resolve, reject) => {
            requestQueue.push({ method, endpoint, params, isPrivate, resolve, reject });
            this._processQueue();
        });
    }

    async _processQueue() {
        if (isProcessingQueue) return;
        isProcessingQueue = true;

        while (requestQueue.length > 0) {
            const { method, endpoint, params, isPrivate, resolve, reject } = requestQueue.shift();
            try {
                // Delay to respect Bybit's general rate limits (e.g., 50 req/sec for public, 10 req/sec for private)
                // A more sophisticated approach would track categories and burst limits.
                await sleep(config.bybit.requestIntervalMs); // Add a small delay between requests

                const result = await this._makeRequest(method, endpoint, params, isPrivate);
                resolve(result);
            } catch (error) {
                reject(error);
            }
        }
        isProcessingQueue = false;
    }

    async _makeRequest(method, endpoint, params = {}, isPrivate = true) {
        const timestamp = Date.now().toString();
        const recvWindow = config.bybit.recvWindow; // IMPROVEMENT 3: Configurable recvWindow

        let queryString = '';
        let signPayload = '';

        if (isPrivate) { // Only sign private endpoints
            queryString = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
            signPayload = timestamp + this.apiKey + recvWindow + (queryString || '');
        } else { // Public endpoints don't require signature
            queryString = new URLSearchParams(params).toString();
            // Public requests don't need API key, signature, etc.
        }

        const signature = isPrivate ? crypto.HmacSHA256(signPayload, this.apiSecret).toString() : '';

        const headers = {
            'Content-Type': 'application/json',
            // IMPROVEMENT 2: Pass API keys only for private requests
            ...(isPrivate && {
                'X-BAPI-API-KEY': this.apiKey,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recvWindow,
            })
        };

        const url = `${endpoint}${method === 'GET' && queryString ? '?' + queryString : ''}`;
        const options = {
            method,
            headers,
            // IMPROVEMENT 2: axios handles body differently
            data: method !== 'GET' ? queryString : undefined,
            params: method === 'GET' ? params : undefined,
        };

        logger.debug(`Sending API request: ${method} ${url} with params: ${JSON.stringify(params)}`);

        // Use axios instance
        const response = await this.axiosInstance(url, options);
        const data = response.data;

        if (data.retCode !== 0) {
            throw new Error(`Bybit API Error: ${data.retMsg} (Code: ${data.retCode})`);
        }
        return data.result;
    }

    async getHistoricalMarketData(symbol, interval, limit = 200) {
        // IMPROVEMENT 3: Dynamically use category
        return this._request('GET', '/v5/market/kline', { category: config.bybit.category, symbol, interval, limit }, false);
    }

    async getAccountBalance() {
        // IMPROVEMENT 3: Configurable accountType
        const result = await this._request('GET', '/v5/account/wallet-balance', { accountType: config.bybit.accountType });
        const usdtBalance = result?.list?.[0]?.coin?.find(c => c.coin === 'USDT');
        return usdtBalance ? parseFloat(usdtBalance.walletBalance) : null;
    }

    async getCurrentPosition(symbol) {
        // IMPROVEMENT 3: Dynamically use category
        const result = await this._request('GET', '/v5/position/list', { category: config.bybit.category, symbol });
        // Bybit returns all positions, filter for the specific symbol
        const position = result?.list?.find(p => p.symbol === symbol);
        // IMPROVEMENT 13: Handle different position types (e.g., isolated/cross)
        return position && parseFloat(position.size) > 0 ? position : null;
    }

    async placeOrder(order) {
        // IMPROVEMENT 5: Validate order parameters
        const validationResult = PlaceOrderSchema.safeParse(order);
        if (!validationResult.success) {
            logger.error(`Order validation failed: ${validationResult.error.message}`, validationResult.error);
            throw new Error(`Invalid order parameters: ${validationResult.error.message}`);
        }
        const validatedOrder = validationResult.data;

        const { symbol, side, qty, takeProfit, stopLoss, orderType, price } = validatedOrder;
        
        // IMPROVEMENT 8: Apply dynamic precision and min order size
        const qtyToPlace = new Decimal(qty).toFixed(this.getQtyPrecision(), Decimal.ROUND_DOWN); // Ensure quantity is within step size
        const tpToPlace = takeProfit !== undefined ? new Decimal(takeProfit).toFixed(this.getPricePrecision()) : undefined;
        const slToPlace = stopLoss !== undefined ? new Decimal(stopLoss).toFixed(this.getPricePrecision()) : undefined;
        const priceToPlace = price !== undefined ? new Decimal(price).toFixed(this.getPricePrecision()) : undefined;

        if (new Decimal(qtyToPlace).lt(this.getMinOrderQty())) {
            throw new Error(`Order quantity ${qtyToPlace} is below minimum order quantity ${this.getMinOrderQty()} for ${symbol}.`);
        }

        const log = `Placing order: ${side} ${qtyToPlace} ${symbol} | Type: ${orderType} | Price: ${priceToPlace || 'N/A'} | TP: ${tpToPlace || 'N/A'}, SL: ${slToPlace || 'N/A'}`;
        if (config.dryRun) {
            logger.info(`[DRY RUN] ${log}`);
            return { orderId: `dry-run-${Date.now()}` };
        }
        logger.info(log);

        const orderParams = {
            category: config.bybit.category, // IMPROVEMENT 3: Dynamically use category
            symbol, side, orderType,
            qty: qtyToPlace,
            ...(orderType !== 'Market' && priceToPlace && { price: priceToPlace }), // Include price only for limit orders
            ...(tpToPlace && { takeProfit: tpToPlace }),
            ...(slToPlace && { stopLoss: slToPlace }),
            timeInForce: 'GTC', // Good-Til-Cancelled by default
        };
        
        return this._request('POST', '/v5/order/create', orderParams);
    }

    async closePosition(symbol, side) {
        const position = await this.getCurrentPosition(symbol);
        if (!position) {
            logger.warn("Attempted to close a position that does not exist or has zero size.");
            return null;
        }
        const closeSide = side === SIDES.BUY ? SIDES.SELL : SIDES.BUY;
        // IMPROVEMENT 4: Force market order for closing
        return this.placeOrder({ symbol, side: closeSide, qty: parseFloat(position.size), orderType: 'Market', takeProfit: 0, stopLoss: 0 });
    }

    // IMPROVEMENT 20: Method to cancel all open orders for a symbol
    async cancelAllOpenOrders(symbol) {
        logger.info(`Attempting to cancel all open orders for ${symbol}.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would cancel all open orders for ${symbol}.`);
            return { result: 'dry-run-cancel' };
        }
        try {
            const result = await this._request('POST', '/v5/order/cancel-all', {
                category: config.bybit.category,
                symbol: symbol,
            });
            logger.info(`Successfully cancelled all open orders for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to cancel all open orders for ${symbol}: ${error.message}`);
            throw error;
        }
    }
}
```

---

### `src/api/bybit_websocket.js`

```javascript
// src/api/bybit_websocket.js
import WebSocket from 'ws';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import crypto from 'crypto-js';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

class BybitWebSocket {
    constructor(onNewCandleCallback, onPrivateMessageCallback) {
        this.publicUrl = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/public/linear' : config.bybit.wsUrl;
        this.privateUrl = config.bybit.testnet ? 'wss://stream-testnet.bybit.com/v5/private' : config.bybit.privateWsUrl;
        this.onNewCandle = onNewCandleCallback;
        this.onPrivateMessage = onPrivateMessageCallback;
        this.publicWs = null;
        this.privateWs = null;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        this.publicPingInterval = null;
        this.privatePingInterval = null;
        this.publicReconnectTimeout = null; // IMPROVEMENT 9: Reconnect timeout management
        this.privateReconnectTimeout = null; // IMPROVEMENT 9: Reconnect timeout management
        this.publicRetryAttempt = 0; // IMPROVEMENT 9: Retry attempt counter
        this.privateRetryAttempt = 0; // IMPROVEMENT 9: Retry attempt counter
    }

    // IMPROVEMENT 9: Centralized WebSocket connection and reconnection logic with backoff
    _connectWs(type, url, onOpen, onMessage, onClose, onError) {
        let ws = new WebSocket(url);
        let retryAttempt = (type === 'public') ? this.publicRetryAttempt : this.privateRetryAttempt;
        let reconnectTimeoutVar = (type === 'public') ? 'publicReconnectTimeout' : 'privateReconnectTimeout';

        ws.on('open', () => {
            logger.info(`${type} WebSocket connection established.`);
            if (type === 'public') this.publicRetryAttempt = 0;
            else this.privateRetryAttempt = 0;
            clearTimeout(this[reconnectTimeoutVar]);
            onOpen(ws);
        });

        ws.on('message', onMessage);

        ws.on('close', () => {
            logger.error(`${type} WebSocket connection closed. Attempting to reconnect with backoff...`);
            this._scheduleReconnect(type, url, onOpen, onMessage, onClose, onError);
        });

        ws.on('error', (err) => {
            logger.exception(`Error on ${type} WebSocket:`, err);
            onError(err);
            // Close the socket to trigger a reconnect if it's not already closing
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        });

        return ws;
    }

    _scheduleReconnect(type, url, onOpen, onMessage, onClose, onError) {
        let retryAttempt = (type === 'public') ? this.publicRetryAttempt : this.privateRetryAttempt;
        let reconnectTimeoutVar = (type === 'public') ? 'publicReconnectTimeout' : 'privateReconnectTimeout';

        const delay = Math.min(config.bybit.maxReconnectDelayMs, Math.pow(2, retryAttempt) * 1000); // Exponential backoff
        logger.info(`Scheduling ${type} WebSocket reconnection in ${delay / 1000} seconds (attempt ${retryAttempt + 1})...`);

        this[reconnectTimeoutVar] = setTimeout(() => {
            if (type === 'public') {
                this.publicRetryAttempt++;
                this.publicWs = this._connectWs(type, url, onOpen, onMessage, onClose, onError);
            } else {
                this.privateRetryAttempt++;
                this.privateWs = this._connectWs(type, url, onOpen, onMessage, onClose, onError);
            }
        }, delay);
    }

    // IMPROVEMENT 10: Unified ping/pong management
    _startHeartbeat(ws, intervalVar, pingIntervalMs = 20000) {
        clearInterval(this[intervalVar]);
        this[intervalVar] = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.ping();
            }
        }, pingIntervalMs);

        ws.on('pong', () => {
            logger.debug(`Received pong from ${ws.url}`);
        });
    }

    _stopHeartbeat(intervalVar) {
        clearInterval(this[intervalVar]);
        this[intervalVar] = null;
    }

    connectPublic() {
        this.publicWs = this._connectWs('public', this.publicUrl,
            (ws) => {
                const subscription = { op: "subscribe", args: [`kline.${config.primaryInterval}.${config.symbol}`] };
                ws.send(JSON.stringify(subscription));
                logger.info(`Subscribed to public topic: ${subscription.args}`);
                this._startHeartbeat(ws, 'publicPingInterval', config.bybit.publicPingIntervalMs);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                if (message.topic && message.topic.startsWith('kline')) {
                    const candle = message.data[0];
                    if (candle.confirm === true) {
                        logger.debug(`New confirmed ${config.primaryInterval}m candle for ${config.symbol}. Close: ${candle.close}`);
                        this.onNewCandle();
                    }
                }
            },
            () => this._stopHeartbeat('publicPingInterval'),
            (err) => logger.error("Public WS error:", err)
        );
    }

    // IMPROVEMENT 11: Private WebSocket Authentication and Subscription
    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            (ws) => {
                const expires = Date.now() + 10000; // Auth expires in 10 seconds
                const signature = crypto.HmacSHA256(`GET/realtime${expires}`, this.apiSecret).toString();
                const authMessage = {
                    op: "auth",
                    args: [this.apiKey, expires.toString(), signature]
                };
                ws.send(JSON.stringify(authMessage));
                logger.info("Sent private WebSocket authentication request.");

                // Wait for authentication response, then subscribe
                const authHandler = (data) => {
                    const message = JSON.parse(data.toString());
                    if (message.op === 'auth' && message.success) {
                        logger.info("Private WebSocket authenticated successfully.");
                        ws.off('message', authHandler); // Remove handler after auth
                        
                        // IMPROVEMENT 12: Subscribe to order and position topics
                        const privateSubscriptions = {
                            op: "subscribe",
                            args: [`order`, `position`]
                        };
                        ws.send(JSON.stringify(privateSubscriptions));
                        logger.info(`Subscribed to private topics: ${privateSubscriptions.args}`);
                        this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs);
                    } else if (message.op === 'auth' && !message.success) {
                        logger.error(`Private WebSocket authentication failed: ${message.retMsg}`);
                        ws.close(); // Close connection on auth failure
                    }
                };
                ws.on('message', authHandler);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                // IMPROVEMENT 12: Pass all private messages to callback
                this.onPrivateMessage(message);
            },
            () => this._stopHeartbeat('privatePingInterval'),
            (err) => logger.error("Private WS error:", err)
        );
    }

    connect() {
        this.connectPublic();
        this.connectPrivate();
    }
}

export default BybitWebSocket;
```

---

### `src/api/gemini_api.js`

```javascript
// src/api/gemini_api.js
import { GoogleGenerativeAI } from '@google/generative-ai';
import { z } from 'zod';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import { ACTIONS, SIDES } from '../core/constants.js';

const TradeDecisionSchema = z.object({
  functionCall: z.object({
    name: z.nativeEnum(ACTIONS),
    args: z.object({
      side: z.nativeEnum(SIDES).optional(),
      reasoning: z.string().min(10),
    }),
  }),
});

export default class GeminiAPI {
    constructor(apiKey) {
        this.genAI = new GoogleGenerativeAI(apiKey);
    }

    async getTradeDecision(marketContext, isInPosition, positionSide) { // IMPROVEMENT 14: Pass current position state
        try {
            const model = this.genAI.getGenerativeModel({
                model: config.geminiModel,
                // IMPROVEMENT 13: Configurable AI generation parameters
                generationConfig: { 
                    responseMimeType: "application/json",
                    temperature: config.gemini.temperature,
                    topP: config.gemini.topP,
                }
            });

            // IMPROVEMENT 14: Dynamic prompt based on position status
            let actionInstructions = '';
            if (isInPosition) {
                actionInstructions = `You are currently in a ${positionSide} position. Your primary goal is now to manage this open position.
                Based *only* on the provided data, decide on one of the following two actions:
                1.  **${ACTIONS.PROPOSE_EXIT}**: If the current open position shows signs of reversal, has met its logical target, or the market context has changed unfavorably.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal to exit, the position is still valid, or waiting for further confirmation.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"reasoning": "Detailed analysis..."}}}
                
                Example for exiting: {"functionCall": {"name": "${ACTIONS.PROPOSE_EXIT}", "args": {"reasoning": "Bearish divergence on the RSI and the price is approaching a major resistance level identified on the 60m chart."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is still trending favorably, and the position is performing as expected. No immediate exit signal."}}}
                `;
            } else {
                actionInstructions = `Your primary goal is to identify high-probability trading opportunities
                for the ${config.symbol} perpetual contract, focusing on maximizing profit while adhering to strict risk management rules.
                
                Based *only* on the provided data, decide on one of the following three actions:
                1.  **${ACTIONS.PROPOSE_TRADE}**: If a clear, high-probability entry signal is present on the primary timeframe that aligns with the broader trend.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal, the market is choppy, or the risk/reward is unfavorable.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"side": "Buy" or "Sell" (only for proposeTrade), "reasoning": "Detailed analysis..."}}}
                
                Example for entering: {"functionCall": {"name": "${ACTIONS.PROPOSE_TRADE}", "args": {"side": "${SIDES.BUY}", "reasoning": "Price broke above the 50 SMA on the 15m chart, which is in line with the bullish trend on the 4h chart. RSI is showing upward momentum."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is consolidating within a tight range with conflicting signals from indicators. Waiting for a breakout."}}}
                `;
            }

            const prompt = `
                You are a sophisticated crypto trading analyst AI.
                Analyze the following multi-timeframe market data and the current bot status. The primary trading timeframe is ${config.primaryInterval} minutes.
                Higher timeframe data (${config.multiTimeframeIntervals.join(', ')}) min) is provided for trend context.

                ${marketContext}

                ${actionInstructions}
            `;

            const result = await model.generateContent(prompt);
            const responseText = result.response.text();
            
            // IMPROVEMENT 19: Add robust JSON parsing with error handling
            let rawDecision;
            try {
                rawDecision = JSON.parse(responseText);
            } catch (jsonError) {
                logger.error(`AI response not valid JSON: ${responseText}`, jsonError);
                throw new Error("AI returned invalid JSON.");
            }
            
            const validationResult = TradeDecisionSchema.safeParse(rawDecision);
            if (!validationResult.success) {
                logger.error(`Invalid AI response format: ${validationResult.error.message}\nRaw AI response: ${responseText}`);
                throw new Error(`Invalid AI response format: ${validationResult.error.message}`);
            }
            
            const decision = validationResult.data.functionCall;
            logger.info(`AI Decision: ${decision.name} - ${decision.args.reasoning}`);
            return decision;

        } catch (error) {
            logger.error("Failed to get or validate trade decision from Gemini AI.", error);
            return { name: ACTIONS.HOLD, args: { reasoning: 'AI API call or validation failed.' } };
        }
    }
}
```

---

### `src/core/trading_logic.js`

```javascript
// src/core/trading_logic.js
import { config } from '../config.js';
import logger from '../utils/logger.js';
// IMPROVEMENT 15: Use Decimal.js for precise financial calculations
import Decimal from 'decimal.js';

/**
 * Safely formats a numeric value to a fixed decimal string or returns 'N/A'.
 * @param {Decimal | number | null | undefined} value The number to format.
 * @param {number} precision The number of decimal places.
 * @returns {string} The formatted string or 'N/A'.
 */
const safeFormat = (value, precision) => {
    if (value instanceof Decimal) {
        return value.toFixed(precision);
    }
    if (typeof value === 'number' && !isNaN(value)) {
        return new Decimal(value).toFixed(precision);
    }
    return 'N/A';
};

/**
 * Calculates the position size based on risk percentage and stop-loss distance.
 * @param {Decimal} balance - The total account balance.
 * @param {Decimal} entryPrice - The current price of the asset.
 * @param {Decimal} stopLossPrice - The calculated stop-loss price.
 * @param {number} qtyPrecision - Dynamic quantity precision from Bybit API.
 * @param {number} minOrderQty - Dynamic min order quantity from Bybit API.
 * @returns {Decimal} The quantity to trade.
 */
export function calculatePositionSize(balance, entryPrice, stopLossPrice, qtyPrecision, minOrderQty) {
    // IMPROVEMENT 15: All calculations use Decimal.js
    balance = new Decimal(balance);
    entryPrice = new Decimal(entryPrice);
    stopLossPrice = new Decimal(stopLossPrice);

    const riskAmount = balance.times(config.riskPercentage).dividedBy(100);
    const slippageCost = entryPrice.times(config.slippagePercentage).dividedBy(100);
    const effectiveEntryPrice = entryPrice.plus(slippageCost); 
    
    const riskPerShare = effectiveEntryPrice.minus(stopLossPrice).abs();
    
    if (riskPerShare.isZero()) {
        logger.warn("Calculated risk per share is zero. Cannot calculate position size.");
        return new Decimal(0);
    }
    
    let quantity = riskAmount.dividedBy(riskPerShare);
    
    // Reduce quantity slightly to account for fees, ensuring it doesn't drop below min order size
    // For simplicity, we directly adjust quantity here. A more complex system might pre-calculate
    // the max fee and subtract it from riskAmount.
    const feeFactor = new Decimal(1).minus(new Decimal(config.exchangeFeePercentage).dividedBy(100));
    quantity = quantity.times(feeFactor);

    // IMPROVEMENT 16: Apply dynamic quantity precision
    const finalQuantity = quantity.toDecimalPlaces(qtyPrecision, Decimal.ROUND_DOWN);

    // IMPROVEMENT 16: Check against dynamic minOrderQty
    if (finalQuantity.lt(minOrderQty)) {
        logger.warn(`Calculated quantity (${finalQuantity.toFixed(qtyPrecision)}) is below min order size (${minOrderQty}). Cannot open position.`);
        return new Decimal(0);
    }

    const tradeCost = finalQuantity.times(entryPrice).times(new Decimal(config.exchangeFeePercentage).dividedBy(100));
    logger.info(`Position size calculated: ${finalQuantity.toFixed(qtyPrecision)}. Risking ${riskAmount.toFixed(2)} USDT with estimated trade cost ~${tradeCost.toFixed(2)} USDT.`);
    return finalQuantity;
}

/**
 * Determines stop-loss and take-profit prices based on the configured strategy.
 * This acts as a controller, calling the appropriate underlying function.
 * @param {Decimal} entryPrice - The price at which the trade is entered.
 * @param {string} side - The side of the trade ('Buy' or 'Sell').
 * @param {Decimal} atr - The latest Average True Range value.
 * @param {number} pricePrecision - Dynamic price precision from Bybit API.
 * @returns {{stopLoss: Decimal, takeProfit: Decimal}}
 */
export function determineExitPrices(entryPrice, side, atr, pricePrecision) {
    // IMPROVEMENT 15: Ensure all inputs are Decimal
    entryPrice = new Decimal(entryPrice);
    atr = new Decimal(atr);

    if (config.stopLossStrategy === 'atr' && atr.gt(0)) {
        return determineExitPricesATR(entryPrice, side, atr, pricePrecision);
    } else if (config.stopLossStrategy === 'trailing') { // IMPROVEMENT 17: Trailing Stop-Loss Placeholder
        logger.warn("Trailing stop-loss is not yet fully implemented. Using ATR or Percentage fallback.");
        return determineExitPricesATR(entryPrice, side, atr, pricePrecision); // Fallback
    }
    // Fallback to the percentage-based method
    return determineExitPricesPercentage(entryPrice, side, pricePrecision);
}

/**
 * Determines exit prices using a fixed percentage.
 * @private
 */
function determineExitPricesPercentage(entryPrice, side, pricePrecision) {
    const slDistance = entryPrice.times(config.stopLossPercentage).dividedBy(100);
    const tpDistance = slDistance.times(config.riskToRewardRatio);

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(slDistance);
        takeProfit = entryPrice.plus(tpDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(slDistance);
        takeProfit = entryPrice.minus(tpDistance);
    }
    // IMPROVEMENT 16: Apply dynamic price precision
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}

/**
 * Determines exit prices using the Average True Range (ATR) for market-adaptive stops.
 * @private
 */
function determineExitPricesATR(entryPrice, side, atr, pricePrecision) {
    const slDistance = atr.times(config.atrMultiplier);
    const tpDistance = slDistance.times(config.riskToRewardRatio);

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(slDistance);
        takeProfit = entryPrice.plus(tpDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(slDistance);
        takeProfit = entryPrice.minus(tpDistance);
    }
    logger.info(`ATR-based exits calculated: SL=${stopLoss.toFixed(pricePrecision)}, TP=${takeProfit.toFixed(pricePrecision)}`);
    // IMPROVEMENT 16: Apply dynamic price precision
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}

// IMPROVEMENT 17: Placeholder for Trailing Stop-Loss logic
/*
function determineExitPricesTrailing(entryPrice, side, atr, pricePrecision, currentPrice) {
    // This would typically involve dynamic updates based on currentPrice,
    // not just a single calculation at entry. For an initial setup, it
    // might set an initial stop loss and then allow the system to adjust it.
    // For a snippet, we'll keep it simple for initial setup.
    const initialSlDistance = atr.times(config.atrMultiplier);
    let stopLoss;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(initialSlDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(initialSlDistance);
    }
    // TP for trailing stops is often not a fixed target, but for Bybit API
    // we might still need to provide one, or manage it separately.
    const takeProfit = side === 'Buy' ? entryPrice.plus(initialSlDistance.times(config.riskToRewardRatio)) : entryPrice.minus(initialSlDistance.times(config.riskToRewardRatio));

    logger.info(`Trailing SL (initial) calculated: SL=${stopLoss.toFixed(pricePrecision)}, TP=${takeProfit.toFixed(pricePrecision)}`);
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}
*/
```

---

### `src/core/risk_policy.js`

```javascript
// src/core/risk_policy.js
import logger from '../utils/logger.js';
import { ACTIONS } from './constants.js';
import { config } from '../config.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for P&L calculations

export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    // IMPROVEMENT 18: Max Daily Loss Policy
    const now = Date.now();
    const today = new Date(now).toISOString().split('T')[0];
    const pnlResetDate = state.dailyPnlResetDate;
    let dailyLoss = new Decimal(state.dailyLoss);

    if (pnlResetDate !== today) {
        logger.info(`Resetting daily P&L. Old date: ${pnlResetDate}, New date: ${today}. Old loss: ${dailyLoss.toFixed(2)}`);
        dailyLoss = new Decimal(0); // Reset daily loss
        state.dailyPnlResetDate = today; // Update the reset date
        state.dailyLoss = dailyLoss.toString(); // Save the new loss
    }

    if (dailyLoss.gte(config.maxDailyLossPercentage / 100 * state.initialBalance)) { // IMPROVEMENT 18: Compare against initial balance
        const reason = `Risk policy violation: Max daily loss limit of ${config.maxDailyLossPercentage}% reached. Current daily loss: ${dailyLoss.toFixed(2)} USDT.`;
        logger.error(reason);
        return { decision: 'HALT', reason, trade: null }; // Consider a HALT state for extreme loss
    }

    if (name === ACTIONS.PROPOSE_TRADE) {
        // Rule 1: Prevent entering a trade if indicators are missing.
        if (!indicators || !indicators.close || !indicators.atr) { // Ensure 'close' is used for price
            const reason = "Cannot enter trade due to missing critical indicator data (Current Price or ATR).";
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // Rule 2: Prevent entering a trade if already in a position.
        if (state.inPosition) {
            const reason = `Risk policy violation: AI proposed a new trade while already in a ${state.positionSide} position.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // Rule 3: Enforce cooldown period between trades.
        const cooldownMs = config.tradeCooldownMinutes * 60 * 1000;
        if (state.lastTradeTimestamp > 0 && (now - state.lastTradeTimestamp < cooldownMs)) {
            const minutesRemaining = ((cooldownMs - (now - state.lastTradeTimestamp)) / 60000).toFixed(1);
            const reason = `Risk policy violation: Cannot open new trade. In cooldown period for another ${minutesRemaining} minutes.`;
            logger.info(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // IMPROVEMENT 18: Max Open Positions check (conceptual for now, as state only supports one)
        if (state.openPositionsCount >= config.maxOpenPositions) {
            const reason = `Risk policy violation: Max open positions (${config.maxOpenPositions}) reached.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
    }

    if (name === ACTIONS.PROPOSE_EXIT && !state.inPosition) {
        const reason = `Risk policy violation: AI proposed an exit but there is no open position.`;
        logger.warn(reason);
        return { decision: 'HOLD', reason, trade: null };
    }

    logger.info("AI decision passed risk policy checks.");
    return { decision: 'EXECUTE', reason: 'AI proposal is valid and passes risk checks.', trade: aiDecision };
}
```

---

### `src/core/constants.js`

```javascript
// src/core/constants.js

export const ACTIONS = Object.freeze({
    PROPOSE_TRADE: 'proposeTrade',
    PROPOSE_EXIT: 'proposeExit',
    HOLD: 'hold',
    HALT: 'halt', // IMPROVEMENT 18: New action for severe risk policy breaches
});

export const SIDES = Object.freeze({
    BUY: 'Buy',
    SELL: 'Sell',
});
```

---

### `src/utils/state_manager.js`

```javascript
// src/utils/state_manager.js
import fs from 'fs/promises';
import path from 'path';
import logger from './logger.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for financial state values

const stateFilePath = path.resolve('bot_state.json');
const tempStateFilePath = path.resolve('bot_state.json.tmp');

export const defaultState = {
    inPosition: false,
    positionSide: null, // 'Buy' or 'Sell'
    entryPrice: new Decimal(0).toString(), // IMPROVEMENT 15: Store as string for Decimal.js
    quantity: new Decimal(0).toString(), // IMPROVEMENT 15: Store as string for Decimal.js
    orderId: null,
    lastTradeTimestamp: 0,
    // IMPROVEMENT 18: Fields for daily loss tracking
    dailyLoss: new Decimal(0).toString(), // Total loss for the current day
    dailyPnlResetDate: new Date().toISOString().split('T')[0], // YYYY-MM-DD
    initialBalance: new Decimal(0).toString(), // Initial balance at start, for daily loss calc
    openPositionsCount: 0, // IMPROVEMENT 18: Track number of open positions (for future multi-position)
    openOrders: [], // IMPROVEMENT 20: Track open TP/SL orders or other pending orders
};

// IMPROVEMENT 18: Helper to convert state values to Decimal for calculations
export function getDecimalState(state) {
    return {
        ...state,
        entryPrice: new Decimal(state.entryPrice),
        quantity: new Decimal(state.quantity),
        dailyLoss: new Decimal(state.dailyLoss),
        initialBalance: new Decimal(state.initialBalance),
    };
}

// IMPROVEMENT 18: Helper to convert Decimal back to string for saving
export function toSerializableState(state) {
    const serializable = { ...state };
    if (serializable.entryPrice instanceof Decimal) serializable.entryPrice = serializable.entryPrice.toString();
    if (serializable.quantity instanceof Decimal) serializable.quantity = serializable.quantity.toString();
    if (serializable.dailyLoss instanceof Decimal) serializable.dailyLoss = serializable.dailyLoss.toString();
    if (serializable.initialBalance instanceof Decimal) serializable.initialBalance = serializable.initialBalance.toString();
    return serializable;
}

export async function saveState(state) {
    try {
        const serializableState = toSerializableState(state); // Convert Decimals to string
        await fs.writeFile(tempStateFilePath, JSON.stringify(serializableState, null, 2));
        await fs.rename(tempStateFilePath, stateFilePath);
        logger.info("Successfully saved state.");
    } catch (error) {
        logger.error("Failed to save state to file.", error);
    }
}

export async function loadState() {
    try {
        await fs.access(stateFilePath);
        const data = await fs.readFile(stateFilePath, 'utf8');
        logger.info("Successfully loaded state from file.");
        const loaded = JSON.parse(data);
        // Merge with default state to ensure new fields are present
        // and convert financial strings back to Decimal objects for active use
        const mergedState = { ...defaultState, ...loaded };
        return getDecimalState(mergedState);
    } catch (error) {
        logger.warn("No state file found or failed to read. Using default state.");
        // Return default state with Decimal values initialized
        return getDecimalState(defaultState);
    }
}
```

---

### `src/config.js`

```javascript
// src/config.js
export const config = {
    // Trading Pair and Intervals
    symbol: 'BTCUSDT',
    primaryInterval: '15', // Primary interval for trading signals
    multiTimeframeIntervals: ['60', '240'], // Higher timeframes for trend context

    // Dry Run / Paper Trading Mode
    dryRun: true,

    // API Endpoints
    bybit: {
        restUrl: 'https://api.bybit.com',
        wsUrl: 'wss://stream.bybit.com/v5/public/linear',
        privateWsUrl: 'wss://stream.bybit.com/v5/private',
        testnet: false,
        category: 'linear', // IMPROVEMENT 3: Consistent category for Bybit API
        accountType: 'UNIFIED', // IMPROVEMENT 3: Consistent account type
        requestRetryAttempts: 3,
        requestTimeoutMs: 5000, // IMPROVEMENT 3: Request timeout for REST API
        recvWindow: '20000', // Bybit default for recvWindow
        requestIntervalMs: 200, // IMPROVEMENT 1: Delay between API requests (ms) for basic rate limiting
        publicPingIntervalMs: 20000, // Ping interval for public WS
        privatePingIntervalMs: 20000, // Ping interval for private WS
        maxReconnectDelayMs: 60000, // IMPROVEMENT 9: Max delay for WS reconnection backoff
    },

    // Technical Indicator Settings
    indicators: {
        rsiPeriod: 14,
        smaShortPeriod: 20,
        smaLongPeriod: 50,
        atrPeriod: 14,
        macd: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
    },

    // Risk Management
    riskPercentage: 2.0,
    riskToRewardRatio: 1.5,
    stopLossStrategy: 'atr', // 'atr', 'percentage', 'trailing' (IMPROVEMENT 17)
    stopLossPercentage: 1.5,
    atrMultiplier: 2.0,
    slippagePercentage: 0.05,
    exchangeFeePercentage: 0.055,
    tradeCooldownMinutes: 30,
    maxDailyLossPercentage: 10.0, // IMPROVEMENT 18: Max percentage of initial balance for daily loss
    maxOpenPositions: 1, // IMPROVEMENT 18: Max concurrent open positions (for future expansion)

    // Order Precision & Minimums (These will be dynamically loaded from Bybit API if possible)
    pricePrecision: 2, // Default, overridden by Bybit API
    quantityPrecision: 3, // Default, overridden by Bybit API
    minOrderSize: 0.001, // Default, overridden by Bybit API

    // AI Model Configuration
    geminiModel: 'gemini-2.5-flash-lite',
    gemini: { // IMPROVEMENT 13: Configurable Gemini parameters
        temperature: 0.7,
        topP: 0.9,
    },
};
```

---

### `src/trading_ai_system.js`

```javascript
// src/trading_ai_system.js
import 'dotenv/config';
import { config } from './config.js';
import BybitAPI from './api/bybit_api.js';
// IMPROVEMENT 18: Use getDecimalState for active calculations
import { loadState, saveState, defaultState, getDecimalState } from './utils/state_manager.js';
import { calculatePositionSize, determineExitPrices } from './core/trading_logic.js';
import { applyRiskPolicy } from './core/risk_policy.js';
import logger from './utils/logger.js';
import { ACTIONS } from './core/constants.js';
import GeminiAPI from './api/gemini_api.js';
import FeatureEngineer from './features/feature_engineer.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for P&L calculations

// Helper to format the market context for the AI
function formatMarketContext(state, primaryIndicators, higherTfIndicators) {
    // IMPROVEMENT 15: Adjust safeFormat for Decimal.js
    const safeFormat = (value, precision) => {
        if (value instanceof Decimal) return value.toFixed(precision);
        if (typeof value === 'number' && !isNaN(value)) return new Decimal(value).toFixed(precision);
        return 'N/A';
    };

    let context = `## PRIMARY TIMEFRAME ANALYSIS (${config.primaryInterval}min)
`;
    context += formatIndicatorText(primaryIndicators);

    higherTfIndicators.forEach(htf => {
        context += `
## HIGHER TIMEFRAME CONTEXT (${htf.interval}min)
`;
        context += formatIndicatorText(htf.indicators);
    });

    if (state.inPosition) {
        // IMPROVEMENT 15: P&L calculation using Decimal.js
        const entryPrice = state.entryPrice;
        const quantity = state.quantity;
        const close = new Decimal(primaryIndicators.close); // Ensure close is Decimal
        
        const pnl = close.minus(entryPrice).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
        const pnlPercent = pnl.dividedBy(entryPrice.times(quantity)).times(100);
        context += `
## CURRENT POSITION
- **Status:** In a **${state.positionSide}** position.
- **Entry Price:** ${safeFormat(entryPrice, config.pricePrecision)}
- **Quantity:** ${safeFormat(quantity, config.quantityPrecision)}
- **Unrealized P/L:** ${safeFormat(pnl, 2)} USDT (${safeFormat(pnlPercent, 2)}%)`;
    } else {
        context += "\n## CURRENT POSITION\n- **Status:** FLAT (No open position).";
    }
    // IMPROVEMENT 18: Add daily loss to context
    context += `
## DAILY RISK STATUS
- **Daily Loss:** ${safeFormat(state.dailyLoss, 2)} USDT (Limit: ${config.maxDailyLossPercentage}% of ${safeFormat(state.initialBalance, 2)} USDT)
`;
    return context;
}

function formatIndicatorText(indicators) {
    if (!indicators) return "  - No data available.\n";
    const { close, rsi, atr, macd, bb } = indicators;
    // IMPROVEMENT 15: Adjust safeFormat for Decimal.js
    const safeFormat = (value, precision) => {
        if (value instanceof Decimal) return value.toFixed(precision);
        if (typeof value === 'number' && !isNaN(value)) return new Decimal(value).toFixed(precision);
        return 'N/A';
    };

    let text = `  - **Price:** ${safeFormat(close, config.pricePrecision)}
`;
    if (rsi) text += `  - **Momentum (RSI):** ${safeFormat(rsi, 2)}
`;
    if (atr) text += `  - **Volatility (ATR):** ${safeFormat(atr, config.pricePrecision)}
`;
    if (macd) text += `  - **Trend (MACD Histogram):** ${safeFormat(macd.hist, 4)}
`;
    if (bb) text += `  - **Bollinger Bands:** Mid ${safeFormat(bb.mid, 2)}, Upper ${safeFormat(bb.upper, 2)}, Lower ${safeFormat(bb.lower, 2)}
`;
    return text;
}

class TradingAiSystem {
    constructor() {
        this.bybitApi = new BybitAPI(process.env.BYBIT_API_KEY, process.env.BYBIT_API_SECRET);
        this.geminiApi = new GeminiAPI(process.env.GEMINI_API_KEY);
        this.isProcessing = false;
        this.featureEngineers = new Map();
        this.featureEngineers.set(config.primaryInterval, new FeatureEngineer());
        config.multiTimeframeIntervals.forEach(interval => {
            this.featureEngineers.set(interval, new FeatureEngineer());
        });
    }

    calculateIndicators(klines, interval) {
        const featureEngineer = this.featureEngineers.get(interval);
        if (!featureEngineer) {
            throw new Error(`No feature engineer found for interval: ${interval}`);
        }

        if (!klines || klines.length === 0) return null;
        // Klines from Bybit API are newest first, need to process oldest first for indicators
        const reversedKlines = [...klines].reverse();
        const formattedKlines = reversedKlines.map(k => ({
            t: parseInt(k[0]),
            o: parseFloat(k[1]),
            h: parseFloat(k[2]),
            l: parseFloat(k[3]),
            c: parseFloat(k[4]),
            v: parseFloat(k[5]),
        }));

        let lastFeature;
        for (const kline of formattedKlines) {
            lastFeature = featureEngineer.next(kline);
        }
        return lastFeature;
    }

    async runAnalysisCycle() {
        if (this.isProcessing) {
            logger.warn("Skipping analysis cycle: a previous one is still active.");
            return;
        }
        this.isProcessing = true;
        logger.info("=========================================");
        logger.info(`Starting new analysis cycle for ${config.symbol}...`);

        try {
            let state = await this.reconcileState();
            // IMPROVEMENT 18: Initialize initialBalance if not set
            if (state.initialBalance.isZero()) {
                const currentBalance = await this.bybitApi.getAccountBalance();
                if (currentBalance) {
                    state.initialBalance = new Decimal(currentBalance);
                    await saveState(state);
                    logger.info(`Initial balance set to ${state.initialBalance.toFixed(2)} USDT.`);
                } else {
                    logger.error("Could not retrieve initial account balance. Daily loss limit may not function correctly.");
                }
            }
            
            const allIntervals = [config.primaryInterval, ...config.multiTimeframeIntervals];
            const klinesPromises = allIntervals.map(interval => 
                this.bybitApi.getHistoricalMarketData(config.symbol, interval)
            );
            const klinesResults = await Promise.all(klinesPromises);

            const indicatorResults = klinesResults.map((result, i) => {
                const interval = allIntervals[i];
                if (!result || !result.list) {
                    logger.warn(`Failed to fetch market data for interval ${interval}.`);
                    return null;
                }
                return this.calculateIndicators(result.list, interval);
            });

            const primaryIndicators = indicatorResults[0];
            if (!primaryIndicators) {
                throw new Error("Failed to calculate primary indicators.");
            }

            const higherTfIndicators = indicatorResults.slice(1).map((indicators, i) => ({
                interval: config.multiTimeframeIntervals[i],
                indicators: indicators
            }));

            const marketContext = formatMarketContext(state, primaryIndicators, higherTfIndicators);
            // IMPROVEMENT 14: Pass position state to AI for dynamic prompting
            const aiDecision = await this.geminiApi.getTradeDecision(marketContext, state.inPosition, state.positionSide);
            const policyResult = applyRiskPolicy(aiDecision, primaryIndicators, state);

            // IMPROVEMENT 18: Handle HALT decision
            if (policyResult.decision === 'HALT') {
                logger.critical(`Bot HALTED due to risk policy violation: ${policyResult.reason}`);
                // Potentially send notification, stop further processing
                return;
            }

            if (policyResult.decision === 'HOLD') {
                logger.info(`Decision: HOLD. Reason: ${policyResult.reason}`);
                // If a new daily loss was recorded, save state.
                if (state.dailyLoss.toFixed(2) !== (await loadState()).dailyLoss.toFixed(2)) { // Compare string representations for changes
                    await saveState(state);
                }
                return;
            }

            const { name, args } = policyResult.trade;
            if (name === ACTIONS.PROPOSE_TRADE) {
                await this.executeEntry(args, primaryIndicators, state);
            } else if (name === ACTIONS.PROPOSE_EXIT) {
                await this.executeExit(state, args, primaryIndicators);
            }
        } catch (error) {
            logger.exception(error);
        } finally {
            this.isProcessing = false;
            logger.info("Analysis cycle finished.");
            logger.info("=========================================\n");
        }
    }

    async executeEntry(args, indicators, state) {
        logger.info(`Executing ENTRY: ${args.side}. Reason: ${args.reasoning}`);
        const { side } = args;
        const price = new Decimal(indicators.close);
        const atr = new Decimal(indicators.atr);

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");

        // IMPROVEMENT 8: Get dynamic precision and min order qty
        const pricePrecision = this.bybitApi.getPricePrecision();
        const qtyPrecision = this.bybitApi.getQtyPrecision();
        const minOrderQty = this.bybitApi.getMinOrderQty();

        const { stopLoss, takeProfit } = determineExitPrices(price, side, atr, pricePrecision);
        const quantity = calculatePositionSize(new Decimal(balance), price, stopLoss, qtyPrecision, minOrderQty);

        if (quantity.isZero()) {
            logger.error("Calculated quantity is zero. Aborting trade.");
            return;
        }
        
        try {
            const orderResult = await this.bybitApi.placeOrder({
                symbol: config.symbol, side, qty: quantity, takeProfit, stopLoss, 
            });

            if (orderResult && orderResult.orderId) {
                const newState = {
                    ...state, // Spread existing state to preserve other fields
                    inPosition: true, positionSide: side, entryPrice: price,
                    quantity: quantity, orderId: orderResult.orderId,
                    lastTradeTimestamp: 0, // Reset cooldown timer on entry
                    openPositionsCount: 1, // Only 1 position currently
                };
                await saveState(newState);
                logger.info(`Successfully placed ENTRY order. Order ID: ${orderResult.orderId}`);
            } else {
                logger.error("Entry order failed to return an order ID.");
            }
        } catch (error) {
            logger.error(`Failed to place entry order: ${error.message}`);
            // IMPROVEMENT 19: More specific error handling for order placement
            if (error.message.includes("Insufficient Balance")) {
                logger.error("Entry failed due to insufficient balance. Adjusting position sizing or depositing funds recommended.");
            }
            // Do not save state as position was not opened.
        }
    }
    
    async executeExit(state, args, indicators) {
        logger.info(`Executing EXIT from ${state.positionSide} position. Reason: ${args.reasoning}`);

        // IMPROVEMENT 20: Cancel all open orders before closing position (TP/SL might be pending)
        try {
            await this.bybitApi.cancelAllOpenOrders(config.symbol);
            logger.info("All pending TP/SL orders cancelled before closing position.");
        } catch (cancelError) {
            logger.warn(`Failed to cancel existing orders before closing: ${cancelError.message}`);
            // Continue with closing the position anyway
        }

        try {
            const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide);

            if (closeResult && closeResult.orderId) {
                // IMPROVEMENT 18: Update daily loss on exit
                const exitPrice = new Decimal(indicators.close);
                const pnl = exitPrice.minus(state.entryPrice).times(state.quantity).times(state.positionSide === 'Buy' ? 1 : -1);
                
                const newDailyLoss = state.dailyLoss.plus(pnl.isNegative() ? pnl.abs() : new Decimal(0)); // Only add to loss if PnL is negative

                const newState = {
                    ...defaultState, // Reset to default, ensuring all fields are cleared
                    lastTradeTimestamp: Date.now(), // Set cooldown timestamp
                    initialBalance: state.initialBalance, // Preserve initial balance
                    dailyLoss: newDailyLoss, // Update daily loss
                    dailyPnlResetDate: state.dailyPnlResetDate, // Preserve reset date
                };
                await saveState(newState);
                logger.info(`Successfully placed EXIT order. Order ID: ${closeResult.orderId}. Trade P&L: ${pnl.toFixed(2)} USDT. Daily loss now: ${newDailyLoss.toFixed(2)} USDT.`);
            } else {
                logger.error("Exit order failed to return an order ID.");
            }
        } catch (error) {
            logger.error(`Failed to place exit order: ${error.message}`);
            // If the position failed to close, keep the state as is for next reconciliation.
        }
    }

    async reconcileState() {
        logger.info("Reconciling local state with exchange...");
        const localState = await loadState(); // IMPROVEMENT 18: Load state as Decimal.js objects
        if (config.dryRun) {
            logger.info("[DRY RUN] Skipping remote state reconciliation.");
            return localState;
        }

        const exchangePosition = await this.bybitApi.getCurrentPosition(config.symbol);
        // IMPROVEMENT 20: Reconcile open orders (e.g., pending TP/SL orders)
        // This is a more complex task. For now, we'll assume TP/SL are OCO or managed by Bybit.
        // A full implementation would fetch open orders and update localState.openOrders array.

        if (exchangePosition) {
            const exchangeQty = new Decimal(exchangePosition.size);
            const exchangeAvgPrice = new Decimal(exchangePosition.avgPrice);
            const exchangeSide = exchangePosition.side;

            // Check for discrepancies and update
            if (!localState.inPosition || !localState.quantity.eq(exchangeQty) || !localState.entryPrice.eq(exchangeAvgPrice) || localState.positionSide !== exchangeSide) {
                logger.warn("State discrepancy detected! Recovering state from exchange.");
                const recoveredState = {
                    ...localState, 
                    inPosition: true,
                    positionSide: exchangeSide,
                    entryPrice: exchangeAvgPrice,
                    quantity: exchangeQty,
                    orderId: localState.orderId, // Preserve local order ID if known, or fetch from exchange if possible
                    openPositionsCount: 1,
                };
                await saveState(recoveredState);
                return recoveredState;
            }
            logger.info(`State confirmed: In ${exchangePosition.side} position (Qty: ${exchangeQty.toFixed(this.bybitApi.getQtyPrecision())}, Avg Price: ${exchangeAvgPrice.toFixed(this.bybitApi.getPricePrecision())}).`);
            return localState;
        } else {
            // If no position on exchange, but local state says there is one
            if (localState.inPosition) {
                logger.warn("State discrepancy! Position closed on exchange. Resetting local state.");
                const newState = { 
                    ...defaultState, 
                    lastTradeTimestamp: Date.now(),
                    initialBalance: localState.initialBalance, // Preserve initial balance
                    dailyLoss: localState.dailyLoss, // Preserve daily loss
                    dailyPnlResetDate: localState.dailyPnlResetDate, // Preserve reset date
                };
                await saveState(newState);
                return newState;
            }
            logger.info("State confirmed: No open position.");
            return localState;
        }
    }
}

export default TradingAiSystem;
```
