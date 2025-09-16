import { jest } from '@jest/globals';
import { Decimal } from 'decimal.js';

// Mock the bybit-api library
const mockGetWalletBalance = jest.fn();
const mockGetPositionInfo = jest.fn();
const mockGetTickers = jest.fn();
const mockGetKlines = jest.fn();
const mockGetOrderbook = jest.fn();
const mockGetInstrumentsInfo = jest.fn();
const mockSetLeverage = jest.fn();
const mockPlaceOrder = jest.fn();
const mockCancelAllOrders = jest.fn();
const mockSetTradingStop = jest.fn();
const mockGetOpenOrders = jest.fn();

jest.mock('bybit-api', () => ({
  RestClientV5: jest.fn().mockImplementation(() => ({
    getWalletBalance: mockGetWalletBalance,
    getPositionInfo: mockGetPositionInfo,
    getTickers: mockGetTickers,
    getKlines: mockGetKlines,
    getOrderbook: mockGetOrderbook,
    getInstrumentsInfo: mockGetInstrumentsInfo,
    setLeverage: mockSetLeverage,
    placeOrder: mockPlaceOrder,
    cancelAllOrders: mockCancelAllOrders,
    setTradingStop: mockSetTradingStop,
    getOpenOrders: mockGetOpenOrders,
  })),
}));

// Mock the CONFIG and logger modules
const mockConfig = {
  API_KEY: 'test_key',
  API_SECRET: 'test_secret',
  TESTNET: true,
  DRY_RUN: false,
  ORDER_RETRY_ATTEMPTS: 3,
  ORDER_RETRY_DELAY_SECONDS: 0.01, // Short delay for tests
  TRADE_MANAGEMENT: { // Required by some strategies
    TRADING_FEE_PERCENT: 0.0005,
    ACCOUNT_BALANCE: 10000,
    RISK_PER_TRADE_PERCENT: 0.01,
    STOP_LOSS_ATR_MULTIPLE: 1.5,
    TAKE_PROFIT_ATR_MULTIPLE: 2.0,
    MAX_OPEN_POSITIONS: 1,
    ORDER_PRECISION: 5,
    PRICE_PRECISION: 3,
    SLIPPAGE_PERCENT: 0.001,
  },
  EXECUTION: {
    USE_PYBIT: true,
    TP_SCHEME: {},
    SL_SCHEME: {},
  },
  INDICATOR_SETTINGS: { // Required by some strategies
    STOCH_K_PERIOD: 14,
    STOCH_D_PERIOD: 3,
    STOCH_SMOOTHING: 3,
  },
};

jest.mock('../config.js', () => ({
  CONFIG: mockConfig,
}));

jest.mock('../logger.js', () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
    critical: jest.fn(),
  },
  neon: {
    header: jest.fn(str => str),
    info: jest.fn(str => str),
    success: jest.fn(str => str),
    warn: jest.fn(str => str),
    error: jest.fn(str => str),
    critical: jest.fn(str => str),
    dim: jest.fn(str => str),
    price: jest.fn(str => str),
    pnl: jest.fn(str => str),
    bid: jest.fn(str => str),
    ask: jest.fn(str => str),
    blue: jest.fn(str => str),
    purple: jest.fn(str => str),
    cyan: jest.fn(str => str),
    magenta: jest.fn(str => str),
  },
}));

// Mock uuid for consistent dry run order IDs
jest.mock('uuid', () => ({
  v4: () => 'mock-uuid',
}));

// Mock setTimeout from timers/promises
jest.mock('timers/promises', () => ({
  setTimeout: jest.fn((ms) => new Promise(resolve => setTimeout(resolve, ms))),
}));

// Import the module to be tested AFTER all mocks
const { bybitClient } = await import('../bybit_api_client.js');

