import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import dotenv from 'dotenv';

dotenv.config(); // Load environment variables from .env file

const DEFAULT_CONFIG_PATH = "config.yaml"; // Default path for the YAML configuration file

// --- Configuration Parameters from market-maker.js ---
// These defaults are specific to the market-making strategy.
const MARKET_MAKER_DEFAULTS = {
    BID_SPREAD_BASE: 0.00025,
    ASK_SPREAD_BASE: 0.00025,
    SPREAD_MULTIPLIER: 1.5,
    MAX_ORDERS_PER_SIDE: 3,
    MIN_ORDER_SIZE: 0.0001,
    ORDER_SIZE_FIXED: false,
    VOLATILITY_WINDOW: 20,
    VOLATILITY_FACTOR: 2.0,
    REFRESH_INTERVAL: 5000, // Interval for refreshing market data in milliseconds
    HEARTBEAT_INTERVAL: 30000, // Interval for sending heartbeat signals in milliseconds
    RETRY_DELAY_BASE: 1000, // Base delay for retrying operations in milliseconds
    MAX_NET_POSITION: 0.01,
    STOP_ON_LARGE_POS: false,
    LOG_TO_FILE: false,
    LOG_LEVEL: 'info',
    DEBUG_MODE: false, // New debug flag to enable verbose logging
    PNL_CSV_PATH: './logs/pnl.csv', // Path to log Profit & Loss data
    USE_TERMUX_SMS: false,
    SMS_PHONE_NUMBER: '',
    POSITION_SKEW_FACTOR: 0.15,
    VOLATILITY_SPREAD_FACTOR: 0.75,
    STATE_FILE_PATH: './logs/state.json', // Path for saving bot state
    FILL_PROBABILITY: 0.15,
    SLIPPAGE_FACTOR: 0.0001,
    GRID_SPACING_BASE: 0.00015,
    IMBALANCE_SPREAD_FACTOR: 0.2,
    IMBALANCE_ORDER_SIZE_FACTOR: 0.5,
};

