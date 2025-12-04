/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Full TA Integration)
 * ======================================================
 * This is the main entry point for the trading bot.
 * UPDATE: Fully integrated 10 advanced indicators into the scoring engine.
 *
 * CONSOLIDATED:
 * - leviathan-v3/src/risk.js
 * - leviathan-v3/src/technical-analysis.js
 * - leviathan-v3/src/technical-analysis-advanced.js
 * - leviathan-v3/src/utils.js
 *
 * This consolidation is a temporary measure to diagnose and workaround module resolution issues
 * in the current environment where ES module imports for classes and functions are not
 * correctly preserving prototype chains or executable nature.
 */

import dotenv from 'dotenv';
import path from 'path'; // Import path module
import { Decimal } from 'decimal.js'; // Added for consolidated utils.js

// Ensure .env file is loaded from the leviathan-v3 directory.
// IMPORTANT: Do not commit your .env file to version control.
// It should contain your sensitive API keys (e.g., GEMINI_API_KEY, BYBIT_API_KEY, BYBIT_API_SECRET).
console.log(`[DEBUG] Current working directory: ${process.cwd()}`);
dotenv.config({ path: path.resolve(process.cwd(), 'leviathan-v3', '.env') }); // <-- Explicitly set the absolute path
console.log(`[DEBUG] GEMINI_API_KEY from .env (after path.resolve): ${process.env.GEMINI_API_KEY}`); // <-- Added debug log

import { ConfigManager } from './src/config.js';
// Removed: import { CircuitBreaker } from './src/risk.js';
// Removed: console.log('Imported CircuitBreaker:', CircuitBreaker); // Debug log removed

import { AIBrain } from './src/services/ai-brain.js';
import { MarketData } from './src/services/market-data.js';
import { LiveBybitExchange, PaperExchange } from './src/services/bybit-exchange.js';
// Removed: import * as TA from './src/technical-analysis.js';
// Removed: import * as TAA from './src/technical-analysis-advanced.js'; // Import Advanced TA
// Removed: import * as Utils from './src/utils.js';
import { renderHUD, COLOR } from './src/ui.js';

// --- CONSOLIDATED CODE FROM leviathan-v3/src/risk.js ---
/**
 * A circuit breaker to halt trading if the daily loss limit is exceeded.
 */
class CircuitBreaker { // Changed to class without export
    constructor(config) {
        this.maxLossPct = config.risk.maxDailyLoss;
        this.initialBalance = 0;
        this.currentPnL = 0;
        this.triggered = false;
        this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
    }

    setBalance(bal) {
        if (this.initialBalance === 0) this.initialBalance = bal;
        
        if (Date.now() > this.resetTime) {
            this.initialBalance = bal;
            this.currentPnL = 0;
            this.triggered = false;
            this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
            console.log(COLOR.GREEN(`[CircuitBreaker] Daily stats reset.`));
        }
    }

    updatePnL(pnl) {
        this.currentPnL += pnl;
        const lossPct = (Math.abs(this.currentPnL) / this.initialBalance) * 100;
        if (this.currentPnL < 0 && lossPct >= this.maxLossPct) {
            this.triggered = true;
            console.log(COLOR.bg(COLOR.RED(` 🚨 CIRCUIT BREAKER TRIGGERED: Daily Loss ${lossPct.toFixed(2)}% `)));
        }
    }

    isOpen() { // Added this method, as it was called in aisig.js but not present in the provided risk.js content.
        return this.triggered;
    }
    
    trip(reason) { // Added this method, as it was called in aisig.js but not present in the provided risk.js content.
        this.triggered = true;
        console.error(COLOR.RED(`[CircuitBreaker] TRIP forced by reason: ${reason}`));
    }
    
    reset() { // Added this method, if needed
        this.triggered = false;
        console.log(COLOR.GREEN(`[CircuitBreaker] Manually reset.`));
    }
}

// --- CONSOLIDATED CODE FROM leviathan-v3/src/utils.js ---
/**
 * A collection of pure utility functions for mathematical operations and data handling.
 */

/**
 * Creates a new array of a given length, filled with zeros.
 * @param {number} len The length of the array.
 * @returns {number[]} A new array filled with zeros.
 */
const safeArray = (len) => new Array(Math.max(0, Math.floor(len))).fill(0);

/**
 * Calculates the sum of all numbers in an array.
 * @param {number[]} arr The array of numbers.
 * @returns {number} The sum of the numbers.
 */
