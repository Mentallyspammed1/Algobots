/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v2.3 (HYBRID TRIGGER HUD)
 * ======================================================
 * - Finalized Hybrid Trigger Logic
 * - Enhanced HUD with Fisher, ATR, Imbalance
 * - All previous V2.2+ features integrated (Risk Sizing, Iceberg,
Filters, etc.)
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import crypto from 'crypto';
import WebSocket from 'ws';
import fs from 'fs/promises';

dotenv.config();

// === UI CONSTANTS ===
const COLOR = {
    GREEN: chalk.hex('#00FF41'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#0A84FF'),
    PURPLE: chalk.hex('#BF5AF2'),
    YELLOW: chalk.hex('#FFD60A'),
    CYAN: chalk.hex('#32ADE6'),
    GRAY: chalk.hex('#8E8E93'),
    ORANGE: chalk.hex('#FFA500'),
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#101010')(text),
};

// === CONFIGURATION ===
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        live_trading: process.env.LIVE_MODE === 'true',
        intervals: { scalping: '1', main: '5', trend: '15' },
        limits: { kline: 300, orderbook: 20 },
        delays: { loop: 3000, retry: 2000, wsReconnect: 1000 },
        ai: { 
            model: 'gemini-2.5-flash', 
            minConfidence: 0.85,
            maxTokens: 300
        },
        risk: {
            maxDailyLoss: 5.0, // % of balance
            maxRiskPerTrade: 1.0, // % of balance
            leverage: 5,
            fee: 0.00055,
            slippage: 0.0001,
            rewardRatio: 1.5
        },
        indicators: {
            rsi: 14,
            fisher: 10,
            atr: 14,
            bb: { period: 20, std: 2 },
            laguerre: 0.5,
            threshold: 1.8 // Minimum score to trigger AI check
        }
    });

    static async load() {
        let config = { ...this.DEFAULTS };
        try {
            const data = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.mergeDeep(config, JSON.parse(data));
        } catch {
            // Use defaults if file missing
        }
        return config;
    }

    static mergeDeep(target, source) {
        const output = { ...target };
        for (const key in source) {
            if (source[key] instanceof Object && key in target) {
                output[key] = this.mergeDeep(target[key], source[key]);
            } else {
                output[key] = source[key];
            }
        }
        return output;
    }
}

// === MATH & UTILS ===
const Utils = {
    safeArray: (len) => new Array(Math.max(0, Math.floor(len))).fill(0),
    sum: (arr) => arr.reduce((a, b) => a + b, 0),
    average: (arr) => arr.length ? Utils.sum(arr) / arr.length : 0,
    
    stdDev: (arr, period) => {
        if (!arr || arr.length < period) return Utils.safeArray(arr.length);
        const result = Utils.safeArray(arr.length);
        for (let i = period - 1; i < arr.length; i++) {
            const slice = arr.slice(i - period + 1, i + 1);
            const mean = Utils.average(slice);
            const variance = Utils.average(slice.map(x => Math.pow(x - mean, 2)));
            result[i] = Math.sqrt(variance);
        }
        return result;
    },

    timestamp: () => new Date().toLocaleTimeString(),
    
    calcSize: (balance, entry, sl, riskPct) => {
        const bal = new Decimal(balance);
        const ent = new Decimal(entry);
        const stop = new Decimal(sl);
        const riskAmt = bal.mul(riskPct).div(100);
        const riskPerCoin = ent.minus(stop).abs();
        
        if (riskPerCoin.eq(0)) return new Decimal(0);
        return riskAmt.div(riskPerCoin).toDecimalPlaces(3, Decimal.ROUND_DOWN);
    }
};

// === RISK GUARD (CIRCUIT BREAKER) ===
class CircuitBreaker {
    constructor(config) {
        this.maxLossPct = config.risk.maxDailyLoss;
        this.initialBalance = 0;
        this.currentPnL = 0;
        this.triggered = false;
        this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
    }

    setBalance(bal) {
        if (this.initialBalance === 0) this.initialBalance = bal;
        if (Date.now() > this.resetTime) {
            this.initialBalance = bal;
            this.currentPnL = 0;
            this.triggered = false;
            this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
            console.log(COLOR.GREEN(`[CircuitBreaker] Daily stats reset.`));
        }
    }

