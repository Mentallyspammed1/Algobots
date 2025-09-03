Here are 20 update and improvement code snippets for the provided codebase, focusing on robustness, configurability, and advanced features.

---

**1. `src/api/bybit_api.js` - Enhanced Request Queue with Basic Retry**
This improvement adds a basic retry mechanism to the request queue processing, allowing transient errors (e.g., rate limits, temporary network issues) to be retried a few times before failing.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// IMPROVEMENT 1: Simple Request Queue for Rate Limiting and Retry
const requestQueue = [];
let isProcessingQueue = false;

// ... (existing PlaceOrderSchema and BybitAPI constructor) ...

    // NEW: Internal request method with retry logic
    async _request(method, endpoint, params = {}, isPrivate = true, retryCount = 0) { // Add retryCount parameter
        return new Promise((resolve, reject) => {
            requestQueue.push({ method, endpoint, params, isPrivate, resolve, reject, retryCount });
            this._processQueue();
        });
    }

    async _processQueue() {
        if (isProcessingQueue) return;
        isProcessingQueue = true;

        while (requestQueue.length > 0) {
            const request = requestQueue.shift(); // Get the request object
            const { method, endpoint, params, isPrivate, resolve, reject, retryCount } = request; // Destructure all properties

            try {
                // Delay to respect Bybit's general rate limits
                await sleep(config.bybit.requestIntervalMs);

                const result = await this._makeRequest(method, endpoint, params, isPrivate);
                resolve(result);
            } catch (error) {
                // IMPROVEMENT 1: Implement retry logic for specific errors
                if (retryCount < config.bybit.maxRetries && error.message.includes('Bybit API Error')) { // Only retry specific API errors
                    const delay = Math.min(config.bybit.maxRetryDelayMs, Math.pow(2, retryCount) * 1000); // Exponential backoff
                    logger.warn(`API request failed, retrying in ${delay / 1000}s (attempt ${retryCount + 1}): ${error.message}`);
                    requestQueue.unshift({ ...request, retryCount: retryCount + 1 }); // Re-add to front of queue with incremented retry count
                    await sleep(delay); // Wait before retrying
                } else {
                    reject(error); // Reject if max retries reached or it's a non-retryable error
                }
            }
        }
        isProcessingQueue = false;
    }

    // ... (rest of _makeRequest and other methods) ...
```
**`src/config.js` Update for Improvement 1:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    bybit: {
        // ... (existing bybit config) ...
        requestIntervalMs: 200, // Delay between queued requests for rate limiting
        maxRetries: 3,          // Max retries for failed API requests
        maxRetryDelayMs: 10000, // Max delay for exponential backoff (10 seconds)
    },
    // ... (rest of config) ...
};
```

---

**2. `src/api/bybit_api.js` - Axios Interceptors for Robust Error Reporting**
This enhances the `axios` interceptor to provide more specific and actionable error messages, including the Bybit `retCode` and `retMsg`.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        // ... (existing constructor code) ...

        this.axiosInstance.interceptors.response.use(
            response => {
                logger.debug(`API Response [${response.config.method}] ${response.config.url}: Status ${response.status}`);
                return response;
            },
            error => {
                logger.error(`API Request Error [${error.config?.method}] ${error.config?.url}: ${error.message}`);
                if (error.response) {
                    logger.error(`Response data: ${JSON.stringify(error.response.data)}`);
                    const retCode = error.response.data?.retCode;
                    const retMsg = error.response.data?.retMsg;
                    // IMPROVEMENT 2: Detailed error reporting and throwing
                    if (retCode !== undefined) {
                        const specificError = `Bybit API Error (${retCode}): ${retMsg || 'Unknown error'}. Request: ${error.config?.url}`;
                        logger.error(specificError);
                        // Enhance with specific known error codes for more actionable advice
                        if (retCode === 10001) throw new Error(`Authentication Failed: Invalid API key/signature. Check credentials. (${retCode})`);
                        if (retCode === 110001) throw new Error(`Trading Error: Insufficient Balance. (${retCode})`);
                        if (retCode === 110007) throw new Error(`Trading Error: Order quantity too small. (${retCode})`);
                        throw new Error(specificError); // Throw a general Bybit API error
                    }
                } else if (error.request) {
                    // The request was made but no response was received (e.g., network error, timeout)
                    logger.error(`No response received for [${error.config?.method}] ${error.config?.url}. Network or Timeout error.`);
                    throw new Error(`Network Error: No response from Bybit. Check internet or API status.`);
                }
                // Fallback for other errors (e.g., config error)
                return Promise.reject(new Error(`General Request Error: ${error.message}`));
            }
        );

        // ... (rest of constructor) ...
    }
    // ... (rest of class) ...
}
```

---

**3. `src/api/bybit_api.js` - Dynamic Precision & Min Order Qty in `placeOrder`**
This ensures that quantities and prices are formatted according to the exchange's symbol information, preventing `INVALID_QUANTITY` or `INVALID_PRICE` errors.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

export default class BybitAPI {
    // ... (constructor and other methods) ...

    async placeOrder(order) {
        // ... (existing validation) ...
        const validatedOrder = validationResult.data;

        const { symbol, side, qty, takeProfit, stopLoss, orderType, price } = validatedOrder;
        
        // IMPROVEMENT 3: Apply dynamic precision and min order size fetched from symbolInfo
        const qtyPrecision = this.getQtyPrecision();
        const pricePrecision = this.getPricePrecision();
        const minOrderQty = this.getMinOrderQty();

        const qtyToPlace = new Decimal(qty).toDecimalPlaces(qtyPrecision, Decimal.ROUND_DOWN); // Ensure quantity is within step size
        const tpToPlace = takeProfit !== undefined && takeProfit !== 0 ? new Decimal(takeProfit).toDecimalPlaces(pricePrecision) : undefined;
        const slToPlace = stopLoss !== undefined && stopLoss !== 0 ? new Decimal(stopLoss).toDecimalPlaces(pricePrecision) : undefined;
        const priceToPlace = price !== undefined ? new Decimal(price).toDecimalPlaces(pricePrecision) : undefined;

        // Ensure minimum order quantity check is robust
        if (qtyToPlace.lt(minOrderQty)) {
            throw new Error(`Order quantity ${qtyToPlace.toFixed(qtyPrecision)} is below minimum order quantity ${minOrderQty.toFixed(qtyPrecision)} for ${symbol}.`);
        }
        if (qtyToPlace.eq(0)) { // Ensure quantity is not zero after rounding
            throw new Error(`Order quantity rounded to zero for ${symbol}. Original: ${qty}`);
        }

        const log = `Placing order: ${side} ${qtyToPlace.toFixed(qtyPrecision)} ${symbol} | Type: ${orderType} | Price: ${priceToPlace || 'N/A'} | TP: ${tpToPlace || 'N/A'}, SL: ${slToPlace || 'N/A'}`;
        if (config.dryRun) {
            logger.info(`[DRY RUN] ${log}`);
            return { orderId: `dry-run-${Date.now()}` };
        }
        logger.info(log);

        const orderParams = {
            category: config.bybit.category,
            symbol, side, orderType,
            qty: qtyToPlace.toString(), // Bybit API expects string for qty
            ...(orderType !== 'Market' && priceToPlace && { price: priceToPlace.toString() }), // price for Limit/PostOnly
            ...(tpToPlace && { takeProfit: tpToPlace.toString() }),
            ...(slToPlace && { stopLoss: slToPlace.toString() }),
            timeInForce: 'GTC',
            // IMPROVEMENT: Optionally add `reduceOnly: true` for closing orders if desired
        };
        
        return this._request('POST', '/v5/order/create', orderParams);
    }

    // ... (rest of class) ...
}
```

