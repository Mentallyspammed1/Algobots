Below are code snippets for a JavaScript indicator module tailored for Bybit trading bots. This module uses the `trading-signals` library (recommended for its precision and TypeScript support) to compute common technical indicators like SMA, EMA, RSI, and MACD, which are useful for Bybit's crypto trading environment. The snippets include fetching real-time OHLCV data from Bybit's API and calculating indicators for bot decision-making. The module is designed to be lightweight, modular, and suitable for both spot and futures trading on Bybit.

### Prerequisites
- Install required packages: `npm i trading-signals ccxt`
- Get a Bybit API key/secret from [Bybit API Management](https://www.bybit.com/en-US/user/api-management).
- Basic understanding of Bybit's trading pairs (e.g., BTCUSDT) and timeframes (e.g., 1m, 5m, 1h).

### Indicator Module Snippets

#### 1. **Module Setup and Bybit API Connection**
This sets up the module, initializes the Bybit exchange via `ccxt`, and fetches OHLCV data.

```javascript
// indicatorModule.js
const { SMA, EMA, RSI, MACD } = require('trading-signals');
const ccxt = require('ccxt');

class BybitIndicatorModule {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.exchange = new ccxt.bybit({
      apiKey,
      secret: apiSecret,
      enableRateLimit: true, // Respect Bybit's rate limits
    });
    this.symbol = symbol; // e.g., 'BTCUSDT', 'ETHUSDT'
    this.timeframe = timeframe; // e.g., '1m', '5m', '1h'
  }

  // Fetch OHLCV data from Bybit
  async fetchOHLCV(limit = 100) {
    try {
      const ohlcv = await this.exchange.fetchOHLCV(
        this.symbol,
        this.timeframe,
        undefined,
        limit
      );
      // Returns [timestamp, open, high, low, close, volume]
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
}
module.exports = BybitIndicatorModule;
```

#### 2. **Simple Moving Average (SMA)**
Computes the SMA for a given period, useful for trend-following strategies.

```javascript
// Add to BybitIndicatorModule class
async getSMA(period = 14) {
  const ohlcv = await this.fetchOHLCV(period + 10); // Fetch extra candles for safety
  if (ohlcv.length < period) return null;

  const sma = new SMA(period);
  const closes = ohlcv.map(candle => candle.close);
  closes.forEach(price => sma.add(price));
  return sma.getResult(); // Returns latest SMA value
}
```

**Usage Example**:
```javascript
const BybitIndicatorModule = require('./indicatorModule');
const indicator = new BybitIndicatorModule('your-api-key', 'your-api-secret', 'BTCUSDT', '5m');

(async () => {
  const smaValue = await indicator.getSMA(14);
  console.log(`Latest SMA(14): ${smaValue}`); // e.g., 60000.25
})();
```

#### 3. **Exponential Moving Average (EMA)**
Computes the EMA, which is more sensitive to recent price changes.

```javascript
// Add to BybitIndicatorModule class
async getEMA(period = 14) {
  const ohlcv = await this.fetchOHLCV(period + 10);
  if (ohlcv.length < period) return null;

  const ema = new EMA(period);
  const closes = ohlcv.map(candle => candle.close);
  closes.forEach(price => ema.add(price));
  return ema.getResult(); // Returns latest EMA value
}
```

#### 4. **Relative Strength Index (RSI)**
Calculates RSI for momentum-based strategies (e.g., overbought/oversold conditions).

```javascript
// Add to BybitIndicatorModule class
async getRSI(period = 14) {
  const ohlcv = await this.fetchOHLCV(period + 10);
  if (ohlcv.length < period) return null;

  const rsi = new RSI(period);
  const closes = ohlcv.map(candle => candle.close);
  closes.forEach(price => rsi.add(price));
  return rsi.getResult(); // Returns latest RSI (0-100)
}
```

**Usage Example**:
```javascript
(async () => {
  const rsiValue = await indicator.getRSI(14);
  console.log(`Latest RSI(14): ${rsiValue}`); // e.g., 65.43 (overbought > 70, oversold < 30)
})();
```

#### 5. **MACD (Moving Average Convergence Divergence)**
Computes MACD for trend and momentum signals, including MACD line, signal line, and histogram.

```javascript
// Add to BybitIndicatorModule class
async getMACD(fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  const ohlcv = await this.fetchOHLCV(slowPeriod + signalPeriod + 10);
  if (ohlcv.length < slowPeriod + signalPeriod) return null;

  const macd = new MACD({ fastPeriod, slowPeriod, signalPeriod });
  const closes = ohlcv.map(candle => candle.close);
  closes.forEach(price => macd.add(price));
  const result = macd.getResult();
  return {
    macd: result.macd, // MACD line
    signal: result.signal, // Signal line
    histogram: result.histogram, // Difference
  };
}
```

**Usage Example**:
```javascript
(async () => {
  const macdValues = await indicator.getMACD(12, 26, 9);
  console.log('MACD:', macdValues);
  // e.g., { macd: 150.23, signal: 120.45, histogram: 29.78 }
  // Positive histogram suggests bullish momentum
})();
```

#### 6. **Real-Time Streaming Example**
For a bot, you may want to update indicators incrementally as new candles arrive.

```javascript
// Add to BybitIndicatorModule class
async streamIndicators(period = 14) {
  const sma = new SMA(period);
  const rsi = new RSI(period);

  // Simulate streaming (in a real bot, use Bybit WebSocket)
  while (true) {
    const ohlcv = await this.fetchOHLCV(1); // Fetch latest candle
    if (ohlcv.length === 0) continue;

    const latestClose = ohlcv[0].close;
    sma.add(latestClose);
    rsi.add(latestClose);

    console.log({
      sma: sma.getResult(),
      rsi: rsi.getResult(),
    });

    await new Promise(resolve => setTimeout(resolve, 60000 * parseInt(this.timeframe))); // Wait for next candle
  }
}
```

**Usage Example**:
```javascript
(async () => {
  await indicator.streamIndicators(14); // Logs SMA and RSI every 5 minutes for '5m' timeframe
})();
```

### Integration with a Bybit Trading Bot
Here’s how to use the module in a simple bot that places orders based on RSI and MACD signals.

```javascript
// bot.js
const BybitIndicatorModule = require('./indicatorModule');

class BybitTradingBot {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.indicators = new BybitIndicatorModule(apiKey, apiSecret, symbol, timeframe);
  }

  async run() {
    const rsi = await this.indicators.getRSI(14);
    const macd = await this.indicators.getMACD(12, 26, 9);

    if (!rsi || !macd) {
      console.log('Insufficient data');
      return;
    }

    console.log(`RSI: ${rsi}, MACD:`, macd);

    // Example strategy: Buy if RSI < 30 (oversold) and MACD histogram positive
    if (rsi < 30 && macd.histogram > 0) {
      console.log('Buy signal detected!');
      // Place buy order via ccxt
      // await this.indicators.exchange.createMarketBuyOrder(this.indicators.symbol, amount);
    }
    // Sell if RSI > 70 (overbought) and MACD histogram negative
    else if (rsi > 70 && macd.histogram < 0) {
      console.log('Sell signal detected!');
      // Place sell order
      // await this.indicators.exchange.createMarketSellOrder(this.indicators.symbol, amount);
    }
  }
}

const bot = new BybitTradingBot('your-api-key', 'your-api-secret');
setInterval(() => bot.run(), 60000 * 5); // Run every 5 minutes
```

### Notes
- **Error Handling**: Always handle API rate limits and errors (e.g., network issues). Bybit’s API limits vary by endpoint (check [Bybit API Docs](https://bybit-exchange.github.io/docs/v5/intro)).
- **WebSocket for Real-Time**: For production bots, use Bybit’s WebSocket API (`ccxt` supports it) instead of polling `fetchOHLCV` to reduce latency.
- **Precision**: `trading-signals` uses `big.js` for financial precision, critical for crypto trading.
- **Testing**: Backtest strategies with historical data before live trading. Use `fetchOHLCV` with larger limits for backtesting.
- **Security**: Store API keys securely (e.g., environment variables, not in code).
- **Customization**: Add more indicators (e.g., Bollinger Bands, ATR) from `trading-signals` as needed. Check [trading-signals docs](https://github.com/bennycode/trading-signals) for the full list.

If you need additional indicators, WebSocket integration, or a specific trading strategy, let me know!
Below are JavaScript snippets to enhance the Bybit trading bot indicator module with **order book analysis** and **support and resistance** detection, tailored for Bybit bots using the `ccxt` library for API access and `trading-signals` for indicators. These snippets analyze the Bybit order book to identify liquidity clusters and calculate support/resistance levels based on price action and volume. The code is modular, lightweight, and designed for integration with the previously provided `BybitIndicatorModule`.

### Prerequisites
- Ensure `ccxt` and `trading-signals` are installed: `npm i ccxt trading-signals`.
- Bybit API key/secret configured (as in the previous module).
- Familiarity with Bybit's order book data (bids/asks) and OHLCV data.
- The snippets assume you're extending the `BybitIndicatorModule` class from the prior response.

### 1. **Order Book Analysis**
This snippet fetches and analyzes the Bybit order book to identify liquidity clusters (areas with high bid/ask volume) and market depth, which can inform trading decisions (e.g., slippage estimation or detecting whale activity).

```javascript
// Add to indicatorModule.js (BybitIndicatorModule class)

// Fetch and analyze order book
async getOrderBookAnalysis(depth = 50) {
  try {
    const orderBook = await this.exchange.fetchOrderBook(this.symbol, depth);
    const { bids, asks } = orderBook;

    // Calculate total bid/ask volume
    const bidVolume = bids.reduce((sum, [price, volume]) => sum + volume, 0);
    const askVolume = asks.reduce((sum, [price, volume]) => sum + volume, 0);
    const bidAskRatio = bidVolume / (bidVolume + askVolume); // Ratio of buying pressure

    // Identify liquidity clusters (price levels with high volume)
    const clusterThreshold = 0.1; // Top 10% of total volume
    const significantBids = bids
      .filter(([price, volume]) => volume > bidVolume * clusterThreshold)
      .map(([price, volume]) => ({ price, volume }));
    const significantAsks = asks
      .filter(([price, volume]) => volume > askVolume * clusterThreshold)
      .map(([price, volume]) => ({ price, volume }));

    // Mid-price and spread
    const bestBid = bids[0]?.[0] || 0;
    const bestAsk = asks[0]?.[0] || 0;
    const midPrice = (bestBid + bestAsk) / 2;
    const spread = bestAsk - bestBid;

    return {
      bidVolume,
      askVolume,
      bidAskRatio, // >0.5 suggests buying pressure, <0.5 suggests selling
      significantBids, // Potential support levels
      significantAsks, // Potential resistance levels
      midPrice,
      spread,
    };
  } catch (error) {
    console.error('Error fetching order book:', error.message);
    return null;
  }
}
```

**Usage Example**:
```javascript
(async () => {
  const indicator = new BybitIndicatorModule('your-api-key', 'your-api-secret', 'BTCUSDT', '5m');
  const analysis = await indicator.getOrderBookAnalysis(50);
  if (analysis) {
    console.log('Order Book Analysis:', {
      bidAskRatio: analysis.bidAskRatio.toFixed(2),
      significantBids: analysis.significantBids,
      significantAsks: analysis.significantAsks,
      spread: analysis.spread,
      midPrice: analysis.midPrice,
    });
    // Example output: 
    // {
    //   bidAskRatio: '0.55',
    //   significantBids: [{ price: 60000, volume: 10.5 }, ...],
    //   significantAsks: [{ price: 61000, volume: 8.2 }, ...],
    //   spread: 50,
    //   midPrice: 60500
    // }
  }
})();
```

**How It Works**:
- Fetches the order book with `fetchOrderBook` (up to `depth` levels of bids/asks).
- Calculates total volume for bids and asks, and the bid/ask ratio to gauge buying/selling pressure.
- Identifies "significant" price levels (clusters) where volume exceeds 10% of total volume, indicating potential support (bids) or resistance (asks).
- Computes mid-price and spread for slippage or market tightness analysis.
- Use `significantBids` and `significantAsks` as potential support/resistance zones or to detect whale orders.

### 2. **Support and Resistance Detection**
This snippet calculates support and resistance levels based on historical price action (OHLCV data) using pivot points and volume-weighted price clusters. It complements order book analysis by identifying key levels from past price behavior.

```javascript
// Add to BybitIndicatorModule class

// Calculate support and resistance levels
async getSupportResistance(lookback = 100, clusterSize = 0.01) {
  try {
    const ohlcv = await this.fetchOHLCV(lookback);
    if (ohlcv.length < lookback) return null;

    // Extract highs, lows, and volumes
    const highs = ohlcv.map(candle => candle.high);
    const lows = ohlcv.map(candle => candle.low);
    const closes = ohlcv.map(candle => candle.close);
    const volumes = ohlcv.map(candle => candle.volume);

    // Calculate pivot points (simplified floor trader method)
    const lastCandle = ohlcv[ohlcv.length - 1];
    const pivot = (lastCandle.high + lastCandle.low + lastCandle.close) / 3;
    const support1 = 2 * pivot - lastCandle.high;
    const resistance1 = 2 * pivot - lastCandle.low;
    const support2 = pivot - (lastCandle.high - lastCandle.low);
    const resistance2 = pivot + (lastCandle.high - lastCandle.low);

    // Volume-weighted price clusters
    const priceRange = Math.max(...highs) - Math.min(...lows);
    const binSize = priceRange * clusterSize; // e.g., 1% of range
    const priceBins = {};

    ohlcv.forEach(candle => {
      const price = candle.close;
      const volume = candle.volume;
      const bin = Math.floor(price / binSize) * binSize; // Group into price bins
      priceBins[bin] = (priceBins[bin] || 0) + volume;
    });

    // Sort bins by volume to find significant levels
    const sortedBins = Object.entries(priceBins)
      .map(([price, volume]) => ({ price: parseFloat(price), volume }))
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 5); // Top 5 volume-weighted levels

    return {
      pivot,
      support1,
      resistance1,
      support2,
      resistance2,
      volumeClusters: sortedBins, // High-volume price levels (potential S/R)
    };
  } catch (error) {
    console.error('Error calculating S/R:', error.message);
    return null;
  }
}
```

**Usage Example**:
```javascript
(async () => {
  const indicator = new BybitIndicatorModule('your-api-key', 'your-api-secret', 'BTCUSDT', '5m');
  const srLevels = await indicator.getSupportResistance(100, 0.01);
  if (srLevels) {
    console.log('Support/Resistance Levels:', {
      pivot: srLevels.pivot.toFixed(2),
      support1: srLevels.support1.toFixed(2),
      resistance1: srLevels.resistance1.toFixed(2),
      support2: srLevels.support2.toFixed(2),
      resistance2: srLevels.resistance2.toFixed(2),
      volumeClusters: srLevels.volumeClusters,
    });
    // Example output:
    // {
    //   pivot: '60500.00',
    //   support1: '60000.50',
    //   resistance1: '61000.75',
    //   support2: '59500.25',
    //   resistance2: '61500.80',
    //   volumeClusters: [{ price: 60500, volume: 150.2 }, { price: 60000, volume: 120.5 }, ...]
    // }
  }
})();
```

**How It Works**:
- Uses OHLCV data to calculate pivot points (floor trader method) for primary support (S1, S2) and resistance (R1, R2) levels.
- Identifies volume-weighted price clusters by grouping prices into bins (e.g., 1% of the price range) and sorting by volume. High-volume bins indicate strong support/resistance zones.
- `lookback` controls how many candles to analyze; `clusterSize` adjusts bin granularity (smaller = more precise but noisier).
- Volume clusters complement pivot points by highlighting where trading activity is concentrated, often aligning with psychological or historical S/R levels.

### 3. **Integration with Trading Bot**
This snippet extends the `BybitTradingBot` class to use order book analysis and support/resistance levels for trading decisions.

```javascript
// bot.js (extend previous bot)
class BybitTradingBot {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.indicators = new BybitIndicatorModule(apiKey, apiSecret, symbol, timeframe);
  }

  async run() {
    const rsi = await this.indicators.getRSI(14);
    const macd = await this.indicators.getMACD(12, 26, 9);
    const orderBook = await this.indicators.getOrderBookAnalysis(50);
    const srLevels = await this.indicators.getSupportResistance(100, 0.01);

    if (!rsi || !macd || !orderBook || !srLevels) {
      console.log('Insufficient data');
      return;
    }

    const currentPrice = orderBook.midPrice;
    console.log(`Current Price: ${currentPrice}, RSI: ${rsi}, MACD:`, macd);

    // Example strategy:
    // Buy: RSI < 30, positive MACD histogram, price near support, and strong bid volume
    if (
      rsi < 30 &&
      macd.histogram > 0 &&
      Math.abs(currentPrice - srLevels.support1) < currentPrice * 0.005 && // Within 0.5% of S1
      orderBook.bidAskRatio > 0.6 // Strong buying pressure
    ) {
      console.log('Buy signal detected!');
      console.log('Support Level:', srLevels.support1, 'Bid/Ask Ratio:', orderBook.bidAskRatio);
      // Place buy order
      // await this.indicators.exchange.createMarketBuyOrder(this.indicators.symbol, amount);
    }
    // Sell: RSI > 70, negative MACD histogram, price near resistance, and strong ask volume
    else if (
      rsi > 70 &&
      macd.histogram < 0 &&
      Math.abs(currentPrice - srLevels.resistance1) < currentPrice * 0.005 && // Within 0.5% of R1
      orderBook.bidAskRatio < 0.4 // Strong selling pressure
    ) {
      console.log('Sell signal detected!');
      console.log('Resistance Level:', srLevels.resistance1, 'Bid/Ask Ratio:', orderBook.bidAskRatio);
      // Place sell order
      // await this.indicators.exchange.createMarketSellOrder(this.indicators.symbol, amount);
    }
  }
}

// Run bot every 5 minutes
const bot = new BybitTradingBot('your-api-key', 'your-api-secret');
setInterval(() => bot.run(), 60000 * 5);
```

### Notes
- **Order Book Analysis**:
  - `significantBids` and `significantAsks` from the order book can act as dynamic support/resistance levels, as they reflect real-time liquidity.
  - Use `bidAskRatio` to gauge market sentiment (e.g., >0.5 for bullish, <0.5 for bearish).
  - Adjust `depth` to balance detail vs. API rate limits (Bybit allows up to 200 for spot, 500 for futures).
- **Support/Resistance**:
  - Pivot points are simple but effective for short-term trading. Combine with volume clusters for confirmation.
  - `clusterSize` (e.g., 0.01 for 1% bins) can be tuned based on the asset’s volatility (smaller for stable coins like USDT pairs, larger for volatile ones like BTC).
  - Volume clusters highlight where traders have historically accumulated, often aligning with psychological levels (e.g., 60,000 for BTCUSDT).
- **Performance**:
  - Cache OHLCV data locally to reduce API calls (Bybit’s rate limits are strict: ~120 requests/min for public endpoints).
  - For real-time order book updates, use Bybit’s WebSocket API (`ccxt` supports WebSocket streams) instead of polling `fetchOrderBook`.
- **Strategy Tips**:
  - Combine indicators (RSI, MACD), order book (bid/ask ratio), and S/R levels for robust signals.
  - Example: Buy near `support1` with high `bidAskRatio` and oversold RSI; sell near `resistance1` with low `bidAskRatio` and overbought RSI.
  - Test with Bybit’s testnet (`testnet: true` in `ccxt.bybit` constructor) to avoid risking real funds.
- **Security**: Secure API keys in environment variables (e.g., `process.env.BYBIT_API_KEY`).
- **Extensions**: Add more indicators (e.g., Bollinger Bands, ATR) or advanced S/R methods (e.g., Fibonacci retracement) from `trading-signals`.

If you need WebSocket integration, additional indicators, or a specific strategy (e.g., scalping near S/R levels), let me know!
Below are 10 additional technical indicators commonly used in trading, implemented as snippets for the `BybitIndicatorModule` class to enhance your Bybit trading bot. These indicators are calculated using the `trading-signals` library, which provides high-precision calculations suitable for crypto trading on Bybit. Each snippet includes a brief description, implementation, and usage example, designed to integrate seamlessly with the previously provided module for order book analysis and support/resistance detection. The indicators cover trend, momentum, volatility, and volume-based metrics, tailored for Bybit's OHLCV data.

### Prerequisites
- Ensure `ccxt` and `trading-signals` are installed: `npm i ccxt trading-signals`.
- Bybit API key/secret configured in `BybitIndicatorModule` (as in prior snippets).
- The snippets extend the `BybitIndicatorModule` class, which includes the `fetchOHLCV` method for retrieving OHLCV data.
- Each indicator uses historical OHLCV data and supports batch processing; for real-time, adapt to WebSocket streams as shown in prior snippets.

### Updated `BybitIndicatorModule` with New Indicators
Add these methods to the `indicatorModule.js` file. Each method fetches OHLCV data, computes the indicator, and returns the latest value(s) for use in trading strategies.

```javascript
// indicatorModule.js (extend existing BybitIndicatorModule class)
const { 
  BollingerBands, ATR, StochasticRSI, ADX, CCI, 
  VWAP, OBV, MFI, WilliamsR, IchimokuCloud 
} = require('trading-signals');

class BybitIndicatorModule {
  // ... existing methods (fetchOHLCV, getSMA, getEMA, getRSI, getMACD, etc.)

  // 1. Bollinger Bands (Volatility)
  async getBollingerBands(period = 20, stdDev = 2) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const bb = new BollingerBands(period, stdDev);
      const closes = ohlcv.map(candle => candle.close);
      closes.forEach(price => bb.add(price));
      const result = bb.getResult();
      return {
        upper: result.upper,
        middle: result.middle, // SMA
        lower: result.lower,
        width: (result.upper - result.lower) / result.middle, // Band width as % of middle
      };
    } catch (error) {
      console.error('Error calculating Bollinger Bands:', error.message);
      return null;
    }
  }

  // 2. Average True Range (ATR, Volatility)
  async getATR(period = 14) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const atr = new ATR(period);
      ohlcv.forEach(candle => atr.add(candle.high, candle.low, candle.close));
      return atr.getResult();
    } catch (error) {
      console.error('Error calculating ATR:', error.message);
      return null;
    }
  }

  // 3. Stochastic RSI (Momentum)
  async getStochasticRSI(rsiPeriod = 14, kPeriod = 14, dPeriod = 3, smooth = 3) {
    try {
      const ohlcv = await this.fetchOHLCV(rsiPeriod + kPeriod + dPeriod + 10);
      if (ohlcv.length < rsiPeriod + kPeriod + dPeriod) return null;

      const stochRSI = new StochasticRSI(rsiPeriod, kPeriod, dPeriod, smooth);
      const closes = ohlcv.map(candle => candle.close);
      closes.forEach(price => stochRSI.add(price));
      const result = stochRSI.getResult();
      return {
        k: result.k, // %K line
        d: result.d, // %D line
      };
    } catch (error) {
      console.error('Error calculating Stochastic RSI:', error.message);
      return null;
    }
  }

  // 4. Average Directional Index (ADX, Trend Strength)
  async getADX(period = 14) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const adx = new ADX(period);
      ohlcv.forEach(candle => adx.add(candle.high, candle.low, candle.close));
      return adx.getResult();
    } catch (error) {
      console.error('Error calculating ADX:', error.message);
      return null;
    }
  }

  // 5. Commodity Channel Index (CCI, Momentum)
  async getCCI(period = 20) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const cci = new CCI(period);
      ohlcv.forEach(candle => cci.add(candle.high, candle.low, candle.close));
      return cci.getResult();
    } catch (error) {
      console.error('Error calculating CCI:', error.message);
      return null;
    }
  }

  // 6. Volume-Weighted Average Price (VWAP, Volume/Price)
  async getVWAP(period = 14) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const vwap = new VWAP(period);
      ohlcv.forEach(candle => vwap.add(candle.close, candle.volume));
      return vwap.getResult();
    } catch (error) {
      console.error('Error calculating VWAP:', error.message);
      return null;
    }
  }

  // 7. On-Balance Volume (OBV, Volume)
  async getOBV() {
    try {
      const ohlcv = await this.fetchOHLCV(100); // No fixed period, uses full history
      if (ohlcv.length < 2) return null;

      const obv = new OBV();
      ohlcv.forEach(candle => obv.add(candle.close, candle.volume));
      return obv.getResult();
    } catch (error) {
      console.error('Error calculating OBV:', error.message);
      return null;
    }
  }

  // 8. Money Flow Index (MFI, Momentum/Volume)
  async getMFI(period = 14) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const mfi = new MFI(period);
      ohlcv.forEach(candle => mfi.add(candle.high, candle.low, candle.close, candle.volume));
      return mfi.getResult();
    } catch (error) {
      console.error('Error calculating MFI:', error.message);
      return null;
    }
  }

  // 9. Williams %R (Momentum)
  async getWilliamsR(period = 14) {
    try {
      const ohlcv = await this.fetchOHLCV(period + 10);
      if (ohlcv.length < period) return null;

      const williamsR = new WilliamsR(period);
      ohlcv.forEach(candle => williamsR.add(candle.high, candle.low, candle.close));
      return williamsR.getResult();
    } catch (error) {
      console.error('Error calculating Williams %R:', error.message);
      return null;
    }
  }

  // 10. Ichimoku Cloud (Trend/Momentum)
  async getIchimokuCloud(tenkanPeriod = 9, kijunPeriod = 26, senkouBPeriod = 52) {
    try {
      const ohlcv = await this.fetchOHLCV(senkouBPeriod + kijunPeriod + 10);
      if (ohlcv.length < senkouBPeriod + kijunPeriod) return null;

      const ichimoku = new IchimokuCloud(tenkanPeriod, kijunPeriod, senkouBPeriod);
      ohlcv.forEach(candle => ichimoku.add(candle.high, candle.low));
      const result = ichimoku.getResult();
      return {
        tenkanSen: result.tenkanSen, // Conversion Line
        kijunSen: result.kijunSen, // Base Line
        senkouSpanA: result.senkouSpanA, // Leading Span A
        senkouSpanB: result.senkouSpanB, // Leading Span B
        chikouSpan: result.chikouSpan, // Lagging Span
      };
    } catch (error) {
      console.error('Error calculating Ichimoku Cloud:', error.message);
      return null;
    }
  }
}

module.exports = BybitIndicatorModule;
```

### Indicator Descriptions and Usage Examples
Each indicator is implemented with error handling and returns the latest value(s). Below are brief descriptions, trading use cases, and usage examples.

#### 1. **Bollinger Bands (Volatility)**
- **Description**: Measures volatility with a middle band (SMA) and upper/lower bands (±stdDev * SMA). Useful for identifying overbought/oversold conditions or breakouts.
- **Trading Use**: Buy when price touches lower band and RSI is oversold; sell at upper band with overbought RSI.
- **Example**:
  ```javascript
  (async () => {
    const indicator = new BybitIndicatorModule('your-api-key', 'your-api-secret', 'BTCUSDT', '5m');
    const bb = await indicator.getBollingerBands(20, 2);
    if (bb) {
      console.log('Bollinger Bands:', {
        upper: bb.upper.toFixed(2),
        middle: bb.middle.toFixed(2),
        lower: bb.lower.toFixed(2),
        width: (bb.width * 100).toFixed(2) + '%',
      });
      // Example: { upper: '61000.50', middle: '60500.00', lower: '60000.50', width: '1.65%' }
    }
  })();
  ```

#### 2. **Average True Range (ATR, Volatility)**
- **Description**: Measures average price range to gauge volatility. Used for stop-loss placement or position sizing.
- **Trading Use**: Set stop-loss at 2x ATR below entry price for buys; scale position size inversely with ATR.
- **Example**:
  ```javascript
  (async () => {
    const atr = await indicator.getATR(14);
    if (atr) console.log(`ATR(14): ${atr.toFixed(2)}`); // e.g., '500.25' (volatility in USDT)
  })();
  ```

#### 3. **Stochastic RSI (Momentum)**
- **Description**: Combines Stochastic oscillator with RSI to identify overbought/oversold conditions with smoother signals.
- **Trading Use**: Buy when %K crosses above %D below 20; sell when %K crosses below %D above 80.
- **Example**:
  ```javascript
  (async () => {
    const stochRSI = await indicator.getStochasticRSI(14, 14, 3, 3);
    if (stochRSI) console.log('Stochastic RSI:', { k: stochRSI.k.toFixed(2), d: stochRSI.d.toFixed(2) });
    // Example: { k: '25.40', d: '22.10' }
  })();
  ```

#### 4. **Average Directional Index (ADX, Trend Strength)**
- **Description**: Measures trend strength (0-100). ADX > 25 indicates a strong trend; < 20 suggests ranging.
- **Trading Use**: Trade with trend (e.g., EMA crossover) only if ADX > 25; avoid in low ADX markets.
- **Example**:
  ```javascript
  (async () => {
    const adx = await indicator.getADX(14);
    if (adx) console.log(`ADX(14): ${adx.toFixed(2)}`); // e.g., '30.50' (strong trend)
  })();
  ```

#### 5. **Commodity Channel Index (CCI, Momentum)**
- **Description**: Measures deviation from average price. CCI > 100 is overbought; < -100 is oversold.
- **Trading Use**: Buy on CCI crossing above -100; sell on crossing below 100.
- **Example**:
  ```javascript
  (async () => {
    const cci = await indicator.getCCI(20);
    if (cci) console.log(`CCI(20): ${cci.toFixed(2)}`); // e.g., '-120.75' (oversold)
  })();
  ```

#### 6. **Volume-Weighted Average Price (VWAP, Volume/Price)**
- **Description**: Average price weighted by volume, used as a fair value benchmark.
- **Trading Use**: Buy when price is below VWAP and rising; sell when above and falling.
- **Example**:
  ```javascript
  (async () => {
    const vwap = await indicator.getVWAP(14);
    if (vwap) console.log(`VWAP(14): ${vwap.toFixed(2)}`); // e.g., '60500.30'
  })();
  ```

#### 7. **On-Balance Volume (OBV, Volume)**
- **Description**: Tracks cumulative volume to confirm price trends. Rising OBV confirms uptrends; falling OBV confirms downtrends.
- **Trading Use**: Buy on OBV uptrend with price breakout; sell on divergence.
- **Example**:
  ```javascript
  (async () => {
    const obv = await indicator.getOBV();
    if (obv) console.log(`OBV: ${obv.toFixed(2)}`); // e.g., '1500000.00'
  })();
  ```

#### 8. **Money Flow Index (MFI, Momentum/Volume)**
- **Description**: RSI-like indicator incorporating volume. MFI > 80 is overbought; < 20 is oversold.
- **Trading Use**: Buy on MFI < 20 with price near support; sell on MFI > 80 near resistance.
- **Example**:
  ```javascript
  (async () => {
    const mfi = await indicator.getMFI(14);
    if (mfi) console.log(`MFI(14): ${mfi.toFixed(2)}`); // e.g., '65.20'
  })();
  ```

#### 9. **Williams %R (Momentum)**
- **Description**: Measures overbought/oversold levels (-100 to 0). %R > -20 is overbought; < -80 is oversold.
- **Trading Use**: Buy when %R crosses above -80; sell when below -20.
- **Example**:
  ```javascript
  (async () => {
    const williamsR = await indicator.getWilliamsR(14);
    if (williamsR) console.log(`Williams %R(14): ${williamsR.toFixed(2)}`); // e.g., '-75.50'
  })();
  ```

#### 10. **Ichimoku Cloud (Trend/Momentum)**
- **Description**: Comprehensive indicator with multiple lines (Tenkan-sen, Kijun-sen, Senkou Span A/B, Chikou Span) to identify trend, momentum, and support/resistance.
- **Trading Use**: Buy when price is above cloud (Senkou Span A > B) and Tenkan-sen crosses above Kijun-sen; sell on opposite signals.
- **Example**:
  ```javascript
  (async () => {
    const ichimoku = await indicator.getIchimokuCloud(9, 26, 52);
    if (ichimoku) {
      console.log('Ichimoku Cloud:', {
        tenkanSen: ichimoku.tenkanSen.toFixed(2),
        kijunSen: ichimoku.kijunSen.toFixed(2),
        senkouSpanA: ichimoku.senkouSpanA.toFixed(2),
        senkouSpanB: ichimoku.senkouSpanB.toFixed(2),
        chikouSpan: ichimoku.chikouSpan.toFixed(2),
      });
      // Example: { tenkanSen: '60500.00', kijunSen: '60450.75', ... }
    }
  })();
  ```

### Integration with Trading Bot
Here’s an updated `BybitTradingBot` to incorporate these indicators into a trading strategy, combining them with prior indicators (RSI, MACD) and order book/support-resistance analysis.

```javascript
// bot.js (extend existing BybitTradingBot class)
class BybitTradingBot {
  constructor(apiKey, apiSecret, symbol = 'BTCUSDT', timeframe = '5m') {
    this.indicators = new BybitIndicatorModule(apiKey, apiSecret, symbol, timeframe);
  }

  async run() {
    const rsi = await this.indicators.getRSI(14);
    const macd = await this.indicators.getMACD(12, 26, 9);
    const orderBook = await this.indicators.getOrderBookAnalysis(50);
    const srLevels = await this.indicators.getSupportResistance(100, 0.01);
    const bb = await this.indicators.getBollingerBands(20, 2);
    const atr = await this.indicators.getATR(14);
    const stochRSI = await this.indicators.getStochasticRSI(14, 14, 3, 3);
    const adx = await this.indicators.getADX(14);
    const cci = await this.indicators.getCCI(20);
    const vwap = await this.indicators.getVWAP(14);
    const mfi = await this.indicators.getMFI(14);
    const williamsR = await this.indicators.getWilliamsR(14);

    if (!rsi || !macd || !orderBook || !srLevels || !bb || !atr || !stochRSI || !adx || !cci || !vwap || !mfi || !williamsR) {
      console.log('Insufficient data');
      return;
    }

    const currentPrice = orderBook.midPrice;
    console.log(`Price: ${currentPrice}, RSI: ${rsi}, MACD:`, macd, `ADX: ${adx}`);

    // Example strategy: Buy on multiple confirmations
    if (
      rsi < 30 && // Oversold
      macd.histogram > 0 && // Bullish momentum
      stochRSI.k > stochRSI.d && stochRSI.k < 20 && // StochRSI bullish
      adx > 25 && // Strong trend
      cci < -100 && // Oversold CCI
      mfi < 20 && // Oversold MFI
      williamsR < -80 && // Oversold Williams %R
      currentPrice < vwap && // Below fair value
      Math.abs(currentPrice - srLevels.support1) < currentPrice * 0.005 && // Near support
      currentPrice < bb.lower && // Below lower Bollinger Band
      orderBook.bidAskRatio > 0.6 // Strong buying pressure
    ) {
      console.log('Buy signal detected!');
      console.log(`Support: ${srLevels.support1}, ATR: ${atr}, VWAP: ${vwap}`);
      // Place buy order
      // const amount = 0.001; // Example: 0.001 BTC
      // await this.indicators.exchange.createMarketBuyOrder(this.indicators.symbol, amount);
    }
    // Sell on opposite conditions
    else if (
      rsi > 70 &&
      macd.histogram < 0 &&
      stochRSI.k < stochRSI.d && stochRSI.k > 80 &&
      adx > 25 &&
      cci > 100 &&
      mfi > 80 &&
      williamsR > -20 &&
      currentPrice > vwap &&
      Math.abs(currentPrice - srLevels.resistance1) < currentPrice * 0.005 &&
      currentPrice > bb.upper &&
      orderBook.bidAskRatio < 0.4
    ) {
      console.log('Sell signal detected!');
      console.log(`Resistance: ${srLevels.resistance1}, ATR: ${atr}, VWAP: ${vwap}`);
      // Place sell order
      // await this.indicators.exchange.createMarketSellOrder(this.indicators.symbol, amount);
    }
  }
}

// Run bot every 5 minutes
const bot = new BybitTradingBot('your-api-key', 'your-api-secret');
setInterval(() => bot.run(), 60000 * 5);
```

### Notes
- **Indicator Selection**: The strategy uses multiple indicators for confirmation to reduce false signals. Adjust thresholds (e.g., RSI < 30, ADX > 25) based on backtesting.
- **Performance**: Fetching OHLCV for multiple indicators can hit Bybit’s API rate limits (~120 requests/min for public endpoints). Cache data or use WebSocket streams for real-time updates.
- **WebSocket Integration**: For real-time order book and price updates, use Bybit’s WebSocket API via `ccxt` (e.g., `exchange.watchOrderBook` or `watchOHLCV`).
- **Risk Management**: Use ATR for dynamic stop-loss (e.g., 2x ATR below entry) and position sizing. Avoid over-leveraging on Bybit futures.
- **Testing**: Backtest on Bybit’s testnet (`testnet: true` in `ccxt.bybit`) with historical data. Use `fetchOHLCV` with larger `limit` for backtesting.
- **Security**: Store API keys in environment variables (e.g., `process.env.BYBIT_API_KEY`).
- **Customization**: Tune periods (e.g., Bollinger Bands `stdDev`, Ichimoku periods) based on timeframe and asset volatility. Add Ichimoku Cloud signals (e.g., price above cloud for bullish) to the bot strategy.

If you need WebSocket streaming, additional indicators (e.g., Fibonacci retracement, Keltner Channels), or a specific strategy (e.g., scalping near Bollinger Bands), let me know!
