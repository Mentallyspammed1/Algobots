const { Supertrend, RSI, SMA, FisherTransform, ATR } = require('technicalindicators');
const { Decimal } = require('decimal.js');

// Helper to calculate EMA (Decimal.js compatible)
/**
 * Calculates the Exponentially Weighted Moving Average (EMA) for a given series.
 * @param {Array<Decimal>} series - The input data series.
 * @param {number} span - The span (period) for the EMA calculation.
 * @param {number} [minPeriods=0] - The minimum number of periods required to start calculating EMA.
 * @returns {Array<Decimal>} An array containing the EMA values.
 */
function ewmMeanCustom(series, span, minPeriods = 0) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < minPeriods) return new Array(seriesDecimals.length).fill(new Decimal(NaN));
    
    const alpha = new Decimal(2).dividedBy(new Decimal(span).plus(1));
    const result = new Array(seriesDecimals.length).fill(new Decimal(NaN));
    let ema = new Decimal(NaN); // Initialize ema to NaN
    
    for (let i = 0; i < seriesDecimals.length; i++) {
        const value = seriesDecimals[i];

        if (value.isNaN()) {
            ema = new Decimal(NaN); // Propagate NaN
            result[i] = new Decimal(NaN);
            continue;
        }

        if (ema.isNaN()) { // If ema is NaN, initialize it with the current value
            ema = value;
        } else {
            ema = value.times(alpha).plus(ema.times(new Decimal(1).minus(alpha)));
        }

        if (i + 1 >= minPeriods) { // Check if enough periods have passed
            result[i] = ema;
        }
    }
    
    return result;
}

// Helper to calculate SMA (Decimal.js compatible)
/**
 * Calculates the Simple Moving Average (SMA) for a given series.
 * @param {Array<Decimal>} series - The input data series.
 * @param {number} window - The window (period) for the SMA calculation.
 * @returns {Array<Decimal>} An array containing the SMA values.
 */
function rollingMean(series, window) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < window) return new Array(seriesDecimals.length).fill(new Decimal(NaN));
    
    const result = new Array(seriesDecimals.length).fill(new Decimal(NaN));
    for (let i = window - 1; i < seriesDecimals.length; i++) {
        const sum = seriesDecimals.slice(i - window + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
        result[i] = sum.dividedBy(window);
    }
    return result;
}

// Helper to calculate True Range (Decimal.js compatible)
/**
 * Calculates the True Range (TR) for a given set of OHLC prices.
 * @param {Array<Decimal>} high - Array of high prices.
 * @param {Array<Decimal>} low - Array of low prices.
 * @param {Array<Decimal>} close - Array of close prices.
 * @returns {Array<Decimal>} An array containing the True Range values.
 */
function calculateTR(high, low, close) {
    const tr = [new Decimal(NaN)]; // Pad with NaN for the first element
    for (let i = 1; i < high.length; i++) {
        const h = high[i]; const l = low[i]; const cPrev = close[i - 1];
        tr.push(Decimal.max(h.minus(l), h.minus(cPrev).abs(), l.minus(cPrev).abs()));
    }
    return tr;
}

// Helper to calculate ATR (Decimal.js compatible)
function calculateATR(high, low, close, period) {
    if (high.length < period + 1) return new Array(high.length).fill(new Decimal(NaN));
    const tr = calculateTR(high, low, close);
    return ewmMeanCustom(tr, period, period);
}

// Helper to calculate RSI (Decimal.js compatible)
function calculateRSI(close, period) {
    if (close.length <= period) return new Array(close.length).fill(new Decimal(NaN));
    
    const delta = close.map((c, i) => i > 0 ? c.minus(close[i-1]) : new Decimal(0));
    const gain = delta.map(d => Decimal.max(0, d));
    const loss = delta.map(d => Decimal.max(0, d.neg()));

    const avgGain = ewmMeanCustom(gain, period, period);
    const avgLoss = ewmMeanCustom(loss, period, period);
    
    const rsi = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = 0; i < close.length; i++) {
        if (!avgGain[i].isNaN() && !avgLoss[i].isNaN()) {
            if (avgLoss[i].isZero()) {
                rsi[i] = new Decimal(100);
            } else {
                const rs = avgGain[i].dividedBy(avgLoss[i]);
                rsi[i] = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs)));
            }
        }
    }
    return rsi.map(val => val.isNaN() ? new Decimal(50) : val);
}

