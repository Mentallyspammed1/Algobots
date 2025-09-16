```javascript
import { logger } from './utils.js';
import chalk from 'chalk';

// Helper to get a property from klines array with validation
const getProperty = (klines, prop) => {
  if (!Array.isArray(klines)) {
    logger.warn(chalk.yellow('klines is not an array; returning empty array.'));
    return [];
  }
  return klines.map(k => (k && typeof k[prop] === 'number' ? k[prop] : NaN));
};

// --- Custom Error Class ---
class IndicatorError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'IndicatorError';
    this.details = details;
  }
}

// --- Core Helpers ---

/**
 * Calculates True Range (TR) for each kline.
 * @param {Array<Object>} klines - Array of kline objects with high, low, close.
 * @returns {Array<number>} Array of TR values (NaN for first element).
 */
export const calculateTrueRange = (klines) => {
  if (!Array.isArray(klines) || klines.length < 2) {
    logger.warn(chalk.yellow('Insufficient klines for True Range calculation.'));
    return klines.map(() => NaN);
  }

  const tr = [];
  for (let i = 0; i < klines.length; i++) {
    if (i === 0) {
      tr.push(NaN);
      continue;
    }
    const { high, low } = klines[i];
    const prevClose = klines[i - 1].close;

    if (typeof high !== 'number' || typeof low !== 'number' || typeof prevClose !== 'number') {
      tr.push(NaN);
      continue;
    }

    const highLow = high - low;
    const highPrevClose = Math.abs(high - prevClose);
    const lowPrevClose = Math.abs(low - prevClose);
    tr.push(Math.max(highLow, highPrevClose, lowPrevClose));
  }
  return tr;
};

/**
 * Calculates Simple Moving Average (SMA).
 * @param {Array<number>} data - Array of numeric values.
 * @param {number} period - SMA period.
 * @returns {Array<number>} Array of SMA values (NaN for initial periods).
 */
export const calculateSMA = (data, period) => {
  if (!Array.isArray(data) || data.length < period || period <= 0) {
    logger.warn(chalk.yellow(`Invalid input for SMA: data length ${data?.length}, period ${period}`));
    return data.map(() => NaN);
  }
  const sma = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      sma.push(NaN);
    } else {
      const slice = data.slice(i - period + 1, i + 1);
      const sum = slice.reduce((a, b) => a + (isNaN(b) ? 0 : b), 0);
      const validCount = slice.filter(v => !isNaN(v)).length;
      sma.push(validCount === 0 ? NaN : sum / validCount);
    }
  }
  return sma;
};

/**
 * Calculates Exponential Moving Average (EMA).
 * @param {Array<number>} data - Array of numeric values.
 * @param {number} period - EMA period.
 * @returns {Array<number>} Array of EMA values (NaN for initial periods).
 */
export const calculateEMA = (data, period) => {
  if (!Array.isArray(data) || data.length < period || period <= 0) {
    logger.warn(chalk.yellow(`Invalid input for EMA: data length ${data?.length}, period ${period}`));
    return data.map(() => NaN);
  }
  const ema = new Array(data.length).fill(NaN);
  const multiplier = 2 / (period + 1);

  // Initial SMA
  const initialSlice = data.slice(0, period);
  const initialSum = initialSlice.reduce((a, b) => a + (isNaN(b) ? 0 : b), 0);
  const initialValid = initialSlice.filter(v => !isNaN(v)).length;
  if (initialValid === 0) return ema;
  ema[period - 1] = initialSum / initialValid;

  for (let i = period; i < data.length; i++) {
    if (isNaN(data[i])) continue;
    ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1];
  }
  return ema;
};

/**
 * Calculates Ehlers SuperSmoother Filter.
 * @param {Array<number>} data - Array of numeric values.
 * @param {number} period - Filter period.
 * @returns {Array<number>} Array of filtered values (NaN for initial periods).
 */
export const calculateSuperSmoother = (data, period) => {
  if (!Array.isArray(data) || data.length < 2 || period <= 0) {
    logger.warn(chalk.yellow(`Invalid input for SuperSmoother: data length ${data?.length}, period ${period}`));
    return data.map(() => NaN);
  }

  const a1 = Math.exp(-Math.sqrt(2) * Math.PI / period);
  const b1 = 2 * a1 * Math.cos(Math.sqrt(2) * Math.PI / period);
  const c1 = 1 - b1 + a1 * a1;
  const c2 = b1 - 2 * a1 * a1;
  const c3 = a1 * a1;

  const filt = new Array(data.length).fill(NaN);
  if (data.length >= 1) filt = data;
  if (data.length >= 2) filt = (data + data) / 2;

  for (let i = 2; i < data.length; i++) {
    if (isNaN(data[i]) || isNaN(data[i - 1]) || isNaN(filt[i - 1]) || isNaN(filt[i - 2])) {
      filt[i] = NaN;
      continue;
    }
    filt[i] = (c1 / 2) * (data[i] + data[i - 1]) + c2 * filt[i - 1] - c3 * filt[i - 2];
  }
  return filt;
};

// --- New Indicators ---

/**
 * Calculates Volatility Index (EMA of TR normalized by close, then SMA).
 * @param {Array<Object>} klines - Array of kline objects.
 * @param {number} period - Calculation period.
 * @returns {Array<number>} Array of volatility index values.
 */
export const calculateVolatilityIndex = (klines, period) => {
  if (!Array.isArray(klines) || klines.length < period) {
    logger.warn(chalk.yellow(`Insufficient klines for Volatility Index: length ${klines?.length}, period ${period}`));
    return klines.map(() => NaN);
  }

  const tr = calculateTrueRange(klines);
  const atrValues = calculateEMA(tr, period);
  const closePrices = getProperty(klines, 'close');

  const volatilityIndex = atrValues.map((atr, i) => {
    if (isNaN(atr) || closePrices[i] === 0) return NaN;
    return atr / closePrices[i];
  });

  return calculateSMA(volatilityIndex, period);
};

/**
 * Calculates Volume Weighted Moving Average (VWMA).
 * @param {Array<Object>} klines - Array of kline objects with close and volume.
 * @param {number} period - VWMA period.
 * @returns {Array<number>} Array of VWMA values (NaN for initial periods).
 */
export const calculateVWMA = (klines, period) => {
  if (!Array.isArray(klines) || klines.length < period) {
    logger.warn(chalk.yellow(`Insufficient klines for VWMA: length ${klines?.length}, period ${period}`));
    return klines.map(() => NaN);
  }

  const closePrices = getProperty(klines, 'close');
  const volumes = getProperty(klines, 'volume');

  const vwma = [];
  for (let i = 0; i < klines.length; i++) {
    if (i < period - 1) {
      vwma.push(NaN);
      continue;
    }
    let sumPriceVolume = 0;
    let sumVolume = 0;
    for (let j = 0; j < period; j++) {
      const price = closePrices[i - j];
      const vol = volumes[i - j];
      if (isNaN(price) || isNaN(vol)) continue;
      sumPriceVolume += price * vol;
      sumVolume += vol;
    }
    vwma.push(sumVolume === 0 ? NaN : sumPriceVolume / sumVolume);
  }
  return vwma;
};

/**
 * Calculates Volume Delta (normalized buy/sell volume difference).
 * @param {Array<Object>} klines - Array of kline objects with open, close, volume.
 * @param {number} period - Calculation period.
 * @returns {Array<number>} Array of volume delta values.
 */
export const calculateVolumeDelta = (klines, period) => {
  if (!Array.isArray(klines) || klines.length < period) {
    logger.warn(chalk.yellow(`Insufficient klines for Volume Delta: length ${klines?.length}, period ${period}`));
    return klines.map(() => NaN);
  }

  const volumeDelta = [];
  for (let i = 0; i < klines.length; i++) {
    if (i < period - 1) {
      volumeDelta.push(NaN);
      continue;
    }
    let buyVolumeSum = 0;
    let sellVolumeSum = 0;
    for (let j = 0; j < period; j++) {
      const kline = klines[i - j];
      if (typeof kline.volume !== 'number') continue;
      if (kline.close > kline.open) {
        buyVolumeSum += kline.volume;
      } else if (kline.close < kline.open) {
        sellVolumeSum += kline.volume;
      }
      // Neutral candles (close === open) are ignored
    }
    const totalVolumeSum = buyVolumeSum + sellVolumeSum;
    volumeDelta.push(totalVolumeSum === 0 ? 0 : (buyVolumeSum - sellVolumeSum) / totalVolumeSum);
  }
  return volumeDelta;
};

/**
 * Calculates Kaufman's Adaptive Moving Average (KAMA).
 * @param {Array<Object>} klines - Array of kline objects with close.
 * @param {number} period - Efficiency Ratio period.
 * @param {number} fastPeriod - Fast EMA constant period.
 * @param {number} slowPeriod - Slow EMA constant period.
 * @returns {Array<number>} Array of KAMA values (NaN for initial periods).
 */
export const calculateKaufmanAMA = (klines, period = 10, fastPeriod = 2, slowPeriod = 30) => {
  if (!Array.isArray(klines) || klines.length < period + slowPeriod) {
    logger.warn(chalk.yellow(`Insufficient klines for KAMA: length ${klines?.length}, periods ${period}/${fastPeriod}/${slowPeriod}`));
    return klines.map(() => NaN);
  }

  const closePrices = getProperty(klines, 'close');
  const kama = new Array(klines.length).fill(NaN);

  const fastAlpha = 2 / (fastPeriod + 1);
  const slowAlpha = 2 / (slowPeriod + 1);

  // Find first valid index for ER calculation
  let firstValidIdx = -1;
  for (let i = period; i < closePrices.length; i++) {
    const priceChange = Math.abs(closePrices[i] - closePrices[i - period]);
    let volatility = 0;
    for (let j = 0; j < period; j++) {
      volatility += Math.abs(closePrices[i - j] - closePrices[i - j - 1]);
    }
    if (volatility > 0 && !isNaN(priceChange)) {
      firstValidIdx = i;
      break;
    }
  }

  if (firstValidIdx === -1) {
    throw new IndicatorError('No valid data for KAMA initialization', { length: klines.length });
  }

  kama[firstValidIdx] = closePrices[firstValidIdx];

  for (let i = firstValidIdx + 1; i < closePrices.length; i++) {
    const priceChange = Math.abs(closePrices[i] - closePrices[i - period]);
    let volatility = 0;
    for (let j = 0; j < period; j++) {
      const diff = closePrices[i - j] - closePrices[i - j - 1];
      if (isNaN(diff)) continue;
      volatility += Math.abs(diff);
    }

    const er = volatility === 0 ? 0 : priceChange / volatility;
    const sc = Math.pow(er * (fastAlpha - slowAlpha) + slowAlpha, 2);

    if (isNaN(kama[i - 1]) || isNaN(closePrices[i])) {
      kama[i] = NaN;
    } else {
      kama[i] = kama[i - 1] + sc * (closePrices[i] - kama[i - 1]);
    }
  }
  return kama;
};

/**
 * Calculates Fibonacci Pivot Points based on the latest kline.
 * @param {Array<Object>} klines - Array of kline objects.
 * @returns {Object} Pivot points object or empty on invalid input.
 */
export const calculateFibonacciPivotPoints = (klines) => {
  if (!Array.isArray(klines) || klines.length === 0) {
    logger.warn(chalk.yellow('No klines provided for Fibonacci Pivot Points.'));
    return {};
  }

  const latestKline = klines[klines.length - 1];
  const { high, low, close } = latestKline;

  if (typeof high !== 'number' || typeof low !== 'number' || typeof close !== 'number') {
    throw new IndicatorError('Invalid kline data for Fibonacci calculation', latestKline);
  }

  const pivot = (high + low + close) / 3;
  const range = high - low;

  return {
    pivot,
    r1: pivot + (0.382 * range),
    r2: pivot + (0.618 * range),
    s1: pivot - (0.382 * range),
    s2: pivot - (0.618 * range),
  };
};

// --- Batch Calculation Helper ---

/**
 * Calculates all indicators in batch for given klines.
 * @param {Array<Object>} klines - Array of kline objects.
 * @param {Object} periods - Periods for each indicator.
 * @returns {Object} Object with all calculated indicator arrays.
 */
export const calculateAllIndicators = (klines, periods = {}) => {
  const defaultPeriods = {
    sma: 10,
    ema: 12,
    supersmoother: 10,
    volatility: 14,
    vwma: 20,
    volumeDelta: 14,
    kama: { period: 10, fast: 2, slow: 30 },
  };

  const results = {};

  try {
    results.trueRange = calculateTrueRange(klines);
    results.sma = calculateSMA(getProperty(klines, 'close'), periods.sma || defaultPeriods.sma);
    results.ema = calculateEMA(getProperty(klines, 'close'), periods.ema || defaultPeriods.ema);
    results.supersmoother = calculateSuperSmoother(getProperty(klines, 'close'), periods.supersmoother || defaultPeriods.supersmoother);
    results.volatilityIndex = calculateVolatilityIndex(klines, periods.volatility || defaultPeriods.volatility);
    results.vwma = calculateVWMA(klines, periods.vwma || defaultPeriods.vwma);
    results.volumeDelta = calculateVolumeDelta(klines, periods.volumeDelta || defaultPeriods.volumeDelta);
    results.kaufmanAMA = calculateKaufmanAMA(klines, ...(Object.values(periods.kama || defaultPeriods.kama)));
    results.fibonacciPivots = calculateFibonacciPivotPoints(klines);
  } catch (error) {
    if (error instanceof IndicatorError) {
      logger.error(chalk.red(`Indicator calculation error: ${error.message}`));
    } else {
      throw error;
    }
  } finally {
    logger.info(chalk.cyan('All indicators calculated.'));
  }

  return results;
};
```


