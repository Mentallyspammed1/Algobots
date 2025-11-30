const sma = (arr, period) => {
    if (!arr || arr.length < period) return new Array(arr.length).fill(0);
    let result = [];
    let sum = 0;
    for (let i = 0; i < period; i++) sum += arr[i];
    result.push(sum / period);
    for (let i = period; i < arr.length; i++) {
        sum += arr[i] - arr[i - period];
        result.push(sum / period);
    }
    return new Array(period - 1).fill(0).concat(result);
};

const ema = (arr, period) => {
    if (!arr || arr.length === 0) return [];
    let result = new Array(arr.length).fill(0);
    const k = 2 / (period + 1);
    result[0] = arr[0];
    for (let i = 1; i < arr.length; i++) result[i] = (arr[i] * k) + (result[i - 1] * (1 - k));
    return result;
};

const wilders = (data, period) => {
    if (!data || data.length < period) return new Array(data.length).fill(0);
    let result = new Array(data.length).fill(0);
    let sum = 0;
    for (let i = 0; i < period; i++) sum += data[i];
    result[period - 1] = sum / period;
    const alpha = 1 / period;
    for (let i = period; i < data.length; i++) result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
    return result;
};

const atr = (highs, lows, closes, period) => {
    let tr = [0];
    for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
    return wilders(tr, period);
};

const rsi = (closes, period) => {
    let gains = [0], losses = [0];
    for (let i = 1; i < closes.length; i++) {
        const diff = closes[i] - closes[i - 1];
        gains.push(diff > 0 ? diff : 0); losses.push(diff < 0 ? Math.abs(diff) : 0);
    }
    const avgGain = wilders(gains, period);
    const avgLoss = wilders(losses, period);
    return closes.map((_, i) => avgLoss[i] === 0 ? 100 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
};

const stoch = (highs, lows, closes, period, kP, dP) => {
    let rsi = new Array(closes.length).fill(0);
    for (let i = period - 1; i < closes.length; i++) {
        const sliceH = highs.slice(i - period + 1, i + 1); const sliceL = lows.slice(i - period + 1, i + 1);
        const minL = Math.min(...sliceL); const maxH = Math.max(...sliceH);
        rsi[i] = (maxH - minL === 0) ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
    }
    const k = sma(rsi, kP); const d = sma(k, dP); return { k, d };
};

const macd = (closes, fast, slow, sig) => {
    const emaFast = ema(closes, fast); const emaSlow = ema(closes, slow);
    const line = emaFast.map((v, i) => v - emaSlow[i]); const signal = ema(line, sig);
    return { line, signal, hist: line.map((v, i) => v - signal[i]) };
};

const adx = (highs, lows, closes, period) => {
    let plusDM = [0], minusDM = [0];
    for (let i = 1; i < closes.length; i++) {
        const up = highs[i] - highs[i - 1]; const down = lows[i - 1] - lows[i];
        plusDM.push(up > down && up > 0 ? up : 0); minusDM.push(down > up && down > 0 ? down : 0);
    }
    const sTR = wilders(atr(highs, lows, closes, 1), period);
    const sPlus = wilders(plusDM, period); const sMinus = wilders(minusDM, period);
    let dx = [];
    for (let i = 0; i < closes.length; i++) {
        const pDI = sTR[i] === 0 ? 0 : (sPlus[i] / sTR[i]) * 100; const mDI = sTR[i] === 0 ? 0 : (sMinus[i] / sTR[i]) * 100;
        const sum = pDI + mDI;
        dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100);
    }
    return wilders(dx, period);
};

const mfi = (h,l,c,v,p) => { 
    let posFlow = [], negFlow = [];
    for (let i = 0; i < c.length; i++) {
        if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
        const tp = (h[i] + l[i] + c[i]) / 3; const prevTp = (h[i-1] + l[i-1] + c[i-1]) / 3;
        const raw = tp * v[i];
        if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
        else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
        else { posFlow.push(0); negFlow.push(0); }
    }
    let result = new Array(c.length).fill(0);
    for (let i = p - 1; i < c.length; i++) {
        let pSum = 0, nSum = 0;
        for (let j = 0; j < p; j++) { pSum += posFlow[i-j]; nSum += negFlow[i-j]; }
        if (nSum === 0) result[i] = 100; else result[i] = 100 - (100 / (1 + (pSum / nSum)));
    }
    return result;
};

