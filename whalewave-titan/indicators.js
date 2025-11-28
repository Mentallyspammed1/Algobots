// indicators.js (merged core + advanced)

// ======================= Utility Functions =======================

/**
 * Safely accesses an element in an array, returning null for out-of-bounds indices.
 * @param {Array<any>} arr
 * @param {number} index
 * @returns {any|null}
 */
function safeArr(arr, index) {
    return index >= 0 && index < arr.length ? arr[index] : null;
}

/**
 * Safely gets the last non-null value from an array.
 * @param {Array<any>} arr
 * @returns {any|null}
 */
function safeGetFinalValue(arr) {
    for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i] !== null && arr[i] !== undefined) return arr[i];
    }
    return null;
}

// ======================= Smoothing Functions =======================

/**
 * Wilder's Smoothing
 * @param {Array<number|null>} arr
 * @param {number} period
 * @returns {Array<number|null>}
 */
function wilders(arr, period) {
    const out = [];
    let sum = 0;
    let count = 0;

    for (let i = 0; i < arr.length; i++) {
        const v = safeArr(arr, i);

        if (i < period) {
            if (v !== null) {
                sum += v;
                count++;
            }
            out.push(null);
            if (i === period - 1) {
                out[i] = count === period ? sum / period : null;
            }
            continue;
        }

        const prev = safeArr(out, i - 1);
        if (v === null || prev === null) {
            out.push(null);
        } else {
            out.push(((prev * (period - 1)) + v) / period);
        }
    }

    return out;
}

/**
 * Simple Moving Average (SMA)
 * @param {Array<number|null>} arr
 * @param {number} period
 * @returns {Array<number|null>}
 */
function sma(arr, period) {
    const result = [];
    let sum = 0;

    for (let i = 0; i < arr.length; i++) {
        const val = safeArr(arr, i);
        if (val !== null) sum += val;

        if (i >= period) {
            const valToRemove = safeArr(arr, i - period);
            if (valToRemove !== null) sum -= valToRemove;
        }

        if (i >= period - 1) {
            result.push(sum / period);
        } else {
            result.push(null);
        }
    }
    return result;
}

/**
 * Exponential Moving Average (EMA)
 * @param {Array<number|null>} arr
 * @param {number} period
 * @returns {Array<number|null>}
 */
function ema(arr, period) {
    const result = [];
    const k = 2 / (period + 1);
    let prevEMA = null;

    const initialSMA = sma(arr, period);
    prevEMA = safeGetFinalValue(initialSMA);

    for (let i = 0; i < arr.length; i++) {
        const val = safeArr(arr, i);

        if (val === null) {
            result.push(null);
            continue;
        }

        if (i < period - 1) {
            result.push(null);
            continue;
        }

        if (i === period - 1) {
            result.push(prevEMA);
            continue;
        }

        if (prevEMA !== null) {
            const currentEMA = val * k + prevEMA * (1 - k);
            result.push(currentEMA);
            prevEMA = currentEMA;
        } else {
            result.push(null);
        }
    }
    return result;
}

// ======================= Core Indicators =======================

/**
 * Average True Range (ATR)
 * @param {Array<number|null>} high
 * @param {Array<number|null>} low
 * @param {Array<number|null>} close
 * @param {number} period
 * @returns {Array<number|null>}
 */
function atr(high, low, close, period) {
    const len = Math.min(high.length, low.length, close.length);
    const trueRanges = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const cPrev = i > 0 ? safeArr(close, i - 1) : null;
        if (h === null || l === null) {
            trueRanges[i] = null;
            continue;
        }
        if (i === 0 || cPrev === null) {
            trueRanges[i] = h - l;
        } else {
            const tr1 = h - l;
            const tr2 = Math.abs(h - cPrev);
            const tr3 = Math.abs(l - cPrev);
            trueRanges[i] = Math.max(tr1, tr2, tr3);
        }
    }

    return wilders(trueRanges, period);
}

/**
 * RSI (Wilder)
 * @param {Array<number|null>} close
 * @param {number} period
 * @returns {Array<number|null>}
 */
