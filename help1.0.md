Ah, seeker, the will of the digital realm shall be done! You wish to invoke these potent enchantments.

Pyrmethus shall now present the revised code, organized by file, for your direct integration. Copy each block into its designated file, replacing the old incantations with these new, fortified spells.

---

### 1. **WebSocket Connection Handling**
**File: `src/api/bybit_websocket.js`**

Replace the existing `connect()` method, and add the `scheduleReconnection()`, `constructor`, and `disconnect()` methods as shown below.

```javascript
// Replace the current connect() method with this improved version
connect() {
    const connectWebSocket = () => {
        this.ws = new WebSocket(this.url);
        
        this.ws.on('open', () => {
            logger.info("WebSocket connection established.");
            const subscription = { 
                op: "subscribe", 
                args: [`kline.${config.interval}.${config.symbol}`] 
            };
            this.ws.send(JSON.stringify(subscription));
            
            // Reset reconnect delay on successful connection
            this.reconnectDelay = 1000;
        });

        this.ws.on('message', (data) => {
            try {
                const message = JSON.parse(data.toString());
                if (message.topic && message.topic.startsWith('kline')) {
                    const candle = message.data[0];
                    if (candle.confirm === true) {
                        logger.info(`New confirmed ${config.interval}m candle for ${config.symbol}. Close: ${candle.close}`);
                        this.onNewCandle(); // Trigger the main analysis logic
                    }
                }
                
                // Handle pong response for keep-alive
                if (message.op === 'pong') {
                    this.lastPong = Date.now();
                }
            } catch (error) {
                logger.error("Error processing WebSocket message:", error);
            }
        });

        this.ws.on('close', (code, reason) => {
            logger.error(`WebSocket connection closed. Code: ${code}, Reason: ${reason}`);
            this.scheduleReconnection();
        });

        this.ws.on('error', (err) => {
            logger.exception("WebSocket error:", err);
            this.ws.close(); // Ensure proper cleanup
        });
    };

    // Initial connection
    connectWebSocket();
    
    // Keep-alive mechanism
    this.keepAliveInterval = setInterval(() => {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.ping();
            
            // Check if we're getting responses to our pings
            if (this.lastPong && Date.now() - this.lastPong > 30000) {
                logger.warn("No pong response received, reconnecting...");
                this.ws.close();
            }
        }
    }, 20000);
}

scheduleReconnection() {
    // Exponential backoff for reconnection
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
    logger.info(`Attempting to reconnect in ${this.reconnectDelay / 1000} seconds...`);
    
    setTimeout(() => this.connect(), this.reconnectDelay);
}

// Add to the class constructor
constructor(onNewCandleCallback) {
    this.url = config.bybit.wsUrl;
    this.onNewCandle = onNewCandleCallback;
    this.ws = null;
    this.reconnectDelay = 1000;
    this.lastPong = null;
    this.keepAliveInterval = null;
}

// Add cleanup method
disconnect() {
    if (this.keepAliveInterval) {
        clearInterval(this.keepAliveInterval);
    }
    if (this.ws) {
        this.ws.close();
    }
}
```

---

### 2. **Order Execution Safety**
**File: `src/core/risk_policy.js`**

Replace the entire `applyRiskPolicy` function with this enhanced version.

```javascript
// Enhanced risk policy with additional checks
export function applyRiskPolicy(proposedTrade, indicators, state) {
    if (!proposedTrade) {
        return { decision: 'HOLD', reason: 'No trade proposed by AI.' };
    }

    // Prevent conflicting actions
    if (proposedTrade.name === 'proposeTrade' && state.inPosition) {
        return { decision: 'HOLD', reason: 'Already in a position. Cannot enter new trade.' };
    }
    
    if (proposedTrade.name === 'proposeExit' && !state.inPosition) {
        return { decision: 'HOLD', reason: 'No position to exit.' };
    }

    if (proposedTrade.name === 'proposeTrade') {
        const { confidence } = proposedTrade.args;
        
        // Confidence threshold check
        if (confidence < config.ai.confidenceThreshold) {
            return { decision: 'HOLD', reason: `AI confidence (${confidence}) is below threshold (${config.ai.confidenceThreshold}).` };
        }
        
        // Volatility check using ATR
        const atrPercentage = (indicators.atr / indicators.price) * 100;
        if (atrPercentage > 5) { // If ATR is >5% of price
            return { decision: 'HOLD', reason: `Market volatility is too high (ATR: ${atrPercentage.toFixed(2)}%).` };
        }
        
        // Check if market is trending (optional)
        const priceVsSma = ((indicators.price - indicators.smaLong) / indicators.smaLong) * 100;
        if (Math.abs(priceVsSma) < 1) { // Price within 1% of long SMA
            return { decision: 'HOLD', reason: 'Market is not trending strongly enough.' };
        }
    }

    logger.info(`Risk policy approved the proposed action: ${proposedTrade.name}`);
    return { decision: 'PROCEED', trade: proposedTrade };
}
```

