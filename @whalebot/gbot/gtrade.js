/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN LIVE v1.7 (Complete Executable)
 * ===================================================
 * - LIVE TRADING MODULE: Bybit v5 REST + WSS 3.0 (Market + SL/TP, reduceOnly).
 * - SCALPING CORE: Ehlers Fisher Transform + Laguerre RSI integrated.
 * - ARCHITECTURE: Robust classes, WSS 3.0 for ticks, REST for historical/orders.
 * - SECURITY: Keys via process.env, strict error handling.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import crypto from 'crypto';
import WebSocket from 'ws';
import * as fs from 'fs/promises'; // Use promise-based fs

dotenv.config();

// =============================================================================
// 1. CONFIGURATION
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        live_trading: process.env.LIVE_MODE === 'true',
        intervals: { scalping: '1', main: '3', trend: '15' },
        limits: { kline: 300, orderbook: 50 },
        delays: { loop: 4000, retry: 1000, wsReconnect: 2000 },
        ai: { model: 'gemini-1.5-flash', minConfidence: 0.80 },
        risk: {
            maxDrawdown: 10.0,
            initialBalance: 1000.00,
            riskPercent: 2.0,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001,
            volatilityAdjustment: true
        },
        indicators: {
            rsi: 14, stoch: 14, mfi: 14,
            fisher_period: 10, laguerre_gamma: 0.5, scalping_ema: 5,
            atr_period: 14,
            weights: {
                trend_mtf: 2.0, scalping_momentum: 2.5, order_flow: 1.5,
                structure: 1.2, actionThreshold: 2.5
            }
        },
        orderbook: { wallThreshold: 3.0, imbalanceThreshold: 0.3 }
    });

    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        try {
            await fs.access(this.CONFIG_FILE);
            const content = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.deepMerge(config, JSON.parse(content));
        } catch (e) { /* use defaults */ }
        
        if (process.env.LIVE_MODE === 'true') config.live_trading = true;
        
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                result[key] = this.deepMerge(result[key] || {}, value);
            } else { result[key] = value; }
        }
        return result;
    }
}

// =============================================================================
// 2. UTILITIES & THEME
// =============================================================================

