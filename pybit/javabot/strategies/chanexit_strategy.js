import { v4 as uuidv4 } from 'uuid';
import moment from 'moment-timezone';
const { Decimal } = require('decimal.js');
const { calculateEMA, calculateSMA, calculateATR, calculateRSI, calculateEhlersSupertrend, calculateFisherTransform } = require('../indicators/indicators.js');

class ChanExitStrategy {
  constructor(config, logger) {
    this.config = config;
    this.logger = logger;
    this.lastSignalBar = {};
  }

  // Helper to calculate EMA (Decimal.js compatible)
  _calculateEMA(data, period) {
    return calculateEMA(data, period, period);
  }

  // Helper to calculate SMA (Decimal.js compatible)
  _calculateSMA(data, period) {
    return calculateSMA(data, period);
  }

  // Helper to calculate ATR (Decimal.js compatible)
  _calculateATR(high, low, close, period) {
    return calculateATR(high, low, close, period);
  }

  // Helper for RSI (Decimal.js compatible)
  _calculateRSI(data, period) {
    return calculateRSI(data, period);
  }

  

  async _higherTfTrend(symbol) {
    const htf = this.config.strategies.chanExit.higherTfTimeframe;
    const short = this.config.strategies.chanExit.htfEmaShort;
    const long = this.config.strategies.chanExit.htfEmaLong;
    const klines = await this.bybitClient.getKlines(symbol, htf, long + 5);

    if (!klines || klines.length < Math.max(short, long) + 1) {
      this.logger.debug(`Not enough data for HTF trend for ${symbol}.`);
      return 'none';
    }
    const closePrices = klines.map(k => k.close);
    const emaS = this._calculateEMA(closePrices, short).slice(-1)[0];
    const emaL = this._calculateEMA(closePrices, long).slice(-1)[0];

    if (emaS.gt(emaL)) return 'long';
    if (emaS.lt(emaL)) return 'short';
    return 'none';
  }

