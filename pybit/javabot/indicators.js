// indicators.js — Upgraded Technical Indicators for unified_whalebot.js
// Fully Decimal.js compatible, NaN-safe, index-aligned, production-ready

const { Supertrend, RSI, SMA, FisherTransform, ATR } = require('technicalindicators');
const { Decimal } = require('decimal.js');

/**
 * Centralized indicator calculator using external library (for EhlSupertrend strategy)
 * @param {Array<Object>} klines - Raw kline data
 * @param {Object} config - Strategy config
 * @param {Object} logger - Logger instance
 * @returns {Array<Object>} Klines with indicators attached
 */
function calculateEhlSupertrendIndicators(klines, config, logger) {
    if (!klines || klines.length === 0) return [];

    const processedKlines = klines.map(kline => ({
        ...kline,
        open: parseFloat(kline.open) || 0,
        high: parseFloat(kline.high) || 0,
        low: parseFloat(kline.low) || 0,
        close: parseFloat(kline.close) || 0,
        volume: parseFloat(kline.volume) || 0
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
        const stFastResult = Supertrend.calculate({
            high: input.high,
            low: input.low,
            close: input.close,
            period: stFastConfig.length,
            multiplier: stFastConfig.multiplier
        });
        df_with_indicators.forEach((k, i) => {
            k.st_fast_line = stFastResult[i]?.supertrend || 0;
            k.st_fast_direction = stFastResult[i]?.direction || 0;
        });
    } catch (e) {
        logger.error(`Error calculating fast Supertrend: ${e.message}`);
        df_with_indicators.forEach(k => { k.st_fast_line = 0; k.st_fast_direction = 0; });
    }

    try {
        const stSlowConfig = config.strategy.est_slow;
        const stSlowResult = Supertrend.calculate({
            high: input.high,
            low: input.low,
            close: input.close,
            period: stSlowConfig.length,
            multiplier: stSlowConfig.multiplier
        });
        df_with_indicators.forEach((k, i) => {
            k.st_slow_line = stSlowResult[i]?.supertrend || 0;
            k.st_slow_direction = stSlowResult[i]?.direction || 0;
        });
    } catch (e) {
        logger.error(`Error calculating slow Supertrend: ${e.message}`);
        df_with_indicators.forEach(k => { k.st_slow_line = 0; k.st_slow_direction = 0; });
    }

    try {
        const rsiResult = RSI.calculate({
            values: input.close,
            period: config.strategy.rsi.period
        });
        const rsiOffset = df_with_indicators.length - rsiResult.length;
        df_with_indicators.forEach((k, i) => { 
            k.rsi = i >= rsiOffset ? rsiResult[i - rsiOffset] : 0;
        });
    } catch (e) {
        logger.error(`Error calculating RSI: ${e.message}`);
        df_with_indicators.forEach(k => { k.rsi = 0; });
    }

    try {
        const volumeMASeries = SMA.calculate({
            values: input.volume,
            period: config.strategy.volume.ma_period
        });
        const volMaOffset = df_with_indicators.length - volumeMASeries.length;
        df_with_indicators.forEach((k, i) => {
            k.volume_ma = i >= volMaOffset ? volumeMASeries[i - volMaOffset] : 0;
            k.volume_spike = k.volume_ma > 0 && (k.volume / k.volume_ma) > config.strategy.volume.threshold_multiplier;
        });
    } catch (e) {
        logger.error(`Error calculating Volume MA: ${e.message}`);
        df_with_indicators.forEach(k => { k.volume_ma = 0; k.volume_spike = false; });
    }

    try {
        const fisherConfig = config.strategy.ehlers_fisher;
        const fisherResult = FisherTransform.calculate({
            high: input.high,
            low: input.low,
            period: fisherConfig.period
        });
        df_with_indicators.forEach((k, i) => {
            k.fisher = fisherResult[i]?.value || 0;
            k.fisher_signal = fisherResult[i]?.signal || 0;
        });
    } catch (e) {
        logger.error(`Error calculating Fisher Transform: ${e.message}`);
        df_with_indicators.forEach(k => { k.fisher = 0; k.fisher_signal = 0; });
    }

    try {
        const atrResult = ATR.calculate({
            high: input.high,
            low: input.low,
            close: input.close,
            period: config.strategy.atr.period
        });
        const atrOffset = df_with_indicators.length - atrResult.length;
        df_with_indicators.forEach((k, i) => { 
            k.atr = i >= atrOffset ? atrResult[i - atrOffset] : 0;
        });
    } catch (e) {
        logger.error(`Error calculating ATR: ${e.message}`);
        df_with_indicators.forEach(k => { k.atr = 0; });
    }
    
    // Forward-fill zeros for continuity
    for (let i = 1; i < df_with_indicators.length; i++) {
        for (const key of ['st_fast_line', 'st_fast_direction', 'st_slow_line', 'st_slow_direction', 'rsi', 'volume_ma', 'fisher', 'fisher_signal', 'atr']) {
            if (df_with_indicators[i][key] === 0 && df_with_indicators[i-1][key] !== undefined) {
                df_with_indicators[i][key] = df_with_indicators[i-1][key];
            }
        }
    }

    return df_with_indicators;
}

/**
 * Custom Exponential Weighted Mean
 * @param {number[]} series - Input values
 * @param {number} span - EMA span
 * @param {number} minPeriods - Minimum periods before output
 * @returns {Decimal[]}
 */
function ewmMeanCustom(series, span, minPeriods = 0) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < minPeriods) return new Array(seriesDecimals.length).fill(new Decimal(NaN));
    
    const alpha = new Decimal(2).dividedBy(new Decimal(span).plus(1));
    const result = new Array(seriesDecimals.length).fill(new Decimal(NaN));
    let ema = new Decimal(0);
    let count = 0;
    
    for (let i = 0; i < seriesDecimals.length; i++) {
        const value = seriesDecimals[i];
        if (value.isNaN()) {
            result[i] = new Decimal(NaN);
            continue;
        }
        
        if (count === 0) {
            ema = value;
        } else {
            ema = value.times(alpha).plus(ema.times(new Decimal(1).minus(alpha)));
        }
        
        count++;
        if (count >= minPeriods) {
            result[i] = ema;
        }
    }
    
    return result;
}

