
const yargs = require('yargs/yargs');
const { hideBin } = require('yargs/helpers');
const argv = yargs(hideBin(process.argv)).argv;

// --- Configuration ---
const CONFIG = {
    symbols: process.env.SYMBOLS ? process.env.SYMBOLS.split(',').map(s => s.trim()) : [argv.symbol || 'BTCUSDT'], // Improvement 11: Multi-symbol support, allow override via env
    interval: process.env.INTERVAL || argv.interval || '1m', // Allow override via env or CLI
    baseFetchLimit: 150, // Base limit; will be dynamically adjusted
    fetchBuffer: 1.5,    // Improvement 6: Configurable buffer
    retryAttempts: 3,    // Improvement 1: Auto-retry
    retryDelay: 1000,    // Improvement 2: Backoff base delay (ms)

    periods: {
        smaShort: 10, smaLong: 30, emaShort: 10, emaLong: 30,
        macd: { fast: 12, slow: 26, signal: 9 },
        rsi: 14, stochastic: { k: 14, d: 3 }, atr: 14,
        bollinger: { period: 20, stdDev: 2 },
        williamsR: 14, cmf: 20, elderRay: 13,
        keltner: { period: 10, atrMultiplier: 1.5 },
        aroon: 25,
    },

    weights: {
        smaCrossoverBullish: 1.5, smaCrossoverBearish: 1.5,
        emaCrossoverBullish: 2.0, emaCrossoverBearish: 2.0,
        rsiOversold: 1.0, rsiOverbought: 1.0,
        stochasticBullishCross: 1.2, stochasticBearishCross: 1.2,
        bollingerBandBreakoutUpper: 0.8, bollingerBandBreakoutLower: 0.8,
        bollingerPriceAboveMiddle: 0.5, bollingerPriceBelowMiddle: 0.5,
        williamsROversold: 1.0, williamsROverbought: 1.0,
        cmfPositive: 1.3, cmfNegative: 1.3,
        elderRayBullish: 1.0, elderRayBearish: 1.0,
        keltnerChannelBreakoutUpper: 0.9, keltnerChannelBreakoutLower: 0.9,
        aroonUptrend: 1.0, aroonDowntrend: 1.0,
        macdBullish: 1.5, macdBearish: 1.5, // Activated with defaults
    },

    signalThresholds: {
        strength: 3.0, // Minimum weighted score difference for a "strong" signal
        rsiOversold: 30, rsiOverbought: 70,
        stochasticOversold: 20, stochasticOverbought: 80,
        williamsROversold: -80, williamsROverbought: -20,
        aroonUptrend: 70, aroonDowntrend: 70,
    },

    tradeManagement: {
        atrMultiplierTP: 1.5,
        atrMultiplierSL: 1.0,
        confidenceThresholdLow: 3.0,
        confidenceThresholdMedium: 6.0,
        confidenceThresholdHigh: 10.0,
        riskPerTrade: parseFloat(process.env.RISK_PER_TRADE) || 0.01, // 1% of account balance
    },

    bybitApiUrl: 'https://api.bybit.com/v5/market/kline',
    apiCategory: 'linear',
    logFile: 'signals.log', // Improvement 17: Logging to file
    continuousMode: argv.continuous, // Improvement 12: Continuous monitoring
    loopInterval: parseInt(process.env.LOOP_INTERVAL_MS) || 60000, // Default 1 minute in ms, allow env override
    webhookUrl: process.env.WEBHOOK_URL || '',
    newsApiKey: process.env.NEWS_API_KEY || '',
};

module.exports = CONFIG;
