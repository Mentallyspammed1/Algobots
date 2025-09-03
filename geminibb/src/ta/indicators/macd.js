import EMA from "./ema.js";
// Returns {macd, signal, hist} once both EMAs and signal are ready
class MACD {
  constructor(fast = 12, slow = 26, signal = 9) {
    if (fast >= slow) throw new Error("MACD fast must be < slow");
    this.fast = new EMA(fast);
    this.slow = new EMA(slow);
    this.signalEma = new EMA(signal);
    this.value = undefined;
  }

  /**
   * Resets all internal EMA indicators for MACD, Signal, and Histogram.
   */
  reset() {
    this.fast.reset();
    this.slow.reset();
    this.signalEma.reset();
    this.value = undefined;
  }
  next(x) {
    const f = this.fast.next(x);
    const s = this.slow.next(x);
    if (this.fast.value === undefined || this.slow.value === undefined) return undefined;
    const macd = this.fast.value - this.slow.value;
    const sig = this.signalEma.next(macd);
    if (this.signalEma.value === undefined) return undefined;
    const hist = macd - this.signalEma.value;
    return this.value = { macd, signal: this.signalEma.value, hist };
  }
  /**
   * Indicates if the MACD indicator has enough data to produce all three values (MACD, Signal, Hist).
   * @returns {boolean}
   */
  get isReady() {
    return this.value !== undefined;
  }
}
export default MACD;