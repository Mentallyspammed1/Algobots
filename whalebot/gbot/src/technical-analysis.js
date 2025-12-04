import { average, safeArray, stdDev } from './utils.js';

/**
 * This file contains pure-function versions of the original technical analysis
 * logic from aisig.js. The goal is to be a 1:1 match of the original behavior
 * to ensure the refactoring is behaviorally identical.
 */

export function rsi(closes, period = 14) {
    if (!closes.length) return [];
    
    let gains = [];
    let losses = [];
    for (let i = 1; i < closes.length; i++) {
        const diff = closes[i] - closes[i - 1];
        gains.push(Math.max(diff, 0));
        losses.push(Math.max(-diff, 0));
    }
    
    const rsi = safeArray(closes.length);
    // This check is important to match original behavior which slices from beginning
    if (gains.length < period) return rsi;

    let avgGain = average(gains.slice(0, period));
    let avgLoss = average(losses.slice(0, period));
    
    // The first calculated value in the original was at period index, but it was using sliced data.
    // To replicate, we need to be careful. The loop starts at `period + 1`.
    // There is no RSI value calculated for the first `period` indexes.
    
    for(let i = period; i < closes.length; i++) {
        // RSI is calculated for closes[i], using change from closes[i-1]
        const change = closes[i] - closes[i-1];

        // This is the first value calculation which was implicit in the original's loop structure
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

// This is the version with the BUG from the original code
export function bollinger_original(closes, period, stdDevMultiplier) {
    const len = closes.length;
    const mid = safeArray(len);
    let sum = 0;
    for(let i=0; i<len; i++) {
        sum += closes[i];
        // This block is NOT entered if len === period, resulting in an array of 0s for `mid`
        if(i >= period) {
            sum -= closes[i-period];
            mid[i] = sum/period;
        }
    }
    const dev = stdDev(closes, period);
    return {
        upper: mid.map((m, i) => m + dev[i] * stdDevMultiplier),
        lower: mid.map((m, i) => m - dev[i] * stdDevMultiplier),
        mid: mid
    };
}

// This is the CORRECTED version of the Bollinger logic
export function bollinger_fixed(closes, period, stdDevMultiplier) {
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
