// unified_whalebot.js — Enhanced Whale Trading Bot for Bybit Unified Account

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
const { execSync } = require('child_process');

// Initialize Decimal.js precision
Decimal.set({ precision: 32, rounding: Decimal.ROUND_HALF_UP });
dotenv.config();

// --- Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs/trading-bot/logs";
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });

const TIMEZONE = "UTC";
const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000;
const LOOP_DELAY_SECONDS = 15;

// Magic Numbers as Constants
const ADX_STRONG_TREND_THRESHOLD = 25;
const ADX_WEAK_TREND_THRESHOLD = 20;
const STOCH_RSI_MID_POINT = 50;
const MIN_CANDLESTICK_PATTERNS_BARS = 2;
const MIN_DATA_POINTS_TR = 2;
const MIN_DATA_POINTS_SMOOTHER_INIT = 2;
const MIN_DATA_POINTS_OBV = 2;
const MIN_DATA_POINTS_PSAR = 2;

// Utility Functions
/**
 * Rounds quantity to exchange step size
 * @param {Decimal} qty
 * @param {Decimal} step
 * @returns {Decimal}
 */
function round_qty(qty, step) {
    if (step.lte(0)) return qty;
    return qty.dividedToIntegerBy(step).times(step);
}

/**
 * Rounds price to specified decimal precision
 * @param {Decimal} price
 * @param {number} precision
 * @returns {Decimal}
 */
function round_price(price, precision) {
    if (precision < 0) precision = 0;
    const factor = new Decimal(10).pow(precision);
    return Decimal.floor(price.times(factor)).dividedBy(factor);
}

