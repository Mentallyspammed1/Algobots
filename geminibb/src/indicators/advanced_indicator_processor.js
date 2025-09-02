// src/indicators/advanced_indicator_processor.js
import Decimal from 'decimal.js';
import { Logger } from '../utils/logger.js';

const logger = new Logger('INDICATOR_PROCESSOR');

export class AdvancedIndicatorProcessor {
    constructor() {
        logger.info('AdvancedIndicatorProcessor initialized.');
    }

    /**
     * Calculates Simple Moving Average (SMA).
     * @param {Array<Decimal>} closes - Array of closing prices.
     * @param {number} period - SMA period.
     * @returns {Array<Decimal>} - Array of SMA values.
     */
    calculateSMA(closes, period) {
        const smas = [];
        for (let i = 0; i < closes.length; i++) {
            if (i >= period - 1) {
                const sum = closes.slice(i - period + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
                smas.push(sum.dividedBy(period));
            } else {
                smas.push(new Decimal(NaN)); // Not enough data
            }
        }
        return smas;
    }

    /**
     * Calculates Relative Strength Index (RSI).
     * @param {Array<Decimal>} closes - Array of closing prices.
     * @param {number} period - RSI period.
     * @returns {Array<Decimal>} - Array of RSI values (0-100).
     */
    calculateRSI(closes, period = 14) {
        if (closes.length < period) return closes.map(() => new Decimal(NaN));

        const rsiValues = [];
        let avgGain = new Decimal(0);
        let avgLoss = new Decimal(0);

        // Calculate initial AVG Gain and AVG Loss
        let firstPeriodGains = new Decimal(0);
        let firstPeriodLosses = new Decimal(0);
        for (let i = 1; i <= period; i++) {
            const diff = closes[i].minus(closes[i - 1]);
            if (diff.greaterThan(0)) {
                firstPeriodGains = firstPeriodGains.plus(diff);
            } else {
                firstPeriodLosses = firstPeriodLosses.plus(diff.abs());
            }
        }
        avgGain = firstPeriodGains.dividedBy(period);
        avgLoss = firstPeriodLosses.dividedBy(period);

        // Add NaN for initial period where RSI cannot be calculated
        for (let i = 0; i < period; i++) {
            rsiValues.push(new Decimal(NaN));
        }

        // Calculate subsequent RSI values
        for (let i = period + 1; i < closes.length; i++) {
            const diff = closes[i].minus(closes[i - 1]);
            let gain = new Decimal(0);
            let loss = new Decimal(0);

            if (diff.greaterThan(0)) {
                gain = diff;
            } else {
                loss = diff.abs();
            }

            avgGain = (avgGain.times(period - 1).plus(gain)).dividedBy(period);
            avgLoss = (avgLoss.times(period - 1).plus(loss)).dividedBy(period);

            let rs = avgGain.dividedBy(avgLoss);
            if (avgLoss.isZero()) rs = new Decimal(Infinity); // Prevent division by zero
            if (avgGain.isZero() && avgLoss.isZero()) rs = new Decimal(0); // No movement

            const rsi = new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs)));
            rsiValues.push(rsi);
        }
        return rsiValues;
    }

    /**
     * Calculates Moving Average Convergence Divergence (MACD).
     * @param {Array<Decimal>} closes - Array of closing prices.
     * @param {number} fastPeriod - Fast EMA period.
     * @param {number} slowPeriod - Slow EMA period.
     * @param {number} signalPeriod - Signal line EMA period.
     * @returns {object} - { macd: Array<Decimal>, signal: Array<Decimal>, hist: Array<Decimal> }
     */
    calculateMACD(closes, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
        const emas = this._calculateEMA(closes, slowPeriod); // Re-use internal EMA
        const fastEmas = this._calculateEMA(closes, fastPeriod);

        const macd = [];
        for (let i = 0; i < closes.length; i++) {
            if (emas[i].isNaN() || fastEmas[i].isNaN()) {
                macd.push(new Decimal(NaN));
            } else {
                macd.push(fastEmas[i].minus(emas[i]));
            }
        }

        const signal = this._calculateEMA(macd, signalPeriod);
        const hist = macd.map((m, i) => (m.isNaN() || signal[i].isNaN()) ? new Decimal(NaN) : m.minus(signal[i]));

        return { macd, signal, hist };
    }

    /**
     * Helper to calculate Exponential Moving Average (EMA).
     * @param {Array<Decimal>} data - Array of data points.
     * @param {number} period - EMA period.
     * @returns {Array<Decimal>} - Array of EMA values.
     */
    _calculateEMA(data, period) {
        const emas = [];
        const multiplier = new Decimal(2).dividedBy(new Decimal(period).plus(1));
        let ema = new Decimal(NaN);

        for (let i = 0; i < data.length; i++) {
            if (data[i].isNaN()) {
                emas.push(new Decimal(NaN));
                continue;
            }
            if (i < period - 1) { // Not enough data for initial EMA
                emas.push(new Decimal(NaN));
            } else if (i === period - 1) { // Calculate initial SMA for first EMA value
                ema = data.slice(0, period).reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
                emas.push(ema);
            } else {
                ema = data[i].minus(ema).times(multiplier).plus(ema);
                emas.push(ema);
            }
        }
        return emas;
    }

    /**
     * Calculates Bollinger Bands (BBands).
     * @param {Array<Decimal>} closes - Array of closing prices.
     * @param {number} period - Period for SMA.
     * @param {number} stdDevFactor - Standard deviation multiplier.
     * @returns {object} - { middle: Array<Decimal>, upper: Array<Decimal>, lower: Array<Decimal> }
     */
    calculateBBands(closes, period = 20, stdDevFactor = 2) {
        const middleBand = this.calculateSMA(closes, period);
        const upperBand = [];
        const lowerBand = [];

        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) {
                upperBand.push(new Decimal(NaN));
                lowerBand.push(new Decimal(NaN));
                continue;
            }

            const slice = closes.slice(i - period + 1, i + 1);
            const mean = middleBand[i];

            // Calculate standard deviation
            const sumOfSquares = slice.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0));
            const stdDev = sumOfSquares.dividedBy(period).sqrt();

            upperBand.push(mean.plus(stdDev.times(stdDevFactor)));
            lowerBand.push(mean.minus(stdDev.times(stdDevFactor)));
        }
        return { middle: middleBand, upper: upperBand, lower: lowerBand };
    }

    /**
     * Calculates Average True Range (ATR).
     * @param {Array<object>} candles - Array of candle objects {high, low, close}.
     * @param {number} period - ATR period.
     * @returns {Array<Decimal>} - Array of ATR values.
     */
    calculateATR(candles, period = 14) {
        if (candles.length < period) return candles.map(() => new Decimal(NaN));

        const trueRanges = [];
        for (let i = 1; i < candles.length; i++) {
            const highLow = candles[i].high.minus(candles[i].low);
            const highPrevClose = candles[i].high.minus(candles[i - 1].close).abs();
            const lowPrevClose = candles[i].low.minus(candles[i - 1].close).abs();
            trueRanges.push(Decimal.max(highLow, highPrevClose, lowPrevClose));
        }

        const atrValues = [];
        let atr = new Decimal(0);

        // Initial ATR is SMA of first 'period' true ranges
        for (let i = 0; i < period; i++) {
            atr = atr.plus(trueRanges[i]);
        }
        atr = atr.dividedBy(period);
        atrValues.push(new Decimal(NaN)); // First candle has no TR
        for (let i = 0; i < period - 1; i++) atrValues.push(new Decimal(NaN)); // Fill leading NaNs for period

        atrValues.push(atr);

        // Subsequent ATR calculations (Wilder's smoothing)
        for (let i = period; i < trueRanges.length; i++) {
            atr = (atr.times(period - 1).plus(trueRanges[i])).dividedBy(period);
            atrValues.push(atr);
        }
        return atrValues;
    }

    /**
     * Calculates a composite signal based on multiple indicators.
     * @param {object} indicatorData - Object containing various indicator results.
     * @param {object} weights - Weights for each indicator (e.g., { rsi: 0.4, macd: 0.6 }).
     * @returns {object} - { signal: number (between -1 and 1), interpretation: string }.
     */
    calculateCompositeSignals(indicatorData, weights = {}) {
        let compositeScore = new Decimal(0);
        let signalCount = 0;
        const interpretations = [];

        // Example: RSI (Overbought/Oversold)
        if (indicatorData.rsi && !indicatorData.rsi.slice(-1)[0].isNaN()) {
            const lastRSI = indicatorData.rsi.slice(-1)[0];
            let rsiSignal = new Decimal(0);
            if (lastRSI.greaterThan(70)) {
                rsiSignal = new Decimal(-1); // Bearish
                interpretations.push(`RSI (${lastRSI.toFixed(2)}) is overbought.`);
            } else if (lastRSI.lessThan(30)) {
                rsiSignal = new Decimal(1); // Bullish
                interpretations.push(`RSI (${lastRSI.toFixed(2)}) is oversold.`);
            } else {
                interpretations.push(`RSI (${lastRSI.toFixed(2)}) is neutral.`);
            }
            compositeScore = compositeScore.plus(rsiSignal.times(weights.rsi || 0.3));
            signalCount++;
        }

        // Example: MACD (Crossover)
        if (indicatorData.macd && indicatorData.macd.macd && indicatorData.macd.signal &&
            !indicatorData.macd.macd.slice(-1)[0].isNaN() && !indicatorData.macd.signal.slice(-1)[0].isNaN()) {
            const lastMACD = indicatorData.macd.macd.slice(-1)[0];
            const lastSignal = indicatorData.macd.signal.slice(-1)[0];
            const prevMACD = indicatorData.macd.macd.slice(-2)[0];
            const prevSignal = indicatorData.macd.signal.slice(-2)[0];

            let macdSignal = new Decimal(0);
            if (lastMACD.greaterThan(lastSignal) && prevMACD.lessThanOrEqualTo(prevSignal)) {
                macdSignal = new Decimal(1); // Bullish crossover
                interpretations.push(`MACD bullish crossover.`);
            } else if (lastMACD.lessThan(lastSignal) && prevMACD.greaterThanOrEqualTo(prevSignal)) {
                macdSignal = new Decimal(-1); // Bearish crossover
                interpretations.push(`MACD bearish crossover.`);
            } else {
                interpretations.push(`MACD is neutral.`);
            }
            compositeScore = compositeScore.plus(macdSignal.times(weights.macd || 0.4));
            signalCount++;
        }

        // Example: Bollinger Bands (Price vs Bands)
        if (indicatorData.bbands && indicatorData.bbands.upper && indicatorData.bbands.lower && indicatorData.closes) {
            const lastClose = indicatorData.closes.slice(-1)[0];
            const lastUpper = indicatorData.bbands.upper.slice(-1)[0];
            const lastLower = indicatorData.bbands.lower.slice(-1)[0];

            if (!lastClose.isNaN() && !lastUpper.isNaN() && !lastLower.isNaN()) {
                let bbandSignal = new Decimal(0);
                if (lastClose.greaterThan(lastUpper)) {
                    bbandSignal = new Decimal(-0.5); // Price above upper band, potentially overextended
                    interpretations.push(`Price (${lastClose.toFixed(2)}) is above upper BBand (${lastUpper.toFixed(2)}).`);
                } else if (lastClose.lessThan(lastLower)) {
                    bbandSignal = new Decimal(0.5); // Price below lower band, potentially oversold
                    interpretations.push(`Price (${lastClose.toFixed(2)}) is below lower BBand (${lastLower.toFixed(2)}).`);
                } else {
                    interpretations.push(`Price (${lastClose.toFixed(2)}) is within BBands.`);
                }
                compositeScore = compositeScore.plus(bbandSignal.times(weights.bbands || 0.3));
                signalCount++;
            }
        }

        // Normalize score to -1 to 1 range (if weights sum to 1, this isn't strictly necessary but good for robustness)
        let finalSignal = new Decimal(0);
        if (signalCount > 0) {
            finalSignal = compositeScore.dividedBy(new Decimal(Object.values(weights).reduce((a, b) => a + b, 0) || signalCount));
        }

        let overallInterpretation = 'Neutral';
        if (finalSignal.greaterThan(0.5)) overallInterpretation = 'Strong Bullish';
        else if (finalSignal.greaterThan(0)) overallInterpretation = 'Bullish';
        else if (finalSignal.lessThan(-0.5)) overallInterpretation = 'Strong Bearish';
        else if (finalSignal.lessThan(0)) overallInterpretation = 'Bearish';

        return {
            signal: finalSignal.toNumber(),
            interpretation: overallInterpretation,
            details: interpretations.join('\n')
        };
    }
}
