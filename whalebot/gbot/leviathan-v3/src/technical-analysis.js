import { safeArray, average } from './utils.js';

/**
 * This file contains pure-function versions of standard technical analysis indicators.
 * @module TechnicalAnalysis
 */

/**
 * Calculates Exponential Moving Average (EMA).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period for the EMA.
 * @returns {number[]} Array of EMA values.
 */
export function ema(closes, period) {
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

/**
 * Calculates Relative Strength Index (RSI).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [period=14] - The time period for the RSI.
 * @returns {number[]} Array of RSI values.
 */
export function rsi(closes, period = 14) {
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

/**
 * Calculates the Fisher Transform.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number} [period=9] - The time period.
 * @returns {number[]} Array of Fisher Transform values.
 */
export function fisher(highs, lows, period = 9) {
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

/**
 * Calculates Average True Range (ATR).
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [period=14] - The time period.
 * @returns {number[]} Array of ATR values.
 */
export function atr(highs, lows, closes, period = 14) {
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

/**
 * Calculates Bollinger Bands.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @param {number} stdDevMultiplier - The standard deviation multiplier.
 * @returns {{upper: number[], mid: number[], lower: number[]}} - An object with arrays for upper, middle, and lower bands.
 */
export function bollinger(closes, period, stdDevMultiplier) {
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

/**
 * Calculates Moving Average Convergence Divergence (MACD).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} fastPeriod - The fast EMA period.
 * @param {number} slowPeriod - The slow EMA period.
 * @param {number} signalPeriod - The signal line EMA period.
 * @returns {{macd: number[], signal: number[], histogram: number[]}} - An object with arrays for MACD line, signal line, and histogram.
 */
export function macd(closes, fastPeriod, slowPeriod, signalPeriod) {
    if (closes.length < slowPeriod) return { macd: [], signal: [], histogram: [] };
    const emaFast = ema(closes, fastPeriod);
    const emaSlow = ema(closes, slowPeriod);
    const macdLine = emaFast.map((fast, i) => fast - emaSlow[i]);
    const signalLine = ema(macdLine, signalPeriod);
    const histogram = macdLine.map((macd, i) => macd - signalLine[i]);
    return { macd: macdLine, signal: signalLine, histogram: histogram };
}

/**
 * Calculates Stochastic RSI.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} rsiPeriod - The RSI period.
 * @param {number} stochPeriod - The stochastic period.
 * @param {number} kPeriod - The %K period.
 * @param {number} dPeriod - The %D period.
 * @returns {{k: number[], d: number[]}} - An object with arrays for %K and %D lines.
 */
export function stochRSI(closes, rsiPeriod, stochPeriod, kPeriod, dPeriod) {
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

/**
 * Calculates the Average Directional Index (ADX).
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @returns {{adx: number[], pdi: number[], ndi: number[]}} - An object with arrays for ADX, +DI, and -DI lines.
 */
export function adx(highs, lows, closes, period) {
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

/**
 * Calculates Williams %R.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [period=14] - The time period.
 * @returns {number[]} Array of Williams %R values.
 */
export function williamsR(highs, lows, closes, period = 14) {
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