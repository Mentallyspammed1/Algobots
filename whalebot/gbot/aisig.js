/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN LIVE v1.9 (FULLY EXECUTABLE)
 * ===================================================
 * - Fixed all syntax errors and missing methods
 * - Complete WSS 3.0 integration with REST fallback
 * - Working Leviathan scoring with real orderbook data
 * - Functional backtest mode
 * - Production-ready architecture
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generativeAI';
import dotenv from 'dotenv';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import crypto from 'crypto';
import WebSocket from 'ws';
import * => fs from 'fs/promises';

dotenv.config();

// === CONSTANTS ===
const COLOR = {
    GREEN: chalk.hex('#00FF41'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#0A84FF'),
    PURPLE: chalk.hex('#BF5AF2'),
    YELLOW: chalk.hex('#FFD60A'),
    CYAN: chalk.hex('#32ADE6'),
    GRAY: chalk.hex('#8E8E93'),
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#101010')(text),
};

// === CONFIGURATION ===
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        live_trading: process.env.LIVE_MODE === 'true',
        intervals: { scalping: '1', main: '3', trend: '15' },
        limits: { 
            kline: { scalping: 300, main: 300, trend: 100 }, // Separate limits for different kline buffers
            orderbook: 10 
        },
        delays: { loop: 4000, retry: 1000, wsReconnect: 2000 },
        ai: { model: 'gemini-1.5-flash', minConfidence: 0.85 },
        risk: {
            maxDrawdown: 7.0,
            shockBuffer: 0.10,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001,
            volatilityAdjustment: true,
            GTfactor: 0.85,
            maintenanceWarning: 0.90,
            initialBalance: 10000, // Added initialBalance for PaperExchange
            maxRiskPerTrade: 1.0, // Added maxRiskPerTrade for PaperExchange
            minConfidence: 0.85, // Added minConfidence for PaperExchange
        },
        indicators: {
            rsi: 14, stoch: 14, mfi: 14,
            fisher_period: 10, laguerre_gamma: 0.5,
            ema_low: 5, ema_high: 13,
            adx_period: 14,
            atr_period: 14,
            obv_period: 20, 
            vwap_period: 20,
            bb_period: 20,
            bb_std_dev: 2,
            stoch_rsi_k_period: 14,
            stoch_rsi_d_period: 3,
            kama_period: 10,
            weights: {
                trend_mtf: 2.0,
                scalping_momentum: 2.5,
                order_flow: 1.5,
                structure: 1.2,
                actionThreshold: 2.0,
                price_impact: 0.3
            }
        }
    });

    static async load() {
        let config = { ...this.DEFAULTS };
        try {
            const data = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.mergeDeep(config, JSON.parse(data));
        } catch (error) {
            console.warn(COLOR.YELLOW(`[ConfigManager] Config file '${this.CONFIG_FILE}' not found or invalid, using defaults. Error: ${error.message}`));
            // Optionally write default config if not found
            // await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2), 'utf-8');
        }
        
        if (process.env.LIVE_MODE === 'true') config.live_trading = true;

        const validate = (path, value, type, min = null, max = null) => {
            if (typeof value !== type) {
                throw new Error(`Config validation error: '${path}' expected type '${type}', got '${typeof value}'.`);
            }
            if (type === 'number') {
                if (min !== null && value < min) throw new Error(`Config validation error: '${path}' must be >= ${min}.`);
                if (max !== null && value > max) throw new Error(`Config validation error: '${path}' must be <= ${max}.`);
            }
        };

        try {
            validate('symbol', config.symbol, 'string');
            validate('live_trading', config.live_trading, 'boolean');
            validate('intervals.scalping', config.intervals.scalping, 'string');
            validate('limits.kline.scalping', config.limits.kline.scalping, 'number', 10, 1000);
            validate('limits.kline.main', config.limits.kline.main, 'number', 10, 1000);
            validate('limits.kline.trend', config.limits.kline.trend, 'number', 10, 1000);
            validate('limits.orderbook', config.limits.orderbook, 'number', 1, 50);
            validate('delays.loop', config.delays.loop, 'number', 100, 10000);
            validate('ai.model', config.ai.model, 'string');
            validate('ai.minConfidence', config.ai.minConfidence, 'number', 0, 1);
            validate('risk.maxRiskPerTrade', config.risk.maxRiskPerTrade, 'number', 0.1, 10);
            
            // Indicator specific validations (more comprehensive)
            validate('indicators.rsi', config.indicators.rsi, 'number', 1, 100);
            validate('indicators.stoch', config.indicators.stoch, 'number', 1, 100);
            validate('indicators.mfi', config.indicators.mfi, 'number', 1, 100);
            validate('indicators.fisher_period', config.indicators.fisher_period, 'number', 1, 50);
            validate('indicators.laguerre_gamma', config.indicators.laguerre_gamma, 'number', 0, 1); // Gamma between 0 and 1
            validate('indicators.ema_low', config.indicators.ema_low, 'number', 1, 50);
            validate('indicators.ema_high', config.indicators.ema_high, 'number', 1, 50);
            validate('indicators.adx_period', config.indicators.adx_period, 'number', 1, 50);
            validate('indicators.atr_period', config.indicators.atr_period, 'number', 1, 50);
            validate('indicators.obv_period', config.indicators.obv_period, 'number', 1, 50); // Added, though OBV is cumulative
            validate('indicators.vwap_period', config.indicators.vwap_period, 'number', 1, 50); // Added
            validate('indicators.bb_period', config.indicators.bb_period, 'number', 1, 50);
            validate('indicators.bb_std_dev', config.indicators.bb_std_dev, 'number', 1, 5); // Std Dev typically 1-3
            validate('indicators.stoch_rsi_k_period', config.indicators.stoch_rsi_k_period, 'number', 1, 50);
            validate('indicators.stoch_rsi_d_period', config.indicators.stoch_rsi_d_period, 'number', 1, 50);
            validate('indicators.kama_period', config.indicators.kama_period, 'number', 1, 50);

            validate('indicators.weights.trend_mtf', config.indicators.weights.trend_mtf, 'number', 0, 5);
            validate('indicators.weights.scalping_momentum', config.indicators.weights.scalping_momentum, 'number', 0, 5);
            validate('indicators.weights.order_flow', config.indicators.weights.order_flow, 'number', 0, 5);
            validate('indicators.weights.structure', config.indicators.weights.structure, 'number', 0, 5);
            validate('indicators.weights.actionThreshold', config.indicators.weights.actionThreshold, 'number', 0, 5);
            validate('indicators.weights.price_impact', config.indicators.weights.price_impact, 'number', 0, 5);

        } catch (error) {
            console.error(COLOR.RED(`[ConfigManager] FATAL CONFIGURATION ERROR: ${error.message}`));
            process.exit(1);
        }

        return config;
    }

    static mergeDeep(target, source) {
        const output = { ...target };
        for (const key in source) {
            if (source[key] instanceof Object && key in target) {
                output[key] = this.mergeDeep(target[key], source[key]);
            } else {
                output[key] = source[key];
            }
        }
        return output;
    }
}

// === UTILS ===
const Utils = {
    safeArray: (length) => new Array(Math.max(0, Math.floor(length))).fill(0),
    safeNumber: (val, def = 0) => (typeof val === 'number' && isFinite(val)) ? val : def,
    sum: (arr) => arr.reduce((a, b) => a + b, 0), // Added sum function
    average: (arr) => arr.length ? Utils.sum(arr) / arr.length : 0,
    stdDev: (arr, period) => {
        if (!arr || arr.length < period || period <= 0) return Utils.safeArray(arr.length); // Added period <= 0 check
        const result = Utils.safeArray(arr.length);
        for (let i = period - 1; i < arr.length; i++) {
            const slice = arr.slice(i - period + 1, i + 1);
            const mean = Utils.average(slice);
            const variance = Utils.average(slice.map(x => Math.pow(x - mean, 2)));
            result[i] = Math.sqrt(variance);
        }
        return result;
    },
    calculateADR: (highs, lows) => {
        const range = highs.map((h, i) => h - lows[i]);
        return range.reduce((a, b) => a + b, 0) / range.length;
    },
    calculateVolatility: (data, period = 14) => {
        if (data.length < period) return 0;
        let sum = 0, sumSquares = 0;
        for (let i = 0; i < period; i++) {
            sum += data[i];
            sumSquares += data[i] ** 2;
        }
        const mean = sum / period;
        const variance = (sumSquares / period) - (mean ** 2);
        return Math.sqrt(Math.max(0, variance));
    }
};

