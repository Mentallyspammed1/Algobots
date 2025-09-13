const { Decimal } = require('decimal.js');
const {
    ewmMeanCustom,
    rollingMean,
    calculateTR,
    calculateATR,
    calculateRSI,
    calculateEhlersSupertrend,
    calculateFisherTransform,
    calculateEhlSupertrendIndicators
} = require('../indicators/indicators.js');

// Mock logger for indicator functions
const mockLogger = {
    error: jest.fn(),
    warn: jest.fn(),
    info: jest.fn(),
    debug: jest.fn(),
};

describe('ewmMeanCustom', () => {
    test('should calculate EMA correctly for a simple series', () => {
        const series = [new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16)];
        const span = 3;
        const expected = [
            new Decimal(NaN), // Not enough periods for first value
            new Decimal(NaN), // Not enough periods for second value
            new Decimal('12.5000000000'), 
            new Decimal('14.2500000000')
        ];
        const result = ewmMeanCustom(series, span, 3);
        expect(result.map(d => d.toFixed(10))).toEqual(expected.map(d => d.toFixed(10)));
    });

    test('should handle NaN values in series', () => {
        const series = [new Decimal(10), new Decimal(NaN), new Decimal(14), new Decimal(16)];
        const span = 3;
        const expected = [
            new Decimal(NaN),
            new Decimal(NaN),
            new Decimal(NaN),
            new Decimal(NaN)
        ];
        const result = ewmMeanCustom(series, span, 3);
        expect(result.map(d => d.isNaN())).toEqual(expected.map(d => d.isNaN()));
    });

    test('should return NaN for insufficient periods', () => {
        const series = [new Decimal(10), new Decimal(12)];
        const span = 3;
        const minPeriods = 3;
        const result = ewmMeanCustom(series, span, minPeriods);
        expect(result.map(d => d.isNaN())).toEqual([true, true]);
    });
});

describe('rollingMean', () => {
    test('should calculate SMA correctly for a simple series', () => {
        const series = [new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18)];
        const window = 3;
        const expected = [
            new Decimal(NaN),
            new Decimal(NaN),
            new Decimal(12), // (10+12+14)/3
            new Decimal(14), // (12+14+16)/3
            new Decimal(16)  // (14+16+18)/3
        ];
        const result = rollingMean(series, window);
        expect(result.map(d => d.toFixed(10))).toEqual(expected.map(d => d.toFixed(10)));
    });

    test('should return NaN for insufficient window size', () => {
        const series = [new Decimal(10), new Decimal(12)];
        const window = 3;
        const result = rollingMean(series, window);
        expect(result.map(d => d.isNaN())).toEqual([true, true]);
    });
});

describe('calculateTR and calculateATR', () => {
    const high = [new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18)];
    const low = [new Decimal(8), new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16)];
    const close = [new Decimal(9), new Decimal(11), new Decimal(13), new Decimal(15), new Decimal(17)];

    test('calculateATR should calculate Average True Range correctly', () => {
        const period = 3;
        const expectedATR = [
            new Decimal(NaN),
            new Decimal(NaN),
            new Decimal(NaN),
            new Decimal('3.0000000000'), 
            new Decimal('3.0000000000')  
        ];
        const result = calculateATR(high, low, close, period);
        expect(result.map(d => d.toFixed(10))).toEqual(expectedATR.map(d => d.toFixed(10)));
    });
});

describe('calculateRSI', () => {
    test('should calculate RSI correctly for a simple series', () => {
        const close = [
            new Decimal(44.34), new Decimal(44.09), new Decimal(43.65), new Decimal(43.03), new Decimal(42.51),
            new Decimal(43.17), new Decimal(44.25), new Decimal(45.00), new Decimal(44.58), new Decimal(45.35),
            new Decimal(44.15), new Decimal(43.51), new Decimal(43.82), new Decimal(43.61), new Decimal(44.22)
        ];
        const period = 14;
        const expectedRSI = [
            NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN, NaN,
            new Decimal('52.5527025408') 
        ];
        const result = calculateRSI(close, period);
        expect(result[result.length - 1].toFixed(10)).toEqual(expectedRSI[expectedRSI.length - 1].toFixed(10));
        expect(result.slice(0, period - 1).every(d => d.isNaN())).toBe(true); // Adjusted to period - 1
        expect(result[period - 1].isNaN()).toBe(false); // First calculated value should not be NaN
    });

    test('should return 100 if all gains and 0 losses', () => {
        const close = Array(20).fill(new Decimal(10)).map((d, i) => d.plus(i)); 
        const period = 14;
        const result = calculateRSI(close, period);
        expect(result[result.length - 1].toFixed(0)).toEqual(new Decimal(100).toFixed(0));
    });

    test('should return 0 if all losses and 0 gains', () => {
        const close = Array(20).fill(new Decimal(29)).map((d, i) => d.minus(i)); 
        const period = 14;
        const result = calculateRSI(close, period);
        expect(result[result.length - 1].toFixed(0)).toEqual(new Decimal(0).toFixed(0));
    });
});

