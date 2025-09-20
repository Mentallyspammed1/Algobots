// config.js
import dotenv from 'dotenv';
import { z } from 'zod';

dotenv.config({ override: true });

const configSchema = z.object({
    API_KEY: z.string().min(1, "BYBIT_API_KEY is required"),
    API_SECRET: z.string().min(1, "BYBIT_API_SECRET is required"),
    TESTNET: z.boolean().default(false),
    DRY_RUN: z.boolean().default(false),
    SYMBOL: z.string().min(1, "SYMBOL is required"),
    CATEGORY: z.enum(['linear', 'spot', 'inverse']).default('linear'),
    ACCOUNT_TYPE: z.enum(['UNIFIED', 'CONTRACT', 'SPOT']).default('UNIFIED'),
    TIMEFRAME: z.number().int().positive().default(5),
    LOOP_INTERVAL_MS: z.number().int().positive().default(10000),
    CE_ATR_PERIOD: z.number().int().positive().default(22),
    CE_ATR_MULTIPLIER: z.number().positive().default(3.0),
    TRADE_AMOUNT_PERCENTAGE: z.number().min(0).max(1).default(0.01),
    TAKE_PROFIT_PERCENTAGE: z.number().min(0).default(0.005),
    STOP_LOSS_PERCENTAGE: z.number().min(0).default(0.002),
    RSI_OVERBOUGHT: z.number().default(70),
    RSI_OVERSOLD: z.number().default(30),
    RSI_CONFIRM_LONG_THRESHOLD: z.number().default(50),
    RSI_CONFIRM_SHORT_THRESHOLD: z.number().default(50),
    ADX_THRESHOLD: z.number().default(25),
});

const parsedConfig = configSchema.safeParse({
    API_KEY: process.env.BYBIT_API_KEY,
    API_SECRET: process.env.BYBIT_API_SECRET,
    TESTNET: process.env.TESTNET === 'true',
    DRY_RUN: process.env.DRY_RUN === 'true',
    SYMBOL: process.env.SYMBOL,
    CATEGORY: process.env.CATEGORY,
    ACCOUNT_TYPE: process.env.ACCOUNT_TYPE,
    TIMEFRAME: process.env.TIMEFRAME ? parseInt(process.env.TIMEFRAME) : undefined,
    LOOP_INTERVAL_MS: process.env.LOOP_INTERVAL_MS ? parseInt(process.env.LOOP_INTERVAL_MS) : undefined,
    CE_ATR_PERIOD: process.env.CE_ATR_PERIOD ? parseInt(process.env.CE_ATR_PERIOD) : undefined,
    CE_ATR_MULTIPLIER: process.env.CE_ATR_MULTIPLIER ? parseFloat(process.env.CE_ATR_MULTIPLIER) : undefined,
    TRADE_AMOUNT_PERCENTAGE: process.env.TRADE_AMOUNT_PERCENTAGE ? parseFloat(process.env.TRADE_AMOUNT_PERCENTAGE) : undefined,
    TAKE_PROFIT_PERCENTAGE: process.env.TAKE_PROFIT_PERCENTAGE ? parseFloat(process.env.TAKE_PROFIT_PERCENTAGE) : undefined,
    STOP_LOSS_PERCENTAGE: process.env.STOP_LOSS_PERCENTAGE ? parseFloat(process.env.STOP_LOSS_PERCENTAGE) : undefined,
});

if (!parsedConfig.success) {
    console.error("Invalid configuration:", parsedConfig.error.errors);
    process.exit(1);
}

export default parsedConfig.data;