const sum = (arr) => arr.reduce((a, b) => a + b, 0);

/**
 * Calculates the average of numbers in an array.
 * @param {number[]} arr The array of numbers.
 * @returns {number} The average of the numbers.
 */
const average = (arr) => (arr && arr.length ? sum(arr) / arr.length : 0);

/**
 * Calculates the standard deviation of a slice of an array.
 * This is not optimal for per-tick updates but reflects the original logic.
 * @param {number[]} arr The array of numbers.
 * @param {number} period The period over which to calculate the standard deviation.
 * @returns {number[]} An array containing the standard deviation for each point.
 */
const stdDev = (arr, period) => {
    if (!arr || arr.length < period) return safeArray(arr.length);
    const result = safeArray(arr.length);
    for (let i = period - 1; i < arr.length; i++) {
        const slice = arr.slice(i - period + 1, i + 1);
        const mean = average(slice);
        const variance = average(slice.map(x => Math.pow(x - mean, 2)));
        result[i] = Math.sqrt(variance);
    }
    return result;
};

/**
 * Gets the current time as a formatted string.
 * @returns {string} Formatted time string (HH:MM:SS).
 */
const timestamp = () => new Date().toLocaleTimeString();

/**
 * Calculates the trade size based on balance and risk parameters.
 * @param {number|string} balance The total balance.
 * @param {number|string} entry The entry price.
 * @param {number|string} sl The stop-loss price.
 * @param {number} riskPct The percentage of the balance to risk.
 * @returns {Decimal} The calculated trade size.
 */
const calcSize = (balance, entry, sl, riskPct) => {
    const bal = new Decimal(balance);
    const ent = new Decimal(entry);
    const stop = new Decimal(sl);
    const riskAmt = bal.mul(riskPct).div(100);
    const riskPerCoin = ent.minus(stop).abs();
    
    if (riskPerCoin.eq(0)) return new Decimal(0);
    
    // Returns position size in base currency (e.g., BTC for BTCUSDT)
    return riskAmt.div(riskPerCoin).toDecimalPlaces(3, Decimal.ROUND_DOWN);
};

// --- CONSOLIDATED CODE FROM leviathan-v3/src/technical-analysis.js ---
/**
 * This file contains pure-function versions of the original technical analysis logic,
 * plus new standard indicators.
 */

// UTILITY INDICATORS (used by other indicators)
function ema(closes, period) {
    if (closes.length < period) return safeArray(closes.length);
    const results = safeArray(closes.length);
    const multiplier = 2 / (period + 1);
    
    // Initial value is a simple moving average
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += closes[i];
    }
    results[period - 1] = sum / period;

    // Calculate subsequent EMA values
    for (let i = period; i < closes.length; i++) {
        results[i] = (closes[i] - results[i - 1]) * multiplier + results[i - 1];
    }
    return results;
}

// PRIMARY INDICATORS
function rsi(closes, period = 14) { // Changed to function without export
    if (!closes.length || closes.length <= period) return safeArray(closes.length);
    
    let gains = [];
    let losses = [];
    for (let i = 1; i < closes.length; i++) {
        const diff = closes[i] - closes[i - 1];
        gains.push(Math.max(diff, 0));
        losses.push(Math.max(-diff, 0));
    }
    
    const rsi = safeArray(closes.length);
    if (gains.length < period) return rsi;

    let avgGain = average(gains.slice(0, period));
    let avgLoss = average(losses.slice(0, period));
    
    for(let i = period; i < closes.length; i++) {
        const change = closes[i] - closes[i-1];
        if (i === period) {
             const rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
             rsi[i] = 100 - (100 / (1 + rs));
             continue;
        }
        avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period;
        avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
        const rs = avgLoss === 0 ? Infinity : avgGain / avgLoss;
        rsi[i] = 100 - (100 / (1 + rs));
    }
    return rsi;
}