---

**4. `src/api/bybit_api.js` - `PlaceOrderSchema` with Conditional `price` Validation**
This refines the Zod schema to make the `price` field required only when the `orderType` is `Limit` or `PostOnly`, aligning with Bybit's API requirements.

```javascript
// src/api/bybit_api.js
// ... (existing imports) ...
import { z } from 'zod';

// IMPROVEMENT 4: Schema for placeOrder parameters with conditional price
const PlaceOrderSchema = z.object({
    symbol: z.string(),
    side: z.enum(['Buy', 'Sell']),
    qty: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).refine(n => n > 0, "Quantity must be positive."),
    takeProfit: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    stopLoss: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    orderType: z.enum(['Market', 'Limit', 'PostOnly']).default('Market'),
    price: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(), // Optional by default
}).superRefine((data, ctx) => { // Refine to make price mandatory for Limit/PostOnly
    if (data.orderType !== 'Market' && (data.price === undefined || data.price === null)) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Price is required for Limit or PostOnly orders.",
            path: ['price'],
        });
    }
});

// ... (rest of file) ...
```

---

**5. `src/api/bybit_api.js` - New `cancelOrder` Method**
Adds a method to cancel a specific open order by its ID, which is a common requirement for order management.

```javascript
// src/api/bybit_api.js
// ... (existing imports and class definition) ...

export default class BybitAPI {
    // ... (existing methods) ...

    // IMPROVEMENT 5: Method to cancel a specific order by ID
    async cancelOrder(symbol, orderId) {
        logger.info(`Attempting to cancel order ${orderId} for ${symbol}.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would cancel order ${orderId} for ${symbol}.`);
            return { result: 'dry-run-cancel-order' };
        }
        try {
            const result = await this._request('POST', '/v5/order/cancel', {
                category: config.bybit.category,
                symbol: symbol,
                orderId: orderId,
            });
            logger.info(`Successfully cancelled order ${orderId} for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to cancel order ${orderId} for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    // IMPROVEMENT 20: Method to cancel all open orders for a symbol (already provided, including it for context)
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

**6. `src/api/bybit_api.js` - Configurable `requestIntervalMs` for Rate Limiting**
This explicitly uses the `requestIntervalMs` from `config.js` to control the delay between API requests, making rate limiting behavior configurable.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

class BybitAPI {
    // ... (constructor and other methods) ...

    async _processQueue() {
        if (isProcessingQueue) return;
        isProcessingQueue = true;

        while (requestQueue.length > 0) {
            const request = requestQueue.shift();
            const { method, endpoint, params, isPrivate, resolve, reject, retryCount } = request;

            try {
                // IMPROVEMENT 6: Delay to respect Bybit's general rate limits using configured interval
                await sleep(config.bybit.requestIntervalMs);

                const result = await this._makeRequest(method, endpoint, params, isPrivate);
                resolve(result);
            } catch (error) {
                // ... (retry logic as in improvement #1) ...
            }
        }
        isProcessingQueue = false;
    }
    // ... (rest of class) ...
}
```
**`src/config.js` Update for Improvement 6:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    bybit: {
        // ... (existing bybit config) ...
        requestIntervalMs: 200, // IMPROVEMENT 6: Delay between queued requests (in ms)
        // ... (rest of bybit config) ...
    },
    // ... (rest of config) ...
};
```

---