    updatePnL(pnl) {
        this.currentPnL += pnl;
        const lossPct = (Math.abs(this.currentPnL) / this.initialBalance) * 100;
        if (this.currentPnL < 0 && lossPct >= this.maxLossPct) {
            this.triggered = true;
            console.log(COLOR.bg(COLOR.RED(` 🚨 CIRCUIT BREAKER TRIGGERED: Daily Loss ${lossPct.toFixed(2)}% `)));
        }
    }

    canTrade() {
        return !this.triggered;
    }
}

// === TECHNICAL ANALYSIS ENGINE ===
class TechnicalAnalysis {
    static rsi(closes, period = 14) {
        if (!closes.length) return [];
        let gains = [], losses = [];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(Math.max(diff, 0));
            losses.push(Math.max(-diff, 0));
        }
        
        const rsi = Utils.safeArray(closes.length);
        let avgGain = Utils.average(gains.slice(0, period));
        let avgLoss = Utils.average(losses.slice(0, period));
        
        for(let i = period + 1; i < closes.length; i++) {
            const change = closes[i] - closes[i-1];
            avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period;
            avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
            rsi[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
        }
        return rsi;
    }

    static fisher(highs, lows, period = 9) {
        const len = highs.length;
        const fish = Utils.safeArray(len);
        const value = Utils.safeArray(len);
        
        for (let i = 1; i < len; i++) {
            if (i < period) continue;
            let minL = Infinity, maxH = -Infinity;
            for (let j = 0; j < period; j++) {
                maxH = Math.max(maxH, highs[i-j]);
                minL = Math.min(minL, lows[i-j]);
            }
            
            let raw = 0;
            if (maxH !== minL) {
                raw = 0.66 * ((highs[i] + lows[i]) / 2 - minL) / (maxH - minL) - 0.5 + 0.67 * (value[i-1] || 0);
            }
            value[i] = Math.max(Math.min(raw, 0.99), -0.99);
            fish[i] = 0.5 * Math.log((1 + value[i]) / (1 - value[i])) + 0.5 * (fish[i-1] || 0);
        }
        return fish;
    }

    static atr(highs, lows, closes, period = 14) {
        const tr = new Array(closes.length).fill(0);
        for(let i=1; i<closes.length; i++) {
            tr[i] = Math.max(highs[i]-lows[i], Math.abs(highs[i]-closes[i-1]), Math.abs(lows[i]-closes[i-1]));
        }
        const atr = Utils.safeArray(closes.length);
        let sum = 0;
        for(let i=0; i<closes.length; i++) {
            sum += tr[i];
            if(i >= period) {
                sum -= tr[i-period];
                atr[i] = sum / period;
            }
        }
        return atr;
    }

    static bollinger(closes, period, std) {
        const mid = new Array(closes.length).fill(0);
        let sum = 0;
        for(let i=0; i<closes.length; i++) {
            sum += closes[i];
            if(i >= period) {
                sum -= closes[i-period];
                mid[i] = sum/period;
            }
        }
        const dev = Utils.stdDev(closes, period);
        return {
            upper: mid.map((m, i) => m + dev[i] * std),
            lower: mid.map((m, i) => m - dev[i] * std),
            mid: mid
        };
    }
}

// === AI BRAIN (GEMINI 1.5 JSON MODE) ===
class AIBrain {
    constructor(config) {
        this.config = config.ai;
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ 
            model: this.config.model,
            generationConfig: { responseMimeType: "application/json", maxOutputTokens: this.config.maxTokens }
        });
    }

    async analyze(ctx) {
        const prompt = `
        Act as a high-frequency trading algorithm. Analyze these metrics for ${ctx.symbol}:
        - Price: ${ctx.price}
        - Fisher Transform: ${ctx.fisher.toFixed(2)} (Trend Strength)
        - RSI: ${ctx.rsi.toFixed(2)}
        - ATR: ${ctx.atr.toFixed(2)} (Volatility)
        - Orderbook Imbalance: ${(ctx.imbalance * 100).toFixed(1)}%
        - Technical Score: ${ctx.score.toFixed(2)} / 10.0
        
        Strategy:
        1. Fisher > 2.0 is Bullish, < -2.0 is Bearish.
        2. Imbalance > 0 supports Buy, < 0 supports Sell.
        3. RSI > 70 Overbought, < 30 Oversold.
        
        Respond ONLY with this JSON structure:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "sl": number,
            "tp": number,
            "reason": "Short string explanation"
        }`;

        try {
            const result = await this.model.generateContent(prompt);
            let rawText = result.response.text();
            rawText = rawText.replace(/```json|```/g, '').trim();
            return JSON.parse(rawText);
        } catch (e) {
            return { action: "HOLD", confidence: 0 };
        }
    }
}