/**
 * Calculate Average True Range
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculateATR(high, low, close, period) {
    if (high.length < period + 1) return new Array(high.length).fill(new Decimal(NaN));
    const tr = [];
    for (let i = 1; i < high.length; i++) {
        const h = high[i]; const l = low[i]; const cPrev = close[i - 1];
        tr.push(Decimal.max(h.minus(l), h.minus(cPrev).abs(), l.minus(cPrev).abs()));
    }
    return ewmMeanCustom(tr, period, period);
}

/**
 * Calculate Relative Strength Index
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {Decimal[]}
 */
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

/**
 * Rolling Mean (SMA)
 * @param {Decimal[]} series
 * @param {number} window
 * @returns {Decimal[]}
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

/**
 * Stochastic RSI
 * @param {Decimal[]} close
 * @param {number} period
 * @param {number} kPeriod
 * @param {number} dPeriod
 * @returns {[Decimal[], Decimal[]]} [k, d]
 */
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

/**
 * Bollinger Bands
 * @param {Decimal[]} close
 * @param {number} period
 * @param {number} stdDev
 * @returns {[Decimal[], Decimal[], Decimal[]]} [upper, middle, lower]
 */
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

/**
 * Volume Weighted Average Price
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {Decimal[]} volume
 * @returns {Decimal[]}
 */
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

/**
 * MACD
 * @param {Decimal[]} close
 * @param {number} fastPeriod
 * @param {number} slowPeriod
 * @param {number} signalPeriod
 * @returns {[Decimal[], Decimal[], Decimal[]]} [macdLine, signalLine, histogram]
 */
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

/**
 * ADX, +DI, -DI
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {[Decimal[], Decimal[], Decimal[]]} [adx, plusDI, minusDI]
 */
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