describe('calculateEhlersSupertrend', () => {
    const high = [new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18), new Decimal(20), new Decimal(22), new Decimal(24), new Decimal(26), new Decimal(28), new Decimal(30), new Decimal(32), new Decimal(34), new Decimal(36), new Decimal(38), new Decimal(40)];
    const low = [new Decimal(8), new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18), new Decimal(20), new Decimal(22), new Decimal(24), new Decimal(26), new Decimal(28), new Decimal(30), new Decimal(32), new Decimal(34), new Decimal(36), new Decimal(38)];
    const close = [new Decimal(9), new Decimal(11), new Decimal(13), new Decimal(15), new Decimal(17), new Decimal(19), new Decimal(21), new Decimal(23), new Decimal(25), new Decimal(27), new Decimal(29), new Decimal(31), new Decimal(33), new Decimal(35), new Decimal(37), new Decimal(39)];
    const period = 7;
    const multiplier = 3;

    test('should return NaN arrays for insufficient data', () => {
        const insufficientClose = [new Decimal(10), new Decimal(12)]; 
        const result = calculateEhlersSupertrend(high.slice(0, 2), low.slice(0, 2), insufficientClose, period, multiplier);
        expect(result.supertrend.every(d => d.isNaN())).toBe(true);
        expect(result.direction.every(d => d === 0)).toBe(true);
    });

    test('should calculate Ehlers Supertrend correctly for sufficient data', () => {
        const result = calculateEhlersSupertrend(high, low, close, period, multiplier);
        expect(result.supertrend.length).toBe(close.length);
        expect(result.direction.length).toBe(close.length);
        expect(result.supertrend.slice(period).some(d => !d.isNaN())).toBe(true);
        expect(result.direction.slice(period).some(d => d !== 0)).toBe(true);
        expect(result.direction[result.direction.length - 1]).toBe(1); 
    });
});

describe('calculateFisherTransform', () => {
    const high = [new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18), new Decimal(20), new Decimal(22), new Decimal(24), new Decimal(26), new Decimal(28), new Decimal(30), new Decimal(32), new Decimal(34), new Decimal(36), new Decimal(38), new Decimal(40)];
    const low = [new Decimal(8), new Decimal(10), new Decimal(12), new Decimal(14), new Decimal(16), new Decimal(18), new Decimal(20), new Decimal(22), new Decimal(24), new Decimal(26), new Decimal(28), new Decimal(30), new Decimal(32), new Decimal(34), new Decimal(36), new Decimal(38)];
    const period = 10;

    test('should calculate Fisher Transform correctly', () => {
        const result = calculateFisherTransform(high, low, period);
        expect(result.fisher.length).toBe(high.length);
        expect(result.trigger.length).toBe(high.length);
        expect(result.fisher.slice(period).some(d => !d.isNaN())).toBe(true);
        expect(result.trigger.slice(period).some(d => !d.isNaN())).toBe(true);
        expect(result.fisher[0].toFixed(0)).toEqual(new Decimal(0).toFixed(0));
        expect(result.trigger[0].toFixed(0)).toEqual(new Decimal(0).toFixed(0));
    });
});