**7. `src/api/bybit_api.js` - Cache Symbol Info on Startup**
Ensures that the bot fetches and caches symbol trading rules (precision, min qty) upon initialization, which is crucial for correct order placement.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        // ... (existing constructor code) ...

        this.symbolInfo = {}; // IMPROVEMENT 7: Cache symbol info
        this.loadSymbolInfo(); // IMPROVEMENT 7: Load on startup
    }

    // IMPROVEMENT 7: Fetch and cache symbol information
    async loadSymbolInfo() {
        try {
            // Use _request which goes through the queue
            const result = await this._request('GET', '/v5/market/instruments-info', { category: 'linear', symbol: config.symbol }, false);
            if (result && result.list && result.list.length > 0) {
                const info = result.list[0];
                this.symbolInfo = {
                    pricePrecision: parseInt(info.priceFilter.tickSize.split('.')[1]?.length || 0),
                    qtyPrecision: parseInt(info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0),
                    minOrderQty: new Decimal(info.lotSizeFilter.minOrderQty), // Store as Decimal
                    maxOrderQty: new Decimal(info.lotSizeFilter.maxOrderQty), // Store as Decimal
                };
                logger.info(`Symbol info for ${config.symbol} loaded: Price Precision ${this.symbolInfo.pricePrecision}, Qty Precision ${this.symbolInfo.qtyPrecision}, Min Qty ${this.symbolInfo.minOrderQty.toString()}`);
            } else {
                logger.warn(`Could not load symbol info for ${config.symbol}. Using default config precisions.`);
            }
        } catch (error) {
            logger.error(`Error loading symbol info: ${error.message}. Using default config precisions.`);
        }
    }

    // Helper getters for symbol info
    getQtyPrecision() { return this.symbolInfo.qtyPrecision ?? config.bybit.qtyPrecision; }
    getPricePrecision() { return this.symbolInfo.pricePrecision ?? config.bybit.pricePrecision; }
    getMinOrderQty() { return this.symbolInfo.minOrderQty ?? new Decimal(config.bybit.minOrderSize); }
    // Add max order qty if needed: getMaxOrderQty() { return this.symbolInfo.maxOrderQty ?? new Decimal(config.bybit.maxOrderSize); }

    // ... (rest of class) ...
}
```
**`src/config.js` Update for Improvement 7:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    bybit: {
        // ... (existing bybit config) ...
        minOrderSize: 0.001, // Default min order size if API info isn't available
        // ... (rest of bybit config) ...
    },
    // ... (rest of config) ...
};
```

---

**8. `src/api/bybit_api.js` - Configurable `category` and `accountType`**
Ensures that API calls use configurable `category` (e.g., `linear`, `inverse`) and `accountType` (e.g., `UNIFIED`, `CONTRACT`) parameters, making the client more flexible.

```javascript
// src/api/bybit_api.js
// ... (existing imports and code) ...

export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        // ... (existing constructor code) ...
    }

    // ... (loadSymbolInfo and precision getters) ...

    async getHistoricalMarketData(symbol, interval, limit = 200) {
        // IMPROVEMENT 8: Dynamically use category from config
        return this._request('GET', '/v5/market/kline', { category: config.bybit.category, symbol, interval, limit }, false);
    }

    async getAccountBalance() {
        // IMPROVEMENT 8: Dynamically use accountType from config
        const result = await this._request('GET', '/v5/account/wallet-balance', { accountType: config.bybit.accountType });
        const usdtBalance = result?.list?.[0]?.coin?.find(c => c.coin === 'USDT');
        return usdtBalance ? parseFloat(usdtBalance.walletBalance) : null;
    }

    async getCurrentPosition(symbol) {
        // IMPROVEMENT 8: Dynamically use category from config
        const result = await this._request('GET', '/v5/position/list', { category: config.bybit.category, symbol });
        const position = result?.list?.find(p => p.symbol === symbol && parseFloat(p.size) > 0); // Ensure size > 0
        return position || null;
    }

    async placeOrder(order) {
        // ... (existing placeOrder code) ...
        const orderParams = {
            category: config.bybit.category, // IMPROVEMENT 8: Dynamically use category from config
            symbol, side, orderType,
            // ... (rest of orderParams) ...
        };
        return this._request('POST', '/v5/order/create', orderParams);
    }
    // ... (rest of class) ...
}
```
**`src/config.js` Update for Improvement 8:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    bybit: {
        // ... (existing bybit config) ...
        category: 'linear',     // IMPROVEMENT 8: 'linear' for USDT perpetuals
        accountType: 'UNIFIED', // IMPROVEMENT 8: 'UNIFIED' or 'CONTRACT'
        // ... (rest of bybit config) ...
    },
    // ... (rest of config) ...
};
```

---

**9. `src/api/bybit_websocket.js` - Configurable WebSocket Ping Intervals**
This externalizes the ping interval settings to `config.js`, allowing easy adjustments to maintain WebSocket connection health.

```javascript
// src/api/bybit_websocket.js
// ... (existing imports and class definition) ...

class BybitWebSocket {
    constructor(onNewCandleCallback, onPrivateMessageCallback) {
        // ... (existing constructor code) ...
    }