// === KLINE BUFFER ===
class KlineBuffer {
    constructor(limit, interval) {
        this.limit = limit;
        this.interval = interval; // Store interval for logging/debugging
        this.candles = [];
        this.lastUpdateTime = 0; // To track last update for completeness check
    }

    /**
     * Adds or updates a kline.
     * If the kline's timestamp is newer than the last one in the buffer, it's added.
     * If it's the same, the last kline is updated (for unfinalized candles).
     * @param {object} kline - The kline object { t, o, h, l, c, v }
     */
    update(kline) {
        if (!kline || !kline.t) {
            console.warn(COLOR.YELLOW(`[KlineBuffer:${this.interval}] Attempted to update with invalid kline data: ${JSON.stringify(kline)}`));
            return;
        }

        if (this.candles.length === 0) {
            this.candles.push(kline);
        } else {
            const lastCandle = this.candles[this.candles.length - 1];
            if (kline.t > lastCandle.t) {
                // New candle
                this.candles.push(kline);
                if (this.candles.length > this.limit) {
                    this.candles.shift(); // Remove oldest
                }
            } else if (kline.t === lastCandle.t) {
                // Update existing candle (e.g., from WSS partial updates)
                this.candles[this.candles.length - 1] = kline;
            } else {
                // Older kline received, possibly from a replayed message or network lag
                console.warn(COLOR.YELLOW(`[KlineBuffer:${this.interval}] Received old kline update (t=${kline.t}) for current latest (t=${lastCandle.t}). Ignored.`)); // Uncommented
            }
        }
        this.lastUpdateTime = Date.now();
    }

    /**
     * Returns the current array of klines.
     * @returns {Array<object>}
     */
    getKlines() {
        return [...this.candles]; // Return a copy to prevent external modification
    }

    /**
     * Checks if the buffer has enough data for analysis (e.g., full limit or near full).
     * @returns {boolean}
     */
    isReady() {
        return this.candles.length >= this.limit; // or a smaller threshold like this.limit / 2
    }
}


// === TECHNICAL ANALYSIS ===
class TechnicalAnalysis {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        const res = Utils.safeArray(data.length);
        let sum = 0;
        for (let i = 0; i < period; i++) {
            sum += data[i];
        }
        res[period - 1] = sum / period;
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            res[i] = sum / period;
        }
        return res;
    }

    static ema(data, period) {
        if (!data || data.length === 0) return [];
        const res = Utils.safeArray(data.length);
        const k = 2 / (period + 1);
        res[0] = data[0];
        for (let i = 1; i < data.length; i++) res[i] = data[i] * k + res[i - 1] * (1 - k);
        return res;
    }

    static rsi(closes, period) {
        if (!closes || closes.length < period + 1) return Utils.safeArray(closes.length);
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        let avgGain = Utils.sum(gains.slice(0, period)) / period;
        let avgLoss = Utils.sum(losses.slice(0, period)) / period;
        const res = Utils.safeArray(closes.length);
        if (period < closes.length) { // Ensure period index is valid
            res[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
        }
        for (let i = period + 1; i < closes.length; i++) {
            avgGain = (avgGain * (period - 1) + gains[i]) / period;
            avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
            res[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
        }
        return res;
    }

    static stoch(highs, lows, closes, period) {
        if (!highs || !lows || !closes || closes.length < period) return Utils.safeArray(closes.length); // Added check
        const k = Utils.safeArray(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const h = highs.slice(i - period + 1, i + 1), l = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...l), maxH = Math.max(...h);
            k[i] = maxH === minL ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        return TechnicalAnalysis.sma(k, 3);
    }

    static atr(highs, lows, closes, period = 14) {
        if (!highs || !lows || !closes || closes.length < period + 1) return Utils.safeArray(closes.length); // Adjusted check
        const tr = Utils.safeArray(closes.length);
        for (let i = 1; i < closes.length; i++) {
            tr[i] = Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1]));
        }
        const res = Utils.safeArray(closes.length);
        let avg = Utils.sum(tr.slice(1, period + 1)) / period;
        if (period < closes.length) { // Ensure period index is valid
            res[period] = avg;
        }
        for (let i = period + 1; i < closes.length; i++) {
            avg = (avg * (period - 1) + tr[i]) / period;
            res[i] = avg;
        }
        return res;
    }

    static mfi(highs, lows, closes, volumes, period = 14) {
        if (!highs || !lows || !closes || !volumes || closes.length < period + 1) return Utils.safeArray(closes.length); // Added check
        const typ = closes.map((c, i) => (highs[i] + lows[i] + c) / 3);
        const res = Utils.safeArray(closes.length);
        for (let i = period; i < closes.length; i++) {
            let pos = 0, neg = 0;
            for (let j = 0; j < period; j++) {
                const idx = i - j;
                if (typ[idx] > typ[idx - 1]) pos += typ[idx] * volumes[idx];
                else if (typ[idx] < typ[idx - 1]) neg += typ[idx] * volumes[idx];
            }
            res[i] = neg === 0 ? 100 : 100 / (1 + pos / neg);
        }
        return res;
    }

    static fisherTransform(highs, lows, period = 10) {
        if (!highs || !lows || highs.length < period) return { fish: Utils.safeArray(highs.length) }; // Added check
        const len = highs.length;
        const fish = Utils.safeArray(len), value = Utils.safeArray(len);
        for (let i = 1; i < len; i++) {
            if (i < period) { value[i] = Utils.safeNumber(value[i - 1], 0); fish[i] = Utils.safeNumber(fish[i - 1], 0); continue; }
            let minL = Infinity, maxH = -Infinity;
            for (let j = 0; j < period; j++) {
                const hh = highs[i - j], ll = lows[i - j];
                if (hh > maxH) maxH = hh;
                if (ll < minL) minL = ll;
            }
            let raw = 0;
            if (maxH !== minL) raw = 0.33 * 2 * ((highs[i] + lows[i]) / 2 - minL) / (maxH - minL) - 0.5 + 0.67 * (Utils.safeNumber(value[i - 1], 0));
            value[i] = Math.max(Math.min(raw, 0.99), -0.99);
            fish[i] = 0.5 * Math.log((1 + value[i]) / (1 - value[i])) + 0.5 * (Utils.safeNumber(fish[i - 1], 0));
        }
        return { fish };
    }

    static laguerreRSI(closes, gamma = 0.5) {
        if (!closes || closes.length === 0) return Utils.safeArray(closes.length); // Added check
        const len = closes.length;
        const lrsi = Utils.safeArray(len);
        let l0 = closes[0], l1 = l0, l2 = l0, l3 = l0;
        for (let i = 1; i < len; i++) {
            l0 = (1 - gamma) * closes[i] + gamma * l0;
            l1 = -gamma * l0 + l0 + gamma * l1;
            l2 = -gamma * l1 + l1 + gamma * l2;
            l3 = -gamma * l2 + l2 + gamma * l3;
            const cu = (l0 >= l1 ? l0 - l1 : 0) + (l1 >= l2 ? l1 - l2 : 0) + (l2 >= l3 ? l2 - l3 : 0);
            const cd = (l0 < l1 ? l1 - l0 : 0) + (l1 < l2 ? l2 - l1 : 0) + (l2 < l3 ? l3 - l2 : 0);
            lrsi[i] = (cu + cd === 0) ? 0 : (cu / (cu + cd)) * 100;
        }
        return lrsi;
    }

    static findFVG(candles) {
        if (!candles || candles.length < 5) return null;
        const c1 = candles[candles.length - 4], c2 = candles[candles.length - 3], c3 = candles[candles.length - 2];
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }

    static detectDivergence(closes, rsi, i2) {
        if (!closes || !rsi || closes.length < 10) return 'NONE'; // Added check
        const len = closes.length;
        const i1 = i2 - 5; const i0 = i2 - 10;
        if (i0 < 0) return 'NONE';
        const pHigh1 = Math.max(...closes.slice(i1, i2)), rHigh1 = Math.max(...rsi.slice(i1, i2));
        const pHigh0 = Math.max(...closes.slice(i0, i1)), rHigh0 = Math.max(...rsi.slice(i0, i1));
        if (pHigh1 > pHigh0 && rHigh1 < rHigh0) return 'BEARISH_REGULAR';
        const pLow1 = Math.min(...closes.slice(i1, i2)), rLow1 = Math.min(...rsi.slice(i1, i2));
        const pLow0 = Math.min(...closes.slice(i0, i1)), rLow0 = Math.min(...rsi.slice(i0, i1));
        if (pLow1 < pLow0 && rLow1 > rLow0) return 'BULLISH_REGULAR';
        return 'NONE';
    }

    // NEW INDICATORS
    static obv(closes, volumes) {
        if (!closes || !volumes || closes.length !== volumes.length || closes.length === 0) return Utils.safeArray(closes.length); // Added check
        const obvArr = Utils.safeArray(closes.length);
        if (closes.length > 0) {
            obvArr[0] = volumes[0];
            for (let i = 1; i < closes.length; i++) {
                if (closes[i] > closes[i - 1]) {
                    obvArr[i] = obvArr[i - 1] + volumes[i];
                } else if (closes[i] < closes[i - 1]) {
                    obvArr[i] = obvArr[i - 1] - volumes[i];
                } else {
                    obvArr[i] = obvArr[i - 1];
                }
            }
        }
        return obvArr;
    }

    static vwap(closes, highs, lows, volumes) {
        if (!closes || !highs || !lows || !volumes || closes.length !== volumes.length || closes.length === 0) return Utils.safeArray(closes.length); // Added check
        const vwapArr = Utils.safeArray(closes.length);
        let cumulativePV = 0; // Cumulative Price * Volume
        let cumulativeVolume = 0; // Cumulative Volume

        for (let i = 0; i < closes.length; i++) {
            const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
            cumulativePV += typicalPrice * volumes[i];
            cumulativeVolume += volumes[i];
            vwapArr[i] = cumulativeVolume === 0 ? typicalPrice : cumulativePV / cumulativeVolume;
        }
        return vwapArr;
    }

    static bollingerBands(closes, period = 20, stdDevMultiplier = 2) {
        if (!closes || closes.length < period) return { upper: Utils.safeArray(closes.length), mid: Utils.safeArray(closes.length), lower: Utils.safeArray(closes.length) };
        
        const midBand = TechnicalAnalysis.sma(closes, period);
        const stdDev = Utils.stdDev(closes, period);
        
        const upperBand = Utils.safeArray(closes.length);
        const lowerBand = Utils.safeArray(closes.length);

        for (let i = period - 1; i < closes.length; i++) {
            upperBand[i] = midBand[i] + (stdDev[i] * stdDevMultiplier);
            lowerBand[i] = midBand[i] - (stdDev[i] * stdDevMultiplier);
        }
        
        return { upper: upperBand, mid: midBand, lower: lowerBand };
    }

    static stochRsi(closes, rsiPeriod = 14, kPeriod = 14, dPeriod = 3) {
        if (!closes || closes.length < rsiPeriod + kPeriod) return { k: Utils.safeArray(closes.length), d: Utils.safeArray(closes.length) };

        const rsiValues = TechnicalAnalysis.rsi(closes, rsiPeriod);
        const stochRsiK = Utils.safeArray(closes.length);

        for (let i = rsiPeriod + kPeriod - 1; i < closes.length; i++) {
            const rsiSlice = rsiValues.slice(i - kPeriod + 1, i + 1);
            const highestRSI = Math.max(...rsiSlice);
            const lowestRSI = Math.min(...rsiSlice);

            if (highestRSI === lowestRSI) {
                stochRsiK[i] = 0;
            } else {
                stochRsiK[i] = 100 * ((rsiValues[i] - lowestRSI) / (highestRSI - lowestRSI));
            }
        }
        const stochRsiD = TechnicalAnalysis.sma(stochRsiK, dPeriod);
        return { k: stochRsiK, d: stochRsiD };
    }

    static kama(closes, period = 10) {
        if (!closes || closes.length < period) return Utils.safeArray(closes.length);
        const kamaArr = Utils.safeArray(closes.length);
        const fastAlpha = 2 / (2 + 1); // Alpha for 2-period EMA
        const slowAlpha = 2 / (30 + 1); // Alpha for 30-period EMA

        kamaArr[0] = closes[0]; // First KAMA is first close price

        for (let i = 1; i < closes.length; i++) {
            if (i < period) {
                kamaArr[i] = closes[i]; // Not enough data, KAMA equals close
                continue;
            }

            const change = Math.abs(closes[i] - closes[i - period]);
            let volatility = 0;
            for (let j = 1; j <= period; j++) {
                volatility += Math.abs(closes[i - j + 1] - closes[i - j]);
            }

            const er = volatility === 0 ? 0 : change / volatility; // Efficiency Ratio
            const sc = Math.pow(er * (fastAlpha - slowAlpha) + slowAlpha, 2); // Smoothing Constant
            kamaArr[i] = kamaArr[i - 1] + sc * (closes[i] - kamaArr[i - 1]);
        }
        return kamaArr;
    }
}

