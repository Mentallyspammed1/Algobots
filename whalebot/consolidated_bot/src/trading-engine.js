import axios from 'axios';
import dotenv from 'dotenv';
import { Decimal } from 'decimal.js';
import { ConfigManager } from './config.js';
import { TA } from './technical-analysis.js';
import * as Utils from './utils.js';
import { NEON } from './ui.js';
import { CircuitBreaker } from './risk.js'; // Assuming CircuitBreaker is needed here

dotenv.config();

// --- MAIN TRADING ENGINE ---
// Orchestrates data fetching, analysis, AI signaling, and trade execution.
export class TradingEngine {
    constructor(config) {
        this.config = config;
        this.circuitBreaker = new CircuitBreaker(this.config); // Instantiate CircuitBreaker
        this.exchange = this.config.live_trading
            ? new LiveBybitExchange(this.config, this.circuitBreaker) // Pass CircuitBreaker
            : new PaperExchange(this.config, this.circuitBreaker); // Pass CircuitBreaker
        this.ai = new AIBrain(this.config);
        this.dataProvider = new MarketData(this.config, (type) => this.onTick(type));
        this.isRunning = true;
        this.consecutiveErrors = 0;
        this.maxConsecutiveErrors = 5;
        this.lastAiQueryTime = 0; // To manage AI query frequency
        this.state = {}; // State for HUD/JSON output
    }

    // Initializes engine components and starts data fetching.
    async initialize() {
        console.clear();
        console.log(NEON.BLUE("🚀 Initializing WhaleWave Scalping Engine..."));
        await this.dataProvider.start(); // Start fetching data
        // Balance is set when exchange is initialized or after first fetch
        // For paper trading, it's set in PaperExchange constructor.
        // For live, it might need an explicit fetch if not from env/config.
        if (!this.config.live_trading) {
            this.circuitBreaker.setBalance(this.config.paper_trading.initial_balance);
        }
        console.log(NEON.GREEN("✅ Engine initialized successfully"));
    }

    // Processes a new tick of market data.
    async onTick(type) {
        // Prevent concurrent processing or processing if risk limits are breached
        if (this.isProcessing || !['kline', 'price'].includes(type) || !this.dataProvider.lastPrice || !this.circuitBreaker.canTrade()) {
            return;
        }
        this.isProcessing = true;
        console.time('tick_processing'); // Benchmark cycle time

        try {
            const data = this.dataProvider.fetchAllData(); // Get fetched data
            if (!data) {
                this.handleError('Market data fetch failed');
                this.isProcessing = false;
                return;
            }
            
            const analysis = await this.performAnalysis(data);
            const context = Utils.buildContext(data, analysis, this.config);

            let aiSignal = { action: 'HOLD', confidence: 0, reason: 'No signal' };
            const now = Date.now();
            
            // Trigger AI query if conditions are met and enough time has passed since last query
            if (!this.exchange.getPos() && now - this.lastAiQueryTime > this.config.delays.ai_query * 1000) {
                 // Basic check: if not in a position and AI signal conditions met (e.g., score threshold)
                 // More sophisticated conditions could be added here.
                 if (Math.abs(context.wss) > this.config.indicators.wss_weights.action_threshold) {
                    this.lastAiQueryTime = now;
                    console.log(NEON.CYAN(`\n[AI Trigger] WSS ${context.wss} suggests action. Querying Gemini...`));
                    aiSignal = await this.ai.analyze(context);
                 }
            }

            // Evaluate trade decision (either from AI or hold)
            this.exchange.evaluate(data.price, aiSignal);

            // Update state for display
            this.state = {
                time: Utils.timestamp(),
                symbol: this.config.symbol,
                price: data.price,
                latency: this.dataProvider.latency,
                wss: context.wss,
                rsi: context.rsi,
                stoch_k: context.stoch_k,
                stoch_d: context.stoch_d,
                trend_mtf: context.trend_mtf,
                marketRegime: context.marketRegime,
                volatility: context.volatility,
                position: this.exchange.getPos(),
                aiSignal: aiSignal,
                balance: this.exchange.circuitBreaker.balance, // Use CircuitBreaker's balance
                benchmarkMs: console.timeEnd('tick_processing') // End benchmark
            };
            
            this.displayState(); // Render HUD or JSON

            this.consecutiveErrors = 0; // Reset error count on successful cycle

        } catch (error) {
            this.handleError(`Trading cycle error: ${error.message}`);
        } finally {
            this.isProcessing = false;
        }
    }