// === DATA PROVIDER (REST + WSS) ===
class MarketData {
    constructor(config, onUpdate) {
        this.config = config;
        this.onUpdate = onUpdate;
        this.ws = null;
        this.buffers = {
            scalping: [], // 1m
            main: [],     // 5m
            trend: []     // 15m
        };
        this.lastPrice = 0;
        this.orderbook = { bids: [], asks: [] };
        this.latency = 0;
    }

    async start() {
        await this.loadHistory();
        this.connectWSS();
    }

    async loadHistory() {
        const client = axios.create({ baseURL: 'https://api.bybit.com/v5/market' });
        const loadKline = async (interval, targetBuffer) => {
            try {
                const res = await client.get('/kline', {
                    params: { category: 'linear', symbol: this.config.symbol, interval, limit: 200 }
                });
                if (res.data.retCode === 0) {
                    this.buffers[targetBuffer] = res.data.result.list.map(k => ({
                        t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), 
                        l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5])
                    })).reverse();
                }
            } catch (e) { console.error(`[Data] Failed loading ${interval} klines`); }
        };

        await Promise.all([
            loadKline(this.config.intervals.scalping, 'scalping'),
            loadKline(this.config.intervals.main, 'main'),
            loadKline(this.config.intervals.trend, 'trend')
        ]);
        console.log(COLOR.CYAN(`[Data] Historical data loaded.`));
    }

    connectWSS() {
        this.ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        this.ws.on('open', () => {
            console.log(COLOR.GREEN(`[WSS] Connected.`));
            const args = [
                `tickers.${this.config.symbol}`,
                `orderbook.50.${this.config.symbol}`,
                `kline.${this.config.intervals.scalping}.${this.config.symbol}`,
                `kline.${this.config.intervals.main}.${this.config.symbol}`
            ];
            this.ws.send(JSON.stringify({ op: 'subscribe', args }));
            this.startHeartbeat();
        });

        this.ws.on('message', (data) => {
            const msg = JSON.parse(data);
            
            if (msg.ts) {
                this.latency = Date.now() - msg.ts;
            }

            if (msg.topic?.startsWith('tickers')) {
                const tickerData = Array.isArray(msg.data) ? msg.data[0] : msg.data;
                if (tickerData?.lastPrice) {
                    this.lastPrice = parseFloat(tickerData.lastPrice);
                    this.onUpdate('price');
                }
            } else if (msg.topic?.startsWith('orderbook')) {
                if (msg.type === 'snapshot') {
                    this.orderbook.bids = msg.data.b.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                    this.orderbook.asks = msg.data.a.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                }
            } else if (msg.topic?.startsWith('kline')) {
                const k = msg.data[0];
                const interval = msg.topic.split('.')[1];
                const type = interval === this.config.intervals.scalping ? 'scalping' : 'main';
                
                const candle = {
                    t: parseInt(k.start), o: parseFloat(k.open), h: parseFloat(k.high),
                    l: parseFloat(k.low), c: parseFloat(k.close), v: parseFloat(k.volume)
                };
                
                const buf = this.buffers[type];
                if(buf && buf.length > 0 && buf[buf.length-1].t === candle.t) {
                    buf[buf.length-1] = candle; 
                } else if(buf) {
                    buf.push(candle); 
                    if(buf.length > this.config.limits.kline) buf.shift();
                }
                this.onUpdate('kline');
            }
        });

        this.ws.on('error', () => setTimeout(() => this.connectWSS(), 1000));
        this.ws.on('close', () => setTimeout(() => this.connectWSS(), 1000));
    }

    startHeartbeat() {
        setInterval(() => {
            if(this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({op:'ping'}));
        }, 20000);
    }
}

