import { logger } from './utils.js';
import chalk from 'chalk';

// Helper to get a property from klines array
const getProperty = (klines, prop) => klines.map(k => k[prop]);

// --- Core Helpers ---

// True Range (TR)
export const calculateTrueRange = (klines) => {
  if (klines.length < 2) return klines.map(() => NaN);

  const tr = [];
  for (let i = 0; i < klines.length; i++) {
    if (i === 0) {
      tr.push(NaN);
      continue;
    }
    const high = klines[i].high;
    const low = klines[i].low;
    const prevClose = klines[i - 1].close;

    const highLow = high - low;
    const highPrevClose = Math.abs(high - prevClose);
    const lowPrevClose = Math.abs(low - prevClose);
    tr.push(Math.max(highLow, highPrevClose, lowPrevClose));
  }
  return tr;
};

// Simple Moving Average (SMA)
const calculateSMA = (data, period) => {
  if (data.length < period) return data.map(() => NaN);
  const sma = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      sma.push(NaN);
    } else {
      const sum = data.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
      sma.push(sum / period);
    }
  }
  return sma;
};

// Exponential Moving Average (EMA)
const calculateEMA = (data, period) => {
  if (data.length < period) return data.map(() => NaN);
  const ema = [];
  let sum = 0;
  let multiplier = 2 / (period + 1);

  // Initial SMA for first EMA value
  for (let i = 0; i < period; i++) {
    sum += data[i];
    ema.push(NaN); // Fill with NaN until enough data
  }
  ema[period - 1] = sum / period; // First EMA is SMA

  for (let i = period; i < data.length; i++) {
    ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1];
  }
  return ema;
};

// Ehlers SuperSmoother Filter
export const calculateSuperSmoother = (data, period) => {
  if (data.length < 2 || period <= 0) return data.map(() => NaN);

  const a1 = Math.exp(-Math.sqrt(2) * Math.PI / period);
  const b1 = 2 * a1 * Math.cos(Math.sqrt(2) * Math.PI / period);
  const c1 = 1 - b1 + a1 * a1;
  const c2 = b1 - 2 * a1 * a1;
  const c3 = a1 * a1;

  const filt = new Array(data.length).fill(NaN);
  if (data.length >= 1) filt[0] = data[0];
  if (data.length >= 2) filt[1] = (data[0] + data[1]) / 2;

  for (let i = 2; i < data.length; i++) {
    filt[i] = (c1 / 2) * (data[i] + data[i - 1]) + c2 * filt[i - 1] - c3 * filt[i - 2];
  }
  return filt;
};

// --- New Indicators ---

export const calculateVolatilityIndex = (klines, period) => {
  if (klines.length < period) return klines.map(() => NaN);

  const atrValues = calculateEMA(calculateTrueRange(klines), period); // Using EMA for ATR as in whalebot.py
  const closePrices = getProperty(klines, 'close');

  const volatilityIndex = [];
  for (let i = 0; i < klines.length; i++) {
    if (i < period - 1 || isNaN(atrValues[i]) || closePrices[i] === 0) {
      volatilityIndex.push(NaN);
    } else {
      volatilityIndex.push(atrValues[i] / closePrices[i]);
    }
  }
  // Then apply a rolling mean for the final volatility index
  return calculateSMA(volatilityIndex, period);
};

export const calculateVWMA = (klines, period) => {
  if (klines.length < period) return klines.map(() => NaN);

  const closePrices = getProperty(klines, 'close');
  const volumes = getProperty(klines, 'volume');

  const vwma = [];
  for (let i = 0; i < klines.length; i++) {
    if (i < period - 1) {
      vwma.push(NaN);
    } else {
      let sumPriceVolume = 0;
      let sumVolume = 0;
      for (let j = 0; j < period; j++) {
        sumPriceVolume += closePrices[i - j] * volumes[i - j];
        sumVolume += volumes[i - j];
      }
      vwma.push(sumVolume === 0 ? NaN : sumPriceVolume / sumVolume);
    }
  }
  return vwma;
};

export const calculateVolumeDelta = (klines, period) => {
  if (klines.length < period) return klines.map(() => NaN);

  const volumeDelta = [];
  for (let i = 0; i < klines.length; i++) {
    if (i < period - 1) {
      volumeDelta.push(NaN);
    } else {
      let buyVolumeSum = 0;
      let sellVolumeSum = 0;
      for (let j = 0; j < period; j++) {
        const kline = klines[i - j];
        if (kline.close > kline.open) {
          buyVolumeSum += kline.volume;
        } else if (kline.close < kline.open) {
          sellVolumeSum += kline.volume;
        }
      }
      const totalVolumeSum = buyVolumeSum + sellVolumeSum;
      volumeDelta.push(totalVolumeSum === 0 ? 0 : (buyVolumeSum - sellVolumeSum) / totalVolumeSum);
    }
  }
  return volumeDelta;
};

export const calculateKaufmanAMA = (klines, period, fastPeriod, slowPeriod) => {
  if (klines.length < period + slowPeriod) return klines.map(() => NaN);

  const closePrices = getProperty(klines, 'close');
  const kama = new Array(klines.length).fill(NaN);

  const fastAlpha = 2 / (fastPeriod + 1);
  const slowAlpha = 2 / (slowPeriod + 1);

  // Initialize KAMA with the first valid close price (after enough data for initial ER calculation)
  let firstValidIdx = -1;
  for(let i = period; i < klines.length; i++) {
    const priceChange = Math.abs(closePrices[i] - closePrices[i - period]);
    let volatility = 0;
    for (let j = 0; j < period; j++) {
      volatility += Math.abs(closePrices[i - j] - closePrices[i - j - 1]);
    }
    if (volatility !== 0) {
      firstValidIdx = i;
      break;
    }
  }

  if (firstValidIdx === -1) return klines.map(() => NaN); // No valid ER could be calculated

  kama[firstValidIdx] = closePrices[firstValidIdx];

  for (let i = firstValidIdx + 1; i < klines.length; i++) {
    const priceChange = Math.abs(closePrices[i] - closePrices[i - period]);
    let volatility = 0;
    for (let j = 0; j < period; j++) {
      volatility += Math.abs(closePrices[i - j] - closePrices[i - j - 1]);
    }

    const er = volatility === 0 ? 0 : priceChange / volatility;
    const sc = Math.pow((er * (fastAlpha - slowAlpha) + slowAlpha), 2);

    kama[i] = kama[i - 1] + sc * (closePrices[i] - kama[i - 1]);
  }
  return kama;
};

// Fibonacci Pivot Points (simplified for now, just calculating the latest)
export const calculateFibonacciPivotPoints = (klines) => {
  if (klines.length === 0) return {};

  const latestKline = klines[klines.length - 1];
  const high = latestKline.high;
  const low = latestKline.low;
  const close = latestKline.close;

  const pivot = (high + low + close) / 3;
  const range = high - low;

  const r1 = pivot + (0.382 * range);
  const r2 = pivot + (0.618 * range);
  const s1 = pivot - (0.382 * range);
  const s2 = pivot - (0.618 * range);

  return {
    pivot: pivot,
    r1: r1,
    r2: r2,
    s1: s1,
    s2: s2,
  };
};