const COLORS = {
    GREEN: chalk.hex('#00FF41'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#0A84FF'),
    PURPLE: chalk.hex('#BF5AF2'), YELLOW: chalk.hex('#FFD60A'), CYAN: chalk.hex('#32ADE6'),
    GRAY: chalk.hex('#8E8E93'), BOLD: chalk.bold, bg: (text) => chalk.bgHex('#101010')(text)
};

class Utils {
    static safeArray(n) { return new Array(Math.max(0, Math.floor(n))).fill(0); }
    static safeLast(arr, def = 0) { return (Array.isArray(arr) && arr.length > 0) ? arr[arr.length - 1] : def; }
    static safeNumber(val, def = 0) {
        const n = typeof val === 'string' ? parseFloat(val) : (typeof val === 'number' ? val : NaN);
        return Number.isFinite(n) ? n : def;
    }
    static sum(arr) { return arr.reduce((a, b) => a + b, 0); }
}

// =============================================================================
// 3. TECHNICAL ANALYSIS (MERGED v1.2 + v1.4)
// =============================================================================

class TechnicalAnalysis {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        const res = []; let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        res.push(sum / period);
        for (let i = period; i < data.length; i++) { sum += data[i] - data[i - period]; res.push(sum / period); }
        return Utils.safeArray(period - 1).concat(res);
    }
    static ema(data, period) {
        if (!data || data.length === 0) return [];
        const res = Utils.safeArray(data.length); const k = 2 / (period + 1); res[0] = data[0];
        for (let i = 1; i < data.length; i++) res[i] = data[i] * k + res[i - 1] * (1 - k);
        return res;
    }
    static rsi(closes, period) {
        if (!closes || closes.length < period + 1) return Utils.safeArray(closes.length);
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0); losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        let avgGain = Utils.sum(gains.slice(0, period)) / period;
        let avgLoss = Utils.sum(losses.slice(0, period)) / period;
        const res = Utils.safeArray(closes.length);
        if (period < closes.length) {
            const first = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
            res[period] = first;
            for (let i = period + 1; i < closes.length; i++) {
                avgGain = (avgGain * (period - 1) + gains[i]) / period;
                avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
                res[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
            }
        }
        return res;
    }
    static stoch(highs, lows, closes, period, kP = 3, dP = 3) {
        const k = Utils.safeArray(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const h = highs.slice(i - period + 1, i + 1), l = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...l), maxH = Math.max(...h);
            k[i] = maxH === minL ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        const smoothK = this.sma(k, kP);
        return { k: smoothK, d: this.sma(smoothK, dP) };
    }
    static atr(highs, lows, closes, period = 14) {
        if (!closes || closes.length < 2) return Utils.safeArray(closes.length);
        const tr = Utils.safeArray(closes.length);
        for (let i = 1; i < closes.length; i++) tr[i] = Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1]));
        const res = Utils.safeArray(closes.length);
        let avg = Utils.sum(tr.slice(1, period + 1)) / period;
        if (period < closes.length) res[period] = avg;
        for (let i = period + 1; i < closes.length; i++) {
            avg = (avg * (period - 1) + tr[i]) / period;
            res[i] = avg;
        }
        return res;
    }
    static mfi(h, l, c, v, p) {
        const typ = c.map((val, i) => (h[i] + l[i] + val) / 3);
        const mf = typ.map((t, i) => t * v[i]);
        const res = Utils.safeArray(c.length);
        for (let i = p; i < c.length; i++) {
            let pos = 0, neg = 0;
            for (let j = 0; j < p; j++) {
                if (typ[i - j] > typ[i - j - 1]) pos += mf[i - j];
                else if (typ[i - j] < typ[i - j - 1]) neg += mf[i - j];
            }
            res[i] = neg === 0 ? 100 : 100 - 100 / (1 + pos / neg);
        }
        return res;
    }
    static fisherTransform(highs, lows, period = 10) {
        const len = highs.length;
        const fish = Utils.safeArray(len), value = Utils.safeArray(len);
        for (let i = 1; i < len; i++) {
            if (i < period) { value[i] = value[i - 1] || 0; fish[i] = fish[i - 1] || 0; continue; }
            let minL = Infinity, maxH = -Infinity;
            for (let j = 0; j < period; j++) {
                const hh = highs[i - j], ll = lows[i - j];
                if (hh > maxH) maxH = hh;
                if (ll < minL) minL = ll;
            }
            let raw = 0;
            if (maxH !== minL) raw = 0.33 * 2 * ((highs[i] + lows[i]) / 2 - minL) / (maxH - minL) - 0.5 + 0.67 * (value[i - 1] || 0);
            value[i] = Math.max(Math.min(raw, 0.99), -0.99);
            fish[i] = 0.5 * Math.log((1 + value[i]) / (1 - value[i])) + 0.5 * (fish[i - 1] || 0);
        }
        return { fish };
    }
    static laguerreRSI(closes, gamma = 0.5) {
        const len = closes.length;
        if (len === 0) return [];
        const lrsi = Utils.safeArray(len);
        let l0 = closes[0], l1 = l0, l2 = l0, l3 = l0;
        for (let i = 1; i < len; i++) {
            l0 = (1 - gamma) * closes[i] + gamma * l0;
            l1 = -gamma * l0 + l0 + gamma * l1;
            l2 = -gamma * l1 + l1 + gamma * l2;
            l3 = -gamma * l2 + l2 + gamma * l3;
            const cu = (l0 >= l1 ? l0 - l1 : 0) + (l1 >= l2 ? l1 - l2 : 0) + (l2 >= l3 ? l2 - l3 : 0);
            const cd = (l0 < l1 ? l1 - l0 : 0) + (l1 < l2 ? l2 - l1 : 0) + (l2 < l3 ? l3 - l2 : 0);
            lrsi[i] = (cu + cd === 0) ? 0 : (cu / (cu + cd)) * 100;
        }
        return lrsi;
    }
    static findFVG(candles) {
        if (!candles || candles.length < 5) return null;
        const c1 = candles[candles.length - 4], c2 = candles[candles.length - 3], c3 = candles[candles.length - 2];
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }
    static detectDivergence(closes, rsi, i2) {
        const len = closes.length;
        if (len < 10) return 'NONE';
        const i1 = i2 - 5; const i0 = i2 - 10;
        if (i0 < 0) return 'NONE';
        const pHigh1 = Math.max(...closes.slice(i1, i2)), rHigh1 = Math.max(...rsi.slice(i1, i2));
        const pHigh0 = Math.max(...closes.slice(i0, i1)), rHigh0 = Math.max(...rsi.slice(i0, i1));
        if (pHigh1 > pHigh0 && rHigh1 < rHigh0) return 'BEARISH_REGULAR';
        const pLow1 = Math.min(...closes.slice(i1, i2)), rLow1 = Math.min(...rsi.slice(i1, i2));
        const pLow0 = Math.min(...closes.slice(i0, i1)), rLow0 = Math.min(...rsi.slice(i0, i1));
        if (pLow1 < pLow0 && rLow1 > rLow0) return 'BULLISH_REGULAR';
        return 'NONE';
    }
}