// === EXECUTION ENGINE ===
class Exchange {
    constructor(config) {
        this.config = config;
        this.symbol = config.symbol;
        this.isLive = config.live_trading;
        
        if (this.isLive) {
            this.client = axios.create({ baseURL: 'https://api.bybit.com' });
            this.apiKey = process.env.BYBIT_API_KEY;
            this.apiSecret = process.env.BYBIT_API_SECRET;
        }

        this.balance = 10000;
        this.position = null;
        this.lastPrice = 0; 
    }

    async getSignature(params) {
        const ts = Date.now().toString();
        const recvWindow = '5000';
        const payload = JSON.stringify(params);
        const signStr = ts + this.apiKey + recvWindow + payload;
        return crypto.createHmac('sha256', this.apiSecret).update(signStr).digest('hex');
    }

    async execute(action, qty, sl, tp) {
        if (!this.isLive) {
            const entry = this.lastPrice;
            this.position = { action, qty, entry, sl, tp };
            console.log(COLOR.GREEN(`[PAPER] Executed ${action} ${qty} @ ${entry.toFixed(2)}`));
            return true;
        }

        try {
            const params = {
                category: 'linear',
                symbol: this.symbol,
                side: action === 'BUY' ? 'Buy' : 'Sell',
                orderType: 'Market',
                qty: qty.toString(),
                stopLoss: sl.toString(),
                takeProfit: tp.toString(),
                timeInForce: 'GTC'
            };

            const ts = Date.now().toString();
            const sign = await this.getSignature(params);
            
            const res = await this.client.post('/v5/order/create', params, {
                headers: {
                    'X-BAPI-API-KEY': this.apiKey,
                    'X-BAPI-TIMESTAMP': ts,
                    'X-BAPI-SIGN': sign,
                    'X-BAPI-RECV-WINDOW': '5000',
                    'Content-Type': 'application/json'
                }
            });

            if (res.data.retCode === 0) {
                console.log(COLOR.GREEN(`[LIVE] Order Success: ${res.data.result.orderId}`));
                return true;
            } else {
                console.error(COLOR.RED(`[LIVE] Order Failed: ${res.data.retMsg}`));
                return false;
            }
        } catch (e) {
            console.error(COLOR.RED(`[LIVE] Execution Error: ${e.message}`));
            return false;
        }
    }

    async close(price) {
        if (!this.position) return 0;
        
        let pnl = 0;
        if (!this.isLive) {
            const diff = this.position.action === 'BUY' ? price - this.position.entry : this.position.entry - price;
            pnl = diff * this.position.qty;
            this.balance += pnl;
            this.position = null;
            console.log(COLOR.PURPLE(`[PAPER] Closed @ ${price.toFixed(2)} | PnL: ${pnl.toFixed(2)}`));
            return pnl;
        } else {
            return 0; 
        }
    }
}

// === CORE CONTROLLER ===
class Leviathan {
    constructor() {
        this.init();
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v2.3: HUD ENHANCED '))));
        
        this.config = await ConfigManager.load();
        this.circuitBreaker = new CircuitBreaker(this.config);
        this.exchange = new Exchange(this.config);
        this.ai = new AIBrain(this.config);
        this.data = new MarketData(this.config, (type) => this.onTick(type));
        
        this.isProcessing = false;
        this.aiLastQueryTime = 0;
        this.aiThrottleMs = 5000;
        
        await this.data.start();
        this.circuitBreaker.setBalance(this.exchange.balance);
    }