---

### 3. **Position Sizing Improvement**
**File: `src/core/trading_logic.js`**

Replace the existing `calculatePositionSize` and `determineExitPrices` functions with these improved versions.

```javascript
// Improved position sizing with ATR-based stop loss
export function calculatePositionSize(balance, currentPrice, atr, side) {
    const riskAmount = balance * (config.riskPercentage / 100);
    
    // Use ATR for dynamic stop loss instead of fixed percentage
    const atrMultiplier = 1.5; // Adjust based on strategy
    const stopLossDistance = atr * atrMultiplier;
    
    // Calculate position size
    const quantity = riskAmount / stopLossDistance;
    
    // Ensure minimum and maximum position size
    const minQuantity = 0.001; // Minimum trade size for BTC
    const maxQuantity = riskAmount / (currentPrice * 0.01); // Don't risk more than 1% of position
    
    return Math.max(minQuantity, Math.min(quantity, maxQuantity));
}

// Update the determineExitPrices function to use ATR
export function determineExitPrices(entryPrice, side, atr) {
    const atrMultiplier = 1.5;
    const rewardMultiplier = 2; // Risk-to-reward ratio
    
    const stopLossDistance = atr * atrMultiplier;
    const takeProfitDistance = stopLossDistance * rewardMultiplier;

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice - stopLossDistance;
        takeProfit = entryPrice + takeProfitDistance;
    } else { // Sell
        stopLoss = entryPrice + stopLossDistance; // Corrected from takeProfitDistance
        takeProfit = entryPrice - takeProfitDistance;
    }
    
    return { 
        stopLoss: parseFloat(stopLoss.toFixed(2)), 
        takeProfit: parseFloat(takeProfit.toFixed(2)) 
    };
}
```

---

### 4. **Enhanced Error Handling in API Calls**
**File: `src/api/bybit_api.js`**

Replace the existing `sendRequest` method with this robust version.

```javascript
// Add retry mechanism to API calls
async sendRequest(path, method, body = null, retries = 3) {
    const timestamp = Date.now().toString();
    const recvWindow = '5000';
    const bodyString = body ? JSON.stringify(body) : '';
    const signature = this.generateSignature(timestamp, recvWindow, bodyString);

    const headers = {
        'X-BAPI-API-KEY': this.apiKey,
        'X-BAPI-TIMESTAMP': timestamp,
        'X-BAPI-SIGN': signature,
        'X-BAPI-RECV-WINDOW': recvWindow,
        'Content-Type': 'application/json',
    };

    for (let attempt = 1; attempt <= retries; attempt++) {
        try {
            const response = await fetch(this.baseUrl + path, { 
                method, 
                headers, 
                body: body ? bodyString : null,
                timeout: 10000 // 10 second timeout
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.retCode !== 0) {
                // Handle specific Bybit error codes
                if (data.retCode === 10001) { // Insufficient balance
                    logger.error("Insufficient balance for trade");
                    throw new Error(`Bybit API Error (${path}): ${data.retMsg}`);
                } else if (data.retCode === 10002) { // Position conflict
                    logger.error("Position conflict detected");
                    throw new Error(`Bybit API Error (${path}): ${data.retMsg}`);
                } else {
                    throw new Error(`Bybit API Error (${path}): ${data.retMsg}`);
                }
            }
            
            return data.result;
        } catch (error) {
            if (attempt === retries) {
                logger.exception(`API call failed after ${retries} attempts:`, error);
                return null;
            }
            
            logger.warn(`API call attempt ${attempt} failed, retrying in ${attempt * 1000}ms:`, error.message);
            await new Promise(resolve => setTimeout(resolve, attempt * 1000));
        }
    }
}
```

---

### 5. **State Management Enhancement**
**File: `src/utils/state_manager.js`**

Replace the existing `loadState` function and add the `verifyPositionWithExchange` and `validateState` helper functions.

