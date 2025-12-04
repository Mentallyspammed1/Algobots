import { safeArray, average } from './utils.js';
import { rsi, atr, stochRSI, ema } from './technical-analysis.js';

/**
 * This file contains pure-function versions of advanced technical analysis indicators.
 * @module TechnicalAnalysisAdvanced
 */


/**
 * Calculates Simple Moving Average (SMA).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period for the SMA.
 * @returns {number[]} Array of SMA values.
 */
export function sma(closes, period) {
    if (closes.length < period) return safeArray(closes.length);
    const results = safeArray(closes.length);
    for(let i = period - 1; i < closes.length; i++) {
        const slice = closes.slice(i - period + 1, i + 1);
        results[i] = average(slice);
    }
    return results;
}

/**
 * Calculates Weighted Moving Average (WMA).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period for the WMA.
 * @returns {number[]} Array of WMA values.
 */
export function wma(closes, period) {
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

/** 
 * Calculates T3 Moving Average.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @param {number} [vFactor=0.7] - The volume factor.
 * @returns {number[]} Array of T3 values.
 */
export function t3(closes, period, vFactor = 0.7) {
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

/** 
 * Calculates SuperTrend.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @param {number} [multiplier=3] - The ATR multiplier.
 * @returns {{trend: number[], direction: number[]}} - An object with arrays for the trend line and direction.
 */
export function superTrend(highs, lows, closes, period, multiplier = 3) {
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

/** 
 * Calculates Volume Weighted Average Price (VWAP).
 * This is a session-based indicator. The implementation here is a continuous version.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number[]} volumes - Array of volumes.
 * @returns {number[]} Array of VWAP values.
 */
export function vwap(highs, lows, closes, volumes) {
    let cumulativePV = 0, cumulativeVol = 0;
    return closes.map((_, i) => {
        const typicalPrice = (highs[i] + lows[i] + closes[i]) / 3;
        cumulativePV += typicalPrice * volumes[i];
        cumulativeVol += volumes[i];
        return cumulativeVol === 0 ? typicalPrice : cumulativePV / cumulativeVol;
    });
}

/** 
 * Calculates Hull Moving Average (HMA).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @returns {number[]} Array of HMA values.
 */
export function hullMA(closes, period) {
    const halfPeriod = Math.floor(period / 2);
    const sqrtPeriod = Math.floor(Math.sqrt(period));
    const wma1 = wma(closes, halfPeriod);
    const wma2 = wma(closes, period);
    const diff = wma2.map((val, i) => 2 * wma1[i] - val);
    return wma(diff, sqrtPeriod);
}

/** 
 * Calculates Choppiness Index.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @returns {number[]} Array of Choppiness Index values.
 */
export function choppiness(highs, lows, closes, period) {
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

/** 
 * Calculates Connors RSI (CRSI).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [rsiPeriod=3] - The period for the main RSI component.
 * @param {number} [streakRsiPeriod=2] - The period for the streak RSI component.
 * @param {number} [rankPeriod=100] - The period for the percentile rank component.
 * @returns {number[]} Array of CRSI values.
 */
export function connorsRSI(closes, rsiPeriod = 3, streakRsiPeriod = 2, rankPeriod = 100) {
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

/** 
 * Calculates Kaufman Efficiency Ratio (KER).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @returns {number[]} Array of KER values.
 */
export function kaufmanER(closes, period) {
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

/** 
 * Calculates Ichimoku Cloud components.
 * @param {number[]} highs - Array of high prices.
 * @param {number[]} lows - Array of low prices.
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [span1=9] - Tenkan-sen period.
 * @param {number} [span2=26] - Kijun-sen period.
 * @param {number} [span3=52] - Senkou Span B period.
 * @returns {{conv: number[], base: number[], spanA: number[], spanB: number[]}} - Ichimoku components.
 */
export function ichimoku(highs, lows, closes, span1 = 9, span2 = 26, span3 = 52) {
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

/** 
 * Calculates Schaff Trend Cycle (STC).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} [fast=23] - Fast MACD period.
 * @param {number} [slow=50] - Slow MACD period.
 * @param {number} [cycle=10] - STC cycle length.
 * @returns {number[]} Array of STC values.
 */
export function schaffTC(closes, fast = 23, slow = 50, cycle = 10) {
    const macdLine = ema(closes, fast).map((v, i) => v - ema(closes, slow)[i]);
    const stoch = stochRSI(macdLine, cycle, cycle, 3, 3);
    return ema(stoch.k, 3);
}

/** 
 * Calculates Detrended Price Oscillator (DPO).
 * @param {number[]} closes - Array of closing prices.
 * @param {number} period - The time period.
 * @returns {number[]} Array of DPO values.
 */
export function dpo(closes, period) {
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