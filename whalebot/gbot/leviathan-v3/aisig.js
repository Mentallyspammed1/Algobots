/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Full TA Integration)
 * ======================================================
 * This is the main entry point for the trading bot.
 * UPDATE: Fully integrated 10 advanced indicators into the scoring engine.
 */

import dotenv from 'dotenv';
import path from 'path'; // Import path module

// Ensure .env file is loaded from the leviathan-v3 directory.
// IMPORTANT: Do not commit your .env file to version control.
// It should contain your sensitive API keys (e.g., GEMINI_API_KEY, BYBIT_API_KEY, BYBIT_API_SECRET).
console.log(`[DEBUG] Current working directory: ${process.cwd()}`);
dotenv.config({ path: path.resolve(process.cwd(), 'leviathan-v3', '.env') }); // <-- Explicitly set the absolute path
console.log(`[DEBUG] GEMINI_API_KEY from .env (after path.resolve): ${process.env.GEMINI_API_KEY}`); // <-- Added debug log

import { ConfigManager } from './src/config.js';
import { CircuitBreaker } from './src/risk.js';
console.log('Imported CircuitBreaker:', CircuitBreaker); // Debug log

import { AIBrain } from './src/services/ai-brain.js';
import { MarketData } from './src/services/market-data.js';
import { LiveBybitExchange, PaperExchange } from './src/services/bybit-exchange.js';
import * as TA from './src/technical-analysis.js';
import * as TAA from './src/technical-analysis-advanced.js'; // Import Advanced TA
import * as Utils from './src/utils.js';
import { renderHUD, COLOR } from './src/ui.js';

class Leviathan {
    constructor() {
        this.config = null;
        this.circuitBreaker = null;
        this.exchange = null;
        this.ai = null;
        this.data = null;
        this.isProcessing = false;
        this.aiLastQueryTime = 0;
        this.state = {
            position: 'none', // 'long', 'short', 'none'
            entryPrice: null,
            currentPrice: null,
            lastSignal: 'HOLD',
            lastAIDecision: 'HOLD',
            lastIndicators: {},
            timestamp: null,
            balance: {
                total: 0,
                available: 0,
                used: 0
            }
        };
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v3.5: FULL TA INTEGRATION '))));
        
        const isLive = process.argv.includes('--live');
        this.config = await ConfigManager.load();
        this.config.live_trading = isLive; // Corrected: set live_trading before logging
        console.log(COLOR.GREEN(`[Leviathan] Config loaded. Live Trading: ${this.config.live_trading}`)); 

        if (this.config.live_trading) { 
            console.log(COLOR.RED(COLOR.BOLD('🚨 LIVE TRADING ENABLED 🚨')));
        } else {
            console.log(COLOR.YELLOW('PAPER TRADING MODE ENABLED. Use --live flag to trade with real funds.'));
        }

        this.circuitBreaker = new CircuitBreaker(this.config);
        console.log('Instantiated this.circuitBreaker:', this.circuitBreaker); // Debug log
        // Pass this.ai to PaperExchange constructor
        this.ai = new AIBrain(this.config); // Initialize AI before exchange
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker, this.ai); // Pass this.ai here
        
        this.data = new MarketData(this.config, (type) => this.onTick(type));
        console.log(COLOR.GREEN(`[Leviathan] MarketData and Exchange initialized.`)); 
        
