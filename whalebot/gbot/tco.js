const WebSocket = require('ws');
const config = require('./config');
const { analyzeSignal } = require('./services/gemini');
const { sendSMS, formatSMS } = require('./services/alert');
const {
  sma, ema, atr, superTrend, ehlersCyberCycle,
  calculateRSI, isImpulsiveCandle
} = require('./indicators');

class MultiSymbolOHLC {
  constructor(symbols = [config.SYMBOL], maxCandles = 100) {
    this.buffers = new Map();
    this.lastUpdateTimes = new Map();
    symbols.forEach(sym => {
      this.buffers.set(sym, []);
      this.lastUpdateTimes.set(sym, 0);
    });
    this.maxCandles = maxCandles;
  }

  updateCandle(symbol, candle) {
    const buffer = this.buffers.get(symbol);
    const lastCandle = buffer.length > 0 ? buffer[buffer.length - 1] : null;

    if (lastCandle && lastCandle.timestamp === candle.timestamp) {
      buffer[buffer.length - 1] = candle;
    } else if (candle.timestamp > this.lastUpdateTimes.get(symbol)) {
      if (buffer.length >= this.maxCandles) {
        buffer.shift();
      }
      buffer.push(candle);
      this.lastUpdateTimes.set(symbol, candle.timestamp);
    }
  }

  getCandles(symbol) {
    return this.buffers.get(symbol);
  }

  getLatestCandle(symbol) {
    const buffer = this.buffers.get(symbol);
    return buffer.length > 0 ? buffer[buffer.length - 1] : null;
  }
}

class ScalpTrader {
  static lastAlert = 0;
  static ws = null;
  static multiOHLC = null;

  static async initialize() {
    console.log('Initializing ScalpTrader...');
    this.multiOHLC = new MultiSymbolOHLC([config.SYMBOL]);
    await this.connectWebSocket();
    console.log('ScalpTrader initialized.');
  }

  static async connectWebSocket() {
    if (ScalpTrader.ws && ScalpTrader.ws.readyState === WebSocket.OPEN) {
      return;
    }
    console.log('Connecting to Bybit WebSocket...');
    ScalpTrader.ws = new WebSocket('wss://stream.bybit.com/v5/public/spot');

    ScalpTrader.ws.on('open', () => {
      console.log('WebSocket connected.');
      const subscribeMsg = {
        op: 'subscribe',
        args: [`kline.${config.TIMEFRAME}.${config.SYMBOL}`]
      };
      ScalpTrader.ws.send(JSON.stringify(subscribeMsg));
      console.log(`Subscribed to kline.${config.TIMEFRAME}.${config.SYMBOL}`);
    });

    ScalpTrader.ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data);
        if (msg.topic && msg.topic.startsWith('kline.')) {
          const klineData = msg.data[0];
          const candle = {
            timestamp: parseInt(klineData.start),
            open: parseFloat(klineData.open),
            high: parseFloat(klineData.high),
            low: parseFloat(klineData.low),
            close: parseFloat(klineData.close),
            volume: parseFloat(klineData.volume),
          };
          ScalpTrader.multiOHLC.updateCandle(config.SYMBOL, candle);
        }
      } catch (error) {
        console.error('Error processing WebSocket message:', error);
      }
    });

    ScalpTrader.ws.on('ping', () => {
      ScalpTrader.ws.pong();
    });

    ScalpTrader.ws.on('close', () => {
      console.log('WebSocket disconnected. Reconnecting in 5 seconds...');
      setTimeout(ScalpTrader.connectWebSocket, 5000);
    });

    ScalpTrader.ws.on('error', (err) => {
      console.error('WebSocket error:', err.message);
      ScalpTrader.ws.close();
    });
  }

  static async run() {
    await ScalpTrader.initialize();
    console.log(`\nULTIMATE SCALP TRADER PRO vFINAL\nWatching ${config.SYMBOL} ${config.TIMEFRAME}m...\n`);

    setInterval(ScalpTrader.checkSignals, config.CHECK_INTERVAL);
  }

  static async checkSignals() {
    const candles = ScalpTrader.multiOHLC.getCandles(config.SYMBOL);
    if (candles.length < 50) { // Ensure enough data for indicators
      return;
    }

    try {
      const close = candles.map(c => c.close);
      const high = candles.map(c => c.high);
      const low = candles.map(c => c.low);
      const volume = candles.map(c => c.volume);
      const price = close[close.length - 1];
      const last = ScalpTrader.multiOHLC.getLatestCandle(config.SYMBOL);

      if (!last) return;

      const trendUp = ema(close, 40) >= ema(close, 40);
      const st = superTrend(candles);
      const ehlers = ehlersCyberCycle(close);
      const rsiVal = calculateRSI(close);
      const avgRange = sma(high.map((h, i) => h - low[i]), 20);
      const volSpike = volume[volume.length - 1] > sma(volume, 10) * 1.3;
      const { bullish: impBull, bearish: impBear } = isImpulsiveCandle(last, avgRange);

      const confluence = [
        trendUp, st.trend === 1, ehlers.bullish,
        rsiVal > 55, volSpike, impBull
      ].filter(Boolean).length;

      const scalpBuy = confluence >= config.MIN_CONFIDENCE;
      const scalpSell = confluence <= 1 && !trendUp && rsiVal < 45 && impBear;

      if ((scalpBuy || scalpSell) && Date.now() - ScalpTrader.lastAlert > config.COOLDOWN) {
        const direction = scalpBuy ? "LONG" : "SHORT";

        const analysis = await analyzeSignal({
          symbol: config.SYMBOL,
          timeframe: config.TIMEFRAME,
          price: price.toFixed(2),
          supertrend: st.trend === 1 ? "Bullish" : "Bearish",
          ehlers: ehlers.bullish ? "Bullish" : "Bearish",
          rsi: rsiVal.toFixed(1),
          volSpike: volSpike ? "Yes" : "No",
          impulsive: scalpBuy ? "Strong Bullish" : "Strong Bearish",
          confluence,
          direction
        });

        const sms = formatSMS({ ...analysis, direction });
        sendSMS(sms);
        console.log(`\nSIGNAL DETECTED (${confluence}/${config.MIN_CONFIDENCE}+)\nSymbol: ${config.SYMBOL} ${config.TIMEFRAME}m\nDirection: ${direction}\n${sms}\n`);

        ScalpTrader.lastAlert = Date.now();
      }
    } catch (err) {
      console.error("Error in checkSignals:", err.message);
    }
  }
}

ScalpTrader.run();
