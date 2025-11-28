/**
 * ðŸŒŠ WHALEWAVE PRO - TITAN EDITION v7.1 (ENHANCED)
 * ===================================================
 * ENHANCEMENTS:
 * - Advanced weighted sentiment scoring with dynamic weights
 * - Extended technical indicators (Williams %R, CCI, MFI, ADX, CMF, OBV, VWAP)
 * - Enhanced volume analysis and order book insights
 * - Market microstructure analysis
 * - Performance optimizations and caching
 * - Multi-timeframe confirmation system
 * - Advanced risk management with volatility-adjusted sizing
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
// CONFIGURATION & VALIDATION (ENHANCED)
// =============================================================================

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
        ai: { 
            model: 'gemini-1.5-flash', 
            minConfidence: 0.75,
            rateLimitMs: 1500,
            maxRetries: 3
        },
        risk: {
            maxDrawdown: 10.0,
            dailyLossLimit: 5.0,
            maxPositions: 1,
            initialBalance: 1000.00,
            riskPercent: 2.0,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001,
            volatilityAdjustment: true,
            maxRiskPerTrade: 0.02
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
        },
        api: { timeout: 10000, retries: 3, backoffFactor: 1.5 }
    });

    /**
     * Enhanced configuration loading with validation
     */
    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        
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
        
        return this.validateEnhanced(config);
    }

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

    static validateEnhanced(config) {
        const requiredFields = ['symbol', 'intervals', 'limits', 'delays', 'ai', 'risk', 'indicators'];
        for (const field of requiredFields) {
            if (!config[field]) throw new Error(`Missing required config field: ${field}`);
        }

        // Enhanced validation
        if (config.risk.maxDrawdown < 0 || config.risk.maxDrawdown > 50) {
            throw new Error('maxDrawdown must be between 0 and 50');
        }
        
        if (config.ai.minConfidence < 0 || config.ai.minConfidence > 1) {
            throw new Error('minConfidence must be between 0 and 1');
        }

        if (config.indicators.weights.actionThreshold < 0.5) {
            throw new Error('actionThreshold should be at least 0.5 for safety');
        }

        return config;
    }
}

// =============================================================================
// UTILITIES & CONSTANTS (ENHANCED)
// =============================================================================

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
    bg: (text) => chalk.bgHex('#1C1C1E')(text)
});

/**
 * Enhanced utility functions with performance optimizations
 */
class Utils {
    static safeArray(length) {
        return new Array(Math.max(0, Math.floor(length))).fill(0);
    }

    static safeLast(arr, defaultValue = 0) {
        return Array.isArray(arr) && arr.length > 0 ? arr[arr.length - 1] : defaultValue;
    }

    static safeNumber(value, defaultValue = 0) {
        const num = typeof value === 'number' ? value : parseFloat(value);
        return Number.isFinite(num) ? num : defaultValue;
    }

    static backoffDelay(attempt, baseDelay, factor) {
        return baseDelay * Math.pow(factor, attempt);
    }

    /**
     * Calculate percentage change
     */
    static percentChange(current, previous) {
        if (previous === 0) return 0;
        return ((current - previous) / previous) * 100;
    }

    /**
     * Normalize array values to range 0-1
     */
    static normalize(values) {
        if (!Array.isArray(values) || values.length === 0) return [];
        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min;
        if (range === 0) return values.map(() => 0.5);
        return values.map(v => (v - min) / range);
    }

    /**
     * Calculate moving standard deviation
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
     * Fast percentile calculation
     */
    static percentile(values, p) {
        if (!Array.isArray(values) || values.length === 0) return 0;
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.ceil(p * sorted.length) - 1;
        return sorted[Math.max(0, Math.min(index, sorted.length - 1))];
    }
}

// =============================================================================
// ENHANCED TECHNICAL ANALYSIS LIBRARY
// =============================================================================

/**
 * Comprehensive technical analysis library with extended indicators
 */
class TechnicalAnalysis {
    // Moving averages
    static sma(data, period) {
        if (!Array.isArray(data) || data.length < period) return Utils.safeArray(data.length);
        const result = [];
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result.push(sum / period);
        }
        return Utils.safeArray(period - 1).concat(result);
    }

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

    // RSI and oscillators
    static rsi(closes, period) {
        if (!Array.isArray(closes) || closes.length < 2) return Utils.safeArray(closes.length);
        const gains = [0], losses = [0];
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

    static williamsR(highs, lows, closes, period) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const sliceLow = Math.min(...lows.slice(i - period + 1, i + 1));
            if (sliceHigh === sliceLow) {
                result[i] = -50; // Neutral value
            } else {
                result[i] = ((sliceHigh - closes[i]) / (sliceHigh - sliceLow)) * -100;
            }
        }
        return result;
    }

    static cci(highs, lows, closes, period) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
        const typicalPrices = closes.map((close, i) => (highs[i] + lows[i] + close) / 3);
        const sma = this.sma(typicalPrices, period);
        
        for (let i = period - 1; i < closes.length; i++) {
            const mean = sma[i];
            const sum = Math.abs(typicalPrices.slice(i - period + 1, i + 1)
                .reduce((sum, tp) => sum + Math.abs(tp - mean), 0)) / period;
            const divisor = sum === 0 ? 1 : sum;
            result[i] = (typicalPrices[i] - mean) / (0.015 * divisor);
        }
        return result;
    }

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

    // Money Flow Index (MFI)
    static mfi(highs, lows, closes, volumes, period) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
        const typicalPrices = closes.map((close, i) => (highs[i] + lows[i] + close) / 3);
        const moneyFlow = typicalPrices.map((tp, i) => tp * volumes[i]);
        
        for (let i = 1; i < closes.length; i++) {
            const positiveFlow = typicalPrices[i] > typicalPrices[i-1] ? moneyFlow[i] : 0;
            const negativeFlow = typicalPrices[i] < typicalPrices[i-1] ? moneyFlow[i] : 0;
            
            if (i >= period) {
                const slicePositive = moneyFlow.slice(i - period + 1, i + 1)
                    .filter((_, idx) => typicalPrices[i - period + 1 + idx] > typicalPrices[i - period + idx]);
                const sliceNegative = moneyFlow.slice(i - period + 1, i + 1)
                    .filter((_, idx) => typicalPrices[i - period + 1 + idx] < typicalPrices[i - period + idx]);
                
                const positiveSum = slicePositive.reduce((sum, val) => sum + val, 0);
                const negativeSum = sliceNegative.reduce((sum, val) => sum + val, 0);
                
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

    // Average Directional Index (ADX)
    static adx(highs, lows, closes, period = 14) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes)) {
            return { adx: Utils.safeArray(closes.length), plusDI: Utils.safeArray(closes.length), minusDI: Utils.safeArray(closes.length) };
        }
        
        const tr = [0];
        const plusDM = [0];
        const minusDM = [0];
        
        for (let i = 1; i < closes.length; i++) {
            // True Range
            const range = highs[i] - lows[i];
            const rangeFromClose = Math.abs(highs[i] - closes[i - 1]);
            const rangeFromPrevClose = Math.abs(lows[i] - closes[i - 1]);
            tr.push(Math.max(range, rangeFromClose, rangeFromPrevClose));
            
            // Directional Movement
            const upMove = highs[i] - highs[i - 1];
            const downMove = lows[i - 1] - lows[i];
            
            plusDM.push(upMove > downMove && upMove > 0 ? upMove : 0);
            minusDM.push(downMove > upMove && downMove > 0 ? downMove : 0);
        }
        
        const atr = this.wilders(tr, period);
        const plusDI = Utils.safeArray(closes.length);
        const minusDI = Utils.safeArray(closes.length);
        const adx = Utils.safeArray(closes.length);
        
        for (let i = period - 1; i < closes.length; i++) {
            const smoothedPlusDM = this.wilders(plusDM, period)[i];
            const smoothedMinusDM = this.wilders(minusDM, period)[i];
            
            plusDI[i] = atr[i] === 0 ? 0 : (smoothedPlusDM / atr[i]) * 100;
            minusDI[i] = atr[i] === 0 ? 0 : (smoothedMinusDM / atr[i]) * 100;
            
            if (i >= period * 2 - 1) {
                const dx = Math.abs(plusDI[i] - minusDI[i]) / (plusDI[i] + minusDI[i]) * 100;
                adx[i] = dx; // Simplified ADX calculation
            }
        }
        
        return { adx, plusDI, minusDI };
    }

    // MACD
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

    // Volume-based indicators
    static onBalanceVolume(closes, volumes) {
        if (!Array.isArray(closes) || !Array.isArray(volumes)) return Utils.safeArray(closes.length);
        const result = Utils.safeArray(closes.length);
        result[0] = volumes[0];
        
        for (let i = 1; i < closes.length; i++) {
            result[i] = result[i - 1] + (closes[i] > closes[i - 1] ? volumes[i] : 
                       closes[i] < closes[i - 1] ? -volumes[i] : 0);
        }
        return result;
    }

    static accumulationDistributionLine(highs, lows, closes, volumes) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
        
        for (let i = 0; i < closes.length; i++) {
            const range = highs[i] - lows[i];
            const multiplier = range === 0 ? 0 : ((closes[i] - lows[i]) - (highs[i] - closes[i])) / range;
            const moneyFlowVolume = multiplier * volumes[i];
            result[i] = i > 0 ? result[i - 1] + moneyFlowVolume : moneyFlowVolume;
        }
        return result;
    }

    static chaikinMoneyFlow(highs, lows, closes, volumes, period) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
        
        for (let i = period - 1; i < closes.length; i++) {
            let sum = 0;
            let volumeSum = 0;
            
            for (let j = i - period + 1; j <= i; j++) {
                const range = highs[j] - lows[j];
                if (range !== 0) {
                    const multiplier = ((closes[j] - lows[j]) - (highs[j] - closes[j])) / range;
                    const moneyFlowVolume = multiplier * volumes[j];
                    sum += moneyFlowVolume;
                    volumeSum += volumes[j];
                }
            }
            
            result[i] = volumeSum === 0 ? 0 : sum / volumeSum;
        }
        return result;
    }

    // VWAP (Volume Weighted Average Price)
    static vwap(highs, lows, closes, volumes) {
        if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes)) {
            return Utils.safeArray(closes.length);
        }
        const result = Utils.safeArray(closes.length);
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

    // Other indicators
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

    static bollingerBands(closes, period, stdDev) {
        if (!Array.isArray(closes) || closes.length < period) {
            return { upper: Utils.safeArray(closes.length), middle: Utils.safeArray(closes.length), lower: Utils.safeArray(closes.length) };
        }
        const middle = this.sma(closes, period);
        const upper = [], lower = [];
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) {
                upper.push(0); lower.push(0);
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
}