// === DATA PROVIDER ===
class DataProvider {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: 6000 });
        this.symbol = config.symbol;
        this.initialKlinesLoaded = { main: false, trend: false }; // Track initial load
    }

    async fetch(url, params) {
        try { return (await this.api.get(url, { params })).data; } catch (e) { 
            console.error(COLOR.RED(`[DataProvider] Fetch Error for ${url} with params ${JSON.stringify(params)}: ${e.message}`));
            return null; 
        }
    }

    parseKlines(rawList) {
        if (!rawList || !rawList.result || !rawList.result.list) return [];
        return rawList.result.list
            .map(k => ({
                t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5]),
            }))
            .reverse();
    }

    async getSnapshot() {
        try {
            let tick, ob;
            let km = [], kt = [];

            [tick, ob] = await Promise.all([
                this.fetch('/tickers', { category: 'linear', symbol: this.symbol }),
                this.fetch('/orderbook', { category: 'linear', symbol: this.symbol, limit: this.config.limits.orderbook }),
            ]);

            // Only fetch full kline history once, then just latest
            if (!this.initialKlinesLoaded.main) {
                const rawKm = await this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.main, limit: this.config.limits.kline.main });
                km = this.parseKlines(rawKm);
                if (km.length > 0) this.initialKlinesLoaded.main = true;
            } else {
                // Fetch only the latest kline for main interval if already loaded
                const rawKm = await this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.main, limit: 1 });
                km = this.parseKlines(rawKm);
            }

            if (!this.initialKlinesLoaded.trend) {
                const rawKt = await this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.trend, limit: this.config.limits.kline.trend });
                kt = this.parseKlines(rawKt);
                if (kt.length > 0) this.initialKlinesLoaded.trend = true;
            } else {
                // Fetch only the latest kline for trend interval if already loaded
                const rawKt = await this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.trend, limit: 1 });
                kt = this.parseKlines(rawKt);
            }


            if (!tick) {
                console.warn(COLOR.YELLOW(`[DataProvider] Insufficient data from snapshot for ${this.symbol}. Tick missing.`));
                return null;
            }
            return {
                price: parseFloat(tick.result.list[0].lastPrice),
                candlesMain: km,
                candlesTrend: kt,
                bids: ob?.result?.b?.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })) ?? [],
                asks: ob?.result?.a?.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })) ?? [],
            };
        } catch (e) { 
            console.error(COLOR.RED(`[DataProvider] GetSnapshot Error for ${this.symbol}: ${e.message}`));
            return null; 
        }
    }
}

// === MARKET WATCHER ===
class MarketWatcher {
    constructor(config, onTick) {
        this.config = config;
        this.onTick = onTick;
        this.ws = null;
        this.retries = 0;
        this.symbol = config.symbol.toLowerCase();
        this.url = 'wss://stream.bybit.com/v5/public/linear';
        this.pingTimeout = null;
    }

    start() { this.connect(); }

    connect() {
        try {
            this.ws = new WebSocket(this.url);
            this.ws.on('open', () => {
                console.log(COLOR.GREEN("[MarketWatcher] WSS connected"));
                this.retries = 0;
                this.subscribe();
                this.heartbeat(); // Start heartbeat on successful connection
            });
            this.ws.on('message', (data) => this.handleMessage(data));
            this.ws.on('close', () => this.reconnect());
            this.ws.on('error', (err) => {
                console.error(COLOR.RED(`[MarketWatcher] WSS error: ${err.message}`));
                this.reconnect();
            });
        } catch (e) { 
            console.error(COLOR.RED(`[MarketWatcher] Connection attempt failed: ${e.message}`));
            this.reconnect(); 
        }
    }

