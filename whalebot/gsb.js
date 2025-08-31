// Import Node.js native modules and third-party libraries
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { URLSearchParams } = require('url'); // For URL encoding
const process = require('process'); // For process.env and process.exit
const { Buffer } = require('buffer'); // For base64 encoding/decoding

// Third-party libraries
require('dotenv').config(); // For .env file loading
const axios = require('axios'); // For HTTP requests
const axiosRetry = require('axios-retry'); // For request retries
const df = require('danfo.js'); // For DataFrame operations (Pandas equivalent)
const Decimal = require('decimal.js'); // For high-precision arithmetic
const { DateTime, Settings } = require('luxon'); // For date/time and timezones
const { GoogleGenerativeAI } = require('@google/generative-ai'); // For Gemini AI
const { ChartJSNodeCanvas } = require('chartjs-node-canvas'); // For server-side chart generation
const { Chart, registerables } = require('chart.js'); // Required by ChartJSNodeCanvas

Chart.register(...registerables); // Register all chart.js components

// Global decimal precision setting
Decimal.set({ precision: 28, rounding: Decimal.ROUND_DOWN });

// --- Colorama equivalent for console output ---
// ANSI escape codes for colors
const RESET = "\x1b[0m";
const NEON_GREEN = "\x1b[92m"; // Light Green
const NEON_BLUE = "\x1b[96m";  // Cyan
const NEON_PURPLE = "\x1b[95m"; // Magenta
const NEON_YELLOW = "\x1b[93m"; // Yellow
const NEON_RED = "\x1b[91m";   // Light Red
const NEON_CYAN = "\x1b[96m"; // Cyan (duplicate for consistency with Python)
const Fore = {
    LIGHTGREEN_EX: NEON_GREEN,
    CYAN: NEON_CYAN,
    MAGENTA: NEON_PURPLE,
    YELLOW: NEON_YELLOW,
    LIGHTRED_EX: NEON_RED,
    BLUE: "\x1b[34m", // Blue
    LIGHTBLUE_EX: "\x1b[94m", // Light Blue
    WHITE: "\x1b[37m", // White
    GREEN: "\x1b[32m", // Green
    RED: "\x1b[31m", // Red
};
const Style = {
    RESET_ALL: RESET,
};

// Indicator specific colors (translated from Python)
const INDICATOR_COLORS = {
    "SMA_10": Fore.LIGHTBLUE_EX,
    "SMA_Long": Fore.BLUE,
    "EMA_Short": Fore.MAGENTA, // Using MAGENTA as LIGHTMAGENTA_EX not standard ANSI
    "EMA_Long": Fore.MAGENTA,
    "ATR": Fore.YELLOW,
    "RSI": Fore.GREEN,
    "StochRSI_K": Fore.CYAN,
    "StochRSI_D": Fore.CYAN, // Using CYAN as LIGHTCYAN_EX not standard ANSI
    "BB_Upper": Fore.RED,
    "BB_Middle": Fore.WHITE,
    "BB_Lower": Fore.RED,
    "CCI": Fore.LIGHTGREEN_EX,
    "WR": Fore.LIGHTRED_EX,
    "MFI": Fore.GREEN,
    "OBV": Fore.BLUE,
    "OBV_EMA": Fore.LIGHTBLUE_EX,
    "CMF": Fore.MAGENTA,
    "Tenkan_Sen": Fore.CYAN,
    "Kijun_Sen": Fore.CYAN, // Using CYAN as LIGHTCYAN_EX not standard ANSI
    "Senkou_Span_A": Fore.GREEN,
    "Senkou_Span_B": Fore.RED,
    "Chikou_Span": Fore.YELLOW,
    "PSAR_Val": Fore.MAGENTA,
    "PSAR_Dir": Fore.MAGENTA, // Using MAGENTA as LIGHTMAGENTA_EX not standard ANSI
    "VWAP": Fore.WHITE,
    "ST_Fast_Dir": Fore.BLUE,
    "ST_Fast_Val": Fore.LIGHTBLUE_EX,
    "ST_Slow_Dir": Fore.MAGENTA,
    "ST_Slow_Val": Fore.MAGENTA,
    "MACD_Line": Fore.GREEN,
    "MACD_Signal": Fore.LIGHTGREEN_EX,
    "MACD_Hist": Fore.YELLOW,
    "ADX": Fore.CYAN,
    "PlusDI": Fore.CYAN, // Using CYAN as LIGHTCYAN_EX not standard ANSI
    "MinusDI": Fore.RED,
};

// --- Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs";

// Ensure log directory exists
if (!fs.existsSync(LOG_DIRECTORY)) {
    fs.mkdirSync(LOG_DIRECTORY, { recursive: true });
}

// Luxon setup for timezone
const TIMEZONE = "America/Chicago";
Settings.defaultZone = TIMEZONE;

const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000; // milliseconds

const LOOP_DELAY_SECONDS = 15;

// Magic Numbers as Constants
const MIN_DATA_POINTS_TR = 2;
const MIN_DATA_POINTS_SMOOTHER = 2;
const MIN_DATA_POINTS_OBV = 2;
const MIN_DATA_POINTS_PSAR = 2;
const ADX_STRONG_TREND_THRESHOLD = 25;
const ADX_WEAK_TREND_THRESHOLD = 20;

// --- Logger Setup ---
// Simple custom logger to mimic Python's RotatingFileHandler and SensitiveFormatter
class SensitiveFormatter {
    constructor(formatString) {
        this.formatString = formatString;
        this.sensitiveWords = ["API_KEY", "API_SECRET", "GEMINI_API_KEY"];
    }

    format(level, name, message) {
        let formattedMessage = this.formatString
            .replace('%(asctime)s', DateTime.now().setZone(TIMEZONE).toFormat("yyyy-MM-dd HH:mm:ss,SSS"))
            .replace('%(name)s', name)
            .replace('%(levelname)s', level)
            .replace('%(message)s', message);

        for (const word of this.sensitiveWords) {
            const envValue = process.env[word];
            if (envValue) {
                formattedMessage = formattedMessage.replace(new RegExp(envValue.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(envValue.length));
            }
            formattedMessage = formattedMessage.replace(new RegExp(word, 'g'), '*'.repeat(word.length));
        }
        return formattedMessage;
    }
}

class CustomLogger {
    constructor(logName, level = 'INFO') {
        this.logName = logName;
        this.logLevel = this._getLevelValue(level);
        this.consoleFormatter = new SensitiveFormatter(`${NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s${RESET}`);
        this.fileFormatter = new SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s");
        this.logFilePath = path.join(LOG_DIRECTORY, `${logName}.log`);
        this.maxBytes = 10 * 1024 * 1024; // 10 MB
        this.backupCount = 5;
    }

    _getLevelValue(level) {
        const levels = {
            'DEBUG': 1,
            'INFO': 2,
            'WARNING': 3,
            'ERROR': 4,
            'CRITICAL': 5,
        };
        return levels[level.toUpperCase()] || 2;
    }

    _log(level, message, color = '') {
        const levelValue = this._getLevelValue(level);
        if (levelValue < this.logLevel) {
            return;
        }

        const consoleOutput = this.consoleFormatter.format(level, this.logName, message);
        console.log(color + consoleOutput + RESET);

        const fileOutput = this.fileFormatter.format(level, this.logName, message);
        this._writeToFile(fileOutput);
    }

    _writeToFile(message) {
        if (!fs.existsSync(this.logFilePath)) {
            fs.writeFileSync(this.logFilePath, message + '\n');
            return;
        }

        const stats = fs.statSync(this.logFilePath);
        if (stats.size > this.maxBytes) {
            this._rotateLogs();
        }
        fs.appendFileSync(this.logFilePath, message + '\n');
    }

    _rotateLogs() {
        for (let i = this.backupCount - 1; i >= 0; i--) {
            const oldPath = i === 0 ? this.logFilePath : `${this.logFilePath}.${i}`;
            const newPath = `${this.logFilePath}.${i + 1}`;
            if (fs.existsSync(oldPath)) {
                fs.renameSync(oldPath, newPath);
            }
        }
    }

    debug(message) { this._log('DEBUG', message); }
    info(message) { this._log('INFO', message); }
    warning(message) { this._log('WARNING', message, NEON_YELLOW); }
    error(message) { this._log('ERROR', message, NEON_RED); }
    critical(message) { this._log('CRITICAL', message, NEON_RED); }
    exception(message) { this._log('ERROR', message, NEON_RED); } // For mimicking Python's exception logging
}

const loggers = {}; // To prevent duplicate loggers

function setupLogger(logName, level = 'INFO') {
    if (!loggers[logName]) {
        loggers[logName] = new CustomLogger(logName, level);
    }
    return loggers[logName];
}

// --- Axios Session with Retry Logic ---
function createSession() {
    const session = axios.create({
        timeout: REQUEST_TIMEOUT,
        headers: {
            'Content-Type': 'application/json',
        },
    });

    axiosRetry(session, {
        retries: MAX_API_RETRIES,
        retryDelay: (retryCount) => {
            return RETRY_DELAY_SECONDS * 1000;
        },
        retryCondition: (error) => {
            // Retry on network error or specific HTTP status codes
            return axiosRetry.isNetworkError(error) ||
                   [429, 500, 502, 503, 504].includes(error.response && error.response.status);
        },
    });
    return session;
}

// --- Bybit API Interaction ---
function generateSignature(payload, apiSecret) {
    return crypto.createHmac('sha256', apiSecret).update(payload).digest('hex');
}

async function bybitRequest(
    method,
    endpoint,
    params = {},
    signed = false,
    logger = setupLogger("bybit_api")
) {
    const session = createSession();
    const url = `${BASE_URL}${endpoint}`;
    let headers = {
        'Content-Type': 'application/json',
    };
    let requestConfig = {
        method: method,
        url: url,
        headers: headers,
        timeout: REQUEST_TIMEOUT,
    };

    if (signed) {
        if (!API_KEY || !API_SECRET) {
            logger.error(`${NEON_RED}API_KEY or API_SECRET not set for signed request.${RESET}`);
            return null;
        }

        const timestamp = String(Date.now());
        const recvWindow = "20000"; // 20 seconds

        let paramStr;
        if (method === "GET") {
            const queryString = new URLSearchParams(params).toString();
            paramStr = timestamp + API_KEY + recvWindow + queryString;
            requestConfig.params = params;
            logger.debug(`GET Request: ${url}?${queryString}`);
        } else { // POST
            const jsonParams = JSON.stringify(params);
            paramStr = timestamp + API_KEY + recvWindow + jsonParams;
            requestConfig.data = params; // For axios, data is for POST body
            logger.debug(`POST Request: ${url} with payload ${jsonParams}`);
        }

        const signature = generateSignature(paramStr, API_SECRET);
        requestConfig.headers = {
            ...requestConfig.headers,
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": recvWindow,
        };
    } else {
        requestConfig.params = params;
        logger.debug(`Public Request: ${url} with params ${JSON.stringify(params)}`);
    }

    try {
        const response = await session(requestConfig);
        const data = response.data;
        if (data.retCode !== 0) {
            logger.error(`${NEON_RED}Bybit API Error: ${data.retMsg} (Code: ${data.retCode})${RESET}`);
            return null;
        }
        return data;
    } catch (error) {
        if (error.response) {
            logger.error(`${NEON_RED}HTTP Error: ${error.response.status} - ${JSON.stringify(error.response.data)}${RESET}`);
        } else if (error.request) {
            logger.error(`${NEON_RED}No response received: ${error.message}${RESET}`);
        } else {
            logger.error(`${NEON_RED}Request setup error: ${error.message}${RESET}`);
        }
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
    logger.warning(`${NEON_YELLOW}Could not fetch current price for ${symbol}.${RESET}`);
    return null;
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
        // Ensure data is sorted oldest to newest for indicator calculations
        const sortedList = response.result.list.sort((a, b) => parseInt(a[0]) - parseInt(b[0]));

        const data = sortedList.map(item => ({
            start_time: DateTime.fromMillis(parseInt(item[0]), { zone: TIMEZONE }),
            open: new Decimal(item[1]),
            high: new Decimal(item[2]),
            low: new Decimal(item[3]),
            close: new Decimal(item[4]),
            volume: new Decimal(item[5]),
            turnover: new Decimal(item[6]),
        }));

        const df_result = new df.DataFrame(data);

        // Convert Decimal to numbers for danfo.js internal operations.
        // danfo.js handles numeric types best. Indicator calculations usually don't require Decimal until the final output.
        // It's crucial to convert back to Decimal when doing financial calculations (e.g., in PositionManager).
        const df_numeric = new df.DataFrame(df_result.columns.reduce((acc, col) => {
            if (['open', 'high', 'low', 'close', 'volume', 'turnover'].includes(col)) {
                acc[col] = df_result[col].values.map(d => d.toNumber());
            } else {
                acc[col] = df_result[col].values;
            }
            return acc;
        }, {}));
        df_numeric.setIndex(df_result['start_time'].values); // Use start_time as index

        if (df_numeric.empty) {
            logger.warning(
                `${NEON_YELLOW}Fetched klines for ${symbol} ${interval} but DataFrame is empty after processing. Raw response: ${JSON.stringify(response)}${RESET}`
            );
            return null;
        }

        logger.debug(`Fetched ${df_numeric.shape[0]} ${interval} klines for ${symbol}.`);
        return df_numeric;
    }
    logger.warning(
        `${NEON_YELLOW}Could not fetch klines for ${symbol} ${interval}. API response might be empty or invalid. Raw response: ${JSON.stringify(response)}${RESET}`
    );
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
    logger.warning(`${NEON_YELLOW}Could not fetch orderbook for ${symbol}.${RESET}`);
    return null;
}

// --- Configuration Loading ---
const DEFAULT_CONFIG = {
    // Core Settings
    "symbol": "BTCUSDT",
    "interval": "15", // Bybit's API uses string numbers for intervals
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
        "min_stop_loss_distance_ratio": 0.001 // 0.1% of price, to prevent too small SL
    },
    // Multi-Timeframe Analysis
    "mtf_analysis": {
        "enabled": true,
        "higher_timeframes": ["60", "240"], // Bybit's API uses string numbers
        "trend_indicators": ["ema", "ehlers_supertrend"],
        "trend_period": 50,
        "mtf_request_delay_seconds": 0.5,
    },
    // Machine Learning Enhancement (Explicitly excluded as per user request.)
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
    // Gemini AI Configuration
    "gemini_ai": {
        "enabled": true,
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-1.5-flash-latest",
        "min_confidence_for_override": 60, // Minimum AI confidence (0-100) to consider its signal for override
        "rate_limit_delay_seconds": 1.0,
        "cache_ttl_seconds": 300, // Cache duration for AI analysis
        "daily_api_limit": 1000, // Max calls per 24 hours
        "signal_weights": { // Weights for combining technical and AI scores
            "technical": 0.6,
            "ai": 0.4
        },
        "low_ai_confidence_threshold": 20, // If AI confidence below this, technical signal dominates
        "chart_image_analysis": {
            "enabled": false, // Set to true to enable chart image analysis with Gemini Vision (requires chartjs-node-canvas and canvas)
            "frequency_loops": 0, // Analyze chart image every N loops (0 to disable)
            "data_points_for_chart": 100, // Number of candles to plot for vision analysis
        }
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
        "obv_ema_period": 20, // For OBV EMA signal line
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
    },
    // Active Indicators & Weights
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
    },
    "weight_sets": {
        "default_scalping": {
            "ema_alignment": 0.22,
            "sma_trend_filter": 0.28,
            "momentum": 0.18,
            "volume_confirmation": 0.12,
            "stoch_rsi": 0.30,
            "rsi": 0.12,
            "bollinger_bands": 0.22,
            "vwap": 0.22,
            "cci": 0.08,
            "wr": 0.08,
            "psar": 0.22,
            "sma_10": 0.07,
            "mfi": 0.12,
            "orderbook_imbalance": 0.07,
            "ehlers_supertrend_alignment": 0.55,
            "macd_alignment": 0.28,
            "adx_strength": 0.18,
            "ichimoku_confluence": 0.38,
            "obv_momentum": 0.18,
            "cmf_flow": 0.12,
            "mtf_trend_confluence": 0.32,
        }
    },
};

function _ensureConfigKeys(config, defaultConfig) {
    for (const key in defaultConfig) {
        if (!config.hasOwnProperty(key)) {
            config[key] = defaultConfig[key];
        } else if (typeof defaultConfig[key] === 'object' && defaultConfig[key] !== null &&
                   !Array.isArray(defaultConfig[key]) && typeof config[key] === 'object' && config[key] !== null) {
            _ensureConfigKeys(config[key], defaultConfig[key]);
        }
    }
}