```javascript
export async function loadState() {
    try {
        const data = await fs.readFile(stateFilePath, 'utf-8');
        const state = JSON.parse(data);
        
        // Validate state structure
        if (!validateState(state)) {
            logger.warn("State file is invalid, creating a new one.");
            await saveState(defaultState);
            return { ...defaultState };
        }
        
        // Check if we need to reconcile with actual position
        if (state.inPosition) {
            const hasActualPosition = await verifyPositionWithExchange(state);
            if (!hasActualPosition) {
                logger.warn("State shows position but exchange doesn't, resetting state.");
                await saveState(defaultState);
                return { ...defaultState };
            }
        }
        
        return state;
    } catch (error) {
        if (error.code === 'ENOENT') {
            logger.info("No state file found, creating a new one.");
            await saveState(defaultState);
            return { ...defaultState };
        }
        logger.exception(error);
        return { ...defaultState };
    }
}

async function verifyPositionWithExchange(state) {
    // This would need to be implemented using the Bybit API
    // to check if the position actually exists on the exchange
    try {
        // Placeholder for actual exchange position verification
        // const position = await bybitApi.getOpenPosition(config.symbol);
        // return position !== null && parseFloat(position.size) > 0;
        return true; // Assume valid for now
    } catch (error) {
        logger.error("Error verifying position with exchange:", error);
        return false;
    }
}

function validateState(state) {
    return state && 
           typeof state.inPosition === 'boolean' &&
           (state.positionSide === null || state.positionSide === 'Buy' || state.positionSide === 'Sell') &&
           typeof state.entryPrice === 'number' &&
           typeof state.quantity === 'number';
}
```

---

### 6. **Enhanced Gemini API Prompt Engineering**
**File: `src/api/gemini_api.js`**

Replace the existing `prompt` constant and the `tools` array with these enhanced versions.

```javascript
// Enhanced prompt for better trading decisions
const prompt = `You are an expert trading analyst specializing in cryptocurrency markets. 
Analyze the provided market data and follow these guidelines:

STRICT RULES:
1. Only propose trades when technical indicators align with strong momentum signals
2. Never risk more than 2% of account equity on any single trade
3. Always recommend a stop-loss and take-profit level
4. Consider volatility (ATR) when setting position sizes
5. Favor trades with at least a 2:1 risk-reward ratio

TRADING BIASES:
- In high volatility (ATR > 3% of price), reduce position size by 50%
- During low volume periods, require stronger confirmation signals
- Avoid trading against the primary trend (price vs 50 SMA)

CURRENT MARKET CONTEXT:
${marketContext}

ANALYSIS REQUIREMENTS:
1. Assess trend strength and direction
2. Identify key support and resistance levels
3. Evaluate momentum indicators for convergence/divergence
4. Determine optimal entry, stop-loss, and take-profit levels
5. Calculate appropriate position size based on risk management rules

RESPONSE FORMAT:
- If proposing a trade: use proposeTrade with detailed reasoning and confidence score
- If proposing to exit: use proposeExit with detailed reasoning
- If no action: provide analysis explaining why current conditions don't meet criteria`;

// Update the tools definition to include more parameters
const tools = [{
    functionDeclarations: [
        {
            name: "proposeTrade",
            description: "Proposes a trade entry (Buy or Sell) based on comprehensive market analysis.",
            parameters: {
                type: "OBJECT",
                properties: {
                    side: { 
                        type: "STRING", 
                        enum: ["Buy", "Sell"],
                        description: "Direction of the trade" 
                    },
                    reasoning: { 
                        type: "STRING", 
                        description: "Detailed technical and fundamental reasoning for the trade" 
                    },
                    confidence: { 
                        type: "NUMBER", 
                        description: "Confidence score from 0.0 to 1.0 based on signal strength" 
                    },
                    recommendedSize: {
                        type: "NUMBER",
                        description: "Recommended position size as percentage of portfolio (0.5-2%)"
                    },
                    timeFrame: {
                        type: "STRING",
                        description: "Expected holding period (scalp/intraday/swing)"
                    }
                },
                required: ["side", "reasoning", "confidence"]
            }
        },
        // ... keep proposeExit tool
    ]
}];
```

---

**A Note of Caution, Seeker:**
Remember to carefully review each change as you integrate it. Ensure that any existing imports or variable declarations in your files are compatible with these new code blocks.

May your code compile swiftly and your bot trade with unparalleled wisdom! Let me know once these enchantments are woven into your system.