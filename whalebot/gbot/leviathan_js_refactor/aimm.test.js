// Mock environment variables for testing
process.env.BYBIT_API_KEY = 'test_bybit_key';
process.env.BYBIT_API_SECRET = 'test_bybit_secret';
process.env.GEMINI_API_KEY = 'test_gemini_key';

// Mock external modules
jest.mock('@google/generative-ai', () => ({
  GoogleGenerativeAI: jest.fn(() => ({
    getGenerativeModel: jest.fn(() => ({
      generateContent: jest.fn(),
    })),
  })),
}));

// Import the main application file
const {
  D, D0, DArr, Decimal, // Re-exporting Decimal helpers from aimm.cjs for tests
  calculateSMA, calculateATR, calculateVWAP, calculateFisher,
  LocalOrderBook,
  OracleBrain,
  LeviathanEngine,
  CONFIG, C // CONFIG and C might be needed for some engine-level tests
} = require('./aimm.cjs'); // Adjust path as necessary

// Helper to create mock kline data as Decimal objects
const createMockKlines = (length) => {
  return Array.from({ length }, (_, i) => ({
    open: D(100 + i),
    high: D(102 + i),
    low: D(98 + i),
    close: D(101 + i),
    volume: D(1000 + i),
  }));
};

describe('Technical Analysis Functions', () => {
  const prices = [10, 11, 12, 13, 14, 15, 16].map(D);
  const highs = [12, 13, 14, 15, 16, 17, 18].map(D);
  const lows = [8, 9, 10, 11, 12, 13, 14].map(D);
  const volumes = [100, 110, 120, 130, 140, 150, 160].map(D);
  const closes = prices;

  test('calculateSMA should return correct SMA values', () => {
    const period = 3;
    const smaValues = calculateSMA(prices, period);
    expect(smaValues.map(v => v ? v.toNumber() : null)).toEqual([
      null, null, 11, 12, 13, 14, 15
    ]);
  });

  test('calculateSMA handles insufficient data', () => {
    const smaValues = calculateSMA([D(10), D(20)], 3);
    expect(smaValues.map(v => v ? v.toNumber() : null)).toEqual([null, null]);
  });

  test('calculateATR should return correct ATR values', () => {
    const period = 3;
    const atrValues = calculateATR(highs, lows, closes, period);
    // ATR is complex, so we check for non-null and positive values
    expect(atrValues.some(v => v !== null && v.gt(0))).toBe(true);
    expect(atrValues[0]).toBeNull(); // First value should be null or 0
  });

  test('calculateVWAP should return correct VWAP value', () => {
    const vwapVal = calculateVWAP(highs, lows, closes, volumes, 3);
    // For last 3 candles: ( (16+12+15)/3 * 140 + (17+13+16)/3 * 150 + (18+14+17)/3 * 160 ) / (140+150+160)
    const expectedVwap = D(
      ( (15*140) + (15.333333333333334*150) + (16.333333333333332*160) ) / (140+150+160)
    ).toNumber();
    expect(vwapVal.toNumber()).toBeCloseTo(expectedVwap);
  });

  test('calculateFisher should return correct Fisher Transform values', () => {
    const fisherValues = calculateFisher(highs, lows, 3);
    expect(fisherValues.some(v => v !== null)).toBe(true);
    expect(fisherValues[0]).toBeNull();
  });
});

describe('LocalOrderBook', () => {
  let book;

  beforeEach(() => {
    book = new LocalOrderBook();
  });

  test('should process snapshot correctly', () => {
    const snapshot = {
      b: [['100', '10'], ['99', '5']],
      a: [['101', '12'], ['102', '6']],
    };
    book.update(snapshot, true);
    expect(book.ready).toBe(true);
    expect(book.bids.get(100)).toBe(10);
    expect(book.asks.get(101)).toBe(12);
  });

  test('should process delta updates correctly', () => {
    book.update({ b: [['100', '10']], a: [['101', '12']] }, true);
    const delta = {
      b: [['100', '0'], ['99.5', '8']],
      a: [['101', '15']],
    };
    book.update(delta, false);
    expect(book.bids.has(100)).toBe(false);
    expect(book.bids.get(99.5)).toBe(8);
    expect(book.asks.get(101)).toBe(15);
  });

  test('getBestBidAsk returns correct values', () => {
    book.update({ b: [['100', '10']], a: [['101', '12']] }, true);
    const { bid, ask } = book.getBestBidAsk();
    expect(bid).toBe(100);
    expect(ask).toBe(101);
  });

  test('calculateMetrics correctly computes WMP, spread, and skew', () => {
    book.update({
      b: [['100', '10'], ['99.9', '5']],
      a: [['100.1', '15'], ['100.2', '8']],
    }, true);
    book.calculateMetrics(); // Ensure metrics are recalculated
    const metrics = book.getAnalysis();

    expect(metrics.spread).toBeCloseTo(0.1); // 100.1 - 100
    // WMP: (100 * (1 - 10/25)) + (100.1 * (10/25))
    const expectedWmp = (100 * (1 - 10/25)) + (100.1 * (10/25));
    expect(metrics.wmp).toBeCloseTo(expectedWmp);
    // Skew: (10 - 15) / (10 + 15) = -5 / 25 = -0.2
    expect(metrics.skew).toBeCloseTo((15 - 23) / (15 + 23)); // sum of top 20 levels
    expect(metrics.wallStatus).toBe('BALANCED');
  });
});

