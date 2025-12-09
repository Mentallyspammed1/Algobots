// File: src/whalewave-titan.js

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import Decimal from 'decimal.js';
import WebSocket from 'ws';
import https from 'https';
import * as tf from '@tensorflow/tfjs-node';
import { ConfigManager } from './config-manager.js';

dotenv.config();

const keepAliveAgent = new https.Agent({
    keepAlive: true,
    maxSockets: 256,
    scheduling: 'lifo',
    timeout: 3000
});

// =============================================================================
// 1. CONFIGURATION & STATE MANAGEMENT
// =============================================================================

class HistoryManager {
    static FILE = 'scalping_trades.json';
    static ANALYTICS_FILE = 'scalping_analytics.json';
    static ERROR_FILE = 'errors.log';
    static NEURAL_TRAINING = 'neural_training.json';
    static config = null;

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
        try { return JSON.parse(await fs.readFile(this.ANALYTICS_FILE, 'utf-8')); } catch {
            return { scalpingTrades: 0, avgHoldingTime: 0, winRateScalping: 0, profitFactorScalping: 0, bestScalp: 0, worstScalp: 0, consecutiveLosses: 0, avgWin: 0, avgLoss: 0, expectancy: 0 };
        }
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
        const avgWin = wins.length > 0 ? wins.reduce((a, b) => a + b.netPnL, 0) / wins.length : 0;
        const avgLoss = losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b.netPnL, 0)) / losses.length : 0;
        const winRate = wins.length / scalps.length;
        const expectancy = (winRate * avgWin) - ((1 - winRate) * avgLoss);

        const analytics = {
            scalpingTrades: scalps.length, avgHoldingTime: avgHold / 1000, winRateScalping: (winRate) * 100,
            profitFactorScalping: totalLoss > 0 ? totalWin / totalLoss : totalWin, bestScalp: Math.max(...scalps.map(t => t.netPnL)),
            worstScalp: Math.min(...scalps.map(t => t.netPnL)), avgWin: avgWin, avgLoss: avgLoss, totalReturn: totalWin - totalLoss,
            consecutiveLosses: HistoryManager.calculateConsecutiveLosses(scalps), expectancy: expectancy
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

class Logger {
    static log(level, message, context = {}) {
        const timestamp = new Date().toISOString();
        const logEntry = { timestamp, level, message, ...context };
        console.log(JSON.stringify(logEntry));
    }
    static info(message, context) { this.log('INFO', message, context); }
    static warn(message, context) { this.log('WARN', message, context); }
    static error(message, context) { this.log('ERROR', message, context); }
}

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static safeLast(arr, def = 0) { return (Array.isArray(arr) && arr.length > 0 && !isNaN(arr[arr.length - 1])) ? arr[arr.length - 1] : def; }
    static formatNumber(num, decimals = 4) { return (isNaN(num) || !isFinite(num)) ? '0.0000' : Number(num).toFixed(decimals); }
    static formatTime(ms) { return ms < 1000 ? `${Math.floor(ms)}ms` : ms < 60000 ? `${Math.floor(ms / 1000)}s` : `${Math.floor(ms / 60000)}m`; }
    static clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }
    static logistic(x) { return 1 / (1 + Math.exp(-x)); }
    static sigmoid(x) { return this.logistic(x); }
    static tanh(x) { return Math.tanh(x); }

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

        if (v[last] > v[last - 1] * 2.5 && Math.abs(p[last] - p[last - 3]) > p[last - 1] * 0.005) patterns.push({ type: 'VOL_CLIMAX_REVERSAL' });
        const mom1 = p[last] - p[last - 3];
        const mom2 = p[last - 3] - p[last - 6];
        if (mom1 > 0 && mom2 > mom1 * 1.5) patterns.push({ type: 'MOMENTUM_EXHAUSTION', direction: 'BEARISH' });
        if (highs[last] - lows[last] > (highs[last - 1] - lows[last - 1]) * 1.3) patterns.push({ type: 'EXPANSION' });
        if (Math.abs(v[last] - v[last - 1]) > v[last - 1] * 0.8 && Math.abs(p[last] - p[last - 1]) > p[last - 1] * 0.002) patterns.push({ type: 'ORDER_BLOCK' });
        return patterns;
    }
}

// =============================================================================
// 3. TECHNICAL ANALYSIS ENGINE (TA)
// =============================================================================