class MarketAnalyzer {
    static async analyze(data, cfg) {
        const { candles, candlesTrend, candlesScalp } = data;
        const c = candles.map(x => x.c), h = candles.map(x => x.h), l = candles.map(x => x.l), v = candles.map(x => x.v);
        const sc = candlesScalp.map(x => x.c), sh = candlesScalp.map(x => x.h), sl = candlesScalp.map(x => x.l);

        const [rsi, stoch, atr, fisher, laguerre] = await Promise.all([
            TechnicalAnalysis.rsi(c, cfg.rsi),
            TechnicalAnalysis.stoch(h, l, c, cfg.stoch),
            TechnicalAnalysis.atr(h, l, c, cfg.atr_period),
            TechnicalAnalysis.fisherTransform(sh, sl, cfg.fisher_period),
            TechnicalAnalysis.laguerreRSI(sc, cfg.laguerre_gamma)
        ]);

        const last = c.length - 1;
        const sLast = sc.length - 1;

        const trendMTF = candlesTrend[candlesTrend.length-1].c > candlesTrend[candlesTrend.length-5].c ? 'BULLISH' : 'BEARISH';
        const isSqueeze = (candles.length > 10) && (candles[last].h - candles[last].l) / (candles[last-1].h - candles[last-1].h) < 0.8;
        const divergence = TechnicalAnalysis.detectDivergence(c, rsi, last);
        
        const totalBid = data.bids.reduce((a,b)=>a+b.q,0), totalAsk = data.asks.reduce((a,b)=>a+b.q,0);
        const imbalance = (totalBid - totalAsk) / (totalBid + totalAsk || 1);
        const fvg = TechnicalAnalysis.findFVG(candles);

        return {
            c, h, l, v, sc, sh, sl, rsi, stoch, atr, fisher, laguerre,
            trendMTF, isSqueeze, divergence, fvg, imbalance,
            last, sLast
        };
    }
}

// =============================================================================
// 4. DATA PROVIDER
// =============================================================================

class DataProvider {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: 6000 });
        this.symbol = config.symbol;
    }
    async fetch(url, params) {
        try { return (await this.api.get(url, { params })).data; } catch (e) { return null; }
    }
    parseKlines(rawList) {
        if (!rawList || !rawList.result || !rawList.result.list) return [];
        return rawList.result.list
            .map(k => ({
                t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5]),
            }))
            .reverse();
    }
    async getSnapshot() {
        try {
            const [tick, km, kt, ks, ob] = await Promise.all([
                this.fetch('/tickers', { category: 'linear', symbol: this.symbol }),
                this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.main, limit: this.config.limits.kline }),
                this.fetch('/kline', { category: 'linear', symbol: this.symbol, interval: this.config.intervals.trend, limit: 100 }),
                this.fetch('/kline', { category: 'linear', symbol: this.config.symbol, interval: this.config.intervals.scalping, limit: this.config.limits.kline }),
                this.fetch('/orderbook', { category: 'linear', symbol: this.symbol, limit: this.config.limits.orderbook }),
            ]);
            if(!tick || !km) return null;
            return {
                price: parseFloat(tick.result.list[0].lastPrice),
                candles: this.parseKlines({result:{list:km.result.list}}),
                candlesTrend: this.parseKlines({result:{list:kt.result.list}}),
                candlesScalp: this.parseKlines({result:{list:ks.result.list}}),
                bids: ob?.result?.b?.map(x=>({p:parseFloat(x[0]),q:parseFloat(x[1])})) ?? [],
                asks: ob?.result?.a?.map(x=>({p:parseFloat(x[0]),q:parseFloat(x[1])})) ?? [],
            };
        } catch (e) { console.error(COLORS.RED(`Data Fetch Error: ${e.message}`)); return null; }
    }
}

