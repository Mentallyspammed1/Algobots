
const { Decimal } = require('decimal.js');

// unified_config.js
// A single source of truth for all bot configurations.
// Merged from config.js, config.yaml, and config.json

const RAW_UNIFIED_CONFIG = {
    // --- API & General Settings ---
    api: {
        key: process.env.BYBIT_API_KEY || null,
        secret: process.env.BYBIT_API_SECRET || null,
        testnet: false,
        dryRun: true, // Global dry run flag
        category: 'linear',
        accountType: 'UNIFIED',
        retryAttempts: 5,
        retryDelaySeconds: 2,
        requestTimeoutMs: 15000,
    },

    // --- Global Bot Settings ---
    bot: {
        logLevel: "INFO", // DEBUG, INFO, WARNING, ERROR, CRITICAL
        timezone: "UTC",
        loopWaitTimeSeconds: 15,
    },

    // --- Trading Parameters ---
    trading: {
        symbols: ["BTCUSDT", "ETHUSDT"],
        timeframe: "15",
        maxOpenPositions: 1,
        cooldownSec: 60, // Cooldown between trades for the same symbol
        min_klines_for_strategy: 200, // Minimum klines required for strategy calculation
        sessionFilter: {
            enabled: false,
            utcAllowed: [["00:00", "08:00"], ["13:00", "20:00"]],
        },
    },

    // --- Risk Management ---
    risk: {
        riskPerTradePercent: 1.0,
        maxNotionalPerTradeUsdt: 1000,
        guardrails: {
            enabled: true,
            maxDayLossPct: 3.0,
            maxDrawdownPct: 8.0,
            cooldownAfterKillMin: 120,
            spreadFilterBps: 5.0,
        },
        emergencyStopIfDownPct: 15,
    },

    // --- Order Execution ---
    execution: {
        leverage: 10,
        marginMode: 1, // 1 for Isolated, 0 for Cross
        orderType: "Market", // Market, Limit, Conditional
        postOnly: false,
        priceDetectionThresholdPct: 0.0005,
        breakoutTriggerPercent: 0.001,
        tpTriggerBy: "MarkPrice",
        slTriggerBy: "MarkPrice",
        reward_risk_ratio: 2.5, // Default reward to risk ratio for TP/SL calculation
    },

    // --- Advanced Position Management ---
    positionManagement: {
        pyramiding: {
            enabled: false,
            maxAdds: 2,
            stepAtr: 0.7,
            sizePctOfInitial: 0.5,
        },
        martingale: {
            enabled: false,
            multiplier: 2.0,
            maxLevels: 5,
        },
        trailingStop: {
            active: true,
            atrMultiple: 1.2,
        },
        breakEven: {
            enabled: true,
            afterTp1: true,
            offsetAtr: 0.1,
        },
    },

    // --- Strategy Specific Settings ---
    strategies: {
        // Settings from chanexit.js (config.js)
        chanExit: {
            higherTfTimeframe: 60,
            htfEmaShort: 8,
            htfEmaLong: 21,
            atrPeriod: 14,
            trendEmaPeriod: 200,
            emaShort: 5,
            emaLong: 10,
            rsiPeriod: 14,
            rsiOverbought: 70,
            rsiOversold: 30,
            volumeMaPeriod: 20,
            volumeThresholdMultiplier: 1.5,
            useFisherExit: true,
            maxHoldingCandles: 120,
            fixedProfitTargetPct: 0.02,
            rewardRiskRatio: 2.5,
            trailingStopActive: true,
            minBarsBetweenTrades: 1,
            positionReconciliationIntervalMinutes: 5,
            chandelierMultiplier: 3.0,
            maxAtrMultiplier: 5.0,
            minAtrMultiplier: 1.0,
            volatilityLookback: 20,
            estSlowLength: 8,
            estSlowMultiplier: 1.2,
            ehlersFisherPeriod: 8,
        },
        // Settings from ehlst.js (config.yaml)
        ehlersSupertrend: {
            fast: { length: 10, multiplier: 1.0 },
            slow: { length: 20, multiplier: 2.0 },
            rsi: { period: 14, confirmLong: 40, confirmShort: 60, overbought: 70, oversold: 30 },
            volume: { maPeriod: 20, thresholdMultiplier: 1.5 },
            fisher: { period: 10 },
            atr: { period: 14 },
            adx: { period: 14, threshold: 25 },
        },
        // Settings from wb*.js (config.json) - These are extensive and should be fully populated
        whaleBot: {
            signalScoreThreshold: 2.0,
            hysteresisRatio: 0.85,
            mtfAnalysis: {
                enabled: true,
                higherTimeframes: ["60", "240"],
                trendIndicators: ["ema", "ehlers_supertrend"],
                trendPeriod: 50,
            },
            // NOTE: The following sections are placeholders and should be populated
            // with the detailed settings from the original config.json
            indicatorSettings: {
                "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
                "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
                "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
                "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02,
                "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50
            },
            indicators: {
                "ema_alignment": true, "sma_trend_filter": true, "momentum": true,
                "volume_confirmation": true, "stoch_rsi": true, "rsi": true
            },
            weightSets: {
                "default_scalping": { "ema_alignment": 0.30, "sma_trend_filter": 0.20 }
            },
        },
    },

    // --- Dashboard ---
    dashboard: {
        enabled: true,
        port: 3000,
        updateIntervalMs: 1000,
    },
};

function convertNumericStrings(obj) {
    for (const key in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, key)) {
            const value = obj[key];
            if (typeof value === 'string' && !isNaN(parseFloat(value)) && isFinite(value)) {
                obj[key] = parseFloat(value);
            } else if (typeof value === 'object' && value !== null) {
                convertNumericStrings(value);
            }
        }
    }
}

// Convert numeric strings in the raw config to numbers
convertNumericStrings(RAW_UNIFIED_CONFIG);

// Export the processed config
export const UNIFIED_CONFIG = RAW_UNIFIED_CONFIG;