// Helper to calculate StochRSI (Decimal.js compatible)
function calculateStochRSI(close, period, kPeriod, dPeriod) {
    if (close.length <= period + dPeriod) {
        return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];
    }
    
    const rsi = calculateRSI(close, period);
    const lowestRsi = new Array(close.length).fill(new Decimal(NaN));
    const highestRsi = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < close.length; i++) {
        const rsiWindow = rsi.slice(i - period + 1, i + 1).filter(val => !val.isNaN());
        if (rsiWindow.length > 0) {
            lowestRsi[i] = Decimal.min(...rsiWindow);
            highestRsi[i] = Decimal.max(...rsiWindow);
        }
    }
    
    const stochRsiK = new Array(close.length).fill(new Decimal(NaN));
    for (let i = 0; i < close.length; i++) {
        if (!rsi[i].isNaN() && !lowestRsi[i].isNaN() && !highestRsi[i].isNaN()) {
            const denominator = highestRsi[i].minus(lowestRsi[i]);
            if (denominator.isZero()) {
                stochRsiK[i] = new Decimal(50);
            } else {
                stochRsiK[i] = (rsi[i].minus(lowestRsi[i])).dividedBy(denominator).times(100);
            }
        }
    }
    
    const stochRsiD = ewmMeanCustom(stochRsiK, dPeriod, dPeriod);
    
    return [stochRsiK, stochRsiD];
}

// Helper to calculate Bollinger Bands (Decimal.js compatible)
function calculateBollingerBands(close, period, stdDev) {
    if (close.length < period) {
        return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];
    }
    
    const middleBand = rollingMean(close, period);
    const std = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < close.length; i++) {
        const window = close.slice(i - period + 1, i + 1);
        const mean = middleBand[i];
        const sumOfSquares = window.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0));
        std[i] = (sumOfSquares.dividedBy(period)).sqrt();
    }
    
    const upperBand = middleBand.map((mb, i) => mb.plus(std[i].times(stdDev)));
    const lowerBand = middleBand.map((mb, i) => mb.minus(std[i].times(stdDev)));
    
    return [upperBand, middleBand, lowerBand];
}

// Helper to calculate VWAP (Decimal.js compatible)
function calculateVWAP(high, low, close, volume) {
    if (high.length === 0) return new Array(high.length).fill(new Decimal(NaN));
    
    const typicalPrice = high.map((h, i) => (h.plus(low[i]).plus(close[i])).dividedBy(3));
    const tpVol = typicalPrice.map((tp, i) => tp.times(volume[i]));
    
    const cumulativeTpVol = new Array(high.length).fill(new Decimal(NaN));
    const cumulativeVol = new Array(high.length).fill(new Decimal(NaN));
    const vwap = new Array(high.length).fill(new Decimal(NaN));
    
    let sumTpVol = new Decimal(0);
    let sumVol = new Decimal(0);
    
    for (let i = 0; i < high.length; i++) {
        sumTpVol = sumTpVol.plus(tpVol[i]);
        sumVol = sumVol.plus(volume[i]);
        cumulativeTpVol[i] = sumTpVol;
        cumulativeVol[i] = sumVol;
        
        if (sumVol.gt(0)) {
            vwap[i] = sumTpVol.dividedBy(sumVol);
        } else {
            vwap[i] = new Decimal(NaN);
        }
    }
    
    return vwap;
}

// Helper to calculate MACD (Decimal.js compatible)
function calculateMACD(close, fastPeriod, slowPeriod, signalPeriod) {
    if (close.length < slowPeriod + signalPeriod) {
        return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];
    }
    
    const emaFast = ewmMeanCustom(close, fastPeriod, fastPeriod);
    const emaSlow = ewmMeanCustom(close, slowPeriod, slowPeriod);
    const macdLine = emaFast.map((fast, i) => fast.minus(emaSlow[i] || new Decimal(NaN)));
    const signalLine = ewmMeanCustom(macdLine, signalPeriod, signalPeriod);
    const histogram = macdLine.map((macd, i) => macd.minus(signalLine[i] || new Decimal(NaN)));
    
    return [macdLine, signalLine, histogram];
}