// =============================================================================
// ENHANCED MARKET ANALYSIS ENGINE
// =============================================================================

/**
 * Enhanced market analyzer with volume and order book analysis
 */
class MarketAnalyzer {
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
                rsi, stoch, macd, atr, bb, adx,
                williamsR, cci, mfi, obv, adLine, cmf, vwap,
                linearReg, fvg, divergence
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
                    config.indicators.periods.rsi,
                    config.indicators.periods.stoch,
                    9
                ),
                TechnicalAnalysis.atr(highs, lows, closes, config.indicators.periods.atr),
                TechnicalAnalysis.bollingerBands(
                    closes, 
                    config.indicators.periods.bb, 
                    config.indicators.settings.bbStd
                ),
                TechnicalAnalysis.adx(highs, lows, closes, config.indicators.periods.adx),
                TechnicalAnalysis.williamsR(highs, lows, closes, config.indicators.periods.williams),
                TechnicalAnalysis.cci(highs, lows, closes, config.indicators.periods.cci),
                TechnicalAnalysis.mfi(highs, lows, closes, volumes, config.indicators.periods.mfi),
                TechnicalAnalysis.onBalanceVolume(closes, volumes),
                TechnicalAnalysis.accumulationDistributionLine(highs, lows, closes, volumes),
                TechnicalAnalysis.chaikinMoneyFlow(highs, lows, closes, volumes, config.indicators.periods.cmf),
                TechnicalAnalysis.vwap(highs, lows, closes, volumes),
                TechnicalAnalysis.sma(mtfCloses, 20), // Linear regression simplified
                TechnicalAnalysis.findFairValueGap(candles),
                TechnicalAnalysis.detectDivergence(closes, 
                    TechnicalAnalysis.rsi(closes, config.indicators.periods.rsi))
            ]);
            
            // Additional calculations
            const last = closes.length - 1;
            const trendMTF = mtfCloses[last] > Utils.safeLast(mtfCloses.slice(0, -1), mtfCloses[last]) ? 'BULLISH' : 'BEARISH';
            
            // Enhanced market structure analysis
            const volatility = this.calculateVolatility(closes);
            const avgVolatility = TechnicalAnalysis.sma(volatility, 50);
            const marketRegime = this.determineMarketRegime(
                Utils.safeLast(volatility, 0),
                Utils.safeLast(avgVolatility, 1)
            );
            
            // Volume analysis
            const volumeAnalysis = this.analyzeVolume(volumes, closes, config.volumeAnalysis);
            const volumeProfile = this.createVolumeProfile(data.price, volumes, highs, lows);
            
            // Enhanced order book analysis
            const orderBookAnalysis = this.analyzeOrderBook(
                data.bids, data.asks, data.price, atr[last], config.orderbook
            );
            
            // Support/Resistance levels
            const srLevels = this.calculateSupportResistance(
                data.bids, data.asks, data.price, config.orderbook.srLevels
            );
            
            // Liquidity zones
            const liquidityZones = this.identifyLiquidityZones(
                data.bids, data.asks, data.price, 
                Utils.safeLast(atr, 1), config.orderbook.wallThreshold
            );
            
            return {
                // Core data
                closes, highs, lows, volumes,
                
                // All indicators
                rsi, stoch, macd, atr, bollinger: bb, adx,
                williamsR, cci, mfi, obv, adLine, cmf, vwap,
                regression: { slope: linearReg }, // Simplified
                fvg, divergence, volatility, avgVolatility,
                
                // Market structure
                trendMTF, marketRegime, supportResistance: srLevels,
                liquidity: liquidityZones,
                
                // Volume and order book analysis
                volumeAnalysis, volumeProfile, orderBookAnalysis,
                
                // Additional derived data
                isSqueeze: this.detectSqueeze(bb),
                timestamp: Date.now()
            };
            
        } catch (error) {
            throw new Error(`Market analysis failed: ${error.message}`);
        }
    }
    
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
            volatility[i] = Math.sqrt(variance) * Math.sqrt(252);
        }
        return volatility;
    }
    
    static determineMarketRegime(currentVol, avgVol) {
        if (avgVol <= 0) return 'NORMAL';
        const ratio = currentVol / avgVol;
        if (ratio > 1.5) return 'HIGH_VOLATILITY';
        if (ratio < 0.5) return 'LOW_VOLATILITY';
        return 'NORMAL_VOLATILITY';
    }
    
    /**
     * Enhanced volume analysis
     */
    static analyzeVolume(volumes, closes, config) {
        const analysis = {
            volumeSMA: TechnicalAnalysis.sma(volumes, 20),
            volumeRatio: [],
            accumulation: [],
            distribution: [],
            flow: 'NEUTRAL'
        };
        
        const volSMA = analysis.volumeSMA;
        for (let i = 0; i < volumes.length; i++) {
            const ratio = volSMA[i] > 0 ? volumes[i] / volSMA[i] : 1;
            analysis.volumeRatio.push(ratio);
            
            // Accumulation/Distribution analysis
            const priceChange = i > 0 ? closes[i] - closes[i-1] : 0;
            const accDist = priceChange > 0 ? 'ACCUMULATION' : 
                           priceChange < 0 ? 'DISTRIBUTION' : 'NEUTRAL';
            analysis.accumulation.push(accDist);
        }
        
        // Determine overall flow
        const recentVolume = analysis.volumeRatio.slice(-5).reduce((sum, r) => sum + r, 0) / 5;
        analysis.flow = recentVolume > 1.2 ? 'STRONG_BULLISH' :
                       recentVolume < 0.8 ? 'STRONG_BEARISH' :
                       recentVolume > 1.0 ? 'BULLISH' :
                       recentVolume < 1.0 ? 'BEARISH' : 'NEUTRAL';
        
        return analysis;
    }
    
    /**
     * Create volume profile
     */
    static createVolumeProfile(currentPrice, volumes, highs, lows) {
        if (!Array.isArray(volumes) || volumes.length === 0) {
            return { price: currentPrice, volume: 0, profile: [] };
        }
        
        const totalVolume = volumes.reduce((sum, v) => sum + v, 0);
        const avgPrice = volumes.reduce((sum, v, i) => sum + (v * (highs[i] + lows[i]) / 2), 0) / totalVolume;
        
        return {
            price: currentPrice,
            volume: totalVolume,
            profile: [
                { level: 'HIGH_VP', price: avgPrice, percentage: 100 },
                { level: 'LOW_VP', price: (Math.min(...highs) + Math.max(...lows)) / 2, percentage: 0 }
            ]
        };
    }
    
    /**
     * Enhanced order book analysis
     */
    static analyzeOrderBook(bids, asks, currentPrice, atr, config) {
        if (!Array.isArray(bids) || !Array.isArray(asks)) {
            return { imbalance: 0, depth: 0, flow: 'NEUTRAL', liquidity: 0 };
        }
        
        const totalBidVolume = bids.reduce((sum, b) => sum + b.q, 0);
        const totalAskVolume = asks.reduce((sum, a) => sum + a.q, 0);
        const totalVolume = totalBidVolume + totalAskVolume;
        
        const imbalance = totalVolume > 0 ? (totalBidVolume - totalAskVolume) / totalVolume : 0;
        
        // Calculate depth (ATR multiples)
        const atrMultiplier = atr > 0 ? Math.abs(currentPrice - currentPrice) / atr : 1;
        const depth = Math.min(atrMultiplier, 10); // Cap at 10x ATR
        
        // Determine order flow
        const flow = Math.abs(imbalance) > config.imbalanceThreshold ? 
                    (imbalance > 0 ? 'STRONG_BUY' : 'STRONG_SELL') :
                    imbalance > 0 ? 'BUY' :
                    imbalance < 0 ? 'SELL' : 'NEUTRAL';
        
        // Calculate liquidity score
        const liquidity = totalVolume > 1000000 ? 1.0 : 
                         totalVolume > 500000 ? 0.8 : 
                         totalVolume > 100000 ? 0.6 : 0.3;
        
        return { imbalance, depth, flow, liquidity };
    }
    
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
        const avgBidVol = bids.reduce((sum, b) => sum + b.q, 0) / bids.length;
        const avgAskVol = asks.reduce((sum, a) => sum + a.q, 0) / asks.length;
        
        for (const price of uniquePrices) {
            const bidVol = bids.filter(b => b.p === price).reduce((sum, b) => sum + b.q, 0);
            const askVol = asks.filter(a => a.p === price).reduce((sum, a) => sum + a.q, 0);
            
            if (bidVol > avgBidVol * 2) {
                potentialLevels.push({ price, type: 'SUPPORT', strength: bidVol });
            } else if (askVol > avgAskVol * 2) {
                potentialLevels.push({ price, type: 'RESISTANCE', strength: askVol });
            }
        }
        
        const sorted = potentialLevels.sort((a, b) => 
            Math.abs(a.price - currentPrice) - Math.abs(b.price - currentPrice)
        );
        
        const support = sorted
            .filter(p => p.type === 'SUPPORT' && p.price < currentPrice)
            .slice(0, maxLevels)
            .map(p => ({ price: p.price, strength: p.strength }));
            
        const resistance = sorted
            .filter(p => p.type === 'RESISTANCE' && p.price > currentPrice)
            .slice(0, maxLevels)
            .map(p => ({ price: p.price, strength: p.strength }));
        
        return { support, resistance };
    }
    
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
                volume: b.q,
                distance: Math.abs(b.p - currentPrice),
                proximity: Math.abs(b.p - currentPrice) < atr ? 'HIGH' : 'LOW'
            }));
            
        const sellWalls = asks
            .filter(a => a.q > avgAskVol * threshold)
            .map(a => ({
                price: a.p,
                volume: a.q,
                distance: Math.abs(a.p - currentPrice),
                proximity: Math.abs(a.p - currentPrice) < atr ? 'HIGH' : 'LOW'
            }));
        
        return { buyWalls, sellWalls };
    }
    
    static detectSqueeze(bb) {
        if (!bb || !bb.upper || !bb.lower) return false;
        const last = bb.upper.length - 1;
        if (last < 1) return false;
        const currentWidth = bb.upper[last] - bb.lower[last];
        const prevWidth = bb.upper[last - 1] - bb.lower[last - 1];
        return currentWidth < prevWidth * 0.8;
    }
    
    static findFairValueGap(candles) {
        if (!Array.isArray(candles) || candles.length < 5) return null;
        const len = candles.length;
        const c1 = candles[len - 4];
        const c2 = candles[len - 3];
        const c3 = candles[len - 2];
        
        if (c2.c > c2.o && c3.l > c1.h) {
            return {
                type: 'BULLISH',
                top: c3.l,
                bottom: c1.h,
                price: (c3.l + c1.h) / 2
            };
        }
        
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
    
    static detectDivergence(closes, rsi, period = 5) {
        if (!Array.isArray(closes) || !Array.isArray(rsi) || closes.length < period * 2) {
            return 'NONE';
        }
        
        const len = closes.length;
        const currentPriceHigh = Math.max(...closes.slice(len - period, len));
        const currentRsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period));
        const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        
        if (currentPriceHigh > prevPriceHigh && currentRsiHigh < prevRsiHigh) {
            return 'BEARISH_REGULAR';
        }
        
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
// ENHANCED WEIGHTED SENTIMENT CALCULATOR
// =============================================================================