function rsi(close, period) {
    const len = close.length;
    const gains = new Array(len).fill(null);
    const losses = new Array(len).fill(null);

    for (let i = 1; i < len; i++) {
        const c = safeArr(close, i);
        const p = safeArr(close, i - 1);
        if (c === null || p === null) continue;
        const diff = c - p;
        gains[i] = diff > 0 ? diff : 0;
        losses[i] = diff < 0 ? -diff : 0;
    }

    const avgGain = wilders(gains, period);
    const avgLoss = wilders(losses, period);
    const out = [];

    for (let i = 0; i < len; i++) {
        const ag = safeArr(avgGain, i);
        const al = safeArr(avgLoss, i);

        if (ag === null || al === null) {
            out.push(null);
            continue;
        }

        if (al === 0) {
            out.push(ag === 0 ? 50 : 100);
        } else {
            const rs = ag / al;
            out.push(100 - 100 / (1 + rs));
        }
    }
    return out;
}

/**
 * Stochastic Oscillator
 * @param {Array<number|null>} high
 * @param {Array<number|null>} low
 * @param {Array<number|null>} close
 * @param {number} period
 * @param {number} smoothK
 * @param {number} smoothD
 * @returns {{k: Array<number|null>, d: Array<number|null>}}
 */
function stoch(high, low, close, period, smoothK = 3, smoothD = 3) {
    const len = close.length;
    const rawK = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;

        let highestHigh = -Infinity;
        let lowestLow = Infinity;
        let hasNull = false;

        for (let j = 0; j < period; j++) {
            const h = safeArr(high, i - j);
            const l = safeArr(low, i - j);
            if (h === null || l === null) {
                hasNull = true;
                break;
            }
            if (h > highestHigh) highestHigh = h;
            if (l < lowestLow) lowestLow = l;
        }

        const c = safeArr(close, i);
        if (hasNull || c === null) continue;

        const range = highestHigh - lowestLow;
        rawK[i] = range === 0 ? 100 : ((c - lowestLow) / range) * 100;
    }

    const k = sma(rawK, smoothK);
    const d = sma(k, smoothD);
    return { k, d };
}

/**
 * MACD
 * @param {Array<number|null>} close
 * @param {number} fastPeriod
 * @param {number} slowPeriod
 * @param {number} signalPeriod
 * @returns {{macd: Array<number|null>, signal: Array<number|null>, hist: Array<number|null>}}
 */
function macd(close, fastPeriod, slowPeriod, signalPeriod) {
    const fast = ema(close, fastPeriod);
    const slow = ema(close, slowPeriod);

    const macdLine = [];
    for (let i = 0; i < close.length; i++) {
        const f = safeArr(fast, i);
        const s = safeArr(slow, i);
        macdLine.push(f !== null && s !== null ? f - s : null);
    }

    const signal = ema(macdLine, signalPeriod);
    const hist = [];

    for (let i = 0; i < close.length; i++) {
        const m = safeArr(macdLine, i);
        const s = safeArr(signal, i);
        hist.push(m !== null && s !== null ? m - s : null);
    }

    return { macd: macdLine, signal, hist };
}

/**
 * ADX
 * @param {Array<number|null>} high
 * @param {Array<number|null>} low
 * @param {Array<number|null>} close
 * @param {number} period
 * @returns {Array<number|null>}
 */
function adx(high, low, close, period) {
    const len = Math.min(high.length, low.length, close.length);

    const plusDM = new Array(len).fill(0);
    const minusDM = new Array(len).fill(0);

    for (let i = 1; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const ph = safeArr(high, i - 1);
        const pl = safeArr(low, i - 1);
        if (h === null || l === null || ph === null || pl === null) continue;

        const upMove = h - ph;
        const downMove = pl - l;

        if (upMove > downMove && upMove > 0) {
            plusDM[i] = upMove;
            minusDM[i] = 0;
        } else if (downMove > upMove && downMove > 0) {
            plusDM[i] = 0;
            minusDM[i] = downMove;
        }
    }

    const trArr = atr(high, low, close, period);
    const smPlusDM = wilders(plusDM, period);
    const smMinusDM = wilders(minusDM, period);

    const plusDI = new Array(len).fill(null);
    const minusDI = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const pdm = safeArr(smPlusDM, i);
        const mdm = safeArr(smMinusDM, i);
        const trv = safeArr(trArr, i);
        if (pdm === null || mdm === null || trv === null || trv === 0) continue;
        plusDI[i] = (pdm / trv) * 100;
        minusDI[i] = (mdm / trv) * 100;
    }

    const dx = new Array(len).fill(null);
    for (let i = 0; i < len; i++) {
        const p = safeArr(plusDI, i);
        const m = safeArr(minusDI, i);
        if (p === null || m === null) continue;
        const sum = p + m;
        const diff = Math.abs(p - m);
        if (sum !== 0) dx[i] = (diff / sum) * 100;
    }

    return wilders(dx, period);
}