    // Performs all technical analysis calculations.
    async performAnalysis(data) {
        const closes = data.candles.map(c => c.c);
        const highs = data.candles.map(c => c.h);
        const lows = data.candles.map(c => c.l);
        const volumes = data.candles.map(c => c.v);
        const mtfCloses = data.candlesMTF.map(c => c.c);

        // Volatility calculation needed for market regime and context
        const volatility = TA.historicalVolatility(closes);
        const avgVolatility = TA.sma(volatility, 50);
        const marketRegime = TA.marketRegime(closes, volatility);

        // Calculate all indicators using parallel promises for efficiency
        const indicatorPromises = Utils.getIndicatorList(this.config).map(indicator => {
            const params = { ...indicator, data: { highs, lows, closes, volumes } };
            // Map indicator names to their TA functions
            switch (indicator.name) {
                case 'rsi': return TA.rsi(params.data.closes, params.period);
                case 'stoch': return TA.stoch(params.data.highs, params.data.lows, params.data.closes, params.period, params.kP, params.dP);
                case 'cci': return TA.cci(params.data.highs, params.data.lows, params.data.closes, params.period);
                case 'macd': return TA.macd(params.data.closes, params.period, params.slow, params.sig);
                case 'adx': return TA.adx(params.data.highs, params.data.lows, params.data.closes, params.period);
                case 'mfi': return TA.mfi(params.data.highs, params.data.lows, params.data.closes, params.data.volumes, params.period);
                case 'chop': return TA.chop(params.data.highs, params.data.lows, params.data.closes, params.period);
                case 'linReg': return TA.linReg(params.data.closes, params.period);
                case 'bb': return TA.bollinger_fixed(params.data.closes, params.period, params.std);
                case 'kc': return TA.keltner(params.data.highs, params.data.lows, params.data.closes, params.period, params.mult);
                case 'atr': return TA.atr(params.data.highs, params.data.lows, params.data.closes, params.period);
                case 'st': return TA.superTrend(params.data.highs, params.data.lows, params.data.closes, params.period, params.factor);
                case 'ce': return TA.chandelierExit(params.data.highs, params.data.lows, params.data.closes, params.period, params.mult);
                default: return []; // Unknown indicator
            }
        });

        const [rsi, stoch, cci, macd, adx, mfi, chop, reg, bb, kc, atr, st, ce] = await Promise.all(indicatorPromises);
        
        // Multi-Timeframe Trend Calculation
        const mtfSma = TA.sma(mtfCloses, 20); // Using a fixed SMA period for MTF trend
        const trendMTF = mtfCloses[mtfCloses.length - 1] > mtfSma[mtfSma.length - 1] ? "BULLISH" : "BEARISH";

        // Advanced Logic Analysis (e.g., Squeeze)
        const last = closes.length - 1;
        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);

        // Orderbook Wall Detection
        const avgBidVol = Utils.sum(data.bids.map(b => b.q)) / data.bids.length;
        const avgAskVol = Utils.sum(data.asks.map(a => a.q)) / data.asks.length;
        const wallThresh = this.config.orderbook.wall_threshold;
        const buyWall = data.bids.find(b => b.q > avgBidVol * wallThresh);
        const sellWall = data.asks.find(a => a.q > avgAskVol * wallThresh);

        // Fibonacci Pivots based on Daily High/Low/Close
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);

        return {
            closes, rsi, stoch, cci, macd, adx, mfi, chop, reg, atr, fvg: TA.findFVG(data.candles), 
            isSqueeze, buyWall: buyWall?.p, sellWall: sellWall?.p, trendMTF, st, ce, fibs,
            volatility, avgVolatility, marketRegime
        };
    }

    // Displays the current state (either HUD or JSON).
    displayState() {
        const outputMode = process.env.OUTPUT_MODE || 'HUD'; // Default to HUD
        if (outputMode === 'HUD') {
            renderHUD(this.state);
        } else {
            console.log(this.toJSON());
        }
    }
    
    // Converts the current state to a JSON string.
    toJSON() {
        // Create a serializable representation of the state
        const serializableState = { ...this.state };
        if (serializableState.position) { // Ensure position object is serializable
            serializableState.position = {
                side: serializableState.position.side,
                entry: serializableState.position.entry.toString(),
                qty: serializableState.position.qty.toString(),
                sl: serializableState.position.sl.toString(),
                tp: serializableState.position.tp.toString(),
            };
        }
        serializableState.balance = serializableState.balance.toString(); // Convert Decimal balance to string
        return JSON.stringify(serializableState, null, 2);
    }

    // Handles errors by logging and potentially shutting down after consecutive failures.
    handleError(message) {
        this.consecutiveErrors++;
        console.error(NEON.RED(`\nLOOP ERROR (${this.consecutiveErrors}/${this.maxConsecutiveErrors}): ${message}`));

        if (this.consecutiveErrors >= this.maxConsecutiveErrors) {
            this.isRunning = false;
            console.error(NEON.RED(`\nSHUTDOWN: Too many consecutive errors. Review logs and configuration.`));
            this.shutdown(); // Initiate shutdown
        }
    }

    // Starts the main trading loop.
    async start() {
        await this.initialize();
        while (this.isRunning) {
            await this.onTick('kline'); // Manually trigger onTick to start the loop
            await new Promise(resolve => setTimeout(resolve, this.config.delays.loop * 1000));
        }
        this.shutdown();
    }

    // Handles graceful shutdown.
    shutdown() {
        this.isRunning = false;
        console.log('\n');
        console.log(NEON.RED("🛑 SHUTDOWN INITIATED..."));
        const finalBalance = this.exchange.circuitBreaker.balance;
        const startBalance = this.exchange.circuitBreaker.startBalance;
        const pnl = finalBalance.sub(startBalance);
        const pnlColor = pnl.gte(0) ? NEON.GREEN : NEON.RED;
        
        // Render summary using the UI utility
        renderBox("SESSION SUMMARY", [
            `Final Balance: $${finalBalance.toFixed(2)}`,
            `Total PnL:     ${pnlColor('$' + pnl.toFixed(2))}`,
            `Active Pos:    ${this.exchange.getPos() ? NEON.YELLOW('YES - Manual Exit Required') : NEON.GREEN('NO')}`
        ]);
        process.exit(0);
    }
}