const chop = (h, l, c, p) => {
    let result = new Array(c.length).fill(0);
    let tr = [h[0] - l[0]]; 
    for(let i=1; i<c.length; i++) tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i-1]), Math.abs(l[i] - c[i-1])));
    for (let i = p - 1; i < c.length; i++) {
        let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
        for (let j = 0; j < p; j++) {
            sumTr += tr[i - j];
            if (h[i - j] > maxHi) maxHi = h[i - j];
            if (l[i - j] < minLo) minLo = l[i - j];
        }
        const range = maxHi - minLo;
        result[i] = (range === 0 || sumTr === 0) ? 0 : 100 * (Math.log10(sumTr / range) / Math.log10(p));
    }
    return result;
};

const cci = (highs, lows, closes, period) => {
    const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3); const smaTp = sma(tp, period);
    let cci = new Array(closes.length).fill(0);
    for (let i = period - 1; i < tp.length; i++) {
        let meanDev = 0; for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
        meanDev /= period;
        cci[i] = (meanDev === 0) ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
    }
    return cci;
};

const linReg = (closes, period) => {
    let slopes = new Array(closes.length).fill(0), r2s = new Array(closes.length).fill(0);
    let sumX = 0, sumX2 = 0;
    for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }
    for (let i = period - 1; i < closes.length; i++) {
        let sumY = 0, sumXY = 0;
        const ySlice = [];
        for (let j = 0; j < period; j++) {
            const val = closes[i - (period - 1) + j]; ySlice.push(val); sumY += val; sumXY += j * val;
        }
        const n = period;
        const num = (n * sumXY) - (sumX * sumY);
        const den = (n * sumX2) - (sumX * sumX);
        const slope = den === 0 ? 0 : num / den;
        const intercept = (sumY - slope * sumX) / n;
        let ssTot = 0, ssRes = 0;
        const yMean = sumY / n;
        for(let j=0; j<period; j++) {
            const y = ySlice[j]; const yPred = slope * j + intercept;
            ssTot += Math.pow(y - yMean, 2); ssRes += Math.pow(y - yPred, 2);
        }
        slopes[i] = slope; r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
    }
    return { slope: slopes, r2: r2s };
};

const bollinger = (closes, period, stdDev) => {
    const smaVal = sma(closes, period);
    let upper = [], lower = [], middle = smaVal;
    for (let i = 0; i < closes.length; i++) {
        if (i < period - 1) { upper.push(0); lower.push(0); continue; }
        let sumSq = 0;
        for (let j = 0; j < period; j++) sumSq += Math.pow(closes[i - j] - smaVal[i], 2);
        const std = Math.sqrt(sumSq / period);
        upper.push(smaVal[i] + (std * stdDev)); lower.push(smaVal[i] - (std * stdDev));
    }
    return { upper, middle, lower };
};

const keltner = (highs, lows, closes, period, mult) => {
    const emaVal = ema(closes, period); const atrVal = atr(highs, lows, closes, period);
    return { upper: emaVal.map((e, i) => e + atrVal[i] * mult), lower: emaVal.map((e, i) => e - atrVal[i] * mult), middle: emaVal };
};

const superTrend = (highs, lows, closes, period, factor) => {
    const atrVal = atr(highs, lows, closes, period);
    let st = new Array(closes.length).fill(0); let trend = new Array(closes.length).fill(1);
    for (let i = period; i < closes.length; i++) {
        let up = (highs[i] + lows[i]) / 2 + factor * atrVal[i];
        let dn = (highs[i] + lows[i]) / 2 - factor * atrVal[i];
        if (i > 0) {
            const prevST = st[i-1];
            if (trend[i-1] === 1) { up = up; dn = Math.max(dn, prevST); } else { up = Math.min(up, prevST); dn = dn; }
        }
        if (closes[i] > up) trend[i] = 1; else if (closes[i] < dn) trend[i] = -1; else trend[i] = trend[i-1];
        st[i] = trend[i] === 1 ? dn : up;
    }
    return { trend, value: st };
};

