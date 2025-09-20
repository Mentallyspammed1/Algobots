import { SMA, EMA, MACD, RSI } from './indicators';

describe('Technical Indicators', () => {
  describe('SMA', () => {
    it('should calculate the simple moving average correctly', () => {
      const sma = new SMA(3);
      expect(sma.update(1)).toBeNull();
      expect(sma.update(2)).toBeNull();
      expect(sma.update(3)).toBe(2);
      expect(sma.update(4)).toBe(3);
      expect(sma.update(5)).toBe(4);
    });
  });

  describe('EMA', () => {
    it('should calculate the exponential moving average correctly', () => {
      const ema = new EMA(3);
      expect(ema.update(2)).toBe(2);
      expect(ema.update(5)).toBe(3.5);
      expect(ema.update(1)).toBe(2.25);
      expect(ema.update(6)).toBe(4.125);
    });
  });

  describe('MACD', () => {
    it('should calculate MACD, signal, and histogram correctly', () => {
        const macd = new MACD(3, 6, 4);
        let result;
        const prices = [2, 3, 4, 5, 6, 5, 4, 5];
        const expected_histograms = [
            0,
            0.0625,
            0.140625,
            0.2109375,
            0.2138671875,
            -0.03076171875,
            -0.311279296875,
            -0.21942138671875
        ];
        for (let i = 0; i < prices.length; i++) {
            result = macd.update(prices[i]);
            expect(result.histogram).toBeCloseTo(expected_histograms[i]);
        }
    });
  });

  describe('RSI', () => {
      it('should calculate RSI correctly', () => {
          const rsi = new RSI(4);
          const prices = [10, 12, 11, 13, 14, 13, 15, 17];
          const expected_rsi = [
              null,
              100,
              60,
              82.08333333333334,
              86.39175257731959,
              65.39473684210526,
              79.52380952380952,
              86.51162790697675
          ];

          for (let i = 0; i < prices.length; i++) {
              const result = rsi.update(prices[i]);
              const expected = expected_rsi[i];
              if (expected === null) {
                  expect(result).toBeNull();
              } else {
                  expect(result).not.toBeNull();
                  expect(result).toBeCloseTo(expected);
              }
          }
      });
  });
});
loseTo(expected);
              }
          }
      });
  });
});