// Helper to calculate ADX (Decimal.js compatible)
function calculateADX(high, low, close, period) {
    if (high.length < period * 2) {
        return [new Array(high.length).fill(new Decimal(NaN)), new Array(high.length).fill(new Decimal(NaN)), new Array(high.length).fill(new Decimal(NaN))];
    }
    
    const tr = calculateATR(high, low, close, period);
    
    const plusDM = new Array(high.length).fill(new Decimal(0));
    const minusDM = new Array(high.length).fill(new Decimal(0));
    
    for (let i = 1; i < high.length; i++) {
        const upMove = high[i].minus(high[i - 1]);
        const downMove = low[i - 1].minus(low[i]);
        plusDM[i] = (upMove.gt(downMove) && upMove.gt(0)) ? upMove : new Decimal(0);
        minusDM[i] = (downMove.gt(upMove) && downMove.gt(0)) ? downMove : new Decimal(0);
    }
    
    const smoothedPlusDM = ewmMeanCustom(plusDM, period, period);
    const smoothedMinusDM = ewmMeanCustom(minusDM, period, period);

    const plusDI = smoothedPlusDM.map((val, i) => 
        (!val.isNaN() && !tr[i].isNaN() && tr[i].gt(0)) ? val.dividedBy(tr[i]).times(100) : new Decimal(NaN)
    );
    const minusDI = smoothedMinusDM.map((val, i) => 
        (!val.isNaN() && !tr[i].isNaN() && tr[i].gt(0)) ? val.dividedBy(tr[i]).times(100) : new Decimal(NaN)
    );
    
    const dx = new Array(high.length).fill(new Decimal(NaN));
    for (let i = 0; i < high.length; i++) {
        if (!plusDI[i].isNaN() && !minusDI[i].isNaN()) {
            const diDiff = plusDI[i].minus(minusDI[i]).abs();
            const diSum = plusDI[i].plus(minusDI[i]);
            dx[i] = (diSum.isZero()) ? new Decimal(0) : diDiff.dividedBy(diSum).times(100);
        }
    }
    
    const adx = ewmMeanCustom(dx, period, period);
    
    return [adx, plusDI, minusDI];
}

// Helper to calculate OBV (Decimal.js compatible)
function calculateOBV(close, volume, emaPeriod) {
    if (close.length === 0) return null;
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
    const obvEma = ewmMeanCustom(obv, emaPeriod, emaPeriod);
    return { obv, obv_ema: obvEma };
}

// Helper to calculate CMF (Decimal.js compatible)
function calculateCMF(high, low, close, volume, period) {
    if (close.length < period) return [];
    const mfv = [];
    for (let i = 0; i < close.length; i++) {
        const clv = close[i].equals(high[i]) && close[i].equals(low[i])
            ? new Decimal(0)
            : close[i].minus(low[i]).minus(high[i].minus(close[i]))
                .dividedBy(high[i].minus(low[i]));
        mfv.push(clv.times(volume[i]));
    }

    const cmf = [];
    for (let i = 0; i < close.length; i++) {
        if (i < period - 1) {
            cmf.push(new Decimal(NaN));
        } else {
            const sumMfv = mfv.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
            const sumVol = volume.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
            cmf.push(sumVol.isZero() ? new Decimal(0) : sumMfv.dividedBy(sumVol));
        }
    }
    return cmf;
}

// Helper to calculate Ichimoku Cloud (Decimal.js compatible)
function calculateIchimokuCloud(high, low, close, tenkan, kijun, senkouBPeriod, chikouOffset) {
    const tenkanSen = [], kijunSen = [], senkouSpanA = [], senkouSpanB = [], chikouSpan = [];

    for (let i = 0; i < close.length; i++) {
        // Tenkan-sen
        if (i < tenkan - 1) {
            tenkanSen.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...high.slice(i - tenkan + 1, i + 1));
            const windowLow = Decimal.min(...low.slice(i - tenkan + 1, i + 1));
            tenkanSen.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Kijun-sen
        if (i < kijun - 1) {
            kijunSen.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...high.slice(i - kijun + 1, i + 1));
            const windowLow = Decimal.min(...low.slice(i - kijun + 1, i + 1));
            kijunSen.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Senkou Span A
        if (i + chikouOffset < close.length) {
            senkouSpanA.push(tenkanSen[i].plus(kijunSen[i]).dividedBy(2));
        } else {
            senkouSpanA.push(new Decimal(NaN));
        }

        // Senkou Span B
        if (i < senkouBPeriod - 1) {
            senkouSpanB.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...high.slice(i - senkouBPeriod + 1, i + 1));
            const windowLow = Decimal.min(...low.slice(i - senkouBPeriod + 1, i + 1));
            senkouSpanB.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Chikou Span
        if (i >= chikouOffset) {
            chikouSpan.push(close[i - chikouOffset]);
        } else {
            chikouSpan.push(new Decimal(NaN));
        }
    }

    // Shift forward
    for (let i = 0; i < chikouOffset; i++) {
        senkouSpanA.unshift(new Decimal(NaN));
        senkouSpanB.unshift(new Decimal(NaN));
    }
    senkouSpanA.splice(close.length);
    senkouSpanB.splice(close.length);

    return { tenkan_sen: tenkanSen, kijun_sen: kijunSen, senkou_span_a: senkouSpanA, senkou_span_b: senkouSpanB, chikou_span: chikouSpan };
}