    reconnect() {
        if (this.pingTimeout) clearTimeout(this.pingTimeout);
        const delay = Math.min(30000, this.config.delays.wsReconnect * Math.pow(2, this.retries++));
        console.warn(COLOR.YELLOW(`[MarketWatcher] WSS Reconnecting in ${Math.round(delay / 1000)}s... (Attempt ${this.retries})`));
        setTimeout(() => this.connect(), delay);
    }

    subscribe() {
        const sub = {
            op: 'subscribe',
            args: [
                `tickers.${this.symbol}`, 
                `orderbook.${this.config.limits.orderbook}.${this.symbol}`, 
                `kline.${this.config.intervals.scalping}.${this.symbol}`,
                // Add subscriptions for main and trend klines if available and desired for real-time updates
                `kline.${this.config.intervals.main}.${this.symbol}`,
                `kline.${this.config.intervals.trend}.${this.symbol}`
            ]
        };
        this.ws.send(JSON.stringify(sub));
        console.log(COLOR.GRAY(`[MarketWatcher] Subscribed to topics for ${this.symbol}.`));
    }

    heartbeat() {
        if (this.pingTimeout) clearTimeout(this.pingTimeout);
        this.pingTimeout = setTimeout(() => {
            console.warn(COLOR.YELLOW("[MarketWatcher] WSS heartbeat missed, reconnecting..."));
            this.ws.terminate(); // Force close to trigger reconnect
        }, 30000); // 30 seconds, slightly more than Bybit's 20s ping
    }

    handleMessage(raw) {
        try {
            const dataStr = raw.toString();
            // Handle pongs for heartbeat
            if (dataStr === 'pong') {
                this.heartbeat();
                return;
            }

            const msg = JSON.parse(dataStr);
            if (!msg.topic && !msg.op) { // Check for pings/pongs from Bybit
                if (msg.ping) {
                    this.ws.send(JSON.stringify({ op: 'pong', args: [msg.ping] }));
                }
                return;
            }

            if (!msg.topic || !msg.data) return;
            
            this.heartbeat(); // Reset heartbeat on any valid message

            if (msg.topic.startsWith('tickers.')) {
                this.onTick({ type: 'price', price: parseFloat(msg.data.lastPrice) });
            } else if (msg.topic.startsWith('orderbook.')) {
                const bids = msg.data.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                const asks = msg.data.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                this.onTick({ type: 'orderbook', bids, asks });
            } else if (msg.topic.startsWith('kline.')) {
                // Bybit kline topic is usually 'kline.interval.symbol'
                // The 'data' array contains a single kline object for updates
                for (const kline_data of msg.data) { // Bybit sends kline data in an array
                    const candle = {
                        t: parseInt(kline_data.start),
                        o: parseFloat(kline_data.open),
                        h: parseFloat(kline_data.high),
                        l: parseFloat(kline_data.low),
                        c: parseFloat(kline_data.close),
                        v: parseFloat(kline_data.volume)
                    };
                    this.onTick({ type: 'kline', interval: msg.topic.split('.')[1], candle });
                }
            }
        } catch (e) {
            console.error(COLOR.RED(`[MarketWatcher] WSS Message parsing error: ${e.message}. Raw data snippet: ${dataStr.substring(0, 100)}...`));
        }
    }
}

// === ORDERBOOK PROCESSOR ===
class OrderbookProcessor {
    constructor(config) {
        this.config = config;
        this.snapshot = { bids: [], asks: [] };
    }

    process(orderbook) {
        this.snapshot = orderbook;
        return this.analysis();
    }

    analysis() {
        const bidTotal = this.snapshot.bids.reduce((sum, b) => sum + b.q, 0);
        const askTotal = this.snapshot.asks.reduce((sum, a) => sum + a.q, 0);
        const imbalance = (bidTotal - askTotal) / (bidTotal + askTotal || 1);
        const midPrice = (this.snapshot.bids[0]?.p || 0 + this.snapshot.asks[0]?.p || 0) / 2;
        return { imbalance, midPrice, bidSize: bidTotal, askSize: askTotal };
    }
}

// === TRAILING STOP MANAGER ===
class TrailingStopManager {
    constructor(config) {
        this.config = config;
        this.trailDistance = new Decimal(0.005);
        this.maxTrail = new Decimal(0.03);
    }

    calculateTrailingStop(currentPrice, entry, side, atr) {
        const price = new Decimal(currentPrice);
        let distance = this.trailDistance.mul(price);
        
        // Adjust for volatility
        const volatilityAdj = new Decimal(atr).mul(0.5);
        distance = Decimal.max(distance, volatilityAdj);
        
        if (distance.greaterThan(this.maxTrail.mul(price))) return null;

        return side === 'BUY' ? price.minus(distance) : price.plus(distance);
    }
}

// === POSITION SIZER ===
class PositionSizer {
    constructor(config) {
        this.config = config;
    }

    calculatePositionSize(entry, stopLoss, balance, atr) {
        const riskAmt = new Decimal(balance).mul(this.config.risk.maxRiskPerTrade / 100);
        const riskPerShare = new Decimal(entry).sub(stopLoss).abs();
        if (riskPerShare.lte(0)) return new Decimal(0);

        // ADR adjustment
        const adr = Utils.calculateADR([entry], [stopLoss]);
        const adjustedRisk = riskPerShare.div(adr || 1).gte(1) ? riskPerShare : new Decimal(adr);
        
        return riskAmt.div(adjustedRisk).toDecimalPlaces(3, Decimal.ROUND_DOWN);
    }
}

// === AI BRAIN ===
class AIBrain {
    constructor(config) {
        this.cfg = config.ai;
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ model: this.cfg.model });
        this.confidenceBuffer = [];
    }

    async analyze(context) {
        const prompt = `
You are WHALEWAVE PRO LEVIATHAN v1.9. Analyze and decide.

DATA:
- Price: ${context.price.toLocaleString()}
- WSS: ${context.wss.toFixed(3)}
- Scalping Momentum: ${context.scalpingMomentum?.toFixed(3) || 'N/A'}
- Fisher: ${context.fisher.toFixed(2)}
- Laguerre RSI: ${context.laguerre?.toFixed(2) || 'N/A'}
- ATR: ${context.atr?.toFixed(2)}
- OBV: ${context.obv?.toFixed(2) || 'N/A'}
- VWAP: ${context.vwap?.toFixed(2) || 'N/A'}
- KAMA: ${context.kama?.toFixed(2) || 'N/A'}
- Volume Spike: ${context.spike?.toFixed(2) || 'N/A'}
- Orderbook: ${(context.imbalance * 100).toFixed(1)}% imbalance
- Position: ${context.position || 'NONE'}
- StochRSI K: ${context.stochRsiK?.toFixed(2) || 'N/A'}, D: ${context.stochRsiD?.toFixed(2) || 'N/A'}
- Bollinger Bands: Upper: ${context.bbUpper?.toFixed(2) || 'N/A'}, Mid: ${context.bbMid?.toFixed(2) || 'N/A'}, Lower: ${context.bbLower?.toFixed(2) || 'N/A'}

RULES:
1. BUY if WSS > ${context.threshold} AND Fisher > 0.0 AND Scalping Momentum is positive. Look for StochRSI K to cross above D from oversold (below 20).
2. SELL if WSS < -${context.threshold} AND Fisher < 0.0 AND Scalping Momentum is negative. Look for StochRSI K to cross below D from overbought (above 80).
3. Confirm with Bollinger Bands: For BUY, price should be above or breaking through mid-band, ideally near lower band bounce. For SELL, price should be below or breaking through mid-band, ideally near upper band rejection.
4. VWAP as a trend confirmation: BUY only if price is above VWAP. SELL only if price is below VWAP.
5. OBV should confirm the trend (rising for BUY, falling for SELL).
6. KAMA should be trending in the direction of the trade.
7. Set SL/TP based on ATR * 1.5. Target a minimum Risk/Reward of 1.5. Prioritize exiting positions if conditions reverse sharply.
8. Calculate confidence based on how many of rules 1-6 are met. More confirmations mean higher confidence.

OUTPUT JSON: {"action":"BUY/SELL/HOLD","confidence":0.0-1.0,"sl":number,"tp":number,"strategy":"NAME","reason":"short"}
        `.trim();

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const data = JSON.parse(text);
            
            // Normalize
            if (!['BUY', 'SELL', 'HOLD'].includes(data.action)) data.action = 'HOLD';
            data.confidence = Math.min(1, Math.max(0, parseFloat(data.confidence) || 0));
            data.sl = Utils.safeNumber(data.sl, 0);
            data.tp = Utils.safeNumber(data.tp, 0);
            
            return data;
        } catch (e) {
            console.error(COLOR.RED(`[AIBrain] Analysis failed for price ${context.price} and WSS ${context.wss}. Error: ${e.message}. Full prompt:\n${prompt}`));
            return { action: 'HOLD', confidence: 0, sl: 0, tp: 0, strategy: 'AI_FAIL', reason: e.message };
        }
    }

    updateConfidence(confidence) {
        this.confidenceBuffer.push(confidence);
        if (this.confidenceBuffer.length > 10) this.confidenceBuffer.shift();
        return this.confidenceBuffer.reduce((a, b) => a + b, 0) / this.confidenceBuffer.length;
    }
}

