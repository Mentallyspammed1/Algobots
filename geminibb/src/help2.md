Here are 20 update and improvement code snippets for the provided files:

---

### **FILE: `ta/core/ring_buffer.js`**

**1. Add `peek()` method to view the most recent element.**

```javascript
// ... existing code ...
  }
  push(x) { /* ... existing push logic ... */ }

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
  
  filled() { return this.count === this.size; }
// ... existing code ...
```

**2. Add `at(index)` method for logical indexed access.**

```javascript
// ... existing code ...
  peek() { /* ... existing peek logic ... */ }

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

  filled() { return this.count === this.size; }
// ... existing code ...
```

**3. Add `isEmpty()` and `isFull()` methods.**

```javascript
// ... existing code ...
  at(index) { /* ... existing at logic ... */ }
  
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

  filled() { return this.count === this.size; } // Can be aliased by isFull()
// ... existing code ...
```

**4. Allow `Float32Array` option in constructor for memory efficiency.**

```javascript
// ... existing code ...
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
// ... existing code ...
```

---

### **FILE: `ta/core/rolling_stats.js`**

**5. Add `reset()` method to clear the internal state.**

```javascript
// ... existing code ...
class RollingStats {
  constructor(period) { /* ... existing constructor logic ... */ }
  
  /**
   * Resets the rolling statistics, clearing all sums and the internal buffer.
   */
  reset() {
    this.buf = new RingBuffer(this.n); // Re-initialize buffer
    this.sum = 0;
    this.sumSq = 0;
  }

  next(x) { /* ... existing next logic ... */ }
// ... existing code ...
```

**6. Add `variance` getter property.**

```javascript
// ... existing code ...
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

  filled() { return this.buf.filled(); }
// ... existing code ...
```

**7. Add `mean` and `std` getter properties.**

```javascript
// ... existing code ...
  get variance() { /* ... existing variance logic ... */ }
  
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
// ... existing code ...
```

---

### **FILE: `ta/indicators/sma.js`**

**8. Add `reset()` method to clear the internal state.**

```javascript
// ... existing code ...
class SMA {
  constructor(period) { /* ... existing constructor logic ... */ }

  /**
   * Resets the SMA, clearing the internal buffer and sum.
   */
  reset() {
    this.buf = new RingBuffer(this.n);
    this.sum = 0;
    this.value = undefined;
  }

  next(x) { /* ... existing next logic ... */ }
// ... existing code ...
```

**9. Add `isReady` getter property.**

```javascript
// ... existing code ...
  next(x) { /* ... existing next logic ... */ }
  
  /**
   * Indicates if the SMA has enough data to produce a value.
   * @returns {boolean}
   */
  get isReady() {
    return this.buf.filled();
  }
}
export default SMA;
```

---

### **FILE: `ta/indicators/ema.js`**

**10. Handle `period = 1` as a special case (EMA(1) is just the input).**

```javascript
// ... existing code ...
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
      // ... existing seed logic ...
// ... existing code ...
```

**11. Add `isReady` getter property.**

```javascript
// ... existing code ...
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
```

---

### **FILE: `ta/indicators/rsi.js`**

**12. Add `reset()` method to clear the internal state.**

```javascript
// ... existing code ...
class RSI {
  constructor(period = 14) { /* ... existing constructor logic ... */ }

  /**
   * Resets the RSI, clearing all previous values and sums.
   */
  reset() {
    this.prev = undefined;
    this.gain = undefined;
    this.loss = undefined;
    this.value = undefined;
    this._initCount = 0;
    this._sumGain = 0;
    this._sumLoss = 0;
  }

  next(close) { /* ... existing next logic ... */ }
// ... existing code ...
```

**13. Add `isReady` getter property.**

```javascript
// ... existing code ...
    return this.value;
  }

  /**
   * Indicates if the RSI has enough data to produce a value.
   * @returns {boolean}
   */
  get isReady() {
    return this.value !== undefined;
  }
}
export default RSI;
```

**14. Add `currentGain` and `currentLoss` getters.**

```javascript
// ... existing code ...
  get isReady() { /* ... existing isReady logic ... */ }

  /**
   * Returns the current average gain (Wilder's smoothing).
   * @returns {number|undefined}
   */
  get currentGain() {
    return this.gain;
  }

  /**
   * Returns the current average loss (Wilder's smoothing).
   * @returns {number|undefined}
   */
  get currentLoss() {
    return this.loss;
  }
}
export default RSI;
```

---

### **FILE: `ta/indicators/atr.js`**

**15. Add `reset()` method to clear the internal state.**

```javascript
// ... existing code ...
class ATR {
  constructor(period = 14) { /* ... existing constructor logic ... */ }

  /**
   * Resets the ATR, clearing previous close, ATR value, and initialization sums.
   */
  reset() {
    this.prevClose = undefined;
    this.atr = undefined;
    this._initCount = 0;
    this._sumTR = 0;
  }

  next(candle) { /* ... existing next logic ... */ }
// ... existing code ...
```

**16. Add `isReady` getter property.**

```javascript
// ... existing code ...
  get value() { return this.atr; }

  /**
   * Indicates if the ATR has enough data to produce a value.
   * @returns {boolean}
   */
  get isReady() {
    return this.atr !== undefined;
  }
}
export default ATR;
```

---

### **FILE: `ta/indicators/macd.js`**

**17. Add `reset()` method to reset all internal EMAs.**

```javascript
// ... existing code ...
class MACD {
  constructor(fast = 12, slow = 26, signal = 9) { /* ... existing constructor logic ... */ }

  /**
   * Resets all internal EMA indicators for MACD, Signal, and Histogram.
   */
  reset() {
    this.fast.reset();
    this.slow.reset();
    this.signalEma.reset();
    this.value = undefined;
  }

  next(x) { /* ... existing next logic ... */ }
// ... existing code ...
```

**18. Add `isReady` getter property.**

```javascript
// ... existing code ...
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
```

---

### **FILE: `ta/indicators/bbands.js`**

**19. Add `isReady` getter property.**

```javascript
// ... existing code ...
class BollingerBands {
  constructor(period = 20, k = 2) { /* ... existing constructor logic ... */ }
  
  next(x) { /* ... existing next logic ... */ }

  /**
   * Indicates if the Bollinger Bands indicator has enough data to produce values.
   * @returns {boolean}
   */
  get isReady() {
    return this.stats.filled();
  }
}
export default BollingerBands;
```

---

### **FILE: `ta/aggregators/candle_aggregator.js`**

**20. Add `flush()` method to return the current partial candle and reset.**

```javascript
// ... existing code ...
class CandleAggregator {
  constructor(factor) { /* ... existing constructor logic ... */ }

  next(c) { /* ... existing next logic ... */ }

  /**
   * Returns the current in-progress aggregated candle and resets the aggregator,
   * even if the `factor` has not been met. Useful for end-of-session handling.
   * @returns {object|undefined} The current partial candle, or undefined if no work in progress.
   */
  flush() {
    const out = this._work;
    this._work = null;
    this._count = 0;
    return out;
  }
}
export default CandleAggregator;
```
