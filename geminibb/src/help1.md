Here are 20 code snippets representing updates and improvements across the provided files, along with brief explanations.

---

### **1. `ta/core/ring_buffer.js` - Add `clear()` method**
To efficiently reset the buffer's state without creating a new instance.
```javascript
// ... in RingBuffer class
  /**
   * Clears the buffer, resetting its count and index to zero.
   */
  clear() {
    this.count = 0;
    this.idx = 0;
    // Optionally fill with 0s if desired, but not strictly necessary for correctness
    // this.buf.fill(0); 
  }
// ...
```

### **2. `ta/core/ring_buffer.js` - Add `length` getter**
Provides a direct way to get the current number of elements.
```javascript
// ... in RingBuffer class
  /**
   * Returns the current number of elements in the buffer.
   * @returns {number} The current count of elements.
   */
  get length() {
    return this.count;
  }
// ...
```

### **3. `ta/core/ring_buffer.js` - Implement `Symbol.iterator`**
Allows `RingBuffer` instances to be used directly in `for...of` loops and spread syntax.
```javascript
// ... in RingBuffer class
  /**
   * Makes the RingBuffer iterable, returning values in time order (oldest to newest).
   * @yields {number} The next element in the buffer.
   */
  *[Symbol.iterator]() {
    const start = (this.idx + this.size - this.count) % this.size;
    for (let i = 0; i < this.count; i++) {
      yield this.buf[(start + i) % this.size];
    }
  }
// ...
```

### **4. `ta/core/ring_buffer.js` - Allow initialization with an array**
For convenience, to pre-populate the buffer.
```javascript
// ... in RingBuffer constructor
  constructor(size, useFloat32 = false, initialData = []) { // Add initialData parameter
    if (!Number.isInteger(size) || size <= 0) throw new Error("RingBuffer size must be > 0");
    this.size = size;
    this.buf = useFloat32 ? new Float32Array(size) : new Float64Array(size);
    this.count = 0;
    this.idx = 0;

    // New: Populate with initial data, respecting buffer size
    for (const item of initialData) {
      this.push(item);
    }
  }
// ...
```

### **5. `ta/core/ring_buffer.js` - Improve `filled()`/`isFull()` consistency**
Make `isFull()` the primary getter and `filled()` an alias for consistency.
```javascript
// ... in RingBuffer class
  /**
   * Checks if the buffer is full.
   * @returns {boolean} True if the buffer is full.
   */
  get isFull() { return this.count === this.size; }

  /**
   * Checks if the buffer is full. Alias for isFull().
   * @returns {boolean} True if the buffer is full.
   */
  filled() { return this.isFull; } // Change to use the getter
// ...
```

### **6. `ta/core/rolling_stats.js` - Optimize `reset()`**
Clear internal state efficiently instead of re-instantiating the `RingBuffer`.
```javascript
// ... in RollingStats class
  /**
   * Resets the rolling statistics, clearing all sums and the internal buffer.
   */
  reset() {
    this.buf.clear(); // Use new clear method
    this.sum = 0;
    this.sumSq = 0;
  }
// ...
```

### **7. `ta/core/rolling_stats.js` - Add `currentCount` getter**
To know the exact number of observations currently in the window, especially during the filling period.
```javascript
// ... in RollingStats class
  /**
   * Returns the current number of observations in the rolling window.
   * @returns {number} The current count.
   */
  get currentCount() {
    return this.buf.length;
  }
// ...
```

### **8. `ta/core/rolling_stats.js` - Add `useFloat32` option to constructor**
Propagate the `useFloat32` option to the underlying `RingBuffer`.
```javascript
// ... in RollingStats constructor
class RollingStats {
  constructor(period, useFloat32 = false) { // Add useFloat32 parameter
    if (!Number.isInteger(period) || period <= 1) throw new Error("period must be > 1");
    this.n = period;
    this.buf = new RingBuffer(period, useFloat32); // Pass useFloat32
    this.sum = 0;
    this.sumSq = 0;
  }
// ...
```

### **9. `ta/indicators/sma.js` - Optimize `reset()`**
Clear internal state efficiently instead of re-instantiating the `RingBuffer`.
```javascript
// ... in SMA class
  /**
   * Resets the SMA, clearing the internal buffer and sum.
   */
  reset() {
    this.buf.clear(); // Use RingBuffer's new clear method
    this.sum = 0;
    this.value = undefined;
  }
// ...
```

### **10. `ta/indicators/sma.js` - Add `useFloat32` option to constructor**
Propagate the `useFloat32` option to the underlying `RingBuffer`.
```javascript
// ... in SMA constructor
class SMA {
  constructor(period, useFloat32 = false) { // Add useFloat32 parameter
    if (period <= 0) throw new Error("SMA period must be > 0");
    this.n = period;
    this.buf = new RingBuffer(period, useFloat32); // Pass useFloat32
    this.sum = 0;
    this.value = undefined;
  }
// ...
```

