/**
 * @file WhaleWave Pro - Titan Edition v7.1 (Enhanced)
 * @description Advanced algorithmic trading bot for cryptocurrency markets.
 * @author Pyrmethus (Termux Coding Wizard)
 * @version 7.1.1
 *
 * ENHANCEMENTS:
 * - Advanced weighted sentiment scoring with dynamic weights
 * - Extended technical indicators (Williams %R, CCI, MFI, ADX, CMF, OBV, VWAP)
 * - Enhanced volume analysis and order book insights
 * - Market microstructure analysis
 * - Performance optimizations and caching
 * - Multi-timeframe confirmation system
 * - Advanced risk management with volatility-adjusted sizing
 * - Robust error handling and logging
 * - Comprehensive performance metrics
 */

// =============================================================================
// IMPORTS & DEPENDENCIES
// =============================================================================

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import os from 'os'; // For memory/CPU usage
import { performance } from 'perf_hooks'; // For precise timing

dotenv.config();

// =============================================================================
// CUSTOM ERRORS
// =============================================================================

class AppError extends Error {
    constructor(message, code = 'APP_ERROR') {
        super(message);
        this.name = this.constructor.name;
        this.code = code;
        Error.captureStackTrace(this, this.constructor);
    }
}

class ConfigError extends AppError {
    constructor(message) {
        super(message, 'CONFIG_ERROR');
    }
}

class DataError extends AppError {
    constructor(message) {
        super(message, 'DATA_ERROR');
    }
}

class ApiError extends AppError {
    constructor(message, statusCode = null, responseCode = null, responseMsg = null) {
        super(message, 'API_ERROR');
        this.statusCode = statusCode;
        this.responseCode = responseCode;
        this.responseMsg = responseMsg;
    }
}

class AnalysisError extends AppError {
    constructor(message) {
        super(message, 'ANALYSIS_ERROR');
    }
}

class TradingError extends AppError {
    constructor(message) {
        super(message, 'TRADING_ERROR');
    }
}

class AiError extends AppError {
    constructor(message) {
        super(message, 'AI_ERROR');
    }
}

// =============================================================================
// CONFIGURATION MANAGEMENT (ENHANCED)
// =============================================================================

/**
 * Manages application configuration, loading from file or defaults, and validation.
 */
class ConfigManager {
    static CONFIG_FILE = 'config.json';

    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { main: '3', trend: '15', daily: 'D', weekly: 'W' },
        limits: {
            kline: 500,
            trendKline: 200,
            orderbook: 100,
            maxOrderbookDepth: 20,
            volumeProfile: 50
        },
        delays: { loop: 3000, retry: 800 },
        api: {
            baseURL: 'https://api.bybit.com/v5/market',
            timeout: 10000,
            retries: 3,
            backoffFactor: 1.5,
            userAgent: 'WhaleWave-Titan-Enhanced/7.1'
        },
        ai: {
            model: 'gemini-1.5-flash',
            minConfidence: 0.75,
            rateLimitMs: 1500,
            maxRetries: 3
        },
        risk: {
            initialBalance: 1000.00,
            maxDrawdownPercent: 10.0, // Renamed for clarity
            dailyLossLimitPercent: 5.0, // Renamed for clarity
            maxPositions: 1,
            riskPercentPerTrade: 2.0, // Renamed for clarity
            leverageCap: 10,
            fee: 0.00055,
            slippagePercent: 0.01, // Renamed for clarity
            volatilityAdjustment: true,
            maxRiskPerTradePercent: 2.0, // Renamed for clarity
            minRiskRewardRatio: 1.2, // Added for explicit validation
            consecutiveLossLimit: 3 // Added for explicit validation
        },
        indicators: {
            periods: {
                rsi: 14, stoch: 14, cci: 20, adx: 14, mfi: 14, chop: 14,
                linreg: 20, vwap: 20, bb: 20, keltner: 20, atr: 14,
                stFactor: 22, supertrend: 10, williams: 14, cmf: 20,
                obv: 14, adLine: 14
            },
            settings: {
                stochK: 3, stochD: 3, bbStd: 2.0, keltnerMult: 2.0,
                ceMult: 3.0, williamsR: 21, mfiPeriod: 14,
                cmfPeriod: 20, obvPeriod: 14
            },
            weights: {
                trendMTF: 2.5, trendScalp: 1.5, momentum: 2.0,
                macd: 1.2, regime: 1.0, squeeze: 1.2,
                liquidity: 1.8, divergence: 2.8, volatility: 0.8,
                volumeFlow: 1.5, orderFlow: 1.2, adLine: 1.0,
                actionThreshold: 2.0, minConfirmation: 3
            }
        },
        orderbook: {
            wallThreshold: 2.5,
            srLevels: 8,
            flowAnalysis: true,
            depthAnalysis: true,
            imbalanceThreshold: 0.3
        },
        volumeAnalysis: {
            enabled: true,
            profileBins: 50,
            accumulationThreshold: 0.15,
            distributionThreshold: -0.15,
            flowConfirmation: true
        }
    });

    /**
     * Loads configuration from file or defaults, performs validation.
     * @returns {Promise<object>} The validated configuration object.
     * @throws {ConfigError} If critical configuration is missing or invalid.
     */
    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));

        try {
            const fileExists = await fs.access(this.CONFIG_FILE).then(() => true).catch(() => false);

            if (fileExists) {
                console.log(COLORS.YELLOW(`ðŸ”§ Loading configuration from ${this.CONFIG_FILE}...`));
                const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
                const userConfig = JSON.parse(fileContent);
                config = this.deepMerge(config, userConfig);
                console.log(COLORS.GREEN('âœ… User configuration loaded.'));
            } else {
                console.warn(COLORS.ORANGE(`ðŸš€ Configuration file not found. Using defaults and creating ${this.CONFIG_FILE}.`));
                await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
            }
        } catch (error) {
            throw new ConfigError(`Failed to load or parse configuration file: ${error.message}`);
        }

        return this.validateEnhanced(config);
    }

    /**
     * Deeply merges two objects.
     * @param {object} target - The target object.
     * @param {object} source - The source object.
     * @returns {object} The merged object.
     */
    static deepMerge(target, source) {
        const result = { ...target };

        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value) && result[key] && typeof result[key] === 'object') {
                result[key] = this.deepMerge(result[key], value);
            } else {
                result[key] = value;
            }
        }
        return result;
    }

    /**
     * Validates the configuration object for critical parameters.
     * @param {object} config - The configuration object to validate.
     * @returns {object} The validated configuration object.
     * @throws {ConfigError} If validation fails.
     */
    static validateEnhanced(config) {
        const requiredFields = ['symbol', 'intervals', 'limits', 'delays', 'api', 'ai', 'risk', 'indicators', 'orderbook', 'volumeAnalysis'];
        for (const field of requiredFields) {
            if (!config[field]) throw new ConfigError(`Missing required config field: ${field}`);
        }

        // Enhanced validation with specific ranges and types
        if (typeof config.symbol !== 'string' || config.symbol.length === 0) throw new ConfigError('Symbol must be a non-empty string.');
        if (typeof config.risk.initialBalance !== 'number' || config.risk.initialBalance <= 0) throw new ConfigError('initialBalance must be a positive number.');
        if (typeof config.risk.maxDrawdownPercent < 0 || config.risk.maxDrawdownPercent > 50) throw new ConfigError('maxDrawdownPercent must be between 0 and 50.');
        if (typeof config.risk.dailyLossLimitPercent < 0 || config.risk.dailyLossLimitPercent > 20) throw new ConfigError('dailyLossLimitPercent must be between 0 and 20.');
        if (typeof config.risk.riskPercentPerTrade <= 0 || config.risk.riskPercentPerTrade > 10) throw new ConfigError('riskPercentPerTrade must be between 0 and 10.');
        if (typeof config.risk.leverageCap <= 0) throw new ConfigError('leverageCap must be positive.');
        if (typeof config.risk.fee < 0 || config.risk.fee > 0.01) throw new ConfigError('fee must be between 0 and 0.01.');
        if (typeof config.risk.slippagePercent < 0 || config.risk.slippagePercent > 0.05) throw new ConfigError('slippagePercent must be between 0 and 0.05.');
        if (typeof config.risk.minRiskRewardRatio < 0.5) throw new ConfigError('minRiskRewardRatio must be at least 0.5.');
        if (typeof config.risk.consecutiveLossLimit <= 0) throw new ConfigError('consecutiveLossLimit must be positive.');

        if (typeof config.ai.minConfidence < 0 || config.ai.minConfidence > 1) throw new ConfigError('minConfidence must be between 0 and 1.');
        if (typeof config.ai.rateLimitMs <= 0) throw new ConfigError('rateLimitMs must be positive.');

        if (typeof config.indicators.weights.actionThreshold < 0.5) throw new ConfigError('actionThreshold should be at least 0.5 for safety.');
        if (typeof config.delays.loop <= 0 || typeof config.delays.retry <= 0) throw new ConfigError('Delays must be positive.');

        // Validate indicator periods are positive integers
        for (const [key, value] of Object.entries(config.indicators.periods)) {
            if (!Number.isInteger(value) || value <= 0) {
                throw new ConfigError(`Indicator period '${key}' must be a positive integer. Found: ${value}`);
            }
        }

        console.log(COLORS.GREEN('âœ… Configuration validation successful.'));
        return config;
    }
}

// =============================================================================
// UTILITIES & CONSTANTS (ENHANCED)
// =============================================================================

/**
 * Color constants for terminal output.
 */