/**
 * MFI
 * @param {Array<number|null>} high
 * @param {Array<number|null>} low
 * @param {Array<number|null>} close
 * @param {Array<number|null>} volume
 * @param {number} period
 * @returns {Array<number|null>}
 */
function mfi(high, low, close, volume, period) {
    const len = close.length;
    const typicalPrice = new Array(len).fill(null);
    const moneyFlow = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const c = safeArr(close, i);
        const v = safeArr(volume, i);
        if (h === null || l === null || c === null || v === null) continue;
        const tp = (h + l + c) / 3;
        typicalPrice[i] = tp;
        moneyFlow[i] = tp * v;
    }

    const posMF = new Array(len).fill(0);
    const negMF = new Array(len).fill(0);

    for (let i = 1; i < len; i++) {
        const tp = safeArr(typicalPrice, i);
        const ptp = safeArr(typicalPrice, i - 1);
        const mf = safeArr(moneyFlow, i);
        if (tp === null || ptp === null || mf === null) continue;

        if (tp > ptp) posMF[i] = mf;
        else if (tp < ptp) negMF[i] = mf;
    }

    const out = [];
    for (let i = 0; i < len; i++) {
        if (i < period) {
            out.push(null);
            continue;
        }

        let sumPos = 0;
        let sumNeg = 0;
        for (let j = 0; j < period; j++) {
            sumPos += posMF[i - j] || 0;
            sumNeg += negMF[i - j] || 0;
        }

        if (sumNeg === 0) {
            out.push(sumPos === 0 ? null : 100);
        } else {
            const mr = sumPos / sumNeg;
            out.push(100 - 100 / (1 + mr));
        }
    }

    return out;
}

/**
 * Bollinger Bands
 * @param {Array<number|null>} close
 * @param {number} period
 * @param {number} stdMult
 * @returns {Array<{upper:number|null,middle:number|null,lower:number|null}>}
 */
function bollinger(close, period, stdMult) {
    const ma = sma(close, period);
    const len = close.length;
    const out = [];

    for (let i = 0; i < len; i++) {
        if (i < period - 1) {
            out.push({ upper: null, middle: null, lower: null });
            continue;
        }

        const m = safeArr(ma, i);
        if (m === null) {
            out.push({ upper: null, middle: null, lower: null });
            continue;
        }

        let sumSq = 0;
        let hasNull = false;
        for (let j = 0; j < period; j++) {
            const v = safeArr(close, i - j);
            if (v === null) {
                hasNull = true;
                break;
            }
            const d = v - m;
            sumSq += d * d;
        }
        if (hasNull) {
            out.push({ upper: null, middle: null, lower: null });
            continue;
        }

        const std = Math.sqrt(sumSq / period);
        out.push({
            upper: m + stdMult * std,
            middle: m,
            lower: m - stdMult * std
        });
    }

    return out;
}

// ======================= WSS Helpers =======================

function isBullishCrossover(fast, slow, prevFast, prevSlow) {
    return prevFast <= prevSlow && fast > slow;
}

function isBearishCrossover(fast, slow, prevFast, prevSlow) {
    return prevFast >= prevSlow && fast < slow;
}

/**
 * Weighted Scoring System
 * @param {Array<number|null>} closePrices
 * @param {Array<number|null>} highPrices
 * @param {Array<number|null>} lowPrices
 * @param {Array<number|null>} volumes
 * @param {object} config
 * @returns {Array<number>} signals -1,0,1
 */
