
const { Supertrend, RSI, SMA, FisherTransform, ATR } = require('technicalindicators');
const Decimal = require('decimal.js');

/**
 * A centralized function to calculate a set of technical indicators.
 * @param {Array<Object>} klines - The kline data.
 * @param {Object} config - The strategy configuration object.
 * @param {Object} logger - The logger instance.
 * @returns {Array<Object>} The klines with indicators added.
 */
function calculateEhlSupertrendIndicators(klines, config, logger) {
    if (!klines || klines.length === 0) {
        return [];
    }

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
        // The RSI output array might be shorter than the input array.
        // We need to align it to the end of the klines.
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
            if (k.volume_ma > 0) {
                k.volume_spike = (k.volume / k.volume_ma) > config.strategy.volume.threshold_multiplier;
            } else {
                k.volume_spike = false;
            }
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
    
    for (let i = 1; i < df_with_indicators.length; i++) {
        for (const key of ['st_fast_line', 'st_fast_direction', 'st_slow_line', 'st_slow_direction', 'rsi', 'volume_ma', 'fisher', 'fisher_signal', 'atr']) {
            if (df_with_indicators[i][key] === 0 && df_with_indicators[i-1][key] !== undefined) {
                df_with_indicators[i][key] = df_with_indicators[i-1][key];
            }
        }
    }

    return df_with_indicators;
}

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

function calculateATR(high, low, close, period) {
    if (high.length < period + 1) return new Array(high.length).fill(new Decimal(NaN));
    const tr = [];
    for (let i = 1; i < high.length; i++) {
        const h = high[i]; const l = low[i]; const cPrev = close[i - 1];
        tr.push(Decimal.max(h.minus(l), h.minus(cPrev).abs(), l.minus(cPrev).abs()));
    }
    return ewmMeanCustom(tr, period, period);
}

function calculateRSI(close, period) {
    if (close.length <= period) return new Array(close.length).fill(new Decimal(NaN));
    
    const closeDecimals = close.map(x => new Decimal(x));

    const delta = closeDecimals.map((c, i) => i > 0 ? c.minus(closeDecimals[i-1]) : new Decimal(0));
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

function calculateBollingerBands(close, period, stdDev) {
    if (close.length < period) {
        return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];
    }
    
    const closeDecimals = close.map(x => new Decimal(x));
    const middleBand = rollingMean(closeDecimals, period); // Assumes rollingMean returns Decimals
    const std = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < close.length; i++) {
        const window = closeDecimals.slice(i - period + 1, i + 1);
        const mean = middleBand[i];
        const sumOfSquares = window.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0));
        std[i] = (sumOfSquares.dividedBy(period)).sqrt();
    }
    
    const upperBand = middleBand.map((mb, i) => mb.plus(std[i].times(stdDev)));
    const lowerBand = middleBand.map((mb, i) => mb.minus(std[i].times(stdDev)));
    
    return [upperBand, middleBand, lowerBand];
}

function calculateVWAP(high, low, close, volume) {
    if (high.length === 0) return new Array(high.length).fill(new Decimal(NaN));
    
    const highDecimals = high.map(x => new Decimal(x));
    const lowDecimals = low.map(x => new Decimal(x));
    const closeDecimals = close.map(x => new Decimal(x));
    const volumeDecimals = volume.map(x => new Decimal(x));

    const typicalPrice = highDecimals.map((h, i) => (h.plus(lowDecimals[i]).plus(closeDecimals[i])).dividedBy(3));
    const tpVol = typicalPrice.map((tp, i) => tp.times(volumeDecimals[i]));
    
    const cumulativeTpVol = new Array(high.length).fill(new Decimal(NaN));
    const cumulativeVol = new Array(high.length).fill(new Decimal(NaN));
    const vwap = new Array(high.length).fill(new Decimal(NaN));
    
    let sumTpVol = new Decimal(0);
    let sumVol = new Decimal(0);
    
    for (let i = 0; i < high.length; i++) {
        sumTpVol = sumTpVol.plus(tpVol[i]);
        sumVol = sumVol.plus(volumeDecimals[i]);
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

function calculateMACD(close, fastPeriod, slowPeriod, signalPeriod) {
    if (close.length < slowPeriod + signalPeriod) {
        return [new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN)), new Array(close.length).fill(new Decimal(NaN))];
    }
    
    const closeDecimals = close.map(x => new Decimal(x));
    const emaFast = ewmMeanCustom(closeDecimals, fastPeriod, fastPeriod);
    const emaSlow = ewmMeanCustom(closeDecimals, slowPeriod, slowPeriod);
    const macdLine = emaFast.map((fast, i) => fast.minus(emaSlow[i] || new Decimal(NaN)));
    const signalLine = ewmMeanCustom(macdLine, signalPeriod, signalPeriod);
    const histogram = macdLine.map((macd, i) => macd.minus(signalLine[i] || new Decimal(NaN)));
    
    return [macdLine, signalLine, histogram];
}