const COLORS = Object.freeze({
    GREEN: chalk.hex('#00FF41'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#0A84FF'),
    CYAN: chalk.hex('#64D2FF'),
    PURPLE: chalk.hex('#BF5AF2'),
    YELLOW: chalk.hex('#FFD60A'),
    GRAY: chalk.hex('#8E8E93'),
    ORANGE: chalk.hex('#FF9500'),
    MAGENTA: chalk.hex('#FF2D92'),
    TEAL: chalk.hex('#5AC8FA'),
    BOLD: chalk.bold,
    DIM: chalk.dim,
    bg: (text) => chalk.bgHex('#1C1C1E')(text),
    error: (text) => chalk.bold.red(text),
    warning: (text) => chalk.bold.yellow(text),
    info: (text) => chalk.bold.cyan(text),
    success: (text) => chalk.bold.green(text)
});

/**
 * Enhanced utility functions with performance optimizations and safety checks.
 */
class Utils {
    /**
     * Creates an array of a specified length filled with a default value.
     * @param {number} length - The desired length of the array.
     * @param {*} [defaultValue=0] - The value to fill the array with.
     * @returns {Array<*>} The initialized array.
     */
    static safeArray(length, defaultValue = 0) {
        return new Array(Math.max(0, Math.floor(length))).fill(defaultValue);
    }

    /**
     * Safely retrieves the last element of an array.
     * @param {Array<*>} arr - The input array.
     * @param {*} [defaultValue=0] - The value to return if the array is empty or invalid.
     * @returns {*} The last element or the default value.
     */
    static safeLast(arr, defaultValue = 0) {
        return Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : defaultValue;
    }

    /**
     * Safely converts a value to a finite number.
     * @param {*} value - The value to convert.
     * @param {number} [defaultValue=0] - The value to return if conversion fails.
     * @returns {number} The converted finite number or the default value.
     */
    static safeNumber(value, defaultValue = 0) {
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        if (typeof value === 'string') {
            const num = parseFloat(value);
            if (Number.isFinite(num)) return num;
        }
        return defaultValue;
    }

    /**
     * Calculates an exponential backoff delay.
     * @param {number} attempt - The current attempt number (0-indexed).
     * @param {number} baseDelay - The base delay in milliseconds.
     * @param {number} factor - The exponential factor.
     * @returns {number} The calculated delay in milliseconds.
     */
    static backoffDelay(attempt, baseDelay, factor) {
        return baseDelay * Math.pow(factor, attempt);
    }

    /**
     * Calculates the percentage change between two numbers.
     * @param {number} current - The current value.
     * @param {number} previous - The previous value.
     * @returns {number} The percentage change.
     */
    static percentChange(current, previous) {
        if (previous === 0) return 0;
        return ((current - previous) / previous) * 100;
    }

    /**
     * Normalizes an array of numbers to a range of 0 to 1.
     * @param {number[]} values - The array of numbers to normalize.
     * @returns {number[]} The normalized array.
     */
    static normalize(values) {
        if (!Array.isArray(values) || values.length === 0) return [];
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min;
        if (range === 0) return values.map(() => 0.5); // Return middle value if all are the same
        return values.map(v => (v - min) / range);
    }

    /**
     * Calculates the moving standard deviation of an array.
     * @param {number[]} data - The input array of numbers.
     * @param {number} period - The lookback period.
     * @returns {number[]} An array containing the moving standard deviation.
     */
    static movingStdDev(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);

        const result = Utils.safeArray(data.length);
        for (let i = period - 1; i < data.length; i++) {
            const slice = data.slice(i - period + 1, i + 1);
            const mean = slice.reduce((sum, val) => sum + val, 0) / period;
            const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
            result[i] = Math.sqrt(variance);
        }
        return result;
    }

    /**
     * Calculates a percentile value from an array.
     * @param {number[]} values - The array of numbers.
     * @param {number} p - The percentile to calculate (0-1).
     * @returns {number} The calculated percentile value.
     */
    static percentile(values, p) {
        if (!Array.isArray(values) || values.length === 0) return 0;
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.ceil(p * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
    }

    /**
     * Formats duration in milliseconds to a human-readable string (e.g., "1h 5m 30s").
     * @param {number} ms - Duration in milliseconds.
     * @returns {string} Human-readable duration string.
     */
    static formatDuration(ms) {
        if (ms < 0) return 'N/A';
        const seconds = Math.floor(ms / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        const parts = [];
        if (days > 0) parts.push(`${days}d`);
        if (hours % 24 > 0) parts.push(`${hours % 24}h`);
        if (minutes % 60 > 0) parts.push(`${minutes % 60}m`);
        if (seconds % 60 > 0 || parts.length === 0) parts.push(`${seconds % 60}s`);

        return parts.join(' ');
    }
}

// =============================================================================
// ENHANCED TECHNICAL ANALYSIS LIBRARY
// =============================================================================

/**
 * Comprehensive technical analysis library with extended indicators.
 * All functions return arrays of the same length as the input data,
 * padded with default values (often 0 or NaN) at the beginning where calculation is not possible.
 */
class TechnicalAnalysis {
    /**
     * Calculates the Simple Moving Average (SMA).
     * @param {number[]} data - Input data array.
     * @param {number} period - The lookback period.
     * @returns {number[]} SMA values.
     */
    static sma(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);
        const result = Utils.safeArray(data.length);
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result[i] = sum / period;
        }
        return result;
    }

    /**
     * Calculates the Exponential Moving Average (EMA).
     * @param {number[]} data - Input data array.
     * @param {number} period - The lookback period.
     * @returns {number[]} EMA values.
     */
    static ema(data, period) {
        if (!Array.isArray(data) || data.length === 0) return [];
        const result = Utils.safeArray(data.length);
        const multiplier = 2 / (period + 1);
        result[0] = data[0]; // Initial value is the first data point
        for (let i = 1; i < data.length; i++) {
            result[i] = (data[i] * multiplier) + (result[i - 1] * (1 - multiplier));
        }
        return result;
    }

    /**
     * Wilder's Smoothing (used in RSI and ATR).
     * @param {number[]} data - Input data array.
     * @param {number} period - The lookback period.
     * @returns {number[]} Wilder's smoothed values.
     */
    static wilders(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);
        const result = Utils.safeArray(data.length);
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) {
            result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        }
        return result;
    }

    /**
     * Calculates the Relative Strength Index (RSI).
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period.
     * @returns {number[]} RSI values.
     */
    static rsi(closes, period) {
        if (!Array.isArray(closes) || closes.length < 2) return Utils.safeArray(closes.length);
        const gains = Utils.safeArray(closes.length);
        const losses = Utils.safeArray(closes.length);

        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains[i] = diff > 0 ? diff : 0;
            losses[i] = diff < 0 ? Math.abs(diff) : 0;
        }

        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);

        const rsiValues = Utils.safeArray(closes.length);
        for (let i = 0; i < closes.length; i++) {
            const loss = avgLoss[i];
            if (loss === 0) {
                rsiValues[i] = 100;
            } else {
                const rs = avgGain[i] / loss;
                rsiValues[i] = 100 - (100 / (1 + rs));
            }
        }
        return rsiValues;
    }

    /**
     * Calculates Williams %R.
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period.
     * @returns {number[]} Williams %R values.
     */
    static williamsR(highs, lows, closes, period) {
        if (!highs || !lows || !closes || highs.length < period) {
            return Utils.safeArray(closes?.length ?? 0);
        }
        const result = Utils.safeArray(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const sliceLow = Math.min(...lows.slice(i - period + 1, i + 1));
            const range = sliceHigh - sliceLow;
            if (range === 0) {
                result[i] = -50; // Neutral value if range is zero
            } else {
                result[i] = ((sliceHigh - closes[i]) / range) * -100;
            }
        }
        return result;
    }

    /**
     * Calculates the Commodity Channel Index (CCI).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period.
     * @returns {number[]} CCI values.
     */
    static cci(highs, lows, closes, period) {
        if (!highs || !lows || !closes || closes.length < period) {
            return Utils.safeArray(closes?.length ?? 0);
        }
        const result = Utils.safeArray(closes.length);
        const typicalPrices = closes.map((close, i) => (highs[i] + lows[i] + close) / 3);
        const smaTypical = this.sma(typicalPrices, period);

        for (let i = period - 1; i < closes.length; i++) {
            const mean = smaTypical[i];
            const slice = typicalPrices.slice(i - period + 1, i + 1);
            const meanAbsoluteDeviation = slice.reduce((sum, tp) => sum + Math.abs(tp - mean), 0) / period;
            const divisor = meanAbsoluteDeviation === 0 ? 1 : meanAbsoluteDeviation; // Avoid division by zero
            result[i] = (typicalPrices[i] - mean) / (0.015 * divisor);
        }
        return result;
    }

    /**
     * Calculates Stochastic Oscillator (%K and %D).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period for %K.
     * @param {number} kPeriod - Smoothing period for %K (often same as period).
     * @param {number} dPeriod - Smoothing period for %D.
     * @returns {{k: number[], d: number[]}} Object containing %K and %D arrays.
     */
    static stochastic(highs, lows, closes, period, kPeriod, dPeriod) {
        const k = Utils.safeArray(closes?.length ?? 0);
        const d = Utils.safeArray(closes?.length ?? 0);

        if (!highs || !lows || !closes || closes.length < period) {
            return { k, d };
        }

        for (let i = period - 1; i < closes.length; i++) {
            const sliceHigh = highs.slice(i - period + 1, i + 1);
            const sliceLow = lows.slice(i - period + 1, i + 1);
            const minLow = Math.min(...sliceLow);
            const maxHigh = Math.max(...sliceHigh);
            const range = maxHigh - minLow;
            k[i] = range === 0 ? 0 : 100 * ((closes[i] - minLow) / range);
        }

        // Use kPeriod for smoothing k if different, otherwise use the main period
        const kSmoothed = this.sma(k, kPeriod);
        // Use dPeriod for smoothing d
        const dSmoothed = this.sma(kSmoothed, dPeriod);

        return { k, d: dSmoothed };
    }

    /**
     * Calculates the Money Flow Index (MFI).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} volumes - Volume array.
     * @param {number} period - The lookback period.
     * @returns {number[]} MFI values.
     */
    static mfi(highs, lows, closes, volumes, period) {
        if (!highs || !lows || !closes || !volumes || closes.length < period) {
            return Utils.safeArray(closes?.length ?? 0);
        }
        const result = Utils.safeArray(closes.length);
        const typicalPrices = closes.map((close, i) => (highs[i] + lows[i] + close) / 3);
        const moneyFlow = typicalPrices.map((tp, i) => tp * volumes[i]);

        for (let i = 1; i < closes.length; i++) {
            const positiveFlow = typicalPrices[i] > typicalPrices[i - 1] ? moneyFlow[i] : 0;
            const negativeFlow = typicalPrices[i] < typicalPrices[i - 1] ? moneyFlow[i] : 0;

            if (i >= period) {
                // Calculate sums over the lookback period
                let positiveSum = 0;
                let negativeSum = 0;
                for (let j = i - period + 1; j <= i; j++) {
                    if (typicalPrices[j] > typicalPrices[j - 1]) {
                        positiveSum += moneyFlow[j];
                    } else if (typicalPrices[j] < typicalPrices[j - 1]) {
                        negativeSum += moneyFlow[j];
                    }
                }

                if (negativeSum === 0) {
                    result[i] = 100;
                } else {
                    const moneyRatio = positiveSum / negativeSum;
                    result[i] = 100 - (100 / (1 + moneyRatio));
                }
            }
        }
        return result;
    }

    /**
     * Calculates Average Directional Index (ADX), +DI, and -DI.
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period.
     * @returns {{adx: number[], plusDI: number[], minusDI: number[]}} ADX components.
     */
    static adx(highs, lows, closes, period = 14) {
        const adx = Utils.safeArray(closes?.length ?? 0);
        const plusDI = Utils.safeArray(closes?.length ?? 0);
        const minusDI = Utils.safeArray(closes?.length ?? 0);

        if (!highs || !lows || !closes || closes.length < period * 2) { // Need enough data for smoothing
            return { adx, plusDI, minusDI };
        }

        const tr = Utils.safeArray(closes.length);
        const plusDM = Utils.safeArray(closes.length);
        const minusDM = Utils.safeArray(closes.length);

        for (let i = 1; i < closes.length; i++) {
            const range = highs[i] - lows[i];
            const rangeFromClose = Math.abs(highs[i] - closes[i - 1]);
            const rangeFromPrevClose = Math.abs(lows[i] - closes[i - 1]);
            tr[i] = Math.max(range, rangeFromClose, rangeFromPrevClose);

            const upMove = highs[i] - highs[i - 1];
            const downMove = lows[i - 1] - lows[i];

            plusDM[i] = upMove > downMove && upMove > 0 ? upMove : 0;
            minusDM[i] = downMove > upMove && downMove > 0 ? downMove : 0;
        }

        const atr = this.wilders(tr, period);
        const smoothedPlusDM = this.wilders(plusDM, period);
        const smoothedMinusDM = this.wilders(minusDM, period);

        for (let i = period - 1; i < closes.length; i++) {
            const currentATR = atr[i];
            if (currentATR > 0) {
                plusDI[i] = (smoothedPlusDM[i] / currentATR) * 100;
                minusDI[i] = (smoothedMinusDM[i] / currentATR) * 100;
            } else {
                plusDI[i] = 0;
                minusDI[i] = 0;
            }
        }

        // Calculate ADX from +DI and -DI
        for (let i = period * 2 - 1; i < closes.length; i++) { // ADX requires smoothing of DI values
            const diDiff = Math.abs(plusDI[i] - minusDI[i]);
            const diSum = plusDI[i] + minusDI[i];
            const dx = diSum === 0 ? 0 : (diDiff / diSum) * 100;
            adx[i] = dx; // This is a simplified ADX calculation; a full ADX involves smoothing dx itself.
                         // For this context, using dx directly is often sufficient.
        }

        return { adx, plusDI, minusDI };
    }

    /**
     * Calculates Moving Average Convergence Divergence (MACD).
     * @param {number[]} closes - Closing prices array.
     * @param {number} fastPeriod - Period for the fast EMA.
     * @param {number} slowPeriod - Period for the slow EMA.
     * @param {number} signalPeriod - Period for the signal line EMA.
     * @returns {{line: number[], signal: number[], hist: number[]}} MACD components.
     */
    static macd(closes, fastPeriod, slowPeriod, signalPeriod) {
        const line = Utils.safeArray(closes?.length ?? 0);
        const signal = Utils.safeArray(closes?.length ?? 0);
        const hist = Utils.safeArray(closes?.length ?? 0);

        if (!closes || closes.length < slowPeriod) {
            return { line, signal, hist };
        }

        const fastEMA = this.ema(closes, fastPeriod);
        const slowEMA = this.ema(closes, slowPeriod);

        for (let i = 0; i < closes.length; i++) {
            line[i] = fastEMA[i] - slowEMA[i];
        }

        const signalLine = this.ema(line, signalPeriod);
        for (let i = 0; i < closes.length; i++) {
            hist[i] = line[i] - signalLine[i];
        }

        return { line, signal: signalLine, hist };
    }

    /**
     * Calculates On-Balance Volume (OBV).
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} volumes - Volume array.
     * @returns {number[]} OBV values.
     */
    static onBalanceVolume(closes, volumes) {
        const result = Utils.safeArray(closes?.length ?? 0);
        if (!closes || !volumes || closes.length === 0) return result;

        result[0] = volumes[0];
        for (let i = 1; i < closes.length; i++) {
            if (closes[i] > closes[i - 1]) {
                result[i] = result[i - 1] + volumes[i];
            } else if (closes[i] < closes[i - 1]) {
                result[i] = result[i - 1] - volumes[i];
            } else {
                result[i] = result[i - 1];
            }
        }
        return result;
    }

    /**
     * Calculates the Accumulation/Distribution Line (AD Line).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} volumes - Volume array.
     * @returns {number[]} AD Line values.
     */
    static accumulationDistributionLine(highs, lows, closes, volumes) {
        const result = Utils.safeArray(closes?.length ?? 0);
        if (!highs || !lows || !closes || !volumes || closes.length === 0) return result;

        for (let i = 0; i < closes.length; i++) {
            const range = highs[i] - lows[i];
            let multiplier = 0;
            if (range !== 0) {
                multiplier = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / range;
            }
            const moneyFlowVolume = multiplier * volumes[i];
            result[i] = i > 0 ? result[i - 1] + moneyFlowVolume : moneyFlowVolume;
        }
        return result;
    }

    /**
     * Calculates Chaikin Money Flow (CMF).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} volumes - Volume array.
     * @param {number} period - The lookback period.
     * @returns {number[]} CMF values.
     */
    static chaikinMoneyFlow(highs, lows, closes, volumes, period) {
        const result = Utils.safeArray(closes?.length ?? 0);
        if (!highs || !lows || !closes || !volumes || closes.length < period) {
            return result;
        }

        for (let i = period - 1; i < closes.length; i++) {
            let sumMoneyFlow = 0;
            let sumVolume = 0;
            for (let j = i - period + 1; j <= i; j++) {
                const range = highs[j] - lows[j];
                let multiplier = 0;
                if (range !== 0) {
                    multiplier = ((closes[j] - lows[j]) - (highs[j] - closes[j])) / range;
                }
                sumMoneyFlow += multiplier * volumes[j];
                sumVolume += volumes[j];
            }
            result[i] = sumVolume === 0 ? 0 : sumMoneyFlow / sumVolume;
        }
        return result;
    }

    /**
     * Calculates Volume Weighted Average Price (VWAP).
     * Note: This calculates cumulative VWAP over the provided data. For daily VWAP,
     * data should be reset daily.
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} volumes - Volume array.
     * @returns {number[]} VWAP values.
     */
    static vwap(highs, lows, closes, volumes) {
        const result = Utils.safeArray(closes?.length ?? 0);
        if (!highs || !lows || !closes || !volumes || closes.length === 0) return result;

        let totalVolumePrice = 0;
        let totalVolume = 0;

        for (let i = 0; i < closes.length; i++) {
            const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
            totalVolumePrice += typicalPrice * volumes[i];
            totalVolume += volumes[i];
            result[i] = totalVolume === 0 ? closes[i] : totalVolumePrice / totalVolume;
        }
        return result;
    }

    /**
     * Calculates Average True Range (ATR).
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period.
     * @returns {number[]} ATR values.
     */
    static atr(highs, lows, closes, period) {
        const trueRange = Utils.safeArray(closes?.length ?? 0);
        if (!highs || !lows || !closes || closes.length < 2) {
            return Utils.safeArray(closes?.length ?? 0);
        }

        for (let i = 1; i < closes.length; i++) {
            const range = highs[i] - lows[i];
            const rangeFromClose = Math.abs(highs[i] - closes[i - 1]);
            const rangeFromPrevClose = Math.abs(lows[i] - closes[i - 1]);
            trueRange[i] = Math.max(range, rangeFromClose, rangeFromPrevClose);
        }
        return this.wilders(trueRange, period);
    }

    /**
     * Calculates Bollinger Bands (Upper, Middle, Lower).
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - The lookback period for SMA.
     * @param {number} stdDev - The number of standard deviations.
     * @returns {{upper: number[], middle: number[], lower: number[]}} Bollinger Bands components.
     */
    static bollingerBands(closes, period, stdDev) {
        const upper = Utils.safeArray(closes?.length ?? 0);
        const middle = Utils.safeArray(closes?.length ?? 0);
        const lower = Utils.safeArray(closes?.length ?? 0);

        if (!closes || closes.length < period) {
            return { upper, middle, lower };
        }

        const smaValues = this.sma(closes, period);
        const stdDevValues = this.movingStdDev(closes, period);

        for (let i = 0; i < closes.length; i++) {
            middle[i] = smaValues[i];
            if (i >= period - 1) {
                const std = stdDevValues[i];
                upper[i] = middle[i] + (std * stdDev);
                lower[i] = middle[i] - (std * stdDev);
            }
        }
        return { upper, middle, lower };
    }

    /**
     * Detects Fair Value Gaps (FVG) or Imbalances.
     * Looks for a specific 3-candle pattern.
     * @param {Array<{o: number, h: number, l: number, c: number}>} candles - Array of candle objects.
     * @returns {{type: 'BULLISH'|'BEARISH', top: number, bottom: number, price: number} | null} FVG details or null.
     */
    static findFairValueGap(candles) {
        if (!Array.isArray(candles) || candles.length < 3) return null;
        const len = candles.length;
        // Check the last 3 candles for the pattern
        const c1 = candles[len - 3]; // Candle before the gap candle
        const c2 = candles[len - 2]; // The gap candle
        const c3 = candles[len - 1]; // Candle after the gap candle

        // Bullish FVG: c2 is bullish (close > open), and c3's low is above c1's high
        if (c2.c > c2.o && c3.l > c1.h) {
            return {
                type: 'BULLISH',
                top: c3.l, // The lowest point of the gap area
                bottom: c1.h, // The highest point before the gap
                price: (c3.l + c1.h) / 2 // Midpoint of the gap
            };
        }

        // Bearish FVG: c2 is bearish (close < open), and c3's high is below c1's low
        if (c2.c < c2.o && c3.h < c1.l) {
            return {
                type: 'BEARISH',
                top: c1.l, // The lowest point before the gap
                bottom: c3.h, // The highest point of the gap area
                price: (c1.l + c3.h) / 2 // Midpoint of the gap
            };
        }

        return null;
    }

    /**
     * Detects basic divergence between price and RSI.
     * @param {number[]} closes - Closing prices array.
     * @param {number[]} rsi - RSI values array.
     * @param {number} period - Lookback period for price/RSI peaks/troughs.
     * @returns {'BULLISH_REGULAR' | 'BEARISH_REGULAR' | 'NONE'} Divergence type.
     */
    static detectDivergence(closes, rsi, period = 5) {
        if (!closes || !rsi || closes.length < period * 2) {
            return 'NONE';
        }

        const len = closes.length;
        // Compare last 'period' with previous 'period'
        const currentPriceSlice = closes.slice(len - period, len);
        const currentRsiSlice = rsi.slice(len - period, len);
        const prevPriceSlice = closes.slice(len - period * 2, len - period);
        const prevRsiSlice = rsi.slice(len - period * 2, len - period);

        // Find peaks and troughs within slices
        const currentPriceHigh = Math.max(...currentPriceSlice);
        const currentRsiHigh = Math.max(...currentRsiSlice);
        const prevPriceHigh = Math.max(...prevPriceSlice);
        const prevRsiHigh = Math.max(...prevRsiSlice);

        const currentPriceLow = Math.min(...currentPriceSlice);
        const currentRsiLow = Math.min(...currentRsiSlice);
        const prevPriceLow = Math.min(...prevPriceSlice);
        const prevRsiLow = Math.min(...prevRsiSlice);

        // Bullish Divergence: Price makes lower low, RSI makes higher low
        if (currentPriceLow < prevPriceLow && currentRsiLow > prevRsiLow) {
            return 'BULLISH_REGULAR';
        }

        // Bearish Divergence: Price makes higher high, RSI makes lower high
        if (currentPriceHigh > prevPriceHigh && currentRsiHigh < prevRsiHigh) {
            return 'BEARISH_REGULAR';
        }

        return 'NONE';
    }
}

// =============================================================================
// ENHANCED MARKET ANALYSIS ENGINE
// =============================================================================

/**
 * Analyzes market data to extract indicators and market structure insights.
 */