describe('calculateEhlSupertrendIndicators', () => {
    const klines = [
        { time: 1, open: 10, high: 12, low: 8, close: 11, volume: 100 },
        { time: 2, open: 11, high: 13, low: 9, close: 12, volume: 110 },
        { time: 3, open: 12, high: 14, low: 10, close: 13, volume: 120 },
        { time: 4, open: 13, high: 15, low: 11, close: 14, volume: 130 },
        { time: 5, open: 14, high: 16, low: 12, close: 15, volume: 140 },
        { time: 6, open: 15, high: 17, low: 13, close: 16, volume: 150 },
        { time: 7, open: 16, high: 18, low: 14, close: 17, volume: 160 },
        { time: 8, open: 17, high: 19, low: 15, close: 18, volume: 170 },
        { time: 9, open: 18, high: 20, low: 16, close: 19, volume: 180 },
        { time: 10, open: 19, high: 21, low: 17, close: 20, volume: 190 },
        { time: 11, open: 20, high: 22, low: 18, close: 21, volume: 200 },
        { time: 12, open: 21, high: 23, low: 19, close: 22, volume: 210 },
        { time: 13, open: 22, high: 24, low: 20, close: 23, volume: 220 },
        { time: 14, open: 23, high: 25, low: 21, close: 24, volume: 230 },
        { time: 15, open: 24, high: 26, low: 22, close: 25, volume: 240 },
        { time: 16, open: 25, high: 27, low: 23, close: 26, volume: 250 },
        { time: 17, open: 26, high: 28, low: 24, close: 27, volume: 260 },
        { time: 18, open: 27, high: 29, low: 25, close: 28, volume: 270 },
        { time: 19, open: 28, high: 30, low: 26, close: 29, volume: 280 },
        { time: 20, open: 29, high: 31, low: 27, close: 30, volume: 290 },
        { time: 21, open: 30, high: 32, low: 28, close: 31, volume: 300 },
        { time: 22, open: 31, high: 33, low: 29, close: 32, volume: 310 },
        { time: 23, open: 32, high: 34, low: 30, close: 33, volume: 320 },
        { time: 24, open: 33, high: 35, low: 31, close: 34, volume: 330 },
        { time: 25, open: 34, high: 36, low: 32, close: 35, volume: 340 },
        { time: 26, open: 35, high: 37, low: 33, close: 36, volume: 350 },
        { time: 27, open: 36, high: 38, low: 34, close: 37, volume: 360 },
        { time: 28, open: 37, high: 39, low: 35, close: 38, volume: 370 },
        { time: 29, open: 38, high: 40, low: 36, close: 39, volume: 380 },
        { time: 30, open: 39, high: 41, low: 37, close: 40, volume: 390 },
    ];

    const config = {
        strategy: {
            est_fast: { length: 7, multiplier: 3.0 },
            est_slow: { length: 14, multiplier: 3.0 },
            rsi: { period: 14 },
            volume: { ma_period: 10, threshold_multiplier: 1.5 },
            ehlers_fisher: { period: 10 },
            atr: { period: 14 },
            adx: { period: 14 },
        }
    };

    test('should calculate all Ehlers Supertrend indicators and attach to klines', () => {
        const result = calculateEhlSupertrendIndicators(klines, config, mockLogger);
        expect(result.length).toBe(klines.length);

        // Check that key indicators are present and not all NaN (after initial periods)
        const lastKline = result[result.length - 1];
        expect(lastKline).toHaveProperty('st_fast_line');
        expect(lastKline).toHaveProperty('st_fast_direction');
        expect(lastKline).toHaveProperty('st_slow_line');
        expect(lastKline).toHaveProperty('st_slow_direction');
        expect(lastKline).toHaveProperty('rsi');
        expect(lastKline).toHaveProperty('volume_ma');
        expect(lastKline).toHaveProperty('volume_spike');
        expect(lastKline).toHaveProperty('fisher');
        expect(lastKline).toHaveProperty('fisher_signal');
        expect(lastKline).toHaveProperty('atr');
        expect(lastKline).toHaveProperty('adx');

        // Check that some values are calculated (not NaN) for the last kline
        expect(lastKline.st_fast_line.isNaN()).toBe(false);
        expect(lastKline.st_slow_line.isNaN()).toBe(false);
        expect(lastKline.rsi.isNaN()).toBe(false);
        expect(lastKline.volume_ma.isNaN()).toBe(false);
        expect(lastKline.fisher.isNaN()).toBe(false);
        expect(lastKline.atr.isNaN()).toBe(false);
        expect(lastKline.adx.isNaN()).toBe(false);

        // Check forward-fill logic (e.g., if an early value was NaN, it should be filled)
        // For this linear data, there shouldn't be NaNs after the initial calculation periods.
        expect(result.every(k => !k.st_fast_line.isNaN())).toBe(true);
    });

    test('should handle empty klines array', () => {
        const result = calculateEhlSupertrendIndicators([], config, mockLogger);
        expect(result).toEqual([]);
    });
});