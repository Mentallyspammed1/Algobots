import RingBuffer from "./ring_buffer.js";

// Rolling window mean/std with O(1) updates (keeps sum and sumSq)
class RollingStats {
  constructor(period) {
    if (!Number.isInteger(period) || period <= 1) throw new Error("period must be > 1");
    this.n = period;
    this.buf = new RingBuffer(period);
    this.sum = 0;
    this.sumSq = 0;
  }
  
  /**
   * Resets the rolling statistics, clearing all sums and the internal buffer.
   */
  reset() {
    this.buf = new RingBuffer(this.n); // Re-initialize buffer
    this.sum = 0;
    this.sumSq = 0;
  }
  next(x) {
    const dropped = this.buf.push(x);
    this.sum += x;
    this.sumSq += x * x;
    if (dropped !== undefined) {
      this.sum -= dropped;
      this.sumSq -= dropped * dropped;
    }
    if (!this.buf.filled()) return undefined;
    const mean = this.sum / this.n;
    const varPop = Math.max(0, this.sumSq / this.n - mean * mean);
    const std = Math.sqrt(varPop);
    return { mean, std };
  }
  /**
   * Returns the current population variance if the buffer is filled, otherwise undefined.
   * @returns {number|undefined}
   */
  get variance() {
    if (!this.buf.filled()) return undefined;
    const mean = this.sum / this.n;
    return Math.max(0, this.sumSq / this.n - mean * mean);
  }

  /**
   * Returns the current mean if the buffer is filled, otherwise undefined.
   * @returns {number|undefined}
   */
  get mean() {
    if (!this.buf.filled()) return undefined;
    return this.sum / this.n;
  }

  /**
   * Returns the current standard deviation if the buffer is filled, otherwise undefined.
   * @returns {number|undefined}
   */
  get std() {
    if (!this.buf.filled()) return undefined;
    return Math.sqrt(this.variance);
  }

  filled() { return this.buf.filled(); }
}
export default RollingStats;