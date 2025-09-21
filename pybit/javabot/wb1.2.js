// -----------------------------------
// Imports & Initialization - The First Incantations
// -----------------------------------
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { URLSearchParams } = require('url');
const { setTimeout } = require('timers/promises');
const { Decimal } = require('decimal.js');
const chalk = require('chalk');
const dotenv = require('dotenv');
const fetch = require('node-fetch');
const winston = require('winston');
require('winston-daily-rotate-file');
const WebSocket = require('ws');
const _ = require('lodash');
const readline = require('readline');
const { execSync } = require('child_process'); // For Termux commands

// Load environment variables from .env file
dotenv.config();

// -----------------------------------
// Constants & Configuration - The Sacred Scrolls
// -----------------------------------
class Config {
    constructor() {
        this.configFile = 'termux_scalping_config.json';
        this.logDir = 'bot_logs/termux_scalper/logs';
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        this.baseUrl = process.env.BYBIT_BASE_URL || 'https://api.bybit.com';
        this.websocketUrl = 'wss://stream.bybit.com/v5/public/linear';
        this.paperTrading = process.env.PAPER_TRADING_MODE === 'true';

        // Default configuration values with Decimals where needed
        this.defaults = {
            symbol: 'BTCUSDT',
            timeframes: ['1', '3', '5'],
            loopDelayMs: 1000,
            maxApiRetries: 5,
            retryDelayMs: 1500,
            requestTimeout: 15000,
            minOrderSize: new Decimal("0.001"),
            pricePrecision: 2,
            qtyPrecision: 4,
            maxPositions: 3,
            maxPositionSizePercent: new Decimal("0.05"),
            riskPerTradePercent: new Decimal("0.005"),
            martingaleEnabled: false,
            martingaleMultiplier: new Decimal("2.0"),
            maxMartingaleLevels: 5,
            correlationFilter: true,
            indicators: {
                smaShort: 5, smaLong: 20, emaShort: 5, emaLong: 20, atr: 14, rsi: 14,
                stochRsiK: 14, stochRsiD: 3, stochRsiSmooth: 3, bollingerBandsPeriod: 20,
                bollingerBandsStddev: 2, vwap: true, macdFast: 12, macdSlow: 26, macdSignal: 9,
                adxPeriod: 14, momentumPeriod: 10, williamsRPeriod: 14, cciPeriod: 20,
                mfiPeriod: 14, priceOscillatorFast: 5, priceOscillatorSlow: 10,
                tickDivergenceLookback: 5, volatilitySqueezePeriod: 20, microTrendPeriod: 5,
                orderFlowLookback: 10, supportResistance: true,
            },
            scalpingStrategy: {
                entryConditions: {
                    rsiOversold: 30, rsiOverbought: 70, stochRsiKOversold: 20, stochRsiKOverbought: 80,
                    cciOversold: -100, cciOverbought: 100, mfiOversold: 20, mfiOverbought: 80,
                    adxThreshold: 25, macdCrossoverBuy: "bullish", macdCrossoverSell: "bearish",
                    emaCrossBuy: "golden", emaCrossSell: "death", vwapRejectionBuy: true,
                    vwapRejectionSell: true, supportResistanceBounceBuy: true,
                    supportResistanceBounceSell: true, volatilitySqueezeBreakoutBuy: true,
                    volatilitySqueezeBreakoutSell: true, orderFlowConfirmationBuy: true,
                    orderFlowConfirmationSell: true,
                },
                exitConditions: {
                    stopLossAtrMultiple: new Decimal("1.5"), takeProfitAtrMultiple: new Decimal("2.0"),
                    partialTakeProfit: true, partialTakeProfitPercent: new Decimal("0.5"),
                    partialTakeProfitAtrMultiple: new Decimal("1.0"), breakEvenThresholdAtrMultiple: new Decimal("0.8"),
                    breakEvenDelayMs: 5000, trailingStopEnabled: true, trailingAtrMultiple: new Decimal("1.2"),
                    maxHoldTimeMs: 15 * 60 * 1000,
                }
            },
            // News filter is disabled by default, requires external API implementation
            newsFilter: { enabled: false, highImpactNewsLookbackMinutes: 30 }
        };

        this.loadConfig();
    }

    loadConfig() {
        const configPath = path.join(__dirname, this.configFile);
        if (!fs.existsSync(configPath)) {
            this.saveConfig(this.defaults);
            this.log('warn', `Default config file created at ${configPath}. Please review and adjust.`);
            this.applyConfig(this.defaults);
        } else {
            try {
                const raw = fs.readFileSync(configPath, 'utf-8');
                const userConfig = JSON.parse(raw);
                // Use lodash.mergeWith for deep merging, ensuring Decimals are handled
                const mergedConfig = _.mergeWith({}, this.defaults, userConfig, (objValue, srcValue) => {
                    if (objValue instanceof Decimal) return new Decimal(srcValue);
                    if (Array.isArray(objValue) && Array.isArray(srcValue)) return objValue.concat(srcValue);
                });
                this.applyConfig(mergedConfig);
                this.log('info', `Configuration loaded from ${this.configFile}.`);
            } catch (e) {
                this.log('error', `Failed to load config file ${this.configFile}: ${e.message}. Using defaults.`);
                this.applyConfig(this.defaults);
            }
        }
        fs.mkdirSync(this.logDir, { recursive: true });
    }

    saveConfig(configData) {
        try {
            fs.writeFileSync(this.configFile, JSON.stringify(configData, this.decimalReplacer, 4));
            this.log('success', `Configuration saved to ${this.configFile}.`);
        } catch (e) {
            this.log('error', `Failed to save config file ${this.configFile}: ${e.message}`);
        }
    }

    applyConfig(configData) {
        Object.assign(this, configData);
        // Ensure Decimals are correctly instantiated after loading/merging
        this.minOrderSize = new Decimal(this.minOrderSize);
        this.maxPositionSizePercent = new Decimal(this.maxPositionSizePercent);
        this.riskPerTradePercent = new Decimal(this.riskPerTradePercent);
        this.martingaleMultiplier = new Decimal(this.martingaleMultiplier);
        this.scalpingStrategy.exitConditions.stopLossAtrMultiple = new Decimal(this.scalpingStrategy.exitConditions.stopLossAtrMultiple);
        this.scalpingStrategy.exitConditions.takeProfitAtrMultiple = new Decimal(this.scalpingStrategy.exitConditions.takeProfitAtrMultiple);
        this.scalpingStrategy.exitConditions.partialTakeProfitPercent = new Decimal(this.scalpingStrategy.exitConditions.partialTakeProfitPercent);
        this.scalpingStrategy.exitConditions.partialTakeProfitAtrMultiple = new Decimal(this.config.scalpingStrategy.exitConditions.partialTakeProfitAtrMultiple);
        this.scalpingStrategy.exitConditions.breakEvenThresholdAtrMultiple = new Decimal(this.config.scalpingStrategy.exitConditions.breakEvenThresholdAtrMultiple);
        this.scalpingStrategy.exitConditions.trailingAtrMultiple = new Decimal(this.config.scalpingStrategy.exitConditions.trailingAtrMultiple);
    }

    decimalReplacer(key, value) {
        if (value instanceof Decimal) return parseFloat(value.toString());
        return value;
    }

    log(level, message) { // Simple logger for config messages
        const color = chalk[level] || chalk.white;
        console.log(`${color(`[${level.toUpperCase()}] ${message}`)}`);
    }
}

const CONFIG = new Config();

// -----------------------------------
// Logging Setup - The Oracle's Whispers
// -----------------------------------
const NEON_COLORS = {
    INFO: 'cyan', WARN: 'yellow', ERROR: 'red', SUCCESS: 'green', DEBUG: 'blue', RESET: 'reset',
};

const logger = winston.createLogger({
    level: 'debug',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
        winston.format.errors({ stack: true }),
        winston.format.printf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`)
    ),
    transports: [
        new winston.transports.DailyRotateFile({
            dirname: CONFIG.logDir, filename: 'termux_scalper-%DATE%.log', datePattern: 'YYYY-MM-DD',
            zippedArchive: true, maxSize: '5m', maxFiles: '7d',
            format: winston.format.combine(
                winston.format.timestamp({ format: 'HH:mm:ss.SSS' }),
                winston.format.printf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`)
            ),
        }),
        new winston.transports.Console({
            level: 'info',
            format: winston.format.combine(
                winston.format.timestamp({ format: 'HH:mm:ss.SSS' }),
                winston.format.printf(info => {
                    let message = info.message;
                    // Mask sensitive data
                    if (CONFIG.apiKey) message = message.replace(new RegExp(CONFIG.apiKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(CONFIG.apiKey.length));
                    if (CONFIG.apiSecret) message = message.replace(new RegExp(CONFIG.apiSecret.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(CONFIG.apiSecret.length));

                    const color = chalk[NEON_COLORS[info.level.toUpperCase()] || NEON_COLORS.INFO];
                    return `${color(info.timestamp)} - ${color(info.level.toUpperCase())} - ${color(message)}`;
                })
            ),
        }),
    ],
});

function logMessage(level, message) {
    const color = chalk[NEON_COLORS[level.toUpperCase()] || NEON_COLORS.INFO];
    const formattedMessage = `${color(`[${level.toUpperCase()}]`)} ${message}`;
    logger.log(level, formattedMessage);

    // Termux specific notifications
    if (level.toUpperCase() === "ERROR" || level.toUpperCase() === "WARN") {
        try {
            execSync(`termux-toast "${formattedMessage}"`);
            execSync(`termux-vibrate -d 300`);
        } catch (e) { /* Ignore if Termux commands are unavailable */ }
    }
}

// -----------------------------------
// Utility Functions - The Wizard's Toolkit
// -----------------------------------
const delay = ms => new Promise(res => setTimeout(res, ms));

function getTimestampMs() { return Date.now(); }

function formatDecimal(value, precision, rounding = Decimal.ROUND_DOWN) {
    if (!(value instanceof Decimal)) value = new Decimal(value);
    return value.toDecimalPlaces(precision, rounding);
}

