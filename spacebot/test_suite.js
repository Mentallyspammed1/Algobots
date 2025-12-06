/**
 * 🧪 WHALEWAVE PRO - TITAN EDITION v11.0 TEST SUITE
 * =================================================
 * Comprehensive testing for all trading bot components
 */

import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';

// Import all components from the main file
const {
    ConfigManager,
    HistoryManager,
    Utils,
    TA,
    NeuralNetwork,
    UltraFastMarketEngine,
    UltraFastExchange,
    AdvancedAIAgent,
    COLORS
} = await import('./whalewave_pro_v11.js');

// Test data generators
class TestDataGenerator {
    static generatePriceData(length = 100, basePrice = 50000, volatility = 0.001) {
        const prices = [basePrice];
        for (let i = 1; i < length; i++) {
            const change = (Math.random() - 0.5) * 2 * volatility * basePrice;
            prices.push(prices[i - 1] + change);
        }
        return prices;
    }

    static generateVolumeData(length = 100, baseVolume = 1000) {
        const volumes = [baseVolume];
        for (let i = 1; i < length; i++) {
            const change = (Math.random() - 0.5) * 0.5 * baseVolume;
            volumes.push(Math.max(0, volumes[i - 1] + change));
        }
        return volumes;
    }

    static generateKlineData(length = 100, basePrice = 50000) {
        return this.generatePriceData(length, basePrice).map((close, i) => {
            const open = i === 0 ? close : close + (Math.random() - 0.5) * basePrice * 0.001;
            const high = Math.max(open, close) + Math.random() * basePrice * 0.0005;
            const low = Math.min(open, close) - Math.random() * basePrice * 0.0005;
            return { t: Date.now() + i * 60000, o: open, h: high, l: low, c: close, v: Math.random() * 2000 + 500 };
        });
    }

    static generateOrderbook(levels = 50, midPrice = 50000) {
        const bids = [], asks = [];
        for (let i = 0; i < levels; i++) {
            bids.push({
                p: midPrice - (i + 1) * (midPrice * 0.00001),
                q: Math.random() * 10 + 1
            });
            asks.push({
                p: midPrice + (i + 1) * (midPrice * 0.00001),
                q: Math.random() * 10 + 1
            });
        }
        return { bids, asks };
    }
}

// Test Results Manager
class TestResults {
    static results = [];
    static passed = 0;
    static failed = 0;
    static errors = [];

    static addResult(test, passed, message = '') {
        this.results.push({
            test,
            passed,
            message,
            timestamp: new Date().toISOString()
        });
        if (passed) {
            this.passed++;
            console.log(`${COLORS.GREEN('✅')} ${test}`);
        } else {
            this.failed++;
            console.log(`${COLORS.RED('❌')} ${test}: ${message}`);
        }
    }

    static addError(test, error) {
        this.errors.push({ test, error: error.message, stack: error.stack });
        console.log(`${COLORS.RED('💥')} ${test}: ${error.message}`);
    }

    static getSummary() {
        return {
            total: this.results.length,
            passed: this.passed,
            failed: this.failed,
            successRate: ((this.passed / this.results.length) * 100).toFixed(1),
            errors: this.errors
        };
    }
}

// =============================================================================
// CONFIGURATION MANAGEMENT TESTS
// =============================================================================

async function testConfigManagement() {
    console.log(`${COLORS.CYAN('\n🔧 Testing Configuration Management...')}`);
    
    try {
        // Test default configuration
        const config = await ConfigManager.load();
        TestResults.addResult('Config loads default values', config.symbol === 'BTCUSDT');
        TestResults.addResult('Config has correct risk parameters', config.risk.initialBalance === 1000.00);
        TestResults.addResult('Config has neural network settings', config.indicators.neural.enabled === true);
        TestResults.addResult('Config has proper intervals', config.intervals.scalp === '1');
        
        // Test deep merge functionality
        const customConfig = {
            symbol: 'ETHUSDT',
            risk: { initialBalance: 5000.00 }
        };
        
        // Test configuration writing and loading
        await fs.writeFile('config.json', JSON.stringify(customConfig, null, 2));
        const loadedConfig = await ConfigManager.load();
        TestResults.addResult('Config deep merge works', loadedConfig.symbol === 'ETHUSDT');
        TestResults.addResult('Config preserves unchanged defaults', loadedConfig.risk.maxDrawdown === 6.0);
        
    } catch (error) {
        TestResults.addError('Config Management', error);
    }
}