function loadConfig(filepath, logger) {
    if (!fs.existsSync(filepath)) {
        try {
            fs.writeFileSync(filepath, JSON.stringify(DEFAULT_CONFIG, null, 4), "utf-8");
            logger.warning(
                `${NEON_YELLOW}Configuration file not found. Created default config at ${filepath}${RESET}`
            );
            return DEFAULT_CONFIG;
        } catch (e) {
            logger.error(`${NEON_RED}Error creating default config file: ${e.message}${RESET}`);
            return DEFAULT_CONFIG;
        }
    }

    try {
        const config = JSON.parse(fs.readFileSync(filepath, "utf-8"));
        _ensureConfigKeys(config, DEFAULT_CONFIG); // Ensure all default keys are present
        fs.writeFileSync(filepath, JSON.stringify(config, null, 4), "utf-8"); // Save updated config
        return config;
    } catch (e) {
        logger.error(
            `${NEON_RED}Error loading config: ${e.message}. Using default and attempting to save.${RESET}`
        );
        try {
            fs.writeFileSync(filepath, JSON.stringify(DEFAULT_CONFIG, null, 4), "utf-8");
        } catch (e_save) {
            logger.error(`${NEON_RED}Could not save default config: ${e_save.message}${RESET}`);
        }
        return DEFAULT_CONFIG;
    }
}

// --- Gemini Signal Analyzer Class ---
class GeminiSignalAnalyzer {
    constructor(apiKey, logger, model = "gemini-1.5-flash-latest", config = {}) {
        this.logger = logger;
        this.model = model;
        this.config = config;

        // Initialize Gemini client
        try {
            this.client = new GoogleGenerativeAI(apiKey).getGenerativeModel({ model: this.model });
            this.logger.info(`${NEON_GREEN}Gemini API initialized with model: ${model}${RESET}`);
        } catch (e) {
            this.logger.error(`${NEON_RED}Failed to initialize Gemini API: ${e.message}${RESET}`);
            throw e;
        }

        // --- Caching ---
        this._analysis_cache = new Map(); // Map<string, [number, object]>
        this._cache_ttl = this.config.cache_ttl_seconds || 300; // Default 5 minutes

        // --- Performance Metrics Tracking ---
        this.performance_metrics = {
            'total_analyses': 0,
            'successful_analyses': 0,
            'api_errors': 0,
            'avg_response_time_ms': 0.0,
            'signal_accuracy': {}, // {signal_type: {'WIN': X, 'LOSS': Y, 'BREAKEVEN': Z, 'total': A}}
            'cache_hits': 0
        };

        // --- API Safety Checks and Limits ---
        this.daily_api_calls = 0;
        this.daily_limit = this.config.daily_api_limit || 1000; // Default 1000 calls
        this.last_reset = DateTime.now().setZone(TIMEZONE).toISODate(); // YYYY-MM-DD
    }

    _checkApiLimits() {
        const currentDate = DateTime.now().setZone(TIMEZONE).toISODate();
        if (currentDate > this.last_reset) {
            this.daily_api_calls = 0;
            this.last_reset = currentDate;
            this.logger.info("Daily API call count reset.");
        }

        if (this.daily_api_calls >= this.daily_limit) {
            this.logger.warning(`${NEON_YELLOW}Daily Gemini API limit (${this.daily_limit}) reached. Skipping AI analysis for today.${RESET}`);
            return false;
        }

        this.daily_api_calls += 1;
        return true;
    }

    _getCacheKey(marketSummary) {
        const keyData = {
            'symbol': marketSummary.symbol,
            'price_rounded': parseFloat(marketSummary.price_statistics?.current).toFixed(2),
            'indicators_summary': Object.fromEntries(
                Object.entries(marketSummary.technical_indicators || {})
                    .filter(([k]) => ['RSI', 'MACD_Hist', 'ADX'].includes(k))
                    .map(([k, v]) => [k, typeof v === 'number' ? v.toFixed(2) : v])
            ),
            'mtf_trends': JSON.stringify(Object.entries(marketSummary.multi_timeframe_trends || {}).sort())
        };
        return crypto.createHash('md5').update(JSON.stringify(keyData)).digest('hex');
    }

    async analyzeMarketContext(df_data, indicatorValues, currentPrice, symbol, mtfTrends) {
        if (!this._checkApiLimits()) {
            this.performance_metrics.api_errors++;
            return {
                "signal": "HOLD", "confidence": 0, "analysis": "API daily limit reached.",
                "risk_level": "HIGH", "market_sentiment": "NEUTRAL"
            };
        }

        const marketSummary = this._prepareMarketSummary(
            df_data, indicatorValues, currentPrice, symbol, mtfTrends
        );
        if (!marketSummary) {
            return {
                "signal": "HOLD", "confidence": 0, "analysis": "Insufficient data for market summary.",
                "risk_level": "HIGH", "market_sentiment": "NEUTRAL"
            };
        }

        const cacheKey = this._getCacheKey(marketSummary);

        // Check cache
        if (this._analysis_cache.has(cacheKey)) {
            const [cachedTime, cachedResult] = this._analysis_cache.get(cacheKey);
            if (Date.now() / 1000 - cachedTime < this._cache_ttl) {
                this.logger.debug(`Using cached Gemini analysis for key: ${cacheKey}`);
                this.performance_metrics.cache_hits++;
                return cachedResult;
            }
        }

        const startTime = process.hrtime.bigint();
        let result = {};
        try {
            const promptContent = this._createAnalysisPrompt(marketSummary);
            const contentsParts = [{ text: promptContent }];

            const response = await this.client.generateContent({
                contents: contentsParts,
                generationConfig: {
                    temperature: 0.3,
                    responseMimeType: "application/json"
                }
            });

            if (response.response.candidates && response.response.candidates[0].content.parts) {
                const jsonString = response.response.candidates[0].content.parts[0].text;
                result = JSON.parse(jsonString);
                this.logger.debug(`Gemini Analysis Raw Result: ${JSON.stringify(result)}`);
                this.logger.info(`Gemini Analysis Complete: Signal=${result.signal}, Confidence=${result.confidence}%`);
                this.performance_metrics.successful_analyses++;
            } else {
                this.logger.warning("Gemini API returned no content or candidates.");
                result = {
                    "signal": "HOLD", "confidence": 0, "analysis": "Gemini returned no content.",
                    "risk_level": "MEDIUM", "market_sentiment": "NEUTRAL"
                };
                this.performance_metrics.api_errors++;
            }
        } catch (e) {
            if (e instanceof SyntaxError) { // JSON decoding error
                this.logger.error(`${NEON_RED}Error decoding JSON from Gemini response: ${e.message}. Response: ${e.response ? e.response.text : 'N/A'}${RESET}`);
                result = {
                    "signal": "HOLD", "confidence": 0, "analysis": `JSON decoding error: ${e.message}`,
                    "risk_level": "HIGH", "market_sentiment": "NEUTRAL"
                };
            } else {
                this.logger.error(`${NEON_RED}Error in Gemini market analysis: ${e.message}${RESET}`);
                result = {
                    "signal": "HOLD", "confidence": 0, "analysis": `General error during AI analysis: ${e.message}`,
                    "risk_level": "HIGH", "market_sentiment": "NEUTRAL"
                };
            }
            this.performance_metrics.api_errors++;
        } finally {
            const endTime = process.hrtime.bigint();
            const responseTimeMs = Number(endTime - startTime) / 1_000_000;
            // Update average response time
            const nonCachedAnalyses = this.performance_metrics.total_analyses - this.performance_metrics.cache_hits;
            if (nonCachedAnalyses > 0) {
                this.performance_metrics.avg_response_time_ms =
                    (this.performance_metrics.avg_response_time_ms * nonCachedAnalyses + responseTimeMs) / (nonCachedAnalyses + 1);
            } else {
                this.performance_metrics.avg_response_time_ms = responseTimeMs;
            }
            this.performance_metrics.total_analyses++;
        }

        // Cache the result
        if (result && (result.signal !== "HOLD" || result.confidence > 0)) {
            this._analysis_cache.set(cacheKey, [Date.now() / 1000, result]);
        }
        return result;
    }

    _prepareMarketSummary(df_data, indicatorValues, currentPrice, symbol, mtfTrends) {
        const safeDf = df_data.copy();
        if (safeDf.empty) {
            this.logger.warning("DataFrame is empty, cannot prepare market summary.");
            return null;
        }

        // Convert Decimal to number for JSON serialization as Gemini API expects numbers
        const last96 = safeDf.tail(96);
        const lastClose96 = last96.iloc({rows: [-96]}).loc({columns: ['close']}).values[0][0];
        const lastClose = safeDf.iloc({rows: [-1]}).loc({columns: ['close']}).values[0][0];


        const priceStats = {
            "current": currentPrice.toNumber(),
            "24h_high": safeDf.high.tail(96).max().values[0],
            "24h_low": safeDf.low.tail(96).min().values[0],
            "24h_change_pct": ((currentPrice.minus(new Decimal(lastClose96))).div(new Decimal(lastClose96)).times(100)).toNumber(),
            "volume_24h": safeDf.volume.tail(96).sum().values[0],
            "avg_volume": safeDf.volume.tail(96).mean().values[0]
        };

        const formattedIndicators = {};
        for (const key in indicatorValues) {
            const value = indicatorValues[key];
            if (value instanceof Decimal) {
                formattedIndicators[key] = value.toNumber();
            } else if (typeof value === 'number' && isNaN(value)) {
                formattedIndicators[key] = null;
            } else {
                formattedIndicators[key] = value;
            }
        }

        const recentCandles = [];
        const numCandles = Math.min(5, safeDf.shape[0]);
        for (let i = 0; i < numCandles; i++) {
            const idx = safeDf.shape[0] - (i + 1);
            const candle = safeDf.iloc({ rows: [idx] });
            recentCandles.push({
                "open": candle.loc({ columns: ['open'] }).values[0][0],
                "high": candle.loc({ columns: ['high'] }).values[0][0],
                "low": candle.loc({ columns: ['low'] }).values[0][0],
                "close": candle.loc({ columns: ['close'] }).values[0][0],
                "volume": candle.loc({ columns: ['volume'] }).values[0][0]
            });
        }
        recentCandles.reverse(); // Newest first

        return {
            "symbol": symbol,
            "timestamp": DateTime.now().setZone(TIMEZONE).toISOString(),
            "price_statistics": priceStats,
            "technical_indicators": formattedIndicators,
            "multi_timeframe_trends": mtfTrends,
            "recent_candles": recentCandles,
            "market_conditions": this._detectMarketConditions(safeDf, formattedIndicators)
        };
    }

    _detectMarketConditions(df_data, indicatorValues) {
        const conditions = {
            "volatility": "NORMAL",
            "trend_strength": "NEUTRAL",
            "volume_profile": "AVERAGE"
        };

        if (df_data.empty) {
            return conditions;
        }

        const atr = indicatorValues.ATR;
        if (typeof atr === 'number' && !isNaN(atr)) {
            if (df_data.columns.includes("ATR") && df_data.shape[0] >= 20 && !df_data.ATR.isna().all().values[0]) {
                const recentAtrMean = df_data.ATR.tail(20).mean().values[0];
                if (atr > recentAtrMean * 1.5) {
                    conditions["volatility"] = "HIGH";
                } else if (atr < recentAtrMean * 0.5) {
                    conditions["volatility"] = "LOW";
                }
            } else if (df_data.shape[0] > 0) {
                const lastHigh = df_data.high.iloc({rows: [-1]}).values[0][0];
                const lastLow = df_data.low.iloc({rows: [-1]}).values[0][0];
                if (atr > (lastHigh - lastLow) * 0.5) {
                    conditions["volatility"] = "HIGH";
                }
            }
        } else {
            conditions["volatility"] = "UNKNOWN";
        }

        const adx = indicatorValues.ADX;
        if (typeof adx === 'number' && !isNaN(adx)) {
            if (adx > 40) {
                conditions["trend_strength"] = "STRONG";
            } else if (adx > 25) {
                conditions["trend_strength"] = "MODERATE";
            } else if (adx < 20) {
                conditions["trend_strength"] = "WEAK";
            }
        } else {
            conditions["trend_strength"] = "UNKNOWN";
        }

        if (df_data.shape[0] >= 20) {
            const recentVolume = df_data.volume.tail(5).mean().values[0];
            const avgVolume = df_data.volume.tail(20).mean().values[0];
            if (recentVolume > avgVolume * 1.5) {
                conditions["volume_profile"] = "HIGH";
            } else if (recentVolume < avgVolume * 0.5) {
                conditions["volume_profile"] = "LOW";
            }
        } else {
            conditions["volume_profile"] = "UNKNOWN";
        }

        return conditions;
    }

    _formatMarketData(marketSummary) {
        const priceStats = marketSummary.price_statistics || {};
        const indicators = marketSummary.technical_indicators || {};
        const mtfTrends = marketSummary.multi_timeframe_trends || {};
        const marketConditions = marketSummary.market_conditions || {};
        const recentCandles = marketSummary.recent_candles || [];

        return `
        Symbol: ${marketSummary.symbol || 'N/A'}
        Current Price: $${priceStats.current?.toFixed(2) || 0.00}
        24h High: $${priceStats['24h_high']?.toFixed(2) || 0.00}
        24h Low: $${priceStats['24h_low']?.toFixed(2) || 0.00}
        24h Change: ${priceStats['24h_change_pct']?.toFixed(2) || 0.00}%
        Volume (24h): ${priceStats.volume_24h?.toFixed(2) || 0.00}
        
        Technical Indicators (latest values):
        ${JSON.stringify(indicators, null, 2)}
        
        Multi-Timeframe Trends:
        ${JSON.stringify(mtfTrends, null, 2)}
        
        Market Conditions:
        ${JSON.stringify(marketConditions, null, 2)}
        
        Recent Price Action (Last ${recentCandles.length} candles, newest first):
        ${JSON.stringify(recentCandles.slice(0, 5), null, 2)}
        `;
    }

    _createAnalysisPrompt(marketSummary) {
        // Few-shot examples for better consistency
        const fewShotExamples = `
        Example 1:
        MARKET DATA:
        Symbol: BTCUSDT
        Current Price: $65000.00
        24h Change: 1.50%
        Technical Indicators: {"RSI": 72.0, "MACD_Hist": 150.0, "ADX": 35.0, "EMA_Short": 64500.0, "EMA_Long": 63000.0}
        Multi-Timeframe Trends: {"1h_ema": "UP", "4h_ema": "UP"}
        Market Conditions: {"volatility": "MODERATE", "trend_strength": "STRONG", "volume_profile": "HIGH"}
        
        JSON OUTPUT:
        {"signal": "HOLD", "confidence": 65, "analysis": "Price is overbought per RSI but showing strong momentum and trend alignment across higher timeframes. MACD histogram is positive but may be peaking. Volume is high. Await clear reversal or breakout confirmation.", "key_factors": ["RSI overbought", "Strong uptrend", "High volume", "MTF alignment"], "risk_level": "MEDIUM", "market_sentiment": "BULLISH", "pattern_detected": null, "suggested_entry": null, "suggested_stop_loss": null, "suggested_take_profit": null}
        
        Example 2:
        MARKET DATA:
        Symbol: ETHUSDT
        Current Price: $3200.00
        24h Change: -2.80%
        Technical Indicators: {"RSI": 28.0, "MACD_Hist": -80.0, "ADX": 20.0, "EMA_Short": 3250.0, "EMA_Long": 3300.0}
        Multi-Timeframe Trends: {"1h_ema": "DOWN", "4h_ema": "SIDEWAYS"}
        Market Conditions: {"volatility": "HIGH", "trend_strength": "WEAK", "volume_profile": "LOW"}
        
        JSON OUTPUT:
        {"signal": "BUY", "confidence": 70, "analysis": "RSI indicates oversold conditions, potentially signaling a bounce. Price is below EMAs, but ADX suggests weak trend. Volume is low, which could lead to sharp reversals. High volatility suggests careful entry. Looking for a bounce off recent support.", "key_factors": ["RSI oversold", "Weak trend", "High volatility", "Low volume"], "risk_level": "HIGH", "market_sentiment": "BEARISH", "pattern_detected": "Potential Double Bottom", "suggested_entry": 3180.00, "suggested_stop_loss": 3100.00, "suggested_take_profit": 3350.00}
        `;

        return `
        You are an expert cryptocurrency trading bot. Analyze the following real-time market data and provide a trading signal (BUY, SELL, HOLD) and comprehensive analysis.

        **Your output MUST be a JSON object conforming to the following schema:**
        \`\`\`json
        {
            "signal": { "type": "string", "enum": ["BUY", "SELL", "HOLD"] },
            "confidence": { "type": "number", "minimum": 0, "maximum": 100, "description": "Confidence level in percentage for the signal." },
            "analysis": { "type": "string", "description": "Detailed explanation of the reasoning behind the signal." },
            "key_factors": { "type": "array", "items": { "type": "string" }, "description": "Top influencing factors for the decision." },
            "risk_level": { "type": "string", "enum": ["LOW", "MEDIUM", "HIGH"], "description": "Assessed risk level for taking this trade." },
            "suggested_entry": { "type": "number", "optional": true, "description": "Suggested entry price." },
            "suggested_stop_loss": { "type": "number", "optional": true, "description": "Suggested stop loss price." },
            "suggested_take_profit": { "type": "number", "optional": true, "description": "Suggested take profit price." },
            "market_sentiment": { "type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"], "description": "Overall market sentiment." },
            "pattern_detected": { "type": "string", "optional": true, "description": "Notable chart pattern detected (e.g., 'Head and Shoulders', 'Double Bottom', 'Bull Flag')." }
        }
        \`\`\`
        
        ${fewShotExamples}

        **Now, analyze the following MARKET DATA FOR ANALYSIS:**
        ${this._formatMarketData(marketSummary)}

        **Based on the provided data, provide your expert trading analysis and signal in the specified JSON format.**
        Consider all aspects: price action, indicator confluence/divergence, volume, multi-timeframe trends, and market conditions.
        If a pattern or suggested levels are not applicable or too uncertain, set them to \`null\`.
        `;
    }

