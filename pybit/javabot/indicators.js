import { Decimal } from 'decimal.js';
import { CONFIG } from './config.js';
import { logger } from './logger.js';
import { DataFrame } from 'dataframe-js';

Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_UP });

// --- Helper Functions for Decimal.js operations ---
/**
 * @function sum
 * @description Calculates the sum of an array of Decimal.js numbers.
 * @param {Array<Decimal>} arr - The array of Decimal.js numbers.
 * @returns {Decimal} The sum of the numbers.
 */
function sum(arr) {
    return arr.reduce((acc, val) => acc.plus(val), new Decimal(0));
}

/**
 * @function avg
 * @description Calculates the average of an array of Decimal.js numbers.
 * @param {Array<Decimal>} arr - The array of Decimal.js numbers.
 * @returns {Decimal} The average of the numbers, or NaN if the array is empty.
 */
function avg(arr) {
    if (arr.length === 0) return new Decimal(NaN);
    return sum(arr).dividedBy(arr.length);
}

/**
 * @function stdDev
 * @description Calculates the standard deviation of an array of Decimal.js numbers.
 * @param {Array<Decimal>} arr - The array of Decimal.js numbers.
 * @param {Decimal} mean - The mean of the numbers.
 * @returns {Decimal} The standard deviation.
 */
function stdDev(arr, mean) {
    if (arr.length < 2) return new Decimal(0);
    const variance = arr.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0)).dividedBy(arr.length);
    return variance.sqrt();
}

// --- Core Moving Averages ---
/**
 * @function calculateSMA
 * @description Calculates the Simple Moving Average (SMA) for a given data set.
 * @param {Array<Decimal>} data - An array of Decimal.js numbers (e.g., closing prices).
 * @param {number} period - The period for the SMA calculation.
 * @returns {Array<Decimal>} An array of SMA values, with NaN for periods where data is insufficient.
 */
export function calculateSMA(data, period) {
    if (data.length < period) return new Array(data.length).fill(new Decimal(NaN));
    const sma = [];
    for (let i = 0; i <= data.length - period; i++) {
        const slice = data.slice(i, i + period);
        sma.push(avg(slice));
    }
    return new Array(period - 1).fill(new Decimal(NaN)).concat(sma);
}

/**
 * @function calculateEMA
 * @description Calculates the Exponential Moving Average (EMA) for a given data set.
 * @param {Array<Decimal>} data - An array of Decimal.js numbers (e.g., closing prices).
 * @param {number} period - The period for the EMA calculation.
 * @returns {Array<Decimal>} An array of EMA values, with NaN for periods where data is insufficient.
 */
export function calculateEMA(data, period) {
    if (data.length < period) return new Array(data.length).fill(new Decimal(NaN));
    const ema = [];
    let multiplier = new Decimal(2).dividedBy(new Decimal(period).plus(1));
    
    // Initial SMA for the first EMA value
    let initialSum = new Decimal(0);
    for (let i = 0; i < period; i++) {
        initialSum = initialSum.plus(data[i]);
    }
    ema[period - 1] = initialSum.dividedBy(period);

    for (let i = period; i < data.length; i++) {
        ema[i] = data[i].minus(ema[i - 1]).times(multiplier).plus(ema[i - 1]);
    }
    return new Array(period - 1).fill(new Decimal(NaN)).concat(ema.slice(period - 1));
}

/**
 * @function calculateDEMA
 * @description Calculates the Double Exponential Moving Average (DEMA).
 * @param {Array<Decimal>} data - An array of Decimal.js numbers (e.g., closing prices).
 * @param {number} period - The period for the DEMA calculation.
 * @returns {Array<Decimal>} An array of DEMA values.
 */
export function calculateDEMA(data, period) {
    const ema1 = calculateEMA(data, period);
    const ema2 = calculateEMA(ema1.filter(d => !d.isNaN()), period); // EMA of EMA

    const dema = ema1.map((val, i) => {
        if (val.isNaN() || ema2[i].isNaN()) return new Decimal(NaN);
        return new Decimal(2).times(val).minus(ema2[i]);
    });
    return dema;
}

// --- Volatility Indicators ---
/**
 * @function calculateATR
 * @description Calculates the Average True Range (ATR).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the ATR calculation.
 * @returns {Array<Decimal>} An array of ATR values.
 */
export function calculateATR(high, low, close, period) {
    if (high.length < period) return new Array(high.length).fill(new Decimal(NaN));
    const tr = [];
    for (let i = 0; i < high.length; i++) {
        const h = high[i];
        const l = low[i];
        const cPrev = i > 0 ? close[i - 1] : close[i];
        tr.push(Decimal.max(h.minus(l).abs(), h.minus(cPrev).abs(), l.minus(cPrev).abs()));
    }
    const atr = calculateEMA(tr, period);
    return atr;
}

// --- Momentum Indicators ---
/**
 * @function calculateRSI
 * @description Calculates the Relative Strength Index (RSI).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the RSI calculation.
 * @returns {Array<Decimal>} An array of RSI values.
 */
export function calculateRSI(close, period) {
    if (close.length < period + 1) return new Array(close.length).fill(new Decimal(NaN));
    const rsi = new Array(close.length).fill(new Decimal(NaN));
    const gains = new Array(close.length).fill(new Decimal(0));
    const losses = new Array(close.length).fill(new Decimal(0));

    for (let i = 1; i < close.length; i++) {
        const diff = close[i].minus(close[i - 1]);
        if (diff.gt(0)) {
            gains[i] = diff;
        } else {
            losses[i] = diff.abs();
        }
    }

    let avgGain = avg(gains.slice(1, period + 1));
    let avgLoss = avg(losses.slice(1, period + 1));

    if (avgLoss.isZero()) {
        rsi[period] = new Decimal(100);
    } else {
        const rs = avgGain.dividedBy(avgLoss);
        rsi[period] = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs)));
    }

    for (let i = period + 1; i < close.length; i++) {
        avgGain = avgGain.times(period - 1).plus(gains[i]).dividedBy(period);
        avgLoss = avgLoss.times(period - 1).plus(losses[i]).dividedBy(period);

        if (avgLoss.isZero()) {
            rsi[i] = new Decimal(100);
        } else {
            const rs = avgGain.dividedBy(avgLoss);
            rsi[i] = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs)));
        }
    }
    return rsi;
}

/**
 * @function calculateStochasticOscillator
 * @description Calculates the Stochastic Oscillator (%K and %D).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} kPeriod - The period for %K calculation.
 * @param {number} dPeriod - The period for %D calculation.
 * @param {number} smoothing - The smoothing period for %K.
 * @returns {Array<Array<Decimal>>} An array containing two arrays: [%K values, %D values].
 */