/**
 * Simple Moving Average
 * @param {Object} df - DataFrame-like with .close
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_sma(df, period) {
    return rollingMean(df.close, period);
}

/**
 * Exponential Moving Average
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_ema(df, period) {
    return ewmMeanCustom(df.close, period, period);
}

/**
 * On-Balance Volume + EMA
 * @param {Object} df
 * @param {number} emaPeriod
 * @returns {{obv: Decimal[], obv_ema: Decimal[]}}
 */
function calculate_obv(df, emaPeriod) {
    if (df.close.length === 0) return null;
    const obv = [new Decimal(0)];
    for (let i = 1; i < df.close.length; i++) {
        if (df.close[i].gt(df.close[i - 1])) {
            obv.push(obv[i - 1].plus(df.volume[i]));
        } else if (df.close[i].lt(df.close[i - 1])) {
            obv.push(obv[i - 1].minus(df.volume[i]));
        } else {
            obv.push(obv[i - 1]);
        }
    }
    const obvEma = ewmMeanCustom(obv, emaPeriod, emaPeriod);
    return { obv, obv_ema: obvEma };
}

/**
 * Chaikin Money Flow
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_cmf(df, period) {
    if (df.close.length < period) return [];
    const mfv = [];
    for (let i = 0; i < df.close.length; i++) {
        const clv = df.close[i].equals(df.high[i]) && df.close[i].equals(df.low[i])
            ? new Decimal(0)
            : df.close[i].minus(df.low[i]).minus(df.high[i].minus(df.close[i]))
                .dividedBy(df.high[i].minus(df.low[i]));
        mfv.push(clv.times(df.volume[i]));
    }

    const cmf = [];
    for (let i = 0; i < df.close.length; i++) {
        if (i < period - 1) {
            cmf.push(new Decimal(NaN));
        } else {
            const sumMfv = mfv.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
            const sumVol = df.volume.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
            cmf.push(sumVol.isZero() ? new Decimal(0) : sumMfv.dividedBy(sumVol));
        }
    }
    return cmf;
}

/**
 * Ichimoku Cloud
 * @param {Object} df
 * @param {number} tenkan
 * @param {number} kijun
 * @param {number} senkouBPeriod
 * @param {number} chikouOffset
 * @returns {{tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span}}
 */
function calculate_ichimoku_cloud(df, tenkan, kijun, senkouBPeriod, chikouOffset) {
    const tenkanSen = [], kijunSen = [], senkouSpanA = [], senkouSpanB = [], chikouSpan = [];

    for (let i = 0; i < df.close.length; i++) {
        // Tenkan-sen
        if (i < tenkan - 1) {
            tenkanSen.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...df.high.slice(i - tenkan + 1, i + 1));
            const windowLow = Decimal.min(...df.low.slice(i - tenkan + 1, i + 1));
            tenkanSen.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Kijun-sen
        if (i < kijun - 1) {
            kijunSen.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...df.high.slice(i - kijun + 1, i + 1));
            const windowLow = Decimal.min(...df.low.slice(i - kijun + 1, i + 1));
            kijunSen.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Senkou Span A
        if (i + chikouOffset < df.close.length) {
            senkouSpanA.push(tenkanSen[i].plus(kijunSen[i]).dividedBy(2));
        } else {
            senkouSpanA.push(new Decimal(NaN));
        }

        // Senkou Span B
        if (i < senkouBPeriod - 1) {
            senkouSpanB.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...df.high.slice(i - senkouBPeriod + 1, i + 1));
            const windowLow = Decimal.min(...df.low.slice(i - senkouBPeriod + 1, i + 1));
            senkouSpanB.push(windowHigh.plus(windowLow).dividedBy(2));
        }

        // Chikou Span
        if (i >= chikouOffset) {
            chikouSpan.push(df.close[i - chikouOffset]);
        } else {
            chikouSpan.push(new Decimal(NaN));
        }
    }

    // Shift forward
    for (let i = 0; i < chikouOffset; i++) {
        senkouSpanA.unshift(new Decimal(NaN));
        senkouSpanB.unshift(new Decimal(NaN));
    }
    senkouSpanA.splice(df.close.length);
    senkouSpanB.splice(df.close.length);

    return { tenkan_sen: tenkanSen, kijun_sen: kijunSen, senkou_span_a: senkouSpanA, senkou_span_b: senkouSpanB, chikou_span: chikouSpan };
}

