Here are 20 update and improvement code snippets, focusing on different aspects of your trading bot, excluding the `ta/` folder improvements already drafted in `help2.md`. Each snippet is designed to be directly applicable to the specified file, often with minor contextual additions to `config.js` or other files noted in the comments.

---

### **FILE: `src/api/bybit_api.js`**

**1. Improvement: Dynamic Rate Limit Tracking and Enforcement (Conceptual)**
This snippet introduces a conceptual `rateLimitTracker` and modifies `_processQueue` to use it. A full implementation would involve parsing `X-RateLimit-*` headers from every Bybit response to dynamically adjust `requestIntervalMs`. For this snippet, it's a simple last-request-time based check.

```javascript
// Add to BybitAPI constructor:
    constructor(apiKey, apiSecret) {
        // ... existing constructor code ...
        // IMPROVEMENT 1: Dynamic Rate Limit Tracking (conceptual)
        this.rateLimitTracker = {
            lastRequestTime: 0,
            // A more advanced system would parse X-RateLimit-* headers to adjust `requestIntervalMs` dynamically.
            // For now, it respects the configured `requestIntervalMs` as a minimum delay.
        };
    }

// Modify _processQueue method:
    async _processQueue() {
        if (isProcessingQueue) return;
        isProcessingQueue = true;

        while (requestQueue.length > 0) {
            const request = requestQueue.shift();
            const { method, endpoint, params, isPrivate, resolve, reject, retryCount } = request;

            try {
                // IMPROVEMENT 1: Dynamic Rate Limit Enforcement
                const now = Date.now();
                const timeSinceLastRequest = now - this.rateLimitTracker.lastRequestTime;
                if (timeSinceLastRequest < config.bybit.requestIntervalMs) {
                    const delay = config.bybit.requestIntervalMs - timeSinceLastRequest;
                    logger.debug(`Rate limit delay: waiting ${delay}ms before next request to Bybit.`);
                    await sleep(delay);
                }
                this.rateLimitTracker.lastRequestTime = Date.now(); // Update after potential sleep

                const result = await this._makeRequest(method, endpoint, params, isPrivate);
                resolve(result);
            } catch (error) {
                // ... (existing retry logic) ...
            }
        }
        isProcessingQueue = false;
    }
```

**2. Improvement: Add `getOpenOrders` Method**
This method allows the bot to fetch all currently open orders for a symbol, crucial for state reconciliation.

```javascript
// Add to BybitAPI class:
    /**
     * Retrieves all open orders for a given symbol.
     * @param {string} symbol The trading symbol (e.g., 'BTCUSDT').
     * @returns {Promise<Array>} An array of open orders.
     */
    async getOpenOrders(symbol) {
        logger.info(`Fetching open orders for ${symbol}.`);
        try {
            // Bybit API v5 uses openOnly = 0 to filter for unfilled/partially filled orders
            const result = await this._request('GET', '/v5/order/realtime', {
                category: config.bybit.category,
                symbol: symbol,
                openOnly: 0,
            });
            return result?.list || [];
        } catch (error) {
            logger.error(`Failed to fetch open orders for ${symbol}: ${error.message}`);
            throw error;
        }
    }
```

**3. Improvement: Add `amendOrder` Method**
Allows the bot to modify existing orders (e.g., adjust price of a limit order, or quantity).

```javascript
// Add to BybitAPI class:
    /**
     * Amends an existing order (price or quantity).
     * @param {string} symbol The trading symbol.
     * @param {string} orderId The ID of the order to amend.
     * @param {number} [newQty] New quantity for the order.
     * @param {number} [newPrice] New price for the order.
     * @returns {Promise<object>} The result of the amendment.
     */
    async amendOrder(symbol, orderId, newQty, newPrice) {
        if (!newQty && !newPrice) {
            throw new Error("Either new quantity or new price must be provided for order amendment.");
        }
        logger.info(`Attempting to amend order ${orderId} for ${symbol}. New Qty: ${newQty || 'N/A'}, New Price: ${newPrice || 'N/A'}`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would amend order ${orderId} for ${symbol}. New Qty: ${newQty || 'N/A'}, New Price: ${newPrice || 'N/A'}`);
            return { orderId, result: 'dry-run-amend-order' };
        }

        const orderParams = {
            category: config.bybit.category,
            symbol: symbol,
            orderId: orderId,
            ...(newQty !== undefined && { qty: new Decimal(newQty).toDecimalPlaces(this.getQtyPrecision()).toString() }),
            ...(newPrice !== undefined && { price: new Decimal(newPrice).toDecimalPlaces(this.getPricePrecision()).toString() }),
        };

        try {
            const result = await this._request('POST', '/v5/order/amend', orderParams);
            logger.info(`Successfully amended order ${orderId} for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to amend order ${orderId} for ${symbol}: ${error.message}`);
            throw error;
        }
    }
