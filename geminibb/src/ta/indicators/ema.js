class EMA {
  constructor(period) {
    if (!Number.isInteger(period) || period <= 0) throw new Error("EMA period must be > 0");
    this.n = period;
    this.k = 2 / (period + 1);
    this.value = undefined;
    this._seedCount = 0;
    this._seedSum = 0;

    // Optimization for EMA(1)
    if (period === 1) {
      this.value = undefined; // Will be set on first next call
      this._seedCount = period; // Effectively skips seeding
    }
  }
  next(x) {
    // Special handling for EMA(1)
    if (this.n === 1) {
      return this.value = x;
    }

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
  /**
   * Indicates if the EMA has completed its seeding period and is producing values.
   * @returns {boolean}
   */
  get isReady() {
    return this.value !== undefined;
  }
}
export default EMA;