/**
 * Parabolic SAR
 * @param {Object} df
 * @param {number} acceleration
 * @param {number} maxAcceleration
 * @returns {{psar: Decimal[], direction: number[]}}
 */
function calculate_psar(df, acceleration, maxAcceleration) {
    if (df.close.length < 2) return null;
    const psar = [df.low[0]];
    const direction = [1];
    let acc = acceleration;
    let ep = df.high[0];

    for (let i = 1; i < df.close.length; i++) {
        let nextPsar = psar[i - 1].plus(acc.times(ep.minus(psar[i - 1])));
        let nextDir = direction[i - 1];
        let nextAcc = acc;
        let nextEp = ep;

        if (nextDir === 1) {
            if (df.low[i] < nextPsar) {
                nextDir = -1;
                nextPsar = ep;
                nextAcc = acceleration;
                nextEp = df.low[i];
            } else {
                if (df.high[i] > ep) {
                    nextEp = df.high[i];
                    nextAcc = Math.min(acc + acceleration, maxAcceleration);
                }
                if (df.low[i - 1] < nextPsar) nextPsar = df.low[i - 1];
                if (i > 1 && df.low[i - 2] < nextPsar) nextPsar = df.low[i - 2];
            }
        } else {
            if (df.high[i] > nextPsar) {
                nextDir = 1;
                nextPsar = ep;
                nextAcc = acceleration;
                nextEp = df.high[i];
            } else {
                if (df.low[i] < ep) {
                    nextEp = df.low[i];
                    nextAcc = Math.min(acc + acceleration, maxAcceleration);
                }
                if (df.high[i - 1] > nextPsar) nextPsar = df.high[i - 1];
                if (i > 1 && df.high[i - 2] > nextPsar) nextPsar = df.high[i - 2];
            }
        }

        psar.push(nextPsar);
        direction.push(nextDir);
        acc = nextAcc;
        ep = nextEp;
    }

    return { psar, direction };
}

/**
 * Ehlers SuperTrend (Custom Implementation)
 * @param {Object} df
 * @param {number} period
 * @param {number} multiplier
 * @returns {{supertrend: Decimal[], direction: number[]}}
 */