export function calculateStochasticOscillator(high, low, close, kPeriod, dPeriod, smoothing) {
    if (close.length < kPeriod) return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];

    const percentK = [];
    for (let i = 0; i < close.length; i++) {
        const startIndex = Math.max(0, i - kPeriod + 1);
        const periodHigh = Decimal.max(...high.slice(startIndex, i + 1));
        const periodLow = Decimal.min(...low.slice(startIndex, i + 1));

        if (periodHigh.minus(periodLow).isZero()) {
            percentK[i] = new Decimal(0);
        } else {
            percentK[i] = close[i].minus(periodLow).dividedBy(periodHigh.minus(periodLow)).times(100);
        }
    }

    const smoothedK = calculateSMA(percentK, smoothing);
    const percentD = calculateSMA(smoothedK.filter(d => !d.isNaN()), dPeriod);

    return [percentK, percentD];
}

/**
 * @function calculateMACD
 * @description Calculates the Moving Average Convergence Divergence (MACD).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} fastPeriod - The period for the fast EMA.
 * @param {number} slowPeriod - The period for the slow EMA.
 * @param {number} signalPeriod - The period for the signal line EMA.
 * @returns {Object} An object containing `macd_line`, `signal_line`, and `histogram` arrays.
 */
export function calculateMACD(close, fastPeriod, slowPeriod, signalPeriod) {
    const emaFast = calculateEMA(close, fastPeriod);
    const emaSlow = calculateEMA(close, slowPeriod);

    const macdLine = emaFast.map((val, i) => {
        if (val.isNaN() || emaSlow[i].isNaN()) return new Decimal(NaN);
        return val.minus(emaSlow[i]);
    });
    const signalLine = calculateEMA(macdLine.filter(d => !d.isNaN()), signalPeriod);
    const histogram = macdLine.map((val, i) => {
        if (val.isNaN() || signalLine[i].isNaN()) return new Decimal(NaN);
        return val.minus(signalLine[i]);
    });

    return { macd_line: macdLine, signal_line: signalLine, histogram: histogram };
}

/**
 * @function calculateADX
 * @description Calculates the Average Directional Index (ADX).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the ADX calculation.
 * @returns {Object} An object containing `adx`, `plus_di`, and `minus_di` arrays.
 */
export function calculateADX(high, low, close, period) {
    const plusDM = [];
    const minusDM = [];
    const tr = [];

    for (let i = 1; i < close.length; i++) {
        const upMove = high[i].minus(high[i - 1]);
        const downMove = low[i - 1].minus(low[i]);

        plusDM[i] = (upMove.gt(downMove) && upMove.gt(0)) ? upMove : new Decimal(0);
        minusDM[i] = (downMove.gt(upMove) && downMove.gt(0)) ? downMove : new Decimal(0);

        tr[i] = Decimal.max(high[i].minus(low[i]).abs(), high[i].minus(close[i - 1]).abs(), low[i].minus(close[i - 1]).abs());
    }
    plusDM[0] = new Decimal(0); minusDM[0] = new Decimal(0); tr[0] = new Decimal(0);

    const smoothPlusDM = calculateEMA(plusDM, period);
    const smoothMinusDM = calculateEMA(minusDM, period);
    const smoothTR = calculateEMA(tr, period);

    const plusDI = smoothPlusDM.map((val, i) => {
        if (val.isNaN() || smoothTR[i].isZero()) return new Decimal(NaN);
        return val.dividedBy(smoothTR[i]).times(100);
    });
    const minusDI = smoothMinusDM.map((val, i) => {
        if (val.isNaN() || smoothTR[i].isZero()) return new Decimal(NaN);
        return val.dividedBy(smoothTR[i]).times(100);
    });

    const dx = plusDI.map((val, i) => {
        if (val.isNaN() || minusDI[i].isNaN() || val.plus(minusDI[i]).isZero()) return new Decimal(NaN);
        return val.minus(minusDI[i]).abs().dividedBy(val.plus(minusDI[i])).times(100);
    });
    const adx = calculateEMA(dx.filter(d => !d.isNaN()), period);

    return { adx: adx, plus_di: plusDI, minus_di: minusDI };
}

/**
 * @function calculateBollingerBands
 * @description Calculates Bollinger Bands (Upper, Middle, Lower).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the Bollinger Bands calculation.
 * @param {number} stdDevMultiplier - The standard deviation multiplier.
 * @returns {Object} An object containing `upper`, `middle` (SMA), and `lower` band arrays.
 */
export function calculateBollingerBands(close, period, stdDevMultiplier) {
    const sma = calculateSMA(close, period);
    const upperBand = [];
    const lowerBand = [];

    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            upperBand.push(new Decimal(NaN));
            lowerBand.push(new Decimal(NaN));
            continue;
        }
        const slice = close.slice(i - period + 1, i + 1);
        const currentSMA = sma[i];
        const currentStdDev = stdDev(slice, currentSMA);

        upperBand.push(currentSMA.plus(currentStdDev.times(stdDevMultiplier)));
        lowerBand.push(currentSMA.minus(currentStdDev.times(stdDevMultiplier)));
    }
    return { upper: upperBand, middle: sma, lower: lowerBand };
}

/**
 * @function calculateCCI
 * @description Calculates the Commodity Channel Index (CCI).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the CCI calculation.
 * @returns {Array<Decimal>} An array of CCI values.
 */
export function calculateCCI(high, low, close, period) {
    const typicalPrice = high.map((h, i) => h.plus(low[i]).plus(close[i]).dividedBy(3));
    const smaTP = calculateSMA(typicalPrice, period);
    const meanDeviation = [];

    for (let i = 0; i < typicalPrice.length; i++) {
        if (i < period - 1) {
            meanDeviation.push(new Decimal(NaN));
            continue;
        }
        const sliceTP = typicalPrice.slice(i - period + 1, i + 1);
        const currentSmaTP = smaTP[i];
        const md = sliceTP.reduce((acc, val) => acc.plus(val.minus(currentSmaTP).abs()), new Decimal(0)).dividedBy(period);
        meanDeviation.push(md);
    }

    const cci = typicalPrice.map((tp, i) => {
        if (tp.isNaN() || smaTP[i].isNaN() || meanDeviation[i].isNaN() || meanDeviation[i].isZero()) return new Decimal(NaN);
        return tp.minus(smaTP[i]).dividedBy(new Decimal(0.015).times(meanDeviation[i]));
    });
    return cci;
}

/**
 * @function calculateWilliamsR
 * @description Calculates Williams %R.
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the Williams %R calculation.
 * @returns {Array<Decimal>} An array of Williams %R values.
 */