// Helper to calculate PSAR (Decimal.js compatible)
function calculatePSAR(high, low, close, acceleration, maxAcceleration) {
    if (close.length < 2) return null;
    const psar = [low[0]];
    const direction = [1];
    let acc = acceleration;
    let ep = high[0];

    for (let i = 1; i < close.length; i++) {
        let nextPsar = psar[i - 1].plus(acc.times(ep.minus(psar[i - 1])));
        let nextDir = direction[i - 1];
        let nextAcc = acc;
        let nextEp = ep;

        if (nextDir === 1) {
            if (low[i].lt(nextPsar)) {
                nextDir = -1;
                nextPsar = ep;
                nextAcc = acceleration;
                nextEp = low[i];
            } else {
                if (high[i].gt(ep)) {
                    nextEp = high[i];
                    nextAcc = Decimal.min(acc.plus(acceleration), maxAcceleration);
                }
                if (low[i - 1].lt(nextPsar)) nextPsar = low[i - 1];
                if (i > 1 && low[i - 2].lt(nextPsar)) nextPsar = low[i - 2];
            }
        } else {
            if (high[i].gt(nextPsar)) {
                nextDir = 1;
                nextPsar = ep;
                nextAcc = acceleration;
                nextEp = high[i];
            } else {
                if (low[i].lt(ep)) {
                    nextEp = low[i];
                    nextAcc = Decimal.min(acc.plus(acceleration), maxAcceleration);
                }
                if (high[i - 1].gt(nextPsar)) nextPsar = high[i - 1];
                if (i > 1 && high[i - 2].gt(nextPsar)) nextPsar = high[i - 2];
            }
        }

        psar.push(nextPsar);
        direction.push(nextDir);
        acc = nextAcc;
        ep = nextEp;
    }

    return { psar, direction };
}

// Helper to calculate Ehlers SuperTrend (Decimal.js compatible)
function calculateEhlersSupertrend(high, low, close, period, multiplier) {
    if (close.length < period * 2) return { supertrend: new Array(close.length).fill(new Decimal(NaN)), direction: new Array(close.length).fill(0) };

    const src = close;
    const supertrend = [];
    const direction = [];

    // Super Smoother Filter
    const smooth = [];
    const arg = new Decimal(Math.SQRT2 * Math.PI).dividedBy(new Decimal(period));
    const a1 = new Decimal(Math.exp(arg.negated().toNumber()));
    const b1 = new Decimal(2).times(a1).times(new Decimal(Math.cos(arg.toNumber())));
    const coeff2 = b1;
    const coeff3 = a1.times(a1).negated();
    const coeff1 = new Decimal(1).minus(coeff2).minus(coeff3);

    for (let i = 0; i < src.length; i++) {
        if (i < 2) {
            smooth.push(src[i]);
        } else {
            smooth.push(
                coeff1.times(src[i])
                    .plus(coeff2.times(smooth[i - 1]))
                    .plus(coeff3.times(smooth[i - 2]))
            );
        }
    }

    // Median Price
    const median = [];
    for (let i = 0; i < src.length; i++) {
        median.push(src[i].plus(high[i]).plus(low[i]).dividedBy(3));
    }

    // Trend Logic
    const trendUp = [], trendDown = [];
    for (let i = 0; i < src.length; i++) {
        if (i < period) {
            trendUp.push(new Decimal(Infinity));
            trendDown.push(new Decimal(-Infinity));
            supertrend.push(smooth[i]);
            direction.push(1);
        } else {
            const atr = calculateATR(high, low, smooth, period)[i];
            const up = median[i].minus(atr.times(multiplier));
            const dn = median[i].plus(atr.times(multiplier));

            let finalUp = up.lt(trendUp[i - 1]) || src[i - 1].gt(trendUp[i - 1]) ? up : trendUp[i - 1];
            let finalDn = dn.gt(trendDown[i - 1]) || src[i - 1].lt(trendDown[i - 1]) ? dn : trendDown[i - 1];

            let dir = direction[i - 1];
            let st = supertrend[i - 1];

            if (dir === -1 && src[i].gt(finalDn)) {
                dir = 1;
                st = finalUp;
            } else if (dir === 1 && src[i].lt(finalUp)) {
                dir = -1;
                st = finalDn;
            } else {
                st = dir === 1 ? finalUp : finalDn;
            }

            trendUp.push(finalUp);
            trendDown.push(finalDn);
            supertrend.push(st);
            direction.push(dir);
        }
    }

    return { supertrend, direction };
}

