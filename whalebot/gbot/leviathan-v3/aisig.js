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
import { Strategy } from './src/strategy.js';
import { Trader } from './src/trader.js';
import { renderHUD, COLOR } from './src/ui.js';

class Leviathan {
    constructor() {
        this.config = null;
        this.circuitBreaker = null;
        this.exchange = null;
        this.ai = null;
        this.data = null;
        this.strategy = null;
        this.trader = null;
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
            balance: 0
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
        
        this.initializeServices();
        
        await this.data.start();
        const balance = await this.exchange.getBalance();
        this.circuitBreaker.setBalance(balance);
        this.state.balance = balance;
        console.log(COLOR.CYAN(`[Engine] Leviathan initialized. Symbol: ${this.config.symbol}`));
        console.log(COLOR.GREEN(`[Leviathan] init() completed.`));
    }

    initializeServices() {
        this.circuitBreaker = new CircuitBreaker(this.config);
        this.ai = new AIBrain(this.config);
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker, this.ai);
        
        this.data = new MarketData(this.config, this);
        this.strategy = new Strategy(this.config);
        this.trader = new Trader(this.exchange, this.circuitBreaker, this.config);
        
        console.log(COLOR.GREEN(`[Leviathan] All services initialized.`));
    }

    validateKlines(klines) {
        if (!klines || klines.length < 50) {
            return null;
        }
    
        const cleanKlines = klines.filter(k => 
            k && typeof k.startTime === 'number' && typeof k.open === 'number' && !isNaN(k.open) &&
            typeof k.high === 'number' && !isNaN(k.high) && typeof k.low === 'number' && !isNaN(k.low) &&
            typeof k.close === 'number' && !isNaN(k.close) && typeof k.volume === 'number' && !isNaN(k.volume)
        );
    
        if (cleanKlines.length < klines.length) {
            console.warn(COLOR.YELLOW(`[Validator] Filtered out ${klines.length - cleanKlines.length} invalid klines.`));
        }
        
        return cleanKlines;
    }

    async getAIDecision(currentPrice, score, indicators) {
        const indicatorsForAI = Object.keys(indicators).reduce((acc, key) => {
            const value = indicators[key];
            if (Array.isArray(value)) {
                const lastVal = value[value.length - 1];
                acc[key] = typeof lastVal === 'number' ? lastVal : 0;
            } else if (typeof value === 'object' && value !== null) {
                acc[key] = Object.keys(value).reduce((subAcc, subKey) => {
                    const subValue = value[subKey];
                    if(Array.isArray(subValue)) {
                        const lastSubVal = subValue[subValue.length - 1];
                        subAcc[subKey] = typeof lastSubVal === 'number' ? lastSubVal : 0;
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
        
        const decision = await this.ai.getTradingDecision(context);
        console.log(COLOR.BLUE(`[AIBrain] Decision: ${decision.decision} (Confidence: ${(decision.confidence * 100).toFixed(1)}%) Reason: ${decision.reason}`));
        return decision;
    }

    async updateState(newState) {
        this.state.balance = await this.exchange.getBalance();
        this.state.currentPrice = newState.currentPrice;
        this.state.position = newState.position;
        this.state.entryPrice = newState.entryPrice;
        this.state.lastSignal = newState.signal;
        this.state.lastAIDecision = newState.aiDecision.decision;
        this.state.aiDecision = newState.aiDecision;
        this.state.score = newState.score;
        this.state.lastIndicators = newState.indicators;
        this.state.timestamp = Date.now();
    }

    async onTick(type) {
        if (this.isProcessing) {
            return;
        }
        this.isProcessing = true;

        try {
            const klines = this.data.getKlines('main');
            const cleanKlines = this.validateKlines(klines);

            if (!cleanKlines || cleanKlines.length < 50) {
                this.isProcessing = false;
                return;
            }

            const latestKline = cleanKlines[cleanKlines.length - 1];
            const currentPrice = latestKline.close;

            if (!currentPrice || currentPrice === 0) {
                console.warn(COLOR.YELLOW(`[onTick] Invalid currentPrice (${currentPrice}). Skipping tick processing.`));
                this.isProcessing = false;
                return;
            }

            // --- Step 1: Calculate Indicators ---
            const indicators = this.strategy.calculateIndicators(cleanKlines);

            // --- Step 2: Generate Signal from Strategy ---
            const { score, signal } = this.strategy.generateSignal(indicators, currentPrice);

            // --- Step 3: Get AI Decision ---
            let aiDecision = { decision: 'HOLD', confidence: 0, reason: 'No signal' };
            if (signal !== 'HOLD' || this.state.position !== 'none') {
                aiDecision = await this.getAIDecision(currentPrice, score, indicators);
            }

            // --- Step 4: Execute Trade ---
            const { newPosition, newEntryPrice } = await this.trader.execute(aiDecision, { ...this.state, currentPrice });

            // --- Step 5: Update State ---
            await this.updateState({
                currentPrice,
                position: newPosition,
                entryPrice: newEntryPrice,
                score,
                signal,
                aiDecision,
                indicators
            });

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
        const lastVal = (val) => val && val.length > 0 ? val[val.length-1] : 0;
        
        const displayData = {
            time: this.state.timestamp ? new Date(this.state.timestamp).toLocaleTimeString() : 'N/A',
            symbol: this.config.symbol,
            price: this.state.currentPrice || 0,
            latency: this.data.latency,
            score: this.state.score,
            rsi: lastVal(this.state.lastIndicators.rsi),
            fisher: lastVal(this.state.lastIndicators.ehlersFisher),
            atr: lastVal(this.state.lastIndicators.atr),
            imbalance: 0, // Placeholder to prevent crash in ui.js
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

// Keep process alive
setInterval(() => {}, 1000 * 60);