function fisher(highs, lows, period = 9) { // Changed to function without export
    const len = highs.length;
    const fish = safeArray(len);
    const value = safeArray(len);
    for (let i = 1; i < len; i++) {
        if (i < period) continue;
        let minL = Infinity, maxH = -Infinity;
        for (let j = 0; j < period; j++) {
            maxH = Math.max(maxH, highs[i-j]);
            minL = Math.min(minL, lows[i-j]);
        }
        let raw = 0;
        if (maxH !== minL) {
            raw = 0.66 * (((highs[i] + lows[i]) / 2) - minL) / (maxH - minL) - 0.5 + 0.67 * (value[i-1] || 0);
        }
        value[i] = Math.max(Math.min(raw, 0.99), -0.99);
        fish[i] = 0.5 * Math.log((1 + value[i]) / (1 - value[i])) + 0.5 * (fish[i-1] || 0);
    }
    return fish;
}

function atr(highs, lows, closes, period = 14) { // Changed to function without export
    const len = closes.length;
    const tr = safeArray(len);
    for(let i=1; i<len; i++) {
        tr[i] = Math.max(highs[i]-lows[i], Math.abs(highs[i]-closes[i-1]), Math.abs(lows[i]-closes[i-1]));
    }
    const atr = safeArray(len);
    let sum = 0;
    for(let i=0; i<len; i++) {
        sum += tr[i];
        if(i >= period) {
            sum -= tr[i-period];
            atr[i] = sum / period;
        }
    }
    return atr;
}

function bollinger(closes, period, stdDevMultiplier) { // Changed to function without export
    if (closes.length < period) return { upper: [], mid: [], lower: [] };
    const mid = safeArray(closes.length);
    const upper = safeArray(closes.length);
    const lower = safeArray(closes.length);
    for(let i = period - 1; i < closes.length; i++) {
        const slice = closes.slice(i - period + 1, i + 1);
        const mean = average(slice);
        mid[i] = mean;
        const variance = average(slice.map(x => Math.pow(x - mean, 2)));
        const std = Math.sqrt(variance);
        upper[i] = mean + std * stdDevMultiplier;
        lower[i] = mean - std * stdDevMultiplier;
    }
    return { upper, mid, lower };
}

// --- NEW INDICATORS ---

function macd(closes, fastPeriod, slowPeriod, signalPeriod) { // Changed to function without export
    if (closes.length < slowPeriod) return { macd: [], signal: [], histogram: [] };
    const emaFast = ema(closes, fastPeriod);
    const emaSlow = ema(closes, slowPeriod);
    const macdLine = emaFast.map((fast, i) => fast - emaSlow[i]);
    const signalLine = ema(macdLine, signalPeriod);
    const histogram = macdLine.map((macd, i) => macd - signalLine[i]);
    return { macd: macdLine, signal: signalLine, histogram: histogram };
}

function stochRSI(closes, rsiPeriod, stochPeriod, kPeriod, dPeriod) { // Changed to function without export
    const rsiValues = rsi(closes, rsiPeriod);
    const len = rsiValues.length;
    if (len < rsiPeriod + stochPeriod) return { k: [], d: [] };
    
    const k = safeArray(len);
    for (let i = rsiPeriod + stochPeriod - 1; i < len; i++) {
        const slice = rsiValues.slice(i - stochPeriod + 1, i + 1);
        const minRsi = Math.min(...slice);
        const maxRsi = Math.max(...slice);
        if (maxRsi === minRsi) {
            k[i] = 0;
        } else {
            k[i] = ((rsiValues[i] - minRsi) / (maxRsi - minRsi)) * 100;
        }
    }
    
    const d = ema(k, dPeriod); // Using EMA for the D-line is common
    return { k, d };
}

function adx(highs, lows, closes, period) { // Changed to function without export
    if (highs.length < period * 2) return { adx: [], pdi: [], ndi: [] };
    const len = highs.length;
    const tr = safeArray(len);
    const pdi = safeArray(len);
    const ndi = safeArray(len);

    for (let i = 1; i < len; i++) {
        tr[i] = Math.max(highs[i]-lows[i], Math.abs(highs[i]-closes[i-1]), Math.abs(lows[i]-closes[i-1]));
        const upMove = highs[i] - highs[i-1];
        const downMove = lows[i-1] - lows[i];
        pdi[i] = upMove > downMove && upMove > 0 ? upMove : 0;
        ndi[i] = downMove > upMove && downMove > 0 ? downMove : 0;
    }

    const smoothedTR = ema(tr, period);
    const smoothedPDI = ema(pdi, period);
    const smoothedNDI = ema(ndi, period);

    const pdiLine = safeArray(len);
    const ndiLine = safeArray(len);
    for(let i = period; i < len; i++) {
        if(smoothedTR[i] !== 0) {
            pdiLine[i] = 100 * (smoothedPDI[i] / smoothedTR[i]);
            ndiLine[i] = 100 * (smoothedNDI[i] / smoothedTR[i]);
        }
    }

    const dx = safeArray(len);
    for(let i = period; i < len; i++) {
        const sum = pdiLine[i] + ndiLine[i];
        if (sum !== 0) {
            dx[i] = 100 * (Math.abs(pdiLine[i] - ndiLine[i]) / sum);
        }
    }
    
    const adxLine = ema(dx, period);
    return { adx: adxLine, pdi: pdiLine, ndi: ndiLine };
}