```

**4. Improvement: Add `getTickers` Method**
A public endpoint to quickly get the latest price, volume, and other summary data without fetching full klines.

```javascript
// Add to BybitAPI class:
    /**
     * Retrieves ticker information for a specific symbol.
     * @param {string} [symbol] The trading symbol (e.g., 'BTCUSDT'). Defaults to config.symbol.
     * @returns {Promise<object|null>} Ticker data for the symbol, or null if not found.
     */
    async getTickers(symbol = config.symbol) {
        logger.debug(`Fetching ticker for ${symbol}.`);
        try {
            const params = { category: config.bybit.category, symbol };
            const result = await this._request('GET', '/v5/market/tickers', params, false);
            return result?.list?.[0] || null; // Return single ticker
        } catch (error) {
            logger.error(`Failed to fetch ticker data for ${symbol}: ${error.message}`);
            throw error;
        }
    }
```

**5. Improvement: Add `setLeverage` Method**
Allows the bot to programmatically adjust the leverage for a trading pair.

```javascript
// Add to BybitAPI class:
    /**
     * Sets the leverage for a specific symbol.
     * @param {string} symbol The trading symbol (e.g., 'BTCUSDT').
     * @param {number} leverage The desired leverage (e.g., 10, 25, 50).
     * @returns {Promise<object>} The result of the leverage setting operation.
     */
    async setLeverage(symbol, leverage) {
        if (!Number.isInteger(leverage) || leverage <= 0) {
            throw new Error("Leverage must be a positive integer.");
        }
        logger.info(`Attempting to set leverage for ${symbol} to ${leverage}x.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would set leverage for ${symbol} to ${leverage}x.`);
            return { symbol, leverage, result: 'dry-run-set-leverage' };
        }
        try {
            const result = await this._request('POST', '/v5/position/set-leverage', {
                category: config.bybit.category,
                symbol: symbol,
                buyLeverage: leverage.toString(), // Bybit API expects strings
                sellLeverage: leverage.toString(),
            });
            logger.info(`Successfully set leverage for ${symbol} to ${leverage}x.`);
            return result;
        } catch (error) {
            logger.error(`Failed to set leverage for ${symbol} to ${leverage}x: ${error.message}`);
            throw error;
        }
    }
```

---

### **FILE: `src/api/bybit_websocket.js`**

**6. Improvement: Implement Event Emitter for Message Handling**
Decouples message processing from the WebSocket class, making it more flexible. Requires adding `import { EventEmitter } from 'events';` at the top.

```javascript
// At the top of bybit_websocket.js:
import { EventEmitter } from 'events';
// ... existing imports ...