function calculateADX(high, low, close, period) {
    if (high.length < period * 2) {
        return [new Array(high.length).fill(new Decimal(NaN)), new Array(high.length).fill(new Decimal(NaN)), new Array(high.length).fill(new Decimal(NaN))];
    }
    
    const highDecimals = high.map(x => new Decimal(x));
    const lowDecimals = low.map(x => new Decimal(x));
    const closeDecimals = close.map(x => new Decimal(x));

    const tr = calculateATR(highDecimals, lowDecimals, closeDecimals, period);
    
    const plusDM = new Array(high.length).fill(new Decimal(0));
    const minusDM = new Array(high.length).fill(new Decimal(0));
    
    for (let i = 1; i < high.length; i++) {
        const upMove = highDecimals[i].minus(highDecimals[i - 1]);
        const downMove = lowDecimals[i - 1].minus(lowDecimals[i]);
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

function calculateMomentum(close, period) {
    if (close.length < period) return new Array(close.length).fill(new Decimal(NaN));
    
    const closeDecimals = close.map(x => new Decimal(x));
    const momentum = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < close.length; i++) {
        if (!closeDecimals[i].isNaN() && !closeDecimals[i - period].isNaN()) {
            momentum[i] = closeDecimals[i].minus(closeDecimals[i - period]);
        }
    }
    
    return momentum;
}

function calculateWilliamsR(high, low, close, period) {
    if (high.length < period) return new Array(high.length).fill(new Decimal(NaN));
    
    const highDecimals = high.map(x => new Decimal(x));
    const lowDecimals = low.map(x => new Decimal(x));
    const closeDecimals = close.map(x => new Decimal(x));

    const highestHigh = new Array(high.length).fill(new Decimal(NaN));
    const lowestLow = new Array(high.length).fill(new Decimal(NaN));
    
    for (let i = period - 1; i < high.length; i++) {
        const highWindow = highDecimals.slice(i - period + 1, i + 1);
        const lowWindow = lowDecimals.slice(i - period + 1, i + 1);
        highestHigh[i] = Decimal.max(...highWindow);
        lowestLow[i] = Decimal.min(...lowWindow);
    }
    
    const williamsR = new Array(high.length).fill(new Decimal(NaN));
    for (let i = 0; i < high.length; i++) {
        if (!closeDecimals[i].isNaN() && !highestHigh[i].isNaN() && !lowestLow[i].isNaN()) {
            const denominator = highestHigh[i].minus(lowestLow[i]);
            if (denominator.isZero()) {
                williamsR[i] = new Decimal(-50);
            } else {
                williamsR[i] = (highestHigh[i].minus(closeDecimals[i])).dividedBy(denominator).times(-100);
            }
        }
    }
    
    return williamsR;
}

function calculateCCI(high, low, close, period) {
    if (high.length < period) return new Array(high.length).fill(new Decimal(NaN));
    
    const highDecimals = high.map(x => new Decimal(x));
    const lowDecimals = low.map(x => new Decimal(x));
    const closeDecimals = close.map(x => new Decimal(x));

    const tp = highDecimals.map((h, i) => (h.plus(lowDecimals[i]).plus(closeDecimals[i])).dividedBy(3));
    const smaTp = ewmMeanCustom(tp, period, period); // Using EMA for SMA for responsiveness
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

function calculateMFI(high, low, close, volume, period) {
    if (high.length <= period) return new Array(high.length).fill(new Decimal(NaN));
    
    const highDecimals = high.map(x => new Decimal(x));
    const lowDecimals = low.map(x => new Decimal(x));
    const closeDecimals = close.map(x => new Decimal(x));
    const volumeDecimals = volume.map(x => new Decimal(x));

    const typicalPrice = highDecimals.map((h, i) => (h.plus(lowDecimals[i]).plus(closeDecimals[i])).dividedBy(3));
    const moneyFlow = typicalPrice.map((tp, i) => tp.times(volumeDecimals[i]));
    
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

function calculatePriceOscillator(close, fastPeriod, slowPeriod) {
    if (close.length < slowPeriod) return new Array(close.length).fill(new Decimal(NaN));
    
    const closeDecimals = close.map(x => new Decimal(x));
    const emaFast = ewmMeanCustom(closeDecimals, fastPeriod, fastPeriod);
    const emaSlow = ewmMeanCustom(closeDecimals, slowPeriod, slowPeriod);
    
    const priceOscillator = emaFast.map((fast, i) => {
        if (!fast.isNaN() && !emaSlow[i].isNaN() && emaSlow[i].gt(0)) {
            return (fast.minus(emaSlow[i])).dividedBy(emaSlow[i]).times(100);
        }
        return new Decimal(NaN);
    });
    
    return priceOscillator;
}

function calculateTickDivergence(tickData, close, lookback = 5) {
    if (tickData.length < lookback * 2) return new Array(close.length).fill(new Decimal(NaN));
    
    const tickDivergence = new Array(close.length).fill(new Decimal(NaN));
    
    for (let i = 0; i < close.length; i++) {
        // Need enough recent ticks for analysis within the scope of the current kline
        // This is a simplified approach, a more robust solution would map ticks to klines
        // or use time-based windows. For now, we use a global recent ticks buffer.
        if (i < lookback) continue; // Not enough klines for a meaningful comparison

        const recentTicks = tickData.slice(Math.max(0, tickData.length - 100)); // Consider last 100 ticks
        if (recentTicks.length < 20) continue; // Need sufficient ticks

        const recentKlinesClose = close.slice(Math.max(0, i - lookback), i + 1);
        if (recentKlinesClose.length < 2) continue;

        const latestPrice = recentKlinesClose[recentKlinesClose.length - 1];
        const oldestPrice = recentKlinesClose[0];

        // Calculate tick pressure (buy vs sell ticks in recent history)
        let buyTicks = 0;
        let sellTicks = 0;
        for (const tick of recentTicks) {
            // Assuming tick.timestamp and klineData.data[i].timestamp are comparable
            // This part needs to be adapted based on how klineData.data[i].timestamp is structured
            // For now, a placeholder for time-based filtering of ticks
            // if (tick.timestamp > klineData.data[i].timestamp - (lookback * 60 * 1000)) { 
                if (tick.side === 'Buy') buyTicks++;
                else if (tick.side === 'Sell') sellTicks++;
            // }
        }
        const totalTicks = buyTicks + sellTicks;
        const tickPressure = totalTicks > 0 ? (new Decimal(buyTicks).minus(new Decimal(sellTicks))).dividedBy(new Decimal(totalTicks)) : new Decimal(0);
        
        // Calculate price momentum
        const priceChange = latestPrice.minus(oldestPrice);
        const priceMomentum = oldestPrice.gt(0) ? priceChange.dividedBy(oldestPrice).times(100) : new Decimal(0);
        
        // Calculate divergence (when tick pressure and price momentum diverge)
        if (tickPressure.abs().gt(0.3) && priceMomentum.abs().lt(0.1)) { // Example thresholds
            tickDivergence[i] = tickPressure.gt(0) ? new Decimal(1) : new Decimal(-1); // Bullish or bearish divergence
        } else {
            tickDivergence[i] = new Decimal(0); // No divergence
        }
    }
    
    return tickDivergence;
}

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

module.exports = {
    calculateEhlSupertrendIndicators,
    calculateATR,
    calculateRSI,
    calculateStochRSI,
    rollingMean,
    calculateBollingerBands,
    calculateVWAP,
    calculateMACD,
    calculateADX,
    calculateMomentum,
    calculateWilliamsR,
    calculateCCI,
    calculateMFI,
    calculatePriceOscillator,
    calculateTickDivergence,
    diff,
    pctChange,
    std
};
