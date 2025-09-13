const { RSI, SMA, ATR, ADX } = require('technicalindicators');
const SuperTrend = require('supertrend-indicator');
const Decimal = require('decimal.js');

function calculateFisherTransform(high, low, period) {
    const length = high.length;
    const fisher = new Array(length).fill(0);
    const trigger = new Array(length).fill(0);
    const values = new Array(length).fill(0);
    let fish = new Array(length).fill(0);

    for (let i = 0; i < length; i++) {
        const highestHigh = Math.max(...high.slice(Math.max(0, i - period + 1), i + 1));
        const lowestLow = Math.min(...low.slice(Math.max(0, i - period + 1), i + 1));
        const range = highestHigh - lowestLow;
        const price = (high[i] + low[i]) / 2;
        
        let value = 0;
        if (range > 0) {
            value = 0.33 * 2 * ((price - lowestLow) / range - 0.5) + 0.67 * (values[i-1] || 0);
        } else {
            value = values[i-1] || 0;
        }

        if (value > 0.99) value = 0.999;
        if (value < -0.99) value = -0.999;
        
        values[i] = value;
        
        fish[i] = 0.5 * Math.log((1 + value) / (1 - value)) + 0.5 * (fish[i-1] || 0);
        fisher[i] = fish[i];
        trigger[i] = fish[i-1] || 0;
    }

    return { fisher, trigger };
}

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
        const stFastResult = SuperTrend(processedKlines, stFastConfig.multiplier, stFastConfig.length);
        df_with_indicators.forEach((k, i) => {
            k.st_fast_line = stFastResult[i]?.supertrend || 0;
            k.st_fast_direction = stFastResult[i]?.trendDirection || 0;
        });
    } catch (e) {
        logger.error(`Error calculating fast Supertrend: ${e.message}`);
        df_with_indicators.forEach(k => { k.st_fast_line = 0; k.st_fast_direction = 0; });
    }

    try {
        const stSlowConfig = config.strategy.est_slow;
        const stSlowResult = SuperTrend(processedKlines, stSlowConfig.multiplier, stSlowConfig.length);
        df_with_indicators.forEach((k, i) => {
            k.st_slow_line = stSlowResult[i]?.supertrend || 0;
            k.st_slow_direction = stSlowResult[i]?.trendDirection || 0;
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
        const fisherResult = calculateFisherTransform(input.high, input.low, fisherConfig.period);
        df_with_indicators.forEach((k, i) => {
            k.fisher = fisherResult.fisher[i] || 0;
            k.fisher_signal = fisherResult.trigger[i] || 0;
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

    try {
        const adxConfig = config.strategy.adx;
        const adxResult = ADX.calculate({
            high: input.high,
            low: input.low,
            close: input.close,
            period: adxConfig.period
        });
        const adxOffset = df_with_indicators.length - adxResult.length;
        df_with_indicators.forEach((k, i) => {
            if (i >= adxOffset) {
                k.adx = adxResult[i - adxOffset].adx || 0;
            } else {
                k.adx = 0;
            }
        });
    } catch (e) {
        logger.error(`Error calculating ADX: ${e.message}`);
        df_with_indicators.forEach(k => { k.adx = 0; });
    }
    
    for (let i = 1; i < df_with_indicators.length; i++) {
        for (const key of ['st_fast_line', 'st_fast_direction', 'st_slow_line', 'st_slow_direction', 'rsi', 'volume_ma', 'fisher', 'fisher_signal', 'atr', 'adx']) {
            if (df_with_indicators[i][key] === 0 && df_with_indicators[i-1][key] !== undefined) {
                df_with_indicators[i][key] = df_with_indicators[i-1][key];
            }
        }
    }

    return df_with_indicators;
}



module.exports = {
    calculateEhlSupertrendIndicators
};