export function calculateWilliamsR(high, low, close, period) {
    const wr = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            wr.push(new Decimal(NaN));
            continue;
        }
        const startIndex = i - period + 1;
        const periodHigh = Decimal.max(...high.slice(startIndex, i + 1));
        const periodLow = Decimal.min(...low.slice(startIndex, i + 1));

        if (periodHigh.minus(periodLow).isZero()) {
            wr.push(new Decimal(NaN)); // Avoid division by zero
        } else {
            wr.push(close[i].minus(periodHigh).dividedBy(periodHigh.minus(periodLow)).times(-100));
        }
    }
    return wr;
}

/**
 * @function calculateMFI
 * @description Calculates the Money Flow Index (MFI).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @param {number} period - The period for the MFI calculation.
 * @returns {Array<Decimal>} An array of MFI values.
 */
export function calculateMFI(high, low, close, volume, period) {
    const typicalPrice = high.map((h, i) => h.plus(low[i]).plus(close[i]).dividedBy(3));
    const moneyFlow = typicalPrice.map((tp, i) => tp.times(volume[i]));

    const positiveMoneyFlow = [];
    const negativeMoneyFlow = [];

    for (let i = 1; i < typicalPrice.length; i++) {
        if (typicalPrice[i].gt(typicalPrice[i - 1])) {
            positiveMoneyFlow.push(moneyFlow[i]);
            negativeMoneyFlow.push(new Decimal(0));
        } else if (typicalPrice[i].lt(typicalPrice[i - 1])) {
            positiveMoneyFlow.push(new Decimal(0));
            negativeMoneyFlow.push(moneyFlow[i]);
        } else {
            positiveMoneyFlow.push(new Decimal(0));
            negativeMoneyFlow.push(new Decimal(0));
        }
    }
    positiveMoneyFlow.unshift(new Decimal(0)); // Align length
    negativeMoneyFlow.unshift(new Decimal(0)); // Align length

    const mfi = [];
    for (let i = 0; i < typicalPrice.length; i++) {
        if (i < period - 1) {
            mfi.push(new Decimal(NaN));
            continue;
        }
        const startIndex = i - period + 1;
        const periodPositiveMF = sum(positiveMoneyFlow.slice(startIndex, i + 1));
        const periodNegativeMF = sum(negativeMoneyFlow.slice(startIndex, i + 1));

        if (periodNegativeMF.isZero()) {
            mfi.push(new Decimal(100));
        } else {
            const moneyRatio = periodPositiveMF.dividedBy(periodNegativeMF);
            mfi.push(new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(moneyRatio))));
        }
    }
    return mfi;
}

/**
 * @function calculateOBV
 * @description Calculates On-Balance Volume (OBV).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @returns {Array<Decimal>} An array of OBV values.
 */
export function calculateOBV(close, volume) {
    const obv = [new Decimal(0)];
    for (let i = 1; i < close.length; i++) {
        if (close[i].gt(close[i - 1])) {
            obv.push(obv[i - 1].plus(volume[i]));
        } else if (close[i].lt(close[i - 1])) {
            obv.push(obv[i - 1].minus(volume[i]));
        } else {
            obv.push(obv[i - 1]);
        }
    }
    return obv;
}

/**
 * @function calculateCMF
 * @description Calculates Chaikin Money Flow (CMF).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @param {number} period - The period for the CMF calculation.
 * @returns {Array<Decimal>} An array of CMF values.
 */
export function calculateCMF(high, low, close, volume, period) {
    const cmf = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            cmf.push(new Decimal(NaN));
            continue;
        }
        const startIndex = i - period + 1;
        const periodHigh = high.slice(startIndex, i + 1);
        const periodLow = low.slice(startIndex, i + 1);
        const periodClose = close.slice(startIndex, i + 1);
        const periodVolume = volume.slice(startIndex, i + 1);

        let sumMFV = new Decimal(0);
        let sumVolume = new Decimal(0);

        for (let j = 0; j < period; j++) {
            const mf = (periodHigh[j].minus(periodLow[j]).isZero()) ? new Decimal(0) : 
                       (periodClose[j].minus(periodLow[j]).minus(periodHigh[j].minus(periodClose[j]))).dividedBy(periodHigh[j].minus(periodLow[j]));
            sumMFV = sumMFV.plus(mf.times(periodVolume[j]));
            sumVolume = sumVolume.plus(periodVolume[j]);
        }
        if (sumVolume.isZero()) {
            cmf.push(new Decimal(NaN));
        } else {
            cmf.push(sumMFV.dividedBy(sumVolume));
        }
    }
    return cmf;
}

/**
 * @function calculateIchimokuCloud
 * @description Calculates Ichimoku Cloud components (Tenkan-sen, Kijun-sen, Senkou Span A, Senkou Span B, Chikou Span).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} tenkanPeriod - The period for Tenkan-sen.
 * @param {number} kijunPeriod - The period for Kijun-sen.
 * @param {number} senkouSpanBPeriod - The period for Senkou Span B.
 * @param {number} chikouSpanOffset - The offset for Chikou Span.
 * @returns {Object} An object containing arrays for `tenkan_sen`, `kijun_sen`, `senkou_span_a`, `senkou_span_b`, and `chikou_span`.
 */
