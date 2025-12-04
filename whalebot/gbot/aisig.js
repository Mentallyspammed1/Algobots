/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.0 (Refactored)
 * ======================================================
 * This is the main entry point for the trading bot.
 * It orchestrates all the refactored components.
 */

import dotenv from 'dotenv';
dotenv.config();

import { ConfigManager } from './src/config.js';
import { CircuitBreaker } from './src/risk.js';
import { AIBrain } from './src/services/ai-brain.js';
import { MarketData } from './src/services/market-data.js';
import { LiveBybitExchange, PaperExchange } from './src/services/bybit-exchange.js';
import * as TA from './src/technical-analysis.js';
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

        // State for HUD and JSON output
        this.state = {};
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v3.0: MODULAR CORE '))));
        
        this.config = await ConfigManager.load();
        this.circuitBreaker = new CircuitBreaker(this.config);
        
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker);

        this.ai = new AIBrain(this.config);
        this.data = new MarketData(this.config, (type) => this.onTick(type));
        
        await this.data.start();
        this.circuitBreaker.setBalance(this.exchange.getBalance());
        console.log(COLOR.CYAN(`[Engine] Leviathan initialized. Live Mode: ${this.config.live_trading}`));
    }

    async onTick(type) {
        const price = this.data.lastPrice;
        if (this.isProcessing || !['kline', 'price'].includes(type) || !price || price === 0 || !this.circuitBreaker.canTrade()) {
            return;
        }
        
        this.isProcessing = true;
        console.time('tick_processing'); // Start benchmark

        try {
            const candles = this.data.buffers.main;
            const indicatorsConf = this.config.indicators;
            
            if (candles.length < indicatorsConf.bb.period) {
                this.isProcessing = false;
                console.timeEnd('tick_processing');
                return;
            }

            // 1. Technical Calculation
            const closes = candles.map(c => c.c);
            const highs = candles.map(c => c.h);
            const lows = candles.map(c => c.l);

            const rsiSeries = TA.rsi(closes, indicatorsConf.rsi);
            const fisherSeries = TA.fisher(highs, lows, indicatorsConf.fisher);
            const atrSeries = TA.atr(highs, lows, closes, indicatorsConf.atr);
            const bbSeries = TA.bollinger_fixed(closes, indicatorsConf.bb.period, indicatorsConf.bb.std);

            const i = closes.length - 1; // Last index
            const currentRsi = rsiSeries[i];
            const currentFisher = fisherSeries[i];
            const currentAtr = atrSeries[i];

            // 2. Orderbook Imbalance
            const bidVol = Utils.sum(this.data.orderbook.bids.map(b => parseFloat(b[1])));
            const askVol = Utils.sum(this.data.orderbook.asks.map(a => parseFloat(a[1])));
            const imbalance = (bidVol - askVol) / ((bidVol + askVol) || 1);

            // 3. Score Calculation
            let score = 0;
            if (currentFisher > 0) score += 2; else score -= 2;
            if (currentRsi > 50) score += 1; else score -= 1;
            if (imbalance > 0.2) score += 1.5; else if (imbalance < -0.2) score -= 1.5;
            if (price > bbSeries.mid[i]) score += 1; else score -= 1;

            // 4. Position Evaluation (Paper or Live)
            if (this.exchange.getPos()) {
                this.exchange.evaluate(price, { action: 'HOLD' }); // Let exchange check for SL/TP
            }

            // 5. AI Signal Trigger
            const now = Date.now();
            const scoreThreshold = this.config.indicators.threshold;
            let decision = { action: 'HOLD', confidence: 0, aiEntry: 0, volatilityForecast: 'MEDIUM' }; 

            if (!this.exchange.getPos() && Math.abs(score) >= scoreThreshold && (now - this.aiLastQueryTime > this.config.delays.loop)) {
                 if (Math.sign(score) === Math.sign(currentFisher) || Math.abs(score) >= 4.0) {
                    this.aiLastQueryTime = now;
                    console.log(COLOR.CYAN(`\n[Trigger] Score ${score.toFixed(2)} hit threshold. Querying Gemini...`));
                    
                    const context = { symbol: this.config.symbol, price, rsi: currentRsi, fisher: currentFisher, atr: currentAtr, imbalance, score };
                    decision = await this.ai.analyze(context);
                    
                    if (decision.confidence >= this.config.ai.minConfidence && decision.action !== 'HOLD') {
                        this.exchange.evaluate(price, decision);
                    }
                }
            }
            
            // 6. Update State & Render
            this.state = {
                time: Utils.timestamp(),
                symbol: this.config.symbol,
                price,
                latency: this.data.latency,
                score,
                rsi: currentRsi,
                fisher: currentFisher,
                atr: currentAtr,
                imbalance,
                position: this.exchange.getPos(),
                aiSignal: decision,
                benchmarkMs: console.timeEnd('tick_processing') // End benchmark
            };
            
            // Output JSON or render HUD
            this.output();

        } catch (e) {
            console.error(COLOR.RED(`[onTick Error] ${e.message}\n${e.stack}`));
        } finally {
            this.isProcessing = false;
        }
    }

    output() {
        // As per request, output is changed to JSON.
        // The HUD is kept for optional use.
        const outputMode = process.env.OUTPUT_MODE || 'JSON'; // 'HUD' or 'JSON'

        if (outputMode === 'HUD') {
            renderHUD(this.state);
        } else {
            console.log(this.toJSON());
        }
    }
    
    toJSON() {
        // Create a serializable representation of the state
        const safeState = { ...this.state };
        if (safeState.position) {
            safeState.position = {
                side: safeState.position.side,
                entry: safe.position.entry.toString(),
                qty: safe.position.qty.toString(),
                sl: safe.position.sl.toString(),
                tp: safe.position.tp.toString(),
            }
        }
        return JSON.stringify(safeState, null, 2);
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