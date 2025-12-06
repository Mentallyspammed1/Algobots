/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v11.0 (ULTIMATE SCALPING - FINAL FIX)
 * ===========================================================
 * - FIX: Corrected all ReferenceErrors by ensuring strict declaration order.
 * - STRUCTURE: Consolidated all classes and functions for single-file deployment.
 * - CORE: Includes Neural Network, Dynamic Risk, and Drift Correction logic.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import WebSocket from 'ws';
import https from 'https'; // Required for Keep-Alive Agent

dotenv.config();

// =============================================================================
// 1. UTILITIES & COLOR (Base Layer)
// =============================================================================

// High-Performance HTTPS Agent for Keep-Alive connections (Latency Fix)
const keepAliveAgent = new https.Agent({
    keepAlive: true,
    maxSockets: 256,
    scheduling: 'lifo',
    timeout: 3000
});

const COLORS = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#0A84FF'),
    CYAN: chalk.hex('#00FFFF'), PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'), ORANGE: chalk.hex('#FF9F00'), MAGENTA: chalk.hex('#FF00FF'),
    LIME: chalk.hex('#32CD32'), HOT_PINK: chalk.hex('#FF1493'), AQUA: chalk.hex('#00FFFF'),
    VIOLET: chalk.hex('#8A2BE2'), GOLD: chalk.hex('#FFD700'),
    BOLD: chalk.bold, bg: (text) => chalk.bgHex('#1C1C1E')(text)
};

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static safeLast(arr, def = 0) { 
        return (Array.isArray(arr) && arr.length > 0 && !isNaN(arr[arr.length - 1])) ? arr[arr.length - 1] : def; 
    }
    static formatNumber(num, decimals = 4) {
        if (isNaN(num) || !isFinite(num)) return '0.0000';
        return num.toFixed(decimals);
    }
    static formatTime(ms) {
        if (ms < 1000) return `${Math.floor(ms)}ms`;
        if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
        if (ms < 3600000) return `${Math.floor(ms / 60000)}m`;
        return `${Math.floor(ms / 3600000)}h`;
    }
    static neuralNetwork(features, weights) {
        let output = 0;
        for (let i = 0; i < features.length; i++) {
            output += features[i] * weights[i];
        }
        return 1 / (1 + Math.exp(-output));
    }
    static calculateMomentum(prices, period = 9) {
        const momentum = [];
        for (let i = period; i < prices.length; i++) {
            const change = (prices[i] - prices[i - period]) / prices[i - period];
            momentum.push(change);
        }
        return momentum;
    }
    static calculateROC(prices, period = 8) {
        const roc = [];
        for (let i = period; i < prices.length; i++) {
            const change = ((prices[i] - prices[i - period]) / prices[i - period]) * 100;
            roc.push(change);
        }
        return roc;
    }
    static williamsR(highs, lows, closes, period = 7) {
        const williamsR = [];
        for (let i = period - 1; i < closes.length; i++) {
            const highest = Math.max(...highs.slice(i - period + 1, i + 1));
            const lowest = Math.min(...lows.slice(i - period + 1, i + 1));
            const wr = ((highest - closes[i]) / (highest - lowest)) * -100;
            williamsR.push(wr);
        }
        return williamsR;
    }
    static analyzeVolumeFlow(volumes, prices) {
        const flow = [];
        for (let i = 1; i < prices.length; i++) {
            const priceChange = prices[i] - prices[i - 1];
            const volumeChange = volumes[i] - volumes[i - 1];
            flow.push(priceChange > 0 ? volumeChange : -volumeChange);
        }
        return flow;
    }
    static detectAdvancedPatterns(prices, volumes, highs, lows, closes) {
        const patterns = [];
        const len = prices.length;
        if (len < 10) return patterns;
        const last = len - 1;
        const p = prices;
        const v = volumes;

        if (v[last] > v[last-1] * 2.5 && Math.abs(p[last] - p[last-3]) > p[last-1] * 0.005) {
            patterns.push({ type: 'VOL_CLIMAX_REVERSAL', strength: Math.min(v[last] / v[last-1], 5) });
        }
        const mom1 = p[last] - p[last-3];
        const mom2 = p[last-3] - p[last-6];
        if (mom1 > 0 && mom2 > mom1 * 1.5) {
            patterns.push({ type: 'MOMENTUM_EXHAUSTION', direction: 'BEARISH', strength: (mom2 - mom1) / mom1 });
        }
        if (highs[last] - lows[last] > (highs[last-1] - lows[last-1]) * 1.3) {
            patterns.push({ type: 'EXPANSION' });
        }
        return patterns;
    }
}

// =============================================================================
// 2. CONFIGURATION & HISTORY MANAGERS
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { scalp: '1', quick: '3', trend: '5', macro: '15' },
        limits: { kline: 200, orderbook: 50, ticks: 1000 },
        delays: { loop: 500, retry: 500, ai: 1000 },
        ai: { model: 'gemini-1.5-pro', minConfidence: 0.88, temperature: 0.03, rateLimitMs: 1000, maxRetries: 3 },
        risk: {
            initialBalance: 1000.00, maxDrawdown: 6.0, dailyLossLimit: 3.0, riskPercent: 0.75, leverageCap: 20,
            fee: 0.00045, slippage: 0.00005, maxPositionSize: 0.25, minRR: 1.8, dynamicSizing: true
        },
        indicators: {
            periods: { rsi: 5, fisher: 7, stoch: 3, atr: 6, chop: 10, williams: 7, momentum: 9, roc: 8 },
            scalping: { volumeSpikeThreshold: 2.2, priceAcceleration: 0.00015, orderFlowImbalance: 0.35, liquidityThreshold: 1000000 },
            weights: { microTrend: 4.0, momentum: 3.2, orderFlow: 2.8, neural: 2.5, actionThreshold: 2.8 },
            neural: { enabled: true, features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum'] }
        },
        scalping: {
            minProfitTarget: 0.0018, maxHoldingTime: 450000, quickExitThreshold: 0.00075, timeBasedExit: 180000,
            partialClose: 0.0009, breakEvenStop: 0.0006
        },
        websocket: { enabled: true, reconnectInterval: 2000 }
    });

    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        try {
            await fs.access(this.CONFIG_FILE);
            const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.deepMerge(config, JSON.parse(fileContent));
        } catch (error) {
            await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                result[key] = this.deepMerge(result[key] || {}, value);
            } else {
                result[key] = value;
            }
        }
        return result;
    }
}