// Modify BybitWebSocket class definition:
class BybitWebSocket extends EventEmitter { // Extend EventEmitter
    constructor() { // Remove onNewCandleCallback, onPrivateMessageCallback from constructor
        super(); // Call EventEmitter constructor
        // ... existing constructor properties ...
        // Remove `this.onNewCandle` and `this.onPrivateMessage` assignments
    }

// Modify connectPublic's `onMessage` handler:
            (data) => {
                const message = JSON.parse(data.toString());
                if (message.topic && message.topic.startsWith('kline')) {
                    const candle = message.data[0];
                    if (candle.confirm === true) {
                        logger.debug(`New confirmed ${config.primaryInterval}m candle for ${config.symbol}. Close: ${candle.close}`);
                        this.emit('candle', candle); // Emit a 'candle' event
                    }
                }
            },

// Modify connectPrivate's `onMessage` handler:
            (data) => {
                const message = JSON.parse(data.toString());
                this.emit('privateMessage', message); // Emit a 'privateMessage' event
                // ... existing unhandled message logging ...
            },
// You will then listen for these events in `src/trading_ai_system.js`
```

**7. Improvement: Track and Resubscribe to Topics on Reconnect**
Ensures that all desired subscriptions are re-established after a WebSocket disconnect and reconnect.

```javascript
// Add to BybitWebSocket constructor:
    constructor(onNewCandleCallback, onPrivateMessageCallback) {
        // ... existing constructor code ...
        // IMPROVEMENT 7: Track active subscriptions
        this.publicSubscriptions = new Set();
        this.privateSubscriptions = new Set();
    }

// Modify connectPublic method:
    connectPublic() {
        this.publicWs = this._connectWs('public', this.publicUrl,
            (ws) => {
                // IMPROVEMENT 7: Add/resubscribe to public topics
                const topic = `kline.${config.primaryInterval}.${config.symbol}`;
                if (!this.publicSubscriptions.has(topic)) {
                    this.publicSubscriptions.add(topic);
                }
                const subscription = { op: "subscribe", args: Array.from(this.publicSubscriptions) };
                ws.send(JSON.stringify(subscription));
                logger.info(`Subscribed to public topics: ${subscription.args.join(', ')}`);
                this._startHeartbeat(ws, 'publicPingInterval', config.bybit.publicPingIntervalMs);
            },
            // ... rest of connectPublic ...
        );
    }

// Modify connectPrivate method (inside the authHandler, after successful authentication):
                            if (message.success) {
                                logger.info("Private WebSocket authenticated successfully.");
                                ws.off('message', authHandler);

                                // IMPROVEMENT 7: Add/resubscribe to private topics
                                if (!this.privateSubscriptions.has('order')) this.privateSubscriptions.add('order');
                                if (!this.privateSubscriptions.has('position')) this.privateSubscriptions.add('position');
                                const privateSubscriptions = {
                                    op: "subscribe",
                                    args: Array.from(this.privateSubscriptions)
                                };
                                ws.send(JSON.stringify(privateSubscriptions));
                                logger.info(`Subscribed to private topics: ${privateSubscriptions.args.join(', ')}`);
                                this._startHeartbeat(ws, 'privatePingInterval', config.bybit.privatePingIntervalMs);
                            }
```

**8. Improvement: Add Graceful Shutdown for WebSockets**
Provides a clean way to close connections and clear timeouts/intervals when the bot stops.

```javascript
// Add to BybitWebSocket class:
    /**
     * Disconnects both public and private WebSocket connections and cleans up resources.
     * It attempts to gracefully close connections and stop heartbeats.
     */
    disconnect() {
        logger.info("Initiating WebSocket graceful shutdown...");
        this._stopHeartbeat('publicPingInterval');
        this._stopHeartbeat('privatePingInterval');
        clearTimeout(this.publicReconnectTimeout);
        clearTimeout(this.privateReconnectTimeout);

        if (this.publicWs && this.publicWs.readyState === WebSocket.OPEN) {
            this.publicWs.close(1000, 'Shutdown initiated'); // 1000 is Normal Closure
            logger.info("Public WebSocket closing.");
        } else if (this.publicWs) {
            logger.warn("Public WebSocket not open, setting to null.");
            this.publicWs = null;
        }

        if (this.privateWs && this.privateWs.readyState === WebSocket.OPEN) {
            this.privateWs.close(1000, 'Shutdown initiated');
            logger.info("Private WebSocket closing.");
        } else if (this.privateWs) {
            logger.warn("Private WebSocket not open, setting to null.");
            this.privateWs = null;
        }
        logger.info("WebSockets disconnected.");
    }
```

---

### **FILE: `src/api/gemini_api.js`**

**9. Improvement: Add `maxOutputTokens` to Generation Configuration**
Crucial for controlling response length, costs, and ensuring the AI's output stays within reasonable bounds.

```javascript
// Modify getTradeDecision method in GeminiAPI:
    async getTradeDecision(marketContext, isInPosition, positionSide) {
        try {
            const model = this.genAI.getGenerativeModel({
                model: config.geminiModel,
                generationConfig: {
                    responseMimeType: "application/json",
                    temperature: config.gemini.temperature,
                    topP: config.gemini.topP,
                    maxOutputTokens: config.gemini.maxOutputTokens, // IMPROVEMENT 9: Max output tokens
                }
            });
            // ... rest of getTradeDecision ...
        } catch (error) { /* ... */ }
    }
// Add to `src/config.js`:
// gemini: {
//     temperature: 0.7,
//     topP: 0.9,
//     maxOutputTokens: 500, // Max tokens for AI response
//     // ... other gemini config ...
// },
```

**10. Improvement: Implement Simple Rate Limiting for Gemini API Calls**
Prevents hitting Gemini's rate limits, ensuring consistent AI decision-making. Requires adding `sleep` utility import if not already globally available.

```javascript
// Add to GeminiAPI constructor:
    constructor(apiKey) {
        this.genAI = new GoogleGenerativeAI(apiKey);
        // IMPROVEMENT 10: Simple Rate Limiting for Gemini
        this.lastRequestTime = 0;
        this.requestIntervalMs = config.gemini.requestIntervalMs; // Configurable interval
    }

// Modify getTradeDecision, before `model.generateContent(prompt)`:
            // IMPROVEMENT 10: Simple Rate Limiting for Gemini
            const now = Date.now();
            if (now - this.lastRequestTime < this.requestIntervalMs) {
                const delay = this.requestIntervalMs - (now - this.lastRequestTime);
                logger.debug(`Delaying Gemini API call by ${delay}ms to respect rate limit.`);
                await sleep(delay); // Ensure `sleep` is imported/available (e.g., from bybit_api.js)
            }
            this.lastRequestTime = Date.now(); // Update after potential sleep