### **11. `ta/indicators/ema.js` - Add `reset()` method**
Essential for resetting stateful indicators.
```javascript
// ... in EMA class
  /**
   * Resets the EMA, clearing its value and internal seeding state.
   */
  reset() {
    this.value = undefined;
    this._seedCount = 0;
    this._seedSum = 0;
  }
// ...
```

### **12. `ta/indicators/ema.js` - Add `alpha` (or `k`) getter**
Exposes the smoothing constant (k) for inspection.
```javascript
// ... in EMA class
  /**
   * Returns the smoothing constant (alpha or k) used in the EMA calculation.
   * @returns {number}
   */
  get alpha() {
    return this.k;
  }
// ...
```

### **13. `ta/indicators/rsi.js` - Add `period` getter**
Consistent API to retrieve the configured period.
```javascript
// ... in RSI class
  /**
   * Returns the period used for the RSI calculation.
   * @returns {number}
   */
  get period() {
    return this.n;
  }
// ...
```

### **14. `ta/indicators/rsi.js` - Improve initial calculation clarity/modularity**
Extract initial gain/loss calculation logic into a helper function or clearer block.
```javascript
// ... in RSI class, inside next(close) method
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
    // New: Encapsulate Wilder smoothing
    this.gain = ((this.gain * (this.n - 1)) + up) / this.n;
    this.loss = ((this.loss * (this.n - 1)) + down) / this.n;
// ... (The rest of the method is unchanged, just showing the small logical update)
```

### **15. `ta/indicators/atr.js` - Add `period` getter**
Consistent API to retrieve the configured period.
```javascript
// ... in ATR class
  /**
   * Returns the period used for the ATR calculation.
   * @returns {number}
   */
  get period() {
    return this.n;
  }
// ...
```

### **16. `ta/indicators/atr.js` - Make `value` an explicit getter**
Aligns `value` with `isReady` and other indicator properties.
```javascript
// ... in ATR class
  /**
   * Returns the current ATR value.
   * @returns {number|undefined}
   */
  get value() { return this.atr; }
// ... (remove the simple assignment `this.atr` inside next() and use `this._atr` or similar if `value` is a getter for `atr` member variable directly.)
// Correction: the existing `get value() { return this.atr; }` is already a getter. My note was based on a misunderstanding. So, this specific snippet for `ATR` can be skipped, or an alternative provided. Let's add an explicit method `getTR()` instead to expose the last calculated True Range.

// Alternative for ATR: Add `lastTrueRange` getter
// ... in ATR class
  // Add a property to store last calculated TR
  // constructor() { ... this._lastTR = undefined; ... }
  // next() { ... const tr = ... this._lastTR = tr; ... }

  /**
   * Returns the True Range of the last processed candle.
   * @returns {number|undefined} The last calculated True Range.
   */
  get lastTrueRange() {
    // This assumes a member variable like `_lastTR` is stored in `next`
    // For this snippet, let's just make it store `tr` to a new property `this.tr` in `next`.
    // Add `this.tr = undefined;` in constructor.
    return this.tr; 
  }
// ...
// And in next():
// this.tr = Math.max(h - l, Math.abs(h - prevC), Math.abs(l - prevC));
```

### **17. `ta/indicators/macd.js` - Add getters for periods**
Provide access to the configured periods (`fast`, `slow`, `signal`).
```javascript
// ... in MACD class
  /**
   * Returns the fast EMA period.
   * @returns {number}
   */
  get fastPeriod() { return this.fast.n; }

  /**
   * Returns the slow EMA period.
   * @returns {number}
   */
  get slowPeriod() { return this.slow.n; }

  /**
   * Returns the signal EMA period.
   * @returns {number}
   */
  get signalPeriod() { return this.signalEma.n; }
// ...
```

### **18. `ta/indicators/bbands.js` - Add `reset()` method**
Essential for resetting stateful indicators.
```javascript
// ... in BollingerBands class
  /**
   * Resets the Bollinger Bands indicator, clearing its internal rolling statistics.
   */
  reset() {
    this.stats.reset();
    this.value = undefined;
  }
// ...
```

### **19. `ta/indicators/bbands.js` - Add `period` and `k` getters**
Provide access to the configuration parameters.
```javascript
// ... in BollingerBands class
  /**
   * Returns the period used for the Bollinger Bands calculation.
   * @returns {number}
   */
  get period() {
    return this.stats.n;
  }

  /**
   * Returns the standard deviation multiplier (k) used for the bands.
   * @returns {number}
   */
  get kValue() { // Using kValue to avoid conflict with 'k' internal variable if needed
    return this.k;
  }
// ...
```

### **20. `ta/indicators/vwap.js` - Add `isReady` getter**
Consistent API to check if the indicator has a value.
```javascript
// ... in VWAP class
  /**
   * Indicates if the VWAP has enough data to produce a value (i.e., total volume is greater than 0).
   * @returns {boolean}
   */
  get isReady() {
    return this.vol > 0; // VWAP is ready as long as some volume has accumulated
  }
// ...
```