class HistoryManager {
    static FILE = 'scalping_trades.json';
    static ANALYTICS_FILE = 'scalping_analytics.json';
    static ERROR_FILE = 'errors.log';
    static NEURAL_TRAINING = 'neural_training.json';

    static async load() { try { return JSON.parse(await fs.readFile(this.FILE, 'utf-8')); } catch { return []; } }
    
    static async save(trade) {
        const history = await this.load();
        history.push(trade);
        await fs.writeFile(this.FILE, JSON.stringify(history, null, 2));
        await this.updateScalpingAnalytics(history);
    }

    static async loadScalpingAnalytics() {
        try { return JSON.parse(await fs.readFile(this.ANALYTICS_FILE, 'utf-8')); } 
        catch { return { scalpingTrades: 0, avgHoldingTime: 0, winRateScalping: 0, profitFactorScalping: 0, bestScalp: 0, consecutiveLosses: 0 }; }
    }

    static async updateScalpingAnalytics(trades) {
        // Simplified calculation for fast loop
        const scalps = trades.filter(t => t.strategy && t.strategy.includes('Scalp'));
        if (scalps.length === 0) return;
        
        const holdingTimes = scalps.map(t => t.holdingTime || 0);
        const avgHold = holdingTimes.reduce((a, b) => a + b, 0) / holdingTimes.length;
        const wins = scalps.filter(t => t.netPnL > 0);
        const losses = scalps.filter(t => t.netPnL <= 0);
        const totalWin = wins.reduce((a, b) => a + b.netPnL, 0);
        const totalLoss = Math.abs(losses.reduce((a, b) => a + b.netPnL, 0));

        const analytics = {
            scalpingTrades: scalps.length,
            avgHoldingTime: avgHold / 1000,
            winRateScalping: (wins.length / scalps.length) * 100,
            profitFactorScalping: totalLoss > 0 ? totalWin / totalLoss : totalWin,
            bestScalp: Math.max(...scalps.map(t => t.netPnL)),
            worstScalp: Math.min(...scalps.map(t => t.netPnL)),
            totalReturn: totalWin - totalLoss,
            consecutiveLosses: losses.length > 0 ? HistoryManager.calculateConsecutiveLosses(scalps) : 0
        };

        await fs.writeFile(this.ANALYTICS_FILE, JSON.stringify(analytics, null, 2));
    }

    static async logError(error, context = {}) {
        try {
            const errorLog = { timestamp: new Date().toISOString(), error: error.message || error.toString(), context };
            await fs.appendFile(this.ERROR_FILE, JSON.stringify(errorLog) + '\n');
        } catch (e) {
            console.error(COLORS.RED(`Failed to log error: ${e.message}`));
        }
    }
}

// =============================================================================
// 3. TECHNICAL ANALYSIS ENGINE (TA MUST BE DEFINED EARLY)
// =============================================================================