function calculateWSS(closePrices, highPrices, lowPrices, volumes, config) {
    const { indicators, weights, thresholds } = config;
    const len = closePrices.length;
    const combinedScore = new Array(len).fill(0);

    const buyThreshold = thresholds.buy ?? 0.5;
    const sellThreshold = thresholds.sell ?? -0.5;

    // --- RSI ---
    if (indicators.rsi && weights.rsi) {
        const rsiVals = rsi(closePrices, indicators.rsi.period);
        const overbought = indicators.rsi.overbought ?? 70;
        const oversold = indicators.rsi.oversold ?? 30;

        for (let i = 0; i < len; i++) {
            const v = safeArr(rsiVals, i);
            if (v === null) continue;
            let score = 0;
            if (v > overbought) score = -1;
            else if (v < oversold) score = 1;
            combinedScore[i] += score * weights.rsi;
        }
    }

    // --- MACD ---
    if (indicators.macd && weights.macd) {
        const macdRes = macd(
            closePrices,
            indicators.macd.fastPeriod,
            indicators.macd.slowPeriod,
            indicators.macd.signalPeriod
        );
        for (let i = 1; i < len; i++) {
            const m = safeArr(macdRes.macd, i);
            const s = safeArr(macdRes.signal, i);
            const pm = safeArr(macdRes.macd, i - 1);
            const ps = safeArr(macdRes.signal, i - 1);
            if (m === null || s === null || pm === null || ps === null) continue;

            let score = 0;
            if (isBullishCrossover(m, s, pm, ps)) score = 1;
            else if (isBearishCrossover(m, s, pm, ps)) score = -1;
            combinedScore[i] += score * weights.macd;
        }
    }

    // --- SMA Crossover ---
    if (indicators.smaCrossover && weights.smaCrossover) {
        const fastSma = sma(closePrices, indicators.smaCrossover.fastPeriod);
        const slowSma = sma(closePrices, indicators.smaCrossover.slowPeriod);

        for (let i = 1; i < len; i++) {
            const f = safeArr(fastSma, i);
            const s = safeArr(slowSma, i);
            const pf = safeArr(fastSma, i - 1);
            const ps = safeArr(slowSma, i - 1);
            if (f === null || s === null || pf === null || ps === null) continue;

            let score = 0;
            if (isBullishCrossover(f, s, pf, ps)) score = 1;
            else if (isBearishCrossover(f, s, pf, ps)) score = -1;
            combinedScore[i] += score * weights.smaCrossover;
        }
    }

    const finalSignals = [];
    let lastSignal = 0;
    for (let i = 0; i < len; i++) {
        const score = combinedScore[i];
        let sig = 0;
        if (score > buyThreshold) sig = 1;
        else if (score < sellThreshold) sig = -1;
        else sig = lastSignal;

        finalSignals.push(sig);
        lastSignal = sig;
    }

    return finalSignals;
}

// ======================= Advanced Indicators =======================

/* CCI */
function cci(high, low, close, period = 20) {
    const len = close.length;
    const typicalPrice = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const c = safeArr(close, i);
        if (h === null || l === null || c === null) continue;
        typicalPrice[i] = (h + l + c) / 3;
    }

    const tpSma = sma(typicalPrice, period);
    const out = [];
    const constant = 0.015;

    for (let i = 0; i < len; i++) {
        const tp = safeArr(typicalPrice, i);
        const avg = safeArr(tpSma, i);

        if (tp === null || avg === null || i < period - 1) {
            out.push(null);
            continue;
        }

        let sumAbs = 0;
        let count = 0;
        let hasNull = false;

        for (let j = 0; j < period; j++) {
            const v = safeArr(typicalPrice, i - j);
            if (v === null) {
                hasNull = true;
                break;
            }
            sumAbs += Math.abs(v - avg);
            count++;
        }

        if (hasNull || count === 0) {
            out.push(null);
            continue;
        }

        const md = sumAbs / count;
        if (md === 0) {
            out.push(null);
        } else {
            out.push((tp - avg) / (constant * md));
        }
    }

    return out;
}

