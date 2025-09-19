import { z } from 'zod';

// Helper to transform string 'true'/'false' to boolean
const booleanFromString = z.preprocess((val) => {
    if (typeof val === 'string') {
        if (val.toLowerCase() === 'true') return true;
        if (val.toLowerCase() === 'false') return false;
    }
    return val;
}, z.boolean());

// Schema for common settings applicable to the entire bot
const commonSchema = z.object({
    API_KEY: z.string().optional().describe('Bybit API Key'),
    API_SECRET: z.string().optional().describe('Bybit API Secret'),
    TESTNET: booleanFromString.default(false).describe('Use Bybit testnet'),
    DRY_RUN: booleanFromString.default(true).describe('Simulate trades without using real funds'),
    TIMEZONE: z.string().default('UTC'),
    LOOP_WAIT_TIME_SECONDS: z.number().positive().default(5),
    ORDER_RETRY_ATTEMPTS: z.number().int().min(0).default(3),
    ORDER_RETRY_DELAY_SECONDS: z.number().positive().default(1),
});

// Schema for indicator settings, used by multiple strategies
const indicatorSettingsSchema = z.object({
    ATR_PERIOD: z.number().int().positive().default(14),
    TREND_EMA_PERIOD: z.number().int().positive().default(50),
    EMA_SHORT_PERIOD: z.number().int().positive().default(8),
    EMA_LONG_PERIOD: z.number().int().positive().default(21),
    RSI_PERIOD: z.number().int().positive().default(14),
    RSI_OVERBOUGHT: z.number().int().positive().default(70),
    RSI_OVERSOLD: z.number().int().positive().default(30),
    VOLUME_MA_PERIOD: z.number().int().positive().default(20),
    // Ehlers Supertrend specific
    EST_FAST_LENGTH: z.number().int().positive().default(10),
    EST_FAST_MULTIPLIER: z.number().positive().default(2.0),
    EST_SLOW_LENGTH: z.number().int().positive().default(20),
    EST_SLOW_MULTIPLIER: z.number().positive().default(3.0),
    EHLERS_FISHER_PERIOD: z.number().int().positive().default(10),
    ADX_PERIOD: z.number().int().positive().default(14),
    ADX_THRESHOLD: z.number().int().positive().default(25),
});

// Schema for the 'ehlst' (Ehlers Supertrend) strategy
const ehlstStrategySchema = z.object({
    enabled: booleanFromString.default(false),
    symbol: z.string().default('BTCUSDT'),
    timeframe: z.string().default('5'),
    max_positions: z.number().int().min(1).default(1),
    leverage: z.number().int().positive().default(10),
    risk_per_trade_pct: z.number().positive().default(1.0),
    // You can add more strategy-specific overrides here
});

// Schema for the 'whale' strategy
const whaleStrategySchema = z.object({
    enabled: booleanFromString.default(false),
    symbol: z.string().default('BTCUSDT'),
    timeframe: z.string().default('5'),
    loop_delay_seconds: z.number().positive().default(15),
    signal_score_threshold: z.number().default(2.0),
    ORDERBOOK_LIMIT: z.number().int().positive().default(50),
    COOLDOWN_SEC: z.number().int().positive().default(60),
    HYSTERESIS_RATIO: z.number().positive().default(0.85),
    VOLUME_CONFIRMATION_MULTIPLIER: z.number().positive().default(1.5),
    // ... add other whale-specific settings from WHALE_BOT_DEFAULTS
});


// Main configuration schema that combines all the parts
const configSchema = z.object({
    common: commonSchema,
    indicators: indicatorSettingsSchema,
    strategies: z.object({
        ehlst: ehlstStrategySchema,
        whale: whaleStrategySchema,
        // Future strategies would be added here
        market_maker: z.object({ enabled: z.boolean().default(false) }).passthrough(),
        chanexit: z.object({ enabled: z.boolean().default(false) }).passthrough(),
        wbglm: z.object({ enabled: z.boolean().default(false) }).passthrough(),
    }),
});

export { configSchema };