  buildIndicators(klines) {
    // Ensure all OHLCV values are Decimal.js objects
    const processedKlines = klines.map(kline => ({
        ...kline,
        open: new Decimal(kline.open),
        high: new Decimal(kline.high),
        low: new Decimal(kline.low),
        close: new Decimal(kline.close),
        volume: new Decimal(kline.volume)
    }));

    const highPrices = processedKlines.map(k => k.high);
    const lowPrices = processedKlines.map(k => k.low);
    const closePrices = processedKlines.map(k => k.close);
    const volumes = processedKlines.map(k => k.volume);

    const atrSeries = this._calculateATR(highPrices, lowPrices, closePrices, this.config.strategies.chanExit.atrPeriod);
    processedKlines.forEach((k, i) => k.atr = atrSeries[i] || new Decimal(0));

    const volatilityLookback = this.config.strategies.chanExit.volatilityLookback || 20;
    const pricePctChange = [];
    for (let i = 1; i < closePrices.length; i++) {
        pricePctChange.push(closePrices[i].minus(closePrices[i-1]).dividedBy(closePrices[i-1]));
    }
    const priceStd = [];
    for (let i = 0; i < pricePctChange.length; i++) {
        const window = pricePctChange.slice(Math.max(0, i - volatilityLookback + 1), i + 1);
        const mean = window.reduce((a, b) => a.plus(b), new Decimal(0)).dividedBy(window.length);
        const std = new Decimal(Math.sqrt(window.map(x => x.minus(mean).pow(2)).reduce((a, b) => a.plus(b), new Decimal(0)).dividedBy(window.length)));
        priceStd.push(std);
    }
    
    let dynamicMultiplier = new Array(processedKlines.length).fill(new Decimal(this.config.strategies.chanExit.chandelierMultiplier));
    if (processedKlines.length >= volatilityLookback && priceStd.length > 0) {
        const meanPriceStd = priceStd.reduce((a,b) => a.plus(b), new Decimal(0)).dividedBy(priceStd.length);
        if (meanPriceStd.gt(0)) {
            for (let i = 0; i < priceStd.length; i++) {
              dynamicMultiplier[i] = Decimal.min(
                  new Decimal(this.config.strategies.chanExit.maxAtrMultiplier),
                  Decimal.max(new Decimal(this.config.strategies.chanExit.minAtrMultiplier), new Decimal(this.config.strategies.chanExit.chandelierMultiplier).times(priceStd[i].dividedBy(meanPriceStd)))
              );
            }
        }
    }
    processedKlines.forEach((k, i) => k.dynamic_multiplier = dynamicMultiplier[i] || new Decimal(0));

    processedKlines.forEach((k, i) => {
        k.ch_long = k.high.minus(k.atr.times(k.dynamic_multiplier));
        k.ch_short = k.low.plus(k.atr.times(k.dynamic_multiplier));
    });
    
    const trendEma = this._calculateEMA(closePrices, this.config.strategies.chanExit.trendEmaPeriod);
    const emaS = this._calculateEMA(closePrices, this.config.strategies.chanExit.emaShort);
    const emaL = this._calculateEMA(closePrices, this.config.strategies.chanExit.emaLong);
    const rsi = this._calculateRSI(closePrices, this.config.strategies.chanExit.rsiPeriod);

    processedKlines.forEach((k, i) => {
        k.trend_ema = trendEma[i] || new Decimal(0);
        k.ema_s = emaS[i] || new Decimal(0);
        k.ema_l = emaL[i] || new Decimal(0);
        k.rsi = rsi[i] || new Decimal(0);
    });

    const volumeMa = this._calculateSMA(volumes, this.config.strategies.chanExit.volumeMaPeriod || 20);
    processedKlines.forEach((k, i) => {
        k.vol_ma = volumeMa[i] || new Decimal(0);
        k.vol_spike = k.vol_ma.gt(0) && (k.volume.dividedBy(k.vol_ma)).gt(this.config.strategies.chanExit.volumeThresholdMultiplier);
    });
    
    // Use actual implementations
    const estSlowResult = calculateEhlersSupertrend(highPrices, lowPrices, closePrices, this.config.strategies.chanExit.estSlowLength || 8, this.config.strategies.chanExit.estSlowMultiplier || 1.2);
    const fisherResult = calculateFisherTransform(highPrices, lowPrices, this.config.strategies.chanExit.ehlersFisherPeriod || 8);
    processedKlines.forEach((k, i) => {
        k.est_slow = estSlowResult?.supertrend[i] || new Decimal(0);
        k.est_slow_direction = estSlowResult?.direction[i] || 0;
        k.fisher = fisherResult?.fisher[i] || new Decimal(0);
        k.fisher_signal = fisherResult?.trigger[i] || new Decimal(0);
    });

    // Final ffill and fillna(0) for all new columns
    // This is simplified; a full ffill would require more complex logic for each column.
    processedKlines.forEach(kline => {
        for (const key in kline) {
            if (kline[key] instanceof Decimal && kline[key].isNaN()) {
                kline[key] = new Decimal(0); // Replace NaN with 0 for simplicity
            }
        }
    });

    return processedKlines;
  }

