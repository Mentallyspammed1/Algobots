// unified_whalebot.js - Enhanced Version 5.0
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
const _ = require('lodash');
const { execSync } = require('child_process');
const WebSocket = require('ws');
const express = require('express');
const http = require('http');
const socketIo = require('socket.io');

// Initialize Decimal.js precision
Decimal.set({ precision: 28 });
dotenv.config();

// --- Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const WEBSOCKET_URL = "wss://stream.bybit.com/v5/public/linear";
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs/trading-bot/logs";
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });
const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000;
const LOOP_DELAY_SECONDS = 15;

// --- Utility Functions ---
function round_qty(qty, step) {
    if (step.lte(0)) return qty;
    return qty.div(step).floor().times(step);
}

function round_price(price, precision) {
    const factor = new Decimal(10).pow(precision);
    return price.times(factor).floor().div(factor);
}

// --- Logging Setup ---
const sensitivePrintf = (template, sensitiveWords) => {
    const escapeRegExp = (string) => {
        return string.replace(/[.*+?^${}()|[\\]/g, '\\$&');
    };
    return winston.format.printf(info => {
        let message = template(info);
        for (const word of sensitiveWords) {
            if (typeof word === 'string' && message.includes(word)) {
                const escapedWord = escapeRegExp(word);
                message = message.replace(new RegExp(escapedWord, 'g'), '*'.repeat(word.length));
            }
        }
        return message;
    });
};

const setup_logger = (log_name, level = 'info') => {
    const logger = winston.createLogger({
        level: level,
        format: winston.format.combine(
            winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
            winston.format.errors({ stack: true }),
            sensitivePrintf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`, [API_KEY, API_SECRET].filter(Boolean))
        ),
        transports: [
            new winston.transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${log_name}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '10m',
                maxFiles: '5d'
            }),
            new winston.transports.Console({
                format: winston.format.combine(
                    winston.format.timestamp({ format: 'HH:mm:ss.SSS' }),
                    sensitivePrintf(info => {
                        let levelColor;
                        switch (info.level) {
                            case 'info': levelColor = chalk.cyan; break;
                            case 'warn': levelColor = chalk.yellow; break;
                            case 'error': levelColor = chalk.red; break;
                            case 'debug': levelColor = chalk.blue; break;
                            case 'critical': levelColor = chalk.magentaBright; break;
                            default: levelColor = chalk.white;
                        }
                        return `${levelColor(info.timestamp)} - ${levelColor(info.level.toUpperCase())} - ${levelColor(info.message)}`;
                    }, [API_KEY, API_SECRET].filter(Boolean))
                )
            })
        ],
        exitOnError: false
    });
    return logger;
};

// --- Technical Indicators (omitted for brevity) ---
const indicators = {};

// --- Configuration Management ---
class ConfigManager {
    constructor(filepath, logger) {
        this.filepath = filepath;
        this.logger = logger;
        this.config = {};
        this.load_config();
    }

    load_config() {
        const defaultConfig = {
            "symbol": "BTCUSDT",
            "interval": "15",
            "loop_delay": LOOP_DELAY_SECONDS,
            "trade_management": {
                "enabled": true,
                "account_balance": 1000.0,
                "risk_per_trade_percent": 1.0,
                "stop_loss_atr_multiple": 1.5,
                "take_profit_atr_multiple": 2.0,
                "max_open_positions": 1
            },
            "martingale": {
                "enabled": false,
                "multiplier": 2.0,
                "max_levels": 5
            },
            "dashboard": {
                "enabled": true,
                "port": 3000,
                "update_interval_ms": 1000
            }
        };

        if (!fs.existsSync(this.filepath)) {
            this.config = defaultConfig;
            fs.writeFileSync(this.filepath, JSON.stringify(this.config, null, 4), 'utf-8');
            this.logger.warn(`Config file not found. Created default at ${this.filepath}`);
        } else {
            const userConfig = JSON.parse(fs.readFileSync(this.filepath, 'utf-8'));
            this.config = _.mergeWith({}, defaultConfig, userConfig, (obj, src) => {
                if (_.isNumber(obj) && _.isNumber(src)) return src;
            });
            fs.writeFileSync(this.filepath, JSON.stringify(this.config, null, 4), 'utf-8');
            this.logger.info(`Configuration loaded from ${this.filepath}`);
        }
    }
}

// --- WebSocket Client ---
class WebSocketClient {
    constructor(url, logger) {
        this.ws = null;
        this.url = url;
        this.logger = logger;
        this.subscriptions = new Set();
        this.callbacks = {};
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelayBase = 1000;
        this.pingInterval = null;
    }

    connect() {
        if (this.ws) {
            this.ws.close();
        }
        this.ws = new WebSocket(this.url);

        this.ws.on('open', () => {
            this.logger.info(chalk.green('WebSocket connected.'));
            this.reconnectAttempts = 0;
            this.resubscribe();
            this.startPing();
        });

        this.ws.on('message', (data) => {
            try {
                const message = JSON.parse(data);
                if (message.topic && this.callbacks[message.topic]) {
                    this.callbacks[message.topic](message.data);
                } else if (message.op === 'pong') {
                    // Handled by ping interval
                } else {
                     for (const key in this.callbacks) {
                        if (message.type && key.includes(message.type)) {
                            this.callbacks[key](message.data);
                            break;
                        }
                    }
                }
            } catch (e) {
                this.logger.error(`Error processing WebSocket message: ${e.message}`);
            }
        });

        this.ws.on('close', () => {
            this.logger.warn('WebSocket disconnected.');
            this.stopPing();
            this.reconnect();
        });

        this.ws.on('error', (err) => {
            this.logger.error(`WebSocket error: ${err.message}`);
            this.ws.close();
        });
    }

    subscribe(topics, callback) {
        const topicKey = Array.isArray(topics) ? topics.join(',') : topics;
        this.subscriptions.add(topicKey);
        this.callbacks[topicKey] = callback;

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ op: 'subscribe', args: Array.isArray(topics) ? topics : [topics] }));
        }
    }
    
    resubscribe() {
        if (this.subscriptions.size > 0) {
            this.subscriptions.forEach(topicKey => {
                const topics = topicKey.split(',');
                this.logger.info(`Resubscribing to topics: ${topics.join(', ')}`);
                this.ws.send(JSON.stringify({ op: 'subscribe', args: topics }));
            });
        }
    }

    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelayBase * Math.pow(2, this.reconnectAttempts);
            this.logger.info(`Attempting to reconnect in ${delay / 1000}s...`);
            setTimeout(() => this.connect(), delay);
        } else {
            this.logger.error('Max WebSocket reconnect attempts reached.');
        }
    }

    startPing() {
        this.pingInterval = setInterval(() => {
            if (this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ op: 'ping' }));
            }
        }, 20000);
    }

    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
}

// --- Dashboard ---
class Dashboard {
    constructor(config, logger) {
        this.config = config.dashboard;
        this.logger = logger;
        if (!this.config.enabled) return;

        this.app = express();
        this.server = http.createServer(this.app);
        this.io = socketIo(this.server);
        this.port = this.config.port;
    }

    start() {
        if (!this.config.enabled) return;

        this.app.use(express.static(path.join(__dirname, 'public')));
        
        this.app.get('/', (req, res) => {
            res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
        });

        this.io.on('connection', (socket) => {
            this.logger.info('Dashboard client connected');
            socket.on('disconnect', () => {
                this.logger.info('Dashboard client disconnected');
            });
        });

        this.server.listen(this.port, () => {
            this.logger.info(`Dashboard running on http://localhost:${this.port}`);
        });
    }

    update(data) {
        if (this.config.enabled) {
            this.io.emit('update', data);
        }
    }
}

// --- BybitClient (as in wb4.0.js) ---
class BybitClient { 
    constructor(apiKey, apiSecret, baseUrl, logger) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = baseUrl;
        this.logger = logger;
        this.recvWindow = '5000'; // Default receive window
        this.timestamp = null;
        this.requestCount = 0;
    }

    async getTimestamp() {
        if (this.timestamp && (Date.now() - this.timestamp.time < 60000)) {
            return this.timestamp.serverTime;
        }
        try {
            const response = await fetch(`${this.baseUrl}/v5/time`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            this.timestamp = { time: Date.now(), serverTime: data.time };
            return data.time;
        } catch (error) {
            this.logger.error(`Failed to get server time: ${error.message}`);
            throw error;
        }
    }

    sign(path, method, params = {}) {
        const timestamp = String(Date.now());
        const queryString = new URLSearchParams(params).toString();
        const data = `${timestamp}${this.apiKey}${this.recvWindow}${queryString ? queryString : ''}`;
        const signature = crypto.createHmac('sha256', this.apiSecret).update(data).digest('hex');
        return signature;
    }

    async _request(method, endpoint, params = {}, is_signed = true) {
        let retries = 0;
        while (retries < MAX_API_RETRIES) {
            try {
                const timestamp = await this.getTimestamp();
                const headers = {
                    'X-BAPI-API-KEY': this.apiKey,
                    'X-BAPI-TIMESTAMP': String(timestamp),
                    'X-BAPI-RECV-WINDOW': this.recvWindow,
                    'Content-Type': 'application/json'
                };

                if (is_signed) {
                    headers['X-BAPI-SIGN'] = this.sign(endpoint, method, params);
                }

                let url = `${this.baseUrl}${endpoint}`;
                let options = {
                    method: method,
                    headers: headers,
                    timeout: REQUEST_TIMEOUT
                };

                if (method === 'GET') {
                    const queryParams = new URLSearchParams(params).toString();
                    url = `${url}?${queryParams}`;
                } else {
                    options.body = JSON.stringify(params);
                }

                const response = await fetch(url, options);
                const data = await response.json();

                if (data.retCode === 0) {
                    return data.result;
                } else {
                    this.logger.warn(`API Error: ${data.retCode} - ${data.retMsg}`);
                    if (data.retCode === 10001) { // Unified account error
                        throw new Error('Account type error: Unified account required.');
                    }
                    if (data.retCode === 30037) { // Rate limit error
                        this.logger.warn(`Rate limit hit. Retrying in ${RETRY_DELAY_SECONDS} seconds...`);
                        await setTimeout(RETRY_DELAY_SECONDS * 1000);
                        retries++;
                        continue;
                    }
                    throw new Error(`API Error: ${data.retMsg}`);
                }
            } catch (error) {
                this.logger.error(`Request failed (${method} ${endpoint}): ${error.message}`);
                if (retries < MAX_API_RETRIES - 1) {
                    this.logger.warn(`Retrying in ${RETRY_DELAY_SECONDS} seconds... (${retries + 1}/${MAX_API_RETRIES})`);
                    await setTimeout(RETRY_DELAY_SECONDS * 1000);
                    retries++;
                } else {
                    throw error;
                }
            }
        }
        throw new Error('Max retries reached for API request.');
    }

    async fetch_klines(symbol, interval, limit = 1000) {
        try {
            const klines = await this._request('GET', '/v5/market/kline', {
                symbol: symbol,
                interval: interval,
                limit: limit
            });
            if (!klines || !klines.list || klines.list.length === 0) {
                this.logger.warn(`No kline data received for ${symbol}`);
                return null;
            }
            const formatted_klines = klines.list.map(k => ({
                timestamp: new Date(parseInt(k[0])),
                open: new Decimal(k[1]),
                high: new Decimal(k[2]),
                low: new Decimal(k[3]),
                close: new Decimal(k[4]),
                volume: new Decimal(k[5]),
                turnover: new Decimal(k[6])
            }));
            return formatted_klines;
        } catch (error) {
            this.logger.error(`Error fetching klines: ${error.message}`);
            return null;
        }
    }

    async get_account_info() {
        try {
            return await this._request('GET', '/v5/account/wallet-balance', {
                accountType: 'UNIFIED'
            });
        } catch (error) {
            this.logger.error(`Error fetching account info: ${error.message}`);
            throw error;
        }
    }

    async get_symbol_info(symbol) {
        try {
            const data = await this._request('GET', '/v5/market/symbol', {
                symbol: symbol
            });
            if (data && data.list && data.list.length > 0) {
                const symbolInfo = data.list[0];
                return {
                    symbol: symbolInfo.symbol,
                    price_precision: parseInt(symbolInfo.priceScale),
                    qty_precision: parseInt(symbolInfo.volumeScale)
                };
            }
            return null;
        } catch (error) {
            this.logger.error(`Error fetching symbol info for ${symbol}: ${error.message}`);
            return null;
        }
    }

    async create_order(symbol, side, orderType, qty, price = null, stopLoss = null, takeProfit = null) {
        const params = {
            symbol: symbol,
            side: side,
            orderType: orderType,
            qty: qty.toString(),
            timeInForce: 'GTC', // Good Till Cancelled
            accountType: 'UNIFIED'
        };
        if (orderType === 'Limit') {
            params.price = price.toString();
        }
        if (stopLoss) {
            params.stopLoss = stopLoss.toString();
        }
        if (takeProfit) {
            params.takeProfit = takeProfit.toString();
        }

        try {
            this.logger.info(`Creating ${orderType} order: ${side} ${qty} ${symbol} ${price ? `@ ${price}` : ''}`);
            const order = await this._request('POST', '/v5/order/create', params);
            this.logger.info(`Order created successfully: ${JSON.stringify(order)}`);
            return order;
        } catch (error) {
            this.logger.error(`Failed to create order: ${error.message}`);
            throw error;
        }
    }

    async cancel_order(symbol, orderId) {
        try {
            this.logger.info(`Cancelling order ${orderId} for ${symbol}`);
            await this._request('POST', '/v5/order/cancel', {
                symbol: symbol,
                orderId: orderId,
                accountType: 'UNIFIED'
            });
            this.logger.info(`Order ${orderId} cancelled successfully.`);
        } catch (error) {
            this.logger.error(`Failed to cancel order ${orderId}: ${error.message}`);
            throw error;
        }
    }
}

// --- PositionManager (with Martingale) ---
class PositionManager {
    constructor(config, logger, symbol, bybitClient) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.bybitClient = bybitClient;
        this.open_positions = {}; // { position_id: { entry_price, qty, side, status, ... } }
        this.active_orders = {}; // { order_id: { ... } }
        this.martingale_level = 0;
        this.load_state();
    }

    load_state() {
        // In a real application, you'd load this from a file or database
        this.logger.info('Loading position manager state (stubbed).');
    }

    save_state() {
        // In a real application, you'd save this to a file or database
        this.logger.info('Saving position manager state (stubbed).');
    }

    async manage_positions(current_price, performanceTracker) {
        // Check for open positions and update their status
        // For simplicity, we'll assume positions are managed externally or via order updates
        // In a real scenario, you'd fetch open positions from Bybit API
        
        // Example: If a position is open, check if SL/TP was hit (this logic would be more complex)
        // For now, we just ensure we don't open too many positions
        if (Object.keys(this.open_positions).length >= this.config.trade_management.max_open_positions) {
            // logger.debug('Max open positions reached.');
        }
    }

    async open_position(signal, current_price, atr_value, conviction) {
        if (!this.config.trade_management.enabled) {
            this.logger.debug('Trade management is disabled.');
            return;
        }

        if (Object.keys(this.open_positions).length >= this.config.trade_management.max_open_positions) {
            this.logger.debug('Max open positions reached, cannot open new position.');
            return;
        }

        const symbol_info = await this.bybitClient.get_symbol_info(this.symbol);
        if (!symbol_info) {
            this.logger.error(`Could not get symbol info for ${this.symbol}. Cannot open position.`);
            return;
        }

        const price_precision = symbol_info.price_precision;
        const qty_precision = symbol_info.qty_precision;

        let side = signal;
        let order_type = 'Market';
        let qty_step = new Decimal(10).pow(-qty_precision);
        let price_step = new Decimal(10).pow(-price_precision);

        let base_qty = new Decimal(this.config.trade_management.account_balance)
            .times(this.config.trade_management.risk_per_trade_percent / 100)
            .div(current_price);

        if (this.config.martingale.enabled) {
            this.martingale_level = Math.min(this.martingale_level, this.config.martingale.max_levels);
            base_qty = base_qty.times(Math.pow(this.config.martingale.multiplier, this.martingale_level));
        }

        let qty = round_qty(base_qty, qty_step);

        if (qty.isZero() || qty.isNaN()) {
            this.logger.warn(`Calculated quantity is zero or NaN. Cannot open position.`);
            return;
        }

        let stop_loss_price = null;
        let take_profit_price = null;

        if (signal === 'BUY') {
            stop_loss_price = round_price(current_price.minus(atr_value.times(this.config.trade_management.stop_loss_atr_multiple)), price_precision);
            take_profit_price = round_price(current_price.plus(atr_value.times(this.config.trade_management.take_profit_atr_multiple)), price_precision);
        } else { // SELL
            stop_loss_price = round_price(current_price.plus(atr_value.times(this.config.trade_management.stop_loss_atr_multiple)), price_precision);
            take_profit_price = round_price(current_price.minus(atr_value.times(this.config.trade_management.take_profit_atr_multiple)), price_precision);
        }

        try {
            const order = await this.bybitClient.create_order(
                this.symbol,
                side,
                order_type,
                qty,
                null, // Market orders don't need a price
                stop_loss_price,
                take_profit_price
            );
            
            // Add to open positions (simplified)
            const position_id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
            this.open_positions[position_id] = {
                id: position_id,
                entry_price: current_price,
                qty: qty,
                side: side,
                status: 'OPEN',
                order_id: order.orderId
            };
            this.logger.info(`Opened ${side} position: ${qty} @ ${current_price}. SL: ${stop_loss_price}, TP: ${take_profit_price}`);
            
            if (this.config.martingale.enabled && signal === side) { // If it's a winning trade for this side, reset martingale level
                this.martingale_level = 0;
            } else if (this.config.martingale.enabled && signal !== side) { // If it's a losing trade, increase martingale level
                this.martingale_level++;
            }

            this.save_state();
        } catch (error) {
            this.logger.error(`Failed to open position: ${error.message}`);
            // If order creation failed, do not increment martingale level
        }
    }
}