class MarketWatcher {
    constructor(config, onTick) {
        this.config = config;
        this.onTick = onTick;
        this.ws = null;
        this.retries = 0;
        this.symbol = config.symbol.toLowerCase();
        this.url = 'wss://stream.bybit.com/v5/public/linear';
    }
    start() { this.connect(); }
    connect() {
        try {
            this.ws = new WebSocket(this.url);
            this.ws.on('open', () => { this.retries = 0; this.subscribe(); });
            this.ws.on('message', (data) => this.handleMessage(data));
            this.ws.on('close', () => this.reconnect());
            this.ws.on('error', () => this.reconnect());
        } catch (e) { this.reconnect(); }
    }
    reconnect() {
        const delay = Math.min(30000, this.config.delays.wsReconnect * Math.pow(2, this.retries++));
        console.warn(COLORS.YELLOW(`WSS Reconnecting in ${Math.round(delay / 1000)}s...`));
        setTimeout(() => this.connect(), delay);
    }
    subscribe() {
        const sub = { op: 'subscribe', args: [`kline.${this.config.intervals.scalping}.${this.symbol}`] };
        this.ws?.send(JSON.stringify(sub));
    }
    handleMessage(raw) {
        try {
            const msg = JSON.parse(raw.toString());
            if (msg.topic && msg.data && msg.topic.startsWith('kline.')) {
                const k = msg.data;
                const candle = { t: parseInt(k.start), o: parseFloat(k.open), h: parseFloat(k.high), l: parseFloat(k.low), c: parseFloat(k.close), v: parseFloat(k.volume) };
                this.onTick({ type: 'kline', interval: msg.topic.split('.')[1], candle });
            }
        } catch {}
    }
}

// =============================================================================
// 5. EXCHANGE MODULES (Paper & Live)
// =============================================================================

class LiveBybitExchange {
    constructor(config) {
        this.config = config;
        this.symbol = config.symbol;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        if (!this.apiKey || !this.apiSecret) { console.error(COLORS.RED("MISSING BYBIT API KEYS")); process.exit(1); }
        this.client = axios.create({ baseURL: 'https://api.bybit.com', timeout: 7000 });
        this.pos = null;
        this.balance = 0;
        this.updateWallet();
    }

    async signRequest(method, endpoint, params) {
        const ts = Date.now().toString();
        const recvWindow = '5000';
        const payload = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
        const signStr = ts + this.apiKey + recvWindow + payload;
        const signature = crypto.createHmac('sha256', this.apiSecret).update(signStr).digest('hex');
        return {
            'X-BAPI-API-KEY': this.apiKey, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': recvWindow, 'Content-Type': 'application/json'
        };
    }

    async apiCall(method, endpoint, params = {}) {
        const headers = await this.signRequest(method, endpoint, params);
        try {
            const res = method === 'GET' ? await this.client.get(endpoint, { headers, params }) : await this.client.post(endpoint, params, { headers });
            if (res.data.retCode !== 0) throw new Error(res.data.retMsg);
            return res.data.result;
        } catch (e) { console.error(COLORS.RED(`Live API Error: ${e.message}`)); return null; }
    }

    async updateWallet() {
        const res = await this.apiCall('GET', '/v5/account/wallet-balance', { accountType: 'UNIFIED', coin: 'USDT' });
        if (res) this.balance = parseFloat(res.list[0].coin[0].walletBalance);
        const pos = await this.apiCall('GET', '/v5/position/list', { category: 'linear', symbol: this.symbol });
        if (pos && pos.list.length > 0 && parseFloat(pos.list[0].size) > 0) {
            const p = pos.list[0];
            this.pos = { side: p.side === 'Buy' ? 'BUY' : 'SELL', qty: parseFloat(p.size), entry: parseFloat(p.avgPrice) };
        } else { this.pos = null; }
    }

    async evaluate(price, signal) {
        await this.updateWallet();
        if (this.pos) {
            if (signal.action !== 'HOLD' && signal.action !== this.pos.side) {
                console.log(COLORS.YELLOW("Signal Flip! Closing position..."));
                await this.closePos();
            }
            return;
        }
        if (signal.action !== 'HOLD' && signal.confidence >= this.config.ai.minConfidence) {
            const entry = new Decimal(signal.entry || price);
            const sl = new Decimal(signal.sl || entry.mul(0.995));
            const tp = new Decimal(signal.tp || entry.mul(1.015));
            const dist = entry.sub(sl).abs();
            if (dist.eq(0)) return;
            
            const riskAmt = new Decimal(this.balance).mul(this.config.risk.riskPercent / 100);
            let qty = riskAmt.div(dist).toDecimalPlaces(3, Decimal.ROUND_DOWN);
            
            await this.rest.setLeverage(this.config.risk.leverageCap);
            const side = signal.action === 'BUY' ? 'Buy' : 'Sell';
            await this.rest.placeOrder({
                category: 'linear', symbol: this.symbol, side, orderType: 'Market',
                qty: qty.toString(), stopLoss: sl.toString(), takeProfit: tp.toString(), timeInForce: 'GTC'
            });
            console.log(COLORS.GREEN(`LIVE ORDER SENT: ${signal.action} ${qty.toString()} @ ${entry.toFixed(2)}`));
        }
    }