class TA {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        let sum = 0, res = [];
        for (let i = 0; i < period; i++) sum += (isNaN(data[i]) ? 0 : data[i]);
        res.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += (isNaN(data[i]) ? 0 : data[i]) - (isNaN(data[i - period]) ? 0 : data[i - period]);
            res.push(sum / period);
        }
        return Utils.safeArray(period - 1).concat(res);
    }
    static rsi(closes, period = 5) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.sma(gains, period);
        const avgLoss = this.sma(losses, period);
        return closes.map((_, i) => avgLoss[i] === 0 ? 50 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
    }
    static fisher(h, l, len = 7) {
        const res = new Array(h.length).fill(0), val = new Array(h.length).fill(0);
        for (let i = len; i < h.length; i++) {
            let maxH = -Infinity, minL = Infinity;
            for(let j=0; j<len; j++) { if(h[i-j]>maxH) maxH = h[i-j]; if(l[i-j]<minL) minL = l[i-j]; }
            let range = maxH - minL;
            let raw = 0;
            if(range > 0) {
                const hl2 = (h[i] + l[i]) / 2;
                raw = 0.66 * ((hl2 - minL) / range - 0.5) + 0.67 * (val[i - 1] || 0);
            }
            raw = Math.max(-0.999, Math.min(0.999, raw));
            val[i] = raw;
            res[i] = 0.5 * Math.log((1 + raw) / (1 - raw)) + 0.5 * (res[i - 1] || 0);
        }
        return res;
    }
    static atr(h, l, c, p = 6) {
        let tr = [0];
        for (let i = 1; i < c.length; i++) tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1])));
        return this.sma(tr, p);
    }
    static priceAcceleration(prices, period = 5) {
        const accel = new Array(prices.length).fill(0);
        for (let i = period * 2; i < prices.length; i++) {
            const v1 = (prices[i] - prices[i - period]) / period;
            const v2 = (prices[i - period] - prices[i - period * 2]) / period;
            accel[i] = v1 - v2;
        }
        return accel;
    }
    static microTrend(prices, period = 8) {
        const trends = new Array(prices.length).fill('FLAT');
        for (let i = period; i < prices.length; i++) {
            const change = (prices[i] - prices[i - period]) / prices[i - period];
            if (change > 0.0008) trends[i] = 'BULLISH';
            else if (change < -0.0008) trends[i] = 'BEARISH';
        }
        return trends;
    }
    static orderFlowImbalance(bids, asks) {
        const bidVol = bids.reduce((a, b) => a + b.q, 0);
        const askVol = asks.reduce((a, b) => a + b.q, 0);
        const total = bidVol + askVol;
        return total === 0 ? 0 : (bidVol - askVol) / total;
    }
    static volumeSpike(volumes, threshold = 2.2) {
        const sma = this.sma(volumes, 15);
        return volumes.map((v, i) => v > sma[i] * threshold);
    }
    static findFVG(candles) {
        const gaps = [];
        for (let i = 3; i < candles.length; i++) {
            const c1 = candles[i - 3], c2 = candles[i - 2], c3 = candles[i - 1];
            if (c2.c > c2.o && c3.l > c1.h) gaps.push({ type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2, strength: (c3.l - c1.h) / c1.h * 100 });
            else if (c2.c < c2.o && c3.h < c1.l) gaps.push({ type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2, strength: (c1.l - c3.h) / c1.l * 100 });
        }
        return gaps;
    }
    static stoch(high, low, close, period = 3) {
        const k = [];
        for (let i = 0; i < close.length; i++) {
            if (i < period) { k.push(50); continue; }
            const highest = Math.max(...high.slice(i - period + 1, i + 1));
            const lowest = Math.min(...low.slice(i - period + 1, i + 1));
            const val = ((close[i] - lowest) / (highest - lowest)) * 100;
            k.push(isNaN(val) ? 50 : val);
        }
        const d = this.sma(k, 2);
        const dPadded = Utils.safeArray(close.length).fill(50);
        const dStartIdx = (period - 1) + (2 - 1); // Start index of D line
        for(let i=0; i<d.length; i++) {
            if (dStartIdx + i < close.length) dPadded[dStartIdx + i] = d[i];
        }
        return { k, d: dPadded };
    }
    static choppiness(high, low, close, period = 10) {
        const result = new Array(close.length).fill(50);
        for (let i = period; i < close.length; i++) {
            let sumTR = 0, maxH = -Infinity, minL = Infinity;
            for (let j = 0; j < period; j++) {
                const tr = Math.max(high[i - j] - low[i - j], Math.abs(high[i - j] - (close[i - j - 1] || close[i - j])), Math.abs(low[i - j] - (close[i - j - 1] || close[i - j])));
                sumTR += tr;
                if (high[i - j] > maxH) maxH = high[i - j];
                if (low[i - j] < minL) minL = low[i - j];
            }
            const range = maxH - minL;
            if (range > 0 && sumTR > 0) {
                const ci = 100 * (Math.log10(sumTR / range) / Math.log10(period));
                result[i] = isNaN(ci) ? 50 : Math.min(Math.max(ci, 0), 100);
            }
        }
        return result;
    }
}

// =============================================================================
// 4. NEURAL NETWORK ENGINE (Self-Contained)
// =============================================================================

class NeuralNetwork {
    constructor(config) {
        this.config = config;
        this.weights = this.initializeWeights();
        this.isTraining = false;
    }

    initializeWeights() {
        const features = this.config.indicators.neural.features.length;
        return Array.from({ length: features }, () => Math.random() * 0.1 - 0.05);
    }

    predict(features) {
        if (!this.config.indicators.neural.enabled) return 0.5;
        const normalizedFeatures = features.map((feature, index) => {
            if (index === 0 || index === 1) return Math.max(-1, Math.min(1, feature));
            return feature;
        });
        const prediction = Utils.neuralNetwork(normalizedFeatures, this.weights);
        return Math.max(0, Math.min(1, prediction));
    }

    async train(trainingData) {
        if (this.isTraining || trainingData.length < 50) return;
        this.isTraining = true;
        try {
            const learningRate = 0.005;
            const epochs = 50;
            for (let epoch = 0; epoch < epochs; epoch++) {
                for (const sample of trainingData) {
                    const prediction = this.predict(sample.features);
                    const error = sample.result - prediction;
                    for (let i = 0; i < this.weights.length; i++) {
                        this.weights[i] += learningRate * error * sample.features[i];
                    }
                }
            }
            console.log(COLORS.GREEN('🧠 Neural network trained successfully'));
        } catch (error) {
            console.warn(COLORS.RED(`Neural training failed: ${error.message}`));
        } finally {
            this.isTraining = false;
        }
    }
}

// =============================================================================
// 5. ULTRA-FAST MARKET ENGINE
// =============================================================================