export function calculateIchimokuCloud(high, low, close, tenkanPeriod, kijunPeriod, senkouSpanBPeriod, chikouSpanOffset) {
    const tenkanSen = [];
    const kijunSen = [];
    const senkouSpanA = [];
    const senkouSpanB = [];
    const chikouSpan = [];

    for (let i = 0; i < close.length; i++) {
        // Tenkan Sen
        if (i < tenkanPeriod - 1) {
            tenkanSen.push(new Decimal(NaN));
        } else {
            const sliceHigh = high.slice(i - tenkanPeriod + 1, i + 1);
            const sliceLow = low.slice(i - tenkanPeriod + 1, i + 1);
            tenkanSen.push(Decimal.max(...sliceHigh).plus(Decimal.min(...sliceLow)).dividedBy(2));
        }

        // Kijun Sen
        if (i < kijunPeriod - 1) {
            kijunSen.push(new Decimal(NaN));
        } else {
            const sliceHigh = high.slice(i - kijunPeriod + 1, i + 1);
            const sliceLow = low.slice(i - kijunPeriod + 1, i + 1);
            kijunSen.push(Decimal.max(...sliceHigh).plus(Decimal.min(...sliceLow)).dividedBy(2));
        }

        // Senkou Span A (leading span 1)
        if (i < kijunPeriod - 1) {
            senkouSpanA.push(new Decimal(NaN));
        } else {
            const val = tenkanSen[i].plus(kijunSen[i]).dividedBy(2);
            senkouSpanA.push(val);
        }

        // Senkou Span B (leading span 2)
        if (i < senkouSpanBPeriod - 1) {
            senkouSpanB.push(new Decimal(NaN));
        } else {
            const sliceHigh = high.slice(i - senkouSpanBPeriod + 1, i + 1);
            const sliceLow = low.slice(i - senkouSpanBPeriod + 1, i + 1);
            senkouSpanB.push(Decimal.max(...sliceHigh).plus(Decimal.min(...sliceLow)).dividedBy(2));
        }

        // Chikou Span (lagging span)
        if (i - chikouSpanOffset >= 0) {
            chikouSpan.push(close[i - chikouSpanOffset]);
        } else {
            chikouSpan.push(new Decimal(NaN));
        }
    }

    // Shift Senkou Spans forward
    const shiftedSenkouSpanA = new Array(chikouSpanOffset).fill(new Decimal(NaN)).concat(senkouSpanA.slice(0, senkouSpanA.length - chikouSpanOffset));
    const shiftedSenkouSpanB = new Array(chikouSpanOffset).fill(new Decimal(NaN)).concat(senkouSpanB.slice(0, senkouSpanB.length - chikouSpanOffset));

    return {
        tenkan_sen: tenkanSen,
        kijun_sen: kijunSen,
        senkou_span_a: shiftedSenkouSpanA,
        senkou_span_b: shiftedSenkouSpanB,
        chikou_span: chikouSpan
    };
}

/**
 * @function calculatePSAR
 * @description Calculates Parabolic SAR (Stop and Reverse).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Decimal} acceleration - The acceleration factor.
 * @param {Decimal} maxAcceleration - The maximum acceleration factor.
 * @returns {Object} An object containing `psar` values and `direction` (1 for uptrend, -1 for downtrend).
 */
export function calculatePSAR(high, low, acceleration, maxAcceleration) {
    const psar = [];
    const direction = []; // 1 for uptrend, -1 for downtrend
    const extremePoint = [];
    const accelerationFactor = [];

    // Initial values
    psar.push(low[0]);
    direction.push(1); // Assume initial uptrend
    extremePoint.push(high[0]);
    accelerationFactor.push(acceleration);

    for (let i = 1; i < high.length; i++) {
        let currentPsar = psar[i - 1];
        let currentDirection = direction[i - 1];
        let currentEP = extremePoint[i - 1];
        let currentAF = accelerationFactor[i - 1];

        if (currentDirection === 1) { // Uptrend
            currentPsar = currentPsar.plus(currentAF.times(currentEP.minus(currentPsar)));
            if (low[i].lt(currentPsar)) { // Trend reversal
                currentDirection = -1;
                currentPsar = extremePoint[i - 1];
                currentEP = low[i];
                currentAF = acceleration;
            } else {
                if (high[i].gt(currentEP)) {
                    currentEP = high[i];
                    currentAF = Decimal.min(maxAcceleration, currentAF.plus(acceleration));
                }
            }
        } else { // Downtrend
            currentPsar = currentPsar.minus(currentAF.times(currentPsar.minus(currentEP)));
            if (high[i].gt(currentPsar)) { // Trend reversal
                currentDirection = 1;
                currentPsar = extremePoint[i - 1];
                currentEP = high[i];
                currentAF = acceleration;
            } else {
                if (low[i].lt(currentEP)) {
                    currentEP = low[i];
                    currentAF = Decimal.min(maxAcceleration, currentAF.plus(acceleration));
                }
            }
        }

        psar.push(currentPsar);
        direction.push(currentDirection);
        extremePoint.push(currentEP);
        accelerationFactor.push(currentAF);
    }

    return { psar: psar, direction: direction };
}

/**
 * @function calculateVWAP
 * @description Calculates Volume Weighted Average Price (VWAP).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @returns {Array<Decimal>} An array of VWAP values.
 */
export function calculateVWAP(high, low, close, volume) {
    const typicalPrice = high.map((h, i) => h.plus(low[i]).plus(close[i]).dividedBy(3));
    const cumulativeTPxV = [];
    const cumulativeVolume = [];
    const vwap = [];

    let currentCumulativeTPxV = new Decimal(0);
    let currentCumulativeVolume = new Decimal(0);

    for (let i = 0; i < typicalPrice.length; i++) {
        currentCumulativeTPxV = currentCumulativeTPxV.plus(typicalPrice[i].times(volume[i]));
        currentCumulativeVolume = currentCumulativeVolume.plus(volume[i]);

        cumulativeTPxV.push(currentCumulativeTPxV);
        cumulativeVolume.push(currentCumulativeVolume);

        if (currentCumulativeVolume.isZero()) {
            vwap.push(new Decimal(NaN));
        } else {
            vwap.push(currentCumulativeTPxV.dividedBy(currentCumulativeVolume));
        }
    }
    return vwap;
}

/**
 * @function calculateVolatilityIndex
 * @description Calculates a Volatility Index based on price returns.
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the volatility calculation.
 * @returns {Array<Decimal>} An array of Volatility Index values.
 */
export function calculateVolatilityIndex(high, low, close, period) {
    const returns = close.map((c, i) => i > 0 ? c.minus(close[i - 1]).dividedBy(close[i - 1]) : new Decimal(0));
    const volatility = [];

    for (let i = 0; i < returns.length; i++) {
        if (i < period - 1) {
            volatility.push(new Decimal(NaN));
            continue;
        }
        const sliceReturns = returns.slice(i - period + 1, i + 1);
        const meanReturn = avg(sliceReturns);
        const std = stdDev(sliceReturns, meanReturn);
        volatility.push(std);
    }
    return volatility;
}

/**
 * @function calculateVWMA
 * @description Calculates Volume Weighted Moving Average (VWMA).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @param {number} period - The period for the VWMA calculation.
 * @returns {Array<Decimal>} An array of VWMA values.
 */
export function calculateVWMA(close, volume, period) {
    const vwma = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            vwma.push(new Decimal(NaN));
            continue;
        }
        const startIndex = i - period + 1;
        const sliceClose = close.slice(startIndex, i + 1);
        const sliceVolume = volume.slice(startIndex, i + 1);

        let sumCloseTimesVolume = new Decimal(0);
        let sumVolume = new Decimal(0);

        for (let j = 0; j < period; j++) {
            sumCloseTimesVolume = sumCloseTimesVolume.plus(sliceClose[j].times(sliceVolume[j]));
            sumVolume = sumVolume.plus(sliceVolume[j]);
        }
        if (sumVolume.isZero()) {
            vwma.push(new Decimal(NaN));
        } else {
            vwma.push(sumCloseTimesVolume.dividedBy(sumVolume));
        }
    }
    return vwma;
}