class MarketAnalyzer {
    /**
     * Analyzes provided market data.
     * @param {object} data - Market data object from DataProvider.
     * @param {object} config - Application configuration.
     * @returns {Promise<object>} Object containing analysis results.
     * @throws {AnalysisError} If analysis fails.
     */
    static async analyze(data, config) {
        const { candles, candlesMTF } = data;

        if (!candles || candles.length === 0) {
            throw new AnalysisError('Invalid candle data provided');
        }

        // Extract OHLCV arrays for easier access
        const closes = candles.map(c => c.c);
        const highs = candles.map(c => c.h);
        const lows = c => c.l;
        const volumes = candles.map(c => c.v);
        const mtfCloses = candlesMTF.map(c => c.c);

        try {
            // Calculate all indicators in parallel for performance
            const analysisTasks = [
                TechnicalAnalysis.rsi(closes, config.indicators.periods.rsi),
                TechnicalAnalysis.stochastic(highs, lows, closes, config.indicators.periods.stoch, config.indicators.settings.stochK, config.indicators.settings.stochD),
                TechnicalAnalysis.macd(closes, config.indicators.periods.rsi, config.indicators.periods.stoch, 9), // Assuming MACD fast/slow periods are related to RSI/Stoch periods, signal is fixed at 9
                TechnicalAnalysis.atr(highs, lows, closes, config.indicators.periods.atr),
                TechnicalAnalysis.bollingerBands(closes, config.indicators.periods.bb, config.indicators.settings.bbStd),
                TechnicalAnalysis.adx(highs, lows, closes, config.indicators.periods.adx),
                TechnicalAnalysis.williamsR(highs, lows, closes, config.indicators.periods.williams),
                TechnicalAnalysis.cci(highs, lows, closes, config.indicators.periods.cci),
                TechnicalAnalysis.mfi(highs, lows, closes, volumes, config.indicators.periods.mfi),
                TechnicalAnalysis.onBalanceVolume(closes, volumes),
                TechnicalAnalysis.accumulationDistributionLine(highs, lows, closes, volumes),
                TechnicalAnalysis.chaikinMoneyFlow(highs, lows, closes, volumes, config.indicators.periods.cmf),
                TechnicalAnalysis.vwap(highs, lows, closes, volumes),
                TechnicalAnalysis.sma(mtfCloses, config.indicators.periods.linreg), // Simplified linear regression proxy
                TechnicalAnalysis.findFairValueGap(candles),
                TechnicalAnalysis.detectDivergence(closes, TechnicalAnalysis.rsi(closes, config.indicators.periods.rsi))
            ];

            const [
                rsi, stoch, macd, atr, bb, adx,
                williamsR, cci, mfi, obv, adLine, cmf, vwap,
                regressionSlope, fvg, divergence
            ] = await Promise.all(analysisTasks);

            // Post-calculation analysis
            const last = closes.length - 1;
            const trendMTF = mtfCloses[last] > Utils.safeLast(mtfCloses.slice(0, -1), mtfCloses[last]) ? 'BULLISH' : 'BEARISH';

            // Volatility and Market Regime
            const volatility = this.calculateVolatility(closes);
            const avgVolatility = TechnicalAnalysis.sma(volatility, 50); // Use SMA for average volatility
            const marketRegime = this.determineMarketRegime(
                Utils.safeLast(volatility, 0),
                Utils.safeLast(avgVolatility, 1)
            );

            // Volume Analysis
            const volumeAnalysis = config.volumeAnalysis.enabled ?
                this.analyzeVolume(volumes, closes, config.volumeAnalysis) :
                { volumeSMA: [], volumeRatio: [], accumulation: [], distribution: [], flow: 'DISABLED' };

            // Volume Profile (simplified)
            const volumeProfile = this.createVolumeProfile(data.price, volumes, highs, lows);

            // Order Book Analysis
            const orderBookAnalysis = config.orderbook.flowAnalysis || config.orderbook.depthAnalysis ?
                this.analyzeOrderBook(data.bids, data.asks, data.price, Utils.safeLast(atr, 1), config.orderbook) :
                { imbalance: 0, depth: 0, flow: 'DISABLED', liquidity: 0 };

            // Support/Resistance Levels
            const srLevels = (config.orderbook.srLevels > 0) ?
                this.calculateSupportResistance(data.bids, data.asks, data.price, config.orderbook.srLevels) :
                { support: [], resistance: [] };

            // Liquidity Zones
            const liquidityZones = config.orderbook.wallThreshold > 0 ?
                this.identifyLiquidityZones(data.bids, data.asks, data.price, Utils.safeLast(atr, 1), config.orderbook.wallThreshold) :
                { buyWalls: [], sellWalls: [] };

            // Squeeze Detection
            const isSqueeze = MarketAnalyzer.detectSqueeze(bb);

            return {
                // Core data
                closes, highs, lows: closes.map((_, i) => lows[i]), volumes, // Ensure lows is mapped correctly
                mtfCloses,

                // Indicators
                rsi, stoch, macd, atr, bollinger: bb, adx: adx.adx, plusDI: adx.plusDI, minusDI: adx.minusDI,
                williamsR, cci, mfi, obv, adLine, cmf, vwap,
                regression: { slope: regressionSlope }, // Simplified regression slope
                fvg, divergence, volatility, avgVolatility,

                // Market Structure
                trendMTF, marketRegime, supportResistance: srLevels,
                liquidity: liquidityZones, isSqueeze,

                // Volume and Order Book Analysis
                volumeAnalysis, volumeProfile, orderBookAnalysis,

                timestamp: Date.now()
            };

        } catch (error) {
            throw new AnalysisError(`Market analysis failed: ${error.message}`);
        }
    }

    /**
     * Calculates recent price volatility.
     * @param {number[]} closes - Closing prices array.
     * @param {number} period - Lookback period for calculation.
     * @returns {number[]} Volatility values.
     */
    static calculateVolatility(closes, period = 20) {
        const volatility = Utils.safeArray(closes?.length ?? 0);
        if (!closes || closes.length < 2) return volatility;

        const returns = [];
        for (let i = 1; i < closes.length; i++) {
            // Using log returns for better statistical properties
            returns.push(Math.log(closes[i] / closes[i - 1]));
        }

        const annualizationFactor = 252; // Approx. trading days in a year

        for (let i = period; i < closes.length; i++) {
            const slice = returns.slice(i - period + 1, i + 1);
            const mean = slice.reduce((sum, val) => sum + val, 0) / period;
            const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
            const stdDev = Math.sqrt(variance);
            volatility[i] = stdDev * Math.sqrt(annualizationFactor); // Annualized volatility
        }
        return volatility;
    }

    /**
     * Determines the market regime based on current vs. average volatility.
     * @param {number} currentVol - Current volatility value.
     * @param {number} avgVol - Average volatility value.
     * @returns {'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'NORMAL_VOLATILITY'} Market regime.
     */
    static determineMarketRegime(currentVol, avgVol) {
        if (avgVol <= 0) return 'NORMAL_VOLATILITY';
        const ratio = currentVol / avgVol;
        if (ratio > 1.5) return 'HIGH_VOLATILITY';
        if (ratio < 0.5) return 'LOW_VOLATILITY';
        return 'NORMAL_VOLATILITY';
    }

    /**
     * Analyzes volume trends and flow.
     * @param {number[]} volumes - Volume array.
     * @param {number[]} closes - Closing prices array.
     * @param {object} config - Volume analysis configuration.
     * @returns {object} Volume analysis results.
     */
    static analyzeVolume(volumes, closes, config) {
        const volumeSMA = TechnicalAnalysis.sma(volumes, 20); // Use SMA for volume trend
        const volumeRatio = [];
        const accumulation = Utils.safeArray(volumes.length);
        const distribution = Utils.safeArray(volumes.length);

        for (let i = 0; i < volumes.length; i++) {
            const ratio = volumeSMA[i] > 0 ? volumes[i] / volumeSMA[i] : 1;
            volumeRatio.push(ratio);

            // Accumulation/Distribution based on price change
            const priceChange = i > 0 ? closes[i] - closes[i - 1] : 0;
            if (priceChange > 0) {
                accumulation[i] = 1; // Accumulation signal
            } else if (priceChange < 0) {
                distribution[i] = 1; // Distribution signal
            }
        }

        // Determine overall flow based on recent volume surge
        const recentVolumeRatios = volumeRatio.slice(-5); // Last 5 periods
        const avgRecentRatio = recentVolumeRatios.reduce((sum, r) => sum + r, 0) / recentVolumeRatios.length;

        let flow = 'NEUTRAL';
        if (avgRecentRatio > 1.3) flow = 'BULLISH'; // Increased volume on rising prices
        if (avgRecentRatio < 0.7) flow = 'BEARISH'; // Increased volume on falling prices

        // Add confirmation based on config
        if (config.flowConfirmation) {
            const recentAccumulation = accumulation.slice(-5).filter(a => a === 1).length;
            const recentDistribution = distribution.slice(-5).filter(d => d === 1).length;
            if (flow === 'BULLISH' && recentAccumulation < 3) flow = 'NEUTRAL'; // Weak confirmation
            if (flow === 'BEARISH' && recentDistribution < 3) flow = 'NEUTRAL'; // Weak confirmation
        }

        return {
            volumeSMA,
            volumeRatio,
            accumulation, // Binary array indicating price up (1) or not (0)
            distribution, // Binary array indicating price down (1) or not (0)
            flow
        };
    }

    /**
     * Creates a simplified volume profile.
     * @param {number} currentPrice - The current market price.
     * @param {number[]} volumes - Volume array.
     * @param {number[]} highs - High prices array.
     * @param {number[]} lows - Low prices array.
     * @returns {object} Simplified volume profile data.
     */
    static createVolumeProfile(currentPrice, volumes, highs, lows) {
        if (!volumes || volumes.length === 0) {
            return { price: currentPrice, volume: 0, profile: [] };
        }

        const totalVolume = volumes.reduce((sum, v) => sum + v, 0);
        // Simple approximation: average price weighted by volume
        const avgPriceWeighted = volumes.reduce((sum, v, i) => sum + (v * ((highs[i] + lows[i]) / 2)), 0) / totalVolume;

        // Placeholder for Point of Control (POC) and Value Area High/Low (VAH/VAL) if needed
        // For simplicity, returning current price and average weighted price.
        return {
            price: currentPrice,
            volume: totalVolume,
            profile: [
                { level: 'AVERAGE_VP', price: avgPriceWeighted, percentage: 100 },
                { level: 'CURRENT_PRICE', price: currentPrice, percentage: 0 }
            ]
        };
    }

    /**
     * Analyzes order book data for imbalance, depth, and flow.
     * @param {Array<{p: number, q: number}>} bids - Bid orders.
     * @param {Array<{p: number, q: number}>} asks - Ask orders.
     * @param {number} currentPrice - Current market price.
     * @param {number} atr - Average True Range value.
     * @param {object} config - Order book configuration.
     * @returns {object} Order book analysis results.
     */
    static analyzeOrderBook(bids, asks, currentPrice, atr, config) {
        const imbalance = 0;
        const depth = 0;
        let flow = 'NEUTRAL';

        if (!bids || !asks || bids.length === 0 || asks.length === 0) {
            return { imbalance, depth, flow, liquidity: 0 };
        }

        // Calculate total volume within a certain depth (e.g., top N levels or within ATR range)
        const depthLimit = Math.min(config.maxOrderbookDepth, bids.length, asks.length);
        const bidsDepth = bids.slice(0, depthLimit);
        const asksDepth = asks.slice(0, depthLimit);

        const totalBidVolume = bidsDepth.reduce((sum, b) => sum + b.q, 0);
        const totalAskVolume = asksDepth.reduce((sum, a) => sum + a.q, 0);
        const totalVolume = totalBidVolume + totalAskVolume;

        const imbalanceValue = totalVolume > 0 ? (totalBidVolume - totalAskVolume) / totalVolume : 0;

        // Calculate depth relative to ATR
        const atrRange = atr > 0 ? atr * 2 : currentPrice * 0.01; // Use 2*ATR or 1% of price as spread
        const priceSpread = Math.max(bids[0].p, asks[0].p) - Math.min(bids[0].p, asks[0].p);
        const depthValue = priceSpread > 0 ? Math.min(priceSpread / atrRange, 10) : 1; // Cap depth at 10x ATR

        // Determine order flow direction
        if (Math.abs(imbalanceValue) > config.imbalanceThreshold) {
            flow = imbalanceValue > 0 ? 'STRONG_BUY' : 'STRONG_SELL';
        } else if (imbalanceValue > 0) {
            flow = 'BUY';
        } else if (imbalanceValue < 0) {
            flow = 'SELL';
        }

        // Calculate liquidity score (simplified)
        const liquidityScore = Math.min(totalVolume / 1000000, 1.0); // Normalize volume, cap at 1M

        return {
            imbalance: imbalanceValue,
            depth: depthValue,
            flow,
            liquidity: liquidityScore
        };
    }

    /**
     * Calculates potential support and resistance levels from order book data.
     * @param {Array<{p: number, q: number}>} bids - Bid orders.
     * @param {Array<{p: number, q: number}>} asks - Ask orders.
     * @param {number} currentPrice - Current market price.
     * @param {number} maxLevels - Maximum number of levels to return.
     * @returns {{support: Array<{price: number, strength: number}>, resistance: Array<{price: number, strength: number}>}} SR levels.
     */
    static calculateSupportResistance(bids, asks, currentPrice, maxLevels) {
        const support = [];
        const resistance = [];

        if (!bids || !asks || bids.length === 0 || asks.length === 0) {
            return { support, resistance };
        }

        // Aggregate volume at specific price levels
        const bidVolumeAtPrice = bids.reduce((acc, order) => {
            acc[order.p] = (acc[order.p] || 0) + order.q;
            return acc;
        }, {});
        const askVolumeAtPrice = asks.reduce((acc, order) => {
            acc[order.p] = (acc[order.p] || 0) + order.q;
            return acc;
        }, {});

        const allPrices = new Set([...Object.keys(bidVolumeAtPrice).map(Number), ...Object.keys(askVolumeAtPrice).map(Number)]);
        const sortedPrices = Array.from(allPrices).sort((a, b) => a - b);

        // Simple heuristic: High volume at a price level can indicate support/resistance
        // Threshold could be dynamic (e.g., based on average volume or ATR)
        const avgBidVol = bids.reduce((sum, b) => sum + b.q, 0) / bids.length;
        const avgAskVol = asks.reduce((sum, a) => sum + a.q, 0) / asks.length;
        const volumeThresholdMultiplier = 2.0; // Consider levels with volume > 2x average

        for (const price of sortedPrices) {
            const bidVol = bidVolumeAtPrice[price] || 0;
            const askVol = askVolumeAtPrice[price] || 0;

            if (price < currentPrice && bidVol > avgBidVol * volumeThresholdMultiplier) {
                support.push({ price, strength: bidVol });
            } else if (price > currentPrice && askVol > avgAskVol * volumeThresholdMultiplier) {
                resistance.push({ price, strength: askVol });
            }
        }

        // Sort by proximity to current price and take top levels
        support.sort((a, b) => Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice));
        resistance.sort((a, b) => Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice));

        return {
            support: support.slice(0, maxLevels),
            resistance: resistance.slice(0, maxLevels)
        };
    }

    /**
     * Identifies significant volume clusters ("walls") in the order book.
     * @param {Array<{p: number, q: number}>} bids - Bid orders.
     * @param {Array<{p: number, q: number}>} asks - Ask orders.
     * @param {number} currentPrice - Current market price.
     * @param {number} atr - Average True Range value.
     * @param {number} wallThreshold - Multiplier to identify significant volume.
     * @returns {{buyWalls: Array<object>, sellWalls: Array<object>}} Identified liquidity zones.
     */
    static identifyLiquidityZones(bids, asks, currentPrice, atr, wallThreshold) {
        const buyWalls = [];
        const sellWalls = [];

        if (!bids || !asks || bids.length === 0 || asks.length === 0 || wallThreshold <= 0) {
            return { buyWalls, sellWalls };
        }

        const avgBidVol = bids.reduce((sum, b) => sum + b.q, 0) / bids.length;
        const avgAskVol = asks.reduce((sum, a) => sum + a.q, 0) / asks.length;
        const atrRange = atr > 0 ? atr : currentPrice * 0.005; // Use ATR or 0.5% of price

        for (const bid of bids) {
            if (bid.q > avgBidVol * wallThreshold) {
                buyWalls.push({
                    price: bid.p,
                    volume: bid.q,
                    distance: Math.abs(bid.p - currentPrice),
                    proximity: Math.abs(bid.p - currentPrice) < atrRange ? 'HIGH' : 'LOW'
                });
            }
        }

        for (const ask of asks) {
            if (ask.q > avgAskVol * wallThreshold) {
                sellWalls.push({
                    price: ask.p,
                    volume: ask.q,
                    distance: Math.abs(ask.p - currentPrice),
                    proximity: Math.abs(ask.p - currentPrice) < atrRange ? 'HIGH' : 'LOW'
                });
            }
        }

        return { buyWalls, sellWalls };
    }

    /**
     * Detects Bollinger Band Squeeze.
     * @param {{upper: number[], middle: number[], lower: number[]}} bb - Bollinger Bands data.
     * @returns {boolean} True if a squeeze is detected.
     */
    static detectSqueeze(bb) {
        if (!bb || !bb.upper || !bb.lower || bb.upper.length < 2) return false;
        const last = bb.upper.length - 1;
        const currentWidth = bb.upper[last] - bb.lower[last];
        const prevWidth = bb.upper[last - 1] - bb.lower[last - 1];
        // Squeeze occurs when current width is significantly smaller than previous
        return currentWidth < prevWidth * 0.8;
    }
}