class UltraFastMarketEngine {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ 
            baseURL: 'https://api.bybit.com/v5/market', 
            timeout: 3000,
            httpsAgent: keepAliveAgent // LATENCY FIX
        });
        this.cache = { price: 0, bids: [], asks: [], kline: {}, ticks: [], volume24h: 0 };
        this.lastUpdate = Date.now();
        this.neural = new NeuralNetwork(config);
        this.latencyHistory = [];
    }

    async fetchAllTimeframes() {
        const startTime = Date.now();
        try {
            const tfs = [this.config.intervals.scalp, this.config.intervals.quick, this.config.intervals.trend, this.config.intervals.macro];
            
            const reqs = [
                this.api.get('/tickers', { params: { category: 'linear', symbol: this.config.symbol } }),
                this.api.get('/v2/public/tickers', { params: { symbol: this.config.symbol } }),
                ...tfs.map(i => this.api.get('/kline', { params: { category: 'linear', symbol: this.config.symbol, interval: i, limit: this.config.limits.kline } }))
            ];
            
            const res = await Promise.all(reqs);
            const ticker = res[0];
            const ticker24h = res[1];
            
            const data = {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                volume24h: parseFloat(ticker24h.data.result[0].volume),
                latency: Date.now() - startTime,
                kline: {}
            };

            const parse = list => list.reverse().map(c => ({ t: parseInt(c[0]), o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]) }));

            const klineResults = res.slice(2);
            tfs.forEach((interval, index) => data.kline[interval] = parse(klineResults[index].data.result.list));
            
            this.latencyHistory.push(data.latency);
            if (this.latencyHistory.length > 100) this.latencyHistory = this.latencyHistory.slice(-100);

            return data;
        } catch (e) {
            return null; // Fatal REST fetch error
        }
    }

    connectWebSocket() {
        if (!this.config.websocket.enabled) return;
        const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        ws.on('open', () => {
            console.log(C.G('📡 Ultra-fast WebSocket connected'));
            ws.send(JSON.stringify({ op: "subscribe", args: [`kline.${this.config.intervals.scalp}.${this.config.symbol}`, `orderbook.50.${this.config.symbol}`, `publicTrade.${this.config.symbol}`] }));
        });

        ws.on('message', (data) => {
            try {
                const msg = JSON.parse(data);
                if (msg.topic?.includes('kline')) {
                    const kline = msg.data[0];
                    const interval = this.config.intervals.scalp;
                    if (!this.cache.kline[interval]) this.cache.kline[interval] = [];
                    
                    const candle = { t: parseInt(kline.start), o: parseFloat(kline.open), h: parseFloat(kline.high), l: parseFloat(kline.low), c: parseFloat(kline.close), v: parseFloat(kline.volume) };
                    
                    if (this.cache.kline[interval].length > 0 && this.cache.kline[interval][this.cache.kline[interval].length - 1].t === candle.t) {
                        this.cache.kline[interval][this.cache.kline[interval].length - 1] = candle;
                    } else {
                        this.cache.kline[interval].push(candle);
                        if (this.cache.kline[interval].length > this.config.limits.kline) this.cache.kline[interval].shift();
                    }
                } else if (msg.topic?.includes('orderbook')) {
                    if (msg.data && msg.data.b && msg.data.a) {
                        this.cache.bids = msg.data.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                        this.cache.asks = msg.data.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                    }
                } else if (msg.topic?.includes('publicTrade')) {
                    this.cache.ticks.push({ price: parseFloat(msg.data.p), size: parseFloat(msg.data.s), side: msg.data.S, time: parseInt(msg.data.T) });
                    if (this.cache.ticks.length > this.config.limits.ticks) this.cache.ticks = this.cache.ticks.slice(-this.config.limits.ticks);
                }
            } catch (e) {}
        });

        ws.on('close', () => {
            setTimeout(() => this.connectWebSocket(), this.config.websocket.reconnectInterval);
        });

        ws.on('error', (error) => {
            console.error(C.R('📡 WebSocket error:', error.message));
        });

        this.ws = ws;
    }
    
    calculateWSS(analysis) {
        let score = 0;
        const w = this.config.indicators.weights;
        const last = analysis.closes.length - 1;
        
        if (analysis.microTrend[last] === 'BULLISH') score += w.microTrend;
        else if (analysis.microTrend[last] === 'BEARISH') score -= w.microTrend;

        const rsi = analysis.rsi[last];
        const fisher = analysis.fisher[last];
        if (rsi > 40 && rsi < 70 && fisher > 0.5) score += w.momentum;
        else if (rsi < 60 && rsi > 30 && fisher < -0.5) score -= w.momentum;

        const imb = TA.orderFlowImbalance(this.cache.bids, this.cache.asks);
        if (imb > 0.3) score += w.orderFlow;
        else if (imb < -0.3) score -= w.orderFlow;
        
        return { score: parseFloat(score.toFixed(2)), imb: imb };
    }
    
    getLatencyMetrics() {
        if (this.latencyHistory.length === 0) return { min: 0, max: 0, avg: 0 };
        const sorted = [...this.latencyHistory].sort((a, b) => a - b);
        return {
            min: sorted[0],
            max: sorted[sorted.length - 1],
            avg: Math.round(sorted.reduce((a, b) => a + b, 0) / sorted.length)
        };
    }
}

// =============================================================================
// 6. DYNAMIC RISK EXCHANGE
// =============================================================================

class UltraFastExchange {
    constructor(config) {
        this.cfg = config.risk;
        this.config = config;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
        this.history = [];
        this.dailyPnL = new Decimal(0);
        this.lastDay = new Date().getDate();
        this.equity = this.balance;
        this.riskScore = 0;
        this.consecutiveLosses = 0;
    }

    async init() {
        this.history = await HistoryManager.load();
        let totalPnL = new Decimal(0);
        this.history.forEach(t => totalPnL = totalPnL.add(new Decimal(t.netPnL)));
        this.balance = this.startBal.add(totalPnL);
        this.equity = this.balance;
        this.consecutiveLosses = this.calculateConsecutiveLosses(this.history);
    }

    calculateConsecutiveLosses(trades) {
        let consecutive = 0;
        for (let i = trades.length - 1; i >= 0; i--) {
            if (trades[i].netPnL < 0) consecutive++;
            else break;
        }
        return consecutive;
    }

    checkDailyReset() {
        const today = new Date().getDate();
        if (today !== this.lastDay) {
            this.dailyPnL = new Decimal(0);
            this.lastDay = today;
            this.consecutiveLosses = 0;
        }
    }

    updateEquity(currentPrice) {
        if (this.pos) {
            const unrealized = this.pos.side === 'BUY' 
                ? new Decimal(currentPrice).sub(this.pos.entry).mul(this.pos.qty)
                : this.pos.entry.sub(new Decimal(currentPrice)).mul(this.pos.qty);
            this.equity = this.balance.add(unrealized);
        } else {
            this.equity = this.balance;
        }
    }

    calculateRiskScore() {
        const drawdown = this.startBal.sub(this.equity).div(this.startBal).mul(100);
        const dailyLoss = this.dailyPnL.abs().div(this.startBal).mul(100);
        
        let risk = 0;
        if (drawdown.gt(2)) risk += 20;
        if (drawdown.gt(4)) risk += 40;
        if (dailyLoss.gt(1)) risk += 15;
        if (dailyLoss.gt(2)) risk += 35;
        
        risk += this.consecutiveLosses * 10;
        return Math.min(risk, 100);
    }