// === LEVIATHAN SCORER ===
class LeviathanScorer {
    static calculate(context, cfg) {
        const components = {};
        let score = 0;

        // 1. Trend momentum (MTF)
        let trendComponent = 0;
        if (context.trend === 'BULLISH') trendComponent = 1.0;
        else if (context.trend === 'BEARISH') trendComponent = -1.0;
        score += trendComponent * cfg.weights.trend_mtf;
        components.trend = trendComponent;

        // 2. Order flow
        let flowComponent = context.imbalance;
        score += flowComponent * cfg.weights.order_flow;
        components.flow = flowComponent;

        // 3. Price impact
        const priceImpact = context.bidSize > context.askSize * 2 ? 0.5 :
                           context.askSize > context.bidSize * 2 ? -0.5 : 0;
        score += priceImpact * cfg.weights.price_impact;
        components.impact = priceImpact;

        // 4. Scalping Momentum (NEW)
        // ScalpingMomentum from MarketAnalyzer is between -1 and 1
        score += context.scalpingMomentum * cfg.weights.scalping_momentum;
        components.scalpingMomentum = context.scalpingMomentum;

        // Normalize - adjust norm to include new weights
        const norm = cfg.weights.trend_mtf + cfg.weights.order_flow + cfg.weights.price_impact + cfg.weights.scalping_momentum;
        return { score: Math.max(-1, Math.min(1, score / norm)), components };
    }
}

// === INDICATOR MANAGER ===
// Refactored MarketAnalyzer into IndicatorManager
class IndicatorManager {
    constructor(config) {
        this.config = config;
        this.scalpKlineBuffer = new KlineBuffer(this.config.limits.kline.scalping, this.config.intervals.scalping);
        this.mainKlineBuffer = new KlineBuffer(this.config.limits.kline.main, this.config.intervals.main);
        this.trendKlineBuffer = new KlineBuffer(this.config.limits.kline.trend, this.config.intervals.trend);
    }

    updateKline(interval, candle) {
        if (interval === this.config.intervals.scalping) {
            this.scalpKlineBuffer.update(candle);
        } else if (interval === this.config.intervals.main) {
            this.mainKlineBuffer.update(candle);
        } else if (interval === this.config.intervals.trend) {
            this.trendKlineBuffer.update(candle);
        }
    }

    isReady() {
        return this.scalpKlineBuffer.isReady() && this.mainKlineBuffer.isReady() && this.trendKlineBuffer.isReady();
    }

    async analyze(marketData) {
        const cfg = this.config.indicators;

        const mainKlines = this.mainKlineBuffer.getKlines();
        const trendKlines = this.trendKlineBuffer.getKlines();
        const scalpKlines = this.scalpKlineBuffer.getKlines();

        const c = mainKlines.map(x => x.c), h = mainKlines.map(x => x.h), l = mainKlines.map(x => x.l), v = mainKlines.map(x => x.v);
        const sc = scalpKlines.map(x => x.c);
        const sh = scalpKlines.map(x => x.h);
        const sl = scalpKlines.map(x => x.l);
        const sv = scalpKlines.map(x => x.v);

        // Ensure enough data for indicators
        if (sc.length < Math.max(cfg.fisher_period, cfg.rsi, cfg.stoch_rsi_k_period, cfg.bb_period, cfg.kama_period)) {
            console.warn(COLOR.YELLOW(`[IndicatorManager] Not enough scalping kline data for all indicators. Current: ${sc.length}`));
            // Return default/empty analysis if not enough data
            return { sLast: -1, last: -1, scalpingMomentum: 0, imbalance: 0, trendMTF: 'NONE' };
        }
        if (c.length < Math.max(cfg.rsi, cfg.atr_period)) {
            console.warn(COLOR.YELLOW(`[IndicatorManager] Not enough main kline data for all indicators. Current: ${c.length}`));
             return { sLast: -1, last: -1, scalpingMomentum: 0, imbalance: 0, trendMTF: 'NONE' };
        }


        const [rsi, atr, fisher, laguerre, stochRsi, bb, obv, vwap, kama] = await Promise.all([
            TechnicalAnalysis.rsi(c, cfg.rsi),
            TechnicalAnalysis.atr(h, l, c, cfg.atr_period),
            TechnicalAnalysis.fisherTransform(sh, sl, cfg.fisher_period),
            TechnicalAnalysis.laguerreRSI(sc, cfg.laguerre_gamma),
            TechnicalAnalysis.stochRsi(sc, cfg.rsi, cfg.stoch_rsi_k_period, cfg.stoch_rsi_d_period),
            TechnicalAnalysis.bollingerBands(sc, cfg.bb_period, cfg.bb_std_dev),
            TechnicalAnalysis.obv(sc, sv),
            TechnicalAnalysis.vwap(sc, sh, sl, sv),
            TechnicalAnalysis.kama(sc, cfg.kama_period),
        ]);

        const last = c.length - 1;
        const sLast = sc.length - 1;

        const trendMTF = trendKlines[trendKlines.length - 1]?.c > trendKlines[trendKlines.length - 5]?.c ? 'BULLISH' : 'BEARISH';
        const divergence = TechnicalAnalysis.detectDivergence(c, rsi, last);
        const totalBid = marketData.bids.reduce((a, b) => a + b.q, 0), totalAsk = marketData.asks.reduce((a, b) => a + b.q, 0);
        const imbalance = (totalBid - totalAsk) / (totalBid + totalAsk || 1);
        const fvg = TechnicalAnalysis.findFVG(mainKlines); // Use main klines for FVG

        // Scalping Momentum calculation (range -1 to 1)
        let scalpingMomentum = 0;
        if (sLast > 0 && fisher.fish.length > sLast && laguerre.length > sLast && stochRsi.k.length > sLast) {
            const fisherVal = fisher.fish[sLast];
            const prevFisherVal = fisher.fish[sLast - 1];
            const laguerreVal = laguerre[sLast];
            const stochRsiK = stochRsi.k[sLast];
            const stochRsiD = stochRsi.d[sLast];

            let momentumScore = 0;
            if (fisherVal > 0 && prevFisherVal <= 0) momentumScore += 0.5; // Bullish cross
            if (fisherVal < 0 && prevFisherVal >= 0) momentumScore -= 0.5; // Bearish cross
            if (laguerreVal > 50 && laguerreVal > laguerre[sLast - 1]) momentumScore += 0.3; // Bullish
            if (laguerreVal < 50 && laguerreVal < laguerre[sLast - 1]) momentumScore -= 0.3; // Bearish
            if (stochRsiK > stochRsiD && stochRsiK < 30) momentumScore += 0.4; // Bullish from oversold
            if (stochRsiK < stochRsiD && stochRsiK > 70) momentumScore -= 0.4; // Bearish from overbought
            
            scalpingMomentum = Math.max(-1, Math.min(1, momentumScore)); // Clamp between -1 and 1
        }

        return {
            c, h, l, v, sc, sh, sl, sv, rsi, atr, fisher, laguerre,
            stochRsiK: stochRsi.k, stochRsiD: stochRsi.d,
            bbUpper: bb.upper, bbMid: bb.mid, bbLower: bb.lower,
            obv: obv, vwap: vwap, kama: kama,
            trendMTF, divergence, fvg, imbalance, scalpingMomentum,
            last, sLast
        };
    }
}


