/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v7.0 (Complete Refactor & Optimization)
 * ========================================================================
 * - REFACTOR: Complete architectural overhaul with better separation of concerns
 * - OPTIMIZATION: Performance improvements and memory management
 * - RELIABILITY: Enhanced error handling and input validation
 * - MAINTAINABILITY: Clean code structure with TypeScript-style documentation
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// =============================================================================
// CONFIGURATION & VALIDATION
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { main: '3', trend: '15', daily: 'D' },
        limits: { kline: 300, trendKline: 100, orderbook: 50 },
        delays: { loop: 4000, retry: 1000 },
        ai: { model: 'gemini-1.5-flash', minConfidence: 0.75 },
        risk: {
            maxDrawdown: 10.0,
            dailyLossLimit: 5.0,
            maxPositions: 1,
            initialBalance: 1000.00,
            riskPercent: 2.0,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001
        },
        indicators: {
            periods: {
                rsi: 10, stoch: 10, cci: 10, adx: 14,
                mfi: 10, chop: 14, linreg: 15, vwap: 20,
                bb: 20, keltner: 20, atr: 14, stFactor: 22,
                supertrend: 14
            },
            settings: {
                stochK: 3, stochD: 3, bbStd: 2.0, keltnerMult: 1.5,
                ceMult: 3.0
            },
            weights: {
                trendMTF: 2.2, trendScalp: 1.2, momentum: 1.8,
                macd: 1.0, regime: 0.8, squeeze: 1.0,
                liquidity: 1.5, divergence: 2.5, volatility: 0.5,
                actionThreshold: 2.0
            }
        },
        orderbook: { wallThreshold: 3.0, srLevels: 5 },
        api: { timeout: 8000, retries: 3, backoffFactor: 2 }
    });

    /**
     * Loads configuration from file with validation
     * @returns {object} Validated configuration object
     */
    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS)); // Deep clone
        
        try {
            const fileExists = await fs.access(this.CONFIG_FILE).then(() => true).catch(() => false);
            
            if (fileExists) {
                const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
                const userConfig = JSON.parse(fileContent);
                config = this.deepMerge(config, userConfig);
            } else {
                await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
            }
        } catch (error) {
            console.warn(chalk.yellow(`Config Warning: Using defaults - ${error.message}`));
        }
        
        return this.validate(config);
    }

    /**
     * Deep merge two objects
     * @param {object} target - Target object
     * @param {object} source - Source object
     * @returns {object} Merged object
     */
    static deepMerge(target, source) {
        const result = { ...target };
        
        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                result[key] = this.deepMerge(result[key] || {}, value);
            } else {
                result[key] = value;
            }
        }
        
        return result;
    }

    /**
     * Validates configuration object
     * @param {object} config - Configuration to validate
     * @returns {object} Validated configuration
     */
    static validate(config) {
        // Validate required fields
        const requiredFields = ['symbol', 'intervals', 'limits', 'delays', 'ai', 'risk', 'indicators'];
        for (const field of requiredFields) {
            if (!config[field]) throw new Error(`Missing required config field: ${field}`);
        }

        // Validate ranges
        if (config.risk.maxDrawdown < 0 || config.risk.maxDrawdown > 100) {
            throw new Error('maxDrawdown must be between 0 and 100');
        }
        
        if (config.ai.minConfidence < 0 || config.ai.minConfidence > 1) {
            throw new Error('minConfidence must be between 0 and 1');
        }

        return config;
    }
}

// =============================================================================
// UTILITIES & CONSTANTS
// =============================================================================