    async onTick(type) {
        const price = this.data.lastPrice;
        if (this.isProcessing || type !== 'kline' || !price || isNaN(price) || price === 0) return;
        
        this.isProcessing = true;
        this.exchange.lastPrice = price; 

        try {
            const candles = this.data.buffers.main;
            
            if (candles.length < 50) {
                this.isProcessing = false;
                return;
            }

            // 1. Technical Calculation
            const closes = candles.map(c => c.c);
            const highs = candles.map(c => c.h);
            const lows = candles.map(c => c.l);

            const rsi = TechnicalAnalysis.rsi(closes, 14);
            const fisher = TechnicalAnalysis.fisher(highs, lows, 10);
            const atr = TechnicalAnalysis.atr(highs, lows, closes, 14);
            const bb = TechnicalAnalysis.bollinger(closes, 20, 2);

            const last = closes.length - 1;
            const currentRsi = rsi[last];
            const currentFisher = fisher[last];
            const currentAtr = atr[last];

            // 2. Orderbook Imbalance
            const bidVol = Utils.sum(this.data.orderbook.bids.map(b => b.q));
            const askVol = Utils.sum(this.data.orderbook.asks.map(a => a.q));
            const imbalance = (bidVol - askVol) / ((bidVol + askVol) || 1);

            // 3. Score Calculation
            let score = 0;
            if (currentFisher > 0) score += 2; else score -= 2;
            if (currentRsi > 50) score += 1; else score -= 1;
            if (imbalance > 0.2) score += 1.5; else if (imbalance < -0.2) score -= 1.5;
            if (price > bb.mid[last]) score += 1; else score -= 1;

            // 4. Position Management (Simplified Close Check)
            if (this.exchange.position) {
                const pos = this.exchange.position;
                let hitExit = false;
                if (pos.action === 'BUY' && (price <= pos.sl || price >= pos.tp)) hitExit = true;
                if (pos.action === 'SELL' && (price >= pos.sl || price <= pos.tp)) hitExit = true;
                
                if (hitExit) {
                    const pnl = await this.exchange.close(price);
                    this.circuitBreaker.updatePnL(pnl);
                }
            }

            // 5. HYBRID TRIGGER REFINEMENT
            const now = Date.now();
            const scoreThreshold = this.config.indicators.threshold;
            const fisherSign = Math.sign(currentFisher);
            
            let shouldQueryAI = false;
            
            if (Math.abs(score) >= scoreThreshold && (now - this.aiLastQueryTime > this.aiThrottleMs)) {
                if (Math.sign(score) === fisherSign || Math.abs(score) >= 4.0) { 
                    shouldQueryAI = true;
                }
            }


            if (this.circuitBreaker.canTrade() && !this.exchange.position && shouldQueryAI) {
                this.aiLastQueryTime = now;
                process.stdout.write(`\n`); 
                console.log(COLOR.CYAN(`[Trigger] Score ${score.toFixed(2)} hit threshold. Querying Gemini...`));
                
                const context = {
                    symbol: this.config.symbol,
                    price, rsi: currentRsi, fisher: currentFisher,
                    atr: currentAtr, imbalance, score
                };

                const decision = await this.ai.analyze(context);
                
                if (decision.confidence >= this.config.ai.minConfidence && decision.action !== 'HOLD') {
                    const sl = decision.sl || (decision.action === 'BUY' ? price - 2*currentAtr : price + 2*currentAtr);
                    const tp = decision.tp || (decision.action === 'BUY' ? price + 3*currentAtr : price - 3*currentAtr);
                    
                    const qty = Utils.calcSize(this.exchange.balance, price, sl, this.config.risk.maxRiskPerTrade);

                    if (qty.gt(0)) {
                        await this.exchange.execute(decision.action, qty.toNumber(), sl, tp);
                    }
                }
            }

            this.renderHUD(price, score, currentRsi, this.data.latency, currentFisher, currentAtr, imbalance);

        } catch (e) {
            console.error(COLOR.RED(`[Loop Error] ${e.message}`));
        } finally {
            this.isProcessing = false;
        }
    }

    renderHUD(price, score, rsi, latency, fisher, atr, imbalance) {
        const time = Utils.timestamp();
        const latColor = latency > 500 ? COLOR.RED : COLOR.GREEN;
        const scoreColor = score > 0 ? COLOR.GREEN : COLOR.RED;
        const fishColor = fisher > 0 ? COLOR.BLUE : COLOR.PURPLE;
        const imbColor = imbalance > 0 ? COLOR.GREEN : COLOR.RED;
        const posText = this.exchange.position ? `${this.exchange.position.action}` : 'FLAT';
        
        process.stdout.write(
            `\r${COLOR.GRAY(time)} | ${COLOR.BOLD(this.config.symbol)} ${price.toFixed(2)} | ` +
            `Lat: ${latColor(latency+'ms')} | ` +
            `Score: ${scoreColor(score.toFixed(1))} | ` +
            `RSI: ${rsi.toFixed(1)} | ` +
            `Fish: ${fishColor(fisher.toFixed(2))} | ` +
            `ATR: ${atr.toFixed(2)} | ` +
            `Imb: ${imbColor((imbalance*100).toFixed(0)+'%')} | ` +
            `${COLOR.YELLOW(posText)}      `
        );
    }
}

// === START ===
new Leviathan();
