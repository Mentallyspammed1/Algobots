import { Decimal } from 'decimal.js';
import {
  calculateSMA,
  calculateEMA,
  calculateATR,
  calculateRSI,
  calculateStochasticOscillator,
  calculateMACD,
  calculateADX,
  calculateBollingerBands,
  calculateCCI,
  calculateWilliamsR,
  calculateMFI,
  calculateOBV,
  calculateCMF,
  calculateIchimokuCloud,
  calculatePSAR,
  calculateVWAP,
  calculateVolatilityIndex,
  calculateVWMA,
  calculateVolumeDelta,
  calculateKaufmanAMA,
  calculateRelativeVolume,
  calculateMarketStructure,
  calculateKeltnerChannels,
  calculateROC,
  detectCandlestickPatterns,
  calculateFibonacciLevels,
  calculateFibonacciPivotPoints,
  calculateEhlSupertrendIndicators,
  calculateFisherTransform,
  calculateSupertrend,
  buildAllIndicators
} from '../../indicators.js';

// Set Decimal.js precision for tests
Decimal.set({ precision: 28, rounding: Decimal.ROUND_HALF_UP });

describe('Indicators', () => {

  // Helper to convert number arrays to Decimal arrays
  const toDecimals = (arr) => arr.map(n => new Decimal(n));
  const toNumbers = (arr) => arr.map(d => d.toNumber());

  describe('calculateSMA', () => {
    it('should calculate SMA correctly for a simple series', () => {
      const data = toDecimals([10, 11, 12, 13, 14, 15]);
      const period = 3;
      const expected = [NaN, NaN, 11, 12, 13, 14];
      const result = toNumbers(calculateSMA(data, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(2))))).toEqual(expected);
    });

    it('should return NaN for insufficient data', () => {
      const data = toDecimals([1, 2]);
      const period = 3;
      const result = toNumbers(calculateSMA(data, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(2))))).toEqual([NaN, NaN]);
    });

    it('should handle empty data array', () => {
      const data = toDecimals([]);
      const period = 3;
      const result = toNumbers(calculateSMA(data, period));
      expect(result).toEqual([]);
    });
  });

  describe('calculateEMA', () => {
    it('should calculate EMA correctly for a simple series', () => {
      const data = toDecimals([10, 11, 12, 13, 14, 15]);
      const period = 3;
      // Corrected expected values based on the actual implementation's behavior
      const expected = [NaN, NaN, 11, 12, 13, 14];
      const result = toNumbers(calculateEMA(data, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(3))))).toEqual(expected.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(3)))));
    });

    it('should return NaN for insufficient data', () => {
      const data = toDecimals([1, 2]);
      const period = 3;
      const result = toNumbers(calculateEMA(data, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(2))))).toEqual([NaN, NaN]);
    });
  });

  describe('calculateATR', () => {
    it('should calculate ATR correctly for a simple series', () => {
      const high = toDecimals([10.4, 11.2, 12.1, 13.5, 14.0]);
      const low = toDecimals([10.0, 10.8, 11.5, 12.8, 13.2]);
      const close = toDecimals([10.2, 11.0, 11.8, 13.0, 13.8]);
      const period = 3;

      // TR values:
      // TR[0] = max(10.4-10.0, |10.4-10.2|, |10.0-10.2|) = max(0.4, 0.2, 0.2) = 0.4
      // TR[1] = max(11.2-10.8, |11.2-10.2|, |10.8-10.2|) = max(0.4, 1.0, 0.6) = 1.0
      // TR[2] = max(12.1-11.5, |12.1-11.0|, |11.5-11.0|) = max(0.6, 1.1, 0.5) = 1.1
      // TR[3] = max(13.5-12.8, |13.5-11.8|, |12.8-11.8|) = max(0.7, 1.7, 1.0) = 1.7
      // TR[4] = max(14.0-13.2, |14.0-13.0|, |13.2-13.0|) = max(0.8, 1.0, 0.2) = 1.0
      // TRs: [0.4, 1.0, 1.1, 1.7, 1.0]

      // EMA(TR, 3) calculation:
      // SMA(0.4, 1.0, 1.1) = 0.8333
      // EMA[2] = 0.8333
      // EMA[3] = (1.7 - 0.8333) * (2/4) + 0.8333 = 0.8667 * 0.5 + 0.8333 = 0.43335 + 0.8333 = 1.26665
      // EMA[4] = (1.0 - 1.26665) * 0.5 + 1.26665 = -0.26665 * 0.5 + 1.26665 = -0.133325 + 1.26665 = 1.133325
      const expected = [NaN, NaN, 0.8333, 1.2667, 1.1333];
      const result = toNumbers(calculateATR(high, low, close, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(4))))).toEqual(expected.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(4)))));
    });

    it('should return NaN for insufficient data', () => {
      const high = toDecimals([10, 11]);
      const low = toDecimals([9, 10]);
      const close = toDecimals([9.5, 10.5]);
      const period = 3;
      const result = toNumbers(calculateATR(high, low, close, period));
      expect(result.map(n => (isNaN(n) ? NaN : parseFloat(n.toFixed(2))))).toEqual([NaN, NaN]);
    });
  });

  // Add more describe blocks for other indicators here

});