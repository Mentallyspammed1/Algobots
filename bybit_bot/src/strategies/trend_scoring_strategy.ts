import { IStrategy } from './base_strategy';
import { Candle, Signal, StrategyConfig } from '../core/types';
import { logger } from '../core/logger';
import * as indicators from '../utils/indicators';

export class TrendScoringStrategy implements IStrategy {
  readonly name = 'TrendScoring';
  private last_signal: Signal = 'hold';

  // Indicator instances
  private macd: indicators.MACD;
  private rsi: indicators.RSI;
  private adx: indicators.ADX;
  private st: indicators.SuperTrend;
  private stoch: indicators.Stochastic;
  private bb: indicators.BollingerBands;
  private ichimoku: indicators.IchimokuCloud;
  private itrend: indicators.EhlersInstantaneousTrendline;
  private fisher: indicators.EhlersFisherTransform;

  private config: StrategyConfig;

  constructor(config: StrategyConfig) {
    this.config = config;
    const { params } = this.config;

    // Initialize indicators with params from config
    this.macd = new indicators.MACD(params.macd_fast_period, params.macd_slow_period, params.macd_signal_period);
    this.rsi = new indicators.RSI(params.rsi_period);
    this.adx = new indicators.ADX(params.adx_period);
    this.st = new indicators.SuperTrend(params.st_period, params.st_factor);
    this.stoch = new indicators.Stochastic(params.stoch_period, params.stoch_smoothing);
    this.bb = new indicators.BollingerBands(params.bb_period, params.bb_stddev);
    this.ichimoku = new indicators.IchimokuCloud(params.ichimoku_tenkan, params.ichimoku_kijun, params.ichimoku_senkou_b);
    this.itrend = new indicators.EhlersInstantaneousTrendline(params.itrend_period);
    this.fisher = new indicators.EhlersFisherTransform(params.fisher_period);

    logger.system(`Initialized TrendScoringStrategy with a comprehensive indicator set.`);
  }

  update(candle: Candle): void {
    // Update all indicators with the new candle data
    this.macd.update(candle.close);
    this.rsi.update(candle.close);
    this.adx.update(candle);
    this.st.next(candle);
    this.stoch.update(candle);
    this.bb.update(candle.close);
    this.ichimoku.update(candle);
    this.itrend.update(candle.close);
    this.fisher.update(candle.close);
  }

  getSignal(): Signal {
    let score = 0;
    const { weights, params } = this.config;
    const candle = this.st.candles[this.st.candles.length-1];

    const indicator_values = {
        price: candle.close,
        macd_hist: this.macd.histogram,
        rsi: this.rsi.value,
        adx: this.adx.adx,
        st_direction: this.st.direction,
        stoch_k: this.stoch.update(candle)?.k,
        ichimoku_cloud: this.ichimoku.senkou_span_a && this.ichimoku.senkou_span_b ? (this.ichimoku.senkou_span_a > this.ichimoku.senkou_span_b ? 'bullish' : 'bearish') : 'n/a',
    };

    // 1. MACD Score: Based on histogram direction and crossover strength
    if (this.macd.histogram !== null) {
        if (this.macd.histogram > 0) score += weights.macd;
        else score -= weights.macd;
    }

    // 2. RSI Score: Granular score based on distance from 50
    if (this.rsi.value !== null) {
        score += ((this.rsi.value - 50) / 50) * weights.rsi; // Scale: -1 to +1
    }

    // 3. ADX Score: Confirms trend strength before adding score
    if (this.adx.adx !== null && this.adx.adx > params.adx_threshold) {
        if (this.adx.pdi! > this.adx.mdi!) score += weights.adx;
        else score -= weights.adx;
    }

    // 4. SuperTrend Score: Clear trend direction
    if (this.st.direction === 'up') {
        score += weights.st;
    } else {
        score -= weights.st;
    }

    // 5. Stochastic Score: Looks for momentum and overbought/oversold conditions
    const stoch_data = this.stoch.update(candle);
    if (stoch_data) {
        if (stoch_data.k > stoch_data.d) score += weights.stochastic * 0.5; // K above D is bullish
        else score -= weights.stochastic * 0.5;
        if (stoch_data.k < 20) score += weights.stochastic * 0.5; // Oversold
        if (stoch_data.k > 80) score -= weights.stochastic * 0.5; // Overbought
    }

    // 6. Bollinger Bands Score: Price relative to bands for mean reversion signals
    const bb_data = this.bb.update(candle.close);
    if (bb_data) {
        if (candle.close > bb_data.upper) score -= weights.bollinger_bands; // Potential reversal short
        if (candle.close < bb_data.lower) score += weights.bollinger_bands; // Potential reversal long
    }

    // 7. Ichimoku Cloud Score: A comprehensive trend indicator
    const ichimoku_data = this.ichimoku;
    if (ichimoku_data.senkou_span_a !== null && ichimoku_data.senkou_span_b !== null) {
        // Price vs. Cloud
        if (candle.close > ichimoku_data.senkou_span_a && candle.close > ichimoku_data.senkou_span_b) {
            score += weights.ichimoku * 0.5; // Bullish
        } else if (candle.close < ichimoku_data.senkou_span_a && candle.close < ichimoku_data.senkou_span_b) {
            score -= weights.ichimoku * 0.5; // Bearish
        }
        // Tenkan/Kijun Cross
        if (ichimoku_data.tenkan_sen! > ichimoku_data.kijun_sen!) score += weights.ichimoku * 0.5;
        else score -= weights.ichimoku * 0.5;
    }

    // 8. Ehlers Instantaneous Trendline Score
    const itrend_data = this.itrend.update(candle.close);
    if (itrend_data) {
        if (candle.close > itrend_data.trend) score += weights.ehlers_itrend;
        else score -= weights.ehlers_itrend;
    }

    // 9. Ehlers Fisher Transform Score
    const fisher_data = this.fisher.update(candle.close);
    if (fisher_data && fisher_data.trigger !== null) {
        if (fisher_data.fisher > fisher_data.trigger) score += weights.ehlers_fisher; // Bullish crossover
        else score -= weights.ehlers_fisher; // Bearish crossover
    }

    logger.info('Indicator Values:', indicator_values);
    logger.info(`Total Trend Score: ${score.toFixed(2)}`);

    // Determine final signal based on thresholds
    if (score >= this.config.thresholds.long) {
        this.last_signal = 'long';
    } else if (score <= this.config.thresholds.short) {
        this.last_signal = 'short';
    } else {
        this.last_signal = 'hold';
    }
    return this.last_signal;
  }
}