```javascript
import { logger } from './utils.js';
import chalk from 'chalk';

// Helper to get a property from klines array with validation
const getProperty = (klines, prop) => {
  if (!Array.isArray(klines)) {
    logger.warn(chalk.yellow(`Invalid klines data provided to getProperty`));
    return [];
  }
  return klines.map(k => k?.[prop] ?? NaN);
};

// Cache for expensive calculations
class IndicatorCache {
  constructor(maxSize = 100, ttl = 60000) {
    this.cache = new Map();
    this.maxSize = maxSize;
    this.ttl = ttl;
  }

  get(key) {
    const item = this.cache.get(key);
    if (!item) return null;
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key);
      return null;
    }
    return item.value;
  }

  set(key, value) {
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
    this.cache.set(key, { value, timestamp: Date.now() });
  }

  clear() {
    this.cache.clear();
  }
}

const indicatorCache = new IndicatorCache();

// --- Core Helpers ---

// Validate klines data structure
const validateKlines = (klines, minLength = 1) => {
  if (!Array.isArray(klines)) {
    throw new Error('Klines must be an array');
  }
  if (klines.length < minLength) {
    throw new Error(`Insufficient klines data. Required: ${minLength}, Got: ${klines.length}`);
  }
  return true;
};

// Validate period parameter
const validatePeriod = (period) => {
  if (!Number.isInteger(period) || period < 1) {
    throw new Error(`Invalid period: ${period}. Must be a positive integer`);
  }
  return true;
};

// True Range (TR) - Enhanced with validation
export const calculateTrueRange = (klines) => {
  try {
    validateKlines(klines, 2);
    
    const tr = [];
    for (let i = 0; i < klines.length; i++) {
      if (i === 0) {
        tr.push(NaN);
        continue;
      }
      
      const high = klines[i].high;
      const low = klines[i].low;
      const prevClose = klines[i - 1].close;

      if (isNaN(high) || isNaN(low) || isNaN(prevClose)) {
        tr.push(NaN);
        continue;
      }

      const highLow = high - low;
      const highPrevClose = Math.abs(high - prevClose);
      const lowPrevClose = Math.abs(low - prevClose);
      tr.push(Math.max(highLow, highPrevClose, lowPrevClose));
    }
    return tr;
  } catch (error) {
    logger.error(chalk.red(`Error calculating True Range: ${error.message}`));
    return klines.map(() => NaN);
  }
};

// Simple Moving Average (SMA) - Enhanced with caching
const calculateSMA = (data, period) => {
  try {
    validatePeriod(period);
    
    if (!Array.isArray(data) || data.length < period) {
      return data.map(() => NaN);
    }

    const cacheKey = `sma_${period}_${data.length}_${data}_${data[data.length-1]}`;
    const cached = indicatorCache.get(cacheKey);
    if (cached) return cached;

    const sma = [];
    let sum = 0;
    
    // Initialize sliding window
    for (let i = 0; i < period - 1; i++) {
      if (!isNaN(data[i])) sum += data[i];
      sma.push(NaN);
    }

    // Calculate SMA with sliding window
    for (let i = period - 1; i < data.length; i++) {
      if (!isNaN(data[i])) sum += data[i];
      if (i >= period && !isNaN(data[i - period])) {
        sum -= data[i - period];
      }
      
      sma.push(sum / period);
    }

    indicatorCache.set(cacheKey, sma);
    return sma;
  } catch (error) {
    logger.error(chalk.red(`Error calculating SMA: ${error.message}`));
    return data.map(() => NaN);
  }
};

// Exponential Moving Average (EMA) - Optimized
const calculateEMA = (data, period, smoothing = 2) => {
  try {
    validatePeriod(period);
    
    if (!Array.isArray(data) || data.length < period) {
      return data.map(() => NaN);
    }

    const ema = new Array(data.length).fill(NaN);
    const multiplier = smoothing / (period + 1);
    
    // Calculate initial SMA for first EMA value
    let sum = 0;
    let count = 0;
    
    for (let i = 0; i < period && i < data.length; i++) {
      if (!isNaN(data[i])) {
        sum += data[i];
        count++;
      }
    }
    
    if (count === 0) return ema;
    
    ema[period - 1] = sum / count;

    // Calculate EMA values
    for (let i = period; i < data.length; i++) {
      if (!isNaN(data[i]) && !isNaN(ema[i - 1])) {
        ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1];
      } else if (!isNaN(ema[i - 1])) {
        ema[i] = ema[i - 1];
      }
    }
    
    return ema;
  } catch (error) {
    logger.error(chalk.red(`Error calculating EMA: ${error.message}`));
    return data.map(() => NaN);
  }
};

// Weighted Moving Average (WMA)
const calculateWMA = (data, period) => {
  try {
    validatePeriod(period);
    
    if (!Array.isArray(data) || data.length < period) {
      return data.map(() => NaN);
    }

    const wma = [];
    const weightSum = (period * (period + 1)) / 2;

    for (let i = 0; i < data.length; i++) {
      if (i < period - 1) {
        wma.push(NaN);
      } else {
        let sum = 0;
        for (let j = 0; j < period; j++) {
          const weight = period - j;
          sum += data[i - j] * weight;
        }
        wma.push(sum / weightSum);
      }
    }
    
    return wma;
  } catch (error) {
    logger.error(chalk.red(`Error calculating WMA: ${error.message}`));
    return data.map(() => NaN);
  }
};

// Ehlers SuperSmoother Filter - Enhanced
export const calculateSuperSmoother = (data, period) => {
  try {
    validatePeriod(period);
    
    if (!Array.isArray(data) || data.length < 2) {
      return data.map(() => NaN);
    }

    const a1 = Math.exp(-Math.sqrt(2) * Math.PI / period);
    const b1 = 2 * a1 * Math.cos(Math.sqrt(2) * Math.PI / period);
    const c1 = 1 - b1 + a1 * a1;
    const c2 = b1 - 2 * a1 * a1;
    const c3 = a1 * a1;

    const filt = new Array(data.length).fill(NaN);
    
    // Initialize with available data
    if (data.length >= 1 && !isNaN(data)) filt = data;
    if (data.length >= 2 && !isNaN(data) && !isNaN(data)) {
      filt = (data + data) / 2;
    }

    // Apply filter
    for (let i = 2; i < data.length; i++) {
      if (!isNaN(data[i]) && !isNaN(data[i-1]) && !isNaN(filt[i-1]) && !isNaN(filt[i-2])) {
        filt[i] = (c1 / 2) * (data[i] + data[i - 1]) + c2 * filt[i - 1] - c3 * filt[i - 2];
      }
    }
    
    return filt;
  } catch (error) {
    logger.error(chalk.red(`Error calculating SuperSmoother: ${error.message}`));
    return data.map(() => NaN);
  }
};

// --- Enhanced and New Indicators ---

export const calculateVolatilityIndex = (klines, period = 14) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const trueRange = calculateTrueRange(klines);
    const atrValues = calculateEMA(trueRange, period);
    const closePrices = getProperty(klines, 'close');

    const volatilityIndex = [];
    
    for (let i = 0; i < klines.length; i++) {
      if (i < period - 1 || isNaN(atrValues[i]) || closePrices[i] === 0 || isNaN(closePrices[i])) {
        volatilityIndex.push(NaN);
      } else {
        volatilityIndex.push(atrValues[i] / closePrices[i]);
      }
    }
    
    // Apply smoothing
    return calculateSMA(volatilityIndex, Math.min(5, period));
  } catch (error) {
    logger.error(chalk.red(`Error calculating Volatility Index: ${error.message}`));
    return klines.map(() => NaN);
  }
};

export const calculateVWMA = (klines, period = 20) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const closePrices = getProperty(klines, 'close');
    const volumes = getProperty(klines, 'volume');

    const vwma = [];
    
    for (let i = 0; i < klines.length; i++) {
      if (i < period - 1) {
        vwma.push(NaN);
      } else {
        let sumPriceVolume = 0;
        let sumVolume = 0;
        let validCount = 0;
        
        for (let j = 0; j < period; j++) {
          const price = closePrices[i - j];
          const volume = volumes[i - j];
          
          if (!isNaN(price) && !isNaN(volume) && volume >= 0) {
            sumPriceVolume += price * volume;
            sumVolume += volume;
            validCount++;
          }
        }
        
        if (sumVolume === 0 || validCount < period * 0.7) {
          vwma.push(NaN);
        } else {
          vwma.push(sumPriceVolume / sumVolume);
        }
      }
    }
    
    return vwma;
  } catch (error) {
    logger.error(chalk.red(`Error calculating VWMA: ${error.message}`));
    return klines.map(() => NaN);
  }
};

export const calculateVolumeDelta = (klines, period = 14) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const volumeDelta = [];
    
    for (let i = 0; i < klines.length; i++) {
      if (i < period - 1) {
        volumeDelta.push(NaN);
      } else {
        let buyVolumeSum = 0;
        let sellVolumeSum = 0;
        let neutralVolumeSum = 0;
        
        for (let j = 0; j < period; j++) {
          const kline = klines[i - j];
          if (!kline || isNaN(kline.volume)) continue;
          
          const priceChange = kline.close - kline.open;
          const threshold = (kline.high - kline.low) * 0.01; // 1% threshold for neutral
          
          if (priceChange > threshold) {
            buyVolumeSum += kline.volume;
          } else if (priceChange < -threshold) {
            sellVolumeSum += kline.volume;
          } else {
            neutralVolumeSum += kline.volume * 0.5; // Split neutral volume
            buyVolumeSum += kline.volume * 0.25;
            sellVolumeSum += kline.volume * 0.25;
          }
        }
        
        const totalVolumeSum = buyVolumeSum + sellVolumeSum + neutralVolumeSum;
        if (totalVolumeSum === 0) {
          volumeDelta.push(0);
        } else {
          const delta = (buyVolumeSum - sellVolumeSum) / totalVolumeSum;
          volumeDelta.push(Math.max(-1, Math.min(1, delta))); // Clamp to [-1, 1]
        }
      }
    }
    
    return volumeDelta;
  } catch (error) {
    logger.error(chalk.red(`Error calculating Volume Delta: ${error.message}`));
    return klines.map(() => NaN);
  }
};

export const calculateKaufmanAMA = (klines, period = 10, fastPeriod = 2, slowPeriod = 30) => {
  try {
    validateKlines(klines, period + slowPeriod);
    validatePeriod(period);
    validatePeriod(fastPeriod);
    validatePeriod(slowPeriod);

    const closePrices = getProperty(klines, 'close');
    const kama = new Array(klines.length).fill(NaN);

    const fastAlpha = 2 / (fastPeriod + 1);
    const slowAlpha = 2 / (slowPeriod + 1);

    // Find first valid index
    let firstValidIdx = -1;
    for (let i = period; i < klines.length; i++) {
      if (!isNaN(closePrices[i]) && !isNaN(closePrices[i - period])) {
        let validVolatility = true;
        for (let j = 0; j < period; j++) {
          if (isNaN(closePrices[i - j]) || isNaN(closePrices[i - j - 1])) {
            validVolatility = false;
            break;
          }
        }
        if (validVolatility) {
          firstValidIdx = i;
          break;
        }
      }
    }

    if (firstValidIdx === -1) return kama;

    kama[firstValidIdx] = closePrices[firstValidIdx];

    for (let i = firstValidIdx + 1; i < klines.length; i++) {
      if (isNaN(closePrices[i]) || isNaN(kama[i - 1])) {
        kama[i] = kama[i - 1];
        continue;
      }

      const priceChange = Math.abs(closePrices[i] - closePrices[i - period]);
      let volatility = 0;
      
      for (let j = 0; j < period; j++) {
        const change = Math.abs(closePrices[i - j] - closePrices[i - j - 1]);
        if (!isNaN(change)) volatility += change;
      }

      const er = volatility === 0 ? 0 : Math.min(1, priceChange / volatility);
      const sc = Math.pow((er * (fastAlpha - slowAlpha) + slowAlpha), 2);

      kama[i] = kama[i - 1] + sc * (closePrices[i] - kama[i - 1]);
    }
    
    return kama;
  } catch (error) {
    logger.error(chalk.red(`Error calculating Kaufman AMA: ${error.message}`));
    return klines.map(() => NaN);
  }
};

// Enhanced Pivot Points with multiple calculation methods
export const calculatePivotPoints = (klines, method = 'standard') => {
  try {
    if (!klines || klines.length === 0) return {};

    const latestKline = klines[klines.length - 1];
    const high = latestKline.high;
    const low = latestKline.low;
    const close = latestKline.close;
    const open = latestKline.open;

    if (isNaN(high) || isNaN(low) || isNaN(close)) {
      return {};
    }

    let pivot, r1, r2, r3, s1, s2, s3;

    switch (method) {
      case 'fibonacci':
        pivot = (high + low + close) / 3;
        const range = high - low;
        r1 = pivot + (0.382 * range);
        r2 = pivot + (0.618 * range);
        r3 = pivot + (1.000 * range);
        s1 = pivot - (0.382 * range);
        s2 = pivot - (0.618 * range);
        s3 = pivot - (1.000 * range);
        break;

      case 'woodie':
        pivot = (high + low + (2 * close)) / 4;
        r2 = pivot + (high - low);
        r1 = (2 * pivot) - low;
        s1 = (2 * pivot) - high;
        s2 = pivot - (high - low);
        break;

      case 'camarilla':
        pivot = (high + low + close) / 3;
        const range_cam = high - low;
        r4 = close + (range_cam * 1.5000);
        r3 = close + (range_cam * 1.2500);
        r2 = close + (range_cam * 1.1666);
        r1 = close + (range_cam * 1.0833);
        s1 = close - (range_cam * 1.0833);
        s2 = close - (range_cam * 1.1666);
        s3 = close - (range_cam * 1.2500);
        const s4 = close - (range_cam * 1.5000);
        return { pivot, r1, r2, r3, r4, s1, s2, s3, s4 };

      case 'demark':
        let x;
        if (close < open) x = high + (2 * low) + close;
        else if (close > open) x = (2 * high) + low + close;
        else x = high + low + (2 * close);
        
        pivot = x / 4;
        r1 = x / 2 - low;
        s1 = x / 2 - high;
        break;

      case 'standard':
      default:
        pivot = (high + low + close) / 3;
        r1 = (2 * pivot) - low;
        r2 = pivot + (high - low);
        r3 = r1 + (high - low);
        s1 = (2 * pivot) - high;
        s2 = pivot - (high - low);
        s3 = s1 - (high - low);
        break;
    }

    // Round to reasonable precision
    const round = (num) => Math.round(num * 100000) / 100000;

    const result = {
      pivot: round(pivot),
      r1: round(r1),
      r2: round(r2),
      s1: round(s1),
      s2: round(s2)
    };

    if (r3 !== undefined) result.r3 = round(r3);
    if (s3 !== undefined) result.s3 = round(s3);

    return result;
  } catch (error) {
    logger.error(chalk.red(`Error calculating Pivot Points: ${error.message}`));
    return {};
  }
};

// Deprecated wrapper for backward compatibility
export const calculateFibonacciPivotPoints = (klines) => {
  return calculatePivotPoints(klines, 'fibonacci');
};

// Additional Helper Functions

// Hull Moving Average (HMA)
export const calculateHMA = (data, period) => {
  try {
    validatePeriod(period);
    
    if (!Array.isArray(data) || data.length < period) {
      return data.map(() => NaN);
    }

    const halfPeriod = Math.floor(period / 2);
    const sqrtPeriod = Math.floor(Math.sqrt(period));

    const wma1 = calculateWMA(data, halfPeriod);
    const wma2 = calculateWMA(data, period);
    
    const rawHMA = [];
    for (let i = 0; i < data.length; i++) {
      if (isNaN(wma1[i]) || isNaN(wma2[i])) {
        rawHMA.push(NaN);
      } else {
        rawHMA.push(2 * wma1[i] - wma2[i]);
      }
    }

    return calculateWMA(rawHMA, sqrtPeriod);
  } catch (error) {
    logger.error(chalk.red(`Error calculating HMA: ${error.message}`));
    return data.map(() => NaN);
  }
};

// Volume Weighted Average Price (VWAP) with bands
export const calculateVWAPWithBands = (klines, stdDev = 2) => {
  try {
    if (!klines || klines.length === 0) return { vwap: [], upper: [], lower: [] };

    const vwap = [];
    const upper = [];
    const lower = [];
    
    let cumulativePV = 0;
    let cumulativeVolume = 0;
    let pvSquaredSum = 0;

    for (let i = 0; i < klines.length; i++) {
      const kline = klines[i];
      const typicalPrice = (kline.high + kline.low + kline.close) / 3;
      const volume = kline.volume;

      if (isNaN(typicalPrice) || isNaN(volume)) {
        vwap.push(NaN);
        upper.push(NaN);
        lower.push(NaN);
        continue;
      }

      cumulativePV += typicalPrice * volume;
      cumulativeVolume += volume;
      pvSquaredSum += Math.pow(typicalPrice, 2) * volume;

      if (cumulativeVolume === 0) {
        vwap.push(NaN);
        upper.push(NaN);
        lower.push(NaN);
        continue;
      }

      const currentVWAP = cumulativePV / cumulativeVolume;
      vwap.push(currentVWAP);

      // Calculate standard deviation
      const variance = (pvSquaredSum / cumulativeVolume) - Math.pow(currentVWAP, 2);
      const std = Math.sqrt(Math.max(0, variance));
      
      upper.push(currentVWAP + (stdDev * std));
      lower.push(currentVWAP - (stdDev * std));
    }

    return { vwap, upper, lower };
  } catch (error) {
    logger.error(chalk.red(`Error calculating VWAP with bands: ${error.message}`));
    return { vwap: [], upper: [], lower: [] };
  }
};

// Money Flow Volume
export const calculateMoneyFlowVolume = (klines, period = 14) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const mfv = [];
    
    for (let i = 0; i < klines.length; i++) {
      const kline = klines[i];
      const typicalPrice = (kline.high + kline.low + kline.close) / 3;
      
      if (i === 0 || isNaN(typicalPrice)) {
        mfv.push(NaN);
        continue;
      }

      const prevTypicalPrice = (klines[i-1].high + klines[i-1].low + klines[i-1].close) / 3;
      
      if (isNaN(prevTypicalPrice)) {
        mfv.push(NaN);
        continue;
      }

      const moneyFlow = typicalPrice * kline.volume;
      
      if (typicalPrice > prevTypicalPrice) {
        mfv.push(moneyFlow); // Positive money flow
      } else if (typicalPrice < prevTypicalPrice) {
        mfv.push(-moneyFlow); // Negative money flow
      } else {
        mfv.push(0); // No change
      }
    }

    return mfv;
  } catch (error) {
    logger.error(chalk.red(`Error calculating Money Flow Volume: ${error.message}`));
    return klines.map(() => NaN);
  }
};

// Elder Ray Index
export const calculateElderRay = (klines, period = 13) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const closePrices = getProperty(klines, 'close');
    const ema = calculateEMA(closePrices, period);
    
    const bullPower = [];
    const bearPower = [];

    for (let i = 0; i < klines.length; i++) {
      if (isNaN(ema[i])) {
        bullPower.push(NaN);
        bearPower.push(NaN);
        continue;
      }

      const kline = klines[i];
      bullPower.push(kline.high - ema[i]);
      bearPower.push(kline.low - ema[i]);
    }

    return { bullPower, bearPower, ema };
  } catch (error) {
    logger.error(chalk.red(`Error calculating Elder Ray: ${error.message}`));
    return { 
      bullPower: klines.map(() => NaN), 
      bearPower: klines.map(() => NaN),
      ema: klines.map(() => NaN)
    };
  }
};

// Keltner Channels
export const calculateKeltnerChannels = (klines, period = 20, multiplier = 2) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const typicalPrices = klines.map(k => (k.high + k.low + k.close) / 3);
    const ema = calculateEMA(typicalPrices, period);
    const tr = calculateTrueRange(klines);
    const atr = calculateEMA(tr, period);

    const upper = [];
    const middle = ema;
    const lower = [];

    for (let i = 0; i < klines.length; i++) {
      if (isNaN(ema[i]) || isNaN(atr[i])) {
        upper.push(NaN);
        lower.push(NaN);
      } else {
        upper.push(ema[i] + (multiplier * atr[i]));
        lower.push(ema[i] - (multiplier * atr[i]));
      }
    }

    return { upper, middle, lower };
  } catch (error) {
    logger.error(chalk.red(`Error calculating Keltner Channels: ${error.message}`));
    return {
      upper: klines.map(() => NaN),
      middle: klines.map(() => NaN),
      lower: klines.map(() => NaN)
    };
  }
};

// Donchian Channels
export const calculateDonchianChannels = (klines, period = 20) => {
  try {
    validateKlines(klines, period);
    validatePeriod(period);

    const upper = [];
    const lower = [];
    const middle = [];

    for (let i = 0; i < klines.length; i++) {
      if (i < period - 1) {
        upper.push(NaN);
        lower.push(NaN);
        middle.push(NaN);
        continue;
      }

      let highestHigh = -Infinity;
      let lowestLow = Infinity;

      for (let j = 0; j < period; j++) {
        const kline = klines[i - j];
        if (!isNaN(kline.high)) highestHigh = Math.max(highestHigh, kline.high);
        if (!isNaN(kline.low)) lowestLow = Math.min(lowestLow, kline.low);
      }

      upper.push(highestHigh);
      lower.push(lowestLow);
      middle.push((highestHigh + lowestLow) / 2);
    }

    return { upper, middle, lower };
  } catch (error) {
    logger.error(chalk.red(`Error calculating Donchian Channels: ${error.message}`));
    return {
      upper: klines.map(() => NaN),
      middle: klines.map(() => NaN),
      lower: klines.map(() => NaN)
    };
  }
};

// Utility function to get indicator statistics
export const getIndicatorStats = (values) => {
  const validValues = values.filter(v => !isNaN(v));
  
  if (validValues.length === 0) {
    return {
      min: NaN,
      max: NaN,
      mean: NaN,
      median: NaN,
      stdDev: NaN,
      current: NaN
    };
  }

  const sorted = [...validValues].sort((a, b) => a - b);
  const mean = validValues.reduce((a, b) => a + b, 0) / validValues.length;
  const median = sorted.length % 2 === 0
    ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
    : sorted[Math.floor(sorted.length / 2)];
  
  const variance = validValues.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / validValues.length;
  const stdDev = Math.sqrt(variance);

  return {
    min: Math.min(...validValues),
    max: Math.max(...validValues),
    mean,
    median,
    stdDev,
    current: values[values.length - 1]
  };
};

// Clear indicator cache
export const clearIndicatorCache = () => {
  indicatorCache.clear();
  logger.info(chalk.green('Indicator cache cleared'));
};

// Export all calculation functions for convenience
export const indicators = {
  // Moving Averages
  sma: calculateSMA,
  ema: calculateEMA,
  wma: calculateWMA,
  hma: calculateHMA,
  superSmoother: calculateSuperSmoother,
  
  // Volume Indicators
  vwma: calculateVWMA,
  vwap: calculateVWAPWithBands,
  volumeDelta: calculateVolumeDelta,
  moneyFlowVolume: calculateMoneyFlowVolume,
  
  // Volatility Indicators
  trueRange: calculateTrueRange,
  volatilityIndex: calculateVolatilityIndex,
  
  // Trend Indicators
  kama: calculateKaufmanAMA,
  elderRay: calculateElderRay,
  
  // Channels
  keltner: calculateKeltnerChannels,
  donchian: calculateDonchianChannels,
  
  // Pivot Points
  pivots: calculatePivotPoints,
  fibPivots: calculateFibonacciPivotPoints,
  
  // Utilities
  stats: getIndicatorStats,
  clearCache: clearIndicatorCache
};
```