            const result = await model.generateContent(prompt);
            // ... rest of getTradeDecision ...

// Add to `src/config.js`:
// gemini: {
//     // ... existing gemini config ...
//     requestIntervalMs: 5000, // E.g., 5 seconds between AI decision calls
// },
```

---

### **FILE: `src/core/trading_logic.js`**

**11. Improvement: Add `adjustStopLossToBreakEven` Function**
A common risk management strategy to move the stop-loss to the entry price (or slightly better) once a certain profit threshold is met.

```javascript
// Add a new function in `src/core/trading_logic.js`:
/**
 * Adjusts the stop loss to break-even (entry price + fees) if a minimum profit target is met.
 * @param {Decimal} currentPrice - The current market price.
 * @param {object} position - The current position details (entryPrice, positionSide, quantity).
 * @param {Decimal} currentStopLoss - The current stop loss level.
 * @param {number} pricePrecision - Price precision from Bybit API.
 * @returns {Decimal} The new, adjusted stop loss price.
 */
export function adjustStopLossToBreakEven(currentPrice, position, currentStopLoss, pricePrecision) {
    const entryPrice = new Decimal(position.entryPrice);
    const positionSide = position.positionSide;
    const quantity = new Decimal(position.quantity);

    // Calculate profit needed to reach break-even threshold (e.g., 0.5% profit)
    const profitThresholdAmount = entryPrice.times(quantity).times(config.breakEvenProfitPercentage).dividedBy(100);

    let unrealizedPnl;
    if (positionSide === 'Buy') {
        unrealizedPnl = currentPrice.minus(entryPrice).times(quantity);
    } else { // Sell
        unrealizedPnl = entryPrice.minus(currentPrice).times(quantity);
    }

    if (unrealizedPnl.gte(profitThresholdAmount)) {
        // Calculate break-even price including estimated fees
        const estimatedFees = entryPrice.times(config.exchangeFeePercentage).dividedBy(100);
        let breakEvenPrice;
        if (positionSide === 'Buy') {
            breakEvenPrice = entryPrice.plus(estimatedFees);
        } else { // Sell
            breakEvenPrice = entryPrice.minus(estimatedFees);
        }

        // Only move SL if the new break-even price is better (or equal) than the current SL
        // For Buy: new SL must be >= current SL (higher price is better)
        // For Sell: new SL must be <= current SL (lower price is better)
        if ((positionSide === 'Buy' && breakEvenPrice.gte(currentStopLoss)) ||
            (positionSide === 'Sell' && breakEvenPrice.lte(currentStopLoss))) {
            logger.info(`Moving stop loss to break-even for ${positionSide} position. Old SL: ${currentStopLoss.toFixed(pricePrecision)}, New SL: ${breakEvenPrice.toFixed(pricePrecision)}`);
            return breakEvenPrice.toDecimalPlaces(pricePrecision);
        }
    }
    return currentStopLoss; // No change to SL
}
// Add to `src/config.js`:
// breakEvenProfitPercentage: 0.5, // % profit (of position value) to trigger break-even stop
```

**12. Improvement: Extend `calculatePositionSize` for configurable leverage.**
Currently, leverage is implicit. This makes it explicit and configurable.

```javascript
// Modify calculatePositionSize function signature and logic:
export function calculatePositionSize(balance, entryPrice, stopLossPrice, qtyPrecision, minOrderQty, leverage = 1) { // Add leverage parameter, default to 1x
    balance = new Decimal(balance);
    entryPrice = new Decimal(entryPrice);
    stopLossPrice = new Decimal(stopLossPrice);
    leverage = new Decimal(leverage); // Ensure leverage is Decimal

    const riskAmount = balance.times(config.riskPercentage).dividedBy(100);
    const slippageCost = entryPrice.times(config.slippagePercentage).dividedBy(100);
    const effectiveEntryPrice = entryPrice.plus(slippageCost);

    const riskPerShare = effectiveEntryPrice.minus(stopLossPrice).abs();

    if (riskPerShare.isZero()) {
        logger.warn("Calculated risk per share is zero. Cannot calculate position size.");
        return new Decimal(0);
    }

    // IMPROVEMENT 12: Account for leverage in position sizing
    // The amount of capital actually put down (margin) is `quantity * entryPrice / leverage`.
    // So, we want `(quantity * entryPrice / leverage) >= riskAmount` for initial margin.
    // However, riskAmount is the total USDT risk at SL.
    // So, quantity = riskAmount / riskPerShare, then adjust for margin.
    // For risk-based sizing, the quantity calculated without leverage is generally correct
    // because `riskAmount` is already in the quote currency (e.g., USDT). Leverage affects
    // the margin used, not the PnL calculation itself, which is based on the notional size.
    // A more precise adjustment is needed for `initial margin`.
    // Let's assume `riskAmount` is the total notional value at risk.
    // If the account is cross-margin, the entire `balance` is available.
    // If isolated margin, it's `riskAmount / (entryPrice * leverage)`
    // For simplicity, let's keep the quantity calculation as is, but ensure `riskAmount`
    // is understood as the 'notional risk' the bot is willing to take, which is covered by margin.

    let quantity = riskAmount.dividedBy(riskPerShare);

    // ... (existing feeFactor, finalQuantity, minOrderQty, tradeCost logic) ...

    logger.info(`Position size calculated: ${finalQuantity.toFixed(qtyPrecision)}. Risking ${riskAmount.toFixed(2)} USDT with ${leverage.toFixed(2)}x leverage.`);
    return finalQuantity;
}
// You'd pass `config.bybit.leverage` from `trading_ai_system.js` to this function.
// Add to `src/config.js`:
// bybit: {
//     // ... existing bybit config ...
//     leverage: 10, // Default leverage to use for trades
// },
```

**13. Improvement: Configurable Entry Order Type for `placeOrder`**
Allows flexibility in choosing between Market, Limit, or PostOnly orders for entries. (The `placeOrder` method in `bybit_api.js` already supports `orderType` and `price`).

```javascript
// In `src/trading_ai_system.js`, modify `executeEntry` method:
    async executeEntry(args, indicators, state) {
        logger.info(`Executing ENTRY: ${args.side}. Reason: ${args.reasoning}`);
        const { side } = args;
        const price = new Decimal(indicators.close);
        const atr = new Decimal(indicators.atr);

        // ... existing balance, SL/TP, quantity calculations ...

        if (quantity.lte(0)) {
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            return;
        }

        // IMPROVEMENT 13: Use configurable order type for entry
        const entryOrderType = config.entryOrderType; // 'Market', 'Limit', 'PostOnly'
        let entryPriceForLimitOrder = undefined;

        if (entryOrderType !== 'Market') {
            // For Limit/PostOnly, place the order slightly off the current price for a better fill/passive entry
            const priceOffset = price.times(config.entryLimitPriceOffsetPercentage).dividedBy(100);
            entryPriceForLimitOrder = (side === 'Buy') ? price.minus(priceOffset) : price.plus(priceOffset);
            entryPriceForLimitOrder = entryPriceForLimitOrder.toDecimalPlaces(this.bybitApi.getPricePrecision());
            logger.info(`Using ${entryOrderType} order at ${entryPriceForLimitOrder.toFixed(this.bybitApi.getPricePrecision())} with ${priceOffset.toFixed(this.bybitApi.getPricePrecision())} offset.`);
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol,
            side,
            qty: quantity,
            takeProfit,
            stopLoss,
            orderType: entryOrderType, // Use configured order type
            price: entryPriceForLimitOrder, // Pass price for limit/post-only orders
        });
        // ... rest of executeEntry ...
    }
