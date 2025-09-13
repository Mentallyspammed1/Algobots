const BybitClient = require('../clients/bybit_client');
const { RestClientV5, WebsocketClient } = require('bybit-api');
const { Decimal } = require('decimal.js');
jest.mock('bybit-api'); // Mock the external library

describe('BybitClient', () => {
    let client;
    let mockConfig;

    beforeEach(() => {
        // Reset mocks before each test
        jest.clearAllMocks();

        // Mock config
        mockConfig = { api: { key: 'test', secret: 'test', testnet: true, dryRun: false, category: 'linear', accountType: 'UNIFIED' } };
        client = new BybitClient(mockConfig);

        // Mock RestClientV5 methods
        RestClientV5.mockImplementation(() => ({
            getKline: jest.fn(),
            submitOrder: jest.fn(),
            getWalletBalance: jest.fn(),
            cancelOrder: jest.fn(),
            cancelAllOrders: jest.fn(),
            amendOrder: jest.fn(),
            getOpenOrders: jest.fn(),
            getPositionInfo: jest.fn(),
            setLeverage: jest.fn(),
            setTradingStop: jest.fn(),
            getInstrumentsInfo: jest.fn(),
        }));

        // Mock WebsocketClient methods
        WebsocketClient.mockImplementation(() => ({
            subscribeV5: jest.fn(),
            on: jest.fn(),
            close: jest.fn(),
        }));

        // Re-initialize client with mocked RestClientV5 and WebsocketClient
        client = new BybitClient(mockConfig);
    });

    test('constructor initializes correctly', () => {
        expect(client.dryRun).toBe(mockConfig.api.dryRun);
        expect(client.category).toBe(mockConfig.api.category);
        expect(client.accountType).toBe(mockConfig.api.accountType);
        expect(RestClientV5).toHaveBeenCalledWith(expect.objectContaining({ key: 'test' }));
        expect(WebsocketClient).toHaveBeenCalledWith(expect.objectContaining({ key: 'test' }));
    });

    describe('getKlines', () => {
        test('should return formatted klines on success', async () => {
            client.restClient.getKline.mockResolvedValue({
                retCode: 0,
                result: {
                    list: [
                        ['1678886400000', '30000', '30100', '29900', '30050', '100'],
                        ['1678886460000', '30050', '30150', '29950', '30100', '120']
                    ]
                }
            });

            const klines = await client.getKlines('BTCUSDT', '1', 2);
            expect(klines).toHaveLength(2);
            expect(klines[0].close.toString()).toBe('30050');
            expect(klines[1].open.toString()).toBe('30050');
            expect(klines[0].time).toBe(1678886400000);
        });

        test('should return empty array on API error', async () => {
            client.restClient.getKline.mockResolvedValue({ retCode: 10001, retMsg: 'Error' });
            const klines = await client.getKlines('BTCUSDT', '1', 1);
            expect(klines).toBeNull();
        });

        test('should return simulated klines in dry run mode', async () => {
            client.dryRun = true;
            const klines = await client.getKlines('BTCUSDT', '1', 5);
            expect(klines).toHaveLength(5);
            expect(klines[0]).toHaveProperty('open');
            expect(klines[0].open).toBeInstanceOf(Decimal);
        });
    });

    describe('placeOrder', () => {
        test('should call restClient.submitOrder and return orderId on success', async () => {
            client.restClient.submitOrder.mockResolvedValue({ retCode: 0, result: { orderId: 'testOrderId' } });
            const result = await client.placeOrder({ symbol: 'BTCUSDT', side: 'Buy', qty: '0.001', orderType: 'Market' });
            expect(client.restClient.submitOrder).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'BTCUSDT' }));
            expect(result).toEqual({ orderId: 'testOrderId' });
        });

        test('should return null on API error', async () => {
            client.restClient.submitOrder.mockResolvedValue({ retCode: 10001, retMsg: 'Error' });
            const result = await client.placeOrder({ symbol: 'BTCUSDT', side: 'Buy', qty: '0.001', orderType: 'Market' });
            expect(result).toBeNull();
        });

        test('should log and return simulated order in dry run mode', async () => {
            client.dryRun = true;
            const result = await client.placeOrder({ symbol: 'BTCUSDT', side: 'Buy', qty: '0.001', orderType: 'Market' });
            expect(result).toHaveProperty('orderId');
            expect(result).toHaveProperty('status', 'FILLED');
        });
    });

    describe('getWalletBalance', () => {
        test('should return wallet balance on success', async () => {
            client.restClient.getWalletBalance.mockResolvedValue({
                retCode: 0,
                result: { list: [{ coin: [{ coin: 'USDT', walletBalance: '5000.00' }] }] }
            });
            const balance = await client.getWalletBalance('USDT');
            expect(balance.toString()).toBe('5000.00');
        });

        test('should return simulated balance in dry run mode', async () => {
            client.dryRun = true;
            const balance = await client.getWalletBalance('USDT');
            expect(balance).toBeInstanceOf(Decimal);
            expect(balance.toString()).toBe('10000.00');
        });
    });

    describe('closePosition', () => {
        test('should close position successfully', async () => {
            client.getPositionInfo = jest.fn().mockResolvedValue([{ side: 'Buy', size: '0.01' }]);
            client.restClient.submitOrder.mockResolvedValue({ retCode: 0, result: { orderId: 'closeOrderId' } });

            const result = await client.closePosition('BTCUSDT');
            expect(client.getPositionInfo).toHaveBeenCalledWith('BTCUSDT');
            expect(client.restClient.submitOrder).toHaveBeenCalledWith(expect.objectContaining({
                symbol: 'BTCUSDT',
                side: 'Sell',
                orderType: 'Market',
                qty: '0.01',
                reduceOnly: true,
            }));
            expect(result).toEqual({ success: true });
        });

        test('should not attempt to close if no open position', async () => {
            client.getPositionInfo = jest.fn().mockResolvedValue([]);
            const result = await client.closePosition('BTCUSDT');
            expect(client.getPositionInfo).toHaveBeenCalledWith('BTCUSDT');
            expect(client.restClient.submitOrder).not.toHaveBeenCalled();
            expect(result).toEqual({ success: true });
        });

        test('should return simulated success in dry run mode', async () => {
            client.dryRun = true;
            const result = await client.closePosition('BTCUSDT');
            expect(result).toEqual({ success: true });
        });
    });

    describe('connectWebSocket', () => {
        test('should subscribe to kline topic', () => {
            client.connectWebSocket('BTCUSDT', '1');
            expect(client.wsClient.subscribeV5).toHaveBeenCalledWith('kline.1.BTCUSDT', 'linear');
        });

        test('should not connect if already connected', () => {
            client.wsConnected = true;
            client.connectWebSocket('BTCUSDT', '1');
            expect(client.wsClient.subscribeV5).not.toHaveBeenCalled();
        });

        test('should handle WebSocket open event', () => {
            client.connectWebSocket('BTCUSDT', '1');
            const openHandler = client.wsClient.on.mock.calls.find(call => call[0] === 'open')[1];
            openHandler();
            expect(client.wsConnected).toBe(true);
        });

        test('should handle WebSocket update event for kline data', () => {
            client.connectWebSocket('BTCUSDT', '1');
            const updateHandler = client.wsClient.on.mock.calls.find(call => call[0] === 'update')[1];
            const mockKlineData = {
                topic: 'kline.1.BTCUSDT',
                data: [{
                    start: '1678886400000',
                    open: '30000',
                    high: '30100',
                    low: '29900',
                    close: '30050',
                    volume: '100',
                    confirm: true
                }]
            };
            updateHandler(mockKlineData);
            expect(client.klinesData).toHaveLength(1);
            expect(client.klinesData[0].close.toString()).toBe('30050');
        });

        test('should update existing kline if time matches', () => {
            client.klinesData = [{
                time: 1678886400000,
                open: new Decimal('30000'),
                high: new Decimal('30100'),
                low: new Decimal('29900'),
                close: new Decimal('30050'),
                volume: new Decimal('100'),
            }];
            client.connectWebSocket('BTCUSDT', '1');
            const updateHandler = client.wsClient.on.mock.calls.find(call => call[0] === 'update')[1];
            const mockKlineData = {
                topic: 'kline.1.BTCUSDT',
                data: [{
                    start: '1678886400000',
                    open: '30000',
                    high: '30100',
                    low: '29900',
                    close: '30200',
                    volume: '150',
                    confirm: true
                }]
            };
            updateHandler(mockKlineData);
            expect(client.klinesData).toHaveLength(1);
            expect(client.klinesData[0].close.toString()).toBe('30200');
        });

        test('should add new kline and maintain limit', () => {
            client.klinesData = Array(200).fill(0).map((_, i) => ({
                time: 1678886400000 + i * 60000,
                open: new Decimal('100'), high: new Decimal('100'), low: new Decimal('100'), close: new Decimal('100'), volume: new Decimal('100')
            }));
            client.connectWebSocket('BTCUSDT', '1');
            const updateHandler = client.wsClient.on.mock.calls.find(call => call[0] === 'update')[1];
            const mockKlineData = {
                topic: 'kline.1.BTCUSDT',
                data: [{
                    start: '1678886400000' + 200 * 60000,
                    open: '30000',
                    high: '30100',
                    low: '29900',
                    close: '30200',
                    volume: '150',
                    confirm: true
                }]
            };
            updateHandler(mockKlineData);
            expect(client.klinesData).toHaveLength(200);
            expect(client.klinesData[0].time).toBe(1678886400000 + 1 * 60000); // First element shifted out
            expect(client.klinesData[199].close.toString()).toBe('30200'); // New element at the end
        });
    });
});