class TA {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data?.length ?? 0);
        let sum = 0, res = [];
        for (let i = 0; i < period; i++) sum += (isNaN(data[i]) ? 0 : data[i]);
        res.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += (isNaN(data[i]) ? 0 : data[i]) - (isNaN(data[i - period]) ? 0 : data[i - period]);
            res.push(sum / period);
        }
        return Utils.safeArray(period - 1).concat(res);
    }

    static rsi(prices, period = 5) {
        const gains = [];
        const losses = [];
        for (let i = 1; i < prices.length; i++) {
            const diff = prices[i] - prices[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? -diff : 0);
        }
        const avgGains = this.sma(gains, period);
        const avgLosses = this.sma(losses, period);
        const rsi = [];
        for (let i = 0; i < avgGains.length; i++) {
            const avgG = avgGains[i] || 0.0000001;
            const avgL = avgLosses[i] || 0.0000001;
            const rs = avgG / avgL;
            rsi.push(100 - (100 / (1 + rs)));
        }
        return rsi;
    }

    static fisher(h, l, len = 7) {
        const res = new Array(h.length).fill(0), val = new Array(h.length).fill(0);
        for (let i = len; i < h.length; i++) {
            let maxH = -Infinity, minL = Infinity;
            for (let j = 0; j < len; j++) {
                if (h[i - j] > maxH) maxH = h[i - j];
                if (l[i - j] < minL) minL = l[i - j];
            }
            let range = maxH - minL;
            let raw = 0;
            if (range > 0) {
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
        let tr = [Math.max(h[0] - l[0], Math.abs(h[0] - (c[0] || h[0])), Math.abs(l[0] - (c[0] || h[0])))];
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
        const dPadded = new Array(close.length).fill(50);
        const dStartIdx = (period - 1) + (2 - 1);
        for (let i = 0; i < d.length; i++) {
            if (dStartIdx + i < close.length) dPadded[dStartIdx + i] = d[i];
        }
        return { k, d: dPadded };
    }
}

class IncrementalTA {
    constructor(period) {
        this.period = period;
        this.data = [];
        this.sum = 0;
    }
    updateSMA(newClose) {
        this.data.push(newClose);
        this.sum += newClose;
        if (this.data.length > this.period) {
            this.sum -= this.data.shift();
        }
        return this.sum / this.period;
    }
}

// =============================================================================
// 4. NEURAL NETWORK ENGINE
// =============================================================================

class NeuralNetwork {
    constructor(config) {
        this.config = config;
        this.model = this.createModel();
    }

    createModel() {
        const features = this.config.indicators.neural.features.length;
        const model = tf.sequential();
        model.add(tf.layers.dense({ units: 10, inputShape: [features], activation: 'relu' }));
        model.add(tf.layers.dense({ units: 1, activation: 'sigmoid' }));
        model.compile({ optimizer: 'adam', loss: 'binaryCrossentropy', metrics: ['accuracy'] });
        return model;
    }

    async predict(features) {
        if (!this.config.indicators.neural.enabled) return 0.5;
        try {
            const normalizedFeatures = features.map((feature, index) => {
                if (index === 0 || index === 1) return Utils.clamp(feature, -1, 1);
                return feature;
            });
            const inputTensor = tf.tensor2d([normalizedFeatures]);
            const predictionTensor = this.model.predict(inputTensor);
            const prediction = (await predictionTensor.data())[0];
            inputTensor.dispose();
            predictionTensor.dispose();
            return Utils.clamp(prediction, 0, 1);
        } catch (error) {
            Logger.error('Neural network prediction failed', { error: error.message });
            return 0.5;
        }
    }

    async train(trainingData) {
        if (trainingData.length < 50) return;
        try {
            const features = trainingData.map(d => d.features);
            const labels = trainingData.map(d => d.result);
            const xs = tf.tensor2d(features);
            const ys = tf.tensor2d(labels, [labels.length, 1]);

            await this.model.fit(xs, ys, {
                epochs: 50,
                batchSize: 32,
                callbacks: {
                    onEpochEnd: (epoch, logs) => {
                        if (epoch % 10 === 0) Logger.info(`Epoch ${epoch}: Loss = ${logs.loss.toFixed(4)}`);
                    }
                }
            });
            xs.dispose();
            ys.dispose();
            Logger.info('Neural network trained successfully');
        } catch (error) {
            Logger.warn(`Neural training failed: ${error.message}`);
        }
    }
}

// =============================================================================
// 5. ULTRA-FAST MARKET ENGINE
// =============================================================================

class RingBuffer {
    constructor(capacity) {
        this.capacity = capacity;
        this.buffer = new Array(capacity);
        this.size = 0;
        this.head = 0;
    }
    push(item) {
        this.buffer[this.head] = item;
        this.head = (this.head + 1) % this.capacity;
        if (this.size < this.capacity) this.size++;
    }
    get(index) {
        if (index >= this.size) return undefined;
        return this.buffer[(this.head - this.size + index + this.capacity) % this.capacity];
    }
    toArray() {
        const result = [];
        for (let i = 0; i < this.size; i++) result.push(this.get(i));
        return result;
    }
    get length() { return this.size; }
}

class UltraFastMarketEngine {
    constructor(config) {
        this.config = config;
        this.api = axios.create({
            baseURL: 'https://api.bybit.com/v5/market',
            timeout: 3000,
            httpsAgent: keepAliveAgent
        });
        this.ws = null;
        this.cache = { price: 0, bids: [], asks: [], kline: {}, ticks: new RingBuffer(config.limits.ticks), volume24h: 0, cumulativeDelta: 0 };
        this.lastUpdate = Date.now();
        this.neural = new NeuralNetwork(config);
        this.latencyHistory = [];
        this.reconnectAttempts = 0;
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
            Logger.error('Failed to fetch market data', { error: e.message });
            return null;
        }
    }

    connectWebSocket() {
        if (!this.config.websocket.enabled) return;
        const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');

        ws.on('open', () => {
            Logger.info('Ultra-fast WebSocket connected');
            ws.send(JSON.stringify({ op: "subscribe", args: [`kline.${this.config.intervals.scalp}.${this.config.symbol}`, `orderbook.50.${this.config.symbol}`, `publicTrade.${this.config.symbol}`] }));
            this.reconnectAttempts = 0;
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
                    const d = msg.data;
                    const trades = Array.isArray(d) ? d : [d];
                    trades.forEach(t => {
                        this.cache.ticks.push({ price: parseFloat(t.p), size: parseFloat(t.s), side: t.S, time: parseInt(t.T) });
                        const delta = t.S === 'Buy' ? parseFloat(t.s) : -parseFloat(t.s);
                        this.cache.cumulativeDelta += delta;
                    });
                }
            } catch (e) {}
        });

        ws.on('close', () => {
            this.reconnectAttempts++;
            const delay = Math.min(this.config.websocket.reconnectInterval * Math.pow(2, this.reconnectAttempts), 60000);
            Logger.warn(`WebSocket disconnected. Retrying in ${delay / 1000}s...`);
            setTimeout(() => this.connectWebSocket(), delay);
        });

        ws.on('error', (error) => {
            Logger.error('WebSocket error', { error: error.message });
        });

        this.ws = ws;
    }

    calculateWSS(analysis) {
        const { closes, rsi, fisher, stoch, microTrend, accel, volSpikes, imbalance } = analysis;
        const weights = this.config.indicators.weights;
        const trend = microTrend[microTrend.length - 1];
        const rsiV = Utils.safeLast(rsi, 50);
        const fisherV = Utils.safeLast(fisher, 0);
        const stochK = Utils.safeLast(stoch.k, 50);
        const accelV = Utils.safeLast(accel, 0);
        const volSpk = volSpikes[volSpikes.length - 1] ? 1 : 0;

        let score = 0;
        if (trend === 'BULLISH') score += weights.microTrend;
        if (trend === 'BEARISH') score -= weights.microTrend;

        if (rsiV > 60) score += weights.momentum;
        if (rsiV < 40) score -= weights.momentum;

        if (fisherV > 0.2) score += weights.momentum * 0.5;
        if (fisherV < -0.2) score -= weights.momentum * 0.5;

        if (stochK > 80) score -= weights.momentum * 0.3;
        if (stochK < 20) score += weights.momentum * 0.3;

        score += (accelV > 0 ? weights.acceleration : -weights.acceleration) * 0.5;

        if (volSpk) score += weights.volume;

        if (imbalance > this.config.indicators.scalping.orderFlowImbalance) score += weights.orderFlow;
        if (imbalance < -this.config.indicators.scalping.orderFlowImbalance) score -= weights.orderFlow;

        return { score, trend, rsi: rsiV, fisher: fisherV, stochK, volSpk, imbalance };
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

    calculatePositionSize(price, slDistance, signalStrength, marketRegime, choppiness, trendMTF, microTrend, analytics) {
        let riskMultiplier = this.getDynamicRiskMultiplier();

        if (choppiness > 60) {
            riskMultiplier *= 0.6;
        } else if (trendMTF === microTrend) {
            riskMultiplier *= 1.2;
        }

        let baseRisk = this.balance.mul(this.cfg.riskPercent / 100);
        if (analytics.winRateScalping > 0 && analytics.avgLoss > 0) {
            const winRate = analytics.winRateScalping / 100;
            const avgWin = analytics.avgWin;
            const avgLoss = analytics.avgLoss;
            const kellyFraction = (winRate) - ((1 - winRate) / (avgWin / avgLoss));
            if (kellyFraction > 0) {
                baseRisk = this.balance.mul(kellyFraction);
            }
        }

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

    async evaluateUltraFast(priceVal, signal, analysis, ctx, analytics) {
        this.checkDailyReset();
        const price = new Decimal(priceVal);
        this.updateEquity(priceVal);
        this.riskScore = this.calculateRiskScore();

        if (this.pos) {
            const elapsed = Date.now() - this.pos.time;
            let close = false, reason = '';

            const zombieLimit = this.cfg.zombie_time_ms || 300000;
            const pnlDecimal = this.pos.side === 'BUY'
                ? price.sub(this.pos.entry).mul(this.pos.qty)
                : this.pos.entry.sub(price).mul(this.pos.qty);

            if (elapsed > zombieLimit && pnlDecimal.abs().lt(this.cfg.zombie_pnl_threshold || 0.001)) {
                close = true;
                reason = `🧟 ZOMBIE KILL (Stale > ${Math.floor(elapsed / 1000)}s)`;
            }

            if (!close) {
                const currentAtr = (analysis.atr && analysis.atr.length > 0) ? analysis.atr[analysis.atr.length - 1] : price.mul(0.01).toNumber();
                const trailDist = new Decimal(currentAtr).mul(this.cfg.trailing_ratchet_dist || 2.0);

                if (this.pos.side === 'BUY') {
                    const potentialNewSL = price.sub(trailDist);
                    if (potentialNewSL.gt(this.pos.sl)) {
                        const oldSL = this.pos.sl;
                        this.pos.sl = potentialNewSL;
                        Logger.info(`RATCHET UP: SL ${oldSL.toFixed(6)} -> ${this.pos.sl.toFixed(6)}`);
                    }
                } else if (this.pos.side === 'SELL') {
                    const potentialNewSL = price.add(trailDist);
                    if (potentialNewSL.lt(this.pos.sl)) {
                        const oldSL = this.pos.sl;
                        this.pos.sl = potentialNewSL;
                        Logger.info(`RATCHET DOWN: SL ${oldSL.toFixed(6)} -> ${this.pos.sl.toFixed(6)}`);
                    }
                }
            }

            if (!close && !this.pos.isBreakEven) {
                const initialRisk = this.pos.entry.sub(this.pos.originalSl || this.pos.sl).abs();
                const triggerDist = initialRisk.mul(this.cfg.break_even_trigger || 1.0);

                if (this.pos.side === 'BUY' && price.gte(this.pos.entry.add(triggerDist))) {
                    this.pos.sl = this.pos.entry.add(price.mul(0.0002));
                    this.pos.isBreakEven = true;
                    Logger.info(`SHIELD UP: Buy locked at Break-Even`);
                } else if (this.pos.side === 'SELL' && price.lte(this.pos.entry.sub(triggerDist))) {
                    this.pos.sl = this.pos.entry.sub(price.mul(0.0002));
                    this.pos.isBreakEven = true;
                    Logger.info(`SHIELD UP: Sell locked at Break-Even`);
                }
            }

            if (!close && !this.pos.partialClosed) {
                const pnlDecimal = this.pos.side === 'BUY'
                    ? price.sub(this.pos.entry).div(this.pos.entry)
                    : this.pos.entry.sub(price).div(this.pos.entry);
                if (pnlDecimal.gt(this.config.scalping.partialClose)) {
                    const partialQty = this.pos.qty.mul(0.5);
                    this.executePartialClose(price, partialQty, 'Partial Take Profit');
                    this.pos.partialClosed = true;
                }
            }

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
                    close = true;
                    reason = `SIGNAL_FLIP (${signal.action})`;
                }
            }

            if (close) {
                this.executeClose(price, reason);
            }
        } else if (signal && signal.action !== 'HOLD' && signal.confidence >= this.config.ai.minConfidence) {
            if (this.riskScore > 90) { Logger.warn('Risk Score too high, skipping trade'); return; }

            const entry = new Decimal(priceVal);

            let tp = new Decimal(signal.takeProfit);
            let sl = new Decimal(signal.stopLoss);

            const atrValue = (analysis.atr && analysis.atr.length > 0) ? analysis.atr[analysis.atr.length - 1] : price.mul(0.01).toNumber();
            const dynamicLimit = new Decimal(atrValue).mul(this.cfg.atr_tp_limit || 3.5);

            const maxUpside = entry.add(dynamicLimit);
            const maxDownside = entry.sub(dynamicLimit);

            if (signal.action === 'BUY' && tp.gt(maxUpside)) {
                tp = maxUpside;
                Logger.warn(`Clamped BUY TP to ATR Limit: ${tp.toFixed(6)}`);
            } else if (signal.action === 'SELL' && tp.lt(maxDownside)) {
                tp = maxDownside;
                Logger.warn(`Clamped SELL TP to ATR Limit: ${tp.toFixed(6)}`);
            }

            const dist = entry.sub(sl).abs();
            if (dist.isZero() || dist.lt(price.mul(0.0002))) return;

            const qty = this.calculatePositionSize(price, dist, signal.confidence, ctx.marketRegime, ctx.choppiness, ctx.trendMTF, ctx.microTrend, analytics);

            if (qty.mul(price).lt(5)) return;

            const trendMTF = ctx.trendMTF;
            const microTrend = ctx.microTrend;
            if ((signal.action === 'BUY' && trendMTF !== 'BULLISH') || (signal.action === 'SELL' && trendMTF !== 'BEARISH')) {
                Logger.warn(`MTF mismatch: ${signal.action} signal rejected due to ${trendMTF} trend.`);
                return;
            }

            this.pos = {
                side: signal.action, entry, qty, sl, tp,
                originalSl: sl,
                strategy: signal.strategy || `Scalp-${signal.action}`,
                time: Date.now(), partialClosed: false, isBreakEven: false
            };

            const col = signal.action === 'BUY' ? COLORS.LIME : COLORS.HOT_PINK;
            Logger.info(`SCALP ${signal.action} @ ${entry.toFixed(6)} | Size: ${qty.toFixed(6)} | SL: ${sl.toFixed(6)} | TP: ${tp.toFixed(6)}`);
        }
    }

    async executeClose(price, reason) {
        const rawPnL = this.pos.side === 'BUY' ? price.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(price).mul(this.pos.qty);
        const fee = price.mul(this.pos.qty).mul(this.cfg.fee);

        let slippageCost = 0;
        const orderBook = this.pos.side === 'BUY' ? marketEngine.cache.asks : marketEngine.cache.bids;
        const orderSize = this.pos.qty;
        let cumulativeSize = 0;
        for (const level of orderBook) {
            cumulativeSize += level.q;
            if (cumulativeSize >= orderSize) {
                const slippagePriceImpact = Math.abs(level.p - price.toNumber());
                slippageCost = slippagePriceImpact * this.pos.qty;
                break;
            }
        }

        const netPnL = rawPnL.sub(fee).sub(slippageCost);

        this.balance = this.balance.add(netPnL);
        this.dailyPnL = this.dailyPnL.add(netPnL);

        if (netPnL.lt(0)) this.consecutiveLosses++;
        else this.consecutiveLosses = 0;

        const tradeRecord = {
            date: new Date().toISOString(), symbol: this.config.symbol, side: this.pos.side,
            entry: this.pos.entry.toNumber(), exit: price.toNumber(), qty: this.pos.qty.toNumber(),
            netPnL: netPnL.toNumber(), reason, strategy: this.pos.strategy, holdingTime: Date.now() - this.pos.time,
            riskScore: this.riskScore, slippageCost: slippageCost.toNumber()
        };

        await HistoryManager.save(tradeRecord);
        this.history.push(tradeRecord);

        const color = netPnL.gte(0) ? COLORS.LIME : COLORS.HOT_PINK;
        Logger.info(`${reason}! PnL: ${netPnL.toFixed(4)}`, { trade: tradeRecord });
        this.pos = null;
    }

    async executePartialClose(price, partialQty, reason) {
        const rawPnL = this.pos.side === 'BUY' ? price.sub(this.pos.entry).mul(partialQty) : this.pos.entry.sub(price).mul(partialQty);
        const fee = price.mul(partialQty).mul(this.cfg.fee);
        const netPnL = rawPnL.sub(fee);

        this.balance = this.balance.add(netPnL);
        this.dailyPnL = this.dailyPnL.add(netPnL);
        this.pos.qty = this.pos.qty.sub(partialQty);

        Logger.info(`PARTIAL CLOSE: ${reason} | PnL: ${netPnL.toFixed(4)}`);
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
// 7. ADVANCED AI AGENT (with local heuristic fallback)
// =============================================================================

class AdvancedAIAgent {
    constructor(config) {
        this.config = config;
        this.model = null;
        this.rateLimit = config.ai.rateLimitMs;
        this.maxRetries = config.ai.maxRetries || 3;
        this.lastCall = 0;
        this.apiCalls = [];
        this.localHeuristicCooldown = 0;
        if (process.env.GEMINI_API_KEY) {
            this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
                model: config.ai.model,
                generationConfig: { temperature: config.ai.temperature, topK: 12, topP: 0.7, maxOutputTokens: 300 }
            });
        } else {
            Logger.warn('GEMINI_API_KEY missing. Using local heuristic fallback.');
        }
    }

    async analyzeUltraFast(ctx, indicators) {
        if (!this.model) {
            return this.localHeuristic(ctx, indicators);
        }

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
                    return this.localHeuristic(ctx, indicators);
                }
                await sleep(2 ** retries * 100);
            }
        }
    }

    buildAdvancedPrompt(ctx, indicators) {
        const { price, microTrend, trendMTF, rsi, fisher, stochK, imbalance, volumeSpike, choppiness, acceleration, wss } = ctx;
        const atr = (indicators.atr && indicators.atr.length > 0) ? indicators.atr[indicators.atr.length - 1] : price * 0.0005; // Fallback ATR
        const slDist = atr * 1.2;
        const tpDist = atr * this.config.risk.minRR;

        return `ROLE: Ultra-High Frequency Crypto Scalper (Professional)
MARKET MICRO-STRUCTURE:
┌─ Price: $${Utils.formatNumber(price, 6)} | WSS: ${wss.score.toFixed(3)}
├─ Trend (1m/3m): ${microTrend}/${trendMTF} | Choppiness: ${choppiness.toFixed(2)}
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
        if (!signal || typeof signal !== 'object') signal = { action: 'HOLD', confidence: 0 };
        if (signal.confidence < this.config.ai.minConfidence) { signal.confidence = 0; signal.action = 'HOLD'; signal.reason = 'Below confidence threshold'; }

        const atr = (indicators.atr && indicators.atr.length > 0) ? indicators.atr[indicators.atr.length - 1] : ctx.price * 0.0005; // Fallback ATR
        const R = atr * 1.2;
        const R_R_Ratio = this.config.risk.minRR;

        if (signal.action === 'BUY') {
            signal.stopLoss = Math.min(signal.stopLoss ?? (ctx.price - R), ctx.price - R);
            signal.takeProfit = Math.max(signal.takeProfit ?? (ctx.price + R * R_R_Ratio), ctx.price + R * R_R_Ratio);
        } else if (signal.action === 'SELL') {
            signal.stopLoss = Math.max(signal.stopLoss ?? (ctx.price + R), ctx.price + R);
            signal.takeProfit = Math.min(signal.takeProfit ?? (ctx.price - R * R_R_Ratio), ctx.price - R * R_R_Ratio);
        } else {
            signal.stopLoss = ctx.price;
            signal.takeProfit = ctx.price;
        }

        if (!signal.strategy) signal.strategy = 'Ultra-Scalp';
        if (!signal.timeframe) signal.timeframe = '1m';

        return signal;
    }

    localHeuristic(ctx, indicators) {
        const now = Date.now();
        if (now < this.localHeuristicCooldown) {
            return { action: 'HOLD', confidence: 0, strategy: 'Heuristic-Cooldown', entry: ctx.price, stopLoss: ctx.price, takeProfit: ctx.price, reason: 'Local heuristic cooldown' };
        }

        const atr = (indicators.atr && indicators.atr.length > 0) ? indicators.atr[indicators.atr.length - 1] : ctx.price * 0.0005; // Fallback ATR
        const R = atr * 1.2;
        const R_R_Ratio = this.config.risk.minRR;

        const rsiFuzzy = Utils.sigmoid((ctx.rsi - 50) / 10);
        const fisherFuzzy = Utils.sigmoid(ctx.fisher);
        const trendFuzzy = ctx.microTrend === 'BULLISH' ? 1 : ctx.microTrend === 'BEARISH' ? 0 : 0.5;

        const buyScore = (rsiFuzzy * 0.4) + (fisherFuzzy * 0.3) + (trendFuzzy * 0.3);
        const sellScore = 1 - buyScore;

        let action = 'HOLD';
        if (buyScore > 0.7) action = 'BUY';
        else if (sellScore > 0.7) action = 'SELL';

        const signal = {
            action,
            confidence: action === 'HOLD' ? 0 : this.config.ai.minConfidence + 0.03,
            strategy: 'Local-Heuristic',
            entry: ctx.price,
            stopLoss: action === 'BUY' ? ctx.price - R : ctx.price + R,
            takeProfit: action === 'BUY' ? ctx.price + R * R_R_Ratio : ctx.price - R * R_R_Ratio,
            reason: 'Heuristic fallback (fuzzy logic)',
            timeframe: '1m',
            riskLevel: 'LOW'
        };

        this.localHeuristicCooldown = now + this.config.ai.rateLimitMs;
        return this.validateSignal(signal, ctx, indicators);
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
    console.log(COLORS.bg(COLORS.BOLD(COLORS.HOT_PINK(` ⚡ WHALEWAVE TITAN v12.1 (INSTITUTIONAL) `))));

    const config = await ConfigManager.load();
    HistoryManager.config = config;
    const marketEngine = new UltraFastMarketEngine(config);
    const exchange = new UltraFastExchange(config);
    const ai = new AdvancedAIAgent(config);

    await exchange.init();
    marketEngine.connectWebSocket();
    await marketEngine.fetchAllTimeframes();

    Logger.info(`Symbol: ${config.symbol} | Initial Bal: $${exchange.balance.toFixed(2)}`);

    let loopCount = 0;
    const incrementalSma = new IncrementalTA(10);

    while (true) {
        const loopStart = Date.now();

        try {
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

            const [rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc] = await Promise.all([
                TA.rsi(closes, config.indicators.periods.rsi),
                TA.fisher(highs, lows, config.indicators.periods.fisher),
                TA.stoch(highs, lows, closes, config.indicators.periods.stoch),
                TA.atr(highs, lows, closes, config.indicators.periods.atr),
                TA.choppiness(highs, lows, closes, config.indicators.periods.chop),
                TA.priceAcceleration(closes, 5),
                TA.volumeSpike(volumes, config.indicators.scalping.volumeSpikeThreshold),
                TA.microTrend(closes, config.indicators.periods.microTrendLength),
                TA.findFVG(scalpData),
                Utils.williamsR(highs, lows, closes, config.indicators.periods.williams),
                Utils.calculateMomentum(closes, config.indicators.periods.momentum),
                Utils.calculateROC(closes, config.indicators.periods.roc)
            ]);

            const imbalance = TA.orderFlowImbalance(marketEngine.cache.bids, marketEngine.cache.asks);
            const qCloses = data.kline[config.intervals.quick].map(x => x.c);
            const qSMA = TA.sma(qCloses, 15);
            const trendMTF = qCloses[qCloses.length - 1] > qSMA[qSMA.length - 1] ? 'BULLISH' : 'BEARISH';
            const divergences = TA.detectAdvancedDivergence(closes, { rsi, fisher }, 5);
            const patterns = Utils.detectAdvancedPatterns(closes, volumes, highs, lows, closes);

            let neuralScore = 0.5;
            let features = [];
            if (config.indicators.neural.enabled) {
                features = [
                    (closes[closes.length - 1] - closes[closes.length - 6]) / closes[closes.length - 6],
                    (volumes[volumes.length - 1] - volumes[volumes.length - 6]) / volumes[volumes.length - 6],
                    (rsi[rsi.length - 1] || 50) / 100,
                    (fisher[fisher.length - 1] || 0) / 5,
                    (stoch.k[stoch.k.length - 1] || 50) / 100,
                    (momentum[momentum.length - 1] || 0)
                ];
                neuralScore = await marketEngine.neural.predict(features);
            }

            const analysis = { closes, rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc, imbalance };
            const scoreObj = marketEngine.calculateWSS(analysis);

            const ctx = {
                symbol: config.symbol, price: data.price, lastUpdate: marketEngine.lastUpdate, trendMTF, microTrend: microTrend[microTrend.length - 1], imbalance,
                rsi: rsi[rsi.length - 1] ?? 50, fisher: fisher[fisher.length - 1] ?? 0, stochK: stoch.k[stoch.k.length - 1] ?? 50,
                choppiness: chop[chop.length - 1] ?? 50, acceleration: accel[accel.length - 1] ?? 0, wss: scoreObj,
                neuralConfidence: neuralScore, neuralSignal: neuralScore > 0.6 ? 'BUY' : neuralScore < 0.4 ? 'SELL' : 'HOLD',
                cumulativeDelta: marketEngine.cache.cumulativeDelta
            };

            let signal = null;
            const choppinessValue = ctx.choppiness;
            if (choppinessValue > 65) {
                Logger.warn(`Market too choppy (${choppinessValue.toFixed(2)}), skipping trade evaluation.`);
                signal = { action: 'HOLD', confidence: 0 };
            } else if (Math.abs(scoreObj.score) > config.indicators.weights.actionThreshold) {
                process.stdout.write(COLORS.HOT_PINK(" 🧠 AI Ultra-Fast Analysis... "));
                signal = await ai.analyzeUltraFast(ctx, analysis);
                process.stdout.write("\r");
            }

            if (loopCount % (config.delays.loop / 500) === 0 || signal) {
                console.clear();
                const border = COLORS.GRAY('═'.repeat(100));
                console.log(border);

                const timestamp = new Date().toLocaleTimeString();
                const latency = marketEngine.getLatencyMetrics();

                console.log(COLORS.BOLD(COLORS.MAGENTA(` ⚡ ${timestamp} | ${config.symbol} | $${Utils.formatNumber(data.price, 6)} | LAT: ${latency.avg}ms | v12.1 `)));
                console.log(border);

                const scoreColor = scoreObj.score > 0 ? COLORS.LIME : scoreObj.score < 0 ? COLORS.HOT_PINK : COLORS.GRAY;
                const stats = exchange.getStats();

                console.log(COLORS.BOLD(` 💰 Price: ${COLORS.LIME('$' + Utils.formatNumber(data.price, 6))} | Score: ${scoreColor(scoreObj.score.toFixed(3))} | Neural: ${neuralScore > 0.6 ? COLORS.LIME : neuralScore < 0.4 ? COLORS.HOT_PINK : COLORS.GRAY}(${(neuralScore * 100).toFixed(1)}%) | ${trendMTF} `));
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
                    const ratchetStatus = (exchange.pos.sl.toNumber() !== (exchange.pos.originalSl ? exchange.pos.originalSl.toNumber() : exchange.pos.sl.toNumber())) ? '🔒RATCHET' : '🔓OPEN';

                    console.log(`🟢 POS: ${exchange.pos.side} @ ${exchange.pos.entry.toFixed(6)} | PnL ${posColor(unrealized.toFixed(5))} | ${Utils.formatTime(holdingTime)} | ${ratchetStatus}`);
                } else {
                    console.log(COLORS.GRAY('⚪ POS: None'));
                }

                const analytics = await HistoryManager.loadScalpingAnalytics();
                const apiMetrics = ai.getApiMetrics();
                console.log(COLORS.BOLD(` 🏆 PF: ${Utils.formatNumber(analytics.profitFactorScalping, 2)} | Win: ${stats.winRate}% | NN Acc: 0.00% | AI Lat: ${apiMetrics.avgLatency}ms | Expectancy: ${Utils.formatNumber(analytics.expectancy, 4)} `));
                console.log(border);
            }

            const analytics = await HistoryManager.loadScalpingAnalytics();
            await exchange.evaluateUltraFast(data.price, signal, analysis, ctx, analytics);

            if (config.indicators.neural.enabled && loopCount % 200 === 0) {
                const trainingData = await HistoryManager.loadNeuralTraining();
                if (trainingData.length > 100) {
                    marketEngine.neural.train(trainingData.slice(-1000));
                }
            }

            loopCount++;

        } catch (err) {
            Logger.error('Loop Error', { error: err.message, stack: err.stack });
        }

        const processingTime = Date.now() - loopStart;
        const waitTime = Math.max(0, config.delays.loop - processingTime);

        if (processingTime > config.delays.loop * 0.8) {
            Logger.warn(`Loop processing time exceeded threshold: ${processingTime}ms`);
        }

        await sleep(waitTime);
    }
}

process.on('SIGINT', async () => {
    Logger.info('Shutting down gracefully...');
    if (marketEngine.ws) marketEngine.ws.close();
    process.exit(0);
});

// -----------------------------------------------------------------------------
// 10. START APPLICATION
// -----------------------------------------------------------------------------

if (!process.env.GEMINI_API_KEY) {
    Logger.warn('GEMINI_API_KEY missing in .env. The bot will use a local heuristic fallback.');
}

main().catch(err => {
    Logger.error('Fatal Ultra-Fast Error', { error: err.message, stack: err.stack });
    process.exit(1);
});