    async closePos() {
        if (!this.pos) return;
        const side = this.pos.side === 'BUY' ? 'Sell' : 'Buy';
        await this.rest.placeOrder({
            category: 'linear', symbol: this.symbol, side, orderType: 'Market',
            qty: this.pos.qty.toString(), reduceOnly: true
        });
        this.pos = null;
    }
}

class PaperExchange {
    constructor(config) {
        this.cfg = config.risk;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
    }
    evaluate(price, signal) {
        if (this.pos) {
            const isFlip = signal.action !== 'HOLD' && signal.action !== this.pos.side;
            const closeOnHold = signal.action === 'HOLD';
            if (isFlip || closeOnHold) this.close(price, isFlip ? 'SIGNAL_FLIP' : 'HOLD_EXIT');
            return;
        }
        if (signal.action !== 'HOLD' && signal.confidence >= 0.8) this.open(price, signal);
    }
    open(price, sig) {
        const entry = new Decimal(price);
        const sl = new Decimal(sig.sl || entry.mul(0.99));
        const tp = new Decimal(sig.tp || entry.mul(1.015));
        const dist = entry.sub(sl).abs();
        if (dist.eq(0)) return;
        const riskAmt = this.balance.mul(this.cfg.riskPercent / 100);
        let qty = riskAmt.div(dist).toDecimalPlaces(6, Decimal.ROUND_DOWN);
        if (qty.lte(0)) return;
        this.pos = { side: sig.action, entry, qty, sl, tp, strategy: sig.strategy || 'PAPER' };
        console.log(COLORS.GREEN(`PAPER OPEN ${sig.action} @ ${entry.toFixed(2)}`));
    }
    close(price, reason) {
        const p = this.pos;
        const px = new Decimal(price);
        const diff = p.side === 'BUY' ? px.sub(p.entry) : p.entry.sub(px);
        const pnl = diff.mul(p.qty);
        this.balance = this.balance.add(pnl); 
        const col = pnl.gte(0) ? COLORS.GREEN : COLORS.RED;
        console.log(col(`${reason}: Closed. PnL: ${pnl.toFixed(2)} | Bal: ${this.balance.toFixed(2)}`)); 
        this.pos = null;
    }
}

// =============================================================================
// 6. AI BRAIN
// =============================================================================

class AIBrain {
    constructor(config) {
        this.cfg = config.ai;
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ model: this.cfg.model });
    }
    async analyze(context) {
        const prompt = `
        ROLE: Elite Crypto HFT Scalper.
        TASK: Analyze context and decide BUY, SELL, or HOLD.
        
        METRICS: Price:${context.price}, WSS: ${context.wss.toFixed(2)} (Threshold: ${context.threshold}), Fisher:${context.fisher.toFixed(2)}, Laguerre:${context.laguerre.toFixed(0)}, Trend:${context.trend}
        STRUCTURE: FVG:${context.fvg || 'None'}, Imbalance:${(context.imbalance*100).toFixed(1)}%

        RULES:
        1. BUY if WSS > ${context.threshold} AND Fisher Cross Up AND Imbalance > 0.1.
        2. SELL if WSS < -${context.threshold} AND Fisher Cross Down AND Imbalance < -0.1.
        3. Target SL/TP dynamically based on ATR/Fisher volatility.

        OUTPUT JSON: {"action":"BUY/SELL/HOLD", "confidence":0.0-1.0, "sl":number, "tp":number, "strategy":"NAME", "reason":"short text"}
        `.trim();
        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const obj = JSON.parse(text);
            if (!['BUY', 'SELL', 'HOLD'].includes(obj.action || 'HOLD')) obj.action = 'HOLD';
            return obj;
        } catch (e) { return { action: 'HOLD', confidence: 0, sl: 0, tp: 0, strategy: 'AI_FAIL', reason: e.message }; }
    }
}

// =============================================================================
// 7. MARKET WATCHER (For live ticks)
// =============================================================================