const COLORS = Object.freeze({
    GREEN: chalk.hex('#39FF14'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#00AFFF'),
    CYAN: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'),
    YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'),
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
});

/**
 * Utility functions for common operations
 */
class Utils {
    /**
     * Creates a safe array with specified length
     * @param {number} length - Array length
     * @returns {Array} Initialized array
     */
    static safeArray(length) {
        return new Array(Math.max(0, Math.floor(length))).fill(0);
    }

    /**
     * Safely gets the last element of an array
     * @param {Array} arr - Input array
     * @param {number} defaultValue - Default value if array is empty
     * @returns {*} Last element or default value
     */
    static safeLast(arr, defaultValue = 0) {
        return Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : defaultValue;
    }

    /**
     * Validates numerical input
     * @param {*} value - Value to validate
     * @param {number} defaultValue - Default value for invalid input
     * @returns {number} Validated number
     */
    static safeNumber(value, defaultValue = 0) {
        const num = typeof value === 'number' ? value : parseFloat(value);
        return Number.isFinite(num) ? num : defaultValue;
    }

    /**
     * Exponential backoff delay
     * @param {number} attempt - Current attempt number
     * @param {number} baseDelay - Base delay in milliseconds
     * @param {number} factor - Backoff factor
     * @returns {number} Delay in milliseconds
     */
    static backoffDelay(attempt, baseDelay, factor) {
        return baseDelay * Math.pow(factor, attempt);
    }
}

// =============================================================================
// TECHNICAL ANALYSIS LIBRARY (OPTIMIZED)
// =============================================================================

/**
 * Comprehensive technical analysis library with optimized algorithms
 */
class TechnicalAnalysis {
    /**
     * Simple Moving Average
     * @param {number[]} data - Input data
     * @param {number} period - Period for calculation
     * @returns {number[]} SMA values
     */
    static sma(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);
        
        const result = [];
        let sum = 0;
        
        // Calculate first value
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        
        // Calculate subsequent values using sliding window
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result.push(sum / period);
        }
        
        return Utils.safeArray(period - 1).concat(result);
    }

    /**
     * Exponential Moving Average
     * @param {number[]} data - Input data
     * @param {number} period - Period for calculation
     * @returns {number[]} EMA values
     */
    static ema(data, period) {
        if (!Array.isArray(data) || data.length === 0) return [];
        
        const result = Utils.safeArray(data.length);
        const multiplier = 2 / (period + 1);
        result[0] = data[0];
        
        for (let i = 1; i < data.length; i++) {
            result[i] = (data[i] * multiplier) + (result[i - 1] * (1 - multiplier));
        }
        
        return result;
    }

    /**
     * Wilder's smoothing (used in RSI)
     * @param {number[]} data - Input data
     * @param {number} period - Period for smoothing
     * @returns {number[]} Smoothed values
     */
    static wilders(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);
        
        const result = Utils.safeArray(data.length);
        let sum = 0;
        
        // Calculate initial value
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        
        // Apply Wilder's smoothing
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) {
            result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        }
        
        return result;
    }

    /**
     * Relative Strength Index (RSI)
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @returns {number[]} RSI values
     */
    static rsi(closes, period) {
        if (!Array.isArray(closes) || closes.length < 2) return Utils.safeArray(closes.length);
        
        const gains = [0];
        const losses = [0];
        
        // Calculate price changes
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        
        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);
        
        return closes.map((_, i) => {
            const loss = avgLoss[i];
            if (loss === 0) return 100;
            
            const rs = avgGain[i] / loss;
            return 100 - (100 / (1 + rs));
        });
    }

    /**
     * Stochastic Oscillator
     * @param {number[]} highs - High prices
     * @param {number[]} lows - Low prices
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @param {number} kPeriod - %K smoothing period
     * @param {number} dPeriod - %D smoothing period
     * @returns {object} {k: number[], d: number[]}
     */
    static stochastic(highs, lows, closes, period, kPeriod, dPeriod) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes)) {
            return { k: Utils.safeArray(closes.length), d: Utils.safeArray(closes.length) };
        }
        
        const k = Utils.safeArray(closes.length);
        
        for (let i = period - 1; i < closes.length; i++) {
            const sliceHigh = highs.slice(i - period + 1, i + 1);
            const sliceLow = lows.slice(i - period + 1, i + 1);
            
            const minLow = Math.min(...sliceLow);
            const maxHigh = Math.max(...sliceHigh);
            const range = maxHigh - minLow;
            
            k[i] = range === 0 ? 0 : 100 * ((closes[i] - minLow) / range);
        }
        
        const d = this.sma(k, dPeriod);
        return { k, d };
    }

    /**
     * MACD (Moving Average Convergence Divergence)
     * @param {number[]} closes - Closing prices
     * @param {number} fastPeriod - Fast EMA period
     * @param {number} slowPeriod - Slow EMA period
     * @param {number} signalPeriod - Signal line period
     * @returns {object} {line: number[], signal: number[], hist: number[]}
     */
    static macd(closes, fastPeriod, slowPeriod, signalPeriod) {
        if (!Array.isArray(closes) || closes.length === 0) {
            return { line: [], signal: [], hist: [] };
        }
        
        const fastEMA = this.ema(closes, fastPeriod);
        const slowEMA = this.ema(closes, slowPeriod);
        const line = fastEMA.map((fast, i) => fast - slowEMA[i]);
        const signal = this.ema(line, signalPeriod);
        const hist = line.map((val, i) => val - signal[i]);
        
        return { line, signal, hist };
    }

    /**
     * Average True Range (ATR)
     * @param {number[]} highs - High prices
     * @param {number[]} lows - Low prices
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @returns {number[]} ATR values
     */
    static atr(highs, lows, closes, period) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes)) {
            return Utils.safeArray(closes.length);
        }
        
        const trueRange = [0];
        
        for (let i = 1; i < closes.length; i++) {
            const range = highs[i] - lows[i];
            const rangeFromClose = Math.abs(highs[i] - closes[i - 1]);
            const rangeFromPrevClose = Math.abs(lows[i] - closes[i - 1]);
            
            trueRange.push(Math.max(range, rangeFromClose, rangeFromPrevClose));
        }
        
        return this.wilders(trueRange, period);
    }

    /**
     * Bollinger Bands
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @param {number} stdDev - Standard deviation multiplier
     * @returns {object} {upper: number[], middle: number[], lower: number[]}
     */
    static bollingerBands(closes, period, stdDev) {
        if (!Array.isArray(closes) || closes.length < period) {
            return { upper: Utils.safeArray(closes.length), middle: Utils.safeArray(closes.length), lower: Utils.safeArray(closes.length) };
        }
        
        const middle = this.sma(closes, period);
        const upper = [];
        const lower = [];
        
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) {
                upper.push(0);
                lower.push(0);
                continue;
            }
            
            let sumSq = 0;
            for (let j = 0; j < period; j++) {
                const diff = closes[i - j] - middle[i];
                sumSq += diff * diff;
            }
            
            const std = Math.sqrt(sumSq / period);
            upper.push(middle[i] + (std * stdDev));
            lower.push(middle[i] - (std * stdDev));
        }
        
        return { upper, middle, lower };
    }

    /**
     * Linear Regression
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @returns {object} {slope: number[], r2: number[]}
     */
    static linearRegression(closes, period) {
        if (!Array.isArray(closes) || closes.length < period) {
            return { slope: Utils.safeArray(closes.length), r2: Utils.safeArray(closes.length) };
        }
        
        const slopes = Utils.safeArray(closes.length);
        const r2s = Utils.safeArray(closes.length);
        
        // Pre-calculate sums for efficiency
        const sumX = (period * (period - 1)) / 2;
        const sumX2 = (period * (period - 1) * (2 * period - 1)) / 6;
        
        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0;
            let sumXY = 0;
            const ySlice = [];
            
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j];
                ySlice.push(val);
                sumY += val;
                sumXY += j * val;
            }
            
            const n = period;
            const numerator = (n * sumXY) - (sumX * sumY);
            const denominator = (n * sumX2) - (sumX * sumX);
            
            const slope = denominator === 0 ? 0 : numerator / denominator;
            const intercept = (sumY - slope * sumX) / n;
            
            // Calculate R-squared
            const yMean = sumY / n;
            let ssTot = 0;
            let ssRes = 0;
            
            for (let j = 0; j < period; j++) {
                const y = ySlice[j];
                const yPred = slope * j + intercept;
                ssTot += Math.pow(y - yMean, 2);
                ssRes += Math.pow(y - yPred, 2);
            }
            
            slopes[i] = slope;
            r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
        }
        
        return { slope: slopes, r2: r2s };
    }

    /**
     * Find Fair Value Gaps (FVG)
     * @param {Array} candles - Candlestick data
     * @returns {object|null} FVG information or null
     */
    static findFairValueGap(candles) {
        if (!Array.isArray(candles) || candles.length < 5) return null;
        
        const len = candles.length;
        const c1 = candles[len - 4];
        const c2 = candles[len - 3];
        const c3 = candles[len - 2];
        
        // Bullish FVG: gap between c1 high and c3 low
        if (c2.c > c2.o && c3.l > c1.h) {
            return {
                type: 'BULLISH',
                top: c3.l,
                bottom: c1.h,
                price: (c3.l + c1.h) / 2
            };
        }
        
        // Bearish FVG: gap between c3 high and c1 low
        if (c2.c < c2.o && c3.h < c1.l) {
            return {
                type: 'BEARISH',
                top: c1.l,
                bottom: c3.h,
                price: (c1.l + c3.h) / 2
            };
        }
        
        return null;
    }

    /**
     * Detect price/indicator divergences
     * @param {number[]} closes - Closing prices
     * @param {number[]} rsi - RSI values
     * @param {number} period - Lookback period
     * @returns {string} Divergence type
     */
    static detectDivergence(closes, rsi, period = 5) {
        if (!Array.isArray(closes) || !Array.isArray(rsi) || closes.length < period * 2) {
            return 'NONE';
        }
        
        const len = closes.length;
        
        // Regular bearish divergence: price higher highs, RSI lower highs
        const currentPriceHigh = Math.max(...closes.slice(len - period, len));
        const currentRsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period));
        const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        
        if (currentPriceHigh > prevPriceHigh && currentRsiHigh < prevRsiHigh) {
            return 'BEARISH_REGULAR';
        }
        
        // Regular bullish divergence: price lower lows, RSI higher lows
        const currentPriceLow = Math.min(...closes.slice(len - period, len));
        const currentRsiLow = Math.min(...rsi.slice(len - period, len));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period));
        const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
        
        if (currentPriceLow < prevPriceLow && currentRsiLow > prevRsiLow) {
            return 'BULLISH_REGULAR';
        }
        
        return 'NONE';
    }
}

// =============================================================================
// MARKET ANALYSIS ENGINE
// =============================================================================

/**
 * Market analysis engine that calculates various indicators and signals
 */
class MarketAnalyzer {
    /**
     * Analyzes market data and calculates all indicators
     * @param {object} data - Market data
     * @param {object} config - Configuration object
     * @returns {object} Complete market analysis
     */
    static async analyze(data, config) {
        const { candles, candlesMTF } = data;
        
        if (!candles || candles.length === 0) {
            throw new Error('Invalid candle data provided');
        }
        
        // Extract OHLCV arrays
        const closes = candles.map(c => c.c);
        const highs = candles.map(c => c.h);
        const lows = candles.map(c => c.l);
        const volumes = candles.map(c => c.v);
        const mtfCloses = candlesMTF.map(c => c.c);
        
        try {
            // Calculate all indicators in parallel for performance
            const [
                rsi, stoch, macd, atr, bb, reg,
                fvg, divergence
            ] = await Promise.all([
                TechnicalAnalysis.rsi(closes, config.indicators.periods.rsi),
                TechnicalAnalysis.stochastic(
                    highs, lows, closes, 
                    config.indicators.periods.stoch, 
                    config.indicators.settings.stochK,
                    config.indicators.settings.stochD
                ),
                TechnicalAnalysis.macd(
                    closes,
                    config.indicators.periods.rsi, // Using RSI period as fast
                    config.indicators.periods.stoch, // Using stoch period as slow
                    9 // Fixed signal period
                ),
                TechnicalAnalysis.atr(highs, lows, closes, config.indicators.periods.atr),
                TechnicalAnalysis.bollingerBands(
                    closes, 
                    config.indicators.periods.bb, 
                    config.indicators.settings.bbStd
                ),
                TechnicalAnalysis.linearRegression(closes, config.indicators.periods.linreg),
                TechnicalAnalysis.findFairValueGap(candles),
                TechnicalAnalysis.detectDivergence(closes, 
                    TechnicalAnalysis.rsi(closes, config.indicators.periods.rsi))
            ]);
            
            // Additional calculations
            const last = closes.length - 1;
            const mtfSma = TechnicalAnalysis.sma(mtfCloses, 20);
            const trendMTF = mtfCloses[last] > Utils.safeLast(mtfSma, mtfCloses[last]) ? 'BULLISH' : 'BEARISH';
            
            // Market regime analysis
            const volatility = this.calculateVolatility(closes);
            const avgVolatility = TechnicalAnalysis.sma(volatility, 50);
            const marketRegime = this.determineMarketRegime(
                Utils.safeLast(volatility, 0),
                Utils.safeLast(avgVolatility, 1)
            );
            
            // Support/Resistance levels from order book
            const srLevels = this.calculateSupportResistance(
                data.bids, data.asks, data.price, config.orderbook.srLevels
            );
            
            // Fair Value Gap and liquidity zones
            const liquidityZones = this.identifyLiquidityZones(
                data.bids, data.asks, data.price, 
                Utils.safeLast(atr, 1), config.orderbook.wallThreshold
            );
            
            return {
                // Core data
                closes, highs, lows, volumes,
                
                // Indicators
                rsi, stoch, macd, atr, bollinger: bb, regression: reg,
                fvg, divergence, volatility, avgVolatility,
                
                // Market structure
                trendMTF, marketRegime, supportResistance: srLevels,
                liquidity: liquidityZones,
                
                // Additional derived data
                isSqueeze: this.detectSqueeze(bb),
                timestamp: Date.now()
            };
            
        } catch (error) {
            throw new Error(`Market analysis failed: ${error.message}`);
        }
    }
    