    async generateAdvancedSignal(df_data, indicatorValues, currentPrice, symbol, mtfTrends, existingSignal, existingScore) {
        const aiAnalysis = await this.analyzeMarketContext(
            df_data, indicatorValues, currentPrice, symbol, mtfTrends
        );

        const [combinedSignal, combinedScore] = this._combineSignals(
            existingSignal, existingScore, aiAnalysis
        );

        const signalDetails = {
            "final_signal": combinedSignal,
            "final_score": combinedScore,
            "technical_signal": existingSignal,
            "technical_score": existingScore,
            "ai_signal": aiAnalysis.signal || "HOLD",
            "ai_confidence": aiAnalysis.confidence || 0,
            "ai_analysis": aiAnalysis.analysis || "",
            "key_factors": aiAnalysis.key_factors || [],
            "risk_level": aiAnalysis.risk_level || "MEDIUM",
            "market_sentiment": aiAnalysis.market_sentiment || "NEUTRAL",
            "pattern_detected": aiAnalysis.pattern_detected || null,
            "suggested_levels": {
                "entry": aiAnalysis.suggested_entry,
                "stop_loss": aiAnalysis.suggested_stop_loss,
                "take_profit": aiAnalysis.suggested_take_profit
            }
        };

        this._logSignalDetails(signalDetails);

        return [combinedSignal, combinedScore, signalDetails];
    }

    _combineSignals(technicalSignal, technicalScore, aiAnalysis) {
        const TECHNICAL_WEIGHT = this.config.signal_weights?.technical || 0.6;
        const AI_WEIGHT = this.config.signal_weights?.ai || 0.4;
        const SIGNAL_THRESHOLD = this.config.signal_score_threshold || 2.0;
        const LOW_AI_CONFIDENCE_THRESHOLD = this.config.low_ai_confidence_threshold || 20;

        let aiScoreComponent = 0.0;
        const aiConfidence = (aiAnalysis.confidence || 0) / 100.0;

        if (aiAnalysis.signal === "BUY") {
            aiScoreComponent = (aiConfidence * 5.0); // Scale to match technical range
        } else if (aiAnalysis.signal === "SELL") {
            aiScoreComponent = -(aiConfidence * 5.0);
        }

        let combinedScore = (technicalScore * TECHNICAL_WEIGHT) + (aiScoreComponent * AI_WEIGHT);
        let finalSignal = "HOLD";

        if (combinedScore >= SIGNAL_THRESHOLD) {
            finalSignal = "BUY";
        } else if (combinedScore <= -SIGNAL_THRESHOLD) {
            finalSignal = "SELL";
        }

        // Special handling for strong disagreements or very low AI confidence
        if (aiConfidence * 100 < LOW_AI_CONFIDENCE_THRESHOLD) {
            this.logger.debug(`AI confidence very low (${(aiConfidence * 100).toFixed(0)}% < ${LOW_AI_CONFIDENCE_THRESHOLD}%). Technical signal will dominate.`);
            if (technicalScore >= SIGNAL_THRESHOLD) {
                finalSignal = "BUY";
            } else if (technicalScore <= -SIGNAL_THRESHOLD) {
                finalSignal = "SELL";
            } else {
                finalSignal = "HOLD";
            }
            combinedScore = technicalScore; // Revert to technical score or a heavy lean
        } else if (
            (technicalSignal === "BUY" && aiAnalysis.signal === "SELL" && aiConfidence > 0.5) ||
            (technicalSignal === "SELL" && aiAnalysis.signal === "BUY" && aiConfidence > 0.5)
        ) {
            this.logger.warning(`${NEON_YELLOW}Strong signal conflict detected between Technical and AI (moderate/high AI confidence). Defaulting to HOLD.${RESET}`);
            finalSignal = "HOLD";
            combinedScore = 0.0; // Neutralize score on conflict
        }

        return [finalSignal, combinedScore];
    }

    _logSignalDetails(signalDetails) {
        this.logger.info(`${NEON_PURPLE}=== GEMINI AI SIGNAL ANALYSIS ===${RESET}`);
        this.logger.info(`${NEON_CYAN}Final Signal: ${signalDetails.final_signal} (Score: ${signalDetails.final_score.toFixed(2)})${RESET}`);
        this.logger.info(`Technical: ${signalDetails.technical_signal} (${signalDetails.technical_score.toFixed(2)})${RESET}`);
        this.logger.info(`AI: ${signalDetails.ai_signal} (Confidence: ${signalDetails.ai_confidence}%)${RESET}`);
        this.logger.info(`Risk Level: ${signalDetails.risk_level}${RESET}`);
        this.logger.info(`Market Sentiment: ${signalDetails.market_sentiment}${RESET}`);
        if (signalDetails.pattern_detected && signalDetails.pattern_detected !== "None") {
            this.logger.info(`${NEON_YELLOW}Pattern Detected: ${signalDetails.pattern_detected}${RESET}`);
        }
        if (signalDetails.key_factors && signalDetails.key_factors.length > 0) {
            this.logger.info(`${NEON_YELLOW}Key Factors: ${signalDetails.key_factors.slice(0, 3).join(', ')}${RESET}`);
        }
        if (signalDetails.suggested_levels) {
            const levels = signalDetails.suggested_levels;
            if (levels.entry !== null && levels.entry !== undefined) {
                this.logger.info(`  ${NEON_GREEN}Suggested Entry: ${levels.entry.toFixed(2)}${RESET}`);
            }
            if (levels.stop_loss !== null && levels.stop_loss !== undefined) {
                this.logger.info(`  ${NEON_RED}Suggested SL: ${levels.stop_loss.toFixed(2)}${RESET}`);
            }
            if (levels.take_profit !== null && levels.take_profit !== undefined) {
                this.logger.info(`  ${NEON_GREEN}Suggested TP: ${levels.take_profit.toFixed(2)}${RESET}`);
            }
        }
        this.logger.info(`${NEON_PURPLE}----------------------------------${RESET}`);
    }

    trackSignalPerformance(signal, actualOutcome = null) {
        if (!this.performance_metrics.signal_accuracy[signal]) {
            this.performance_metrics.signal_accuracy[signal] = { 'WIN': 0, 'LOSS': 0, 'BREAKEVEN': 0, 'total': 0 };
        }

        this.performance_metrics.signal_accuracy[signal].total++;
        if (actualOutcome) {
            if (this.performance_metrics.signal_accuracy[signal].hasOwnProperty(actualOutcome)) {
                this.performance_metrics.signal_accuracy[signal][actualOutcome]++;
            } else {
                this.performance_metrics.signal_accuracy[signal].total--; // Don't count unknown outcomes
                this.logger.warning(`Unknown actual_outcome '${actualOutcome}' for signal performance tracking.`);
            }
        }
    }

    calculatePositionSizing(aiAnalysis, accountBalance, riskPerTradePercent, minStopLossDistance) {
        const riskMultipliers = {
            'LOW': new Decimal('1.0'),
            'MEDIUM': new Decimal('0.7'),
            'HIGH': new Decimal('0.4')
        };

        const riskLevel = (aiAnalysis.risk_level || 'MEDIUM').toUpperCase();
        const confidence = new Decimal(aiAnalysis.confidence || 50).div(100);

        const adjustedRiskRatio = riskPerTradePercent.times(riskMultipliers[riskLevel] || new Decimal('0.7')).times(confidence);

        const suggestedEntry = aiAnalysis.suggested_levels?.entry;
        const suggestedStopLoss = aiAnalysis.suggested_levels?.stop_loss;

        if (suggestedEntry === null || suggestedEntry === undefined ||
            suggestedStopLoss === null || suggestedStopLoss === undefined) {
            this.logger.debug("AI did not provide suggested entry or stop-loss for position sizing.");
            return null;
        }

        const entry = new Decimal(suggestedEntry);
        const stopLoss = new Decimal(suggestedStopLoss);

        let stopDistance = entry.minus(stopLoss).abs();
        if (stopDistance.lessThan(minStopLossDistance)) {
            this.logger.warning(`${NEON_YELLOW}AI suggested stop loss distance (${stopDistance.toFixed(8)}) is too small. Using default ATR-based sizing or minimum.${RESET}`);
            return null;
        }

        const riskAmount = accountBalance.times(adjustedRiskRatio);

        this.logger.debug(
            `AI-adjusted position sizing: Risk Ratio=${adjustedRiskRatio.times(100).toFixed(2)}%, Risk Amount=$${riskAmount.toFixed(2)}, ` +
            `Stop Distance=${stopDistance.toFixed(8)}. Suggested Entry=${entry.toFixed(2)}, SL=${stopLoss.toFixed(2)}`
        );

        return {
            'risk_amount': riskAmount,
            'stop_distance': stopDistance,
            'suggested_entry': entry,
            'suggested_stop_loss': stopLoss,
            'suggested_take_profit': aiAnalysis.suggested_levels?.take_profit ? new Decimal(aiAnalysis.suggested_levels.take_profit) : null,
            'adjusted_risk_percentage': adjustedRiskRatio.times(100)
        };
    }

    async _generateChartForAnalysis(df_data) {
        if (df_data.empty || df_data.shape[0] < 50) {
            this.logger.warning("Not enough data to generate chart for AI Vision.");
            return null;
        }

        const chartImageWidth = 800;
        const chartImageHeight = 600;
        const canvasRenderService = new ChartJSNodeCanvas({ width: chartImageWidth, height: chartImageHeight });

        const df_plot = df_data.tail(this.config.chart_image_data_points || 100);
        const labels = df_plot.index.values.map(dt => DateTime.fromJSDate(dt).toFormat('MM-dd HH:mm'));

        const datasets = [
            {
                label: 'Close Price',
                data: df_plot.close.values,
                borderColor: 'blue',
                backgroundColor: 'rgba(0, 0, 255, 0.1)',
                fill: false,
                yAxisID: 'price'
            }
        ];

        if (df_plot.columns.includes('EMA_Short') && !df_plot.EMA_Short.isna().all().values[0]) {
            datasets.push({
                label: 'EMA Short',
                data: df_plot.EMA_Short.values,
                borderColor: 'orange',
                backgroundColor: 'rgba(255, 165, 0, 0.1)',
                fill: false,
                yAxisID: 'price'
            });
        }
        if (df_plot.columns.includes('EMA_Long') && !df_plot.EMA_Long.isna().all().values[0]) {
            datasets.push({
                label: 'EMA Long',
                data: df_plot.EMA_Long.values,
                borderColor: 'purple',
                backgroundColor: 'rgba(128, 0, 128, 0.1)',
                fill: false,
                yAxisID: 'price'
            });
        }

        const chartConfig = {
            type: 'line',
            data: {
                labels: labels,
                datasets: datasets
            },
            options: {
                responsive: false,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    },
                    price: {
                        type: 'linear',
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Price'
                        }
                    },
                    volume: {
                        type: 'linear',
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Volume'
                        },
                        grid: {
                            drawOnChartArea: false
                        },
                        beginAtZero: true
                    },
                    rsi: {
                        type: 'linear',
                        position: 'right',
                        title: {
                            display: true,
                            text: 'RSI'
                        },
                        min: 0,
                        max: 100,
                        grid: {
                            drawOnChartArea: false
                        },
                        display: false // Initially hidden, will be enabled if RSI data exists
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: `${this.config.symbol || 'N/A'} ${this.config.interval || 'N/A'} Chart for AI Analysis`
                    }
                }
            }
        };

        // Add Volume and RSI as separate sub-charts or secondary axes.
        // For Chart.js, sub-charts usually means separate canvases or a complex layout.
        // For simplicity and direct `chartjs-node-canvas` usage, we'll layer them or use secondary axes if suitable.
        // A common approach is to use multiple y-axes or a custom plugin to render sub-charts.
        // For the sake of direct conversion, let's add volume and RSI to the same chart config
        // as separate datasets on potentially separate y-axes or a more complex configuration.

        // Adding Volume:
        chartConfig.data.datasets.push({
            label: 'Volume',
            data: df_plot.volume.values,
            type: 'bar',
            backgroundColor: 'rgba(128, 128, 128, 0.5)',
            yAxisID: 'volume',
            borderWidth: 0.1 // Make bars thin
        });
        chartConfig.options.scales.volume.display = true;

        // Adding RSI:
        if (df_plot.columns.includes('RSI') && !df_plot.RSI.isna().all().values[0]) {
            chartConfig.data.datasets.push({
                label: 'RSI',
                data: df_plot.RSI.values,
                borderColor: 'green',
                backgroundColor: 'rgba(0, 255, 0, 0.1)',
                fill: false,
                yAxisID: 'rsi'
            });
            chartConfig.options.scales.rsi.display = true;
            // Add RSI overbought/oversold lines
            chartConfig.options.plugins.annotation = {
                annotations: {
                    rsiOverbought: {
                        type: 'line',
                        yMin: 70,
                        yMax: 70,
                        borderColor: 'red',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        label: {
                            display: true,
                            content: 'Overbought (70)',
                            position: 'start'
                        },
                        yAxisID: 'rsi'
                    },
                    rsiOversold: {
                        type: 'line',
                        yMin: 30,
                        yMax: 30,
                        borderColor: 'green',
                        borderWidth: 1,
                        borderDash: [5, 5],
                        label: {
                            display: true,
                            content: 'Oversold (30)',
                            position: 'end'
                        },
                        yAxisID: 'rsi'
                    }
                }
            };
        }


        try {
            const buffer = await canvasRenderService.renderToBuffer(chartConfig);
            const imageBase64 = buffer.toString('base64');
            this.logger.debug("Chart image generated successfully for AI Vision.");
            return imageBase64;
        } catch (e) {
            this.logger.error(`${NEON_RED}Error generating chart image with chartjs-node-canvas: ${e.message}${RESET}`);
            return null;
        }
    }

    async analyzeChartImage(df_data, timeframe) {
        if (!this._checkApiLimits()) {
            this.performance_metrics.api_errors++;
            return { "analysis": "API daily limit reached.", "status": "error" };
        }

        const base64Image = await this._generateChartForAnalysis(df_data);
        if (!base64Image) {
            return { "analysis": "Failed to generate chart image.", "status": "error" };
        }

        const startTime = process.hrtime.bigint();
        let result = {};
        try {
            const imagePart = {
                inlineData: {
                    data: base64Image,
                    mimeType: "image/png"
                }
            };

            const promptParts = [
                { text: `Analyze this ${timeframe} cryptocurrency chart and provide:` },
                { text: "1. Identified chart patterns (e.g., Head and Shoulders, Triangles, Flags, Double Top/Bottom)." },
                { text: "2. Key visual support and resistance levels." },
                { text: "3. Trend analysis (strong, weak, sideways, reversal potential)." },
                { text: "4. Volume analysis in relation to price action." },
                { text: "5. Overall trading recommendation based on visual analysis." },
                { text: "Provide the response as a clear, structured text summary." },
                imagePart
            ];

            const response = await this.client.generateContent({
                contents: promptParts,
                generationConfig: {
                    temperature: 0.4,
                    responseMimeType: "text/plain"
                }
            });

            if (response.response.candidates && response.response.candidates[0].content.parts) {
                result = { "analysis": response.response.candidates[0].content.parts[0].text, "status": "success" };
                this.logger.info("Gemini Vision analysis successful.");
            } else {
                this.logger.warning("Gemini Vision analysis returned no content or candidates.");
                result = { "analysis": "No content from AI.", "status": "error", "error": "No content" };
            }
            this.performance_metrics.successful_analyses++;
        } catch (e) {
            this.logger.error(`${NEON_RED}Error analyzing chart image with Gemini Vision: ${e.message}${RESET}`);
            result = { "analysis": `Vision analysis failed: ${e.message}`, "status": "error" };
            this.performance_metrics.api_errors++;
        } finally {
            const endTime = process.hrtime.bigint();
            const responseTimeMs = Number(endTime - startTime) / 1_000_000;
            const nonCachedAnalyses = this.performance_metrics.total_analyses - this.performance_metrics.cache_hits;
            if (nonCachedAnalyses > 0) {
                this.performance_metrics.avg_response_time_ms =
                    (this.performance_metrics.avg_response_time_ms * nonCachedAnalyses + responseTimeMs) / (nonCachedAnalyses + 1);
            } else {
                this.performance_metrics.avg_response_time_ms = responseTimeMs;
            }
            this.performance_metrics.total_analyses++;
        }
        return result;
    }
}

