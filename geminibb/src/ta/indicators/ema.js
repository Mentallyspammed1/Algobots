class EMA {
  constructor(period) {
    if (period <= 1) throw new Error("EMA period must be > 1");
    this.n = period;
    this.k = 2 / (period + 1);
    this.value = undefined;
    this._seedCount = 0;
    this._seedSum = 0;
  }
  next(x) {
    if (this.value === undefined) {
      // seed with SMA over first n points
      this._seedSum += x;
      this._seedCount++;
      if (this._seedCount === this.n) {
        this.value = this._seedSum / this.n;
      }
      return undefined;
    }
    this.value = x * this.k + this.value * (1 - this.k);
    return this.value;
  }
}
export default EMA;