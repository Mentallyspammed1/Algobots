const bybit = require('../../src/services/bybit');
const WebSocket = require('ws');
const config = require('../../src/config');

jest.mock('ws');

describe('Bybit Service', () => {
    let mockWebSocket;
    const onMessageCallback = jest.fn();

    beforeEach(() => {
        mockWebSocket = {
            on: jest.fn(),
            send: jest.fn(),
            close: jest.fn(),
            pong: jest.fn()
        };
        WebSocket.mockImplementation(() => mockWebSocket);
        jest.useFakeTimers();
    });

    afterEach(() => {
        jest.clearAllMocks();
        jest.useRealTimers();
    });

    it('should connect to the correct URL and subscribe', () => {
        bybit.connect(onMessageCallback);
        expect(WebSocket).toHaveBeenCalledWith('wss://stream.bybit.com/v5/public/spot');
        
        const openHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'open')[1];
        openHandler();

        expect(mockWebSocket.send).toHaveBeenCalledWith(JSON.stringify({
            op: 'subscribe',
            args: [`kline.${config.TIMEFRAME}.${config.SYMBOL}`]
        }));
    });

    it('should call the message callback on new kline message', () => {
        bybit.connect(onMessageCallback);
        const messageHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'message')[1];
        const mockMessage = { topic: `kline.${config.TIMEFRAME}.${config.SYMBOL}`, data: 'test data' };
        messageHandler(JSON.stringify(mockMessage));
        expect(onMessageCallback).toHaveBeenCalledWith(mockMessage);
    });

    it('should not call the message callback for non-kline messages', () => {
        bybit.connect(onMessageCallback);
        const messageHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'message')[1];
        const mockMessage = { topic: 'other.topic', data: 'test data' };
        messageHandler(JSON.stringify(mockMessage));
        expect(onMessageCallback).not.toHaveBeenCalled();
    });

    it('should respond to ping', () => {
        bybit.connect(onMessageCallback);
        const pingHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'ping')[1];
        pingHandler();
        expect(mockWebSocket.pong).toHaveBeenCalled();
    });

    it('should attempt to reconnect on close', () => {
        const connectSpy = jest.spyOn(bybit, 'connect');
        const setTimeoutSpy = jest.spyOn(global, 'setTimeout');

        bybit.connect(onMessageCallback);
        const closeHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'close')[1];
        closeHandler();
        
        expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 5000);
        
        jest.runAllTimers();
        expect(connectSpy).toHaveBeenCalledTimes(2);

        connectSpy.mockRestore();
        setTimeoutSpy.mockRestore();
    });
    
    it('should close connection on error', () => {
        bybit.connect(onMessageCallback);
        const errorHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'error')[1];
        errorHandler(new Error('Test Error'));
        expect(mockWebSocket.close).toHaveBeenCalled();
    });
});
