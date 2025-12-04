/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v11.1 (LATENCY OPTIMIZED)
 * ===========================================================
 * - FIX: Implemented persistent HTTPS connection agent (Keep-Alive)
 * - FIX: Added Drift-Correcting Execution Loop (Strict 500ms intervals)
 * - FIX: Optimized Parallel Startup Sequence
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import WebSocket from 'ws';
import https from 'https'; // NEW: For Keep-Alive Agent

dotenv.config();

// =============================================================================
// 1. SYSTEM CONFIGURATION & AGENT SETUP
// =============================================================================

// High-Performance HTTPS Agent to reuse TCP connections
// This removes 50-100ms of SSL Handshake latency per request
const keepAliveAgent = new https.Agent({
    keepAlive: true,
    maxSockets: 256,
    maxFreeSockets: 256,
    scheduling: 'lifo',
    timeout: 5000 // 5s socket timeout
});

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'TRUMPUSDT',
        intervals: { scalp: '1', quick: '3', trend: '5', macro: '15' },
        limits: { kline: 100, orderbook: 50, ticks: 1000 }, // Reduced K-line buffer for speed
        delays: { loop: 500, retry: 500, ai: 1000 },
        ai: { 
            model: 'gemini-1.5-pro', 
            minConfidence: 0.88,
            temperature: 0.05,
            rateLimitMs: 1200,
            maxRetries: 2
        },
        risk: {
            initialBalance: 1000.00,
            maxDrawdown: 6.0,
            riskPercent: 0.75,
            leverageCap: 15,
            fee: 0.00045,
            slippage: 0.00005,
            volatilityAdjustment: true,
            maxPositionSize: 0.30
        },
        indicators: {
            periods: { rsi: 5, fisher: 7, stoch: 3, cci: 10, adx: 6, mfi: 5, chop: 10, bollinger: 15, atr: 6, williams: 7, momentum: 9, roc: 8, ema_fast: 5 },
            scalping: {
                volumeSpikeThreshold: 2.0,
                priceAcceleration: 0.00015,
                orderFlowImbalance: 0.30,
                liquidityThreshold: 500000
            },
            weights: {
                microTrend: 4.0, momentum: 3.5, volume: 3.0, orderFlow: 2.8, neural: 3.0, actionThreshold: 2.5  
            },
            neural: { enabled: true, features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum'] }
        },
        scalping: {
            maxHoldingTime: 600000,      // 10 minutes
            timeBasedExit: 180000,       // 3 minutes stale
            quickExitThreshold: 0.00075, // 0.075% quick scalp
            trailingStop: 0.0005
        },
        websocket: { enabled: true, reconnectInterval: 1000 }
    });

    static async load() {
        try {
            await fs.access(this.CONFIG_FILE);
            const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            return this.deepMerge(JSON.parse(JSON.stringify(this.DEFAULTS)), JSON.parse(fileContent));
        } catch (error) {
            return JSON.parse(JSON.stringify(this.DEFAULTS));
        }
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value)) result[key] = this.deepMerge(result[key] || {}, value);
            else result[key] = value;
        }
        return result;
    }
}

class HistoryManager {
    static FILE = 'scalping_trades.json';
    static ANALYTICS_FILE = 'scalping_analytics.json';
    static NEURAL_FILE = 'neural_weights.json';

    static async load() { try { return JSON.parse(await fs.readFile(this.FILE, 'utf-8')); } catch { return []; } }
    
    static async save(trade) {
        const history = await this.load();
        history.push(trade);
        await fs.writeFile(this.FILE, JSON.stringify(history, null, 2));
        await this.updateAnalytics(history);
    }

    static async updateAnalytics(trades) {
        const scalps = trades.filter(t => t.strategy.includes('Scalp'));
        if (scalps.length === 0) return;
        const wins = scalps.filter(t => t.netPnL > 0);
        const losses = scalps.filter(t => t.netPnL <= 0);
        
        const analytics = {
            trades: scalps.length,
            winRate: (wins.length / scalps.length) * 100,
            bestWin: Math.max(...scalps.map(t => t.netPnL)),
            worstLoss: Math.min(...scalps.map(t => t.netPnL)),
            pf: Math.abs(wins.reduce((a,b)=>a+b.netPnL,0) / (losses.reduce((a,b)=>a+b.netPnL,0) || 1))
        };
        await fs.writeFile(this.ANALYTICS_FILE, JSON.stringify(analytics, null, 2));
    }