// =============================================================================
// ENHANCED WEIGHTED SENTIMENT CALCULATOR
// =============================================================================

/**
 * Calculates a weighted sentiment score based on various market analysis components.
 */
class EnhancedWeightedSentimentCalculator {
    /**
     * Calculates the overall weighted sentiment score and confidence.
     * @param {object} analysis - Market analysis results.
     * @param {number} currentPrice - The current market price.
     * @param {object} weights - Weights for different components.
     * @param {object} config - Application configuration.
     * @returns {{score: number, confidence: number, components: object, timestamp: number}} Sentiment analysis results.
     */
    static calculate(analysis, currentPrice, weights, config) {
        if (!analysis || !analysis.closes) {
            throw new AnalysisError('Invalid analysis data for WSS calculation');
        }

        const last = analysis.closes.length - 1;
        let totalScore = 0;
        let totalWeight = 0;
        const components = {};

        try {
            // Define component calculations with their weights
            const componentCalculations = [
                { name: 'trend', weight: 0.25, func: this.calculateTrendComponent.bind(this) },
                { name: 'momentum', weight: 0.25, func: this.calculateMomentumComponent.bind(this) },
                { name: 'volume', weight: 0.20, func: this.calculateVolumeComponent.bind(this) },
                { name: 'orderFlow', weight: 0.15, func: this.calculateOrderFlowComponent.bind(this) },
                { name: 'structure', weight: 0.15, func: this.calculateStructureComponent.bind(this) }
            ];

            for (const comp of componentCalculations) {
                const result = await comp.func(analysis, currentPrice, last, weights, config);
                components[comp.name] = { ...result, weight: comp.weight }; // Store weight with result
                totalScore += result.score * comp.weight;
                totalWeight += comp.weight;
            }

            const weightedScore = totalWeight > 0 ? totalScore / totalWeight : 0;
            const confidence = this.calculateConfidence(components, analysis, config);

            return {
                score: Math.round(weightedScore * 100) / 100,
                confidence: Math.round(confidence * 100) / 100,
                components,
                timestamp: Date.now()
            };

        } catch (error) {
            console.error(COLORS.error(`Enhanced WSS calculation error: ${error.message}`));
            // Return neutral score with low confidence on error
            return { score: 0, confidence: 0, components: {}, timestamp: Date.now(), error: error.message };
        }
    }

    /**
     * Calculates the trend component score.
     * @private
     */
    static async calculateTrendComponent(analysis, last, weights, config) {
        let score = 0;
        const breakdown = {};

        // Multi-timeframe trend alignment
        if (analysis.trendMTF === 'BULLISH') {
            score += weights.trendMTF;
            breakdown.mtf = `Bullish (${analysis.trendMTF})`;
        } else if (analysis.trendMTF === 'BEARISH') {
            score -= weights.trendMTF;
            breakdown.mtf = `Bearish (${analysis.trendMTF})`;
        } else {
            breakdown.mtf = 'Neutral';
        }

        // Enhanced regression analysis (using SMA slope as proxy)
        const slope = Utils.safeNumber(analysis.regression?.slope?.[last], 0);
        // R-squared is not directly calculated here, using slope magnitude as proxy for trend strength
        if (slope > 0.00001) { // Threshold for positive slope
            score += weights.trendScalp * Math.min(slope * 10000, weights.trendScalp); // Scale slope to contribute
            breakdown.slope = `Positive (${slope.toFixed(6)})`;
        } else if (slope < -0.00001) { // Threshold for negative slope
            score -= weights.trendScalp * Math.min(Math.abs(slope) * 10000, weights.trendScalp);
            breakdown.slope = `Negative (${slope.toFixed(6)})`;
        } else {
            breakdown.slope = `Flat (${slope.toFixed(6)})`;
        }

        // Volume-weighted trend confirmation
        const volumeAnalysis = analysis.volumeAnalysis;
        if (volumeAnalysis && volumeAnalysis.flow.includes('BULLISH')) {
            score *= 1.1; // 10% boost for bullish volume confirmation
            breakdown.volumeConfirmation = 'Bullish Volume';
        } else if (volumeAnalysis && volumeAnalysis.flow.includes('BEARISH')) {
            score *= 0.9; // 10% reduction for bearish volume confirmation
            breakdown.volumeConfirmation = 'Bearish Volume';
        } else {
            breakdown.volumeConfirmation = 'Neutral Volume';
        }

        return { score, breakdown };
    }

    /**
     * Calculates the momentum component score.
     * @private
     */
    static async calculateMomentumComponent(analysis, last, weights) {
        let score = 0;
        const breakdown = {};

        // RSI momentum
        const rsi = Utils.safeNumber(analysis.rsi?.[last], 50);
        if (rsi < 30) {
            const oversoldStrength = (30 - rsi) / 30; // Normalized strength
            score += oversoldStrength * 0.6;
            breakdown.rsi = `Oversold (${rsi.toFixed(1)})`;
        } else if (rsi > 70) {
            const overboughtStrength = (rsi - 70) / 30;
            score -= overboughtStrength * 0.6;
            breakdown.rsi = `Overbought (${rsi.toFixed(1)})`;
        } else {
            breakdown.rsi = `Neutral (${rsi.toFixed(1)})`;
        }

        // Williams %R momentum
        const williams = Utils.safeNumber(analysis.williamsR?.[last], -50);
        if (williams < -80) { // Strongly oversold
            score += 0.4;
            breakdown.williams = 'Strong Oversold';
        } else if (williams > -20) { // Strongly overbought
            score -= 0.4;
            breakdown.williams = 'Strong Overbought';
        } else {
            breakdown.williams = `Neutral (${williams.toFixed(1)})`;
        }

        // CCI momentum
        const cci = Utils.safeNumber(analysis.cci?.[last], 0);
        if (cci < -100) {
            score += 0.3;
            breakdown.cci = 'Oversold';
        } else if (cci > 100) {
            score -= 0.3;
            breakdown.cci = 'Overbought';
        } else {
            breakdown.cci = `Neutral (${cci.toFixed(1)})`;
        }

        // MACD histogram momentum
        const macdHist = Utils.safeNumber(analysis.macd?.hist?.[last], 0);
        if (macdHist > 0.00001) { // Positive histogram indicates bullish momentum
            score += Math.min(macdHist * 10000, 0.4); // Scale histogram value
            breakdown.macd = `Bullish (${macdHist.toFixed(6)})`;
        } else if (macdHist < -0.00001) { // Negative histogram indicates bearish momentum
            score += Math.max(macdHist * 10000, -0.4);
            breakdown.macd = `Bearish (${macdHist.toFixed(6)})`;
        } else {
            breakdown.macd = `Neutral (${macdHist.toFixed(6)})`;
        }

        // ADX strength (trend strength, not direction)
        const adxValue = Utils.safeNumber(analysis.adx?.[last], 0);
        if (adxValue > 25) { // Strong trend indicated by ADX
            const strengthMultiplier = Math.min(adxValue / 50, 1.5); // Scale multiplier up to 1.5
            score *= strengthMultiplier;
            breakdown.adx = `Strong Trend (${adxValue.toFixed(1)})`;
        } else {
            breakdown.adx = `Weak Trend (${adxValue.toFixed(1)})`;
        }

        return { score, breakdown };
    }

    /**
     * Calculates the volume component score.
     * @private
     */
    static async calculateVolumeComponent(analysis, last, weights) {
        let score = 0;
        const breakdown = {};

        if (!analysis.volumeAnalysis || analysis.volumeAnalysis.flow === 'DISABLED') {
            return { score: 0, breakdown: { error: 'Volume analysis disabled or missing' } };
        }

        const { volumeAnalysis } = analysis;

        // Volume flow direction
        const flow = volumeAnalysis.flow;
        if (flow.includes('BULLISH')) {
            score += weights.volumeFlow;
            breakdown.flow = 'Bullish Volume';
        } else if (flow.includes('BEARISH')) {
            score -= weights.volumeFlow;
            breakdown.flow = 'Bearish Volume';
        } else {
            breakdown.flow = 'Neutral Volume';
        }

        // Volume surge detection (using volume ratio)
        const recentVolumeRatio = Utils.safeLast(volumeAnalysis.volumeRatio, 1);
        if (recentVolumeRatio > 1.8) { // Significant volume surge
            score += weights.volumeFlow * 0.4;
            breakdown.volumeSurge = 'Significant surge';
        } else if (recentVolumeRatio > 1.3) { // Moderate increase
            score += weights.volumeFlow * 0.2;
            breakdown.volumeSurge = 'Moderate increase';
        } else {
            breakdown.volumeSurge = 'Normal';
        }

        return { score, breakdown };
    }

    /**
     * Calculates the order flow component score.
     * @private
     */
    static async calculateOrderFlowComponent(analysis, last, weights) {
        let score = 0;
        const breakdown = {};

        if (!analysis.orderBookAnalysis || analysis.orderBookAnalysis.flow === 'DISABLED') {
            return { score: 0, breakdown: { error: 'Order book analysis disabled or missing' } };
        }

        const { orderBookAnalysis } = analysis;

        // Imbalance analysis
        const imbalance = orderBookAnalysis.imbalance;
        const imbalanceStrength = Math.min(Math.abs(imbalance), 1.0); // Cap at 100%

        if (imbalance > 0.3) { // Significant buy imbalance
            score += weights.orderFlow * imbalanceStrength;
            breakdown.imbalance = `Strong Buy (${(imbalance * 100).toFixed(1)}%)`;
        } else if (imbalance < -0.3) { // Significant sell imbalance
            score -= weights.orderFlow * imbalanceStrength;
            breakdown.imbalance = `Strong Sell (${(Math.abs(imbalance) * 100).toFixed(1)}%)`;
        } else {
            breakdown.imbalance = `Balanced (${(imbalance * 100).toFixed(1)}%)`;
        }

        // Liquidity quality bonus/penalty
        const liquidity = orderBookAnalysis.liquidity;
        if (liquidity > 0.8) { // High liquidity
            score *= 1.1; // Bonus for high liquidity
            breakdown.liquidity = 'High Quality';
        } else if (liquidity < 0.4) { // Low liquidity
            score *= 0.9; // Penalty for low liquidity
            breakdown.liquidity = 'Low Quality';
        } else {
            breakdown.liquidity = 'Moderate';
        }

        return { score, breakdown };
    }

    /**
     * Calculates the market structure component score.
     * @private
     */
    static async calculateStructureComponent(analysis, currentPrice, last, weights) {
        let score = 0;
        const breakdown = {};

        // Squeeze indicator
        if (analysis.isSqueeze) {
            const squeezeBonus = analysis.trendMTF === 'BULLISH' ? weights.squeeze : -weights.squeeze;
            score += squeezeBonus;
            breakdown.squeeze = `Active (${analysis.trendMTF})`;
        } else {
            breakdown.squeeze = 'Inactive';
        }

        // Divergence analysis
        const divergence = analysis.divergence || 'NONE';
        if (divergence.includes('BULLISH')) {
            score += weights.divergence;
            breakdown.divergence = divergence;
        } else if (divergence.includes('BEARISH')) {
            score -= weights.divergence;
            breakdown.divergence = divergence;
        } else {
            breakdown.divergence = 'None';
        }

        // Fair Value Gap interaction
        if (analysis.fvg) {
            const { fvg } = analysis;
            const priceDecimal = new Decimal(currentPrice);
            const fvgTop = new Decimal(fvg.top);
            const fvgBottom = new Decimal(fvg.bottom);

            if (fvg.type === 'BULLISH' && priceDecimal.gt(fvgBottom) && priceDecimal.lt(fvgTop)) {
                score += weights.liquidity; // Reward for price interacting with bullish FVG
                breakdown.fvg = 'Within Bullish FVG';
            } else if (fvg.type === 'BEARISH' && priceDecimal.lt(fvgTop) && priceDecimal.gt(fvgBottom)) {
                score -= weights.liquidity; // Penalize for price interacting with bearish FVG
                breakdown.fvg = 'Within Bearish FVG';
            } else {
                breakdown.fvg = `${fvg.type} (Outside Range)`;
            }
        } else {
            breakdown.fvg = 'None';
        }

        // Support/Resistance levels proximity
        if (analysis.supportResistance) {
            const { support, resistance } = analysis.supportResistance;
            const priceDecimal = new Decimal(currentPrice);

            // Find closest support below current price
            const closestSupport = support.length > 0
                ? support.reduce((prev, curr) => (curr.price < priceDecimal.toNumber() && curr.price > prev.price ? curr : prev), { price: -Infinity })
                : null;

            // Find closest resistance above current price
            const closestResistance = resistance.length > 0
                ? resistance.reduce((prev, curr) => (curr.price > priceDecimal.toNumber() && curr.price < prev.price ? curr : prev), { price: Infinity })
                : null;

            const priceThreshold = priceDecimal.mul(0.01); // 1% threshold

            if (closestSupport && priceDecimal.sub(closestSupport.price).lt(priceThreshold)) {
                score += weights.liquidity * 0.3; // Proximity bonus
                breakdown.srProximity = `Near Support (${closestSupport.price.toFixed(2)})`;
            } else if (closestResistance && closestResistance.price.sub(priceDecimal).lt(priceThreshold)) {
                score -= weights.liquidity * 0.3; // Proximity penalty
                breakdown.srProximity = `Near Resistance (${closestResistance.price.toFixed(2)})`;
            } else {
                breakdown.srProximity = 'Neutral';
            }
        }

        return { score, breakdown };
    }

    /**
     * Calculates confidence based on component agreement and confirmation signals.
     * @private
     */
    static calculateConfidence(components, analysis, config) {
        let agreementScore = 0;
        let totalComponents = 0;
        const directions = []; // 1 for bullish, -1 for bearish, 0 for neutral/weak

        // Determine direction from each component's score
        for (const compName in components) {
            const comp = components[compName];
            if (!comp || comp.score === undefined) continue;

            const threshold = 0.5; // Threshold for considering a component strongly directional
            if (comp.score > threshold) directions.push(1);
            else if (comp.score < -threshold) directions.push(-1);
            else directions.push(0);
            totalComponents++;
        }

        if (totalComponents === 0) return 0;

        // Calculate agreement percentage
        const positiveCount = directions.filter(d => d === 1).length;
        const negativeCount = directions.filter(d => d === -1).length;

        if (positiveCount > negativeCount) {
            agreementScore = positiveCount / totalComponents;
        } else if (negativeCount > positiveCount) {
            agreementScore = negativeCount / totalComponents;
        } else {
            agreementScore = 0.3; // Neutral confidence if counts are equal or all are neutral
        }

        // Boost confidence with strong volume confirmation
        if (analysis.volumeAnalysis && analysis.volumeAnalysis.flow.includes('BULLISH')) {
            agreementScore = Math.min(agreementScore * 1.15, 1.0); // Boost for bullish volume
        } else if (analysis.volumeAnalysis && analysis.volumeAnalysis.flow.includes('BEARISH')) {
            agreementScore = Math.min(agreementScore * 1.15, 1.0); // Boost for bearish volume
        }

        // Boost confidence with strong order book imbalance
        if (analysis.orderBookAnalysis && Math.abs(analysis.orderBookAnalysis.imbalance) > 0.4) {
            agreementScore = Math.min(agreementScore * 1.1, 1.0); // Boost for strong imbalance
        }

        // Ensure confidence is within bounds
        return Math.max(0, Math.min(agreementScore, 1.0));
    }
}

// =============================================================================
// DATA PROVIDER (ENHANCED)
// =============================================================================

/**
 * Fetches and caches market data from the exchange API.
 */
class DataProvider {
    /**
     * @param {object} config - Application configuration.
     */
    constructor(config) {
        if (!config) throw new ConfigError('Configuration is required');

        this.config = config.api;
        this.api = axios.create({
            baseURL: this.config.baseURL,
            timeout: this.config.timeout,
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': this.config.userAgent || 'WhaleWave-Titan-Enhanced/7.1'
            }
        });