/**
 * Clamps value between min and max
 * @param {number} val
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
function np_clip(val, min, max) {
    return Math.min(Math.max(val, min), max);
}

// --- Configuration Management ---
class ConfigManager {
    constructor(filepath, logger) {
        this.filepath = filepath;
        this.logger = logger;
        this.config = {};
        this.load_config();
    }

    load_config() {
        const default_config = {
            "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS,
            "orderbook_limit": 50, "signal_score_threshold": 2.0, "cooldown_sec": 60,
            "hysteresis_ratio": 0.85, "volume_confirmation_multiplier": 1.5,
            "trade_management": {
                "enabled": true, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
                "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
                "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
                "slippage_percent": 0.001, "trading_fee_percent": 0.0005,
            },
            "risk_guardrails": {
                "enabled": true, "max_day_loss_pct": 3.0, "max_drawdown_pct": 8.0,
                "cooldown_after_kill_min": 120, "spread_filter_bps": 5.0, "ev_filter_enabled": true,
            },
            "session_filter": {
                "enabled": false, "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
            },
            "pyramiding": {
                "enabled": false, "max_adds": 2, "step_atr": 0.7, "size_pct_of_initial": 0.5,
            },
            "mtf_analysis": {
                "enabled": true, "higher_timeframes": ["60", "240"],
                "trend_indicators": ["ema", "ehlers_supertrend"], "trend_period": 50,
                "mtf_request_delay_seconds": 0.5,
            },
            "ml_enhancement": {"enabled": false},
            "indicator_settings": {
                "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
                "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
                "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
                "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02,
                "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50,
                "fibonacci_window": 60, "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0,
                "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0, "macd_fast_period": 12,
                "macd_slow_period": 26, "macd_signal_period": 9, "adx_period": 14,
                "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26,
                "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26,
                "obv_ema_period": 20, "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70,
                "stoch_rsi_oversold": 20, "stoch_rsi_overbought": 80, "cci_oversold": -100,
                "cci_overbought": 100, "williams_r_oversold": -80, "williams_r_overbought": -20,
                "mfi_oversold": 20, "mfi_overbought": 80, "volatility_index_period": 20,
                "vwma_period": 20, "volume_delta_period": 5, "volume_delta_threshold": 0.2,
                "kama_period": 10, "kama_fast_period": 2, "kama_slow_period": 30,
                "relative_volume_period": 20, "relative_volume_threshold": 1.5,
                "market_structure_lookback_period": 20, "dema_period": 14,
                "keltner_period": 20, "keltner_atr_multiplier": 2.0, "roc_period": 12,
                "roc_oversold": -5.0, "roc_overbought": 5.0,
            },
            "indicators": {
                "ema_alignment": true, "sma_trend_filter": true, "momentum": true,
                "volume_confirmation": true, "stoch_rsi": true, "rsi": true, "bollinger_bands": true,
                "vwap": true, "cci": true, "wr": true, "psar": true, "sma_10": true, "mfi": true,
                "orderbook_imbalance": true, "fibonacci_levels": true, "ehlers_supertrend": true,
                "macd": true, "adx": true, "ichimoku_cloud": true, "obv": true, "cmf": true,
                "volatility_index": true, "vwma": true, "volume_delta": true,
                "kaufman_ama": true, "relative_volume": true, "market_structure": true,
                "dema": true, "keltner_channels": true, "roc": true, "candlestick_patterns": true,
                "fibonacci_pivot_points": true,
            },
            "weight_sets": {
                "default_scalping": {
                    "ema_alignment": 0.30, "sma_trend_filter": 0.20, "ehlers_supertrend_alignment": 0.40,
                    "macd_alignment": 0.30, "adx_strength": 0.25, "ichimoku_confluence": 0.35,
                    "psar": 0.15, "vwap": 0.15, "vwma_cross": 0.10, "sma_10": 0.05,
                    "bollinger_bands": 0.25, "momentum_rsi_stoch_cci_wr_mfi": 0.35,
                    "volume_confirmation": 0.10, "obv_momentum": 0.15, "cmf_flow": 0.10,
                    "volume_delta_signal": 0.10, "orderbook_imbalance": 0.10,
                    "mtf_trend_confluence": 0.25, "volatility_index_signal": 0.10,
                    "kaufman_ama_cross": 0.20, "relative_volume_confirmation": 0.10,
                    "market_structure_confluence": 0.25, "dema_crossover": 0.18,
                    "keltner_breakout": 0.20, "roc_signal": 0.12, "candlestick_confirmation": 0.15,
                    "fibonacci_pivot_points_confluence": 0.20,
                }
            },
            "execution": {
                "use_pybit": false, "testnet": false, "account_type": "UNIFIED", "category": "linear",
                "position_mode": "ONE_WAY", "tpsl_mode": "Full", "buy_leverage": "3",
                "sell_leverage": "3", "tp_trigger_by": "LastPrice", "sl_trigger_by": "LastPrice",
                "default_time_in_force": "GTC", "reduce_only_default": false,
                "post_only_default": false,
                "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
                "proxies": { "enabled": false, "http": "", "https": "" },
                "tp_scheme": {
                    "mode": "atr_multiples",
                    "targets": [
                        {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.40, "order_type": "Limit", "tif": "PostOnly", "post_only": true},
                        {"name": "TP2", "atr_multiple": 1.5, "size_pct": 0.40, "order_type": "Limit", "tif": "IOC", "post_only": false},
                        {"name": "TP3", "atr_multiple": 2.0, "size_pct": 0.20, "order_type": "Limit", "tif": "GTC", "post_only": false},
                    ],
                },
                "sl_scheme": {
                    "type": "atr_multiple", "atr_multiple": 1.5, "percent": 1.0,
                    "use_conditional_stop": true, "stop_order_type": "Market",
                },
                "breakeven_after_tp1": {
                    "enabled": true, "offset_type": "atr", "offset_value": 0.10,
                    "lock_in_min_percent": 0, "sl_trigger_by": "LastPrice",
                },
                "live_sync": {
                    "enabled": true, "poll_ms": 2500, "max_exec_fetch": 200,
                    "only_track_linked": true, "heartbeat": {"enabled": true, "interval_ms": 5000},
                },
            },
        };

        if (!fs.existsSync(this.filepath)) {
            try {
                fs.writeFileSync(this.filepath, JSON.stringify(default_config, null, 4), 'utf-8');
                this.logger.warn(`${chalk.yellow("Configuration file not found. Created default config at ")}${this.filepath}${chalk.reset()}`);
                this.config = default_config;
            } catch (e) {
                this.logger.error(`${chalk.red("Error creating default config file: ")}${e}${chalk.reset()}`);
                this.config = default_config;
            }
        } else {
            try {
                let current_config = JSON.parse(fs.readFileSync(this.filepath, 'utf-8'));
                this.config = _.mergeWith({}, default_config, current_config, (objValue, srcValue, key) => {
                    const decimalKeys = [
                        "risk_per_trade_percent", "stop_loss_atr_multiple", "take_profit_atr_multiple",
                        "slippage_percent", "trading_fee_percent", "account_balance",
                        "max_day_loss_pct", "max_drawdown_pct"
                    ];
                    if (decimalKeys.includes(key) && typeof srcValue === 'number') {
                        return new Decimal(srcValue);
                    }
                    if (_.isArray(objValue) && _.isArray(srcValue)) {
                        return srcValue;
                    }
                    return undefined;
                });
                fs.writeFileSync(this.filepath, JSON.stringify(this.config, null, 4), 'utf-8');
                this.logger.info(`${chalk.green("Configuration loaded and updated at ")}${this.filepath}${chalk.reset()}`);
            } catch (e) {
                this.logger.error(`${chalk.red("Error loading config: ")}${e}. Using default.${chalk.reset()}`);
                this.config = default_config;
            }
        }
    }
}

// --- Logging Setup ---
const sensitivePrintf = (template, sensitiveWords) => {
    const escapeRegExp = (string) => string.replace(/[.*+?^${}()|[```\```/g, '\\$&');
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

const logger = setup_logger("wgwhalex_bot");

// --- API Interaction ---
class BybitClient {
    constructor(api_key, api_secret, base_url, logger) {
        this.api_key = api_key;
        this.api_secret = api_secret;
        this.base_url = base_url;
        this.logger = logger;
    }

    _generate_signature(payload) {
        return crypto.createHmac('sha256', this.api_secret).update(payload).digest('hex');
    }

    async _send_signed_request(method, endpoint, params) {
        if (!this.api_key || !this.api_secret) {
            this.logger.error(`${chalk.red("API_KEY or API_SECRET not set for signed request.")}`);
            return null;
        }

        const timestamp = String(Date.now());
        const recv_window = "20000";
        const headers = {"Content-Type": "application/json"};
        const url = `${this.base_url}${endpoint}`;

        let param_str;
        if (method === "GET") {
            const query_string = params ? new URLSearchParams(params).toString() : "";
            param_str = timestamp + this.api_key + recv_window + query_string;
            headers["X-BAPI-API-KEY"] = this.api_key;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = this._generate_signature(param_str);
            headers["X-BAPI-RECV-WINDOW"] = recv_window;
            this.logger.debug(`GET Request: ${url}?${query_string}`);
            return fetch(`${url}?${query_string}`, { method: "GET", headers, timeout: REQUEST_TIMEOUT });
        } else {
            const json_params = params ? JSON.stringify(params) : "";
            param_str = timestamp + this.api_key + recv_window + json_params;
            headers["X-BAPI-API-KEY"] = this.api_key;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = this._generate_signature(param_str);
            headers["X-BAPI-RECV-WINDOW"] = recv_window;
            this.logger.debug(`POST Request: ${url} with payload ${json_params}`);
            return fetch(url, { method: "POST", headers, body: json_params, timeout: REQUEST_TIMEOUT });
        }
    }

    async _handle_api_response(response) {
        try {
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP Error: ${response.status} - ${errorText}`);
            }
            const data = await response.json();
            if (data.retCode !== 0) {
                this.logger.error(`${chalk.red("Bybit API Error: ")}${data.retMsg} (Code: ${data.retCode})${chalk.reset()}`);
                return null;
            }
            return data;
        } catch (e) {
            this.logger.error(`${chalk.red("API Response Error: ")}${e.message}${chalk.reset()}`);
            return null;
        }
    }

    async bybit_request(method, endpoint, params = null, signed = false) {
        for (let attempt = 0; attempt < MAX_API_RETRIES; attempt++) {
            try {
                let response;
                if (signed) {
                    response = await this._send_signed_request(method, endpoint, params);
                } else {
                    const url = `${this.base_url}${endpoint}`;
                    const query_string = params ? new URLSearchParams(params).toString() : "";
                    this.logger.debug(`Public Request: ${url}?${query_string}`);
                    response = await fetch(`${url}?${query_string}`, { method: "GET", timeout: REQUEST_TIMEOUT });
                }

                if (response) {
                    const data = await this._handle_api_response(response);
                    if (data !== null) return data;
                }
            } catch (e) {
                this.logger.error(`${chalk.red("Request Attempt ")}${attempt + 1}/${MAX_API_RETRIES} failed: ${e.message}${chalk.reset()}`);
            }
            await setTimeout(RETRY_DELAY_SECONDS * 1000 * Math.pow(2, attempt)); // Exponential backoff
        }
        return null;
    }

    async fetch_current_price(symbol) {
        const endpoint = "/v5/market/tickers";
        const params = {"category": "linear", "symbol": symbol};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result && response.result.list) {
            const price = new Decimal(response.result.list[0].lastPrice);
            this.logger.debug(`Fetched current price for ${symbol}: ${price}`);
            return price;
        }
        this.logger.warning(`${chalk.yellow("Could not fetch current price for ")}${symbol}${chalk.reset()}`);
        return null;
    }

    async fetch_klines(symbol, interval, limit) {
        const endpoint = "/v5/market/kline";
        const params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result && response.result.list) {
            const df_data = response.result.list.map(k => ({
                start_time: new Date(parseInt(k[0])),
                open: new Decimal(k[1]), high: new Decimal(k[2]), low: new Decimal(k[3]),
                close: new Decimal(k[4]), volume: new Decimal(k[5]), turnover: new Decimal(k[6])
            })).sort((a, b) => a.start_time.getTime() - b.start_time.getTime());

            this.logger.debug(`Fetched ${df_data.length} ${interval} klines for ${symbol}.`);
            return df_data;
        }
        this.logger.warning(`${chalk.yellow("Could not fetch klines for ")}${symbol} ${interval}${chalk.reset()}`);
        return null;
    }

    async fetch_orderbook(symbol, limit) {
        const endpoint = "/v5/market/orderbook";
        const params = {"category": "linear", "symbol": symbol, "limit": limit};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result) {
            this.logger.debug(`Fetched orderbook for ${symbol} with limit ${limit}.`);
            return response.result;
        }
        this.logger.warning(`${chalk.yellow("Could not fetch orderbook for ")}${symbol}${chalk.reset()}`);
        return null;
    }

    async get_wallet_balance(coin = "USDT") {
        const endpoint = "/v5/account/wallet-balance";
        const params = {"accountType": "UNIFIED", "coin": coin};
        const response = await this.bybit_request("GET", endpoint, params, true);
        if (response && response.result && response.result.list && response.result.list.length > 0) {
            const coin_info = response.result.list[0].coin.find(c => c.coin === coin);
            if (coin_info) return new Decimal(coin_info.walletBalance);
        }
        this.logger.warning(`${chalk.yellow("Could not fetch wallet balance for ")}${coin}${chalk.reset()}`);
        return new Decimal(0);
    }

    async set_leverage(symbol, buy_leverage, sell_leverage) {
        const endpoint = "/v5/position/set-leverage";
        const params = {"category": "linear", "symbol": symbol, "buyLeverage": String(buy_leverage), "sellLeverage": String(sell_leverage)};
        const response = await this.bybit_request("POST", endpoint, params, true);
        return response !== null;
    }

    async place_order(symbol, side, orderType, qty, price = null, stopLoss = null, takeProfit = null, isLeverage = 1, timeInForce = "GTC") {
        const endpoint = "/v5/order/create";
        const params = {
            category: "linear", symbol, side, orderType,
            qty: qty.toString(), isLeverage, timeInForce
        };
        if (price !== null) params.price = price.toString();
        if (stopLoss !== null) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = "MarkPrice"; }
        if (takeProfit !== null) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = "MarkPrice"; }

        const response = await this.bybit_request("POST", endpoint, params, true);
        if (response && response.result) {
            this.logger.info(`${chalk.green("Order placed: ")}${side} ${qty.toString()} ${symbol} SL: ${stopLoss ? stopLoss.toString() : 'N/A'}, TP: ${takeProfit ? takeProfit.toString() : 'N/A'}${chalk.reset()}`);
            return response.result;
        }
        return null;
    }
}

// --- Position Management ---
class PositionManager {
    constructor(config, logger, symbol, pybit_client) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.open_positions = [];
        this.trade_management_enabled = config.trade_management.enabled;
        this.max_open_positions = config.trade_management.max_open_positions;
        this.order_precision = config.trade_management.order_precision;
        this.price_precision = config.trade_management.price_precision;
        this.slippage_percent = new Decimal(config.trade_management.slippage_percent);
        this.pybit = pybit_client;
        this.qty_step = new Decimal("0.000001");
        this._update_precision_from_exchange();
    }

    async _update_precision_from_exchange() {
        const info = await this.pybit.bybit_request("GET", "/v5/market/instruments-info", {category: "linear", symbol: this.symbol});
        if (info && info.result && info.result.list && info.result.list.length > 0) {
            const instrument = info.result.list[0];
            if (instrument.lotSizeFilter) {
                this.qty_step = new Decimal(instrument.lotSizeFilter.qtyStep);
                this.order_precision = this.qty_step.precision();
            }
            if (instrument.priceFilter) {
                this.price_precision = new Decimal(instrument.priceFilter.tickSize).precision();
            }
            this.logger.info(`${chalk.blue("Updated precision: qty_step=")}${this.qty_step}, order_precision=${this.order_precision}, price_precision=${this.price_precision}${chalk.reset()}`);
        }
    }

    _get_current_balance() {
        return new Decimal(this.config.trade_management.account_balance);
    }

    _calculate_order_size(current_price, atr_value, conviction = 1.0) {
        if (!this.trade_management_enabled) return new Decimal("0");
        const account_balance = this._get_current_balance();
        const base_risk_pct = new Decimal(this.config.trade_management.risk_per_trade_percent).dividedBy(100);
        const risk_multiplier = new Decimal(np_clip(0.5 + conviction, 0.5, 1.5));
        const risk_pct = base_risk_pct.times(risk_multiplier);
        const stop_loss_atr_multiple = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const risk_amount = account_balance.times(risk_pct);
        const stop_loss_distance = atr_value.times(stop_loss_atr_multiple);

        if (stop_loss_distance.lte(0)) {
            this.logger.warning(`${chalk.yellow("Stop loss distance invalid. Cannot calculate order size.")}${chalk.reset()}`);
            return new Decimal("0");
        }

        const order_value = risk_amount.dividedBy(stop_loss_distance);
        let order_qty = order_value.dividedBy(current_price);
        return round_qty(order_qty, this.qty_step);
    }

    _compute_stop_loss_price(side, entry_price, atr_value) {
        const sl_cfg = this.config.execution.sl_scheme;
        let sl;
        if (sl_cfg.type === "atr_multiple") {
            const sl_mult = new Decimal(sl_cfg.atr_multiple);
            sl = (side === "BUY") ? entry_price.minus(atr_value.times(sl_mult)) : entry_price.plus(atr_value.times(sl_mult));
        } else {
            const sl_pct = new Decimal(sl_cfg.percent).dividedBy(100);
            sl = (side === "BUY") ? entry_price.times(new Decimal(1).minus(sl_pct)) : entry_price.times(new Decimal(1).plus(sl_pct));
        }
        return round_price(sl, this.price_precision);
    }

    _calculate_take_profit_price(signal, current_price, atr_value) {
        const tp_mult = new Decimal(this.config.trade_management.take_profit_atr_multiple);
        const tp = (signal === "BUY") ? current_price.plus(atr_value.times(tp_mult)) : current_price.minus(atr_value.times(tp_mult));
        return round_price(tp, this.price_precision);
    }

    async open_position(signal, current_price, atr_value, conviction) {
        if (!this.trade_management_enabled || this.open_positions.length >= this.max_open_positions) {
            this.logger.info(`${chalk.yellow("Max positions reached or trade management disabled.")}${chalk.reset()}`);
            return null;
        }

        const order_qty = this._calculate_order_size(current_price, atr_value, conviction);
        if (order_qty.lte(0)) {
            this.logger.warning(`${chalk.yellow("Order quantity zero. Skipping position.")}${chalk.reset()}`);
            return null;
        }

        const stop_loss = this._compute_stop_loss_price(signal, current_price, atr_value);
        const take_profit = this._calculate_take_profit_price(signal, current_price, atr_value);

        let adjusted_entry_price_sim = current_price;
        if (signal === "BUY") {
            adjusted_entry_price_sim = current_price.times(new Decimal(1).plus(this.slippage_percent));
        } else {
            adjusted_entry_price_sim = current_price.times(new Decimal(1).minus(this.slippage_percent));
        }

        const position = {
            "entry_time": new Date(), "symbol": this.symbol, "side": signal,
            "entry_price": round_price(adjusted_entry_price_sim, this.price_precision), "qty": order_qty,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "status": "OPEN", "link_prefix": `wgx_${Date.now()}`, "adds": 0,
            "order_id": null, "stop_loss_order_id": null, "take_profit_order_ids": [],
            "best_price": adjusted_entry_price_sim
        };

        if (this.config.execution.use_pybit && this.pybit) {
            try {
                const resp = await this.pybit.place_order(
                    this.symbol, signal, "Market", order_qty, null, stop_loss, take_profit
                );
                if (resp && resp.orderId) {
                    position.order_id = resp.orderId;
                    this.logger.info(`${chalk.green("Live order placed: ")}${JSON.stringify(position)}${chalk.reset()}`);
                }
            } catch (e) {
                this.logger.error(`${chalk.red("Live order failed: ")}${e.message}. Simulating.${chalk.reset()}`);
            }
        }

        this.open_positions.push(position);
        this.logger.info(`${chalk.green("Opened position: ")}${JSON.stringify(position)}${chalk.reset()}`);
        return position;
    }

    _check_and_close_position(position, current_price) {
        const side = position.side;
        const stop_loss = position.stop_loss;
        const take_profit = position.take_profit;

        let closed_by = null;
        let close_price = new Decimal("0");

        if (side === "BUY") {
            if (current_price.lte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).minus(this.slippage_percent));
            } else if (current_price.gte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).minus(this.slippage_percent));
            }
        } else {
            if (current_price.gte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).plus(this.slippage_percent));
            } else if (current_price.lte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).plus(this.slippage_percent));
            }
        }

        if (closed_by) {
            const adjusted_close_price = round_price(close_price, this.price_precision);
            return { is_closed: true, adjusted_close_price, closed_by };
        }
        return { is_closed: false, adjusted_close_price: new Decimal("0"), closed_by: "" };
    }

    manage_positions(current_price, performance_tracker) {
        if (!this.trade_management_enabled) return;

        const positions_to_remove = [];
        for (let i = 0; i < this.open_positions.length; i++) {
            const pos = this.open_positions[i];
            if (pos.status !== "OPEN") continue;

            const result = this._check_and_close_position(pos, current_price);
            if (result.is_closed) {
                pos.status = "CLOSED";
                pos.exit_time = new Date();
                pos.exit_price = result.adjusted_close_price;
                pos.closed_by = result.closed_by;

                const pnl = pos.side === "BUY"
                    ? (pos.exit_price.minus(pos.entry_price)).times(pos.qty)
                    : (pos.entry_price.minus(pos.exit_price)).times(pos.qty);

                performance_tracker.record_trade(pos, pnl);
                this.logger.info(`${chalk.purple("Closed position: ")}${JSON.stringify(pos)}. PnL: ${pnl.toFixed(4)}${chalk.reset()}`);

                positions_to_remove.push(i);

                if (this.config.execution.use_pybit && this.pybit) {
                    this.pybit.bybit_request("POST", "/v5/order/cancel-all", {
                        category: "linear", symbol: this.symbol, orderLinkId: pos.link_prefix
                    }, true);
                }
            } else {
                this.trail_stop(pos, current_price, this._get_indicator_value("ATR"));
            }
        }

        // Remove closed positions
        for (let i = positions_to_remove.length - 1; i >= 0; i--) {
            this.open_positions.splice(positions_to_remove[i], 1);
        }
    }

    trail_stop(pos, current_price, atr_value) {
        if (!atr_value || !pos.best_price) return;
        const atr_mult = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const side = pos.side;

        if (side === "BUY") {
            pos.best_price = Decimal.max(pos.best_price, current_price);
            const new_sl = pos.best_price.minus(atr_mult.times(atr_value));
            if (new_sl.gt(pos.stop_loss)) {
                pos.stop_loss = round_price(new_sl, this.price_precision);
                this.logger.debug(`${chalk.blue("Trailing BUY SL to ")}${pos.stop_loss}${chalk.reset()}`);
            }
        } else {
            pos.best_price = Decimal.min(pos.best_price, current_price);
            const new_sl = pos.best_price.plus(atr_mult.times(atr_value));
            if (new_sl.lt(pos.stop_loss)) {
                pos.stop_loss = round_price(new_sl, this.price_precision);
                this.logger.debug(`${chalk.blue("Trailing SELL SL to ")}${pos.stop_loss}${chalk.reset()}`);
            }
        }
    }

    async try_pyramid(current_price, atr_value) {
        if (!this.config.pyramiding.enabled) return;

        for (const pos of this.open_positions) {
            if (pos.status !== "OPEN" || pos.adds >= this.config.pyramiding.max_adds) continue;

            const step_atr_mult = new Decimal(this.config.pyramiding.step_atr);
            const step_distance = step_atr_mult.times(atr_value).times(new Decimal(pos.adds + 1));

            let target_price;
            if (pos.side === "BUY") {
                target_price = pos.entry_price.plus(step_distance);
                if (current_price.lt(target_price)) continue;
            } else {
                target_price = pos.entry_price.minus(step_distance);
                if (current_price.gt(target_price)) continue;
            }

            const add_qty = round_qty(pos.qty.times(this.config.pyramiding.size_pct_of_initial), this.qty_step);
            if (add_qty.lte(0)) continue;

            const total_cost = pos.entry_price.times(pos.qty).plus(current_price.times(add_qty));
            pos.qty = pos.qty.plus(add_qty);
            pos.entry_price = total_cost.dividedBy(pos.qty);
            pos.adds++;

            this.logger.info(`${chalk.green("Pyramided: Added ")}${add_qty} at ${current_price}. New avg: ${pos.entry_price.toFixed(this.price_precision)}${chalk.reset()}`);

            if (this.config.execution.use_pybit && this.pybit) {
                try {
                    await this.pybit.place_order(this.symbol, pos.side, "Market", add_qty, null, pos.stop_loss, pos.take_profit);
                } catch (e) {
                    this.logger.error(`${chalk.red("Pyramid order failed: ")}${e.message}${chalk.reset()}`);
                }
            }
        }
    }

    _get_indicator_value(key) {
        // Stub — should be passed from analyzer or fetched live
        return new Decimal(NaN);
    }
}

// --- Performance Tracking ---
class PerformanceTracker {
    constructor(logger, config) {
        this.logger = logger;
        this.config = config;
        this.trades = [];
        this.total_pnl = new Decimal("0");
        this.gross_profit = new Decimal("0");
        this.gross_loss = new Decimal("0");
        this.wins = 0;
        this.losses = 0;
        this.peak_pnl = new Decimal("0");
        this.max_drawdown = new Decimal("0");
        this.trading_fee_percent = new Decimal(config.trade_management.trading_fee_percent);
    }

    record_trade(position, pnl) {
        const entry_fee = position.entry_price.times(position.qty).times(this.trading_fee_percent);
        const exit_fee = position.exit_price.times(position.qty).times(this.trading_fee_percent);
        const total_fees = entry_fee.plus(exit_fee);
        const pnl_net = pnl.minus(total_fees);

        const trade = {
            ...position,
            fees: total_fees,
            pnl_gross: pnl,
            pnl_net: pnl_net
        };

        this.trades.push(trade);
        this.total_pnl = this.total_pnl.plus(pnl_net);

        if (pnl_net.gt(0)) {
            this.wins++;
            this.gross_profit = this.gross_profit.plus(pnl_net);
        } else {
            this.losses++;
            this.gross_loss = this.gross_loss.plus(pnl_net.abs());
        }

        if (this.total_pnl.gt(this.peak_pnl)) this.peak_pnl = this.total_pnl;
        const drawdown = this.peak_pnl.minus(this.total_pnl);
        if (drawdown.gt(this.max_drawdown)) this.max_drawdown = drawdown;

        this.logger.info(
            `${chalk.cyan("Trade recorded | Net PnL: ")}${pnl_net.toFixed(4)} | Total: ${this.total_pnl.toFixed(4)}${chalk.reset()}`
        );
    }

    day_pnl() {
        const today = new Date().toISOString().slice(0, 10);
        return this.trades
            .filter(t => t.exit_time?.toISOString().slice(0, 10) === today)
            .reduce((sum, t) => sum.plus(t.pnl_net || new Decimal(0)), new Decimal(0));
    }

    get_summary() {
        const total_trades = this.trades.length;
        const win_rate = total_trades > 0 ? (this.wins / total_trades) * 100 : 0;
        const profit_factor = this.gross_loss.gt(0) ? this.gross_profit.dividedBy(this.gross_loss) : new Decimal("Infinity");
        const avg_win = this.wins > 0 ? this.gross_profit.dividedBy(this.wins) : new Decimal("0");
        const avg_loss = this.losses > 0 ? this.gross_loss.dividedBy(this.losses) : new Decimal("0");

        return {
            total_trades,
            total_pnl: this.total_pnl,
            gross_profit: this.gross_profit,
            gross_loss: this.gross_loss,
            profit_factor,
            max_drawdown: this.max_drawdown,
            wins: this.wins,
            losses: this.losses,
            win_rate: `${win_rate.toFixed(2)}%`,
            avg_win,
            avg_loss
        };
    }
}

// --- Alert System ---
class AlertSystem {
    constructor(logger) {
        this.logger = logger;
        this.termux_api_available = this._check_termux_api();
    }

    _check_termux_api() {
        try {
            execSync('which termux-toast', { stdio: 'pipe' });
            return true;
        } catch (e) {
            this.logger.warn(`${chalk.yellow("Termux toast notifications disabled (command not found).")}${chalk.reset()}`);
            return false;
        }
    }

    send_alert(message, level = "INFO") {
        const colorMap = {
            INFO: chalk.blue,
            WARNING: chalk.yellow,
            ERROR: chalk.red
        };
        const prefixMap = {
            INFO: "ℹ️ ",
            WARNING: "⚠️ ",
            ERROR: "⛔ "
        };

        const color = colorMap[level] || chalk.white;
        const prefix = prefixMap[level] || "";
        this.logger.log(level.toLowerCase(), `${prefix}${message}`);

        if (this.termux_api_available) {
            try {
                execSync(`termux-toast "${prefix}${message}"`, { timeout: 5000 });
            } catch (e) {
                this.logger.error(`${chalk.red("Termux toast failed: ")}${e.message}${chalk.reset()}`);
            }
        }
    }
}

// --- Trading Analysis ---
class TradingAnalyzer {
    constructor(df_raw, config, logger, symbol) {
        this.df = this._process_dataframe(df_raw);
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.fib_levels = {};
        this.weights = config.weight_sets.default_scalping;
        this.indicator_settings = config.indicator_settings;

        if (this.df.length === 0) {
            this.logger.warning(`${chalk.yellow("Empty DataFrame. Skipping indicators.")}${chalk.reset()}`);
            return;
        }

        this._calculate_all_indicators();
        if (config.indicators.fibonacci_levels) this.calculate_fibonacci_levels();
        if (config.indicators.fibonacci_pivot_points) this.calculate_fibonacci_pivot_points();
    }

    _process_dataframe(df_raw) {
        const processed = {
            start_time: [], open: [], high: [], low: [], close: [], volume: [], turnover: []
        };
        df_raw.forEach(row => {
            processed.start_time.push(row.start_time);
            processed.open.push(new Decimal(row.open));
            processed.high.push(new Decimal(row.high));
            processed.low.push(new Decimal(row.low));
            processed.close.push(new Decimal(row.close));
            processed.volume.push(new Decimal(row.volume));
            processed.turnover.push(new Decimal(row.turnover));
        });

        const df_like = { ...processed, length: processed.close.length };
        df_like.iloc = (index) => {
            if (index < 0) index += df_like.length;
            const row = {};
            for (const key in df_like) {
                if (Array.isArray(df_like[key])) row[key] = df_like[key][index];
            }
            return row;
        };
        return df_like;
    }

    _safe_calculate(func, name, min_data_points, ...args) {
        if (this.df.length < min_data_points) {
            this.logger.debug(`${chalk.blue(`Skipping ${name}: Insufficient data (${this.df.length} < ${min_data_points})`)}`);
            return null;
        }
        try {
            const result = func(this.df, this.indicator_settings, this.logger, this.symbol, ...args);
            if (result === null || (Array.isArray(result) && result.length === 0)) {
                this.logger.warning(`${chalk.yellow(`${name} returned empty result.`)}${chalk.reset()}`);
            }
            return result;
        } catch (e) {
            this.logger.error(`${chalk.red(`Error calculating ${name}: ${e.message}`)}${chalk.reset()}`);
            return null;
        }
    }

    _calculate_all_indicators() {
        const cfg = this.config.indicators;
        const isd = this.indicator_settings;

        // Load indicator functions dynamically (you must create indicators.js)
        const indicators = require('./indicators');

        if (cfg.sma_10) {
            const sma = this._safe_calculate(indicators.calculate_sma, "SMA_10", isd.sma_short_period, isd.sma_short_period);
            if (sma) this.indicator_values["SMA_10"] = sma[sma.length - 1];
        }

        if (cfg.sma_trend_filter) {
            const sma = this._safe_calculate(indicators.calculate_sma, "SMA_Long", isd.sma_long_period, isd.sma_long_period);
            if (sma) this.indicator_values["SMA_Long"] = sma[sma.length - 1];
        }

        if (cfg.ema_alignment) {
            const ema_short = this._safe_calculate(indicators.calculate_ema, "EMA_Short", isd.ema_short_period, isd.ema_short_period);
            const ema_long = this._safe_calculate(indicators.calculate_ema, "EMA_Long", isd.ema_long_period, isd.ema_long_period);
            if (ema_short) this.indicator_values["EMA_Short"] = ema_short[ema_short.length - 1];
            if (ema_long) this.indicator_values["EMA_Long"] = ema_long[ema_long.length - 1];
        }

        if (cfg.atr) {
            const atr = this._safe_calculate(indicators.calculate_atr, "ATR", isd.atr_period, isd.atr_period);
            if (atr) this.indicator_values["ATR"] = atr[atr.length - 1];
        }

        if (cfg.rsi) {
            const rsi = this._safe_calculate(indicators.calculate_rsi, "RSI", isd.rsi_period + 1, isd.rsi_period);
            if (rsi) this.indicator_values["RSI"] = rsi[rsi.length - 1];
        }

        if (cfg.stoch_rsi) {
            const stoch = this._safe_calculate(indicators.calculate_stoch_rsi, "StochRSI", 
                isd.stoch_rsi_period + isd.stoch_k_period + isd.stoch_d_period,
                isd.stoch_rsi_period, isd.stoch_k_period, isd.stoch_d_period);
            if (stoch) {
                this.indicator_values["StochRSI_K"] = stoch.k[stoch.k.length - 1];
                this.indicator_values["StochRSI_D"] = stoch.d[stoch.d.length - 1];
            }
        }

        if (cfg.bollinger_bands) {
            const bb = this._safe_calculate(indicators.calculate_bollinger_bands, "BollingerBands", 
                isd.bollinger_bands_period, isd.bollinger_bands_period, isd.bollinger_bands_std_dev);
            if (bb) {
                this.indicator_values["BB_Upper"] = bb.upper[bb.upper.length - 1];
                this.indicator_values["BB_Middle"] = bb.middle[bb.middle.length - 1];
                this.indicator_values["BB_Lower"] = bb.lower[bb.lower.length - 1];
            }
        }

        if (cfg.cci) {
            const cci = this._safe_calculate(indicators.calculate_cci, "CCI", isd.cci_period, isd.cci_period);
            if (cci) this.indicator_values["CCI"] = cci[cci.length - 1];
        }

        if (cfg.wr) {
            const wr = this._safe_calculate(indicators.calculate_williams_r, "WR", isd.williams_r_period, isd.williams_r_period);
            if (wr) this.indicator_values["WR"] = wr[wr.length - 1];
        }

        if (cfg.mfi) {
            const mfi = this._safe_calculate(indicators.calculate_mfi, "MFI", isd.mfi_period + 1, isd.mfi_period);
            if (mfi) this.indicator_values["MFI"] = mfi[mfi.length - 1];
        }

        if (cfg.obv) {
            const obv = this._safe_calculate(indicators.calculate_obv, "OBV", isd.obv_ema_period, isd.obv_ema_period);
            if (obv) {
                this.indicator_values["OBV"] = obv.obv[obv.obv.length - 1];
                this.indicator_values["OBV_EMA"] = obv.obv_ema[obv.obv_ema.length - 1];
            }
        }

        if (cfg.cmf) {
            const cmf = this._safe_calculate(indicators.calculate_cmf, "CMF", isd.cmf_period, isd.cmf_period);
            if (cmf) this.indicator_values["CMF"] = cmf[cmf.length - 1];
        }

        if (cfg.ichimoku_cloud) {
            const ichi = this._safe_calculate(indicators.calculate_ichimoku_cloud, "IchimokuCloud",
                Math.max(isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period) + isd.ichimoku_chikou_span_offset,
                isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period, isd.ichimoku_chikou_span_offset);
            if (ichi) {
                this.indicator_values["Tenkan_Sen"] = ichi.tenkan_sen[ichi.tenkan_sen.length - 1];
                this.indicator_values["Kijun_Sen"] = ichi.kijun_sen[ichi.kijun_sen.length - 1];
                this.indicator_values["Senkou_Span_A"] = ichi.senkou_span_a[ichi.senkou_span_a.length - 1];
                this.indicator_values["Senkou_Span_B"] = ichi.senkou_span_b[ichi.senkou_span_b.length - 1];
                this.indicator_values["Chikou_Span"] = ichi.chikou_span[ichi.chikou_span.length - 1];
            }
        }

        if (cfg.psar) {
            const psar = this._safe_calculate(indicators.calculate_psar, "PSAR", MIN_DATA_POINTS_PSAR,
                isd.psar_acceleration, isd.psar_max_acceleration);
            if (psar) {
                this.indicator_values["PSAR_Val"] = psar.psar[psar.psar.length - 1];
                this.indicator_values["PSAR_Dir"] = psar.direction[psar.direction.length - 1];
            }
        }

        if (cfg.vwap) {
            const vwap = this._safe_calculate(indicators.calculate_vwap, "VWAP", 1);
            if (vwap) this.indicator_values["VWAP"] = vwap[vwap.length - 1];
        }

        if (cfg.ehlers_supertrend) {
            const st_fast = this._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast",
                isd.ehlers_fast_period * 3, isd.ehlers_fast_period, isd.ehlers_fast_multiplier);
            const st_slow = this._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow",
                isd.ehlers_slow_period * 3, isd.ehlers_slow_period, isd.ehlers_slow_multiplier);
            if (st_fast) {
                this.indicator_values["ST_Fast_Dir"] = st_fast.direction[st_fast.direction.length - 1];
                this.indicator_values["ST_Fast_Val"] = st_fast.supertrend[st_fast.supertrend.length - 1];
            }
            if (st_slow) {
                this.indicator_values["ST_Slow_Dir"] = st_slow.direction[st_slow.direction.length - 1];
                this.indicator_values["ST_Slow_Val"] = st_slow.supertrend[st_slow.supertrend.length - 1];
            }
        }

        if (cfg.macd) {
            const macd = this._safe_calculate(indicators.calculate_macd, "MACD",
                isd.macd_slow_period + isd.macd_signal_period,
                isd.macd_fast_period, isd.macd_slow_period, isd.macd_signal_period);
            if (macd) {
                this.indicator_values["MACD_Line"] = macd.macd_line[macd.macd_line.length - 1];
                this.indicator_values["MACD_Signal"] = macd.signal_line[macd.signal_line.length - 1];
                this.indicator_values["MACD_Hist"] = macd.histogram[macd.histogram.length - 1];
            }
        }

        if (cfg.adx) {
            const adx = this._safe_calculate(indicators.calculate_adx, "ADX", isd.adx_period * 2, isd.adx_period);
            if (adx) {
                this.indicator_values["ADX"] = adx.adx[adx.adx.length - 1];
                this.indicator_values["PlusDI"] = adx.plus_di[adx.plus_di.length - 1];
                this.indicator_values["MinusDI"] = adx.minus_di[adx.minus_di.length - 1];
            }
        }

        if (cfg.volatility_index) {
            const vi = this._safe_calculate(indicators.calculate_volatility_index, "Volatility_Index", isd.volatility_index_period, isd.volatility_index_period);
            if (vi) this.indicator_values["Volatility_Index"] = vi[vi.length - 1];
        }

        if (cfg.vwma) {
            const vwma = this._safe_calculate(indicators.calculate_vwma, "VWMA", isd.vwma_period, isd.vwma_period);
            if (vwma) this.indicator_values["VWMA"] = vwma[vwma.length - 1];
        }

        if (cfg.volume_delta) {
            const vd = this._safe_calculate(indicators.calculate_volume_delta, "Volume_Delta", isd.volume_delta_period, isd.volume_delta_period);
            if (vd) this.indicator_values["Volume_Delta"] = vd[vd.length - 1];
        }

        if (cfg.kaufman_ama) {
            const kama = this._safe_calculate(indicators.calculate_kaufman_ama, "Kaufman_AMA",
                isd.kama_period + isd.kama_slow_period, isd.kama_period, isd.kama_fast_period, isd.kama_slow_period);
            if (kama) this.indicator_values["Kaufman_AMA"] = kama[kama.length - 1];
        }

        if (cfg.relative_volume) {
            const rv = this._safe_calculate(indicators.calculate_relative_volume, "Relative_Volume", isd.relative_volume_period, isd.relative_volume_period);
            if (rv) this.indicator_values["Relative_Volume"] = rv[rv.length - 1];
        }

        if (cfg.market_structure) {
            const ms = this._safe_calculate(indicators.calculate_market_structure, "Market_Structure",
                isd.market_structure_lookback_period * 2, isd.market_structure_lookback_period);
            if (ms) this.indicator_values["Market_Structure_Trend"] = ms[ms.length - 1];
        }

        if (cfg.dema) {
            const dema = this._safe_calculate(indicators.calculate_dema, "DEMA", isd.dema_period * 2, this.df.close, isd.dema_period);
            if (dema) this.indicator_values["DEMA"] = dema[dema.length - 1];
        }

        if (cfg.keltner_channels) {
            const kc = this._safe_calculate(indicators.calculate_keltner_channels, "KeltnerChannels",
                isd.keltner_period + isd.atr_period, isd.keltner_period, isd.keltner_atr_multiplier, isd.atr_period);
            if (kc) {
                this.indicator_values["Keltner_Upper"] = kc.upper[kc.upper.length - 1];
                this.indicator_values["Keltner_Middle"] = kc.middle[kc.middle.length - 1];
                this.indicator_values["Keltner_Lower"] = kc.lower[kc.lower.length - 1];
            }
        }

        if (cfg.roc) {
            const roc = this._safe_calculate(indicators.calculate_roc, "ROC", isd.roc_period + 1, isd.roc_period);
            if (roc) this.indicator_values["ROC"] = roc[roc.length - 1];
        }

        if (cfg.candlestick_patterns) {
            const patterns = this._safe_calculate(indicators.detect_candlestick_patterns, "Candlestick_Patterns", MIN_CANDLESTICK_PATTERNS_BARS);
            if (patterns) this.indicator_values["Candlestick_Pattern"] = patterns[patterns.length - 1];
        }

        // Clean NaNs
        for (const key in this.indicator_values) {
            const val = this.indicator_values[key];
            if (val instanceof Decimal && val.isNaN()) {
                this.indicator_values[key] = new Decimal(NaN);
            }
        }

        this.logger.debug(`${chalk.blue("Indicators calculated for ")}${this.symbol}${chalk.reset()}`);
    }

    calculate_fibonacci_levels() {
        const fib = require('./indicators').calculate_fibonacci_levels(this.df, this.config.indicator_settings.fibonacci_window);
        if (fib) this.fib_levels = fib;
    }

    calculate_fibonacci_pivot_points() {
        if (this.df.length < 2) return;
        const pivot = require('./indicators').calculate_fibonacci_pivot_points(this.df);
        if (pivot) {
            const pp = this.config.trade_management.price_precision;
            this.indicator_values["Pivot"] = pivot.pivot.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["R1"] = pivot.r1.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["R2"] = pivot.r2.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["S1"] = pivot.s1.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["S2"] = pivot.s2.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
        }
    }

    _get_indicator_value(key, def = new Decimal(NaN)) {
        const val = this.indicator_values[key];
        return (val instanceof Decimal && !val.isNaN()) ? val : def;
    }

    _check_orderbook(ob) {
        if (!ob?.b || !ob?.a) return 0;
        const bidVol = ob.b.reduce((sum, b) => sum.plus(new Decimal(b[1])), new Decimal(0));
        const askVol = ob.a.reduce((sum, a) => sum.plus(new Decimal(a[1])), new Decimal(0));
        if (bidVol.plus(askVol).isZero()) return 0;
        return bidVol.minus(askVol).dividedBy(bidVol.plus(askVol)).toNumber();
    }

    calculate_support_resistance_from_orderbook(ob) {
        if (!ob?.b || !ob?.a) return;
        let maxBid = new Decimal(0), support = new Decimal(0);
        for (const [p, v] of ob.b) {
            const vol = new Decimal(v);
            if (vol.gt(maxBid)) { maxBid = vol; support = new Decimal(p); }
        }
        let maxAsk = new Decimal(0), resistance = new Decimal(0);
        for (const [p, v] of ob.a) {
            const vol = new Decimal(v);
            if (vol.gt(maxAsk)) { maxAsk = vol; resistance = new Decimal(p); }
        }
        const pp = this.config.trade_management.price_precision;
        if (support.gt(0)) this.indicator_values["Support_Level"] = support.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
        if (resistance.gt(0)) this.indicator_values["Resistance_Level"] = resistance.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
    }

    _get_mtf_trend(higher_tf_df_raw, indicator_type) {
        if (!higher_tf_df_raw || higher_tf_df_raw.length === 0) return "UNKNOWN";
        const df = this._process_dataframe(higher_tf_df_raw);
        const last = df.close[df.close.length - 1];
        const period = this.config.mtf_analysis.trend_period;
        const ind = require('./indicators');

        if (indicator_type === "sma" && df.length >= period) {
            const sma = ind.calculate_sma(df, period)[df.length - 1];
            return last.gt(sma) ? "UP" : last.lt(sma) ? "DOWN" : "SIDEWAYS";
        }

        if (indicator_type === "ema" && df.length >= period) {
            const ema = ind.calculate_ema(df, period)[df.length - 1];
            return last.gt(ema) ? "UP" : last.lt(ema) ? "DOWN" : "SIDEWAYS";
        }

        if (indicator_type === "ehlers_supertrend") {
            const st = ind.calculate_ehlers_supertrend(df, this.indicator_settings.ehlers_slow_period, this.indicator_settings.ehlers_slow_multiplier);
            if (st && st.direction.length > 0) {
                const dir = st.direction[st.direction.length - 1];
                return dir === 1 ? "UP" : dir === -1 ? "DOWN" : "UNKNOWN";
            }
        }
        return "UNKNOWN";
    }

    // All scoring methods (_score_*) are implemented here — truncated for brevity in this response.
    // See previous assistant response for full implementations of _score_adx, _score_ema_alignment, etc.

    calculate_signal_score(orderbook_data = null, higher_tf_signals = {}) {
        if (this.df.length === 0) return { total_score: 0, signal: "NEUTRAL", conviction: 0, breakdown: {} };

        const current = this.df.close[this.df.close.length - 1];
        const prev = this.df.length > 1 ? this.df.close[this.df.close.length - 2] : current;

        let score = 0;
        let breakdown = {};
        let trendMult = 1.0;

        // ADX first
        const adx = this._score_adx(trendMult);
        score += adx.adx_contrib;
        trendMult = adx.trend_strength_multiplier_out;
        Object.assign(breakdown, adx.breakdown);

        // Then all others...
        const components = [
            this._score_ema_alignment(current, trendMult),
            this._score_sma_trend_filter(current),
            this._score_momentum_indicators(),
            this._score_bollinger_bands(current),
            this._score_vwap(current, prev),
            this._score_psar(current, prev),
            this._score_obv(),
            this._score_cmf(),
            this._score_volatility_index(),
            this._score_vwma_cross(current, prev),
            this._score_volume_delta(),
            this._score_kaufman_ama_cross(current, prev),
            this._score_relative_volume(),
            this._score_market_structure(),
            this._score_dema_crossover(current, prev),
            this._score_keltner_breakout(current, prev),
            this._score_roc(),
            this._score_candlestick_patterns(),
            this._score_fibonacci_levels(current, prev),
            this._score_fibonacci_pivot_points(current, prev),
            this._score_ehlers_supertrend(trendMult),
            this._score_macd(trendMult),
            this._score_ichimoku_cloud(current, trendMult),
            this._score_orderbook_imbalance(orderbook_data)
        ];

        for (const comp of components) {
            score += comp.contrib || 0;
            Object.assign(breakdown, comp.breakdown);
        }

        // MTF
        if (this.config.mtf_analysis.enabled && Object.keys(higher_tf_signals).length > 0) {
            let mtf = 0;
            const weight = this.weights.mtf_trend_confluence / Object.keys(higher_tf_signals).length;
            for (const tf in higher_tf_signals) {
                if (higher_tf_signals[tf] === "UP") mtf += weight;
                else if (higher_tf_signals[tf] === "DOWN") mtf -= weight;
            }
            score += mtf;
            breakdown["MTF Confluence"] = mtf;
        }

        const threshold = this.config.signal_score_threshold;
        const signal = score > threshold ? "BUY" : score < -threshold ? "SELL" : "NEUTRAL";
        const conviction = Math.abs(score);

        return { total_score: score, signal, conviction, breakdown };
    }

    // Include all _score_* methods here — omitted for space.
    // Full versions provided in prior assistant response.
    _score_adx(tm) { /* ... */ return { adx_contrib: 0, trend_strength_multiplier_out: tm, breakdown: {} }; }
    _score_ema_alignment() { return { ema_contrib: 0, breakdown: {} }; }
    _score_sma_trend_filter() { return { sma_contrib: 0, breakdown: {} }; }
    _score_momentum_indicators() { return { momentum_contrib: 0, breakdown: {} }; }
    _score_bollinger_bands() { return { bb_contrib: 0, breakdown: {} }; }
    _score_vwap() { return { vwap_contrib: 0, breakdown: {} }; }
    _score_psar() { return { psar_contrib: 0, breakdown: {} }; }
    _score_obv() { return { obv_contrib: 0, breakdown: {} }; }
    _score_cmf() { return { cmf_contrib: 0, breakdown: {} }; }
    _score_volatility_index() { return { vi_contrib: 0, breakdown: {} }; }
    _score_vwma_cross() { return { vwma_contrib: 0, breakdown: {} }; }
    _score_volume_delta() { return { vd_contrib: 0, breakdown: {} }; }
    _score_kaufman_ama_cross() { return { kama_contrib: 0, breakdown: {} }; }
    _score_relative_volume() { return { rv_contrib: 0, breakdown: {} }; }
    _score_market_structure() { return { ms_contrib: 0, breakdown: {} }; }
    _score_dema_crossover() { return { dema_contrib: 0, breakdown: {} }; }
    _score_keltner_breakout() { return { kc_contrib: 0, breakdown: {} }; }
    _score_roc() { return { roc_contrib: 0, breakdown: {} }; }
    _score_candlestick_patterns() { return { pattern_contrib: 0, breakdown: {} }; }
    _score_fibonacci_levels() { return { fib_contrib: 0, breakdown: {} }; }
    _score_fibonacci_pivot_points() { return { fib_pivot_contrib: 0, breakdown: {} }; }
    _score_ehlers_supertrend() { return { st_contrib: 0, breakdown: {} }; }
    _score_macd() { return { macd_contrib: 0, breakdown: {} }; }
    _score_ichimoku_cloud() { return { ichimoku_contrib: 0, breakdown: {} }; }
    _score_orderbook_imbalance() { return { imbalance_contrib: 0, breakdown: {} }; }
}

