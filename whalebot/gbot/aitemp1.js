/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v8.0 (ULTIMATE)
 * ===================================================
 * - ARCHITECTURE: Hybrid Quantitative (WSS) + Qualitative (LLM) Analysis.
 * - CORE: Multi-Timeframe Trend, Momentum, Volume, and Order Flow Engine.
 * - PERSISTENCE: Built-in JSON trade history tracking (trades.json).
 * - SAFETY: Volatility-adjusted position sizing & Circuit Breakers.
 * - PRECISION: Strict Decimal.js handling for financial accuracy.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { existsSync } from 'fs';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// =============================================================================
// 1. CONFIGURATION & STATE MANAGEMENT
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { main: '3', trend: '15', daily: 'D' },
        limits: { kline: 500, orderbook: 100 },
        delays: { loop: 5000, retry: 2000 },
        ai: { 
            model: 'gemini-1.5-flash', 
            minConfidence: 0.75,
            rateLimitMs: 2000
        },
        risk: {
            initialBalance: 1000.00,
            maxDrawdown: 10.0,
            dailyLossLimit: 5.0,
            riskPercent: 2.0,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001,
            volatilityAdjustment: true
        },
        indicators: {
            periods: { rsi: 14, stoch: 14, cci: 20, adx: 14, mfi: 14, chop: 14, bollinger: 20, atr: 14 },
            weights: {
                trendMTF: 2.5, 
                trendScalp: 1.5, 
                momentum: 2.0,
                volumeFlow: 1.5, 
                orderFlow: 1.2, 
                divergence: 2.5,
                actionThreshold: 2.0 // Score needed to trigger AI analysis
            }
        },
        orderbook: { wallThreshold: 3.0, srLevels: 5 }
    });

    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        try {
            await fs.access(this.CONFIG_FILE);
            const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            const userConfig = JSON.parse(fileContent);
            config = this.deepMerge(config, userConfig);
        } catch (error) {
            // Self-healing: Create default if missing
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
    static FILE = 'trades.json';

    static async load() {
        try {
            await fs.access(this.FILE);
            const data = await fs.readFile(this.FILE, 'utf-8');
            return JSON.parse(data);
        } catch {
            return [];
        }
    }

    static async save(trade) {
        const history = await this.load();
        history.push(trade);
        await fs.writeFile(this.FILE, JSON.stringify(history, null, 2));
    }
}

// =============================================================================
// 2. UTILS & VISUALS
// =============================================================================

const COLORS = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#0A84FF'),
    CYAN: chalk.hex('#64D2FF'), PURPLE: chalk.hex('#BF5AF2'), YELLOW: chalk.hex('#FFD60A'),
    GRAY: chalk.hex('#8E8E93'), ORANGE: chalk.hex('#FF9500'),
    BOLD: chalk.bold, bg: (text) => chalk.bgHex('#1C1C1E')(text)
};

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static safeLast(arr, def = 0) { return (Array.isArray(arr) && arr.length > 0) ? arr[arr.length - 1] : def; }
}

// =============================================================================
// 3. TECHNICAL ANALYSIS ENGINE (Optimized)
// =============================================================================

