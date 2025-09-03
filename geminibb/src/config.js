// Central configuration for the trading bot
export const config = {
    // Trading Pair and Timeframe
    symbol: 'BTCUSDT',
    interval: '60', // 60 minutes (1h)

    // Risk Management
    riskPercentage: 1.5, // Risk 1.5% of equity per trade
    riskToRewardRatio: 2, // Aim for a 2:1 reward/risk ratio (e.g., 4% TP for 2% SL)
    stopLossPercentage: 2, // The maximum percentage of price movement for the stop-loss

    // Execution Settings
    hedgeMode: false,       // Set to true for dual-side (hedged) positions, false for one-way.
    flipCooldownMs: 30000,  // Cooldown in milliseconds to prevent rapid position flips.
    maxSpreadPct: 0.0015,   // Maximum allowed bid-ask spread percentage to place a trade (e.g., 0.0015 for 0.15%).
    dryRun: false,          // Set to true to simulate trades without executing them on the exchange.

    // Technical Indicator Settings
    indicators: {
        rsiPeriod: 14,
        smaShortPeriod: 20,
        smaLongPeriod: 50,
        macd: {
            fastPeriod: 12,
            slowPeriod: 26,
            signalPeriod: 9,
        },
        atrPeriod: 14,
    },

    // AI Settings
    ai: {
        model: 'gemini-pro',
        confidenceThreshold: 0.7, // Minimum confidence score from AI to consider a trade
    },

    // API Endpoints
    bybit: {
        restUrl: 'https://api.bytick.com',
        wsUrl: 'wss://stream.bytick.com/v5/public/linear',
    },
};