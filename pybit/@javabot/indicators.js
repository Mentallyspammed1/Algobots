const { SMA, EMA, RSI, MACD, BollingerBands, ATR, StochasticRSI, ADX, CCI, VWAP, OBV, MFI, WilliamsR, IchimokuCloud } = require('trading-signals');
const ccxt = require('ccxt');
const { Supertrend, FisherTransform } = require('technicalindicators');

class BybitIndicatorModule {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.exchange = new ccxt.bybit({
      apiKey,
      secret: apiSecret,
      enableRateLimit: true,
    });
    this.symbol = symbol;
    this.timeframe = timeframe;
  }

  async fetchOHLCV(limit = 100) {
    try {
      const ohlcv = await this.exchange.fetchOHLCV(
        this.symbol,
        this.timeframe,
        undefined,
        limit
      );
      return ohlcv.map(candle => ({
        timestamp: candle[0],
        open: candle[1],
        high: candle[2],
        low: candle[3],
        close: candle[4],
        volume: candle[5],
      }));
    } catch (error) {
      console.error('Error fetching OHLCV:', error.message);
      return [];
    }
  }

  // --- START: Indicators from 'trading-signals' ---

  async getSMA(period = 14) {
    const ohlcv = await this.fetchOHLCV(period + 10);
    if (ohlcv.length < period) return null;

    const sma = new SMA(period);
    const closes = ohlcv.map(candle => candle.close);
    closes.forEach(price => sma.add(price));
    return sma.getResult();
  }

  async getEMA(period = 14) {
    const ohlcv = await this.fetchOHLCV(period + 10);
    if (ohlcv.length < period) return null;

    const ema = new EMA(period);
    const closes = ohlcv.map(candle => candle.close);
    closes.forEach(price => ema.add(price));
    return ema.getResult();
  }

  async getRSI(period = 14) {
    const ohlcv = await this.fetchOHLCV(period + 10);
    if (ohlcv.length < period) return null;

    const rsi = new RSI(period);
    const closes = ohlcv.map(candle => candle.close);
    closes.forEach(price => rsi.add(price));
    return rsi.getResult();
  }

  async getMACD(fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
    const ohlcv = await this.fetchOHLCV(slowPeriod + signalPeriod + 10);
    if (ohlcv.length < slowPeriod + signalPeriod) return null;

    const macd = new MACD({ fastPeriod, slowPeriod, signalPeriod });
    const closes = ohlcv.map(candle => candle.close);
    closes.forEach(price => macd.add(price));
    const result = macd.getResult();
    return {
      macd: result.macd,
      signal: result.signal,
      histogram: result.histogram,
    };
  }

  async getBollingerBands(period = 20, stdDev = 2) {
    const ohlcv = await this.fetchOHLCV(period + 10);
    if (ohlcv.length < period) return null;

    const bb = new BollingerBands(period, stdDev);
    const closes = ohlcv.map(candle => candle.close);
    closes.forEach(price => bb.add(price));
    const result = bb.getResult();
    return {
      upper: result.upper,
      middle: result.middle,
      lower: result.lower,
      width: (result.upper - result.lower) / result.middle,
    };
  }

  async getATR(period = 14) {
    const ohlcv = await this.fetchOHLCV(period + 10);
    if (ohlcv.length < period) return null;

    const atr = new ATR(period);
    ohlcv.forEach(candle => atr.add(candle.high, candle.low, candle.close));
    return atr.getResult();
  }

  // ... other indicators from trading-signals ...

  // --- END: Indicators from 'trading-signals' ---


  // --- START: Indicators from 'technicalindicators' ---

  async getSupertrend(period = 10, multiplier = 3) {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const input = {
          high: ohlcv.map(c => c.high),
          low: ohlcv.map(c => c.low),
          close: ohlcv.map(c => c.close),
          period: period,
          multiplier: multiplier
      };
      return Supertrend.calculate(input);
  }

  async getFisherTransform(period = 9) {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const input = {
          high: ohlcv.map(c => c.high),
          low: ohlcv.map(c => c.low),
          period: period
      };
      return FisherTransform.calculate(input);
  }

  // --- END: Indicators from 'technicalindicators' ---

}

// Example of how to use the combined module
class BybitTradingBot {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.indicators = new BybitIndicatorModule(apiKey, apiSecret, symbol, timeframe);
  }

  async placeBuyOrder(symbol, amount) {
    try {
      const order = await this.indicators.exchange.createMarketBuyOrderWithCost(symbol, amount);
      console.log('Buy order placed:', order);
      return order;
    } catch (error) {
      console.error('Error placing buy order:', error.message);
      return null;
    }
  }

  async placeSellOrder(symbol, amount) {
    try {
      const order = await this.indicators.exchange.createMarketSellOrder(symbol, amount);
      console.log('Sell order placed:', order);
      return order;
    } catch (error) {
      console.error('Error placing sell order:', error.message);
      return null;
    }
  }

  async run() {
    // Fetch indicators from 'trading-signals'
    const rsi = await this.indicators.getRSI(14);
    const macd = await this.indicators.getMACD(12, 26, 9);
    
    // Fetch indicators from 'technicalindicators'
    const supertrend = await this.indicators.getSupertrend(10, 3);
    const fisher = await this.indicators.getFisherTransform(9);

    if (!rsi || !macd || !supertrend || !fisher) {
      console.log('Insufficient data to generate signals.');
      return;
    }

    const lastSupertrend = supertrend[supertrend.length - 1];
    const lastFisher = fisher[fisher.length - 1];

    console.log(`RSI: ${rsi.toFixed(2)}`);
    console.log(`MACD Histogram: ${macd.histogram.toFixed(2)}`);
    console.log(`Supertrend: ${lastSupertrend.supertrend.toFixed(2)} (Direction: ${lastSupertrend.direction > 0 ? 'Up' : 'Down'})`);
    console.log(`Fisher: ${lastFisher.fisher.toFixed(2)} (Signal: ${lastFisher.signal.toFixed(2)})`);

    // --- Example Strategy ---
    if (rsi < 30 && macd.histogram > 0 && lastSupertrend.direction > 0 && lastFisher.fisher > lastFisher.signal) {
      console.log('Strong Buy Signal Detected!');
      await this.placeBuyOrder(this.indicators.symbol, 10); // Example: Buy 10 USDT worth of BTC
    } else if (rsi > 70 && macd.histogram < 0 && lastSupertrend.direction < 0 && lastFisher.fisher < lastFisher.signal) {
      console.log('Strong Sell Signal Detected!');
      await this.placeSellOrder(this.indicators.symbol, 0.001); // Example: Sell 0.001 BTC
    }
  }
}

module.exports = { BybitIndicatorModule, BybitTradingBot };