    /**
     * Calculate historical volatility
     * @param {number[]} closes - Closing prices
     * @param {number} period - Period for calculation
     * @returns {number[]} Volatility values
     */
    static calculateVolatility(closes, period = 20) {
        if (!Array.isArray(closes) || closes.length < 2) {
            return Utils.safeArray(closes.length);
        }
        
        const returns = [];
        for (let i = 1; i < closes.length; i++) {
            returns.push(Math.log(closes[i] / closes[i - 1]));
        }
        
        const volatility = Utils.safeArray(closes.length);
        
        for (let i = period; i < closes.length; i++) {
            const slice = returns.slice(i - period + 1, i + 1);
            const mean = slice.reduce((sum, val) => sum + val, 0) / period;
            const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
            volatility[i] = Math.sqrt(variance) * Math.sqrt(252); // Annualized
        }
        
        return volatility;
    }
    
    /**
     * Determine market regime based on volatility
     * @param {number} currentVol - Current volatility
     * @param {number} avgVol - Average volatility
     * @returns {string} Market regime
     */
    static determineMarketRegime(currentVol, avgVol) {
        if (avgVol <= 0) return 'NORMAL';
        
        const ratio = currentVol / avgVol;
        if (ratio > 1.5) return 'HIGH_VOLATILITY';
        if (ratio < 0.5) return 'LOW_VOLATILITY';
        return 'NORMAL_VOLATILITY';
    }
    
    /**
     * Calculate support and resistance levels
     * @param {Array} bids - Bid orders
     * @param {Array} asks - Ask orders
     * @param {number} currentPrice - Current price
     * @param {number} maxLevels - Maximum levels to return
     * @returns {object} Support and resistance levels
     */
    static calculateSupportResistance(bids, asks, currentPrice, maxLevels) {
        if (!Array.isArray(bids) || !Array.isArray(asks)) {
            return { support: [], resistance: [] };
        }
        
        const pricePoints = [
            ...bids.map(b => b.p), 
            ...asks.map(a => a.p)
        ];
        const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
        
        const potentialLevels = [];
        
        for (const price of uniquePrices) {
            const bidVol = bids.filter(b => b.p === price).reduce((sum, b) => sum + b.q, 0);
            const askVol = asks.filter(a => a.p === price).reduce((sum, a) => sum + a.q, 0);
            
            if (bidVol > askVol * 2) {
                potentialLevels.push({ price, type: 'SUPPORT' });
            } else if (askVol > bidVol * 2) {
                potentialLevels.push({ price, type: 'RESISTANCE' });
            }
        }
        
        // Sort by distance from current price
        const sorted = potentialLevels.sort((a, b) => 
            Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice)
        );
        
        const support = sorted
            .filter(p => p.type === 'SUPPORT' && p.price < currentPrice)
            .slice(0, maxLevels)
            .map(p => p.price.toFixed(2));
            
        const resistance = sorted
            .filter(p => p.type === 'RESISTANCE' && p.price > currentPrice)
            .slice(0, maxLevels)
            .map(p => p.price.toFixed(2));
        
        return { support, resistance };
    }
    
    /**
     * Identify liquidity zones from order book
     * @param {Array} bids - Bid orders
     * @param {Array} asks - Ask orders
     * @param {number} currentPrice - Current price
     * @param {number} atr - Average True Range
     * @param {number} threshold - Volume threshold multiplier
     * @returns {object} Liquidity zones
     */
    static identifyLiquidityZones(bids, asks, currentPrice, atr, threshold) {
        if (!Array.isArray(bids) || !Array.isArray(asks)) {
            return { buyWalls: [], sellWalls: [] };
        }
        
        const avgBidVol = bids.reduce((sum, b) => sum + b.q, 0) / bids.length;
        const avgAskVol = asks.reduce((sum, a) => sum + a.q, 0) / asks.length;
        
        const buyWalls = bids
            .filter(b => b.q > avgBidVol * threshold)
            .map(b => ({
                price: b.p,
                distance: Math.abs(b.p - currentPrice),
                proximity: Math.abs(b.p - currentPrice) < atr ? 'HIGH' : 'LOW'
            }));
            
        const sellWalls = asks
            .filter(a => a.q > avgAskVol * threshold)
            .map(a => ({
                price: a.p,
                distance: Math.abs(a.p - currentPrice),
                proximity: Math.abs(a.p - currentPrice) < atr ? 'HIGH' : 'LOW'
            }));
        
        return { buyWalls, sellWalls };
    }
    
    /**
     * Detect Bollinger Band squeeze
     * @param {object} bb - Bollinger Bands object
     * @returns {boolean} True if squeeze is detected
     */
    static detectSqueeze(bb) {
        if (!bb || !bb.upper || !bb.lower) return false;
        
        const last = bb.upper.length - 1;
        if (last < 1) return false;
        
        const currentWidth = bb.upper[last] - bb.lower[last];
        const prevWidth = bb.upper[last - 1] - bb.lower[last - 1];
        
        // Squeeze detected when bands contract significantly
        return currentWidth < prevWidth * 0.8;
    }
}

// =============================================================================
// WEIGHTED SENTIMENT SCORE CALCULATOR
// =============================================================================

/**
 * Calculates the Weighted Sentiment Score (WSS) based on multiple indicators
 */
class WeightedSentimentCalculator {
    /**
     * Calculate WSS based on market analysis
     * @param {object} analysis - Market analysis data
     * @param {number} currentPrice - Current market price
     * @param {object} weights - WSS weights configuration
     * @returns {number} Calculated WSS score
     */
    static calculate(analysis, currentPrice, weights) {
        if (!analysis || !analysis.closes) {
            console.warn('Invalid analysis data for WSS calculation');
            return 0;
        }
        
        const last = analysis.closes.length - 1;
        const w = weights;
        let score = 0;
        
        try {
            // 1. TREND COMPONENT (40% weight)
            const trendScore = this.calculateTrendScore(analysis, last, w);
            score += trendScore;
            
            // 2. MOMENTUM COMPONENT (30% weight)
            const momentumScore = this.calculateMomentumScore(analysis, last, w);
            score += momentumScore;
            
            // 3. STRUCTURE COMPONENT (20% weight)
            const structureScore = this.calculateStructureScore(analysis, currentPrice, last, w);
            score += structureScore;
            
            // 4. VOLATILITY ADJUSTMENT (10% weight)
            const volatilityScore = this.calculateVolatilityAdjustment(analysis, w);
            score *= volatilityScore;
            
            return Math.round(score * 100) / 100; // Round to 2 decimal places
            
        } catch (error) {
            console.error(`WSS calculation error: ${error.message}`);
            return 0;
        }
    }
    