/* CHOP */
function chop(high, low, close, period = 14) {
    const len = close.length;
    const trArr = atr(high, low, close, 1);
    const logTR = trArr.map(tr => (tr !== null && tr > 0 ? Math.log10(tr) : null));

    const sumLogTR = sma(logTR, period);

    const maxLogTR = new Array(len).fill(null);
    const minLogTR = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;

        let maxVal = -Infinity;
        let minVal = Infinity;
        let hasNull = false;

        for (let j = 0; j < period; j++) {
            const v = safeArr(logTR, i - j);
            if (v === null) {
                hasNull = true;
                break;
            }
            if (v > maxVal) maxVal = v;
            if (v < minVal) minVal = v;
        }

        if (!hasNull) {
            maxLogTR[i] = maxVal;
            minLogTR[i] = minVal;
        }
    }

    const out = [];
    for (let i = 0; i < len; i++) {
        const sum = safeArr(sumLogTR, i);
        const max = safeArr(maxLogTR, i);
        const min = safeArr(minLogTR, i);

        if (sum === null || max === null || min === null) {
            out.push(null);
            continue;
        }

        const denom = max - min;
        if (denom === 0) {
            out.push(0);
        } else {
            out.push(100 * Math.log10(sum / denom));
        }
    }

    return out;
}

/* Linear Regression (value at last bar) */
function linReg(arr, period) {
    const len = arr.length;
    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;

        const window = [];
        let hasNull = false;
        for (let j = 0; j < period; j++) {
            const v = safeArr(arr, i - (period - 1) + j);
            if (v === null) {
                hasNull = true;
                break;
            }
            window.push(v);
        }
        if (hasNull) continue;

        const N = window.length;
        let sumX = 0,
            sumY = 0,
            sumXY = 0,
            sumX2 = 0;
        for (let x = 0; x < N; x++) {
            const y = window[x];
            sumX += x;
            sumY += y;
            sumXY += x * y;
            sumX2 += x * x;
        }
        const denom = N * sumX2 - sumX * sumX;
        if (denom === 0) continue;
        const m = (N * sumXY - sumX * sumY) / denom;
        const b = (sumY - m * sumX) / N;
        out[i] = m * (N - 1) + b;
    }

    return out;
}

/* Keltner Channel */
function keltner(high, low, close, period = 20, multiplier = 2, atrPeriod) {
    const len = close.length;
    const emaClose = ema(close, period);
    const atrValues = atr(high, low, close, atrPeriod || period);
    const out = [];

    for (let i = 0; i < len; i++) {
        const mid = safeArr(emaClose, i);
        const a = safeArr(atrValues, i);
        if (mid === null || a === null) {
            out.push({ upper: null, middle: null, lower: null });
            continue;
        }
        const offset = multiplier * a;
        out.push({
            upper: mid + offset,
            middle: mid,
            lower: mid - offset
        });
    }

    return out;
}

/* SuperTrend */
function superTrend(high, low, close, period = 10, multiplier = 3) {
    const len = close.length;
    const atrVals = atr(high, low, close, period);

    const basicUpper = new Array(len).fill(null);
    const basicLower = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const a = safeArr(atrVals, i);
        if (h === null || l === null || a === null) continue;
        const mid = (h + l) / 2;
        const off = multiplier * a;
        basicUpper[i] = mid + off;
        basicLower[i] = mid - off;
    }

    const finalUpper = new Array(len).fill(null);
    const finalLower = new Array(len).fill(null);
    const stLine = new Array(len).fill(null);

    let prevFU = null;
    let prevFL = null;
    let prevST = null;

    for (let i = 0; i < len; i++) {
        const c = safeArr(close, i);
        const bu = safeArr(basicUpper, i);
        const bl = safeArr(basicLower, i);

        if (c === null || bu === null || bl === null) continue;

        let fu = bu;
        let fl = bl;

        if (i > 0 && prevFU !== null && prevFL !== null) {
            fu = c > prevFU ? Math.min(bu, prevFU) : bu;
            fl = c < prevFL ? Math.max(bl, prevFL) : bl;
        }

        finalUpper[i] = fu;
        finalLower[i] = fl;

        let st = prevST;
        if (st === null) {
            st = c > fl ? fl : fu;
        } else if (prevST === prevFU && c > fu) {
            st = fl;
        } else if (prevST === prevFL && c < fl) {
            st = fu;
        } else if (prevST === prevFU) {
            st = fu;
        } else if (prevST === prevFL) {
            st = fl;
        }

        stLine[i] = st;
        prevFU = fu;
        prevFL = fl;
        prevST = st;
    }

    const direction = [];
    for (let i = 0; i < len; i++) {
        const st = safeArr(stLine, i);
        const c = safeArr(close, i);
        if (st === null || c === null) {
            direction.push(0);
        } else {
            direction.push(c > st ? 1 : -1);
        }
    }

    return { superTrend: stLine, direction };
}