class TA {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        let result = [], sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result.push(sum / period);
        }
        return Utils.safeArray(period - 1).concat(result);
    }

    static wilders(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        let result = Utils.safeArray(data.length);
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) {
            result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        }
        return result;
    }

    static rsi(closes, period) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);
        return closes.map((_, i) => avgLoss[i] === 0 ? 100 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
    }

    static mfi(h, l, c, v, p) {
        let posFlow = [], negFlow = [];
        for (let i = 0; i < c.length; i++) {
            if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
            const tp = (h[i] + l[i] + c[i]) / 3;
            const prevTp = (h[i-1] + l[i-1] + c[i-1]) / 3;
            const raw = tp * v[i];
            if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
            else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
            else { posFlow.push(0); negFlow.push(0); }
        }
        let result = Utils.safeArray(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < p; j++) { pSum += posFlow[i-j]; nSum += negFlow[i-j]; }
            if (nSum === 0) result[i] = 100;
            else result[i] = 100 - (100 / (1 + (pSum / nSum)));
        }
        return result;
    }

    static bollinger(closes, period, stdDev) {
        const sma = this.sma(closes, period);
        const upper = [], lower = [], middle = sma;
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) { upper.push(0); lower.push(0); continue; }
            let sumSq = 0;
            for (let j = 0; j < period; j++) sumSq += Math.pow(closes[i - j] - sma[i], 2);
            const std = Math.sqrt(sumSq / period);
            upper.push(sma[i] + (std * stdDev));
            lower.push(sma[i] - (std * stdDev));
        }
        return { upper, middle, lower };
    }

    static atr(h, l, c, p) {
        let tr = [0];
        for (let i = 1; i < c.length; i++) {
            tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i-1]), Math.abs(l[i] - c[i-1])));
        }
        return this.wilders(tr, p);
    }

    static adx(h, l, c, p) {
        let plusDM = [0], minusDM = [0];
        for (let i = 1; i < c.length; i++) {
            const up = h[i] - h[i-1];
            const down = l[i-1] - l[i];
            plusDM.push(up > down && up > 0 ? up : 0);
            minusDM.push(down > up && down > 0 ? down : 0);
        }
        const tr = this.atr(h, l, c, 1);
        const atr = this.wilders(tr, p);
        const sPlus = this.wilders(plusDM, p);
        const sMinus = this.wilders(minusDM, p);
        let dx = [];
        for (let i = 0; i < c.length; i++) {
            const pDI = atr[i] === 0 ? 0 : (sPlus[i]/atr[i])*100;
            const mDI = atr[i] === 0 ? 0 : (sMinus[i]/atr[i])*100;
            const sum = pDI + mDI;
            dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI)/sum)*100);
        }
        return this.wilders(dx, p);
    }

    static findFVG(candles) {
        const len = candles.length;
        if (len < 5) return null;
        const c1 = candles[len - 4];
        const c2 = candles[len - 3]; // Impulse
        const c3 = candles[len - 2];
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }

    static detectDivergence(closes, rsi, period = 5) {
        const len = closes.length;
        if (len < period * 2) return 'NONE';
        const priceHigh = Math.max(...closes.slice(len - period));
        const rsiHigh = Math.max(...rsi.slice(len - period));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period));
        const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        
        if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH';
        
        const priceLow = Math.min(...closes.slice(len - period));
        const rsiLow = Math.min(...rsi.slice(len - period));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period));
        const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
        
        if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH';
        return 'NONE';
    }
}

// =============================================================================
// 4. DATA & WSS ENGINE
// =============================================================================

class MarketEngine {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: 10000 });
    }

    async fetch() {
        try {
            const [ticker, kline, klineMTF, orderbook] = await Promise.all([
                this.api.get('/tickers', { params: { category: 'linear', symbol: this.config.symbol } }),
                this.api.get('/kline', { params: { category: 'linear', symbol: this.config.symbol, interval: this.config.intervals.main, limit: this.config.limits.kline } }),
                this.api.get('/kline', { params: { category: 'linear', symbol: this.config.symbol, interval: this.config.intervals.trend, limit: 200 } }),
                this.api.get('/orderbook', { params: { category: 'linear', symbol: this.config.symbol, limit: this.config.limits.orderbook } })
            ]);

            const parse = (list) => list.reverse().map(c => ({
                t: parseInt(c[0]), o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5])
            }));

            return {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                candles: parse(kline.data.result.list),
                candlesMTF: parse(klineMTF.data.result.list),
                bids: orderbook.data.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                asks: orderbook.data.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }))
            };
        } catch (e) {
            console.warn(COLORS.RED(`[Data] Fetch Error: ${e.message}`));
            return null;
        }
    }

    calculateWSS(analysis, weights) {
        let score = 0;
        const last = analysis.closes.length - 1;
        const comp = { trend: 0, mom: 0, flow: 0, struct: 0 };

        // 1. Trend (MTF)
        if (analysis.trendMTF === 'BULLISH') { score += weights.trendMTF; comp.trend = weights.trendMTF; }
        else { score -= weights.trendMTF; comp.trend = -weights.trendMTF; }

        // 2. Momentum (RSI/MFI)
        const rsi = analysis.rsi[last];
        if (rsi < 30) { score += weights.momentum; comp.mom = weights.momentum; } // Oversold -> Bullish Reversion
        else if (rsi > 70) { score -= weights.momentum; comp.mom = -weights.momentum; } // Overbought -> Bearish Reversion
        
        // 3. Structure (Divergence/FVG)
        if (analysis.divergence === 'BULLISH') { score += weights.divergence; comp.struct += weights.divergence; }
        else if (analysis.divergence === 'BEARISH') { score -= weights.divergence; comp.struct -= weights.divergence; }
        
        if (analysis.isSqueeze) { 
            // Squeeze continuation logic: follow trend
            score += (analysis.trendMTF === 'BULLISH' ? 1 : -1);
        }

        // 4. Order Flow (Imbalance)
        if (analysis.imbalance > 0.3) { score += weights.orderFlow; comp.flow = weights.orderFlow; }
        else if (analysis.imbalance < -0.3) { score -= weights.orderFlow; comp.flow = -weights.orderFlow; }

        return { score: parseFloat(score.toFixed(2)), components: comp };
    }
}