/**
 * @function calculateVolumeDelta
 * @description Calculates Volume Delta.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @param {number} period - The period for the Volume Delta calculation.
 * @returns {Array<Decimal>} An array of Volume Delta values.
 */
export function calculateVolumeDelta(close, volume, period) {
    const volumeDelta = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            volumeDelta.push(new Decimal(NaN));
            continue;
        }
        const startIndex = i - period + 1;
        const sliceClose = close.slice(startIndex, i + 1);
        const sliceVolume = volume.slice(startIndex, i + 1);

        let buyingVolume = new Decimal(0);
        let sellingVolume = new Decimal(0);

        for (let j = 1; j < period; j++) {
            if (sliceClose[j].gt(sliceClose[j - 1])) {
                buyingVolume = buyingVolume.plus(sliceVolume[j]);
            } else if (sliceClose[j].lt(sliceClose[j - 1])) {
                sellingVolume = sellingVolume.plus(sliceVolume[j]);
            }
        }
        volumeDelta.push(buyingVolume.minus(sellingVolume));
    }
    return volumeDelta;
}

/**
 * @function calculateKaufmanAMA
 * @description Calculates Kaufman's Adaptive Moving Average (KAMA).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the KAMA calculation.
 * @param {number} fastPeriod - The period for the fast EMA smoothing constant.
 * @param {number} slowPeriod - The period for the slow EMA smoothing constant.
 * @returns {Array<Decimal>} An array of KAMA values.
 */
export function calculateKaufmanAMA(close, period, fastPeriod, slowPeriod) {
    const kama = [];
    const er = []; // Efficiency Ratio
    const sc = []; // Smoothing Constant

    const fastEmaConst = new Decimal(2).dividedBy(new Decimal(fastPeriod).plus(1));
    const slowEmaConst = new Decimal(2).dividedBy(new Decimal(slowPeriod).plus(1));

    for (let i = 0; i < close.length; i++) {
        if (i < period) {
            kama.push(new Decimal(NaN));
            er.push(new Decimal(NaN));
            sc.push(new Decimal(NaN));
            continue;
        }

        const change = close[i].minus(close[i - period].abs());
        let volatility = new Decimal(0);
        for (let j = i - period + 1; j <= i; j++) {
            volatility = volatility.plus(close[j].minus(close[j - 1]).abs());
        }

        if (volatility.isZero()) {
            er.push(new Decimal(0));
        } else {
            er.push(change.dividedBy(volatility));
        }

        const currentER = er[er.length - 1];
        sc.push(currentER.times(fastEmaConst.minus(slowEmaConst)).plus(slowEmaConst).pow(2));

        const currentSC = sc[sc.length - 1];
        if (kama[i - 1].isNaN()) {
            kama.push(close[i]); // First valid KAMA is current close
        } else {
            kama.push(kama[i - 1].plus(currentSC.times(close[i].minus(kama[i - 1]))));
        }
    }
    return kama;
}

/**
 * @function calculateRelativeVolume
 * @description Calculates Relative Volume.
 * @param {Array<Decimal>} volume - An array of Decimal.js volume data.
 * @param {number} period - The period for the average volume calculation.
 * @returns {Array<Decimal>} An array of Relative Volume values.
 */
export function calculateRelativeVolume(volume, period) {
    const relativeVolume = [];
    const avgVolume = calculateSMA(volume, period);

    for (let i = 0; i < volume.length; i++) {
        if (avgVolume[i].isZero()) {
            relativeVolume.push(new Decimal(NaN));
        } else {
            relativeVolume.push(volume[i].dividedBy(avgVolume[i]));
        }
    }
    return relativeVolume;
}

/**
 * @function calculateMarketStructure
 * @description Determines market structure (uptrend, downtrend, sideways) based on higher highs/lows.
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {number} lookbackPeriod - The lookback period for identifying highs and lows.
 * @returns {Array<Decimal>} An array of trend indicators (1 for uptrend, -1 for downtrend, 0 for sideways).
 */
export function calculateMarketStructure(high, low, lookbackPeriod) {
    const trend = []; // 1 for uptrend, -1 for downtrend, 0 for sideways

    for (let i = 0; i < high.length; i++) {
        if (i < lookbackPeriod) {
            trend.push(new Decimal(0)); // Not enough data
            continue;
        }

        const sliceHigh = high.slice(i - lookbackPeriod, i + 1);
        const sliceLow = low.slice(i - lookbackPeriod, i + 1);

        const highestHigh = Decimal.max(...sliceHigh);
        const lowestLow = Decimal.min(...sliceLow);

        const currentHigh = high[i];
        const currentLow = low[i];

        if (currentHigh.gt(highestHigh.minus(highestHigh.times(0.01))) && currentLow.gt(lowestLow.plus(lowestLow.times(0.01)))) {
            trend.push(new Decimal(1)); // Higher High, Higher Low (Uptrend)
        } else if (currentHigh.lt(highestHigh.plus(highestHigh.times(0.01))) && currentLow.lt(lowestLow.minus(lowestLow.times(0.01)))) {
            trend.push(new Decimal(-1)); // Lower High, Lower Low (Downtrend)
        } else {
            trend.push(new Decimal(0)); // Sideways
        }
    }
    return trend;
}

/**
 * @function calculateKeltnerChannels
 * @description Calculates Keltner Channels (Upper, Middle, Lower).
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the Keltner Channels calculation.
 * @param {number} atrMultiplier - The ATR multiplier for the bands.
 * @returns {Object} An object containing `upper`, `middle` (EMA), and `lower` band arrays.
 */
export function calculateKeltnerChannels(high, low, close, period, atrMultiplier) {
    const middleBand = calculateEMA(close, period);
    const atr = calculateATR(high, low, close, period);

    const upperBand = middleBand.map((mb, i) => {
        if (mb.isNaN() || atr[i].isNaN()) return new Decimal(NaN);
        return mb.plus(atr[i].times(atrMultiplier));
    });
    const lowerBand = middleBand.map((mb, i) => {
        if (mb.isNaN() || atr[i].isNaN()) return new Decimal(NaN);
        return mb.minus(atr[i].times(atrMultiplier));
    });

    return { upper: upperBand, middle: middleBand, lower: lowerBand };
}

/**
 * @function calculateROC
 * @description Calculates the Rate of Change (ROC).
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the ROC calculation.
 * @returns {Array<Decimal>} An array of ROC values.
 */
