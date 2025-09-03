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
        requestRetryAttempts: 3, // Number of times to retry a failed API request
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
    stopLossStrategy: 'atr',
    stopLossPercentage: 1.5,
    atrMultiplier: 2.0,
    // NEW: Slippage and fee estimation for more accurate calculations
    slippagePercentage: 0.05, // Estimated 0.05% slippage on market orders
    exchangeFeePercentage: 0.055, // Bybit taker fee for USDT perpetuals
    // NEW: Cooldown period after a trade is closed (in minutes)
    tradeCooldownMinutes: 30,

    // Order Precision & Minimums
    pricePrecision: 2,
    quantityPrecision: 3,
    minOrderSize: 0.001,

    // AI Model Configuration
    geminiModel: 'gemini-1.5-pro-latest',
};