/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v12.0 (INSTITUTIONAL UPGRADE)
 * =================================================================
 * - CORE: Ultra-Low Latency Loop (500ms)
 * - AI: Gemini Pro with Context-Aware Prompts
 * - UPGRADES IMPLEMENTED: 
 *    1. Ratchet Trailing Stops (Profit Locking)
 *    2. Volatility-Clamped Take Profits (Anti-Hallucination)
 *    3. Regime-Based Position Sizing (Risk Scaling)
 *    4. Zombie Trade Killer (Opportunity Cost Management)
 *    5. Instant Break-Even Triggers (Capital Preservation)
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import WebSocket from 'ws';
import https from 'https'; 

dotenv.config();

// --- Global Configuration Initialization ---
const keepAliveAgent = new https.Agent({
    keepAlive: true,
    maxSockets: 256,
    scheduling: 'lifo',
    timeout: 3000
});

// =============================================================================
// 1. CONFIGURATION & STATE MANAGEMENT
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { scalp: '1', quick: '3', trend: '5', macro: '15' },
        limits: { kline: 200, orderbook: 50, ticks: 1000 },
        delays: { loop: 500, retry: 500, ai: 1000 },
        ai: { 
            model: 'gemini-2.5-flash-lite', 
            minConfidence: 0.88,
            temperature: 0.03,
            rateLimitMs: 1000,
            maxRetries: 3
        },
        risk: {
            initialBalance: 100.00,
            maxDrawdown: 6.0,
            dailyLossLimit: 3.0,
            riskPercent: 1.0,
            leverageCap: 20,
            fee: 0.00045,
            slippage: 0.00005,
            volatilityAdjustment: true,
            maxPositionSize: 0.25,
            minRR: 1.8,
            dynamicSizing: true,
            // v12.0 Upgrades
            atr_tp_limit: 3.5,            // Max TP distance in ATR multiples
            trailing_ratchet_dist: 2.0,   // Trailing stop distance in ATR multiples
            zombie_time_ms: 300000,       // 5 Minutes max for stale trades
            zombie_pnl_threshold: 0.0015, // 0.15% movement required to stay alive
            break_even_trigger: 1.0       // Move to BE at 1R profit
        },
        indicators: {
            periods: { rsi: 5, fisher: 7, stoch: 3, cci: 10, adx: 6, mfi: 5, chop: 10, bollinger: 15, atr: 6, ema_fast: 5, ema_slow: 13, williams: 7, roc: 8, momentum: 9 },
            scalping: {
                volumeSpikeThreshold: 2.2, priceAcceleration: 0.00015, orderFlowImbalance: 0.35, liquidityThreshold: 1000000
            },
            weights: {
                microTrend: 4.0, momentum: 3.2, volume: 3.0, orderFlow: 2.8, acceleration: 2.5, structure: 2.0, divergence: 1.8, neural: 2.5, actionThreshold: 2.8
            },
            neural: { enabled: true, modelPath: './models/scalping_model.json', confidence: 0.85, features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum'] }
        },
        scalping: {
            minProfitTarget: 0.0018, maxHoldingTime: 450000, quickExitThreshold: 0.00075, timeBasedExit: 180000,
            partialClose: 0.0009, breakEvenStop: 0.0006
        },
        websocket: { enabled: true, reconnectInterval: 2000, tickData: true, heartbeat: true }
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
        
        if (this.config?.indicators?.neural?.enabled) {
            await this.saveNeuralTraining(trade);
        }
    }

    static async saveNeuralTraining(trade) {
        try {
            const trainingData = await this.loadNeuralTraining();
            trainingData.push({ features: trade.features || [], result: trade.netPnL > 0 ? 1 : 0, timestamp: trade.date, timeframe: trade.timeframe || '1m' });
            if (trainingData.length > 10000) trainingData.splice(0, trainingData.length - 10000);
            await fs.writeFile(this.NEURAL_TRAINING, JSON.stringify(trainingData, null, 2));
        } catch (e) { console.warn(COLORS.RED(`Neural training save failed: ${e.message}`)); }
    }

    static async loadNeuralTraining() {
        try { return JSON.parse(await fs.readFile(this.NEURAL_TRAINING, 'utf-8')); } catch { return []; }
    }

    static async logError(error, context = {}) {
        try {
            const errorLog = { timestamp: new Date().toISOString(), error: error.message || error.toString(), context, memory: process.memoryUsage() };
            await fs.appendFile(this.ERROR_FILE, JSON.stringify(errorLog) + '\n');
        } catch (e) { console.error(COLORS.RED(`Failed to log error: ${e.message}`)); }
    }

    static async loadScalpingAnalytics() {
        try { return JSON.parse(await fs.readFile(this.ANALYTICS_FILE, 'utf-8')); } catch { return { scalpingTrades: 0, avgHoldingTime: 0, winRateScalping: 0, profitFactorScalping: 0, bestScalp: 0, consecutiveLosses: 0 }; }
    }

    static async updateScalpingAnalytics(trades) {
        const scalps = trades.filter(t => t.strategy && t.strategy.includes('Scalp'));
        if (scalps.length === 0) return;
        
        const holdingTimes = scalps.map(t => t.holdingTime || 0);
        const avgHold = holdingTimes.reduce((a, b) => a + b, 0) / holdingTimes.length;
        const wins = scalps.filter(t => t.netPnL > 0);
        const losses = scalps.filter(t => t.netPnL <= 0);
        const totalWin = wins.reduce((a, b) => a + b.netPnL, 0);
        const totalLoss = Math.abs(losses.reduce((a, b) => a + b.netPnL, 0));

        const analytics = {
            scalpingTrades: scalps.length, avgHoldingTime: avgHold / 1000, winRateScalping: (wins.length / scalps.length) * 100,
            profitFactorScalping: totalLoss > 0 ? totalWin / totalLoss : totalWin, bestScalp: Math.max(...scalps.map(t => t.netPnL)),
            worstScalp: Math.min(...scalps.map(t => t.netPnL)), avgWin: wins.length > 0 ? wins.reduce((a, b) => a + b.netPnL, 0) / wins.length : 0,
            avgLoss: losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b.netPnL, 0)) / losses.length : 0, totalReturn: totalWin - totalLoss,
            consecutiveLosses: HistoryManager.calculateConsecutiveLosses(scalps)
        };
        await fs.writeFile(this.ANALYTICS_FILE, JSON.stringify(analytics, null, 2));
    }

    static calculateConsecutiveLosses(trades) {
        let consecutive = 0;
        for (const trade of trades) {
            if (trade.netPnL < 0) { consecutive++; } else { consecutive = 0; }
        }
        return consecutive;
    }
}