        this.cache = new Map();
        this.cacheTimeout = 5000; // Cache duration in milliseconds (e.g., 5 seconds)

        this.setupInterceptors();
    }

    /** Sets up Axios interceptors for logging and error handling. */
    setupInterceptors() {
        this.api.interceptors.request.use(
            (config) => {
                console.debug(COLORS.DIM(`ðŸ”„ API Request: ${config.method?.toUpperCase()} ${config.url} Params: ${JSON.stringify(config.params)}`));
                return config;
            },
            (error) => Promise.reject(new ApiError(`Request interceptor error: ${error.message}`))
        );

        this.api.interceptors.response.use(
            (response) => response,
            (error) => {
                let apiError = error;
                if (error.response) {
                    // API returned a status code outside the 2xx range
                    apiError = new ApiError(
                        `API Error: ${error.response.data?.retMsg || error.message}`,
                        error.response.status,
                        error.response.data?.retCode,
                        error.response.data?.retMsg
                    );
                } else if (error.request) {
                    // Request was made but no response received
                    apiError = new ApiError(`No response received from API: ${error.message}`);
                } else {
                    // Something else happened
                    apiError = new ApiError(`API setup or request error: ${error.message}`);
                }
                console.error(COLORS.error(apiError.message));
                return Promise.reject(apiError);
            }
        );
    }

    /**
     * Fetches data from the API with retry logic and caching.
     * @param {string} endpoint - The API endpoint.
     * @param {object} params - Request parameters.
     * @param {number} maxRetries - Maximum number of retries.
     * @returns {Promise<object>} The API response data.
     * @throws {ApiError} If fetching fails after all retries.
     */
    async fetchWithRetry(endpoint, params, maxRetries = this.config.retries) {
        const cacheKey = `${endpoint}:${JSON.stringify(params)}`;
        const cached = this.cache.get(cacheKey);

        if (cached && (Date.now() - cached.timestamp) < this.cacheTimeout) {
            console.debug(COLORS.DIM(`ðŸ”„ Cache hit for: ${cacheKey}`));
            return cached.data;
        }

        let lastError;
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await this.api.get(endpoint, { params });

                if (!response.data) {
                    throw new ApiError('API returned empty response', response.status);
                }

                // Check Bybit's specific response format
                if (response.data.retCode !== undefined && response.data.retCode !== 0) {
                    throw new ApiError(
                        `API Error ${response.data.retCode}: ${response.data.retMsg}`,
                        response.status,
                        response.data.retCode,
                        response.data.retMsg
                    );
                }

                // Cache the successful response
                this.cache.set(cacheKey, {
                    data: response.data,
                    timestamp: Date.now()
                });
                console.debug(COLORS.DIM(`ðŸ”„ Cache set for: ${cacheKey}`));
                return response.data;

            } catch (error) {
                lastError = error;
                if (attempt === maxRetries) {
                    console.error(COLORS.error(`â Œ Failed to fetch ${endpoint} after ${maxRetries + 1} attempts.`));
                    break;
                }

                const delay = Utils.backoffDelay(attempt, this.config.delays?.retry || 800, this.config.backoffFactor || 1.5);
                console.warn(COLORS.warning(`âš ï¸  Retry ${attempt + 1}/${maxRetries} for ${endpoint} in ${delay}ms...`));
                await sleep(delay);
            }
        }

        throw lastError || new ApiError(`Unknown error fetching ${endpoint}`);
    }

    /**
     * Fetches all necessary market data for analysis.
     * @returns {Promise<object|null>} Market data object or null if fetching fails.
     */
    async fetchMarketData() {
        const { symbol, intervals, limits } = this.config;

        try {
            const requests = [
                this.fetchWithRetry('/tickers', { category: 'linear', symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol, interval: intervals.main, limit: limits.kline }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol, interval: intervals.trend, limit: limits.trendKline }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol, limit: limits.orderbook }),
                // Fetching daily/weekly for potential future use or broader context, ensure limit is sufficient
                this.fetchWithRetry('/kline', { category: 'linear', symbol, interval: intervals.daily, limit: 2 }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol, interval: intervals.weekly, limit: 2 })
            ];

            const [tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes, weeklyRes] = await Promise.all(requests);

            this.validateMarketDataResponse(tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes, weeklyRes);

            return this.parseMarketData(tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes, weeklyRes);

        } catch (error) {
            console.error(COLORS.error(`â Œ Data fetching failed: ${error.message}`));
            return null; // Indicate failure without crashing the loop
        }
    }

    /**
     * Validates the structure and content of API responses.
     * @param {object} tickerRes - Ticker API response.
     * @param {object} klineRes - Kline API response.
     * @param {object} klineMtfRes - MTF Kline API response.
     * @param {object} orderbookRes - Orderbook API response.
     * @param {object} dailyRes - Daily kline API response.
     * @param {object} weeklyRes - Weekly kline API response.
     * @throws {DataError} If validation fails.
     */
    validateMarketDataResponse(tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes, weeklyRes) {
        const validations = [
            { name: 'ticker data', check: tickerRes?.result?.list?.[0] },
            { name: 'main klines', check: klineRes?.result?.list },
            { name: 'trend klines', check: klineMtfRes?.result?.list },
            { name: 'orderbook bids', check: orderbookRes?.result?.b },
            { name: 'orderbook asks', check: orderbookRes?.result?.a },
            { name: 'daily klines', check: dailyRes?.result?.list?.[1] }, // Check second element for latest daily
            { name: 'weekly klines', check: weeklyRes?.result?.list?.[1] } // Check second element for latest weekly
        ];

        const missing = validations.filter(v => !v.check).map(v => v.name);
        if (missing.length > 0) {
            throw new DataError(`Missing or invalid data in API responses: ${missing.join(', ')}`);
        }
        // Further checks could be added for data types and array lengths.
    }

    /**
     * Parses raw API data into a structured format.
     * @param {object} tickerRes - Ticker API response.
     * @param {object} klineRes - Kline API response.
     * @param {object} klineMtfRes - MTF Kline API response.
     * @param {object} orderbookRes - Orderbook API response.
     * @param {object} dailyRes - Daily kline API response.
     * @param {object} weeklyRes - Weekly kline API response.
     * @returns {object} Structured market data.
     */
    parseMarketData(tickerRes, klineRes, klineMtfRes, orderbookRes, dailyRes, weeklyRes) {
        const parseCandles = (list) => {
            if (!list) return [];
            return list.reverse().map(c => ({
                t: parseInt(c[0]), // Timestamp
                o: parseFloat(c[1]), // Open
                h: parseFloat(c[2]), // High
                l: parseFloat(c[3]), // Low
                c: parseFloat(c[4]), // Close
                v: parseFloat(c[5])  // Volume
            }));
        };

        return {
            price: parseFloat(tickerRes.result.list[0].lastPrice),
            candles: parseCandles(klineRes.result.list),
            candlesMTF: parseCandles(klineMtfRes.result.list),
            daily: parseCandles([dailyRes.result.list[1]])[0] || null, // Handle potential missing daily data
            weekly: parseCandles([weeklyRes.result.list[1]])[0] || null, // Handle potential missing weekly data
            bids: orderbookRes.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
            asks: orderbookRes.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
            timestamp: Date.now()
        };
    }
}

// =============================================================================
// ENHANCED PAPER EXCHANGE
// =============================================================================

/**
 * Simulates trading operations with advanced risk management and performance tracking.
 */
class EnhancedPaperExchange {
    /**
     * @param {object} config - Risk and trading configuration.
     */
    constructor(config) {
        if (!config) throw new TradingError('Configuration is required');
        if (typeof Decimal === 'undefined') throw new TradingError('Decimal.js library is required');

        this.config = config.risk;
        this.startBalance = new Decimal(this.config.initialBalance);
        this.balance = new Decimal(this.config.initialBalance);
        this.dailyPnL = new Decimal(0);
        this.position = null; // { side, entry, quantity, stopLoss, takeProfit, strategy, timestamp, fees, confidence }
        this.lastDailyReset = new Date();
        this.tradeHistory = []; // Stores closed trades
        this.tradeDurations = []; // Stores duration of each trade in ms

        this.consecutiveLosses = 0;

        // Initialize performance metrics
        this.metrics = {
            totalTrades: 0,
            winningTrades: 0,
            losingTrades: 0,
            totalFees: new Decimal(0),
            maxDrawdownPercent: new Decimal(0),
            winRate: 0,
            profitFactor: 0,
            sharpeRatio: NaN, // Placeholder
            sortinoRatio: NaN, // Placeholder
            maxConsecutiveLosses: 0,
            avgWinAmount: new Decimal(0),
            avgLossAmount: new Decimal(0),
            avgTradeDurationMs: 0,
            totalPnL: new Decimal(0)
        };
    }

    /** Resets daily PnL if the day has changed. */
    resetDailyPnL() {
        const now = new Date();
        if (now.getDate() !== this.lastDailyReset.getDate()) {
            this.dailyPnL = new Decimal(0);
            this.lastDailyReset = now;
            console.log(COLORS.gray('ðŸ“… Daily P&L reset'));
        }
    }

    /** Checks if trading is allowed based on risk limits. */
    canTrade() {
        this.resetDailyPnL();

        // Calculate current drawdown percentage
        const drawdown = this.startBalance.isZero() ?
            new Decimal(0) :
            this.startBalance.sub(this.balance).div(this.startBalance).mul(100);

        if (drawdown.gt(this.config.maxDrawdownPercent)) {
            console.error(COLORS.error(`ðŸš¨ MAX DRAWDOWN HIT (${drawdown.toFixed(2)}%)`));
            return false;
        }

        // Calculate daily loss percentage
        const dailyLossPct = this.startBalance.isZero() ?
            new Decimal(0) :
            this.dailyPnL.div(this.startBalance).mul(100);

        if (dailyLossPct.lt(-this.config.dailyLossLimitPercent)) {
            console.error(COLORS.error(`ðŸš¨ DAILY LOSS LIMIT HIT (${dailyLossPct.toFixed(2)}%)`));
            return false;
        }

        // Check consecutive losses limit
        if (this.consecutiveLosses >= this.config.consecutiveLossLimit) {
            console.error(COLORS.error(`ðŸš¨ CONSECUTIVE LOSS LIMIT HIT (${this.consecutiveLosses})`));
            return false;
        }

        // Volatility adjustment check (if enabled)
        if (this.config.volatilityAdjustment) {
            const volatilityFactor = this.calculateVolatilityFactor();
            if (volatilityFactor > 2.0) { // Threshold for high volatility
                console.warn(COLORS.warning(`âš ï¸  High volatility detected (${volatilityFactor.toFixed(2)}x), reducing position size.`));
                // Note: This check currently only warns. A stricter implementation might return false.
            }
        }

        return true;
    }

    /**
     * Calculates a volatility factor based on recent trade returns.
     * Higher factor indicates higher recent volatility, suggesting smaller position sizes.
     * @returns {number} Volatility factor (1.0 = normal, >1.0 = higher volatility).
     */
    calculateVolatilityFactor() {
        if (this.tradeHistory.length < 5) return 1.0; // Not enough data

        // Consider returns of the last N trades (e.g., 10)
        const recentReturns = this.tradeHistory
            .slice(-10)
            .map(trade => trade.pnl.div(this.startBalance).toNumber()); // PnL as % of starting balance

        if (recentReturns.length === 0) return 1.0;

        // Calculate standard deviation of returns as a measure of volatility
        const mean = recentReturns.reduce((sum, r) => sum + r, 0) / recentReturns.length;
        const variance = recentReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / recentReturns.length;
        const stdDev = Math.sqrt(variance);

        // Convert std dev to a factor, capping it to avoid extreme values
        // This scaling factor (e.g., 100) might need tuning.
        const volatilityFactor = Math.min(stdDev * 100, 5.0); // Cap at 5x

        return Math.max(1.0, volatilityFactor); // Ensure factor is at least 1.0
    }

    /**
     * Evaluates a trading signal and manages open positions.
     * @param {number} price - Current market price.
     * @param {object} signal - Trading signal object { action, strategy, confidence, entry, stopLoss, takeProfit, riskReward, wss, reason }.
     */
    evaluate(price, signal) {
        const priceDecimal = new Decimal(price);

        // 1. Check Risk Management First
        if (!this.canTrade()) {
            if (this.position) {
                this.closePosition(priceDecimal, 'RISK_LIMIT_HIT');
            }
            return; // Cannot trade if risk limits are breached
        }

        // 2. Manage Existing Position
        if (this.position) {
            const closeDecision = this.shouldClosePosition(priceDecimal, signal);
            if (closeDecision.shouldClose) {
                this.closePosition(priceDecimal, closeDecision.reason);
            }
        }

        // 3. Open New Position if Signal is Valid and No Position Exists
        if (!this.position && signal.action !== 'HOLD') {
            // Validate signal quality before opening
            if (signal.confidence >= this.config.minConfidence && this.validateSignalQuality(signal)) {
                this.openPosition(priceDecimal, signal);
            }
        }
    }

    /**
     * Validates the quality of a trading signal before execution.
     * @param {object} signal - The trading signal.
     * @returns {boolean} True if the signal is considered valid.
     */
    validateSignalQuality(signal) {
        // Check for AI errors or invalid strategies
        if (!signal.strategy || signal.strategy === 'AI_ERROR' || signal.strategy === 'PARSING_ERROR') {
            console.warn(COLORS.warning(`Signal rejected: Invalid strategy '${signal.strategy}'.`));
            return false;
        }

        // Check risk-reward ratio
        if (signal.riskReward < this.config.minRiskRewardRatio) {
            console.warn(COLORS.warning(`Signal rejected: Poor risk-reward ratio (${signal.riskReward.toFixed(2)}), minimum required is ${this.config.minRiskRewardRatio}.`));
            return false;
        }

        // Check confidence level against minimum requirement
        if (signal.confidence < this.config.ai.minConfidence) {
            console.warn(COLORS.warning(`Signal rejected: Confidence (${(signal.confidence * 100).toFixed(1)}%) below minimum (${(this.config.ai.minConfidence * 100).toFixed(0)}%).`));
            return false;
        }

        // Check if entry, SL, TP are valid numbers
        if (isNaN(signal.entry) || isNaN(signal.stopLoss) || isNaN(signal.takeProfit) ||
            signal.entry === 0 || signal.stopLoss === 0 || signal.takeProfit === 0) {
            console.warn(COLORS.warning('Signal rejected: Invalid price levels (entry, SL, or TP).'));
            return false;
        }

        return true;
    }

    /**
     * Determines if an open position should be closed based on price action, signal, or risk rules.
     * @param {Decimal} price - Current market price as a Decimal.
     * @param {object} signal - The latest trading signal.
     * @returns {{shouldClose: boolean, reason: string}} Decision to close and reason.
     */
    shouldClosePosition(price, signal) {
        if (!this.position) return { shouldClose: false, reason: '' };

        const { position } = this;
        let shouldClose = false;
        let reason = '';

        // Check Stop Loss
        if (position.side === 'BUY' && price.lte(position.stopLoss)) {
            shouldClose = true;
            reason = 'STOP_LOSS';
            this.consecutiveLosses++;
        } else if (position.side === 'SELL' && price.gte(position.stopLoss)) {
            shouldClose = true;
            reason = 'STOP_LOSS';
            this.consecutiveLosses++;
        }

        // Check Take Profit
        if (!shouldClose) {
            if (position.side === 'BUY' && price.gte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
                this.consecutiveLosses = 0; // Reset losses on a win
            } else if (position.side === 'SELL' && price.lte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
                this.consecutiveLosses = 0; // Reset losses on a win
            }
        }

        // Check for Signal Change (if position side is opposite to new signal action)
        if (!shouldClose && signal.action !== 'HOLD' && signal.action !== position.side) {
            shouldClose = true;
            reason = `SIGNAL_CHANGE_${signal.action}`;
            // Note: Closing due to signal change might be considered a loss or win depending on price vs entry.
            // This logic assumes it's a forced exit, potentially resetting consecutive losses if profitable.
            if (position.side === 'BUY' && price.gt(position.entry)) this.consecutiveLosses = 0;
            if (position.side === 'SELL' && price.lt(position.entry)) this.consecutiveLosses = 0;
        }

        // Check consecutive losses limit (already checked in canTrade, but good as a final safety)
        if (!shouldClose && this.consecutiveLosses >= this.config.consecutiveLossLimit) {
            shouldClose = true;
            reason = 'CONSECUTIVE_LOSSES';
            this.consecutiveLosses = 0; // Reset after hitting limit
        }

        return { shouldClose, reason };
    }