export function calculateROC(close, period) {
    const roc = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period) {
            roc.push(new Decimal(NaN));
            continue;
        }
        const currentClose = close[i];
        const pastClose = close[i - period];

        if (pastClose.isZero()) {
            roc.push(new Decimal(NaN));
        } else {
            roc.push(currentClose.minus(pastClose).dividedBy(pastClose).times(100));
        }
    }
    return roc;
}

/**
 * @function detectCandlestickPatterns
 * @description Detects basic candlestick patterns (e.g., Engulfing, Doji).
 * @param {Object} df - A DataFrame-like object containing kline data with `open`, `high`, `low`, `close`.
 * @returns {Array<string>} An array of detected pattern names (e.g., "BULLISH_ENGULFING", "DOJI", "NONE").
 */
export function detectCandlestickPatterns(df) {
    const patterns = [];
    for (let i = 0; i < df.length; i++) {
        if (i < 1) {
            patterns.push("NONE");
            continue;
        }

        const current = df.iloc(i);
        const prev = df.iloc(i - 1);

        const isBullish = current.close.gt(current.open);
        const isBearish = current.close.lt(current.open);

        // Simple Bullish Engulfing
        if (isBullish && prev.isBearish && current.open.lt(prev.close) && current.close.gt(prev.open)) {
            patterns.push("BULLISH_ENGULFING");
        } 
        // Simple Bearish Engulfing
        else if (isBearish && prev.isBullish && current.open.gt(prev.close) && current.close.lt(prev.open)) {
            patterns.push("BEARISH_ENGULFING");
        }
        // Doji
        else if (current.close.minus(current.open).abs().dividedBy(current.high.minus(current.low)).lt(0.1)) {
            patterns.push("DOJI");
        }
        else {
            patterns.push("NONE");
        }
    }
    return patterns;
}

/**
 * @function calculateFibonacciLevels
 * @description Calculates Fibonacci retracement levels based on a lookback period.
 * @param {Object} df - A DataFrame-like object containing kline data with `high` and `low` prices.
 * @param {number} lookbackPeriod - The period to look back for highest high and lowest low.
 * @returns {Object|null} An object containing Fibonacci levels (e.g., "0%", "23.6%"), or null if insufficient data.
 */
export function calculateFibonacciLevels(df, lookbackPeriod) {
    if (df.length < lookbackPeriod) return null;

    const sliceHigh = df.high.slice(df.length - lookbackPeriod, df.length);
    const sliceLow = df.low.slice(df.length - lookbackPeriod, df.length);

    const highestHigh = Decimal.max(...sliceHigh);
    const lowestLow = Decimal.min(...sliceLow);
    const range = highestHigh.minus(lowestLow);

    const levels = {
        "0%": highestHigh,
        "23.6%": highestHigh.minus(range.times(0.236)),
        "38.2%": highestHigh.minus(range.times(0.382)),
        "50%": highestHigh.minus(range.times(0.5)),
        "61.8%": highestHigh.minus(range.times(0.618)),
        "78.6%": highestHigh.minus(range.times(0.786)),
        "100%": lowestLow,
    };
    return levels;
}

/**
 * @function calculateFibonacciPivotPoints
 * @description Calculates Fibonacci Pivot Points (Pivot, R1, R2, S1, S2).
 * @param {Object} df - A DataFrame-like object containing kline data with `high`, `low`, and `close` prices.
 * @returns {Object|null} An object containing `pivot`, `r1`, `r2`, `s1`, `s2` values, or null if insufficient data.
 */
export function calculateFibonacciPivotPoints(df) {
    if (df.length < 1) return null;

    const lastClose = df.close[df.close.length - 1];
    const lastHigh = df.high[df.high.length - 1];
    const lastLow = df.low[df.low.length - 1];

    const pivot = lastHigh.plus(lastLow).plus(lastClose).dividedBy(3);
    const r1 = pivot.plus(lastHigh.minus(lastLow).times(0.382));
    const r2 = pivot.plus(lastHigh.minus(lastLow));
    const s1 = pivot.minus(lastHigh.minus(lastLow).times(0.382));
    const s2 = pivot.minus(lastHigh.minus(lastLow));

    return { pivot, r1, r2, s1, s2 };
}

/**
 * @function calculateEhlSupertrendIndicators
 * @description Calculates a comprehensive set of indicators for the Ehlers Supertrend strategy.
 * Includes ATR, Fisher Transform, Supertrend (Fast & Slow), RSI, ADX, and Volume Spike.
 * @param {Array<Object>} klines - An array of kline data objects.
 * @param {Object} config - The configuration object containing indicator settings.
 * @returns {Array<Object>} An array of kline objects augmented with calculated indicator values.
 */
export function calculateEhlSupertrendIndicators(klines, config) {
    if (!klines || klines.length === 0) {
        return [];
    }

    const highPrices = klines.map(k => new Decimal(k.high));
    const lowPrices = klines.map(k => new Decimal(k.low));
    const closePrices = klines.map(k => new Decimal(k.close));
    const volumes = klines.map(k => new Decimal(k.volume));

    // ATR
    const atr = calculateATR(highPrices, lowPrices, closePrices, config.ATR_PERIOD);

    // Ehlers Fisher Transform
    const fisher = calculateFisherTransform(highPrices, lowPrices, config.EHLERS_FISHER_PERIOD);
    const fisherSignal = calculateSMA(fisher.filter(d => !d.isNaN()), 1); // Simple 1-period SMA for signal

    // Supertrend Fast
    const [stFastLine, stFastDirection] = calculateSupertrend(highPrices, lowPrices, closePrices, config.EST_FAST_LENGTH, new Decimal(config.EST_FAST_MULTIPLIER));

    // Supertrend Slow
    const [stSlowLine, stSlowDirection] = calculateSupertrend(highPrices, lowPrices, closePrices, config.EST_SLOW_LENGTH, new Decimal(config.EST_SLOW_MULTIPLIER));

    // RSI
    const rsi = calculateRSI(closePrices, config.RSI_PERIOD);

    // ADX
    const adx = calculateADX(highPrices, lowPrices, closePrices, config.ADX_PERIOD);

    // Volume MA and Spike
    const volumeMa = calculateSMA(volumes, config.VOLUME_MA_PERIOD);
    const volSpike = volumes.map((vol, i) => (volumeMa[i].gt(0) && vol.dividedBy(volumeMa[i]).gt(config.VOLUME_THRESHOLD_MULTIPLIER)));

    // Combine into a DataFrame-like structure (array of objects)
    const indicators = klines.map((kline, i) => ({
        ...kline,
        atr: atr[i] || new Decimal(NaN),
        fisher: fisher[i] || new Decimal(NaN),
        fisher_signal: fisherSignal[i] || new Decimal(NaN),
        st_fast_line: stFastLine[i] || new Decimal(NaN),
        st_fast_direction: stFastDirection[i] || new Decimal(NaN),
        st_slow_line: stSlowLine[i] || new Decimal(NaN),
        st_slow_direction: stSlowDirection[i] || new Decimal(NaN),
        rsi: rsi[i] || new Decimal(NaN),
        adx: adx.adx[i] || new Decimal(NaN),
        volume_ma: volumeMa[i] || new Decimal(NaN),
        volume_spike: volumeSpike[i] || false,
    }));

    return indicators;
}

