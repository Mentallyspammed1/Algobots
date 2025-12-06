import { Strategy } from '../strategy.js';
import { safeArray } from '../utils.js'; // Assuming safeArray is exported from utils.js

// Mock dependencies and data
const mockConfig = {
    indicators: {
        rsi: 14, macd: { fast: 12, slow: 26, signal: 9 }, bb: { period: 20, std: 2 },
        atr: 14, stochRSI: { rsi: 14, stoch: 14, k: 3, d: 3 }, adx: 14, fisher: 9,
        advanced: {
            superTrend: { period: 10, multiplier: 3 },
            ichimoku: { span1: 9, span2: 26, span3: 52 },
            vwap: {}, hullMA: { period: 16 }, choppiness: { period: 14 },
            t3: { period: 10, vFactor: 0.7 }
        }
    }
};

// Mocking technical analysis functions to control inputs and outputs for strategy tests
// In a real scenario, these would be imported and potentially mocked if their internal logic was complex to set up for tests.
// For this test, we'll assume they are pure functions that return predictable arrays.
const mockTA = {
    rsi: jest.fn(), macd: jest.fn(), bollinger: jest.fn(), atr: jest.fn(),
    stochRSI: jest.fn(), adx: jest.fn(), williamsR: jest.fn(), fisher: jest.fn()
};
const mockTAA = {
    superTrend: jest.fn(), ichimoku: jest.fn(), vwap: jest.fn(), hullMA: jest.fn(),
    choppiness: jest.fn(), t3: jest.fn()
};

// Mocking to return predictable data, ensuring enough data points for calculations
const createMockIndicatorArray = (length, valueGenerator, offset = 0) => {
    const arr = safeArray(length);
    for (let i = 0; i < length; i++) {
        arr[i] = valueGenerator(i + offset);
    }
    return arr;
};

