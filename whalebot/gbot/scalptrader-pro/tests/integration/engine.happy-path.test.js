const { ScalpTrader } = require('../../src/engine');
const WebSocket = require('ws');
const config = require('../../src/config');

// Mock dependencies
jest.mock('ws');
jest.mock('../../src/services/gemini');
jest.mock('../../src/services/alert');

const { analyzeSignal } = require('../../src/services/gemini');
const { sendSMS, formatSMS } = require('../../src/services/alert');

describe('ScalpTrader Integration - Happy Path', () => {
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
        
        jest.useFakeTimers();

        analyzeSignal.mockClear();
        sendSMS.mockClear();
        if(formatSMS.mockClear) formatSMS.mockClear();
        
        jest.restoreAllMocks();
    });

    afterEach(() => {
        jest.useRealTimers();
        jest.clearAllMocks();
        if (ScalpTrader.multiOHLC && ScalpTrader.multiOHLC.buffers.has(config.SYMBOL)) {
            ScalpTrader.multiOHLC.buffers.get(config.SYMBOL).length = 0;
        }
    });

    it('should initialize and connect to WebSocket', async () => {
        await ScalpTrader.initialize();
        const WebSocket = require('ws');
        expect(WebSocket).toHaveBeenCalledWith('wss://stream.bybit.com/v5/public/spot');
    });

    it('should trigger a LONG signal on high confluence', async () => {
        await ScalpTrader.initialize();
        
        analyzeSignal.mockResolvedValue({
            entry: "150", tp: "160", sl: "140", confidence: "High", reasoning: "Test reasoning"
        });
        const { formatSMS } = require('../../src/services/alert');
        formatSMS.mockImplementation(signal => `Test SMS: ${signal.direction}`);

        const messageHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'message')[1];

        for (let i = 0; i < 50; i++) {
            let candle;
            if (i === 49) {
                candle = {
                    start: Date.now(),
                    open: 140, high: 155, low: 139, close: 154, volume: 2000,
                };
            } else {
                candle = {
                    start: Date.now() - (50 - i) * 180000,
                    open: 100 + i * 0.8, high: 101.2 + i * 0.8, low: 99.8 + i * 0.8, close: 101 + i * 0.8, volume: 500,
                };
            }
            messageHandler(JSON.stringify({
                topic: `kline.${config.TIMEFRAME}.${config.SYMBOL}`,
                data: [candle]
            }));
        }
        
        await ScalpTrader.checkSignals();

        expect(analyzeSignal).toHaveBeenCalled();
        expect(sendSMS).toHaveBeenCalledWith('Test SMS: LONG');
    });

    it('should not trigger a signal if confluence is not met', async () => {
        await ScalpTrader.initialize();

        const messageHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'message')[1];

        for (let i = 0; i < 50; i++) {
            const candle = {
                start: Date.now() - (50 - i) * 180000,
                open: 100, high: 101, low: 99, close: 100, volume: 500
            };
            messageHandler(JSON.stringify({
                topic: `kline.${config.TIMEFRAME}.${config.SYMBOL}`,
                data: [candle]
            }));
        }
        
        await ScalpTrader.checkSignals();

        expect(analyzeSignal).not.toHaveBeenCalled();
        expect(sendSMS).not.toHaveBeenCalled();
    });
});
