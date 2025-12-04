/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Refactored)
 * ======================================================
 * Strategy Module
 *
 * This module encapsulates the logic for calculating technical indicators
 * and generating trading signals based on a scoring model.
 */

import * as TA from './technical-analysis.js';
import * as TAA from './technical-analysis-advanced.js';

export class Strategy {
    constructor(config) {
        this.config = config.indicators;
    }

    calculateIndicators(klines) {
        const closes = klines.map(k => k.close);
        const highs = klines.map(k => k.high);
        const lows = klines.map(k => k.low);
        const volumes = klines.map(k => k.volume);

        return {
            rsi: TA.rsi(closes, this.config.rsi),
            macd: TA.macd(closes, this.config.macd.fast, this.config.macd.slow, this.config.macd.signal),
            bollingerBands: TA.bollinger(closes, this.config.bb.period, this.config.bb.std),
            atr: TA.atr(highs, lows, closes, this.config.atr),
            stochRSI: TA.stochRSI(closes, this.config.stochRSI.rsi, this.config.stochRSI.stoch, this.config.stochRSI.k, this.config.stochRSI.d),
            adx: TA.adx(highs, lows, closes, this.config.adx),
            williamsR: TA.williamsR(highs, lows, closes, 14),
            
            ehlersFisher: TA.fisher(highs, lows, this.config.fisher),
            supertrend: TAA.superTrend(highs, lows, closes, this.config.advanced.superTrend.period, this.config.advanced.superTrend.multiplier),
            ichimoku: TAA.ichimoku(highs, lows, closes, this.config.advanced.ichimoku.span1, this.config.advanced.ichimoku.span2, this.config.advanced.ichimoku.span3),
            vwap: TAA.vwap(highs, lows, closes, volumes),
            hma: TAA.hullMA(closes, this.config.advanced.hma.period),
            choppiness: TAA.choppiness(highs, lows, closes, this.config.advanced.choppiness.period),
            t3: TAA.t3(closes, this.config.advanced.t3.period, this.config.advanced.t3.vFactor)
        };
    }

    generateSignal(indicators, currentPrice) {
        let score = 0;
        const latest = (arr) => arr[arr.length - 1];

        // Trend
        if (latest(indicators.ehlersFisher) > 0 && latest(indicators.ehlersFisher) > indicators.ehlersFisher[indicators.ehlersFisher.length - 2]) score += 20;
        if (latest(indicators.ehlersFisher) < 0 && latest(indicators.ehlersFisher) < indicators.ehlersFisher[indicators.ehlersFisher.length - 2]) score -= 20;
        if (currentPrice > latest(indicators.supertrend.trend)) score += 15; else score -= 15;
        if (latest(indicators.adx.adx) > 25 && latest(indicators.adx.pdi) > latest(indicators.adx.ndi)) score += 10;
        if (latest(indicators.adx.adx) > 25 && latest(indicators.adx.ndi) > latest(indicators.adx.pdi)) score -= 10;

        // Momentum
        if (latest(indicators.rsi) < 30) score += 10; else if (latest(indicators.rsi) > 70) score -= 10;
        if (latest(indicators.macd.histogram) > 0 && indicators.macd.histogram[indicators.macd.histogram.length - 2] < 0) score += 15; // Bullish crossover
        if (latest(indicators.macd.histogram) < 0 && indicators.macd.histogram[indicators.macd.histogram.length - 2] > 0) score -= 15; // Bearish crossover
        if (latest(indicators.stochRSI.k) < 20 && latest(indicators.stochRSI.d) < 20) score += 10;
        if (latest(indicators.stochRSI.k) > 80 && latest(indicators.stochRSI.d) > 80) score -= 10;
        
        let signal = 'HOLD';
        if (score > 40) signal = 'BUY';
        if (score < -40) signal = 'SELL';

        return { score, signal };
    }
}