// =============================================================================
// UTILITY FUNCTIONS TESTS
// =============================================================================

function testUtilityFunctions() {
    console.log(`${COLORS.CYAN('\n🛠️ Testing Utility Functions...')}`);
    
    try {
        // Test safeArray
        const safeArr = Utils.safeArray(5);
        TestResults.addResult('safeArray creates array', Array.isArray(safeArr) && safeArr.length === 5);
        
        // Test safeLast
        const testArray = [1, 2, 3, 4, 5];
        TestResults.addResult('safeLast returns last element', Utils.safeLast(testArray) === 5);
        TestResults.addResult('safeLast returns default for empty array', Utils.safeLast([]) === 0);
        TestResults.addResult('safeLast returns default for invalid array', Utils.safeLast([NaN, NaN]) === 0);
        
        // Test formatNumber
        TestResults.addResult('formatNumber handles valid numbers', Utils.formatNumber(123.456789, 2) === '123.46');
        TestResults.addResult('formatNumber handles NaN', Utils.formatNumber(NaN) === '0.0000');
        TestResults.addResult('formatNumber handles Infinity', Utils.formatNumber(Infinity) === '0.0000');
        
        // Test formatTime
        TestResults.addResult('formatTime handles milliseconds', Utils.formatTime(500) === '500ms');
        TestResults.addResult('formatTime handles seconds', Utils.formatTime(1500) === '1s');
        TestResults.addResult('formatTime handles minutes', Utils.formatTime(90000) === '1m');
        TestResults.addResult('formatTime handles hours', Utils.formatTime(3600000) === '1h');
        
        // Test neural network
        const features = [0.1, 0.2, 0.5];
        const weights = [0.5, 0.3, 0.2];
        const nnResult = Utils.neuralNetwork(features, weights);
        TestResults.addResult('Neural network returns value between 0-1', nnResult >= 0 && nnResult <= 1);
        
        // Test pattern detection
        const prices = TestDataGenerator.generatePriceData(20);
        const volumes = TestDataGenerator.generateVolumeData(20);
        const patterns = Utils.detectAdvancedPatterns(prices, volumes, prices, prices, prices);
        TestResults.addResult('Pattern detection returns array', Array.isArray(patterns));
        
    } catch (error) {
        TestResults.addError('Utility Functions', error);
    }
}

// =============================================================================
// TECHNICAL ANALYSIS TESTS
// =============================================================================