    /**
     * Opens a new position based on a valid signal.
     * @param {Decimal} entryPrice - The entry price as a Decimal.
     * @param {object} signal - The trading signal object.
     */
    openPosition(entryPrice, signal) {
        try {
            const entry = new Decimal(signal.entry);
            const stopLoss = new Decimal(signal.stopLoss);
            const takeProfit = new Decimal(signal.takeProfit);

            // Validate price levels
            if (entry.isZero() || stopLoss.isZero() || takeProfit.isZero()) {
                throw new TradingError('Invalid price levels provided in signal.');
            }

            const distance = entry.sub(stopLoss).abs();
            if (distance.isZero()) {
                throw new TradingError('Entry and Stop Loss levels are identical.');
            }

            // Calculate position size based on risk parameters
            const riskAmountPerTrade = this.balance.mul(this.config.riskPercentPerTrade / 100);
            const volatilityFactor = this.config.volatilityAdjustment ? this.calculateVolatilityFactor() : 1.0;
            const adjustedRiskAmount = riskAmountPerTrade.div(volatilityFactor);

            let quantity = adjustedRiskAmount.div(distance);

            // Apply leverage cap
            const maxQuantityByLeverage = this.balance.mul(this.config.leverageCap).div(entryPrice);
            if (quantity.gt(maxQuantityByLeverage)) {
                quantity = maxQuantityByLeverage;
                console.warn(COLORS.warning('Position size capped by leverage limit.'));
            }

            // Ensure quantity is positive and reasonable
            if (quantity.isNegative() || quantity.isZero() || quantity.isNaN()) {
                throw new TradingError(`Calculated invalid position quantity: ${quantity.toString()}`);
            }

            // Calculate fees and slippage
            const slippageAmount = entryPrice.mul(this.config.slippagePercent / 100);
            const executionPrice = signal.action === 'BUY' ? entry.add(slippageAmount) : entry.sub(slippageAmount);
            const fee = executionPrice.mul(quantity).mul(this.config.fee);

            // Check if balance is sufficient for fees
            if (this.balance.lt(fee)) {
                throw new TradingError('Insufficient balance to cover trading fees.');
            }

            // Update balance and create position object
            this.balance = this.balance.sub(fee);
            this.position = {
                side: signal.action,
                entry: executionPrice,
                quantity,
                stopLoss,
                takeProfit,
                strategy: signal.strategy,
                timestamp: Date.now(),
                fees: fee,
                confidence: signal.confidence,
                entryPriceSignal: entryPrice.toNumber() // Store original signal entry for reference
            };

            this.metrics.totalFees = this.metrics.totalFees.add(fee);
            this.metrics.totalTrades++; // Increment total trades upon opening
            if (signal.action === 'BUY') this.metrics.winningTrades++; // Assume initial trade is potentially winning for stats if BUY
            else this.metrics.losingTrades++; // Assume initial trade is potentially losing if SELL for stats

            console.log(COLORS.success(
                `ðŸ“ˆ OPEN ${signal.action} [${signal.strategy}] @ ${executionPrice.toFixed(4)} | ` +
                `Size: ${quantity.toFixed(4)} | SL: ${stopLoss.toFixed(4)} | TP: ${takeProfit.toFixed(4)} | ` +
                `Conf: ${(signal.confidence * 100).toFixed(0)}%`
            ));

        } catch (error) {
            console.error(COLORS.error(`Position opening failed: ${error.message}`));
            // Ensure state is clean if opening fails
            this.position = null;
            this.consecutiveLosses = 0; // Reset losses if position couldn't open
        }
    }

    /**
     * Closes the current open position.
     * @param {Decimal} exitPrice - The exit price as a Decimal.
     * @param {string} reason - The reason for closing (e.g., 'STOP_LOSS', 'TAKE_PROFIT', 'SIGNAL_CHANGE').
     */
    closePosition(exitPrice, reason) {
        if (!this.position) return;

        try {
            const { position } = this;

            // Calculate slippage and execution price
            const slippageAmount = exitPrice.mul(this.config.slippagePercent / 100);
            const executionPrice = position.side === 'BUY' ? exitPrice.sub(slippageAmount) : exitPrice.add(slippageAmount);

            // Calculate PnL
            const rawPnL = position.side === 'BUY' ?
                executionPrice.sub(position.entry).mul(position.quantity) :
                position.entry.sub(executionPrice).mul(position.quantity);

            // Calculate exit fee
            const exitFee = executionPrice.mul(position.quantity).mul(this.config.fee);
            const netPnL = rawPnL.sub(exitFee);

            // Update balance and daily PnL
            this.balance = this.balance.add(netPnL);
            this.dailyPnL = this.dailyPnL.add(netPnL);
            this.metrics.totalFees = this.metrics.totalFees.add(exitFee);
            this.metrics.totalPnL = this.metrics.totalPnL.add(netPnL); // Track total PnL

            // Update trade statistics based on outcome
            if (netPnL.gte(0)) {
                this.metrics.winningTrades++;
                this.consecutiveLosses = 0; // Reset losses on a win
            } else {
                this.metrics.losingTrades++;
                this.consecutiveLosses++;
            }

            // Update max drawdown
            const currentDrawdown = this.startBalance.isZero() ?
                new Decimal(0) :
                this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
            if (currentDrawdown.gt(this.metrics.maxDrawdownPercent)) {
                this.metrics.maxDrawdownPercent = currentDrawdown;
            }

            // Record trade details
            const tradeDurationMs = Date.now() - position.timestamp;
            this.tradeDurations.push(tradeDurationMs);
            this.tradeHistory.push({
                side: position.side,
                entry: position.entry.toNumber(),
                exit: executionPrice.toNumber(),
                quantity: position.quantity.toNumber(),
                pnl: netPnL.toNumber(),
                strategy: position.strategy,
                durationMs: tradeDurationMs,
                reason,
                confidence: position.confidence,
                fees: exitFee.toNumber(),
                entrySignal: position.entryPriceSignal
            });

            // Log trade result
            const pnlColor = netPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(`${COLORS.bold(reason)}! PnL: ${pnlColor(netPnL.toFixed(2))} ` +
                `[${position.strategy}] | Duration: ${Utils.formatDuration(tradeDurationMs)}`);

            // Clear position and update metrics
            this.position = null;
            this.updatePerformanceMetrics();

        } catch (error) {
            console.error(COLORS.error(`Position closing failed: ${error.message}`));
        }
    }

    /** Updates performance metrics after a trade closes. */
    updatePerformanceMetrics() {
        const totalTrades = this.metrics.winningTrades + this.metrics.losingTrades;
        this.metrics.totalTrades = totalTrades; // Ensure totalTrades is accurate

        this.metrics.winRate = totalTrades > 0 ? this.metrics.winningTrades / totalTrades : 0;
        this.metrics.profitFactor = this.calculateProfitFactor();
        this.metrics.avgWinAmount = this.calculateAverageWinAmount();
        this.metrics.avgLossAmount = this.calculateAverageLossAmount();
        this.metrics.avgTradeDurationMs = this.tradeDurations.length > 0
            ? this.tradeDurations.reduce((sum, d) => sum + d, 0) / this.tradeDurations.length
            : 0;
        this.metrics.maxConsecutiveLosses = Math.max(this.metrics.maxConsecutiveLosses, this.consecutiveLosses);

        // Placeholders for Sharpe and Sortino ratios - require historical PnL data
        // this.metrics.sharpeRatio = this.calculateSharpeRatio();
        // this.metrics.sortinoRatio = this.calculateSortinoRatio();
    }

    /** Calculates the Profit Factor (Gross Profit / Gross Loss). */
    calculateProfitFactor() {
        const totalWins = this.tradeHistory
            .filter(t => t.pnl >= 0)
            .reduce((sum, t) => sum + t.pnl, 0);
        const totalLosses = this.tradeHistory
            .filter(t => t.pnl < 0)
            .reduce((sum, t) => sum + Math.abs(t.pnl), 0);

        if (totalLosses === 0) return totalWins > 0 ? Infinity : 1; // Avoid division by zero
        return totalWins / totalLosses;
    }

    /** Calculates the average amount of winning trades. */
    calculateAverageWinAmount() {
        const wins = this.tradeHistory.filter(t => t.pnl >= 0);
        if (wins.length === 0) return new Decimal(0);
        return wins.reduce((sum, t) => sum.add(new Decimal(t.pnl)), new Decimal(0)).div(wins.length);
    }

    /** Calculates the average absolute amount of losing trades. */
    calculateAverageLossAmount() {
        const losses = this.tradeHistory.filter(t => t.pnl < 0);
        if (losses.length === 0) return new Decimal(0);
        return losses.reduce((sum, t) => sum.add(new Decimal(Math.abs(t.pnl))), new Decimal(0)).div(losses.length);
    }

    /**
     * Calculates the current unrealized PnL for an open position.
     * @param {number} currentPrice - The current market price.
     * @returns {Decimal} The unrealized PnL.
     */
    getCurrentPnL(currentPrice) {
        if (!this.position) return new Decimal(0);

        const price = new Decimal(currentPrice);
        const { position } = this;

        return position.side === 'BUY' ?
            price.sub(position.entry).mul(position.quantity) :
            position.entry.sub(price).mul(position.quantity);
    }

    /**
     * Returns the current trading metrics and status.
     * @returns {object} Trading metrics object.
     */
    getMetrics() {
        const currentDrawdown = this.startBalance.isZero() ?
            new Decimal(0) :
            this.startBalance.sub(this.balance).div(this.startBalance).mul(100);

        const openPositionData = this.position ? {
            side: this.position.side,
            entry: this.position.entry.toNumber(),
            quantity: this.position.quantity.toNumber(),
            pnl: this.getCurrentPnL(this.position.entry.toNumber()).toNumber(), // PnL at entry price for reference
            strategy: this.position.strategy,
            confidence: this.position.confidence,
            stopLoss: this.position.stopLoss.toNumber(),
            takeProfit: this.position.takeProfit.toNumber(),
            entrySignalPrice: this.position.entrySignal
        } : null;

        return {
            ...this.metrics,
            currentBalance: this.balance.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalPnL: this.metrics.totalPnL.toNumber(),
            totalReturnPercent: this.startBalance.isZero() ? 0 : this.balance.sub(this.startBalance).div(this.startBalance).mul(100).toNumber(),
            currentDrawdownPercent: currentDrawdown.toNumber(),
            avgWinAmount: this.metrics.avgWinAmount.toNumber(),
            avgLossAmount: this.metrics.avgLossAmount.toNumber(),
            avgTradeDurationMinutes: this.metrics.avgTradeDurationMs / 1000 / 60,
            consecutiveLosses: this.consecutiveLosses,
            openPosition: openPositionData
        };
    }
}

// =============================================================================
// ENHANCED AI ANALYSIS ENGINE
// =============================================================================

/**
 * Manages interaction with the Generative AI model for signal generation.
 */
class EnhancedAIAnalysisEngine {
    /**
     * @param {object} config - AI configuration.
     */
    constructor(config) {
        if (!config) throw new AiError('Configuration is required');

        const apiKey = process.env.GEMINI_API_KEY;
        if (!apiKey) {
            throw new AiError('GEMINI_API_KEY environment variable is required.');
        }

        this.config = config.ai;
        try {
            this.gemini = new GoogleGenerativeAI(apiKey);
            this.model = this.gemini.getGenerativeModel({ model: this.config.model });
        } catch (error) {
            throw new AiError(`Failed to initialize Gemini AI: ${error.message}`);
        }

        this.lastRequestTime = 0;
        this.minRequestInterval = this.config.rateLimitMs || 1500;
        this.requestQueue = [];
        this.processingQueue = false;
    }

    /** Enforces rate limiting between AI API calls. */
    async enforceRateLimit() {
        const now = Date.now();
        const timeSinceLastRequest = now - this.lastRequestTime;

        if (timeSinceLastRequest < this.minRequestInterval) {
            const waitTime = this.minRequestInterval - timeSinceLastRequest;
            await sleep(waitTime);
        }
        this.lastRequestTime = Date.now();
    }

    /**
     * Generates a trading signal using the AI model.
     * @param {object} context - Context object containing market data, analysis, WSS, and config.
     * @returns {Promise<object>} The generated trading signal.
     */
    async generateSignal(context) {
        await this.enforceRateLimit();

        const prompt = this.buildEnhancedPrompt(context);

        let responseText = '';
        try {
            // Implement retry logic for AI calls
            for (let attempt = 0; attempt <= this.config.maxRetries; attempt++) {
                try {
                    const result = await this.model.generateContent(prompt);
                    const response = await result.response;
                    responseText = response.text();
                    if (!responseText) throw new AiError('AI returned empty response.');
                    break; // Success
                } catch (error) {
                    if (attempt === this.config.maxRetries) {
                        throw new AiError(`AI generation failed after ${this.config.maxRetries + 1} attempts: ${error.message}`);
                    }
                    const delay = Utils.backoffDelay(attempt, this.config.rateLimitMs || 1500, 1.5);
                    console.warn(COLORS.warning(`AI retry ${attempt + 1}/${this.config.maxRetries} in ${delay}ms...`));
                    await sleep(delay);
                }
            }
            return this.parseEnhancedAIResponse(responseText, context);

        } catch (error) {
            console.error(COLORS.error(`AI signal generation failed: ${error.message}`));
            return { // Return a safe default signal on error
                action: 'HOLD',
                strategy: 'AI_ERROR',
                confidence: 0,
                entry: 0, stopLoss: 0, takeProfit: 0, riskReward: 0, wss: 0,
                reason: `AI Error: ${error.message}`
            };
        }
    }