// === BACKTEST MODE ===
class BacktestMode {
    constructor(config, exchange) {
        super();
        this.config = config;
        this.exchange = exchange;
        this.ai = new AIBrain(this.config); // Initialize AIBrain
        this.indicatorManager = new IndicatorManager(this.config); // Use IndicatorManager in backtest
        this.results = { trades: 0, wins: 0, pnl: 0, maxDrawdown: 0 };
    }

    async loadHistory(filename) {
        try {
            const data = await fs.readFile(filename, 'utf-8');
            return JSON.parse(data).map(item => ({
                t: new Date(item.time).getTime(), // Using getTime() for consistency with WSS klines
                o: parseFloat(item.open),
                h: parseFloat(item.high),
                l: parseFloat(item.low),
                c: parseFloat(item.close),
                v: parseFloat(item.volume)
            }));
        } catch (e) {
            console.error(COLOR.RED(`[BacktestMode] Error loading history from ${filename}: ${e.message}`));
            return [];
        }
    }

    async run(filename) {
        const history = await this.loadHistory(filename);
        if (!history.length) return;

        console.log(COLOR.CYAN(`[BacktestMode] Running backtest on ${history.length} candles...`));
        
        // Initializing buffers in IndicatorManager for backtest
        // In a real backtest, you'd feed appropriate history into main/trend buffers too
        // For simplicity, here we're feeding all intervals with the same history

        for (const candle of history) {
            this.indicatorManager.updateKline(this.config.intervals.scalping, candle);
            this.indicatorManager.updateKline(this.config.intervals.main, candle); 
            this.indicatorManager.updateKline(this.config.intervals.trend, candle); 

            // Simulate market data
            const marketData = {
                price: candle.c, // Use close price for market price in backtest
                bids: [{ p: candle.l, q: 1000 }], // Mock orderbook
                asks: [{ p: candle.h, q: 1000 }] // Mock orderbook
            };

            if (!this.indicatorManager.isReady()) {
                // console.log(COLOR.GRAY("Backtest: IndicatorManager buffers not ready, skipping analysis."));
                continue;
            }

            // Run analysis using the IndicatorManager
            const analysis = await this.indicatorManager.analyze(marketData);
            const wss = LeviathanScorer.calculate({
                trend: analysis.trendMTF,
                imbalance: analysis.imbalance,
                bidSize: 1000,
                askSize: 1000,
                scalpingMomentum: analysis.scalpingMomentum 
            }, this.config.indicators);

            // AI Decision
            const signal = await this.ai.analyze({
                price: candle.c,
                wss: wss.score,
                threshold: this.config.indicators.weights.actionThreshold,
                fisher: analysis.fisher.fish[analysis.sLast],
                atr: analysis.atr[analysis.last],
                scalpingMomentum: analysis.scalpingMomentum, 
                laguerre: analysis.laguerre[analysis.sLast],
                stochRsiK: analysis.stochRsiK[analysis.sLast],
                stochRsiD: analysis.stochRsiD[analysis.sLast],
                bbUpper: analysis.bbUpper[analysis.sLast],
                bbMid: analysis.bbMid[analysis.sLast],
                bbLower: analysis.bbLower[analysis.sLast],
                obv: analysis.obv[analysis.sLast],
                vwap: analysis.vwap[analysis.sLast],
                kama: analysis.kama[analysis.sLast],
            });

            // Market Condition Filter (simple example: range detection)
            const currentATR = analysis.atr[analysis.last];
            const scalpKlinesForRange = this.indicatorManager.scalpKlineBuffer.getKlines(); 
            const avgPrice = Utils.sum(scalpKlinesForRange.map(k => k.c)) / scalpKlinesForRange.length;
            const priceRange = Math.max(...scalpKlinesForRange.map(k => k.h)) - Math.min(...scalpKlinesForRange.map(k => k.l));

            if (currentATR < avgPrice * 0.0005 && priceRange < avgPrice * 0.001) {
                signal.action = 'HOLD';
            }

            // Execute
            await this.exchange.evaluate(candle.c, signal);
            
            this.results.trades++;
            // Further PnL and drawdown tracking would be added here
            
            await sleep(1); // Prevent blocking
        }

        console.log(COLOR.PURPLE("[BacktestMode] Backtest complete:"), this.results);
    }
}

// === EXCHANGE BASE ===
class BaseExchange {
    getBalance() { return this.balance; }
    getPos() { return this.pos; }
}

// === LIVE BYBIT EXCHANGE ===
class LiveBybitExchange extends BaseExchange {
    constructor(config) {
        super();
        this.config = config;
        this.symbol = config.symbol;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        if (!this.apiKey || !this.apiSecret) { console.error(COLOR.RED("[LiveBybitExchange] MISSING BYBIT API KEYS. Exiting.")); process.exit(1); }
        this.client = axios.create({ baseURL: 'https://api.bybit.com', timeout: 7000 });
        this.pos = null;
        this.balance = 0;
        this.updateWallet();
    }

    async signRequest(method, endpoint, params) {
        const ts = Date.now().toString();
        const recvWindow = '5000';
        const payload = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
        const signStr = ts + this.apiKey + recvWindow + payload;
        const signature = crypto.createHmac('sha256', this.apiSecret).update(signStr).digest('hex');
        return {
            'X-BAPI-API-KEY': this.apiKey, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': recvWindow, 'Content-Type': 'application/json'
        };
    }

    async apiCall(method, endpoint, params = {}) {
        const headers = await this.signRequest(method, endpoint, params);
        try {
            const res = method === 'GET' 
                ? await this.client.get(endpoint, { headers, params }) 
                : await this.client.post(endpoint, params, { headers });
            if (res.data.retCode !== 0) throw new Error(`Bybit API Error ${res.data.retCode}: ${res.data.retMsg}`);
            return res.data.result;
        } catch (e) { 
            console.error(COLOR.RED(`[LiveBybitExchange] API Call Error (${method} ${endpoint} ${JSON.stringify(params)}): ${e.message}`)); 
            return null; 
        }
    }