function runTermuxCommand(command) {
    try {
        const output = execSync(`termux-exec sh -c "${command}"`, { encoding: 'utf8' });
        return output.trim();
    } catch (e) {
        logMessage("warn", `Termux command execution failed: ${command} - ${e.message}`);
        return null;
    }
}

function getCurrentBalance() {
    if (CONFIG.paperTrading) return new Decimal("10000.00");
    logMessage("warn", "Fetching real balance not implemented. Using placeholder.");
    return new Decimal("10000.00");
}

// -----------------------------------
// API Client - The Conduit to Bybit
// -----------------------------------
class BybitAPI {
    constructor(logger) {
        this.logger = logger;
        this.ws = null; this.wsConnected = false; this.wsCallbacks = {};
        this.reconnectAttempts = 0; this.maxReconnectAttempts = 10;
        this.reconnectDelayBase = 1000; this.lastPingTime = 0; this.pingInterval = 20000;
    }

    _getSignature(params, timestamp, recvWindow = '5000') {
        let paramStr = `${timestamp}${CONFIG.apiKey}`;
        if (params && typeof params === 'object' && Object.keys(params).length > 0) {
            if (this.lastMethod === 'GET') {
                const sortedParams = Object.keys(params).sort().map(key => `${key}=${params[key]}`).join('&');
                paramStr += sortedParams;
            } else paramStr += JSON.stringify(params);
        }
        return crypto.createHmac('sha256', CONFIG.apiSecret).update(paramStr).digest('hex');
    }

    async _makeRequest(method, endpoint, params = {}, signed = false) {
        const url = `${CONFIG.baseUrl}${endpoint}`;
        const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
        let data = null; let queryParams = null; this.lastMethod = method.toUpperCase();

        if (signed) {
            if (!CONFIG.apiKey || !CONFIG.apiSecret) throw new Error('API Key and Secret required.');
            const timestamp = String(Date.now()); const recvWindow = '5000';
            headers['X-BAPI-API-KEY'] = CONFIG.apiKey; headers['X-BAPI-TIMESTAMP'] = timestamp; headers['X-BAPI-RECV-WINDOW'] = recvWindow;

            if (this.lastMethod === 'GET') {
                queryParams = params || {}; headers['X-BAPI-SIGN'] = this._getSignature(queryParams, timestamp, recvWindow);
            } else {
                data = JSON.stringify(params || {}); headers['X-BAPI-SIGN'] = this._getSignature(data, timestamp, recvWindow);
            }
        } else if (params) queryParams = params;

        const requestArgs = { method, headers, timeout: CONFIG.requestTimeout };
        if (queryParams) requestArgs.searchParams = new URLSearchParams(queryParams);
        if (data) requestArgs.body = data;

        for (let attempt = 1; attempt <= CONFIG.maxApiRetries; attempt++) {
            try {
                const response = await fetch(url, requestArgs);
                if (!response.ok) throw new Error(`HTTP error ${response.status}: ${await response.text()}`);
                const result = await response.json();

                if (result.retCode !== 0) {
                    const errorMsg = result.retMsg || 'Unknown API error';
                    this.logger.error(chalk.red(`API Error (${result.retCode}): ${errorMsg} - Endpoint: ${endpoint}`));
                    if (attempt < CONFIG.maxApiRetries) { await delay(CONFIG.retryDelayMs * attempt); continue; }
                    else throw new Error(`API request failed after ${CONFIG.maxApiRetries} retries: ${errorMsg}`);
                }
                this.logger.debug(chalk.blue(`API Success: ${method.toUpperCase()} ${endpoint} | Params: ${this._maskSensitive(JSON.stringify(params || ''))}`));
                return result.result;
            } catch (err) {
                this.logger.warn(chalk.yellow(`API request failed (${attempt}/${CONFIG.maxApiRetries}): ${err.message}. Retrying...`));
                if (attempt < CONFIG.maxApiRetries) await delay(CONFIG.retryDelayMs * attempt);
                else throw err;
            }
        }
        throw new Error(`API request to ${endpoint} failed after ${CONFIG.maxApiRetries} retries.`);
    }

    _maskSensitive(text) {
        let maskedText = text;
        if (CONFIG.apiKey) maskedText = maskedText.replace(new RegExp(CONFIG.apiKey.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(CONFIG.apiKey.length));
        if (CONFIG.apiSecret) maskedText = maskedText.replace(new RegExp(CONFIG.apiSecret.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(CONFIG.apiSecret.length));
        return maskedText;
    }

    async fetchKlines(symbol, interval, limit = 100) {
        logMessage("info", `Fetching ${limit} klines for ${symbol} interval ${interval}...`);
        const params = { category: 'linear', symbol, interval, limit };
        try {
            const data = await this._makeRequest('GET', '/v5/market/kline', params);
            if (data?.list) return data.list.map(k => ({
                timestamp: new Date(parseInt(k[0])), open: new Decimal(k[1]), high: new Decimal(k[2]),
                low: new Decimal(k[3]), close: new Decimal(k[4]), volume: new Decimal(k[5]), turnover: new Decimal(k[6]),
            }));
            logMessage("warn", `No kline data received for ${symbol} interval ${interval}.`); return [];
        } catch (e) { logMessage("error", `Failed to fetch klines for ${symbol}: ${e.message}`); return []; }
    }

    async fetchOrderbook(symbol, limit = 50) {
        const params = { category: 'linear', symbol, limit };
        try {
            const data = await this._makeRequest('GET', '/v5/market/orderbook', params);
            if (data?.orderbook) return {
                bids: data.orderbook.bids.map(p => [new Decimal(p[0]), new Decimal(p[1])]),
                asks: data.orderbook.asks.map(p => [new Decimal(p[0]), new Decimal(p[1])]),
                time: data.orderbook.time || null
            };
            logMessage("warn", `No orderbook data received for ${symbol}.`); return null;
        } catch (e) { logMessage("error", `Failed to fetch orderbook for ${symbol}: ${e.message}`); return null; }
    }

    async fetchTicker(symbol) {
        const params = { category: 'linear', symbol };
        try {
            const data = await this._makeRequest('GET', '/v5/market/tickers', params);
            if (data?.list?.[0]) {
                const ticker = data.list[0];
                return {
                    symbol: ticker.symbol, lastPrice: new Decimal(ticker.lastPrice), highPrice: new Decimal(ticker.highPrice),
                    lowPrice: new Decimal(ticker.lowPrice), volume24h: new Decimal(ticker.volume24h),
                    turnover24h: new Decimal(ticker.turnover24h), time: ticker.time || null
                };
            }
            logMessage("warn", `No ticker data received for ${symbol}.`); return null;
        } catch (e) { logMessage("error", `Failed to fetch ticker for ${symbol}: ${e.message}`); return null; }
    }

    async placeOrder(symbol, side, orderType, qty, price = null, timeInForce = 'GTC') {
        if (CONFIG.paperTrading) {
            logMessage("info", chalk.green(`[Paper] Placing ${side} ${orderType} order: ${qty} ${symbol} @ ${price || 'Market'}`));
            return { orderId: `paper_${Date.now()}`, symbol, side, orderType, qty, price: price || await this.fetchTicker(symbol)?.lastPrice || new Decimal(0), status: 'FILLED', createdTime: Date.now(), execTime: Date.now() };
        }
        logMessage("info", `Placing ${side} ${orderType} order: ${qty} ${symbol} @ ${price || 'Market'}...`);
        const params = { category: 'linear', symbol, side, orderType, qty: qty.toString(), timeInForce };
        if (price) params.price = price.toString();
        try {
            const data = await this._makeRequest('POST', '/v5/order/create', params, true);
            logMessage("success", `Order placed successfully: ID ${data.orderId}, Side: ${side}, Qty: ${qty}, Price: ${price || 'Market'}`);
            return data;
        } catch (e) { logMessage("error", `Failed to place order for ${symbol}: ${e.message}`); return null; }
    }

    async closePosition(symbol, side, qty, price = null) {
        if (CONFIG.paperTrading) {
            logMessage("info", chalk.green(`[Paper] Closing position: ${qty} ${symbol} @ ${price || 'Market'}`));
            return { orderId: `paper_close_${Date.now()}`, symbol, side: side === 'BUY' ? 'SELL' : 'BUY', orderType: 'Market', qty: qty.toString(), status: 'FILLED', createdTime: Date.now(), execTime: Date.now() };
        }
        logMessage("info", `Closing position: ${qty} ${symbol} (${side})...`);
        const params = { category: 'linear', symbol, qty: qty.toString(), side: side === 'BUY' ? 'SELL' : 'BUY', orderType: 'Market', reduceOnly: true };
        if (price) { params.price = price.toString(); params.orderType = 'Limit'; }
        try {
            const data = await this._makeRequest('POST', '/v5/order/replace', params, true);
            logMessage("success", `Position closed successfully: ID ${data.orderId}, Qty: ${qty}`);
            return data;
        } catch (e) { logMessage("error", `Failed to close position for ${symbol}: ${e.message}`); return null; }
    }

    connectWebSocket(symbol) {
        if (this.wsConnected) { logMessage("info", "WebSocket already connected."); return; }
        logMessage("info", `Attempting to connect WebSocket to ${this.websocketUrl}...`);
        this.ws = new WebSocket(this.websocketUrl);
        this.ws.onopen = () => {
            this.wsConnected = true; this.reconnectAttempts = 0;
            logMessage("info", `WebSocket connected for ${symbol}.`);
            const subscribeMessage = { op: "subscribe", args: [`orderbook.${symbol}`, `trade.${symbol}`, `publicTrade.${symbol}`] };
            this.ws.send(JSON.stringify(subscribeMessage));
            logMessage("info", `Sent subscription request for ${symbol}.`);
        };
        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "pong") { this.lastPingTime = Date.now(); return; }
                if (msg.topic) {
                    const topic = msg.topic;
                    if (topic.startsWith("publicTrade.") || topic.startsWith("trade.")) { if (this.wsCallbacks.trade) this.wsCallbacks.trade(msg); }
                    else if (topic.startsWith("orderbook.")) { if (this.wsCallbacks.orderbook) this.wsCallbacks.orderbook(msg); }
                }
            } catch (e) { logMessage("error", `Failed to parse WebSocket message: ${e.message}`); }
        };
        this.ws.onerror = (error) => { logMessage("error", `WebSocket error: ${error.message || 'Unknown error'}`); this.wsConnected = false; this.reconnectWebsocket(); };
        this.ws.onclose = () => { logMessage("warn", "WebSocket connection closed. Reconnecting..."); this.wsConnected = false; this.reconnectWebsocket(); };
    }

    reconnectWebsocket() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            logMessage("error", `Max WebSocket reconnect attempts (${this.maxReconnectAttempts}) reached.`); return;
        }
        const delayMs = this.reconnectDelayBase * Math.pow(2, this.reconnectAttempts);
        logMessage("warn", `Attempting WebSocket reconnect ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts} in ${delayMs / 1000.0}s...`);
        setTimeout(delayMs).then(() => { this.reconnectAttempts++; this.connectWebSocket(CONFIG.symbol); }).catch(e => logMessage("error", `WebSocket reconnect attempt failed: ${e.message}`));
    }

    sendWsPing() {
        if (this.ws && this.wsConnected) {
            try {
                this.ws.send(JSON.stringify({ op: "ping" }));
                this.lastPingTime = Date.now();
            } catch (e) { logMessage("error", `Failed to send WebSocket ping: ${e.message}`); this.wsConnected = false; this.ws.close(); }
        }
    }

    registerCallback(eventType, callback) { this.wsCallbacks[eventType] = callback; }
}