/* Chandelier Exit */
function chandelierExit(high, low, close, period = 22, multiplier = 3) {
    const len = close.length;
    const atrVals = atr(high, low, close, period);

    const outLong = new Array(len).fill(null);
    const outShort = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;

        let highest = -Infinity;
        let lowest = Infinity;
        let hasNull = false;

        for (let j = 0; j < period; j++) {
            const h = safeArr(high, i - j);
            const l = safeArr(low, i - j);
            if (h === null || l === null) {
                hasNull = true;
                break;
            }
            if (h > highest) highest = h;
            if (l < lowest) lowest = l;
        }

        const a = safeArr(atrVals, i);
        if (hasNull || a === null) continue;
        const off = multiplier * a;

        outLong[i] = highest - off;
        outShort[i] = lowest + off;
    }

    return { long: outLong, short: outShort };
}

/* VWAP */
function vwap(high, low, close, volume) {
    const len = close.length;
    const out = new Array(len).fill(null);

    let sumTPV = 0;
    let sumVol = 0;

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const c = safeArr(close, i);
        const v = safeArr(volume, i);

        if (h === null || l === null || c === null || v === null) {
            out[i] = null;
            continue;
        }

        const tp = (h + l + c) / 3;
        sumTPV += tp * v;
        sumVol += v;

        out[i] = sumVol === 0 ? null : sumTPV / sumVol;
    }

    return out;
}

/* Fair Value Gaps */
function findFVG(high, low) {
    const len = high.length;
    const out = new Array(len).fill(null);

    for (let i = 2; i < len; i++) {
        const h0 = safeArr(high, i - 2);
        const l0 = safeArr(low, i - 2);
        const h2 = safeArr(high, i);
        const l2 = safeArr(low, i);
        if (h0 === null || l0 === null || h2 === null || l2 === null) continue;

        if (l2 > h0) {
            out[i] = {
                type: 'bullish',
                index: i,
                from: h0,
                to: l2
            };
        } else if (h2 < l0) {
            out[i] = {
                type: 'bearish',
                index: i,
                from: h2,
                to: l0
            };
        }
    }

    return out;
}

/* Divergence Detection */
function detectDivergence(close, oscillatorValues, lookback = 50) {
    const len = close.length;
    const result = new Array(len).fill(null);
    const window = 2;

    const isPivotHigh = (arr, idx) => {
        const c = safeArr(arr, idx);
        if (c === null) return false;
        for (let k = 1; k <= window; k++) {
            const l = safeArr(arr, idx - k);
            const r = safeArr(arr, idx + k);
            if (l === null || r === null) return false;
            if (c <= l || c <= r) return false;
        }
        return true;
    };

    const isPivotLow = (arr, idx) => {
        const c = safeArr(arr, idx);
        if (c === null) return false;
        for (let k = 1; k <= window; k++) {
            const l = safeArr(arr, idx - k);
            const r = safeArr(arr, idx + k);
            if (l === null || r === null) return false;
            if (c >= l || c >= r) return false;
        }
        return true;
    };

    const pHigh = [];
    const pLow = [];
    const oHigh = [];
    const oLow = [];

    for (let i = 0; i < len; i++) {
        if (i < window || i > len - window - 1) continue;

        const c = safeArr(close, i);
        const o = safeArr(oscillatorValues, i);
        if (c === null || o === null) continue;

        if (isPivotHigh(close, i)) pHigh.push({ index: i, value: c });
        if (isPivotLow(close, i)) pLow.push({ index: i, value: c });
        if (isPivotHigh(oscillatorValues, i)) oHigh.push({ index: i, value: o });
        if (isPivotLow(oscillatorValues, i)) oLow.push({ index: i, value: o });

        const cutoff = i - lookback;

        const ph = pHigh.filter(p => p.index <= i && p.index >= cutoff);
        const oh = oHigh.filter(p => p.index <= i && p.index >= cutoff);
        const pl = pLow.filter(p => p.index <= i && p.index >= cutoff);
        const ol = oLow.filter(p => p.index <= i && p.index >= cutoff);

        // Bearish divergence
        if (ph.length >= 2 && oh.length >= 2) {
            const p1 = ph[ph.length - 2];
            const p2 = ph[ph.length - 1];

            let o1 = null,
                o2 = null;
            for (let x = oh.length - 1; x >= 1; x--) {
                const c2 = oh[x];
                const c1 = oh[x - 1];
                if (c1.index < p1.index || c2.index > p2.index) continue;
                o1 = c1;
                o2 = c2;
                break;
            }

            if (o1 && o2 && p2.value > p1.value && o2.value < o1.value) {
                result[i] = {
                    type: 'bearish',
                    pricePivot1: p1,
                    pricePivot2: p2,
                    oscPivot1: o1,
                    oscPivot2: o2
                };
                continue;
            }
        }

        // Bullish divergence
        if (pl.length >= 2 && ol.length >= 2) {
            const p1 = pl[pl.length - 2];
            const p2 = pl[pl.length - 1];

            let o1 = null,
                o2 = null;
            for (let x = ol.length - 1; x >= 1; x--) {
                const c2 = ol[x];
                const c1 = ol[x - 1];
                if (c1.index < p1.index || c2.index > p2.index) continue;
                o1 = c1;
                o2 = c2;
                break;
            }

            if (o1 && o2 && p2.value < p1.value && o2.value > o1.value) {
                result[i] = {
                    type: 'bullish',
                    pricePivot1: p1,
                    pricePivot2: p2,
                    oscPivot1: o1,
                    oscPivot2: o2
                };
                continue;
            }
        }
    }

    return result;
}

