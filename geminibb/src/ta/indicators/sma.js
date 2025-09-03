import RingBuffer from "../core/ring_buffer.js";
class SMA {
  constructor(period) {
    if (period <= 0) throw new Error("SMA period must be > 0");
    this.n = period;
    this.buf = new RingBuffer(period);
    this.sum = 0;
    this.value = undefined;
  }
  next(x) {
    const dropped = this.buf.push(x);
    this.sum += x;
    if (dropped !== undefined) this.sum -= dropped;
    if (!this.buf.filled()) return this.value = undefined;
    return this.value = this.sum / this.n;
  }
}
export default SMA;