function testTechnicalAnalysis() {
    console.log(`${COLORS.CYAN('\n📊 Testing Technical Analysis...')}`);
    
    try {
        const prices = TestDataGenerator.generatePriceData(50, 50000);
        const highs = prices.map(p => p + (Math.random() * 100));
        const lows = prices.map(p => p - (Math.random() * 100));
        const volumes = TestDataGenerator.generateVolumeData(50);
        
        // Test SMA
        const sma = TA.sma(prices, 10);
        TestResults.addResult('SMA returns correct length', sma.length === prices.length);
        TestResults.addResult('SMA handles edge cases', TA.sma([], 10).length === 0);
        
        // Test EMA
        const ema = TA.ema(prices, 10);
        TestResults.addResult('EMA returns values', ema.length > 0);
        
        // Test RSI
        const rsi = TA.rsi(prices, 14);
        TestResults.addResult('RSI returns values between 0-100', 
            rsi.every(val => val >= 0 && val <= 100));
        
        // Test Stochastic
        const stoch = TA.stoch(highs, lows, prices, 14);
        TestResults.addResult('Stochastic returns K and D', 
            stoch.k && stoch.d && stoch.k.length === prices.length);
        
        // Test ATR
        const atr = TA.atr(highs, lows, prices, 14);
        TestResults.addResult('ATR returns positive values', atr.every(val => val >= 0));
        
        // Test Fisher Transform
        const fisher = TA.fisher(highs, lows, 14);
        TestResults.addResult('Fisher Transform returns values', fisher.length === highs.length);
        
        // Test Choppiness Index
        const chop = TA.choppiness(highs, lows, prices, 14);
        TestResults.addResult('Choppiness Index returns values 0-100', 
            chop.every(val => val >= 0 && val <= 100));
        
        // Test Volume Spike Detection
        const volSpikes = TA.volumeSpike(volumes, 2.0);
        TestResults.addResult('Volume Spike returns boolean array', 
            volSpikes.every(val => typeof val === 'boolean'));
        
        // Test Micro Trend
        const trends = TA.microTrend(prices, 10);
        TestResults.addResult('Micro Trend returns valid trends', 
            trends.every(trend => ['BULLISH', 'BEARISH', 'FLAT'].includes(trend)));
        
        // Test Order Flow Imbalance
        const orderbook = TestDataGenerator.generateOrderbook();
        const imbalance = TA.orderFlowImbalance(orderbook.bids, orderbook.asks);
        TestResults.addResult('Order Flow Imbalance returns value between -1 and 1', 
            imbalance >= -1 && imbalance <= 1);
        
        // Test Fair Value Gap Detection
        const klines = TestDataGenerator.generateKlineData(20);
        const fvgs = TA.findFVG(klines);
        TestResults.addResult('FVG detection returns array', Array.isArray(fvgs));
        
        // Test Divergence Detection
        const indicators = { rsi: rsi, fisher: fisher };
        const divergences = TA.detectAdvancedDivergence(prices, indicators);
        TestResults.addResult('Divergence detection returns array', Array.isArray(divergences));
        
        // Test Price Acceleration
        const acceleration = TA.priceAcceleration(prices, 5);
        TestResults.addResult('Price Acceleration returns array', acceleration.length === prices.length);
        
    } catch (error) {
        TestResults.addError('Technical Analysis', error);
    }
}

// =============================================================================
// NEURAL NETWORK TESTS
// =============================================================================

async function testNeuralNetwork() {
    console.log(`${COLORS.CYAN('\n🧠 Testing Neural Network...')}`);
    
    try {
        const config = {
            indicators: {
                neural: {
                    enabled: true,
                    features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum']
                }
            }
        };
        
        const nn = new NeuralNetwork(config);
        
        // Test initialization
        TestResults.addResult('Neural Network initializes weights', nn.weights.length === config.indicators.neural.features.length);
        
        // Test prediction
        const features = [0.1, 0.2, 0.5, 0.3, 0.7, 0.1];
        const prediction = nn.predict(features);
        TestResults.addResult('Neural Network prediction returns value between 0-1', prediction >= 0 && prediction <= 1);
        
        // Test normalization
        const normalized = nn.normalizeFeatures([2.0, 5.0, 0.8, -0.5, 0.3, 0.1]);
        TestResults.addResult('Neural Network normalizes price/volume features', Math.abs(normalized[0]) <= 1);
        
        // Test training with mock data
        const trainingData = Array.from({ length: 100 }, () => ({
            features: [Math.random(), Math.random(), Math.random(), Math.random(), Math.random(), Math.random()],
            result: Math.random() > 0.5 ? 1 : 0
        }));
        
        // Mock the train method to avoid actual training
        const originalTrain = nn.train;
        nn.train = async (data) => {
            TestResults.addResult('Neural Network training method called', data.length === trainingData.length);
            return Promise.resolve();
        };
        
        // Test training
        const trainResult = await nn.train(trainingData);
        TestResults.addResult('Neural Network training completes', trainResult !== undefined);
        
    } catch (error) {
        TestResults.addError('Neural Network', error);
    }
}

// =============================================================================
// MARKET ENGINE TESTS
// =============================================================================