/**
 * Enhanced weighted sentiment calculator with dynamic weights and confidence intervals
 */
class EnhancedWeightedSentimentCalculator {
    /**
     * Calculate enhanced WSS with multi-component analysis
     */
    static calculate(analysis, currentPrice, weights, config) {
        if (!analysis || !analysis.closes) {
            console.warn('Invalid analysis data for WSS calculation');
            return { score: 0, confidence: 0, components: {} };
        }
        
        const last = analysis.closes.length - 1;
        let totalScore = 0;
        let totalWeight = 0;
        const components = {};
        
        try {
            // 1. TREND COMPONENT (25% weight)
            const trendScore = this.calculateTrendComponent(analysis, last, weights, config);
            totalScore += trendScore.score * trendScore.weight;
            totalWeight += trendScore.weight;
            components.trend = trendScore;
            
            // 2. MOMENTUM COMPONENT (25% weight)
            const momentumScore = this.calculateMomentumComponent(analysis, last, weights);
            totalScore += momentumScore.score * momentumScore.weight;
            totalWeight += momentumScore.weight;
            components.momentum = momentumScore;
            
            // 3. VOLUME COMPONENT (20% weight)
            const volumeScore = this.calculateVolumeComponent(analysis, weights);
            totalScore += volumeScore.score * volumeScore.weight;
            totalWeight += volumeScore.weight;
            components.volume = volumeScore;
            
            // 4. ORDER FLOW COMPONENT (15% weight)
            const orderFlowScore = this.calculateOrderFlowComponent(analysis, weights);
            totalScore += orderFlowScore.score * orderFlowScore.weight;
            totalWeight += orderFlowScore.weight;
            components.orderFlow = orderFlowScore;
            
            // 5. STRUCTURE COMPONENT (15% weight)
            const structureScore = this.calculateStructureComponent(analysis, currentPrice, last, weights);
            totalScore += structureScore.score * structureScore.weight;
            totalWeight += structureScore.weight;
            components.structure = structureScore;
            
            // Calculate weighted average
            const weightedScore = totalWeight > 0 ? totalScore / totalWeight : 0;
            
            // Calculate confidence based on component agreement
            const confidence = this.calculateConfidence(components, analysis);
            
            return {
                score: Math.round(weightedScore * 100) / 100,
                confidence: Math.round(confidence * 100) / 100,
                components,
                timestamp: Date.now()
            };
            
        } catch (error) {
            console.error(`Enhanced WSS calculation error: ${error.message}`);
            return { score: 0, confidence: 0, components: {} };
        }
    }
    
    /**
     * Calculate trend component
     */
    static calculateTrendComponent(analysis, last, weights, config) {
        let score = 0;
        
        // Multi-timeframe trend alignment
        if (analysis.trendMTF === 'BULLISH') {
            score += weights.trendMTF;
        } else if (analysis.trendMTF === 'BEARISH') {
            score -= weights.trendMTF;
        }
        
        // Enhanced regression analysis
        const slope = Utils.safeNumber(analysis.regression?.slope?.[last], 0);
        const r2 = Utils.safeNumber(analysis.regression?.r2?.[last], 0);
        
        if (slope > 0 && r2 > 0.3) {
            score += weights.trendScalp * r2;
        } else if (slope < 0 && r2 > 0.3) {
            score -= weights.trendScalp * r2;
        }
        
        // Volume-weighted trend confirmation
        const volumeAnalysis = analysis.volumeAnalysis;
        if (volumeAnalysis && volumeAnalysis.flow.includes('BULLISH')) {
            score *= 1.1; // 10% boost
        } else if (volumeAnalysis && volumeAnalysis.flow.includes('BEARISH')) {
            score *= 0.9; // 10% reduction
        }
        
        return { score, weight: 0.25, breakdown: { mtf: analysis.trendMTF, slope: slope, r2: r2 } };
    }
    
    /**
     * Calculate momentum component with enhanced oscillators
     */
    static calculateMomentumComponent(analysis, last, weights) {
        let score = 0;
        const breakdown = {};
        
        // RSI momentum (normalized)
        const rsi = Utils.safeNumber(analysis.rsi?.[last], 50);
        if (rsi < 30) {
            const oversoldStrength = (30 - rsi) / 30;
            score += oversoldStrength * 0.6;
            breakdown.rsi = `Oversold (${rsi.toFixed(1)})`;
        } else if (rsi > 70) {
            const overboughtStrength = (rsi - 70) / 30;
            score -= overboughtStrength * 0.6;
            breakdown.rsi = `Overbought (${rsi.toFixed(1)})`;
        } else {
            breakdown.rsi = `Neutral (${rsi.toFixed(1)})`;
        }
        
        // Williams %R
        const williams = Utils.safeNumber(analysis.williamsR?.[last], -50);
        if (williams < -80) {
            score += 0.4;
            breakdown.williams = 'Strong Oversold';
        } else if (williams > -20) {
            score -= 0.4;
            breakdown.williams = 'Strong Overbought';
        } else {
            breakdown.williams = `Neutral (${williams.toFixed(1)})`;
        }
        
        // CCI
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
        
        // MACD histogram
        const macdHist = Utils.safeNumber(analysis.macd?.hist?.[last], 0);
        if (macdHist > 0) {
            score += Math.min(macdHist * 100, 0.4);
            breakdown.macd = `Bullish (${macdHist.toFixed(6)})`;
        } else {
            score += Math.max(macdHist * 100, -0.4);
            breakdown.macd = `Bearish (${macdHist.toFixed(6)})`;
        }
        
        // ADX strength
        const adx = Utils.safeNumber(analysis.adx?.adx?.[last], 0);
        if (adx > 25) {
            const strengthMultiplier = Math.min(adx / 50, 1.5);
            score *= strengthMultiplier;
            breakdown.adx = `Strong Trend (${adx.toFixed(1)})`;
        } else {
            breakdown.adx = `Weak Trend (${adx.toFixed(1)})`;
        }
        
        return { score, weight: 0.25, breakdown };
    }
    
    /**
     * Calculate volume component
     */
    static calculateVolumeComponent(analysis, weights) {
        let score = 0;
        const breakdown = {};
        
        if (!analysis.volumeAnalysis) {
            return { score: 0, weight: 0.20, breakdown: { error: 'No volume analysis' } };
        }
        
        const { volumeAnalysis } = analysis;
        
        // Volume flow direction
        const flow = volumeAnalysis.flow;
        if (flow.includes('STRONG_BULLISH')) {
            score += weights.volumeFlow;
            breakdown.flow = 'Strong Bullish Volume';
        } else if (flow.includes('BULLISH')) {
            score += weights.volumeFlow * 0.6;
            breakdown.flow = 'Bullish Volume';
        } else if (flow.includes('STRONG_BEARISH')) {
            score -= weights.volumeFlow;
            breakdown.flow = 'Strong Bearish Volume';
        } else if (flow.includes('BEARISH')) {
            score -= weights.volumeFlow * 0.6;
            breakdown.flow = 'Bearish Volume';
        } else {
            breakdown.flow = 'Neutral Volume';
        }
        
        // Volume surge detection
        const recentVolumeRatio = Utils.safeLast(volumeAnalysis.volumeRatio, 1);
        if (recentVolumeRatio > 2.0) {
            score += weights.volumeFlow * 0.3;
            breakdown.volumeSurge = 'Significant volume surge detected';
        } else if (recentVolumeRatio > 1.5) {
            score += weights.volumeFlow * 0.2;
            breakdown.volumeSurge = 'Moderate volume increase';
        }
        
        return { score, weight: 0.20, breakdown };
    }
    