function williamsR(highs, lows, closes, period = 14) {
    const len = closes.length;
    const wr = safeArray(len);
    for (let i = period - 1; i < len; i++) {
        const highestHigh = Math.max(...highs.slice(i - period + 1, i + 1));
        const lowestLow = Math.min(...lows.slice(i - period + 1, i + 1));
        if (highestHigh === lowestLow) {
            wr[i] = -50; // Neutral value
        } else {
            wr[i] = ((highestHigh - closes[i]) / (highestHigh - lowestLow)) * -100;
        }
    }
    return wr;
}

// --- CONSOLIDATED CODE FROM leviathan-v3/src/technical-analysis-advanced.js ---
// NOTE: Imports rsi, atr, stochRSI from technical-analysis.js and safeArray, average from utils.js,
// which are now also consolidated.

// --- HELPER FUNCTIONS for Advanced Indicators (from TAA) ---
// ema function is already defined in technical-analysis.js. Redefining it here
// would cause a conflict. I will assume the first ema definition is sufficient.
/*
function ema(closes, period) {
    if (closes.length < period) return safeArray(closes.length);
    const results = safeArray(closes.length);
    const multiplier = 2 / (period + 1);
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += closes[i];
    }
    results[period - 1] = sum / period;
    for (let i = period; i < closes.length; i++) {
        results[i] = (closes[i] - results[i - 1]) * multiplier + results[i - 1];
    }
    return results;
}
*/

function sma(closes, period) {
    if (closes.length < period) return safeArray(closes.length);
    const results = safeArray(closes.length);
    for(let i = period - 1; i < closes.length; i++) {
        const slice = closes.slice(i - period + 1, i + 1);
        results[i] = average(slice);
    }
    return results;
}

function wma(closes, period) {
    if (closes.length < period) return safeArray(closes.length);
    const results = safeArray(closes.length);
    const weightSum = (period * (period + 1)) / 2;
    for (let i = period - 1; i < closes.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += closes[i - j] * (period - j);
        }
        results[i] = sum / weightSum;
    }
    return results;
}

// --- 10 ADVANCED INDICATORS (from TAA) ---

/** 1. T3 Moving Average */
function t3(closes, period, vFactor = 0.7) { // Changed to function without export
    if (closes.length < period * 6) return safeArray(closes.length);
    const ema1 = ema(closes, period);
    const ema2 = ema(ema1, period);
    const ema3 = ema(ema2, period);
    const ema4 = ema(ema3, period);
    const ema5 = ema(ema4, period);
    const ema6 = ema(ema5, period);
    const c1 = -(vFactor ** 3);
    const c2 = 3 * (vFactor ** 2) + 3 * (vFactor ** 3);
    const c3 = -(6 * (vFactor ** 2)) - (3 * vFactor) - (3 * (vFactor ** 3));
    const c4 = 1 + 3 * vFactor + (vFactor ** 3) + 3 * (vFactor ** 2);
    return ema6.map((_, i) => c1 * ema6[i] + c2 * ema5[i] + c3 * ema4[i] + c4 * ema3[i]);
}

/** 2. SuperTrend */
function superTrend(highs, lows, closes, period, multiplier = 3) { // Changed to function without export
    if (highs.length < period) return { trend: [], direction: [] };
    const atrVals = atr(highs, lows, closes, period);
    const len = closes.length;
    const trend = safeArray(len);
    const direction = safeArray(len);
    for (let i = period; i < len; i++) {
        const mid = (highs[i] + lows[i]) / 2;
        const upper = mid + multiplier * atrVals[i];
        const lower = mid - multiplier * atrVals[i];
        direction[i] = closes[i] > (trend[i-1] || lower) ? 1 : -1;
        trend[i] = direction[i] === 1 ? lower : upper;
    }
    return { trend, direction };
}

