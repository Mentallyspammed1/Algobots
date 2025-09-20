import dotenv from 'dotenv';
import { z } from 'zod';
import { logger } from './logger';
import { BotConfig } from './types';
import { KlineIntervalV5 } from 'bybit-api';

dotenv.config();

const envSchema = z.object({
  BYBIT_API_KEY: z.string().min(1, "BYBIT_API_KEY is required"),
  BYBIT_API_SECRET: z.string().min(1, "BYBIT_API_SECRET is required"),
  BYBIT_TESTNET: z.enum(['true', 'false']).transform(val => val === 'true'),
});

const strategyConfigSchema = z.object({
    name: z.string(),
    params: z.record(z.number()),
    weights: z.record(z.number()),
    thresholds: z.object({
        long: z.number(),
        short: z.number(),
    }),
});

const botConfigSchema = z.object({
    symbol: z.string(),
    interval: z.string(),
    leverage: z.number(),
    max_leverage: z.number(),
    position_size_usd: z.number(),
    stop_loss_pct: z.number().positive(),
    take_profit_pct: z.number().positive(),
    entry_order_type: z.enum(['Market', 'Limit']),
    limit_order_price_offset_pct: z.number(),
    run_mode: z.enum(['LIVE', 'DRY_RUN', 'BACKTEST']),
    strategy: strategyConfigSchema,
});

// Hardcoded default config for the Trend Scoring Strategy
const DEFAULT_CONFIG: BotConfig = {
    symbol: 'BTCUSDT',
    interval: '60' as KlineIntervalV5,
    leverage: 5,
    max_leverage: 10,
    position_size_usd: 500,
    stop_loss_pct: 0.02, // 2% stop loss
    take_profit_pct: 0.04, // 4% take profit
    entry_order_type: 'Limit',
    limit_order_price_offset_pct: 0.0005, // 0.05% offset for limit orders
    run_mode: 'DRY_RUN', // Default to dry run for safety
    strategy: {
        name: 'TrendScoring',
        params: {
            // Indicator periods & settings
            macd_fast_period: 12,
            macd_slow_period: 26,
            macd_signal_period: 9,
            rsi_period: 14,
            adx_period: 14,
            adx_threshold: 25,
            st_period: 10,
            st_factor: 3,
            stoch_period: 14,
            stoch_smoothing: 3,
            bb_period: 20,
            bb_stddev: 2,
            ichimoku_tenkan: 9,
            ichimoku_kijun: 26,
            ichimoku_senkou_b: 52,
            itrend_period: 7, // Ehlers ITrend alpha period
            fisher_period: 10, // Ehlers Fisher Transform period
        },
        weights: {
            // The importance of each indicator's signal
            macd: 1.0,
            rsi: 0.5,
            adx: 1.0,
            st: 1.5,
            stochastic: 0.5,
            bollinger_bands: 0.5, // Reversal indicator, less weight for trend
            ichimoku: 1.5,
            ehlers_itrend: 1.5, // Strong, low-lag trend indicator
            ehlers_fisher: 1.0, // Good for reversal signals
        },
        thresholds: {
            long: 5.0,  // Score needed to open a long
            short: -5.0, // Score needed to open a short
        },
    },
};

function loadConfig(): { env: z.infer<typeof envSchema>, bot: BotConfig } {
  const parsedEnv = envSchema.safeParse(process.env);
  if (!parsedEnv.success) {
    logger.error("Invalid environment variables:", parsedEnv.error.flatten());
    process.exit(1);
  }

  // For this template, we use a hardcoded config. 
  // In a real-world scenario, you might load this from a JSON file.
  const botConfig = DEFAULT_CONFIG;

  const parsedBotConfig = botConfigSchema.safeParse(botConfig);
  if (!parsedBotConfig.success) {
    logger.error("Invalid bot configuration:", parsedBotConfig.error.flatten());
    process.exit(1);
  }

  logger.success("Configuration loaded and validated successfully.");

  return {
    env: parsedEnv.data,
    bot: parsedBotConfig.data as BotConfig,
  };
}

export const config = loadConfig();