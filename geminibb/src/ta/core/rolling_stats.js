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
  filled() { return this.buf.filled(); }
}
export default RollingStats;