// --- PerformanceTracker (as in wb4.0.js) ---
class PerformanceTracker { /* ... */ }

// --- AlertSystem (as in wb4.0.js) ---
class AlertSystem { /* ... */ }

// --- TradingAnalyzer (as in wb4.0.js) ---
class TradingAnalyzer {
    constructor(klines, config, logger, symbol) {
        this.klines = klines;
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.calculate_indicators();
    }

    calculate_indicators() {
        if (!this.klines || this.klines.length < 14) { // Need at least 14 periods for StochRSI
            this.logger.warn('Not enough kline data to calculate indicators.');
            return;
        }

        const closes = this.klines.map(k => k.close);
        const highs = this.klines.map(k => k.high);
        const lows = this.klines.map(k => k.low);

        // --- Pivot Points ---
        const last_pivot_kline = this.klines[this.klines.length - 1];
        const prev_pivot_kline = this.klines[this.klines.length - 2];

        const pivot_high = prev_pivot_kline.high;
        const pivot_low = prev_pivot_kline.low;
        const pivot_close = prev_pivot_kline.close;

        const pivot_point = (pivot_high.plus(pivot_low).plus(pivot_close)).div(3);
        const r1 = pivot_point.times(2).minus(pivot_low);
        const s1 = pivot_point.times(2).minus(pivot_high);
        const r2 = pivot_point.plus(pivot_high.minus(pivot_low));
        const s2 = pivot_point.minus(pivot_high.minus(pivot_low));
        const r3 = pivot_point.plus(pivot_high.minus(pivot_low).times(2));
        const s3 = pivot_point.minus(pivot_high.minus(pivot_low).times(2));

        this.indicator_values.pivot = {
            pp: pivot_point,
            r1: r1, s1: s1, r2: r2, s2: s2, r3: r3, s3: s3
        };

        // --- StochRSI ---
        const rsi_period = 14;
        const stoch_k_period = 3;
        const stoch_d_period = 3;

        const rsi_values = this.calculate_rsi(closes, rsi_period);
        const stoch_rsi_values = this.calculate_stoch_rsi(rsi_values, rsi_period);

        this.indicator_values.stoch_rsi = stoch_rsi_values;

        // --- ATR ---
        const atr_period = 14;
        this.indicator_values.ATR = this.calculate_atr(highs, lows, closes, atr_period);
    }