const chandelierExit = (highs, lows, closes, period, mult) => {
    const atrVal = atr(highs, lows, closes, period);
    let longStop = new Array(closes.length).fill(0); let shortStop = new Array(closes.length).fill(0);
    let trend = new Array(closes.length).fill(1);
    for (let i = period; i < closes.length; i++) {
        const maxHigh = Math.max(...highs.slice(i - period + 1, i + 1));
        const minLow = Math.min(...lows.slice(i - period + 1, i + 1));
        longStop[i] = maxHigh - atrVal[i] * mult; shortStop[i] = minLow + atrVal[i] * mult;
        if (closes[i] > shortStop[i]) trend[i] = 1; else if (closes[i] < longStop[i]) trend[i] = -1; else trend[i] = trend[i-1];
    }
    return { trend, value: trend.map((t, i) => t === 1 ? longStop[i] : shortStop[i]) };
};

const vwap = (h, l, c, v, p) => {
    let vwap = new Array(c.length).fill(0);
    for (let i = p - 1; i < c.length; i++) {
        let sumPV = 0, sumV = 0;
        for (let j = 0; j < p; j++) {
            const tp = (h[i-j] + l[i-j] + c[i-j]) / 3; sumPV += tp * v[i-j]; sumV += v[i-j];
        }
        vwap[i] = sumV === 0 ? 0 : sumPV / sumV;
    }
    return vwap;
};

const findFVG = (candles) => {
    const len = candles.length;
    if (len < 5) return null; 
    const c1 = candles[len - 4]; const c2 = candles[len - 3]; const c3 = candles[len - 2]; 
    if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
    else if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
    return null;
};

const detectDivergence = (closes, rsi, period = 5) => {
    const len = closes.length;
    if (len < period * 2) return 'NONE';
    const priceHigh = Math.max(...closes.slice(len - period, len)); const rsiHigh = Math.max(...rsi.slice(len - period, len));
    const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period)); const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
    if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';
    const priceLow = Math.min(...closes.slice(len - period, len)); const rsiLow = Math.min(...rsi.slice(len - period, len));
    const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period)); const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
    if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH_REGULAR';
    return 'NONE';
};

const historicalVolatility = (closes, period = 20) => {
    const returns = [];
    for (let i = 1; i < closes.length; i++) returns.push(Math.log(closes[i] / closes[i - 1]));
    const volatility = new Array(closes.length).fill(0);
    for (let i = period; i < closes.length; i++) {
        const slice = returns.slice(i - period + 1, i + 1);
        const mean = slice.reduce((a, b) => a + b, 0) / period;
        const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period;
        volatility[i] = Math.sqrt(variance) * Math.sqrt(365);
    }
    return volatility;
};

const marketRegime = (closes, volatility, period = 50) => {
    const avgVol = sma(volatility, period);
    const currentVol = volatility[volatility.length - 1] || 0;
    const avgVolValue = avgVol[avgVol.length - 1] || 1;
    if (currentVol > avgVolValue * 1.5) return 'HIGH_VOLATILITY';
    if (currentVol < avgVolValue * 0.5) return 'LOW_VOLATILITY';
    return 'NORMAL';
};

const fibPivots = (h, l, c) => {
    const P = (h + l + c) / 3; const R = h - l;
    return { P, R1: P + 0.382 * R, R2: P + 0.618 * R, S1: P - 0.382 * R, S2: P - 0.618 * R };
};

// --- Export all indicators ---
module.exports = {
    sma, ema, wilders, atr, rsi, stoch, macd, adx, mfi, chop, cci, linReg, bollinger, keltner,
    superTrend, chandelierExit, vwap, findFVG, detectDivergence, historicalVolatility,
    marketRegime, fibPivots
};