// --- General Bot Configuration Parameters (from ehlst.js and chanexit.js) ---
// These defaults apply to various trading bots and general operations.
const BOT_DEFAULTS = {
    API_KEY: process.env.BYBIT_API_KEY || '',
    API_SECRET: process.env.BYBIT_API_SECRET || '',
    TESTNET: process.env.TESTNET === 'true' || false,
    DRY_RUN: process.env.DRY_RUN === 'true' || false,
    TIMEZONE: 'UTC',
    MARKET_OPEN_HOUR: 0,
    MARKET_CLOSE_HOUR: 24,
    LOOP_WAIT_TIME_SECONDS: 5,
    ORDER_RETRY_ATTEMPTS: 3,
    ORDER_RETRY_DELAY_SECONDS: 1,
    MAX_POSITIONS: 1,
    MAX_OPEN_ORDERS_PER_SYMBOL: 1,
    MIN_KLINES_FOR_STRATEGY: 200,
    RISK_PER_TRADE_PCT: 0.01,
    MAX_NOTIONAL_PER_TRADE_USDT: 1000,
    MARGIN_MODE: 1, // 1 for Isolated, 0 for Cross
    LEVERAGE: 10,
    ORDER_TYPE: 'Market', // Market, Limit, Conditional
    POST_ONLY: false,
    PRICE_DETECTION_THRESHOLD_PCT: 0.0005,
    BREAKOUT_TRIGGER_PERCENT: 0.001,
    EMERGENCY_STOP_IF_DOWN_PCT: 15,
    POSITION_RECONCILIATION_INTERVAL_MINUTES: 5,
    MIN_BARS_BETWEEN_TRADES: 1,
    TRAILING_STOP_ACTIVE: true,
    FIXED_PROFIT_TARGET_PCT: 0.0,
    TRADING_SYMBOLS: ['BTCUSDT', 'ETHUSDT'],

    // Orchestrator settings for enabling/disabling specific strategies
    STRATEGIES: {
        ehlst: {
            enabled: false,
            // Add Ehlers Supertrend specific settings here if they are not already in BOT_DEFAULTS
            // For example:
            // EST_FAST_LENGTH: 10,
            // EST_FAST_MULTIPLIER: 2.0,
            // ...
        },
        whale: {
            enabled: false,
            // Add Whale strategy specific settings here
        },
        market_maker: {
            enabled: false,
            // Add Market Maker strategy specific settings here
        },
        chanexit: {
            enabled: false,
            // Add ChanExit strategy specific settings here
        },
        wbglm: {
            enabled: true,
            // Add wbglm specific settings here if needed
        },
        // Add other strategies as needed
    },

    // Indicator specific settings (from chanexit.js and ehlst.js)
    ATR_PERIOD: 14,
    CHANDELIER_MULTIPLIER: 3.0,
    MAX_ATR_MULTIPLIER: 4.0,
    MIN_ATR_MULTIPLIER: 1.0,
    VOLATILITY_LOOKBACK: 20,
    TREND_EMA_PERIOD: 50,
    EMA_SHORT_PERIOD: 8,
    EMA_LONG_PERIOD: 21,
    RSI_PERIOD: 14,
    RSI_OVERBOUGHT: 70,
    RSI_OVERSOLD: 30,
    VOLUME_MA_PERIOD: 20,
    VOLUME_THRESHOLD_MULTIPLIER: 1.5,
    HIGHER_TF_TIMEFRAME: 5, // Higher timeframe for analysis (in minutes)
    H_TF_EMA_SHORT_PERIOD: 8,
    H_TF_EMA_LONG_PERIOD: 21,

    // Ehlers Supertrend specific (from ehlst.js)
    EST_FAST_LENGTH: 10,
    EST_FAST_MULTIPLIER: 2.0,
    EST_SLOW_LENGTH: 20,
    EST_SLOW_MULTIPLIER: 3.0,
    EHLERS_FISHER_PERIOD: 10,
    ADX_PERIOD: 14,
    ADX_THRESHOLD: 25,

    // Filters (from chanexit.js)
    USE_EST_SLOW_FILTER: true, // Enable/disable Ehlers Supertrend slow filter
    USE_STOCH_FILTER: false, // Enable/disable Stochastic filter
    STOCH_K_PERIOD: 14,
    STOCH_D_PERIOD: 3,
    STOCH_SMOOTHING: 3,
    STOCH_OVERBOUGHT: 80,
    STOCH_OVERSOLD: 20,
    USE_MACD_FILTER: false, // Enable/disable MACD filter
    MACD_FAST_PERIOD: 12,
    MACD_SLOW_PERIOD: 26,
    MACD_SIGNAL_PERIOD: 9,
    USE_ADX_FILTER: false, // Enable/disable ADX filter
};

