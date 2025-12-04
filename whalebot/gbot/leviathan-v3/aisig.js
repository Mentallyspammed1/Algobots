/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Refactored)
 * ======================================================
 * Main entry point for the trading bot.
 * This version is refactored for modularity, profitability, and robustness.
 */

import dotenv from 'dotenv';
import path from 'path';

import { ConfigManager } from './src/config.js';
import { CircuitBreaker } from './src/risk.js';
import { AIBrain } from './src/services/ai-brain.js';
import { MarketData } from './src/services/market-data.js';
import { LiveBybitExchange, PaperExchange } from './src/services/bybit-exchange.js';
import * as TA from './src/technical-analysis.js';
import * as TAA from './src/technical-analysis-advanced.js';
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
        this.state = {
            position: 'none',
            entryPrice: null,
            currentPrice: null,
            lastSignal: 'HOLD',
            lastAIDecision: 'HOLD',
            aiDecision: { decision: 'HOLD', confidence: 0, reason: 'N/A' },
            score: 0,
            lastIndicators: {},
            timestamp: null,
            balance: { total: 0, available: 0, used: 0 }
        };
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v3.5: Refactored '))));
        
        dotenv.config({ path: path.resolve(process.cwd(), '.env') });

        const isLive = process.argv.includes('--live');
        this.config = await ConfigManager.load();
        this.config.live_trading = isLive;
        console.log(COLOR.GREEN(`[Leviathan] Config loaded. Live Trading: ${this.config.live_trading}`)); 

        if (this.config.live_trading) { 
            console.log(COLOR.RED(COLOR.BOLD('🚨 LIVE TRADING ENABLED 🚨')));
        } else {
            console.log(COLOR.YELLOW('PAPER TRADING MODE ENABLED. Use --live flag to trade with real funds.'));
        }

        this.circuitBreaker = new CircuitBreaker(this.config);
        this.ai = new AIBrain(this.config);
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker, this.ai);
        
        this.data = new MarketData(this.config, this);
        console.log(COLOR.GREEN(`[Leviathan] MarketData and Exchange initialized.`)); 
        
        await this.data.start();
        const balance = await this.exchange.getBalance();
        this.circuitBreaker.setBalance(balance);
        this.state.balance = balance;
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

            const klines = this.data.getKlines('main');
            if (!klines || klines.length < 50) { // Increased minimum length
                console.warn(COLOR.YELLOW(`[onTick] Not enough kline data available (${klines?.length || 0}).`));
                this.isProcessing = false;
                return;
            }

            // Data Validation
            const cleanKlines = klines.filter(k => 
                k && typeof k.startTime === 'number' && typeof k.open === 'number' && !isNaN(k.open) &&
                typeof k.high === 'number' && !isNaN(k.high) && typeof k.low === 'number' && !isNaN(k.low) &&
                typeof k.close === 'number' && !isNaN(k.close) && typeof k.volume === 'number' && !isNaN(k.volume)
            );

            if (cleanKlines.length < klines.length) {
                console.warn(COLOR.YELLOW(`[onTick] Filtered out ${klines.length - cleanKlines.length} invalid klines.`));
            }
            
            if (cleanKlines.length < 50) {
                 console.warn(COLOR.YELLOW(`[onTick] Not enough clean klines to calculate indicators (${cleanKlines.length}).`));
                 this.isProcessing = false;
                 return;
            }

            const closes = cleanKlines.map(k => k.close);
            const highs = cleanKlines.map(k => k.high);
            const lows = cleanKlines.map(k => k.low);
            const volumes = cleanKlines.map(k => k.volume);
            
            const latestKline = cleanKlines[cleanKlines.length - 1];
            const currentPrice = latestKline.close;

            if (currentPrice === 0) {
                console.warn(COLOR.YELLOW(`[onTick] latestKline.close is 0. Skipping tick processing.`));
                this.isProcessing = false;
                return;
            }

            // --- Indicator Calculations ---
            const indicators = {
                rsi: TA.rsi(closes, this.config.indicators.rsi),
                macd: TA.macd(closes, this.config.indicators.macd.fast, this.config.indicators.macd.slow, this.config.indicators.macd.signal),
                bollingerBands: TA.bollinger(closes, this.config.indicators.bb.period, this.config.indicators.bb.std),
                atr: TA.atr(highs, lows, closes, this.config.indicators.atr),
                stochRSI: TA.stochRSI(closes, this.config.indicators.stochRSI.rsi, this.config.indicators.stochRSI.stoch, this.config.indicators.stochRSI.k, this.config.indicators.stochRSI.d),
                adx: TA.adx(highs, lows, closes, this.config.indicators.adx),
                williamsR: TA.williamsR(highs, lows, closes, 14),
                
                ehlersFisher: TA.fisher(highs, lows, this.config.indicators.fisher),
                supertrend: TAA.superTrend(highs, lows, closes, this.config.indicators.advanced.superTrend.period, this.config.indicators.advanced.superTrend.multiplier),
                ichimoku: TAA.ichimoku(highs, lows, closes, this.config.indicators.advanced.ichimoku.span1, this.config.indicators.advanced.ichimoku.span2, this.config.indicators.advanced.ichimoku.span3),
                vwap: TAA.vwap(highs, lows, closes, volumes),
                hma: TAA.hullMA(closes, this.config.indicators.advanced.hma.period),
                choppiness: TAA.choppiness(highs, lows, closes, this.config.indicators.advanced.choppiness.period),
                t3: TAA.t3(closes, this.config.indicators.advanced.t3.period, this.config.indicators.advanced.t3.vFactor)
            };

            // --- Scoring Model ---
            let score = 0;
            const latest = (arr) => arr[arr.length - 1];

            // Trend
            if (latest(indicators.ehlersFisher) > 0 && latest(indicators.ehlersFisher) > indicators.ehlersFisher[indicators.ehlersFisher.length - 2]) score += 20;
            if (latest(indicators.ehlersFisher) < 0 && latest(indicators.ehlersFisher) < indicators.ehlersFisher[indicators.ehlersFisher.length - 2]) score -= 20;
            if (currentPrice > latest(indicators.supertrend.trend)) score += 15; else score -= 15;
            if (latest(indicators.adx.adx) > 25 && latest(indicators.adx.pdi) > latest(indicators.adx.ndi)) score += 10;
            if (latest(indicators.adx.adx) > 25 && latest(indicators.adx.ndi) > latest(indicators.adx.pdi)) score -= 10;

            // Momentum
            if (latest(indicators.rsi) < 30) score += 10; else if (latest(indicators.rsi) > 70) score -= 10;
            if (latest(indicators.macd.histogram) > 0 && indicators.macd.histogram[indicators.macd.histogram.length - 2] < 0) score += 15; // Bullish crossover
            if (latest(indicators.macd.histogram) < 0 && indicators.macd.histogram[indicators.macd.histogram.length - 2] > 0) score -= 15; // Bearish crossover
            if (latest(indicators.stochRSI.k) < 20 && latest(indicators.stochRSI.d) < 20) score += 10;
            if (latest(indicators.stochRSI.k) > 80 && latest(indicators.stochRSI.d) > 80) score -= 10;
            
            this.state.score = score;
            
            let signal = 'HOLD';
            if (score > 40) signal = 'BUY';
            if (score < -40) signal = 'SELL';

            // --- AIBrain Interaction ---
            let aiDecision = { decision: 'HOLD', confidence: 0, reason: 'No signal' };
            if (signal !== 'HOLD' || this.state.position !== 'none') {
                const indicatorsForAI = Object.keys(indicators).reduce((acc, key) => {
                    const value = indicators[key];
                    if (Array.isArray(value)) {
                        acc[key] = value[value.length - 1];
                    } else if (typeof value === 'object' && value !== null) {
                        acc[key] = Object.keys(value).reduce((subAcc, subKey) => {
                            const subValue = value[subKey];
                            if(Array.isArray(subValue)) {
                                subAcc[subKey] = subValue[subValue.length - 1];
                            }
                            return subAcc;
                        }, {});
                    }
                    return acc;
                }, {});

                const context = {
                    symbol: this.config.symbol,
                    price: currentPrice,
                    score: score,
                    indicators: indicatorsForAI
                };
                 aiDecision = await this.ai.getTradingDecision(context);
                 console.log(COLOR.BLUE(`[AIBrain] Decision: ${aiDecision.decision} (Confidence: ${(aiDecision.confidence * 100).toFixed(1)}%) Reason: ${aiDecision.reason}`));
            } else {
                 console.log(COLOR.GRAY(`[AIBrain] Skipping AI query: no strong signal or active position.`));
            }

            // --- Trade Execution ---
            if (this.circuitBreaker.isOpen()) {
                console.warn(COLOR.RED(`[Trade] Circuit breaker is OPEN. Skipping trade execution.`));
            } else if (aiDecision.decision === 'BUY' && aiDecision.confidence > this.config.ai.minConfidence && this.state.position === 'none') {
                const amount = this.config.trade_amount_usd / currentPrice;
                const order = await this.exchange.placeOrder(this.config.symbol, 'Buy', amount, currentPrice, { type: 'Market', timeInForce: 'GTC' });
                if (order) {
                    this.state.position = 'long';
                    this.state.entryPrice = currentPrice;
                    console.log(COLOR.GREEN(`[Trade] BUY Order placed: ${JSON.stringify(order)}`));
                }
            } else if (aiDecision.decision === 'SELL' && aiDecision.confidence > this.config.ai.minConfidence && this.state.position === 'long') {
                const amount = this.config.trade_amount_usd / currentPrice;
                const order = await this.exchange.placeOrder(this.config.symbol, 'Sell', amount, currentPrice, { type: 'Market', timeInForce: 'GTC' });
                if (order) {
                    this.state.position = 'none';
                    this.state.entryPrice = null;
                    console.log(COLOR.RED(`[Trade] SELL Order placed: ${JSON.stringify(order)}`));
                }
            } else {
                console.log(COLOR.GRAY(`[Trade] No trade executed.`));
            }
            
            // Update state
            this.state.balance = await this.exchange.getBalance();
            this.state.currentPrice = currentPrice;
            this.state.lastSignal = signal;
            this.state.lastAIDecision = aiDecision.decision;
            this.state.aiDecision = aiDecision;
            this.state.lastIndicators = indicators;
            this.state.timestamp = Date.now();

            this.output();

        } catch (error) {
            console.error(COLOR.RED(`[onTick] Error during tick processing: ${error.message}\n${error.stack}`));
            this.circuitBreaker.trip('onTick_error');
        } finally {
            this.isProcessing = false;
        }
    }

    output() {
        console.clear();
        const last = (arr) => arr && arr.length > 0 ? arr[arr.length-1] : 0;
        
        const displayData = {
            time: this.state.timestamp ? new Date(this.state.timestamp).toLocaleTimeString() : 'N/A',
            symbol: this.config.symbol,
            price: this.state.currentPrice,
            latency: this.data.latency,
            score: this.state.score,
            rsi: last(this.state.lastIndicators.rsi),
            fisher: last(this.state.lastIndicators.ehlersFisher),
            atr: last(this.state.lastIndicators.atr),
            position: this.state.position,
            aiSignal: this.state.aiDecision,
            balance: this.state.balance,
            circuitBreakerTripped: this.circuitBreaker.isOpen(),
        };
        renderHUD(displayData);
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

setInterval(() => {}, 1000);