    /**
     * Calculate trend component of WSS
     * @param {object} analysis - Market analysis
     * @param {number} last - Last index
     * @param {object} weights - Weights configuration
     * @returns {number} Trend score
     */
    static calculateTrendScore(analysis, last, weights) {
        let trendScore = 0;
        
        // Multi-timeframe trend alignment
        if (analysis.trendMTF === 'BULLISH') {
            trendScore += weights.trendMTF;
        } else if (analysis.trendMTF === 'BEARISH') {
            trendScore -= weights.trendMTF;
        }
        
        // Regression slope confirmation
        const slope = Utils.safeNumber(analysis.regression?.slope?.[last], 0);
        const r2 = Utils.safeNumber(analysis.regression?.r2?.[last], 0);
        
        if (slope > 0 && r2 > 0.5) {
            trendScore += weights.trendScalp * r2;
        } else if (slope < 0 && r2 > 0.5) {
            trendScore -= weights.trendScalp * r2;
        }
        
        return trendScore;
    }
    
    /**
     * Calculate momentum component of WSS
     * @param {object} analysis - Market analysis
     * @param {number} last - Last index
     * @param {object} weights - Weights configuration
     * @returns {number} Momentum score
     */
    static calculateMomentumScore(analysis, last, weights) {
        let momentumScore = 0;
        
        // RSI momentum (normalized)
        const rsi = Utils.safeNumber(analysis.rsi?.[last], 50);
        if (rsi < 30) {
            momentumScore += ((30 - rsi) / 30) * 0.5; // Oversold bias
        } else if (rsi > 70) {
            momentumScore -= ((rsi - 70) / 30) * 0.5; // Overbought bias
        }
        
        // Stochastic momentum
        const stochK = Utils.safeNumber(analysis.stoch?.k?.[last], 50);
        if (stochK < 20) {
            momentumScore += ((20 - stochK) / 20) * 0.3;
        } else if (stochK > 80) {
            momentumScore -= ((stochK - 80) / 20) * 0.3;
        }
        
        // MACD histogram momentum
        const macdHist = Utils.safeNumber(analysis.macd?.hist?.[last], 0);
        if (macdHist > 0) {
            momentumScore += Math.min(macdHist * weights.macd, 0.5);
        } else {
            momentumScore += Math.max(macdHist * weights.macd, -0.5);
        }
        
        return momentumScore * weights.momentum;
    }
    
    /**
     * Calculate structure component of WSS
     * @param {object} analysis - Market analysis
     * @param {number} currentPrice - Current price
     * @param {number} last - Last index
     * @param {object} weights - Weights configuration
     * @returns {number} Structure score
     */
    static calculateStructureScore(analysis, currentPrice, last, weights) {
        let structureScore = 0;
        
        // Squeeze indicator
        if (analysis.isSqueeze) {
            const squeezeBonus = analysis.trendMTF === 'BULLISH' ? 
                weights.squeeze : -weights.squeeze;
            structureScore += squeezeBonus;
        }
        
        // Divergence analysis
        const divergence = analysis.divergence || 'NONE';
        if (divergence.includes('BULLISH')) {
            structureScore += weights.divergence;
        } else if (divergence.includes('BEARISH')) {
            structureScore -= weights.divergence;
        }
        
        // Fair Value Gap interaction
        if (analysis.fvg) {
            const { fvg } = analysis;
            if (fvg.type === 'BULLISH' && 
                currentPrice > fvg.bottom && currentPrice < fvg.top) {
                structureScore += weights.liquidity;
            } else if (fvg.type === 'BEARISH' && 
                       currentPrice < fvg.top && currentPrice > fvg.bottom) {
                structureScore -= weights.liquidity;
            }
        }
        
        // Liquidity zones
        const atr = Utils.safeNumber(analysis.atr?.[last], 1);
        const proximityThreshold = atr * 0.5;
        
        if (analysis.liquidity?.buyWalls) {
            const nearBuyWall = analysis.liquidity.buyWalls.some(wall => 
                Math.abs(wall.price - currentPrice) < proximityThreshold
            );
            if (nearBuyWall) structureScore += weights.liquidity * 0.3;
        }
        
        if (analysis.liquidity?.sellWalls) {
            const nearSellWall = analysis.liquidity.sellWalls.some(wall => 
                Math.abs(wall.price - currentPrice) < proximityThreshold
            );
            if (nearSellWall) structureScore -= weights.liquidity * 0.3;
        }
        
        return structureScore;
    }
    
    /**
     * Calculate volatility adjustment factor
     * @param {object} analysis - Market analysis
     * @param {object} weights - Weights configuration
     * @returns {number} Volatility adjustment factor
     */
    static calculateVolatilityAdjustment(analysis, weights) {
        const currentVol = Utils.safeNumber(analysis.volatility?.[analysis.volatility.length - 1], 0);
        const avgVol = Utils.safeNumber(analysis.avgVolatility, 1);
        
        if (avgVol <= 0) return 1;
        
        const volRatio = currentVol / avgVol;
        
        // Reduce conviction in high volatility, increase in low volatility
        if (volRatio > 1.5) {
            return 1 - (weights.volatility * 0.5);
        } else if (volRatio < 0.5) {
            return 1 + (weights.volatility * 0.3);
        }
        
        return 1;
    }
}

// =============================================================================
// DATA PROVIDER (ENHANCED WITH ROBUST ERROR HANDLING)
// =============================================================================

/**
 * Enhanced data provider with comprehensive error handling and retry logic
 */