    calculate_rsi(closes, period) {
        const rsi_values = [];
        let gains = [];
        let losses = [];

        for (let i = 1; i < closes.length; i++) {
            const change = closes[i].minus(closes[i - 1]);
            if (change.gt(0)) {
                gains.push(change);
                losses.push(new Decimal(0));
            } else {
                gains.push(new Decimal(0));
                losses.push(change.abs());
            }
        }

        for (let i = period; i < gains.length; i++) {
            const avg_gain = gains.slice(i - period + 1, i + 1).reduce((sum, val) => sum.plus(val), new Decimal(0)).div(period);
            const avg_loss = losses.slice(i - period + 1, i + 1).reduce((sum, val) => sum.plus(val), new Decimal(0)).div(period);
            
            let rs = new Decimal(0);
            if (!avg_loss.isZero()) {
                rs = avg_loss.isZero() ? new Decimal(0) : avg_gain.div(avg_loss);
            }

            const rsi = new Decimal(100).minus(new Decimal(100).div(new Decimal(1).plus(rs)));
            rsi_values.push(rsi);
        }
        return rsi_values;
    }

    calculate_stoch_rsi(rsi_values, period) {
        const stoch_rsi_results = [];
        for (let i = period - 1; i < rsi_values.length; i++) {
            const rsi_slice = rsi_values.slice(i - period + 1, i + 1);
            const max_rsi = Decimal.max(...rsi_slice);
            const min_rsi = Decimal.min(...rsi_slice);
            const current_rsi = rsi_values[i];

            let stoch_rsi = new Decimal(0);
            if (max_rsi.minus(min_rsi).gt(0)) {
                stoch_rsi = current_rsi.minus(min_rsi).div(max_rsi.minus(min_rsi)).times(100);
            }
            stoch_rsi_results.push(stoch_rsi);
        }
        return stoch_rsi_results;
    }