// -----------------------------------
// Data Structures & Indicator Logic - The Alchemist's Formulas
// -----------------------------------
class Kline {
    constructor(timestamp, open, high, low, close, volume, turnover) {
        this.timestamp = new Date(timestamp);
        this.open = new Decimal(open); this.high = new Decimal(high); this.low = new Decimal(low);
        this.close = new Decimal(close); this.volume = new Decimal(volume); this.turnover = new Decimal(turnover);
    }
    toString() { return `Kline(ts=${this.timestamp.toISOString()}, O=${this.open}, H=${this.high}, L=${this.low}, C=${this.close}, V=${this.volume})`; }
}

class KlineDataStore {
    constructor(logger) {
        this.logger = logger;
        this.klines = new deque(500); this.indicatorCache = {}; this.tickData = new deque(1000);
        this.supportLevels = []; this.resistanceLevels = []; this.lastKlineTimestamp = null;
    }

    addKline(klineData) {
        const kline = new Kline(klineData.timestamp, klineData.open, klineData.high, klineData.low, klineData.close, klineData.volume, klineData.turnover);
        if (kline.timestamp.getTime() === this.lastKlineTimestamp) {
            if (this.klines.length > 0 && kline.timestamp > this.klines[this.klines.length - 1].timestamp) {
                this.klines.pop(); this.klines.push(kline); this.lastKlineTimestamp = kline.timestamp.getTime();
                this.logger.debug(`Updated latest kline: ${kline}`);
            } return;
        }
        this.klines.push(kline); this.lastKlineTimestamp = kline.timestamp.getTime();
        this.indicatorCache = {}; // Clear cache on new kline
        this.logger.debug(`Added kline: ${kline}`);
    }

    addTick(tickData) {
        if (tickData?.data?.trade) {
            const trade = tickData.data.trade;
            this.tickData.push({
                price: new Decimal(trade.price), volume: new Decimal(trade.volume),
                side: trade.side, timestamp: new Date(parseInt(trade.ts)),
            });
        }
    }

    getRecentKlines(count) { return Array.from(this.klines).slice(-count); }
    getColumn(columnName) { return Array.from(this.klines).map(k => k[columnName]); }
    _cacheIndicator(name, values) { this.indicatorCache[name] = values; }
    _getCachedIndicator(name) { return this.indicatorCache[name]; }