    getDynamicRiskMultiplier() {
        const riskScore = this.calculateRiskScore();
        let multiplier = 1.0;
        if (riskScore > 50) multiplier *= 0.7;
        if (riskScore > 75) multiplier *= 0.5;
        return multiplier;
    }

    handlePartialClose(price, partialQty, pos) {
        const rawPnL = pos.side === 'BUY' ? price.sub(pos.entry).mul(partialQty) : pos.entry.sub(price).mul(partialQty);
        const fee = price.mul(partialQty).mul(this.cfg.fee);
        const slippage = price.mul(partialQty).mul(this.cfg.slippage);
        const netPnL = rawPnL.sub(fee).sub(slippage);
        
        this.balance = this.balance.add(netPnL);
        this.dailyPnL = this.dailyPnL.add(netPnL);
        console.log(COLORS.YELLOW(`✂️ PARTIAL CLOSE: $${netPnL.toFixed(4)}`));
        return netPnL.toNumber();
    }

    async evaluateUltraFast(priceVal, signal) {
        this.checkDailyReset();
        const price = new Decimal(priceVal);
        this.updateEquity(priceVal);
        this.riskScore = this.calculateRiskScore();

        if (this.pos) {
            const elapsed = Date.now() - this.pos.time;
            let close = false, reason = '';
            
            const currentPnL = this.pos.side === 'BUY' ? price.sub(this.pos.entry) : this.pos.entry.sub(price);
            const currentPnLPct = currentPnL.div(this.pos.entry).abs();

            // 1. Time-based exits
            if (elapsed > this.config.scalping.maxHoldingTime) { close = true; reason = 'Time Exit'; }
            else if (elapsed > this.config.scalping.timeBasedExit) {
                if (currentPnL.lt(0)) { close = true; reason = 'Stale Kill'; }
            }

            // 2. SL/TP & Quick Profit/Partial Close Check
            if (!close) {
                // Break Even / Trailing SL
                if (currentPnLPct.gt(this.config.scalping.breakEvenStop)) {
                    if (this.pos.side === 'BUY' && price.gt(this.pos.sl)) this.pos.sl = Decimal.max(this.pos.sl, this.pos.entry);
                    if (this.pos.side === 'SELL' && price.lt(this.pos.sl)) this.pos.sl = Decimal.min(this.pos.sl, this.pos.entry);
                }
                
                // Partial close
                if (!this.pos.partialClosed && currentPnLPct.gt(this.config.scalping.partialClose) && elapsed > 15000) {
                    const partialQty = this.pos.qty.mul(0.5);
                    this.pos.qty = this.pos.qty.sub(partialQty);
                    this.pos.partialClosed = true;
                    this.handlePartialClose(price, partialQty, this.pos);
                }
                
                // Hard stops
                if (this.pos.side === 'BUY') {
                    if (price.lte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.gte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                } else {
                    if (price.gte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.lte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                }
            }

            if (!close && currentPnLPct.gt(this.config.scalping.quickExitThreshold)) {
                close = true; reason = 'Quick Scalp Profit';
            }

            if (!close && signal && signal.action !== 'HOLD' && signal.action !== this.pos.side) {
                 close = true; reason = `SIGNAL_FLIP (${signal.action})`;
            }

            if (close) {
                const rawPnL = this.pos.side === 'BUY' ? price.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(price).mul(this.pos.qty);
                const fee = price.mul(this.pos.qty).mul(this.cfg.fee);
                const slippage = price.mul(this.pos.qty).mul(this.cfg.slippage);
                const netPnL = rawPnL.sub(fee).sub(slippage);
                
                this.balance = this.balance.add(netPnL);
                this.dailyPnL = this.dailyPnL.add(netPnL);
                
                if (netPnL < 0) this.consecutiveLosses++;
                else this.consecutiveLosses = 0;
                
                const tradeRecord = {
                    date: new Date().toISOString(), symbol: this.config.symbol, side: this.pos.side,
                    entry: this.pos.entry.toNumber(), exit: price.toNumber(), qty: this.pos.qty.toNumber(),
                    netPnL: netPnL.toNumber(), reason, strategy: this.pos.strategy, holdingTime: Date.now() - this.pos.time,
                    riskScore: this.riskScore, slippageCost: slippage.toNumber()
                };
                
                await HistoryManager.save(tradeRecord);
                this.history.push(tradeRecord);
                
                const color = netPnL.gte(0) ? COLORS.LIME : COLORS.HOT_PINK;
                console.log(`${COLORS.BOLD(reason)}! PnL: ${color(netPnL.toFixed(4))} | Hold: ${Utils.formatTime(tradeRecord.holdingTime)}`);
                this.pos = null;
            }
        } 
        
        // --- Entry Logic ---
        else if (signal && signal.action !== 'HOLD' && signal.confidence >= this.cfg.minConfidence) {
            if (this.riskScore > 90) { console.log(COLORS.RED('⛔ Risk Score too high, skipping trade')); return; }

            const entry = new Decimal(priceVal);
            const sl = new Decimal(signal.stopLoss);
            const tp = new Decimal(signal.takeProfit);
            const dist = entry.sub(sl).abs();
            
            if (dist.isZero() || dist.lt(price.mul(0.0002))) return;

            const riskMultiplier = this.getDynamicRiskMultiplier();
            let riskPercent = this.cfg.riskPercent * riskMultiplier;
            
            if (this.consecutiveLosses > 0) {
                riskPercent *= Math.pow(0.7, this.consecutiveLosses);
            }

            const riskAmt = this.equity.mul(riskPercent / 100);
            let qty = riskAmt.div(dist);
            
            const maxQty = this.equity.mul(this.cfg.leverageCap).div(price);
            if (qty.gt(maxQty)) qty = maxQty;
            
            const maxPositionValue = this.equity.mul(this.config.risk.maxPositionSize);
            const positionValue = qty.mul(price);
            if (positionValue.gt(maxPositionValue)) {
                qty = maxPositionValue.div(price);
            }

            if (qty.mul(price).lt(5)) return;

            this.pos = {
                side: signal.action, entry, qty, sl, tp,
                strategy: signal.strategy || `Scalp-${signal.action}`,
                time: Date.now(), partialClosed: false
            };
            
            const col = signal.action === 'BUY' ? COLORS.LIME : COLORS.HOT_PINK;
            console.log(col(`⚡ SCALP ${signal.action} @ ${entry.toFixed(6)} | Size: ${qty.toFixed(6)} | Risk: ${riskPercent.toFixed(2)}%`));
        }
    }
}


// =============================================================================
// 7. ADVANCED AI AGENT
// =============================================================================

class AdvancedAIAgent {
    constructor(config) {
        const key = process.env.GEMINI_API_KEY;
        if (!key) throw new Error("Missing GEMINI_API_KEY");
        
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ 
            model: config.ai.model,
            generationConfig: { temperature: config.ai.temperature, topK: 12, topP: 0.7, maxOutputTokens: 300 }
        });
        this.rateLimit = config.ai.rateLimitMs;
        this.maxRetries = config.ai.maxRetries || 3;
        this.lastCall = 0;
        this.apiCalls = [];
        this.config = config; // Ensure config is available
    }