    static async logError(msg) { await fs.appendFile('error_log.txt', `[${new Date().toISOString()}] ${msg}\n`); }
}

// =============================================================================
// 2. UTILITIES & NEURAL LOGIC
// =============================================================================

const C = {
    G: chalk.hex('#39FF14'), R: chalk.hex('#FF073A'), B: chalk.hex('#0A84FF'), C: chalk.hex('#00FFFF'),
    Y: chalk.hex('#FAED27'), M: chalk.hex('#FF00FF'), P: chalk.hex('#FF1493'),
    DIM: chalk.dim, BOLD: chalk.bold
};

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static formatVal(n, d = 4) { return isNaN(n) ? '0.0000' : n.toFixed(d); }
    static formatTime(ms) { return ms < 1000 ? `${ms}ms` : ms < 60000 ? `${(ms/1000).toFixed(1)}s` : `${(ms/60000).toFixed(1)}m`; }
    static sigmoid(t) { return 1 / (1 + Math.exp(-t)); }
}

// =============================================================================
// 3. OPTIMIZED INDICATOR LIBRARY
// =============================================================================

class TA {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        let sum = 0, res = [];
        for(let i=0; i<period; i++) sum += data[i] || 0;
        res.push(sum/period);
        for(let i=period; i<data.length; i++) {
            sum += (data[i]||0) - (data[i-period]||0);
            res.push(sum/period);
        }
        return Utils.safeArray(period-1).concat(res);
    }

    static rsi(c, p=5) {
        let gains = [0], losses = [0];
        for(let i=1; i<c.length; i++) {
            const diff = c[i] - c[i-1];
            gains.push(diff>0?diff:0); losses.push(diff<0?Math.abs(diff):0);
        }
        const avgG = this.sma(gains, p), avgL = this.sma(losses, p);
        return c.map((_,i) => avgL[i]===0 ? 50 : 100-(100/(1+avgG[i]/avgL[i])));
    }

    static fisher(h, l, len=7) {
        const res = new Array(h.length).fill(0), val = new Array(h.length).fill(0);
        for(let i=len; i<h.length; i++) {
            let mn = Infinity, mx = -Infinity;
            for(let j=0; j<len; j++) {
                if(h[i-j]>mx) mx = h[i-j];
                if(l[i-j]<mn) mn = l[i-j];
            }
            let raw = 0;
            if(mx-mn > 0) raw = 0.66 * (( (h[i]+l[i])/2 - mn)/(mx-mn) - 0.5) + 0.67*(val[i-1]||0);
            raw = Math.max(-0.999, Math.min(0.999, raw));
            val[i] = raw;
            res[i] = 0.5 * Math.log((1+raw)/(1-raw)) + 0.5*(res[i-1]||0);
        }
        return res;
    }

    static atr(h, l, c, p=6) {
        let tr = [0];
        for(let i=1; i<c.length; i++) tr.push(Math.max(h[i]-l[i], Math.abs(h[i]-c[i-1]), Math.abs(l[i]-c[i-1])));
        return this.sma(tr, p);
    }

    static acceleration(c, p=5) {
        const res = new Array(c.length).fill(0);
        for(let i=p*2; i<c.length; i++) {
            const v1 = (c[i]-c[i-p])/p, v2 = (c[i-p]-c[i-p*2])/p;
            res[i] = v1 - v2;
        }
        return res;
    }

    static findFVG(k) {
        const gaps = [];
        for(let i=3; i<k.length; i++) {
            if(k[i-2].c > k[i-2].o && k[i-1].l > k[i-3].h) gaps.push({ type: 'BULL', price: (k[i-1].l+k[i-3].h)/2 });
            else if(k[i-2].c < k[i-2].o && k[i-3].l > k[i-1].h) gaps.push({ type: 'BEAR', price: (k[i-1].h+k[i-3].l)/2 });
        }
        return gaps;
    }
}