describe('Strategy', () => {
    let strategy;
    let mockCloses, mockHighs, mockLows, mockVolumes;
    let mockIndicators;

    const MOCK_KLINE_LENGTH = 500; // Sufficient length for most indicators

    beforeAll(() => {
        // Create mock data for klines
        mockCloses = createMockIndicatorArray(MOCK_KLINE_LENGTH, i => 100 + i * 0.1);
        mockHighs = createMockIndicatorArray(MOCK_KLINE_LENGTH, i => 100 + i * 0.1 + 0.5);
        mockLows = createMockIndicatorArray(MOCK_KLINE_LENGTH, i => 100 + i * 0.1 - 0.5);
        mockVolumes = createMockIndicatorArray(MOCK_KLINE_LENGTH, i => 1000 + i * 10);
    });

    beforeEach(() => {
        strategy = new Strategy(mockConfig);

        // Mock the TA functions to return predictable arrays
        // Ensure mock data length is sufficient for indicator calculations (e.g., period * 2)
        const rsiPeriod = mockConfig.indicators.rsi;
        const macdFast = mockConfig.indicators.macd.fast;
        const macdSlow = mockConfig.indicators.macd.slow;
        const macdSignal = mockConfig.indicators.macd.signal;
        const bbPeriod = mockConfig.indicators.bb.period;
        const atrPeriod = mockConfig.indicators.atr;
        const stochRsiPeriod = mockConfig.indicators.stochRSI.rsi;
        const fisherPeriod = mockConfig.indicators.fisher;
        const superTrendPeriod = mockConfig.indicators.advanced.superTrend.period;
        const ichimokuSpan2 = mockConfig.indicators.advanced.ichimoku.span2;
        const hmaPeriod = mockConfig.indicators.advanced.hma.period;
        const choppinessPeriod = mockConfig.indicators.advanced.choppiness.period;
        const t3Period = mockConfig.indicators.advanced.t3.period;
        
        const longestIndicatorPeriod = Math.max(
            rsiPeriod, macdSlow + macdSignal, bbPeriod, atrPeriod, stochRsiPeriod, 
            mockConfig.indicators.adx, fisherPeriod, superTrendPeriod, ichimokuSpan2, 
            hmaPeriod, choppinessPeriod, t3Period * 6 // T3 has a long warm-up
        );

        // Ensure mock arrays are long enough for longest indicator period
        const indicatorDataLength = Math.max(MOCK_KLINE_LENGTH, longestIndicatorPeriod + 5);

        const mockClosesIndicator = createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1);
        const mockHighsIndicator = createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1 + 0.5);
        const mockLowsIndicator = createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1 - 0.5);
        const mockVolumesIndicator = createMockIndicatorArray(indicatorDataLength, i => 1000 + i * 10);

        mockTA.rsi.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => Math.min(100, Math.max(0, 50 + i * 0.1))));
        mockTA.macd.mockReturnValue({ macd: createMockIndicatorArray(indicatorDataLength, i => i * 0.01), signal: createMockIndicatorArray(indicatorDataLength, i => i * 0.005), histogram: createMockIndicatorArray(indicatorDataLength, i => i * 0.005) });
        mockTA.bollinger.mockReturnValue({ upper: createMockIndicatorArray(indicatorDataLength, i => 101 + i * 0.1), mid: createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1), lower: createMockIndicatorArray(indicatorDataLength, i => 99 + i * 0.1) });
        mockTA.atr.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => 1 + i * 0.01));
        mockTA.stochRSI.mockReturnValue({ k: createMockIndicatorArray(indicatorDataLength, i => Math.min(100, Math.max(0, 50 + i * 0.2))), d: createMockIndicatorArray(indicatorDataLength, i => Math.min(100, Math.max(0, 45 + i * 0.2))) });
        mockTA.adx.mockReturnValue({ adx: createMockIndicatorArray(indicatorDataLength, i => Math.min(50, 10 + i * 0.05)), pdi: createMockIndicatorArray(indicatorDataLength, i => 20 + i * 0.1), ndi: createMockIndicatorArray(indicatorDataLength, i => 15 + i * 0.08) });
        mockTA.williamsR.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => -50 + i * 0.1));
        mockTA.fisher.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => i * 0.05));

        mockTAA.superTrend.mockReturnValue({ trend: createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1), direction: createMockIndicatorArray(indicatorDataLength, i => (i % 2 === 0 ? 1 : -1)) });
        mockTAA.ichimoku.mockReturnValue({ conv: createMockIndicatorArray(indicatorDataLength, i => 101 + i * 0.1), base: createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.1), spanA: createMockIndicatorArray(indicatorDataLength, i => 101.5 + i * 0.1), spanB: createMockIndicatorArray(indicatorDataLength, i => 99 + i * 0.1) });
        mockTAA.vwap.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.08));
        mockTAA.hullMA.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.09));
        mockTAA.choppiness.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => 50 + i * 0.1));
        mockTAA.t3.mockReturnValue(createMockIndicatorArray(indicatorDataLength, i => 100 + i * 0.11));
        
        // Assign mock implementations to the Strategy class (this is a simplification for testing)
        // In a real Jest setup, you would typically use jest.mock('path/to/module')
        // For this example, we'll temporarily override the imported modules.
        // This approach requires careful management if these modules are used elsewhere.
        // A better approach would be dependency injection or mocking at module level.
        Object.assign(TA, mockTA);
        Object.assign(TAA, mockTAA);

        // Prepare mock klines for the function being tested
        mockIndicators = {
            rsi: mockTA.rsi(mockClosesIndicator, mockConfig.indicators.rsi),
            macd: mockTA.macd(mockClosesIndicator, mockConfig.indicators.macd.fast, mockConfig.indicators.macd.slow, mockConfig.indicators.macd.signal),
            bollingerBands: mockTA.bollinger(mockClosesIndicator, mockConfig.indicators.bb.period, mockConfig.indicators.bb.std),
            atr: mockTA.atr(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockConfig.indicators.atr),
            stochRSI: mockTA.stochRSI(mockClosesIndicator, mockConfig.indicators.stochRSI.rsi, mockConfig.indicators.stochRSI.stoch, mockConfig.indicators.stochRSI.k, mockConfig.indicators.stochRSI.d),
            adx: mockTA.adx(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockConfig.indicators.adx),
            williamsR: mockTA.williamsR(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, 14),
            ehlersFisher: mockTA.fisher(mockHighsIndicator, mockLowsIndicator, mockConfig.indicators.fisher),
            supertrend: mockTAA.superTrend(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockConfig.indicators.advanced.superTrend.period, mockConfig.indicators.advanced.superTrend.multiplier),
            ichimoku: mockTAA.ichimoku(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockConfig.indicators.advanced.ichimoku.span1, mockConfig.indicators.advanced.ichimoku.span2, mockConfig.indicators.advanced.ichimoku.span3),
            vwap: mockTAA.vwap(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockVolumesIndicator),
            hma: mockTAA.hullMA(mockClosesIndicator, mockConfig.indicators.advanced.hma.period),
            choppiness: mockTAA.choppiness(mockHighsIndicator, mockLowsIndicator, mockClosesIndicator, mockConfig.indicators.advanced.choppiness.period),
            t3: mockTAA.t3(mockClosesIndicator, mockConfig.indicators.advanced.t3.period, mockConfig.indicators.advanced.t3.vFactor)
        };
    });

    afterAll(() => {
        // Restore original modules if they were overwritten, important for broader test suites
        // For this example, we assume direct module override is managed per-test or not needed globally.
    });

    describe('calculateIndicators', () => {
        it('should call all expected TA functions with correct parameters', () => {
            const klinesForCalc = Array(MOCK_KLINE_LENGTH).fill({ close: 100, high: 101, low: 99, volume: 1000 });
            strategy.calculateIndicators(klinesForCalc);

            expect(mockTA.rsi).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.rsi);
            expect(mockTA.macd).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.macd.fast, mockConfig.indicators.macd.slow, mockConfig.indicators.macd.signal);
            expect(mockTA.bollinger).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.bb.period, mockConfig.indicators.bb.std);
            expect(mockTA.atr).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), mockConfig.indicators.atr);
            expect(mockTA.stochRSI).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.stochRSI.rsi, mockConfig.indicators.stochRSI.stoch, mockConfig.indicators.stochRSI.k, mockConfig.indicators.stochRSI.d);
            expect(mockTA.adx).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), mockConfig.indicators.adx);
            expect(mockTA.williamsR).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), 14);
            expect(mockTA.fisher).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), mockConfig.indicators.fisher);
            expect(mockTAA.superTrend).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), mockConfig.indicators.advanced.superTrend.period, mockConfig.indicators.advanced.superTrend.multiplier);
            expect(mockTAA.ichimoku).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), mockConfig.indicators.advanced.ichimoku.span1, mockConfig.indicators.advanced.ichimoku.span2, mockConfig.indicators.advanced.ichimoku.span3);
            expect(mockTAA.vwap).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), expect.any(Array));
            expect(mockTAA.hullMA).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.advanced.hma.period);
            expect(mockTAA.choppiness).toHaveBeenCalledWith(expect.any(Array), expect.any(Array), expect.any(Array), mockConfig.indicators.advanced.choppiness.period);
            expect(mockTAA.t3).toHaveBeenCalledWith(expect.any(Array), mockConfig.indicators.advanced.t3.period, mockConfig.indicators.advanced.t3.vFactor);
        });

        it('should return correctly structured indicator object', () => {
            const klines = Array(MOCK_KLINE_LENGTH).fill({ close: 100, high: 101, low: 99, volume: 1000 });
            const indicators = strategy.calculateIndicators(klines);

            expect(indicators).toHaveProperty('rsi');
            expect(indicators).toHaveProperty('macd');
            expect(indicators).toHaveProperty('bollingerBands');
            expect(indicators).toHaveProperty('atr');
            expect(indicators).toHaveProperty('stochRSI');
            expect(indicators).toHaveProperty('adx');
            expect(indicators).toHaveProperty('williamsR');
            expect(indicators).toHaveProperty('ehlersFisher');
            expect(indicators).toHaveProperty('supertrend');
            expect(indicators).toHaveProperty('ichimoku');
            expect(indicators).toHaveProperty('vwap');
            expect(indicators).toHaveProperty('hma');
            expect(indicators).toHaveProperty('choppiness');
            expect(indicators).toHaveProperty('t3');

            // Basic check on array lengths returned by mock functions
            expect(indicators.rsi.length).toBeGreaterThan(0);
            expect(indicators.macd.macd.length).toBeGreaterThan(0);
            expect(indicators.bollingerBands.mid.length).toBeGreaterThan(0);
        });
    });

    describe('generateSignal', () => {
        const mockIndicators = {
            ehlersFisher: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], // Bullish trend
            rsi: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 40, 40, 45, 48, 50, 52, 55, 58, 60, 62], // Neutral RSI
            supertrend: { trend: [100, 100, 100, 100, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115], direction: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] }, // Bullish Supertrend
            adx: { adx: [20, 20, 20, 20, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36], pdi: [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44], ndi: [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34] }, // Strong trend, PDI > NDI
            macd: { histogram: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0] }, // Bullish MACD histogram
            stochRSI: { k: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 45, 48, 50, 52, 55, 58, 60, 62, 64, 66], d: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57] }, // Neutral StochRSI
        };
        const currentPrice = 105;

        it('should generate a BUY signal when score is high and indicators are bullish', () => {
            const result = strategy.generateSignal(mockIndicators, currentPrice);
            expect(result.signal).toBe('BUY');
            expect(result.score).toBeGreaterThan(40);
        });

        it('should generate a SELL signal when score is low and indicators are bearish', () => {
            const bearishIndicators = {
                ...mockIndicators,
                ehlersFisher: [-10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9], // Bearish trend
                supertrend: { trend: [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81], direction: [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1] }, // Bearish Supertrend
                adx: { adx: [30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49], pdi: [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34], ndi: [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44] }, // Strong trend, NDI > PDI
                macd: { histogram: [-2.0, -1.9, -1.8, -1.7, -1.6, -1.5, -1.4, -1.3, -1.2, -1.1, -1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1] }, // Bearish MACD histogram
            };
            const result = strategy.generateSignal(bearishIndicators, 95);
            expect(result.signal).toBe('SELL');
            expect(result.score).toBeLessThan(-40);
        });

        it('should generate a HOLD signal when conditions are neutral or mixed', () => {
            const neutralIndicators = {
                ...mockIndicators,
                ehlersFisher: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], // Flat Ehlers Fisher
                rsi: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50], // Flat RSI
                supertrend: { trend: [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100], direction: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] }, // Trend direction but no price movement
                adx: { adx: [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10], pdi: [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15], ndi: [16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16] }, // Low ADX, no strong trend
                macd: { histogram: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] }, // Flat MACD
                stochRSI: { k: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50], d: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50, 50] }, // Neutral StochRSI
            };
            const result = strategy.generateSignal(neutralIndicators, 100);
            expect(result.signal).toBe('HOLD');
            expect(result.score).toBeGreaterThan(-40);
            expect(result.score).toBeLessThan(40);
        });

        it('should handle missing indicator data gracefully', () => {
            const partialIndicators = {
                ehlersFisher: [1, 2], // Insufficient data
                rsi: [50],
                supertrend: { trend: [100, 101], direction: [1, 1] },
                adx: { adx: [20], pdi: [25], ndi: [15] },
                macd: { histogram: [0.1] },
                stochRSI: { k: [50], d: [48] },
            };
            // Mocking TA functions to return empty or minimal arrays to test graceful handling
            mockTA.rsi.mockReturnValue([50]); // Return minimal valid data
            mockTA.macd.mockReturnValue({ macd: [0.1], signal: [0.05], histogram: [0.05] });
            mockTA.stochRSI.mockReturnValue({ k: [50], d: [48] });
            mockTA.adx.mockReturnValue({ adx: [20], pdi: [25], ndi: [15] });
            mockTAA.superTrend.mockReturnValue({ trend: [100, 101], direction: [1, 1] });

            const result = strategy.generateSignal(partialIndicators, 105);
            // Expect signal to be HOLD due to insufficient data or mixed signals
            expect(result.signal).toBe('HOLD');
            // Score should be calculated based on whatever partial data is available and safe defaults
            expect(result.score).toBeGreaterThan(-40); // Should not be excessively negative
            expect(result.score).toBeLessThan(40); // Should not be excessively positive
        });
    });
});