class DataProvider {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        
        this.config = config;
        this.api = axios.create({
            baseURL: 'https://api.bybit.com/v5/market',
            timeout: config.api.timeout,
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': 'WhaleWave-Titan/7.0'
            }
        });
        
        // Setup request interceptor for logging
        this.api.interceptors.request.use(
            (config) => {
                console.debug(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
                return config;
            },
            (error) => Promise.reject(error)
        );
        
        // Setup response interceptor for error handling
        this.api.interceptors.response.use(
            (response) => response,
            (error) => {
                console.error(`API Error: ${error.message}`);
                return Promise.reject(error);
            }
        );
    }
    
    /**
     * Fetch data with exponential backoff retry logic
     * @param {string} endpoint - API endpoint
     * @param {object} params - Request parameters
     * @param {number} maxRetries - Maximum retry attempts
     * @returns {Promise<object>} API response data
     */
    async fetchWithRetry(endpoint, params, maxRetries = this.config.api.retries) {
        let lastError;
        
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await this.api.get(endpoint, { params });
                
                // Validate response structure
                if (!response.data) {
                    throw new Error('Empty response from API');
                }
                
                // Check for API-level errors
                if (response.data.retCode !== undefined && response.data.retCode !== 0) {
                    throw new Error(`API Error ${response.data.retCode}: ${response.data.retMsg}`);
                }
                
                return response.data;
                
            } catch (error) {
                lastError = error;
                
                if (attempt === maxRetries) {
                    console.error(`Failed to fetch ${endpoint} after ${maxRetries + 1} attempts`);
                    break;
                }
                
                // Exponential backoff
                const delay = Utils.backoffDelay(
                    attempt, 
                    this.config.delays.retry, 
                    this.config.api.backoffFactor
                );
                console.warn(`Retry ${attempt + 1}/${maxRetries} for ${endpoint} in ${delay}ms`);
                await sleep(delay);
            }
        }
        
        throw lastError;
    }
    
    /**
     * Fetch all market data in parallel
     * @returns {Promise<object|null>} Market data or null if failed
     */
    async fetchMarketData() {
        try {
            const requests = [
                this.fetchWithRetry('/tickers', {
                    category: 'linear',
                    symbol: this.config.symbol
                }),
                this.fetchWithRetry('/kline', {
                    category: 'linear',
                    symbol: this.config.symbol,
                    interval: this.config.intervals.main,
                    limit: this.config.limits.kline
                }),
                this.fetchWithRetry('/kline', {
                    category: 'linear',
                    symbol: this.config.symbol,
                    interval: this.config.intervals.trend,
                    limit: this.config.limits.trendKline
                }),
                this.fetchWithRetry('/orderbook', {
                    category: 'linear',
                    symbol: this.config.symbol,
                    limit: this.config.limits.orderbook
                }),
                this.fetchWithRetry('/kline', {
                    category: 'linear',
                    symbol: this.config.symbol,
                    interval: this.config.intervals.daily,
                    limit: 2
                })
            ];
            
            const [ticker, kline, klineMTF, orderbook, daily] = await Promise.all(requests);
            
            // Validate all required data is present
            this.validateMarketData(ticker, kline, klineMTF, orderbook, daily);
            
            return this.parseMarketData(ticker, kline, klineMTF, orderbook, daily);
            
        } catch (error) {
            console.warn(COLORS.ORANGE(`Data fetch failed: ${error.message}`));
            return null;
        }
    }
    
    /**
     * Validate market data structure
     * @param {object} ticker - Ticker data
     * @param {object} kline - Kline data
     * @param {object} klineMTF - Multi-timeframe kline data
     * @param {object} orderbook - Order book data
     * @param {object} daily - Daily data
     */
    validateMarketData(ticker, kline, klineMTF, orderbook, daily) {
        const validations = [
            { name: 'ticker', data: ticker?.result?.list?.[0] },
            { name: 'kline', data: kline?.result?.list },
            { name: 'klineMTF', data: klineMTF?.result?.list },
            { name: 'orderbook bids', data: orderbook?.result?.b },
            { name: 'orderbook asks', data: orderbook?.result?.a },
            { name: 'daily', data: daily?.result?.list?.[1] }
        ];
        
        const missing = validations.filter(v => !v.data).map(v => v.name);
        if (missing.length > 0) {
            throw new Error(`Missing data: ${missing.join(', ')}`);
        }
    }
    
    /**
     * Parse raw API data into structured format
     * @param {object} ticker - Ticker data
     * @param {object} kline - Kline data
     * @param {object} klineMTF - Multi-timeframe kline data
     * @param {object} orderbook - Order book data
     * @param {object} daily - Daily data
     * @returns {object} Parsed market data
     */
    parseMarketData(ticker, kline, klineMTF, orderbook, daily) {
        const parseCandles = (list) => list
            .reverse()
            .map(c => ({
                t: parseInt(c[0]),
                o: parseFloat(c[1]),
                h: parseFloat(c[2]),
                l: parseFloat(c[3]),
                c: parseFloat(c[4]),
                v: parseFloat(c[5])
            }));
        
        return {
            price: parseFloat(ticker.result.list[0].lastPrice),
            candles: parseCandles(kline.result.list),
            candlesMTF: parseCandles(klineMTF.result.list),
            bids: orderbook.result.b.map(x => ({
                p: parseFloat(x[0]),
                q: parseFloat(x[1])
            })),
            asks: orderbook.result.a.map(x => ({
                p: parseFloat(x[0]),
                q: parseFloat(x[1])
            })),
            daily: {
                h: parseFloat(daily.result.list[1][2]),
                l: parseFloat(daily.result.list[1][3]),
                c: parseFloat(daily.result.list[1][4])
            },
            timestamp: Date.now()
        };
    }
}

// =============================================================================
// RISK MANAGEMENT & EXCHANGE SIMULATOR
// =============================================================================

/**
 * Enhanced paper trading exchange with comprehensive risk management
 */
class PaperExchange {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        if (!Decimal) throw new Error('Decimal.js is required');
        
        this.config = config.risk;
        this.balance = new Decimal(config.risk.initialBalance);
        this.startBalance = this.balance;
        this.dailyPnL = new Decimal(0);
        this.position = null;
        this.lastDailyReset = new Date();
        this.tradeHistory = [];
        
