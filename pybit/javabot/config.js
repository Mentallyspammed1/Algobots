// config.js
// Configuration for the Ehlers Chandelier Exit Scalper (chanexit.js)

export const BOT_CONFIG = {
    // --- API Configuration ---
    // API_KEY and API_SECRET are primarily read from environment variables (e.g., in a .env file).
    // These defaults are placeholders for illustration. DO NOT hardcode sensitive keys here in production.
    API_KEY: process.env.BYBIT_API_KEY || 'YOUR_BYBIT_API_KEY',
    API_SECRET: process.env.BYBIT_API_SECRET || 'YOUR_BYBIT_API_SECRET',
    TESTNET: true, // Set to true for Bybit Testnet, false for Mainnet
    DRY_RUN: true, // Set to true to simulate trades without real execution (requires no API keys if true)

    // --- Logging ---
    // Valid levels: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    LOG_LEVEL: "INFO", 

    // --- API Request & Order Handling ---
    ORDER_RETRY_ATTEMPTS: 3, // How many times to retry API calls on failure
    ORDER_RETRY_DELAY_SECONDS: 1, // Delay between retries in seconds

    // --- Trading Parameters ---
    TRADING_SYMBOLS: ["BTCUSDT", "ETHUSDT"], // List of symbols to trade (e.g., ["BTCUSDT", "SOLUSDT"])
    TIMEFRAME: 5, // Kline timeframe in minutes (e.g., 1, 5, 15, 60)
    
    // Timezone for market open/close checks
    TIMEZONE: "UTC", // e.g., "America/New_York", "Europe/London", "Asia/Shanghai"
    MARKET_OPEN_HOUR: 0, // 24-hour format (e.g., 9 for 9 AM)
    MARKET_CLOSE_HOUR: 24, // 24-hour format (e.g., 17 for 5 PM, 24 for always open)
    
    LOOP_WAIT_TIME_SECONDS: 10, // How long to wait between main loop iterations

    // --- Multi-Timeframe Confirmation (Higher TF) ---
    HIGHER_TF_TIMEFRAME: 60, // Higher timeframe for trend confirmation (e.g., 60 for 1-hour)
    H_TF_EMA_SHORT_PERIOD: 8, // Short EMA period for HTF trend
    H_TF_EMA_LONG_PERIOD: 21, // Long EMA period for HTF trend

    // --- Indicator Periods & Multipliers ---
    MIN_KLINES_FOR_STRATEGY: 50, // Minimum number of klines required to calculate all indicators
    
    // Chandelier Exit specific parameters
    CHANDELIER_MULTIPLIER: 3.0, // Base multiplier for Chandelier Exit (controls sensitivity)
    MAX_ATR_MULTIPLIER: 4.0,    // Max dynamic ATR multiplier
    MIN_ATR_MULTIPLIER: 2.0,    // Min dynamic ATR multiplier
    VOLATILITY_LOOKBACK: 20,    // Period for volatility calculation
    
    ATR_PERIOD: 14,             // Period for Average True Range
    TREND_EMA_PERIOD: 200,      // Long-term EMA for trend filtering
    EMA_SHORT_PERIOD: 5,        // Short EMA for crossover
    EMA_LONG_PERIOD: 10,        // Long EMA for crossover
    RSI_PERIOD: 14,             // Period for Relative Strength Index
    RSI_OVERBOUGHT: 70,         // RSI overbought threshold
    RSI_OVERSOLD: 30,           // RSI oversold threshold
    
    VOLUME_MA_PERIOD: 20,           // Period for Volume Moving Average
    VOLUME_THRESHOLD_MULTIPLIER: 1.5, // Multiplier for volume spike detection (e.g., 1.5x average volume)

    // Ehlers Supertrend parameters
    EST_SLOW_LENGTH: 20,        // Period for the slow Ehlers Supertrend
    EST_SLOW_MULTIPLIER: 3.0,   // Multiplier for the slow Ehlers Supertrend
    
    // Ehlers Fisher Transform parameters
    EHLERS_FISHER_PERIOD: 10,   // Period for Ehlers Fisher Transform

    // --- Optional Indicator Filters (set to true to enable) ---
    USE_STOCH_FILTER: true,
    STOCH_K_PERIOD: 14,
    STOCH_D_PERIOD: 3,
    STOCH_SMOOTHING: 3,
    STOCH_OVERBOUGHT: 80,
    STOCH_OVERSOLD: 20,

    USE_MACD_FILTER: true,
    MACD_FAST_PERIOD: 12,
    MACD_SLOW_PERIOD: 26,
    MACD_SIGNAL_PERIOD: 9,

    USE_ADX_FILTER: true,
    ADX_PERIOD: 14,
    ADX_THRESHOLD: 25, // ADX value above which trend strength is considered significant

    USE_EST_SLOW_FILTER: true, // Use the slow Ehlers Supertrend for trend confirmation
    
    // --- Exit Conditions ---
    USE_FISHER_EXIT: true,        // Enable early exit on Fisher Transform flip
    TRAILING_STOP_ACTIVE: true,   // Enable trailing stop loss based on Chandelier Exit
    MAX_HOLDING_CANDLES: 120,     // Max number of candles to hold a position before exiting (e.g., 120 * 5min = 10 hours)
    FIXED_PROFIT_TARGET_PCT: 0.02, // Exit if position is 2% in profit (0.02 = 2%)

    // --- Order & Risk Management ---
    REWARD_RISK_RATIO: 2.5,        // Target Take Profit / Stop Loss ratio
    RISK_PER_TRADE_PCT: 0.01,      // Percentage of total balance to risk per trade (0.01 = 1%)
    MAX_POSITIONS: 1,              // Maximum number of concurrent open positions
    MAX_OPEN_ORDERS_PER_SYMBOL: 1, // Max open orders (including conditional) per symbol
    MAX_NOTIONAL_PER_TRADE_USDT: 1000, // Max USD value for a single trade (e.g., 1000 USDT)
    MIN_BARS_BETWEEN_TRADES: 5,    // Minimum number of bars to wait after a signal before taking another trade on the same symbol

    // --- Position Reconciliation ---
    POSITION_RECONCILIATION_INTERVAL_MINUTES: 10, // How often to reconcile DB positions with exchange

    // --- Emergency Stop ---
    EMERGENCY_STOP_IF_DOWN_PCT: 15, // Stop trading if equity drops by this percentage from its reference point

    // --- Bybit Specific Order Settings ---
    MARGIN_MODE: 1, // 1 for Isolated, 0 for Cross (Unified accounts manage this differently, often implicit)
    LEVERAGE: 10,   // Desired leverage for trades
    ORDER_TYPE: "Market", // "Market", "Limit", or "Conditional" for entry orders
    POST_ONLY: false,     // For limit orders: true to ensure order is not immediately filled
    PRICE_DETECTION_THRESHOLD_PCT: 0.0005, // Threshold for detecting price near S/R or orderbook levels (0.0005 = 0.05%)
    BREAKOUT_TRIGGER_PERCENT: 0.001 // Percentage above/below current price for conditional order trigger (0.001 = 0.1%)
};
