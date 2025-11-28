// __tests__/ta.test.js
import TA from '../ta.js';

const approx = (a, b, eps = 1e-6) => Math.abs(a - b) < eps;

describe('TA.safeArr', () => {
  test('returns array of zeros of specified length', () => {
    const arr = TA.safeArr(5);
    expect(arr).toHaveLength(5);
    expect(arr.every(v => v === 0)).toBe(true);
  });
});

describe('TA.sma', () => {
  test('computes SMA correctly', () => {
    const data = [1, 2, 3, 4, 5];
    const sma = TA.sma(data, 3);
    expect(sma[0]).toBe(0);
    expect(sma[1]).toBe(0);
    expect(approx(sma[2], 2)).toBe(true);
    expect(approx(sma[3], 3)).toBe(true);
    expect(approx(sma[4], 4)).toBe(true);
  });
});

describe('TA.rsi', () => {
  test('produces values between 0 and 100', () => {
    const closes = [1, 2, 3, 2, 1, 2, 3, 4, 5];
    const rsi = TA.rsi(closes, 3);
    expect(rsi).toHaveLength(closes.length);
    rsi.forEach(v => {
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThanOrEqual(100);
    });
  });
});

describe('TA.fibPivots', () => {
  test('computes fib pivots for valid inputs', () => {
    const pivots = TA.fibPivots(100, 80, 90);
    expect(pivots.P).toBeDefined();
    expect(pivots.R1).toBeDefined();
    expect(pivots.S1).toBeDefined();
  });
});