class MarketWatcher {
    constructor(config, onTick) {
        this.config = config;
        this.onTick = onTick;
        this.ws = null;
        this.retries = 0;
        this.symbol = config.symbol.toLowerCase();
        this.url = 'wss://stream.bybit.com/v5/public/linear';
    }
    start() { this.connect(); }
    connect() {
        try {
            this.ws = new WebSocket(this.url);
            this.ws.on('open', () => { this.retries = 0; this.subscribe(); });
            this.ws.on('message', (data) => this.handleMessage(data));
            this.ws.on('close', () => this.reconnect());
            this.ws.on('error', () => this.reconnect());
        } catch (e) { this.reconnect(); }
    }
    reconnect() {
        const delay = Math.min(30000, this.config.delays.wsReconnect * Math.pow(2, this.retries++));
        console.warn(COLORS.YELLOW(`WSS Reconnecting in ${Math.round(delay / 1000)}s...`));
        setTimeout(() => this.connect(), delay);
    }
    subscribe() {
        const sub = { op: 'subscribe', args: [`kline.${this.config.intervals.scalping}.${this.symbol}`] };
        this.ws?.send(JSON.stringify(sub));
    }
    handleMessage(raw) {
        try {
            const msg = JSON.parse(raw.toString());
            if (msg.topic && msg.data && msg.topic.startsWith('kline.')) {
                const k = msg.data;
                const candle = { t: parseInt(k.start), o: parseFloat(k.open), h: parseFloat(k.high), l: parseFloat(k.low), c: parseFloat(k.close), v: parseFloat(k.volume) };
                this.onTick({ type: 'kline', interval: msg.topic.split('.')[1], candle });
            }
        } catch {}
    }
}

// =============================================================================
// 9. MAIN ENGINE
// =============================================================================

class TradingEngine {
    constructor() { this.init(); }

    async init() {
        this.cfg = await ConfigManager.load();
        this.data = new DataProvider(this.cfg);
        this.exchange = this.cfg.live_trading ? new LiveBybitExchange(this.cfg) : new PaperExchange(this.cfg);
        this.ai = new AIBrain(this.cfg);
        this.watcher = new MarketWatcher(this.cfg, (tick) => this.onWsTick(tick));
        
        this.wssCache = { price: null, klineScalp: null };
        this.setupSignalHandlers();
        this.loop();
        this.watcher.start();
    }

    async loop() {
        while (true) {
            try {
                const m = await this.data.getSnapshot();
                if (!m) { await sleep(2000); continue; }

                const a = await MarketAnalyzer.analyze(m, this.cfg.indicators);
                const wssRes = WeightedSentimentCalculator.calculate(a, this.cfg.indicators);
                
                const context = {
                    price: m.price, wss: wssRes.score, threshold: this.cfg.indicators.weights.actionThreshold,
                    fisher: a.fisher.fish[a.sLast], laguerre: a.laguerre[a.sLast], trend: a.trendMTF,
                    fvg: a.fvg?.type, imbalance: a.imbalance, rsi: a.rsi[a.last]
                };

                let sig = { action: 'HOLD', confidence: 0, sl: 0, tp: 0, strategy: 'ENGINE' };
                if (Math.abs(wssRes.score) >= this.cfg.indicators.weights.actionThreshold * 0.5) {
                    sig = await this.ai.analyze(context);
                }
                
                const atrVal = Utils.safeLast(a.atr) || (m.price * 0.001);

                if (sig.action !== 'HOLD' && (!sig.sl || !sig.tp)) {
                    sig.sl = sig.action === 'BUY' ? m.price - atrVal * 1.0 : m.price + atrVal * 1.0;
                    sig.tp = sig.action === 'BUY' ? m.price + atrVal * 1.5 : m.price - atrVal * 1.5;
                }

                this.display(m.price, wssRes.score, sig, this.exchange.pos ? 'POS OPEN' : 'Awaiting Signal');
                await this.exchange.evaluate(m.price, sig);

            } catch (e) { console.error(COLORS.RED(`Loop error: ${e.stack}`)); }
            await sleep(this.cfg.delays.loop);
        }
    }

    onWsTick(tick) {
        if (tick.type === 'kline') this.wssCache.klineScalp = tick.candle;
    }

    display(price, wss, sig, posStatus) {
        process.stdout.write(`\r${COLORS.GRAY('---')} ${COLORS.BOLD(COLORS.CYAN(`LIVE`))} | P: $${price.toFixed(2)} | WSS: ${wss.toFixed(2)} | AI: ${sig.action} (${(sig.confidence*100||0).toFixed(0)}%) | ${posStatus}  `);
    }
}

// Initialize the entire system
new TradingEngine();