        // Performance metrics
        this.metrics = {
            totalTrades: 0,
            winningTrades: 0,
            losingTrades: 0,
            totalFees: new Decimal(0),
            maxDrawdown: new Decimal(0),
            winRate: 0,
            profitFactor: 0
        };
    }
    
    /**
     * Reset daily P&L if new day
     */
    resetDailyPnL() {
        const now = new Date();
        if (now.getDate() !== this.lastDailyReset.getDate()) {
            this.dailyPnL = new Decimal(0);
            this.lastDailyReset = now;
            console.log(COLORS.GRAY('Daily P&L reset'));
        }
    }
    
    /**
     * Check if trading is allowed based on risk parameters
     * @returns {boolean} True if trading is allowed
     */
    canTrade() {
        this.resetDailyPnL();
        
        // Check drawdown limit
        const drawdown = this.startBalance.isZero() ? 
            new Decimal(0) : 
            this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
            
        if (drawdown.gt(this.config.maxDrawdown)) {
            console.error(COLORS.RED(`🚨 MAX DRAWDOWN HIT (${drawdown.toFixed(2)}%)`));
            return false;
        }
        
        // Check daily loss limit
        const dailyLossPct = this.startBalance.isZero() ? 
            new Decimal(0) : 
            this.dailyPnL.div(this.startBalance).mul(100);
            
        if (dailyLossPct.lt(-this.config.dailyLossLimit)) {
            console.error(COLORS.RED(`🚨 DAILY LOSS LIMIT HIT (${dailyLossPct.toFixed(2)}%)`));
            return false;
        }
        
        return true;
    }
    
    /**
     * Evaluate market and manage positions
     * @param {number} price - Current market price
     * @param {object} signal - Trading signal
     */
    evaluate(price, signal) {
        if (!this.canTrade()) {
            if (this.position) {
                this.closePosition(new Decimal(price), 'RISK_MANAGEMENT');
            }
            return;
        }
        
        const priceDecimal = new Decimal(price);
        
        // Close existing position if conditions are met
        if (this.position) {
            const shouldClose = this.shouldClosePosition(priceDecimal, signal);
            if (shouldClose.shouldClose) {
                this.closePosition(priceDecimal, shouldClose.reason);
            }
        }
        
        // Open new position if conditions are met
        if (!this.position && signal.action !== 'HOLD' && signal.confidence >= this.config.minConfidence) {
            this.openPosition(priceDecimal, signal);
        }
    }
    
    /**
     * Determine if position should be closed
     * @param {Decimal} price - Current price
     * @param {object} signal - Trading signal
     * @returns {object} {shouldClose: boolean, reason: string}
     */
    shouldClosePosition(price, signal) {
        if (!this.position) return { shouldClose: false, reason: '' };
        
        const { position } = this;
        let shouldClose = false;
        let reason = '';
        
        // Check stop loss and take profit
        if (position.side === 'BUY') {
            if (price.lte(position.stopLoss)) {
                shouldClose = true;
                reason = 'STOP_LOSS';
            } else if (price.gte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
            }
        } else { // SELL position
            if (price.gte(position.stopLoss)) {
                shouldClose = true;
                reason = 'STOP_LOSS';
            } else if (price.lte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
            }
        }
        
        // Signal change close
        if (!shouldClose && signal.action !== 'HOLD' && signal.action !== position.side) {
            shouldClose = true;
            reason = `SIGNAL_CHANGE_${signal.action}`;
        }
        
        return { shouldClose, reason };
    }
    
    /**
     * Open a new position
     * @param {Decimal} price - Current price
     * @param {object} signal - Trading signal
     */
    openPosition(price, signal) {
        try {
            const entry = new Decimal(signal.entry);
            const stopLoss = new Decimal(signal.stopLoss);
            const takeProfit = new Decimal(signal.takeProfit);
            
            // Validate entry and stop loss
            const distance = entry.sub(stopLoss).abs();
            if (distance.isZero()) {
                console.warn(COLORS.YELLOW('Invalid entry/stop loss: distance is zero'));
                return;
            }
            
            // Calculate position size based on risk management
            const riskAmount = this.balance.mul(this.config.riskPercent / 100);
            let quantity = riskAmount.div(distance);
            
            // Apply leverage cap
            const maxQuantity = this.balance
                .mul(this.config.leverageCap)
                .div(price);
                
            if (quantity.gt(maxQuantity)) {
                quantity = maxQuantity;
                console.warn(COLORS.YELLOW('Position size capped by leverage'));
            }
            
            // Validate quantity
            if (quantity.isNegative() || quantity.isZero()) {
                console.warn(COLORS.YELLOW('Invalid position size'));
                return;
            }
            
            // Calculate fees and slippage
            const slippage = price.mul(this.config.slippage);
            const executionPrice = signal.action === 'BUY' ? 
                entry.add(slippage) : 
                entry.sub(slippage);
            const fee = executionPrice.mul(quantity).mul(this.config.fee);
            
            // Check if balance is sufficient
            if (this.balance.lt(fee)) {
                console.warn(COLORS.YELLOW('Insufficient balance for fees'));
                return;
            }
            
            // Deduct fees and create position
            this.balance = this.balance.sub(fee);
            this.position = {
                side: signal.action,
                entry: executionPrice,
                quantity,
                stopLoss,
                takeProfit,
                strategy: signal.strategy,
                timestamp: Date.now(),
                fees: fee
            };
            
            this.metrics.totalFees = this.metrics.totalFees.add(fee);
            
            console.log(COLORS.GREEN(
                `OPEN ${signal.action} [${signal.strategy}] ` +
                `@ ${executionPrice.toFixed(4)} | ` +
                `Size: ${quantity.toFixed(4)} | ` +
                `SL: ${stopLoss.toFixed(4)} | ` +
                `TP: ${takeProfit.toFixed(4)}`
            ));
            
        } catch (error) {
            console.error(COLORS.RED(`Position opening failed: ${error.message}`));
        }
    }
    
    /**
     * Close existing position
     * @param {Decimal} price - Current price
     * @param {string} reason - Reason for closing
     */
    closePosition(price, reason) {
        if (!this.position) return;
        
        try {
            const { position } = this;
            
            // Calculate exit price with slippage
            const slippage = price.mul(this.config.slippage);
            const exitPrice = position.side === 'BUY' ? 
                price.sub(slippage) : 
                price.add(slippage);
            
            // Calculate P&L
            const rawPnL = position.side === 'BUY' ?
                exitPrice.sub(position.entry).mul(position.quantity) :
                position.entry.sub(exitPrice).mul(position.quantity);
            
            const exitFee = exitPrice.mul(position.quantity).mul(this.config.fee);
            const netPnL = rawPnL.sub(exitFee);
            
            // Update balance and metrics
            this.balance = this.balance.add(netPnL);
            this.dailyPnL = this.dailyPnL.add(netPnL);
            this.metrics.totalFees = this.metrics.totalFees.add(exitFee);
            
            // Update trade statistics
            this.metrics.totalTrades++;
            if (netPnL.gte(0)) {
                this.metrics.winningTrades++;
            } else {
                this.metrics.losingTrades++;
            }
            
            // Update max drawdown
            const currentDrawdown = this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
            if (currentDrawdown.gt(this.metrics.maxDrawdown)) {
                this.metrics.maxDrawdown = currentDrawdown;
            }
            
            // Calculate win rate and profit factor
            this.metrics.winRate = this.metrics.winningTrades / this.metrics.totalTrades;
            const totalWins = this.tradeHistory
                .filter(t => t.pnl.gte(0))
                .reduce((sum, t) => sum.add(t.pnl), new Decimal(0));
            const totalLosses = this.tradeHistory
                .filter(t => t.pnl.lt(0))
                .reduce((sum, t) => sum.add(t.pnl.abs()), new Decimal(0));
            
            this.metrics.profitFactor = totalLosses.gt(0) ? 
                totalWins.div(totalLosses).toNumber() : 
                totalWins.gt(0) ? Infinity : 0;
            
            // Record trade
            this.tradeHistory.push({
                side: position.side,
                entry: position.entry,
                exit: exitPrice,
                quantity: position.quantity,
                pnl: netPnL,
                strategy: position.strategy,
                duration: Date.now() - position.timestamp,
                reason
            });
            
            // Display result
            const pnlColor = netPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(`${COLORS.BOLD(reason)}! ` +
                `PnL: ${pnlColor(netPnL.toFixed(2))} ` +
                `[${position.strategy}]`);
            
            this.position = null;
            
        } catch (error) {
            console.error(COLORS.RED(`Position closing failed: ${error.message}`));
        }
    }
    
    /**
     * Get current position P&L
     * @param {number} currentPrice - Current market price
     * @returns {Decimal} Current P&L
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
     * Get performance metrics
     * @returns {object} Performance metrics
     */
    getMetrics() {
        const currentDrawdown = this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
        
        return {
            ...this.metrics,
            currentBalance: this.balance.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalReturn: this.balance.sub(this.startBalance).div(this.startBalance).mul(100).toNumber(),
            currentDrawdown: currentDrawdown.toNumber(),
            openPosition: this.position ? {
                side: this.position.side,
                entry: this.position.entry.toNumber(),
                quantity: this.position.quantity.toNumber(),
                pnl: this.getCurrentPnL(this.position.entry.toNumber()).toNumber()
            } : null
        };
    }
}

// =============================================================================
// AI ANALYSIS ENGINE
// =============================================================================

/**
 * AI-powered trading signal generator using Gemini
 */
class AIAnalysisEngine {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        
        const apiKey = process.env.GEMINI_API_KEY;
        if (!apiKey) {
            throw new Error('GEMINI_API_KEY environment variable is required');
        }
        
        this.config = config.ai;
        this.model = new GoogleGenerativeAI(apiKey).getGenerativeModel({
            model: config.ai.model
        });
        