    // --- Indicator Calculations ---
    calculateSMA(period, column = 'close') {
        const cacheKey = `SMA_${period}_${column}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const values = this.getColumn(column); if (values.length < period) return Array(values.length).fill(new Decimal(0));
        const result = Array(period - 1).fill(new Decimal(0));
        for (let i = period - 1; i < values.length; i++) {
            const segment = values.slice(i - period + 1, i + 1);
            const sma = segment.reduce((sum, val) => sum.plus(val), new Decimal(0)).dividedBy(period);
            result.push(sma);
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateEMA(period, column = 'close') {
        const cacheKey = `EMA_${period}_${column}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const values = this.getColumn(column); if (!values || values.length === 0) return [];
        const alpha = new Decimal(2).dividedBy(new Decimal(period).plus(1)); const result = []; let ema = new Decimal(0);
        for (let i = 0; i < values.length; i++) {
            const val = values[i]; if (val === null || val === undefined) continue;
            if (i === 0) ema = new Decimal(val); else ema = (new Decimal(val).times(alpha)).plus(ema.times(new Decimal(1).minus(alpha)));
            result.push(ema);
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateATR(period = 14) {
        const cacheKey = `ATR_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close');
        if (highs.length < period + 1) return Array(highs.length).fill(new Decimal(0));
        const trList = [];
        for (let i = 1; i < highs.length; i++) {
            const tr = Decimal.max(highs[i].minus(lows[i]), highs[i].minus(closes[i - 1]).abs(), lows[i].minus(closes[i - 1]).abs());
            trList.push(tr);
        }
        const result = Array(period).fill(new Decimal(0)); const alpha = new Decimal(2).dividedBy(new Decimal(period).plus(1)); let emaTr = new Decimal(0);
        for (let i = 0; i < trList.length; i++) {
            const tr = trList[i]; if (i === 0) emaTr = tr; else emaTr = tr.times(alpha).plus(emaTr.times(new Decimal(1).minus(alpha)));
            if (i >= period - 1) result.push(emaTr);
        }
        const finalResult = Array(highs.length - result.length).fill(new Decimal(0)).concat(result);
        this._cacheIndicator(cacheKey, finalResult); return finalResult;
    }
    calculateRSI(period = 14, column = 'close') {
        const cacheKey = `RSI_${period}_${column}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const values = this.getColumn(column); if (values.length < period + 1) return Array(values.length).fill(new Decimal(50));
        const gains = []; const losses = [];
        for (let i = 1; i < values.length; i++) {
            const delta = values[i].minus(values[i - 1]); gains.push(delta.gt(0) ? delta : new Decimal(0)); losses.push(delta.lt(0) ? delta.abs() : new Decimal(0));
        }
        const avgGain = this.calculateEMA(period, gains); const avgLoss = this.calculateEMA(period, losses);
        const rsi = Array(period).fill(new Decimal(50));
        for (let i = period; i < values.length; i++) {
            const gain = avgGain[i - 1] || new Decimal(0); const loss = avgLoss[i - 1] || new Decimal(0);
            let currentRsi = new Decimal(50);
            if (loss.isZero()) currentRsi = new Decimal(100); else { const rs = gain.dividedBy(loss); currentRsi = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs))); }
            rsi.push(currentRsi);
        } this._cacheIndicator(cacheKey, rsi); return rsi;
    }
    calculateStochRSI(period = 14, kPeriod = 3, dPeriod = 3) {
        const cacheKeyK = `StochRSI_K_${period}_${kPeriod}_${dPeriod}`; const cacheKeyD = `StochRSI_D_${period}_${kPeriod}_${dPeriod}`;
        const cachedK = this._getCachedIndicator(cacheKeyK); const cachedD = this._getCachedIndicator(cacheKeyD); if (cachedK && cachedD) return [cachedK, cachedD];
        const rsiValues = this.calculateRSI(period); if (rsiValues.length < kPeriod) return [Array(rsiValues.length).fill(new Decimal(0)), Array(rsiValues.length).fill(new Decimal(0))];
        const stochK = [];
        for (let i = 0; i < rsiValues.length; i++) {
            if (i < kPeriod - 1) { stochK.push(new Decimal(0)); continue; }
            const rsiSegment = rsiValues.slice(i - kPeriod + 1, i + 1);
            const rsiMax = Decimal.max(...rsiSegment); const rsiMin = Decimal.min(...rsiSegment);
            if (rsiMax.equals(rsiMin)) stochK.push(new Decimal(0)); else {
                const kVal = rsiValues[i].minus(rsiMin).dividedBy(rsiMax.minus(rsiMin)).times(100); stochK.push(kVal);
            }
        }
        const stochD = [];
        for (let i = 0; i < stochK.length; i++) {
            if (i < dPeriod - 1) { stochD.push(new Decimal(0)); continue; }
            const segment = stochK.slice(i - dPeriod + 1, i + 1);
            const dVal = segment.reduce((sum, val) => sum.plus(val), new Decimal(0)).dividedBy(dPeriod);
            stochD.push(dVal);
        } this._cacheIndicator(cacheKeyK, stochK); this._cacheIndicator(cacheKeyD, stochD); return [stochK, stochD];
    }
    calculateBollingerBands(period = 20, stddev = 2) {
        const cacheKeyUpper = `BB_Upper_${period}_${stddev}`; const cacheKeyMiddle = `BB_Middle_${period}_${stddev}`; const cacheKeyLower = `BB_Lower_${period}_${stddev}`;
        const cachedUpper = this._getCachedIndicator(cacheKeyUpper); const cachedMiddle = this._getCachedIndicator(cacheKeyMiddle); const cachedLower = this._getCachedIndicator(cacheKeyLower);
        if (cachedUpper && cachedMiddle && cachedLower) return [cachedUpper, cachedMiddle, cachedLower];
        const closes = this.getColumn('close'); if (closes.length < period) return [Array(closes.length).fill(new Decimal(0)), Array(closes.length).fill(new Decimal(0)), Array(closes.length).fill(new Decimal(0))];
        const middleBand = this.calculateSMA(period, 'close'); const resultUpper = Array(period - 1).fill(new Decimal(0)); const resultLower = Array(period - 1).fill(new Decimal(0));
        for (let i = period - 1; i < closes.length; i++) {
            const segment = closes.slice(i - period + 1, i + 1); const mean = middleBand[i];
            const variance = segment.reduce((sum, x) => sum.plus(x.minus(mean).pow(2)), new Decimal(0)).dividedBy(period);
            const stdev = variance.sqrt(); resultUpper.push(mean.plus(stdev.times(stddev))); resultLower.push(mean.minus(stdev.times(stddev)));
        } this._cacheIndicator(cacheKeyUpper, resultUpper); this._cacheIndicator(cacheKeyMiddle, middleBand); this._cacheIndicator(cacheKeyLower, resultLower); return [resultUpper, middleBand, resultLower];
    }
    calculateVWAP() {
        const cacheKey = "VWAP"; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close'); const volumes = this.getColumn('volume');
        if (!highs || highs.length === 0) return Array(this.klines.size).fill(new Decimal(0));
        const typicalPrices = []; for (let i = 0; i < highs.length; i++) { typicalPrices.push(highs[i].plus(lows[i]).plus(closes[i]).dividedBy(3)); }
        const cumulativeTpVolume = []; const cumulativeVolume = []; let currentTpVolumeSum = new Decimal(0); let currentVolumeSum = new Decimal(0);
        for (let i = 0; i < typicalPrices.length; i++) {
            currentTpVolumeSum = currentTpVolumeSum.plus(typicalPrices[i].times(volumes[i])); currentVolumeSum = currentVolumeSum.plus(volumes[i]);
            cumulativeTpVolume.push(currentTpVolumeSum); cumulativeVolume.push(currentVolumeSum);
        }
        const vwap = cumulativeTpVolume.map((tpVol, i) => cumulativeVolume[i].isZero() ? new Decimal(0) : tpVol.dividedBy(cumulativeVolume[i]));
        this._cacheIndicator(cacheKey, vwap); return vwap;
    }
    calculateMACD(fast = 12, slow = 26, signal = 9) {
        const cacheKeyLine = `MACD_Line_${fast}_${slow}_${signal}`; const cacheKeySignal = `MACD_Signal_${fast}_${slow}_${signal}`; const cacheKeyHist = `MACD_Hist_${fast}_${slow}_${signal}`;
        const cachedLine = this._getCachedIndicator(cacheKeyLine); const cachedSignal = this._getCachedIndicator(cacheKeySignal); const cachedHist = this._getCachedIndicator(cacheKeyHist);
        if (cachedLine && cachedSignal && cachedHist) return [cachedLine, cachedSignal, cachedHist];
        const emaFast = this.calculateEMA(fast, 'close'); const emaSlow = this.calculateEMA(slow, 'close');
        const macdLine = []; for (let i = 0; i < emaFast.length; i++) { macdLine.push(emaFast[i] ? emaFast[i].minus(emaSlow[i] || new Decimal(0)) : new Decimal(0)); }
        const macdSignal = this.calculateEMA(signal, macdLine); const macdHist = []; for (let i = 0; i < macdLine.length; i++) { macdHist.push(macdLine[i] ? macdLine[i].minus(macdSignal[i] || new Decimal(0)) : new Decimal(0)); }
        this._cacheIndicator(cacheKeyLine, macdLine); this._cacheIndicator(cacheKeySignal, macdSignal); this._cacheIndicator(cacheKeyHist, macdHist); return [macdLine, macdSignal, macdHist];
    }
    calculateADX(period = 14) {
        const cacheKeyAdx = `ADX_${period}`; const cacheKeyPlus = `PlusDI_${period}`; const cacheKeyMinus = `MinusDI_${period}`;
        const cachedAdx = this._getCachedIndicator(cacheKeyAdx); const cachedPlus = this._getCachedIndicator(cacheKeyPlus); const cachedMinus = this._getCachedIndicator(cacheKeyMinus);
        if (cachedAdx && cachedPlus && cachedMinus) return [cachedAdx, cachedPlus, cachedMinus];
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close');
        if (highs.length < period + 1) return [Array(highs.length).fill(new Decimal(0)), Array(highs.length).fill(new Decimal(0)), Array(highs.length).fill(new Decimal(0))];
        const plusDm = []; const minusDm = [];
        for (let i = 1; i < highs.length; i++) {
            const upMove = highs[i].minus(highs[i - 1]); const downMove = lows[i - 1].minus(lows[i]);
            let pd = new Decimal(0); let nd = new Decimal(0);
            if (upMove.gt(downMove) && upMove.gt(0)) pd = upMove; else if (downMove.gt(upMove) && downMove.gt(0)) nd = downMove;
            plusDm.push(pd); minusDm.push(nd);
        }
        const smoothedPlusDm = this.calculateEMA(period, plusDm); const smoothedMinusDm = this.calculateEMA(period, minusDm);
        const trList = []; for (let i = 1; i < highs.length; i++) {
            const tr = Decimal.max(highs[i].minus(lows[i]), highs[i].minus(closes[i - 1]).abs(), lows[i].minus(closes[i - 1]).abs()); trList.push(tr);
        } const smoothedTr = this.calculateEMA(period, trList);
        const plusDi = Array(period).fill(new Decimal(0)); const minusDi = Array(period).fill(new Decimal(0)); const adx = Array(period).fill(new Decimal(0));
        for (let i = period; i < smoothedPlusDm.length; i++) {
            const currentSmoothedTr = smoothedTr[i - 1] || new Decimal(0);
            if (currentSmoothedTr.isZero()) { plusDi.push(new Decimal(0)); minusDi.push(new Decimal(0)); } else {
                plusDi.push(smoothedPlusDm[i - 1].dividedBy(currentSmoothedTr).times(100)); minusDi.push(smoothedMinusDm[i - 1].dividedBy(currentSmoothedTr).times(100));
            }
            const diDiff = plusDi[i].minus(minusDi[i]).abs(); const diSum = plusDi[i].plus(minusDi[i]);
            let currentAdx = new Decimal(0);
            if (!diSum.isZero()) {
                const adxVal = diDiff.dividedBy(diSum).times(100);
                if (i < period * 2 - 1) currentAdx = adxVal; else {
                    const prevAdxValues = adx.slice(i - period); currentAdx = prevAdxValues.reduce((sum, val) => sum.plus(val), new Decimal(0)).dividedBy(period);
                } adx.push(currentAdx);
            } else adx.push(new Decimal(0));
        }
        const finalAdx = Array(highs.length - adx.length).fill(new Decimal(0)).concat(adx);
        const finalPlus = Array(highs.length - plusDi.length).fill(new Decimal(0)).concat(plusDi);
        const finalMinus = Array(highs.length - minusDi.length).fill(new Decimal(0)).concat(minusDi);
        this._cacheIndicator(cacheKeyAdx, finalAdx); this._cacheIndicator(cacheKeyPlus, finalPlus); this._cacheIndicator(cacheKeyMinus, finalMinus); return [finalAdx, finalPlus, finalMinus];
    }
    calculateMomentum(period = 10) {
        const cacheKey = `Momentum_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const closes = this.getColumn('close'); if (closes.length < period) return Array(closes.length).fill(new Decimal(0));
        const result = Array(period).fill(new Decimal(0)); for (let i = period; i < closes.length; i++) { result.push(closes[i].minus(closes[i - period])); } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateWilliamsR(period = 14) {
        const cacheKey = `WilliamsR_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close');
        if (highs.length < period) return Array(highs.length).fill(new Decimal(-50));
        const result = Array(period).fill(new Decimal(-50));
        for (let i = period - 1; i < highs.length; i++) {
            const segmentHighs = highs.slice(i - period + 1, i + 1); const segmentLows = lows.slice(i - period + 1, i + 1);
            const highestHigh = Decimal.max(...segmentHighs); const lowestLow = Decimal.min(...segmentLows);
            if (highestHigh.equals(lowestLow)) result.push(new Decimal(-50)); else {
                const wr = highestHigh.minus(closes[i]).dividedBy(highestHigh.minus(lowestLow)).times(-100); result.push(wr);
            }
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateCCI(period = 20) {
        const cacheKey = `CCI_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close');
        if (highs.length < period) return Array(highs.length).fill(new Decimal(0));
        const tp = []; for (let i = 0; i < highs.length; i++) { tp.push(highs[i].plus(lows[i]).plus(closes[i]).dividedBy(3)); }
        const smaTp = this.calculateSMA(period, tp);
        const result = Array(period).fill(new Decimal(0));
        for (let i = period - 1; i < tp.length; i++) {
            const tpSegment = tp.slice(i - period + 1, i + 1); const meanTp = smaTp[i]; if (meanTp.isZero()) { result.push(new Decimal(0)); continue; }
            const mad = tpSegment.reduce((sum, t) => sum.plus(t.minus(meanTp).abs()), new Decimal(0)).dividedBy(period);
            if (mad.isZero()) result.push(new Decimal(0)); else { const cci = tp[i].minus(meanTp).dividedBy(new Decimal('0.015').times(mad)); result.push(cci); }
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateMFI(period = 14) {
        const cacheKey = `MFI_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const closes = this.getColumn('close'); const volumes = this.getColumn('volume');
        if (highs.length < period) return Array(highs.length).fill(new Decimal(50));
        const tp = []; for (let i = 0; i < highs.length; i++) { tp.push(highs[i].plus(lows[i]).plus(closes[i]).dividedBy(3)); }
        const mfi = Array(period).fill(new Decimal(50));
        for (let i = period; i < tp.length; i++) {
            let positiveFlow = new Decimal(0); let negativeFlow = new Decimal(0);
            for (let j = i - period + 1; j <= i; j++) {
                if (tp[j].gt(tp[j - 1])) positiveFlow = positiveFlow.plus(volumes[j].times(tp[j]));
                else if (tp[j].lt(tp[j - 1])) negativeFlow = negativeFlow.plus(volumes[j].times(tp[j]));
            }
            let moneyRatio = new Decimal(0); if (!negativeFlow.isZero()) moneyRatio = positiveFlow.dividedBy(negativeFlow);
            let currentMfi = new Decimal(50);
            if (moneyRatio.isZero()) currentMfi = positiveFlow.gt(0) ? new Decimal(100) : new Decimal(50);
            else currentMfi = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(moneyRatio)));
            mfi.push(currentMfi);
        } this._cacheIndicator(cacheKey, mfi); return mfi;
    }
    calculatePriceOscillator(fastPeriod = 5, slowPeriod = 10) {
        const cacheKey = `PriceOscillator_${fastPeriod}_${slowPeriod}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const emaFast = this.calculateEMA(fastPeriod, 'close'); const emaSlow = this.calculateEMA(slowPeriod, 'close');
        const result = []; for (let i = 0; i < emaFast.length; i++) {
            if (emaFast[i] && emaSlow[i] && !emaSlow[i].isZero()) result.push(emaFast[i].minus(emaSlow[i])); else result.push(new Decimal(0));
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateTickDivergence(lookback = 5) {
        const cacheKey = `TickDivergence_${lookback}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const divergenceScore = Array(this.klines.size).fill(new Decimal(0));
        this.logger.debug("Tick divergence calculation is a placeholder."); this._cacheIndicator(cacheKey, divergenceScore); return divergenceScore;
    }
    calculateVolatilitySqueeze(period = 20) {
        const cacheKey = `VolatilitySqueeze_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); if (highs.length < period) return Array(highs.length).fill(new Decimal(0));
        const result = Array(period).fill(new Decimal(0));
        for (let i = period - 1; i < highs.length; i++) {
            const segmentHighs = highs.slice(i - period + 1, i + 1); const segmentLows = lows.slice(i - period + 1, i + 1);
            const highestHigh = Decimal.max(...segmentHighs); const lowestLow = Decimal.min(...segmentLows);
            const width = highestHigh.minus(lowestLow); result.push(width);
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateMicroTrend(period = 5) {
        const cacheKey = `MicroTrend_${period}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const closes = this.getColumn('close'); if (closes.length < period) return Array(closes.length).fill(0);
        const result = Array(period).fill(0);
        for (let i = period - 1; i < closes.length; i++) {
            if (closes[i].gt(closes[i - period])) result.push(1); else if (closes[i].lt(closes[i - period])) result.push(-1); else result.push(0);
        } this._cacheIndicator(cacheKey, result); return result;
    }
    calculateOrderFlow(lookback = 10) {
        const cacheKey = `OrderFlow_${lookback}`; const cached = this._getCachedIndicator(cacheKey); if (cached) return cached;
        const flowScore = Array(this.klines.size).fill(new Decimal(0));
        if (this.tickData.size < lookback) { this._cacheIndicator(cacheKey, flowScore); return flowScore; }
        let aggressiveBuys = new Decimal(0); let aggressiveSells = new Decimal(0);
        const recentTicks = Array.from(this.tickData).slice(-lookback);
        for (const tick of recentTicks) {
            if (tick.side === 'Buy') aggressiveBuys = aggressiveBuys.plus(tick.volume); else if (tick.side === 'Sell') aggressiveSells = aggressiveSells.plus(tick.volume);
        }
        const netFlow = aggressiveBuys.minus(aggressiveSells); flowScore[flowScore.length - 1] = netFlow;
        this._cacheIndicator(cacheKey, flowScore); return flowScore;
    }

    calculateSupportResistance() {
        if (this.klines.size < 5) return;
        const highs = this.getColumn('high'); const lows = this.getColumn('low'); const n = highs.length;
        const supports = []; const resistances = [];
        for (let i = 2; i < n - 2; i++) {
            if (highs[i].gt(highs[i - 1]) && highs[i].gt(highs[i + 1]) && highs[i].gt(highs[i - 2]) && highs[i].gt(highs[i + 2])) resistances.push(highs[i]);
            if (lows[i].lt(lows[i - 1]) && lows[i].lt(lows[i + 1]) && lows[i].lt(lows[i - 2]) && lows[i].lt(lows[i + 2])) supports.push(lows[i]);
        }
        this.supportLevels = _.sortBy(_.uniq(supports), d => d.toNumber()); this.resistanceLevels = _.sortBy(_.uniq(resistances), d => d.toNumber());
        this.logger.debug(`Identified Supports: ${this.supportLevels.map(d => d.toString())}`); this.logger.debug(`Identified Resistances: ${this.resistanceLevels.map(d => d.toString())}`);
    }

    getIndicatorValues() {
        this.calculateSupportResistance();
        const indicators = CONFIG.indicators;
        if (indicators.smaShort) this.calculateSMA(indicators.smaShort, 'close'); if (indicators.smaLong) this.calculateSMA(indicators.smaLong, 'close');
        if (indicators.emaShort) this.calculateEMA(indicators.emaShort, 'close'); if (indicators.emaLong) this.calculateEMA(indicators.emaLong, 'close');
        if (indicators.atr) this.calculateATR(indicators.atr); if (indicators.rsi) this.calculateRSI(indicators.rsi, 'close');
        if (indicators.stochRsiK) this.calculateStochRSI(indicators.rsi, indicators.stochRsiK, indicators.stochRsiSmooth);
        if (indicators.bollingerBandsPeriod) this.calculateBollingerBands(indicators.bollingerBandsPeriod, indicators.bollingerBandsStddev);
        if (indicators.vwap) this.calculateVWAP();
        if (indicators.macdFast) this.calculateMACD(indicators.macdFast, indicators.macdSlow, indicators.macdSignal);
        if (indicators.adxPeriod) this.calculateADX(indicators.adxPeriod); if (indicators.momentumPeriod) this.calculateMomentum(indicators.momentumPeriod);
        if (indicators.williamsRPeriod) this.calculateWilliamsR(indicators.williamsRPeriod); if (indicators.cciPeriod) this.calculateCCI(indicators.cciPeriod);
        if (indicators.mfiPeriod) this.calculateMFI(indicators.mfiPeriod);
        if (indicators.priceOscillatorFast) this.calculatePriceOscillator(indicators.priceOscillatorFast, indicators.priceOscillatorSlow);
        if (indicators.tickDivergenceLookback) this.calculateTickDivergence(indicators.tickDivergenceLookback);
        if (indicators.volatilitySqueezePeriod) this.calculateVolatilitySqueeze(indicators.volatilitySqueezePeriod);
        if (indicators.microTrendPeriod) this.calculateMicroTrend(indicators.microTrendPeriod);
        if (indicators.orderFlowLookback) this.calculateOrderFlow(indicators.orderFlowLookback);
        return this.getLatestIndicatorValues();
    }

    getLatestIndicatorValues() {
        const latestValues = {};
        for (const [key, values] of Object.entries(this.indicatorCache)) {
            if (values && values.length > 0) latestValues[key] = values[values.length - 1];
        }
        latestValues["supportLevels"] = this.supportLevels; latestValues["resistanceLevels"] = this.resistanceLevels;
        return latestValues;
    }
}