// =============================================================================
// 4. LOW-LATENCY MARKET ENGINE
// =============================================================================

class FastMarket {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ 
            baseURL: 'https://api.bybit.com/v5/market', 
            timeout: 3000,
            httpsAgent: keepAliveAgent // Keeps connection open!
        });
        this.cache = { price: 0, bids: [], asks: [], kline: {} };
        this.lastWsUpdate = 0;
    }

    async fetchTimeframes() {
        const start = Date.now();
        const intervals = [this.config.intervals.scalp, this.config.intervals.quick, this.config.intervals.trend];
        
        try {
            // Parallel execution of heavy I/O
            const [ticker, ...klines] = await Promise.all([
                this.api.get('/tickers', { params: { category: 'linear', symbol: this.config.symbol } }),
                ...intervals.map(i => this.api.get('/kline', { params: { category: 'linear', symbol: this.config.symbol, interval: i, limit: this.config.limits.kline } }))
            ]);

            const data = {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                volume: parseFloat(ticker.data.result.list[0].volume24h),
                latency: Date.now() - start,
                kline: {}
            };

            const parse = list => list.reverse().map(c => ({ 
                t: parseInt(c[0]), o: parseFloat(c[1]), h: parseFloat(c[2]), 
                l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]) 
            }));

            intervals.forEach((interval, i) => data.kline[interval] = parse(klines[i].data.result.list));
            return data;
        } catch (e) {
            console.error(C.R(`[Fetch Error] ${e.message}`));
            return null;
        }
    }

    startWebsocket() {
        if (!this.config.websocket.enabled) return;
        const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        ws.on('open', () => {
            console.log(C.G('📡 WS Connected'));
            ws.send(JSON.stringify({ op: "subscribe", args: [`tickers.${this.config.symbol}`, `orderbook.50.${this.config.symbol}`] }));
        });

        ws.on('message', (d) => {
            try {
                const msg = JSON.parse(d);
                if (msg.topic?.includes('tickers')) { 
                    this.cache.price = parseFloat(msg.data.lastPrice); 
                    this.lastWsUpdate = Date.now();
                }
                if (msg.topic?.includes('orderbook')) {
                    if (msg.type === 'snapshot') {
                        this.cache.bids = msg.data.b.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                        this.cache.asks = msg.data.a.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                    }
                }
            } catch(e) {}
        });
        
        ws.on('close', () => setTimeout(() => this.startWebsocket(), 1000));
    }

    calculateWSS(analysis) {
        let score = 0;
        const w = this.config.indicators.weights;
        const last = analysis.c.length - 1;

        // Trend (Scalp + Trend alignment)
        if (analysis.trendMTF === 'BULLISH') score += w.microTrend;
        else if (analysis.trendMTF === 'BEARISH') score -= w.microTrend;

        // Momentum
        if (analysis.rsi[last] > 40 && analysis.fisher[last] > 0.5) score += w.momentum;
        if (analysis.rsi[last] < 60 && analysis.fisher[last] < -0.5) score -= w.momentum;

        // Order Flow
        const imb = this.cache.bids.reduce((a,b)=>a+b.q,0) / (this.cache.asks.reduce((a,b)=>a+b.q,0) + this.cache.bids.reduce((a,b)=>a+b.q,0) || 1);
        if (imb > 0.6) score += w.orderFlow;
        else if (imb < 0.4) score -= w.orderFlow;

        return { score: parseFloat(score.toFixed(2)), imb: (imb-0.5)*2 };
    }
}

// =============================================================================
// 5. AI EXECUTION AGENT
// =============================================================================

