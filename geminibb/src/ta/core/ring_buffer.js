// Simple fixed-size ring buffer, stores numbers
class RingBuffer {
  constructor(size) {
    if (!Number.isInteger(size) || size <= 0) throw new Error("RingBuffer size must be > 0");
    this.size = size;
    this.buf = new Float64Array(size);
    this.count = 0;
    this.idx = 0;
  }
  push(x) {
    const old = this.buf[this.idx];
    this.buf[this.idx] = x;
    this.idx = (this.idx + 1) % this.size;
    if (this.count < this.size) this.count++;
    return this.count === this.size ? old : undefined;
  }
  filled() { return this.count === this.size; }
  values() {
    // returns array in time order (oldest..newest)
    const out = new Array(this.count);
    const start = (this.idx + this.size - this.count) % this.size;
    for (let i = 0; i < this.count; i++) out[i] = this.buf[(start + i) % this.size];
    return out;
  }
}
export default RingBuffer;