// Helper to calculate Fisher Transform (Decimal.js compatible)
function calculateFisherTransform(high, low, period) {
    const length = high.length;
    const fisher = new Array(length).fill(new Decimal(0));
    const trigger = new Array(length).fill(new Decimal(0));
    const values = new Array(length).fill(new Decimal(0));
    let fish = new Array(length).fill(new Decimal(0));

    for (let i = 0; i < length; i++) {
        const highestHigh = Decimal.max(...high.slice(Math.max(0, i - period + 1), i + 1));
        const lowestLow = Decimal.min(...low.slice(Math.max(0, i - period + 1), i + 1));
        const range = highestHigh.minus(lowestLow);
        const price = (high[i].plus(low[i])).dividedBy(2);
        
        let value = new Decimal(0);
        if (range.gt(0)) {
            value = new Decimal(0.33).times(new Decimal(2).times(price.minus(lowestLow)).dividedBy(range).minus(0.5)).plus(new Decimal(0.67).times(values[i-1] || new Decimal(0)));
        } else {
            value = values[i-1] || new Decimal(0);
        }

        if (value.gt(0.99)) value = new Decimal(0.999);
        if (value.lt(-0.99)) value = new Decimal(-0.999);
        
        values[i] = value;
        
        fish[i] = new Decimal(0.5).times(new Decimal(1).plus(value).dividedBy(new Decimal(1).minus(value)).ln()).plus(new Decimal(0.5).times(fish[i-1] || new Decimal(0)));
        fisher[i] = fish[i];
        trigger[i] = fish[i-1] || new Decimal(0);
    }

    return { fisher, trigger };
}

/**
 * Centralized indicator calculator for Ehlers Supertrend strategy.
 * Uses technicalindicators library for some calculations, and custom Decimal.js compatible ones for others.
 * @param {Array<Object>} klines - Raw kline data (objects with Decimal values for OHLCV)
 * @param {Object} config - Strategy config
 * @param {Object} logger - Logger instance
 * @returns {Array<Object>} Klines with indicators attached
 */