class ScalpingAI {
    constructor(config) {
        if (!process.env.GEMINI_API_KEY) throw new Error("API Key Missing");
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ model: config.ai.model });
        this.config = config;
        this.lastCall = 0;
    }

    async predict(ctx) {
        if (Date.now() - this.lastCall < this.config.ai.rateLimitMs) return null;
        this.lastCall = Date.now();

        const prompt = `SCALPER AI. Market Context for ${ctx.symbol}:
- Price: ${ctx.price} | Latency: ${ctx.latency}ms
- Trend (1m/3m): ${ctx.microTrend}/${ctx.trendMTF}
- Momentum: RSI=${ctx.rsi} | Fisher=${ctx.fisher} | OF=${(ctx.imbalance*100).toFixed(1)}%
- Structure: FVG=${ctx.fvg} | Accel=${ctx.accel.toFixed(7)} | Vol=${ctx.vol ? 'HIGH' : 'NORMAL'}
Rules:
1. Signal ONLY if score > 2.8 or < -2.8.
2. Max risk ${ctx.riskPerc}%.
3. Output valid JSON: {"action":"BUY"|"SELL"|"HOLD","confidence":0.0-1.0,"entry":${ctx.price},"tp":num,"sl":num,"reason":"short_string"}`;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const signal = JSON.parse(text);
            
            // Hard Gate Filters
            const scoreAbs = Math.abs(ctx.score);
            if (signal.action === 'BUY' && (ctx.score < 2.0 || signal.confidence < 0.85)) return null;
            if (signal.action === 'SELL' && (ctx.score > -2.0 || signal.confidence < 0.85)) return null;
            
            return signal;
        } catch { return null; }
    }
}

// =============================================================================
// 6. TRADING LOGIC
// =============================================================================

class TradingEngine {
    constructor(config) {
        this.config = config;
        this.balance = new Decimal(config.risk.initialBalance);
        this.equity = this.balance;
        this.pos = null;
        this.pnlToday = 0;
    }

    async evaluate(priceVal, signal) {
        const price = new Decimal(priceVal);

        if (this.pos) {
            // High-Freq PnL Monitor
            const rawPnL = this.pos.side==='BUY' ? price.sub(this.pos.entry) : this.pos.entry.sub(price);
            const pnlPct = rawPnL.div(this.pos.entry).toNumber();
            const elapsed = Date.now() - this.pos.time;

            let exit = false; reason = "";

            // Dynamic Scalp Targets
            if (pnlPct < -0.0008) { exit = true; reason = 'Quick Stop'; } // Tight 0.08% Stop
            else if (elapsed > this.config.scalping.maxHoldingTime) { exit = true; reason = 'Time Limit'; }
            else if (elapsed > 20000 && pnlPct < 0) { exit = true; reason = 'Stale Scalp'; } // 20s stagnant
            
            if (!exit && this.pos.side === 'BUY') {
                if (price.lte(this.pos.sl) || price.gte(this.pos.tp)) { exit = true; reason = 'Level Hit'; }
            } else if (!exit) {
                if (price.gte(this.pos.sl) || price.lte(this.pos.tp)) { exit = true; reason = 'Level Hit'; }
            }

            if (exit) {
                const size = new Decimal(this.pos.qty);
                const realized = rawPnL.mul(size);
                const fees = price.mul(size).mul(this.config.risk.fee);
                const net = realized.sub(fees);
                
                this.balance = this.balance.add(net);
                this.pnlToday += net.toNumber();
                
                const col = net.gte(0) ? C.G : C.R;
                console.log(C.BOLD(`${col(reason)} | PnL: ${col(net.toFixed(2))} | Time: ${Utils.formatTime(elapsed)}`));
                
                await HistoryManager.save({ 
                    date: new Date().toISOString(), symbol: this.config.symbol, side: this.pos.side,
                    entry: this.pos.entry.toNumber(), exit: priceVal, netPnL: net.toNumber(),
                    strategy: this.pos.strategy, reason
                });
                
                this.pos = null;
            }
        } 
        
        else if (signal && signal.action !== 'HOLD') {
            const entry = new Decimal(signal.entry);
            const sl = new Decimal(signal.sl);
            const dist = entry.sub(sl).abs();
            if (dist.isZero()) return;

            const risk = this.balance.mul(this.config.risk.riskPercent / 100);
            let qty = risk.div(dist);
            const maxPos = this.balance.mul(this.config.risk.leverageCap).div(entry);
            if (qty.gt(maxPos)) qty = maxPos;

            this.pos = {
                side: signal.action, entry, qty, sl, tp: new Decimal(signal.tp),
                time: Date.now(), strategy: signal.strategy
            };
            const icon = signal.action === 'BUY' ? '🚀' : '🔻';
            console.log(C.BOLD(`${icon} OPEN ${signal.action} @ ${entry.toFixed(4)} | Size: ${qty.toFixed(4)} | R:R ${(Math.abs(signal.tp-signal.entry)/Math.abs(signal.entry-signal.sl)).toFixed(1)}`));
        }
    }
}