function calculate_ehlers_supertrend(df, period, multiplier) {
    if (df.close.length < period * 2) return null;

    const src = df.close;
    const supertrend = [];
    const direction = [];

    // Super Smoother Filter
    const smooth = [];
    const a1 = Math.exp(-1.414 * Math.PI / period);
    const b1 = 2 * a1 * Math.cos(1.414 * Math.PI / period);
    const coeff2 = b1;
    const coeff3 = -a1 * a1;
    const coeff1 = 1 - coeff2 - coeff3;

    for (let i = 0; i < src.length; i++) {
        if (i < 2) {
            smooth.push(src[i]);
        } else {
            smooth.push(
                new Decimal(coeff1).times(src[i])
                    .plus(new Decimal(coeff2).times(smooth[i - 1]))
                    .plus(new Decimal(coeff3).times(smooth[i - 2]))
            );
        }
    }

    // Median Price
    const median = [];
    for (let i = 0; i < src.length; i++) {
        median.push(src[i].plus(df.high[i]).plus(df.low[i]).dividedBy(3));
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
            const atr = calculateATR(df.high, df.low, smooth, period)[i];
            const up = median[i].minus(atr.times(multiplier));
            const dn = median[i].plus(atr.times(multiplier));

            let finalUp = up.lt(trendUp[i - 1]) || src[i - 1].gt(trendUp[i - 1]) ? up : trendUp[i - 1];
            let finalDn = dn.gt(trendDown[i - 1]) || src[i - 1].lt(trendDown[i - 1]) ? dn : trendDown[i - 1];

            let dir = direction[i - 1];
            let st = supertrend[i - 1];

            if (dir === -1 && src[i] > finalDn) {
                dir = 1;
                st = finalUp;
            } else if (dir === 1 && src[i] < finalUp) {
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

/**
 * Kaufman Adaptive Moving Average
 * @param {Object} df
 * @param {number} period
 * @param {number} fastPeriod
 * @param {number} slowPeriod
 * @returns {Decimal[]}
 */
function calculate_kaufman_ama(df, period, fastPeriod, slowPeriod) {
    if (df.close.length < period + 1) return [];
    const er = [];
    for (let i = period; i < df.close.length; i++) {
        const change = df.close[i].minus(df.close[i - period]).abs();
        const volatility = df.close.slice(i - period + 1, i + 1)
            .map((c, idx, arr) => idx === 0 ? new Decimal(0) : c.minus(arr[idx - 1]).abs())
            .reduce((sum, val) => sum.plus(val), new Decimal(0));
        er.push(volatility.isZero() ? new Decimal(1) : change.dividedBy(volatility));
    }

    const fastAlpha = new Decimal(2).dividedBy(new Decimal(fastPeriod).plus(1));
    const slowAlpha = new Decimal(2).dividedBy(new Decimal(slowPeriod).plus(1));
    const sc = er.map(e =>
        slowAlpha.plus(e.times(fastAlpha.minus(slowAlpha))).pow(2)
    );

    const kama = [];
    for (let i = 0; i < df.close.length; i++) {
        if (i < period) {
            kama.push(df.close[i]);
        } else {
            const idx = i - period;
            kama.push(
                kama[i - 1].plus(sc[idx].times(df.close[i].minus(kama[i - 1])))
            );
        }
    }
    return kama;
}

/**
 * Double Exponential Moving Average
 * @param {Decimal[]} series
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_dema(series, period) {
    const ema1 = ewmMeanCustom(series, period, period);
    const ema2 = ewmMeanCustom(ema1, period, period);
    return ema1.map((e, i) => e.times(2).minus(ema2[i]));
}

/**
 * Keltner Channels
 * @param {Object} df
 * @param {number} period
 * @param {number} atrMult
 * @param {number} atrPeriod
 * @returns {{upper, middle, lower}}
 */
function calculate_keltner_channels(df, period, atrMult, atrPeriod) {
    const middle = ewmMeanCustom(df.close, period, period);
    const atr = calculateATR(df.high, df.low, df.close, atrPeriod);
    const upper = middle.map((m, i) => m.plus(atr[i].times(atrMult)));
    const lower = middle.map((m, i) => m.minus(atr[i].times(atrMult)));
    return { upper, middle, lower };
}

/**
 * Rate of Change
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_roc(df, period) {
    const roc = [];
    for (let i = 0; i < df.close.length; i++) {
        if (i < period) {
            roc.push(new Decimal(NaN));
        } else {
            roc.push(df.close[i].dividedBy(df.close[i - period]).minus(1).times(100));
        }
    }
    return roc;
}

/**
 * Detect Candlestick Patterns
 * @param {Object} df
 * @returns {string[]}
 */
function detect_candlestick_patterns(df) {
    const patterns = [];
    for (let i = 1; i < df.close.length; i++) {
        const prev = df.iloc(i - 1);
        const curr = df.iloc(i);

        if (curr.close.gt(curr.open) && prev.close.lt(prev.open) &&
            curr.open.lt(prev.close) && curr.close.gt(prev.open)) {
            patterns.push("Bullish Engulfing");
        } else if (curr.close.lt(curr.open) && prev.close.gt(prev.open) &&
                   curr.open.gt(prev.close) && curr.close.lt(prev.open)) {
            patterns.push("Bearish Engulfing");
        } else if (curr.close.gt(curr.open) &&
                   curr.open.minus(curr.low).dividedBy(curr.close.minus(curr.open)).gt(2) &&
                   curr.high.minus(curr.close).dividedBy(curr.close.minus(curr.open)).lt(1)) {
            patterns.push("Hammer");
        } else if (curr.close.lt(curr.open) &&
                   curr.high.minus(curr.open).dividedBy(curr.open.minus(curr.close)).gt(2) &&
                   curr.close.minus(curr.low).dividedBy(curr.open.minus(curr.close)).lt(1)) {
            patterns.push("Shooting Star");
        } else {
            patterns.push("None");
        }
    }
    return patterns;
}

/**
 * Fibonacci Retracement Levels
 * @param {Object} df
 * @param {number} window
 * @returns {Object|null}
 */
function calculate_fibonacci_levels(df, window) {
    if (df.close.length < window) return null;
    const recent = df.close.slice(-window);
    const high = Decimal.max(...recent);
    const low = Decimal.min(...recent);
    const diff = high.minus(low);

    return {
        "0.0%": high,
        "23.6%": high.minus(diff.times(0.236)),
        "38.2%": high.minus(diff.times(0.382)),
        "50.0%": high.minus(diff.times(0.5)),
        "61.8%": high.minus(diff.times(0.618)),
        "78.6%": high.minus(diff.times(0.786)),
        "100.0%": low
    };
}

/**
 * Fibonacci Pivot Points
 * @param {Object} df
 * @returns {{pivot, r1, r2, s1, s2}} or null
 */
function calculate_fibonacci_pivot_points(df) {
    if (df.close.length < 2) return null;
    const prev = df.iloc(df.length - 2);
    const pivot = prev.high.plus(prev.low).plus(prev.close).dividedBy(3);
    const range = prev.high.minus(prev.low);

    return {
        pivot: pivot,
        r1: pivot.plus(range.times(0.382)),
        r2: pivot.plus(range.times(0.618)),
        s1: pivot.minus(range.times(0.382)),
        s2: pivot.minus(range.times(0.618))
    };
}

/**
 * Volatility Index (StdDev of Returns)
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_volatility_index(df, period) {
    if (df.close.length < period + 1) return [];
    const returns = [];
    for (let i = 1; i < df.close.length; i++) {
        returns.push(df.close[i].dividedBy(df.close[i - 1]).minus(1));
    }

    const vi = [];
    for (let i = 0; i < returns.length; i++) {
        if (i < period - 1) {
            vi.push(new Decimal(NaN));
        } else {
            const window = returns.slice(i - period + 1, i + 1);
            const mean = window.reduce((sum, val) => sum.plus(val), new Decimal(0)).dividedBy(period);
            const variance = window.reduce((sum, val) => sum.plus(val.minus(mean).pow(2)), new Decimal(0)).dividedBy(period);
            vi.push(Decimal.sqrt(variance).times(100));
        }
    }
    return vi;
}

/**
 * Volume Weighted Moving Average
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_vwma(df, period) {
    if (df.close.length < period) return [];
    const vwma = [];
    for (let i = 0; i < df.close.length; i++) {
        if (i < period - 1) {
            vwma.push(new Decimal(NaN));
        } else {
            const prices = df.close.slice(i - period + 1, i + 1);
            const volumes = df.volume.slice(i - period + 1, i + 1);
            const pvSum = prices.reduce((sum, p, idx) => sum.plus(p.times(volumes[idx])), new Decimal(0));
            const vSum = volumes.reduce((sum, v) => sum.plus(v), new Decimal(0));
            vwma.push(vSum.isZero() ? prices[prices.length - 1] : pvSum.dividedBy(vSum));
        }
    }
    return vwma;
}

/**
 * Volume Delta Proxy
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_volume_delta(df, period) {
    const delta = df.close.map((c, i) =>
        i === 0 ? new Decimal(0) : c.gt(df.close[i - 1]) ? df.volume[i] : c.lt(df.close[i - 1]) ? df.volume[i].negated() : new Decimal(0)
    );
    return rollingMean(delta, period);
}

/**
 * Relative Volume
 * @param {Object} df
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_relative_volume(df, period) {
    const avgVol = rollingMean(df.volume, period);
    return df.volume.map((v, i) => avgVol[i].isZero() ? new Decimal(1) : v.dividedBy(avgVol[i]));
}

/**
 * Market Structure Trend (HH/HL Detection)
 * @param {Object} df
 * @param {number} lookback
 * @returns {number[]}
 */
function calculate_market_structure(df, lookback) {
    const trend = [];
    for (let i = 0; i < df.close.length; i++) {
        if (i < lookback * 2) {
            trend.push(0);
            continue;
        }

        let higherHighs = 0, lowerLows = 0;
        for (let j = i - lookback; j < i; j++) {
            if (df.high[j] > df.high[j - 1]) higherHighs++;
            if (df.low[j] < df.low[j - 1]) lowerLows++;
        }

        if (higherHighs > lookback * 0.6) {
            trend.push(1);
        } else if (lowerLows > lookback * 0.6) {
            trend.push(-1);
        } else {
            trend.push(0);
        }
    }
    return trend;
}

/**
 * Momentum (Price Difference over N periods)
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_momentum(close, period) {
    if (close.length < period) return new Array(close.length).fill(new Decimal(NaN));
    const momentum = new Array(close.length).fill(new Decimal(NaN));
    for (let i = period - 1; i < close.length; i++) {
        momentum[i] = close[i].minus(close[i - period]);
    }
    return momentum;
}

/**
 * Williams %R
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_williams_r(high, low, close, period) {
    if (high.length < period) return new Array(high.length).fill(new Decimal(NaN));
    const williamsR = [];
    for (let i = 0; i < high.length; i++) {
        if (i < period - 1) {
            williamsR.push(new Decimal(NaN));
        } else {
            const windowHigh = Decimal.max(...high.slice(i - period + 1, i + 1));
            const windowLow = Decimal.min(...low.slice(i - period + 1, i + 1));
            if (windowHigh.minus(windowLow).isZero()) {
                williamsR.push(new Decimal(-50));
            } else {
                williamsR.push(
                    close[i].minus(windowHigh)
                        .dividedBy(windowHigh.minus(windowLow))
                        .times(100)
                );
            }
        }
    }
    return williamsR;
}

/**
 * Commodity Channel Index
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_cci(high, low, close, period) {
    if (high.length < period) return new Array(high.length).fill(new Decimal(NaN));
    const tp = high.map((h, i) => h.plus(low[i]).plus(close[i]).dividedBy(3));
    const smaTp = ewmMeanCustom(tp, period, period);
    const mad = new Array(high.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < high.length; i++) {
        const tpWindow = tp.slice(i - period + 1, i + 1);
        const meanTp = smaTp[i];
        const absDevSum = tpWindow.reduce((acc, val) => acc.plus(val.minus(meanTp).abs()), new Decimal(0));
        mad[i] = absDevSum.dividedBy(period);
    }
    
    const cci = new Array(high.length).fill(new Decimal(NaN));
    for (let i = 0; i < high.length; i++) {
        if (!tp[i].isNaN() && !smaTp[i].isNaN() && !mad[i].isNaN()) {
            if (mad[i].isZero()) {
                cci[i] = new Decimal(0);
            } else {
                cci[i] = (tp[i].minus(smaTp[i])).dividedBy(new Decimal(0.015).times(mad[i]));
            }
        }
    }
    return cci;
}

/**
 * Money Flow Index
 * @param {Decimal[]} high
 * @param {Decimal[]} low
 * @param {Decimal[]} close
 * @param {Decimal[]} volume
 * @param {number} period
 * @returns {Decimal[]}
 */
function calculate_mfi(high, low, close, volume, period) {
    if (high.length <= period) return new Array(high.length).fill(new Decimal(NaN));
    const typicalPrice = high.map((h, i) => h.plus(low[i]).plus(close[i]).dividedBy(3));
    const moneyFlow = typicalPrice.map((tp, i) => tp.times(volume[i]));
    
    const positiveFlow = new Array(high.length).fill(new Decimal(0));
    const negativeFlow = new Array(high.length).fill(new Decimal(0));
    
    for (let i = 1; i < high.length; i++) {
        if (typicalPrice[i].gt(typicalPrice[i - 1])) {
            positiveFlow[i] = moneyFlow[i];
        } else if (typicalPrice[i].lt(typicalPrice[i - 1])) {
            negativeFlow[i] = moneyFlow[i];
        }
    }
    
    const positiveMfSum = new Array(high.length).fill(new Decimal(NaN));
    const negativeMfSum = new Array(high.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < high.length; i++) {
        positiveMfSum[i] = positiveFlow.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
        negativeMfSum[i] = negativeFlow.slice(i - period + 1, i + 1).reduce((a, b) => a.plus(b), new Decimal(0));
    }
    
    const mfi = new Array(high.length).fill(new Decimal(NaN));
    for (let i = 0; i < high.length; i++) {
        if (!positiveMfSum[i].isNaN() && !negativeMfSum[i].isNaN()) {
            const mfRatio = (negativeMfSum[i].isZero()) ? (positiveMfSum[i].isZero() ? new Decimal(0) : new Decimal(Infinity)) : positiveMfSum[i].dividedBy(negativeMfSum[i]);
            mfi[i] = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(mfRatio)));
        }
    }
    return mfi;
}

/**
 * Price Oscillator (Percentage)
 * @param {Decimal[]} close
 * @param {number} fastPeriod
 * @param {number} slowPeriod
 * @returns {Decimal[]}
 */
function calculate_price_oscillator(close, fastPeriod, slowPeriod) {
    if (close.length < slowPeriod) return new Array(close.length).fill(new Decimal(NaN));
    const emaFast = ewmMeanCustom(close, fastPeriod, fastPeriod);
    const emaSlow = ewmMeanCustom(close, slowPeriod, slowPeriod);
    return emaFast.map((fast, i) => {
        if (!fast.isNaN() && !emaSlow[i].isNaN() && emaSlow[i].gt(0)) {
            return (fast.minus(emaSlow[i])).dividedBy(emaSlow[i]).times(100);
        }
        return new Decimal(NaN);
    });
}

// Utility Functions
function diff(series) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < 1) return [];
    const result = [new Decimal(NaN)];
    for (let i = 1; i < seriesDecimals.length; i++) { result.push(seriesDecimals[i].minus(seriesDecimals[i - 1])); }
    return result;
}