  async generateSignals(symbol, klines) {
    let minRequiredKlines = Math.max(
      this.config.strategies.chanExit.minKlinesForStrategy, this.config.strategies.chanExit.trendEmaPeriod,
      this.config.strategies.chanExit.emaLong, this.config.strategies.chanExit.atrPeriod,
      this.config.strategies.chanExit.rsiPeriod, this.config.strategies.chanExit.volumeMaPeriod || 20,
      this.config.strategies.chanExit.volatilityLookback || 20,
      (this.config.strategies.chanExit.estSlowLength || 8) + 5, (this.config.strategies.chanExit.ehlersFisherPeriod || 8) + 5
    );
    // Add checks for other optional filters if they were implemented

    if (!klines || klines.length < minRequiredKlines) {
      return { signal: 'none', currentPrice: new Decimal(0), slPrice: new Decimal(0), tpPrice: new Decimal(0), reason: `not enough bars (${klines ? klines.length : 0} < ${minRequiredKlines})` };
    }

    const dfWithIndicators = this._buildIndicators(klines);
    const i = dfWithIndicators.length - 1; // Current bar (last)
    const j = dfWithIndicators.length - 2; // Previous bar

    if (i < 1) { // Need at least two bars for crossover checks
      return { signal: 'none', currentPrice: new Decimal(0), slPrice: new Decimal(0), tpPrice: new Decimal(0), reason: 'not enough candles for crossover check' };
    }

    const lastRow = dfWithIndicators[i];
    const prevRow = dfWithIndicators[j];

    const cp = lastRow.close;
    const atr = lastRow.atr;
    const dynamicMultiplier = lastRow.dynamic_multiplier;

    if (atr.lte(0) || atr.isNaN() || dynamicMultiplier.isNaN()) {
      return { signal: 'none', currentPrice: new Decimal(0), slPrice: new Decimal(0), tpPrice: new Decimal(0), reason: 'bad atr or dynamic multiplier' };
    }

    const riskDistance = atr.times(dynamicMultiplier);

    const htfTrend = await this._higherTfTrend(symbol);
    if (htfTrend === 'none') {
      return { signal: 'none', currentPrice: new Decimal(0), slPrice: new Decimal(0), tpPrice: new Decimal(0), reason: 'htf neutral' };
    }

    const currentBarTimestamp = lastRow.time; // Assuming 'time' is the timestamp
    if (symbol in this.lastSignalBar && (currentBarTimestamp - this.lastSignalBar[symbol]) < (this.config.strategies.chanExit.minBarsBetweenTrades * this.config.trading.timeframe * 60 * 1000)) { // Convert minutes to milliseconds
      return { signal: 'none', currentPrice: new Decimal(0), slPrice: new Decimal(0), tpPrice: new Decimal(0), reason: 'cool-down period active' };
    }

    // Base conditions
    let longCond = (
      lastRow.ema_s.gt(lastRow.ema_l) &&
      prevRow.ema_s.lte(prevRow.ema_l) &&
      cp.gt(lastRow.trend_ema) &&
      lastRow.rsi.lt(this.config.strategies.chanExit.rsiOverbought) &&
      lastRow.vol_spike &&
      (htfTrend === 'long')
    );

    let shortCond = (
      lastRow.ema_s.lt(lastRow.ema_l) &&
      prevRow.ema_s.gte(prevRow.ema_l) &&
      cp.lt(lastRow.trend_ema) &&
      lastRow.rsi.gt(this.config.strategies.chanExit.rsiOversold) &&
      lastRow.vol_spike &&
      (htfTrend === 'short')
    );

    // Ehlers Supertrend filter (mocked)
    // if (this.config.strategies.chanExit.useEstSlowFilter) {
    //   longCond = longCond && (lastRow.est_slow.eq(1));
    //   shortCond = shortCond && (lastRow.est_slow.eq(-1));
    // }

    let signal = 'none';
    let tpPrice = null;
    let slPrice = null;
    let reason = 'no match';

    if (longCond) {
      signal = 'Buy';
      slPrice = cp.minus(riskDistance);
      tpPrice = cp.plus(riskDistance.times(this.config.strategies.chanExit.rewardRiskRatio || 2.5));
      reason = 'EMA cross up, price above trend EMA, RSI not overbought, volume spike, HTF long';
    } else if (shortCond) {
      signal = 'Sell';
      slPrice = cp.plus(riskDistance);
      tpPrice = cp.minus(riskDistance.times(this.config.strategies.chanExit.rewardRiskRatio || 2.5));
      reason = 'EMA cross down, price below trend EMA, RSI not oversold, volume spike, HTF short';
    }

    if (signal !== 'none') {
      this.lastSignalBar[symbol] = currentBarTimestamp;
    }

    return { signal, currentPrice: cp, slPrice, tpPrice, reason, df_indicators: dfWithIndicators };
  }

  

module.exports = ChanExitStrategy;