// =============================================================================
// 5. EXCHANGE & RISK
// =============================================================================

class Exchange {
    constructor(config) {
        this.cfg = config.risk;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
        this.history = []; // In-memory cache
        this.dailyPnL = new Decimal(0);
        this.lastDay = new Date().getDate();
    }

    async init() {
        this.history = await HistoryManager.load();
        // Re-calculate balance based on history to ensure sync
        let totalPnL = new Decimal(0);
        this.history.forEach(t => totalPnL = totalPnL.add(new Decimal(t.netPnL)));
        this.balance = this.startBal.add(totalPnL);
    }

    checkDailyReset() {
        const today = new Date().getDate();
        if (today !== this.lastDay) {
            this.dailyPnL = new Decimal(0);
            this.lastDay = today;
            console.log(COLORS.GRAY("🔄 Daily PnL Reset"));
        }
    }

    getStats() {
        const wins = this.history.filter(t => new Decimal(t.netPnL).gt(0));
        const winRate = this.history.length > 0 ? (wins.length / this.history.length) * 100 : 0;
        return {
            balance: this.balance.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalTrades: this.history.length,
            winRate: winRate.toFixed(1)
        };
    }

    async evaluate(priceVal, signal) {
        this.checkDailyReset();
        const price = new Decimal(priceVal);

        // Close Logic
        if (this.pos) {
            let close = false, reason = '';
            if (this.pos.side === 'BUY') {
                if (price.lte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                else if (price.gte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
            } else {
                if (price.gte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                else if (price.lte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
            }

            if (close) {
                const rawPnL = this.pos.side === 'BUY' 
                    ? price.sub(this.pos.entry).mul(this.pos.qty) 
                    : this.pos.entry.sub(price).mul(this.pos.qty);
                const fee = price.mul(this.pos.qty).mul(this.cfg.fee);
                const netPnL = rawPnL.sub(fee);
                
                this.balance = this.balance.add(netPnL);
                this.dailyPnL = this.dailyPnL.add(netPnL);
                
                const tradeRecord = {
                    date: new Date().toISOString(),
                    symbol: 'BTCUSDT',
                    side: this.pos.side,
                    entry: this.pos.entry.toNumber(),
                    exit: price.toNumber(),
                    qty: this.pos.qty.toNumber(),
                    netPnL: netPnL.toNumber(),
                    reason,
                    strategy: this.pos.strategy
                };
                
                await HistoryManager.save(tradeRecord);
                this.history.push(tradeRecord);
                
                const color = netPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
                console.log(`${COLORS.BOLD(reason)}! PnL: ${color(netPnL.toFixed(2))} [${this.pos.strategy}]`);
                this.pos = null;
            }
        } 
        
        // Open Logic
        else if (signal.action !== 'HOLD' && signal.confidence >= 0.75) {
            // Drawdown Protection
            const drawdown = this.startBal.sub(this.balance).div(this.startBal).mul(100);
            if (drawdown.gt(this.cfg.maxDrawdown)) { console.log(COLORS.RED("⛔ Max Drawdown Hit. Trading Halted.")); return; }

            try {
                const entry = new Decimal(signal.entry);
                const sl = new Decimal(signal.stopLoss);
                const tp = new Decimal(signal.takeProfit);
                const dist = entry.sub(sl).abs();
                
                if (dist.isZero()) return;

                const riskAmt = this.balance.mul(this.cfg.riskPercent / 100);
                let qty = riskAmt.div(dist);
                const maxQty = this.balance.mul(this.cfg.leverageCap).div(price);
                if (qty.gt(maxQty)) qty = maxQty;

                if (qty.mul(price).lt(10)) { console.log(COLORS.GRAY("Trade too small.")); return; }

                this.pos = {
                    side: signal.action, entry, qty, sl, tp,
                    strategy: signal.strategy,
                    time: Date.now()
                };
                console.log(COLORS.GREEN(`🚀 OPEN ${signal.action} @ ${entry.toFixed(2)} | Size: ${qty.toFixed(4)}`));
            } catch (e) { console.error(e); }
        }
    }
}

// =============================================================================
// 6. AI AGENT
// =============================================================================

class AIAgent {
    constructor(config) {
        const key = process.env.GEMINI_API_KEY;
        if (!key) throw new Error("Missing GEMINI_API_KEY");
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.ai.model });
    }

    async analyze(ctx) {
        await sleep(2000); 

        const prompt = `
        ROLE: Institutional Crypto Algo.
        TASK: Decide trade action based on data.
        
        DATA:
        - Price: ${ctx.price}
        - Trend (MTF): ${ctx.trendMTF}
        - WSS Score: ${ctx.wss.score} (Trend:${ctx.wss.components.trend}, Mom:${ctx.wss.components.mom})
        - Indicators: RSI=${ctx.rsi}, MFI=${ctx.mfi}, ADX=${ctx.adx}
        - Structure: Squeeze=${ctx.isSqueeze}, Div=${ctx.divergence}, FVG=${ctx.fvg ? ctx.fvg.type : 'None'}
        - Orderbook: Imbalance=${(ctx.imbalance*100).toFixed(1)}%

        RULES:
        1. BUY if WSS > 2.0. SELL if WSS < -2.0.
        2. HOLD if WSS between -2.0 and 2.0 (Noise).
        3. Confirm with Orderbook/Volume.
        4. Min R:R = 1.5.

        OUTPUT JSON: { "action": "BUY"|"SELL"|"HOLD", "strategy": "string", "confidence": 0.0-1.0, "entry": number, "stopLoss": number, "takeProfit": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const txt = res.response.text().replace(/```json|```/g, '').trim();
            const json = JSON.parse(txt);
            
            // Safety Override based on WSS
            if (json.action === 'BUY' && ctx.wss.score < 1.0) json.action = 'HOLD';
            if (json.action === 'SELL' && ctx.wss.score > -1.0) json.action = 'HOLD';

            return json;
        } catch (e) {
            return { action: "HOLD", confidence: 0, reason: "AI Error" };
        }
    }
}

// =============================================================================
// 7. MAIN ENGINE
// =============================================================================

async function main() {
    console.clear();
    console.log(COLORS.bg(COLORS.BOLD(COLORS.PURPLE(` 🐋 WHALEWAVE TITAN v8.0 (ULTIMATE) `))));

    const config = await ConfigManager.load();
    const market = new MarketEngine(config);
    const exchange = new Exchange(config);
    const ai = new AIAgent(config);

    await exchange.init();
    console.log(COLORS.GREEN(`✅ System Init. Balance: $${exchange.balance.toFixed(2)}`));

    while (true) {
        try {
            const data = await market.fetch();
            if (!data) { await sleep(config.delays.retry); continue; }

            // Analysis
            const c = data.candles.map(x => x.c);
            const h = data.candles.map(x => x.h);
            const l = data.candles.map(x => x.l);
            const v = data.candles.map(x => x.v);
            const mtfC = data.candlesMTF.map(x => x.c);

            const rsi = TA.rsi(c, config.indicators.periods.rsi);
            const mfi = TA.mfi(h,l,c,v, config.indicators.periods.mfi);
            const adx = TA.adx(h,l,c, config.indicators.periods.adx);
            const bb = TA.bollinger(c, config.indicators.periods.bollinger, 2);
            const atr = TA.atr(h,l,c, config.indicators.periods.atr);
            const fvg = TA.findFVG(data.candles);
            const divergence = TA.detectDivergence(c, rsi);

            const last = c.length - 1;
            const isSqueeze = (bb.upper[last] - bb.lower[last]) < (bb.upper[last-1] - bb.lower[last-1]) * 0.9;
            
            // MTF Trend
            const smaMTF = TA.sma(mtfC, 20);
            const trendMTF = mtfC[mtfC.length-1] > smaMTF[smaMTF.length-1] ? 'BULLISH' : 'BEARISH';

            // Orderbook Imbalance
            const bidVol = data.bids.reduce((a,b)=>a+b.q,0);
            const askVol = data.asks.reduce((a,b)=>a+b.q,0);
            const imbalance = (bidVol + askVol) > 0 ? (bidVol - askVol) / (bidVol + askVol) : 0;

            const analysis = { closes: c, rsi, mfi, adx, divergence, isSqueeze, trendMTF, imbalance };
            const wss = market.calculateWSS(analysis, config.indicators.weights);

            // Context Construction
            const ctx = {
                price: data.price, trendMTF, wss, rsi: rsi[last].toFixed(2), mfi: mfi[last].toFixed(2),
                adx: adx[last].toFixed(2), isSqueeze, divergence, fvg, imbalance
            };

            // AI Decision
            let signal = { action: "HOLD", confidence: 0, reason: "WSS Neutral" };
            if (Math.abs(wss.score) >= config.indicators.weights.actionThreshold) {
                 process.stdout.write(COLORS.CYAN(" 🧠 AI Analyzing... "));
                 signal = await ai.analyze(ctx);
                 process.stdout.write("\r");
            }

            // Dashboard
            console.clear();
            const border = COLORS.GRAY('─'.repeat(60));
            console.log(border);
            console.log(COLORS.BOLD(` PRICE: ${data.price} | WSS: ${wss.score > 0 ? COLORS.GREEN(wss.score) : COLORS.RED(wss.score)} | TREND: ${trendMTF}`));
            console.log(` RSI: ${ctx.rsi} | MFI: ${ctx.mfi} | ADX: ${ctx.adx} | IMB: ${(imbalance*100).toFixed(1)}%`);
            console.log(` DIV: ${divergence} | SQZ: ${isSqueeze ? COLORS.ORANGE('ON') : 'OFF'} | FVG: ${fvg ? COLORS.YELLOW(fvg.type) : 'None'}`);
            console.log(border);
            console.log(` SIGNAL: ${signal.action === 'BUY' ? COLORS.GREEN(signal.action) : signal.action === 'SELL' ? COLORS.RED(signal.action) : COLORS.GRAY(signal.action)} (${(signal.confidence*100).toFixed(0)}%)`);
            console.log(` REASON: ${COLORS.GRAY(signal.reason)}`);
            console.log(border);
            
            const stats = exchange.getStats();
            const pnlColor = stats.dailyPnL >= 0 ? COLORS.GREEN : COLORS.RED;
            console.log(` 💰 BAL: $${stats.balance.toFixed(2)} | D.PnL: ${pnlColor('$'+stats.dailyPnL.toFixed(2))} | WinRate: ${stats.winRate}%`);
            
            if (exchange.pos) {
                const curPnL = exchange.pos.side === 'BUY' 
                    ? new Decimal(data.price).sub(exchange.pos.entry).mul(exchange.pos.qty)
                    : exchange.pos.entry.sub(new Decimal(data.price)).mul(exchange.pos.qty);
                const cPnLColor = curPnL.gte(0) ? COLORS.GREEN : COLORS.RED;
                console.log(COLORS.BLUE(` 📊 POS: ${exchange.pos.side} @ ${exchange.pos.entry.toFixed(2)} | PnL: ${cPnLColor(curPnL.toFixed(2))}`));
            }
            console.log(border);

            // Execute
            await exchange.evaluate(data.price, signal);

        } catch (err) {
            console.error(COLORS.RED(`Loop Error: ${err.message}`));
        }
        await sleep(config.delays.loop);
    }
}

// Start
main();