    /**
     * Calculate order flow component
     */
    static calculateOrderFlowComponent(analysis, weights) {
        let score = 0;
        const breakdown = {};
        
        if (!analysis.orderBookAnalysis) {
            return { score: 0, weight: 0.15, breakdown: { error: 'No order book analysis' } };
        }
        
        const { orderBookAnalysis } = analysis;
        
        // Imbalance analysis
        const imbalance = orderBookAnalysis.imbalance;
        const imbalanceStrength = Math.min(Math.abs(imbalance), 1.0);
        
        if (imbalance > 0.3) {
            score += weights.orderFlow * imbalanceStrength;
            breakdown.imbalance = `Strong Buy Orders (${(imbalance * 100).toFixed(1)}%)`;
        } else if (imbalance < -0.3) {
            score -= weights.orderFlow * imbalanceStrength;
            breakdown.imbalance = `Strong Sell Orders (${(Math.abs(imbalance) * 100).toFixed(1)}%)`;
        } else {
            breakdown.imbalance = `Balanced (${(imbalance * 100).toFixed(1)}%)`;
        }
        
        // Liquidity quality
        const liquidity = orderBookAnalysis.liquidity;
        if (liquidity > 0.8) {
            score *= 1.1; // High liquidity bonus
            breakdown.liquidity = 'High Quality';
        } else if (liquidity < 0.4) {
            score *= 0.9; // Low liquidity penalty
            breakdown.liquidity = 'Low Quality';
        } else {
            breakdown.liquidity = 'Moderate';
        }
        
        return { score, weight: 0.15, breakdown };
    }
    
    /**
     * Calculate structure component
     */
    static calculateStructureComponent(analysis, currentPrice, last, weights) {
        let score = 0;
        const breakdown = {};
        
        // Squeeze indicator
        if (analysis.isSqueeze) {
            const squeezeBonus = analysis.trendMTF === 'BULLISH' ? 
                weights.squeeze : -weights.squeeze;
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
            if (fvg.type === 'BULLISH' && 
                currentPrice > fvg.bottom && currentPrice < fvg.top) {
                score += weights.liquidity;
                breakdown.fvg = 'Within Bullish FVG';
            } else if (fvg.type === 'BEARISH' && 
                       currentPrice < fvg.top && currentPrice > fvg.bottom) {
                score -= weights.liquidity;
                breakdown.fvg = 'Within Bearish FVG';
            } else {
                breakdown.fvg = `${fvg.type} (Outside Range)`;
            }
        } else {
            breakdown.fvg = 'None';
        }
        
        // Support/Resistance levels
        if (analysis.supportResistance) {
            const { support, resistance } = analysis.supportResistance;
            const closestSupport = support.length > 0 ? 
                Math.min(...support.map(s => s.price)) : 0;
            const closestResistance = resistance.length > 0 ? 
                Math.max(...resistance.map(r => r.price)) : 0;
            
            const supportDistance = currentPrice - closestSupport;
            const resistanceDistance = closestResistance - currentPrice;
            
            // Price proximity to levels
            if (supportDistance < currentPrice * 0.01) { // Within 1%
                score += weights.liquidity * 0.3;
                breakdown.srProximity = 'Near Support';
            } else if (resistanceDistance < currentPrice * 0.01) {
                score -= weights.liquidity * 0.3;
                breakdown.srProximity = 'Near Resistance';
            } else {
                breakdown.srProximity = 'Neutral';
            }
        }
        
        return { score, weight: 0.15, breakdown };
    }
    
    /**
     * Calculate confidence based on component agreement
     */
    static calculateConfidence(components, analysis) {
        let agreement = 0;
        let totalComponents = 0;
        
        // Check direction agreement
        const directions = [];
        Object.values(components).forEach(comp => {
            if (comp.score > 0.5) directions.push(1);
            else if (comp.score < -0.5) directions.push(-1);
            else directions.push(0);
            totalComponents++;
        });
        
        // Calculate agreement percentage
        const positiveCount = directions.filter(d => d > 0).length;
        const negativeCount = directions.filter(d => d < 0).length;
        
        if (positiveCount > negativeCount) {
            agreement = positiveCount / totalComponents;
        } else if (negativeCount > positiveCount) {
            agreement = negativeCount / totalComponents;
        } else {
            agreement = 0.3; // Neutral confidence when mixed signals
        }
        
        // Boost confidence with volume confirmation
        if (analysis.volumeAnalysis && analysis.volumeAnalysis.flow.includes('BULLISH')) {
            agreement = Math.min(agreement * 1.2, 1.0);
        } else if (analysis.volumeAnalysis && analysis.volumeAnalysis.flow.includes('BEARISH')) {
            agreement = Math.min(agreement * 1.2, 1.0);
        }
        
        // Boost with strong order book imbalance
        if (analysis.orderBookAnalysis && Math.abs(analysis.orderBookAnalysis.imbalance) > 0.4) {
            agreement = Math.min(agreement * 1.1, 1.0);
        }
        
        return agreement;
    }
}

// =============================================================================
// DATA PROVIDER (ENHANCED)
// =============================================================================

class DataProvider {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        
        this.config = config;
        this.api = axios.create({
            baseURL: 'https://api.bybit.com/v5/market',
            timeout: config.api.timeout,
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': 'WhaleWave-Titan-Enhanced/7.1'
            }
        });
        
        // Cache for performance
        this.cache = new Map();
        this.cacheTimeout = 5000; // 5 seconds
        
        // Request interceptors
        this.api.interceptors.request.use(
            (config) => {
                console.debug(`ðŸ”„ API Request: ${config.method?.toUpperCase()} ${config.url}`);
                return config;
            },
            (error) => Promise.reject(error)
        );
        
        this.api.interceptors.response.use(
            (response) => response,
            (error) => {
                console.error(`âŒ API Error: ${error.message}`);
                return Promise.reject(error);
            }
        );
    }
    
    async fetchWithRetry(endpoint, params, maxRetries = this.config.api.retries) {
        const cacheKey = `${endpoint}:${JSON.stringify(params)}`;
        const cached = this.cache.get(cacheKey);
        
        if (cached && (Date.now() - cached.timestamp) < this.cacheTimeout) {
            return cached.data;
        }
        
        let lastError;
        
        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                const response = await this.api.get(endpoint, { params });
                
                if (!response.data) {
                    throw new Error('Empty response from API');
                }
                
                if (response.data.retCode !== undefined && response.data.retCode !== 0) {
                    throw new Error(`API Error ${response.data.retCode}: ${response.data.retMsg}`);
                }
                
                // Cache the response
                this.cache.set(cacheKey, {
                    data: response.data,
                    timestamp: Date.now()
                });
                
                return response.data;
                
            } catch (error) {
                lastError = error;
                
                if (attempt === maxRetries) {
                    console.error(`âŒ Failed to fetch ${endpoint} after ${maxRetries + 1} attempts`);
                    break;
                }
                
                const delay = Utils.backoffDelay(
                    attempt, 
                    this.config.delays.retry, 
                    this.config.api.backoffFactor
                );
                console.warn(`âš ï¸ Retry ${attempt + 1}/${maxRetries} for ${endpoint} in ${delay}ms`);
                await sleep(delay);
            }
        }
        
        throw lastError;
    }
    
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
                }),
                this.fetchWithRetry('/kline', {
                    category: 'linear',
                    symbol: this.config.symbol,
                    interval: this.config.intervals.weekly,
                    limit: 2
                })
            ];
            
            const [ticker, kline, klineMTF, orderbook, daily, weekly] = await Promise.all(requests);
            
            this.validateMarketData(ticker, kline, klineMTF, orderbook, daily, weekly);
            
            return this.parseMarketData(ticker, kline, klineMTF, orderbook, daily, weekly);
            
        } catch (error) {
            console.warn(COLORS.ORANGE(`âš ï¸ Data fetch failed: ${error.message}`));
            return null;
        }
    }
    
    validateMarketData(ticker, kline, klineMTF, orderbook, daily, weekly) {
        const validations = [
            { name: 'ticker', data: ticker?.result?.list?.[0] },
            { name: 'kline', data: kline?.result?.list },
            { name: 'klineMTF', data: klineMTF?.result?.list },
            { name: 'orderbook bids', data: orderbook?.result?.b },
            { name: 'orderbook asks', data: orderbook?.result?.a },
            { name: 'daily', data: daily?.result?.list?.[1] },
            { name: 'weekly', data: weekly?.result?.list?.[1] }
        ];
        
        const missing = validations.filter(v => !v.data).map(v => v.name);
        if (missing.length > 0) {
            throw new Error(`Missing data: ${missing.join(', ')}`);
        }
    }
    
    parseMarketData(ticker, kline, klineMTF, orderbook, daily, weekly) {
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
            daily: parseCandles([daily.result.list[1]])[0],
            weekly: parseCandles([weekly.result.list[1]])[0],
            bids: orderbook.result.b.map(x => ({
                p: parseFloat(x[0]),
                q: parseFloat(x[1])
            })),
            asks: orderbook.result.a.map(x => ({
                p: parseFloat(x[0]),
                q: parseFloat(x[1])
            })),
            timestamp: Date.now()
        };
    }
}

// =============================================================================
// ENHANCED PAPER EXCHANGE
// =============================================================================

class EnhancedPaperExchange {
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
        
        // Enhanced performance metrics
        this.metrics = {
            totalTrades: 0,
            winningTrades: 0,
            losingTrades: 0,
            totalFees: new Decimal(0),
            maxDrawdown: new Decimal(0),
            winRate: 0,
            profitFactor: 0,
            sharpeRatio: 0,
            sortinoRatio: 0,
            maxConsecutiveLosses: 0,
            avgWin: new Decimal(0),
            avgLoss: new Decimal(0),
            avgTradeDuration: 0
        };
        
