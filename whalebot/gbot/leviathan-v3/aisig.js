/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Full TA Integration)
 * ======================================================
 * This is the main entry point for the trading bot.
 * UPDATE: Fully integrated 10 advanced indicators into the scoring engine.
 */

import dotenv from 'dotenv';
dotenv.config();

import { ConfigManager } from './src/config.js';
import { CircuitBreaker } from './src/risk.js';
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
        this.state = {};
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v3.5: FULL TA INTEGRATION '))));
        
        const isLive = process.argv.includes('--live');
        this.config = await ConfigManager.load();
        this.config.live_trading = isLive;

        if (isLive) {
            console.log(COLOR.RED(COLOR.BOLD('🚨 LIVE TRADING ENABLED 🚨')));
        } else {
            console.log(COLOR.YELLOW('PAPER TRADING MODE ENABLED. Use --live flag to trade with real funds.'));
        }

        this.circuitBreaker = new CircuitBreaker(this.config);
        // Pass this.ai to PaperExchange constructor
        this.ai = new AIBrain(this.config); // Initialize AI before exchange
        this.exchange = this.config.live_trading 
            ? new LiveBybitExchange(this.config) 
            : new PaperExchange(this.config, this.circuitBreaker, this.ai); // Pass this.ai here
        
        this.data = new MarketData(this.config, (type) => this.onTick(type));
        
        await this.data.start();
        this.circuitBreaker.setBalance(this.exchange.getBalance());
        console.log(COLOR.CYAN(`[Engine] Leviathan initialized. Symbol: ${this.config.symbol}`));
    }

    async onTick(type) {
        const price = this.data.lastPrice;
        if (this.isProcessing || !['kline', 'price'].includes(type) || !price || price === 0 || !this.circuitBreaker.canTrade()) {
            return;
        }
        
        this.isProcessing = true;
        const benchmarkTimer = 'tick_processing';
        console.time(benchmarkTimer);

        try {
            const candles = this.data.buffers.main;
            const conf = this.config.indicators;
            const advConf = conf.advanced;
            
            if (candles.length < Math.max(conf.bb.period, conf.macd.slow, advConf.ichimoku.span3)) {
                this.isProcessing = false;
                console.timeEnd(benchmarkTimer);
                return;
            }

            // 1. Technical Calculation
            const closes = candles.map(c => c.c);
            const highs = candles.map(c => c.h);
            const lows = candles.map(c => c.l);
            const volumes = candles.map(c => c.v);

            const rsiSeries = TA.rsi(closes, conf.rsi);
            const fisherSeries = TA.fisher(highs, lows, conf.fisher);
            const atrSeries = TA.atr(highs, lows, closes, conf.atr);
            const bbSeries = TA.bollinger(closes, conf.bb.period, conf.bb.std);
            const macdSeries = TA.macd(closes, conf.macd.fast, conf.macd.slow, conf.macd.signal);
            const stochRsiSeries = TA.stochRSI(closes, conf.stochRSI.rsi, conf.stochRSI.stoch, conf.stochRSI.k, conf.stochRSI.d);
            const adxSeries = TA.adx(highs, lows, closes, conf.adx);
            const t3Series = TAA.t3(closes, advConf.t3.period, advConf.t3.vFactor);
            const superTrendSeries = TAA.superTrend(highs, lows, closes, advConf.superTrend.period, advConf.superTrend.multiplier);
            const vwapSeries = TAA.vwap(highs, lows, closes, volumes);
            const hmaSeries = TAA.hullMA(closes, advConf.hma.period);
            const choppinessSeries = TAA.choppiness(highs, lows, closes, advConf.choppiness.period);
            const connorsRsiSeries = TAA.connorsRSI(closes, advConf.connorsRSI.rsiPeriod, advConf.connorsRSI.streakRsiPeriod, advConf.connorsRSI.rankPeriod);
            const ichimokuSeries = TAA.ichimoku(highs, lows, closes, advConf.ichimoku.span1, advConf.ichimoku.span2, advConf.ichimoku.span3);
            const schaffTCSeries = TAA.schaffTC(closes, advConf.schaffTC.fast, advConf.schaffTC.slow, advConf.schaffTC.cycle);
            
            const i = closes.length - 1;

            // 2. Orderbook Imbalance
            const bidVol = Utils.sum(this.data.orderbook.bids.map(b => parseFloat(b[1])));
            const askVol = Utils.sum(this.data.orderbook.asks.map(a => parseFloat(a[1])));
            const imbalance = (bidVol - askVol) / ((bidVol + askVol) || 1);

            // 3. Score Calculation (remains largely the same)
            let score = 0;
            const trendStrength = adxSeries.adx[i] > conf.thresholds.adx_trend_threshold ? 1 : 0.5;
            score += (fisherSeries[i] > 0 ? 1 : -1) * conf.scoring.fisher_weight;
            score += (closes[i] > bbSeries.mid[i] ? 1 : -1) * conf.scoring.bb_weight;
            score += (macdSeries.histogram[i] > 0 ? 1 : -1) * conf.scoring.macd_weight;
            if (stochRsiSeries.k[i] < 20) score += conf.scoring.stoch_rsi_weight;
            if (stochRsiSeries.k[i] > 80) score -= conf.scoring.stoch_rsi_weight;
            if (imbalance > conf.thresholds.imbalance_threshold) score += conf.scoring.imbalance_weight; 
            else if (imbalance < -conf.thresholds.imbalance_threshold) score -= conf.scoring.imbalance_weight;
            if(advConf.t3.enabled) score += (closes[i] > t3Series[i] ? 1 : -1) * advConf.t3.weight;
            if(advConf.superTrend.enabled) score += superTrendSeries.direction[i] * advConf.superTrend.weight;
            if(advConf.vwap.enabled) score += (closes[i] > vwapSeries[i] ? 1 : -1) * advConf.vwap.weight;
            if(advConf.hma.enabled) score += (closes[i] > hmaSeries[i] ? 1 : -1) * advConf.hma.weight;
            if(advConf.choppiness.enabled && choppinessSeries[i] > advConf.choppiness.threshold) score += advConf.choppiness.weight;
            if(advConf.connorsRSI.enabled) {
                if (connorsRsiSeries[i] < advConf.connorsRSI.oversold) score += advConf.connorsRSI.weight;
                if (connorsRsiSeries[i] > advConf.connorsRSI.overbought) score -= advConf.connorsRSI.weight;
            }
            if(advConf.ichimoku.enabled) {
                const inCloud = closes[i] > ichimokuSeries.spanA[i] && closes[i] < ichimokuSeries.spanB[i];
                if (!inCloud && closes[i] > ichimokuSeries.spanA[i] && closes[i] > ichimokuSeries.spanB[i]) score += advConf.ichimoku.weight;
                if (!inCloud && closes[i] < ichimokuSeries.spanA[i] && closes[i] < ichimokuSeries.spanB[i]) score -= advConf.ichimoku.weight;
            }
            if(advConf.schaffTC.enabled) {
                if(schaffTCSeries[i] < advConf.schaffTC.oversold) score += advConf.schaffTC.weight;
                if(schaffTCSeries[i] > advConf.schaffTC.overbought) score -= advConf.schaffTC.weight;
            }
            score *= trendStrength;

            // 4. Position Evaluation & AI Trigger
            const aiContext = { 
                symbol: this.config.symbol,
                price, 
                score, 
                imbalance,
                rsi: rsiSeries[i], 
                fisher: fisherSeries[i], 
                atr: atrSeries[i],
                bbMid: bbSeries.mid[i],
                bbUpper: bbSeries.upper[i],
                bbLower: bbSeries.lower[i],
                macd: {
                    macdLine: macdSeries.macd[i],
                    signalLine: macdSeries.signal[i],
                    histogram: macdSeries.histogram[i]
                },
                stochRsi: {
                    k: stochRsiSeries.k[i],
                    d: stochRsiSeries.d[i]
                },
                adx: {
                    adxLine: adxSeries.adx[i],
                    pdiLine: adxSeries.pdi[i],
                    ndiLine: adxSeries.ndi[i]
                },
                t3: t3Series[i],
                superTrend: {
                    trend: superTrendSeries.trend[i],
                    direction: superTrendSeries.direction[i]
                },
                vwap: vwapSeries[i],
                hma: hmaSeries[i],
                choppiness: choppinessSeries[i],
                connorsRsi: connorsRsiSeries[i],
                ichimoku: {
                    conv: ichimokuSeries.conv[i],
                    base: ichimokuSeries.base[i],
                    spanA: ichimokuSeries.spanA[i],
                    spanB: ichimokuSeries.spanB[i]
                },
                schaffTC: schaffTCSeries[i],
                // Pass indicator configurations for context in AI prompt
                indicators: this.config.indicators 
            };
            
            if (this.exchange.getPos()) {
                this.exchange.evaluate(price, { action: 'HOLD' }, aiContext); // Pass updated aiContext
            }
            
            let decision = { action: 'HOLD', confidence: 0, reason: 'No trigger' }; 
            if (!this.exchange.getPos() && Math.abs(score) >= conf.thresholds.trigger_threshold) {
                 this.aiLastQueryTime = Date.now();
                 console.log(COLOR.CYAN(`\n[Trigger] Score ${score.toFixed(2)} hit threshold. Querying Gemini...`));
                 decision = await this.ai.analyze(aiContext); // Pass the rich aiContext
                 
                 if (decision.confidence >= this.config.ai.minConfidence && decision.action !== 'HOLD') {
                     console.log(COLOR.PURPLE(`\n[AI Reason] ${decision.reason}`));
                     this.exchange.evaluate(price, decision, aiContext); // Pass updated aiContext here
                 }
            }
            
            // 5. Update State & Render
            const benchmarkMs = console.timeEnd(benchmarkTimer);
            this.state = {
                time: Utils.timestamp(), symbol: this.config.symbol, price, latency: this.data.latency,
                score, rsi: rsiSeries[i], fisher: fisherSeries[i], atr: atrSeries[i], imbalance,
                position: this.exchange.getPos(), aiSignal: decision, benchmarkMs
            };
            this.output();

        } catch (e) {
            console.error(COLOR.RED(`[onTick Error] ${e.message}\n${e.stack}`));
        } finally {
            this.isProcessing = false;
        }
    }

    // ... (output and toJSON methods remain the same)
}

// ... (MAIN EXECUTION remains the same)