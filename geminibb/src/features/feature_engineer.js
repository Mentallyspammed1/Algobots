import { RSI, ATR, MACD, BollingerBands, VWAP } from "../ta/index.js";

class FeatureEngineer {
  constructor({ rsiLen = 14, atrLen = 14, macd = [12,26,9], bb = [20,2] } = {}) {
    this.rsi = new RSI(rsiLen);
    this.atr = new ATR(atrLen);
    this.macd = new MACD(...macd);
    this.bb = new BollingerBands(...bb);
    this.vwap = new VWAP();
    this.last = null;
  }

  // Candle: {t,o,h,l,c,v}
  next(c) {
    const rsi = this.rsi.next(c.c);
    const atr = this.atr.next(c);
    const macd = this.macd.next(c.c);
    const bb = this.bb.next(c.c);
    const vwap = this.vwap.next(c);
    const out = {
      t: c.t,
      close: c.c,
      rsi,
      atr,
      macd, // {macd,signal,hist} or undefined
      bb,   // {mid,upper,lower,std} or undefined
      vwap
    };
    this.last = out;
    return out;
  }

  resetSessionVWAP() { this.vwap.reset(); }
}

export default FeatureEngineer;