    calculate_atr(highs, lows, closes, period) {
        const tr_values = [];
        for (let i = 1; i < highs.length; i++) {
            const h_minus_l = highs[i].minus(lows[i]);
            const h_minus_prev_c = highs[i].minus(closes[i - 1].abs());
            const l_minus_prev_c = lows[i].minus(closes[i - 1].abs());
            tr_values.push(Decimal.max(h_minus_l, h_minus_prev_c, l_minus_prev_c));
        }

        let atr = tr_values.slice(0, period).reduce((sum, val) => sum.plus(val), new Decimal(0)).div(period);
        const smoothed_tr = [atr];

        for (let i = period; i < tr_values.length; i++) {
            const next_atr = tr_values[i].minus(atr).div(period).plus(atr);
            smoothed_tr.push(next_atr);
            atr = next_atr;
        }
        return atr;
    }

    _get_indicator_value(indicator_name, default_value) {
        if (this.indicator_values[indicator_name]) {
            if (Array.isArray(this.indicator_values[indicator_name])) {
                return this.indicator_values[indicator_name][this.indicator_values[indicator_name].length - 1];
            } else {
                return this.indicator_values[indicator_name];
            }
        }
        return default_value;
    }

    generate_trading_signal(latest_orderbook) {
        if (!this.klines || this.klines.length < 20) { // Need enough data for indicators
            return ['HOLD', 0, {}];
        }

        const last_kline = this.klines[this.klines.length - 1];
        const prev_kline = this.klines[this.klines.length - 2];
        const prev_prev_kline = this.klines[this.klines.length - 3];

        const current_price = last_kline.close;
        const atr = this._get_indicator_value('ATR', new Decimal('0.01'));

        // --- Pivot Point Analysis ---
        const pivots = this.indicator_values.pivot;
        let pivot_signal = 'HOLD';
        if (current_price.gt(pivots.r1)) pivot_signal = 'BUY';
        if (current_price.lt(pivots.s1)) pivot_signal = 'SELL';

        // --- StochRSI Analysis ---
        const stoch_rsi_values = this.indicator_values.stoch_rsi;
        let stoch_rsi_signal = 'HOLD';
        if (stoch_rsi_values && stoch_rsi_values.length > 0) {
            const last_stoch_rsi = stoch_rsi_values[stoch_rsi_values.length - 1];
            const prev_stoch_rsi = stoch_rsi_values.length > 1 ? stoch_rsi_values[stoch_rsi_values.length - 2] : last_stoch_rsi;

            if (last_stoch_rsi < 20 && prev_stoch_rsi < last_stoch_rsi) {
                stoch_rsi_signal = 'BUY';
            } else if (last_stoch_rsi > 80 && prev_stoch_rsi > last_stoch_rsi) {
                stoch_rsi_signal = 'SELL';
            }
        }

        // --- Combine Signals ---
        let final_signal = 'HOLD';
        let signal_score = 0;
        const signal_breakdown = {};

        const signals = { pivot: pivot_signal, stoch_rsi: stoch_rsi_signal };
        let buy_count = 0;
        let sell_count = 0;

        for (const [indicator, signal] of Object.entries(signals)) {
            signal_breakdown[indicator] = signal;
            if (signal === 'BUY') {
                buy_count++;
            } else if (signal === 'SELL') {
                sell_count++;
            }
        }

        if (buy_count >= 2) {
            final_signal = 'BUY';
            signal_score = buy_count;
        } else if (sell_count >= 2) {
            final_signal = 'SELL';
            signal_score = -sell_count;
        }

        return [final_signal, signal_score, signal_breakdown];
    }
}

