// src/config.js
export const config = {
    // Trading Pair and Intervals
    symbol: 'BTCUSDT',
    primaryInterval: '15', // Primary interval for trading signals
    multiTimeframeIntervals: ['60', '240'], // Higher timeframes for trend context

    // NEW: Dry Run / Paper Trading Mode
    // If true, no real orders will be placed. Logs intended actions instead.
    dryRun: true,

    // API Endpoints
    bybit: {
        restUrl: 'https://api.bybit.com',
        wsUrl: 'wss://stream.bybit.com/v5/public/linear',
        privateWsUrl: 'wss://stream.bybit.com/v5/private',
        testnet: false,
        category: 'linear', // IMPROVEMENT 3: Consistent category for Bybit API
        accountType: 'UNIFIED', // IMPROVEMENT 3: Consistent account type
        requestRetryAttempts: 3,
        requestTimeoutMs: 5000, // IMPROVEMENT 3: Request timeout for REST API
        recvWindow: '20000', // Bybit default for recvWindow
        requestIntervalMs: 200, // Delay between queued requests for rate limiting
        maxRetries: 3,          // Max retries for failed API requests
        maxRetryDelayMs: 10000, // Max delay for exponential backoff (10 seconds)
        publicPingIntervalMs: 20000, // Ping interval for public WS
        privatePingIntervalMs: 20000, // Ping interval for private WS
        maxReconnectDelayMs: 60000, // IMPROVEMENT 9: Max delay for WS reconnection backoff
    },

    // Technical Indicator Settings
    indicators: {
        rsiPeriod: 14,
        smaShortPeriod: 20,
        smaLongPeriod: 50,
        atrPeriod: 14,
        macd: { fastPeriod: 12, slowPeriod: 26, signalPeriod: 9 },
    },

    // Risk Management
    riskPercentage: 2.0,
    riskToRewardRatio: 1.5,
    stopLossStrategy: 'atr', // 'atr', 'percentage', 'trailing' (IMPROVEMENT 17)
    stopLossPercentage: 1.5,
    atrMultiplier: 2.0,
    slippagePercentage: 0.05,
    exchangeFeePercentage: 0.055,
    tradeCooldownMinutes: 30,
    maxDailyLossPercentage: 10, // IMPROVEMENT 17: Max percentage of initial balance allowed to lose per day
    maxOpenPositions: 1, // IMPROVEMENT 18: Max concurrent open positions (for future expansion)

    // Order Precision & Minimums (These will be dynamically loaded from Bybit API if possible)
    pricePrecision: 2, // Default, overridden by Bybit API
    quantityPrecision: 3, // Default, overridden by Bybit API
    minOrderSize: 0.001, // Default min order size if API info isn't available

    // AI Model Configuration
    geminiModel: 'gemini-2.5-flash-lite',
    gemini: { // IMPROVEMENT 13: Configurable Gemini parameters
        temperature: 0.7,
        topP: 0.9,
    },
}