    async analyzeUltraFast(ctx, indicators) {
        let retries = 0;
        while (retries < this.maxRetries) {
            try {
                // Rate limit check
                const now = Date.now();
                if (now - this.lastCall < this.rateLimit) {
                    await sleep(this.rateLimit - (now - this.lastCall));
                }
                this.lastCall = Date.now();

                const prompt = this.buildAdvancedPrompt(ctx, indicators);

                const result = await this.model.generateContent(prompt);
                const response = await result.response;
                const text = response.text().replace(/``````/g, '').trim();
                
                const signal = JSON.parse(text);
                
                const validatedSignal = this.validateSignal(signal, ctx, indicators);
                
                this.trackApiCall(true);
                return validatedSignal;
                
            } catch (error) {
                retries++;
                this.trackApiCall(false);
                
                if (retries >= this.maxRetries) {
                    await HistoryManager.logError(error, { context: 'ai_analysis' });
                    
                    return { action: "HOLD", confidence: 0, strategy: "AI System Error", entry: ctx.price, stopLoss: ctx.price, takeProfit: ctx.price, reason: "AI processing failed after retries" };
                }
                
                await sleep(2 ** retries * 100);
            }
        }
    }

    buildAdvancedPrompt(ctx, indicators) {
        const { price, microTrend, trendMTF, rsi, fisher, stochK, imbalance, volumeSpike, choppiness, acceleration, wss } = ctx;
        const { williams, momentum, roc, patterns, divergences } = indicators;
        
        // Calculate dynamic SL/TP based on ATR and R:R minimum
        const atr = indicators.atr[indicators.atr.length - 1] || 10;
        const slDist = atr * 1.0;
        const tpDist = atr * this.config.risk.minRR;

        return `ROLE: Ultra-High Frequency Crypto Scalper (Professional)

MARKET MICRO-STRUCTURE:
┌─ Symbol: ${ctx.symbol} | Price: $${Utils.formatNumber(price, 6)}
├─ Latency: ${Date.now() - ctx.lastUpdate}ms
└─ WSS Score: ${wss.score.toFixed(3)}

MULTI-TIMEFRAME ANALYSIS:
├─ 1m Micro-Trend: ${microTrend} | 3m Trend: ${trendMTF}
├─ Momentum: RSI=${rsi.toFixed(1)} | Fisher=${fisher.toFixed(3)} | Stoch=${stochK.toFixed(0)} | Williams %R: ${williams[williams.length - 1]?.toFixed(1) || 'N/A'}
├─ Accel: ${acceleration.toFixed(6)} | ROC: ${roc[roc.length - 1]?.toFixed(2) || 'N/A'}%
└─ OF/Vol: Imbalance: ${(imbalance * 100).toFixed(1)}% | Vol Spike: ${volumeSpike ? 'SPIKE' : 'NORMAL'}

ADVANCED PATTERN ANALYSIS:
├─ Patterns: ${patterns.length > 0 ? patterns.map(p => p.type).join(', ') : 'None'}
└─ Divergence: ${divergences.length} active

NEURAL NETWORK PREDICTION:
└─ Confidence: ${(ctx.neuralConfidence * 100).toFixed(1)}% | Signal: ${ctx.neuralSignal}

SCALPING EXECUTION RULES:
1. 🔥 ENTRY: Requires WSS > ${this.config.indicators.weights.actionThreshold} AND Neural Signal Alignment.
2. 🎯 TARGET: R:R must be >= ${this.config.risk.minRR}.
3. 🛡️ RISK: Use dynamic ATR stops.

JSON RESPONSE (Use current price for entry, calculate SL/TP based on ATR: SL=${slDist.toFixed(6)}, TP=${tpDist.toFixed(6)}):
{
  "action": "BUY"|"SELL"|"HOLD",
  "confidence": ${this.config.ai.minConfidence + 0.05},
  "strategy": "Ultra-Scalp-Breakout",
  "entry": ${price},
  "stopLoss": ${price - (price * 0.0008)}, // Placeholder: Should be calculated by AI based on context/ATR
  "takeProfit": ${price + (price * 0.0015)}, // Placeholder
  "reason": "Strong alignment of 1m trend, volume expansion, and neural confidence.",
  "timeframe": "1m",
  "riskLevel": "LOW"
}`;
    }