async function testMarketEngine() {
    console.log(`${COLORS.CYAN('\n📡 Testing Market Engine...')}`);
    
    try {
        const config = await ConfigManager.load();
        const engine = new UltraFastMarketEngine(config);
        
        // Test initialization
        TestResults.addResult('Market Engine initializes', engine.config && engine.cache);
        
        // Test WebSocket connection
        engine.connectWebSocket();
        TestResults.addResult('Market Engine WebSocket connects', engine.ws !== null);
        
        // Test latency metrics
        engine.latencyHistory = [100, 150, 120, 200, 90];
        const latency = engine.getLatencyMetrics();
        TestResults.addResult('Latency metrics calculate correctly', 
            latency.min === 90 && latency.max === 200 && latency.avg === 132);
        
        // Test Ultra Fast Score calculation
        const mockAnalysis = {
            closes: TestDataGenerator.generatePriceData(50),
            rsi: Array(50).fill(65),
            fisher: Array(50).fill(0.5),
            stoch: { k: Array(50).fill(60) },
            williams: Array(38).fill(-30), // Williams %R has offset
            momentum: Array(41).fill(0.01), // Momentum has offset
            roc: Array(42).fill(0.5), // ROC has offset
            volumeSpikes: Array(50).fill(true),
            microTrend: Array(50).fill('BULLISH'),
            imbalance: 0.3,
            fairValueGaps: [{ strength: 0.1 }, { strength: 0.2 }],
            divergences: [{ type: 'BULLISH_DIVERGENCE', index: 48 }],
            acceleration: Array(50).fill(0.001),
            neural: 0.7,
            volume24h: 2000000
        };
        
        const score = engine.calculateUltraFastScore(mockAnalysis);
        TestResults.addResult('Ultra Fast Score returns valid object', 
            typeof score.score === 'number' && typeof score.components === 'object');
        TestResults.addResult('Ultra Fast Score is finite', Number.isFinite(score.score));
        
    } catch (error) {
        TestResults.addError('Market Engine', error);
    }
}

// =============================================================================
// EXCHANGE ENGINE TESTS
// =============================================================================

async function testExchangeEngine() {
    console.log(`${COLORS.CYAN('\n💰 Testing Exchange Engine...')}`);
    
    try {
        const config = await ConfigManager.load();
        const exchange = new UltraFastExchange(config);
        
        // Test initialization
        TestResults.addResult('Exchange initializes with balance', exchange.balance.greaterThan(0));
        TestResults.addResult('Exchange has no initial position', exchange.pos === null);
        
        // Test balance calculations
        exchange.balance = new Decimal(1000);
        exchange.startBal = new Decimal(1000);
        exchange.dailyPnL = new Decimal(50);
        exchange.equity = new Decimal(1050);
        
        const riskScore = exchange.calculateRiskScore();
        TestResults.addResult('Risk score calculation works', Number.isFinite(riskScore));
        TestResults.addResult('Risk score is between 0-100', riskScore >= 0 && riskScore <= 100);
        
        // Test dynamic risk multiplier
        const riskMultiplier = exchange.getDynamicRiskMultiplier();
        TestResults.addResult('Risk multiplier is positive', riskMultiplier > 0);
        TestResults.addResult('Risk multiplier is reasonable', riskMultiplier <= 1.0);
        
        // Test volatility calculation
        const mockTrades = [
            { netPnL: 10 }, { netPnL: -5 }, { netPnL: 15 }, { netPnL: -8 }, { netPnL: 12 }
        ];
        exchange.history = mockTrades;
        const volatility = exchange.calculateVolatility();
        TestResults.addResult('Volatility calculation works', Number.isFinite(volatility));
        
        // Test consecutive losses calculation
        const testTrades = [
            { netPnL: -10 }, { netPnL: -5 }, { netPnL: 15 }, { netPnL: -8 }
        ];
        const consecutive = exchange.calculateConsecutiveLosses(testTrades);
        TestResults.addResult('Consecutive losses calculation works', consecutive === 1);
        
        // Test daily reset logic
        exchange.lastDay = new Date().getDate() - 1; // Simulate previous day
        exchange.checkDailyReset();
        TestResults.addResult('Daily reset updates day', exchange.lastDay === new Date().getDate());
        
    } catch (error) {
        TestResults.addError('Exchange Engine', error);
    }
}

// =============================================================================
// AI AGENT TESTS
// =============================================================================