// -----------------------------------
// Signal Generation - The Oracle's Prophecy
// -----------------------------------
class SignalGenerator {
    constructor(klineDataStore, logger, config) {
        this.klineData = klineDataStore; this.logger = logger; this.config = config;
    }

    _getLatest(indicatorName) { const values = this.klineData.indicatorCache[indicatorName]; return (values && values.length > 0) ? values[values.length - 1] : null; }
    _getPrevious(indicatorName) { const values = this.klineData.indicatorCache[indicatorName]; return (values && values.length > 1) ? values[values.length - 2] : null; }

    _checkCondition(value, condition, threshold) {
        if (value === null) return false;
        const valDecimal = new Decimal(value); const thresholdDecimal = new Decimal(threshold);
        switch (condition) {
            case 'gt': return valDecimal.gt(thresholdDecimal); case 'lt': return valDecimal.lt(thresholdDecimal);
            case 'gte': return valDecimal.gte(thresholdDecimal); case 'lte': return valDecimal.lte(thresholdDecimal);
            case 'eq': return valDecimal.eq(thresholdDecimal); default: return false;
        }
    }

    generateSignal() {
        let signal = "HOLD"; const signalData = { signal: "HOLD", strength: 0, reason: [], indicators: {}, volatility: null, orderFlow: null, support: [], resistance: [] };
        const minDataPoints = Math.max(CONFIG.indicators.smaLong || 0, CONFIG.indicators.emaLong || 0, CONFIG.indicators.atr || 0, CONFIG.indicators.rsi || 0, CONFIG.indicators.macdSlow || 0, CONFIG.indicators.adxPeriod || 0, CONFIG.indicators.momentumPeriod || 0, CONFIG.indicators.williamsRPeriod || 0, CONFIG.indicators.cciPeriod || 0, CONFIG.indicators.mfiPeriod || 0, CONFIG.indicators.volatilitySqueezePeriod || 0, CONFIG.indicators.microTrendPeriod || 0);
        if (this.klineData.klines.size < minDataPoints) { this.logger.debug("Not enough kline data for signal generation."); return signalData; }

        const latestKline = this.klineData.klines[this.klineData.klines.size - 1];
        const latestIndicators = this.klineData.getIndicatorValues();
        signalData.indicators = latestIndicators; signalData.volatility = this._getLatest(`ATR_${CONFIG.indicators.atr}`);
        signalData.orderFlow = this._getLatest(`OrderFlow_${CONFIG.indicators.orderFlowLookback}`);
        signalData.support = latestIndicators.supportLevels || []; signalData.resistance = latestIndicators.resistanceLevels || [];

        let buyConditionsMet = 0; let sellConditionsMet = 0; let totalBuyConditions = 0; let totalSellConditions = 0;
        const addCondition = (check, weight = 1) => {
            if (check) {
                const [type, condition] = check.split(':');
                if (type === "BUY") { buyConditionsMet += weight; totalBuyConditions += weight; }
                else if (type === "SELL") { sellConditionsMet += weight; totalSellConditions += weight; }
                return true;
            } return false;
        };

        // --- Momentum & Trend ---
        const emaShort = this._getLatest(`EMA_${CONFIG.indicators.emaShort}_close`); const emaLong = this._getLatest(`EMA_${CONFIG.indicators.emaLong}_close`);
        const emaShortPrev = this._getPrevious(`EMA_${CONFIG.indicators.emaShort}_close`); const emaLongPrev = this._getPrevious(`EMA_${CONFIG.indicators.emaLong}_close`);
        if (emaShort && emaLong) {
            if (emaShort.gt(emaLong) && (emaShortPrev === null || emaShortPrev.lte(emaLongPrev))) addCondition("BUY:EMA_CROSS");
            else if (emaShort.lt(emaLong) && (emaShortPrev === null || emaShortPrev.gte(emaLongPrev))) addCondition("SELL:EMA_CROSS");
        }
        const macdLine = this._getLatest(`MACD_Line_${CONFIG.indicators.macdFast}_${CONFIG.indicators.macdSlow}_${CONFIG.indicators.macdSignal}`);
        const macdSignal = this._getLatest(`MACD_Signal_${CONFIG.indicators.macdFast}_${CONFIG.indicators.macdSlow}_${CONFIG.indicators.macdSignal}`);
        const macdLinePrev = this._getPrevious(`MACD_Line_${CONFIG.indicators.macdFast}_${CONFIG.indicators.macdSlow}_${CONFIG.indicators.macdSignal}`);
        const macdSignalPrev = this._getPrevious(`MACD_Signal_${CONFIG.indicators.macdFast}_${CONFIG.indicators.macdSlow}_${CONFIG.indicators.macdSignal}`);
        if (macdLine && macdSignal) {
            if (macdLine.gt(macdSignal) && (macdLinePrev === null || macdLinePrev.lte(macdSignalPrev))) addCondition("BUY:MACD_CROSS");
            else if (macdLine.lt(macdSignal) && (macdLinePrev === null || macdLinePrev.gte(macdSignalPrev))) addCondition("SELL:MACD_CROSS");
        }
        const adx = this._getLatest(`ADX_${CONFIG.indicators.adxPeriod}`); const plusDi = this._getLatest(`PlusDI_${CONFIG.indicators.adxPeriod}`); const minusDi = this._getLatest(`MinusDI_${CONFIG.indicators.adxPeriod}`);
        if (adx && adx.gt(CONFIG.scalpingStrategy.entryConditions.adxThreshold)) {
            if (plusDi && minusDi) { if (plusDi.gt(minusDi)) addCondition("BUY:TREND_UP"); else addCondition("SELL:TREND_DOWN"); }
        }
        // --- Oscillators ---
        const rsi = this._getLatest(`RSI_${CONFIG.indicators.rsi}_close`); const stochK = this._getLatest(`StochRSI_K_${CONFIG.indicators.rsi}_${CONFIG.indicators.stochRsiK}_${CONFIG.indicators.stochRsiSmooth}`);
        const cci = this._getLatest(`CCI_${CONFIG.indicators.cciPeriod}`); const mfi = this._getLatest(`MFI_${CONFIG.indicators.mfiPeriod}`); const williamsR = this._getLatest(`WilliamsR_${CONFIG.indicators.williamsRPeriod}`);
        if (rsi !== null) { if (this._checkCondition(rsi, 'lt', CONFIG.scalpingStrategy.entryConditions.rsiOversold)) addCondition("BUY:RSI_OVERSOLD"); if (this._checkCondition(rsi, 'gt', CONFIG.scalpingStrategy.entryConditions.rsiOverbought)) addCondition("SELL:RSI_OVERBOUGHT"); }
        if (stochK !== null) { if (this._checkCondition(stochK, 'lt', CONFIG.scalpingStrategy.entryConditions.stochRsiKOversold)) addCondition("BUY:STOCH_RSI_OVERSOLD"); if (this._checkCondition(stochK, 'gt', CONFIG.scalpingStrategy.entryConditions.stochRsiKOverbought)) addCondition("SELL:STOCH_RSI_OVERBOUGHT"); }
        if (cci !== null) { if (this._checkCondition(cci, 'lt', CONFIG.scalpingStrategy.entryConditions.cciOversold)) addCondition("BUY:CCI_OVERSOLD"); if (this._checkCondition(cci, 'gt', CONFIG.scalpingStrategy.entryConditions.cciOverbought)) addCondition("SELL:CCI_OVERBOUGHT"); }
        if (mfi !== null) { if (this._checkCondition(mfi, 'lt', CONFIG.scalpingStrategy.entryConditions.mfiOversold)) addCondition("BUY:MFI_OVERSOLD"); if (this._checkCondition(mfi, 'gt', CONFIG.scalpingStrategy.entryConditions.mfiOverbought)) addCondition("SELL:MFI_OVERBOUGHT"); }
        if (williamsR !== null) { if (this._checkCondition(williamsR, 'lt', -80)) addCondition("BUY:WILLIAMS_R_OVERSOLD"); if (this._checkCondition(williamsR, 'gt', -20)) addCondition("SELL:WILLIAMS_R_OVERBOUGHT"); }
        // --- Price Action & Support/Resistance ---
        const [bbUpper, bbMiddle, bbLower] = this.klineData.calculateBollingerBands(CONFIG.indicators.bollingerBandsPeriod, CONFIG.indicators.bollingerBandsStddev);
        const vwap = this._getLatest("VWAP");
        if (bbUpper && bbLower && latestKline) {
            const prevKline = this.klineData.klines.size > 1 ? this.klineData.klines[this.klineData.klines.size - 2] : null;
            if (prevKline) {
                if (latestKline.close.gt(bbUpper[bbUpper.length - 1]) && prevKline.close.lte(bbUpper[bbUpper.length - 2])) addCondition("SELL:BB_BREAKOUT_UP");
                if (latestKline.close.lt(bbLower[bbLower.length - 1]) && prevKline.close.gte(bbLower[bbLower.length - 2])) addCondition("BUY:BB_BREAKOUT_DOWN");
            }
        }
        if (vwap && latestKline) {
            if (CONFIG.scalpingStrategy.entryConditions.vwapRejectionBuy && latestKline.close.lt(vwap) && this.klineData.klines[this.klineData.klines.size - 2]?.close.lt(vwap)) {
                if (latestKline.close.gt(this.klineData.klines[this.klineData.klines.size - 2]?.close)) addCondition("BUY:VWAP_REJECTION");
            }
            if (CONFIG.scalpingStrategy.entryConditions.vwapRejectionSell && latestKline.close.gt(vwap) && this.klineData.klines[this.klineData.klines.size - 2]?.close.gt(vwap)) {
                if (latestKline.close.lt(this.klineData.klines[this.klineData.klines.size - 2]?.close)) addCondition("SELL:VWAP_REJECTION");
            }
        }
        if (CONFIG.scalpingStrategy.entryConditions.supportResistanceBounceBuy && latestIndicators.supportLevels) {
            for (const support of latestIndicators.supportLevels) {
                if (latestKline.low.lte(support) && latestKline.close.gt(support)) { addCondition("BUY:SUPPORT_BOUNCE"); break; }
            }
        }
        if (CONFIG.scalpingStrategy.entryConditions.supportResistanceBounceSell && latestIndicators.resistanceLevels) {
            for (const resistance of latestIndicators.resistanceLevels) {
                if (latestKline.high.gte(resistance) && latestKline.close.lt(resistance)) { addCondition("SELL:RESISTANCE_BOUNCE"); break; }
            }
        }
        const volSqueeze = this._getLatest(`VolatilitySqueeze_${CONFIG.indicators.volatilitySqueezePeriod}`);
        if (volSqueeze && bbUpper && bbLower) {
            const bbWidth = bbUpper[bbUpper.length - 1].minus(bbLower[bbLower.length - 1]);
            if (CONFIG.scalpingStrategy.entryConditions.volatilitySqueezeBreakoutBuy && latestKline.close.gt(bbUpper[bbUpper.length - 1]) && volSqueeze.lt(bbWidth.times(0.5))) addCondition("BUY:VOL_SQZ_BREAKOUT");
            if (CONFIG.scalpingStrategy.entryConditions.volatilitySqueezeBreakoutSell && latestKline.close.lt(bbLower[bbLower.length - 1]) && volSqueeze.lt(bbWidth.times(0.5))) addCondition("SELL:VOL_SQZ_BREAKOUT");
        }
        const orderFlow = signalData.orderFlow;
        if (CONFIG.scalpingStrategy.entryConditions.orderFlowConfirmationBuy && orderFlow !== null && orderFlow.gt(0)) addCondition("BUY:ORDER_FLOW_POSITIVE");
        if (CONFIG.scalpingStrategy.entryConditions.orderFlowConfirmationSell && orderFlow !== null && orderFlow.lt(0)) addCondition("SELL:ORDER_FLOW_NEGATIVE");

        const strengthThreshold = 0.6;
        if (totalBuyConditions > 0 && (buyConditionsMet / totalBuyConditions) >= strengthThreshold) {
            signal = "BUY"; signalData.strength = buyConditionsMet / totalBuyConditions; signalData.reason.push(`Strong BUY (${buyConditionsMet}/${totalBuyConditions})`);
        } else if (totalSellConditions > 0 && (sellConditionsMet / totalSellConditions) >= strengthThreshold) {
            signal = "SELL"; signalData.strength = sellConditionsMet / totalSellConditions; signalData.reason.push(`Strong SELL (${sellConditionsMet}/${totalSellConditions})`);
        } else if (totalBuyConditions > 0 && buyConditionsMet > 0) {
            signal = "BUY"; signalData.strength = buyConditionsMet / totalBuyConditions; signalData.reason.push(`Weak BUY (${buyConditionsMet}/${totalBuyConditions})`);
        } else if (totalSellConditions > 0 && sellConditionsMet > 0) {
            signal = "SELL"; signalData.strength = sellConditionsMet / totalSellConditions; signalData.reason.push(`Weak SELL (${sellConditionsMet}/${totalSellConditions})`);
        }
        signalData.signal = signal; return signalData;
    }
}