    /**
     * Constructs a detailed prompt for the AI model.
     * @param {object} context - Context object.
     * @returns {string} The formatted prompt.
     */
    buildEnhancedPrompt(context) {
        const { marketData, analysis, enhancedWSS, config } = context;
        const { score, confidence, components } = enhancedWSS;

        // Helper to format component scores safely
        const formatComponentScore = (score) => score !== undefined ? score.toFixed(2) : 'N/A';

        // Format indicator values safely
        const rsiVal = Utils.safeNumber(analysis.rsi?.[analysis.rsi.length - 1], 50);
        const williamsVal = Utils.safeNumber(analysis.williamsR?.[analysis.williamsR.length - 1], -50);
        const cciVal = Utils.safeNumber(analysis.cci?.[analysis.cci.length - 1], 0);
        const mfiVal = Utils.safeNumber(analysis.mfi?.[analysis.mfi.length - 1], 50);
        const adxVal = Utils.safeNumber(analysis.adx?.[analysis.adx.length - 1], 0);
        const macdHistVal = Utils.safeNumber(analysis.macd?.hist?.[analysis.macd.hist.length - 1], 0);
        const obvVal = Utils.safeNumber(analysis.obv?.[analysis.obv.length - 1], 0);
        const adLineVal = Utils.safeNumber(analysis.adLine?.[analysis.adLine.length - 1], 0);
        const cmfVal = Utils.safeNumber(analysis.cmf?.[analysis.cmf.length - 1], 0);
        const volRatioVal = Utils.safeNumber(analysis.volumeAnalysis?.volumeRatio?.[analysis.volumeAnalysis.volumeRatio.length - 1], 1);
        const orderImbalanceVal = analysis.orderBookAnalysis?.imbalance !== undefined ? (analysis.orderBookAnalysis.imbalance * 100).toFixed(1) + '%' : 'N/A';
        const liquidityVal = analysis.orderBookAnalysis?.liquidity !== undefined ? (analysis.orderBookAnalysis.liquidity * 100).toFixed(1) + '%' : 'N/A';

        // Format SR levels
        const supportLevels = analysis.supportResistance?.support?.map(s => `$${s.price.toFixed(2)}`).join(', ') || 'N/A';
        const resistanceLevels = analysis.supportResistance?.resistance?.map(r => `$${r.price.toFixed(2)}`).join(', ') || 'N/A';

        return `
ACT AS: Professional Cryptocurrency Trading Algorithm with Advanced Analytics
OBJECTIVE: Generate precise trading signals using enhanced multi-component analysis. Prioritize capital preservation and risk management.

ENHANCED WEIGHTED SENTIMENT SCORE:
- Primary Score: ${score.toFixed(2)} (Bias: ${score > 0 ? 'BULLISH' : score < 0 ? 'BEARISH' : 'NEUTRAL'})
- Confidence Level: ${(confidence * 100).toFixed(1)}%
- Component Breakdown:
    - Trend: ${formatComponentScore(components.trend?.score)}
    - Momentum: ${formatComponentScore(components.momentum?.score)}
    - Volume: ${formatComponentScore(components.volume?.score)}
    - OrderFlow: ${formatComponentScore(components.orderFlow?.score)}
    - Structure: ${formatComponentScore(components.structure?.score)}

CRITICAL THRESHOLDS (WSS Score & Confidence):
- Strong BUY Signal: WSS â‰¥ ${config.indicators.weights.actionThreshold + 1} and Confidence â‰¥ 0.80
- BUY Signal: WSS â‰¥ ${config.indicators.weights.actionThreshold} and Confidence â‰¥ 0.75
- Strong SELL Signal: WSS â‰¤ -${config.indicators.weights.actionThreshold + 1} and Confidence â‰¥ 0.80
- SELL Signal: WSS â‰¤ -${config.indicators.weights.actionThreshold} and Confidence â‰¥ 0.75
- HOLD: All other conditions or if risk limits are breached.

MARKET CONTEXT:
- Symbol: ${config.symbol}
- Current Price: $${marketData.price.toFixed(4)}
- Volatility (Annualized): ${analysis.volatility?.[analysis.volatility.length - 1]?.toFixed(4) || 'N/A'}
- Market Regime: ${analysis.marketRegime}

EXTENDED TECHNICAL INDICATORS (Latest Values):
- Multi-Timeframe Trend: ${analysis.trendMTF}
- RSI: ${rsiVal.toFixed(1)} (${this.colorizeIndicatorValue('rsi', rsiVal)})
- Williams %R: ${williamsVal.toFixed(1)} (${this.colorizeIndicatorValue('williams', williamsVal)})
- CCI: ${cciVal.toFixed(1)} (${this.colorizeIndicatorValue('cci', cciVal)})
- MFI: ${mfiVal.toFixed(1)} (${this.colorizeIndicatorValue('mfi', mfiVal)})
- ADX: ${adxVal.toFixed(1)}
- MACD Histogram: ${macdHistVal.toFixed(6)}
- OBV: ${obvVal.toFixed(0)}
- A/D Line: ${adLineVal.toFixed(0)}
- CMF: ${cmfVal.toFixed(4)}
- Volume Ratio (vs SMA): ${volRatioVal.toFixed(2)}x

VOLUME & ORDER BOOK ANALYSIS:
- Volume Flow: ${analysis.volumeAnalysis?.flow || 'N/A'}
- Order Book Imbalance: ${analysis.orderBookAnalysis?.imbalance !== undefined ? (analysis.orderBookAnalysis.imbalance * 100).toFixed(1) + '%' : 'N/A'} (${this.colorizeImbalanceValue(analysis.orderBookAnalysis?.imbalance)})
- Liquidity Quality: ${analysis.orderBookAnalysis?.liquidity !== undefined ? (analysis.orderBookAnalysis.liquidity * 100).toFixed(1) + '%' : 'N/A'}

MARKET STRUCTURE:
- Fair Value Gap: ${analysis.fvg ? `${analysis.fvg.type} @ $${analysis.fvg.price.toFixed(2)}` : 'None'}
- Divergence: ${analysis.divergence}
- Squeeze Status: ${analysis.isSqueeze ? 'ACTIVE' : 'INACTIVE'}
- Support Levels (Closest): ${supportLevels}
- Resistance Levels (Closest): ${resistanceLevels}

ENHANCED STRATEGY FRAMEWORK (Select the MOST appropriate based on WSS, confidence, and context):
1. **TREND_FOLLOWING_ENHANCED**: Requires strong WSS (> ${config.indicators.weights.actionThreshold + 1}), high confidence (>0.8), bullish/bearish MTF trend alignment, and volume confirmation. Target ~1.5:1 R:R.
2. **VOLUME_BREAKOUT**: Triggered by Squeeze active, high volume ratio (>1.8), strong WSS (> ${config.indicators.weights.actionThreshold}), and high confidence (>0.75). Target ~1.2:1 R:R.
3. **ORDER_FLOW_IMBALANCE**: Triggered by significant order book imbalance (>0.4 or <-0.4), confirmed WSS, and high confidence (>0.8). Target ~1.5:1 R:R.
4. **MEAN_REVERSION_ADVANCED**: Triggered by extreme oscillator readings (RSI < 30 or > 70, Williams < -80 or > -20), strong WSS (> ${config.indicators.weights.actionThreshold + 1}), and high confidence (>0.8). Target ~1.2:1 R:R.
5. **LIQUIDITY_ENGULFING**: Triggered by price interacting with FVG or near SR levels, confirmed by volume and WSS, high confidence. Target ~1.5:1 R:R.

REQUIREMENTS FOR SIGNAL GENERATION:
- Determine the most fitting strategy from the framework.
- Calculate precise entry, stop-loss, and take-profit levels.
- Ensure a minimum risk-reward ratio of ${config.risk.minRiskRewardRatio}:1.
- Utilize technical levels (FVG, SR, ATR-based stops) for targets and stops.
- Consider volume and order flow for entry timing confirmation.
- If WSS threshold, confidence, or risk-reward criteria are not met, or if the setup is unclear, return HOLD.

OUTPUT FORMAT (JSON ONLY):
{
    "action": "BUY | SELL | HOLD",
    "strategy": "STRATEGY_NAME_FROM_FRAMEWORK",
    "confidence": 0.0-1.0,
    "entry": number,
    "stopLoss": number,
    "takeProfit": number,
    "riskReward": number,
    "wss": number,
    "reason": "Detailed reasoning including strategy selection, key indicators, WSS score, confidence, and risk-reward calculation."
}
        `.trim();
    }

    /**
     * Parses the AI's JSON response and performs validation.
     * @param {string} text - The raw text response from the AI.
     * @param {object} context - The context object used to generate the prompt.
     * @returns {object} The validated trading signal.
     */
    parseEnhancedAIResponse(text, context) {
        try {
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                throw new AiError('No valid JSON found in AI response.');
            }

            const signal = JSON.parse(jsonMatch[0]);

            // --- Rigorous Validation ---
            const requiredFields = ['action', 'strategy', 'confidence', 'entry', 'stopLoss', 'takeProfit'];
            for (const field of requiredFields) {
                if (signal[field] === undefined || signal[field] === null) {
                    throw new AiError(`Missing required field: '${field}'.`);
                }
            }

            // Validate action
            const validActions = ['BUY', 'SELL', 'HOLD'];
            if (!validActions.includes(signal.action)) {
                console.warn(COLORS.warning(`Invalid action '${signal.action}' received from AI. Defaulting to HOLD.`));
                signal.action = 'HOLD';
            }

            // Validate numerical fields and apply safe defaults
            signal.confidence = Utils.safeNumber(signal.confidence, 0);
            signal.entry = Utils.safeNumber(signal.entry, 0);
            signal.stopLoss = Utils.safeNumber(signal.stopLoss, 0);
            signal.takeProfit = Utils.safeNumber(signal.takeProfit, 0);
            signal.wss = Utils.safeNumber(signal.wss, 0); // Ensure WSS is also parsed

            // Apply enhanced WSS filter and confidence threshold from context
            const { enhancedWSS, config } = context;
            const actionThreshold = config.indicators.weights.actionThreshold;
            const minConfidence = config.ai.minConfidence;

            // Filter based on WSS score thresholds
            if (signal.action === 'BUY' && (enhancedWSS.score < actionThreshold || signal.confidence < minConfidence)) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${enhancedWSS.score.toFixed(2)}) below BUY threshold (${actionThreshold}) or confidence too low.`;
            } else if (signal.action === 'SELL' && (enhancedWSS.score > -actionThreshold || signal.confidence < minConfidence)) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${enhancedWSS.score.toFixed(2)}) above SELL threshold (${-actionThreshold}) or confidence too low.`;
            }

            // Re-check confidence after potential action change
            if (signal.confidence < minConfidence) {
                signal.action = 'HOLD';
                signal.reason = `Confidence (${(signal.confidence * 100).toFixed(1)}%) below minimum (${(minConfidence * 100).toFixed(0)}%).`;
            }

            // Validate Risk-Reward Ratio
            if (signal.action !== 'HOLD') {
                const risk = Math.abs(signal.entry - signal.stopLoss);
                const reward = Math.abs(signal.takeProfit - signal.entry);
                signal.riskReward = risk > 0 ? reward / risk : 0;

                if (signal.riskReward < config.risk.minRiskRewardRatio) {
                    signal.action = 'HOLD';
                    signal.reason = `Risk-reward ratio (${signal.riskReward.toFixed(2)}) below minimum (${config.risk.minRiskRewardRatio}).`;
                }
            }

            // Finalize reason if action is HOLD due to validation
            if (signal.action === 'HOLD' && !signal.reason) {
                signal.reason = 'No valid trading opportunity based on AI signal and validation rules.';
            } else if (signal.action !== 'HOLD' && !signal.reason) {
                 // Construct a default reason if none was set but action is valid
                 signal.reason = `Strategy: ${signal.strategy} | WSS: ${enhancedWSS.score.toFixed(2)} | Conf: ${(signal.confidence * 100).toFixed(1)}% | R:R ${signal.riskReward.toFixed(2)}`;
            }

            // Ensure all required fields are present, even if default
            signal.action = signal.action || 'HOLD';
            signal.strategy = signal.strategy || 'UNKNOWN';
            signal.confidence = signal.confidence || 0;
            signal.entry = signal.entry || 0;
            signal.stopLoss = signal.stopLoss || 0;
            signal.takeProfit = signal.takeProfit || 0;
            signal.riskReward = signal.riskReward || 0;
            signal.wss = signal.wss || enhancedWSS.score || 0; // Use parsed WSS or context WSS

            return signal;

        } catch (error) {
            console.error(COLORS.error(`Enhanced AI response parsing failed: ${error.message}`));
            return { // Return a safe default signal on parsing error
                action: 'HOLD',
                strategy: 'PARSING_ERROR',
                confidence: 0,
                entry: 0, stopLoss: 0, takeProfit: 0, riskReward: 0, wss: 0,
                reason: `Enhanced parsing error: ${error.message}`
            };
        }
    }

    /** Helper to colorize indicator values for display */
    colorizeIndicatorValue(type, value) {
        const v = Utils.safeNumber(value, 0);
        switch (type) {
            case 'rsi': return v > 70 ? COLORS.RED(v.toFixed(1)) : v < 30 ? COLORS.GREEN(v.toFixed(1)) : COLORS.YELLOW(v.toFixed(1));
            case 'williams': return v > -20 ? COLORS.RED(v.toFixed(1)) : v < -80 ? COLORS.GREEN(v.toFixed(1)) : COLORS.YELLOW(v.toFixed(1));
            case 'cci': return v > 100 ? COLORS.RED(v.toFixed(1)) : v < -100 ? COLORS.GREEN(v.toFixed(1)) : COLORS.YELLOW(v.toFixed(1));
            case 'mfi': return v > 80 ? COLORS.RED(v.toFixed(1)) : v < 20 ? COLORS.GREEN(v.toFixed(1)) : COLORS.YELLOW(v.toFixed(1));
            default: return COLORS.cyan(v.toFixed(2));
        }
    }

    /** Helper to colorize imbalance values */
    colorizeImbalanceValue(imbalance) {
        if (imbalance === undefined || imbalance === null) return COLORS.gray('N/A');
        const pct = (imbalance * 100).toFixed(1);
        return imbalance > 0.3 ? COLORS.GREEN(`+${pct}%`) :
               imbalance < -0.3 ? COLORS.RED(`${pct}%`) : COLORS.YELLOW(`${pct}%`);
    }
}

// =============================================================================
// ENHANCED TRADING ENGINE
// =============================================================================

/**
 * Orchestrates the entire trading bot, managing data flow, analysis, and execution.
 */
class EnhancedTradingEngine {
    /**
     * @param {object} config - The application configuration object.
     */
    constructor(config) {
        if (!config) throw new AppError('Configuration is required');

        this.config = config;
        this.dataProvider = new DataProvider(config);
        this.exchange = new EnhancedPaperExchange(config);
        this.ai = new EnhancedAIAnalysisEngine(config);
        this.isRunning = false;
        this.startTime = Date.now();

        // Initialize statistics
        this.stats = {
            dataFetchAttempts: 0,
            dataFetchSuccesses: 0,
            aiAnalysisCalls: 0,
            signalsGenerated: 0,
            validSignals: 0, // Count signals that passed validation
            tradesOpened: 0,
            tradesClosed: 0,
            wssCalculations: 0,
            marketAnalyses: 0,
            loopIterations: 0
        };

        // Performance monitoring data structures
        this.performanceMetrics = {
            loopTimesMs: [],
            analysisTimesMs: [],
            wssTimesMs: [],
            dataFetchTimesMs: [],
            memoryUsageMB: [],
            cpuUsagePercent: [], // Placeholder, requires external module like 'cpu-stat'
            networkLatencyMs: []
        };
    }