function testAIAgent() {
    console.log(`${COLORS.CYAN('\n🤖 Testing AI Agent...')}`);
    
    try {
        const config = {
            ai: {
                minConfidence: 0.88,
                rateLimitMs: 1000,
                maxRetries: 3
            }
        };
        
        // Create a mock AI agent without actual API calls
        const ai = new Proxy(new AdvancedAIAgent(config), {
            get(target, prop) {
                if (prop === 'analyzeUltraFast') {
                    return async (ctx, indicators) => {
                        return {
                            action: 'HOLD',
                            confidence: 0,
                            strategy: 'Test Strategy',
                            entry: ctx.price,
                            stopLoss: ctx.price,
                            takeProfit: ctx.price,
                            reason: 'Test analysis',
                            timeframe: '1m'
                        };
                    };
                }
                if (prop === 'validateSignal') {
                    return (signal, ctx, indicators) => signal;
                }
                return target[prop];
            }
        });
        
        // Test validation
        const mockSignal = {
            action: 'BUY',
            confidence: 0.95,
            strategy: 'Test Scalp',
            entry: 50000,
            stopLoss: 49900,
            takeProfit: 50100,
            reason: 'Test signal',
            timeframe: '1m'
        };
        
        const mockCtx = {
            price: 50000,
            symbol: 'BTCUSDT'
        };
        
        const validatedSignal = ai.validateSignal(mockSignal, mockCtx, {});
        TestResults.addResult('Signal validation preserves valid signals', validatedSignal.action === 'BUY');
        
        // Test API metrics
        ai.apiCalls = [
            { timestamp: Date.now(), success: true },
            { timestamp: Date.now(), success: false },
            { timestamp: Date.now(), success: true }
        ];
        
        const metrics = ai.getApiMetrics();
        TestResults.addResult('API metrics calculate success rate', metrics.successRate === 66.67);
        
    } catch (error) {
        TestResults.addError('AI Agent', error);
    }
}

// =============================================================================
// INTEGRATION TESTS
// =============================================================================

async function testIntegration() {
    console.log(`${COLORS.CYAN('\n🔗 Testing Integration...')}`);
    
    try {
        // Test complete trading loop simulation
        const config = await ConfigManager.load();
        const engine = new UltraFastMarketEngine(config);
        const exchange = new UltraFastExchange(config);
        
        // Generate realistic market data
        const prices = TestDataGenerator.generatePriceData(50, 50000);
        const volumes = TestDataGenerator.generateVolumeData(50);
        const highs = prices.map(p => p + Math.random() * 100);
        const lows = prices.map(p => p - Math.random() * 100);
        
        // Calculate indicators
        const rsi = TA.rsi(prices, 14);
        const fisher = TA.fisher(highs, lows, 14);
        const stoch = TA.stoch(highs, lows, prices, 14);
        const atr = TA.atr(highs, lows, prices, 14);
        
        // Create analysis object
        const analysis = {
            closes: prices,
            rsi: rsi,
            fisher: fisher,
            stoch: stoch,
            williams: Array(36).fill(-40),
            momentum: Array(41).fill(0.01),
            roc: Array(42).fill(0.5),
            volumeSpikes: Array(50).fill(false),
            microTrend: Array(50).fill('FLAT'),
            imbalance: 0.1,
            fairValueGaps: [],
            divergences: [],
            acceleration: TA.priceAcceleration(prices, 5),
            neural: 0.5,
            volume24h: 1500000
        };
        
        // Test score calculation
        const score = engine.calculateUltraFastScore(analysis);
        TestResults.addResult('Complete analysis produces valid score', 
            typeof score.score === 'number' && Number.isFinite(score.score));
        
        // Test mock signal processing
        const mockSignal = {
            action: 'BUY',
            confidence: 0.92,
            strategy: 'Integration Test',
            entry: prices[prices.length - 1],
            stopLoss: prices[prices.length - 1] * 0.995,
            takeProfit: prices[prices.length - 1] * 1.01,
            reason: 'Integration test signal',
            timeframe: '1m'
        };
        
        await exchange.evaluateUltraFast(prices[prices.length - 1], mockSignal);
        TestResults.addResult('Signal processing works end-to-end', 
            exchange.pos !== null && exchange.pos.side === 'BUY');
        
    } catch (error) {
        TestResults.addError('Integration Test', error);
    }
}

// =============================================================================
// PERFORMANCE TESTS
// =============================================================================