        // Risk tracking
        this.consecutiveLosses = 0;
        this.tradeDurations = [];
    }
    
    resetDailyPnL() {
        const now = new Date();
        if (now.getDate() !== this.lastDailyReset.getDate()) {
            this.dailyPnL = new Decimal(0);
            this.lastDailyReset = now;
            console.log(COLORS.GRAY('ðŸ“… Daily P&L reset'));
        }
    }
    
    canTrade() {
        this.resetDailyPnL();
        
        const drawdown = this.startBalance.isZero() ? 
            new Decimal(0) : 
            this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
            
        if (drawdown.gt(this.config.maxDrawdown)) {
            console.error(COLORS.RED(`ðŸš¨ MAX DRAWDOWN HIT (${drawdown.toFixed(2)}%)`));
            return false;
        }
        
        const dailyLossPct = this.startBalance.isZero() ? 
            new Decimal(0) : 
            this.dailyPnL.div(this.startBalance).mul(100);
            
        if (dailyLossPct.lt(-this.config.dailyLossLimit)) {
            console.error(COLORS.RED(`ðŸš¨ DAILY LOSS LIMIT HIT (${dailyLossPct.toFixed(2)}%)`));
            return false;
        }
        
        // Volatility-adjusted position sizing
        if (this.config.volatilityAdjustment) {
            const volatilityFactor = this.calculateVolatilityFactor();
            if (volatilityFactor > 2.0) {
                console.warn(COLORS.YELLOW(`âš ï¸ High volatility detected (${volatilityFactor.toFixed(2)}x), reducing position size`));
                return false;
            }
        }
        
        return true;
    }
    
    calculateVolatilityFactor() {
        // Simplified volatility calculation based on recent trades
        if (this.tradeHistory.length < 5) return 1.0;
        
        const recentReturns = this.tradeHistory
            .slice(-10)
            .map(trade => trade.pnl.div(this.startBalance).toNumber());
        
        if (recentReturns.length === 0) return 1.0;
        
        const mean = recentReturns.reduce((sum, r) => sum + r, 0) / recentReturns.length;
        const variance = recentReturns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / recentReturns.length;
        const volatility = Math.sqrt(variance);
        
        return Math.min(volatility * 100, 5.0); // Cap at 5x
    }
    
    evaluate(price, signal) {
        if (!this.canTrade()) {
            if (this.position) {
                this.closePosition(new Decimal(price), 'RISK_MANAGEMENT');
            }
            return;
        }
        
        const priceDecimal = new Decimal(price);
        
        if (this.position) {
            const shouldClose = this.shouldClosePosition(priceDecimal, signal);
            if (shouldClose.shouldClose) {
                this.closePosition(priceDecimal, shouldClose.reason);
            }
        }
        
        // Enhanced signal validation
        if (!this.position && signal.action !== 'HOLD' && 
            signal.confidence >= this.config.minConfidence &&
            this.validateSignalQuality(signal)) {
            this.openPosition(priceDecimal, signal);
        }
    }
    
    validateSignalQuality(signal) {
        // Additional signal quality checks
        if (!signal.strategy || signal.strategy === 'AI_ERROR') {
            return false;
        }
        
        // Risk-reward ratio validation
        if (signal.action !== 'HOLD') {
            const risk = Math.abs(signal.entry - signal.stopLoss);
            const reward = Math.abs(signal.takeProfit - signal.entry);
            const rrRatio = reward / risk;
            
            if (rrRatio < 1.2) {
                console.warn(COLORS.YELLOW(`âš ï¸ Poor risk-reward ratio: ${rrRatio.toFixed(2)}`));
                return false;
            }
        }
        
        return true;
    }
    
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
                this.consecutiveLosses++;
            } else if (price.gte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
                this.consecutiveLosses = 0;
            }
        } else {
            if (price.gte(position.stopLoss)) {
                shouldClose = true;
                reason = 'STOP_LOSS';
                this.consecutiveLosses++;
            } else if (price.lte(position.takeProfit)) {
                shouldClose = true;
                reason = 'TAKE_PROFIT';
                this.consecutiveLosses = 0;
            }
        }
        
        // Signal change close
        if (!shouldClose && signal.action !== 'HOLD' && signal.action !== position.side) {
            shouldClose = true;
            reason = `SIGNAL_CHANGE_${signal.action}`;
        }
        
        // Consecutive losses limit
        if (this.consecutiveLosses >= 3) {
            shouldClose = true;
            reason = 'CONSECUTIVE_LOSSES';
            this.consecutiveLosses = 0;
        }
        
        return { shouldClose, reason };
    }
    
    openPosition(price, signal) {
        try {
            const entry = new Decimal(signal.entry);
            const stopLoss = new Decimal(signal.stopLoss);
            const takeProfit = new Decimal(signal.takeProfit);
            
            const distance = entry.sub(stopLoss).abs();
            if (distance.isZero()) {
                console.warn(COLORS.YELLOW('Invalid entry/stop loss: distance is zero'));
                return;
            }
            
            // Enhanced position sizing with volatility adjustment
            const baseRiskAmount = this.balance.mul(this.config.riskPercent / 100);
            const volatilityFactor = this.calculateVolatilityFactor();
            const adjustedRiskAmount = baseRiskAmount.div(volatilityFactor);
            let quantity = adjustedRiskAmount.div(distance);
            
            // Apply leverage cap
            const maxQuantity = this.balance
                .mul(this.config.leverageCap)
                .div(price);
                
            if (quantity.gt(maxQuantity)) {
                quantity = maxQuantity;
                console.warn(COLORS.YELLOW('Position size capped by leverage'));
            }
            
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
            
            if (this.balance.lt(fee)) {
                console.warn(COLORS.YELLOW('Insufficient balance for fees'));
                return;
            }
            
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
                confidence: signal.confidence
            };
            
            this.metrics.totalFees = this.metrics.totalFees.add(fee);
            
            console.log(COLORS.GREEN(
                `ðŸ“ˆ OPEN ${signal.action} [${signal.strategy}] ` +
                `@ ${executionPrice.toFixed(4)} | ` +
                `Size: ${quantity.toFixed(4)} | ` +
                `SL: ${stopLoss.toFixed(4)} | ` +
                `TP: ${takeProfit.toFixed(4)} | ` +
                `Conf: ${(signal.confidence * 100).toFixed(0)}%`
            ));
            
        } catch (error) {
            console.error(COLORS.RED(`Position opening failed: ${error.message}`));
        }
    }
    
    closePosition(price, reason) {
        if (!this.position) return;
        
        try {
            const { position } = this;
            
            const slippage = price.mul(this.config.slippage);
            const exitPrice = position.side === 'BUY' ? 
                price.sub(slippage) : 
                price.add(slippage);
            
            const rawPnL = position.side === 'BUY' ?
                exitPrice.sub(position.entry).mul(position.quantity) :
                position.entry.sub(exitPrice).mul(position.quantity);
            
            const exitFee = exitPrice.mul(position.quantity).mul(this.config.fee);
            const netPnL = rawPnL.sub(exitFee);
            
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
            
            // Calculate metrics
            this.metrics.winRate = this.metrics.winningTrades / this.metrics.totalTrades;
            this.metrics.profitFactor = this.calculateProfitFactor();
            this.metrics.avgWin = this.calculateAverageWin();
            this.metrics.avgLoss = this.calculateAverageLoss();
            this.metrics.avgTradeDuration = this.calculateAverageTradeDuration();
            this.metrics.maxConsecutiveLosses = Math.max(this.metrics.maxConsecutiveLosses, this.consecutiveLosses);
            
            // Record trade
            const tradeDuration = Date.now() - position.timestamp;
            this.tradeDurations.push(tradeDuration);
            this.tradeHistory.push({
                side: position.side,
                entry: position.entry,
                exit: exitPrice,
                quantity: position.quantity,
                pnl: netPnL,
                strategy: position.strategy,
                duration: tradeDuration,
                reason,
                confidence: position.confidence
            });
            
            // Display result
            const pnlColor = netPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(`${COLORS.BOLD(reason)}! ` +
                `PnL: ${pnlColor(netPnL.toFixed(2))} ` +
                `[${position.strategy}] | ` +
                `Duration: ${(tradeDuration / 1000 / 60).toFixed(1)}m`);
            
            this.position = null;
            
        } catch (error) {
            console.error(COLORS.RED(`Position closing failed: ${error.message}`));
        }
    }
    
    calculateProfitFactor() {
        const totalWins = this.tradeHistory
            .filter(t => t.pnl.gte(0))
            .reduce((sum, t) => sum.add(t.pnl), new Decimal(0));
        const totalLosses = this.tradeHistory
            .filter(t => t.pnl.lt(0))
            .reduce((sum, t) => sum.add(t.pnl.abs()), new Decimal(0));
        
        return totalLosses.gt(0) ? 
            totalWins.div(totalLosses).toNumber() : 
            totalWins.gt(0) ? Infinity : 0;
    }
    
    calculateAverageWin() {
        const wins = this.tradeHistory.filter(t => t.pnl.gte(0));
        if (wins.length === 0) return new Decimal(0);
        return wins.reduce((sum, t) => sum.add(t.pnl), new Decimal(0)).div(wins.length);
    }
    
    calculateAverageLoss() {
        const losses = this.tradeHistory.filter(t => t.pnl.lt(0));
        if (losses.length === 0) return new Decimal(0);
        return losses.reduce((sum, t) => sum.add(t.pnl.abs()), new Decimal(0)).div(losses.length);
    }
    
    calculateAverageTradeDuration() {
        if (this.tradeDurations.length === 0) return 0;
        return this.tradeDurations.reduce((sum, d) => sum + d, 0) / this.tradeDurations.length;
    }
    
    getCurrentPnL(currentPrice) {
        if (!this.position) return new Decimal(0);
        
        const price = new Decimal(currentPrice);
        const { position } = this;
        
        return position.side === 'BUY' ?
            price.sub(position.entry).mul(position.quantity) :
            position.entry.sub(price).mul(position.quantity);
    }
    
    getMetrics() {
        const currentDrawdown = this.startBalance.sub(this.balance).div(this.startBalance).mul(100);
        
        return {
            ...this.metrics,
            currentBalance: this.balance.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalReturn: this.balance.sub(this.startBalance).div(this.startBalance).mul(100).toNumber(),
            currentDrawdown: currentDrawdown.toNumber(),
            avgWin: this.metrics.avgWin.toNumber(),
            avgLoss: this.metrics.avgLoss.toNumber(),
            avgTradeDuration: this.metrics.avgTradeDuration / 1000 / 60, // Convert to minutes
            consecutiveLosses: this.consecutiveLosses,
            openPosition: this.position ? {
                side: this.position.side,
                entry: this.position.entry.toNumber(),
                quantity: this.position.quantity.toNumber(),
                pnl: this.getCurrentPnL(this.position.entry.toNumber()).toNumber(),
                strategy: this.position.strategy,
                confidence: this.position.confidence
            } : null
        };
    }
}

