// Simple fixed-size ring buffer, stores numbers
class RingBuffer {
  /**
   * Creates an instance of RingBuffer.
   * @param {number} size - The maximum number of elements the buffer can hold.
   * @param {boolean} [useFloat32=false] - If true, uses Float32Array for internal storage, otherwise Float64Array.
   */
  constructor(size, useFloat32 = false) {
    if (!Number.isInteger(size) || size <= 0) throw new Error("RingBuffer size must be > 0");
    this.size = size;
    // Use Float32Array for potentially lower memory footprint if precision isn't paramount
    this.buf = useFloat32 ? new Float32Array(size) : new Float64Array(size);
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
  /**
   * Returns the most recently pushed value, or undefined if the buffer is empty.
   * Does not remove the value.
   * @returns {number|undefined} The latest value.
   */
  peek() {
    if (this.count === 0) return undefined;
    const actualIdx = (this.idx + this.size - 1) % this.size;
    return this.buf[actualIdx];
  }
  
  /**
   * Returns the element at a specific logical index.
   * Index 0 is the oldest element, index `count-1` is the newest.
   * @param {number} index - The logical index to retrieve.
   * @returns {number|undefined} The value at the specified index, or undefined if out of bounds.
   */
  at(index) {
    if (index < 0 || index >= this.count) return undefined;
    const start = (this.idx + this.size - this.count) % this.size;
    return this.buf[(start + index) % this.size];
  }
  
  /**
   * Checks if the buffer is empty.
   * @returns {boolean} True if the buffer contains no elements.
   */
  isEmpty() { return this.count === 0; }

  /**
   * Checks if the buffer is full. Alias for filled().
   * @returns {boolean} True if the buffer is full.
   */
  isFull() { return this.count === this.size; }

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