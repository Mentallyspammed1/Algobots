import { Decimal } from 'decimal.js';
import { round_qty, round_price, np_clip } from '../../utils/math_utils.js';

describe('math_utils', () => {
  describe('round_qty', () => {
    it('should round down to the nearest step size', () => {
      const qty = new Decimal('12.3456');
      const step = new Decimal('0.001');
      const rounded = round_qty(qty, step);
      expect(rounded.toString()).toBe('12.345');
    });

    it('should handle quantities that are already multiples of the step size', () => {
      const qty = new Decimal('12.345');
      const step = new Decimal('0.001');
      const rounded = round_qty(qty, step);
      expect(rounded.toString()).toBe('12.345');
    });

    it('should work with larger step sizes', () => {
      const qty = new Decimal('127.5');
      const step = new Decimal('10');
      const rounded = round_qty(qty, step);
      expect(rounded.toString()).toBe('120');
    });

    it('should return the original quantity if step is zero or negative', () => {
      const qty = new Decimal('12.345');
      expect(round_qty(qty, new Decimal(0)).toString()).toBe('12.345');
      expect(round_qty(qty, new Decimal(-1)).toString()).toBe('12.345');
    });
  });

  describe('round_price', () => {
    it('should round down to the specified precision', () => {
      const price = new Decimal('12.345678');
      const rounded = round_price(price, 4);
      expect(rounded.toString()).toBe('12.3456');
    });

    it('should handle rounding to 0 decimal places', () => {
      const price = new Decimal('12.987');
      const rounded = round_price(price, 0);
      expect(rounded.toString()).toBe('12');
    });

    it('should handle prices that do not need rounding', () => {
      const price = new Decimal('12.5000');
      const rounded = round_price(price, 4);
      expect(rounded.toString()).toBe('12.5');
    });

    it('should treat negative precision as 0', () => {
        const price = new Decimal('12.987');
        const rounded = round_price(price, -2);
        expect(rounded.toString()).toBe('12');
      });
  });

  describe('np_clip', () => {
    it('should return the value if it is within the range', () => {
      expect(np_clip(5, 0, 10)).toBe(5);
    });

    it('should clamp the value to the minimum', () => {
      expect(np_clip(-5, 0, 10)).toBe(0);
    });

    it('should clamp the value to the maximum', () => {
      expect(np_clip(15, 0, 10)).toBe(10);
    });

    it('should work with boundary values', () => {
      expect(np_clip(0, 0, 10)).toBe(0);
      expect(np_clip(10, 0, 10)).toBe(10);
    });

    it('should work with negative ranges', () => {
        expect(np_clip(-5, -10, 0)).toBe(-5);
        expect(np_clip(-15, -10, 0)).toBe(-10);
        expect(np_clip(5, -10, 0)).toBe(0);
      });
  });
});