    /** Starts the main trading loop and event listeners. */
    async start() {
        console.clear();
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` ðŸš€ WHALEWAVE TITAN v7.1 ENHANCED STARTING... `
        ))));

        this.isRunning = true;
        this.setupSignalHandlers();

        console.log(COLORS.success('âœ… Enhanced engine started successfully'));
        console.log(COLORS.info(`ðŸ”§ Symbol: ${this.config.symbol}`));
        console.log(COLORS.info(`â ±ï¸  Loop Delay: ${this.config.delays.loop}ms`));
        console.log(COLORS.cyan('ðŸ“Š Features: Multi-Component WSS, Advanced Volume/Order Flow Analysis, AI Signals'));

        await this.mainLoop();
    }

    /** Sets up graceful shutdown handlers for SIGINT and SIGTERM. */
    setupSignalHandlers() {
        const shutdown = (signal) => {
            console.log(COLORS.error(`\nðŸ›‘ Received ${signal}. Initiating graceful shutdown...`));
            this.isRunning = false;
            this.displayEnhancedShutdownReport();
            process.exit(0);
        };

        process.on('SIGINT', () => shutdown('SIGINT'));
        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('uncaughtException', (error) => {
            console.error(COLORS.error(`\nFATAL: Uncaught Exception: ${error.message}`));
            console.error(error.stack); // Log stack trace for debugging
            shutdown('UNCAUGHT_EXCEPTION');
        });
        process.on('unhandledRejection', (reason, promise) => {
            console.error(COLORS.error(`\nFATAL: Unhandled Rejection at: ${promise}, reason: ${reason}`));
            console.error(reason instanceof Error ? reason.stack : reason); // Log stack trace if available
            shutdown('UNHANDLED_REJECTION');
        });
    }

    /** The main execution loop of the trading engine. */
    async mainLoop() {
        while (this.isRunning) {
            const loopStart = Date.now();

            try {
                this.stats.dataFetchAttempts++;
                const marketData = await this.dataProvider.fetchMarketData();

                if (!marketData) {
                    console.warn(COLORS.warning('âš ï¸  Failed to fetch market data. Retrying after delay...'));
                    await sleep(this.config.delays.retry);
                    continue; // Skip to next iteration
                }
                this.stats.dataFetchSuccesses++;

                // --- Market Analysis ---
                const analysisStart = Date.now();
                const analysis = await MarketAnalyzer.analyze(marketData, this.config);
                const analysisTime = Date.now() - analysisStart;
                this.stats.marketAnalyses++;

                // --- Weighted Sentiment Calculation ---
                const wssStart = Date.now();
                const enhancedWSS = await EnhancedWeightedSentimentCalculator.calculate(
                    analysis,
                    marketData.price,
                    this.config.indicators.weights,
                    this.config
                );
                const wssTime = Date.now() - wssStart;
                this.stats.wssCalculations++;

                // --- AI Signal Generation ---
                this.stats.aiAnalysisCalls++;
                const signal = await this.ai.generateSignal({
                    marketData,
                    analysis,
                    enhancedWSS,
                    config: this.config
                });

                this.stats.signalsGenerated++;
                if (signal.action !== 'HOLD') {
                    this.stats.validSignals++; // Count signals that passed AI validation
                }

                // --- Trading Execution ---
                this.exchange.evaluate(marketData.price, signal);
                if (this.exchange.position) {
                    this.stats.tradesOpened++; // Increment if a position was opened
                }
                // Note: tradesClosed count is managed internally by the exchange upon closing

                // --- Dashboard Update ---
                this.displayEnhancedDashboard(marketData, analysis, enhancedWSS, signal);

                // --- Performance Tracking ---
                const loopTime = Date.now() - loopStart;
                this.trackPerformanceMetrics(loopTime, analysisTime, wssTime, marketData.fetchTime);

            } catch (error) {
                console.error(COLORS.error(`Loop iteration failed: ${error.message}`));
                if (error.stack) console.error(COLORS.dim(error.stack)); // Log stack trace for debugging
                // Continue loop after error, potentially with a delay
            }

            await sleep(this.config.delays.loop);
            this.stats.loopIterations++;
        }
    }

    /** Records performance metrics for the current loop iteration. */
    trackPerformanceMetrics(loopTime, analysisTime, wssTime, dataFetchTime) {
        this.performanceMetrics.loopTimesMs.push(loopTime);
        this.performanceMetrics.analysisTimesMs.push(analysisTime);
        this.performanceMetrics.wssTimesMs.push(wssTime);
        if (dataFetchTime !== undefined) this.performanceMetrics.dataFetchTimesMs.push(dataFetchTime);

        // Memory usage (in MB)
        const memUsage = process.memoryUsage();
        this.performanceMetrics.memoryUsageMB.push(memUsage.heapUsed / 1024 / 1024);

        // CPU Usage (requires 'cpu-stat' module, placeholder for now)
        // this.performanceMetrics.cpuUsagePercent.push(currentCpuUsage);
    }

    /** Displays the real-time dashboard in the console. */
    displayEnhancedDashboard(marketData, analysis, enhancedWSS, signal) {
        console.clear();

        const border = COLORS.gray('â”€'.repeat(90));
        console.log(border);
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` ðŸŒŠ WHALEWAVE TITAN v7.1 ENHANCED | ${this.config.symbol} | $${marketData.price.toFixed(4)} `
        ))));
        console.log(border);

        // --- WSS Score and Confidence ---
        const wssScore = enhancedWSS.score;
        const wssConfidence = enhancedWSS.confidence;
        const wssColor = wssScore >= this.config.indicators.weights.actionThreshold + 1 ? COLORS.GREEN : // Strong Bullish
                        wssScore >= this.config.indicators.weights.actionThreshold ? COLORS.GREEN : // Bullish
                        wssScore <= -(this.config.indicators.weights.actionThreshold + 1) ? COLORS.RED : // Strong Bearish
                        wssScore <= -this.config.indicators.weights.actionThreshold ? COLORS.RED : // Bearish
                        COLORS.YELLOW; // Neutral/Weak
        const confidenceColor = wssConfidence >= 0.8 ? COLORS.GREEN :
                               wssConfidence >= 0.6 ? COLORS.YELLOW : COLORS.RED;

        console.log(`ðŸŽ¯ ENHANCED WSS: ${wssColor(wssScore.toFixed(2))} | ` +
                   `Confidence: ${confidenceColor((wssConfidence * 100).toFixed(1))}% | ` +
                   `Signal: ${this.colorizeSignal(signal.action)} ` +
                   `(${(signal.confidence * 100).toFixed(0)}%)`);

        console.log(`ðŸ“‹ Strategy: ${COLORS.blue(signal.strategy)} | ${signal.reason}`);
        console.log(border);

        // --- Component Breakdown ---
        const components = enhancedWSS.components;
        console.log(`ðŸ”§ Components: ` +
                   `Trend ${this.colorizeComponent(components.trend?.score)} | ` +
                   `Momentum ${this.colorizeComponent(components.momentum?.score)} | ` +
                   `Volume ${this.colorizeComponent(components.volume?.score)} | ` +
                   `OrderFlow ${this.colorizeComponent(components.orderFlow?.score)} | ` +
                   `Structure ${this.colorizeComponent(components.structure?.score)}`);
        console.log(border);

        // --- Market State ---
        const regimeColor = analysis.marketRegime.includes('HIGH') ? COLORS.RED :
                           analysis.marketRegime.includes('LOW') ? COLORS.GREEN : COLORS.YELLOW;
        const trendColor = analysis.trendMTF === 'BULLISH' ? COLORS.GREEN : COLORS.RED;

        console.log(`ðŸ“Š Regime: ${regimeColor(analysis.marketRegime)} | ` +
                   `Volatility: ${COLORS.cyan(Utils.safeNumber(analysis.volatility?.[analysis.volatility.length - 1], 0).toFixed(4))} | ` +
                   `Squeeze: ${analysis.isSqueeze ? COLORS.orange('ACTIVE') : 'OFF'} | ` +
                   `MTF Trend: ${trendColor(analysis.trendMTF)}`);

        // --- Key Indicators ---
        const rsi = Utils.safeNumber(analysis.rsi?.[analysis.rsi.length - 1], 50);
        const williams = Utils.safeNumber(analysis.williamsR?.[analysis.williamsR.length - 1], -50);
        const cci = Utils.safeNumber(analysis.cci?.[analysis.cci.length - 1], 0);
        const mfi = Utils.safeNumber(analysis.mfi?.[analysis.mfi.length - 1], 50);
        const adx = Utils.safeNumber(analysis.adx?.[analysis.adx.length - 1], 0);

        console.log(`ðŸ“ˆ Indicators: ` +
                   `RSI: ${this.colorizeIndicatorValue('rsi', rsi)} | ` +
                   `Williams %R: ${this.colorizeIndicatorValue('williams', williams)} | ` +
                   `CCI: ${this.colorizeIndicatorValue('cci', cci)} | ` +
                   `MFI: ${this.colorizeIndicatorValue('mfi', mfi)} | ` +
                   `ADX: ${COLORS.cyan(adx.toFixed(1))}`);
        console.log(border);

        // --- Volume and Order Flow ---
        const volumeFlow = analysis.volumeAnalysis?.flow || 'N/A';
        const volumeColor = volumeFlow.includes('BULLISH') ? COLORS.GREEN :
                           volumeFlow.includes('BEARISH') ? COLORS.RED : COLORS.YELLOW;
        const imbalanceColor = this.colorizeImbalanceValue(analysis.orderBookAnalysis?.imbalance);

        console.log(`ðŸ“Š Volume & Flow: ` +
                   `Flow: ${volumeColor(volumeFlow)} | ` +
                   `Ratio: ${COLORS.cyan(Utils.safeNumber(analysis.volumeAnalysis?.volumeRatio?.[analysis.volumeAnalysis.volumeRatio.length - 1], 1).toFixed(2))}x | ` +
                   `Order Imbalance: ${imbalanceColor} | ` +
                   `Liquidity: ${analysis.orderBookAnalysis?.liquidity ? (analysis.orderBookAnalysis.liquidity * 100).toFixed(1) + '%' : 'N/A'}`);

        // --- Market Structure ---
        const divColor = analysis.divergence.includes('BULLISH') ? COLORS.GREEN :
                        analysis.divergence.includes('BEARISH') ? COLORS.RED : COLORS.GRAY;
        const fvgColor = analysis.fvg ? (analysis.fvg.type === 'BULLISH' ? COLORS.GREEN : COLORS.RED) : COLORS.GRAY;
        const srCount = (analysis.supportResistance?.support?.length || 0) + (analysis.supportResistance?.resistance?.length || 0);

        console.log(`ðŸ”  Structure: ` +
                   `Divergence: ${divColor(analysis.divergence)} | ` +
                   `FVG: ${fvgColor(analysis.fvg ? analysis.fvg.type : 'None')} | ` +
                   `Squeeze: ${analysis.isSqueeze ? COLORS.orange('ACTIVE') : 'OFF'} | ` +
                   `SR Levels: ${COLORS.cyan(srCount)}`);
        console.log(border);

        // --- Performance Metrics ---
        const metrics = this.exchange.getMetrics();
        const pnlColor = metrics.dailyPnL >= 0 ? COLORS.GREEN : COLORS.RED;
        const profitColor = metrics.profitFactor > 1.5 ? COLORS.GREEN :
                           metrics.profitFactor > 1.0 ? COLORS.YELLOW : COLORS.RED;
        const drawdownColor = metrics.currentDrawdownPercent > 5 ? COLORS.RED : COLORS.YELLOW;

        console.log(`ðŸ’° Performance: ` +
                   `Balance: ${COLORS.green('$' + metrics.currentBalance.toFixed(2))} | ` +
                   `Daily P&L: ${pnlColor('$' + metrics.dailyPnL.toFixed(2))} | ` +
                   `Win Rate: ${COLORS.cyan((metrics.winRate * 100).toFixed(1))}% | ` +
                   `Profit Factor: ${profitColor(metrics.profitFactor.toFixed(2))}`);
        console.log(`ðŸ“‰ Max Drawdown: ${drawdownColor(metrics.currentDrawdownPercent.toFixed(2))}% | ` +
                   `Total Return: ${metrics.totalReturnPercent.toFixed(2)}%`);

        // --- Open Position Details ---
        if (metrics.openPosition) {
            const currentUnrealizedPnL = this.exchange.getCurrentPnL(marketData.price);
            const pnlDisplayColor = currentUnrealizedPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(COLORS.blue(`ðŸ“ˆ OPEN: ${metrics.openPosition.side} @ ${metrics.openPosition.entry.toFixed(4)} | ` +
                `Unrealized PnL: ${pnlDisplayColor(currentUnrealizedPnL.toFixed(2))} | ` +
                `Conf: ${(metrics.openPosition.confidence * 100).toFixed(0)}% | ` +
                `Strategy: ${metrics.openPosition.strategy}`));
        }
        console.log(border);

        // --- Uptime and Loop Stats ---
        const uptimeSeconds = (Date.now() - this.startTime) / 1000;
        const avgMemory = this.performanceMetrics.memoryUsageMB.length > 0 ?
            this.performanceMetrics.memoryUsageMB.reduce((sum, m) => sum + m, 0) / this.performanceMetrics.memoryUsageMB.length : 0;

        console.log(COLORS.gray(`â ±ï¸  Uptime: ${Utils.formatDuration(uptimeSeconds * 1000)} | ` +
                   `Avg Loop Time: ${this.stats.loopIterations > 0 ? (this.performanceMetrics.loopTimesMs.reduce((sum, t) => sum + t, 0) / this.performanceMetrics.loopTimesMs.length).toFixed(0) : 0}ms | ` +
                   `Memory Usage: ${COLORS.cyan(avgMemory.toFixed(1))}MB | ` +
                   `Data Success Rate: ${this.stats.dataFetchAttempts > 0 ? ((this.stats.dataFetchSuccesses / this.stats.dataFetchAttempts) * 100).toFixed(1) : 0}%`));
    }

    /** Colorizes the signal action (BUY, SELL, HOLD). */
    colorizeSignal(action) {
        switch (action) {
            case 'BUY': return COLORS.success('BUY');
            case 'SELL': return COLORS.error('SELL');
            default: return COLORS.gray('HOLD');
        }
    }

    /** Colorizes component scores based on their value. */
    colorizeComponent(score) {
        if (score === undefined) return COLORS.gray('N/A');
        const s = Utils.safeNumber(score, 0);
        if (s > 0.5) return COLORS.green(s.toFixed(2));
        if (s < -0.5) return COLORS.red(s.toFixed(2));
        return COLORS.yellow(s.toFixed(2));
    }

    /** Colorizes indicator values based on common thresholds. */
    colorizeIndicatorValue(type, value) {
        const v = Utils.safeNumber(value, 0);
        switch (type) {
            case 'rsi': return v > 70 ? COLORS.red(v.toFixed(1)) : v < 30 ? COLORS.green(v.toFixed(1)) : COLORS.yellow(v.toFixed(1));
            case 'williams': return v > -20 ? COLORS.red(v.toFixed(1)) : v < -80 ? COLORS.green(v.toFixed(1)) : COLORS.yellow(v.toFixed(1));
            case 'cci': return v > 100 ? COLORS.red(v.toFixed(1)) : v < -100 ? COLORS.green(v.toFixed(1)) : COLORS.yellow(v.toFixed(1));
            case 'mfi': return v > 80 ? COLORS.red(v.toFixed(1)) : v < 20 ? COLORS.green(v.toFixed(1)) : COLORS.yellow(v.toFixed(1));
            default: return COLORS.cyan(v.toFixed(2));
        }
    }

    /** Colorizes imbalance values for display. */
    colorizeImbalanceValue(imbalance) {
        if (imbalance === undefined || imbalance === null) return COLORS.gray('N/A');
        const pct = (imbalance * 100).toFixed(1);
        return imbalance > 0.3 ? COLORS.green(`+${pct}%`) :
               imbalance < -0.3 ? COLORS.red(`${pct}%`) : COLORS.yellow(`${pct}%`);
    }

    /** Displays a shutdown report summarizing key statistics. */
    displayEnhancedShutdownReport() {
        console.log(COLORS.error('\n--- ENHANCED SHUTDOWN REPORT ---'));
        const metrics = this.exchange.getMetrics();
        const uptimeMs = Date.now() - this.startTime;

        console.log(`â ±ï¸  Uptime: ${Utils.formatDuration(uptimeMs)}`);
        console.log(`ðŸ”„ Data Fetch Success Rate: ${this.stats.dataFetchAttempts > 0 ? ((this.stats.dataFetchSuccesses / this.stats.dataFetchAttempts) * 100).toFixed(1) : 0}%`);
        console.log(`ðŸ¤– AI Analysis Success Rate: ${this.stats.dataFetchSuccesses > 0 ? ((this.stats.aiAnalysisCalls / this.stats.dataFetchSuccesses) * 100).toFixed(1) : 0}%`);
        console.log(`ðŸŽ¯ WSS Calculations: ${this.stats.wssCalculations}`);
        console.log(`ðŸ“Š Market Analyses: ${this.stats.marketAnalyses}`);
        console.log(`ðŸ”„ Valid Signals Generated: ${this.stats.validSignals}`);
        console.log(`ðŸ’¼ Total Trades Executed: ${metrics.totalTrades}`);
        console.log(`ðŸ † Win Rate: ${(metrics.winRate * 100).toFixed(1)}%`);
        console.log(`ðŸ’° Profit Factor: ${metrics.profitFactor.toFixed(2)}`);
        console.log(`ðŸ’µ Final Balance: $${metrics.currentBalance.toFixed(2)}`);
        console.log(`ðŸ“ˆ Total PnL: $${metrics.totalPnL.toFixed(2)} (${metrics.totalReturnPercent.toFixed(2)}%)`);
        console.log(`ðŸ“‰ Max Drawdown: ${metrics.currentDrawdownPercent.toFixed(2)}%`);
        console.log(`â ±ï¸  Avg Trade Duration: ${Utils.formatDuration(metrics.avgTradeDurationMs)}`);
        console.log(`ðŸ”„ Max Consecutive Losses: ${metrics.maxConsecutiveLosses}`);
        console.log(`ðŸ’¸ Total Fees Paid: $${metrics.totalFees.toFixed(4)}`);

        // Performance Summary
        const avgMemory = this.performanceMetrics.memoryUsageMB.length > 0 ?
            this.performanceMetrics.memoryUsageMB.reduce((sum, m) => sum + m, 0) / this.performanceMetrics.memoryUsageMB.length : 0;
        const avgLoopTime = this.performanceMetrics.loopTimesMs.length > 0 ?
            this.performanceMetrics.loopTimesMs.reduce((sum, t) => sum + t, 0) / this.performanceMetrics.loopTimesMs.length : 0;

        console.log(`\n--- Performance Summary ---`);
        console.log(`ðŸ–¥ï¸  Avg Memory Usage: ${avgMemory.toFixed(1)}MB`);
        console.log(`âš¡ Avg Loop Time: ${avgLoopTime.toFixed(0)}ms`);
        console.log(COLORS.error('--- End of Report ---'));
    }
}

// =============================================================================
// APPLICATION ENTRY POINT
// =============================================================================

/**
 * Main function to initialize and start the trading engine.
 */
async function main() {
    try {
        console.log(COLORS.yellow('ðŸ”§ Loading enhanced configuration...'));
        const config = await ConfigManager.load();

        console.log(COLORS.success('âœ… Configuration loaded and validated.'));

        const engine = new EnhancedTradingEngine(config);
        await engine.start();

    } catch (error) {
        // Handle critical startup errors (e.g., config loading, AI key missing)
        if (error instanceof ConfigError || error instanceof AiError || error instanceof AppError) {
            console.error(COLORS.error(`\nFATAL STARTUP ERROR: ${error.message}`));
        } else {
            console.error(COLORS.error(`\nUNEXPECTED STARTUP ERROR: ${error.message}`));
            if (error.stack) console.error(COLORS.dim(error.stack));
        }
        process.exit(1); // Exit with a non-zero code to indicate failure
    }
}

// Execute main function only when the script is run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    main().catch(error => {
        // Catch any unhandled errors during main execution
        console.error(COLORS.error(`\nFATAL ERROR IN MAIN EXECUTION: ${error.message}`));
        if (error.stack) console.error(COLORS.dim(error.stack));
        process.exit(1);
    });
}

// Export modules for potential testing or external use
export {
    AppError, ConfigError, DataError, ApiError, AnalysisError, TradingError, AiError,
    ConfigManager,
    TechnicalAnalysis,
    MarketAnalyzer,
    EnhancedWeightedSentimentCalculator,
    DataProvider,
    EnhancedPaperExchange,
    EnhancedAIAnalysisEngine,
    EnhancedTradingEngine,
    Utils,
    COLORS
};
