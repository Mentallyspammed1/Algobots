const { ScalpTrader } = require('../../src/engine');
const WebSocket = require('ws');
const config = require('../../src/config');
const indicators = require('../../src/indicators');

// Mock dependencies
jest.mock('ws');
jest.mock('../../src/services/gemini');
jest.mock('../../src/services/alert');
jest.mock('../../src/indicators');

describe('ScalpTrader Integration - Error Handling', () => {
    let mockWebSocket;

    beforeEach(() => {
        const WebSocket = require('ws');
        mockWebSocket = {
            on: jest.fn((event, cb) => {
                if (event === 'open') cb();
            }),
            send: jest.fn(),
            close: jest.fn(),
            pong: jest.fn()
        };
        WebSocket.mockImplementation(() => mockWebSocket);
    });

    afterEach(() => {
        jest.clearAllMocks();
    });

    it('should handle errors in checkSignals gracefully', async () => {
        // Provide mock implementations for all indicators to isolate the test
        indicators.ema.mockReturnValue(0);
        indicators.superTrend.mockReturnValue({ trend: 1 });
        indicators.ehlersCyberCycle.mockReturnValue({ bullish: true });
        indicators.sma.mockReturnValue(0);
        indicators.isImpulsiveCandle.mockReturnValue({ bullish: true, bearish: false });

        indicators.calculateRSI.mockImplementation(() => {
            throw new Error('Test indicator error');
        });

        await ScalpTrader.initialize();
        
        const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    
        const messageHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'message')[1];
        for (let i = 0; i < 50; i++) {
            messageHandler(JSON.stringify({
                topic: `kline.${config.TIMEFRAME}.${config.SYMBOL}`,
                data: [{ start: Date.now(), open: 1, high: 1, low: 1, close: 1, volume: 1 }]
            }));
        }
    
        await ScalpTrader.checkSignals();
    
        expect(consoleErrorSpy).toHaveBeenCalledWith("Error in checkSignals:", "Test indicator error");
        
        consoleErrorSpy.mockRestore();
    });
});