// --- Position Manager ---
class PositionManager {
    constructor(config, logger, symbol) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.open_positions = []; // Stores active positions
        this.trade_management_enabled = config.trade_management.enabled;
        this.max_open_positions = config.trade_management.max_open_positions;
        this.min_stop_loss_distance_ratio = new Decimal(config.trade_management.min_stop_loss_distance_ratio);
    }

    _getCurrentBalance() {
        return new Decimal(this.config.trade_management.account_balance);
    }

    _calculateOrderSize(currentPrice, atrValue, aiPositionSizingInfo = null) {
        if (!this.trade_management_enabled) {
            return new Decimal("0");
        }

        const accountBalance = this._getCurrentBalance();
        const riskPerTradePercent = new Decimal(this.config.trade_management.risk_per_trade_percent).div(100);
        const stopLossAtrMultiple = new Decimal(this.config.trade_management.stop_loss_atr_multiple);

        let riskAmount = accountBalance.times(riskPerTradePercent);
        let stopLossDistance = new Decimal("0");

        if (aiPositionSizingInfo) {
            const aiStopDistance = aiPositionSizingInfo.stop_distance;
            const aiRiskAmount = aiPositionSizingInfo.risk_amount;
            if (aiStopDistance && aiRiskAmount && aiStopDistance.greaterThan(new Decimal("0"))) {
                riskAmount = aiRiskAmount;
                stopLossDistance = aiStopDistance;
                this.logger.debug("Using AI-suggested stop distance and risk amount.");
            } else {
                this.logger.warning(`${NEON_YELLOW}AI position sizing info invalid, falling back to ATR-based calculation.${RESET}`);
            }
        }

        if (stopLossDistance.equals(new Decimal("0"))) { // Fallback to ATR if AI didn't provide or was invalid
            stopLossDistance = atrValue.times(stopLossAtrMultiple);
            this.logger.debug(`Using ATR-based stop distance: ${stopLossDistance.toFixed(8)}`);
        }

        // Ensure stop loss distance is not too small relative to price
        const minAbsStopDistance = currentPrice.times(this.min_stop_loss_distance_ratio);
        if (stopLossDistance.lessThan(minAbsStopDistance)) {
            stopLossDistance = minAbsStopDistance;
            this.logger.warning(
                `${NEON_YELLOW}Calculated stop loss distance (${stopLossDistance.toFixed(8)}) is too small. ` +
                `Adjusted to minimum (${minAbsStopDistance.toFixed(8)}).${RESET}`
            );
        }

        if (stopLossDistance.equals(new Decimal("0"))) {
            this.logger.warning(
                `${NEON_YELLOW}Final stop loss distance is zero. Cannot determine order size.${RESET}`
            );
            return new Decimal("0");
        }

        const orderValue = riskAmount.div(stopLossDistance);
        const orderQty = orderValue.div(currentPrice);

        // Round order_qty to appropriate precision (e.g., BTCUSDT might be 0.0001)
        const roundedQty = orderQty.toDecimalPlaces(4, Decimal.ROUND_DOWN); // Example precision
        this.logger.info(`Calculated order size: ${roundedQty.toFixed(4)} ${this.symbol} (Risk: ${riskAmount.toFixed(2)} USD)`);
        return roundedQty;
    }

    openPosition(signal, currentPrice, atrValue, aiSuggestedLevels = null, aiPositionSizingInfo = null) {
        if (!this.trade_management_enabled) {
            this.logger.info(`${NEON_YELLOW}Trade management is disabled. Skipping opening position.${RESET}`);
            return null;
        }

        if (this.open_positions.length >= this.max_open_positions) {
            this.logger.info(`${NEON_YELLOW}Max open positions (${this.max_open_positions}) reached. Cannot open new position.${RESET}`);
            return null;
        }

        if (!["BUY", "SELL"].includes(signal)) {
            this.logger.debug(`Invalid signal '${signal}' for opening position.`);
            return null;
        }
        
        const orderQty = this._calculateOrderSize(currentPrice, atrValue, aiPositionSizingInfo);

        if (orderQty.equals(new Decimal("0"))) {
            this.logger.warning(`${NEON_YELLOW}Order quantity is zero. Cannot open position.${RESET}`);
            return null;
        }

        const stopLossAtrMultiple = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const takeProfitAtrMultiple = new Decimal(this.config.trade_management.take_profit_atr_multiple);

        let stopLoss = new Decimal("0");
        let takeProfit = new Decimal("0");

        if (aiSuggestedLevels) {
            if (aiSuggestedLevels.stop_loss !== null && aiSuggestedLevels.stop_loss !== undefined) {
                stopLoss = new Decimal(aiSuggestedLevels.stop_loss);
            }
            if (aiSuggestedLevels.take_profit !== null && aiSuggestedLevels.take_profit !== undefined) {
                takeProfit = new Decimal(aiSuggestedLevels.take_profit);
            }
            if (aiSuggestedLevels.entry !== null && aiSuggestedLevels.entry !== undefined) {
                this.logger.debug(`AI suggested entry: ${aiSuggestedLevels.entry}. Using current market price ${currentPrice} as actual entry.`);
            }
        }

        if (stopLoss.equals(new Decimal("0")) || takeProfit.equals(new Decimal("0"))) {
            if (signal === "BUY") {
                stopLoss = currentPrice.minus(atrValue.times(stopLossAtrMultiple));
                takeProfit = currentPrice.plus(atrValue.times(takeProfitAtrMultiple));
            } else { // SELL
                stopLoss = currentPrice.plus(atrValue.times(stopLossAtrMultiple));
                takeProfit = currentPrice.minus(atrValue.times(takeProfitAtrMultiple));
            }
        }

        const position = {
            entry_time: DateTime.now().setZone(TIMEZONE),
            symbol: this.symbol,
            side: signal,
            entry_price: currentPrice,
            qty: orderQty,
            stop_loss: stopLoss.toDecimalPlaces(5, Decimal.ROUND_DOWN),
            take_profit: takeProfit.toDecimalPlaces(5, Decimal.ROUND_DOWN),
            status: "OPEN",
        };
        this.open_positions.push(position);
        this.logger.info(`${NEON_GREEN}Opened ${signal} position: ${JSON.stringify(position)}${RESET}`);
        return position;
    }

    managePositions(currentPrice, performanceTracker, geminiAnalyzer = null) {
        if (!this.trade_management_enabled || this.open_positions.length === 0) {
            return;
        }

        const positionsToClose = [];
        for (let i = 0; i < this.open_positions.length; i++) {
            const position = this.open_positions[i];
            if (position.status === "OPEN") {
                const side = position.side;
                const entryPrice = position.entry_price;
                const stopLoss = position.stop_loss;
                const takeProfit = position.take_profit;
                const qty = position.qty;

                let closedBy = "";
                let closePrice = new Decimal("0");

                if (side === "BUY") {
                    if (currentPrice.lessThanOrEqualTo(stopLoss)) {
                        closedBy = "STOP_LOSS";
                        closePrice = currentPrice;
                    } else if (currentPrice.greaterThanOrEqualTo(takeProfit)) {
                        closedBy = "TAKE_PROFIT";
                        closePrice = currentPrice;
                    }
                } else if (side === "SELL") {
                    if (currentPrice.greaterThanOrEqualTo(stopLoss)) {
                        closedBy = "STOP_LOSS";
                        closePrice = currentPrice;
                    } else if (currentPrice.lessThanOrEqualTo(takeProfit)) {
                        closedBy = "TAKE_PROFIT";
                        closePrice = currentPrice;
                    }
                }

                if (closedBy) {
                    position.status = "CLOSED";
                    position.exit_time = DateTime.now().setZone(TIMEZONE);
                    position.exit_price = closePrice;
                    position.closed_by = closedBy;
                    positionsToClose.push(i);

                    const pnl = side === "BUY" ?
                        (closePrice.minus(entryPrice)).times(qty) :
                        (entryPrice.minus(closePrice)).times(qty);
                    performanceTracker.recordTrade(position, pnl);

                    const logColor = pnl.greaterThanOrEqualTo(new Decimal("0")) ? NEON_GREEN : NEON_RED;
                    this.logger.info(
                        `${NEON_PURPLE}Closed ${side} position by ${closedBy}: ${JSON.stringify(position)}. ${logColor}PnL: ${pnl.toFixed(2)}${RESET}`
                    );

                    if (geminiAnalyzer && position.ai_signal) {
                        let actualOutcome = "BREAKEVEN";
                        if (pnl.greaterThan(new Decimal("0"))) actualOutcome = "WIN";
                        else if (pnl.lessThan(new Decimal("0"))) actualOutcome = "LOSS";
                        geminiAnalyzer.trackSignalPerformance(position.ai_signal, actualOutcome);
                    }
                }
            }
        }

        // Remove closed positions
        this.open_positions = this.open_positions.filter((_, i) => !positionsToClose.includes(i));
    }

    getOpenPositions() {
        return this.open_positions.filter(pos => pos.status === "OPEN");
    }
}