describe('BybitAPIClient', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
    // Reset the dry_run_positions tracker
    bybitClient._dry_run_positions = {};
  });

  describe('Initialization', () => {
    it('should initialize RestClientV5 with correct credentials and testnet setting', async () => {
      const { RestClientV5 } = await import('bybit-api'); // Use import here as bybit-api is mocked
      expect(RestClientV5).toHaveBeenCalledWith({
        key: mockConfig.API_KEY,
        secret: mockConfig.API_SECRET,
        testnet: mockConfig.TESTNET,
        category: 'linear',
      });
      expect(bybitClient.dry_run).toBe(mockConfig.DRY_RUN);
    });

    it('should exit process if API keys are missing and not in dry_run mode', async () => {
      const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {});
      mockConfig.API_KEY = '';
      mockConfig.API_SECRET = '';
      mockConfig.DRY_RUN = false;

      // Re-import the module to trigger constructor logic with new config
      await import('../bybit_api_client.js');

      expect(mockExit).toHaveBeenCalledWith(1);
      mockExit.mockRestore();
      // Restore config for other tests
      mockConfig.API_KEY = 'test_key';
      mockConfig.API_SECRET = 'test_secret';
    });

    it('should NOT exit process if API keys are missing but in dry_run mode', async () => {
      const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {});
      mockConfig.API_KEY = '';
      mockConfig.API_SECRET = '';
      mockConfig.DRY_RUN = true;

      await import('../bybit_api_client.js');

      expect(mockExit).not.toHaveBeenCalled();
      mockExit.mockRestore();
      // Restore config for other tests
      mockConfig.API_KEY = 'test_key';
      mockConfig.API_SECRET = 'test_secret';
    });
  });

  describe('_retryWrapper', () => {
    it('should retry on failure and return success on retry', async () => {
      mockGetWalletBalance.mockResolvedValueOnce({ retCode: 1, retMsg: 'Failed' });
      mockGetWalletBalance.mockResolvedValueOnce({ retCode: 1, retMsg: 'Failed again' });
      mockGetWalletBalance.mockResolvedValueOnce({ retCode: 0, result: { balance: 100 } });

      const resp = await bybitClient._retryWrapper(bybitClient.session.getWalletBalance);

      expect(mockGetWalletBalance).toHaveBeenCalledTimes(3);
      expect(resp.retCode).toBe(0);
      expect(bybitClient.logger.error).toHaveBeenCalledTimes(2);
    });

    it('should return error after max retries', async () => {
      mockGetWalletBalance.mockResolvedValue({ retCode: 1, retMsg: 'Failed' });

      const resp = await bybitClient._retryWrapper(bybitClient.session.getWalletBalance);

      expect(mockGetWalletBalance).toHaveBeenCalledTimes(mockConfig.ORDER_RETRY_ATTEMPTS);
      expect(resp.retCode).toBe(-1);
      expect(resp.retMsg).toBe('Max retries reached');
      expect(bybitClient.logger.error).toHaveBeenCalledTimes(mockConfig.ORDER_RETRY_ATTEMPTS);
    });

    it('should handle exceptions during API calls', async () => {
      mockGetWalletBalance.mockRejectedValue(new Error('Network error'));

      const resp = await bybitClient._retryWrapper(bybitClient.session.getWalletBalance);

      expect(mockGetWalletBalance).toHaveBeenCalledTimes(mockConfig.ORDER_RETRY_ATTEMPTS);
      expect(resp.retCode).toBe(-1);
      expect(resp.retMsg).toBe('Max retries reached');
      expect(bybitClient.logger.error).toHaveBeenCalledTimes(mockConfig.ORDER_RETRY_ATTEMPTS);
    });
  });

  describe('Public Methods (non-dry-run)', () => {
    beforeEach(() => {
      mockConfig.DRY_RUN = false;
    });

    it('getBalance should return wallet balance', async () => {
      mockGetWalletBalance.mockResolvedValueOnce({
        retCode: 0,
        result: { list: [{ coin: [{ coin: 'USDT', walletBalance: '1000.50' }] }] },
      });

      const balance = await bybitClient.getBalance('USDT');

      expect(mockGetWalletBalance).toHaveBeenCalledWith({ accountType: 'UNIFIED' });
      expect(balance).toBe(1000.50);
    });

    it('getPositions should return open positions', async () => {
      mockGetPositionInfo.mockResolvedValueOnce({
        retCode: 0,
        result: { list: [{ symbol: 'BTCUSDT', size: '0.01', side: 'Buy' }] },
      });

      const positions = await bybitClient.getPositions('USDT');

      expect(mockGetPositionInfo).toHaveBeenCalledWith({ category: 'linear', settleCoin: 'USDT' });
      expect(positions).toEqual([{ symbol: 'BTCUSDT', size: '0.01', side: 'Buy' }]);
    });

    it('klines should return formatted kline data', async () => {
      mockGetKlines.mockResolvedValueOnce({
        retCode: 0,
        result: { list: [['1678886400000', '10', '12', '9', '11', '100', '1000']] },
      });

      const klines = await bybitClient.klines('BTCUSDT', '1', 1);

      expect(mockGetKlines).toHaveBeenCalledWith({
        category: 'linear',
        symbol: 'BTCUSDT',
        interval: '1',
        limit: 1,
      });
      expect(klines).toEqual([
        {
          time: 1678886400000,
          open: 10,
          high: 12,
          low: 9,
          close: 11,
          volume: 100,
          turnover: 1000,
        },
      ]);
    });

    it('placeMarketOrder should place a market order', async () => {
      mockGetInstrumentsInfo.mockResolvedValueOnce({
        retCode: 0,
        result: { list: [{ priceFilter: { tickSize: '0.01' }, lotSizeFilter: { qtyStep: '0.001', minOrderQty: '0.001' } }] },
      });
      mockPlaceOrder.mockResolvedValueOnce({ retCode: 0, result: { orderId: 'test_order_id' } });

      const orderId = await bybitClient.placeMarketOrder('BTCUSDT', 'Buy', 0.01, 40000, 30000);

      expect(mockPlaceOrder).toHaveBeenCalledWith({
        category: 'linear',
        symbol: 'BTCUSDT',
        side: 'Buy',
        orderType: 'Market',
        qty: '0.01',
        timeInForce: 'GTC',
        reduceOnly: 0,
        takeProfit: '40000.00',
        tpTriggerBy: 'Market',
        stopLoss: '30000.00',
        slTriggerBy: 'Market',
      });
      expect(orderId).toBe('test_order_id');
    });
  });

  describe('Dry Run Methods', () => {
    beforeEach(() => {
      mockConfig.DRY_RUN = true;
    });

    it('getBalance should return simulated balance in dry run', async () => {
      const balance = await bybitClient.getBalance('USDT');
      expect(balance).toBe(10000.00);
      expect(mockGetWalletBalance).not.toHaveBeenCalled();
    });

    it('placeMarketOrder should simulate order placement in dry run', async () => {
      const orderId = await bybitClient.placeMarketOrder('BTCUSDT', 'Buy', 0.01, 40000, 30000);
      expect(orderId).toMatch(/^DRY_mock-uuid$/);
      expect(mockPlaceOrder).not.toHaveBeenCalled();
      expect(bybitClient._dry_run_positions['BTCUSDT']).toEqual({ side: 'Buy', size: 0.01 });
    });

    it('cancelAllOpenOrders should simulate cancellation in dry run', async () => {
      const resp = await bybitClient.cancelAllOpenOrders('BTCUSDT');
      expect(resp.retCode).toBe(0);
      expect(mockCancelAllOrders).not.toHaveBeenCalled();
    });
  });
});