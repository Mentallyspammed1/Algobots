const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { URLSearchParams } = require('url');
const { setInterval } = require('timers/promises');
const { Decimal } = require('decimal.js');
const { init: initColors, Fore, Style } = require('chalk');
const dotenv = require('dotenv');
const fetch = require('node-fetch');
const { createLogger, format, transports } = require('winston');
require('winston-daily-rotate-file');
const WebSocket = require('ws');
const _ = require('lodash');
const moment = require('moment');
const express = require('express');
const http = require('http');
const socketIo = require('socket.io');

// Initialize colorama (chalk) and set decimal precision
Decimal.set({ precision: 28 });
initColors();
dotenv.config();

// Neon Color Scheme (using chalk)
const NEON_GREEN = Fore.greenBright;
const NEON_BLUE = Fore.cyan;
const NEON_PURPLE = Fore.magentaBright;
const NEON_YELLOW = Fore.yellowBright;
const NEON_RED = Fore.redBright;
const NEON_CYAN = Fore.cyanBright;
const RESET = Style.reset;

// Indicator specific colors (enhanced for scalping)
const INDICATOR_COLORS = {
    "SMA_5": Fore.blueBright,
    "SMA_20": Fore.blue,
    "EMA_5": Fore.magentaBright,
    "EMA_20": Fore.magenta,
    "ATR_5": Fore.yellow,
    "RSI_5": Fore.green,
    "StochRSI_5": Fore.cyan,
    "BB_Upper": Fore.red,
    "BB_Middle": Fore.white,
    "BB_Lower": Fore.red,
    "VWAP": Fore.white,
    "MACD_Line": Fore.green,
    "MACD_Signal": Fore.greenBright,
    "MACD_Hist": Fore.yellow,
    "ADX": Fore.cyan,
    "Momentum": Fore.magenta,
    "Orderbook_Imbalance": Fore.yellow,
    "Tick_Volume": Fore.cyan,
    "Bid_Ask_Spread": Fore.red,
    "Liquidity_Score": Fore.green,
    // New indicators
    "Williams_R": Fore.orange,
    "CCI": Fore.pink,
    "MFI": Fore.lime,
    "Price_Oscillator": Fore.teal,
    "Tick_Divergence": Fore.violet,
    "Scalping_Signal": Fore.magentaBright,
};

// --- Scalping-specific Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const CONFIG_FILE = "scalping_config.json";
const LOG_DIRECTORY = "bot_logs/scalping-bot/logs";
const WEBSOCKET_URL = "wss://stream.bybit.com/v5/public/linear";
const PAPER_TRADING_MODE = process.env.PAPER_TRADING_MODE === "true";
const MAX_API_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
const REQUEST_TIMEOUT = 10000;
const LOOP_DELAY_MS = 1000; // 1 second for scalping
const MIN_ORDER_SIZE = 0.001; // Minimum order size for Bybit
const PRICE_PRECISION = 2; // For BTCUSDT
const QTY_PRECISION = 4; // For BTCUSDT
const MAX_POSITIONS = 3; // Maximum concurrent positions for scalping
const MAX_POSITION_SIZE = 0.1; // Max 10% of account per position
const RISK_PER_TRADE = 0.5; // 0.5% risk per trade
const TAKE_PROFIT_RATIO = 1.2; // TP is 1.2x SL
const SCALPING_TIMEFRAMES = ["1", "3", "5"]; // 1m, 3m, 5m for scalping
const HIGH_IMPACT_NEWS_LOOKBACK_MINUTES = 30;

// Create log directory
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });

// --- Scalping Configuration Management ---
function loadScalpingConfig(filepath, logger) {
    const defaultConfig = {
        "symbol": "BTCUSDT",
        "timeframes": SCALPING_TIMEFRAMES,
        "loop_delay_ms": LOOP_DELAY_MS,
        "orderbook_limit": 25, // Reduced for faster processing
        "paper_trading": PAPER_TRADING_MODE,
        "scalping_strategy": {
            "enabled": true,
            "entry_conditions": {
                "min_signal_strength": 3.0,
                "min_price_movement": 0.1, // 0.1% price movement
                "min_volume_spike": 1.5, // 1.5x average volume
                "min_orderbook_imbalance": 0.3,
                "max_spread_percent": 0.05, // Max 0.05% spread
                "min_liquidity_score": 0.7
            },
            "exit_conditions": {
                "take_profit_atr_multiple": 1.2,
                "stop_loss_atr_multiple": 1.0,
                "trailing_stop_enabled": true,
                "trailing_atr_multiple": 0.5,
                "max_hold_time_ms": 300000, // 5 minutes max hold time
                "profit_target_percent": 0.3, // 0.3% profit target
                "loss_limit_percent": 0.2 // 0.2% loss limit
            }
        },
        "indicators": {
            "sma_short": true,
            "sma_long": true,
            "ema_short": true,
            "ema_long": true,
            "atr": true,
            "rsi": true,
            "stoch_rsi": true,
            "bollinger_bands": true,
            "vwap": true,
            "macd": true,
            "adx": true,
            "momentum": true,
            "orderbook_imbalance": true,
            "tick_volume": true,
            "bid_ask_spread": true,
            "liquidity_score": true,
            // New indicators
            "williams_r": true,
            "cci": true,
            "mfi": true,
            "price_oscillator": true,
            "tick_divergence": true
        },
        "weighted_scoring": {
            "enabled": true,
            "signal_threshold": 3.0,
            "weights": {
                "ema_alignment": 0.15,
                "sma_trend": 0.12,
                "momentum_rsi": 0.15,
                "momentum_williams_r": 0.10,
                "momentum_cci": 0.10,
                "volume_mfi": 0.12,
                "bollinger_bands": 0.08,
                "vwap": 0.05,
                "orderbook_imbalance": 0.08,
                "price_oscillator": 0.03,
                "tick_divergence": 0.02
            },
            "confirmation_required": 2, // Number of confirming indicators
            "signal_decay": 0.95, // Signal strength decay per bar
            "signal_momentum": 0.7 // Weight for signal momentum
        },
        "risk_management": {
            "max_positions": MAX_POSITIONS,
            "max_position_size_percent": MAX_POSITION_SIZE * 100,
            "risk_per_trade_percent": RISK_PER_TRADE,
            "max_daily_loss_percent": 5.0,
            "max_drawdown_percent": 8.0,
            "max_consecutive_losses": 5
        },
        "news_filter": {
            "enabled": true,
            "lookback_minutes": HIGH_IMPACT_NEWS_LOOKBACK_MINUTES,
            "impact_threshold": "high"
        },
        "dashboard": {
            "enabled": true,
            "port": 3001,
            "update_interval_ms": 1000
        }
    };
    
    if (!fs.existsSync(filepath)) {
        try {
            fs.writeFileSync(filepath, JSON.stringify(defaultConfig, null, 4), 'utf-8');
            logger.warn(`${NEON_YELLOW}Scalping config file not found. Created default config at ${filepath}${RESET}`);
            return defaultConfig;
        } catch (e) {
            logger.error(`${NEON_RED}Error creating default scalping config file: ${e.message}${RESET}`);
            return defaultConfig;
        }
    }
    
    try {
        let config = JSON.parse(fs.readFileSync(filepath, 'utf-8'));
        _ensureScalpingConfigKeys(config, defaultConfig);
        fs.writeFileSync(filepath, JSON.stringify(config, null, 4), 'utf-8');
        return config;
    } catch (e) {
        logger.error(`${NEON_RED}Error loading scalping config: ${e.message}. Using default.${RESET}`);
        return defaultConfig;
    }
}

function _ensureScalpingConfigKeys(config, defaultConfig) {
    for (const key in defaultConfig) {
        if (!config.hasOwnProperty(key)) {
            config[key] = defaultConfig[key];
        } else if (typeof defaultConfig[key] === 'object' && defaultConfig[key] !== null && !Array.isArray(defaultConfig[key])) {
            _ensureScalpingConfigKeys(config[key], defaultConfig[key]);
        }
    }
}

// --- Scalping-specific Logging Setup ---
class SensitiveFormatter {
    constructor(colors = false) {
        this.colors = colors;
        this.sensitiveWords = ["API_KEY", "API_SECRET", API_KEY, API_SECRET].filter(Boolean);
    }
    