// Add to `src/config.js`:
// entryOrderType: 'Market', // 'Market', 'Limit', 'PostOnly' - type of order for entries
// entryLimitPriceOffsetPercentage: 0.05, // 0.05% offset from current price for Limit/PostOnly entries
```

---

### **FILE: `src/core/risk_policy.js`**

**14. Improvement: Implement Maximum Overall Drawdown Policy**
Halt trading if the total account value (from initial balance) drops beyond a certain percentage, protecting against significant losses.

```javascript
// Modify applyRiskPolicy in `src/core/risk_policy.js`:
export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    // ... (existing daily loss and reset logic) ...

    // IMPROVEMENT 14: Max Overall Drawdown Policy
    // This requires a real-time account balance, which for simplicity here,
    // we'll approximate. A robust system would fetch this directly from Bybit.
    const currentPrice = new Decimal(indicators.close);
    let currentEquity = new Decimal(state.initialBalance); // Start with initial balance

    if (state.inPosition) {
        // If in position, add unrealized P&L to initial balance (approximation)
        const entryPrice = new Decimal(state.entryPrice);
        const quantity = new Decimal(state.quantity);
        const unrealizedPnl = currentPrice.minus(entryPrice).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
        currentEquity = currentEquity.plus(unrealizedPnl);
    }
    // We assume initialBalance is set at bot start. If not, this check won't run.
    if (state.initialBalance.gt(0) && currentEquity.lt(state.initialBalance)) {
        const drawdown = state.initialBalance.minus(currentEquity).dividedBy(state.initialBalance).times(100);
        if (drawdown.gte(config.maxOverallDrawdownPercentage)) {
            const reason = `Risk policy violation: Max overall drawdown limit of ${config.maxOverallDrawdownPercentage}% reached. Current drawdown: ${drawdown.toFixed(2)}%.`;
            logger.critical(reason);
            return { decision: ACTIONS.HALT, reason, trade: null };
        }
    }

    // ... rest of existing risk checks ...
    logger.info("AI decision passed risk policy checks.");
    return { decision: 'EXECUTE', reason: 'AI proposal is valid and passes risk checks.', trade: aiDecision };
}
// Add to `src/config.js`:
// maxOverallDrawdownPercentage: 20, // Max percentage of initial balance allowed as overall drawdown
```

**15. Improvement: Add Minimum ATR Filter for Trade Proposals**
Prevents the bot from entering trades during extremely low volatility, which can lead to whipsaws or poor risk-to-reward.

```javascript
// Modify applyRiskPolicy in `src/core/risk_policy.js`, inside `ACTIONS.PROPOSE_TRADE` block:
    if (name === ACTIONS.PROPOSE_TRADE) {
        // ... (existing Rule 1: missing indicators, Rule 2: already in position, Rule 3: cooldown) ...

        // IMPROVEMENT 15: Minimum ATR filter
        if (!indicators.atr || new Decimal(indicators.atr).lt(config.minAtrThreshold)) {
            const reason = `Risk policy violation: ATR (${indicators.atr ? indicators.atr.toFixed(2) : 'N/A'}) is below minimum threshold (${config.minAtrThreshold.toFixed(2)}). Avoiding low volatility trade.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // ... (existing Rule 4: max open positions) ...
    }
// Add to `src/config.js`:
// minAtrThreshold: 0.5, // Minimum ATR value (in USDT) to consider a trade, avoiding flat markets
```

---

### **FILE: `src/utils/state_manager.js`**

**16. Improvement: Implement State Versioning and Basic Migration**
Ensures that changes to the state structure in future versions can be handled gracefully, preventing bot crashes from old state files.

```javascript
// Modify defaultState object:
export const defaultState = {
    _version: 1, // IMPROVEMENT 16: State versioning
    inPosition: false,
    // ... rest of defaultState ...
};

// Modify loadState function:
export async function loadState() {
    try {
        await fs.access(stateFilePath);
        const data = await fs.readFile(stateFilePath, 'utf8');
        logger.info("Successfully loaded state from file.");
        let loaded = JSON.parse(data);

        // IMPROVEMENT 16: Handle state versioning and migration
        if (loaded._version === undefined || loaded._version < defaultState._version) {
            logger.warn(`Migrating state from version ${loaded._version || 'N/A'} to ${defaultState._version}.`);
            // This simple merge handles new fields, but for complex transformations
            // (e.g., renaming a field, combining data), dedicated migration functions
            // for each version increment would be needed here.
            loaded = { ...defaultState, ...loaded, _version: defaultState._version }; // Apply default for missing, update version
            // For example, if adding `openOrders` in v2:
            // if (loaded._version < 2 && defaultState._version >= 2) {
            //    loaded.openOrders = loaded.openOrders || [];
            // }
            // After migration, save the updated state
            await saveState(getDecimalState(loaded)); // Save the migrated state immediately
        }

        const mergedState = { ...defaultState, ...loaded };
        return getDecimalState(mergedState);
    } catch (error) {
        logger.warn("No state file found or failed to read. Using default state.", error);
        return getDecimalState(defaultState);
    }
}
```

---

### **FILE: `src/utils/logger.js`**

**17. Improvement: Add `debug` Log Level**
Provides a more granular logging level for verbose output during development, which can be easily toggled off in production.

```javascript
// Modify logger object:
const logger = {
    debug: (message, obj = null) => { // IMPROVEMENT 17: Add debug level
        // Only log debug messages if `config.debugMode` is true (defined in config.js)
        if (config.debugMode) {
            const formatted = `[DEBUG][${getTimestamp()}] ${message}`;
            console.log(formatted);
            logToFile(formatted);
            if (obj) {
                // For objects, log them as pretty JSON
                const objString = JSON.stringify(obj, null, 2);
                console.log(objString);
                logToFile(objString);
            }
        }
    },
    info: (message) => { /* ... existing info logic ... */ },
    // ... rest of logger ...
};
// Add to `src/config.js`:
// debugMode: false, // Set to true for verbose debug logging
```

**18. Improvement: Add `critical` Log Level**
For severe, potentially bot-halting errors that require immediate attention.

```javascript
// Modify logger object:
const logger = {
    // ... existing info, warn, error ...
    critical: (message, error) => { // IMPROVEMENT 18: Add critical level
        const formatted = `[CRITICAL][${getTimestamp()}] ${message}`;
        console.error(formatted);
        logToFile(formatted);
        if (error) {
            const errorStack = error.stack || error.toString();
            console.error(errorStack);
            logToFile(errorStack);
        }
        // In a real production system, this level might also trigger alerts (email, PagerDuty, etc.)
        // For a critical error, you might even want to force exit for safety.
        // process.exit(1); // Uncomment if a critical error should stop the bot immediately
    },
    exception: (error) => { /* ... existing exception logic ... */ }
};
```

---

### **FILE: `src/trading_ai_system.js`**

**19. Improvement: Dedicated `handlePrivateMessage` Method**
This method will process incoming private WebSocket messages (e.g., order fills, position updates), enhancing real-time responsiveness and state accuracy. It relies on the EventEmitter improvement for `bybit_websocket.js`.

```javascript
// In TradingAiSystem constructor:
    constructor() {
        // ... existing constructor code ...
        //