// =============================================================================
// ENHANCED AI ANALYSIS ENGINE
// =============================================================================

class EnhancedAIAnalysisEngine {
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
        
        // Enhanced rate limiting
        this.lastRequest = 0;
        this.minRequestInterval = config.ai.rateLimitMs || 2000;
        this.requestQueue = [];
        this.processingQueue = false;
    }
    
    async enforceRateLimit() {
        const now = Date.now();
        const timeSinceLastRequest = now - this.lastRequest;
        
        if (timeSinceLastRequest < this.minRequestInterval) {
            const waitTime = this.minRequestInterval - timeSinceLastRequest;
            await sleep(waitTime);
        }
        
        this.lastRequest = Date.now();
    }
    
    async generateSignal(context) {
        await this.enforceRateLimit();
        
        const prompt = this.buildEnhancedPrompt(context);
        
        try {
            const response = await this.model.generateContent(prompt);
            const text = response.response.text();
            
            return this.parseEnhancedAIResponse(text, context);
            
        } catch (error) {
            console.error(COLORS.RED(`AI analysis failed: ${error.message}`));
            return {
                action: 'HOLD',
                confidence: 0,
                strategy: 'AI_ERROR',
                entry: 0,
                stopLoss: 0,
                takeProfit: 0,
                reason: `AI Error: ${error.message}`,
                wss: 0,
                riskReward: 0
            };
        }
    }
    
    buildEnhancedPrompt(context) {
        const { marketData, analysis, enhancedWSS, config } = context;
        const { score, confidence, components } = enhancedWSS;
        
        return `
ACT AS: Professional Cryptocurrency Trading Algorithm with Advanced Analytics
OBJECTIVE: Generate precise trading signals using enhanced multi-component analysis

ENHANCED WEIGHTED SENTIMENT SCORE:
- Primary Score: ${score.toFixed(2)} (Bias: ${score > 0 ? 'BULLISH' : score < 0 ? 'BEARISH' : 'NEUTRAL'})
- Confidence Level: ${(confidence * 100).toFixed(1)}%
- Component Breakdown: Trend ${components.trend?.score?.toFixed(2) || 'N/A'}, 
  Momentum ${components.momentum?.score?.toFixed(2) || 'N/A'}, 
  Volume ${components.volume?.score?.toFixed(2) || 'N/A'}, 
  OrderFlow ${components.orderFlow?.score?.toFixed(2) || 'N/A'}, 
  Structure ${components.structure?.score?.toFixed(2) || 'N/A'}

CRITICAL THRESHOLDS:
- Strong BUY Signal: WSS â‰¥ ${config.indicators.weights.actionThreshold + 1} and Confidence â‰¥ 0.8
- BUY Signal: WSS â‰¥ ${config.indicators.weights.actionThreshold} and Confidence â‰¥ 0.75
- Strong SELL Signal: WSS â‰¤ -${config.indicators.weights.actionThreshold + 1} and Confidence â‰¥ 0.8
- SELL Signal: WSS â‰¤ -${config.indicators.weights.actionThreshold} and Confidence â‰¥ 0.75
- HOLD: All other conditions

MARKET CONTEXT:
- Symbol: ${config.symbol}
- Current Price: $${marketData.price.toFixed(4)}
- Volatility: ${analysis.volatility?.[analysis.volatility.length - 1]?.toFixed(4) || 'N/A'}
- Market Regime: ${analysis.marketRegime}

EXTENDED TECHNICAL INDICATORS:
- Multi-Timeframe Trend: ${analysis.trendMTF}
- RSI: ${analysis.rsi?.[analysis.rsi.length - 1]?.toFixed(2) || 'N/A'}
- Williams %R: ${analysis.williamsR?.[analysis.williamsR.length - 1]?.toFixed(2) || 'N/A'}
- CCI: ${analysis.cci?.[analysis.cci.length - 1]?.toFixed(2) || 'N/A'}
- MFI: ${analysis.mfi?.[analysis.mfi.length - 1]?.toFixed(2) || 'N/A'}
- ADX: ${analysis.adx?.adx?.[analysis.adx.adx.length - 1]?.toFixed(2) || 'N/A'}
- Stochastic %K: ${analysis.stoch?.k?.[analysis.stoch.k.length - 1]?.toFixed(0) || 'N/A'}
- MACD Histogram: ${analysis.macd?.hist?.[analysis.macd.hist.length - 1]?.toFixed(6) || 'N/A'}
- OBV: ${analysis.obv?.[analysis.obv.length - 1]?.toFixed(0) || 'N/A'}
- A/D Line: ${analysis.adLine?.[analysis.adLine.length - 1]?.toFixed(0) || 'N/A'}
- CMF: ${analysis.cmf?.[analysis.cmf.length - 1]?.toFixed(4) || 'N/A'}

VOLUME & ORDER BOOK ANALYSIS:
- Volume Flow: ${analysis.volumeAnalysis?.flow || 'N/A'}
- Volume Ratio: ${analysis.volumeAnalysis?.volumeRatio?.[analysis.volumeAnalysis.volumeRatio.length - 1]?.toFixed(2) || 'N/A'}
- Order Book Imbalance: ${analysis.orderBookAnalysis?.imbalance ? (analysis.orderBookAnalysis.imbalance * 100).toFixed(1) + '%' : 'N/A'}
- Liquidity Quality: ${analysis.orderBookAnalysis?.liquidity ? (analysis.orderBookAnalysis.liquidity * 100).toFixed(1) + '%' : 'N/A'}

MARKET STRUCTURE:
- Fair Value Gap: ${analysis.fvg ? `${analysis.fvg.type} @ $${analysis.fvg.price.toFixed(2)}` : 'None'}
- Divergence: ${analysis.divergence}
- Squeeze Status: ${analysis.isSqueeze ? 'ACTIVE' : 'INACTIVE'}
- Support Levels: ${analysis.supportResistance?.support?.map(s => `$${s.price.toFixed(2)}`).join(', ') || 'N/A'}
- Resistance Levels: ${analysis.supportResistance?.resistance?.map(r => `$${r.price.toFixed(2)}`).join(', ') || 'N/A'}

ENHANCED STRATEGY FRAMEWORK:
1. **TREND_FOLLOWING_ENHANCED** (WSS > 2.5): Multi-confirmation trend following with volume and order flow
2. **VOLUME_BREAKOUT** (Squeeze + High Volume + WSS > 1.5): Trade volatility expansion with strong volume
3. **ORDER_FLOW_IMBALANCE** (High Imbalance + Confirmed WSS): Trade strong order book signals
4. **MEAN_REVERSION_ADVANCED** (Multiple Oscillator Oversold/Overbought + WSS > 2.0): Fade extreme conditions
5. **LIQUIDITY_ENGULFING** (Near FVG + Volume Confirmation): Trade level retests with volume

REQUIREMENTS:
- Calculate precise entry, stop-loss, take-profit levels
- Ensure minimum 1:1.5 risk-reward ratio
- Use technical levels (Fibonacci, ATR, FVG, SR) for targets
- Consider volume and order flow in entry timing
- If WSS threshold not met or setup unclear, return HOLD

OUTPUT FORMAT (JSON ONLY):
{
    "action": "BUY|SELL|HOLD",
    "strategy": "STRATEGY_NAME",
    "confidence": 0.0-1.0,
    "entry": number,
    "stopLoss": number,
    "takeProfit": number,
    "riskReward": number,
    "wss": number,
    "reason": "Detailed reasoning with component analysis"
}
        `.trim();
    }
    
    parseEnhancedAIResponse(text, context) {
        try {
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                throw new Error('No valid JSON found in response');
            }
            
            const signal = JSON.parse(jsonMatch[0]);
            
            // Enhanced validation
            const requiredFields = ['action', 'strategy', 'confidence', 'entry', 'stopLoss', 'takeProfit'];
            for (const field of requiredFields) {
                if (signal[field] === undefined) {
                    throw new Error(`Missing required field: ${field}`);
                }
            }
            
            const validActions = ['BUY', 'SELL', 'HOLD'];
            if (!validActions.includes(signal.action)) {
                signal.action = 'HOLD';
            }
            
            signal.confidence = Utils.safeNumber(signal.confidence, 0);
            signal.entry = Utils.safeNumber(signal.entry, 0);
            signal.stopLoss = Utils.safeNumber(signal.stopLoss, 0);
            signal.takeProfit = Utils.safeNumber(signal.takeProfit, 0);
            
            // Apply enhanced WSS filter
            const { enhancedWSS, config } = context;
            const threshold = config.indicators.weights.actionThreshold;
            const confidence = enhancedWSS.confidence;
            
            if (signal.action === 'BUY' && enhancedWSS.score < threshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${enhancedWSS.score.toFixed(2)}) below BUY threshold (${threshold})`;
            } else if (signal.action === 'SELL' && enhancedWSS.score > -threshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${enhancedWSS.score.toFixed(2)}) above SELL threshold (${threshold})`;
            }
            
            // Confidence validation
            if (signal.confidence < config.ai.minConfidence) {
                signal.action = 'HOLD';
                signal.reason += ` | Confidence (${(signal.confidence * 100).toFixed(1)}%) below minimum (${(config.ai.minConfidence * 100).toFixed(0)}%)`;
            }
            
            // Risk-reward validation
            if (signal.action !== 'HOLD') {
                const risk = Math.abs(signal.entry - signal.stopLoss);
                const reward = Math.abs(signal.takeProfit - signal.entry);
                signal.riskReward = risk > 0 ? reward / risk : 0;
                
                if (signal.riskReward < 1.2) {
                    signal.action = 'HOLD';
                    signal.reason = `Risk-reward ratio (${signal.riskReward.toFixed(2)}) below minimum (1.2)`;
                }
            }
            
            // Add enhanced context
            signal.wss = enhancedWSS.score;
            signal.confidenceLevel = confidence;
            if (!signal.reason) {
                signal.reason = signal.action === 'HOLD' ? 
                    'No clear trading opportunity' : 
                    `Strategy: ${signal.strategy} | WSS: ${enhancedWSS.score.toFixed(2)} | Conf: ${(confidence * 100).toFixed(1)}%`;
            }
            
            return signal;
            
        } catch (error) {
            console.error(COLORS.RED(`Enhanced AI response parsing failed: ${error.message}`));
            return {
                action: 'HOLD',
                confidence: 0,
                strategy: 'PARSING_ERROR',
                entry: 0,
                stopLoss: 0,
                takeProfit: 0,
                riskReward: 0,
                wss: 0,
                reason: `Enhanced parsing error: ${error.message}`
            };
        }
    }
}