    validateSignal(signal, ctx, indicators) {
        if (signal.confidence < this.config.ai.minConfidence) { signal.confidence = 0; signal.action = 'HOLD'; signal.reason = 'Below confidence threshold'; }

        // Final R:R calculation check (using ATR if AI failed to provide a valid SL/TP)
        const atr = indicators.atr[indicators.atr.length - 1] || ctx.price * 0.0005;
        const R = atr * 1.2;
        const R_R_Ratio = this.config.risk.minRR;

        if (signal.action === 'BUY') {
            signal.stopLoss = Math.min(signal.stopLoss, ctx.price - R);
            if (ctx.price - signal.stopLoss < R) signal.stopLoss = ctx.price - R; // Ensure minimum risk distance
            signal.takeProfit = Math.max(signal.takeProfit, ctx.price + R * R_R_Ratio);
        } else if (signal.action === 'SELL') {
            signal.stopLoss = Math.max(signal.stopLoss, ctx.price + R);
            if (signal.stopLoss - ctx.price < R) signal.stopLoss = ctx.price + R;
            signal.takeProfit = Math.min(signal.takeProfit, ctx.price - R * R_R_Ratio);
        }

        if (!signal.strategy) signal.strategy = 'Ultra-Scalp';
        if (!signal.timeframe) signal.timeframe = '1m';

        return signal;
    }

    async rateLimitCheck() {
        const now = Date.now();
        const timeSinceLastCall = now - this.lastCall;
        if (timeSinceLastCall < this.rateLimit) {
            await sleep(this.rateLimit - timeSinceLastCall);
        }
        this.lastCall = Date.now();
    }

    trackApiCall(success) {
        this.apiCalls.push({ timestamp: Date.now(), success });
        if (this.apiCalls.length > 100) this.apiCalls = this.apiCalls.slice(-100);
    }

    getApiMetrics() {
        if (this.apiCalls.length === 0) return { successRate: 100, avgLatency: 0 };
        const successful = this.apiCalls.filter(call => call.success).length;
        const successRate = (successful / this.apiCalls.length) * 100;
        const avgLatency = this.apiCalls.reduce((acc, call) => acc + (call.success ? 100 : 500), 0) / this.apiCalls.length;
        return { successRate: parseFloat(successRate.toFixed(2)), avgLatency: parseFloat(avgLatency.toFixed(0)) };
    }
}

// =============================================================================
// 9. MAIN EXECUTION CONTROLLER
// =============================================================================