    // IMPROVEMENT 9: Unified ping/pong management with configurable interval
    _startHeartbeat(ws, intervalVar, pingIntervalMs) { // Pass intervalMs as argument
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

    // ... (connectPublic method) ...
    connectPublic() {
        this.publicWs = this._connectWs('public', this.publicUrl,
            (ws) => {
                // ... (subscription) ...
                this._startHeartbeat(ws, 'publicPingInterval', config.bybit.publicPingIntervalMs); // Use config value
            },
            // ... (message, close, error handlers) ...
        );
    }

    // ... (connectPrivate method) ...
    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            (ws) => {
                // ... (authentication) ...
                const authHandler = (data) => {
                    // ... (auth success/failure) ...
                        this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs); // Use config value
                    // ...
                };
                ws.on('message', authHandler);
            },
            // ... (message, close, error handlers) ...
        );
    }
    // ... (rest of class) ...
}
```
**`src/config.js` Update for Improvement 9:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    bybit: {
        // ... (existing bybit config) ...
        publicPingIntervalMs: 20000,  // IMPROVEMENT 9: Public WebSocket ping interval (20 seconds)
        privatePingIntervalMs: 20000, // IMPROVEMENT 9: Private WebSocket ping interval (20 seconds)
    },
    // ... (rest of config) ...
};
```

---

**10. `src/api/bybit_websocket.js` - Enhanced Private WS Auth Handling**
This improvement makes the private WebSocket authentication more explicit, logging authentication status and ensuring that subscriptions only proceed upon successful authentication.

```javascript
// src/api/bybit_websocket.js
// ... (existing imports and class definition) ...

class BybitWebSocket {
    // ... (constructor and other methods) ...

    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            (ws) => {
                const expires = Date.now() + 10000;
                const signature = crypto.HmacSHA256(`GET/realtime${expires}`, this.apiSecret).toString();
                const authMessage = {
                    op: "auth",
                    args: [this.apiKey, expires.toString(), signature]
                };
                ws.send(JSON.stringify(authMessage));
                logger.info("Sent private WebSocket authentication request.");

                const authHandler = (data) => {
                    const message = JSON.parse(data.toString());
                    if (message.op === 'auth') { // IMPROVEMENT 10: Check for 'auth' operation
                        if (message.success) {
                            logger.info("Private WebSocket authenticated successfully.");
                            ws.off('message', authHandler); // Remove handler after successful auth
                            
                            // IMPROVEMENT 10: Subscribe to topics ONLY after successful authentication
                            const privateSubscriptions = {
                                op: "subscribe",
                                args: [`order`, `position`]
                            };
                            ws.send(JSON.stringify(privateSubscriptions));
                            logger.info(`Subscribed to private topics: ${privateSubscriptions.args}`);
                            this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs);
                        } else {
                            logger.error(`Private WebSocket authentication failed: ${message.retMsg} (Code: ${message.retCode})`);
                            ws.close(); // Close connection on auth failure to trigger reconnect
                            // Optionally throw an error here to propagate the failure
                            // throw new Error(`Private WS Auth Failed: ${message.retMsg}`);
                        }
                    } else {
                        // This else block handles messages that are not 'auth' responses but arrive before auth is complete.
                        // For example, if Bybit sends pings or other messages immediately.
                        // We still pass them to the main handler, but keep authHandler active.
                        this.onPrivateMessage(message); // Pass to main handler
                    }
                };
                ws.on('message', authHandler);
            },
            (data) => {
                const message = JSON.parse(data.toString());
                // IMPROVEMENT 10: Pass all private messages to callback
                this.onPrivateMessage(message);
            },
            // ... (rest of handlers) ...
        );
    }
    // ... (rest of class) ...
}
```

---

**11. `src/api/bybit_websocket.js` - Log Unhandled Private WS Messages**
Adds a logging mechanism in the `onPrivateMessage` callback to catch and report any private WebSocket messages that are not explicitly handled by the bot's logic.

```javascript
// src/api/bybit_websocket.js
// ... (existing imports and class definition) ...

class BybitWebSocket {
    // ... (constructor and connectPublic) ...

    connectPrivate() {
        this.privateWs = this._connectWs('private', this.privateUrl,
            // ... (onOpen and authHandler) ...
            (data) => {
                const message = JSON.parse(data.toString());
                // IMPROVEMENT 11: Pass all private messages to callback for further processing
                // Add a check to log messages not explicitly handled if desired in the callback
                this.onPrivateMessage(message);

                // Optional: Log messages that don't match known topics if your onPrivateMessage doesn't handle everything
                if (message.topic && !['order', 'position'].includes(message.topic)) {
                    logger.debug(`Unhandled private WS message topic: ${message.topic}`, message);
                } else if (!message.topic && message.op && message.op !== 'auth' && message.type !== 'pong') {
                    logger.debug(`Unhandled private WS message (no topic, op: ${message.op}):`, message);
                }
            },
            () => this._stopHeartbeat('privatePingInterval'),
            (err) => logger.error("Private WS error:", err)
        );
    }
    // ... (rest of class) ...
}
```

---

**12. `src/api/gemini_api.js` - Dynamic `isInPosition` and `positionSide` in Prompt**
The `getTradeDecision` method already accepts `isInPosition` and `positionSide`, and the prompt uses them. This snippet emphasizes how the prompt construction dynamically adapts to the current trading state.