/* Historical Volatility */
function historicalVolatility(close, period = 20) {
    const len = close.length;
    const logRets = new Array(len).fill(0);

    for (let i = 1; i < len; i++) {
        const c = safeArr(close, i);
        const p = safeArr(close, i - 1);
        if (c !== null && p !== null && p !== 0) {
            logRets[i] = Math.log(c / p);
        } else {
            logRets[i] = 0;
        }
    }

    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;
        const slice = logRets.slice(i - period + 1, i + 1);
        const N = slice.length;
        const mean = slice.reduce((s, v) => s + v, 0) / N;
        let sumSq = 0;
        for (const v of slice) sumSq += (v - mean) * (v - mean);
        out[i] = Math.sqrt(sumSq / N);
    }

    return out;
}

/* Market Regime */
function marketRegime(adxValues, volatilityValues, adxThreshold = 25, volThreshold = 0.01) {
    const len = adxValues.length;
    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const a = safeArr(adxValues, i);
        if (a === null) {
            out[i] = null;
            continue;
        }
        out[i] = a > adxThreshold ? 'Trending' : 'Ranging';
    }

    return out;
}

/* Fibonacci Pivots */
function fibPivots(high, low, close) {
    const len = close.length;
    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const h = safeArr(high, i);
        const l = safeArr(low, i);
        const c = safeArr(close, i);
        if (h === null || l === null || c === null) continue;

        const range = h - l;
        const P = (h + l + c) / 3;
        const r1 = P + 0.382 * range;
        const r2 = P + 0.618 * range;
        const r3 = P + 1.0 * range;
        const s1 = P - 0.382 * range;
        const s2 = P - 0.618 * range;
        const s3 = P - 1.0 * range;

        out[i] = { P, r1, r2, r3, s1, s2, s3 };
    }

    return out;
}

/* Fib Pivots -> SR */
function getFibonacciPivotsAsSR(fibPivotsArr) {
    const len = fibPivotsArr.length;
    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        const p = safeArr(fibPivotsArr, i);
        if (!p) continue;
        const levels = [p.s3, p.s2, p.s1, p.P, p.r1, p.r2, p.r3].filter(
            v => typeof v === 'number' && Number.isFinite(v)
        );
        out[i] = levels.length ? levels : null;
    }

    return out;
}

