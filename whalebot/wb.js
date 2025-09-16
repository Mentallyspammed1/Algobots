const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { URLSearchParams } = require('url');
const { setInterval } = require('timers/promises'); // For async sleep
const { Decimal } = require('decimal.js');
const { init: initColors, Fore, Style } = require('chalk'); // Using chalk for colors
const dotenv = require('dotenv');
const fetch = require('node-fetch');
const { createLogger, format, transports } = require('winston');
require('winston-daily-rotate-file'); // For log rotation

// Initialize colorama (chalk) and set decimal precision
Decimal.set({ precision: 28 }); // Equivalent to getcontext().prec = 28
initColors(); // Initialize chalk

dotenv.config();

// Neon Color Scheme (using chalk)
const NEON_GREEN = Fore.greenBright;
const NEON_BLUE = Fore.cyan;
const NEON_PURPLE = Fore.magentaBright;
const NEON_YELLOW = Fore.yellowBright;
const NEON_RED = Fore.redBright;
const NEON_CYAN = Fore.cyanBright;
const RESET = Style.reset;

// Indicator specific colors (enhanced for new indicators)
const INDICATOR_COLORS = {
    "SMA_10": Fore.blueBright,
    "SMA_Long": Fore.blue,
    "EMA_Short": Fore.magentaBright,
    "EMA_Long": Fore.magenta,
    "ATR": Fore.yellow,
    "RSI": Fore.green,
    "StochRSI_K": Fore.cyan,
    "StochRSI_D": Fore.cyanBright,
    "BB_Upper": Fore.red,
    "BB_Middle": Fore.white,
    "BB_Lower": Fore.red,
    "CCI": Fore.greenBright,
    "WR": Fore.redBright,
    "MFI": Fore.green,
    "OBV": Fore.blue,
    "OBV_EMA": Fore.blueBright,
    "CMF": Fore.magenta,
    "Tenkan_Sen": Fore.cyan,
    "Kijun_Sen": Fore.cyanBright,
    "Senkou_Span_A": Fore.green,
    "Senkou_Span_B": Fore.red,
    "Chikou_Span": Fore.yellow,
    "PSAR_Val": Fore.magenta,
    "PSAR_Dir": Fore.magentaBright,
    "VWAP": Fore.white,
    "ST_Fast_Dir": Fore.blue,
    "ST_Fast_Val": Fore.blueBright,
    "ST_Slow_Dir": Fore.magenta,
    "ST_Slow_Val": Fore.magentaBright,
    "MACD_Line": Fore.green,
    "MACD_Signal": Fore.greenBright,
    "MACD_Hist": Fore.yellow,
    "ADX": Fore.cyan,
    "PlusDI": Fore.cyanBright,
    "MinusDI": Fore.red,
    "Volatility_Index": Fore.yellow,
    "Volume_Delta": Fore.cyanBright,
    "VWMA": Fore.white,
};

// --- Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs/trading-bot/logs";
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });

// Using UTC for consistency and to avoid timezone issues with API timestamps
// In JS, Date objects are generally UTC internally, converting to ISO string gives UTC.
const TIMEZONE_OFFSET = 0; // Represents UTC.

const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000; // milliseconds
const LOOP_DELAY_SECONDS = 15;

// Magic Numbers as Constants (expanded)
const MIN_DATA_POINTS_TR = 2;
const MIN_DATA_POINTS_SMOOTHER = 2;
const MIN_DATA_POINTS_OBV = 2;
const MIN_DATA_POINTS_PSAR = 2;
const ADX_STRONG_TREND_THRESHOLD = 25;
const ADX_WEAK_TREND_THRESHOLD = 20;
const MIN_DATA_POINTS_VWMA = 2;
const MIN_DATA_POINTS_VOLATILITY = 2;

// --- Configuration Management ---
function loadConfig(filepath, logger) {
    const defaultConfig = {
        // Core Settings
        "symbol": "BTCUSDT",
        "interval": "15",
        "loop_delay": LOOP_DELAY_SECONDS,
        "orderbook_limit": 50,
        // Signal Generation
        "signal_score_threshold": 2.0,
        "volume_confirmation_multiplier": 1.5,
        // Position & Risk Management
        "trade_management": {
            "enabled": true,
            "account_balance": 1000.0,
            "risk_per_trade_percent": 1.0,
            "stop_loss_atr_multiple": 1.5,
            "take_profit_atr_multiple": 2.0,
            "max_open_positions": 1,
            "order_precision": 5,
            "price_precision": 3,
        },
        // Multi-Timeframe Analysis
        "mtf_analysis": {
            "enabled": true,
            "higher_timeframes": ["60", "240"],
            "trend_indicators": ["ema", "ehlers_supertrend"],
            "trend_period": 50,
            "mtf_request_delay_seconds": 0.5,
        },
        // Machine Learning Enhancement (Explicitly disabled)
        "ml_enhancement": {
            "enabled": false,
            "model_path": "ml_model.pkl",
            "retrain_on_startup": false,
            "training_data_limit": 5000,
            "prediction_lookahead": 12,
            "profit_target_percent": 0.5,
            "feature_lags": [1, 2, 3, 5],
            "cross_validation_folds": 5,
        },
        // Indicator Periods & Thresholds
        "indicator_settings": {
            "atr_period": 14,
            "ema_short_period": 9,
            "ema_long_period": 21,
            "rsi_period": 14,
            "stoch_rsi_period": 14,
            "stoch_k_period": 3,
            "stoch_d_period": 3,
            "bollinger_bands_period": 20,
            "bollinger_bands_std_dev": 2.0,
            "cci_period": 20,
            "williams_r_period": 14,
            "mfi_period": 14,
            "psar_acceleration": 0.02,
            "psar_max_acceleration": 0.2,
            "sma_short_period": 10,
            "sma_long_period": 50,
            "fibonacci_window": 60,
            "ehlers_fast_period": 10,
            "ehlers_fast_multiplier": 2.0,
            "ehlers_slow_period": 20,
            "ehlers_slow_multiplier": 3.0,
            "macd_fast_period": 12,
            "macd_slow_period": 26,
            "macd_signal_period": 9,
            "adx_period": 14,
            "ichimoku_tenkan_period": 9,
            "ichimoku_kijun_period": 26,
            "ichimoku_senkou_span_b_period": 52,
            "ichimoku_chikou_span_offset": 26,
            "obv_ema_period": 20,
            "cmf_period": 20,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "stoch_rsi_oversold": 20,
            "stoch_rsi_overbought": 80,
            "cci_oversold": -100,
            "cci_overbought": 100,
            "williams_r_oversold": -80,
            "williams_r_overbought": -20,
            "mfi_oversold": 20,
            "mfi_overbought": 80,
            "volatility_index_period": 20,
            "vwma_period": 20,
            "volume_delta_period": 5,
            "volume_delta_threshold": 0.2,
        },
        // Active Indicators & Weights (expanded)
        "indicators": {
            "ema_alignment": true,
            "sma_trend_filter": true,
            "momentum": true,
            "volume_confirmation": true,
            "stoch_rsi": true,
            "rsi": true,
            "bollinger_bands": true,
            "vwap": true,
            "cci": true,
            "wr": true,
            "psar": true,
            "sma_10": true,
            "mfi": true,
            "orderbook_imbalance": true,
            "fibonacci_levels": true,
            "ehlers_supertrend": true,
            "macd": true,
            "adx": true,
            "ichimoku_cloud": true,
            "obv": true,
            "cmf": true,
            "volatility_index": true,
            "vwma": true,
            "volume_delta": true,
        },
        "weight_sets": {
            "default_scalping": {
                "ema_alignment": 0.22,
                "sma_trend_filter": 0.28,
                "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                "volume_confirmation": 0.12,
                "bollinger_bands": 0.22,
                "vwap": 0.22,
                "psar": 0.22,
                "sma_10": 0.07,
                "orderbook_imbalance": 0.07,
                "ehlers_supertrend_alignment": 0.55,
                "macd_alignment": 0.28,
                "adx_strength": 0.18,
                "ichimoku_confluence": 0.38,
                "obv_momentum": 0.18,
                "cmf_flow": 0.12,
                "mtf_trend_confluence": 0.32,
                "volatility_index_signal": 0.15,
                "vwma_cross": 0.15,
                "volume_delta_signal": 0.10,
            }
        },
    };

    if (!fs.existsSync(filepath)) {
        try {
            fs.writeFileSync(filepath, JSON.stringify(defaultConfig, null, 4), 'utf-8');
            logger.warn(`${NEON_YELLOW}Configuration file not found. Created default config at ${filepath} for symbol ${defaultConfig.symbol}${RESET}`);
            return defaultConfig;
        } catch (e) {
            logger.error(`${NEON_RED}Error creating default config file: ${e.message}${RESET}`);
            return defaultConfig;
        }
    }

    try {
        let config = JSON.parse(fs.readFileSync(filepath, 'utf-8'));
        _ensureConfigKeys(config, defaultConfig);
        fs.writeFileSync(filepath, JSON.stringify(config, null, 4), 'utf-8');
        return config;
    } catch (e) {
        logger.error(`${NEON_RED}Error loading config: ${e.message}. Using default and attempting to save.${RESET}`);
        try {
            fs.writeFileSync(filepath, JSON.stringify(defaultConfig, null, 4), 'utf-8');
        } catch (e_save) {
            logger.error(`${NEON_RED}Could not save default config: ${e_save.message}${RESET}`);
        }
        return defaultConfig;
    }
}

function _ensureConfigKeys(config, defaultConfig) {
    for (const key in defaultConfig) {
        if (!config.hasOwnProperty(key)) {
            config[key] = defaultConfig[key];
        } else if (typeof defaultConfig[key] === 'object' && defaultConfig[key] !== null && !Array.isArray(defaultConfig[key])) {
            _ensureConfigKeys(config[key], defaultConfig[key]);
        }
    }
}