// --- Main Execution Logic ---
async function main() {
    const logger = setup_logger("wgwhalex_bot");
    const configManager = new ConfigManager(CONFIG_FILE, logger);
    const config = configManager.config;
    const dashboard = new Dashboard(config, logger);
    dashboard.start();

    const bybitClient = new BybitClient(API_KEY, API_SECRET, BASE_URL, logger);
    const wsClient = new WebSocketClient(WEBSOCKET_URL, logger);
    wsClient.connect();

    const positionManager = new PositionManager(config, logger, config.symbol, bybitClient);
    const performanceTracker = new PerformanceTracker(logger, config);

    let latest_orderbook = null;
    wsClient.subscribe([`orderbook.50.${config.symbol}`], (data) => {
        const bids = data.b || [];
        const asks = data.a || [];
        if (bids.length > 0 && asks.length > 0) {
            const bidVolume = bids.slice(0, 10).reduce((sum, b) => sum + parseFloat(b[1]), 0);
            const askVolume = asks.slice(0, 10).reduce((sum, a) => sum + parseFloat(a[1]), 0);
            const totalVolume = bidVolume + askVolume;
            latest_orderbook = {
                imbalance: totalVolume > 0 ? (bidVolume - askVolume) / totalVolume : 0,
                liquidity_score: totalVolume > 0 ? Math.min(1, totalVolume / 100) : 0
            };
        }
    });

    while (true) {
        const loop_start_time = Date.now();
        try {
            const df_raw = await bybitClient.fetch_klines(config.symbol, config.interval, 1000);
            if (!df_raw) {
                await setTimeout(config.loop_delay * 1000);
                continue;
            }

            const analyzer = new TradingAnalyzer(df_raw, config, logger, config.symbol);
            const [trading_signal, signal_score, signal_breakdown] = analyzer.generate_trading_signal(latest_orderbook);
            const current_price = new Decimal(df_raw[df_raw.length - 1].close);
            const atr_value = analyzer._get_indicator_value("ATR", new Decimal("0.01"));

            positionManager.manage_positions(current_price, performanceTracker);

            if (trading_signal !== "HOLD") {
                const conviction = Math.min(1.0, Math.abs(signal_score) / (config.signal_score_threshold * 2));
                await positionManager.open_position(trading_signal, current_price, atr_value, conviction);
            }

            // Dashboard Update
            dashboard.update({
                marketData: { [config.symbol]: { price: current_price.toString() } },
                performance: performanceTracker.get_summary(),
                signal: { signal: trading_signal, score: signal_score },
                indicators: analyzer.indicator_values,
                positions: positionManager.open_positions,
                trade_history: performanceTracker.trades.slice(-20)
            });

        } catch (e) {
            logger.error(`Main loop error: ${e.message}`);
        }
        const elapsed_time = Date.now() - loop_start_time;
        const remaining_delay = (config.loop_delay * 1000) - elapsed_time;
        if (remaining_delay > 0) {
            await setTimeout(remaining_delay);
        }
    }
}

if (require.main === module) {
    main();
}