/** 3. VWAP (Volume Weighted Average Price) */
function vwap(highs, lows, closes, volumes) { // Changed to function without export
    let cumulativePV = 0, cumulativeVol = 0;
    return closes.map((_, i) => {
        const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
        cumulativePV += typicalPrice * volumes[i];
        cumulativeVol += volumes[i];
        return cumulativeVol === 0 ? typicalPrice : cumulativePV / cumulativeVol;
    });
}

/** 4. Hull Moving Average (HMA) */
function hullMA(closes, period) { // Changed to function without export
    const halfPeriod = Math.floor(period / 2);
    const sqrtPeriod = Math.floor(Math.sqrt(period));
    const wma1 = wma(closes, halfPeriod);
    const wma2 = wma(closes, period);
    const diff = wma2.map((val, i) => 2 * wma1[i] - val);
    return wma(diff, sqrtPeriod);
}

/** 5. Choppiness Index */
function choppiness(highs, lows, closes, period) { // Changed to function without export
    if (highs.length < period) return safeArray(highs.length);
    const results = safeArray(highs.length);
    for (let i = period - 1; i < highs.length; i++) {
        const sliceHigh = highs.slice(i - period + 1, i + 1);
        const sliceLow = lows.slice(i - period + 1, i + 1);
        const sliceClose = closes.slice(i - period + 1, i + 1);
        const maxH = Math.max(...sliceHigh);
        const minL = Math.min(...sliceLow);
        const range = maxH - minL;
        if (range === 0) {
            results[i] = 100;
            continue;
        }
        const trVals = atr(sliceHigh, sliceLow, sliceClose, period);
        const sumTR = trVals.reduce((a, b) => a + b, 0);
        results[i] = 100 * Math.log10(sumTR / range) / Math.log10(period);
    }
    return results;
}

/** 6. Connors RSI (CRSI) */
function connorsRSI(closes, rsiPeriod = 3, streakRsiPeriod = 2, rankPeriod = 100) { // Changed to function without export
    const rsi1 = rsi(closes, rsiPeriod);
    const streaks = safeArray(closes.length);
    for (let i = 1; i < closes.length; i++) {
        const change = closes[i] > closes[i - 1] ? 1 : (closes[i] < closes[i - 1] ? -1 : 0);
        streaks[i] = (change > 0 && streaks[i-1] > 0) || (change < 0 && streaks[i-1] < 0) ? streaks[i-1] + change : change;
    }
    const rsi2 = rsi(streaks.map(s => s + 100), streakRsiPeriod);
    const rank = closes.map((c, i) => {
        if (i < rankPeriod) return 50;
        const slice = closes.slice(i - rankPeriod + 1, i + 1);
        const below = slice.filter(x => x < c).length;
        return (below / slice.length) * 100;
    });
    return rsi1.map((_, i) => (rsi1[i] + rsi2[i] + rank[i]) / 3);
}

/** 7. Kaufman Efficiency Ratio (KER) */
function kaufmanER(closes, period) { // Changed to function without export
    const len = closes.length;
    const er = safeArray(len);
    for (let i = period; i < len; i++) {
        const change = Math.abs(closes[i] - closes[i - period]);
        let volatility = 0;
        for(let j = i - period + 1; j <= i; j++) {
            volatility += Math.abs(closes[j] - (closes[j-1] || closes[j]));
        }
        er[i] = volatility === 0 ? 0 : change / volatility;
    }
    return er;
}

/** 8. Ichimoku Cloud (Core Components) */
function ichimoku(highs, lows, closes, span1 = 9, span2 = 26, span3 = 52) { // Changed to function without export
    const len = highs.length;
    const conv = safeArray(len), base = safeArray(len), spanA = safeArray(len), spanB = safeArray(len);
    for(let i = 0; i < len; i++) {
        if(i >= span1 - 1) conv[i] = (Math.max(...highs.slice(i - span1 + 1, i + 1)) + Math.min(...lows.slice(i - span1 + 1, i + 1))) / 2;
        if(i >= span2 - 1) base[i] = (Math.max(...highs.slice(i - span2 + 1, i + 1)) + Math.min(...lows.slice(i - span2 + 1, i + 1))) / 2;
        if(i >= span2 - 1) spanA[i] = (conv[i] + base[i]) / 2;
        if(i >= span3 - 1) spanB[i] = (Math.max(...highs.slice(i - span3 + 1, i + 1)) + Math.min(...lows.slice(i - span3 + 1, i + 1))) / 2;
    }
    return { conv, base, spanA, spanB };
}

