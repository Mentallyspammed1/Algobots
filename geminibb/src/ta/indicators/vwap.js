// Session VWAP; call reset() at new session if needed
class VWAP {
  constructor() { this.reset(); }
  reset() { this.pv = 0; this.vol = 0; this.value = undefined; }
  // candle: {h,l,c,v} or {high,low,close,volume}
  next(c) {
    const h = c.h ?? c.high, l = c.l ?? c.low, close = c.c ?? c.close;
    const v = c.v ?? c.volume ?? 0;
    const typical = (h + l + close) / 3;
    this.pv += typical * v;
    this.vol += v;
    if (this.vol === 0) return this.value = undefined;
    return this.value = this.pv / this.vol;
  }
}
export default VWAP;