// Aggregate lower timeframe candles into a higher timeframe N-multiple
// incoming candle shape: {t, o,h,l,c,v} in ms epoch
class CandleAggregator {
  constructor(factor) {
    if (!Number.isInteger(factor) || factor <= 1) throw new Error("factor must be > 1");
    this.factor = factor;
    this._count = 0;
    this._work = null;
  }
  next(c) {
    if (!this._work) {
      this._work = { t: c.t, o: c.o, h: c.h, l: c.l, c: c.c, v: c.v };
      this._count = 1;
      return undefined;
    }
    this._work.h = Math.max(this._work.h, c.h);
    this._work.l = Math.min(this._work.l, c.l);
    this._work.c = c.c;
    this._work.v += c.v;
    this._count++;
    if (this._count === this.factor) {
      const out = this._work;
      this._work = null;
      this._count = 0;
      return out;
    }
    return undefined;
  }
}
export default CandleAggregator;