/** 9. Schaff Trend Cycle (STC) */
function schaffTC(closes, fast = 23, slow = 50, cycle = 10) { // Changed to function without export
    const macdLine = ema(closes, fast).map((v, i) => v - ema(closes, slow)[i]);
    const stoch = stochRSI(macdLine, cycle, cycle, 3, 3);
    return ema(stoch.k, 3);
}

/** 10. Detrended Price Oscillator (DPO) */
function dpo(closes, period) { // Changed to function without export
    if (closes.length < period) return safeArray(closes.length);
    const offset = Math.floor((period / 2) + 1);
    const smaVals = sma(closes, period);
    const results = safeArray(closes.length);
    for(let i = period - 1; i < closes.length; i++) {
        if(i >= offset) {
           results[i] = closes[i - offset] - smaVals[i];
        }
    }
    return results;
}


class Leviathan {
    constructor() {
        this.config = null;
        this.circuitBreaker = null;
        this.exchange = null;
        this.ai = null;
        this.data = null;
        this.isProcessing = false;
        this.aiLastQueryTime = 0;
        this.state = {
            position: 'none', // 'long', 'short', 'none'
            entryPrice: null,
            currentPrice: null,
            lastSignal: 'HOLD',
            lastAIDecision: 'HOLD',
            lastIndicators: {},
            timestamp: null,
            balance: {
                total: 0,
                available: 0,
                used: 0
            }
        };
        // this.onTick = this.onTick.bind(this); // Explicitly bind onTick removed
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v3.5: FULL TA INTEGRATION '))));
        
        const isLive = process.argv.includes('--live');
        this.config = await ConfigManager.load();
        this.config.live_trading = isLive; // Corrected: set live_trading before logging
        console.log(COLOR.GREEN(`[Leviathan] Config loaded. Live Trading: ${this.config.live_trading}`)); 

        if (this.config.live_trading) { 
            console.log(COLOR.RED(COLOR.BOLD('🚨 LIVE TRADING ENABLED 🚨')));
        } else {
            console.log(COLOR.YELLOW('PAPER TRADING MODE ENABLED. Use --live flag to trade with real funds.'));
        }

        this.circuitBreaker = new CircuitBreaker(this.config);
        // console.log('Instantiated this.circuitBreaker:', this.circuitBreaker); // Debug log removed
        // Pass this.ai to PaperExchange constructor
        this.ai = new AIBrain(this.config); // Initialize AI before exchange
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker, this.ai); // Pass this.ai here
        
        this.data = new MarketData(this.config, this); // Pass the Leviathan instance directly
        console.log(COLOR.GREEN(`[Leviathan] MarketData and Exchange initialized.`)); 
        