```javascript
// src/api/gemini_api.js
// ... (existing imports and schema) ...

export default class GeminiAPI {
    // ... (constructor) ...

    async getTradeDecision(marketContext, isInPosition, positionSide) { // IMPROVEMENT 12: Pass current position state
        try {
            const model = this.genAI.getGenerativeModel({
                // ... (existing config) ...
            });

            // IMPROVEMENT 12: Dynamic prompt based on position status
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
            } else { // No open position
                actionInstructions = `Your primary goal is to identify high-probability trading opportunities
                for the ${config.symbol} perpetual contract, focusing on maximizing profit while adhering to strict risk management rules.
                
                Based *only* on the provided data, decide on one of the following two actions:
                1.  **${ACTIONS.PROPOSE_TRADE}**: If a clear, high-probability entry signal is present on the primary timeframe that aligns with the broader trend.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal, the market is choppy, or the risk/reward is unfavorable.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"side": "Buy" or "Sell" (only for proposeTrade), "reasoning": "Detailed analysis..."}}}
                
                Example for entering: {"functionCall": {"name": "${ACTIONS.PROPOSE_TRADE}", "args": {"side": "${SIDES.BUY}", "reasoning": "Price broke above the 50 SMA on the 15m chart, which is in line with the bullish trend on the 4h chart. RSI is showing upward momentum."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is consolidating within a tight range with conflicting signals from indicators. Waiting for a breakout."}}}
                `;
            }
            // ... (rest of the prompt and decision logic) ...
        } catch (error) {
            // ... (error handling) ...
        }
    }
}
```

---

**13. `src/api/gemini_api.js` - AI Prompt Engineering for `PROPOSE_EXIT`**
This improvement demonstrates how the AI prompt is specifically engineered to guide the model to output `PROPOSE_EXIT` without needing a `side` argument, as a position exit implicitly takes the opposite side.

```javascript
// src/api/gemini_api.js
// ... (existing imports and schema) ...

export default class GeminiAPI {
    // ... (constructor) ...

    async getTradeDecision(marketContext, isInPosition, positionSide) {
        try {
            // ... (model setup) ...

            let actionInstructions = '';
            if (isInPosition) {
                // IMPROVEMENT 13: Prompt tailored for 'PROPOSE_EXIT' when in position
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
                // ... (PROPOSE_TRADE instructions) ...
            }
            // ... (rest of the prompt and decision logic) ...
        } catch (error) {
            // ... (error handling) ...
        }
    }
}
```

---

**14. `src/api/gemini_api.js` - AI Prompt for `PROPOSE_TRADE` with `side`**
This highlights the prompt section that specifically instructs the AI to include a `side` argument (Buy/Sell) when proposing a new trade, which is essential when the bot is not in a position.

```javascript
// src/api/gemini_api.js
// ... (existing imports and schema) ...

export default class GeminiAPI {
    // ... (constructor) ...

    async getTradeDecision(marketContext, isInPosition, positionSide) {
        try {
            // ... (model setup) ...

            let actionInstructions = '';
            if (isInPosition) {
                // ... (PROPOSE_EXIT instructions) ...
            } else { // No open position
                // IMPROVEMENT 14: Prompt tailored for 'PROPOSE_TRADE' with 'side' when flat
                actionInstructions = `Your primary goal is to identify high-probability trading opportunities
                for the ${config.symbol} perpetual contract, focusing on maximizing profit while adhering to strict risk management rules.
                
                Based *only* on the provided data, decide on one of the following two actions:
                1.  **${ACTIONS.PROPOSE_TRADE}**: If a clear, high-probability entry signal is present on the primary timeframe that aligns with the broader trend.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal, the market is choppy, or the risk/reward is unfavorable.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"side": "Buy" or "Sell" (only for proposeTrade), "reasoning": "Detailed analysis..."}}}
                
                Example for entering: {"functionCall": {"name": "${ACTIONS.PROPOSE_TRADE}", "args": {"side": "${SIDES.BUY}", "reasoning": "Price broke above the 50 SMA on the 15m chart, which is in line with the bullish trend on the 4h chart. RSI is showing upward momentum."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is consolidating within a tight range with conflicting signals from indicators. Waiting for a breakout."}}}
                `;
            }
            // ... (rest of the prompt and decision logic) ...
        } catch (error) {
            // ... (error handling) ...
        }
    }
}
```

---

**15. `src/core/trading_logic.js` - Decimal.js for Precise Calculations**
This improvement highlights the consistent use of `Decimal.js` throughout the `trading_logic` to prevent floating-point inaccuracies in financial calculations.

```javascript
// src/core/trading_logic.js
import { config } from '../config.js';
import logger from '../utils/logger.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal.js for precise financial calculations

// ... (safeFormat helper) ...

/**
 * Calculates the position size based on risk percentage and stop-loss distance.
 * @param {Decimal} balance - The total account balance.
 * @param {Decimal} entryPrice - The current price of the asset.
 * @param {Decimal} stopLossPrice - The calculated stop-loss price.
 * @param {number} qtyPrecision - Dynamic quantity precision from Bybit API.
 * @param {Decimal} minOrderQty - Dynamic min order quantity from Bybit API.
 * @returns {Decimal} The quantity to trade.
 */
export function calculatePositionSize(balance, entryPrice, stopLossPrice, qtyPrecision, minOrderQty) {
    // IMPROVEMENT 15: All inputs are expected to be Decimal, ensuring all calculations use Decimal.js
    // Defensive conversion, though ideally inputs should already be Decimal
    balance = new Decimal(balance);
    entryPrice = new Decimal(entryPrice);
    stopLossPrice = new Decimal(stopLossPrice);
    minOrderQty = new Decimal(minOrderQty);

    const riskAmount = balance.times(config.riskPercentage).dividedBy(100);
    const slippageCost = entryPrice.times(config.slippagePercentage).dividedBy(100);
    const effectiveEntryPrice = entryPrice.plus(slippageCost); 
    
    const riskPerShare = effectiveEntryPrice.minus(stopLossPrice).abs();
    
    if (riskPerShare.isZero()) {
        logger.warn("Calculated risk per share is zero. Cannot calculate position size.");
        return new Decimal(0);
    }
    
    let quantity = riskAmount.dividedBy(riskPerShare);
    
    // ... (fee factor and precision) ...
    // IMPROVEMENT 15: Ensure finalQuantity is Decimal for return
    const finalQuantity = quantity.times(feeFactor).toDecimalPlaces(qtyPrecision, Decimal.ROUND_DOWN);

    if (finalQuantity.lt(minOrderQty)) {
        logger.warn(`Calculated quantity (${finalQuantity.toFixed(qtyPrecision)}) is below min order size (${minOrderQty.toFixed(qtyPrecision)}). Cannot open position.`);
        return new Decimal(0);
    }
    
    // IMPROVEMENT 15: All logging also uses Decimal's toFixed
    const tradeCost = finalQuantity.times(entryPrice).times(new Decimal(config.exchangeFeePercentage).dividedBy(100));
    logger.info(`Position size calculated: ${finalQuantity.toFixed(qtyPrecision)}. Risking ${riskAmount.toFixed(2)} USDT with estimated trade cost ~${tradeCost.toFixed(2)} USDT.`);
    return finalQuantity;
}

/**
 * Determines stop-loss and take-profit prices based on the configured strategy.
 * @param {Decimal} entryPrice - The price at which the trade is entered.
 * @param {string} side - The side of the trade ('Buy' or 'Sell').
 * @param {Decimal} atr - The latest Average True Range value.
 * @param {number} pricePrecision - Dynamic price precision from Bybit API.
 * @returns {{stopLoss: Decimal, takeProfit: Decimal}}
 */
export function determineExitPrices(entryPrice, side, atr, pricePrecision) {
    // IMPROVEMENT 15: Ensure all inputs are Decimal for internal functions
    entryPrice = new Decimal(entryPrice);
    atr = new Decimal(atr);
    // ... (rest of function and internal functions also use Decimal) ...
}
// ... (rest of file) ...
```

---

**16. `src/core/trading_logic.js` - Flexible Stop Loss Strategies**
This demonstrates the dispatcher pattern in `determineExitPrices`, allowing different stop-loss strategies (e.g., ATR-based, Percentage-based) to be selected via configuration. The trailing stop is included as a placeholder.

```javascript
// src/core/trading_logic.js
// ... (existing imports and calculatePositionSize) ...

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
    entryPrice = new Decimal(entryPrice);
    atr = new Decimal(atr);

    // IMPROVEMENT 16: Dispatch based on configured stopLossStrategy
    if (config.stopLossStrategy === 'atr' && atr.gt(0)) {
        return determineExitPricesATR(entryPrice, side, atr, pricePrecision);
    } else if (config.stopLossStrategy === 'trailing') {
        logger.warn("Trailing stop-loss strategy is a placeholder; using ATR or Percentage fallback for initial SL/TP.");
        // For initial setup, trailing stop might still need an initial fixed SL/TP
        // A true trailing stop would update dynamically during the trade.
        // For this snippet, it falls back.
        return determineExitPricesATR(entryPrice, side, atr.gt(0) ? atr : new Decimal(entryPrice).times(config.stopLossPercentage).dividedBy(config.atrMultiplier).dividedBy(100), pricePrecision);
    }
    // Fallback to the percentage-based method if ATR is not positive or strategy is not recognized
    logger.info("Using percentage-based exit prices as ATR is not valid or strategy is not ATR/Trailing.");
    return determineExitPricesPercentage(entryPrice, side, pricePrecision);
}

/**
 * Determines exit prices using a fixed percentage.
 * @private
 */
function determineExitPricesPercentage(entryPrice, side, pricePrecision) {
    // ... (existing implementation) ...
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
    // ... (existing implementation) ...
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
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}

// IMPROVEMENT 16: Placeholder for Trailing Stop-Loss logic (commented out as it's typically dynamic)
/*
// For a fully functional trailing stop, this method would be more complex and likely
// involve continuous monitoring and updating of the stop loss price based on market movement.
// For initial setup, it might just set an initial ATR-based stop.
function determineExitPricesTrailing(entryPrice, side, atr, pricePrecision) {
    // ... implementation for initial trailing stop calculation ...
    // Note: Actual trailing stop adjustment would occur in a separate monitoring process.
    return determineExitPricesATR(entryPrice, side, atr, pricePrecision); // Fallback for initial setup
}
*/
```
**`src/config.js` Update for Improvement 16:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    riskToRewardRatio: 1.5,
    stopLossStrategy: 'atr', // IMPROVEMENT 16: 'atr', 'percentage', or 'trailing' (trailing is a placeholder)
    stopLossPercentage: 1.5, // Used if stopLossStrategy is 'percentage' or as fallback
    atrMultiplier: 2.0,      // Used if stopLossStrategy is 'atr'
    // ... (rest of config) ...
};
```

---

**17. `src/core/risk_policy.js` - Daily PnL Tracking and Reset**
This feature tracks the cumulative daily loss and automatically resets it at the start of a new day, enabling the "Max Daily Loss" policy.

```javascript
// src/core/risk_policy.js
import logger from '../utils/logger.js';
import { ACTIONS } from './constants.js';
import { config } from '../config.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 17: Use Decimal for P&L calculations

export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    // IMPROVEMENT 17: Max Daily Loss Policy - Tracking and Reset
    const now = Date.now();
    const today = new Date(now).toISOString().split('T')[0]; // YYYY-MM-DD
    const pnlResetDate = state.dailyPnlResetDate;
    let dailyLoss = new Decimal(state.dailyLoss); // Ensure state.dailyLoss is loaded as Decimal

    if (pnlResetDate !== today) {
        logger.info(`Resetting daily P&L. Old date: ${pnlResetDate}, New date: ${today}. Old loss: ${dailyLoss.toFixed(2)} USDT.`);
        dailyLoss = new Decimal(0); // Reset daily loss
        state.dailyPnlResetDate = today; // Update the reset date in the state object
        state.dailyLoss = dailyLoss; // Update the state object (will be saved as string by state_manager)
    }

    // IMPROVEMENT 17: Max Daily Loss Policy - Check
    const initialBalance = new Decimal(state.initialBalance); // Ensure initialBalance is loaded as Decimal
    if (initialBalance.isZero() && config.dryRun === false) { // Warn if initial balance isn't set for live trading
        logger.warn("Initial balance is zero. Max daily loss cannot be calculated accurately.");
    } else if (dailyLoss.gte(initialBalance.times(config.maxDailyLossPercentage).dividedBy(100))) {
        const reason = `Risk policy violation: Max daily loss limit of ${config.maxDailyLossPercentage}% reached. Current daily loss: ${dailyLoss.toFixed(2)} USDT.`;
        logger.error(reason);
        return { decision: ACTIONS.HALT, reason, trade: null }; // Consider a HALT state for extreme loss
    }
    // ... (rest of risk policy logic) ...
}
```
**`src/config.js` Update for Improvement 17:**
```javascript
// src/config.js
export const config = {
    // ... (existing config) ...
    riskPercentage: 2.0,
    riskToRewardRatio: 1.5,
    stopLossStrategy: 'atr',
    stopLossPercentage: 1.5,
    atrMultiplier: 2.0,
    slippagePercentage: 0.05,
    exchangeFeePercentage: 0.055,
    tradeCooldownMinutes: 30,
    maxDailyLossPercentage: 10, // IMPROVEMENT 17: Max percentage of initial balance allowed to lose per day
    // ... (rest of config) ...
};
```
**`src/utils/state_manager.js` Update for Improvement 17 (already present in the provided file, but highlighted):**
```javascript
// src/utils/state_manager.js
// ... (imports) ...
export const defaultState = {
    // ... (existing fields) ...
    dailyLoss: new Decimal(0).toString(), // IMPROVEMENT 17: Total loss for the current day
    dailyPnlResetDate: new Date().toISOString().split('T')[0], // IMPROVEMENT 17: YYYY-MM-DD
    initialBalance: new Decimal(0).toString(), // IMPROVEMENT 17: Initial balance at start, for daily loss calc
    // ... (rest of default state) ...
};
// ... (getDecimalState and toSerializableState ensure correct Decimal handling) ...
```

---

**18. `src/core/risk_policy.js` - Introduce `HALT` Action for Severe Breaches**
This defines a new action, `HALT`, in `constants.js` and ensures that the `risk_policy` can return this action to signify a severe breach requiring the trading bot to stop.

```javascript
// src/core/risk_policy.js
import logger from '../utils/logger.js';
import { ACTIONS } from './constants.js'; // IMPROVEMENT 18: Import ACTIONS including HALT
import { config } from '../config.js';
import Decimal from 'decimal.js';

export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    // ... (daily loss tracking and check) ...
    // IMPROVEMENT 18: Return HALT decision
    if (dailyLoss.gte(initialBalance.times(config.maxDailyLossPercentage).dividedBy(100))) {
        const reason = `Risk policy violation: Max daily loss limit of ${config.maxDailyLossPercentage}% reached. Current daily loss: ${dailyLoss.toFixed(2)} USDT.`;
        logger.error(reason);
        return { decision: ACTIONS.HALT, reason, trade: null }; // Return ACTIONS.HALT
    }
    // ... (rest of risk policy logic) ...
}
```
**`src/core/constants.js` Update for Improvement 18:**
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

**19. `src/utils/state_manager.js` - Track `openPositionsCount` and `openOrders`**
The `defaultState` is extended to include `openPositionsCount` (for potential future multi-position trading) and `openOrders` (to track pending TP/SL or limit orders).

```javascript
// src/utils/state_manager.js
import fs from 'fs/promises';
import path from 'path';
import logger from './logger.js';
import Decimal from 'decimal.js';