// --- Main Bot Loop ---
async function run_bot() {
    const configMgr = new ConfigManager(CONFIG_FILE, logger);
    const config = configMgr.config;
    const client = new BybitClient(API_KEY, API_SECRET, BASE_URL, logger);
    const positionMgr = new PositionManager(config, logger, config.symbol, client);
    const perfTracker = new PerformanceTracker(logger, config);
    const alertSystem = new AlertSystem(logger);

    logger.info(`${chalk.green("🚀 WhaleBot Started for ")}${config.symbol} @ ${config.interval}m interval${chalk.reset()}`);

    while (true) {
        try {
            const currentPrice = await client.fetch_current_price(config.symbol);
            if (!currentPrice) {
                await setTimeout(LOOP_DELAY_SECONDS * 1000);
                continue;
            }

            const candles = await client.fetch_klines(config.symbol, config.interval, 200);
            if (!candles) {
                await setTimeout(LOOP_DELAY_SECONDS * 1000);
                continue;
            }

            const orderbook = await client.fetch_orderbook(config.symbol, config.orderbook_limit);

            const analyzer = new TradingAnalyzer(candles, config, logger, config.symbol);
            const mtfSignals = {};

            if (config.mtf_analysis.enabled) {
                for (const tf of config.mtf_analysis.higher_timeframes) {
                    const tfCandles = await client.fetch_klines(config.symbol, tf, 100);
                    if (tfCandles) {
                        for (const ind of config.mtf_analysis.trend_indicators) {
                            mtfSignals[`${tf}_${ind}`] = analyzer._get_mtf_trend(tfCandles, ind);
                        }
                    }
                    await setTimeout(config.mtf_analysis.mtf_request_delay_seconds * 1000);
                }
            }

            const { total_score, signal, conviction, breakdown } = analyzer.calculate_signal_score(orderbook, mtfSignals);

            logger.info(`${chalk.cyan("[SIGNAL]")} Score: ${total_score.toFixed(2)} | Signal: ${signal} | Conviction: ${conviction.toFixed(2)}`);

            positionMgr.manage_positions(currentPrice, perfTracker);
            await positionMgr.try_pyramid(currentPrice, analyzer._get_indicator_value("ATR"));

            if (signal !== "NEUTRAL" && conviction > 0.5) {
                const atr = analyzer._get_indicator_value("ATR");
                if (!atr.isNaN() && atr.gt(0)) {
                    await positionMgr.open_position(signal, currentPrice, atr, conviction);
                }
            }

            const summary = perfTracker.get_summary();
            logger.info(`${chalk.magenta("[PERFORMANCE]")} PnL: ${summary.total_pnl.toFixed(2)} | Win Rate: ${summary.win_rate} | DD: ${summary.max_drawdown.toFixed(2)}`);

        } catch (e) {
            logger.error(`${chalk.red("Main loop error: ")}${e.message}${chalk.reset()}`);
            alertSystem.send_alert(`Main loop crashed: ${e.message}`, "ERROR");
        }

        await setTimeout(LOOP_DELAY_SECONDS * 1000);
    }
}

// Start Bot
if (require.main === module) {
    run_bot().catch(console.error);
}

module.exports = {
    ConfigManager,
    BybitClient,
    PositionManager,
    PerformanceTracker,
    AlertSystem,
    TradingAnalyzer,
    round_qty,
    round_price,
    np_clip
};