        await this.data.start();
        const balance = await this.exchange.getBalance();
        this.circuitBreaker.setBalance(balance);
        this.state.balance = balance; // Initialize state balance
        console.log(COLOR.CYAN(`[Engine] Leviathan initialized. Symbol: ${this.config.symbol}`));
        console.log(COLOR.GREEN(`[Leviathan] init() completed.`));
    }

    // This is the function passed to MarketData
    // Removed: _marketDataUpdateHandler as it's no longer needed
    // _marketDataUpdateHandler(type) {
    //     console.log(COLOR.RED('DEBUG: Inside _marketDataUpdateHandler, this is:', this));
    //     this.onTick(type); // Ensure onTick is called with the correct 'this'
    // }

    async onTick(type) {
        if (this.isProcessing) {
            console.warn(COLOR.YELLOW(`[onTick] Already processing a tick, skipping.`));
            return;
        }
        this.isProcessing = true;

        try {
            console.log(COLOR.CYAN(`[onTick] Processing new tick of type: ${type}`));

            const klines = this.data.getKlines('main'); // Use the new getKlines method
            if (!klines || klines.length === 0) {
                console.warn(COLOR.YELLOW(`[onTick] No kline data available.`));
                this.isProcessing = false;
                return;
            }

            // Ensure klines are sorted by timestamp in ascending order
            klines.sort((a, b) => a.startTime - b.startTime);

            // Get the latest kline for current price and basic checks
            const latestKline = klines[klines.length - 1];
            const currentPrice = latestKline.close;

            console.log(COLOR.GREEN(`[onTick] Latest Price: ${currentPrice}`));

            // --- Indicator Calculations ---
            const indicators = {};
            // Basic TA
            indicators.rsi = rsi(klines.map(k => k.close), this.config.indicators.rsi);
            indicators.macd = macd(
                klines.map(k => k.close),
                this.config.indicators.macd.fast,
                this.config.indicators.macd.slow,
                this.config.indicators.macd.signal
            );
            indicators.bollingerBands = bollinger(
                klines.map(k => k.close),
                this.config.indicators.bb.period,
                this.config.indicators.bb.std
            );
            
            // Advanced TA
            indicators.ehlersFisher = fisher(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.fisher);
            indicators.supertrend = superTrend(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.advanced.superTrend.period, this.config.indicators.advanced.superTrend.multiplier);
            indicators.ichimoku = ichimoku(
                klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close),
                this.config.indicators.advanced.ichimoku.span1,
                this.config.indicators.advanced.ichimoku.span2,
                this.config.indicators.advanced.ichimoku.span3
            );
            indicators.vwap = vwap(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), klines.map(k => k.volume));
            indicators.adx = adx(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.adx);
            indicators.stochRSI = stochRSI(
                klines.map(k => k.close),
                this.config.indicators.stochRSI.rsi,
                this.config.indicators.stochRSI.stoch,
                this.config.indicators.stochRSI.k,
                this.config.indicators.stochRSI.d
            );
            indicators.williamsR = williamsR(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.stochRSI.rsi); // Using same period as StochRSI for now
            indicators.t3 = t3(klines.map(k => k.close), this.config.indicators.advanced.t3.period, this.config.indicators.advanced.t3.vFactor);
            // Momentum (if available and needed, add here. For now, T3 serves as an advanced indicator example.)


            // Log some indicator values for debugging
            console.log(COLOR.MAGENTA(`[Indicators] RSI: ${indicators.rsi && indicators.rsi.length > 0 ? indicators.rsi[indicators.rsi.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] MACD Hist: ${indicators.macd && indicators.macd.histogram && indicators.macd.histogram.length > 0 ? indicators.macd.histogram[indicators.macd.histogram.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] Supertrend: ${indicators.supertrend && indicators.supertrend.trend && indicators.supertrend.trend.length > 0 ? indicators.supertrend.trend[indicators.supertrend.trend.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] Ehlers Fisher: ${indicators.ehlersFisher && indicators.ehlersFisher.length > 0 ? indicators.ehlersFisher[indicators.ehlersFisher.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] StochRSI K: ${indicators.stochRSI && indicators.stochRSI.k && indicators.stochRSI.k.length > 0 ? indicators.stochRSI.k[indicators.stochRSI.k.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] ADX: ${indicators.adx && indicators.adx.adx && indicators.adx.adx.length > 0 ? indicators.adx.adx[indicators.adx.adx.length - 1].toFixed(2) : 'N/A'}`));


            // --- Signal Generation (Placeholder) ---
            let signal = 'HOLD';
            // Example: Buy if RSI is below 30 and MACD histogram is positive and increasing
            if (indicators.rsi && indicators.macd && indicators.macd.histogram && indicators.macd.histogram.length >= 2) {
                const latestRSI = indicators.rsi[indicators.rsi.length - 1];
                const latestMACDHist = indicators.macd.histogram[indicators.macd.histogram.length - 1];
                const prevMACDHist = indicators.macd.histogram[indicators.macd.histogram.length - 2];

                if (latestRSI < 30 && latestMACDHist > 0 && latestMACDHist > prevMACDHist) {
                    signal = 'BUY';
                }
                // Example: Sell if RSI is above 70 and MACD histogram is negative and decreasing
                else if (latestRSI > 70 && latestMACDHist < 0 && latestMACDHist < prevMACDHist) {
                    signal = 'SELL';
                }
            }
            console.log(COLOR.YELLOW(`[Signal] Generated: ${signal}`));

            // --- AIBrain Interaction ---
            // Only query AIBrain if a potential trade signal is generated or if position needs management
            let aiDecision = { decision: 'HOLD', confidence: 0 };
            if (signal !== 'HOLD' || (this.state.position !== 'none')) {
                 aiDecision = await this.ai.getTradingDecision(currentPrice, indicators, this.state, signal);
                 console.log(COLOR.BLUE(`[AIBrain] Decision: ${aiDecision.decision} (Confidence: ${aiDecision.confidence.toFixed(2)})`));
            } else {
                 console.log(COLOR.GRAY(`[AIBrain] Skipping AI query: no strong signal or active position.`));
            }


            // --- Trade Execution ---
            if (this.circuitBreaker.isOpen()) {
                console.warn(COLOR.RED(`[Trade] Circuit breaker is OPEN. Skipping trade execution.`));
            } else if (aiDecision.decision === 'BUY' && this.state.position === 'none') {
                const amount = this.config.trade_amount_usd / currentPrice; // Example: trade a fixed USD amount
                const order = await this.exchange.placeOrder(
                    this.config.symbol,
                    'Buy',
                    amount,
                    currentPrice, // Or use a limit order price based on strategy
                    {
                        type: 'Market',
                        timeInForce: 'GTC'
                    }
                );
                if (order) {
                    this.state.position = 'long';
                    this.state.entryPrice = currentPrice;
                    console.log(COLOR.GREEN(`[Trade] BUY Order placed: ${JSON.stringify(order)}`));
                }
            } else if (aiDecision.decision === 'SELL' && this.state.position === 'long') {
                const amount = this.config.trade_amount_usd / currentPrice; // Sell the same amount as bought
                const order = await this.exchange.placeOrder(
                    this.config.symbol,
                    'Sell',
                    amount,
                    currentPrice, // Or use a limit order price
                    {
                        type: 'Market',
                        timeInForce: 'GTC'
                    }
                );
                if (order) {
                    this.state.position = 'none';
                    this.state.entryPrice = null;
                    console.log(COLOR.RED(`[Trade] SELL Order placed: ${JSON.stringify(order)}`));
                }
            } else {
                console.log(COLOR.GRAY(`[Trade] No trade executed based on AI decision and current position.`));
            }
            
            // Update balance after potential trade
            this.state.balance = await this.exchange.getBalance();

            // Update bot state
            this.state.currentPrice = currentPrice;
            this.state.lastSignal = signal;
            this.state.lastAIDecision = aiDecision.decision;
            this.state.lastIndicators = indicators;
            this.state.timestamp = Date.now();

            // Output current status (will be implemented in next step)
            this.output();

        } catch (error) {
            console.error(COLOR.RED(`[onTick] Error during tick processing: ${error.message}`));
            console.log(COLOR.RED('DEBUG: this.circuitBreaker in onTick catch:', this.circuitBreaker)); // Keep this for now
            // Further error handling, e.g., notifying circuit breaker
            this.circuitBreaker.trip('onTick_error');
        } finally {
            this.isProcessing = false;
        }
    }
    output() {
        console.clear();
        const displayData = {
            symbol: this.config.symbol,
            interval: this.config.interval,
            liveTrading: this.config.live_trading,
            currentPrice: this.state.currentPrice,
            position: this.state.position,
            entryPrice: this.state.entryPrice,
            lastSignal: this.state.lastSignal,
            lastAIDecision: this.state.lastAIDecision,
            balance: this.state.balance,
            circuitBreakerTripped: this.circuitBreaker.isOpen(),
            lastIndicators: this.state.lastIndicators,
            timestamp: this.state.timestamp
        };
        renderHUD(displayData);
    }
    
    toJSON() {
        return {
            config: {
                symbol: this.config.symbol,
                interval: this.config.interval,
                live_trading: this.config.live_trading,
                trade_amount_usd: this.config.trade_amount_usd,
            },
            state: this.state, // this.state already contains much of the runtime data
            circuitBreakerStatus: this.circuitBreaker.isOpen() ? 'OPEN' : 'CLOSED',
            lastAIQueryTime: new Date(this.aiLastQueryTime).toISOString(),
            // Optionally, add summaries of indicators or other large data to keep JSON lean
            // e.g., lastTenRSI: this.state.lastIndicators.rsi.slice(-10)
        };
    }
}

// === MAIN EXECUTION ===
(async () => {
    try {
        const bot = new Leviathan();
        await bot.init();
    } catch (e) {
        console.error(COLOR.RED(`[FATAL] Failed to initialize Leviathan: ${e.message}`));
        process.exit(1);
    }
})();
// Add this to keep the process alive
setInterval(() => {}, 1000); // Keep the event loop alive