// =============================================================================
// 7. DRIFT-CORRECTING LOOP
// =============================================================================

async function main() {
    console.clear();
    const config = await ConfigManager.load();
    const market = new FastMarket(config);
    const trader = new TradingEngine(config);
    const brain = new ScalpingAI(config);

    console.log(C.BOLD(C.P(`🌊 WHALEWAVE v11.1 (Latency-Optimized)`)));
    console.log(C.C(`System Ready. Target Loop: ${config.delays.loop}ms`));
    market.startWebsocket();

    let loopCount = 0;
    // START PRE-FETCH
    await market.fetchTimeframes(); 

    while (true) {
        const loopStart = Date.now(); // ⏱️ Start Timer

        try {
            // 1. Data Phase
            const data = await market.fetchTimeframes();
            if (!data) throw new Error("Data Drift");

            // 2. Compute
            const c = data.kline[config.intervals.scalp].map(x=>x.c);
            const h = data.kline[config.intervals.scalp].map(x=>x.h);
            const l = data.kline[config.intervals.scalp].map(x=>x.l);
            const v = data.kline[config.intervals.scalp].map(x=>x.v);

            // Light Calc (Keep under 5ms)
            const rsi = TA.rsi(c);
            const fisher = TA.fisher(h, l);
            const accel = TA.acceleration(c);
            const trendQ = data.kline[config.intervals.quick];
            const tQ_SMA = TA.sma(trendQ.map(x=>x.c), 10);
            const trend = trendQ[trendQ.length-1].c > tQ_SMA[tQ_SMA.length-1] ? 'BULLISH' : 'BEARISH';
            const fvg = TA.findFVG(data.kline[config.intervals.scalp]).length;

            const scoreObj = market.calculateWSS({ c, rsi, fisher, trendMTF: trend });
            const ctx = {
                symbol: config.symbol, price: data.price, latency: data.latency,
                rsi: rsi[rsi.length-1].toFixed(1), fisher: fisher[fisher.length-1].toFixed(2),
                score: scoreObj.score, imbalance: scoreObj.imb, trendMTF: trend, fvg,
                accel: accel[accel.length-1], riskPerc: config.risk.riskPercent,
                vol: v[v.length-1] > TA.sma(v, 20)[v.length-1]*2 // Vol Spike check
            };

            // 3. AI Phase (Async, Non-Blocking check first)
            let signal = null;
            if (Math.abs(scoreObj.score) > 2.8) {
                // process.stdout.write(C.Y(" ⚡ Neural Check... "));
                signal = await brain.predict(ctx);
                // process.stdout.write("\r");
            }

            // 4. Exec Phase
            await trader.evaluate(data.price, signal);

            // 5. Dashboard (Updates every 2 cycles to save I/O time)
            if (loopCount++ % 2 === 0) {
                // Clear lines or concise log to reduce overhead
                process.stdout.write(`\r\x1b[K${C.BOLD(new Date().toLocaleTimeString())} | ${C.C(config.symbol)} $${data.price.toFixed(4)} | LAT: ${data.latency < 100 ? C.G(data.latency) : C.R(data.latency)}ms | SCORE: ${scoreObj.score > 0 ? C.G(scoreObj.score) : C.R(scoreObj.score)} | IMB: ${(scoreObj.imb*100).toFixed(0)}%`);
                if (signal) console.log(`\n -> SIGNAL: ${signal.action}`);
            }

        } catch (e) {
            // Silent error on drift to maintain rhythm
        }

        // 6. DRIFT CORRECTION
        const processingTime = Date.now() - loopStart;
        const waitTime = Math.max(0, config.delays.loop - processingTime);
        
        await sleep(waitTime); // Precise sleep
    }
}

if (!process.env.GEMINI_API_KEY) { console.error("Key Missing"); process.exit(1); }
main().catch(console.error);