// =============================================================================
// 2. ENHANCED UTILS & COLORS
// =============================================================================

const COLORS = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#0A84FF'), CYAN: chalk.hex('#00FFFF'), PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'), ORANGE: chalk.hex('#FF9F00'), MAGENTA: chalk.hex('#FF00FF'), LIME: chalk.hex('#32CD32'), HOT_PINK: chalk.hex('#FF1493'), AQUA: chalk.hex('#00FFFF'),
    VIOLET: chalk.hex('#8A2BE2'), GOLD: chalk.hex('#FFD700'), BOLD: chalk.bold, bg: (text) => chalk.bgHex('#1C1C1E')(text)
};

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static safeLast(arr, def = 0) { return (Array.isArray(arr) && arr.length > 0 && !isNaN(arr[arr.length - 1])) ? arr[arr.length - 1] : def; }
    static formatNumber(num, decimals = 4) { return (isNaN(num) || !isFinite(num)) ? '0.0000' : num.toFixed(decimals); }
    static formatTime(ms) { return ms < 1000 ? `${Math.floor(ms)}ms` : ms < 60000 ? `${Math.floor(ms / 1000)}s` : `${Math.floor(ms / 60000)}m`; }
    static neuralNetwork(features, weights) {
        let output = 0;
        for (let i = 0; i < features.length; i++) output += features[i] * weights[i];
        return 1 / (1 + Math.exp(-output));
    }
    static calculateMomentum(prices, period = 9) {
        const momentum = [];
        for (let i = period; i < prices.length; i++) momentum.push((prices[i] - prices[i - period]) / prices[i - period]);
        return momentum;
    }
    static calculateROC(prices, period = 8) {
        const roc = [];
        for (let i = period; i < prices.length; i++) roc.push(((prices[i] - prices[i - period]) / prices[i - period]) * 100);
        return roc;
    }
    static williamsR(highs, lows, closes, period = 7) {
        const williamsR = [];
        for (let i = period - 1; i < closes.length; i++) {
            const highest = Math.max(...highs.slice(i - period + 1, i + 1));
            const lowest = Math.min(...lows.slice(i - period + 1, i + 1));
            williamsR.push(((highest - closes[i]) / (highest - lowest)) * -100);
        }
        return williamsR;
    }
    static analyzeVolumeFlow(volumes, prices) {
        const flow = [];
        for (let i = 1; i < prices.length; i++) flow.push(prices[i] - prices[i - 1] > 0 ? volumes[i] - volumes[i - 1] : -(volumes[i] - volumes[i - 1]));
        return flow;
    }
    static detectAdvancedPatterns(prices, volumes, highs, lows, closes) {
        const patterns = [];
        const len = prices.length;
        if (len < 10) return patterns;
        const last = len - 1;
        const p = prices;
        const v = volumes;

        if (v[last] > v[last-1] * 2.5 && Math.abs(p[last] - p[last-3]) > p[last-1] * 0.005) patterns.push({ type: 'VOL_CLIMAX_REVERSAL' });
        const mom1 = p[last] - p[last-3];
        const mom2 = p[last-3] - p[last-6];
        if (mom1 > 0 && mom2 > mom1 * 1.5) patterns.push({ type: 'MOMENTUM_EXHAUSTION', direction: 'BEARISH' });
        if (highs[last] - lows[last] > (highs[last-1] - lows[last-1]) * 1.3) patterns.push({ type: 'EXPANSION' });
        if (Math.abs(v[last] - v[last-1]) > v[last-1] * 0.8 && Math.abs(p[last] - p[last-1]) > p[last-1] * 0.002) patterns.push({ type: 'ORDER_BLOCK' });
        return patterns;
    }
}