/**
 * @function calculateFisherTransform
 * @description Calculates the Fisher Transform.
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {number} period - The period for the Fisher Transform calculation.
 * @returns {Array<Decimal>} An array of Fisher Transform values.
 */
export function calculateFisherTransform(high, low, period) {
    const fisher = [];
    const prevMaxH = [];
    const prevMinL = [];

    for (let i = 0; i < high.length; i++) {
        const startIndex = Math.max(0, i - period + 1);
        prevMaxH[i] = Decimal.max(...high.slice(startIndex, i + 1));
        prevMinL[i] = Decimal.min(...low.slice(startIndex, i + 1));

        let val = new Decimal(0);
        if (!prevMaxH[i].minus(prevMinL[i]).isZero()) {
            val = new Decimal(0.33).times(high[i].plus(low[i]).dividedBy(2).minus(prevMinL[i]).dividedBy(prevMaxH[i].minus(prevMinL[i])).times(2).minus(1)).plus(new Decimal(0.67).times(i > 0 ? fisher[i - 1] : new Decimal(0)));
        }
        fisher.push(val);
    }

    const transformedFisher = fisher.map(val => {
        if (val.isNaN()) return new Decimal(NaN);
        const tanhArg = new Decimal(0.999).times(val); // Clip to avoid tanh(x) for x >= 1
        return new Decimal(0.5).times(tanhArg.plus(1).dividedBy(new Decimal(1).minus(tanhArg)).log());
    });
    return transformedFisher;
}

/**
 * @function calculateSupertrend
 * @description Calculates the Supertrend indicator.
 * @param {Array<Decimal>} high - An array of Decimal.js high prices.
 * @param {Array<Decimal>} low - An array of Decimal.js low prices.
 * @param {Array<Decimal>} close - An array of Decimal.js closing prices.
 * @param {number} period - The period for the Supertrend calculation.
 * @param {Decimal} multiplier - The multiplier for the ATR.
 * @returns {Array<Array<Decimal>>} An array containing two arrays: [supertrend values, direction (1 for uptrend, -1 for downtrend)].
 */
export function calculateSupertrend(high, low, close, period, multiplier) {
    const atr = calculateATR(high, low, close, period);
    const basicUpperBand = high.map((h, i) => h.plus(low[i]).dividedBy(2).plus(multiplier.times(atr[i])));
    const basicLowerBand = low.map((l, i) => h.plus(l).dividedBy(2).minus(multiplier.times(atr[i])));

    const finalUpperBand = [];
    const finalLowerBand = [];
    const supertrend = [];
    const direction = []; // 1 for uptrend, -1 for downtrend

    for (let i = 0; i < close.length; i++) {
        if (i === 0) {
            finalUpperBand.push(basicUpperBand[i]);
            finalLowerBand.push(basicLowerBand[i]);
            supertrend.push(new Decimal(NaN)); // No trend yet
            direction.push(new Decimal(0));
            continue;
        }

        // Calculate final bands
        let currentFinalUpper = basicUpperBand[i];
        if (basicUpperBand[i].lt(finalUpperBand[i - 1]) || close[i - 1].gt(finalUpperBand[i - 1])) {
            currentFinalUpper = basicUpperBand[i];
        } else {
            currentFinalUpper = finalUpperBand[i - 1];
        }
        finalUpperBand.push(currentFinalUpper);

        let currentFinalLower = basicLowerBand[i];
        if (basicLowerBand[i].gt(finalLowerBand[i - 1]) || close[i - 1].lt(finalLowerBand[i - 1])) {
            currentFinalLower = basicLowerBand[i];
        } else {
            currentFinalLower = finalLowerBand[i - 1];
        }
        finalLowerBand.push(currentFinalLower);

        // Determine Supertrend value and direction
        let currentSupertrend;
        let currentDirection;

        if (supertrend[i - 1].isNaN()) { // First valid Supertrend point
            currentSupertrend = close[i].gt(currentFinalUpper) ? currentFinalLower : currentFinalUpper;
            currentDirection = close[i].gt(currentFinalUpper) ? new Decimal(1) : new Decimal(-1);
        } else if (supertrend[i - 1].eq(finalUpperBand[i - 1])) { // Previous was downtrend
            if (close[i].gt(currentFinalUpper)) {
                currentSupertrend = currentFinalLower;
                currentDirection = new Decimal(1);
            } else {
                currentSupertrend = currentFinalUpper;
                currentDirection = new Decimal(-1);
            }
        } else { // Previous was uptrend
            if (close[i].lt(currentFinalLower)) {
                currentSupertrend = currentFinalUpper;
                currentDirection = new Decimal(-1);
            } else {
                currentSupertrend = currentFinalLower;
                currentDirection = new Decimal(1);
            }
        }

        supertrend.push(currentSupertrend);
        direction.push(currentDirection);
    }

    return [supertrend, direction];
}

/**
 * @function buildAllIndicators
 * @description Builds a DataFrame-like object augmented with all configured technical indicator values.
 * This function processes raw kline data, calculates various indicators using Decimal.js,
 * and handles NaN values by forward-filling and then filling initial NaNs with zero.
 * @param {Array<Object>} klines - An array of kline data objects, each with `open`, `high`, `low`, `close`, `volume`.
 * @returns {DataFrame} A DataFrame-like object with kline data and calculated indicator columns.
 */