// --- Performance Tracker ---
class PerformanceTracker {
    constructor(logger) {
        this.logger = logger;
        this.trades = [];
        this.total_pnl = new Decimal("0");
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
            ai_signal_at_entry: position.ai_signal,
        };
        this.trades.push(tradeRecord);
        this.total_pnl = this.total_pnl.plus(pnl);
        if (pnl.greaterThan(new Decimal("0"))) {
            this.wins++;
        } else {
            this.losses++;
        }
        this.logger.info(
            `${NEON_CYAN}Trade recorded. Current Total PnL: ${this.total_pnl.toFixed(2)}, Wins: ${this.wins}, Losses: ${this.losses}${RESET}`
        );
    }

    getSummary() {
        const totalTrades = this.trades.length;
        const winRate = totalTrades > 0 ? (this.wins / totalTrades) * 100 : 0;

        return {
            total_trades: totalTrades,
            total_pnl: this.total_pnl,
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

    sendAlert(message, level = "INFO") {
        if (level === "INFO") {
            this.logger.info(`${NEON_BLUE}ALERT: ${message}${RESET}`);
        } else if (level === "WARNING") {
            this.logger.warning(`${NEON_YELLOW}ALERT: ${message}${RESET}`);
        } else if (level === "ERROR") {
            this.logger.error(`${NEON_RED}ALERT: ${message}${RESET}`);
        }
    }
}

// --- Trading Analyzer Class ---
class TradingAnalyzer {
    constructor(df_data, config, logger, symbol) {
        // danfo.js DataFrames are mutable by default, so use .copy() if modifications are made
        // within the class that should not affect the original passed DataFrame.
        this.df = df_data; // Assume df_data is already a Danfo.js DataFrame
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.fib_levels = {};
        this.weights = config.weight_sets.default_scalping;
        this.indicator_settings = config.indicator_settings;

        if (this.df.empty) {
            this.logger.warning(
                `${NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.${RESET}`
            );
            return;
        }

        // Convert Decimal values in DataFrame to numbers for danfo.js calculations
        // This is a critical step to ensure danfo.js works correctly with numeric operations.
        // We assume `fetchKlines` already returns a DataFrame with numbers.
        // If not, explicit conversion would be needed here:
        // this.df.columns.forEach(col => {
        //     if (['open', 'high', 'low', 'close', 'volume', 'turnover'].includes(col)) {
        //         this.df[col] = this.df[col].apply(val => val instanceof Decimal ? val.toNumber() : val);
        //     }
        // });

        this._calculateAllIndicators();
        if (this.config.indicators.fibonacci_levels) {
            this.calculateFibonacciLevels();
        }
    }

    _safeCalculate(func, name, minDataPoints = 0, ...args) {
        if (this.df.shape[0] < minDataPoints) {
            this.logger.debug(
                `Skipping indicator '${name}': Not enough data. Need ${minDataPoints}, have ${this.df.shape[0]}.`
            );
            return null;
        }
        try {
            const result = func(...args);
            // Check for empty or all-NaN Series/DataFrame from danfo.js
            if (result === null ||
                (result instanceof df.Series && result.isna().all().values[0]) || // Check if all NaNs for Series
                (result instanceof df.DataFrame && result.empty) ||
                (Array.isArray(result) && result.every(r => r === null || (r instanceof df.Series && r.isna().all().values[0])))
            ) {
                this.logger.warning(
                    `${NEON_YELLOW}Indicator '${name}' returned empty or all NaNs after calculation. Not enough valid data?${RESET}`
                );
                return null;
            }
            return result;
        } catch (e) {
            this.logger.error(
                `${NEON_RED}Error calculating indicator '${name}': ${e.message}${RESET}`
            );
            return null;
        }
    }

    _calculateAllIndicators() {
        this.logger.debug("Calculating technical indicators...");
        const cfg = this.config;
        const isd = this.indicator_settings;

        // SMA
        if (cfg.indicators.sma_10) {
            const sma10 = this._safeCalculate(() => this.df.close.rolling(isd.sma_short_period).mean(), "SMA_10", isd.sma_short_period);
            if (sma10) {
                this.df.addColumn("SMA_10", sma10, { inplace: true });
                this.indicator_values["SMA_10"] = sma10.iloc({rows: [-1]}).values[0];
            }
        }
        if (cfg.indicators.sma_trend_filter) {
            const smaLong = this._safeCalculate(() => this.df.close.rolling(isd.sma_long_period).mean(), "SMA_Long", isd.sma_long_period);
            if (smaLong) {
                this.df.addColumn("SMA_Long", smaLong, { inplace: true });
                this.indicator_values["SMA_Long"] = smaLong.iloc({rows: [-1]}).values[0];
            }
        }

        // EMA
        if (cfg.indicators.ema_alignment) {
            const emaShort = this._safeCalculate(() => this.df.close.ewm(isd.ema_short_period, { adjust: false }).mean(), "EMA_Short", isd.ema_short_period);
            const emaLong = this._safeCalculate(() => this.df.close.ewm(isd.ema_long_period, { adjust: false }).mean(), "EMA_Long", isd.ema_long_period);
            if (emaShort) {
                this.df.addColumn("EMA_Short", emaShort, { inplace: true });
                this.indicator_values["EMA_Short"] = emaShort.iloc({rows: [-1]}).values[0];
            }
            if (emaLong) {
                this.df.addColumn("EMA_Long", emaLong, { inplace: true });
                this.indicator_values["EMA_Long"] = emaLong.iloc({rows: [-1]}).values[0];
            }
        }

        // ATR
        const tr = this._safeCalculate(() => this.calculateTrueRange(), "TR", MIN_DATA_POINTS_TR);
        if (tr) {
            this.df.addColumn("TR", tr, { inplace: true });
            const atr = this._safeCalculate(() => this.df.TR.ewm(isd.atr_period, { adjust: false }).mean(), "ATR", isd.atr_period);
            if (atr) {
                this.df.addColumn("ATR", atr, { inplace: true });
                this.indicator_values["ATR"] = atr.iloc({rows: [-1]}).values[0];
            }
        }

        // RSI
        if (cfg.indicators.rsi) {
            const rsi = this._safeCalculate(() => this.calculateRsi(isd.rsi_period), "RSI", isd.rsi_period + 1);
            if (rsi) {
                this.df.addColumn("RSI", rsi, { inplace: true });
                this.indicator_values["RSI"] = rsi.iloc({rows: [-1]}).values[0];
            }
        }

        // Stochastic RSI
        if (cfg.indicators.stoch_rsi) {
            const [stochRsiK, stochRsiD] = this._safeCalculate(() => this.calculateStochRsi(isd.stoch_rsi_period, isd.stoch_k_period, isd.stoch_d_period), "StochRSI", isd.stoch_rsi_period + isd.stoch_d_period + isd.stoch_k_period);
            if (stochRsiK) {
                this.df.addColumn("StochRSI_K", stochRsiK, { inplace: true });
                this.indicator_values["StochRSI_K"] = stochRsiK.iloc({rows: [-1]}).values[0];
            }
            if (stochRsiD) {
                this.df.addColumn("StochRSI_D", stochRsiD, { inplace: true });
                this.indicator_values["StochRSI_D"] = stochRsiD.iloc({rows: [-1]}).values[0];
            }
        }

        // Bollinger Bands
        if (cfg.indicators.bollinger_bands) {
            const [bbUpper, bbMiddle, bbLower] = this._safeCalculate(() => this.calculateBollingerBands(isd.bollinger_bands_period, isd.bollinger_bands_std_dev), "BollingerBands", isd.bollinger_bands_period);
            if (bbUpper) {
                this.df.addColumn("BB_Upper", bbUpper, { inplace: true });
                this.indicator_values["BB_Upper"] = bbUpper.iloc({rows: [-1]}).values[0];
            }
            if (bbMiddle) {
                this.df.addColumn("BB_Middle", bbMiddle, { inplace: true });
                this.indicator_values["BB_Middle"] = bbMiddle.iloc({rows: [-1]}).values[0];
            }
            if (bbLower) {
                this.df.addColumn("BB_Lower", bbLower, { inplace: true });
                this.indicator_values["BB_Lower"] = bbLower.iloc({rows: [-1]}).values[0];
            }
        }

        // CCI
        if (cfg.indicators.cci) {
            const cci = this._safeCalculate(() => this.calculateCci(isd.cci_period), "CCI", isd.cci_period);
            if (cci) {
                this.df.addColumn("CCI", cci, { inplace: true });
                this.indicator_values["CCI"] = cci.iloc({rows: [-1]}).values[0];
            }
        }

        // Williams %R
        if (cfg.indicators.wr) {
            const wr = this._safeCalculate(() => this.calculateWilliamsR(isd.williams_r_period), "WR", isd.williams_r_period);
            if (wr) {
                this.df.addColumn("WR", wr, { inplace: true });
                this.indicator_values["WR"] = wr.iloc({rows: [-1]}).values[0];
            }
        }

        // MFI
        if (cfg.indicators.mfi) {
            const mfi = this._safeCalculate(() => this.calculateMfi(isd.mfi_period), "MFI", isd.mfi_period + 1);
            if (mfi) {
                this.df.addColumn("MFI", mfi, { inplace: true });
                this.indicator_values["MFI"] = mfi.iloc({rows: [-1]}).values[0];
            }
        }

        // OBV
        if (cfg.indicators.obv) {
            const [obvVal, obvEma] = this._safeCalculate(() => this.calculateObv(isd.obv_ema_period), "OBV", isd.obv_ema_period);
            if (obvVal) {
                this.df.addColumn("OBV", obvVal, { inplace: true });
                this.indicator_values["OBV"] = obvVal.iloc({rows: [-1]}).values[0];
            }
            if (obvEma) {
                this.df.addColumn("OBV_EMA", obvEma, { inplace: true });
                this.indicator_values["OBV_EMA"] = obvEma.iloc({rows: [-1]}).values[0];
            }
        }

        // CMF
        if (cfg.indicators.cmf) {
            const cmfVal = this._safeCalculate(() => this.calculateCmf(isd.cmf_period), "CMF", isd.cmf_period);
            if (cmfVal) {
                this.df.addColumn("CMF", cmfVal, { inplace: true });
                this.indicator_values["CMF"] = cmfVal.iloc({rows: [-1]}).values[0];
            }
        }

        // Ichimoku Cloud
        if (cfg.indicators.ichimoku_cloud) {
            const [tenkanSen, kijunSen, senkouSpanA, senkouSpanB, chikouSpan] = this._safeCalculate(
                () => this.calculateIchimokuCloud(
                    isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period,
                    isd.ichimoku_senkou_span_b_period, isd.ichimoku_chikou_span_offset
                ), "IchimokuCloud",
                Math.max(isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period) + isd.ichimoku_chikou_span_offset
            );
            if (tenkanSen) {
                this.df.addColumn("Tenkan_Sen", tenkanSen, { inplace: true });
                this.indicator_values["Tenkan_Sen"] = tenkanSen.iloc({rows: [-1]}).values[0];
            }
            if (kijunSen) {
                this.df.addColumn("Kijun_Sen", kijunSen, { inplace: true });
                this.indicator_values["Kijun_Sen"] = kijunSen.iloc({rows: [-1]}).values[0];
            }
            if (senkouSpanA) {
                this.df.addColumn("Senkou_Span_A", senkouSpanA, { inplace: true });
                this.indicator_values["Senkou_Span_A"] = senkouSpanA.iloc({rows: [-1]}).values[0];
            }
            if (senkouSpanB) {
                this.df.addColumn("Senkou_Span_B", senkouSpanB, { inplace: true });
                this.indicator_values["Senkou_Span_B"] = senkouSpanB.iloc({rows: [-1]}).values[0];
            }
            if (chikouSpan) {
                this.df.addColumn("Chikou_Span", chikouSpan, { inplace: true });
                this.indicator_values["Chikou_Span"] = chikouSpan.fillna(0).iloc({rows: [-1]}).values[0];
            }
        }

        // PSAR
        if (cfg.indicators.psar) {
            const [psarVal, psarDir] = this._safeCalculate(() => this.calculatePsar(isd.psar_acceleration, isd.psar_max_acceleration), "PSAR", MIN_DATA_POINTS_PSAR);
            if (psarVal) {
                this.df.addColumn("PSAR_Val", psarVal, { inplace: true });
                this.indicator_values["PSAR_Val"] = psarVal.iloc({rows: [-1]}).values[0];
            }
            if (psarDir) {
                this.df.addColumn("PSAR_Dir", psarDir, { inplace: true });
                this.indicator_values["PSAR_Dir"] = psarDir.iloc({rows: [-1]}).values[0];
            }
        }

        // VWAP
        if (cfg.indicators.vwap) {
            const vwap = this._safeCalculate(() => this.calculateVwap(), "VWAP", 1);
            if (vwap) {
                this.df.addColumn("VWAP", vwap, { inplace: true });
                this.indicator_values["VWAP"] = vwap.iloc({rows: [-1]}).values[0];
            }
        }

        // Ehlers SuperTrend
        if (cfg.indicators.ehlers_supertrend) {
            const stFastResult = this._safeCalculate(() => this.calculateEhlersSupertrend(isd.ehlers_fast_period, isd.ehlers_fast_multiplier), "EhlersSuperTrendFast", isd.ehlers_fast_period * 3);
            if (stFastResult && !stFastResult.empty) {
                this.df.addColumn("st_fast_dir", stFastResult.direction, { inplace: true });
                this.df.addColumn("st_fast_val", stFastResult.supertrend, { inplace: true });
                this.indicator_values["ST_Fast_Dir"] = stFastResult.direction.iloc({rows: [-1]}).values[0];
                this.indicator_values["ST_Fast_Val"] = stFastResult.supertrend.iloc({rows: [-1]}).values[0];
            }

            const stSlowResult = this._safeCalculate(() => this.calculateEhlersSupertrend(isd.ehlers_slow_period, isd.ehlers_slow_multiplier), "EhlersSuperTrendSlow", isd.ehlers_slow_period * 3);
            if (stSlowResult && !stSlowResult.empty) {
                this.df.addColumn("st_slow_dir", stSlowResult.direction, { inplace: true });
                this.df.addColumn("st_slow_val", stSlowResult.supertrend, { inplace: true });
                this.indicator_values["ST_Slow_Dir"] = stSlowResult.direction.iloc({rows: [-1]}).values[0];
                this.indicator_values["ST_Slow_Val"] = stSlowResult.supertrend.iloc({rows: [-1]}).values[0];
            }
        }

        // MACD
        if (cfg.indicators.macd) {
            const [macdLine, signalLine, histogram] = this._safeCalculate(() => this.calculateMacd(isd.macd_fast_period, isd.macd_slow_period, isd.macd_signal_period), "MACD", isd.macd_slow_period + isd.macd_signal_period);
            if (macdLine) {
                this.df.addColumn("MACD_Line", macdLine, { inplace: true });
                this.indicator_values["MACD_Line"] = macdLine.iloc({rows: [-1]}).values[0];
            }
            if (signalLine) {
                this.df.addColumn("MACD_Signal", signalLine, { inplace: true });
                this.indicator_values["MACD_Signal"] = signalLine.iloc({rows: [-1]}).values[0];
            }
            if (histogram) {
                this.df.addColumn("MACD_Hist", histogram, { inplace: true });
                this.indicator_values["MACD_Hist"] = histogram.iloc({rows: [-1]}).values[0];
            }
        }

        // ADX
        if (cfg.indicators.adx) {
            const [adxVal, plusDi, minusDi] = this._safeCalculate(() => this.calculateAdx(isd.adx_period), "ADX", isd.adx_period * 2);
            if (adxVal) {
                this.df.addColumn("ADX", adxVal, { inplace: true });
                this.indicator_values["ADX"] = adxVal.iloc({rows: [-1]}).values[0];
            }
            if (plusDi) {
                this.df.addColumn("PlusDI", plusDi, { inplace: true });
                this.indicator_values["PlusDI"] = plusDi.iloc({rows: [-1]}).values[0];
            }
            if (minusDi) {
                this.df.addColumn("MinusDI", minusDi, { inplace: true });
                this.indicator_values["MinusDI"] = minusDi.iloc({rows: [-1]}).values[0];
            }
        }

        // Final dropna after all indicators are calculated
        const initialLen = this.df.shape[0];
        this.df.dropNa({ columns: ["close"], inplace: true });
        // danfo.js fillNa fills with 0 by default for numeric series if no value specified.
        // For indicator columns, fill any remaining NaNs with 0 (or a more appropriate default like previous value)
        this.df.columns.forEach(col => {
            if (!['start_time'].includes(col)) { // Don't fill start_time
                this.df[col].fillNa(0, { inplace: true });
            }
        });


        if (this.df.shape[0] < initialLen) {
            this.logger.debug(
                `Dropped ${initialLen - this.df.shape[0]} rows with NaNs after indicator calculations.`
            );
        }

        if (this.df.empty) {
            this.logger.warning(
                `${NEON_YELLOW}DataFrame is empty after calculating all indicators and dropping NaNs.${RESET}`
            );
        } else {
            this.logger.debug(
                `Indicators calculated. Final DataFrame size: ${this.df.shape[0]}`
            );
        }
    }

    calculateTrueRange() {
        if (this.df.shape[0] < MIN_DATA_POINTS_TR) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const highLow = this.df.high.sub(this.df.low);
        const highPrevClose = this.df.high.sub(this.df.close.shift(1)).abs();
        const lowPrevClose = this.df.low.sub(this.df.close.shift(1)).abs();
        return df.concat({ dfList: [highLow, highPrevClose, lowPrevClose], axis: 1 }).max({ axis: 1 });
    }

    calculateSuperSmoother(series, period) {
        if (period <= 0 || series.shape[0] < MIN_DATA_POINTS_SMOOTHER) {
            return new df.Series(Array(series.shape[0]).fill(NaN), { index: series.index });
        }

        const series_numeric = series.dropNa(); // Drop NaNs for calculation
        if (series_numeric.shape[0] < MIN_DATA_POINTS_SMOOTHER) {
            return new df.Series(Array(series.shape[0]).fill(NaN), { index: series.index });
        }

        const a1 = Math.exp(-Math.sqrt(2) * Math.PI / period);
        const b1 = 2 * a1 * Math.cos(Math.sqrt(2) * Math.PI / period);
        const c1 = 1 - b1 + a1**2;
        const c2 = b1 - 2 * a1**2;
        const c3 = a1**2;

        const filt = Array(series_numeric.shape[0]).fill(0.0);
        if (series_numeric.shape[0] >= 1) {
            filt[0] = series_numeric.values[0];
        }
        if (series_numeric.shape[0] >= 2) {
            filt[1] = (series_numeric.values[0] + series_numeric.values[1]) / 2;
        }

        for (let i = 2; i < series_numeric.shape[0]; i++) {
            filt[i] = ((c1 / 2) * (series_numeric.values[i] + series_numeric.values[i - 1])) +
                     (c2 * filt[i - 1]) - (c3 * filt[i - 2]);
        }
        return new df.Series(filt, { index: series_numeric.index }).reIndex({ index: series.index });
    }

    calculateEhlersSupertrend(period, multiplier) {
        if (this.df.shape[0] < period * 3) {
            this.logger.debug(`Not enough data for Ehlers SuperTrend (period=${period}). Need at least ${period * 3} bars.`);
            return null;
        }

        const df_copy = this.df.copy();

        const hl2 = df_copy.high.add(df_copy.low).div(2);
        const smoothedPrice = this.calculateSuperSmoother(hl2, period);

        const tr = this.calculateTrueRange();
        const smoothedAtr = this.calculateSuperSmoother(tr, period);

        if (smoothedPrice.isna().all().values[0] || smoothedAtr.isna().all().values[0]) {
            this.logger.debug("Ehlers SuperTrend: Smoothed price or ATR is all NaN. Returning null.");
            return null;
        }

        df_copy.addColumn("smoothed_price", smoothedPrice, { inplace: true });
        df_copy.addColumn("smoothed_atr", smoothedAtr, { inplace: true });

        const upperBand = df_copy.smoothed_price.add(df_copy.smoothed_atr.mul(multiplier));
        const lowerBand = df_copy.smoothed_price.sub(df_copy.smoothed_atr.mul(multiplier));

        const direction = new df.Series(Array(df_copy.shape[0]).fill(0), { index: df_copy.index, dtypes: ['int32'] });
        const supertrend = new df.Series(Array(df_copy.shape[0]).fill(NaN), { index: df_copy.index });

        const firstValidIndex = df_copy.smoothed_price.firstValidIndex();
        if (firstValidIndex === undefined || firstValidIndex === null) {
            return null;
        }

        const firstValidLoc = df_copy.index.indexOf(firstValidIndex);
        if (firstValidLoc === -1) {
            return null;
        }

        // Initialize first valid supertrend value (can be arbitrary, often lower_band for first candle)
        supertrend.iloc({rows: [firstValidLoc]}).fill(lowerBand.iloc({rows: [firstValidLoc]}).values[0]);


        for (let i = firstValidLoc + 1; i < df_copy.shape[0]; i++) {
            const currentIdx = df_copy.index.values[i];
            const prevIdx = df_copy.index.values[i - 1];

            const prevDirection = direction.loc({index: [prevIdx]}).values[0];
            const prevSupertrend = supertrend.loc({index: [prevIdx]}).values[0];
            const currClose = df_copy.close.loc({index: [currentIdx]}).values[0];
            const currentLowerBand = lowerBand.loc({index: [currentIdx]}).values[0];
            const currentUpperBand = upperBand.loc({index: [currentIdx]}).values[0];


            if (prevDirection === 1) { // Previously uptrend
                supertrend.loc({index: [currentIdx]}).fill(Math.max(currentLowerBand, prevSupertrend));
                if (currClose < supertrend.loc({index: [currentIdx]}).values[0]) {
                    direction.loc({index: [currentIdx]}).fill(-1); // Trend reversal to downtrend
                    supertrend.loc({index: [currentIdx]}).fill(currentUpperBand);
                } else {
                    direction.loc({index: [currentIdx]}).fill(1);
                }
            } else if (prevDirection === -1) { // Previously downtrend
                supertrend.loc({index: [currentIdx]}).fill(Math.min(currentUpperBand, prevSupertrend));
                if (currClose > supertrend.loc({index: [currentIdx]}).values[0]) {
                    direction.loc({index: [currentIdx]}).fill(1); // Trend reversal to uptrend
                    supertrend.loc({index: [currentIdx]}).fill(currentLowerBand);
                } else {
                    direction.loc({index: [currentIdx]}).fill(-1);
                }
            } else { // Initial state (first valid point)
                if (currClose > currentLowerBand) { // Assuming price above lower band means uptrend start
                    direction.loc({index: [currentIdx]}).fill(1);
                    supertrend.loc({index: [currentIdx]}).fill(currentLowerBand);
                } else { // Assuming price below upper band means downtrend start
                    direction.loc({index: [currentIdx]}).fill(-1);
                    supertrend.loc({index: [currentIdx]}).fill(currentUpperBand);
                }
            }
        }

        const result = new df.DataFrame({ supertrend: supertrend, direction: direction });
        return result.reIndex({ index: this.df.index });
    }

    calculateMacd(fastPeriod, slowPeriod, signalPeriod) {
        if (this.df.shape[0] < slowPeriod + signalPeriod) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }

        const emaFast = this.df.close.ewm(fastPeriod, { adjust: false }).mean();
        const emaSlow = this.df.close.ewm(slowPeriod, { adjust: false }).mean();

        const macdLine = emaFast.sub(emaSlow);
        const signalLine = macdLine.ewm(signalPeriod, { adjust: false }).mean();
        const histogram = macdLine.sub(signalLine);

        return [macdLine, signalLine, histogram];
    }

    calculateRsi(period) {
        if (this.df.shape[0] <= period) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const delta = this.df.close.diff(1);
        const gain = delta.clip(0, Infinity); // where delta > 0, 0
        const loss = delta.clip(-Infinity, 0).abs(); // -delta.where(delta < 0, 0)

        const avgGain = gain.ewm(period, { adjust: false, min_periods: period }).mean();
        const avgLoss = loss.ewm(period, { adjust: false, min_periods: period }).mean();

        // Handle division by zero for RS
        const rs = avgGain.div(avgLoss);
        const rsi = rs.replace(Infinity, 0).fillNa(0).add(1).pow(-1).mul(-100).add(100); // 100 - (100 / (1 + rs))
        return rsi;
    }

    calculateStochRsi(period, k_period, d_period) {
        if (this.df.shape[0] <= period) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }
        const rsi = this.calculateRsi(period);

        const lowestRsi = rsi.rolling(period, { min_periods: period }).min();
        const highestRsi = rsi.rolling(period, { min_periods: period }).max();

        const stochRsiKRaw = rsi.sub(lowestRsi).div(highestRsi.sub(lowestRsi)).mul(100);
        const stochRsiKRawFilled = stochRsiKRaw.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(0); // Handle inf values, then fillnan

        const stochRsiK = stochRsiKRawFilled.rolling(k_period, { min_periods: k_period }).mean();
        const stochRsiD = stochRsiK.rolling(d_period, { min_periods: d_period }).mean();

        return [stochRsiK, stochRsiD];
    }

    calculateAdx(period) {
        if (this.df.shape[0] < period * 2) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }

        const tr = this.calculateTrueRange();

        const highDiff = this.df.high.diff(1);
        const lowDiff = this.df.low.diff(1);

        // Calculate +DM and -DM
        const plusDm = highDiff.gt(lowDiff.abs()) ? highDiff.clip(0, Infinity) : new df.Series(Array(this.df.shape[0]).fill(0));
        const minusDm = lowDiff.abs().gt(highDiff) ? lowDiff.abs().clip(0, Infinity) : new df.Series(Array(this.df.shape[0]).fill(0));

        // Smoothed True Range, +DM, -DM
        const atr = tr.ewm(period, { adjust: false }).mean();
        const plusDi = plusDm.ewm(period, { adjust: false }).mean().div(atr).mul(100);
        const minusDi = minusDm.ewm(period, { adjust: false }).mean().div(atr).mul(100);

        // DX
        const diSum = plusDi.add(minusDi);
        const diDiff = plusDi.sub(minusDi).abs();
        const dx = diDiff.div(diSum).mul(100);
        const dxFilled = dx.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(0);

        // ADX
        const adx = dxFilled.ewm(period, { adjust: false }).mean();

        return [adx, plusDi, minusDi];
    }

    calculateBollingerBands(period, std_dev) {
        if (this.df.shape[0] < period) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }
        const middleBand = this.df.close.rolling(period, { min_periods: period }).mean();
        const std = this.df.close.rolling(period, { min_periods: period }).std();
        const upperBand = middleBand.add(std.mul(std_dev));
        const lowerBand = middleBand.sub(std.mul(std_dev));
        return [upperBand, middleBand, lowerBand];
    }

    calculateVwap() {
        if (this.df.empty) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const typicalPrice = this.df.high.add(this.df.low).add(this.df.close).div(3);
        const cumulativeTpVol = typicalPrice.mul(this.df.volume).cumsum();
        const cumulativeVol = this.df.volume.cumsum();
        const vwap = cumulativeTpVol.div(cumulativeVol);
        return vwap;
    }

    calculateCci(period) {
        if (this.df.shape[0] < period) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const tp = this.df.high.add(this.df.low).add(this.df.close).div(3);
        const smaTp = tp.rolling(period, { min_periods: period }).mean();
        // Mean Absolute Deviation (MAD) for danfo.js needs a custom apply or manual calculation
        const mad = tp.rolling(period, { min_periods: period }).apply((series) => {
            const mean = series.mean().values[0];
            return series.sub(mean).abs().mean().values[0];
        });
        const cci = tp.sub(smaTp).div(mad.mul(0.015));
        return cci.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(0);
    }

    calculateWilliamsR(period) {
        if (this.df.shape[0] < period) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const highestHigh = this.df.high.rolling(period, { min_periods: period }).max();
        const lowestLow = this.df.low.rolling(period, { min_periods: period }).min();
        const wr = highestHigh.sub(this.df.close).div(highestHigh.sub(lowestLow)).mul(-100);
        return wr.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(-50);
    }

    calculateIchimokuCloud(tenkan_period, kijun_period, senkou_span_b_period, chikou_span_offset) {
        if (this.df.shape[0] < Math.max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }

        const tenkanSen = this.df.high.rolling(tenkan_period).max().add(this.df.low.rolling(tenkan_period).min()).div(2);
        const kijunSen = this.df.high.rolling(kijun_period).max().add(this.df.low.rolling(kijun_period).min()).div(2);
        const senkouSpanA = tenkanSen.add(kijunSen).div(2).shift(kijun_period);
        const senkouSpanB = this.df.high.rolling(senkou_span_b_period).max().add(this.df.low.rolling(senkou_span_b_period).min()).div(2).shift(kijun_period);
        const chikouSpan = this.df.close.shift(-chikou_span_offset);

        return [tenkanSen, kijunSen, senkouSpanA, senkouSpanB, chikouSpan];
    }

    calculateMfi(period) {
        if (this.df.shape[0] <= period) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN), { index: this.df.index });
        }
        const typicalPrice = this.df.high.add(this.df.low).add(this.df.close).div(3);
        const moneyFlow = typicalPrice.mul(this.df.volume);

        const positiveFlow = new df.Series(Array(this.df.shape[0]).fill(0.0), { index: this.df.index });
        const negativeFlow = new df.Series(Array(this.df.shape[0]).fill(0.0), { index: this.df.index });

        for (let i = 1; i < this.df.shape[0]; i++) {
            if (typicalPrice.iloc({rows: [i]}).values[0] > typicalPrice.iloc({rows: [i - 1]}).values[0]) {
                positiveFlow.iloc({rows: [i]}).fill(moneyFlow.iloc({rows: [i]}).values[0]);
            } else if (typicalPrice.iloc({rows: [i]}).values[0] < typicalPrice.iloc({rows: [i - 1]}).values[0]) {
                negativeFlow.iloc({rows: [i]}).fill(moneyFlow.iloc({rows: [i]}).values[0]);
            }
        }

        const positiveMfSum = positiveFlow.rolling(period, { min_periods: period }).sum();
        const negativeMfSum = negativeFlow.rolling(period, { min_periods: period }).sum();

        const mfRatio = positiveMfSum.div(negativeMfSum);
        const mfi = mfRatio.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(50).add(1).pow(-1).mul(-100).add(100); // 100 - (100 / (1 + mfRatio))
        return mfi;
    }

    calculateObv(ema_period) {
        if (this.df.shape[0] < MIN_DATA_POINTS_OBV) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }

        const obv = new df.Series(Array(this.df.shape[0]).fill(0.0), { index: this.df.index });
        // The first OBV is 0 or can be the first volume, depending on convention.
        // Python's implementation starts with 0 then calculates, so let's mimic that.
        // No .iloc({rows: [0]}).fill(0) needed as it's initialized to 0.0

        for (let i = 1; i < this.df.shape[0]; i++) {
            if (this.df.close.iloc({rows: [i]}).values[0] > this.df.close.iloc({rows: [i - 1]}).values[0]) {
                obv.iloc({rows: [i]}).fill(obv.iloc({rows: [i - 1]}).values[0] + this.df.volume.iloc({rows: [i]}).values[0]);
            } else if (this.df.close.iloc({rows: [i]}).values[0] < this.df.close.iloc({rows: [i - 1]}).values[0]) {
                obv.iloc({rows: [i]}).fill(obv.iloc({rows: [i - 1]}).values[0] - this.df.volume.iloc({rows: [i]}).values[0]);
            } else {
                obv.iloc({rows: [i]}).fill(obv.iloc({rows: [i - 1]}).values[0]);
            }
        }

        const obvEma = obv.ewm(ema_period, { adjust: false }).mean();

        return [obv, obvEma];
    }

    calculateCmf(period) {
        if (this.df.shape[0] < period) {
            return new df.Series(Array(this.df.shape[0]).fill(NaN));
        }

        const highMinusLow = this.df.high.sub(this.df.low);
        // Handle division by zero for MFM
        const mfm = this.df.close.sub(this.df.low).sub(this.df.high.sub(this.df.close)).div(highMinusLow);
        const mfmFilled = mfm.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(0); // If high == low, it's NaN

        const mfv = mfmFilled.mul(this.df.volume);

        const cmf = mfv.rolling(period).sum().div(this.df.volume.rolling(period).sum());
        const cmfFilled = cmf.replace(Infinity, NaN).replace(-Infinity, NaN).fillNa(0); // If volume sum is zero

        return cmfFilled;
    }

    calculatePsar(acceleration, max_acceleration) {
        if (this.df.shape[0] < MIN_DATA_POINTS_PSAR) {
            return [new df.Series(Array(this.df.shape[0]).fill(NaN)), new df.Series(Array(this.df.shape[0]).fill(NaN))];
        }

        const psar = new df.Series(Array(this.df.shape[0]).fill(0.0), { index: this.df.index });
        const bull = new df.Series(Array(this.df.shape[0]).fill(false), { index: this.df.index });
        let af = acceleration;
        let ep; // Extreme Point

        // Initialize first PSAR value and direction
        if (this.df.close.iloc({rows: [0]}).values[0] < this.df.close.iloc({rows: [1]}).values[0]) {
            bull.iloc({rows: [0]}).fill(true); // Start as bullish
            psar.iloc({rows: [0]}).fill(this.df.low.iloc({rows: [0]}).values[0]);
            ep = this.df.high.iloc({rows: [0]}).values[0];
        } else {
            bull.iloc({rows: [0]}).fill(false); // Start as bearish
            psar.iloc({rows: [0]}).fill(this.df.high.iloc({rows: [0]}).values[0]);
            ep = this.df.low.iloc({rows: [0]}).values[0];
        }

        for (let i = 1; i < this.df.shape[0]; i++) {
            const prevBull = bull.iloc({rows: [i - 1]}).values[0];
            const prevPsar = psar.iloc({rows: [i - 1]}).values[0];
            const currentHigh = this.df.high.iloc({rows: [i]}).values[0];
            const currentLow = this.df.low.iloc({rows: [i]}).values[0];
            const currentClose = this.df.close.iloc({rows: [i]}).values[0];

            let newPsar;
            if (prevBull) { // Previous bar was bullish
                newPsar = prevPsar + af * (ep - prevPsar);
            } else { // Previous bar was bearish
                newPsar = prevPsar - af * (prevPsar - ep);
            }

            let reverse = false;
            let currentBull = prevBull;

            if (prevBull && currentLow < newPsar) {
                currentBull = false;
                reverse = true;
            } else if (!prevBull && currentHigh > newPsar) {
                currentBull = true;
                reverse = true;
            }

            if (reverse) {
                af = acceleration;
                if (currentBull) { // New trend is bullish
                    newPsar = currentLow; // SAR starts at the lowest price of current period
                    ep = currentHigh;
                } else { // New trend is bearish
                    newPsar = currentHigh; // SAR starts at the highest price of current period
                    ep = currentLow;
                }
            } else { // Trend continues
                if (currentBull) {
                    if (currentHigh > ep) {
                        ep = currentHigh;
                        af = Math.min(af + acceleration, max_acceleration);
                    }
                } else {
                    if (currentLow < ep) {
                        ep = currentLow;
                        af = Math.min(af + acceleration, max_acceleration);
                    }
                }
            }

            // Ensure PSAR doesn't penetrate current candle
            if (currentBull) {
                newPsar = Math.min(newPsar, currentLow, psar.iloc({rows: [i -1]}).values[0]); // For bullish, SAR must not go above current low
            } else {
                newPsar = Math.max(newPsar, currentHigh, psar.iloc({rows: [i -1]}).values[0]); // For bearish, SAR must not go below current high
            }
            // If PSAR breaches current price range, cap it at current high/low for visual correctness.
            // This part is a bit tricky to perfectly replicate from standard TA-Lib behavior often assumed in Python libraries.
            // For simple implementation, ensure it doesn't cross the current bar.
            if (currentBull && newPsar > currentLow) newPsar = currentLow;
            if (!currentBull && newPsar < currentHigh) newPsar = currentHigh;


            psar.iloc({rows: [i]}).fill(newPsar);
            bull.iloc({rows: [i]}).fill(currentBull);
        }

        const direction = new df.Series(Array(this.df.shape[0]).fill(0), { index: this.df.index, dtypes: ['int32'] });
        for (let i = 0; i < this.df.shape[0]; i++) {
            if (psar.iloc({rows: [i]}).values[0] < this.df.close.iloc({rows: [i]}).values[0]) {
                direction.iloc({rows: [i]}).fill(1); // Bullish
            } else if (psar.iloc({rows: [i]}).values[0] > this.df.close.iloc({rows: [i]}).values[0]) {
                direction.iloc({rows: [i]}).fill(-1); // Bearish
            }
        }

        return [psar, direction];
    }

    calculateFibonacciLevels() {
        const window = this.config.indicator_settings.fibonacci_window;
        if (this.df.shape[0] < window) {
            this.logger.warning(
                `${NEON_YELLOW}Not enough data for Fibonacci levels (need ${window} bars).${RESET}`
            );
            return;
        }

        const recentHigh = new Decimal(this.df.high.tail(window).max().values[0]);
        const recentLow = new Decimal(this.df.low.tail(window).min().values[0]);

        const diff = recentHigh.minus(recentLow);

        this.fib_levels = {
            "0.0%": recentHigh,
            "23.6%": recentHigh.minus(new Decimal("0.236").times(diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "38.2%": recentHigh.minus(new Decimal("0.382").times(diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "50.0%": recentHigh.minus(new Decimal("0.500").times(diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "61.8%": recentHigh.minus(new Decimal("0.618").times(diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "78.6%": recentHigh.minus(new Decimal("0.786").times(diff)).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            "100.0%": recentLow,
        };
        this.logger.debug(`Calculated Fibonacci levels: ${JSON.stringify(this.fib_levels)}`);
    }

    _getIndicatorValue(key, defaultValue = NaN) {
        const value = this.indicator_values[key];
        return (value === undefined || value === null || (typeof value === 'number' && isNaN(value))) ? defaultValue : value;
    }

    _checkOrderbook(currentPrice, orderbookData) {
        const bids = orderbookData.b || [];
        const asks = orderbookData.a || [];

        const bidVolume = bids.reduce((sum, b) => sum.plus(new Decimal(b[1])), new Decimal("0"));
        const askVolume = asks.reduce((sum, a) => sum.plus(new Decimal(a[1])), new Decimal("0"));

        const totalVolume = bidVolume.plus(askVolume);
        if (totalVolume.equals(new Decimal("0"))) {
            return 0.0;
        }

        const imbalance = bidVolume.minus(askVolume).div(totalVolume);
        this.logger.debug(`Orderbook Imbalance: ${imbalance.toFixed(4)} (Bids: ${bidVolume.toFixed(2)}, Asks: ${askVolume.toFixed(2)})`);
        return imbalance.toNumber();
    }

    _getMtfTrend(higherTfDf, indicatorType) {
        if (higherTfDf.empty) {
            return "UNKNOWN";
        }

        const lastClose = higherTfDf.close.iloc({rows: [-1]}).values[0];

        if (indicatorType === "sma") {
            const period = this.config.mtf_analysis.trend_period;
            if (higherTfDf.shape[0] < period) {
                this.logger.debug(`MTF SMA: Not enough data for ${period} period. Have ${higherTfDf.shape[0]}.`);
                return "UNKNOWN";
            }
            const sma = higherTfDf.close.rolling(period, { min_periods: period }).mean().iloc({rows: [-1]}).values[0];
            if (lastClose > sma) return "UP";
            if (lastClose < sma) return "DOWN";
            return "SIDEWAYS";
        } else if (indicatorType === "ema") {
            const period = this.config.mtf_analysis.trend_period;
            if (higherTfDf.shape[0] < period) {
                this.logger.debug(`MTF EMA: Not enough data for ${period} period. Have ${higherTfDf.shape[0]}.`);
                return "UNKNOWN";
            }
            const ema = higherTfDf.close.ewm(period, { adjust: false, min_periods: period }).mean().iloc({rows: [-1]}).values[0];
            if (lastClose > ema) return "UP";
            if (lastClose < ema) return "DOWN";
            return "SIDEWAYS";
        } else if (indicatorType === "ehlers_supertrend") {
            const tempAnalyzer = new TradingAnalyzer(
                higherTfDf.copy(), this.config, this.logger, this.symbol
            );
            const stResult = tempAnalyzer.calculateEhlersSupertrend(
                this.indicator_settings.ehlers_slow_period,
                this.indicator_settings.ehlers_slow_multiplier
            );
            if (stResult && !stResult.empty) {
                const stDir = stResult.direction.iloc({rows: [-1]}).values[0];
                if (stDir === 1) return "UP";
                if (stDir === -1) return "DOWN";
            }
            return "UNKNOWN";
        }
        return "UNKNOWN";
    }

    generateTradingSignal(currentPrice, orderbookData, mtfTrends) {
        let signalScore = 0.0;
        const activeIndicators = this.config.indicators;
        const weights = this.weights;

        if (this.df.empty) {
            this.logger.warning(
                `${NEON_YELLOW}DataFrame is empty in generateTradingSignal. Cannot generate signal.${RESET}`
            );
            return ["HOLD", 0.0];
        }

        const currentClose = new Decimal(this.df.close.iloc({rows: [-1]}).values[0]);
        const prevClose = this.df.shape[0] > 1 ? new Decimal(this.df.close.iloc({rows: [-2]}).values[0]) : null;

        const isd = this.indicator_settings;

        // EMA Alignment
        if (activeIndicators.ema_alignment) {
            const emaShort = this._getIndicatorValue("EMA_Short");
            const emaLong = this._getIndicatorValue("EMA_Long");
            if (typeof emaShort === 'number' && typeof emaLong === 'number' && !isNaN(emaShort) && !isNaN(emaLong)) {
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
            if (typeof smaLong === 'number' && !isNaN(smaLong)) {
                if (currentClose.greaterThan(new Decimal(smaLong))) {
                    signalScore += weights.sma_trend_filter || 0;
                } else if (currentClose.lessThan(new Decimal(smaLong))) {
                    signalScore -= weights.sma_trend_filter || 0;
                }
            }
        }

        // Momentum
        if (activeIndicators.momentum) {
            const rsi = this._getIndicatorValue("RSI");
            const stochK = this._getIndicatorValue("StochRSI_K");
            const stochD = this._getIndicatorValue("StochRSI_D");
            const cci = this._getIndicatorValue("CCI");
            const wr = this._getIndicatorValue("WR");
            const mfi = this._getIndicatorValue("MFI");

            // RSI
            if (typeof rsi === 'number' && !isNaN(rsi)) {
                if (rsi < isd.rsi_oversold) {
                    signalScore += (weights.rsi || 0) * 0.5;
                } else if (rsi > isd.rsi_overbought) {
                    signalScore -= (weights.rsi || 0) * 0.5;
                }
            }

            // StochRSI Crossover
            if (typeof stochK === 'number' && typeof stochD === 'number' && !isNaN(stochK) && !isNaN(stochD)) {
                if (stochK > stochD && stochK < isd.stoch_rsi_oversold) {
                    signalScore += (weights.stoch_rsi || 0) * 0.5;
                } else if (stochK < stochD && stochK > isd.stoch_rsi_overbought) {
                    signalScore -= (weights.stoch_rsi || 0) * 0.5;
                }
            }

            // CCI
            if (typeof cci === 'number' && !isNaN(cci)) {
                if (cci < isd.cci_oversold) {
                    signalScore += (weights.cci || 0) * 0.5;
                } else if (cci > isd.cci_overbought) {
                    signalScore -= (weights.cci || 0) * 0.5;
                }
            }

            // Williams %R
            if (typeof wr === 'number' && !isNaN(wr)) {
                if (wr < isd.williams_r_oversold) {
                    signalScore += (weights.wr || 0) * 0.5;
                } else if (wr > isd.williams_r_overbought) {
                    signalScore -= (weights.wr || 0) * 0.5;
                }
            }

            // MFI
            if (typeof mfi === 'number' && !isNaN(mfi)) {
                if (mfi < isd.mfi_oversold) {
                    signalScore += (weights.mfi || 0) * 0.5;
                } else if (mfi > isd.mfi_overbought) {
                    signalScore -= (weights.mfi || 0) * 0.5;
                }
            }
        }

        // Bollinger Bands
        if (activeIndicators.bollinger_bands) {
            const bbUpper = this._getIndicatorValue("BB_Upper");
            const bbLower = this._getIndicatorValue("BB_Lower");
            if (typeof bbUpper === 'number' && typeof bbLower === 'number' && !isNaN(bbUpper) && !isNaN(bbLower)) {
                if (currentClose.lessThan(new Decimal(bbLower))) {
                    signalScore += (weights.bollinger_bands || 0) * 0.5;
                } else if (currentClose.greaterThan(new Decimal(bbUpper))) {
                    signalScore -= (weights.bollinger_bands || 0) * 0.5;
                }
            }
        }

        // VWAP
        if (activeIndicators.vwap) {
            const vwap = this._getIndicatorValue("VWAP");
            if (typeof vwap === 'number' && !isNaN(vwap)) {
                if (currentClose.greaterThan(new Decimal(vwap))) {
                    signalScore += (weights.vwap || 0) * 0.2;
                } else if (currentClose.lessThan(new Decimal(vwap))) {
                    signalScore -= (weights.vwap || 0) * 0.2;
                }

                if (this.df.shape[0] > 1 && this.df.columns.includes("VWAP")) {
                    const prevVwap = new Decimal(this.df.VWAP.iloc({rows: [-2]}).values[0]);
                    if (currentClose.greaterThan(new Decimal(vwap)) && prevClose.lessThanOrEqualTo(prevVwap)) {
                        signalScore += (weights.vwap || 0) * 0.3;
                        this.logger.debug("VWAP: Bullish crossover detected.");
                    } else if (currentClose.lessThan(new Decimal(vwap)) && prevClose.greaterThanOrEqualTo(prevVwap)) {
                        signalScore -= (weights.vwap || 0) * 0.3;
                        this.logger.debug("VWAP: Bearish crossover detected.");
                    }
                }
            }
        }

        // PSAR
        if (activeIndicators.psar) {
            const psarVal = this._getIndicatorValue("PSAR_Val");
            const psarDir = this._getIndicatorValue("PSAR_Dir");
            if (typeof psarVal === 'number' && typeof psarDir === 'number' && !isNaN(psarVal) && !isNaN(psarDir)) {
                if (psarDir === 1) { // Bullish
                    signalScore += (weights.psar || 0) * 0.5;
                } else if (psarDir === -1) { // Bearish
                    signalScore -= (weights.psar || 0) * 0.5;
                }

                if (this.df.shape[0] > 1 && this.df.columns.includes("PSAR_Val")) {
                    const prevPsarVal = new Decimal(this.df.PSAR_Val.iloc({rows: [-2]}).values[0]);
                    if (currentClose.greaterThan(new Decimal(psarVal)) && prevClose.lessThanOrEqualTo(prevPsarVal)) {
                        signalScore += (weights.psar || 0) * 0.4;
                        this.logger.debug("PSAR: Bullish reversal detected.");
                    } else if (currentClose.lessThan(new Decimal(psarVal)) && prevClose.greaterThanOrEqualTo(prevPsarVal)) {
                        signalScore -= (weights.psar || 0) * 0.4;
                        this.logger.debug("PSAR: Bearish reversal detected.");
                    }
                }
            }
        }

        // Orderbook Imbalance
        if (activeIndicators.orderbook_imbalance && orderbookData) {
            const imbalance = this._checkOrderbook(currentPrice, orderbookData);
            signalScore += imbalance * (weights.orderbook_imbalance || 0);
        }

        // Fibonacci Levels (confluence with price action)
        if (activeIndicators.fibonacci_levels && Object.keys(this.fib_levels).length > 0) {
            const FIB_THRESHOLD_RATIO = new Decimal("0.001");
            for (const levelName in this.fib_levels) {
                const levelPrice = this.fib_levels[levelName];
                if (!["0.0%", "100.0%"].includes(levelName) &&
                    currentPrice.minus(levelPrice).abs().div(currentPrice).lessThan(FIB_THRESHOLD_RATIO)) {
                    this.logger.debug(`Price near Fibonacci level ${levelName}: ${levelPrice.toFixed(8)}`);
                    if (this.df.shape[0] > 1 && prevClose) {
                        if (currentClose.greaterThan(prevClose) && currentClose.greaterThan(levelPrice)) {
                            signalScore += (weights.fibonacci_levels || 0) * 0.1;
                        } else if (currentClose.lessThan(prevClose) && currentClose.lessThan(levelPrice)) {
                            signalScore -= (weights.fibonacci_levels || 0) * 0.1;
                        }
                    }
                }
            }
        }

        // Ehlers SuperTrend Alignment Scoring
        if (activeIndicators.ehlers_supertrend) {
            const stFastDir = this._getIndicatorValue("ST_Fast_Dir");
            const stSlowDir = this._getIndicatorValue("ST_Slow_Dir");

            const prevStFastDir = (this.df.columns.includes("st_fast_dir") && this.df.shape[0] > 1) ?
                this.df.st_fast_dir.iloc({rows: [-2]}).values[0] : NaN;

            const weight = weights.ehlers_supertrend_alignment || 0.0;

            if (typeof stFastDir === 'number' && typeof stSlowDir === 'number' && typeof prevStFastDir === 'number' &&
                !isNaN(stFastDir) && !isNaN(stSlowDir) && !isNaN(prevStFastDir)) {
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

        // MACD Alignment Scoring
        if (activeIndicators.macd) {
            const macdLine = this._getIndicatorValue("MACD_Line");
            const signalLine = this._getIndicatorValue("MACD_Signal");
            const histogram = this._getIndicatorValue("MACD_Hist");

            const weight = weights.macd_alignment || 0.0;

            if (typeof macdLine === 'number' && typeof signalLine === 'number' && typeof histogram === 'number' &&
                !isNaN(macdLine) && !isNaN(signalLine) && !isNaN(histogram)) {

                if (this.df.shape[0] > 1 && this.df.columns.includes("MACD_Line") && this.df.columns.includes("MACD_Signal")) {
                    const prevMacdLine = new Decimal(this.df.MACD_Line.iloc({rows: [-2]}).values[0]);
                    const prevSignalLine = new Decimal(this.df.MACD_Signal.iloc({rows: [-2]}).values[0]);

                    if (new Decimal(macdLine).greaterThan(new Decimal(signalLine)) && prevMacdLine.lessThanOrEqualTo(prevSignalLine)) {
                        signalScore += weight;
                        this.logger.debug("MACD: BUY signal (MACD line crossed above Signal line).");
                    } else if (new Decimal(macdLine).lessThan(new Decimal(signalLine)) && prevMacdLine.greaterThanOrEqualTo(prevSignalLine)) {
                        signalScore -= weight;
                        this.logger.debug("MACD: SELL signal (MACD line crossed below Signal line).");
                    }
                }
                
                if (this.df.shape[0] > 1 && this.df.columns.includes("MACD_Hist")) {
                    const prevMacdHist = new Decimal(this.df.MACD_Hist.iloc({rows: [-2]}).values[0]);
                    if (new Decimal(histogram).greaterThan(0) && prevMacdHist.lessThan(0)) {
                        signalScore += weight * 0.2;
                    } else if (new Decimal(histogram).lessThan(0) && prevMacdHist.greaterThan(0)) {
                        signalScore -= weight * 0.2;
                    }
                }
            }
        }

        // ADX Alignment Scoring
        if (activeIndicators.adx) {
            const adxVal = this._getIndicatorValue("ADX");
            const plusDi = this._getIndicatorValue("PlusDI");
            const minusDi = this._getIndicatorValue("MinusDI");

            const weight = weights.adx_strength || 0.0;

            if (typeof adxVal === 'number' && typeof plusDi === 'number' && typeof minusDi === 'number' &&
                !isNaN(adxVal) && !isNaN(plusDi) && !isNaN(minusDi)) {
                if (adxVal > ADX_STRONG_TREND_THRESHOLD) {
                    if (plusDi > minusDi) {
                        signalScore += weight;
                        this.logger.debug("ADX: Strong BUY trend (ADX > 25, +DI > -DI).");
                    } else if (minusDi > plusDi) {
                        signalScore -= weight;
                        this.logger.debug("ADX: Strong SELL trend (ADX > 25, -DI > +DI).");
                    }
                } else if (adxVal < ADX_WEAK_TREND_THRESHOLD) {
                    this.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.");
                }
            }
        }

        // Ichimoku Cloud Alignment Scoring
        if (activeIndicators.ichimoku_cloud) {
            const tenkanSen = this._getIndicatorValue("Tenkan_Sen");
            const kijunSen = this._getIndicatorValue("Kijun_Sen");
            const senkouSpanA = this._getIndicatorValue("Senkou_Span_A");
            const senkouSpanB = this._getIndicatorValue("Senkou_Span_B");
            const chikouSpan = this._getIndicatorValue("Chikou_Span");

            const weight = weights.ichimoku_confluence || 0.0;

            if (typeof tenkanSen === 'number' && typeof kijunSen === 'number' && typeof senkouSpanA === 'number' &&
                typeof senkouSpanB === 'number' && typeof chikouSpan === 'number' &&
                !isNaN(tenkanSen) && !isNaN(kijunSen) && !isNaN(senkouSpanA) && !isNaN(senkouSpanB) && !isNaN(chikouSpan)) {

                if (this.df.shape[0] > 1 && this.df.columns.includes("Tenkan_Sen") && this.df.columns.includes("Kijun_Sen")) {
                    const prevTenkanSen = new Decimal(this.df.Tenkan_Sen.iloc({rows: [-2]}).values[0]);
                    const prevKijunSen = new Decimal(this.df.Kijun_Sen.iloc({rows: [-2]}).values[0]);
                    if (new Decimal(tenkanSen).greaterThan(new Decimal(kijunSen)) && prevTenkanSen.lessThanOrEqualTo(prevKijunSen)) {
                        signalScore += weight * 0.5;
                        this.logger.debug("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).");
                    } else if (new Decimal(tenkanSen).lessThan(new Decimal(kijunSen)) && prevTenkanSen.greaterThanOrEqualTo(prevKijunSen)) {
                        signalScore -= weight * 0.5;
                        this.logger.debug("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).");
                    }
                }

                if (this.df.shape[0] > 1 && this.df.columns.includes("Senkou_Span_A") && this.df.columns.includes("Senkou_Span_B")) {
                    const prevSenkouSpanA = new Decimal(this.df.Senkou_Span_A.iloc({rows: [-2]}).values[0]);
                    const prevSenkouSpanB = new Decimal(this.df.Senkou_Span_B.iloc({rows: [-2]}).values[0]);
                    const maxPrevSpan = Decimal.max(prevSenkouSpanA, prevSenkouSpanB);
                    const minPrevSpan = Decimal.min(prevSenkouSpanA, prevSenkouSpanB);

                    if (currentClose.greaterThan(Decimal.max(new Decimal(senkouSpanA), new Decimal(senkouSpanB))) && prevClose.lessThanOrEqualTo(maxPrevSpan)) {
                        signalScore += weight * 0.7;
                        this.logger.debug("Ichimoku: Price broke above Kumo (strong bullish).");
                    } else if (currentClose.lessThan(Decimal.min(new Decimal(senkouSpanA), new Decimal(senkouSpanB))) && prevClose.greaterThanOrEqualTo(minPrevSpan)) {
                        signalScore -= weight * 0.7;
                        this.logger.debug("Ichimoku: Price broke below Kumo (strong bearish).");
                    }
                }

                if (this.df.shape[0] > 1 && this.df.columns.includes("Chikou_Span")) {
                    const prevChikouSpan = new Decimal(this.df.Chikou_Span.iloc({rows: [-2]}).values[0]);
                    if (new Decimal(chikouSpan).greaterThan(currentClose) && prevChikouSpan.lessThanOrEqualTo(prevClose)) {
                        signalScore += weight * 0.3;
                        this.logger.debug("Ichimoku: Chikou Span crossed above price (bullish confirmation).");
                    } else if (new Decimal(chikouSpan).lessThan(currentClose) && prevChikouSpan.greaterThanOrEqualTo(prevClose)) {
                        signalScore -= weight * 0.3;
                        this.logger.debug("Ichimoku: Chikou Span crossed below price (bearish confirmation).");
                    }
                }
            }
        }

        // OBV Alignment Scoring
        if (activeIndicators.obv) {
            const obvVal = this._getIndicatorValue("OBV");
            const obvEma = this._getIndicatorValue("OBV_EMA");

            const weight = weights.obv_momentum || 0.0;

            if (typeof obvVal === 'number' && typeof obvEma === 'number' && !isNaN(obvVal) && !isNaN(obvEma)) {
                if (this.df.shape[0] > 1 && this.df.columns.includes("OBV") && this.df.columns.includes("OBV_EMA")) {
                    const prevObvVal = new Decimal(this.df.OBV.iloc({rows: [-2]}).values[0]);
                    const prevObvEma = new Decimal(this.df.OBV_EMA.iloc({rows: [-2]}).values[0]);
                    if (new Decimal(obvVal).greaterThan(new Decimal(obvEma)) && prevObvVal.lessThanOrEqualTo(prevObvEma)) {
                        signalScore += weight * 0.5;
                        this.logger.debug("OBV: Bullish crossover detected.");
                    } else if (new Decimal(obvVal).lessThan(new Decimal(obvEma)) && prevObvVal.greaterThanOrEqualTo(prevObvEma)) {
                        signalScore -= weight * 0.5;
                        this.logger.debug("OBV: Bearish crossover detected.");
                    }
                }

                if (this.df.shape[0] > 2 && this.df.columns.includes("OBV")) {
                    const prevObvVal2 = new Decimal(this.df.OBV.iloc({rows: [-2]}).values[0]);
                    const prevObvVal3 = new Decimal(this.df.OBV.iloc({rows: [-3]}).values[0]);
                    if (new Decimal(obvVal).greaterThan(prevObvVal2) && prevObvVal2.greaterThan(prevObvVal3)) {
                        signalScore += weight * 0.2;
                    } else if (new Decimal(obvVal).lessThan(prevObvVal2) && prevObvVal2.lessThan(prevObvVal3)) {
                        signalScore -= weight * 0.2;
                    }
                }
            }
        }

        // CMF Alignment Scoring
        if (activeIndicators.cmf) {
            const cmfVal = this._getIndicatorValue("CMF");
            const weight = weights.cmf_flow || 0.0;

            if (typeof cmfVal === 'number' && !isNaN(cmfVal)) {
                if (cmfVal > 0) {
                    signalScore += weight * 0.5;
                } else if (cmfVal < 0) {
                    signalScore -= weight * 0.5;
                }

                if (this.df.shape[0] > 2 && this.df.columns.includes("CMF")) {
                    const prevCmfVal2 = new Decimal(this.df.CMF.iloc({rows: [-2]}).values[0]);
                    const prevCmfVal3 = new Decimal(this.df.CMF.iloc({rows: [-3]}).values[0]);
                    if (new Decimal(cmfVal).greaterThan(prevCmfVal2) && prevCmfVal2.greaterThan(prevCmfVal3)) {
                        signalScore += weight * 0.3;
                    } else if (new Decimal(cmfVal).lessThan(prevCmfVal2) && prevCmfVal2.lessThan(prevCmfVal3)) {
                        signalScore -= weight * 0.3;
                    }
                }
            }
        }

        // Multi-Timeframe Trend Confluence Scoring
        if (this.config.mtf_analysis.enabled && mtfTrends && Object.keys(mtfTrends).length > 0) {
            let mtfBuyScore = 0;
            let mtfSellScore = 0;
            for (const tfIndicator in mtfTrends) {
                const trend = mtfTrends[tfIndicator];
                if (trend === "UP") {
                    mtfBuyScore += 1;
                } else if (trend === "DOWN") {
                    mtfSellScore -= 1;
                }
            }
            const normalizedMtfScore = (mtfBuyScore + mtfSellScore) / Object.keys(mtfTrends).length;
            signalScore += (weights.mtf_trend_confluence || 0.0) * normalizedMtfScore;
            this.logger.debug(
                `MTF Confluence: Score ${normalizedMtfScore.toFixed(2)} (Buy: ${mtfBuyScore}, Sell: ${Math.abs(mtfSellScore)}). Total MTF contribution: ${((weights.mtf_trend_confluence || 0.0) * normalizedMtfScore).toFixed(2)}`
            );
        }

        // Final Signal Determination
        const threshold = this.config.signal_score_threshold;
        let finalSignal = "HOLD";
        if (signalScore >= threshold) {
            finalSignal = "BUY";
        } else if (signalScore <= -threshold) {
            finalSignal = "SELL";
        }

        this.logger.info(
            `${NEON_YELLOW}Raw Technical Signal Score: ${signalScore.toFixed(2)}, Final Technical Signal: ${finalSignal}${RESET}`
        );
        return [finalSignal, signalScore];
    }
}

// --- Display Functions ---
async function displayIndicatorValuesAndPrice(
    config,
    logger,
    currentPrice,
    df_data,
    orderbookData,
    mtfTrends
) {
    logger.info(`${NEON_BLUE}--- Current Market Data & Indicators ---${RESET}`);
    logger.info(`${NEON_GREEN}Current Price: ${currentPrice.toFixed(8)}${RESET}`);

    // Create a temporary analyzer instance to calculate and display current indicators
    const analyzer = new TradingAnalyzer(df_data.copy(), config, logger, config.symbol);

    if (analyzer.df.empty) {
        logger.warning(
            `${NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.${RESET}`
        );
        return;
    }

    logger.info(`${NEON_CYAN}--- Indicator Values ---${RESET}`);
    for (const indicatorName in analyzer.indicator_values) {
        const value = analyzer.indicator_values[indicatorName];
        const color = INDICATOR_COLORS[indicatorName] || NEON_YELLOW;
        if (typeof value === 'number' && !isNaN(value)) {
            logger.info(`  ${color}${indicatorName}: ${value.toFixed(8)}${RESET}`);
        } else {
            logger.info(`  ${color}${indicatorName}: ${value}${RESET}`);
        }
    }

    if (Object.keys(analyzer.fib_levels).length > 0) {
        logger.info(`\n${NEON_CYAN}--- Fibonacci Levels ---${RESET}`);
        for (const levelName in analyzer.fib_levels) {
            const levelPrice = analyzer.fib_levels[levelName];
            logger.info(`  ${NEON_YELLOW}${levelName}: ${levelPrice.toFixed(8)}${RESET}`);
        }
    }

    if (Object.keys(mtfTrends).length > 0) {
        logger.info(`\n${NEON_CYAN}--- Multi-Timeframe Trends ---${RESET}`);
        for (const tfIndicator in mtfTrends) {
            const trend = mtfTrends[tfIndicator];
            logger.info(`  ${NEON_YELLOW}${tfIndicator}: ${trend}${RESET}`);
        }
    }

    logger.info(`${NEON_BLUE}--------------------------------------${RESET}`);
}

// --- Main Bot Logic ---
async function main() {
    const logger = setupLogger("wgwhalex_bot");
    const config = loadConfig(CONFIG_FILE, logger);
    const alertSystem = new AlertSystem(logger);

    // Validate interval format at startup
    const validBybitIntervals = [
        "1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"
    ];
    const intervalMapping = {"1h": "60", "4h": "240"};

    // Check primary interval
    if (intervalMapping[config.interval]) {
        config.interval = intervalMapping[config.interval];
        logger.info(`Normalized primary interval to: ${config.interval}`);
    }
    if (!validBybitIntervals.includes(config.interval)) {
        logger.error(
            `${NEON_RED}Invalid primary interval '${config.interval}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.${RESET}`
        );
        process.exit(1);
    }

    // Check higher timeframes intervals
    for (let i = 0; i < config.mtf_analysis.higher_timeframes.length; i++) {
        let htfInterval = config.mtf_analysis.higher_timeframes[i];
        if (intervalMapping[htfInterval]) {
            htfInterval = intervalMapping[htfInterval];
            config.mtf_analysis.higher_timeframes[i] = htfInterval;
            logger.info(`Normalized MTF interval ${config.mtf_analysis.higher_timeframes[i]} to: ${htfInterval}`);
        }
        if (!validBybitIntervals.includes(htfInterval)) {
            logger.error(
                `${NEON_RED}Invalid higher timeframe interval '${htfInterval}' in config.json. Please use Bybit's valid string formats (e.g., '1h' should be '60', '4h' should be '240'). Exiting.${RESET}`
            );
            process.exit(1);
        }
    }

    logger.info(`${NEON_GREEN}--- Wgwhalex Trading Bot Initialized ---${RESET}`);
    logger.info(`Symbol: ${config.symbol}, Interval: ${config.interval}`);
    logger.info(`Trade Management Enabled: ${config.trade_management.enabled}`);

    const positionManager = new PositionManager(config, logger, config.symbol);
    const performanceTracker = new PerformanceTracker(logger);

    let geminiAnalyzer = null;
    if (config.gemini_ai.enabled) {
        const geminiApiKey = process.env[config.gemini_ai.api_key_env];
        if (geminiApiKey) {
            try {
                geminiAnalyzer = new GeminiSignalAnalyzer(
                    geminiApiKey,
                    logger,
                    config.gemini_ai.model,
                    {
                        cache_ttl_seconds: config.gemini_ai.cache_ttl_seconds,
                        daily_api_limit: config.gemini_ai.daily_api_limit,
                        signal_score_threshold: config.signal_score_threshold,
                        signal_weights: config.gemini_ai.signal_weights,
                        low_ai_confidence_threshold: config.gemini_ai.low_ai_confidence_threshold,
                        symbol: config.symbol,
                        interval: config.interval,
                        chart_image_data_points: config.gemini_ai.chart_image_analysis.data_points_for_chart
                    }
                );
                logger.info(`${NEON_GREEN}Gemini AI Signal Analyzer initialized successfully.${RESET}`);
            } catch (e) {
                logger.error(`${NEON_RED}Failed to initialize Gemini AI: ${e.message}. AI analysis will be disabled.${RESET}`);
                config.gemini_ai.enabled = false;
            }
        } else {
            logger.warning(`${NEON_YELLOW}Gemini API key not found in environment variable '${config.gemini_ai.api_key_env}'. AI analysis disabled.${RESET}`);
            config.gemini_ai.enabled = false;
        }
    }

    let loopCount = 0;
    while (true) {
        loopCount++;
        try {
            logger.info(`${NEON_PURPLE}--- New Analysis Loop Started (Loop: ${loopCount}) ---${RESET}`);
            const currentPrice = await fetchCurrentPrice(config.symbol, logger);
            if (currentPrice === null) {
                alertSystem.sendAlert(
                    "Failed to fetch current price. Skipping loop.", "WARNING"
                );
                await new Promise(resolve => setTimeout(resolve, config.loop_delay * 1000));
                continue;
            }

            const df_primary = await fetchKlines(config.symbol, config.interval, 1000, logger);
            if (df_primary === null || df_primary.empty) {
                alertSystem.sendAlert(
                    "Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING"
                );
                await new Promise(resolve => setTimeout(resolve, config.loop_delay * 1000));
                continue;
            }

            let orderbookData = null;
            if (config.indicators.orderbook_imbalance) {
                orderbookData = await fetchOrderbook(
                    config.symbol, config.orderbook_limit, logger
                );
            }

            const mtfTrends = {};
            if (config.mtf_analysis.enabled) {
                for (const htfInterval of config.mtf_analysis.higher_timeframes) {
                    logger.debug(`Fetching klines for MTF interval: ${htfInterval}`);
                    const htfDf = await fetchKlines(config.symbol, htfInterval, 1000, logger);
                    if (htfDf !== null && !htfDf.empty) {
                        for (const trendInd of config.mtf_analysis.trend_indicators) {
                            const tempHtfAnalyzer = new TradingAnalyzer(
                                htfDf.copy(), config, logger, config.symbol
                            );
                            const trend = tempHtfAnalyzer._getMtfTrend(
                                tempHtfAnalyzer.df, trendInd
                            );
                            mtfTrends[`${htfInterval}_${trendInd}`] = trend;
                            logger.debug(
                                `MTF Trend (${htfInterval}, ${trendInd}): ${trend}`
                            );
                        }
                    } else {
                        logger.warning(
                            `${NEON_YELLOW}Could not fetch klines for higher timeframe ${htfInterval} or it was empty. Skipping MTF trend for this TF.${RESET}`
                        );
                    }
                    await new Promise(resolve => setTimeout(resolve, config.mtf_analysis.mtf_request_delay_seconds * 1000));
                }
            }

            // Create analyzer with a copy of df_primary for calculations
            const analyzer = new TradingAnalyzer(df_primary.copy(), config, logger, config.symbol);

            if (analyzer.df.empty) {
                alertSystem.sendAlert(
                    "TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                    "WARNING",
                );
                await new Promise(resolve => setTimeout(resolve, config.loop_delay * 1000));
                continue;
            }

            await displayIndicatorValuesAndPrice(
                config, logger, currentPrice, analyzer.df.copy(), orderbookData, mtfTrends
            );

            // --- Technical Signal Generation ---
            const [technicalSignal, technicalScore] = analyzer.generateTradingSignal(
                currentPrice, orderbookData, mtfTrends
            );

            let finalTradingSignal = technicalSignal;
            let finalSignalScore = technicalScore;
            let aiSignalDetails = null;
            let aiPositionSizingInfo = null;

            // --- Enhance with Gemini AI if available and enabled ---
            if (geminiAnalyzer && config.gemini_ai.enabled) {
                try {
                    await new Promise(resolve => setTimeout(resolve, config.gemini_ai.rate_limit_delay_seconds * 1000));

                    // Call Gemini for advanced text analysis
                    const [aiEnhancedSignal, aiCombinedScore, aiDetails] = await geminiAnalyzer.generateAdvancedSignal(
                        analyzer.df.copy(), // Pass a copy to AI for analysis
                        analyzer.indicator_values,
                        currentPrice,
                        config.symbol,
                        mtfTrends,
                        technicalSignal,
                        technicalScore
                    );

                    // Apply AI-enhanced signal if confidence is sufficient
                    if (aiDetails.ai_confidence >= config.gemini_ai.min_confidence_for_override) {
                        finalTradingSignal = aiEnhancedSignal;
                        finalSignalScore = aiCombinedScore;
                        aiSignalDetails = aiDetails;

                        logger.info(`${NEON_PURPLE}AI-Enhanced Signal applied: ${finalTradingSignal} (Score: ${finalSignalScore.toFixed(2)})${RESET}`);

                        // Calculate AI-driven position sizing
                        aiPositionSizingInfo = geminiAnalyzer.calculatePositionSizing(
                            aiDetails,
                            new Decimal(config.trade_management.account_balance),
                            new Decimal(config.trade_management.risk_per_trade_percent).div(100),
                            currentPrice.times(new Decimal(config.trade_management.min_stop_loss_distance_ratio))
                        );
                        if (aiPositionSizingInfo) {
                            logger.info(`${NEON_CYAN}AI Suggested Position Sizing: Risk Amount=$${aiPositionSizingInfo.risk_amount.toFixed(2)}, Stop Dist=${aiPositionSizingInfo.stop_distance.toFixed(8)}${RESET}`);
                        }
                    } else {
                        logger.info(`${NEON_YELLOW}Gemini AI confidence (${aiDetails.ai_confidence}%) too low for override (${config.gemini_ai.min_confidence_for_override}% required). Using technical signal.${RESET}`);
                        aiSignalDetails = aiDetails; // Still keep details for logging/debugging
                    }

                    // --- Gemini Vision for Chart Analysis (Optional, performance intensive) ---
                    if (config.gemini_ai.chart_image_analysis.enabled &&
                        config.gemini_ai.chart_image_analysis.frequency_loops > 0 &&
                        loopCount % config.gemini_ai.chart_image_analysis.frequency_loops === 0) {
                        logger.info(`${NEON_BLUE}Performing Gemini Vision chart analysis...${RESET}`);
                        const visionAnalysisResult = await geminiAnalyzer.analyzeChartImage(df_primary.copy(), config.interval);
                        if (visionAnalysisResult.status === "success") {
                            logger.info(`${NEON_CYAN}Gemini Vision Chart Analysis: ${visionAnalysisResult.analysis.substring(0, 300)}...${RESET}`);
                        } else {
                            logger.warning(`${NEON_YELLOW}Gemini Vision Chart Analysis Failed: ${visionAnalysisResult.error || 'Unknown error'}${RESET}`);
                        }
                    }

                } catch (e) {
                    logger.error(`${NEON_RED}Error during Gemini AI analysis. Falling back to technical signal: ${e.message}${RESET}`);
                }
            }
            // --- End Gemini AI Enhancement ---

            const atrValue = new Decimal(analyzer._getIndicatorValue("ATR", 0.01));

            // --- Position Management ---
            const aiSignalAtOpen = aiSignalDetails?.ai_signal || null;

            positionManager.managePositions(currentPrice, performanceTracker, geminiAnalyzer);

            // Determine if we have a BUY/SELL signal from the final (technical or AI-enhanced) signal
            if (
                finalTradingSignal === "BUY" &&
                finalSignalScore >= config.signal_score_threshold
            ) {
                logger.info(
                    `${NEON_GREEN}Strong BUY signal detected! Score: ${finalSignalScore.toFixed(2)}${RESET}`
                );
                const newPos = positionManager.openPosition(
                    "BUY", currentPrice, atrValue,
                    aiSignalDetails?.suggested_levels || null,
                    aiPositionSizingInfo
                );
                if (newPos && aiSignalAtOpen) {
                    newPos.ai_signal = aiSignalAtOpen; // Store AI signal for tracking
                }

            } else if (
                finalTradingSignal === "SELL" &&
                finalSignalScore <= -config.signal_score_threshold
            ) {
                logger.info(
                    `${NEON_RED}Strong SELL signal detected! Score: ${finalSignalScore.toFixed(2)}${RESET}`
                );
                const newPos = positionManager.openPosition(
                    "SELL", currentPrice, atrValue,
                    aiSignalDetails?.suggested_levels || null,
                    aiPositionSizingInfo
                );
                if (newPos && aiSignalAtOpen) {
                    newPos.ai_signal = aiSignalAtOpen; // Store AI signal for tracking
                }
            } else {
                logger.info(
                    `${NEON_BLUE}No strong trading signal. Holding. Score: ${finalSignalScore.toFixed(2)}${RESET}`
                );
            }

            // Log current open positions
            const openPositions = positionManager.getOpenPositions();
            if (openPositions.length > 0) {
                logger.info(`${NEON_CYAN}Open Positions: ${openPositions.length}${RESET}`);
                for (const pos of openPositions) {
                    logger.info(
                        `  - ${pos.side} @ ${pos.entry_price.toFixed(8)} (SL: ${pos.stop_loss.toFixed(8)}, TP: ${pos.take_profit.toFixed(8)})${RESET}`
                    );
                }
            } else {
                logger.info(`${NEON_CYAN}No open positions.${RESET}`);
            }

            // Log performance summary
            const perfSummary = performanceTracker.getSummary();
            logger.info(
                `${NEON_YELLOW}Performance Summary: Total PnL: ${perfSummary.total_pnl.toFixed(2)}, Wins: ${perfSummary.wins}, Losses: ${perfSummary.losses}, Win Rate: ${perfSummary.win_rate}${RESET}`
            );

            // Log Gemini AI performance metrics
            if (geminiAnalyzer && config.gemini_ai.enabled) {
                const gmPerf = geminiAnalyzer.performance_metrics;
                logger.info(`${NEON_PURPLE}Gemini AI Performance:${RESET}`);
                logger.info(`  Total Analyses: ${gmPerf.total_analyses}, Successful: ${gmPerf.successful_analyses}, Errors: ${gmPerf.api_errors}, Cache Hits: ${gmPerf.cache_hits}${RESET}`);
                if (gmPerf.avg_response_time_ms > 0) {
                    logger.info(`  Avg. Response Time: ${gmPerf.avg_response_time_ms.toFixed(2)} ms (non-cached)${RESET}`);
                }

                if (Object.keys(gmPerf.signal_accuracy).length > 0) {
                    logger.info(`${NEON_CYAN}  AI Signal Accuracy (by outcome):${RESET}`);
                    for (const sigType in gmPerf.signal_accuracy) {
                        const stats = gmPerf.signal_accuracy[sigType];
                        const winRate = (stats.total > 0) ? (stats.WIN / stats.total * 100) : 0;
                        logger.info(`    ${sigType}: Total: ${stats.total}, Wins: ${stats.WIN}, Losses: ${stats.LOSS}, BreakEvens: ${stats.BREAKEVEN} (Win Rate: ${winRate.toFixed(2)}%) ${RESET}`);
                    }
                }
            }

            logger.info(
                `${NEON_PURPLE}--- Analysis Loop Finished. Waiting ${config.loop_delay}s ---${RESET}`
            );
            await new Promise(resolve => setTimeout(resolve, config.loop_delay * 1000));

        } catch (e) {
            alertSystem.sendAlert(
                `An unhandled error occurred in the main loop: ${e.message}`, "ERROR"
            );
            logger.exception(`${NEON_RED}Unhandled exception in main loop:${RESET}`);
            console.error(e); // Log full stack trace
            await new Promise(resolve => setTimeout(resolve, config.loop_delay * 2 * 1000)); // Longer delay on error
        }
    }
}

if (require.main === module) {
    main();
}