function pctChange(series) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < 1) return [];
    const result = [new Decimal(NaN)];
    for (let i = 1; i < seriesDecimals.length; i++) {
        if (seriesDecimals[i - 1].gt(0)) { result.push(seriesDecimals[i].minus(seriesDecimals[i - 1]).dividedBy(seriesDecimals[i - 1]).times(100)); }
        else { result.push(new Decimal(NaN)); }
    }
    return result;
}

function std(series, window) {
    const seriesDecimals = series.map(x => new Decimal(x));
    if (seriesDecimals.length < window) { return new Array(seriesDecimals.length).fill(new Decimal(NaN)); }
    const result = new Array(seriesDecimals.length).fill(new Decimal(NaN));
    for (let i = window - 1; i < seriesDecimals.length; i++) {
        const currentWindow = seriesDecimals.slice(i - window + 1, i + 1);
        const mean = currentWindow.reduce((a, b) => a.plus(b), new Decimal(0)).dividedBy(window);
        const variance = currentWindow.reduce((sum, val) => sum.plus(val.minus(mean).pow(2)), new Decimal(0)).dividedBy(window);
        result[i] = variance.sqrt();
    }
    return result;
}

// Export All
module.exports = {
    // External Strategy Calculator
    calculateEhlSupertrendIndicators,

    // Core Indicators
    calculate_sma,
    calculate_ema,
    calculate_atr: calculateATR,
    calculate_rsi: calculateRSI,
    calculate_stoch_rsi: calculateStochRSI,
    calculate_bollinger_bands: calculateBollingerBands,
    calculate_vwap: calculateVWAP,
    calculate_macd: calculateMACD,
    calculate_adx: calculateADX,
    calculate_obv,
    calculate_cmf,
    calculate_ichimoku_cloud,
    calculate_psar,
    calculate_ehlers_supertrend,
    calculate_kaufman_ama,
    calculate_dema,
    calculate_keltner_channels,
    calculate_roc,
    detect_candlestick_patterns,
    calculate_fibonacci_levels,
    calculate_fibonacci_pivot_points,

    // Secondary Indicators
    calculate_volatility_index,
    calculate_vwma,
    calculate_volume_delta,
    calculate_relative_volume,
    calculate_market_structure,
    calculate_momentum,
    calculate_williams_r,
    calculate_cci,
    calculate_mfi,
    calculate_price_oscillator,

    // Utilities
    ewmMeanCustom,
    rollingMean,
    diff,
    pctChange,
    std
};