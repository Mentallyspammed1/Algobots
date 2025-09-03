// ATR (Wilder). Expects candles: {h, l, c} or {high, low, close}
class ATR {
  constructor(period = 14) {
    if (period <= 1) throw new Error("ATR period must be > 1");
    this.n = period;
    this.prevClose = undefined;
    this.atr = undefined;
    this._initCount = 0;
    this._sumTR = 0;
  }
  next(candle) {
    const h = candle.h ?? candle.high;
    const l = candle.l ?? candle.low;
    const c = candle.c ?? candle.close;
    const prevC = this.prevClose ?? c;
    const tr = Math.max(h - l, Math.abs(h - prevC), Math.abs(l - prevC));
    this.prevClose = c;
    if (this.atr === undefined) {
      this._sumTR += tr;
      this._initCount++;
      if (this._initCount === this.n) this.atr = this._sumTR / this.n;
      return undefined;
    }
    this.atr = (this.atr * (this.n - 1) + tr) / this.n;
    return this.atr;
  }
  get value() { return this.atr; }
}
export default ATR;