    format(info) {
        let message = info.message;
        for (const word of this.sensitiveWords) {
            if (typeof word === 'string' && message.includes(word)) {
                message = message.replace(new RegExp(word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(word.length));
            }
        }
        info.message = message;
        return info;
    }
}

function setupScalpingLogger(logName, level = 'info') {
    const logger = createLogger({
        level: level,
        format: format.combine(
            format.timestamp({ format: 'HH:mm:ss.SSS' }),
            format(new SensitiveFormatter(false).format),
            format.printf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`)
        ),
        transports: [
            new transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${logName}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '5m',
                maxFiles: '2d'
            })
        ],
        exitOnError: false
    });
    
    if (!logger.transports.some(t => t instanceof transports.Console)) {
        logger.add(new transports.Console({
            format: format.combine(
                format.timestamp({ format: 'HH:mm:ss.SSS' }),
                format(new SensitiveFormatter(true).format),
                format.printf(info => {
                    let levelColor;
                    switch (info.level) {
                        case 'info': levelColor = NEON_BLUE; break;
                        case 'warn': levelColor = NEON_YELLOW; break;
                        case 'error': levelColor = NEON_RED; break;
                        default: levelColor = RESET;
                    }
                    return `${levelColor}${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}${RESET}`;
                })
            )
        }));
    }
    
    return logger;
}

// --- Scalping-specific API Interaction ---
class BybitScalpingAPI {
    constructor(logger) {
        this.logger = logger;
        this.ws = null;
        this.wsCallbacks = {};
        this.wsId = 0;
        this.rateLimits = {
            requestsPerMinute: 120,
            requestsPerSecond: 10,
            lastRequestTime: 0,
            requestCount: 0
        };
    }
    
    async makeRequest(method, endpoint, params = null, signed = false) {
        // Implement rate limiting for scalping
        const now = Date.now();
        const timeSinceLastRequest = now - this.rateLimits.lastRequestTime;
        const minInterval = 1000 / this.rateLimits.requestsPerSecond;
        
        if (timeSinceLastRequest < minInterval) {
            await timeout(minInterval - timeSinceLastRequest);
        }
        
        const url = `${BASE_URL}${endpoint}`;
        const headers = { "Content-Type": "application/json" };
        let requestOptions = { method, headers };
        
        if (signed) {
            if (!API_KEY || !API_SECRET) {
                throw new Error("API_KEY or API_SECRET not set for signed request");
            }
            
            const timestamp = String(Date.now());
            const recvWindow = "5000"; // Reduced for scalping
            
            if (method === "GET") {
                const queryString = params ? new URLSearchParams(params).toString() : "";
                const paramStr = timestamp + API_KEY + queryString;
                const signature = crypto.createHmac('sha256', API_SECRET).update(paramStr).digest('hex');
                
                headers["X-BAPI-API-KEY"] = API_KEY;
                headers["X-BAPI-TIMESTAMP"] = timestamp;
                headers["X-BAPI-SIGN"] = signature;
                headers["X-BAPI-RECV-WINDOW"] = recvWindow;
                
                requestOptions.headers = headers;
                requestOptions.url = `${url}?${queryString}`;
            } else { // POST
                const jsonParams = JSON.stringify(params);
                const paramStr = timestamp + API_KEY + jsonParams;
                const signature = crypto.createHmac('sha256', API_SECRET).update(paramStr).digest('hex');
                
                headers["X-BAPI-API-KEY"] = API_KEY;
                headers["X-BAPI-TIMESTAMP"] = timestamp;
                headers["X-BAPI-SIGN"] = signature;
                headers["X-BAPI-RECV-WINDOW"] = recvWindow;
                
                requestOptions.headers = headers;
                requestOptions.body = jsonParams;
                requestOptions.url = url;
            }
        } else {
            requestOptions.url = params ? `${url}?${new URLSearchParams(params).toString()}` : url;
        }
        
        try {
            const response = await fetch(requestOptions.url, { ...requestOptions, timeout: REQUEST_TIMEOUT });
            const data = await response.json();
            
            if (data.retCode !== 0) {
                throw new Error(`Bybit API Error: ${data.retMsg} (Code: ${data.retCode})`);
            }
            
            return data;
        } catch (e) {
            throw new Error(`Request Exception: ${e.message}`);
        }
    }
    
    async fetchKlines(symbol, interval, limit = 100) {
        const endpoint = "/v5/market/kline";
        const params = {
            category: "linear",
            symbol: symbol,
            interval: interval,
            limit: limit
        };
        
        const response = await this.makeRequest("GET", endpoint, params, false);
        
        if (response && response.result && response.result.list) {
            const klines = response.result.list.map(kline => ({
                timestamp: new Date(parseInt(kline[0])),
                open: parseFloat(kline[1]),
                high: parseFloat(kline[2]),
                low: parseFloat(kline[3]),
                close: parseFloat(kline[4]),
                volume: parseFloat(kline[5]),
                turnover: parseFloat(kline[6])
            }));
            
            // Sort by timestamp to ensure ascending order
            klines.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
            
            return klines;
        }
        
        throw new Error(`Failed to fetch klines for ${symbol} ${interval}`);
    }
    
    async fetchOrderbook(symbol, limit = 25) {
        const endpoint = "/v5/market/orderbook";
        const params = { category: "linear", symbol: symbol, limit: limit };
        
        const response = await this.makeRequest("GET", endpoint, params, false);
        
        if (response && response.result) {
            return response.result;
        }
        
        throw new Error(`Failed to fetch orderbook for ${symbol}`);
    }
    
    async fetchCurrentPrice(symbol) {
        const endpoint = "/v5/market/tickers";
        const params = { category: "linear", symbol: symbol };
        
        const response = await this.makeRequest("GET", endpoint, params, false);
        
        if (response && response.result && response.result.list && response.result.list.length > 0) {
            return parseFloat(response.result.list[0].lastPrice);
        }
        
        throw new Error(`Failed to fetch current price for ${symbol}`);
    }
    
    async placeOrder(symbol, side, quantity, price = null, orderType = "Limit") {
        if (PAPER_TRADING_MODE) {
            // Simulate order placement in paper trading mode
            const orderId = "paper_" + Date.now();
            const filledPrice = price || await this.fetchCurrentPrice(symbol);
            
            this.logger.info(`${NEON_GREEN}[Paper Trading] Simulated ${side} order: ${quantity} ${symbol} @ ${filledPrice}${RESET}`);
            
            return {
                orderId,
                symbol,
                side,
                quantity,
                price: filledPrice,
                status: "FILLED",
                filledQuantity: quantity,
                filledPrice,
                timestamp: Date.now()
            };
        }
        
        const endpoint = "/v5/order/create";
        const params = {
            category: "linear",
            symbol: symbol,
            side: side,
            orderType: orderType,
            qty: quantity,
            price: price,
            timeInForce: "GTC",
            reduceOnly: false
        };
        
        const response = await this.makeRequest("POST", endpoint, params, true);
        
        if (response && response.result) {
            this.logger.info(`${NEON_GREEN}Placed ${side} order: ${quantity} ${symbol} @ ${price || "market"} | ID: ${response.result.orderId}${RESET}`);
            return response.result;
        }
        
        throw new Error(`Failed to place ${side} order for ${symbol}`);
    }
    
    async closePosition(symbol, quantity, price = null) {
        if (PAPER_TRADING_MODE) {
            // Simulate position closing in paper trading mode
            const orderId = "paper_close_" + Date.now();
            const filledPrice = price || await this.fetchCurrentPrice(symbol);
            
            this.logger.info(`${NEON_GREEN}[Paper Trading] Simulated position close: ${quantity} ${symbol} @ ${filledPrice}${RESET}`);
            
            return {
                orderId,
                symbol,
                quantity,
                price: filledPrice,
                status: "FILLED",
                filledQuantity: quantity,
                filledPrice,
                timestamp: Date.now()
            };
        }
        
        const endpoint = "/v5/order/replace";
        const params = {
            category: "linear",
            symbol: symbol,
            qty: quantity,
            price: price,
            reduceOnly: true
        };
        
        const response = await this.makeRequest("POST", endpoint, params, true);
        
        if (response && response.result) {
            this.logger.info(`${NEON_GREEN}Closed position: ${quantity} ${symbol} @ ${price || "market"} | ID: ${response.result.orderId}${RESET}`);
            return response.result;
        }
        
        throw new Error(`Failed to close position for ${symbol}`);
    }
    
    // WebSocket for real-time data
    connectWebSocket(symbol) {
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket(WEBSOCKET_URL);
            
            this.ws.on('open', () => {
                this.logger.info(`${NEON_GREEN}WebSocket connected for ${symbol}${RESET}`);
                
                // Subscribe to orderbook and trades
                const subscribeMessage = {
                    op: "subscribe",
                    args: [
                        `orderbook.${symbol}`,
                        `trade.${symbol}`,
                        `publicTrade.${symbol}`
                    ]
                };
                
                this.ws.send(JSON.stringify(subscribeMessage));
                resolve();
            });
            
            this.ws.on('error', (error) => {
                this.logger.error(`${NEON_RED}WebSocket error: ${error.message}${RESET}`);
                reject(error);
            });
            
            this.ws.on('close', () => {
                this.logger.warn(`${NEON_YELLOW}WebSocket disconnected${RESET}`);
                // Attempt to reconnect after delay
                setTimeout(() => this.connectWebSocket(symbol), 5000);
            });
            
            this.ws.on('message', (data) => {
                const message = JSON.parse(data);
                
                // Handle different message types
                if (message.type === 'orderbook') {
                    this._handleOrderbookUpdate(message.data);
                } else if (message.type === 'trade') {
                    this._handleTradeUpdate(message.data);
                } else if (message.type === 'publicTrade') {
                    this._handlePublicTrade(message.data);
                }
            });
        });
    }
    
    _handleOrderbookUpdate(data) {
        // Process orderbook updates for scalping
        if (!this.wsCallbacks.orderbook) return;
        
        // Extract bid/ask levels
        const bids = data.b || [];
        const asks = data.a || [];
        
        // Calculate bid-ask spread
        if (bids.length > 0 && asks.length > 0) {
            const highestBid = parseFloat(bids[0][0]);
            const lowestAsk = parseFloat(asks[0][0]);
            const spread = lowestAsk - highestBid;
            const spreadPercent = (spread / highestBid) * 100;
            
            // Calculate orderbook imbalance
            const bidVolume = bids.slice(0, 10).reduce((sum, b) => sum + parseFloat(b[1]), 0);
            const askVolume = asks.slice(0, 10).reduce((sum, a) => sum + parseFloat(a[1]), 0);
            const totalVolume = bidVolume + askVolume;
            const imbalance = totalVolume > 0 ? (bidVolume - askVolume) / totalVolume : 0;
            
            // Calculate liquidity score
            const liquidityScore = totalVolume > 0 ? Math.min(1, totalVolume / 100) : 0;
            
            // Call callback with orderbook data
            if (this.wsCallbacks.orderbook) {
                this.wsCallbacks.orderbook({
                    symbol: data.s,
                    bids,
                    asks,
                    spread,
                    spreadPercent,
                    bidVolume,
                    askVolume,
                    imbalance,
                    liquidityScore,
                    timestamp: Date.now()
                });
            }
        }
    }
    
    _handleTradeUpdate(data) {
        // Process trade updates for scalping
        if (!this.wsCallbacks.trade) return;
        
        const trade = {
            symbol: data.s,
            price: parseFloat(p),
            side: data.S, // 'Buy' or 'Sell'
            size: parseFloat(data.v),
            timestamp: data.T
        };
        
        if (this.wsCallbacks.trade) {
            this.wsCallbacks.trade(trade);
        }
    }
    
    _handlePublicTrade(data) {
        // Process public trade data for scalping
        if (!this.wsCallbacks.publicTrade) return;
        
        const trade = {
            symbol: data.s,
            price: parseFloat(data.p),
            side: data.S, // 'Buy' or 'Sell'
            size: parseFloat(data.v),
            timestamp: data.ts
        };
        
        if (this.wsCallbacks.publicTrade) {
            this.wsCallbacks.publicTrade(trade);
        }
    }
    
    onOrderbookUpdate(callback) {
        this.wsCallbacks.orderbook = callback;
    }
    
    onTradeUpdate(callback) {
        this.wsCallbacks.trade = callback;
    }
    
    onPublicTradeUpdate(callback) {
        this.wsCallbacks.publicTrade = callback;
    }
}

// --- Scalping-specific Kline Data Structure ---
class ScalpingKlineData {
    constructor(data = []) {
        this.data = data; // Array of kline objects
        this.indicators = {};
        this.tickData = []; // Store tick-level data for tick divergence
    }
    
    get length() {
        return this.data.length;
    }
    
    get empty() {
        return this.data.length === 0;
    }
    
    get latest() {
        return this.data[this.data.length - 1];
    }
    
    get previous() {
        return this.data[this.data.length - 2];
    }
    
    // Get kline by index (supports negative indexing)
    get(index) {
        if (index < 0) index = this.data.length + index;
        return this.data[index];
    }
    
    // Get column as array
    column(colName) {
        return this.data.map(row => row[colName]);
    }
    
    // Add calculated column
    addColumn(colName, values) {
        if (values.length !== this.data.length) {
            throw new Error(`Length of values for column '${colName}' does not match DataFrame length.`);
        }
        this.data.forEach((row, i) => row[colName] = values[i]);
        this.indicators[colName] = values;
    }
    
    // Add tick data
    addTickData(tick) {
        this.tickData.push(tick);
        if (this.tickData.length > 1000) {
            this.tickData.shift(); // Keep only last 1000 ticks
        }
    }
    
    // Get tick data
    getTickData() {
        return this.tickData;
    }
    
    // Simple rolling mean
    rollingMean(colName, window) {
        if (this.data.length < window) return this.data.map(() => NaN);
        
        const series = this.column(colName).map(parseFloat);
        const result = new Array(series.length).fill(NaN);
        
        for (let i = window - 1; i < series.length; i++) {
            const sum = series.slice(i - window + 1, i + 1).reduce((a, b) => a + b, 0);
            result[i] = sum / window;
        }
        
        return result;
    }
    
    // Exponential moving average
    ewmMean(colName, span, minPeriods = 0) {
        const series = this.column(colName).map(parseFloat);
        if (series.length < minPeriods) return new Array(series.length).fill(NaN);
        
        const alpha = 2 / (span + 1);
        const result = new Array(series.length).fill(NaN);
        let ema = 0;
        let count = 0;
        
        for (let i = 0; i < series.length; i++) {
            const value = series[i];
            if (isNaN(value)) continue;
            
            if (count === 0) {
                ema = value;
            } else {
                ema = (value * alpha) + (ema * (1 - alpha));
            }
            
            count++;
            if (count >= minPeriods) {
                result[i] = ema;
            }
        }
        
        return result;
    }
    
    // Calculate difference between consecutive values
    diff(colName) {
        const series = this.column(colName).map(parseFloat);
        if (series.length < 1) return [];
        
        const result = [NaN];
        for (let i = 1; i < series.length; i++) {
            result.push(series[i] - series[i - 1]);
        }
        return result;
    }
    
    // Calculate price change percentage
    pctChange(colName) {
        const series = this.column(colName).map(parseFloat);
        if (series.length < 1) return [];
        
        const result = [NaN];
        for (let i = 1; i < series.length; i++) {
            if (series[i - 1] !== 0) {
                result.push((series[i] - series[i - 1]) / series[i - 1] * 100);
            } else {
                result.push(NaN);
            }
        }
        return result;
    }
    
    // Calculate standard deviation
    std(colName, window) {
        if (this.data.length < window) {
            return new Array(this.data.length).fill(NaN);
        }
        
        const series = this.column(colName).map(parseFloat);
        const result = new Array(series.length).fill(NaN);
        
        for (let i = window - 1; i < series.length; i++) {
            const window = series.slice(i - window + 1, i + 1);
            const mean = window.reduce((a, b) => a + b, 0) / window.length;
            const variance = window.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / window.length;
            result[i] = Math.sqrt(variance);
        }
        
        return result;
    }
}

// --- Scalping-specific Technical Indicators with 5 New Indicators ---
class ScalpingIndicators {
    constructor(klineData, logger, symbol) {
        this.klineData = klineData;
        this.logger = logger;
        this.symbol = symbol;
        this.indicatorValues = {};
        this.signalHistory = [];
        this.signalStrength = 0;
    }
    
    // Calculate all indicators for scalping
    calculateAll(config) {
        this.logger.debug(`[${this.symbol}] Calculating scalping indicators...`);
        
        // Short-term SMAs for quick trend identification
        if (config.indicators.sma_short) {
            const sma5 = this.klineData.rollingMean("close", 5);
            this.klineData.addColumn("SMA_5", sma5);
            this.indicatorValues["SMA_5"] = sma5[sma5.length - 1];
        }
        
        // Medium-term SMAs for trend confirmation
        if (config.indicators.sma_long) {
            const sma20 = this.klineData.rollingMean("close", 20);
            this.klineData.addColumn("SMA_20", sma20);
            this.indicatorValues["SMA_20"] = sma20[sma20.length - 1];
        }
        
        // Short-term EMAs for responsive signals
        if (config.indicators.ema_short) {
            const ema5 = this.klineData.ewmMean("close", 5, 5);
            this.klineData.addColumn("EMA_5", ema5);
            this.indicatorValues["EMA_5"] = ema5[ema5.length - 1];
        }
        
        // Medium-term EMAs for trend direction
        if (config.indicators.ema_long) {
            const ema20 = this.klineData.ewmMean("close", 20, 20);
            this.klineData.addColumn("EMA_20", ema20);
            this.indicatorValues["EMA_20"] = ema20[ema20.length - 1];
        }
        
        // ATR for volatility and stop-loss calculation
        if (config.indicators.atr) {
            const atr = this.calculateATR(5);
            this.klineData.addColumn("ATR_5", atr);
            this.indicatorValues["ATR_5"] = atr[atr.length - 1];
        }
        
        // RSI for momentum
        if (config.indicators.rsi) {
            const rsi = this.calculateRSI(5);
            this.klineData.addColumn("RSI_5", rsi);
            this.indicatorValues["RSI_5"] = rsi[rsi.length - 1];
        }
        
        // Stochastic RSI for overbought/oversold conditions
        if (config.indicators.stoch_rsi) {
            const [stochRsiK, stochRsiD] = this.calculateStochRSI(5, 3, 3);
            this.klineData.addColumn("StochRSI_5", stochRsiK);
            this.indicatorValues["StochRSI_5"] = stochRsiK[stochRsiK.length - 1];
        }
        
        // Bollinger Bands for volatility and price levels
        if (config.indicators.bollinger_bands) {
            const [bbUpper, bbMiddle, bbLower] = this.calculateBollingerBands(10, 1.5);
            this.klineData.addColumn("BB_Upper", bbUpper);
            this.klineData.addColumn("BB_Middle", bbMiddle);
            this.klineData.addColumn("BB_Lower", bbLower);
            this.indicatorValues["BB_Upper"] = bbUpper[bbUpper.length - 1];
            this.indicatorValues["BB_Middle"] = bbMiddle[bbMiddle.length - 1];
            this.indicatorValues["BB_Lower"] = bbLower[bbLower.length - 1];
        }
        
        // VWAP for intraday price reference
        if (config.indicators.vwap) {
            const vwap = this.calculateVWAP();
            this.klineData.addColumn("VWAP", vwap);
            this.indicatorValues["VWAP"] = vwap[vwap.length - 1];
        }
        
        // MACD for trend and momentum
        if (config.indicators.macd) {
            const [macdLine, signalLine, histogram] = this.calculateMACD(5, 15, 5);
            this.klineData.addColumn("MACD_Line", macdLine);
            this.klineData.addColumn("MACD_Signal", signalLine);
            this.klineData.addColumn("MACD_Hist", histogram);
            this.indicatorValues["MACD_Line"] = macdLine[macdLine.length - 1];
            this.indicatorValues["MACD_Signal"] = signalLine[signalLine.length - 1];
            this.indicatorValues["MACD_Hist"] = histogram[histogram.length - 1];
        }
        
        // ADX for trend strength
        if (config.indicators.adx) {
            const [adx, plusDI, minusDI] = this.calculateADX(5);
            this.klineData.addColumn("ADX", adx);
            this.klineData.addColumn("PlusDI", plusDI);
            this.klineData.addColumn("MinusDI", minusDI);
            this.indicatorValues["ADX"] = adx[adx.length - 1];
            this.indicatorValues["PlusDI"] = plusDI[plusDI.length - 1];
            this.indicatorValues["MinusDI"] = minusDI[minusDI.length - 1];
        }
        
        // Momentum indicator
        if (config.indicators.momentum) {
            const momentum = this.calculateMomentum(5);
            this.klineData.addColumn("Momentum", momentum);
            this.indicatorValues["Momentum"] = momentum[momentum.length - 1];
        }
        
        // === NEW INDICATORS FOR SCALPING ===
        
        // 1. Williams %R for short-term overbought/oversold
        if (config.indicators.williams_r) {
            const williamsR = this.calculateWilliamsR(5);
            this.klineData.addColumn("Williams_R", williamsR);
            this.indicatorValues["Williams_R"] = williamsR[williamsR.length - 1];
        }
        
        // 2. CCI (Commodity Channel Index) for momentum
        if (config.indicators.cci) {
            const cci = this.calculateCCI(5);
            this.klineData.addColumn("CCI", cci);
            this.indicatorValues["CCI"] = cci[cci.length - 1];
        }
        
        // 3. MFI (Money Flow Index) for volume-weighted momentum
        if (config.indicators.mfi) {
            const mfi = this.calculateMFI(5);
            this.klineData.addColumn("MFI", mfi);
            this.indicatorValues["MFI"] = mfi[mfi.length - 1];
        }
        
        // 4. Price Oscillator for trend changes
        if (config.indicators.price_oscillator) {
            const priceOscillator = this.calculatePriceOscillator(5, 10);
            this.klineData.addColumn("Price_Oscillator", priceOscillator);
            this.indicatorValues["Price_Oscillator"] = priceOscillator[priceOscillator.length - 1];
        }
        
        // 5. Tick Divergence for short-term reversals
        if (config.indicators.tick_divergence) {
            const tickDivergence = this.calculateTickDivergence();
            this.klineData.addColumn("Tick_Divergence", tickDivergence);
            this.indicatorValues["Tick_Divergence"] = tickDivergence[tickDivergence.length - 1];
        }
    }
    
    // Calculate Average True Range (ATR)
    calculateATR(period) {
        if (this.klineData.length < period + 1) return new Array(this.klineData.length).fill(NaN);
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tr = new Array(this.klineData.length).fill(NaN);
        
        // Calculate True Range for each bar
        for (let i = 1; i < this.klineData.length; i++) {
            const highLow = high[i] - low[i];
            const highPrevClose = Math.abs(high[i] - close[i - 1]);
            const lowPrevClose = Math.abs(low[i] - close[i - 1]);
            tr[i] = Math.max(highLow, highPrevClose, lowPrevClose);
        }
        
        // Calculate ATR using EMA for responsiveness
        return this.ewmMeanCustom(tr, period, period);
    }
    
    // Calculate Relative Strength Index (RSI)
    calculateRSI(period) {
        if (this.klineData.length <= period) return new Array(this.klineData.length).fill(NaN);
        
        const close = this.klineData.column("close");
        const delta = this.klineData.diff("close");
        const gain = delta.map(d => Math.max(0, d));
        const loss = delta.map(d => Math.max(0, -d));
        
        // Calculate average gain and loss using EMA
        const avgGain = this.ewmMeanCustom(gain, period, period);
        const avgLoss = this.ewmMeanCustom(loss, period, period);
        
        const rsi = new Array(this.klineData.length).fill(NaN);
        
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(avgGain[i]) && !isNaN(avgLoss[i])) {
                if (avgLoss[i] === 0) {
                    rsi[i] = 100; // If no loss, RSI is 100
                } else {
                    const rs = avgGain[i] / avgLoss[i];
                    rsi[i] = 100 - (100 / (1 + rs));
                }
            }
        }
        
        return rsi;
    }
    
    // Calculate Stochastic RSI
    calculateStochRSI(period, kPeriod, dPeriod) {
        if (this.klineData.length <= period + dPeriod) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        
        const rsi = this.calculateRSI(period);
        const lowestRsi = new Array(this.klineData.length).fill(NaN);
        const highestRsi = new Array(this.klineData.length).fill(NaN);
        
        // Find lowest and highest RSI values in the window
        for (let i = period - 1; i < this.klineData.length; i++) {
            const rsiWindow = rsi.slice(i - period + 1, i + 1).filter(val => !isNaN(val));
            if (rsiWindow.length > 0) {
                lowestRsi[i] = Math.min(...rsiWindow);
                highestRsi[i] = Math.max(...rsiWindow);
            }
        }
        
        // Calculate Stoch RSI K
        const stochRsiK = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(rsi[i]) && !isNaN(lowestRsi[i]) && !isNaN(highestRsi[i])) {
                const denominator = highestRsi[i] - lowestRsi[i];
                if (denominator === 0) {
                    stochRsiK[i] = 50; // Neutral if no range
                } else {
                    stochRsiK[i] = ((rsi[i] - lowestRsi[i]) / denominator) * 100;
                }
            }
        }
        
        // Calculate Stoch RSI D (SMA of K)
        const stochRsiD = this.klineData.rollingMean(stochRsiK, dPeriod);
        
        return [stochRsiK, stochRsiD];
    }
    
    // Calculate Bollinger Bands
    calculateBollingerBands(period, stdDev) {
        if (this.klineData.length < period) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        
        const close = this.klineData.column("close");
        const middleBand = this.klineData.rollingMean("close", period);
        const std = new Array(this.klineData.length).fill(NaN);
        
        // Calculate standard deviation
        for (let i = period - 1; i < this.klineData.length; i++) {
            const window = close.slice(i - period + 1, i + 1);
            const mean = middleBand[i];
            const sumOfSquares = window.reduce((acc, val) => acc + (val - mean) ** 2, 0);
            std[i] = Math.sqrt(sumOfSquares / period);
        }
        
        // Calculate upper and lower bands
        const upperBand = middleBand.map((mb, i) => mb + (std[i] * stdDev));
        const lowerBand = middleBand.map((mb, i) => mb - (std[i] * stdDev));
        
        return [upperBand, middleBand, lowerBand];
    }
    
    // Calculate Volume Weighted Average Price (VWAP)
    calculateVWAP() {
        if (this.klineData.empty) return new Array(this.klineData.length).fill(NaN);
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");
        const typicalPrice = high.map((h, i) => (h + low[i] + close[i]) / 3);
        const tpVol = typicalPrice.map((tp, i) => tp * volume[i]);
        
        const cumulativeTpVol = new Array(this.klineData.length).fill(NaN);
        const cumulativeVol = new Array(this.klineData.length).fill(NaN);
        const vwap = new Array(this.klineData.length).fill(NaN);
        
        let sumTpVol = 0;
        let sumVol = 0;
        
        for (let i = 0; i < this.klineData.length; i++) {
            sumTpVol += tpVol[i];
            sumVol += volume[i];
            cumulativeTpVol[i] = sumTpVol;
            cumulativeVol[i] = sumVol;
            
            if (sumVol !== 0) {
                vwap[i] = sumTpVol / sumVol;
            } else {
                vwap[i] = NaN;
            }
        }
        
        return vwap;
    }
    
    // Calculate MACD
    calculateMACD(fastPeriod, slowPeriod, signalPeriod) {
        if (this.klineData.length < slowPeriod + signalPeriod) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        
        const close = this.klineData.column("close");
        const emaFast = this.ewmMeanCustom(close, fastPeriod, fastPeriod);
        const emaSlow = this.ewmMeanCustom(close, slowPeriod, slowPeriod);
        const macdLine = emaFast.map((fast, i) => fast - emaSlow[i]);
        const signalLine = this.ewmMeanCustom(macdLine, signalPeriod, signalPeriod);
        const histogram = macdLine.map((macd, i) => macd - signalLine[i]);
        
        return [macdLine, signalLine, histogram];
    }
    
    // Calculate ADX (Average Directional Index)
    calculateADX(period) {
        if (this.klineData.length < period * 2) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tr = this.calculateATR(period);
        
        // Calculate +DM and -DM
        const plusDM = new Array(this.klineData.length).fill(0);
        const minusDM = new Array(this.klineData.length).fill(0);
        
        for (let i = 1; i < this.klineData.length; i++) {
            const upMove = high[i] - high[i - 1];
            const downMove = low[i - 1] - low[i];
            plusDM[i] = (upMove > downMove && upMove > 0) ? upMove : 0;
            minusDM[i] = (downMove > upMove && downMove > 0) ? downMove : 0;
        }
        
        // Calculate +DI and -DI
        const plusDI = this.ewmMeanCustom(plusDM, period, period).map((val, i) => 
            !isNaN(val) && !isNaN(tr[i]) && tr[i] !== 0 ? (val / tr[i]) * 100 : NaN
        );
        const minusDI = this.ewmMeanCustom(minusDM, period, period).map((val, i) => 
            !isNaN(val) && !isNaN(tr[i]) && tr[i] !== 0 ? (val / tr[i]) * 100 : NaN
        );
        
        // Calculate DX (Directional Index)
        const dx = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(plusDI[i]) && !isNaN(minusDI[i])) {
                const diDiff = Math.abs(plusDI[i] - minusDI[i]);
                const diSum = plusDI[i] + minusDI[i];
                dx[i] = (diSum === 0) ? 0 : (diDiff / diSum) * 100;
            }
        }
        
        // Calculate ADX (EMA of DX)
        const adx = this.ewmMeanCustom(dx, period, period);
        
        return [adx, plusDI, minusDI];
    }
    
    // Calculate Momentum
    calculateMomentum(period) {
        if (this.klineData.length < period) return new Array(this.klineData.length).fill(NaN);
        
        const close = this.klineData.column("close");
        const momentum = new Array(this.klineData.length).fill(NaN);
        
        for (let i = period - 1; i < this.klineData.length; i++) {
            if (!isNaN(close[i]) && !isNaN(close[i - period])) {
                momentum[i] = close[i] - close[i - period];
            }
        }
        
        return momentum;
    }
    
    // === NEW INDICATOR CALCULATIONS ===
    
    // 1. Calculate Williams %R
    calculateWilliamsR(period) {
        if (this.klineData.length < period) return new Array(this.klineData.length).fill(NaN);
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const highestHigh = new Array(this.klineData.length).fill(NaN);
        const lowestLow = new Array(this.klineData.length).fill(NaN);
        
        // Find highest high and lowest low in the period
        for (let i = period - 1; i < this.klineData.length; i++) {
            const highWindow = high.slice(i - period + 1, i + 1);
            const lowWindow = low.slice(i - period + 1, i + 1);
            highestHigh[i] = Math.max(...highWindow);
            lowestLow[i] = Math.min(...lowWindow);
        }
        
        // Calculate Williams %R
        const williamsR = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(close[i]) && !isNaN(highestHigh[i]) && !isNaN(lowestLow[i])) {
                const denominator = highestHigh[i] - lowestLow[i];
                if (denominator === 0) {
                    williamsR[i] = -50; // Neutral if no range
                } else {
                    williamsR[i] = -100 * ((highestHigh[i] - close[i]) / denominator);
                }
            }
        }
        
        return williamsR;
    }
    
    // 2. Calculate CCI (Commodity Channel Index)
    calculateCCI(period) {
        if (this.klineData.length < period) return new Array(this.klineData.length).fill(NaN);
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tp = high.map((h, i) => (h + low[i] + close[i]) / 3);
        const smaTp = this.klineData.rollingMean(tp, period);
        const mad = new Array(this.klineData.length).fill(NaN);
        
        // Calculate Mean Absolute Deviation
        for (let i = period - 1; i < this.klineData.length; i++) {
            const tpWindow = tp.slice(i - period + 1, i + 1);
            const meanTp = smaTp[i];
            const absDevSum = tpWindow.reduce((acc, val) => acc + Math.abs(val - meanTp), 0);
            mad[i] = absDevSum / period;
        }
        
        // Calculate CCI
        const cci = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(tp[i]) && !isNaN(smaTp[i]) && !isNaN(mad[i])) {
                if (mad[i] === 0) {
                    cci[i] = 0; // Handle division by zero
                } else {
                    cci[i] = (tp[i] - smaTp[i]) / (0.015 * mad[i]);
                }
            }
        }
        
        return cci;
    }
    
    // 3. Calculate MFI (Money Flow Index)
    calculateMFI(period) {
        if (this.klineData.length <= period) return new Array(this.klineData.length).fill(NaN);
        
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");
        const typicalPrice = high.map((h, i) => (h + low[i] + close[i]) / 3);
        const moneyFlow = typicalPrice.map((tp, i) => tp * volume[i]);
        
        // Determine positive and negative money flow
        const positiveFlow = new Array(this.klineData.length).fill(0);
        const negativeFlow = new Array(this.klineData.length).fill(0);
        
        for (let i = 1; i < this.klineData.length; i++) {
            if (typicalPrice[i] > typicalPrice[i - 1]) {
                positiveFlow[i] = moneyFlow[i];
            } else if (typicalPrice[i] < typicalPrice[i - 1]) {
                negativeFlow[i] = moneyFlow[i];
            }
        }
        
        // Calculate cumulative positive and negative money flow
        const positiveMfSum = new Array(this.klineData.length).fill(NaN);
        const negativeMfSum = new Array(this.klineData.length).fill(NaN);
        
        for (let i = period - 1; i < this.klineData.length; i++) {
            positiveMfSum[i] = positiveFlow.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
            negativeMfSum[i] = negativeFlow.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
        }
        
        // Calculate MFI
        const mfi = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(positiveMfSum[i]) && !isNaN(negativeMfSum[i])) {
                const mfRatio = (negativeMfSum[i] === 0) ? (positiveMfSum[i] === 0 ? 0 : Infinity) : positiveMfSum[i] / negativeMfSum[i];
                mfi[i] = 100 - (100 / (1 + mfRatio));
            }
        }
        
        return mfi;
    }
    
    // 4. Calculate Price Oscillator
    calculatePriceOscillator(fastPeriod, slowPeriod) {
        if (this.klineData.length < slowPeriod) return new Array(this.klineData.length).fill(NaN);
        
        const close = this.klineData.column("close");
        const emaFast = this.ewmMeanCustom(close, fastPeriod, fastPeriod);
        const emaSlow = this.ewmMeanCustom(close, slowPeriod, slowPeriod);
        
        // Calculate Price Oscillator as percentage difference
        const priceOscillator = emaFast.map((fast, i) => {
            if (!isNaN(emaSlow[i]) && emaSlow[i] !== 0) {
                return ((fast - emaSlow[i]) / emaSlow[i]) * 100;
            }
            return NaN;
        });
        
        return priceOscillator;
    }
    
    // 5. Calculate Tick Divergence
    calculateTickDivergence() {
        if (this.klineData.tickData.length < 20) return new Array(this.klineData.length).fill(NaN);
        
        const tickData = this.klineData.getTickData();
        const close = this.klineData.column("close");
        const tickDivergence = new Array(this.klineData.length).fill(NaN);
        
        // Calculate tick volume and price momentum
        for (let i = 5; i < this.klineData.length; i++) {
            const recentTicks = tickData.slice(-20); // Last 20 ticks
            const recentClose = close.slice(i - 5, i);
            
            // Calculate tick pressure (buy vs sell ticks)
            const buyTicks = recentTicks.filter(tick => tick.side === 'Buy').length;
            const sellTicks = recentTicks.filter(tick => tick.side === 'Sell').length;
            const tickPressure = (buyTicks - sellTicks) / (buyTicks + sellTicks);
            
            // Calculate price momentum
            const priceChange = recentClose[recentClose.length - 1] - recentClose[0];
            const priceMomentum = priceChange / Math.abs(recentClose[0]) * 100;
            
            // Calculate divergence (when tick pressure and price momentum diverge)
            if (Math.abs(tickPressure) > 0.3 && Math.abs(priceMomentum) < 0.1) {
                tickDivergence[i] = tickPressure > 0 ? 1 : -1; // Bullish or bearish divergence
            } else {
                tickDivergence[i] = 0; // No divergence
            }
        }
        
        return tickDivergence;
    }
    
    // Custom EWM calculation for indicators
    ewmMeanCustom(series, span, minPeriods = 0) {
        if (series.length < minPeriods) return new Array(series.length).fill(NaN);
        
        const alpha = 2 / (span + 1);
        const result = new Array(series.length).fill(NaN);
        let ema = 0;
        let count = 0;
        
        for (let i = 0; i < series.length; i++) {
            const value = parseFloat(series[i]);
            if (isNaN(value)) {
                result[i] = NaN;
                continue;
            }
            
            if (count === 0) {
                ema = value;
            } else {
                ema = (value * alpha) + (ema * (1 - alpha));
            }
            
            count++;
            if (count >= minPeriods) {
                result[i] = ema;
            }
        }
        
        return result;
    }
    
    // Generate scalping signal using weighted scoring
    generateWeightedScalpingSignal(orderbookData, config) {
        if (this.klineData.empty) {
            return { signal: "HOLD", strength: 0, reason: "No kline data" };
        }
        
        const latest = this.latest;
        const previous = this.previous;
        const weights = config.weighted_scoring.weights;
        const signalThreshold = config.weighted_scoring.signal_threshold;
        const signalDecay = config.weighted_scoring.signal_decay;
        const signalMomentum = config.weighted_scoring.signal_momentum;
        
        // Initialize score components
        let scoreComponents = {
            ema_alignment: 0,
            sma_trend: 0,
            momentum_rsi: 0,
            momentum_williams_r: 0,
            momentum_cci: 0,
            volume_mfi: 0,
            bollinger_bands: 0,
            vwap: 0,
            orderbook_imbalance: 0,
            price_oscillator: 0,
            tick_divergence: 0
        };
        
        let confirmingIndicators = 0;
        let signalReasons = [];
        
        // Check price movement condition
        const priceChange = this.klineData.pctChange("close");
        const latestPriceChange = priceChange[priceChange.length - 1];
        
        if (Math.abs(latestPriceChange) >= config.scalping_strategy.entry_conditions.min_price_movement) {
            confirmingIndicators++;
            signalReasons.push(`Price movement: ${latestPriceChange.toFixed(2)}%`);
        }
        
        // 1. EMA Alignment (Weight: 0.15)
        if (this.indicatorValues["EMA_5"] && this.indicatorValues["EMA_20"]) {
            const ema5 = this.indicatorValues["EMA_5"];
            const ema20 = this.indicatorValues["EMA_20"];
            
            if (ema5 > ema20 && latest.close > ema5) {
                scoreComponents.ema_alignment = 1.0;
                confirmingIndicators++;
                signalReasons.push("Strong bullish EMA alignment");
            } else if (ema5 < ema20 && latest.close < ema5) {
                scoreComponents.ema_alignment = -1.0;
                confirmingIndicators++;
                signalReasons.push("Strong bearish EMA alignment");
            } else if (ema5 > ema20) {
                scoreComponents.ema_alignment = 0.5;
                signalReasons.push("Bullish EMA alignment");
            } else if (ema5 < ema20) {
                scoreComponents.ema_alignment = -0.5;
                signalReasons.push("Bearish EMA alignment");
            }
        }
        
        // 2. SMA Trend (Weight: 0.12)
        if (this.indicatorValues["SMA_5"] && this.indicatorValues["SMA_20"]) {
            const sma5 = this.indicatorValues["SMA_5"];
            const sma20 = this.indicatorValues["SMA_20"];
            
            if (sma5 > sma20 && latest.close > sma5) {
                scoreComponents.sma_trend = 1.0;
                confirmingIndicators++;
                signalReasons.push("Bullish SMA trend");
            } else if (sma5 < sma20 && latest.close < sma5) {
                scoreComponents.sma_trend = -1.0;
                confirmingIndicators++;
                signalReasons.push("Bearish SMA trend");
            }
        }
        
        // 3. RSI Momentum (Weight: 0.15)
        if (this.indicatorValues["RSI_5"]) {
            const rsi = this.indicatorValues["RSI_5"];
            
            if (rsi < 20) {
                scoreComponents.momentum_rsi = 1.0;
                confirmingIndicators++;
                signalReasons.push("RSI oversold - strong reversal potential");
            } else if (rsi > 80) {
                scoreComponents.momentum_rsi = -1.0;
                confirmingIndicators++;
                signalReasons.push("RSI overbought - reversal likely");
            } else if (rsi < 50) {
                scoreComponents.momentum_rsi = 0.5;
                signalReasons.push("RSI below 50 - bearish momentum");
            } else {
                scoreComponents.momentum_rsi = -0.5;
                signalReasons.push("RSI above 50 - bullish momentum");
            }
        }
        
        // 4. Williams %R Momentum (Weight: 0.10)
        if (this.indicatorValues["Williams_R"]) {
            const williamsR = this.indicatorValues["Williams_R"];
            
            if (williamsR < -80) {
                scoreComponents.momentum_williams_r = 1.0;
                confirmingIndicators++;
                signalReasons.push("Williams %R oversold - reversal likely");
            } else if (williamsR > -20) {
                scoreComponents.momentum_williams_r = -1.0;
                confirmingIndicators++;
                signalReasons.push("Williams %R overbought - reversal likely");
            } else if (williamsR < -50) {
                scoreComponents.momentum_williams_r = 0.5;
                signalReasons.push("Williams %R below -50 - bearish");
            } else {
                scoreComponents.momentum_williams_r = -0.5;
                signalReasons.push("Williams %R above -50 - bullish");
            }
        }
        
        // 5. CCI Momentum (Weight: 0.10)
        if (this.indicatorValues["CCI"]) {
            const cci = this.indicatorValues["CCI"];
            
            if (cci < -100) {
                scoreComponents.momentum_cci = 1.0;
                confirmingIndicators++;
                signalReasons.push("CCI oversold - reversal likely");
            } else if (cci > 100) {
                scoreComponents.momentum_cci = -1.0;
                confirmingIndicators++;
                signalReasons.push("CCI overbought - reversal likely");
            } else if (cci < 0) {
                scoreComponents.momentum_cci = 0.5;
                signalReasons.push("CCI negative - bearish");
            } else {
                scoreComponents.momentum_cci = -0.5;
                signalReasons.push("CCI positive - bullish");
            }
        }
        
        // 6. MFI Volume (Weight: 0.12)
        if (this.indicatorValues["MFI"]) {
            const mfi = this.indicatorValues["MFI"];
            
            if (mfi < 20) {
                scoreComponents.volume_mfi = 1.0;
                confirmingIndicators++;
                signalReasons.push("MFI oversold - volume-backed reversal");
            } else if (mfi > 80) {
                scoreComponents.volume_mfi = -1.0;
                confirmingIndicators++;
                signalReasons.push("MFI overbought - volume-backed reversal");
            } else if (mfi < 50) {
                scoreComponents.volume_mfi = 0.5;
                signalReasons.push("MFI below 50 - bearish volume");
            } else {
                scoreComponents.volume_mfi = -0.5;
                signalReasons.push("MFI above 50 - bullish volume");
            }
        }
        
        // 7. Bollinger Bands (Weight: 0.08)
        if (this.indicatorValues["BB_Upper"] && this.indicatorValues["BB_Lower"]) {
            const bbUpper = this.indicatorValues["BB_Upper"];
            const bbLower = this.indicatorValues["BB_Lower"];
            
            if (latest.close < bbLower) {
                scoreComponents.bollinger_bands = 1.0;
                confirmingIndicators++;
                signalReasons.push("Price below lower Bollinger Band - reversal likely");
            } else if (latest.close > bbUpper) {
                scoreComponents.bollinger_bands = -1.0;
                confirmingIndicators++;
                signalReasons.push("Price above upper Bollinger Band - reversal likely");
            }
        }
        
        // 8. VWAP (Weight: 0.05)
        if (this.indicatorValues["VWAP"]) {
            const vwap = this.indicatorValues["VWAP"];
            
            if (latest.close > vwap) {
                scoreComponents.vwap = -0.5;
                signalReasons.push("Price above VWAP - intraday bullish");
            } else if (latest.close < vwap) {
                scoreComponents.vwap = 0.5;
                signalReasons.push("Price below VWAP - intraday bearish");
            }
        }
        
        // 9. Orderbook Imbalance (Weight: 0.08)
        if (orderbookData && config.indicators.orderbook_imbalance) {
            const imbalance = orderbookData.imbalance;
            
            if (imbalance > config.scalping_strategy.entry_conditions.min_orderbook_imbalance) {
                scoreComponents.orderbook_imbalance = 1.0;
                confirmingIndicators++;
                signalReasons.push(`Strong buy-side imbalance: ${imbalance.toFixed(2)}`);
            } else if (imbalance < -config.scalping_strategy.entry_conditions.min_orderbook_imbalance) {
                scoreComponents.orderbook_imbalance = -1.0;
                confirmingIndicators++;
                signalReasons.push(`Strong sell-side imbalance: ${imbalance.toFixed(2)}`);
            }
        }
        
        // 10. Price Oscillator (Weight: 0.03)
        if (this.indicatorValues["Price_Oscillator"]) {
            const po = this.indicatorValues["Price_Oscillator"];
            
            if (po > 0.5) {
                scoreComponents.price_oscillator = -0.5;
                signalReasons.push("Price oscillator positive - uptrend");
            } else if (po < -0.5) {
                scoreComponents.price_oscillator = 0.5;
                signalReasons.push("Price oscillator negative - downtrend");
            }
        }
        
        // 11. Tick Divergence (Weight: 0.02)
        if (this.indicatorValues["Tick_Divergence"]) {
            const td = this.indicatorValues["Tick_Divergence"];
            
            if (td === 1) {
                scoreComponents.tick_divergence = 1.0;
                confirmingIndicators++;
                signalReasons.push("Bullish tick divergence detected");
            } else if (td === -1) {
                scoreComponents.tick_divergence = -1.0;
                confirmingIndicators++;
                signalReasons.push("Bearish tick divergence detected");
            }
        }
        
        // Calculate weighted score
        let weightedScore = 0;
        for (const component in scoreComponents) {
            weightedScore += scoreComponents[component] * weights[component];
        }
        
        // Apply signal momentum (previous signal strength affects current signal)
        if (this.signalHistory.length > 0) {
            const prevSignalStrength = this.signalStrength;
            weightedScore = (weightedScore * (1 - signalMomentum)) + (prevSignalStrength * signalMomentum);
        }
        
        // Apply signal decay
        weightedScore *= signalDecay;
        
        // Update signal history
        this.signalHistory.push({
            timestamp: Date.now(),
            score: weightedScore,
            components: scoreComponents,
            confirmingIndicators: confirmingIndicators
        });
        
        // Keep only last 10 signals in history
        if (this.signalHistory.length > 10) {
            this.signalHistory.shift();
        }
        
        // Update current signal strength
        this.signalStrength = weightedScore;
        
        // Determine final signal
        let finalSignal = "HOLD";
        let finalStrength = Math.abs(weightedScore);
        
        if (weightedScore >= signalThreshold && confirmingIndicators >= config.weighted_scoring.confirmation_required) {
            finalSignal = "BUY";
        } else if (weightedScore <= -signalThreshold && confirmingIndicators >= config.weighted_scoring.confirmation_required) {
            finalSignal = "SELL";
        }
        
        return {
            signal: finalSignal,
            strength: finalStrength,
            rawScore: weightedScore,
            reasons: signalReasons,
            confirmingIndicators: confirmingIndicators,
            components: scoreComponents,
            signalHistory: this.signalHistory
        };
    }
}

// --- Scalping-specific Position Management ---
class ScalpingPositionManager {
    constructor(config, logger, symbol) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.openPositions = [];
        this.maxPositions = config.risk_management.max_positions;
        this.maxPositionSize = config.risk_management.max_position_size_percent / 100;
        this.riskPerTrade = config.risk_management.risk_per_trade_percent / 100;
        this.maxDailyLoss = config.risk_management.max_daily_loss_percent / 100;
        this.maxDrawdown = config.risk_management.max_drawdown_percent / 100;
        this.maxConsecutiveLosses = config.risk_management.max_consecutive_losses;
        
        // Performance tracking
        this.dailyPnL = new Decimal("0");
        this.peakBalance = new Decimal("0");
        this.consecutiveLosses = 0;
        this.totalTrades = 0;
        this.winningTrades = 0;
        
        // Position timing
        this.positionTimers = new Map();
    }
    
    // Get current account balance (in paper trading mode, use configured balance)
    _getCurrentBalance() {
        return new Decimal(String(this.config.scalping_strategy.paper_trading ? 10000 : 1000));
    }
    
    // Calculate position size based on risk management
    _calculatePositionSize(currentPrice, atrValue) {
        const accountBalance = this._getCurrentBalance();
        const riskAmount = accountBalance.mul(this.riskPerTrade);
        
        // Calculate stop loss distance based on ATR
        const stopLossDistance = atrValue.mul(this.config.scalping_strategy.exit_conditions.stop_loss_atr_multiple);
        
        if (stopLossDistance.lte(0)) {
            throw new Error("Invalid stop loss distance");
        }
        
        // Calculate position size in USD value
        const positionValue = riskAmount.div(stopLossDistance);
        
        // Apply maximum position size limit
        const maxPositionValue = accountBalance.mul(this.maxPositionSize);
        const finalPositionValue = Decimal.min(positionValue, maxPositionValue);
        
        // Convert to quantity of the asset
        let positionQty = finalPositionValue.div(currentPrice);
        
        // Apply minimum order size
        positionQty = Decimal.max(positionQty, MIN_ORDER_SIZE);
        
        // Round to appropriate precision
        positionQty = positionQty.toDecimalPlaces(QTY_PRECISION, Decimal.ROUND_DOWN);
        
        this.logger.info(`[${this.symbol}] Calculated position size: ${positionQty} (Risk: ${riskAmount.toDecimalPlaces(2)} USD)`);
        
        return positionQty;
    }
    
    // Open a new scalping position
    openPosition(signal, currentPrice, atrValue, signalData) {
        if (this.openPositions.length >= this.maxPositions) {
            throw new Error(`Maximum positions (${this.maxPositions}) reached`);
        }
        
        const positionQty = this._calculatePositionSize(currentPrice, atrValue);
        
        // Calculate stop loss and take profit
        const stopLossAtrMultiple = this.config.scalping_strategy.exit_conditions.stop_loss_atr_multiple;
        const takeProfitAtrMultiple = this.config.scalping_strategy.exit_conditions.take_profit_atr_multiple;
        
        let stopLoss, takeProfit;
        if (signal === "BUY") {
            stopLoss = currentPrice.sub(atrValue.mul(stopLossAtrMultiple));
            takeProfit = currentPrice.add(atrValue.mul(takeProfitAtrMultiple));
        } else { // SELL
            stopLoss = currentPrice.add(atrValue.mul(stopLossAtrMultiple));
            takeProfit = currentPrice.sub(atrValue.mul(takeProfitAtrMultiple));
        }
        
        // Create position object
        const position = {
            id: `pos_${Date.now()}`,
            symbol: this.symbol,
            side: signal,
            entryPrice: currentPrice,
            qty: positionQty,
            stopLoss: stopLoss,
            takeProfit: takeProfit,
            entryTime: Date.now(),
            status: "OPEN",
            signalData: signalData, // Store the signal data that triggered this position
            atrValue: atrValue
        };
        
        // Add to open positions
        this.openPositions.push(position);
        
        // Set position timer for automatic exit if max hold time reached
        const maxHoldTime = this.config.scalping_strategy.exit_conditions.max_hold_time_ms;
        const positionTimer = setTimeout(() => {
            this.forceClosePosition(position.id, "TIME_LIMIT");
        }, maxHoldTime);
        
        this.positionTimers.set(position.id, positionTimer);
        
        // Log position opening
        this.logger.info(`${NEON_GREEN}[${this.symbol}] Opened ${signal} position: ${positionQty} @ ${currentPrice} | SL: ${stopLoss}, TP: ${takeProfit}${RESET}`);
        this.logger.info(`${NEON_GREEN}Signal strength: ${signalData.strength.toFixed(2)} | Confirming indicators: ${signalData.confirmingIndicators}${RESET}`);
        
        return position;
    }
    
    // Close a position manually
    closePosition(positionId, reason) {
        const positionIndex = this.openPositions.findIndex(p => p.id === positionId);
        
        if (positionIndex === -1) {
            throw new Error(`Position ${positionId} not found`);
        }
        
        const position = this.openPositions[positionIndex];
        
        // Clear position timer
        if (this.positionTimers.has(positionId)) {
            clearTimeout(this.positionTimers.get(positionId));
            this.positionTimers.delete(positionId);
        }
        
        // Calculate P&L
        const currentPrice = position.entryPrice; // In real implementation, fetch current price
        const pnl = position.side === "BUY" 
            ? (currentPrice - position.entryPrice).mul(position.qty)
            : (position.entryPrice - currentPrice).mul(position.qty);
        
        // Update position
        position.exitPrice = currentPrice;
        position.exitTime = Date.now();
        position.status = "CLOSED";
        position.closedReason = reason;
        position.pnl = pnl;
        
        // Update performance metrics
        this.totalTrades++;
        if (pnl.gt(0)) {
            this.winningTrades++;
            this.consecutiveLosses = 0;
        } else {
            this.consecutiveLosses++;
        }
        
        this.dailyPnL = this.dailyPnL.add(pnl);
        
        // Update peak balance
        const currentBalance = this._getCurrentBalance().add(this.dailyPnL);
        if (currentBalance.gt(this.peakBalance)) {
            this.peakBalance = currentBalance;
        }
        
        // Remove from open positions
        this.openPositions.splice(positionIndex, 1);
        
        // Log position closing
        this.logger.info(`${NEON_PURPLE}[${this.symbol}] Closed ${position.side} position: ${position.qty} @ ${currentPrice} | PnL: ${pnl.toDecimalPlaces(6)} | Reason: ${reason}${RESET}`);
        
        return position;
    }
    
    // Force close a position (e.g., for stop loss or take profit)
    forceClosePosition(positionId, reason) {
        return this.closePosition(positionId, reason);
    }
    
    // Update trailing stop loss
    updateTrailingStops(currentPrice) {
        if (!this.config.scalping_strategy.exit_conditions.trailing_stop_enabled) {
            return;
        }
        
        const trailingAtrMultiple = this.config.scalping_strategy.exit_conditions.trailing_atr_multiple;
        
        for (const position of this.openPositions) {
            if (position.status !== "OPEN") continue;
            
            const side = position.side;
            const entryPrice = position.entryPrice;
            const currentStopLoss = position.stopLoss;
            const atrValue = position.atrValue;
            
            let newStopLoss = currentStopLoss;
            
            if (side === "BUY") {
                const potentialStopLoss = currentPrice.sub(atrValue.mul(trailingAtrMultiple));
                if (potentialStopLoss.gt(currentStopLoss)) {
                    newStopLoss = potentialStopLoss;
                }
            } else if (side === "SELL") {
                const potentialStopLoss = currentPrice.add(atrValue.mul(trailingAtrMultiple));
                if (potentialStopLoss.lt(currentStopLoss)) {
                    newStopLoss = potentialStopLoss;
                }
            }
            
            if (!newStopLoss.eq(currentStopLoss)) {
                position.stopLoss = newStopLoss;
                
                this.logger.info(`${NEON_CYAN}[${this.symbol}] Updated trailing stop for ${side} position from ${currentStopLoss} to ${newStopLoss}${RESET}`);
            }
        }
    }
    
    // Manage positions based on market conditions
    managePositions(currentPrice, atrValue) {
        // Update trailing stops
        this.updateTrailingStops(currentPrice);
        
        // Check for stop loss or take profit triggers
        const positionsToClose = [];
        
        for (let i = 0; i < this.openPositions.length; i++) {
            const position = this.openPositions[i];
            
            if (position.status !== "OPEN") continue;
            
            const side = position.side;
            const stopLoss = position.stopLoss;
            const takeProfit = position.takeProfit;
            
            let closedBy = "";
            
            if (side === "BUY") {
                if (currentPrice.lte(stopLoss)) {
                    closedBy = "STOP_LOSS";
                } else if (currentPrice.gte(takeProfit)) {
                    closedBy = "TAKE_PROFIT";
                }
            } else if (side === "SELL") {
                if (currentPrice.gte(stopLoss)) {
                    closedBy = "STOP_LOSS";
                } else if (currentPrice.lte(takeProfit)) {
                    closedBy = "TAKE_PROFIT";
                }
            }
            
            if (closedBy) {
                positionsToClose.push({
                    position,
                    reason: closedBy
                });
            }
        }
        
        // Close triggered positions
        for (const { position, reason } of positionsToClose) {
            this.forceClosePosition(position.id, reason);
        }
    }
    
    // Get all open positions
    getOpenPositions() {
        return this.openPositions;
    }
    
    // Check if we should stop trading for the day
    shouldStopTrading() {
        const currentBalance = this._getCurrentBalance().add(this.dailyPnL);
        const drawdown = this.peakBalance.sub(currentBalance).div(this.peakBalance);
        
        // Check daily loss limit
        if (this.dailyPnL.lt(this._getCurrentBalance().mul(-this.maxDailyLoss))) {
            this.logger.error(`${NEON_RED}[${this.symbol}] Daily loss limit reached: ${this.dailyPnL.toDecimalPlaces(2)}${RESET}`);
            return true;
        }
        
        // Check drawdown limit
        if (drawdown.gte(this.maxDrawdown)) {
            this.logger.error(`${NEON_RED}[${this.symbol}] Maximum drawdown reached: ${(drawdown * 100).toFixed(2)}%${RESET}`);
            return true;
        }
        
        // Check consecutive losses
        if (this.consecutiveLosses >= this.maxConsecutiveLosses) {
            this.logger.error(`${NEON_RED}[${this.symbol}] Maximum consecutive losses reached: ${this.consecutiveLosses}${RESET}`);
            return true;
        }
        
        return false;
    }
    
    // Reset daily metrics (call at start of new trading day)
    resetDailyMetrics() {
        this.dailyPnL = new Decimal("0");
        this.peakBalance = this._getCurrentBalance();
        this.consecutiveLosses = 0;
        this.logger.info(`${NEON_GREEN}[${this.symbol}] Daily metrics reset${RESET}`);
    }
    
    // Get performance summary
    getPerformanceSummary() {
        const winRate = this.totalTrades > 0 ? (this.winningTrades / this.totalTrades) * 100 : 0;
        const currentBalance = this._getCurrentBalance().add(this.dailyPnL);
        const drawdown = this.peakBalance.gt(0) ? 
            (this.peakBalance.sub(currentBalance).div(this.peakBalance)) * 100 : 0;
        
        return {
            totalTrades: this.totalTrades,
            winningTrades: this.winningTrades,
            winRate: `${winRate.toFixed(2)}%`,
            dailyPnL: this.dailyPnL,
            currentBalance,
            drawdown: `${drawdown.toFixed(2)}%`,
            consecutiveLosses: this.consecutiveLosses,
            openPositions: this.openPositions.length
        };
    }
}

// --- Scalping-specific Dashboard ---
class ScalpingDashboard {
    constructor(config, logger) {
        this.config = config;
        this.logger = logger;
        this.app = express();
        this.server = http.createServer(this.app);
        this.io = socketIo(this.server);
        this.port = config.dashboard.port;
        this.updateInterval = config.dashboard.update_interval_ms;
        
        // Dashboard data
        this.marketData = {};
        this.positions = [];
        this.performance = {};
        this.indicators = {};
        this.orderbook = {};
        this.trades = [];
        this.signalHistory = [];
        
        this.setupRoutes();
        this.setupSocketIO();
    }
    
    setupRoutes() {
        this.app.use(express.static('public'));
        
        this.app.get('/', (req, res) => {
            res.sendFile(path.join(__dirname, 'public', 'scalping-dashboard.html'));
        });
        
        // API endpoints
        this.app.get('/api/market-data', (req, res) => {
            res.json(this.marketData);
        });
        
        this.app.get('/api/positions', (req, res) => {
            res.json(this.positions);
        });
        
        this.app.get('/api/performance', (req, res) => {
            res.json(this.performance);
        });
        
        this.app.get('/api/indicators', (req, res) => {
            res.json(this.indicators);
        });
        
        this.app.get('/api/orderbook', (req, res) => {
            res.json(this.orderbook);
        });
        
        this.app.get('/api/trades', (req, res) => {
            res.json(this.trades);
        });
        
        this.app.get('/api/signal-history', (req, res) => {
            res.json(this.signalHistory);
        });
        
        this.app.get('/api/score-components', (req, res) => {
            if (this.signalHistory.length > 0) {
                res.json(this.signalHistory[this.signalHistory.length - 1].components);
            } else {
                res.json({});
            }
        });
    }
    
    setupSocketIO() {
        this.io.on('connection', (socket) => {
            this.logger.info(`${NEON_GREEN}Dashboard client connected${RESET}`);
            
            // Send initial data
            socket.emit('market-data', this.marketData);
            socket.emit('positions', this.positions);
            socket.emit('performance', this.performance);
            socket.emit('indicators', this.indicators);
            socket.emit('orderbook', this.orderbook);
            socket.emit('trades', this.trades);
            socket.emit('signal-history', this.signalHistory);
            
            socket.on('disconnect', () => {
                this.logger.info(`${NEON_YELLOW}Dashboard client disconnected${RESET}`);
            });
        });
    }
    
    start() {
        this.server.listen(this.port, () => {
            this.logger.info(`${NEON_GREEN}Scalping dashboard started on port ${this.port}${RESET}`);
        });
        
        // Update data periodically
        setInterval(() => {
            this.io.emit('market-data', this.marketData);
            this.io.emit('positions', this.positions);
            this.io.emit('performance', this.performance);
            this.io.emit('indicators', this.indicators);
            this.io.emit('orderbook', this.orderbook);
            this.io.emit('trades', this.trades);
            this.io.emit('signal-history', this.signalHistory);
        }, this.updateInterval);
    }
    
    updateMarketData(symbol, data) {
        this.marketData[symbol] = data;
        this.io.emit('market-data', this.marketData);
    }
    
    updatePositions(positions) {
        this.positions = positions;
        this.io.emit('positions', this.positions);
    }
    
    updatePerformance(performance) {
        this.performance = performance;
        this.io.emit('performance', this.performance);
    }
    
    updateIndicators(symbol, indicators) {
        this.indicators[symbol] = indicators;
        this.io.emit('indicators', this.indicators);
    }
    
    updateOrderbook(symbol, orderbook) {
        this.orderbook[symbol] = orderbook;
        this.io.emit('orderbook', this.orderbook);
    }
    
    addTrade(trade) {
        this.trades.unshift(trade); // Add to beginning of array
        if (this.trades.length > 100) {
            this.trades.pop(); // Keep only last 100 trades
        }
        this.io.emit('trades', this.trades);
    }
    
    updateSignalHistory(signalData) {
        this.signalHistory.push({
            timestamp: Date.now(),
            signal: signalData.signal,
            strength: signalData.strength,
            rawScore: signalData.rawScore,
            confirmingIndicators: signalData.confirmingIndicators,
            components: signalData.components
        });
        
        // Keep only last 50 signals in history
        if (this.signalHistory.length > 50) {
            this.signalHistory.shift();
        }
        
        this.io.emit('signal-history', this.signalHistory);
    }
}

// --- Main Scalping Bot Logic ---
async function main() {
    const logger = setupScalpingLogger("scalping_bot");
    const config = loadScalpingConfig(CONFIG_FILE, logger);
    const api = new BybitScalpingAPI(logger);
    const positionManager = new ScalpingPositionManager(config, logger, config.symbol);
    const dashboard = new ScalpingDashboard(config, logger);
    
    // Initialize dashboard if enabled
    if (config.dashboard.enabled) {
        dashboard.start();
    }
    
    // Validate symbol
    const validBybitSymbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]; // Add more as needed
    if (!validBybitSymbols.includes(config.symbol)) {
        logger.error(`${NEON_RED}Invalid symbol '${config.symbol}'. Please use one of: ${validBybitSymbols.join(', ')}${RESET}`);
        process.exit(1);
    }
    
    // Validate timeframes
    const validTimeframes = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"];
    for (const tf of config.timeframes) {
        if (!validTimeframes.includes(tf)) {
            logger.error(`${NEON_RED}Invalid timeframe '${tf}'. Please use valid Bybit timeframes.${RESET}`);
            process.exit(1);
        }
    }
    
    logger.info(`${NEON_GREEN}--- Enhanced Scalping Bot Initialized ---${RESET}`);
    logger.info(`Symbol: ${config.symbol}, Timeframes: ${config.timeframes.join(', ')}`);
    logger.info(`Paper Trading: ${config.paper_trading}`);
    logger.info(`Max Positions: ${config.risk_management.max_positions}`);
    logger.info(`Risk per Trade: ${config.risk_management.risk_per_trade_percent}%`);
    logger.info(`Weighted Scoring: ${config.weighted_scoring.enabled}`);
    
    // Connect to WebSocket for real-time data
    try {
        await api.connectWebSocket(config.symbol);
        logger.info(`${NEON_GREEN}WebSocket connected for ${config.symbol}${RESET}`);
    } catch (error) {
        logger.error(`${NEON_RED}Failed to connect WebSocket: ${error.message}${RESET}`);
        process.exit(1);
    }
    
    // Set up WebSocket callbacks
    let orderbookData = null;
    let recentTrades = [];
    
    api.onOrderbookUpdate((data) => {
        orderbookData = data;
        
        // Update dashboard
        dashboard.updateOrderbook(config.symbol, {
            spread: data.spread,
            spreadPercent: data.spreadPercent,
            imbalance: data.imbalance,
            liquidityScore: data.liquidityScore,
            timestamp: data.timestamp
        });
    });
    
    api.onTradeUpdate((trade) => {
        recentTrades.push(trade);
        if (recentTrades.length > 50) {
            recentTrades.shift(); // Keep only last 50 trades
        }
    });
    
    api.onPublicTradeUpdate((trade) => {
        // Add tick data to klineData for tick divergence calculation
        if (klineData) {
            klineData.addTickData(trade);
        }
    });
    
    // Main trading loop
    while (true) {
        try {
            // Check if we should stop trading for the day
            if (positionManager.shouldStopTrading()) {
                logger.error(`${NEON_RED}Stopping trading due to risk limits${RESET}`);
                await timeout(60000); // Wait 1 minute before retrying
                continue;
            }
            
            // Fetch current price
            const currentPrice = await api.fetchCurrentPrice(config.symbol);
            
            // Update dashboard market data
            dashboard.updateMarketData(config.symbol, {
                price: currentPrice,
                timestamp: Date.now()
            });
            
            // Fetch klines for all timeframes
            const klineDataMap = {};
            for (const timeframe of config.timeframes) {
                try {
                    const klines = await api.fetchKlines(config.symbol, timeframe, 100);
                    klineDataMap[timeframe] = new ScalpingKlineData(klines);
                } catch (error) {
                    logger.error(`${NEON_RED}Failed to fetch klines for ${timeframe}: ${error.message}${RESET}`);
                }
            }
            
            // Calculate indicators for primary timeframe (1m for scalping)
            const primaryTimeframe = "1";
            const klineData = klineDataMap[primaryTimeframe];
            
            if (!klineData || klineData.empty) {
                logger.warn(`${NEON_YELLOW}No kline data for primary timeframe ${primaryTimeframe}${RESET}`);
                await timeout(config.loop_delay_ms);
                continue;
            }
            
            const indicators = new ScalpingIndicators(klineData, logger, config.symbol);
            indicators.calculateAll(config);
            
            // Generate weighted scalping signal
            const signalData = indicators.generateWeightedScalpingSignal(orderbookData, config);
            
            // Update dashboard indicators and signal history
            dashboard.updateIndicators(config.symbol, {
                ...indicators.indicatorValues,
                signal: signalData.signal,
                signalStrength: signalData.strength,
                signalReasons: signalData.reasons
            });
            
            dashboard.updateSignalHistory(signalData);
            
            // Manage existing positions
            const atrValue = indicators.indicatorValues["ATR_5"] || 0.01;
            positionManager.managePositions(currentPrice, atrValue);
            
            // Update dashboard positions
            dashboard.updatePositions(positionManager.getOpenPositions());
            
            // Update dashboard performance
            dashboard.updatePerformance(positionManager.getPerformanceSummary());
            
            // Check if we should open a new position
            if (signalData.signal !== "HOLD" && positionManager.getOpenPositions().length < config.risk_management.max_positions) {
                logger.info(`${NEON_GREEN}Weighted scalping signal: ${signalData.signal} (strength: ${signalData.strength.toFixed(2)})${RESET}`);
                
                for (const reason of signalData.reasons) {
                    logger.info(`  ${reason}`);
                }
                
                // Log score components for debugging
                logger.info(`${NEON_CYAN}Score components:${RESET}`);
                for (const component in signalData.components) {
                    const weight = config.weighted_scoring.weights[component];
                    const score = signalData.components[component];
                    const contribution = score * weight;
                    logger.info(`  ${component}: ${score.toFixed(2)} (weight: ${weight}) = ${contribution.toFixed(2)}`);
                }
                
                try {
                    const position = positionManager.openPosition(
                        signalData.signal,
                        currentPrice,
                        atrValue,
                        signalData
                    );
                    
                    // Add to dashboard trades
                    dashboard.addTrade({
                        id: position.id,
                        symbol: position.symbol,
                        side: position.side,
                        entryPrice: position.entryPrice,
                        qty: position.qty,
                        timestamp: position.entryTime,
                        status: "OPEN"
                    });
                } catch (error) {
                    logger.error(`${NEON_RED}Failed to open position: ${error.message}${RESET}`);
                }
            } else {
                logger.info(`${NEON_BLUE}No weighted scalping signal or max positions reached. Signal: ${signalData.signal}, Strength: ${signalData.strength.toFixed(2)}, Confirming: ${signalData.confirmingIndicators}/${config.weighted_scoring.confirmation_required}${RESET}`);
            }
            
            // Log performance summary
            const perfSummary = positionManager.getPerformanceSummary();
            logger.info(`${NEON_YELLOW}Performance - PnL: ${perfSummary.dailyPnL.toDecimalPlaces(6)}, Win Rate: ${perfSummary.winRate}, Drawdown: ${perfSummary.drawdown}${RESET}`);
            
            // Wait before next iteration
            await timeout(config.loop_delay_ms);
        } catch (error) {
            logger.error(`${NEON_RED}Error in main loop: ${error.message}${RESET}`);
            await timeout(config.loop_delay_ms * 2); // Wait longer on error
        }
    }
}

// Utility function
async function timeout(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Start the bot
if (require.main === module) {
    main().catch(error => {
        console.error(`${NEON_RED}Fatal error: ${error.message}${RESET}`);
        process.exit(1);
    });
}