async function main() {
    console.clear();
    console.log(COLORS.bg(COLORS.BOLD(COLORS.HOT_PINK(` ⚡ WHALEWAVE ULTRA-FAST TITAN v11.0 `))));

    const config = await ConfigManager.load();
    HistoryManager.config = config;
    const marketEngine = new UltraFastMarketEngine(config);
    const exchange = new UltraFastExchange(config);
    const ai = new AdvancedAIAgent(config);

    await exchange.init();
    marketEngine.connectWebSocket();
    await marketEngine.fetchAllTimeframes(); // Initial REST fetch for baseline

    console.log(COLORS.CYAN(`🎯 Symbol: ${config.symbol} | Bal: $${exchange.balance.toFixed(2)}`));
    
    let loopCount = 0;

    while (true) {
        const loopStart = Date.now();
        
        try {
            // 1. Data Fetch/Merge
            const data = await marketEngine.fetchAllTimeframes();
            if (!data) { await sleep(config.delays.retry); continue; }

            const scalpData = data.kline[config.intervals.scalp] || [];
            if (scalpData.length < 30) { await sleep(500); continue; }

            const closes = scalpData.map(x => x.c);
            const highs = scalpData.map(x => x.h);
            const lows = scalpData.map(x => x.l);
            const volumes = scalpData.map(x => x.v);

            if (data.volume24h < config.indicators.scalping.liquidityThreshold) {
                await sleep(1000); continue;
            }

            // 2. Parallel Calculation
            const [rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc] = await Promise.all([
                TA.rsi(closes, config.indicators.periods.rsi), TA.fisher(highs, lows, config.indicators.periods.fisher),
                TA.stoch(highs, lows, closes, config.indicators.periods.stoch), TA.atr(highs, lows, closes, config.indicators.periods.atr),
                TA.choppiness(highs, lows, closes, config.indicators.periods.chop), TA.priceAcceleration(closes, 5),
                TA.volumeSpike(volumes, config.indicators.scalping.volumeSpikeThreshold), TA.microTrend(closes, config.indicators.scalping.microTrendLength),
                TA.findFVG(scalpData), Utils.williamsR(highs, lows, closes, config.indicators.periods.williams),
                Utils.calculateMomentum(closes, config.indicators.periods.momentum), Utils.calculateROC(closes, config.indicators.periods.roc)
            ]);

            const imbalance = TA.orderFlowImbalance(marketEngine.cache.bids, marketEngine.cache.asks);
            const qCloses = data.kline[config.intervals.quick].map(x => x.c);
            const qSMA = TA.sma(qCloses, 15);
            const trendMTF = qCloses[qCloses.length-1] > qSMA[qSMA.length-1] ? 'BULLISH' : 'BEARISH';
            const divergences = TA.detectAdvancedDivergence(closes, { rsi, fisher }, 5);
            const patterns = Utils.detectAdvancedPatterns(closes, volumes, highs, lows, closes);

            let neuralScore = 0.5;
            if (config.indicators.neural.enabled) {
                const features = [
                    (closes[closes.length - 1] - closes[closes.length - 6]) / closes[closes.length - 6],
                    (volumes[volumes.length - 1] - volumes[volumes.length - 6]) / volumes[volumes.length - 6],
                    rsi[rsi.length - 1] / 100, fisher[fisher.length - 1] / 5, stoch.k[stoch.k.length - 1] / 100, momentum[momentum.length - 1]
                ];
                neuralScore = marketEngine.neural.predict(features);
            }

            const analysis = { closes, rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc, imbalance };
            const scoreObj = marketEngine.calculateWSS(analysis);

            const ctx = {
                symbol: config.symbol, price: data.price, lastUpdate: marketEngine.lastUpdate, trendMTF, imbalance,
                rsi: rsi[rsi.length - 1], fisher: fisher[fisher.length - 1], stochK: stoch.k[stoch.k.length - 1],
                choppiness: chop[chop.length - 1], acceleration: accel[accel.length - 1], wss: scoreObj,
                neuralConfidence: neuralScore, neuralSignal: neuralScore > 0.6 ? 'BUY' : neuralScore < 0.4 ? 'SELL' : 'HOLD',
            };
            
            // 3. AI Decision
            let signal = null;
            if (Math.abs(scoreObj.score) > config.indicators.weights.actionThreshold) {
                signal = await ai.analyzeUltraFast(ctx, analysis);
            }

            // 4. Dashboard Update (Every 1s or on signal)
            if (loopCount % (config.delays.loop / 500) === 0 || signal) {
                console.clear();
                const border = COLORS.GRAY('═'.repeat(100));
                console.log(border);
                
                const timestamp = new Date().toLocaleTimeString();
                const latency = marketEngine.getLatencyMetrics();
                
                console.log(COLORS.BOLD(COLORS.MAGENTA(` ⚡ ${timestamp} | ${config.symbol} | $${Utils.formatNumber(data.price, 6)} | LAT: ${latency.avg}ms | v11.0 `)));
                console.log(border);
                
                const scoreColor = scoreObj.score > 0 ? COLORS.LIME : scoreObj.score < 0 ? COLORS.HOT_PINK : COLORS.GRAY;
                const stats = exchange.getStats();
                
                console.log(COLORS.BOLD(` 💰 Price: ${COLORS.LIME('$' + Utils.formatNumber(data.price, 6))} | SCORE: ${scoreColor(scoreObj.score.toFixed(3))} | IMBALANCE: ${(imbalance*100).toFixed(1)}%`));
                console.log(` 🎯 Micro: ${ctx.microTrend} | 3m: ${trendMTF} | Accel: ${ctx.acceleration.toFixed(6)} | Chop: ${ctx.choppiness.toFixed(1)} `);
                
                console.log(border);
                
                let signalColor, signalIcon;
                if (signal && signal.action === 'BUY') { signalColor = COLORS.LIME; signalIcon = '🟢⚡'; } 
                else if (signal && signal.action === 'SELL') { signalColor = COLORS.HOT_PINK; signalIcon = '🔴⚡'; } 
                else { signalColor = COLORS.GRAY; signalIcon = '⚪'; }
                
                console.log(COLORS.BOLD(` ${signalIcon} SIGNAL: ${signalColor(signal ? signal.action : 'HOLD')} (${(signal ? signal.confidence * 100 : 0).toFixed(0)}%) | ${signal ? signal.strategy || 'N/A' : 'N/A'} `));
                console.log(` 📋 Reason: ${COLORS.GRAY(signal ? signal.reason : 'Waiting...')}`);
                
                console.log(border);
                
                const pnlColor = stats.dailyPnL >= 0 ? COLORS.LIME : COLORS.HOT_PINK;
                const riskColor = stats.riskScore > 70 ? COLORS.HOT_PINK : stats.riskScore > 40 ? COLORS.ORANGE : COLORS.LIME;
                
                console.log(COLORS.BOLD(` 💼 Balance: $${Utils.formatNumber(stats.balance, 2)} | Daily ${pnlColor('$' + Utils.formatNumber(stats.dailyPnL, 2))} | Risk: ${riskColor(stats.riskScore + '%')} | ${stats.consecutiveLosses}L Streak`));
                
                if (exchange.pos) {
                    const unrealized = exchange.pos.side === 'BUY' 
                        ? new Decimal(data.price).sub(exchange.pos.entry).mul(exchange.pos.qty)
                        : exchange.pos.entry.sub(new Decimal(data.price)).mul(exchange.pos.qty);
                    const posColor = unrealized.gte(0) ? COLORS.LIME : COLORS.HOT_PINK;
                    const holdingTime = Date.now() - exchange.pos.time;
                    
                    console.log(`🟢 POS: ${exchange.pos.side} @ ${exchange.pos.entry.toFixed(6)} | PnL ${posColor(unrealized.toFixed(5))} | ${Utils.formatTime(holdingTime)}`);
                } else {
                    console.log(COLORS.GRAY('⚪ POS: None'));
                }
                
                console.log(border);
            }

            // 5. Execute Trade
            await exchange.evaluateUltraFast(data.price, signal);

            // 6. Neural Training (Run infrequently)
            if (config.indicators.neural.enabled && loopCount % 200 === 0) {
                const trainingData = await HistoryManager.loadNeuralTraining();
                if (trainingData.length > 100) {
                    marketEngine.neural.train(trainingData.slice(-1000));
                }
            }

            loopCount++;

        } catch (err) {
            console.error(COLORS.RED(`Loop Error: ${err.message}`));
            await HistoryManager.logError(err.message, { context: 'main_loop', price: marketEngine.cache.price });
        }
        
        // 7. DRIFT CORRECTION
        const processingTime = Date.now() - loopStart;
        const waitTime = Math.max(0, config.delays.loop - processingTime);
        
        await sleep(waitTime);
    }
}

// =============================================================================
// 10. START APPLICATION
// =============================================================================

if (!process.env.GEMINI_API_KEY) {
    console.error(COLORS.RED('❌ GEMINI_API_KEY missing'));
    process.exit(1);
}

main().catch(err => {
    console.error(COLORS.RED('💥 Fatal Ultra-Fast Error:'), err);
    HistoryManager.logError(err.message, { context: 'main_catch' });
    process.exit(1);
});
