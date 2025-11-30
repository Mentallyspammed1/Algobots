class MultiSymbolOHLC {
  constructor(symbols = [], maxCandles = 100) {
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
module.exports = { MultiSymbolOHLC };