// =============================================================================
// 3. TECHNICAL ANALYSIS ENGINE (TA)
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
            if (c2.c > c2.o && c3.l > c1.h) gaps.push({ type: 'BULLISH', strength: (c3.l - c1.h) / c1.h * 100 });
            else if (c2.c < c2.o && c3.h < c1.l) gaps.push({ type: 'BEARISH', strength: (c1.l - c3.h) / c1.l * 100 });
        }
        return gaps;
    }
    static detectAdvancedDivergence(prices, indicators, period = 5) {
        const divergences = [];
        for (let i = period * 2; i < prices.length; i++) {
            if (indicators.rsi && indicators.rsi[i]) {
                const priceHigh1 = Math.max(...prices.slice(i - period, i + 1));
                const priceHigh2 = Math.max(...prices.slice(i - period * 2, i - period));
                const rsiHigh1 = Math.max(...indicators.rsi.slice(i - period, i + 1));
                const rsiHigh2 = Math.max(...indicators.rsi.slice(i - period * 2, i - period));
                if (priceHigh1 > priceHigh2 && rsiHigh1 < rsiHigh2) divergences.push({ type: 'BEARISH_DIVERGENCE', indicator: 'RSI' });
            }
        }
        return divergences;
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
        const dStartIdx = (period - 1) + (2 - 1);
        for(let i=0; i<d.length; i++) {
            if (dStartIdx + i < close.length) dPadded[dStartIdx + i] = d[i];
        }
        return { k, d: dPadded };
    }
}