// -----------------------------------
// Position Management - The Guardian of Trades
// -----------------------------------
class PositionManager {
    constructor(apiClient, klineDataStore, signalGenerator, config, logger) {
        this.api = apiClient; this.klineData = klineDataStore; this.signalGen = signalGenerator;
        this.config = config; this.logger = logger;
        this.openPositions = {}; this.tradeHistory = new deque(100);
        this.martingaleLevel = 0; this.consecutiveLosses = 0;
        this.dailyPnl = new Decimal("0.0"); this.equity = new Decimal("0.0"); this.peakEquity = new Decimal("0.0");
        this.lastEquityUpdateTime = 0; this.equityUpdateInterval = 60000;
        this.positionTimers = {}; this.breakEvenTimers = {};
    }

    _updateEquity() {
        const currentBalance = getCurrentBalance();
        let unrealizedPnl = new Decimal(0); // Placeholder
        this.equity = currentBalance.plus(unrealizedPnl);
        if (this.equity.gt(this.peakEquity)) this.peakEquity = this.equity;
        this.lastEquityUpdateTime = Date.now();
        this.logger.debug(`Equity updated: ${this.equity.toFixed(4)} | Peak: ${this.peakEquity.toFixed(4)}`);
    }

    _calculatePositionSize(signalData) {
        if (this.klineData.klines.size === 0) return null;
        const latestKline = this.klineData.klines[this.klineData.klines.size - 1];
        const currentPrice = latestKline.close; const atr = signalData.volatility;
        if (!atr || atr.isZero()) { this.logger.warn("ATR is zero or missing, cannot calculate position size."); return null; }

        let riskAmount = this.equity.times(this.config.riskPerTradePercent);
        if (this.config.martingaleEnabled && this.consecutiveLosses > 0 && this.martingaleLevel < this.config.maxMartingaleLevels) {
            const multiplier = this.config.martingaleMultiplier.pow(this.martingaleLevel);
            riskAmount = riskAmount.times(multiplier);
            logMessage("warn", chalk.yellow(`[Martingale] Level ${this.martingaleLevel + 1}, Multiplier x${multiplier.toFixed(2)}`));
        }

        const stopLossAtrMultiple = this.config.scalpingStrategy.exitConditions.stopLossAtrMultiple;
        const stopLossDistance = atr.times(stopLossAtrMultiple);
        if (stopLossDistance.isZero() || stopLossDistance.isNegative()) { this.logger.warn("Calculated stop loss distance is zero or negative."); return null; }

        let positionUsd = riskAmount.dividedBy(stopLossDistance);
        const maxAllowedUsd = this.equity.times(this.config.maxPositionSizePercent);
        positionUsd = Decimal.min(positionUsd, maxAllowedUsd);

        let qty = positionUsd.dividedBy(currentPrice);
        qty = formatDecimal(qty, CONFIG.qtyPrecision);
        qty = Decimal.max(qty, this.config.minOrderSize);

        this.logger.info(`Calculated Position Size: ${qty} ${CONFIG.symbol} | Risk Amount: $${riskAmount.toFixed(2)} | SL Distance: ${stopLossDistance.toFixed(4)}`);
        return qty;
    }