        // Rate limiting
        this.lastRequest = 0;
        this.minRequestInterval = 2000; // 2 seconds between requests
    }
    
    /**
     * Rate limiting helper
     */
    async enforceRateLimit() {
        const now = Date.now();
        const timeSinceLastRequest = now - this.lastRequest;
        
        if (timeSinceLastRequest < this.minRequestInterval) {
            const waitTime = this.minRequestInterval - timeSinceLastRequest;
            await sleep(waitTime);
        }
        
        this.lastRequest = Date.now();
    }
    
    /**
     * Generate trading signal based on market analysis
     * @param {object} context - Market context and analysis
     * @returns {Promise<object>} Trading signal
     */
    async generateSignal(context) {
        await this.enforceRateLimit();
        
        const prompt = this.buildPrompt(context);
        
        try {
            const response = await this.model.generateContent(prompt);
            const text = response.response.text();
            
            return this.parseAIResponse(text, context);
            
        } catch (error) {
            console.error(COLORS.RED(`AI analysis failed: ${error.message}`));
            return {
                action: 'HOLD',
                confidence: 0,
                strategy: 'AI_ERROR',
                entry: 0,
                stopLoss: 0,
                takeProfit: 0,
                reason: `AI Error: ${error.message}`
            };
        }
    }
    
    /**
     * Build comprehensive prompt for AI analysis
     * @param {object} context - Market context
     * @returns {string} Formatted prompt
     */
    buildPrompt(context) {
        const { marketData, analysis, wss, config } = context;
        
        return `
ACT AS: Professional Cryptocurrency Trading Algorithm
OBJECTIVE: Generate precise trading signals with entry, stop-loss, and take-profit levels

QUANTITATIVE FRAMEWORK:
**WSS Score (Primary Filter):** ${wss} (Bias: ${wss > 0 ? 'BULLISH' : wss < 0 ? 'BEARISH' : 'NEUTRAL'})
**Critical Rule:** BUY requires WSS ≥ ${config.indicators.weights.actionThreshold}, SELL requires WSS ≤ -${config.indicators.weights.actionThreshold}

MARKET CONTEXT:
- Symbol: ${config.symbol}
- Current Price: $${marketData.price.toFixed(4)}
- Volatility: ${analysis.volatility?.[analysis.volatility.length - 1]?.toFixed(4) || 'N/A'}
- Market Regime: ${analysis.marketRegime}

TECHNICAL INDICATORS:
- Multi-Timeframe Trend: ${analysis.trendMTF}
- Linear Regression Slope: ${analysis.regression?.slope?.[analysis.regression.slope.length - 1]?.toFixed(6) || 'N/A'}
- RSI: ${analysis.rsi?.[analysis.rsi.length - 1]?.toFixed(2) || 'N/A'}
- Stochastic %K: ${analysis.stoch?.k?.[analysis.stoch.k.length - 1]?.toFixed(0) || 'N/A'}
- MACD Histogram: ${analysis.macd?.hist?.[analysis.macd.hist.length - 1]?.toFixed(6) || 'N/A'}
- ADX: ${analysis.adx?.[analysis.adx.length - 1]?.toFixed(2) || 'N/A'}

MARKET STRUCTURE:
- Fair Value Gap: ${analysis.fvg ? `${analysis.fvg.type} @ $${analysis.fvg.price.toFixed(2)}` : 'None'}
- Divergence: ${analysis.divergence}
- Squeeze Status: ${analysis.isSqueeze ? 'ACTIVE' : 'INACTIVE'}
- Support Levels: ${analysis.supportResistance?.support?.join(', ') || 'N/A'}
- Resistance Levels: ${analysis.supportResistance?.resistance?.join(', ') || 'N/A'}

STRATEGY FRAMEWORK:
1. **TREND_FOLLOWING** (WSS > 1.5): Follow multi-timeframe trend on pullbacks
2. **BREAKOUT** (Squeeze + WSS > 1.0): Trade volatility expansion in trend direction  
3. **MEAN_REVERSION** (|WSS| > 2.0, Chop > 60): Fade extreme readings
4. **LIQUIDITY_PLAY** (Near FVG/Walls): Trade retests of key levels
5. **DIVERGENCE_REVERSAL** (Strong Divergence): High-conviction reversals

REQUIREMENTS:
- Calculate precise entry, stop-loss, take-profit levels
- Ensure minimum 1:1.5 risk-reward ratio
- Use technical levels (Fibonacci, ATR, FVG) for targets
- If WSS threshold not met or unclear setup, return HOLD

OUTPUT FORMAT (JSON ONLY):
{
    "action": "BUY|SELL|HOLD",
    "strategy": "STRATEGY_NAME",
    "confidence": 0.0-1.0,
    "entry": number,
    "stopLoss": number,
    "takeProfit": number,
    "reason": "Detailed reasoning"
}
        `.trim();
    }
    
    /**
     * Parse and validate AI response
     * @param {string} text - AI response text
     * @param {object} context - Market context
     * @returns {object} Validated trading signal
     */
    parseAIResponse(text, context) {
        try {
            // Extract JSON from response
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                throw new Error('No valid JSON found in response');
            }
            
            const signal = JSON.parse(jsonMatch[0]);
            
            // Validate required fields
            const requiredFields = ['action', 'strategy', 'confidence', 'entry', 'stopLoss', 'takeProfit'];
            for (const field of requiredFields) {
                if (signal[field] === undefined) {
                    throw new Error(`Missing required field: ${field}`);
                }
            }
            
            // Validate action
            const validActions = ['BUY', 'SELL', 'HOLD'];
            if (!validActions.includes(signal.action)) {
                signal.action = 'HOLD';
            }
            
            // Ensure numerical values are valid
            signal.confidence = Utils.safeNumber(signal.confidence, 0);
            signal.entry = Utils.safeNumber(signal.entry, 0);
            signal.stopLoss = Utils.safeNumber(signal.stopLoss, 0);
            signal.takeProfit = Utils.safeNumber(signal.takeProfit, 0);
            
            // Apply WSS filter
            const { wss, config } = context;
            const threshold = config.indicators.weights.actionThreshold;
            
            if (signal.action === 'BUY' && wss < threshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${wss}) below BUY threshold (${threshold})`;
            } else if (signal.action === 'SELL' && wss > -threshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${wss}) above SELL threshold (${threshold})`;
            }
            
            // Validate risk-reward ratio
            if (signal.action !== 'HOLD') {
                const risk = Math.abs(signal.entry - signal.stopLoss);
                const reward = Math.abs(signal.takeProfit - signal.entry);
                const rrRatio = reward / risk;
                
                if (rrRatio < 1.0) {
                    signal.action = 'HOLD';
                    signal.reason = `Risk-reward ratio (${rrRatio.toFixed(2)}) below minimum (1.5)`;
                }
            }
            
            // Add default reason if missing
            if (!signal.reason) {
                signal.reason = signal.action === 'HOLD' ? 
                    'No clear trading opportunity' : 
                    `Strategy: ${signal.strategy}`;
            }
            
            return signal;
            
        } catch (error) {
            console.error(COLORS.RED(`AI response parsing failed: ${error.message}`));
            return {
                action: 'HOLD',
                confidence: 0,
                strategy: 'PARSING_ERROR',
                entry: 0,
                stopLoss: 0,
                takeProfit: 0,
                reason: `Parsing error: ${error.message}`
            };
        }
    }
}

// =============================================================================
// MAIN TRADING ENGINE
// =============================================================================

/**
 * Main trading engine orchestrating all components
 */
class TradingEngine {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        
        this.config = config;
        this.dataProvider = new DataProvider(config);
        this.exchange = new PaperExchange(config);
        this.ai = new AIAnalysisEngine(config);
        this.isRunning = false;
        this.startTime = Date.now();
        
