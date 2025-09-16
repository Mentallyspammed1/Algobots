import RollingStats from "../core/rolling_stats.js";
class BollingerBands {
  constructor(period = 20, k = 2) {
    this.stats = new RollingStats(period);
    this.k = k;
    this.value = undefined;
  }
  next(x) {
    const s = this.stats.next(x);
    if (!s) return undefined;
    const mid = s.mean;
    const upper = mid + this.k * s.std;
    const lower = mid - this.k * s.std;
    return this.value = { mid, upper, lower, std: s.std };
  }
  /**
   * Indicates if the Bollinger Bands indicator has enough data to produce values.
   * @returns {boolean}
   */
  get isReady() {
    return this.stats.filled();
  }
}
export default BollingerBands;