const stateFilePath = path.resolve('bot_state.json');
const tempStateFilePath = path.resolve('bot_state.json.tmp');

export const defaultState = {
    inPosition: false,
    positionSide: null, // 'Buy' or 'Sell'
    entryPrice: new Decimal(0).toString(),
    quantity: new Decimal(0).toString(),
    orderId: null, // Main entry order ID
    lastTradeTimestamp: 0,
    dailyLoss: new Decimal(0).toString(),
    dailyPnlResetDate: new Date().toISOString().split('T')[0],
    initialBalance: new Decimal(0).toString(),
    openPositionsCount: 0, // IMPROVEMENT 19: Track number of open positions (for future multi-position)
    openOrders: [], // IMPROVEMENT 19: Track open TP/SL orders or other pending orders
};

// ... (getDecimalState, toSerializableState, saveState, loadState) ...
```

---

**20. `src/trading_ai_system.js` - Handle `HALT` Decision**
The main `TradingAiSystem`'s `runAnalysisCycle` needs to gracefully react when the `risk_policy` returns a `HALT` decision, typically by stopping further trading actions.

```javascript
// src/trading_ai_system.js
// ... (existing imports and functions) ...

class TradingAiSystem {
    // ... (constructor and calculateIndicators) ...

    async runAnalysisCycle() {
        if (this.isProcessing) {
            logger.warn("Skipping analysis cycle: a previous one is still active.");
            return;
        }
        this.isProcessing = true;
        logger.info("=========================================");
        logger.info(`Starting new analysis cycle for ${config.symbol}...`);

        try {
            const state = await this.reconcileState();
            
            // IMPROVEMENT 20: Check if bot is in a HALT state
            if (state.isHalted) { // Assuming a `isHalted` flag could be added to state
                logger.warn(`Bot is currently HALTED due to risk policy. Reason: ${state.haltReason || 'Unknown'}. Skipping trading actions.`);
                return;
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
            const aiDecision = await this.geminiApi.getTradeDecision(marketContext, state.inPosition, state.positionSide); // Pass state for dynamic prompt
            const policyResult = applyRiskPolicy(aiDecision, primaryIndicators, state);

            // IMPROVEMENT 20: Handle HALT decision from risk policy
            if (policyResult.decision === ACTIONS.HALT) {
                logger.critical(`Risk policy HALT: ${policyResult.reason}. Bot operations suspended.`);
                // Update state to reflect HALT, and save.
                await saveState({ ...state, isHalted: true, haltReason: policyResult.reason });
                return; // Stop further processing
            }

            if (policyResult.decision === 'HOLD') {
                logger.info(`Decision: HOLD. Reason: ${policyResult.reason}`);
                return;
            }

            const { name, args } = policyResult.trade;
            if (name === ACTIONS.PROPOSE_TRADE) {
                await this.executeEntry(args, primaryIndicators, state); // Pass state to executeEntry
            } else if (name === ACTIONS.PROPOSE_EXIT) {
                await this.executeExit(state, args);
            }
        } catch (error) {
            logger.exception(error);
        } finally {
            this.isProcessing = false;
            logger.info("Analysis cycle finished.");
            logger.info("=========================================\n");
        }
    }

    // Minor update to executeEntry to take state
    async executeEntry(args, indicators, state) {
        logger.info(`Executing ENTRY: ${args.side}. Reason: ${args.reasoning}`);
        const { side } = args;
        const price = new Decimal(indicators.close); // Ensure price is Decimal
        const atr = new Decimal(indicators.atr); // Ensure atr is Decimal

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");
        const balanceDecimal = new Decimal(balance); // Convert balance to Decimal

        const { stopLoss, takeProfit } = determineExitPrices(price, side, atr, this.bybitApi.getPricePrecision());
        const quantity = calculatePositionSize(balanceDecimal, price, stopLoss, this.bybitApi.getQtyPrecision(), this.bybitApi.getMinOrderQty());

        if (quantity.lte(0)) { // Use lte for Decimal
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol, side, qty: quantity, takeProfit, stopLoss, 
        });

        if (orderResult && orderResult.orderId) {
            await saveState({
                ...state, // Persist other state values
                inPosition: true, positionSide: side, entryPrice: price.toString(), // Store as string
                quantity: quantity.toString(), orderId: orderResult.orderId,
                lastTradeTimestamp: 0, // Reset cooldown timer on entry (0 or current time for new cooldown)
                openPositionsCount: (state.openPositionsCount || 0) + 1, // Increment count
                // Add initialBalance if it's the first trade for the day/session
                initialBalance: state.initialBalance === '0' ? balanceDecimal.toString() : state.initialBalance
            });
            logger.info(`Successfully placed ENTRY order. Order ID: ${orderResult.orderId}`);
        }
    }
    