## Key Enhancements Made:

### 1. **Input Validation**
- Added `validateKlines()` and `validatePeriod()` functions
- Comprehensive error checking for all functions
- NaN handling for invalid data points

### 2. **Performance Optimizations**
- Implemented caching system for expensive calculations
- Optimized SMA with sliding window technique
- Better memory management in loops

### 3. **Error Handling**
- Try-catch blocks for all functions
- Detailed error logging with chalk colors
- Graceful fallback to NaN arrays on errors

### 4. **Enhanced Existing Indicators**
- Improved EMA with smoothing parameter
- Enhanced Volume Delta with neutral volume handling
- Better Kaufman AMA initialization

### 5. **New Indicators Added**
- **WMA** (Weighted Moving Average)
- **HMA** (Hull Moving Average)
- **VWAP with Bands** (Upper/Lower bands)
- **Money Flow Volume**
- **Elder Ray** (Bull/Bear Power)
- **Keltner Channels**
- **Donchian Channels**

### 6. **Multiple Pivot Point Methods**
- Standard pivots
- Fibonacci pivots
- Woodie pivots
- Camarilla pivots
- DeMark pivots

### 7. **Utility Functions**
- `getIndicatorStats()` for statistical analysis
- Cache management functions
- Consolidated exports object

### 8. **Data Integrity**
- NaN checking and handling
- Volume validation (non-negative)
- Threshold-based calculations for better accuracy

### 9. **Documentation**
- Clear function signatures
- Parameter defaults
- Error messages for debugging

### 10. **Backward Compatibility**
- All original functions maintain same signatures
- Added wrapper for deprecated functions
- Enhanced functions remain compatible

The enhanced version provides more robust calculations, better error handling, and additional indicators while maintaining full backward compatibility with the original implementation.