// --- Configuration Parameters from wb4.0.js and whale.js ---
// These defaults are specific to the "Whale" bot variations.
const WHALE_BOT_DEFAULTS = {
    BYBIT_BASE_URL: "https://api.bybit.com", // Base URL for Bybit API
    WEBSOCKET_URL: "wss://stream.bybit.com/v5/public/linear", // WebSocket URL for public data
    MAX_API_RETRIES: 5, // Maximum retries for API calls
    RETRY_DELAY_SECONDS: 7, // Delay between API retries
    REQUEST_TIMEOUT: 20000, // API request timeout in milliseconds
    LOOP_DELAY_SECONDS: 15, // Delay in main bot loop
    ORDERBOOK_LIMIT: 50, // Number of order book levels to fetch
    SIGNAL_SCORE_THRESHOLD: 2.0, // Threshold for trading signal score
    COOLDOWN_SEC: 60, // Cooldown period between trades in seconds
    HYSTERESIS_RATIO: 0.85, // Hysteresis ratio for signals
    VOLUME_CONFIRMATION_MULTIPLIER: 1.5, // Multiplier for volume confirmation
    TRADE_MANAGEMENT: {
        ENABLED: true, // Enable/disable trade management features
        ACCOUNT_BALANCE: 1000.0, // Simulated account balance for calculations
        RISK_PER_TRADE_PERCENT: 1.0, // Risk percentage per trade
        STOP_LOSS_ATR_MULTIPLE: 1.5, // Stop loss based on ATR multiple
        TAKE_PROFIT_ATR_MULTIPLE: 2.0, // Take profit based on ATR multiple
        MAX_OPEN_POSITIONS: 1, // Maximum number of open positions
        ORDER_PRECISION: 5, // Decimal precision for order quantities
        PRICE_PRECISION: 3, // Decimal precision for prices
        SLIPPAGE_PERCENT: 0.001, // Slippage percentage for market orders
        TRADING_FEE_PERCENT: 0.0005, // Trading fee percentage
    },
    MARTINGALE: {
        ENABLED: false, // Enable/disable Martingale strategy
        MULTIPLIER: 2.0, // Martingale multiplier
        MAX_LEVELS: 5 // Maximum Martingale levels
    },
    DASHBOARD: {
        ENABLED: true, // Enable/disable dashboard
        PORT: 3000, // Port for the dashboard
        UPDATE_INTERVAL_MS: 1000 // Dashboard update interval
    },
    RISK_GUARDRAILS: {
        ENABLED: true, // Enable/disable risk guardrails
        MAX_DAY_LOSS_PCT: 3.0, // Maximum daily loss percentage
        MAX_DRAWDOWN_PCT: 8.0, // Maximum drawdown percentage
        COOLDOWN_AFTER_KILL_MIN: 120, // Cooldown after emergency stop in minutes
        SPREAD_FILTER_BPS: 5.0, // Spread filter in basis points
        EV_FILTER_ENABLED: true, // Enable/disable EV filter
    },
    SESSION_FILTER: {
        ENABLED: false, // Enable/disable trading session filter
        UTC_ALLOWED: [["00:00", "08:00"], ["13:00", "20:00"]], // Allowed UTC trading hours
    },
    PYRAMIDING: {
        ENABLED: false, // Enable/disable pyramiding
        MAX_ADDS: 2, // Maximum pyramiding additions
        STEP_ATR: 0.7,
        SIZE_PCT_OF_INITIAL: 0.5,
    },
    MTF_ANALYSIS: {
        ENABLED: true, // Enable/disable multi-timeframe analysis
        HIGHER_TIMEFRAMES: ["60", "240"],
        TREND_INDICATORS: ["ema", "ehlers_supertrend"],
        TREND_PERIOD: 50,
        MTF_REQUEST_DELAY_SECONDS: 0.5,
    },
    ML_ENHANCEMENT: {"ENABLED": false},
    INDICATOR_SETTINGS: {
        ATR_PERIOD: 14,
        EMA_SHORT_PERIOD: 9,
        EMA_LONG_PERIOD: 21,
        RSI_PERIOD: 14,
        STOCH_RSI_PERIOD: 14,
        STOCH_K_PERIOD: 3,
        STOCH_D_PERIOD: 3,
        BOLLINGER_BANDS_PERIOD: 20,
        BOLLINGER_BANDS_STD_DEV: 2.0,
        CCI_PERIOD: 20,
        WILLIAMS_R_PERIOD: 14,
        MFI_PERIOD: 14,
        PSAR_ACCELERATION: 0.02,
        PSAR_MAX_ACCELERATION: 0.2,
        SMA_SHORT_PERIOD: 10,
        SMA_LONG_PERIOD: 50,
        FIBONACCI_WINDOW: 60,
        EHLERS_FAST_PERIOD: 10,
        EHLERS_FAST_MULTIPLIER: 2.0,
        EHLERS_SLOW_PERIOD: 20,
        EHLERS_SLOW_MULTIPLIER: 3.0,
        MACD_FAST_PERIOD: 12,
        MACD_SLOW_PERIOD: 26,
        MACD_SIGNAL_PERIOD: 9,
        ADX_PERIOD: 14,
        ICHIMOKU_TENKAN_PERIOD: 9,
        ICHIMOKU_KIJUN_PERIOD: 26,
        ICHIMOKU_SENKOU_SPAN_B_PERIOD: 52,
        ICHIMOKU_CHIKOU_SPAN_OFFSET: 26,
        OBV_EMA_PERIOD: 20,
        CMF_PERIOD: 20,
        RSI_OVERSOLD: 30,
        RSI_OVERBOUGHT: 70,
        STOCH_RSI_OVERSOLD: 20,
        STOCH_RSI_OVERBOUGHT: 80,
        CCI_OVERSOLD: -100,
        CCI_OVERBOUGHT: 100,
        WILLIAMS_R_OVERSOLD: -80,
        WILLIAMS_R_OVERBOUGHT: -20,
        MFI_OVERSOLD: 20,
        MFI_OVERBOUGHT: 80,
        VOLATILITY_INDEX_PERIOD: 20,
        VWMA_PERIOD: 20,
        VOLUME_DELTA_PERIOD: 5,
        VOLUME_DELTA_THRESHOLD: 0.2,
        KAMA_PERIOD: 10,
        KAMA_FAST_PERIOD: 2,
        KAMA_SLOW_PERIOD: 30,
        RELATIVE_VOLUME_PERIOD: 20,
        RELATIVE_VOLUME_THRESHOLD: 1.5,
        MARKET_STRUCTURE_LOOKBACK_PERIOD: 20,
        DEMA_PERIOD: 14,
        KELTNER_PERIOD: 20,
        KELTNER_ATR_MULTIPLIER: 2.0,
        ROC_PERIOD: 12,
        ROC_OVERSOLD: -5.0,
        ROC_OVERBOUGHT: 5.0,
    },
    INDICATORS: {
        EMA_ALIGNMENT: true,
        SMA_TREND_FILTER: true,
        MOMENTUM: true,
        VOLUME_CONFIRMATION: true,
        STOCH_RSI: true,
        RSI: true,
        BOLLINGER_BANDS: true,
        VWAP: true,
        CCI: true,
        WR: true,
        PSAR: true,
        SMA_10: true,
        MFI: true,
        ORDERBOOK_IMBALANCE: true,
        FIBONACCI_LEVELS: true,
        EHLERS_SUPERTREND: true,
        MACD: true,
        ADX: true,
        ICHIMOKU_CLOUD: true,
        OBV: true,
        CMF: true,
        VOLATILITY_INDEX: true,
        VWMA: true,
        VOLUME_DELTA: true,
        KAUFMAN_AMA: true,
        RELATIVE_VOLUME: true,
        MARKET_STRUCTURE: true,
        DEMA: true,
        KELTNER_CHANNELS: true,
        ROC: true,
        CANDLESTICK_PATTERNS: true,
        FIBONACCI_PIVOT_POINTS: true,
    },
    WEIGHT_SETS: {
        DEFAULT_SCALPING: {
            EMA_ALIGNMENT: 0.30,
            SMA_TREND_FILTER: 0.20,
            EHLERS_SUPERTREND_ALIGNMENT: 0.40,
            MACD_ALIGNMENT: 0.30,
            ADX_STRENGTH: 0.25,
            ICHIMOKU_CONFLUENCE: 0.35,
            PSAR: 0.15,
            VWAP: 0.15,
            VWMA_CROSS: 0.10,
            SMA_10: 0.05,
            BOLLINGER_BANDS: 0.25,
            MOMENTUM_RSI_STOCH_CCI_WR_MFI: 0.35,
            VOLUME_CONFIRMATION: 0.10,
            OBV_MOMENTUM: 0.15,
            CMF_FLOW: 0.10,
            VOLUME_DELTA_SIGNAL: 0.10,
            ORDERBOOK_IMBALANCE: 0.10,
            MTF_TREND_CONFLUENCE: 0.25,
            VOLATILITY_INDEX_SIGNAL: 0.10,
            KAUFMAN_AMA_CROSS: 0.20,
            RELATIVE_VOLUME_CONFIRMATION: 0.10,
            MARKET_STRUCTURE_CONFLUENCE: 0.25,
            DEMA_CROSSOVER: 0.18,
            KELTNER_BREAKOUT: 0.20,
            ROC_SIGNAL: 0.12,
            CANDLESTICK_CONFIRMATION: 0.15,
            FIBONACCI_PIVOT_POINTS_CONFLUENCE: 0.20,
        }
    },
    EXECUTION: {
        USE_PYBIT: false,
        TESTNET: false,
        ACCOUNT_TYPE: "UNIFIED",
        CATEGORY: "linear",
        POSITION_MODE: "ONE_WAY",
        TPSL_MODE: "Full",
        BUY_LEVERAGE: "3",
        SELL_LEVERAGE: "3",
        TP_TRIGGER_BY: "LastPrice",
        SL_TRIGGER_BY: "LastPrice",
        DEFAULT_TIME_IN_FORCE: "GTC",
        REDUCE_ONLY_DEFAULT: false,
        POST_ONLY_DEFAULT: false,
        POSITION_IDX_OVERRIDES: {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
        PROXIES: {"ENABLED": false, "HTTP": "", "HTTPS": ""},
        TP_SCHEME: {
            MODE: "atr_multiples",
            TARGETS: [
                {"NAME": "TP1", "ATR_MULTIPLE": 1.0, "SIZE_PCT": 0.40, "ORDER_TYPE": "Limit", "TIF": "PostOnly", "POST_ONLY": true},
                {"NAME": "TP2", "ATR_MULTIPLE": 1.5, "SIZE_PCT": 0.40, "ORDER_TYPE": "Limit", "TIF": "IOC", "POST_ONLY": false},
                {"NAME": "TP3", "ATR_MULTIPLE": 2.0, "SIZE_PCT": 0.20, "ORDER_TYPE": "Limit", "TIF": "GTC", "POST_ONLY": false},
            ],
        },
        SL_SCHEME: {
            TYPE: "atr_multiple",
            ATR_MULTIPLE: 1.5,
            PERCENT: 1.0,
            USE_CONDITIONAL_STOP: true,
            STOP_ORDER_TYPE: "Market",
        },
        BREAKEVEN_AFTER_TP1: {
            ENABLED: true,
            OFFSET_TYPE: "atr",
            OFFSET_VALUE: 0.10,
            LOCK_IN_MIN_PERCENT: 0,
            SL_TRIGGER_BY: "LastPrice",
        },
        LIVE_SYNC: {
            ENABLED: true,
            POLL_MS: 2500,
            MAX_EXEC_FETCH: 200,
            ONLY_TRACK_LINKED: true,
            HEARTBEAT: {"ENABLED": true, "INTERVAL_MS": 5000},
        },
    },
};

class ConfigManager {
    constructor() {
        this.config = {};
        this.loadConfig();
    }

    loadConfig(configPath = DEFAULT_CONFIG_PATH) {
        let fileConfig = {};
        try {
            const fullPath = path.resolve(process.cwd(), configPath);
            if (fs.existsSync(fullPath)) {
                const fileContents = fs.readFileSync(fullPath, 'utf8');
                fileConfig = yaml.load(fileContents) || {};
                console.log(`Successfully loaded configuration from ${configPath}.`);
            } else {
                console.warn(`Configuration file '${configPath}' not found. Using default and environment variables.`);
            }
        } catch (e) {
            console.error(`Error loading config file '${configPath}': ${e.message}. Using default and environment variables.`);
        }

        // Merge all defaults
        this.config = {
            ...BOT_DEFAULTS,
            ...MARKET_MAKER_DEFAULTS,
            ...WHALE_BOT_DEFAULTS,
            ...fileConfig, // File config overrides defaults
            // Environment variables override everything
            API_KEY: process.env.BYBIT_API_KEY || fileConfig.API_KEY || BOT_DEFAULTS.API_KEY,
            API_SECRET: process.env.BYBIT_API_SECRET || fileConfig.API_SECRET || BOT_DEFAULTS.API_SECRET,
            TESTNET: process.env.TESTNET === 'true' || fileConfig.TESTNET || BOT_DEFAULTS.TESTNET,
            DRY_RUN: process.env.DRY_RUN === 'true' || fileConfig.DRY_RUN || BOT_DEFAULTS.DRY_RUN,
            SYMBOL: process.env.SYMBOL || fileConfig.SYMBOL || MARKET_MAKER_DEFAULTS.SYMBOL, // Specific to market-maker
            LOG_LEVEL: process.env.LOG_LEVEL || fileConfig.LOG_LEVEL || BOT_DEFAULTS.LOG_LEVEL,
            LOG_TO_FILE: process.env.LOG_TO_FILE === 'true' || fileConfig.LOG_TO_FILE || BOT_DEFAULTS.LOG_TO_FILE,
            DEBUG_MODE: process.env.DEBUG_MODE === 'true' || fileConfig.DEBUG_MODE || BOT_DEFAULTS.DEBUG_MODE, // Load debug mode
            USE_TERMUX_SMS: process.env.USE_TERMUX_SMS === 'true' || fileConfig.USE_TERMUX_SMS || BOT_DEFAULTS.USE_TERMUX_SMS,
            SMS_PHONE_NUMBER: process.env.SMS_PHONE_NUMBER || fileConfig.SMS_PHONE_NUMBER || BOT_DEFAULTS.SMS_PHONE_NUMBER,
            BYBIT_BASE_URL: process.env.BYBIT_BASE_URL || fileConfig.BYBIT_BASE_URL || WHALE_BOT_DEFAULTS.BYBIT_BASE_URL,
            WEBSOCKET_URL: process.env.WEBSOCKET_URL || fileConfig.WEBSOCKET_URL || WHALE_BOT_DEFAULTS.WEBSOCKET_URL,
            // Add other env vars that should override file/defaults
        };

        // Ensure boolean values are correctly parsed from environment variables
        this.config.TESTNET = String(this.config.TESTNET).toLowerCase() === 'true';
        this.config.DRY_RUN = String(this.config.DRY_RUN).toLowerCase() === 'true';
        this.config.ORDER_SIZE_FIXED = String(this.config.ORDER_SIZE_FIXED).toLowerCase() === 'true';
        this.config.STOP_ON_LARGE_POS = String(this.config.STOP_ON_LARGE_POS).toLowerCase() === 'true';
        this.config.LOG_TO_FILE = String(this.config.LOG_TO_FILE).toLowerCase() === 'true';
        this.config.USE_TERMUX_SMS = String(this.config.USE_TERMUX_SMS).toLowerCase() === 'true';
        this.config.POST_ONLY = String(this.config.POST_ONLY).toLowerCase() === 'true';
        this.config.TRAILING_STOP_ACTIVE = String(this.config.TRAILING_STOP_ACTIVE).toLowerCase() === 'true';
        this.config.USE_FISHER_EXIT = String(this.config.USE_FISHER_EXIT).toLowerCase() === 'true';
        this.config.USE_EST_SLOW_FILTER = String(this.config.USE_EST_SLOW_FILTER).toLowerCase() === 'true';
        this.config.USE_STOCH_FILTER = String(this.config.USE_STOCH_FILTER).toLowerCase() === 'true';
        this.config.USE_MACD_FILTER = String(this.config.USE_MACD_FILTER).toLowerCase() === 'true';
        this.config.USE_ADX_FILTER = String(this.config.USE_ADX_FILTER).toLowerCase() === 'true';

        // Recursively ensure boolean values in nested objects
        const ensureBooleans = (obj) => {
            for (const key in obj) {
                if (typeof obj[key] === 'object' && obj[key] !== null) {
                    ensureBooleans(obj[key]);
                } else if (typeof obj[key] === 'string' && (obj[key].toLowerCase() === 'true' || obj[key].toLowerCase() === 'false')) {
                    obj[key] = obj[key].toLowerCase() === 'true';
                }
            }
        };
        ensureBooleans(this.config);

        // Override LOG_LEVEL if DEBUG_MODE is true
        if (this.config.DEBUG_MODE) {
            this.config.LOG_LEVEL = 'debug';
            console.log("DEBUG_MODE is enabled. Setting LOG_LEVEL to 'debug'.");
        }

        // Validate required API keys for non-dry-run
        if (!this.config.DRY_RUN && (!this.config.API_KEY || !this.config.API_SECRET)) {
            console.error("ERROR: API_KEY and API_SECRET must be provided in .env or config.yaml for live trading.");
            process.exit(1);
        }
    }

    get(key) {
        return this.config[key];
    }
}

const configManager = new ConfigManager();
export const CONFIG = configManager.config;