    async executeExit(state, args) {
        logger.info(`Executing EXIT from ${state.positionSide} position. Reason: ${args.reasoning}`);
        const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide);

        if (closeResult && closeResult.orderId) {
            // Calculate PnL for daily loss tracking
            // This is a simplified PnL calculation; a full system would use exchange data for realized PnL.
            const currentPrice = new Decimal(this.featureEngineers.get(config.primaryInterval).last.close);
            const entryPrice = new Decimal(state.entryPrice);
            const quantity = new Decimal(state.quantity);
            const positionPnl = (currentPrice.minus(entryPrice)).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
            
            const newDailyLoss = new Decimal(state.dailyLoss).plus(positionPnl.lt(0) ? positionPnl.abs() : 0); // Add absolute loss if PnL is negative

            await saveState({
                ...defaultState, // Reset to default state
                lastTradeTimestamp: Date.now(), // Set cooldown
                dailyLoss: newDailyLoss.toString(), // Update daily loss
                dailyPnlResetDate: state.dailyPnlResetDate, // Keep current day for PnL
                initialBalance: state.initialBalance, // Keep initial balance
                openPositionsCount: Math.max(0, (state.openPositionsCount || 1) - 1), // Decrement count
            });
            logger.info(`Successfully placed EXIT order. Order ID: ${closeResult.orderId}. Position P&L: ${positionPnl.toFixed(2)}.`);
        }
    }

    // ... (reconcileState and other methods) ...
}
```
**`src/utils/state_manager.js` Update for Improvement 20:**
```javascript
// src/utils/state_manager.js
// ... (imports) ...
export const defaultState = {
    // ... (existing fields) ...
    isHalted: false, // IMPROVEMENT 20: New flag to indicate if bot is halted
    haltReason: null, // IMPROVEMENT 20: Reason for halting
};

export function getDecimalState(state) {
    return {
        ...state,
        entryPrice: new Decimal(state.entryPrice),
        quantity: new Decimal(state.quantity),
        dailyLoss: new Decimal(state.dailyLoss),
        initialBalance: new Decimal(state.initialBalance),
        // No Decimal conversion for isHalted/haltReason as they are not numbers
    };
}
// ... (toSerializableState, saveState, loadState) ...
```