// --- Logging Setup ---
class SensitiveFormatter {
    constructor(colors = false) {
        this.colors = colors;
        this.sensitiveWords = ["API_KEY", "API_SECRET", API_KEY, API_SECRET].filter(Boolean); // Filter out undefined if API_KEY/SECRET are not set
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

function setupLogger(logName, level = 'info') {
    const logger = createLogger({
        level: level,
        format: format.combine(
            format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
            format(new SensitiveFormatter(false).format), // Apply redaction
            format.printf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`)
        ),
        transports: [
            new transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${logName}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '10m', // 10MB
                maxFiles: '5d' // Retain logs for 5 days
            })
        ],
        exitOnError: false // Do not exit on handled exceptions
    });

    // Console transport with colors
    if (!logger.transports.some(t => t instanceof transports.Console)) {
        logger.add(new transports.Console({
            format: format.combine(
                format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
                format(new SensitiveFormatter(true).format), // Apply redaction
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

// --- Async sleep utility ---
async function timeout(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// --- API Interaction ---
async function createSessionFetch(url, options, logger) {
    let retries = 0;
    while (retries < MAX_API_RETRIES) {
        try {
            const response = await fetch(url, { ...options, timeout: REQUEST_TIMEOUT });
            if (!response.ok) {
                if ([429, 500, 502, 503, 504].includes(response.status) && retries < MAX_API_RETRIES - 1) {
                    logger.warn(`Request failed with status ${response.status}. Retrying in ${RETRY_DELAY_SECONDS}s...`);
                    await timeout(RETRY_DELAY_SECONDS * 1000);
                    retries++;
                    continue;
                }
            }
            return response;
        } catch (error) {
            if (['AbortError', 'FetchError'].includes(error.name) && retries < MAX_API_RETRIES - 1) { // Timeout or network error
                logger.warn(`Request failed: ${error.message}. Retrying in ${RETRY_DELAY_SECONDS}s...`);
                await timeout(RETRY_DELAY_SECONDS * 1000);
                retries++;
                continue;
            }
            throw error; // Re-throw if unrecoverable or max retries reached
        }
    }
    throw new Error(`Max retries (${MAX_API_RETRIES}) exceeded for ${url}`);
}

function generateSignature(payload, apiSecret) {
    return crypto.createHmac('sha256', apiSecret).update(payload).digest('hex');
}

async function bybitRequest(method, endpoint, params = null, signed = false, logger = null) {
    if (logger === null) {
        logger = setupLogger("bybit_api");
    }
    const url = `${BASE_URL}${endpoint}`;
    const headers = { "Content-Type": "application/json" };
    let requestOptions = { method, headers };

    if (signed) {
        if (!API_KEY || !API_SECRET) {
            logger.error(`${NEON_RED}API_KEY or API_SECRET not set for signed request.${RESET}`);
            return null;
        }

        const timestamp = String(Date.now());
        const recvWindow = "20000";

        if (method === "GET") {
            const queryString = params ? new URLSearchParams(params).toString() : "";
            const paramStr = timestamp + API_KEY + recvWindow + queryString;
            const signature = generateSignature(paramStr, API_SECRET);
            headers["X-BAPI-API-KEY"] = API_KEY;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = signature;
            headers["X-BAPI-RECV-WINDOW"] = recvWindow;
            requestOptions.headers = headers;
            logger.debug(`GET Request: ${url}?${queryString}`);
            if (queryString) requestOptions.url = `${url}?${queryString}`;
            else requestOptions.url = url;
        } else { // POST
            const jsonParams = JSON.stringify(params);
            const paramStr = timestamp + API_KEY + recvWindow + jsonParams;
            const signature = generateSignature(paramStr, API_SECRET);
            headers["X-BAPI-API-KEY"] = API_KEY;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = signature;
            headers["X-BAPI-RECV-WINDOW"] = recvWindow;
            requestOptions.headers = headers;
            requestOptions.body = jsonParams;
            requestOptions.url = url;
            logger.debug(`POST Request: ${url} with payload ${jsonParams}`);
        }
    } else {
        requestOptions.url = params ? `${url}?${new URLSearchParams(params).toString()}` : url;
        logger.debug(`Public Request: ${requestOptions.url}`);
    }

    try {
        const response = await createSessionFetch(requestOptions.url, requestOptions, logger);
        const data = await response.json();
        if (data.retCode !== 0) {
            logger.error(`${NEON_RED}Bybit API Error: ${data.retMsg} (Code: ${data.retCode})${RESET}`);
            return null;
        }
        return data;
    } catch (e) {
        logger.error(`${NEON_RED}Request Exception: ${e.message}${RESET}`);
        return null;
    }
}

async function fetchCurrentPrice(symbol, logger) {
    const endpoint = "/v5/market/tickers";
    const params = { category: "linear", symbol: symbol };
    const response = await bybitRequest("GET", endpoint, params, false, logger);
    if (response && response.result && response.result.list && response.result.list.length > 0) {
        const price = new Decimal(response.result.list[0].lastPrice);
        logger.debug(`Fetched current price for ${symbol}: ${price}`);
        return price;
    }
    logger.warn(`${NEON_YELLOW}Could not fetch current price for ${symbol}.${RESET}`);
    return null;
}

// Minimal DataFrame structure for Klines
// For a full-fledged solution, a library like danfojs-node would be needed.
// This implementation uses plain arrays and objects to simulate a DataFrame for simplicity.
class KlineData {
    constructor(data = []) {
        this.data = data; // Array of kline objects: { start_time, open, high, low, close, volume, turnover }
    }

    get length() {
        return this.data.length;
    }

    get empty() {
        return this.data.length === 0;
    }

    get(index) {
        if (index < 0) index = this.data.length + index;
        return this.data[index];
    }

    // Returns a series (array) for a given column name
    column(colName) {
        return this.data.map(row => row[colName]);
    }

    // Simple rolling mean (no EWM, just basic mean)
    // For full EWM, a custom implementation or library is necessary.
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

    // Simple EWM calculation (adjust=false equivalent)
    ewmMean(colName, span, minPeriods = 0) {
        const series = this.column(colName).map(parseFloat);
        if (series.length < minPeriods) return new Array(series.length).fill(NaN);

        const alpha = 2 / (span + 1);
        const result = new Array(series.length).fill(NaN);

        let ema = 0;
        let windowSum = 0;
        let count = 0;

        for (let i = 0; i < series.length; i++) {
            const value = series[i];
            if (isNaN(value)) continue;

            if (count === 0) {
                ema = value;
            } else {
                ema = (value * alpha) + (ema * (1 - alpha));
            }
            
            windowSum += value;
            count++;

            if (count >= minPeriods) {
                result[i] = ema;
            }
        }
        return result;
    }

    // Simulate pandas Series.diff()
    diff(colName) {
        const series = this.column(colName).map(parseFloat);
        if (series.length < 1) return [];
        const result = [NaN];
        for (let i = 1; i < series.length; i++) {
            result.push(series[i] - series[i - 1]);
        }
        return result;
    }

    // Helper to add a new calculated column
    addColumn(colName, values) {
        if (values.length !== this.data.length) {
            throw new Error(`Length of values for column '${colName}' does not match DataFrame length.`);
        }
        this.data.forEach((row, i) => row[colName] = values[i]);
    }
}


async function fetchKlines(symbol, interval, limit, logger) {
    const endpoint = "/v5/market/kline";
    const params = {
        category: "linear",
        symbol: symbol,
        interval: interval,
        limit: limit,
    };
    const response = await bybitRequest("GET", endpoint, params, false, logger);
    if (response && response.result && response.result.list) {
        const klines = response.result.list.map(kline => ({
            start_time: new Date(parseInt(kline[0])),
            open: parseFloat(kline[1]),
            high: parseFloat(kline[2]),
            low: parseFloat(kline[3]),
            close: parseFloat(kline[4]),
            volume: parseFloat(kline[5]),
            turnover: parseFloat(kline[6]),
        }));

        // Sort by start_time to ensure ascending order
        klines.sort((a, b) => a.start_time.getTime() - b.start_time.getTime());

        const klineData = new KlineData(klines);

        if (klineData.empty) {
            logger.warn(`${NEON_YELLOW}Fetched klines for ${symbol} ${interval} but DataFrame is empty after processing. Raw response: ${JSON.stringify(response)}${RESET}`);
            return null;
        }

        logger.debug(`Fetched ${klineData.length} ${interval} klines for ${symbol}.`);
        return klineData;
    }
    logger.warn(`${NEON_YELLOW}Could not fetch klines for ${symbol} ${interval}. API response might be empty or invalid. Raw response: ${JSON.stringify(response)}${RESET}`);
    return null;
}

async function fetchOrderbook(symbol, limit, logger) {
    const endpoint = "/v5/market/orderbook";
    const params = { category: "linear", symbol: symbol, limit: limit };
    const response = await bybitRequest("GET", endpoint, params, false, logger);
    if (response && response.result) {
        logger.debug(`Fetched orderbook for ${symbol} with limit ${limit}.`);
        return response.result;
    }
    logger.warn(`${NEON_YELLOW}Could not fetch orderbook for ${symbol}.${RESET}`);
    return null;
}

// --- Position Management ---
class PositionManager {
    constructor(config, logger, symbol) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.openPositions = []; // Stores active positions
        this.tradeManagementEnabled = config.trade_management.enabled;
        this.maxOpenPositions = config.trade_management.max_open_positions;
        this.orderPrecision = config.trade_management.order_precision;
        this.pricePrecision = config.trade_management.price_precision;
    }

    _get_current_balance() {
        // In a real bot, this would query the exchange.
        // For simulation, use configured account balance.
        return new Decimal(String(this.config.trade_management.account_balance));
    }

    _calculate_order_size(current_price, atr_value) {
        if (!this.tradeManagementEnabled) {
            return new Decimal("0");
        }

        const accountBalance = this._get_current_balance();
        const riskPerTradePercent = new Decimal(String(this.config.trade_management.risk_per_trade_percent)).div(100);
        const stopLossAtrMultiple = new Decimal(String(this.config.trade_management.stop_loss_atr_multiple));

        const riskAmount = accountBalance.mul(riskPerTradePercent);
        const stopLossDistance = atr_value.mul(stopLossAtrMultiple);

        if (stopLossDistance.lte(0)) {
            this.logger.warn(`${NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.${RESET}`);
            return new Decimal("0");
        }

        // Order size in USD value
        const orderValue = riskAmount.div(stopLossDistance);
        // Convert to quantity of the asset (e.g., BTC)
        let orderQty = orderValue.div(current_price);

        // Round order_qty to appropriate precision for the symbol
        const precisionStr = "1e-" + this.orderPrecision;
        orderQty = orderQty.toDecimalPlaces(this.orderPrecision, Decimal.ROUND_DOWN);

        this.logger.info(`[${this.symbol}] Calculated order size: ${orderQty.toDecimalPlaces(this.orderPrecision, Decimal.ROUND_DOWN)} (Risk: ${riskAmount.toDecimalPlaces(2, Decimal.ROUND_DOWN)} USD)`);
        return orderQty;
    }

    openPosition(signal, current_price, atr_value) {
        if (!this.tradeManagementEnabled) {
            this.logger.info(`${NEON_YELLOW}[${this.symbol}] Trade management is disabled. Skipping opening position.${RESET}`);
            return null;
        }

        if (this.openPositions.length >= this.maxOpenPositions) {
            this.logger.info(`${NEON_YELLOW}[${this.symbol}] Max open positions (${this.maxOpenPositions}) reached. Cannot open new position.${RESET}`);
            return null;
        }

        const orderQty = this._calculate_order_size(current_price, atr_value);
        if (orderQty.lte(0)) {
            this.logger.warn(`${NEON_YELLOW}[${this.symbol}] Order quantity is zero or negative. Cannot open position.${RESET}`);
            return null;
        }

        const stopLossAtrMultiple = new Decimal(String(this.config.trade_management.stop_loss_atr_multiple));
        const takeProfitAtrMultiple = new Decimal(String(this.config.trade_management.take_profit_atr_multiple));

        let stopLoss, takeProfit;
        if (signal === "BUY") {
            stopLoss = current_price.sub(atr_value.mul(stopLossAtrMultiple));
            takeProfit = current_price.add(atr_value.mul(takeProfitAtrMultiple));
        } else { // SELL
            stopLoss = current_price.add(atr_value.mul(stopLossAtrMultiple));
            takeProfit = current_price.sub(atr_value.mul(takeProfitAtrMultiple));
        }

        const pricePrecisionStr = "1e-" + this.pricePrecision;

        const position = {
            entry_time: new Date(),
            symbol: this.symbol,
            side: signal,
            entry_price: current_price.toDecimalPlaces(this.pricePrecision, Decimal.ROUND_DOWN),
            qty: orderQty,
            stop_loss: stopLoss.toDecimalPlaces(this.pricePrecision, Decimal.ROUND_DOWN),
            take_profit: takeProfit.toDecimalPlaces(this.pricePrecision, Decimal.ROUND_DOWN),
            status: "OPEN",
        };
        this.openPositions.push(position);
        this.logger.info(`${NEON_GREEN}[${this.symbol}] Opened ${signal} position: ${JSON.stringify(position, (key, value) => {
            if (value instanceof Decimal) return value.toString();
            return value;
        })}${RESET}`);
        return position;
    }

    managePositions(current_price, performanceTracker) {
        if (!this.tradeManagementEnabled || this.openPositions.length === 0) {
            return;
        }

        const positionsToClose = [];
        for (let i = 0; i < this.openPositions.length; i++) {
            const position = this.openPositions[i];
            if (position.status === "OPEN") {
                const side = position.side;
                const entryPrice = new Decimal(position.entry_price);
                const stopLoss = new Decimal(position.stop_loss);
                const takeProfit = new Decimal(position.take_profit);
                const qty = new Decimal(position.qty);

                let closedBy = "";
                let closePrice = new Decimal("0");

                if (side === "BUY") {
                    if (current_price.lte(stopLoss)) {
                        closedBy = "STOP_LOSS";
                        closePrice = current_price;
                    } else if (current_price.gte(takeProfit)) {
                        closedBy = "TAKE_PROFIT";
                        closePrice = current_price;
                    }
                } else if (side === "SELL") {
                    if (current_price.gte(stopLoss)) {
                        closedBy = "STOP_LOSS";
                        closePrice = current_price;
                    } else if (current_price.lte(takeProfit)) {
                        closedBy = "TAKE_PROFIT";
                        closePrice = current_price;
                    }
                }

                if (closedBy) {
                    position.status = "CLOSED";
                    position.exit_time = new Date();
                    position.exit_price = closePrice.toDecimalPlaces(this.pricePrecision, Decimal.ROUND_DOWN);
                    position.closed_by = closedBy;
                    positionsToClose.push(i);

                    const pnl = (
                        side === "BUY"
                            ? (closePrice.sub(entryPrice)).mul(qty)
                            : (entryPrice.sub(closePrice)).mul(qty)
                    );
                    performanceTracker.recordTrade(position, pnl);
                    this.logger.info(`${NEON_PURPLE}[${this.symbol}] Closed ${side} position by ${closedBy}: ${JSON.stringify(position, (key, value) => {
                        if (value instanceof Decimal) return value.toString();
                        return value;
                    })}. PnL: ${pnl.toDecimalPlaces(2, Decimal.ROUND_DOWN)}${RESET}`);
                }
            }
        }

        // Remove closed positions
        this.openPositions = this.openPositions.filter((_, i) => !positionsToClose.includes(i));
    }

    getOpenPositions() {
        return this.openPositions.filter(pos => pos.status === "OPEN");
    }
}

// --- Performance Tracking ---
class PerformanceTracker {
    constructor(logger) {
        this.logger = logger;
        this.trades = [];
        this.totalPnl = new Decimal("0");
        this.wins = 0;
        this.losses = 0;
    }

    recordTrade(position, pnl) {
        const tradeRecord = {
            entry_time: position.entry_time,
            exit_time: position.exit_time,
            symbol: position.symbol,
            side: position.side,
            entry_price: position.entry_price,
            exit_price: position.exit_price,
            qty: position.qty,
            pnl: pnl,
            closed_by: position.closed_by,
        };
        this.trades.push(tradeRecord);
        this.totalPnl = this.totalPnl.add(pnl);
        if (pnl.gt(0)) {
            this.wins += 1;
        } else {
            this.losses += 1;
        }
        this.logger.info(`${NEON_CYAN}[${position.symbol}] Trade recorded. Current Total PnL: ${this.totalPnl.toDecimalPlaces(2, Decimal.ROUND_DOWN)}, Wins: ${this.wins}, Losses: ${this.losses}${RESET}`);
    }

    getSummary() {
        const totalTrades = this.trades.length;
        const winRate = totalTrades > 0 ? (this.wins / totalTrades) * 100 : 0;

        return {
            total_trades: totalTrades,
            total_pnl: this.totalPnl,
            wins: this.wins,
            losses: this.losses,
            win_rate: `${winRate.toFixed(2)}%`,
        };
    }
}

// --- Alert System ---
class AlertSystem {
    constructor(logger) {
        this.logger = logger;
    }

    sendAlert(message, level) {
        if (level === "INFO") {
            this.logger.info(`${NEON_BLUE}ALERT: ${message}${RESET}`);
        } else if (level === "WARNING") {
            this.logger.warn(`${NEON_YELLOW}ALERT: ${message}${RESET}`);
        } else if (level === "ERROR") {
            this.logger.error(`${NEON_RED}ALERT: ${message}${RESET}`);
        }
        // In a real bot, integrate with Telegram, Discord, Email etc.
    }
}

// --- Trading Analysis (Upgraded with Ehlers SuperTrend and more) ---
class TradingAnalyzer {
    constructor(klineData, config, logger, symbol) {
        this.klineData = klineData; // KlineData instance replaces DataFrame
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicatorValues = {};
        this.fibLevels = {};
        this.weights = config.weight_sets.default_scalping;
        this.indicatorSettings = config.indicator_settings;

        if (this.klineData.empty) {
            this.logger.warn(`${NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.${RESET}`);
            return;
        }

        this._calculateAllIndicators();
        if (this.config.indicators.fibonacci_levels) {
            this.calculateFibonacciLevels();
        }
    }

    _safeCalculate(func, name, minDataPoints = 0, ...args) {
        if (this.klineData.length < minDataPoints) {
            this.logger.debug(`[${this.symbol}] Skipping indicator '${name}': Not enough data. Need ${minDataPoints}, have ${this.klineData.length}.`);
            return null;
        }
        try {
            const result = func(...args);
            if (result === null || (Array.isArray(result) && result.length === 0) || (Array.isArray(result) && result.every(val => val === null || (Array.isArray(val) && val.length === 0)))) {
                this.logger.warn(`${NEON_YELLOW}[${this.symbol}] Indicator '${name}' returned empty or None after calculation. Not enough valid data?${RESET}`);
                return null;
            }
            return result;
        } catch (e) {
            this.logger.error(`${NEON_RED}[${this.symbol}] Error calculating indicator '${name}': ${e.message}${RESET}`);
            return null;
        }
    }

    _calculateAllIndicators() {
        this.logger.debug(`[${this.symbol}] Calculating technical indicators...`);
        const cfg = this.config;
        const isd = this.indicatorSettings;

        // SMA
        if (cfg.indicators.sma_10) {
            const sma10 = this._safeCalculate(() => this.klineData.rollingMean("close", isd.sma_short_period), "SMA_10", isd.sma_short_period);
            if (sma10) {
                this.klineData.addColumn("SMA_10", sma10);
                this.indicatorValues["SMA_10"] = sma10[sma10.length - 1];
            }
        }
        if (cfg.indicators.sma_trend_filter) {
            const smaLong = this._safeCalculate(() => this.klineData.rollingMean("close", isd.sma_long_period), "SMA_Long", isd.sma_long_period);
            if (smaLong) {
                this.klineData.addColumn("SMA_Long", smaLong);
                this.indicatorValues["SMA_Long"] = smaLong[smaLong.length - 1];
            }
        }

        // EMA
        if (cfg.indicators.ema_alignment) {
            const emaShort = this._safeCalculate(() => this.klineData.ewmMean("close", isd.ema_short_period, isd.ema_short_period), "EMA_Short", isd.ema_short_period);
            const emaLong = this._safeCalculate(() => this.klineData.ewmMean("close", isd.ema_long_period, isd.ema_long_period), "EMA_Long", isd.ema_long_period);
            if (emaShort) {
                this.klineData.addColumn("EMA_Short", emaShort);
                this.indicatorValues["EMA_Short"] = emaShort[emaShort.length - 1];
            }
            if (emaLong) {
                this.klineData.addColumn("EMA_Long", emaLong);
                this.indicatorValues["EMA_Long"] = emaLong[emaLong.length - 1];
            }
        }

        // ATR
        const tr = this._safeCalculate(() => this.calculateTrueRange(), "TR", MIN_DATA_POINTS_TR);
        if (tr) {
            this.klineData.addColumn("TR", tr);
            const atr = this._safeCalculate(() => this.ewmMeanCustom(tr, isd.atr_period, isd.atr_period), "ATR", isd.atr_period);
            if (atr) {
                this.klineData.addColumn("ATR", atr);
                this.indicatorValues["ATR"] = atr[atr.length - 1];
            }
        }

        // RSI
        if (cfg.indicators.rsi) {
            const rsi = this._safeCalculate(() => this.calculateRSI(isd.rsi_period), "RSI", isd.rsi_period + 1);
            if (rsi) {
                this.klineData.addColumn("RSI", rsi);
                this.indicatorValues["RSI"] = rsi[rsi.length - 1];
            }
        }

        // Stochastic RSI
        if (cfg.indicators.stoch_rsi) {
            const [stochRsiK, stochRsiD] = this._safeCalculate(
                () => this.calculateStochRSI(isd.stoch_rsi_period, isd.stoch_k_period, isd.stoch_d_period),
                "StochRSI",
                isd.stoch_rsi_period + isd.stoch_d_period + isd.stoch_k_period
            );
            if (stochRsiK) {
                this.klineData.addColumn("StochRSI_K", stochRsiK);
                this.indicatorValues["StochRSI_K"] = stochRsiK[stochRsiK.length - 1];
            }
            if (stochRsiD) {
                this.klineData.addColumn("StochRSI_D", stochRsiD);
                this.indicatorValues["StochRSI_D"] = stochRsiD[stochRsiD.length - 1];
            }
        }

        // Bollinger Bands
        if (cfg.indicators.bollinger_bands) {
            const [bbUpper, bbMiddle, bbLower] = this._safeCalculate(
                () => this.calculateBollingerBands(isd.bollinger_bands_period, isd.bollinger_bands_std_dev),
                "BollingerBands",
                isd.bollinger_bands_period
            );
            if (bbUpper) {
                this.klineData.addColumn("BB_Upper", bbUpper);
                this.indicatorValues["BB_Upper"] = bbUpper[bbUpper.length - 1];
            }
            if (bbMiddle) {
                this.klineData.addColumn("BB_Middle", bbMiddle);
                this.indicatorValues["BB_Middle"] = bbMiddle[bbMiddle.length - 1];
            }
            if (bbLower) {
                this.klineData.addColumn("BB_Lower", bbLower);
                this.indicatorValues["BB_Lower"] = bbLower[bbLower.length - 1];
            }
        }

        // CCI
        if (cfg.indicators.cci) {
            const cci = this._safeCalculate(() => this.calculateCCI(isd.cci_period), "CCI", isd.cci_period);
            if (cci) {
                this.klineData.addColumn("CCI", cci);
                this.indicatorValues["CCI"] = cci[cci.length - 1];
            }
        }

        // Williams %R
        if (cfg.indicators.wr) {
            const wr = this._safeCalculate(() => this.calculateWilliamsR(isd.williams_r_period), "WR", isd.williams_r_period);
            if (wr) {
                this.klineData.addColumn("WR", wr);
                this.indicatorValues["WR"] = wr[wr.length - 1];
            }
        }

        // MFI
        if (cfg.indicators.mfi) {
            const mfi = this._safeCalculate(() => this.calculateMFI(isd.mfi_period), "MFI", isd.mfi_period + 1);
            if (mfi) {
                this.klineData.addColumn("MFI", mfi);
                this.indicatorValues["MFI"] = mfi[mfi.length - 1];
            }
        }

        // OBV
        if (cfg.indicators.obv) {
            const [obvVal, obvEma] = this._safeCalculate(
                () => this.calculateOBV(isd.obv_ema_period),
                "OBV",
                isd.obv_ema_period
            );
            if (obvVal) {
                this.klineData.addColumn("OBV", obvVal);
                this.indicatorValues["OBV"] = obvVal[obvVal.length - 1];
            }
            if (obvEma) {
                this.klineData.addColumn("OBV_EMA", obvEma);
                this.indicatorValues["OBV_EMA"] = obvEma[obvEma.length - 1];
            }
        }

        // CMF
        if (cfg.indicators.cmf) {
            const cmfVal = this._safeCalculate(() => this.calculateCMF(isd.cmf_period), "CMF", isd.cmf_period);
            if (cmfVal) {
                this.klineData.addColumn("CMF", cmfVal);
                this.indicatorValues["CMF"] = cmfVal[cmfVal.length - 1];
            }
        }

        // Ichimoku Cloud
        if (cfg.indicators.ichimoku_cloud) {
            const [tenkanSen, kijunSen, senkouSpanA, senkouSpanB, chikouSpan] = this._safeCalculate(
                () => this.calculateIchimokuCloud(
                    isd.ichimoku_tenkan_period,
                    isd.ichimoku_kijun_period,
                    isd.ichimoku_senkou_span_b_period,
                    isd.ichimoku_chikou_span_offset
                ),
                "IchimokuCloud",
                Math.max(isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period) + isd.ichimoku_chikou_span_offset
            );
            if (tenkanSen) {
                this.klineData.addColumn("Tenkan_Sen", tenkanSen);
                this.indicatorValues["Tenkan_Sen"] = tenkanSen[tenkanSen.length - 1];
            }
            if (kijunSen) {
                this.klineData.addColumn("Kijun_Sen", kijunSen);
                this.indicatorValues["Kijun_Sen"] = kijunSen[kijunSen.length - 1];
            }
            if (senkouSpanA) {
                this.klineData.addColumn("Senkou_Span_A", senkouSpanA);
                this.indicatorValues["Senkou_Span_A"] = senkouSpanA[senkouSpanA.length - 1];
            }
            if (senkouSpanB) {
                this.klineData.addColumn("Senkou_Span_B", senkouSpanB);
                this.indicatorValues["Senkou_Span_B"] = senkouSpanB[senkouSpanB.length - 1];
            }
            if (chikouSpan) {
                this.klineData.addColumn("Chikou_Span", chikouSpan);
                this.indicatorValues["Chikou_Span"] = chikouSpan[chikouSpan.length - 1] || 0;
            }
        }

        // PSAR
        if (cfg.indicators.psar) {
            const [psarVal, psarDir] = this._safeCalculate(
                () => this.calculatePSAR(isd.psar_acceleration, isd.psar_max_acceleration),
                "PSAR",
                MIN_DATA_POINTS_PSAR
            );
            if (psarVal) {
                this.klineData.addColumn("PSAR_Val", psarVal);
                this.indicatorValues["PSAR_Val"] = psarVal[psarVal.length - 1];
            }
            if (psarDir) {
                this.klineData.addColumn("PSAR_Dir", psarDir);
                this.indicatorValues["PSAR_Dir"] = psarDir[psarDir.length - 1];
            }
        }

        // VWAP
        if (cfg.indicators.vwap) {
            const vwap = this._safeCalculate(() => this.calculateVWAP(), "VWAP", 1);
            if (vwap) {
                this.klineData.addColumn("VWAP", vwap);
                this.indicatorValues["VWAP"] = vwap[vwap.length - 1];
            }
        }

        // --- Ehlers SuperTrend Calculation ---
        if (cfg.indicators.ehlers_supertrend) {
            const stFastResult = this._safeCalculate(
                () => this.calculateEhlersSuperTrend(isd.ehlers_fast_period, isd.ehlers_fast_multiplier),
                "EhlersSuperTrendFast",
                isd.ehlers_fast_period * 3
            );
            if (stFastResult) {
                this.klineData.addColumn("st_fast_dir", stFastResult.direction);
                this.klineData.addColumn("st_fast_val", stFastResult.supertrend);
                this.indicatorValues["ST_Fast_Dir"] = stFastResult.direction[stFastResult.direction.length - 1];
                this.indicatorValues["ST_Fast_Val"] = stFastResult.supertrend[stFastResult.supertrend.length - 1];
            }

            const stSlowResult = this._safeCalculate(
                () => this.calculateEhlersSuperTrend(isd.ehlers_slow_period, isd.ehlers_slow_multiplier),
                "EhlersSuperTrendSlow",
                isd.ehlers_slow_period * 3
            );
            if (stSlowResult) {
                this.klineData.addColumn("st_slow_dir", stSlowResult.direction);
                this.klineData.addColumn("st_slow_val", stSlowResult.supertrend);
                this.indicatorValues["ST_Slow_Dir"] = stSlowResult.direction[stSlowResult.direction.length - 1];
                this.indicatorValues["ST_Slow_Val"] = stSlowResult.supertrend[stSlowResult.supertrend.length - 1];
            }
        }

        // MACD
        if (cfg.indicators.macd) {
            const [macdLine, signalLine, histogram] = this._safeCalculate(
                () => this.calculateMACD(isd.macd_fast_period, isd.macd_slow_period, isd.macd_signal_period),
                "MACD",
                isd.macd_slow_period + isd.macd_signal_period
            );
            if (macdLine) {
                this.klineData.addColumn("MACD_Line", macdLine);
                this.indicatorValues["MACD_Line"] = macdLine[macdLine.length - 1];
            }
            if (signalLine) {
                this.klineData.addColumn("MACD_Signal", signalLine);
                this.indicatorValues["MACD_Signal"] = signalLine[signalLine.length - 1];
            }
            if (histogram) {
                this.klineData.addColumn("MACD_Hist", histogram);
                this.indicatorValues["MACD_Hist"] = histogram[histogram.length - 1];
            }
        }

        // ADX
        if (cfg.indicators.adx) {
            const [adxVal, plusDi, minusDi] = this._safeCalculate(
                () => this.calculateADX(isd.adx_period),
                "ADX",
                isd.adx_period * 2
            );
            if (adxVal) {
                this.klineData.addColumn("ADX", adxVal);
                this.indicatorValues["ADX"] = adxVal[adxVal.length - 1];
            }
            if (plusDi) {
                this.klineData.addColumn("PlusDI", plusDi);
                this.indicatorValues["PlusDI"] = plusDi[plusDi.length - 1];
            }
            if (minusDi) {
                this.klineData.addColumn("MinusDI", minusDi);
                this.indicatorValues["MinusDI"] = minusDi[minusDi.length - 1];
            }
        }

        // --- New Indicators ---
        // Volatility Index
        if (cfg.indicators.volatility_index) {
            const volatilityIndex = this._safeCalculate(
                () => this.calculateVolatilityIndex(isd.volatility_index_period),
                "Volatility_Index",
                isd.volatility_index_period
            );
            if (volatilityIndex) {
                this.klineData.addColumn("Volatility_Index", volatilityIndex);
                this.indicatorValues["Volatility_Index"] = volatilityIndex[volatilityIndex.length - 1];
            }
        }

        // VWMA
        if (cfg.indicators.vwma) {
            const vwma = this._safeCalculate(
                () => this.calculateVWMA(isd.vwma_period),
                "VWMA",
                isd.vwma_period
            );
            if (vwma) {
                this.klineData.addColumn("VWMA", vwma);
                this.indicatorValues["VWMA"] = vwma[vwma.length - 1];
            }
        }

        // Volume Delta
        if (cfg.indicators.volume_delta) {
            const volumeDelta = this._safeCalculate(
                () => this.calculateVolumeDelta(isd.volume_delta_period),
                "Volume_Delta",
                isd.volume_delta_period
            );
            if (volumeDelta) {
                this.klineData.addColumn("Volume_Delta", volumeDelta);
                this.indicatorValues["Volume_Delta"] = volumeDelta[volumeDelta.length - 1];
            }
        }
    }

    // Helper for EWM for generic series (used when not a direct df.ewmMean)
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
            } else {
                result[i] = NaN; // Fill with NaN until minPeriods met
            }
        }
        return result;
    }

    calculateTrueRange() {
        if (this.klineData.length < MIN_DATA_POINTS_TR) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tr = new Array(this.klineData.length).fill(NaN);

        for (let i = 1; i < this.klineData.length; i++) {
            const highLow = high[i] - low[i];
            const highPrevClose = Math.abs(high[i] - close[i - 1]);
            const lowPrevClose = Math.abs(low[i] - close[i - 1]);
            tr[i] = Math.max(highLow, highPrevClose, lowPrevClose);
        }
        return tr;
    }

    calculateSuperSmoother(series, period) {
        if (period <= 0 || series.length < MIN_DATA_POINTS_SMOOTHER) {
            return new Array(series.length).fill(NaN);
        }

        const filteredSeries = series.filter(val => !isNaN(val));
        if (filteredSeries.length < MIN_DATA_POINTS_SMOOTHER) {
            return new Array(series.length).fill(NaN);
        }

        const a1 = Math.exp(-Math.sqrt(2) * Math.PI / period);
        const b1 = 2 * a1 * Math.cos(Math.sqrt(2) * Math.PI / period);
        const c1 = 1 - b1 + a1 * a1;
        const c2 = b1 - 2 * a1 * a1;
        const c3 = a1 * a1;

        const filt = new Array(series.length).fill(NaN);
        if (series.length >= 1) {
            filt[0] = series[0];
        }
        if (series.length >= 2) {
            filt[1] = (series[0] + series[1]) / 2;
        }

        for (let i = 2; i < series.length; i++) {
            if (!isNaN(series[i]) && !isNaN(series[i - 1])) {
                filt[i] = (
                    (c1 / 2) * (series[i] + series[i - 1])
                    + c2 * filt[i - 1]
                    - c3 * filt[i - 2]
                );
            }
        }
        return filt;
    }

    calculateEhlersSuperTrend(period, multiplier) {
        if (this.klineData.length < period * 3) {
            return null;
        }

        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");

        const hl2 = high.map((h, i) => (h + low[i]) / 2);
        const smoothedPrice = this.calculateSuperSmoother(hl2, period);

        const tr = this.calculateTrueRange();
        const smoothedAtr = this.calculateSuperSmoother(tr, period);

        if (!smoothedPrice || !smoothedAtr || smoothedPrice.some(isNaN) || smoothedAtr.some(isNaN)) {
            this.logger.debug(`[${this.symbol}] Ehlers SuperTrend: Smoothed price or ATR contains NaN. Returning null.`);
            return null;
        }

        const upperBand = smoothedPrice.map((sp, i) => sp + multiplier * smoothedAtr[i]);
        const lowerBand = smoothedPrice.map((sp, i) => sp - multiplier * smoothedAtr[i]);

        const direction = new Array(this.klineData.length).fill(0);
        const supertrend = new Array(this.klineData.length).fill(NaN);

        // Find the first valid index after smoothing
        const firstValidIdx = smoothedPrice.findIndex(val => !isNaN(val));
        if (firstValidIdx === -1 || firstValidIdx >= this.klineData.length) {
            return null;
        }

        if (close[firstValidIdx] > upperBand[firstValidIdx]) {
            direction[firstValidIdx] = 1;
            supertrend[firstValidIdx] = lowerBand[firstValidIdx];
        } else if (close[firstValidIdx] < lowerBand[firstValidIdx]) {
            direction[firstValidIdx] = -1;
            supertrend[firstValidIdx] = upperBand[firstValidIdx];
        } else {
            direction[firstValidIdx] = 0;
            supertrend[firstValidIdx] = lowerBand[firstValidIdx];
        }

        for (let i = firstValidIdx + 1; i < this.klineData.length; i++) {
            const prevDirection = direction[i - 1];
            const prevSupertrend = supertrend[i - 1];
            const currClose = close[i];

            if (prevDirection === 1) { // Previous was an UP trend
                if (currClose < prevSupertrend) {
                    direction[i] = -1;
                    supertrend[i] = upperBand[i];
                } else {
                    direction[i] = 1;
                    supertrend[i] = Math.max(lowerBand[i], prevSupertrend);
                }
            } else if (prevDirection === -1) { // Previous was a DOWN trend
                if (currClose > prevSupertrend) {
                    direction[i] = 1;
                    supertrend[i] = lowerBand[i];
                } else {
                    direction[i] = -1;
                    supertrend[i] = Math.min(upperBand[i], prevSupertrend);
                }
            } else { // Neutral or initial state
                if (currClose > upperBand[i]) {
                    direction[i] = 1;
                    supertrend[i] = lowerBand[i];
                } else if (currClose < lowerBand[i]) {
                    direction[i] = -1;
                    supertrend[i] = upperBand[i];
                } else {
                    direction[i] = prevDirection;
                    supertrend[i] = prevSupertrend;
                }
            }
        }
        return { supertrend, direction };
    }

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

    calculateRSI(period) {
        if (this.klineData.length <= period) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const close = this.klineData.column("close");
        const delta = this.klineData.diff("close");
        const gain = delta.map(d => Math.max(0, d));
        const loss = delta.map(d => Math.max(0, -d));

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

    calculateStochRSI(period, kPeriod, dPeriod) {
        if (this.klineData.length <= period) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        const rsi = this.calculateRSI(period);

        const lowestRsi = new Array(this.klineData.length).fill(NaN);
        const highestRsi = new Array(this.klineData.length).fill(NaN);

        for (let i = period - 1; i < this.klineData.length; i++) {
            const rsiWindow = rsi.slice(i - period + 1, i + 1).filter(val => !isNaN(val));
            if (rsiWindow.length > 0) {
                lowestRsi[i] = Math.min(...rsiWindow);
                highestRsi[i] = Math.max(...rsiWindow);
            }
        }

        const stochRsiKRaw = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(rsi[i]) && !isNaN(lowestRsi[i]) && !isNaN(highestRsi[i])) {
                const denominator = highestRsi[i] - lowestRsi[i];
                if (denominator === 0) {
                    stochRsiKRaw[i] = 0; // Or NaN, depending on desired behavior for flat RSI
                } else {
                    stochRsiKRaw[i] = ((rsi[i] - lowestRsi[i]) / denominator) * 100;
                }
            }
        }

        const stochRsiK = this.klineData.rollingMean(stochRsiKRaw, kPeriod);
        const stochRsiD = this.klineData.rollingMean(stochRsiK, dPeriod);

        return [stochRsiK.map(val => Math.max(0, Math.min(100, val || 0))), stochRsiD.map(val => Math.max(0, Math.min(100, val || 0)))];
    }

    calculateADX(period) {
        if (this.klineData.length < period * 2) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }

        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tr = this.calculateTrueRange();

        const plusDM = new Array(this.klineData.length).fill(0);
        const minusDM = new Array(this.klineData.length).fill(0);

        for (let i = 1; i < this.klineData.length; i++) {
            const upMove = high[i] - high[i - 1];
            const downMove = low[i - 1] - low[i];

            plusDM[i] = (upMove > downMove && upMove > 0) ? upMove : 0;
            minusDM[i] = (downMove > upMove && downMove > 0) ? downMove : 0;
        }

        const atr = this.ewmMeanCustom(tr, period, period);
        const plusDIMean = this.ewmMeanCustom(plusDM, period, period);
        const minusDIMean = this.ewmMeanCustom(minusDM, period, period);

        const plusDI = new Array(this.klineData.length).fill(NaN);
        const minusDI = new Array(this.klineData.length).fill(NaN);

        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(plusDIMean[i]) && !isNaN(atr[i]) && atr[i] !== 0) {
                plusDI[i] = (plusDIMean[i] / atr[i]) * 100;
            }
            if (!isNaN(minusDIMean[i]) && !isNaN(atr[i]) && atr[i] !== 0) {
                minusDI[i] = (minusDIMean[i] / atr[i]) * 100;
            }
        }

        const dx = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(plusDI[i]) && !isNaN(minusDI[i])) {
                const diDiff = Math.abs(plusDI[i] - minusDI[i]);
                const diSum = plusDI[i] + minusDI[i];
                dx[i] = (diSum === 0) ? 0 : (diDiff / diSum) * 100;
            }
        }
        const adx = this.ewmMeanCustom(dx, period, period);
        return [adx, plusDI, minusDI];
    }

    calculateBollingerBands(period, stdDev) {
        if (this.klineData.length < period) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }
        const close = this.klineData.column("close");
        const middleBand = this.klineData.rollingMean("close", period);

        const std = new Array(this.klineData.length).fill(NaN);
        for (let i = period - 1; i < this.klineData.length; i++) {
            const window = close.slice(i - period + 1, i + 1);
            const mean = middleBand[i];
            const sumOfSquares = window.reduce((acc, val) => acc + (val - mean) ** 2, 0);
            std[i] = Math.sqrt(sumOfSquares / period);
        }

        const upperBand = middleBand.map((mb, i) => mb + (std[i] * stdDev));
        const lowerBand = middleBand.map((mb, i) => mb - (std[i] * stdDev));
        return [upperBand, middleBand, lowerBand];
    }

    calculateVWAP() {
        if (this.klineData.empty) {
            return new Array(this.klineData.length).fill(NaN);
        }
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

    calculateCCI(period) {
        if (this.klineData.length < period) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const tp = high.map((h, i) => (h + low[i] + close[i]) / 3);

        const smaTp = this.klineData.rollingMean(tp, period);

        const mad = new Array(this.klineData.length).fill(NaN);
        for (let i = period - 1; i < this.klineData.length; i++) {
            const tpWindow = tp.slice(i - period + 1, i + 1);
            const meanTp = smaTp[i];
            const absDevSum = tpWindow.reduce((acc, val) => acc + Math.abs(val - meanTp), 0);
            mad[i] = absDevSum / period;
        }

        const cci = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(tp[i]) && !isNaN(smaTp[i]) && !isNaN(mad[i])) {
                if (mad[i] === 0) {
                    cci[i] = 0; // Or handle as appropriate
                } else {
                    cci[i] = (tp[i] - smaTp[i]) / (0.015 * mad[i]);
                }
            }
        }
        return cci;
    }

    calculateWilliamsR(period) {
        if (this.klineData.length < period) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");

        const highestHigh = new Array(this.klineData.length).fill(NaN);
        const lowestLow = new Array(this.klineData.length).fill(NaN);

        for (let i = period - 1; i < this.klineData.length; i++) {
            const highWindow = high.slice(i - period + 1, i + 1);
            const lowWindow = low.slice(i - period + 1, i + 1);
            highestHigh[i] = Math.max(...highWindow);
            lowestLow[i] = Math.min(...lowWindow);
        }

        const wr = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(close[i]) && !isNaN(highestHigh[i]) && !isNaN(lowestLow[i])) {
                const denominator = highestHigh[i] - lowestLow[i];
                if (denominator === 0) {
                    wr[i] = -100; // Or handle as appropriate
                } else {
                    wr[i] = -100 * ((highestHigh[i] - close[i]) / denominator);
                }
            }
        }
        return wr;
    }

    calculateIchimokuCloud(tenkanPeriod, kijunPeriod, senkouSpanBPeriod, chikouSpanOffset) {
        if (this.klineData.length < Math.max(tenkanPeriod, kijunPeriod, senkouSpanBPeriod) + chikouSpanOffset) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }

        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");

        const calculateMinMax = (series, period) => {
            const resultMax = new Array(series.length).fill(NaN);
            const resultMin = new Array(series.length).fill(NaN);
            for (let i = period - 1; i < series.length; i++) {
                const window = series.slice(i - period + 1, i + 1);
                resultMax[i] = Math.max(...window);
                resultMin[i] = Math.min(...window);
            }
            return [resultMax, resultMin];
        };

        const [highTenkan, lowTenkan] = calculateMinMax(high, tenkanPeriod);
        const [highKijun, lowKijun] = calculateMinMax(high, kijunPeriod);
        const [highSenkouB, lowSenkouB] = calculateMinMax(high, senkouSpanBPeriod);

        const tenkanSen = highTenkan.map((h, i) => (h + lowTenkan[i]) / 2);
        const kijunSen = highKijun.map((h, i) => (h + lowKijun[i]) / 2);

        const senkouSpanA = new Array(this.klineData.length).fill(NaN);
        for (let i = kijunPeriod; i < this.klineData.length; i++) {
            if (!isNaN(tenkanSen[i - kijunPeriod]) && !isNaN(kijunSen[i - kijunPeriod])) {
                senkouSpanA[i] = (tenkanSen[i - kijunPeriod] + kijunSen[i - kijunPeriod]) / 2;
            }
        }

        const senkouSpanB = new Array(this.klineData.length).fill(NaN);
        for (let i = kijunPeriod; i < this.klineData.length; i++) {
            if (!isNaN(highSenkouB[i - kijunPeriod]) && !isNaN(lowSenkouB[i - kijunPeriod])) {
                senkouSpanB[i] = (highSenkouB[i - kijunPeriod] + lowSenkouB[i - kijunPeriod]) / 2;
            }
        }

        const chikouSpan = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (i + chikouSpanOffset < this.klineData.length) {
                chikouSpan[i] = close[i + chikouSpanOffset];
            }
        }
        return [tenkanSen, kijunSen, senkouSpanA, senkouSpanB, chikouSpan];
    }

    calculateMFI(period) {
        if (this.klineData.length <= period) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");

        const typicalPrice = high.map((h, i) => (h + low[i] + close[i]) / 3);
        const moneyFlow = typicalPrice.map((tp, i) => tp * volume[i]);

        const positiveFlow = new Array(this.klineData.length).fill(0);
        const negativeFlow = new Array(this.klineData.length).fill(0);

        for (let i = 1; i < this.klineData.length; i++) {
            if (typicalPrice[i] > typicalPrice[i - 1]) {
                positiveFlow[i] = moneyFlow[i];
            } else if (typicalPrice[i] < typicalPrice[i - 1]) {
                negativeFlow[i] = moneyFlow[i];
            }
        }

        const positiveMfSum = new Array(this.klineData.length).fill(NaN);
        const negativeMfSum = new Array(this.klineData.length).fill(NaN);

        for (let i = period - 1; i < this.klineData.length; i++) {
            positiveMfSum[i] = positiveFlow.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
            negativeMfSum[i] = negativeFlow.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
        }

        const mfi = new Array(this.klineData.length).fill(NaN);
        for (let i = 0; i < this.klineData.length; i++) {
            if (!isNaN(positiveMfSum[i]) && !isNaN(negativeMfSum[i])) {
                const mfRatio = (negativeMfSum[i] === 0) ? (positiveMfSum[i] === 0 ? 0 : Infinity) : positiveMfSum[i] / negativeMfSum[i];
                mfi[i] = 100 - (100 / (1 + mfRatio));
            }
        }
        return mfi;
    }

    calculateOBV(emaPeriod) {
        if (this.klineData.length < MIN_DATA_POINTS_OBV) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }

        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");
        const obv = new Array(this.klineData.length).fill(0);

        if (this.klineData.length > 0) {
            obv[0] = volume[0]; // Initialize with first volume
        }

        for (let i = 1; i < this.klineData.length; i++) {
            if (close[i] > close[i - 1]) {
                obv[i] = obv[i - 1] + volume[i];
            } else if (close[i] < close[i - 1]) {
                obv[i] = obv[i - 1] - volume[i];
            } else {
                obv[i] = obv[i - 1];
            }
        }

        const obvEma = this.ewmMeanCustom(obv, emaPeriod, emaPeriod);
        return [obv, obvEma];
    }

    calculateCMF(period) {
        if (this.klineData.length < period) {
            return new Array(this.klineData.length).fill(NaN);
        }

        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");

        const mfm = new Array(this.klineData.length).fill(0);
        for (let i = 0; i < this.klineData.length; i++) {
            const highLowRange = high[i] - low[i];
            if (highLowRange === 0) {
                mfm[i] = 0;
            } else {
                mfm[i] = ((close[i] - low[i]) - (high[i] - close[i])) / highLowRange;
            }
        }

        const mfv = mfm.map((m, i) => m * volume[i]);

        const cmf = new Array(this.klineData.length).fill(NaN);
        for (let i = period - 1; i < this.klineData.length; i++) {
            const mfvSum = mfv.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
            const volumeSum = volume.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
            if (volumeSum === 0) {
                cmf[i] = 0;
            } else {
                cmf[i] = mfvSum / volumeSum;
            }
        }
        return cmf;
    }

    calculatePSAR(acceleration, maxAcceleration) {
        if (this.klineData.length < MIN_DATA_POINTS_PSAR) {
            return [new Array(this.klineData.length).fill(NaN), new Array(this.klineData.length).fill(NaN)];
        }

        const high = this.klineData.column("high");
        const low = this.klineData.column("low");
        const close = this.klineData.column("close");

        const psar = new Array(this.klineData.length).fill(NaN);
        const bull = new Array(this.klineData.length).fill(null); // true for bullish, false for bearish
        const direction = new Array(this.klineData.length).fill(0); // 1 for bullish, -1 for bearish

        let af = acceleration;
        let ep = 0; // Extreme Point

        // Initialize first two bars
        if (close[0] < close[1]) { // Initial bullish trend
            bull[1] = true;
            psar[1] = low[0];
            ep = high[1];
        } else { // Initial bearish trend
            bull[1] = false;
            psar[1] = high[0];
            ep = low[1];
        }
        direction[1] = bull[1] ? 1 : -1;
        psar[0] = NaN; // PSAR starts from the second bar for calculation

        for (let i = 2; i < this.klineData.length; i++) {
            const prevBull = bull[i - 1];
            const prevPsar = psar[i - 1];
            const prevEp = ep;

            let currentPsar;
            if (prevBull) { // Bullish trend
                currentPsar = prevPsar + af * (prevEp - prevPsar);
                // Clamp PSAR to below current and previous lows
                currentPsar = Math.min(currentPsar, low[i - 1], low[i]);
            } else { // Bearish trend
                currentPsar = prevPsar - af * (prevPsar - prevEp);
                // Clamp PSAR to above current and previous highs
                currentPsar = Math.max(currentPsar, high[i - 1], high[i]);
            }

            let reverse = false;
            if (prevBull && low[i] < currentPsar) {
                bull[i] = false; // Reverse to bearish
                reverse = true;
            } else if (!prevBull && high[i] > currentPsar) {
                bull[i] = true; // Reverse to bullish
                reverse = true;
            } else {
                bull[i] = prevBull; // Continue previous trend
            }

            if (reverse) {
                af = acceleration;
                ep = bull[i] ? high[i] : low[i];
                // Set PSAR to swing low/high on reversal
                if (bull[i]) { // Reversing to bullish, PSAR should be below prior lows
                    psar[i] = Math.min(low[i], low[i-1]); // Or other logic to set initial PSAR for new trend
                } else { // Reversing to bearish, PSAR should be above prior highs
                    psar[i] = Math.max(high[i], high[i-1]);
                }
            } else {
                if (bull[i]) { // Continuing bullish
                    if (high[i] > ep) {
                        ep = high[i];
                        af = Math.min(af + acceleration, maxAcceleration);
                    }
                } else { // Continuing bearish
                    if (low[i] < ep) {
                        ep = low[i];
                        af = Math.min(af + acceleration, maxAcceleration);
                    }
                }
                psar[i] = currentPsar;
            }
            direction[i] = bull[i] ? 1 : -1;
        }

        // Fill NaN for the first element
        psar[0] = psar[1]; // A common way to handle the first element for display.
        direction[0] = direction[1];

        return [psar, direction];
    }

    calculateFibonacciLevels() {
        const window = this.config.indicator_settings.fibonacci_window;
        if (this.klineData.length < window) {
            this.logger.warn(`${NEON_YELLOW}[${this.symbol}] Not enough data for Fibonacci levels (need ${window} bars).${RESET}`);
            return;
        }

        const highSeries = this.klineData.column("high").slice(-window);
        const lowSeries = this.klineData.column("low").slice(-window);

        const recentHigh = Math.max(...highSeries);
        const recentLow = Math.min(...lowSeries);

        const diff = recentHigh - recentLow;

        if (diff <= 0) {
            this.logger.warn(`${NEON_YELLOW}[${this.symbol}] Invalid high-low range for Fibonacci calculation. Diff: ${diff}${RESET}`);
            return;
        }

        this.fibLevels = {
            "0.0%": new Decimal(String(recentHigh)),
            "23.6%": new Decimal(String(recentHigh - 0.236 * diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "38.2%": new Decimal(String(recentHigh - 0.382 * diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "50.0%": new Decimal(String(recentHigh - 0.500 * diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "61.8%": new Decimal(String(recentHigh - 0.618 * diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "78.6%": new Decimal(String(recentHigh - 0.786 * diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "100.0%": new Decimal(String(recentLow)),
        };
        this.logger.debug(`[${this.symbol}] Calculated Fibonacci levels: ${JSON.stringify(this.fibLevels, (key, value) => {
            if (value instanceof Decimal) return value.toString();
            return value;
        })}`);
    }

    calculateVolatilityIndex(period) {
        if (this.klineData.length < period || !this.klineData.column("ATR")) {
            return new Array(this.klineData.length).fill(NaN);
        }

        const atr = this.klineData.column("ATR");
        const close = this.klineData.column("close");
        const normalizedAtr = atr.map((a, i) => a / close[i]);

        const volatilityIndex = new Array(this.klineData.length).fill(NaN);
        for (let i = period - 1; i < this.klineData.length; i++) {
            const window = normalizedAtr.slice(i - period + 1, i + 1);
            volatilityIndex[i] = window.reduce((a, b) => a + b, 0) / period;
        }
        return volatilityIndex;
    }

    calculateVWMA(period) {
        if (this.klineData.length < period) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const close = this.klineData.column("close");
        const volume = this.klineData.column("volume");

        const vwma = new Array(this.klineData.length).fill(NaN);
        for (let i = period - 1; i < this.klineData.length; i++) {
            let pvSum = 0;
            let volSum = 0;
            for (let j = 0; j < period; j++) {
                pvSum += close[i - j] * volume[i - j];
                volSum += volume[i - j];
            }
            if (volSum !== 0) {
                vwma[i] = pvSum / volSum;
            } else {
                vwma[i] = NaN;
            }
        }
        return vwma;
    }

    calculateVolumeDelta(period) {
        if (this.klineData.length < MIN_DATA_POINTS_VOLATILITY) {
            return new Array(this.klineData.length).fill(NaN);
        }
        const close = this.klineData.column("close");
        const open = this.klineData.column("open");
        const volume = this.klineData.column("volume");

        const buyVolume = volume.map((v, i) => (close[i] > open[i] ? v : 0));
        const sellVolume = volume.map((v, i) => (close[i] < open[i] ? v : 0));

        const buyVolumeSum = new Array(this.klineData.length).fill(NaN);
        const sellVolumeSum = new Array(this.klineData.length).fill(NaN);
        const volumeDelta = new Array(this.klineData.length).fill(NaN);

        for (let i = 0; i < this.klineData.length; i++) {
            const start = Math.max(0, i - period + 1);
            const currentBuySum = buyVolume.slice(start, i + 1).reduce((a, b) => a + b, 0);
            const currentSellSum = sellVolume.slice(start, i + 1).reduce((a, b) => a + b, 0);
            
            buyVolumeSum[i] = currentBuySum;
            sellVolumeSum[i] = currentSellSum;

            const totalVolumeSum = currentBuySum + currentSellSum;
            if (totalVolumeSum === 0) {
                volumeDelta[i] = 0;
            } else {
                volumeDelta[i] = (currentBuySum - currentSellSum) / totalVolumeSum;
            }
        }
        return volumeDelta;
    }

    _getIndicatorValue(key, defaultValue = NaN) {
        const value = this.indicatorValues[key];
        return (typeof value === 'number' && !isNaN(value)) ? value : defaultValue;
    }

    _checkOrderbook(currentPrice, orderbookData) {
        const bids = orderbookData.b || [];
        const asks = orderbookData.a || [];

        const bidVolume = bids.reduce((sum, b) => sum.add(new Decimal(b[1])), new Decimal("0"));
        const askVolume = asks.reduce((sum, a) => sum.add(new Decimal(a[1])), new Decimal("0"));

        const totalVolume = bidVolume.add(askVolume);
        if (totalVolume.eq(0)) {
            return 0.0;
        }

        const imbalance = bidVolume.sub(askVolume).div(totalVolume);
        this.logger.debug(`[${this.symbol}] Orderbook Imbalance: ${imbalance.toFixed(4)} (Bids: ${bidVolume.toString()}, Asks: ${askVolume.toString()})`);
        return parseFloat(imbalance.toString());
    }

    _getMtfTrend(higherTfKlineData, indicatorType) {
        if (higherTfKlineData.empty) {
            return "UNKNOWN";
        }

        const lastClose = higherTfKlineData.get(-1).close;
        const period = this.config.mtf_analysis.trend_period;

        if (indicatorType === "sma") {
            if (higherTfKlineData.length < period) {
                this.logger.debug(`[${this.symbol}] MTF SMA: Not enough data for ${period} period. Have ${higherTfKlineData.length}.`);
                return "UNKNOWN";
            }
            const sma = higherTfKlineData.rollingMean("close", period)[higherTfKlineData.length - 1];
            if (isNaN(sma)) return "UNKNOWN";
            if (lastClose > sma) return "UP";
            if (lastClose < sma) return "DOWN";
            return "SIDEWAYS";
        } else if (indicatorType === "ema") {
            if (higherTfKlineData.length < period) {
                this.logger.debug(`[${this.symbol}] MTF EMA: Not enough data for ${period} period. Have ${higherTfKlineData.length}.`);
                return "UNKNOWN";
            }
            const ema = higherTfKlineData.ewmMean("close", period, period)[higherTfKlineData.length - 1];
            if (isNaN(ema)) return "UNKNOWN";
            if (lastClose > ema) return "UP";
            if (lastClose < ema) return "DOWN";
            return "SIDEWAYS";
        } else if (indicatorType === "ehlers_supertrend") {
            // Need a temporary analyzer to calculate Ehlers SuperTrend for the MTF data
            const tempAnalyzer = new TradingAnalyzer(higherTfKlineData, this.config, this.logger, this.symbol);
            const stResult = tempAnalyzer.calculateEhlersSuperTrend(
                this.indicatorSettings.ehlers_slow_period,
                this.indicatorSettings.ehlers_slow_multiplier
            );
            if (stResult && stResult.direction && stResult.direction.length > 0) {
                const stDir = stResult.direction[stResult.direction.length - 1];
                if (stDir === 1) return "UP";
                if (stDir === -1) return "DOWN";
            }
            return "UNKNOWN";
        }
        return "UNKNOWN";
    }

    generateTradingSignal(current_price, orderbookData, mtfTrends) {
        let signalScore = 0.0;
        const activeIndicators = this.config.indicators;
        const weights = this.weights;
        const isd = this.indicatorSettings;

        if (this.klineData.empty) {
            this.logger.warn(`${NEON_YELLOW}[${this.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.${RESET}`);
            return ["HOLD", 0.0];
        }

        const currentClose = new Decimal(String(this.klineData.get(-1).close));
        const prevClose = new Decimal(String(this.klineData.length > 1 ? this.klineData.get(-2).close : currentClose));

        // EMA Alignment
        if (activeIndicators.ema_alignment) {
            const emaShort = this._getIndicatorValue("EMA_Short");
            const emaLong = this._getIndicatorValue("EMA_Long");
            if (!isNaN(emaShort) && !isNaN(emaLong)) {
                if (emaShort > emaLong) {
                    signalScore += weights.ema_alignment || 0;
                } else if (emaShort < emaLong) {
                    signalScore -= weights.ema_alignment || 0;
                }
            }
        }

        // SMA Trend Filter
        if (activeIndicators.sma_trend_filter) {
            const smaLong = this._getIndicatorValue("SMA_Long");
            if (!isNaN(smaLong)) {
                if (currentClose.gt(smaLong)) {
                    signalScore += weights.sma_trend_filter || 0;
                } else if (currentClose.lt(smaLong)) {
                    signalScore -= weights.sma_trend_filter || 0;
                }
            }
        }

        // Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
        if (activeIndicators.momentum) {
            const momentumWeight = weights.momentum_rsi_stoch_cci_wr_mfi || 0;

            // RSI
            if (activeIndicators.rsi) {
                const rsi = this._getIndicatorValue("RSI");
                if (!isNaN(rsi)) {
                    if (rsi < isd.rsi_oversold) {
                        signalScore += momentumWeight * 0.5;
                    } else if (rsi > isd.rsi_overbought) {
                        signalScore -= momentumWeight * 0.5;
                    }
                }
            }

            // StochRSI Crossover
            if (activeIndicators.stoch_rsi) {
                const stochK = this._getIndicatorValue("StochRSI_K");
                const stochD = this._getIndicatorValue("StochRSI_D");
                if (!isNaN(stochK) && !isNaN(stochD) && this.klineData.length > 1) {
                    const prevStochK = this.klineData.get(-2).StochRSI_K;
                    const prevStochD = this.klineData.get(-2).StochRSI_D;
                    if (
                        stochK > stochD &&
                        (isNaN(prevStochK) || prevStochK <= prevStochD) &&
                        stochK < isd.stoch_rsi_oversold
                    ) {
                        signalScore += momentumWeight * 0.6;
                        this.logger.debug(`[${this.symbol}] StochRSI: Bullish crossover from oversold.`);
                    } else if (
                        stochK < stochD &&
                        (isNaN(prevStochK) || prevStochK >= prevStochD) &&
                        stochK > isd.stoch_rsi_overbought
                    ) {
                        signalScore -= momentumWeight * 0.6;
                        this.logger.debug(`[${this.symbol}] StochRSI: Bearish crossover from overbought.`);
                    } else if (stochK > stochD && stochK < 50) {
                        signalScore += momentumWeight * 0.2;
                    } else if (stochK < stochD && stochK > 50) {
                        signalScore -= momentumWeight * 0.2;
                    }
                }
            }

            // CCI
            if (activeIndicators.cci) {
                const cci = this._getIndicatorValue("CCI");
                if (!isNaN(cci)) {
                    if (cci < isd.cci_oversold) {
                        signalScore += momentumWeight * 0.4;
                    } else if (cci > isd.cci_overbought) {
                        signalScore -= momentumWeight * 0.4;
                    }
                }
            }

            // Williams %R
            if (activeIndicators.wr) {
                const wr = this._getIndicatorValue("WR");
                if (!isNaN(wr)) {
                    if (wr < isd.williams_r_oversold) {
                        signalScore += momentumWeight * 0.4;
                    } else if (wr > isd.williams_r_overbought) {
                        signalScore -= momentumWeight * 0.4;
                    }
                }
            }

            // MFI
            if (activeIndicators.mfi) {
                const mfi = this._getIndicatorValue("MFI");
                if (!isNaN(mfi)) {
                    if (mfi < isd.mfi_oversold) {
                        signalScore += momentumWeight * 0.4;
                    } else if (mfi > isd.mfi_overbought) {
                        signalScore -= momentumWeight * 0.4;
                    }
                }
            }
        }

        // Bollinger Bands
        if (activeIndicators.bollinger_bands) {
            const bbUpper = this._getIndicatorValue("BB_Upper");
            const bbLower = this._getIndicatorValue("BB_Lower");
            if (!isNaN(bbUpper) && !isNaN(bbLower)) {
                if (currentClose.lt(bbLower)) {
                    signalScore += (weights.bollinger_bands || 0) * 0.5;
                } else if (currentClose.gt(bbUpper)) {
                    signalScore -= (weights.bollinger_bands || 0) * 0.5;
                }
            }
        }

        // VWAP
        if (activeIndicators.vwap) {
            const vwap = this._getIndicatorValue("VWAP");
            if (!isNaN(vwap)) {
                if (currentClose.gt(vwap)) {
                    signalScore += (weights.vwap || 0) * 0.2;
                } else if (currentClose.lt(vwap)) {
                    signalScore -= (weights.vwap || 0) * 0.2;
                }

                if (this.klineData.length > 1 && !isNaN(this.klineData.get(-2).VWAP)) {
                    const prevVwap = new Decimal(String(this.klineData.get(-2).VWAP));
                    if (currentClose.gt(vwap) && prevClose.lte(prevVwap)) {
                        signalScore += (weights.vwap || 0) * 0.3;
                        this.logger.debug(`[${this.symbol}] VWAP: Bullish crossover detected.`);
                    } else if (currentClose.lt(vwap) && prevClose.gte(prevVwap)) {
                        signalScore -= (weights.vwap || 0) * 0.3;
                        this.logger.debug(`[${this.symbol}] VWAP: Bearish crossover detected.`);
                    }
                }
            }
        }

        // PSAR
        if (activeIndicators.psar) {
            const psarVal = this._getIndicatorValue("PSAR_Val");
            const psarDir = this._getIndicatorValue("PSAR_Dir");
            if (!isNaN(psarVal) && !isNaN(psarDir)) {
                if (psarDir === 1) {
                    signalScore += (weights.psar || 0) * 0.5;
                } else if (psarDir === -1) {
                    signalScore -= (weights.psar || 0) * 0.5;
                }

                if (this.klineData.length > 1 && !isNaN(this.klineData.get(-2).PSAR_Val)) {
                    const prevPsarVal = new Decimal(String(this.klineData.get(-2).PSAR_Val));
                    if (currentClose.gt(psarVal) && prevClose.lte(prevPsarVal)) {
                        signalScore += (weights.psar || 0) * 0.4;
                        this.logger.debug("PSAR: Bullish reversal detected.");
                    } else if (currentClose.lt(psarVal) && prevClose.gte(prevPsarVal)) {
                        signalScore -= (weights.psar || 0) * 0.4;
                        this.logger.debug("PSAR: Bearish reversal detected.");
                    }
                }
            }
        }

        // Orderbook Imbalance
        if (activeIndicators.orderbook_imbalance && orderbookData) {
            const imbalance = this._checkOrderbook(current_price, orderbookData);
            signalScore += imbalance * (weights.orderbook_imbalance || 0);
        }

        // Fibonacci Levels (confluence with price action)
        if (activeIndicators.fibonacci_levels && Object.keys(this.fibLevels).length > 0) {
            for (const levelName in this.fibLevels) {
                const levelPrice = this.fibLevels[levelName];
                if (levelName !== "0.0%" && levelName !== "100.0%" &&
                    current_price.sub(levelPrice).abs().div(current_price).lt(new Decimal("0.001"))) {
                    this.logger.debug(`Price near Fibonacci level ${levelName}: ${levelPrice}`);
                    if (this.klineData.length > 1) {
                        if (currentClose.gt(prevClose) && currentClose.gt(levelPrice)) {
                            signalScore += (weights.fibonacci_levels || 0) * 0.1;
                        } else if (currentClose.lt(prevClose) && currentClose.lt(levelPrice)) {
                            signalScore -= (weights.fibonacci_levels || 0) * 0.1;
                        }
                    }
                }
            }
        }

        // --- Ehlers SuperTrend Alignment Scoring ---
        if (activeIndicators.ehlers_supertrend) {
            const stFastDir = this._getIndicatorValue("ST_Fast_Dir");
            const stSlowDir = this._getIndicatorValue("ST_Slow_Dir");
            const prevStFastDir = (this.klineData.length > 1 && this.klineData.get(-2).st_fast_dir !== undefined) ? this.klineData.get(-2).st_fast_dir : NaN;
            const weight = weights.ehlers_supertrend_alignment || 0.0;

            if (!isNaN(stFastDir) && !isNaN(stSlowDir) && !isNaN(prevStFastDir)) {
                if (stSlowDir === 1 && stFastDir === 1 && prevStFastDir === -1) {
                    signalScore += weight;
                    this.logger.debug("Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).");
                } else if (stSlowDir === -1 && stFastDir === -1 && prevStFastDir === 1) {
                    signalScore -= weight;
                    this.logger.debug("Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).");
                } else if (stSlowDir === 1 && stFastDir === 1) {
                    signalScore += weight * 0.3;
                } else if (stSlowDir === -1 && stFastDir === -1) {
                    signalScore -= weight * 0.3;
                }
            }
        }

        // --- MACD Alignment Scoring ---
        if (activeIndicators.macd) {
            const macdLine = this._getIndicatorValue("MACD_Line");
            const signalLine = this._getIndicatorValue("MACD_Signal");
            const histogram = this._getIndicatorValue("MACD_Hist");
            const weight = weights.macd_alignment || 0.0;

            if (!isNaN(macdLine) && !isNaN(signalLine) && !isNaN(histogram) && this.klineData.length > 1) {
                const prevMacdLine = this.klineData.get(-2).MACD_Line;
                const prevSignalLine = this.klineData.get(-2).MACD_Signal;
                const prevHistogram = this.klineData.get(-2).MACD_Hist;

                if (macdLine > signalLine && prevMacdLine <= prevSignalLine) {
                    signalScore += weight;
                    this.logger.debug("MACD: BUY signal (MACD line crossed above Signal line).");
                } else if (macdLine < signalLine && prevMacdLine >= prevSignalLine) {
                    signalScore -= weight;
                    this.logger.debug("MACD: SELL signal (MACD line crossed below Signal line).");
                } else if (histogram > 0 && prevHistogram <= 0) {
                    signalScore += weight * 0.2;
                } else if (histogram < 0 && prevHistogram >= 0) {
                    signalScore -= weight * 0.2;
                }
            }
        }

        // --- ADX Alignment Scoring ---
        if (activeIndicators.adx) {
            const adxVal = this._getIndicatorValue("ADX");
            const plusDi = this._getIndicatorValue("PlusDI");
            const minusDi = this._getIndicatorValue("MinusDI");
            const weight = weights.adx_strength || 0.0;

            if (!isNaN(adxVal) && !isNaN(plusDi) && !isNaN(minusDi)) {
                if (adxVal > ADX_STRONG_TREND_THRESHOLD) {
                    if (plusDi > minusDi) {
                        signalScore += weight;
                        this.logger.debug("ADX: Strong BUY trend (ADX > 25, +DI > -DI).");
                    } else if (minusDi > plusDi) {
                        signalScore -= weight;
                        this.logger.debug("ADX: Strong SELL trend (ADX > 25, -DI > +DI).");
                    }
                } else if (adxVal < ADX_WEAK_TREND_THRESHOLD) {
                    signalScore += 0;
                    this.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.");
                }
            }
        }

        // --- Ichimoku Cloud Alignment Scoring ---
        if (activeIndicators.ichimoku_cloud) {
            const tenkanSen = this._getIndicatorValue("Tenkan_Sen");
            const kijunSen = this._getIndicatorValue("Kijun_Sen");
            const senkouSpanA = this._getIndicatorValue("Senkou_Span_A");
            const senkouSpanB = this._getIndicatorValue("Senkou_Span_B");
            const chikouSpan = this._getIndicatorValue("Chikou_Span");
            const weight = weights.ichimoku_confluence || 0.0;

            if (
                !isNaN(tenkanSen) && !isNaN(kijunSen) && !isNaN(senkouSpanA) &&
                !isNaN(senkouSpanB) && !isNaN(chikouSpan) && this.klineData.length > 1
            ) {
                const prevTenkanSen = this.klineData.get(-2).Tenkan_Sen;
                const prevKijunSen = this.klineData.get(-2).Kijun_Sen;
                const prevSenkouSpanA = this.klineData.get(-2).Senkou_Span_A;
                const prevSenkouSpanB = this.klineData.get(-2).Senkou_Span_B;
                const prevChikouSpan = this.klineData.get(-2).Chikou_Span;

                if (tenkanSen > kijunSen && prevTenkanSen <= prevKijunSen) {
                    signalScore += weight * 0.5;
                    this.logger.debug("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).");
                } else if (tenkanSen < kijunSen && prevTenkanSen >= prevKijunSen) {
                    signalScore -= weight * 0.5;
                    this.logger.debug("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).");
                }

                if (currentClose.gt(Math.max(senkouSpanA, senkouSpanB)) && prevClose.lte(Math.max(prevSenkouSpanA, prevSenkouSpanB))) {
                    signalScore += weight * 0.7;
                    this.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).");
                } else if (currentClose.lt(Math.min(senkouSpanA, senkouSpanB)) && prevClose.gte(Math.min(prevSenkouSpanA, prevSenkouSpanB))) {
                    signalScore -= weight * 0.7;
                    this.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).");
                }

                if (chikouSpan > currentClose.toNumber() && (isNaN(prevChikouSpan) || prevChikouSpan <= prevClose.toNumber())) { // currentClose is Decimal
                    signalScore += weight * 0.3;
                    this.logger.debug("Ichimoku: Chikou Span crossed above price (bullish confirmation).");
                } else if (chikouSpan < currentClose.toNumber() && (isNaN(prevChikouSpan) || prevChikouSpan >= prevClose.toNumber())) {
                    signalScore -= weight * 0.3;
                    this.logger.debug("Ichimoku: Chikou Span crossed below price (bearish confirmation).");
                }
            }
        }

        // --- OBV Alignment Scoring ---
        if (activeIndicators.obv) {
            const obvVal = this._getIndicatorValue("OBV");
            const obvEma = this._getIndicatorValue("OBV_EMA");
            const weight = weights.obv_momentum || 0.0;

            if (!isNaN(obvVal) && !isNaN(obvEma) && this.klineData.length > 1) {
                const prevObvVal = this.klineData.get(-2).OBV;
                const prevObvEma = this.klineData.get(-2).OBV_EMA;

                if (obvVal > obvEma && prevObvVal <= prevObvEma) {
                    signalScore += weight * 0.5;
                    this.logger.debug("OBV: Bullish crossover detected.");
                } else if (obvVal < obvEma && prevObvVal >= prevObvEma) {
                    signalScore -= weight * 0.5;
                    this.logger.debug("OBV: Bearish crossover detected.");
                }

                if (this.klineData.length > 2) {
                    const prevPrevObvVal = this.klineData.get(-3).OBV;
                    if (obvVal > prevObvVal && prevObvVal > prevPrevObvVal) {
                        signalScore += weight * 0.2;
                    } else if (obvVal < prevObvVal && prevObvVal < prevPrevObvVal) {
                        signalScore -= weight * 0.2;
                    }
                }
            }
        }

        // --- CMF Alignment Scoring ---
        if (activeIndicators.cmf) {
            const cmfVal = this._getIndicatorValue("CMF");
            const weight = weights.cmf_flow || 0.0;

            if (!isNaN(cmfVal)) {
                if (cmfVal > 0) {
                    signalScore += weight * 0.5;
                } else if (cmfVal < 0) {
                    signalScore -= weight * 0.5;
                }

                if (this.klineData.length > 2) {
                    const prevCmfVal = this.klineData.get(-2).CMF;
                    const prevPrevCmfVal = this.klineData.get(-3).CMF;
                    if (cmfVal > prevCmfVal && prevCmfVal > prevPrevCmfVal) {
                        signalScore += weight * 0.3;
                    } else if (cmfVal < prevCmfVal && prevCmfVal < prevPrevCmfVal) {
                        signalScore -= weight * 0.3;
                    }
                }
            }
        }

        // --- Volatility Index Scoring ---
        if (activeIndicators.volatility_index) {
            const volIdx = this._getIndicatorValue("Volatility_Index");
            const weight = weights.volatility_index_signal || 0.0;
            if (!isNaN(volIdx)) {
                if (this.klineData.length > 2 && this.klineData.get(-2).Volatility_Index !== undefined && this.klineData.get(-3).Volatility_Index !== undefined) {
                    const prevVolIdx = this.klineData.get(-2).Volatility_Index;
                    const prevPrevVolIdx = this.klineData.get(-3).Volatility_Index;

                    if (volIdx > prevVolIdx && prevVolIdx > prevPrevVolIdx) {
                        this.logger.debug("Volatility Index: Increasing volatility.");
                        if (signalScore > 0) {
                            signalScore += weight * 0.2;
                        } else if (signalScore < 0) {
                            signalScore -= weight * 0.2;
                        }
                    } else if (volIdx < prevVolIdx && prevVolIdx < prevPrevVolIdx) {
                        this.logger.debug("Volatility Index: Decreasing volatility.");
                        if (Math.abs(signalScore) > 0) {
                            signalScore *= 0.8;
                        }
                    }
                }
            }
        }

        // --- VWMA Cross Scoring ---
        if (activeIndicators.vwma) {
            const vwma = this._getIndicatorValue("VWMA");
            const weight = weights.vwma_cross || 0.0;
            if (!isNaN(vwma) && this.klineData.length > 1) {
                const prevVwma = this.klineData.get(-2).VWMA;
                if (currentClose.gt(vwma) && prevClose.lte(prevVwma)) {
                    signalScore += weight;
                    this.logger.debug("VWMA: Bullish crossover (price above VWMA).");
                } else if (currentClose.lt(vwma) && prevClose.gte(prevVwma)) {
                    signalScore -= weight;
                    this.logger.debug("VWMA: Bearish crossover (price below VWMA).");
                }
            }
        }

        // --- Volume Delta Scoring ---
        if (activeIndicators.volume_delta) {
            const volumeDelta = this._getIndicatorValue("Volume_Delta");
            const volumeDeltaThreshold = isd.volume_delta_threshold;
            const weight = weights.volume_delta_signal || 0.0;

            if (!isNaN(volumeDelta)) {
                if (volumeDelta > volumeDeltaThreshold) {
                    signalScore += weight;
                    this.logger.debug("Volume Delta: Strong buying pressure detected.");
                } else if (volumeDelta < -volumeDeltaThreshold) {
                    signalScore -= weight;
                    this.logger.debug("Volume Delta: Strong selling pressure detected.");
                } else if (volumeDelta > 0) {
                    signalScore += weight * 0.3;
                } else if (volumeDelta < 0) {
                    signalScore -= weight * 0.3;
                }
            }
        }


        // --- Multi-Timeframe Trend Confluence Scoring ---
        if (this.config.mtf_analysis.enabled && Object.keys(mtfTrends).length > 0) {
            let mtfBuyScore = 0;
            let mtfSellScore = 0;
            for (const _tfIndicator in mtfTrends) {
                const trend = mtfTrends[_tfIndicator];
                if (trend === "UP") {
                    mtfBuyScore += 1;
                } else if (trend === "DOWN") {
                    mtfSellScore += 1;
                }
            }

            const mtfWeight = weights.mtf_trend_confluence || 0.0;
            if (Object.keys(mtfTrends).length > 0) {
                const normalizedMtfScore = (mtfBuyScore - mtfSellScore) / Object.keys(mtfTrends).length;
                signalScore += mtfWeight * normalizedMtfScore;
                this.logger.debug(`MTF Confluence: Score ${normalizedMtfScore.toFixed(2)} (Buy: ${mtfBuyScore}, Sell: ${mtfSellScore}). Total MTF contribution: ${(mtfWeight * normalizedMtfScore).toFixed(2)}`);
            }
        }

        // --- Final Signal Determination ---
        const threshold = this.config.signal_score_threshold;
        let finalSignal = "HOLD";
        if (signalScore >= threshold) {
            finalSignal = "BUY";
        } else if (signalScore <= -threshold) {
            finalSignal = "SELL";
        }

        this.logger.info(`${NEON_YELLOW}Raw Signal Score: ${signalScore.toFixed(2)}, Final Signal: ${finalSignal}${RESET}`);
        return [finalSignal, signalScore];
    }

    calculateEntryTpSl(currentPrice, atrValue, signal) {
        const stopLossAtrMultiple = new Decimal(String(this.config.trade_management.stop_loss_atr_multiple));
        const takeProfitAtrMultiple = new Decimal(String(this.config.trade_management.take_profit_atr_multiple));
        const pricePrecisionStr = "1e-" + this.config.trade_management.price_precision;

        let stopLoss, takeProfit;
        if (signal === "BUY") {
            stopLoss = currentPrice.sub(atrValue.mul(stopLossAtrMultiple));
            takeProfit = currentPrice.add(atrValue.mul(takeProfitAtrMultiple));
        } else if (signal === "SELL") {
            stopLoss = currentPrice.add(atrValue.mul(stopLossAtrMultiple));
            takeProfit = currentPrice.sub(atrValue.mul(takeProfitAtrMultiple));
        } else {
            return [new Decimal("0"), new Decimal("0")]; // Should not happen for valid signals
        }

        return [
            takeProfit.toDecimalPlaces(this.config.trade_management.price_precision, Decimal.ROUND_DOWN),
            stopLoss.toDecimalPlaces(this.config.trade_management.price_precision, Decimal.ROUND_DOWN)
        ];
    }
}

function displayIndicatorValuesAndPrice(config, logger, currentPrice, klineData, orderbookData, mtfTrends) {
    logger.info(`${NEON_BLUE}--- Current Market Data & Indicators ---${RESET}`);
    logger.info(`${NEON_GREEN}Current Price: ${currentPrice.toDecimalPlaces(config.trade_management.price_precision, Decimal.ROUND_HALF_UP)}${RESET}`);

    const analyzer = new TradingAnalyzer(klineData, config, logger, config.symbol);

    if (analyzer.klineData.empty) {
        logger.warn(`${NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.${RESET}`);
        return;
    }

    logger.info(`${NEON_CYAN}--- Indicator Values ---${RESET}`);
    for (const indicatorName in analyzer.indicatorValues) {
        const value = analyzer.indicatorValues[indicatorName];
        const color = INDICATOR_COLORS[indicatorName] || NEON_YELLOW;
        if (value instanceof Decimal) {
            logger.info(`  ${color}${indicatorName}: ${value.toDecimalPlaces(8, Decimal.ROUND_HALF_UP)}${RESET}`);
        } else if (typeof value === 'number' && !isNaN(value)) {
            logger.info(`  ${color}${indicatorName}: ${value.toFixed(8)}${RESET}`);
        } else {
            logger.info(`  ${color}${indicatorName}: ${value}${RESET}`);
        }
    }

    if (Object.keys(analyzer.fibLevels).length > 0) {
        logger.info(`${NEON_CYAN}--- Fibonacci Levels ---${RESET}`);
        logger.info("");
        for (const levelName in analyzer.fibLevels) {
            const levelPrice = analyzer.fibLevels[levelName];
            logger.info(`  ${NEON_YELLOW}${levelName}: ${levelPrice.toDecimalPlaces(config.trade_management.price_precision, Decimal.ROUND_HALF_UP)}${RESET}`);
        }
    }

    if (Object.keys(mtfTrends).length > 0) {
        logger.info(`${NEON_CYAN}--- Multi-Timeframe Trends ---${RESET}`);
        logger.info("");
        for (const tfIndicator in mtfTrends) {
            const trend = mtfTrends[tfIndicator];
            logger.info(`  ${NEON_YELLOW}${tfIndicator}: ${trend}${RESET}`);
        }
    }

    logger.info(`${NEON_BLUE}--------------------------------------${RESET}`);
}


// --- Main Execution Logic ---
async function main() {
    const logger = setupLogger("wgwhalex_bot");
    const config = loadConfig(CONFIG_FILE, logger);
    const alertSystem = new AlertSystem(logger);

    // Validate interval format at startup
    const validBybitIntervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M",
    ];

    if (!validBybitIntervals.includes(config.interval)) {
        logger.error(`${NEON_RED}Invalid primary interval '${config.interval}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.${RESET}`);
        process.exit(1);
    }

    for (const htfInterval of config.mtf_analysis.higher_timeframes) {
        if (!validBybitIntervals.includes(htfInterval)) {
            logger.error(`${NEON_RED}Invalid higher timeframe interval '${htfInterval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.${RESET}`);
            process.exit(1);
        }
    }

    logger.info(`${NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---${RESET}`);
    logger.info(`Symbol: ${config.symbol}, Interval: ${config.interval}`);
    logger.info(`Trade Management Enabled: ${config.trade_management.enabled}`);

    const positionManager = new PositionManager(config, logger, config.symbol);
    const performanceTracker = new PerformanceTracker(logger);

    while (true) {
        try {
            logger.info(`${NEON_PURPLE}--- New Analysis Loop Started (${new Date().toISOString()}) ---${RESET}`);
            const currentPrice = await fetchCurrentPrice(config.symbol, logger);
            if (currentPrice === null) {
                alertSystem.sendAlert(`[${config.symbol}] Failed to fetch current price. Skipping loop.`, "WARNING");
                await timeout(config.loop_delay * 1000);
                continue;
            }

            const klineData = await fetchKlines(config.symbol, config.interval, 1000, logger);
            if (klineData === null || klineData.empty) {
                alertSystem.sendAlert(`[${config.symbol}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.`, "WARNING");
                await timeout(config.loop_delay * 1000);
                continue;
            }

            let orderbookData = null;
            if (config.indicators.orderbook_imbalance) {
                orderbookData = await fetchOrderbook(config.symbol, config.orderbook_limit, logger);
            }

            const mtfTrends = {};
            if (config.mtf_analysis.enabled) {
                for (const htfInterval of config.mtf_analysis.higher_timeframes) {
                    logger.debug(`Fetching klines for MTF interval: ${htfInterval}`);
                    const htfKlineData = await fetchKlines(config.symbol, htfInterval, 1000, logger);
                    if (htfKlineData !== null && !htfKlineData.empty) {
                        for (const trendInd of config.mtf_analysis.trend_indicators) {
                            const tempHtfAnalyzer = new TradingAnalyzer(htfKlineData, config, logger, config.symbol);
                            const trend = tempHtfAnalyzer._getMtfTrend(tempHtfAnalyzer.klineData, trendInd);
                            mtfTrends[`${htfInterval}_${trendInd}`] = trend;
                            logger.debug(`MTF Trend (${htfInterval}, ${trendInd}): ${trend}`);
                        }
                    } else {
                        logger.warn(`${NEON_YELLOW}Could not fetch klines for higher timeframe ${htfInterval} or it was empty. Skipping MTF trend for this TF.${RESET}`);
                    }
                    await timeout(config.mtf_analysis.mtf_request_delay_seconds * 1000);
                }
            }

            displayIndicatorValuesAndPrice(config, logger, currentPrice, klineData, orderbookData, mtfTrends);

            const analyzer = new TradingAnalyzer(klineData, config, logger, config.symbol);

            if (analyzer.klineData.empty) {
                alertSystem.sendAlert(`[${config.symbol}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.`, "WARNING");
                await timeout(config.loop_delay * 1000);
                continue;
            }

            const [tradingSignal, signalScore] = analyzer.generateTradingSignal(currentPrice, orderbookData, mtfTrends);
            const atrValue = new Decimal(String(analyzer._getIndicatorValue("ATR", 0.01)));

            positionManager.managePositions(currentPrice, performanceTracker);

            if (tradingSignal === "BUY" && signalScore >= config.signal_score_threshold) {
                logger.info(`${NEON_GREEN}Strong BUY signal detected! Score: ${signalScore.toFixed(2)}${RESET}`);
                positionManager.openPosition("BUY", currentPrice, atrValue);
            } else if (tradingSignal === "SELL" && signalScore <= -config.signal_score_threshold) {
                logger.info(`${NEON_RED}Strong SELL signal detected! Score: ${signalScore.toFixed(2)}${RESET}`);
                positionManager.openPosition("SELL", currentPrice, atrValue);
            } else {
                logger.info(`${NEON_BLUE}No strong trading signal. Holding. Score: ${signalScore.toFixed(2)}${RESET}`);
            }

            const openPositions = positionManager.getOpenPositions();
            if (openPositions.length > 0) {
                logger.info(`${NEON_CYAN}Open Positions: ${openPositions.length}${RESET}`);
                for (const pos of openPositions) {
                    logger.info(`  - ${pos.side} @ ${pos.entry_price} (SL: ${pos.stop_loss}, TP: ${pos.take_profit})${RESET}`);
                }
            } else {
                logger.info(`${NEON_CYAN}No open positions.${RESET}`);
            }

            const perfSummary = performanceTracker.getSummary();
            logger.info(`${NEON_YELLOW}Performance Summary: Total PnL: ${perfSummary.total_pnl.toDecimalPlaces(2, Decimal.ROUND_DOWN)}, Wins: ${perfSummary.wins}, Losses: ${perfSummary.losses}, Win Rate: ${perfSummary.win_rate}${RESET}`);

            logger.info(`${NEON_PURPLE}--- Analysis Loop Finished. Waiting ${config.loop_delay}s ---${RESET}`);
            await timeout(config.loop_delay * 1000);

        } catch (e) {
            alertSystem.sendAlert(`[${config.symbol}] An unhandled error occurred in the main loop: ${e.message}`, "ERROR");
            logger.error(`${NEON_RED}Unhandled exception in main loop: ${e.stack}${RESET}`);
            await timeout(config.loop_delay * 2 * 1000);
        }
    }
}

if (require.main === module) {
    main();
}