/* Historical High/Low SR */
function getHistoricalHighLowSR(high, low, period = 50) {
    const len = high.length;
    const out = new Array(len).fill(null);

    for (let i = 0; i < len; i++) {
        if (i < period - 1) continue;

        let highest = -Infinity;
        let lowest = Infinity;
        let valid = true;

        for (let j = 0; j < period; j++) {
            const h = safeArr(high, i - j);
            const l = safeArr(low, i - j);
            if (h === null || l === null) {
                valid = false;
                break;
            }
            if (h > highest) highest = h;
            if (l < lowest) lowest = l;
        }

        if (!valid || highest === -Infinity || lowest === Infinity) continue;
        out[i] = [lowest, highest];
    }

    return out;
}

/* Combine & Filter SR */
function combineAndFilterSR(sr1, sr2, tolerancePercent = 0.1) {
    const len = Math.max(sr1.length, sr2.length);
    const out = new Array(len).fill(null);

    const withinTolerance = (a, b) => {
        const avg = (a + b) / 2;
        if (avg === 0) return Math.abs(a - b) <= 1e-8;
        return (Math.abs(a - b) / Math.abs(avg)) * 100 <= tolerancePercent;
    };

    for (let i = 0; i < len; i++) {
        const a = safeArr(sr1, i);
        const b = safeArr(sr2, i);

        const levels = [];
        if (Array.isArray(a)) {
            for (const x of a) if (typeof x === 'number' && isFinite(x)) levels.push(x);
        }
        if (Array.isArray(b)) {
            for (const x of b) if (typeof x === 'number' && isFinite(x)) levels.push(x);
        }

        if (!levels.length) continue;

        levels.sort((x, y) => x - y);

        const clusters = [];
        let current = [levels[0]];
        for (let j = 1; j < levels.length; j++) {
            const last = current[current.length - 1];
            const v = levels[j];
            if (withinTolerance(last, v)) {
                current.push(v);
            } else {
                clusters.push(current);
                current = [v];
            }
        }
        clusters.push(current);

        out[i] = clusters.map(c => c.reduce((s, v) => s + v, 0) / c.length);
    }

    return out;
}

/* Ehlers Super Trend Cross */
function ehlersSuperTrendCross(close, fastPeriod = 10, slowPeriod = 30) {
    const len = close.length;
    const fast = ema(close, fastPeriod);
    const slow = ema(close, slowPeriod);

    const diff = new Array(len).fill(null);
    for (let i = 0; i < len; i++) {
        const f = safeArr(fast, i);
        const s = safeArr(slow, i);
        if (f === null || s === null) continue;
        diff[i] = f - s;
    }

    const out = new Array(len).fill(0);
    let prev = null;

    for (let i = 0; i < len; i++) {
        const d = safeArr(diff, i);
        if (d === null) {
            out[i] = 0;
            continue;
        }
        if (prev === null) {
            out[i] = 0;
            prev = d;
            continue;
        }
        if (prev <= 0 && d > 0) out[i] = 1;
        else if (prev >= 0 && d < 0) out[i] = -1;
        else out[i] = 0;
        prev = d;
    }

    return out;
}

// ======================= Exports =======================

export {
    // utilities
    safeArr,
    safeGetFinalValue,
    wilders,
    sma,
    ema,
    // core indicators
    atr,
    rsi,
    stoch,
    macd,
    adx,
    mfi,
    bollinger,
    isBullishCrossover,
    isBearishCrossover,
    calculateWSS,
    // advanced
    cci,
    chop,
    linReg,
    keltner,
    superTrend,
    chandelierExit,
    vwap,
    findFVG,
    detectDivergence,
    historicalVolatility,
    marketRegime,
    fibPivots,
    getFibonacciPivotsAsSR,
    getHistoricalHighLowSR,
    combineAndFilterSR,
    ehlersSuperTrendCross
};

export default {
    safeArr,
    safeGetFinalValue,
    wilders,
    sma,
    ema,
    atr,
    rsi,
    stoch,
    macd,
    adx,
    mfi,
    bollinger,
    isBullishCrossover,
    isBearishCrossover,
    calculateWSS,
    cci,
    chop,
    linReg,
    keltner,
    superTrend,
    chandelierExit,
    vwap,
    findFVG,
    detectDivergence,
    historicalVolatility,
    marketRegime,
    fibPivots,
    getFibonacciPivotsAsSR,
    getHistoricalHighLowSR,
    combineAndFilterSR,
    ehlersSuperTrendCross
};