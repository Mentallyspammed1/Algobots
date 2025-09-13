const { calculateEhlSupertrendIndicators } = require('../indicators/indicators.js');
const { Decimal } = require('decimal.js');

class EhlersSupertrendStrategy {
    constructor(config, logger) {
        this.config = config;
        this.logger = logger;
    }

    buildIndicators(klines) {
        return calculateEhlSupertrendIndicators(klines, this.config, this.logger);
    }

    /**
     * Generates trading signals based on Ehlers Supertrend and other indicators.
     * @param {Array<Object>} klines - Array of kline objects (with Decimal values).
     * @returns {Object} Signal, SL, TP, and reasoning.
     */
    generateSignals(klines) {
        if (!klines || klines.length < this.config.trading.min_klines_for_strategy) {
            return { signal: 'none', sl_price: null, tp_price: null, reasoning: 'not enough klines' };
        }

        const df = this.buildIndicators(klines);
        const last = df[df.length - 1];
        const prev = df[df.length - 2];

        const longTrendConfirmed = last.st_slow_direction.gt(0);
        const shortTrendConfirmed = last.st_slow_direction.lt(0);
        const fastCrossesAboveSlow = prev.st_fast_line.lte(prev.st_slow_line) && last.st_fast_line.gt(last.st_slow_line);
        const fastCrossesBelowSlow = prev.st_fast_line.gte(prev.st_slow_line) && last.st_fast_line.lt(last.st_slow_line);

        const fisherConfirmLong = last.fisher.gt(last.fisher_signal);
        const rsiConfirmLong = last.rsi.gt(this.config.strategies.ehlersSupertrend.rsi.confirmLong) && last.rsi.lt(this.config.strategies.ehlersSupertrend.rsi.overbought);
        const volumeConfirm = last.volume_spike || prev.volume_spike;

        const fisherConfirmShort = last.fisher.lt(last.fisher_signal);
        const rsiConfirmShort = last.rsi.lt(this.config.strategies.ehlersSupertrend.rsi.confirmShort) && last.rsi.gt(this.config.strategies.ehlersSupertrend.rsi.oversold);

        let signal = 'none', sl_price = null, tp_price = null, reasoning = [];

        if (longTrendConfirmed && fastCrossesAboveSlow && (fisherConfirmLong + rsiConfirmLong + volumeConfirm >= 2)) {
            signal = 'Buy';
            sl_price = prev.st_slow_line;
            const riskDistance = last.close.minus(sl_price);
            if (riskDistance.gt(0)) {
                tp_price = last.close.plus(riskDistance.times(this.config.order_logic.reward_risk_ratio));
                reasoning = ['SlowST Up', 'Fast>Slow Cross', `Confirms: ${[fisherConfirmLong && 'Fisher', rsiConfirmLong && 'RSI', volumeConfirm && 'Volume'].filter(Boolean).join('+')}`];
            } else { signal = 'none'; }
        } else if (shortTrendConfirmed && fastCrossesBelowSlow && (fisherConfirmShort + rsiConfirmShort + volumeConfirm >= 2)) {
            signal = 'Sell';
            sl_price = prev.st_slow_line;
            const riskDistance = sl_price.minus(last.close);
            if (riskDistance.gt(0)) {
                tp_price = last.close.minus(riskDistance.times(this.config.order_logic.reward_risk_ratio));
                reasoning = ['SlowST Down', 'Fast<Slow Cross', `Confirms: ${[fisherConfirmShort && 'Fisher', rsiConfirmShort && 'RSI', volumeConfirm && 'Volume'].filter(Boolean).join('+')}`];
            } else { signal = 'none'; }
        }

        return { signal, sl_price, tp_price, reasoning: reasoning.join('; '), df_indicators: df };
    }
}

module.exports = EhlersSupertrendStrategy;