export function buildAllIndicators(klines) {
    if (!klines || klines.length === 0) {
        return new DataFrame([]);
    }

    // Convert klines array of objects to DataFrame
    let df = new DataFrame(klines);

    // Ensure OHLCV columns are numbers and handle NaNs (ffill then fill 0)
    const ohlcvColumns = ['open', 'high', 'low', 'close', 'volume'];
    for (const col of ohlcvColumns) {
        df = df.cast(col, Number);
        let colData = df.toArray(col);
        for(let i = 0; i < colData.length; i++) {
            if (isNaN(colData[i]) || colData[i] === null) {
                colData[i] = i > 0 ? colData[i-1] : new Decimal(0); // ffill then fill initial NaNs with 0
            }
        }
        df = df.withColumn(col, (row, i) => colData[i]);
    }

    const highPrices = df.toArray('high');
    const lowPrices = df.toArray('low');
    const closePrices = df.toArray('close');
    const volumes = df.toArray('volume');

    // ATR
    const atrSeries = calculateATR(highPrices, lowPrices, closePrices, CONFIG.ATR_PERIOD);
    df = df.withColumn('atr', (row, i) => atrSeries[i]);

    // Chandelier Exit related calculations
    const highestHigh = [];
    const lowestLow = [];
    for (let i = 0; i < highPrices.length; i++) {
        const startIndex = Math.max(0, i - CONFIG.ATR_PERIOD + 1);
        highestHigh[i] = Decimal.max(...highPrices.slice(startIndex, i + 1));
        lowestLow[i] = Decimal.min(...lowPrices.slice(startIndex, i + 1));
    }
    df = df.withColumn('highest_high', (row, i) => highestHigh[i]);
    df = df.withColumn('lowest_low', (row, i) => lowestLow[i]);

    const volatilityLookback = CONFIG.VOLATILITY_LOOKBACK;
    const pricePctChange = [];
    for (let i = 1; i < closePrices.length; i++) {
        pricePctChange.push(closePrices[i].minus(closePrices[i-1]).dividedBy(closePrices[i-1]));
    }
    const priceStd = [];
    for (let i = 0; i < pricePctChange.length; i++) {
        const window = pricePctChange.slice(Math.max(0, i - volatilityLookback + 1), i + 1);
        const mean = avg(window);
        const std = stdDev(window, mean);
        priceStd.push(std);
    }
    
    let dynamicMultiplier = new Array(df.count()).fill(new Decimal(CONFIG.CHANDELIER_MULTIPLIER));
    if (df.count() >= volatilityLookback && priceStd.length > 0) {
        const meanPriceStd = avg(priceStd);
        if (meanPriceStd.gt(0)) {
            for (let i = 0; i < priceStd.length; i++) {
                dynamicMultiplier[i+1] = Decimal.min(
                    new Decimal(CONFIG.MAX_ATR_MULTIPLIER),
                    Decimal.max(new Decimal(CONFIG.MIN_ATR_MULTIPLIER), new Decimal(CONFIG.CHANDELIER_MULTIPLIER).times(priceStd[i].dividedBy(meanPriceStd)))
                );
            }
        }
    }
    df = df.withColumn('dynamic_multiplier', (row, i) => dynamicMultiplier[i]);

    const chLong = df.toArray('highest_high').map((val, i) => val.minus(atrSeries[i].times(dynamicMultiplier[i])));
    const chShort = df.toArray('lowest_low').map((val, i) => val.plus(atrSeries[i].times(dynamicMultiplier[i])));
    df = df.withColumn('ch_long', (row, i) => chLong[i]);
    df = df.withColumn('ch_short', (row, i) => chShort[i]);
    
    // EMAs
    const trendEma = calculateEMA(closePrices, CONFIG.TREND_EMA_PERIOD);
    const emaS = calculateEMA(closePrices, CONFIG.EMA_SHORT_PERIOD);
    const emaL = calculateEMA(closePrices, CONFIG.EMA_LONG_PERIOD);
    df = df.withColumn('trend_ema', (row, i) => trendEma[i]);
    df = df.withColumn('ema_s', (row, i) => emaS[i]);
    df = df.withColumn('ema_l', (row, i) => emaL[i]);

    // RSI
    const rsi = calculateRSI(closePrices, CONFIG.RSI_PERIOD);
    df = df.withColumn('rsi', (row, i) => rsi[i]);

    // Volume MA and Spike
    const volumeMa = calculateSMA(volumes, CONFIG.VOLUME_MA_PERIOD);
    const volSpike = volumes.map((vol, i) => (volumeMa[i].gt(0) && vol.dividedBy(volumeMa[i]).gt(CONFIG.VOLUME_THRESHOLD_MULTIPLIER)));
    df = df.withColumn('vol_ma', (row, i) => volumeMa[i]);
    df = df.withColumn('vol_spike', (row, i) => volSpike[i]);
    
    // Ehlers Supertrend (from stindicators.js logic)
    const [stSlowLine, stSlowDirection] = calculateSupertrend(highPrices, lowPrices, closePrices, CONFIG.EST_SLOW_LENGTH, new Decimal(CONFIG.EST_SLOW_MULTIPLIER));
    df = df.withColumn('est_slow', (row, i) => stSlowDirection[i]); // Store direction as est_slow

    // Fisher Transform
    const fisher = calculateFisherTransform(highPrices, lowPrices, CONFIG.EHLERS_FISHER_PERIOD);
    df = df.withColumn('fisher', (row, i) => fisher[i]);

    // Stochastic Oscillator
    if (CONFIG.USE_STOCH_FILTER) {
        const [stochK, stochD] = calculateStochasticOscillator(highPrices, lowPrices, closePrices, CONFIG.STOCH_K_PERIOD, CONFIG.STOCH_D_PERIOD, CONFIG.STOCH_SMOOTHING);
        df = df.withColumn('stoch_k', (row, i) => stochK[i]);
        df = df.withColumn('stoch_d', (row, i) => stochD[i]);
    }
    
    // MACD
    if (CONFIG.USE_MACD_FILTER) {
        const macd = calculateMACD(closePrices, CONFIG.MACD_FAST_PERIOD, CONFIG.MACD_SLOW_PERIOD, CONFIG.MACD_SIGNAL_PERIOD);
        df = df.withColumn('macd_line', (row, i) => macd.macd_line[i]);
        df = df.withColumn('macd_signal', (row, i) => macd.signal_line[i]);
        df = df.withColumn('macd_hist', (row, i) => macd.histogram[i]);
    }

    // ADX
    if (CONFIG.USE_ADX_FILTER) {
        const adx = calculateADX(highPrices, lowPrices, closePrices, CONFIG.ADX_PERIOD);
        df = df.withColumn('adx', (row, i) => adx.adx[i]);
    }

    // Final ffill and fillna(0) for all new columns
    for (const col of df.listColumns()) {
        let colData = df.toArray(col);
        for(let i = 0; i < colData.length; i++) {
            if (colData[i] === null || (colData[i] instanceof Decimal && colData[i].isNaN())) {
                colData[i] = i > 0 ? colData[i-1] : new Decimal(0); // ffill then fill initial NaNs with 0
            }
        }
        df = df.withColumn(col, (row, i) => colData[i]);
    }

    return df;
}
