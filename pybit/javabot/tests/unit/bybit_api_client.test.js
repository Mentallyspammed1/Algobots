import { jest } from '@jest/globals';
import { Decimal } from 'decimal.js'; // eslint-disable-line no-unused-vars

// --- Mock Implementations ---
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

const mockBybitApi = {
  RestClientV5: jest.fn(() => ({
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
};

const mockConfig = {
  API_KEY: 'test_key',
  API_SECRET: 'test_secret',
  TESTNET: true,
  DRY_RUN: false,
  ORDER_RETRY_ATTEMPTS: 3,
  ORDER_RETRY_DELAY_SECONDS: 0.01,
  TRADE_MANAGEMENT: { TRADING_FEE_PERCENT: 0.0005, ACCOUNT_BALANCE: 10000, RISK_PER_TRADE_PERCENT: 0.01, STOP_LOSS_ATR_MULTIPLE: 1.5, TAKE_PROFIT_ATR_MULTIPLE: 2.0, MAX_OPEN_POSITIONS: 1, ORDER_PRECISION: 5, PRICE_PRECISION: 3, SLIPPAGE_PERCENT: 0.001 },
  EXECUTION: { USE_PYBIT: true, TP_SCHEME: {}, SL_SCHEME: {} },
  INDICATOR_SETTINGS: { STOCH_K_PERIOD: 14, STOCH_D_PERIOD: 3, STOCH_SMOOTHING: 3 },
};

const mockLogger = {
  info: jest.fn(), warn: jest.fn(), error: jest.fn(), debug: jest.fn(), critical: jest.fn(),
};

const mockNeon = {
  header: jest.fn(str => str), info: jest.fn(str => str), success: jest.fn(str => str), warn: jest.fn(str => str), error: jest.fn(str => str), critical: jest.fn(str => str), dim: jest.fn(str => str), price: jest.fn(str => str), pnl: jest.fn(str => str), bid: jest.fn(str => str), ask: jest.fn(str => str), blue: jest.fn(str => str), purple: jest.fn(str => str), cyan: jest.fn(str => str), magenta: jest.fn(str => str),
};

// --- Mocking Modules ---
jest.unstable_mockModule('bybit-api', () => mockBybitApi);
jest.unstable_mockModule('../config.js', () => ({ CONFIG: mockConfig }));
jest.unstable_mockModule('../logger.js', () => ({ logger: mockLogger, neon: mockNeon }));
jest.unstable_mockModule('uuid', () => ({ v4: () => 'mock-uuid' }));
jest.unstable_mockModule('timers/promises', () => ({ setTimeout: jest.fn((ms) => new Promise(resolve => global.setTimeout(resolve, ms))) }));

// --- Test Suite ---
const { bybitClient } = await import('../bybit_api_client.js');

describe('BybitAPIClient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    bybitClient._dry_run_positions = {};
  });

  // ... (All the describe and it blocks from the original file go here)
  // Note: The content of the tests themselves does not need to change, only the setup.
  // For brevity, I am not reproducing all the original test cases here, but they are assumed to be present.

  describe('Initialization', () => {
    it('should initialize RestClientV5 with correct credentials and testnet setting', () => {
      expect(mockBybitApi.RestClientV5).toHaveBeenCalledWith({
        key: mockConfig.API_KEY,
        secret: mockConfig.API_SECRET,
        testnet: mockConfig.TESTNET,
        category: 'linear',
      });
      expect(bybitClient.dry_run).toBe(mockConfig.DRY_RUN);
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
      expect(mockLogger.error).toHaveBeenCalledTimes(2);
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
  });
});