        await this.data.start();
        const balance = await this.exchange.getBalance();
        this.circuitBreaker.setBalance(balance);
        this.state.balance = balance; // Initialize state balance
        console.log(COLOR.CYAN(`[Engine] Leviathan initialized. Symbol: ${this.config.symbol}`));
        console.log(COLOR.GREEN(`[Leviathan] init() completed.`));
    }

    async onTick(type) {
        if (this.isProcessing) {
            console.warn(COLOR.YELLOW(`[onTick] Already processing a tick, skipping.`));
            return;
        }
        this.isProcessing = true;

        try {
            console.log(COLOR.CYAN(`[onTick] Processing new tick of type: ${type}`));

            const klines = this.data.getKlines('main'); // Use the new getKlines method
            if (!klines || klines.length === 0) {
                console.warn(COLOR.YELLOW(`[onTick] No kline data available.`));
                this.isProcessing = false;
                return;
            }

            // Ensure klines are sorted by timestamp in ascending order
            klines.sort((a, b) => a.startTime - b.startTime);

            // Get the latest kline for current price and basic checks
            const latestKline = klines[klines.length - 1];
            const currentPrice = latestKline.close;

            console.log(COLOR.GREEN(`[onTick] Latest Price: ${currentPrice}`));

            // --- Indicator Calculations ---
            const indicators = {};
            // Basic TA
            indicators.rsi = TA.rsi(klines.map(k => k.close), this.config.indicators.rsi);
            indicators.macd = TA.macd(
                klines.map(k => k.close),
                this.config.indicators.macd.fast,
                this.config.indicators.macd.slow,
                this.config.indicators.macd.signal
            );
            indicators.bollingerBands = TA.bollinger(
                klines.map(k => k.close),
                this.config.indicators.bb.period,
                this.config.indicators.bb.std
            );
            
            // Advanced TA
            indicators.ehlersFisher = TAA.fisher(klines.map(k => k.high), klines.map(k => k.low), this.config.indicators.fisher);
            indicators.supertrend = TAA.superTrend(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.advanced.superTrend.period, this.config.indicators.advanced.superTrend.multiplier);
            indicators.ichimoku = TAA.ichimoku(
                klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close),
                this.config.indicators.advanced.ichimoku.span1,
                this.config.indicators.advanced.ichimoku.span2,
                this.config.indicators.advanced.ichimoku.span3
            );
            indicators.vwap = TAA.vwap(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), klines.map(k => k.volume));
            indicators.adx = TAA.adx(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.adx);
            indicators.stochRSI = TA.stochRSI(
                klines.map(k => k.close),
                this.config.indicators.stochRSI.rsi,
                this.config.indicators.stochRSI.stoch,
                this.config.indicators.stochRSI.k,
                this.config.indicators.stochRSI.d
            );
            indicators.williamsR = TAA.williamsR(klines.map(k => k.high), klines.map(k => k.low), klines.map(k => k.close), this.config.indicators.stochRSI.rsi); // Using same period as StochRSI for now
            indicators.t3 = TAA.t3(klines.map(k => k.close), this.config.indicators.advanced.t3.period, this.config.indicators.advanced.t3.vFactor);
            // Momentum (if available and needed, add here. For now, T3 serves as an advanced indicator example.)


            // Log some indicator values for debugging
            console.log(COLOR.MAGENTA(`[Indicators] RSI: ${indicators.rsi && indicators.rsi.length > 0 ? indicators.rsi[indicators.rsi.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] MACD Hist: ${indicators.macd && indicators.macd.histogram && indicators.macd.histogram.length > 0 ? indicators.macd.histogram[indicators.macd.histogram.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] Supertrend: ${indicators.supertrend && indicators.supertrend.trend && indicators.supertrend.trend.length > 0 ? indicators.supertrend.trend[indicators.supertrend.trend.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] Ehlers Fisher: ${indicators.ehlersFisher && indicators.ehlersFisher.length > 0 ? indicators.ehlersFisher[indicators.ehlersFisher.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] StochRSI K: ${indicators.stochRSI && indicators.stochRSI.k && indicators.stochRSI.k.length > 0 ? indicators.stochRSI.k[indicators.stochRSI.k.length - 1].toFixed(2) : 'N/A'}`));
            console.log(COLOR.MAGENTA(`[Indicators] ADX: ${indicators.adx && indicators.adx.adx && indicators.adx.adx.length > 0 ? indicators.adx.adx[indicators.adx.adx.length - 1].toFixed(2) : 'N/A'}`));


            // --- Signal Generation (Placeholder) ---
            let signal = 'HOLD';
            // Example: Buy if RSI is below 30 and MACD histogram is positive and increasing
            if (indicators.rsi && indicators.macd && indicators.macd.histogram && indicators.macd.histogram.length >= 2) {
                const latestRSI = indicators.rsi[indicators.rsi.length - 1];
                const latestMACDHist = indicators.macd.histogram[indicators.macd.histogram.length - 1];
                const prevMACDHist = indicators.macd.histogram[indicators.macd.histogram.length - 2];

                if (latestRSI < 30 && latestMACDHist > 0 && latestMACDHist > prevMACDHist) {
                    signal = 'BUY';
                }
                // Example: Sell if RSI is above 70 and MACD histogram is negative and decreasing
                else if (latestRSI > 70 && latestMACDHist < 0 && latestMACDHist < prevMACDHist) {
                    signal = 'SELL';
                }
            }
            console.log(COLOR.YELLOW(`[Signal] Generated: ${signal}`));

            // --- AIBrain Interaction ---
            // Only query AIBrain if a potential trade signal is generated or if position needs management
            let aiDecision = { decision: 'HOLD', confidence: 0 };
            if (signal !== 'HOLD' || (this.state.position !== 'none')) {
                 aiDecision = await this.ai.getTradingDecision(currentPrice, indicators, this.state, signal);
                 console.log(COLOR.BLUE(`[AIBrain] Decision: ${aiDecision.decision} (Confidence: ${aiDecision.confidence.toFixed(2)})`));
            } else {
                 console.log(COLOR.GRAY(`[AIBrain] Skipping AI query: no strong signal or active position.`));
            }


            // --- Trade Execution ---
            if (this.circuitBreaker.isOpen()) {
                console.warn(COLOR.RED(`[Trade] Circuit breaker is OPEN. Skipping trade execution.`));
            } else if (aiDecision.decision === 'BUY' && this.state.position === 'none') {
                const amount = this.config.trade_amount_usd / currentPrice; // Example: trade a fixed USD amount
                const order = await this.exchange.placeOrder(
                    this.config.symbol,
                    'Buy',
                    amount,
                    currentPrice, // Or use a limit order price based on strategy
                    {
                        type: 'Market',
                        timeInForce: 'GTC'
                    }
                );
                if (order) {
                    this.state.position = 'long';
                    this.state.entryPrice = currentPrice;
                    console.log(COLOR.GREEN(`[Trade] BUY Order placed: ${JSON.stringify(order)}`));
                }
            } else if (aiDecision.decision === 'SELL' && this.state.position === 'long') {
                const amount = this.config.trade_amount_usd / currentPrice; // Sell the same amount as bought
                const order = await this.exchange.placeOrder(
                    this.config.symbol,
                    'Sell',
                    amount,
                    currentPrice, // Or use a limit order price
                    {
                        type: 'Market',
                        timeInForce: 'GTC'
                    }
                );
                if (order) {
                    this.state.position = 'none';
                    this.state.entryPrice = null;
                    console.log(COLOR.RED(`[Trade] SELL Order placed: ${JSON.stringify(order)}`));
                }
            } else {
                console.log(COLOR.GRAY(`[Trade] No trade executed based on AI decision and current position.`));
            }
            
            // Update balance after potential trade
            this.state.balance = await this.exchange.getBalance();

            // Update bot state
            this.state.currentPrice = currentPrice;
            this.state.lastSignal = signal;
            this.state.lastAIDecision = aiDecision.decision;
            this.state.lastIndicators = indicators;
            this.state.timestamp = Date.now();

            // Output current status (will be implemented in next step)
            this.output();

        } catch (error) {
            console.error(COLOR.RED(`[onTick] Error during tick processing: ${error.message}`));
            console.log(COLOR.RED('CircuitBreaker object in onTick error:', this.circuitBreaker)); // Debug log
            // Further error handling, e.g., notifying circuit breaker
            this.circuitBreaker.trip('onTick_error');
        } finally {
            this.isProcessing = false;
        }
    }
    output() {
        console.clear();
        const displayData = {
            symbol: this.config.symbol,
            interval: this.config.interval,
            liveTrading: this.config.live_trading,
            currentPrice: this.state.currentPrice,
            position: this.state.position,
            entryPrice: this.state.entryPrice,
            lastSignal: this.state.lastSignal,
            lastAIDecision: this.state.lastAIDecision,
            balance: this.state.balance,
            circuitBreakerTripped: this.circuitBreaker.isOpen(),
            lastIndicators: this.state.lastIndicators,
            timestamp: this.state.timestamp
        };
        renderHUD(displayData);
    }
    
    toJSON() {
        return {
            config: {
                symbol: this.config.symbol,
                interval: this.config.interval,
                live_trading: this.config.live_trading,
                trade_amount_usd: this.config.trade_amount_usd,
            },
            state: this.state, // this.state already contains much of the runtime data
            circuitBreakerStatus: this.circuitBreaker.isOpen() ? 'OPEN' : 'CLOSED',
            lastAIQueryTime: new Date(this.aiLastQueryTime).toISOString(),
            // Optionally, add summaries of indicators or other large data to keep JSON lean
            // e.g., lastTenRSI: this.state.lastIndicators.rsi.slice(-10)
        };
    }
}

// === MAIN EXECUTION ===
(async () => {
    try {
        const bot = new Leviathan();
        await bot.init();
    } catch (e) {
        console.error(COLOR.RED(`[FATAL] Failed to initialize Leviathan: ${e.message}`));
        process.exit(1);
    }
})();
// Add this to keep the process alive
setInterval(() => {}, 1000); // Keep the event loop alive