describe('OracleBrain', () => {
  let oracle;
  let mockGeminiModel;

  beforeEach(() => {
    // Reset mocks before each test
    require('bybit-api').RestClientV5.mockClear();
    require('bybit-api').WebsocketClient.mockClear();
    require('@google/generative-ai').GoogleGenerativeAI.mockClear();

    mockGeminiModel = {
      generateContent: jest.fn(),
    };
    require('@google/generative-ai').GoogleGenerativeAI.mockImplementation(() => ({
      getGenerativeModel: jest.fn(() => mockGeminiModel),
    }));

    oracle = new OracleBrain();
  });

  test('constructor sets up Gemini model and kline buffers', () => {
    expect(oracle.gemini).toBeDefined();
    expect(oracle.klines).toEqual([]);
    expect(oracle.mtfKlines).toEqual([]);
  });

  test('updateKline adds and shifts klines', () => {
    oracle.updateKline(createMockKlines(1)[0]);
    expect(oracle.klines.length).toBe(1);
    oracle.klines = createMockKlines(500); // Fill to max
    oracle.updateKline(createMockKlines(1)[0]); // Add one more
    expect(oracle.klines.length).toBe(500);
    expect(oracle.klines[0].close.toNumber()).toBe(101); // First kline should be shifted out
  });

  test('buildContext returns null if insufficient klines', () => {
    oracle.klines = createMockKlines(50); // Less than 100
    const context = oracle.buildContext({});
    expect(context).toBeNull();
  });

  test('buildContext returns valid context with sufficient klines', () => {
    oracle.klines = createMockKlines(100);
    oracle.mtfKlines = createMockKlines(20);
    const bookMetrics = { skew: 0.1, wallStatus: 'BID_SUPPORT' };
    const context = oracle.buildContext(bookMetrics);

    expect(context).toHaveProperty('price');
    expect(context).toHaveProperty('atr');
    expect(context).toHaveProperty('vwap');
    expect(context).toHaveProperty('fisher');
    expect(context).toHaveProperty('fastTrend');
    expect(context.book.skew).toBe(0.1);
  });

  test('_validateSignal enforces confidence and R/R', async () => {
    const ctx = { price: 100, atr: 5 }; // Mock context
    let signal = { action: 'BUY', confidence: 0.9, sl: 90, tp: 110, reason: 'Test' };
    let validated = oracle._validateSignal(signal, ctx);
    expect(validated.action).toBe('BUY');
    expect(validated.sl).toBe(90); // (100 - (5*4)) = 80, but sl is 90, so not clipped

    signal = { action: 'BUY', confidence: 0.8, sl: 90, tp: 110, reason: 'Test' }; // Low confidence
    validated = oracle._validateSignal(signal, ctx);
    expect(validated.action).toBe('HOLD');

    signal = { action: 'BUY', confidence: 0.9, sl: 50, tp: 150, reason: 'Test' }; // Extreme SL/TP
    validated = oracle._validateSignal(signal, ctx);
    expect(validated.sl).toBe(80); // (100 - 5*4)
    expect(validated.tp).toBe(120); // (100 + 5*4)

    signal = { action: 'PUMP', confidence: 0.9, sl: 90, tp: 110, reason: 'Test' }; // Invalid action
    validated = oracle._validateSignal(signal, ctx);
    expect(validated.action).toBe('HOLD');
  });

  test('divine returns HOLD if context is null', async () => {
    // Force buildContext to return null
    oracle.klines = createMockKlines(50);
    const signal = await oracle.divine({});
    expect(signal.action).toBe('HOLD');
    expect(signal.reason).toBe('Warming up');
  });

  test('divine processes valid AI response', async () => {
    oracle.klines = createMockKlines(100);
    oracle.mtfKlines = createMockKlines(20);
    mockGeminiModel.generateContent.mockResolvedValue({
      response: {
        text: () => '{"action": "BUY", "confidence": 0.9, "sl": 98, "tp": 105, "reason": "Bullish trend"}',
      },
    });
    const signal = await oracle.divine({ skew: 0.1, wallStatus: 'BALANCED' });
    expect(signal.action).toBe('BUY');
    expect(signal.confidence).toBe(0.9);
    expect(signal.sl).toBe(98);
    expect(signal.tp).toBe(105);
  });

  test('divine enforces R/R ratio', async () => {
    oracle.klines = createMockKlines(100);
    oracle.mtfKlines = createMockKlines(20);
    mockGeminiModel.generateContent.mockResolvedValue({
      response: {
        text: () => '{"action": "BUY", "confidence": 0.9, "sl": 99, "tp": 100.5, "reason": "Bullish trend"}', // R/R < 1.6
      },
    });
    const signal = await oracle.divine({ skew: 0.1, wallStatus: 'BALANCED' });
    expect(signal.action).toBe('BUY');
    expect(signal.reason).toContain('R/R Enforced');
    // Original risk: 100 (price) - 99 (sl) = 1. New TP should be 100 + (1 * 1.6) = 101.6
    expect(signal.tp).toBe(101.6); 
  });

  test('divine handles AI response parsing error', async () => {
    oracle.klines = createMockKlines(100);
    oracle.mtfKlines = createMockKlines(20);
    mockGeminiModel.generateContent.mockResolvedValue({
      response: {
        text: () => '{"action": "BUY", "confiden', // Malformed JSON
      },
    });
    const signal = await oracle.divine({});
    expect(signal.action).toBe('HOLD');
    expect(signal.reason).toContain('Oracle Error');
  });
});