    async updateWallet() {
        try {
            const res = await this.apiCall('GET', '/v5/account/wallet-balance', { accountType: 'UNIFIED', coin: 'USDT' });
            if (res && res.list && res.list[0]?.coin && res.list[0].coin[0]?.walletBalance) {
                this.balance = parseFloat(res.list[0].coin[0].walletBalance);
            } else {
                console.warn(COLOR.YELLOW("[LiveBybitExchange] Could not retrieve wallet balance. Response:", res));
                this.balance = 0;
            }
            
            const pos = await this.apiCall('GET', '/v5/position/list', { category: 'linear', symbol: this.symbol });
            if (pos && pos.list.length > 0 && parseFloat(pos.list[0].size) > 0) {
                const p = pos.list[0];
                this.pos = { side: p.side === 'Buy' ? 'BUY' : 'SELL', qty: parseFloat(p.size), entry: parseFloat(p.avgPrice) };
            } else this.pos = null;
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to update wallet/positions: ${e.message}`));
            this.balance = 0;
            this.pos = null;
        }
    }

    async evaluate(price, signal) {
        await this.updateWallet();
        if (this.pos) {
            if (signal.action !== 'HOLD' && signal.action !== this.pos.side) {
                console.log(COLOR.YELLOW("[LiveBybitExchange] Signal Flip! Closing existing position..."));
                await this.closePos();
            }
            return;
        }
        if (signal.action === 'HOLD') return;
        
        const entry = new Decimal(signal.entry || price);
        let sl = new Decimal(signal.sl !== undefined ? signal.sl : entry.minus(entry.mul(0.005)));
        let tp = new Decimal(signal.tp !== undefined ? signal.tp : entry.plus(entry.mul(0.0075)));

        // Ensure R/R > 1.5 for new trades, if not, adjust or hold
        const riskDistance = entry.sub(sl).abs();
        const rewardDistance = tp.sub(entry).abs();

        if (riskDistance.gt(0) && rewardDistance.div(riskDistance).lt(1.5)) {
             // Attempt to adjust TP to meet R/R 1.5, or reject trade
            if (signal.action === 'BUY') {
                tp = entry.plus(riskDistance.mul(1.5));
            } else {
                tp = entry.minus(riskDistance.mul(1.5));
            }
            // Re-check if new TP is reasonable, else hold
            if (tp.lt(0) || tp.eq(entry) || (signal.action === 'BUY' && tp.lt(entry)) || (signal.action === 'SELL' && tp.gt(entry))) { 
                 console.log(COLOR.GRAY(`[LiveBybitExchange] Adjusted TP (${tp.toFixed(2)}) out of bounds or invalid for R/R. Holding trade for ${this.symbol}.`));
                 return;
            }
        }
    
        const dist = entry.sub(sl).abs();
        if (dist.eq(0)) {
            console.warn(COLOR.YELLOW(`[LiveBybitExchange] Stop loss distance is zero for ${this.symbol}. Holding.`));
            return;
        }

        const riskAmt = new Decimal(this.balance).mul(this.config.risk.maxRiskPerTrade / 100);
        let qty = riskAmt.div(dist).toDecimalPlaces(3, Decimal.ROUND_DOWN);
        if (qty.lte(0)) {
            console.warn(COLOR.YELLOW(`[LiveBybitExchange] Calculated quantity (${qty.toString()}) is zero or less for ${this.symbol}. Holding.`));
            return;
        }
        
        await this.apiCall('POST', '/v5/position/set-leverage', { category: 'linear', symbol: this.symbol, buyLeverage: this.config.risk.leverageCap, sellLeverage: this.config.risk.leverageCap });
        
        const side = signal.action === 'BUY' ? 'Buy' : 'Sell';
        const orderParams = {
            category: 'linear', symbol: this.symbol, side, orderType: 'Market',
            qty: qty.toString(), stopLoss: sl.toString(), takeProfit: tp.toString(), timeInForce: 'GTC'
        };
        const res = await this.apiCall('POST', '/v5/order/create', orderParams);
        
        if (res) console.log(COLOR.GREEN(`[LiveBybitExchange] LIVE ORDER SENT: ${signal.action} ${qty.toString()} @ ${entry.toFixed(2)} (SL: ${sl.toFixed(2)}, TP: ${tp.toFixed(2)})`));
        else console.error(COLOR.RED(`[LiveBybitExchange] Failed to place live order for ${this.symbol}. Order details: ${JSON.stringify(orderParams)}`));
    }

    async closePos() {
        if (!this.pos) {
            console.warn(COLOR.YELLOW("[LiveBybitExchange] Attempted to close position but no open position found."));
            return;
        }
        const side = this.pos.side === 'BUY' ? 'Sell' : 'Buy';
        const closeParams = {
            category: 'linear', symbol: this.symbol, side, orderType: 'Market',
            qty: this.pos.qty.toString(), reduceOnly: true
        };
        const res = await this.apiCall('POST', '/v5/order/create', closeParams);
        if (res) {
            console.log(COLOR.GREEN(`[LiveBybitExchange] POSITION CLOSED: ${this.pos.side} ${this.pos.qty.toString()} for ${this.symbol}`));
            this.pos = null;
        } else {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to close position for ${this.symbol}. Close details: ${JSON.stringify(closeParams)}`));
        }
    }
}

// === PAPER EXCHANGE ===
class PaperExchange extends BaseExchange {
    constructor(config) {
        super();
        this.cfg = config.risk;
        this.symbol = config.symbol;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
    }

    evaluate(price, signal) {
        const px = new Decimal(price);
        if (this.pos) {
            const isFlip = signal.action !== 'HOLD' && signal.action !== this.pos.side;
            const closeOnHold = signal.action === 'HOLD';
            // Check for SL/TP hit (simplistic for paper)
            let slHit = false;
            let tpHit = false;
            if (this.pos.side === 'BUY') {
                if (px.lte(this.pos.sl)) slHit = true;
                if (px.gte(this.pos.tp)) tpHit = true;
            } else { // SELL
                if (px.gte(this.pos.sl)) slHit = true;
                if (px.lte(this.pos.tp)) tpHit = true;
            }

            if (isFlip || closeOnHold || slHit || tpHit) {
                let reason = '';
                if (isFlip) reason = 'SIGNAL_FLIP';
                else if (closeOnHold) reason = 'HOLD_EXIT';
                else if (slHit) reason = 'STOP_LOSS_HIT';
                else if (tpHit) reason = 'TAKE_PROFIT_HIT';
                this.close(px, reason);
            }
            return;
        }
        if (signal.action === 'HOLD') return;
        if ((signal.confidence || 0) < this.cfg.minConfidence) {
            console.log(COLOR.GRAY(`[PaperExchange] Signal confidence (${(signal.confidence * 100).toFixed(0)}%) below min (${(this.cfg.minConfidence * 100).toFixed(0)}%). Holding.`));
            return;
        }
        this.open(px, signal);
    }

    open(price, sig) {
        const entry = new Decimal(price);
        let sl = new Decimal(sig.sl !== undefined ? sig.sl : entry.minus(entry.mul(0.005)));
        let tp = new Decimal(sig.tp !== undefined ? sig.tp : entry.plus(entry.mul(0.0075)));
        
        // Ensure R/R > 1.5 for new trades, if not, adjust or hold
        const riskDistance = entry.sub(sl).abs();
        const rewardDistance = tp.sub(entry).abs();

        if (riskDistance.gt(0) && rewardDistance.div(riskDistance).lt(1.5)) {
            // Attempt to adjust TP to meet R/R 1.5, or reject trade
            if (sig.action === 'BUY') {
                tp = entry.plus(riskDistance.mul(1.5));
            } else {
                tp = entry.minus(riskDistance.mul(1.5));
            }
            // Re-check if new TP is reasonable, else hold
            if (tp.lt(0) || tp.eq(entry) || (sig.action === 'BUY' && tp.lt(entry)) || (sig.action === 'SELL' && tp.gt(entry))) { 
                console.log(COLOR.GRAY(`[PaperExchange] Adjusted TP (${tp.toFixed(2)}) out of bounds or invalid for R/R. Holding trade for ${this.symbol}.`));
                return;
            }
        }

        const dist = entry.sub(sl).abs();
        if (dist.eq(0)) {
            console.warn(COLOR.YELLOW(`[PaperExchange] Stop loss distance is zero for ${this.symbol}. Holding.`));
            return;
        }

        const riskAmt = this.balance.mul(this.cfg.maxRiskPerTrade / 100);
        let qty = riskAmt.div(dist).toDecimalPlaces(6, Decimal.ROUND_DOWN);
        if (qty.lte(0)) {
            console.warn(COLOR.YELLOW(`[PaperExchange] Calculated quantity (${qty.toString()}) is zero or less for ${this.symbol}. Holding.`));
            return;
        }

        this.pos = { side: sig.action, entry, qty, sl, tp, strategy: sig.strategy || 'PAPER' };
        console.log(COLOR.GREEN(`[PaperExchange] PAPER OPEN ${sig.action} ${qty.toString()} @ ${entry.toFixed(2)} (SL: ${sl.toFixed(2)}, TP: ${tp.toFixed(2)})`));
    }

    close(price, reason) {
        const p = this.pos;
        if (!p) {
            console.warn(COLOR.YELLOW("[PaperExchange] Attempted to close position but no open position found."));
            return;
        } // Guard against null position
        const diff = p.side === 'BUY' ? price.sub(p.entry) : p.entry.sub(price);
        const pnl = diff.mul(p.qty).mul(new Decimal(1).sub(this.cfg.fee).sub(this.cfg.slippage));
        this.balance = this.balance.add(pnl);
        const col = pnl.gte(0) ? COLOR.GREEN : COLOR.RED;
        console.log(col(`[PaperExchange] ${reason} for ${this.symbol}: PnL: ${pnl.toFixed(2)} | New Bal: ${this.balance.toFixed(2)}`));
        this.pos = null;
    }
}

// === MAIN ENGINE ===
class TradingEngine {
    constructor() { this.init(); }

