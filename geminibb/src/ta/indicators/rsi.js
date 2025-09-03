// Wilder's RSI
class RSI {
  constructor(period = 14) {
    if (period <= 1) throw new Error("RSI period must be > 1");
    this.n = period;
    this.prev = undefined;
    this.gain = undefined;
    this.loss = undefined;
    this.value = undefined;
    this._initCount = 0;
    this._sumGain = 0;
    this._sumLoss = 0;
  }
  next(close) {
    if (this.prev === undefined) { this.prev = close; return undefined; }
    const change = close - this.prev;
    this.prev = close;
    const up = Math.max(0, change);
    const down = Math.max(0, -change);
    if (this.gain === undefined) {
      this._sumGain += up;
      this._sumLoss += down;
      this._initCount++;
      if (this._initCount === this.n) {
        this.gain = this._sumGain / this.n;
        this.loss = this._sumLoss / this.n;
      }
      return undefined;
    }
    // Wilder smoothing
    this.gain = (this.gain * (this.n - 1) + up) / this.n;
    this.loss = (this.loss * (this.n - 1) + down) / this.n;
    const rs = this.loss === 0 ? 100 : this.gain / this.loss;
    this.value = 100 - 100 / (1 + rs);
    return this.value;
  }
}
export default RSI;