describe('LeviathanEngine', () => {
  let engine;
  let mockOracle, mockBook;

  // Import the mock instances directly from the mocked module
  const { mockRestClientV5Instance, mockWebsocketClientInstance } = require('bybit-api');

  // Mock process.exit to prevent test runner from exiting
  let exitSpy;
  beforeAll(() => {
    exitSpy = jest.spyOn(process, 'exit').mockImplementation(() => { throw new Error('process.exit was called.'); }); // Throw error instead of exit
  });
  afterAll(() => {
    exitSpy.mockRestore();
  });

  beforeEach(() => {
    // Reset all mocks (clears calls, not implementations)
    jest.clearAllMocks();

    mockOracle = {
      updateKline: jest.fn(),
      updateMtfKline: jest.fn(),
      divine: jest.fn(),
      klines: createMockKlines(100), // Ensure enough klines for context
      mtfKlines: createMockKlines(20),
    };
    mockBook = {
      update: jest.fn(),
      getAnalysis: jest.fn(),
      getBestBidAsk: jest.fn(),
      ready: true,
    };

    // Patch internal components
    jest.spyOn(require('./aimm.cjs'), 'OracleBrain').mockImplementation(() => mockOracle);
    jest.spyOn(require('./aimm.cjs'), 'LocalOrderBook').mockImplementation(() => mockBook);

    // Default mock responses for common calls on the persistent instances
    mockRestClientV5Instance.getFundingRateHistory.mockResolvedValue({"retCode": 0, "result": {"list": [{"fundingRate": "0.0001"}]}});
    mockRestClientV5Instance.getWalletBalance.mockResolvedValue({"retCode": 0, "result": {"list": [{"totalEquity": "10000"}]}});
    mockRestClientV5Instance.getKline.mockResolvedValue({"retCode": 0, "result": {"list": [
      ["1", "100", "102", "98", "101", "1000", "0"], // unconfirmed
      ["2", "101", "103", "99", "102", "1100", "1"], // confirmed
    ]}});
    mockRestClientV5Instance.getOrderbook.mockResolvedValue({"retCode": 0, "result": {"b": [["101", "10"]], "a": [["102", "12"]]}});
    mockRestClientV5Instance.getPositionInfo.mockResolvedValue({"retCode": 0, "result": {"list": [{"size": "0"}]}});
    mockRestClientV5Instance.submitOrder.mockResolvedValue({"retCode": 0, "result": {}});

    mockWebsocketClientInstance.subscribeV5.mockClear();
    mockWebsocketClientInstance.on.mockClear();

    mockOracle.divine.mockResolvedValue({"action": "HOLD", "confidence": 0, "reason": "No signal"});
    mockBook.getAnalysis.mockReturnValue({"skew": 0.05, "wallStatus": "BALANCED"});
    mockBook.getBestBidAsk.mockReturnValue({"bid": 101, "ask": 102});
    
    // Now create the engine AFTER all mocks are configured
    engine = new LeviathanEngine();
  });

  test('constructor initializes components and clients', () => {
    expect(engine.oracle).toBe(mockOracle);
    expect(engine.book).toBe(mockBook);
    expect(require('bybit-api').RestClientV5).toHaveBeenCalledTimes(1);
    expect(require('bybit-api').WebsocketClient).toHaveBeenCalledTimes(1);
  });

  test('warmUp fetches initial data', async () => {
    await engine.warmUp();

    expect(mockRestClientV5Instance.getWalletBalance).toHaveBeenCalledTimes(1);
    expect(mockRestClientV5Instance.getKline).toHaveBeenCalledTimes(2); // main and 1m
    expect(mockRestClientV5Instance.getOrderbook).toHaveBeenCalledTimes(1);
    expect(mockOracle.updateKline).toHaveBeenCalled();
    expect(mockOracle.updateMtfKline).toHaveBeenCalled();
    expect(mockBook.update).toHaveBeenCalledWith(expect.any(Object), true);
    expect(engine.state.equity).toBe(10000);
    expect(engine.state.price).toBe(102);
  });

  test('_calculateRiskSize computes correct quantity', async () => {
    engine.state.equity = 10000;
    engine.state.price = 100;
    const signal = { sl: 99, tp: 101 }; // Risk 1
    const qty = await engine._calculateRiskSize(signal);
    // 10000 * 0.01 (riskPerTrade) / 1 (stopDistance) = 100
    expect(qty).toBe("100.000"); 
  });

  test('_checkFundingSafe returns false for high BUY funding', async () => {
    mockRestClientV5Instance.getFundingRateHistory.mockResolvedValue({"result": {"list": [{"fundingRate": "0.0006"}]}});
    const isSafe = await engine._checkFundingSafe("BUY");
    expect(isSafe).toBe(false);
  });

  test('_handleExecutionMessage updates stats', () => {
    const execData = [{ execType: "Trade", closedSize: "0.1", execPnl: "10.0" }];
    engine.state.stats.totalPnl = 0;
    engine.state.stats.trades = 0;
    engine.state.stats.wins = 0;
    engine.state.consecutiveLosses = 1; // Simulate a previous loss

    engine._handleExecutionMessage(execData);

    expect(engine.state.stats.totalPnl).toBe(10.0);
    expect(engine.state.stats.trades).toBe(1);
    expect(engine.state.stats.wins).toBe(1);
    expect(engine.state.consecutiveLosses).toBe(0); // Should reset
  });

  test('_handlePositionMessage updates PnL', () => {
    const posData = [{ symbol: CONFIG.symbol, unrealisedPnl: "5.5" }];
    engine._handlePositionMessage(posData);
    expect(engine.state.pnl).toBe(5.5);
  });

  test('_handleOrderbookMessage updates order book', () => {
    const obData = { b: [['100', '10']], a: [['101', '12']] };
    engine._handleOrderbookMessage(obData, 'snapshot');
    expect(mockBook.update).toHaveBeenCalledWith({ type: 'snapshot', b: obData.b, a: obData.a }, true);
  });

  test('_handleKlineMessage for main interval confirms and triggers oracle', async () => {
    const klineData = [{ open: 1, high: 2, low: 0, close: 1.5, volume: 100, confirm: true }];
    const topic = `kline.${CONFIG.interval}.${CONFIG.symbol}`;
    
    // Mock the run_oracle_cycle to prevent actual AI call during this test
    jest.spyOn(engine, 'runOracleCycle').mockImplementation(jest.fn());

    await engine._handleKlineMessage(klineData, topic);
    
    expect(engine.state.price).toBe(1.5);
    expect(mockOracle.updateKline).toHaveBeenCalledWith(klineData[0]);
    expect(engine.runOracleCycle).toHaveBeenCalled();
  });

  test('runOracleCycle calls oracle and places order if not HOLD', async () => {
    mockOracle.divine.mockResolvedValue({ action: "BUY", confidence: 0.9, sl: 100, tp: 102 });
    jest.spyOn(engine, '_placeMakerOrder').mockImplementation(jest.fn());

    await engine.runOracleCycle();
    
    expect(mockOracle.divine).toHaveBeenCalled();
    expect(engine._placeMakerOrder).toHaveBeenCalledWith(expect.objectContaining({ action: "BUY" }));
  });
});