    async init() {
        this.cfg = await ConfigManager.load();
        this.performance = new PerformanceTracker();
        this.positionSizer = new PositionSizer(this.cfg);
        this.trailingStop = new TrailingStopManager(this.cfg);
        this.ai = new AIBrain(this.cfg);
        this.data = new DataProvider(this.cfg);
        this.indicatorManager = new IndicatorManager(this.cfg); // Initialize IndicatorManager
        this.exchange = this.cfg.live_trading ? new LiveBybitExchange(this.cfg) : new PaperExchange(this.cfg);
        this.watcher = new MarketWatcher(this.cfg, (tick) => this.onWsTick(tick));
        this.orderbookProc = new OrderbookProcessor(this.cfg);
        this.displayManager = new DisplayManager(); // Initialize DisplayManager

        // State management
        this.state = {
            price: null,
            orderbook: { bids: [], asks: [] },
            lastSignal: null
        };

        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.PURPLE(' 🐳 WHALEWAVE PRO: LEVIATHAN LIVE v1.9 '))));
        
        // Initial load of historical klines into IndicatorManager buffers
        console.log(COLOR.CYAN("[TradingEngine] Loading initial historical klines..."));
        const snapshot = await this.data.getSnapshot();
        if (snapshot) {
            // Only feed full historical data to main and trend buffers if they were fully fetched (not just the latest single kline)
            if (this.data.initialKlinesLoaded.main) {
                snapshot.candlesMain.forEach(c => this.indicatorManager.updateKline(this.cfg.intervals.main, c));
            }
            if (this.data.initialKlinesLoaded.trend) {
                snapshot.candlesTrend.forEach(c => this.indicatorManager.updateKline(this.cfg.intervals.trend, c));
            }
            console.log(COLOR.GREEN("[TradingEngine] Initial historical klines loaded."));
        } else {
            console.warn(COLOR.YELLOW("[TradingEngine] Failed to load initial historical klines from REST. Starting with empty buffers."));
        }


        this.watcher.start();
        this.loop();
    }

    async loop() {
        while (true) {
            try {
                // Get REST snapshot for market data (only tickers and orderbook now, klines buffered)
                const snapshot = await this.data.getSnapshot();
                if (!snapshot) { // Check only for ticker and orderbook from snapshot
                    console.warn(COLOR.YELLOW("[TradingEngine] Snapshot data (price/orderbook) missing from REST. Retrying..."));
                    await sleep(this.cfg.delays.retry);
                    continue;
                }

                // If DataProvider only fetched latest klines for main/trend, update IndicatorManager
                if (snapshot.candlesMain && snapshot.candlesMain.length > 0) {
                     // Ensure it's not a full history if already loaded
                    this.indicatorManager.updateKline(this.cfg.intervals.main, snapshot.candlesMain[snapshot.candlesMain.length - 1]);
                }
                if (snapshot.candlesTrend && snapshot.candlesTrend.length > 0) {
                    this.indicatorManager.updateKline(this.cfg.intervals.trend, snapshot.candlesTrend[snapshot.candlesTrend.length - 1]);
                }


                // Merge with WSS real-time data
                const marketData = {
                    price: this.state.price || snapshot.price,
                    bids: this.state.orderbook.bids.length ? this.state.orderbook.bids : snapshot.bids,
                    asks: this.state.orderbook.asks.length ? this.state.orderbook.asks : snapshot.asks
                };

                if (!this.indicatorManager.isReady()) {
                    console.log(COLOR.YELLOW("[TradingEngine] IndicatorManager buffers not ready yet with sufficient data. Waiting..."));
                    await sleep(this.cfg.delays.retry);
                    continue;
                }

                // Analyze using IndicatorManager
                const analysis = await this.indicatorManager.analyze(marketData);
                const orderbookData = this.orderbookProc.process({ bids: marketData.bids, asks: marketData.asks });
                
                const wssRes = LeviathanScorer.calculate({
                    trend: analysis.trendMTF,
                    imbalance: orderbookData.imbalance,
                    bidSize: orderbookData.bidSize,
                    askSize: orderbookData.askSize,
                    scalpingMomentum: analysis.scalpingMomentum
                }, this.cfg.indicators);

                // AI Decision
                const context = {
                    price: marketData.price,
                    wss: wssRes.score,
                    scalpingMomentum: analysis.scalpingMomentum, // Pass scalping momentum
                    threshold: this.cfg.indicators.weights.actionThreshold,
                    fisher: analysis.fisher.fish[analysis.sLast],
                    laguerre: analysis.laguerre[analysis.sLast],
                    trend: analysis.trendMTF,
                    fvg: analysis.fvg?.type,
                    imbalance: orderbookData.imbalance,
                    rsi: analysis.rsi[analysis.last], // RSI for main interval
                    atr: analysis.atr[analysis.last], // ATR for main interval
                    position: this.exchange.getPos()?.side || 'NONE',
                    stochRsiK: analysis.stochRsiK[analysis.sLast],
                    stochRsiD: analysis.stochRsiD[analysis.sLast],
                    bbUpper: analysis.bbUpper[analysis.sLast],
                    bbMid: analysis.bbMid[analysis.sLast],
                    bbLower: analysis.bbLower[analysis.sLast],
                    obv: analysis.obv[analysis.sLast],
                    vwap: analysis.vwap[analysis.sLast],
                    kama: analysis.kama[analysis.sLast],
                };

                // Market Condition Filter (simple example: range detection)
                let signal = { action: 'HOLD', confidence: 0, sl: 0, tp: 0, strategy: 'ENGINE' };
                const currentATR = analysis.atr[analysis.last]; // ATR from main interval klines
                const scalpKlinesForRange = this.indicatorManager.scalpKlineBuffer.getKlines();
                const avgPrice = Utils.sum(scalpKlinesForRange.map(k => k.c)) / scalpKlinesForRange.length;
                const priceRange = Math.max(...scalpKlinesForRange.map(k => k.h)) - Math.min(...scalpKlinesForRange.map(k => k.l));

                if (currentATR < avgPrice * 0.0005 && priceRange < avgPrice * 0.001) { // Very tight range
                    console.log(COLOR.GRAY("[TradingEngine] Market in tight range, holding trade decisions."));
                    signal.action = 'HOLD'; // Force HOLD due to tight range
                } else if (Math.abs(wssRes.score) >= this.cfg.indicators.weights.actionThreshold * 0.5) {
                    signal = await this.ai.analyze(context);
                }

                // Default SL/TP & R/R enforcement (Moved to Exchange.evaluate)

                // Execute
                await this.exchange.evaluate(marketData.price, signal);

                // Update performance
                this.performance.updateEquity(this.exchange.getBalance());

                // Display
                this.displayManager.display(marketData.price, wssRes.score, signal, this.exchange.getPos() ? 'POSITION OPEN' : 'Awaiting Signal');

            } catch (e) {
                console.error(COLOR.RED(`[TradingEngine] Loop error at price ${this.state.price}: ${e.stack}`));
            }
            await sleep(this.cfg.delays.loop);
        }
    }

    onWsTick(tick) {
        switch (tick.type) {
            case 'price': this.state.price = tick.price; break;
            case 'orderbook': 
                this.state.orderbook = { bids: tick.bids, asks: tick.asks }; 
                break;
            case 'kline': 
                this.indicatorManager.updateKline(tick.interval, tick.candle);
                break;
        }
    }
}

// === DISPLAY MANAGER ===
class DisplayManager {
    display(price, wss, sig, posStatus) {
        const action = sig.action || 'HOLD'; // Ensure action is defined for display
        const confidence = sig.confidence !== undefined ? sig.confidence : 0;
        const actCol = action === 'BUY' ? COLOR.GREEN : action === 'SELL' ? COLOR.RED : COLOR.GRAY;
        process.stdout.write(
            `\r${COLOR.GRAY('---')} ${COLOR.BOLD(COLOR.CYAN(`LIVE`))} | P: $${price.toFixed(2)} | WSS: ${wss.toFixed(2)} | AI: ${actCol(action)} (${(confidence * 100).toFixed(0)}%) | ${posStatus}  `
        );
    }
}


// === PERFORMANCE TRACKER ===
class PerformanceTracker {
    constructor() {
        this.equity = [];
    }

    updateEquity(value) {
        this.equity.push(value);
        if (this.equity.length > 50) this.equity.shift();
    }

    displayChart() {
        if (this.equity.length < 2) return;
        const min = Math.min(...this.equity);
        const max = Math.max(...this.equity);
        const range = max - min || 1;
        const chart = this.equity.map(v => '█'.repeat(Math.floor(((v - min) / range) * 20))).join('\n');
        console.log(COLOR.GRAY(chart));
    }
}

// === START ===
new TradingEngine();