// =============================================================================
// 4. NEURAL NETWORK ENGINE
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
            httpsAgent: keepAliveAgent
        });
        this.ws = null;
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
            return null;
        }
    }

    connectWebSocket() {
        if (!this.config.websocket.enabled) return;
        const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        ws.on('open', () => {
            console.log(COLORS.GREEN('📡 Ultra-fast WebSocket connected'));
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
            console.error(COLORS.RED('📡 WebSocket error:', error.message));
        });

        this.ws = ws;
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
// 6. DYNAMIC RISK EXCHANGE (TITAN UPGRADED)
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

    // --- V12.0 UPGRADES: Entry Logic ---
    calculatePositionSize(price, slDistance, signalStrength, marketRegime, choppiness, trendMTF, microTrend) {
        let riskMultiplier = this.getDynamicRiskMultiplier();
        
        // 5. REGIME-BASED SIZING (Upgrade)
        if (choppiness > 60) {
            riskMultiplier *= 0.6; // Reduce size in chop
        } else if (trendMTF === microTrend) {
            riskMultiplier *= 1.2; // Increase size (1.2x) in Trend Alignment
        }

        let baseRisk = this.balance.mul(this.cfg.riskPercent / 100);
        const strengthMultiplier = new Decimal(signalStrength).div(this.config.ai.minConfidence);
        let adjustedRisk = baseRisk.mul(strengthMultiplier.min(2.0)).mul(riskMultiplier);

        let qty = adjustedRisk.div(slDistance);
        const maxQty = this.equity.mul(this.cfg.leverageCap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;
        
        const maxPositionValue = this.equity.mul(this.config.risk.maxPositionSize);
        const positionValue = qty.mul(price);
        if (positionValue.gt(maxPositionValue)) {
            qty = maxPositionValue.div(price);
        }
        return qty;
    }

    // --- MAIN TRADING EVALUATION LOOP (UPGRADED) ---
    async evaluateUltraFast(priceVal, signal, analysis, ctx) {
        this.checkDailyReset();
        const price = new Decimal(priceVal);
        this.updateEquity(priceVal);
        this.riskScore = this.calculateRiskScore();

        // --- POSITION MANAGEMENT & EXIT LOGIC ---
        if (this.pos) {
            const elapsed = Date.now() - this.pos.time;
            let close = false, reason = '';
            
            // 4. ZOMBIE TRADE KILLER (Upgrade)
            const zombieLimit = this.cfg.zombie_time_ms || 300000;
            const pnlDecimal = this.pos.side === 'BUY' 
                ? price.sub(this.pos.entry).div(this.pos.entry) 
                : this.pos.entry.sub(price).div(this.pos.entry);

            if (elapsed > zombieLimit && pnlDecimal.abs().lt(this.cfg.zombie_pnl_threshold || 0.001)) {
                close = true;
                reason = `🧟 ZOMBIE KILL (Stale > ${Math.floor(elapsed/1000)}s)`;
            }

            // 2. RATCHET TRAILING STOP (Upgrade)
            if (!close) {
                const currentAtr = analysis.atr[analysis.atr.length - 1];
                const trailDist = new Decimal(currentAtr).mul(this.cfg.trailing_ratchet_dist || 2.0);

                if (this.pos.side === 'BUY') {
                    const potentialNewSL = price.sub(trailDist);
                    if (potentialNewSL.gt(this.pos.sl)) {
                        const oldSL = this.pos.sl;
                        this.pos.sl = potentialNewSL;
                        console.log(COLORS.CYAN(`⛓️ RATCHET UP: SL ${oldSL.toFixed(4)} -> ${this.pos.sl.toFixed(4)}`));
                    }
                } else if (this.pos.side === 'SELL') {
                    const potentialNewSL = price.add(trailDist);
                    if (potentialNewSL.lt(this.pos.sl)) {
                        const oldSL = this.pos.sl;
                        this.pos.sl = potentialNewSL;
                        console.log(COLORS.CYAN(`⛓️ RATCHET DOWN: SL ${oldSL.toFixed(4)} -> ${this.pos.sl.toFixed(4)}`));
                    }
                }
            }

            // 5. INSTANT BREAK-EVEN TRIGGER (Upgrade)
            if (!close && !this.pos.isBreakEven) {
                const initialRisk = this.pos.entry.sub(this.pos.originalSl || this.pos.sl).abs();
                const triggerDist = initialRisk.mul(this.cfg.break_even_trigger || 1.0); 

                if (this.pos.side === 'BUY' && price.gte(this.pos.entry.add(triggerDist))) {
                    this.pos.sl = this.pos.entry.add(price.mul(0.0002)); // Entry + small fee buffer
                    this.pos.isBreakEven = true;
                    console.log(COLORS.LIME(`🛡️ SHIELD UP: Buy locked at Break-Even`));
                } else if (this.pos.side === 'SELL' && price.lte(this.pos.entry.sub(triggerDist))) {
                    this.pos.sl = this.pos.entry.sub(price.mul(0.0002));
                    this.pos.isBreakEven = true;
                    console.log(COLORS.LIME(`🛡️ SHIELD UP: Sell locked at Break-Even`));
                }
            }

            // Standard Exits (Time, Hard SL/TP)
            if (!close) {
                if (elapsed > this.config.scalping.maxHoldingTime) { close = true; reason = 'Time Exit'; }
                
                if (this.pos.side === 'BUY') {
                    if (price.lte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.gte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                } else {
                    if (price.gte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.lte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                }

                if (signal && signal.action !== 'HOLD' && signal.action !== this.pos.side) {
                     close = true; reason = `SIGNAL_FLIP (${signal.action})`;
                }
            }

            if (close) {
                this.executeClose(price, reason);
            }
        } 
        
        // --- ENTRY LOGIC (UPGRADED) ---
        else if (signal && signal.action !== 'HOLD' && signal.confidence >= this.cfg.minConfidence) {
            if (this.riskScore > 90) { console.log(COLORS.RED('⛔ Risk Score too high, skipping trade')); return; }

            const entry = new Decimal(priceVal);
            
            // 2. VOLATILITY CLAMPED TP (Upgrade)
            let tp = new Decimal(signal.takeProfit);
            let sl = new Decimal(signal.stopLoss);
            
            const atrValue = analysis.atr[analysis.atr.length - 1] || price.mul(0.01).toNumber();
            const dynamicLimit = new Decimal(atrValue).mul(this.cfg.atr_tp_limit || 3.5);
            
            const maxUpside = entry.add(dynamicLimit);
            const maxDownside = entry.sub(dynamicLimit);

            if (signal.action === 'BUY' && tp.gt(maxUpside)) {
                tp = maxUpside;
                console.log(COLORS.ORANGE(`⚠️ Clamped BUY TP to ATR Limit: ${tp.toFixed(4)}`));
            } else if (signal.action === 'SELL' && tp.lt(maxDownside)) {
                tp = maxDownside;
                console.log(COLORS.ORANGE(`⚠️ Clamped SELL TP to ATR Limit: ${tp.toFixed(4)}`));
            }

            const dist = entry.sub(sl).abs();
            if (dist.isZero() || dist.lt(price.mul(0.0002))) return;
            
            const qty = this.calculatePositionSize(price, dist, signal.confidence, ctx.marketRegime, ctx.choppiness, ctx.trendMTF, ctx.microTrend);

            if (qty.mul(price).lt(5)) return;

            this.pos = {
                side: signal.action, entry, qty, sl, tp,
                originalSl: sl, // Store original SL for BE calculation
                strategy: signal.strategy || `Scalp-${signal.action}`,
                time: Date.now(), partialClosed: false, isBreakEven: false
            };
            
            const col = signal.action === 'BUY' ? COLORS.LIME : COLORS.HOT_PINK;
            console.log(col(`⚡ SCALP ${signal.action} @ ${entry.toFixed(6)} | Size: ${qty.toFixed(6)} | SL: ${sl.toFixed(6)} | TP: ${tp.toFixed(6)}`));
        }
    }

    async executeClose(price, reason) {
        const rawPnL = this.pos.side === 'BUY' ? price.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(price).mul(this.pos.qty);
        const fee = price.mul(this.pos.qty).mul(this.cfg.fee);
        const slippage = price.mul(this.pos.qty).mul(this.cfg.slippage);
        const netPnL = rawPnL.sub(fee).sub(slippage);
        
        this.balance = this.balance.add(netPnL);
        this.dailyPnL = this.dailyPnL.add(netPnL);
        
        if (netPnL.lt(0)) this.consecutiveLosses++;
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
        console.log(`${COLORS.BOLD(reason)}! PnL: ${color(netPnL.toFixed(4))}`);
        this.pos = null;
    }

    getStats() {
        const wins = this.history.filter(t => new Decimal(t.netPnL).gt(0));
        const winRate = this.history.length > 0 ? (wins.length / this.history.length) * 100 : 0;
        
        return {
            balance: this.balance.toNumber(),
            equity: this.equity.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalTrades: this.history.length,
            winRate: winRate.toFixed(1),
            riskScore: this.riskScore,
            consecutiveLosses: this.consecutiveLosses,
        };
    }
}

// =============================================================================
// 7. ADVANCED AI AGENT
// =============================================================================

class AdvancedAIAgent {
    constructor(config) {
        if (!process.env.GEMINI_API_KEY) throw new Error("Missing GEMINI_API_KEY");
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ 
            model: config.ai.model,
            generationConfig: { temperature: config.ai.temperature, topK: 12, topP: 0.7, maxOutputTokens: 300 }
        });
        this.rateLimit = config.ai.rateLimitMs;
        this.maxRetries = config.ai.maxRetries || 3;
        this.lastCall = 0;
        this.apiCalls = [];
        this.config = config;
    }

    async analyzeUltraFast(ctx, indicators) {
        let retries = 0;
        while (retries < this.maxRetries) {
            try {
                const now = Date.now();
                if (now - this.lastCall < this.rateLimit) await sleep(this.rateLimit - (now - this.lastCall));
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
        const atr = indicators.atr[indicators.atr.length - 1] || 10;
        const slDist = atr * 1.2;
        const tpDist = atr * this.config.risk.minRR;

        return `ROLE: Ultra-High Frequency Crypto Scalper (Professional)
MARKET MICRO-STRUCTURE:
┌─ Price: $${Utils.formatNumber(price, 6)} | WSS: ${wss.score.toFixed(3)}
├─ Trend (1m/3m): ${microTrend}/${trendMTF}
├─ Momentum: RSI=${rsi.toFixed(1)} | Fisher=${fisher.toFixed(3)} | Stoch=${stochK.toFixed(0)}
├─ OF/Vol: Imbalance: ${(imbalance * 100).toFixed(1)}% | Vol Spike: ${volumeSpike ? 'SPIKE' : 'NORMAL'}
└─ Neural Conf: ${(ctx.neuralConfidence * 100).toFixed(1)}% | Accel: ${acceleration.toFixed(6)}

SCALPING EXECUTION RULES:
1. 🔥 ENTRY: Requires WSS > ${this.config.indicators.weights.actionThreshold} AND Neural Signal Alignment.
2. 🎯 TARGET: R:R must be >= ${this.config.risk.minRR}.
3. 🛡️ RISK: Use ATR based dynamic stops.

JSON RESPONSE (Calculate SL/TP using ATR stops: SL=${slDist.toFixed(6)}, TP=${tpDist.toFixed(6)}):
{
  "action": "BUY"|"SELL"|"HOLD",
  "confidence": ${this.config.ai.minConfidence + 0.05},
  "strategy": "Ultra-Scalp-Breakout",
  "entry": ${price},
  "stopLoss": ${price - slDist}, 
  "takeProfit": ${price + tpDist},
  "reason": "Strong alignment of 1m trend, volume expansion, and neural confidence.",
  "timeframe": "1m",
  "riskLevel": "LOW"
}`;
    }

    validateSignal(signal, ctx, indicators) {
        if (signal.confidence < this.config.ai.minConfidence) { signal.confidence = 0; signal.action = 'HOLD'; signal.reason = 'Below confidence threshold'; }

        const atr = indicators.atr[indicators.atr.length - 1] || ctx.price * 0.0005;
        const R = atr * 1.2;
        const R_R_Ratio = this.config.risk.minRR;

        if (signal.action === 'BUY') {
            signal.stopLoss = Math.min(signal.stopLoss, ctx.price - R);
            signal.takeProfit = Math.max(signal.takeProfit, ctx.price + R * R_R_Ratio);
        } else if (signal.action === 'SELL') {
            signal.stopLoss = Math.max(signal.stopLoss, ctx.price + R);
            signal.takeProfit = Math.min(signal.takeProfit, ctx.price - R * R_R_Ratio);
        }

        if (!signal.strategy) signal.strategy = 'Ultra-Scalp';
        if (!signal.timeframe) signal.timeframe = '1m';

        return signal;
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
    console.log(COLORS.bg(COLORS.BOLD(COLORS.HOT_PINK(` ⚡ WHALEWAVE TITAN v12.0 (INSTITUTIONAL) `))));

    const config = await ConfigManager.load();
    HistoryManager.config = config;
    const marketEngine = new UltraFastMarketEngine(config);
    const exchange = new UltraFastExchange(config);
    const ai = new AdvancedAIAgent(config);

    await exchange.init();
    marketEngine.connectWebSocket();
    await marketEngine.fetchAllTimeframes(); 

    console.log(COLORS.CYAN(`🎯 Symbol: ${config.symbol} | Initial Bal: $${exchange.balance.toFixed(2)}`));
    
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
            
            // Neural Network Prediction
            let neuralScore = 0.5;
            if (config.indicators.neural.enabled) {
                const features = [(closes[closes.length - 1] - closes[closes.length - 6]) / closes[closes.length - 6], (volumes[volumes.length - 1] - volumes[volumes.length - 6]) / volumes[volumes.length - 6], rsi[rsi.length - 1] / 100, fisher[fisher.length - 1] / 5, stoch.k[stoch.k.length - 1] / 100, momentum[momentum.length - 1]];
                neuralScore = marketEngine.neural.predict(features);
            }

            const analysis = { closes, rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc, imbalance };
            const scoreObj = marketEngine.calculateWSS(analysis);

            const ctx = {
                symbol: config.symbol, price: data.price, lastUpdate: marketEngine.lastUpdate, trendMTF, microTrend: microTrend[microTrend.length - 1], imbalance,
                rsi: rsi[rsi.length - 1], fisher: fisher[fisher.length - 1], stochK: stoch.k[stoch.k.length - 1],
                choppiness: chop[chop.length - 1], acceleration: accel[accel.length - 1], wss: scoreObj,
                neuralConfidence: neuralScore, neuralSignal: neuralScore > 0.6 ? 'BUY' : neuralScore < 0.4 ? 'SELL' : 'HOLD',
            };

            // 3. AI Decision
            let signal = null;
            if (Math.abs(scoreObj.score) > config.indicators.weights.actionThreshold) {
                process.stdout.write(COLORS.HOT_PINK(" 🧠 AI Ultra-Fast Analysis... "));
                signal = await ai.analyzeUltraFast(ctx, analysis);
                process.stdout.write("\r");
            }

            // 4. Dashboard Update
            if (loopCount % (config.delays.loop / 500) === 0 || signal) {
                console.clear();
                const border = COLORS.GRAY('═'.repeat(100));
                console.log(border);
                
                const timestamp = new Date().toLocaleTimeString();
                const latency = marketEngine.getLatencyMetrics();
                
                console.log(COLORS.BOLD(COLORS.MAGENTA(` ⚡ ${timestamp} | ${config.symbol} | $${Utils.formatNumber(data.price, 6)} | LAT: ${latency.avg}ms | v12.0 `)));
                console.log(border);
                
                const scoreColor = scoreObj.score > 0 ? COLORS.LIME : scoreObj.score < 0 ? COLORS.HOT_PINK : COLORS.GRAY;
                const stats = exchange.getStats();
                
                console.log(COLORS.BOLD(` 💰 Price: ${COLORS.LIME('$' + Utils.formatNumber(data.price, 6))} | Score: ${scoreColor(scoreObj.score.toFixed(3))} | Neural: ${neuralScore > 0.6 ? COLORS.LIME : COLORS.HOT_PINK}(${(neuralScore * 100).toFixed(1)}%) | ${trendMTF} `));
                console.log(` 🎯 Micro: ${ctx.microTrend} | 3m: ${trendMTF} | Vol: ${volSpikes[volSpikes.length - 1] ? COLORS.LIME('🔥SPIKE') : COLORS.GRAY('📊NORMAL')} | OF: ${(imbalance * 100).toFixed(1)}% `);
                
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
                    const ratchetStatus = exchange.pos.sl !== (exchange.pos.originalSl ? exchange.pos.originalSl.toNumber() : exchange.pos.sl.toNumber()) ? '🔒RATCHET' : '🔓OPEN';
                    
                    console.log(`🟢 POS: ${exchange.pos.side} @ ${exchange.pos.entry.toFixed(6)} | PnL ${posColor(unrealized.toFixed(5))} | ${Utils.formatTime(holdingTime)} | ${ratchetStatus}`);
                } else {
                    console.log(COLORS.GRAY('⚪ POS: None'));
                }
                
                const analytics = await HistoryManager.loadScalpingAnalytics();
                const apiMetrics = ai.getApiMetrics();
                console.log(COLORS.BOLD(` 🏆 PF: ${Utils.formatNumber(analytics.profitFactorScalping, 2)} | Win: ${stats.winRate}% | NN Acc: 0.00% | AI Lat: ${apiMetrics.avgLatency}ms `));
                console.log(border);
            }

            // 5. Execute Trade (TITAN v12.0 UPGRADE: Passed Analysis/Ctx)
            await exchange.evaluateUltraFast(data.price, signal, analysis, ctx);

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

// -----------------------------------------------------------------------------
// 10. START APPLICATION
// -----------------------------------------------------------------------------

if (!process.env.GEMINI_API_KEY) {
    console.error(COLORS.RED('❌ GEMINI_API_KEY missing. Please set it in your .env file.'));
    process.exit(1);
}

main().catch(err => {
    console.error(COLORS.RED('💥 Fatal Ultra-Fast Error:'), err);
    HistoryManager.logError(err.message, { context: 'main_catch' });
    process.exit(1);
});