// =============================================================================
// ENHANCED TRADING ENGINE
// =============================================================================

class EnhancedTradingEngine {
    constructor(config) {
        if (!config) throw new Error('Configuration is required');
        
        this.config = config;
        this.dataProvider = new DataProvider(config);
        this.exchange = new EnhancedPaperExchange(config);
        this.ai = new EnhancedAIAnalysisEngine(config);
        this.isRunning = false;
        this.startTime = Date.now();
        
        // Enhanced statistics
        this.stats = {
            dataFetchAttempts: 0,
            dataFetchSuccesses: 0,
            aiAnalysisCalls: 0,
            signalsGenerated: 0,
            positionsOpened: 0,
            positionsClosed: 0,
            averageLoopTime: 0,
            wssCalculations: 0,
            enhancedSignals: 0,
            volumeAnalyses: 0,
            orderBookAnalyses: 0
        };
        
        // Performance monitoring
        this.performanceMetrics = {
            memoryUsage: [],
            cpuUsage: [],
            networkLatency: [],
            signalLatency: []
        };
    }
    
    async start() {
        console.clear();
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` ðŸš€ WHALEWAVE TITAN v7.1 ENHANCED STARTING... `
        ))));
        
        this.isRunning = true;
        
        this.setupSignalHandlers();
        
        console.log(COLORS.GREEN('âœ… Enhanced engine started successfully'));
        console.log(COLORS.GRAY(`ðŸ”§ Configuration: ${this.config.symbol}`));
        console.log(COLORS.GRAY(`â±ï¸ Loop delay: ${this.config.delays.loop}ms`));
        console.log(COLORS.CYAN('ðŸ“Š Enhanced Features: Multi-Component WSS, Volume Analysis, Order Flow'));
        
        await this.mainLoop();
    }
    
    setupSignalHandlers() {
        const shutdown = (signal) => {
            console.log(COLORS.RED(`\nðŸ›‘ Received ${signal}. Starting graceful shutdown...`));
            this.isRunning = false;
            this.displayEnhancedShutdownReport();
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
    
    async mainLoop() {
        let loopCount = 0;
        let totalLoopTime = 0;
        
        while (this.isRunning) {
            const loopStart = Date.now();
            
            try {
                this.stats.dataFetchAttempts++;
                
                const startTime = Date.now();
                const marketData = await this.dataProvider.fetchMarketData();
                const dataFetchTime = Date.now() - startTime;
                
                if (!marketData) {
                    console.warn(COLORS.YELLOW('âš ï¸ Failed to fetch market data, retrying...'));
                    await sleep(this.config.delays.retry);
                    continue;
                }
                
                this.stats.dataFetchSuccesses++;
                this.performanceMetrics.networkLatency.push(dataFetchTime);
                
                // Enhanced market analysis
                const analysisStart = Date.now();
                const analysis = await MarketAnalyzer.analyze(marketData, this.config);
                const analysisTime = Date.now() - analysisStart;
                
                // Calculate enhanced WSS
                const wssStart = Date.now();
                const enhancedWSS = EnhancedWeightedSentimentCalculator.calculate(
                    analysis, 
                    marketData.price, 
                    this.config.indicators.weights,
                    this.config
                );
                analysis.enhancedWSS = enhancedWSS;
                const wssTime = Date.now() - wssStart;
                
                this.stats.wssCalculations++;
                
                // Generate enhanced AI signal
                this.stats.aiAnalysisCalls++;
                const signal = await this.ai.generateSignal({
                    marketData,
                    analysis,
                    enhancedWSS,
                    config: this.config
                });
                
                this.stats.signalsGenerated++;
                this.stats.enhancedSignals++;
                
                // Execute trading logic
                this.exchange.evaluate(marketData.price, signal);
                if (signal.action !== 'HOLD') {
                    this.stats.positionsOpened++;
                }
                
                // Display enhanced dashboard
                this.displayEnhancedDashboard(marketData, analysis, enhancedWSS, signal);
                
                // Performance tracking
                const loopTime = Date.now() - loopStart;
                totalLoopTime += loopTime;
                this.stats.averageLoopTime = totalLoopTime / ++loopCount;
                
                // Store performance metrics
                this.trackPerformanceMetrics(loopTime, analysisTime, wssTime, dataFetchTime);
                
            } catch (error) {
                console.error(COLORS.RED(`Loop error: ${error.message}`));
                console.debug(error.stack);
            }
            
            await sleep(this.config.delays.loop);
        }
    }
    
    trackPerformanceMetrics(loopTime, analysisTime, wssTime, dataTime) {
        // Memory usage (simplified)
        const memUsage = process.memoryUsage();
        this.performanceMetrics.memoryUsage.push(memUsage.heapUsed / 1024 / 1024);
        
        // Store timing metrics
        this.performanceMetrics.signalLatency.push(loopTime);
    }
    
    displayEnhancedDashboard(marketData, analysis, enhancedWSS, signal) {
        console.clear();
        
        const border = COLORS.GRAY('â”€'.repeat(90));
        console.log(border);
        console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(
            ` ðŸŒŠ WHALEWAVE TITAN v7.1 ENHANCED | ${this.config.symbol} | $${marketData.price.toFixed(4)} `
        ))));
        console.log(border);
        
        // Enhanced WSS display
        const wssScore = enhancedWSS.score;
        const wssConfidence = enhancedWSS.confidence;
        const wssColor = wssScore >= this.config.indicators.weights.actionThreshold ? COLORS.GREEN :
                        wssScore <= -this.config.indicators.weights.actionThreshold ? COLORS.RED : COLORS.YELLOW;
        const confidenceColor = wssConfidence >= 0.8 ? COLORS.GREEN :
                               wssConfidence >= 0.6 ? COLORS.YELLOW : COLORS.RED;
        
        console.log(`ðŸŽ¯ ENHANCED WSS: ${wssColor(wssScore.toFixed(2))} | ` +
                   `Confidence: ${confidenceColor((wssConfidence * 100).toFixed(1))}% | ` +
                   `Signal: ${this.colorizeSignal(signal.action)} ` +
                   `(${(signal.confidence * 100).toFixed(0)}%)`);
        
        console.log(COLORS.GRAY(`ðŸ“‹ Strategy: ${COLORS.BLUE(signal.strategy)} | ${signal.reason}`));
        console.log(border);
        
        // Component breakdown
        const components = enhancedWSS.components;
        console.log(`ðŸ”§ Components: ` +
                   `Trend ${this.colorizeComponent(components.trend?.score)} | ` +
                   `Momentum ${this.colorizeComponent(components.momentum?.score)} | ` +
                   `Volume ${this.colorizeComponent(components.volume?.score)} | ` +
                   `OrderFlow ${this.colorizeComponent(components.orderFlow?.score)} | ` +
                   `Structure ${this.colorizeComponent(components.structure?.score)}`);
        console.log(border);
        
        // Market state with enhanced indicators
        const regimeColor = analysis.marketRegime.includes('HIGH') ? COLORS.RED :
                           analysis.marketRegime.includes('LOW') ? COLORS.GREEN : COLORS.YELLOW;
        const trendColor = analysis.trendMTF === 'BULLISH' ? COLORS.GREEN : COLORS.RED;
        
        console.log(`ðŸ“Š Regime: ${regimeColor(analysis.marketRegime)} | ` +
                   `Volatility: ${COLORS.CYAN(Utils.safeNumber(analysis.volatility?.[analysis.volatility.length - 1], 0).toFixed(4))} | ` +
                   `Squeeze: ${analysis.isSqueeze ? COLORS.ORANGE('ACTIVE') : 'OFF'} | ` +
                   `MTF: ${trendColor(analysis.trendMTF)}`);
        
        // Extended indicators
        const rsi = Utils.safeNumber(analysis.rsi?.[analysis.rsi.length - 1], 50);
        const williams = Utils.safeNumber(analysis.williamsR?.[analysis.williamsR.length - 1], -50);
        const cci = Utils.safeNumber(analysis.cci?.[analysis.cci.length - 1], 0);
        const mfi = Utils.safeNumber(analysis.mfi?.[analysis.mfi.length - 1], 50);
        const adx = Utils.safeNumber(analysis.adx?.adx?.[analysis.adx.adx.length - 1], 0);
        
        console.log(`ðŸ“ˆ RSI: ${this.colorizeIndicator(rsi, 'rsi')} | ` +
                   `Williams %R: ${this.colorizeIndicator(williams, 'williams')} | ` +
                   `CCI: ${this.colorizeIndicator(cci, 'cci')} | ` +
                   `MFI: ${this.colorizeIndicator(mfi, 'mfi')} | ` +
                   `ADX: ${COLORS.CYAN(adx.toFixed(1))}`);
        console.log(border);
        
        // Volume and order flow analysis
        const volumeFlow = analysis.volumeAnalysis?.flow || 'N/A';
        const volumeColor = volumeFlow.includes('BULLISH') ? COLORS.GREEN :
                           volumeFlow.includes('BEARISH') ? COLORS.RED : COLORS.YELLOW;
        
        console.log(`ðŸ“Š Volume: ${volumeColor(volumeFlow)} | ` +
                   `Ratio: ${COLORS.CYAN(Utils.safeNumber(analysis.volumeAnalysis?.volumeRatio?.[analysis.volumeAnalysis.volumeRatio.length - 1], 1).toFixed(2))}x | ` +
                   `OrderFlow: ${this.colorizeOrderFlow(analysis.orderBookAnalysis?.flow)} | ` +
                   `Imbalance: ${this.colorizeImbalance(analysis.orderBookAnalysis?.imbalance)}`);
        
        // Structure analysis
        const divColor = analysis.divergence.includes('BULLISH') ? COLORS.GREEN :
                        analysis.divergence.includes('BEARISH') ? COLORS.RED : COLORS.GRAY;
        console.log(`ðŸ” Divergence: ${divColor(analysis.divergence)} | ` +
                   `FVG: ${analysis.fvg ? COLORS.YELLOW(analysis.fvg.type) : 'None'} | ` +
                   `SR Levels: ${COLORS.CYAN((analysis.supportResistance?.support?.length || 0) + (analysis.supportResistance?.resistance?.length || 0))}`);
        console.log(border);
        
        // Enhanced performance metrics
        const metrics = this.exchange.getMetrics();
        const pnlColor = metrics.dailyPnL >= 0 ? COLORS.GREEN : COLORS.RED;
        const profitColor = metrics.profitFactor > 1.5 ? COLORS.GREEN :
                           metrics.profitFactor > 1.0 ? COLORS.YELLOW : COLORS.RED;
        
        console.log(`ðŸ’° Balance: ${COLORS.GREEN('$' + metrics.currentBalance.toFixed(2))} | ` +
                   `Daily P&L: ${pnlColor('$' + metrics.dailyPnL.toFixed(2))} | ` +
                   `Win Rate: ${COLORS.CYAN((metrics.winRate * 100).toFixed(1))}% | ` +
                   `Profit Factor: ${profitColor(metrics.profitFactor.toFixed(2))}`);
        
        // Current position with enhanced details
        if (metrics.openPosition) {
            const currentPnl = this.exchange.getCurrentPnL(marketData.price);
            const posColor = currentPnl.gte(0) ? COLORS.GREEN : COLORS.RED;
            console.log(COLORS.BLUE(`ðŸ“ˆ OPEN: ${metrics.openPosition.side} @ ${metrics.openPosition.entry.toFixed(4)} | ` +
                `PnL: ${posColor(currentPnl.toFixed(2))} | ` +
                `Conf: ${(metrics.openPosition.confidence * 100).toFixed(0)}% | ` +
                `Strategy: ${metrics.openPosition.strategy}`));
        }
        console.log(border);
        
        // Uptime and enhanced statistics
        const uptime = Math.floor((Date.now() - this.startTime) / 1000);
        const avgMemory = this.performanceMetrics.memoryUsage.length > 0 ? 
            this.performanceMetrics.memoryUsage.reduce((sum, m) => sum + m, 0) / this.performanceMetrics.memoryUsage.length : 0;
        
        console.log(COLORS.GRAY(`â±ï¸ Uptime: ${Math.floor(uptime / 3600)}h ${Math.floor((uptime % 3600) / 60)}m | ` +
                   `Avg Loop: ${this.stats.averageLoopTime.toFixed(0)}ms | ` +
                   `Memory: ${COLORS.CYAN(avgMemory.toFixed(1))}MB | ` +
                   `Success Rate: ${COLORS.CYAN(((this.stats.dataFetchSuccesses / this.stats.dataFetchAttempts) * 100).toFixed(1))}%`));
    }
    
    colorizeSignal(action) {
        switch (action) {
            case 'BUY': return COLORS.GREEN('BUY');
            case 'SELL': return COLORS.RED('SELL');
            default: return COLORS.GRAY('HOLD');
        }
    }
    
    colorizeComponent(score) {
        if (score > 0.5) return COLORS.GREEN(score.toFixed(2));
        if (score < -0.5) return COLORS.RED(score.toFixed(2));
        return COLORS.YELLOW(score.toFixed(2));
    }
    
    colorizeOrderFlow(flow) {
        if (!flow) return COLORS.GRAY('N/A');
        if (flow.includes('STRONG_BUY')) return COLORS.GREEN(flow);
        if (flow.includes('BUY')) return COLORS.GREEN(flow.replace('STRONG_', ''));
        if (flow.includes('STRONG_SELL')) return COLORS.RED(flow);
        if (flow.includes('SELL')) return COLORS.RED(flow.replace('STRONG_', ''));
        return COLORS.YELLOW(flow);
    }
    
    colorizeImbalance(imbalance) {
        if (imbalance === undefined || imbalance === null) return COLORS.GRAY('N/A');
        const pct = (imbalance * 100).toFixed(1);
        return imbalance > 0.3 ? COLORS.GREEN(`+${pct}%`) :
               imbalance < -0.3 ? COLORS.RED(`${pct}%`) : COLORS.YELLOW(`${pct}%`);
    }
    
    colorizeIndicator(value, type) {
        const v = Utils.safeNumber(value, 0);
        
        switch (type) {
            case 'rsi':
                if (v > 70) return COLORS.RED(v.toFixed(2));
                if (v < 30) return COLORS.GREEN(v.toFixed(2));
                return COLORS.YELLOW(v.toFixed(2));
                
            case 'williams':
                if (v > -20) return COLORS.RED(v.toFixed(2));
                if (v < -80) return COLORS.GREEN(v.toFixed(2));
                return COLORS.YELLOW(v.toFixed(2));
                
            case 'cci':
                if (v > 100) return COLORS.RED(v.toFixed(2));
                if (v < -100) return COLORS.GREEN(v.toFixed(2));
                return COLORS.YELLOW(v.toFixed(2));
                
            case 'mfi':
                if (v > 80) return COLORS.RED(v.toFixed(2));
                if (v < 20) return COLORS.GREEN(v.toFixed(2));
                return COLORS.YELLOW(v.toFixed(2));
                
            default:
                return COLORS.CYAN(v.toFixed(2));
        }
    }
    
    displayEnhancedShutdownReport() {
        console.log(COLORS.RED('\nðŸ“Š ENHANCED SHUTDOWN REPORT'));
        console.log(COLORS.GRAY('='.repeat(60)));
        
        const metrics = this.exchange.getMetrics();
        const uptime = (Date.now() - this.startTime) / 1000 / 60; // minutes
        
        console.log(`â±ï¸ Uptime: ${uptime.toFixed(1)} minutes`);
        console.log(`ðŸ”„ Data Success Rate: ${(this.stats.dataFetchSuccesses / this.stats.dataFetchAttempts * 100).toFixed(1)}%`);
        console.log(`ðŸ¤– AI Analysis Success: ${(this.stats.aiAnalysisCalls / this.stats.dataFetchSuccesses * 100).toFixed(1)}%`);
        console.log(`ðŸŽ¯ Enhanced WSS Calculations: ${this.stats.wssCalculations}`);
        console.log(`ðŸ“Š Volume Analyses: ${this.stats.volumeAnalyses}`);
        console.log(`ðŸ“ˆ Order Book Analyses: ${this.stats.orderBookAnalyses}`);
        console.log(`ðŸ’¼ Total Trades: ${metrics.totalTrades}`);
        console.log(`ðŸ† Win Rate: ${(metrics.winRate * 100).toFixed(1)}%`);
        console.log(`ðŸ’° Profit Factor: ${metrics.profitFactor.toFixed(2)}`);
        console.log(`ðŸ’µ Final Balance: $${metrics.currentBalance.toFixed(2)}`);
        console.log(`ðŸ“ˆ Total Return: ${metrics.totalReturn.toFixed(2)}%`);
        console.log(`ðŸ“‰ Max Drawdown: ${metrics.maxDrawdown.toFixed(2)}%`);
        console.log(`â±ï¸ Avg Trade Duration: ${metrics.avgTradeDuration.toFixed(1)} minutes`);
        console.log(`ðŸ”„ Max Consecutive Losses: ${metrics.maxConsecutiveLosses}`);
        console.log(`ðŸ’¸ Total Fees: $${metrics.totalFees.toFixed(4)}`);
        
        // Performance summary
        const avgMemory = this.performanceMetrics.memoryUsage.length > 0 ? 
            this.performanceMetrics.memoryUsage.reduce((sum, m) => sum + m, 0) / this.performanceMetrics.memoryUsage.length : 0;
        console.log(`ðŸ–¥ï¸ Avg Memory Usage: ${avgMemory.toFixed(1)}MB`);
        console.log(`âš¡ Avg Loop Time: ${this.stats.averageLoopTime.toFixed(0)}ms`);
        
        console.log(COLORS.GRAY('='.repeat(60)));
        console.log(COLORS.RED('ðŸ›‘ Enhanced engine stopped gracefully'));
    }
}

// =============================================================================
// APPLICATION ENTRY POINT
// =============================================================================

async function main() {
    try {
        console.log(COLORS.YELLOW('ðŸ”§ Loading enhanced configuration...'));
        const config = await ConfigManager.load();
        
        console.log(COLORS.GREEN('âœ… Configuration loaded successfully'));
        
        const engine = new EnhancedTradingEngine(config);
        await engine.start();
        
    } catch (error) {
        console.error(COLORS.RED(`Enhanced application failed to start: ${error.message}`));
        console.debug(error.stack);
        process.exit(1);
    }
}

// Start the enhanced application
if (import.meta.url === `file://${process.argv[1]}`) {
    main().catch(error => {
        console.error(COLORS.RED(`Fatal error: ${error.message}`));
        process.exit(1);
    });
}

export { 
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