function calculateEhlSupertrendIndicators(klines, config, logger) {
    if (!klines || klines.length === 0) return [];

    // Ensure all OHLCV values are Decimal.js objects
    const processedKlines = klines.map(kline => ({
        ...kline,
        open: new Decimal(kline.open),
        high: new Decimal(kline.high),
        low: new Decimal(kline.low),
        close: new Decimal(kline.close),
        volume: new Decimal(kline.volume)
    }));

    const input = {
        open: processedKlines.map(k => k.open),
        high: processedKlines.map(k => k.high),
        low: processedKlines.map(k => k.low),
        close: processedKlines.map(k => k.close),
        volume: processedKlines.map(k => k.volume)
    };

    let df_with_indicators = processedKlines.map(kline => ({ ...kline }));

    try {
        const stFastConfig = config.strategy.est_fast;
        const stFastResult = calculateEhlersSupertrend(input.high, input.low, input.close, stFastConfig.length, stFastConfig.multiplier);
        df_with_indicators.forEach((k, i) => {
            k.st_fast_line = stFastResult?.supertrend[i] !== undefined ? stFastResult.supertrend[i] : new Decimal(NaN);
            k.st_fast_direction = stFastResult?.direction[i] !== undefined ? stFastResult.direction[i] : 0;
        });
    } catch (e) {
        logger.error(`Error calculating fast Supertrend: ${e.message}`);
        df_with_indicators.forEach(k => { k.st_fast_line = new Decimal(0); k.st_fast_direction = 0; });
    }

    try {
        const stSlowConfig = config.strategy.est_slow;
        const stSlowResult = calculateEhlersSupertrend(input.high, input.low, input.close, stSlowConfig.length, stSlowConfig.multiplier);
        df_with_indicators.forEach((k, i) => {
            k.st_slow_line = stSlowResult?.supertrend[i] !== undefined ? stSlowResult.supertrend[i] : new Decimal(NaN);
            k.st_slow_direction = stSlowResult?.direction[i] !== undefined ? stSlowResult.direction[i] : 0;
        });
    } catch (e) {
        logger.error(`Error calculating slow Supertrend: ${e.message}`);
        df_with_indicators.forEach(k => { k.st_slow_line = new Decimal(0); k.st_slow_direction = 0; });
    }

    try {
        const rsiResult = calculateRSI(input.close, config.strategy.rsi.period);
        df_with_indicators.forEach((k, i) => { 
            k.rsi = rsiResult[i] !== undefined ? rsiResult[i] : new Decimal(NaN);
        });
    } catch (e) {
        logger.error(`Error calculating RSI: ${e.message}`);
        df_with_indicators.forEach(k => { k.rsi = new Decimal(0); });
    }

    try {
        const volumeMASeries = rollingMean(input.volume, config.strategy.volume.ma_period);
        df_with_indicators.forEach((k, i) => {
            k.volume_ma = volumeMASeries[i] !== undefined ? volumeMASeries[i] : new Decimal(NaN);
            k.volume_spike = k.volume_ma.gt(0) && (k.volume.dividedBy(k.volume_ma)).gt(config.strategy.volume.threshold_multiplier);
        });
    } catch (e) {
        logger.error(`Error calculating Volume MA: ${e.message}`);
        df_with_indicators.forEach(k => { k.volume_ma = new Decimal(0); k.volume_spike = false; });
    }

    try {
        const fisherConfig = config.strategy.ehlers_fisher;
        const fisherResult = calculateFisherTransform(input.high, input.low, fisherConfig.period);
        df_with_indicators.forEach((k, i) => {
            k.fisher = fisherResult?.fisher[i] !== undefined ? fisherResult.fisher[i] : new Decimal(NaN);
            k.fisher_signal = fisherResult?.trigger[i] !== undefined ? fisherResult.trigger[i] : new Decimal(NaN);
        });
    } catch (e) {
        logger.error(`Error calculating Fisher Transform: ${e.message}`);
        df_with_indicators.forEach(k => { k.fisher = new Decimal(0); k.fisher_signal = new Decimal(0); });
    }

    try {
        const atrResult = calculateATR(input.high, input.low, input.close, config.strategy.atr.period);
        df_with_indicators.forEach((k, i) => { 
            k.atr = atrResult[i] !== undefined ? atrResult[i] : new Decimal(NaN);
        });
    } catch (e) {
        logger.error(`Error calculating ATR: ${e.message}`);
        df_with_indicators.forEach(k => { k.atr = new Decimal(0); });
    }

    try {
        const adxResult = calculateADX(input.high, input.low, input.close, config.strategy.adx.period);
        df_with_indicators.forEach((k, i) => {
            k.adx = adxResult?.[0][i] !== undefined ? adxResult[0][i] : new Decimal(NaN);
        });
    } catch (e) {
        logger.error(`Error calculating ADX: ${e.message}`);
        df_with_indicators.forEach(k => { k.adx = new Decimal(0); });
    }
    
    // Forward-fill zeros/NaNs for continuity
    for (let i = 1; i < df_with_indicators.length; i++) {
        for (const key of ['st_fast_line', 'st_fast_direction', 'st_slow_line', 'st_slow_direction', 'rsi', 'volume_ma', 'fisher', 'fisher_signal', 'atr', 'adx']) {
            if (df_with_indicators[i][key].isNaN()) { // Check for NaN
                df_with_indicators[i][key] = df_with_indicators[i-1][key];
            }
        }
    }

    return df_with_indicators;
}

// Export All
module.exports = {
    // External Strategy Calculator
    calculateEhlSupertrendIndicators,

    // Core Indicators (Decimal.js compatible)
    calculateSMA: rollingMean,
    calculateEMA: ewmMeanCustom,
    calculateATR,
    calculateRSI,
    calculateStochRSI,
    calculateBollingerBands,
    calculateVWAP,
    calculateMACD,
    calculateADX,
    calculateOBV,
    calculateCMF,
    calculateIchimokuCloud,
    calculatePSAR,
    calculateEhlersSupertrend,
    calculateFisherTransform,

    // Utility functions (from whale.js indicators)
    ewmMeanCustom,
    rollingMean,
};
