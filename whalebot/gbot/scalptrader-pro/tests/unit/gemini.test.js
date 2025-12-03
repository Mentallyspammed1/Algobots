const { EnhancedGeminiBrain } = require('../../src/services/gemini');
const config = require('../../src/config'); // Import config to mock
jest.mock('../../src/config', () => ({
    GEMINI_API_KEY: 'mock-api-key',
    gemini_model: 'mock-model',
    indicators: {
        wss_weights: {
            action_threshold: 2.0
        }
    }
}));


jest.mock('@google/generative-ai', () => {
    const mockGenerateContent = jest.fn();
    const mockGetGenerativeModel = jest.fn(() => ({
        generateContent: mockGenerateContent,
    }));
    const mockGoogleGenerativeAI = jest.fn(() => ({
        getGenerativeModel: mockGetGenerativeModel,
    }));
    return { 
        GoogleGenerativeAI: mockGoogleGenerativeAI,
        mockGenerateContent: mockGenerateContent
    };
});

const { mockGenerateContent } = require('@google/generative-ai');


describe('EnhancedGeminiBrain', () => {
    let geminiBrain;
    const mockContext = {
        wss: 3.5, price: 100, volatility: 0.01, marketRegime: 'NORMAL',
        trend_mtf: 'BULLISH', trend_angle: 0.05, adx: 30, rsi: 60, stoch_k: 80, macd_hist: 0.001,
        vwap: 99.5, fvg: null, isSqueeze: 'NO', divergence: 'NONE',
        fibs: { P: 100, S1: 99, R1: 101 }, sr_levels: 'S:[98] R:[102]'
    };
    
    beforeEach(() => {
        geminiBrain = new EnhancedGeminiBrain();
        mockGenerateContent.mockClear();
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.useRealTimers();
    });

    it('should parse a valid response correctly', async () => {
        mockGenerateContent.mockResolvedValue({
            response: { text: () => `{ "action": "BUY", "strategy": "TREND_SURFER", "confidence": 0.8, "entry": 100.5, "sl": 99.8, "tp": 101.2, "reason": "Strong trend" }` }
        });

        const result = await geminiBrain.analyze(mockContext);

        expect(result.action).toBe("BUY");
        expect(result.strategy).toBe("TREND_SURFER");
        expect(result.confidence).toBe(0.8);
        expect(result.entry).toBe(100.5);
    });

    it('should return default values for a malformed JSON response', async () => {
        mockGenerateContent.mockResolvedValue({
            response: { text: () => `INVALID RESPONSE TEXT` }
        });

        const result = await geminiBrain.analyze(mockContext);

        expect(result.action).toBe("HOLD");
        expect(result.confidence).toBe(0);
        expect(result.reason).toContain("AI Comms Failure");
    });

    it('should retry on API failure and eventually succeed', async () => {
        mockGenerateContent
            .mockRejectedValueOnce(new Error('API Error 1'))
            .mockRejectedValueOnce(new Error('API Error 2'))
            .mockResolvedValue({
                response: { text: () => `{ "action": "BUY", "strategy": "RECOVERY", "confidence": 0.7, "entry": 101, "sl": 100, "tp": 102, "reason": "Recovered" }` }
            });

        const promise = geminiBrain.analyze(mockContext);
        
        await jest.advanceTimersByTimeAsync(1000); // First delay
        await jest.advanceTimersByTimeAsync(2000); // Second delay

        const result = await promise;

        expect(mockGenerateContent).toHaveBeenCalledTimes(3);
        expect(result.action).toBe("BUY");
        expect(result.strategy).toBe("RECOVERY");
    });

    it('should return default values after all retries fail', async () => {
        mockGenerateContent.mockRejectedValue(new Error('API Error'));

        const promise = geminiBrain.analyze(mockContext);

        await jest.advanceTimersByTimeAsync(1000);
        await jest.advanceTimersByTimeAsync(2000);
        await jest.advanceTimersByTimeAsync(4000);

        const result = await promise;

        expect(mockGenerateContent).toHaveBeenCalledTimes(3);
        expect(result.reason).toBe("AI Comms Failure: API Error");
        expect(result.action).toBe("HOLD");
    });
});