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
            balance: 0,
            orderbook: {},
            consecutiveLosses: 0
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
        
        // Handle Decimal object from PaperExchange
        if (typeof balance === 'object' && balance.isDecimal) {
             this.circuitBreaker.setBalance(balance.toNumber());
             this.state.balance = balance.toNumber();
        } else {
             this.circuitBreaker.setBalance(balance);
             this.state.balance = balance;
        }

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

    async getAIDecision(currentPrice, score, indicators, orderbookMetrics) {
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
            indicators: indicatorsForAI,
            orderbook: orderbookMetrics,
        };
        
        const decision = await this.ai.getTradingDecision(context);
        return decision;
    }

    async updateState(newState) {
        const balance = await this.exchange.getBalance();
        if (typeof balance === 'object' && balance.isDecimal) {
            this.state.balance = balance.toNumber();
        } else {
            this.state.balance = balance;
        }
        
        this.circuitBreaker.setBalance(this.state.balance);

        this.state.currentPrice = newState.currentPrice;
        this.state.position = newState.position;
        this.state.entryPrice = newState.entryPrice;
        this.state.lastSignal = newState.signal;
        this.state.lastAIDecision = newState.aiDecision.decision;
        this.state.aiDecision = newState.aiDecision;
        this.state.score = newState.score;
        this.state.lastIndicators = newState.indicators;
        this.state.orderbook = newState.orderbookMetrics;
        if (newState.consecutiveLosses !== undefined) {
            this.state.consecutiveLosses = newState.consecutiveLosses;
        }
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

            // --- Step 0: Maintain Position (for SL/TP in paper mode) ---
            const maintenance = await this.exchange.maintainPosition(currentPrice);
            if (maintenance?.positionClosed) {
                this.state.position = 'none';
                this.state.entryPrice = null;
                if (maintenance.pnl) {
                     this.state.consecutiveLosses = maintenance.pnl < 0 ? this.state.consecutiveLosses + 1 : 0;
                }
            }

            // --- Step 1: Calculate Indicators & Signals ---
            const indicators = this.strategy.calculateIndicators(cleanKlines);
            const { score, signal } = this.strategy.generateSignal(indicators, currentPrice);
            const orderbookMetrics = this.data.getOrderbookAnalysis();

            // --- Step 2: Get AI Decision ---
            let aiDecision = { decision: 'HOLD', confidence: 0, reason: 'No signal' };
            if (signal !== 'HOLD' || this.state.position !== 'none') {
                aiDecision = await this.getAIDecision(currentPrice, score, indicators, orderbookMetrics);
            }

            // --- Step 3: Execute Trade ---
            const { orderResult, newPosition, newEntryPrice } = await this.trader.execute(aiDecision, { ...this.state, currentPrice });

            if (orderResult && orderResult.pnl) {
                this.state.consecutiveLosses = orderResult.pnl < 0 ? this.state.consecutiveLosses + 1 : 0;
            }

            // --- Step 4: Update State ---
            await this.updateState({
                currentPrice,
                position: newPosition,
                entryPrice: newEntryPrice,
                score,
                signal,
                aiDecision,
                indicators,
                orderbookMetrics,
                consecutiveLosses: this.state.consecutiveLosses
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
        const getLatestValue = (val) => (Array.isArray(val) && val.length > 0) ? val[val.length - 1] : (typeof val === 'number' ? val : 0);
        const getNestedLatestValue = (obj, key) => {
            if (obj && obj[key]) {
                return getLatestValue(obj[key]);
            }
            return 0;
        };

        const lastIndicators = this.state.lastIndicators;
        
        const posObjectForUI = this.state.position === 'long' ? { side: 'LONG' } : null;

        const displayData = {
            time: this.state.timestamp ? new Date(this.state.timestamp).toLocaleTimeString() : 'N/A',
            symbol: this.config.symbol,
            price: this.state.currentPrice || 0,
            latency: this.data.latency,
            score: this.state.score,
            
            // Core Indicators
            rsi: getLatestValue(lastIndicators.rsi),
            fisher: getLatestValue(lastIndicators.ehlersFisher),
            atr: getLatestValue(lastIndicators.atr),
            williamsR: getLatestValue(lastIndicators.williamsR),

            // MACD
            macd: {
                macd: getLatestValue(getNestedLatestValue(lastIndicators.macd, 'macd')),
                signal: getLatestValue(getNestedLatestValue(lastIndicators.macd, 'signal')),
                histogram: getLatestValue(getNestedLatestValue(lastIndicators.macd, 'histogram'))
            },

            // Bollinger Bands
            bollingerBands: {
                upper: getLatestValue(getNestedLatestValue(lastIndicators.bollingerBands, 'upper')),
                mid: getLatestValue(getNestedLatestValue(lastIndicators.bollingerBands, 'mid')),
                lower: getLatestValue(getNestedLatestValue(lastIndicators.bollingerBands, 'lower'))
            },

            // Stochastic RSI
            stochRSI: {
                k: getLatestValue(getNestedLatestValue(lastIndicators.stochRSI, 'k')),
                d: getLatestValue(getNestedLatestValue(lastIndicators.stochRSI, 'd'))
            },

            // ADX
            adx: {
                adx: getLatestValue(getNestedLatestValue(lastIndicators.adx, 'adx')),
                pdi: getLatestValue(getNestedLatestValue(lastIndicators.adx, 'pdi')),
                ndi: getLatestValue(getNestedLatestValue(lastIndicators.adx, 'ndi'))
            },

            // Advanced Indicators
            supertrend: {
                trend: getLatestValue(getNestedLatestValue(lastIndicators.supertrend, 'trend')),
                direction: getLatestValue(getNestedLatestValue(lastIndicators.supertrend, 'direction'))
            },
            ichimoku: {
                conv: getLatestValue(getNestedLatestValue(lastIndicators.ichimoku, 'conv')),
                base: getLatestValue(getNestedLatestValue(lastIndicators.ichimoku, 'base')),
                spanA: getLatestValue(getNestedLatestValue(lastIndicators.ichimoku, 'spanA')),
                spanB: getLatestValue(getNestedLatestValue(lastIndicators.ichimoku, 'spanB'))
            },
            vwap: getLatestValue(lastIndicators.vwap),
            hma: getLatestValue(lastIndicators.hma),
            choppiness: getLatestValue(lastIndicators.choppiness),
            t3: getLatestValue(lastIndicators.t3),

            orderbook: this.state.orderbook,
            position: posObjectForUI,
            aiSignal: this.state.aiDecision,
            balance: this.state.balance,
            circuitBreakerTripped: this.circuitBreaker.isOpen(),
            consecutiveLosses: this.state.consecutiveLosses
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