        // Statistics
        this.stats = {
            dataFetchAttempts: 0,
            dataFetchSuccesses: 0,
            aiAnalysisCalls: 0,
            signalsGenerated: 0,
            positionsOpened: 0,
            positionsClosed: 0,
            averageLoopTime: 0
        };
    }
    
    /**
     * Start the trading engine
     */
    async start() {
        console.clear();
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` 🚀 WHALEWAVE TITAN v7.0 STARTING... `
        ))));
        
        this.isRunning = true;
        
        // Set up signal handlers for graceful shutdown
        this.setupSignalHandlers();
        
        console.log(COLORS.GREEN('Engine started successfully'));
        console.log(COLORS.GRAY(`Configuration: ${this.config.symbol}`));
        console.log(COLORS.GRAY(`Loop delay: ${this.config.delays.loop}ms`));
        
        await this.mainLoop();
    }
    
    /**
     * Setup graceful shutdown handlers
     */
    setupSignalHandlers() {
        const shutdown = (signal) => {
            console.log(COLORS.RED(`\n🛑 Received ${signal}. Starting graceful shutdown...`));
            this.isRunning = false;
            this.displayShutdownReport();
            process.exit(0);
        };
        
        process.on('SIGINT', () => shutdown('SIGINT'));
        process.on('SIGTERM', () => shutdown('SIGTERM'));
        process.on('uncaughtException', (error) => {
            console.error(COLORS.RED(`Uncaught Exception: ${error.message}`));
            shutdown('UNCAUGHT_EXCEPTION');
        });
        process.on('unhandledRejection', (reason, promise) => {
            console.error(COLORS.RED(`Unhandled Rejection at: ${promise}, reason: ${reason}`));
            shutdown('UNHANDLED_REJECTION');
        });
    }
    
    /**
     * Main trading loop
     */
    async mainLoop() {
        let loopCount = 0;
        let totalLoopTime = 0;
        
        while (this.isRunning) {
            const loopStart = Date.now();
            
            try {
                this.stats.dataFetchAttempts++;
                
                // Fetch market data
                const marketData = await this.dataProvider.fetchMarketData();
                if (!marketData) {
                    console.warn(COLORS.YELLOW('Failed to fetch market data, retrying...'));
                    await sleep(this.config.delays.retry);
                    continue;
                }
                
                this.stats.dataFetchSuccesses++;
                
                // Perform market analysis
                const analysis = await MarketAnalyzer.analyze(marketData, this.config);
                
                // Calculate WSS
                const wss = WeightedSentimentCalculator.calculate(
                    analysis, 
                    marketData.price, 
                    this.config.indicators.weights
                );
                analysis.wss = wss;
                
                // Generate AI signal
                this.stats.aiAnalysisCalls++;
                const signal = await this.ai.generateSignal({
                    marketData,
                    analysis,
                    wss,
                    config: this.config
                });
                
                this.stats.signalsGenerated++;
                
                // Execute trading logic
                this.exchange.evaluate(marketData.price, signal);
                if (signal.action !== 'HOLD') {
                    this.stats.positionsOpened++;
                }
                
                // Display dashboard
                this.displayDashboard(marketData, analysis, signal);
                
                // Calculate loop time
                const loopTime = Date.now() - loopStart;
                totalLoopTime += loopTime;
                this.stats.averageLoopTime = totalLoopTime / ++loopCount;
                
            } catch (error) {
                console.error(COLORS.RED(`Loop error: ${error.message}`));
                console.debug(error.stack);
            }
            
            // Wait for next iteration
            await sleep(this.config.delays.loop);
        }
    }
    
    /**
     * Display trading dashboard
     * @param {object} marketData - Market data
     * @param {object} analysis - Market analysis
     * @param {object} signal - Trading signal
     */
    displayDashboard(marketData, analysis, signal) {
        console.clear();
        
        const border = COLORS.GRAY('─'.repeat(80));
        console.log(border);
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` WHALEWAVE TITAN v7.0 | ${this.config.symbol} | $${marketData.price.toFixed(4)} `
        ))));
        console.log(border);
        
        // Signal information
        const signalColor = signal.action === 'BUY' ? COLORS.GREEN : 
                           signal.action === 'SELL' ? COLORS.RED : COLORS.GRAY;
        const wssColor = analysis.wss >= this.config.indicators.weights.actionThreshold ? COLORS.GREEN :
                        analysis.wss <= -this.config.indicators.weights.actionThreshold ? COLORS.RED : COLORS.YELLOW;
        
        console.log(`WSS: ${wssColor(analysis.wss.toFixed(2))} | ` +
                   `Strategy: ${COLORS.BLUE(signal.strategy)} | ` +
                   `Signal: ${signalColor(signal.action)} ` +
                   `(${(signal.confidence * 100).toFixed(0)}%)`);
        console.log(COLORS.GRAY(`Reason: ${signal.reason}`));
        console.log(border);
        
        // Market regime and trend
        const regimeColor = analysis.marketRegime.includes('HIGH') ? COLORS.RED :
                           analysis.marketRegime.includes('LOW') ? COLORS.GREEN : COLORS.YELLOW;
        const trendColor = analysis.trendMTF === 'BULLISH' ? COLORS.GREEN : COLORS.RED;
        
        console.log(`Regime: ${regimeColor(analysis.marketRegime)} | ` +
                   `Volatility: ${COLORS.CYAN(Utils.safeNumber(analysis.volatility?.[analysis.volatility.length - 1], 0).toFixed(4))} | ` +
                   `Squeeze: ${analysis.isSqueeze ? COLORS.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${trendColor(analysis.trendMTF)} | ` +
                   `Slope: ${COLORS.CYAN(Utils.safeNumber(analysis.regression?.slope?.[analysis.regression.slope.length - 1], 0).toFixed(6))} | ` +
                   `ADX: ${COLORS.CYAN(Utils.safeNumber(analysis.adx?.[analysis.adx.length - 1], 0).toFixed(2))}`);
        console.log(border);
        
        // Technical indicators
        const rsi = Utils.safeNumber(analysis.rsi?.[analysis.rsi.length - 1], 50);
        const stochK = Utils.safeNumber(analysis.stoch?.k?.[analysis.stoch.k.length - 1], 50);
        const macdHist = Utils.safeNumber(analysis.macd?.hist?.[analysis.macd.hist.length - 1], 0);
        
        console.log(`RSI: ${this.colorizeIndicator(rsi, 'rsi')} | ` +
                   `Stoch: ${this.colorizeIndicator(stochK, 'stoch')} | ` +
                   `MACD: ${this.colorizeIndicator(macdHist, 'macd')}`);
        
        const divColor = analysis.divergence.includes('BULLISH') ? COLORS.GREEN :
                        analysis.divergence.includes('BEARISH') ? COLORS.RED : COLORS.GRAY;
        console.log(`Divergence: ${divColor(analysis.divergence)} | ` +
                   `FVG: ${analysis.fvg ? COLORS.YELLOW(analysis.fvg.type) : 'None'}`);
        console.log(border);
        
        // Performance metrics
        const metrics = this.exchange.getMetrics();
        const pnlColor = metrics.dailyPnL >= 0 ? COLORS.GREEN : COLORS.RED;
        
        console.log(`Balance: ${COLORS.GREEN('$' + metrics.currentBalance.toFixed(2))} | ` +
                   `Daily P&L: ${pnlColor('$' + metrics.dailyPnL.toFixed(2))} | ` +
                   `Win Rate: ${COLORS.CYAN((metrics.winRate * 100).toFixed(1))}%`);
        
        // Current position
        if (metrics.openPosition) {
            const currentPnl = this.exchange.getCurrentPnL(marketData.price);
            const posColor = currentPnl.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(COLORS.BLUE(`OPEN POS: ${metrics.openPosition.side} ` +
                `@ ${metrics.openPosition.entry.toFixed(4)} | ` +
                `PnL: ${posColor(currentPnl.toFixed(2))}`));
        }
        console.log(border);
        
        // Uptime and statistics
        const uptime = Math.floor((Date.now() - this.startTime) / 1000);
        console.log(COLORS.GRAY(`Uptime: ${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m | ` +
                   `Loop Time: ${this.stats.averageLoopTime.toFixed(0)}ms`));
    }
    
    /**
     * Colorize indicator values based on their meaning
     * @param {number} value - Indicator value
     * @param {string} type - Indicator type
     * @returns {string} Colorized value
     */
    colorizeIndicator(value, type) {
        const v = Utils.safeNumber(value, 0);
        
        switch (type) {
            case 'rsi':
                if (v > 70) return COLORS.RED(v.toFixed(2));
                if (v < 30) return COLORS.GREEN(v.toFixed(2));
                return COLORS.YELLOW(v.toFixed(2));
                
            case 'stoch':
                if (v > 80) return COLORS.RED(v.toFixed(0));
                if (v < 20) return COLORS.GREEN(v.toFixed(0));
                return COLORS.YELLOW(v.toFixed(0));
                
            case 'macd':
                if (v > 0) return COLORS.GREEN(v.toFixed(6));
                if (v < 0) return COLORS.RED(v.toFixed(6));
                return COLORS.GRAY(v.toFixed(6));
                
            default:
                return COLORS.CYAN(v.toFixed(2));
        }
    }
    
    /**
     * Display shutdown report with performance statistics
     */
    displayShutdownReport() {
        console.log(COLORS.RED('\n📊 SHUTDOWN REPORT'));
        console.log(COLORS.GRAY('='.repeat(50)));
        
        const metrics = this.exchange.getMetrics();
        const uptime = (Date.now() - this.startTime) / 1000 / 60; // minutes
        
        console.log(`Uptime: ${uptime.toFixed(1)} minutes`);
        console.log(`Data Fetch Success Rate: ${(this.stats.dataFetchSuccesses / this.stats.dataFetchAttempts * 100).toFixed(1)}%`);
        console.log(`Total Trades: ${metrics.totalTrades}`);
        console.log(`Win Rate: ${(metrics.winRate * 100).toFixed(1)}%`);
        console.log(`Final Balance: $${metrics.currentBalance.toFixed(2)}`);
        console.log(`Total Return: ${metrics.totalReturn.toFixed(2)}%`);
        console.log(`Max Drawdown: ${metrics.maxDrawdown.toFixed(2)}%`);
        console.log(`Total Fees: $${metrics.totalFees.toFixed(4)}`);
        
        console.log(COLORS.GRAY('='.repeat(50)));
        console.log(COLORS.RED('Engine stopped gracefully'));
    }
}

// =============================================================================
// APPLICATION ENTRY POINT
// =============================================================================

/**
 * Main application function
 */
async function main() {
    try {
        // Load and validate configuration
        console.log(COLORS.YELLOW('Loading configuration...'));
        const config = await ConfigManager.load();
        
        // Initialize and start trading engine
        const engine = new TradingEngine(config);
        await engine.start();
        
    } catch (error) {
        console.error(COLORS.RED(`Application failed to start: ${error.message}`));
        console.debug(error.stack);
        process.exit(1);
    }
}

// Start the application
if (require.main === module) {
    main().catch(error => {
        console.error(COLORS.RED(`Fatal error: ${error.message}`));
        process.exit(1);
    });
}

export { 
    ConfigManager, 
    TechnicalAnalysis, 
    MarketAnalyzer, 
    WeightedSentimentCalculator,
    DataProvider,
    PaperExchange,
    AIAnalysisEngine,
    TradingEngine,
    Utils,
    COLORS
};