    _getEntryExitPrices(side, currentPrice, atr) {
        const stopLossAtrMultiple = this.config.scalpingStrategy.exitConditions.stopLossAtrMultiple;
        const takeProfitAtrMultiple = this.config.scalpingStrategy.exitConditions.takeProfitAtrMultiple;
        const stopLossDistance = atr.times(stopLossAtrMultiple);
        const takeProfitDistance = atr.times(takeProfitAtrMultiple);
        let stopLoss, takeProfit;
        if (side === "BUY") {
            stopLoss = currentPrice.minus(stopLossDistance); takeProfit = currentPrice.plus(takeProfitDistance);
        } else {
            stopLoss = currentPrice.plus(stopLossDistance); takeProfit = currentPrice.minus(takeProfitDistance);
        }
        stopLoss = formatDecimal(stopLoss, CONFIG.pricePrecision); takeProfit = formatDecimal(takeProfit, CONFIG.pricePrecision);
        return { entryPrice: currentPrice, stopLoss, takeProfit };
    }

    async _placeOrderAndUpdatePosition(side, qty, signalData) {
        const currentTicker = await this.api.fetchTicker(CONFIG.symbol);
        if (!currentTicker) { this.logger.error("Could not fetch current price for order placement."); return null; }
        const currentPrice = currentTicker.lastPrice; const atr = signalData.volatility;
        if (!atr || atr.isZero()) { this.logger.warn("ATR is missing or zero, cannot calculate SL/TP."); return null; }

        const { entryPrice, stopLoss, takeProfit } = this._getEntryExitPrices(side, currentPrice, atr);
        const orderResult = await this.api.placeOrder(CONFIG.symbol, side, 'Market', qty);

        if (orderResult && orderResult.status === 'FILLED') {
            const positionId = `pos_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
            let partialTpPrice = null;
            if (this.config.scalpingStrategy.exitConditions.partialTakeProfit) {
                const partialTpDistance = atr.times(this.config.scalpingStrategy.exitConditions.partialTakeProfitAtrMultiple);
                partialTpPrice = side === "BUY" ? entryPrice.plus(partialTpDistance) : entryPrice.minus(partialTpDistance);
                partialTpPrice = formatDecimal(partialTpPrice, CONFIG.pricePrecision);
            }

            const position = {
                id: positionId, symbol: CONFIG.symbol, side, entryPrice, qty, stopLoss, takeProfit,
                partialTpPrice, partialTpTriggered: false, entryTime: Date.now(), status: 'OPEN',
                signalData, atrAtEntry: atr, martingaleLevel: this.martingaleLevel,
                breakEvenPrice: null, trailingStopActive: false, trailingStopPrice: null,
            };
            this.openPositions[positionId] = position;

            const maxHoldTime = this.config.scalpingStrategy.exitConditions.maxHoldTimeMs;
            if (maxHoldTime > 0) {
                const timerId = setTimeout(maxHoldTime, positionId, 'TIME_LIMIT');
                timerId.then(id => this.forceClosePosition(id, 'TIME_LIMIT')).catch(e => this.logger.error(`Timer error: ${e.message}`));
                this.positionTimers[positionId] = timerId;
            }
            const breakEvenDelay = this.config.scalpingStrategy.exitConditions.breakEvenDelayMs;
            if (breakEvenDelay > 0 && this.config.scalpingStrategy.exitConditions.breakEvenThresholdAtrMultiple.gt(0)) {
                const beTimerId = setTimeout(breakEvenDelay, positionId);
                beTimerId.then(id => this.updateBreakEven(id)).catch(e => this.logger.error(`BE Timer error: ${e.message}`));
                this.breakEvenTimers[positionId] = beTimerId;
            }

            this.tradeHistory.push({ id: positionId, side, entryPrice, qty, entryTime: Date.now(), signalData });
            logMessage("success", `Opened Position: ${side} ${qty} ${CONFIG.symbol} @ ${entryPrice} | SL: ${stopLoss} | TP: ${takeProfit}`);
            try { execSync(`termux-toast "Opened ${side} ${CONFIG.symbol}"`); } catch (e) {}
            return position;
        } else { this.logger.error(`Failed to open position for ${CONFIG.symbol}.`); return null; }
    }

    async manageOpenPositions(currentPriceDecimal) {
        if (Object.keys(this.openPositions).length === 0) return;
        const positionsToClose = [];
        for (const [posId, pos] of Object.entries(this.openPositions)) {
            if (pos.status !== 'OPEN') continue;
            let { side, stopLoss, takeProfit } = pos;
            let currentStopLoss = new Decimal(stopLoss);

            // Trailing Stop Logic
            if (this.config.scalpingStrategy.exitConditions.trailingStopEnabled) {
                const trailingAtrMultiple = this.config.scalpingStrategy.exitConditions.trailingAtrMultiple;
                const atrAtEntry = pos.atrAtEntry || new Decimal(0);
                if (atrAtEntry.gt(0)) {
                    let potentialNewSl = null;
                    if (side === "BUY") {
                        potentialNewSl = currentPriceDecimal.minus(atrAtEntry.times(trailingAtrMultiple));
                        if (potentialNewSl.gt(currentStopLoss)) {
                            currentStopLoss = potentialNewSl; pos.trailingStopActive = true; pos.trailingStopPrice = currentStopLoss;
                            this.logger.debug(chalk.cyan(`[Trailing SL] ${pos.id} updated to ${currentStopLoss.toFixed(4)}`));
                        }
                    } else { // SELL
                        potentialNewSl = currentPriceDecimal.plus(atrAtEntry.times(trailingAtrMultiple));
                        if (potentialNewSl.lt(currentStopLoss)) {
                            currentStopLoss = potentialNewSl; pos.trailingStopActive = true; pos.trailingStopPrice = currentStopLoss;
                            this.logger.debug(chalk.cyan(`[Trailing SL] ${pos.id} updated to ${currentStopLoss.toFixed(4)}`));
                        }
                    }
                }
            }
            pos.stopLoss = currentStopLoss; // Update position's SL

            // Check SL/TP Hit
            let closeReason = null;
            if (side === "BUY") {
                if (currentPriceDecimal.lte(currentStopLoss)) closeReason = "STOP_LOSS";
                else if (currentPriceDecimal.gte(takeProfit)) closeReason = "TAKE_PROFIT";
            } else { // SELL
                if (currentPriceDecimal.gte(currentStopLoss)) closeReason = "STOP_LOSS";
                else if (currentPriceDecimal.lte(takeProfit)) closeReason = "TAKE_PROFIT";
            }

            // Partial Take Profit Logic
            if (this.config.scalpingStrategy.exitConditions.partialTakeProfit && !pos.partialTpTriggered) {
                const partialTpPrice = pos.partialTpPrice;
                if (partialTpPrice) {
                    if (side === "BUY" && currentPriceDecimal.gte(partialTpPrice)) {
                        await this.triggerPartialTakeProfit(posId); closeReason = "PARTIAL_TP";
                    } else if (side === "SELL" && currentPriceDecimal.lte(partialTpPrice)) {
                        await this.triggerPartialTakeProfit(posId); closeReason = "PARTIAL_TP";
                    }
                }
            }
            if (closeReason) positionsToClose.push({ id: posId, reason: closeReason });
        }
        for (const item of positionsToClose) await this.closePosition(item.id, item.reason);
    }

    async updateBreakEven(positionId) {
        const pos = this.openPositions[positionId];
        if (!pos || pos.status !== 'OPEN') return;
        const currentTicker = await this.api.fetchTicker(CONFIG.symbol);
        if (!currentTicker) { this.logger.warn(`Could not fetch ticker for BE update ${positionId}.`); return; }
        const currentPrice = currentTicker.lastPrice;
        const beThresholdAtrMultiple = this.config.scalpingStrategy.exitConditions.breakEvenThresholdAtrMultiple;
        const atrAtEntry = pos.atrAtEntry || new Decimal(0);
        const profitTargetForBe = atrAtEntry.times(beThresholdAtrMultiple);
        let profitAchieved = false;
        if (pos.side === "BUY") {
            if (currentPrice.gte(pos.entryPrice.plus(profitTargetForBe))) profitAchieved = true;
        } else { // SELL
            if (currentPrice.lte(pos.entryPrice.minus(profitTargetForBe))) profitAchieved = true;
        }
        if (profitAchieved) {
            pos.stopLoss = pos.entryPrice; pos.breakEvenPrice = pos.entryPrice;
            logMessage("info", chalk.cyan(`[Break Even] Position ${positionId} SL moved to entry price: ${pos.stopLoss.toFixed(4)}`));
            try { execSync(`termux-toast "BE stop set for ${pos.symbol}"`); } catch (e) {}
            if (this.breakEvenTimers[positionId]) { clearTimeout(this.breakEvenTimers[positionId]); delete this.breakEvenTimers[positionId]; }
        }
    }

    async triggerPartialTakeProfit(positionId) {
        const pos = this.openPositions[positionId];
        if (!pos || pos.status !== 'OPEN' || pos.partialTpTriggered) return;
        const partialQtyPercent = this.config.scalpingStrategy.exitConditions.partialTakeProfitPercent;
        let partialQty = pos.qty.times(partialQtyPercent); partialQty = formatDecimal(partialQty, CONFIG.qtyPrecision);
        if (partialQty.isZero() || partialQty.isNegative()) { this.logger.warn(`Partial TP quantity zero for ${positionId}.`); return; }
        const closeSide = pos.side === "BUY" ? "SELL" : "BUY";
        const closeResult = await this.api.closePosition(CONFIG.symbol, closeSide, partialQty, pos.partialTpPrice);
        if (closeResult) {
            pos.qty = pos.qty.minus(partialQty); pos.partialTpTriggered = true;
            logMessage("info", chalk.magenta(`[Partial TP] Closed ${partialQty} of ${positionId}. Remaining Qty: ${pos.qty.toFixed(4)}`));
            if (pos.qty.lte(CONFIG.minOrderSize)) await this.forceClosePosition(positionId, "REMAINING_QTY_ZERO");
        }
    }

    async closePosition(positionId, reason) {
        const pos = this.openPositions[positionId];
        if (!pos || pos.status !== 'OPEN') return null;
        const currentTicker = await this.api.fetchTicker(CONFIG.symbol);
        const currentPrice = currentTicker?.lastPrice || pos.entryPrice; // Fallback
        const closeSide = pos.side === "BUY" ? "SELL" : "BUY";
        const closeResult = await this.api.closePosition(CONFIG.symbol, closeSide, pos.qty, currentPrice);
        if (closeResult) {
            const exitPrice = new Decimal(closeResult.avgPrice || currentPrice);
            let pnl = new Decimal(0);
            if (pos.side === "BUY") pnl = exitPrice.minus(pos.entryPrice).times(pos.qty);
            else pnl = pos.entryPrice.minus(exitPrice).times(pos.qty);
            pos.exitPrice = exitPrice; pos.exitTime = Date.now(); pos.status = 'CLOSED'; pos.closedReason = reason; pos.pnl = pnl;
            this.dailyPnl = this.dailyPnl.plus(pnl); this.equity = this.equity.plus(pnl);
            if (this.equity.gt(this.peakEquity)) this.peakEquity = this.equity;
            if (pnl.gt(0)) { this.consecutiveLosses = 0; this.martingaleLevel = 0; } else {
                this.consecutiveLosses++;
                if (this.config.martingaleEnabled && this.martingaleLevel < this.config.maxMartingaleLevels) {
                    this.martingaleLevel++;
                }
            }
            const logMsg = `${chalk.magenta(`Closed Position: ${pos.id} | ${pos.side} ${pos.qty} ${CONFIG.symbol} @ ${exitPrice.toFixed(4)} | Entry: ${pos.entryPrice.toFixed(4)} | PnL: ${pnl.toFixed(4)} | Reason: ${reason} | Daily PnL: ${this.dailyPnl.toFixed(4)} | Equity: ${this.equity.toFixed(4)}`)}`;
            logMessage("info", logMsg);
            try { execSync(`termux-toast "Closed ${pos.symbol} PnL: ${pnl.toFixed(4)}"`); } catch (e) {}
            if (this.positionTimers[positionId]) { clearTimeout(this.positionTimers[positionId]); delete this.positionTimers[positionId]; }
            if (this.breakEvenTimers[positionId]) { clearTimeout(this.breakEvenTimers[positionId]); delete this.breakEvenTimers[positionId]; }
            delete this.openPositions[positionId];
            return pos;
        } else { this.logger.error(`Failed to close position ${positionId}.`); return null; }
    }

    forceClosePosition(positionId, reason) { this.logger.warn(`Forcing closure of position ${positionId} due to: ${reason}`); return this.closePosition(positionId, reason); }

    async checkForNewTrades(signalData) {
        if (signalData.signal === "HOLD") return;
        if (Object.keys(this.openPositions).length >= this.config.maxPositions) {
            this.logger.warn(`Max positions (${this.config.maxPositions}) reached.`); return;
        }
        if (this.config.correlationFilter && this.tradeHistory.length >= 5) {
            const recentTrades = Array.from(this.tradeHistory).slice(-5);
            const sameSideTrades = recentTrades.filter(t => t.side === signalData.signal.toLowerCase());
            if (sameSideTrades.length >= 3) { this.logger.warn(`Correlation filter active: Too many recent ${signalData.signal} trades.`); return; }
        }
        const qty = this._calculatePositionSize(signalData);
        if (!qty) { this.logger.warn("Failed to calculate position size."); return; }
        await this._placeOrderAndUpdatePosition(signalData.signal, qty, signalData);
    }
}

// -----------------------------------
// Main Execution Loop - The Grand Conjuration
// -----------------------------------
async function mainLoop(apiClient, klineData, signalGenerator, positionManager) {
    while (true) {
        const startTime = Date.now();
        try {
            if (Date.now() - positionManager.lastEquityUpdateTime > positionManager.equityUpdateInterval) positionManager._updateEquity();
            const latestKlines = await apiClient.fetchKlines(CONFIG.symbol, CONFIG.timeframes[0], 2);
            if (!latestKlines || latestKlines.length === 0) { logMessage("warn", "No kline data. Skipping."); await delay(CONFIG.loopDelayMs); continue; }
            latestKlines.forEach(k => klineData.addKline(k));

            const minDataPoints = Math.max(CONFIG.indicators.smaLong || 0, CONFIG.indicators.emaLong || 0, CONFIG.indicators.atr || 0, CONFIG.indicators.rsi || 0, CONFIG.indicators.macdSlow || 0, CONFIG.indicators.adxPeriod || 0, CONFIG.indicators.momentumPeriod || 0, CONFIG.indicators.williamsRPeriod || 0, CONFIG.indicators.cciPeriod || 0, CONFIG.indicators.mfiPeriod || 0, CONFIG.indicators.volatilitySqueezePeriod || 0, CONFIG.indicators.microTrendPeriod || 0);
            if (klineData.klines.size < minDataPoints) { logMessage("debug", "Insufficient kline data. Waiting..."); await delay(CONFIG.loopDelayMs); continue; }

            const latestIndicators = klineData.getIndicatorValues();
            const ticker = await apiClient.fetchTicker(CONFIG.symbol);
            if (!ticker) { logMessage("warn", "Ticker data unavailable. Skipping."); await delay(CONFIG.loopDelayMs); continue; }
            const currentPriceDecimal = ticker.lastPrice;

            const signalData = signalGenerator.generateSignal();
            logMessage("info", `Signal: ${signalData.signal} (Strength: ${signalData.strength.toFixed(2)}) | Reason: ${signalData.reason.join(', ')}`);

            await positionManager.manageOpenPositions(currentPriceDecimal);
            if (signalData.signal !== "HOLD") await positionManager.checkForNewTrades(signalData);

            if (apiClient.wsConnected && (Date.now() - apiClient.lastPingTime) > apiClient.pingInterval) apiClient.sendWsPing();

            const elapsedTime = Date.now() - startTime;
            const waitTime = Math.max(0, CONFIG.loopDelayMs - elapsedTime);
            await delay(waitTime);

        } catch (e) {
            logMessage("error", `Main loop error: ${e.message}\n${e.stack}`);
            await delay(CONFIG.retryDelayMs * 2);
        }
    }
}

// --- Entry Point ---
async function startBot() {
    try { require('chalk'); require('node-fetch'); require('ws'); require('lodash'); require('decimal.js'); require('winston'); }
    catch (e) { logMessage("error", `Missing dependency: ${e.message}. Install: npm install chalk node-fetch ws lodash decimal.js winston winston-daily-rotate-file dotenv`); process.exit(1); }
    if (!CONFIG.apiKey || !CONFIG.apiSecret) { logMessage("error", "API keys not set. Export BYBIT_API_KEY and BYBIT_API_SECRET."); process.exit(1); }

    logMessage("info", `Starting Termux Scalping Bot for ${CONFIG.symbol}...`); logMessage("info", `Paper Trading Mode: ${CONFIG.paperTrading}`);

    const api = new BybitAPI(logger); const klineDataStore = new KlineDataStore(logger);
    const signalGenerator = new SignalGenerator(klineDataStore, logger, CONFIG);
    const positionManager = new PositionManager(api, klineDataStore, signalGenerator, CONFIG, logger);

    api.connectWebSocket(CONFIG.symbol);
    api.registerCallback("trade", (msg) => klineDataStore.addTick(msg));

    try { await mainLoop(api, klineDataStore, signalGenerator, positionManager); }
    catch (error) { logMessage("error", `Bot crashed: ${error.message}\n${error.stack}`); }
    finally { logMessage("info", "Bot stopped."); if (api.ws) api.ws.close(); process.exit(0); }
}

startBot();