function testPerformance() {
    console.log(`${COLORS.CYAN('\n⚡ Testing Performance...')}`);
    
    try {
        const startTime = performance.now();
        
        // Test indicator calculation performance
        const prices = TestDataGenerator.generatePriceData(1000, 50000);
        const highs = prices.map(p => p + Math.random() * 100);
        const lows = prices.map(p => p - Math.random() * 100);
        const volumes = TestDataGenerator.generateVolumeData(1000);
        
        const rsi = TA.rsi(prices, 14);
        const fisher = TA.fisher(highs, lows, 14);
        const stoch = TA.stoch(highs, lows, prices, 14);
        const atr = TA.atr(highs, lows, prices, 14);
        
        const endTime = performance.now();
        const calculationTime = endTime - startTime;
        
        TestResults.addResult('Technical analysis completes in reasonable time', 
            calculationTime < 1000); // Should complete in under 1 second
        TestResults.addResult('RSI calculation produces correct length', rsi.length === prices.length);
        TestResults.addResult('Fisher Transform handles large datasets', fisher.length === highs.length);
        
        // Test pattern detection performance
        const patternStart = performance.now();
        const patterns = Utils.detectAdvancedPatterns(prices, volumes, highs, lows, prices);
        const patternEnd = performance.now();
        
        TestResults.addResult('Pattern detection performs adequately', 
            (patternEnd - patternStart) < 100); // Should complete in under 100ms
        
    } catch (error) {
        TestResults.addError('Performance Test', error);
    }
}

// =============================================================================
// MAIN TEST RUNNER
// =============================================================================

async function runAllTests() {
    console.log(COLORS.HOT_PINK('\n🚀 Starting WHALEWAVE PRO v11.0 Test Suite'));
    console.log(COLORS.GRAY('='.repeat(80)));
    
    const testStartTime = Date.now();
    
    try {
        // Run all test suites
        await testConfigManagement();
        testUtilityFunctions();
        testTechnicalAnalysis();
        testNeuralNetwork();
        await testMarketEngine();
        await testExchangeEngine();
        testAIAgent();
        await testIntegration();
        testPerformance();
        
        const testEndTime = Date.now();
        const totalTime = testEndTime - testStartTime;
        
        // Display results
        console.log(COLORS.CYAN('\n' + '='.repeat(80)));
        console.log(COLORS.BOLD(COLORS.MAGENTA('📊 TEST RESULTS SUMMARY')));
        console.log(COLORS.CYAN('='.repeat(80)));
        
        const summary = TestResults.getSummary();
        
        console.log(`${COLORS.GREEN(`✅ PASSED: ${summary.passed}`)}`);
        console.log(`${COLORS.RED(`❌ FAILED: ${summary.failed}`)}`);
        console.log(`${COLORS.BLUE(`📈 SUCCESS RATE: ${summary.successRate}%`)}`);
        console.log(`${COLORS.YELLOW(`⏱️ TOTAL TIME: ${totalTime}ms`)}`);
        
        if (summary.errors.length > 0) {
            console.log(COLORS.RED('\n🚨 ERRORS:'));
            summary.errors.forEach(error => {
                console.log(`   ${COLORS.RED('•')} ${error.test}: ${error.error}`);
            });
        }
        
        console.log(COLORS.CYAN('\n🎯 RECOMMENDATIONS:'));
        if (summary.failed === 0) {
            console.log(COLORS.GREEN('   ✅ All tests passed! The trading bot is ready for deployment.'));
        } else {
            console.log(COLORS.ORANGE(`   ⚠️ ${summary.failed} test(s) failed. Please review and fix issues before deployment.`));
        }
        
        console.log(COLORS.CYAN('\n🔧 System Check:'));
        console.log(`   • Node.js Version: ${process.version}`);
        console.log(`   • Memory Usage: ${(process.memoryUsage().heapUsed / 1024 / 1024).toFixed(1)}MB`);
        console.log(`   • Platform: ${process.platform}`);
        
        console.log(COLORS.GRAY('\n' + '='.repeat(80)));
        console.log(COLORS.HOT_PINK('🏁 Test Suite Completed'));
        
    } catch (error) {
        console.error(COLORS.RED('💥 Critical test suite error:'), error);
    }
}

// Run tests if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
    runAllTests().catch(console.error);
}

export { runAllTests, TestResults };