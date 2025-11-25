/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION
 * -----------------------------------------------------
 * - Architecture: Multi-Timeframe (MTF) Data Aggregation.
 * - New Indicators: MFI, Chop Index, LinReg Slope/R2, Keltner Channels.
 * - SMC Features: Fair Value Gap (FVG) & Orderbook Whale Wall detection.
 * - Logic: "Regime-Based" AI decision making (Momentum vs Reversion).
 * - Safety: Strict type checking and defensive math throughout.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ CONFIGURATION ---
const CONFIG_FILE = 'config.json';
const DEFAULTS = {
    symbol: 'BTCUSDT',
    interval: '3',       // Scalping Timeframe
    trend_interval: '15', // Trend Timeframe (MTF)
    limit: 300,
    loop_delay: 15,
    gemini_model: 'gemini-2.5-flash-lite', // Use 'gemini-2.0-flash' if available
    min_confidence: 0.60, // Higher threshold for Titan
    paper_trading: {
        initial_balance: 1000.00,
        risk_percent: 1.0,
        leverage_cap: 10,
        fee: 0.00055
    },
    indicators: {
        rsi: 14,
        mfi: 14,
        chop_period: 14,
        linreg_period: 20,
        bb_period: 20, bb_std: 2.0,
        kc_period: 20, kc_mult: 1.5, // Keltner Channels
        adx_period: 14,
        vwap_period: 20
    },
    orderbook: {
        depth: 50,
        wall_threshold: 5.0 // Multiplier of avg volume to define a "Wall"
    }
};

// Load Config
let config = DEFAULTS;
if (fs.existsSync(CONFIG_FILE)) {
    try {
        const userConfig = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
        config = { ...DEFAULTS, ...userConfig, indicators: { ...DEFAULTS.indicators, ...userConfig.indicators } };
    } catch (e) {
        console.error("Config Error: Using defaults.");
    }
} else {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(DEFAULTS, null, 2));
}

// Precision setup
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME ---
const NEON = {
    GREEN: chalk.hex('#39FF14'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'),
    YELLOW: chalk.hex('#FAED27'),
    ORANGE: chalk.hex('#FF9F00'),
    GRAY: chalk.hex('#666666'),
    BOLD: chalk.bold
};

// --- 📐 ADVANCED TA LIBRARY ---
class TA {
    static safeArr(len) { return new Array(Math.floor(len)).fill(0); }

    static sma(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = [];
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            sum += data[i] - data[i - period];
            result.push(sum / period);
        }
        return TA.safeArr(period - 1).concat(result);
    }

    static ema(data, period) {
        if (!data || data.length === 0) return [];
        let result = TA.safeArr(data.length);
        const k = 2 / (period + 1);
        result[0] = data[0];
        for (let i = 1; i < data.length; i++) {
            result[i] = (data[i] * k) + (result[i - 1] * (1 - k));
        }
        return result;
    }

    static wilders(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = TA.safeArr(data.length);
        let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) {
            result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        }
        return result;
    }

    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) {
            tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        }
        return this.wilders(tr, period);
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

    static mfi(highs, lows, closes, volumes, period) {
        let posFlow = [], negFlow = [];
        for (let i = 0; i < closes.length; i++) {
            if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
            const tp = (highs[i] + lows[i] + closes[i]) / 3;
            const prevTp = (highs[i-1] + lows[i-1] + closes[i-1]) / 3;
            const raw = tp * volumes[i];
            if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
            else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
            else { posFlow.push(0); negFlow.push(0); }
        }
        
        let result = TA.safeArr(period);
        for (let i = period; i < closes.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < period; j++) {
                pSum += posFlow[i-j];
                nSum += negFlow[i-j];
            }
            if (nSum === 0) result.push(100);
            else result.push(100 - (100 / (1 + (pSum / nSum))));
        }
        return TA.safeArr(period).concat(result).slice(period); // Align length
    }

    static bollinger(closes, period, stdDev) {
        const sma = this.sma(closes, period);
        let upper = [], lower = [], middle = sma;
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

    static keltner(highs, lows, closes, period, mult) {
        const ema = this.ema(closes, period);
        const atr = this.atr(highs, lows, closes, period);
        return {
            upper: ema.map((e, i) => e + atr[i] * mult),
            lower: ema.map((e, i) => e - atr[i] * mult),
            middle: ema
        };
    }

    static linReg(closes, period) {
        let slopes = TA.safeArr(closes.length), r2s = TA.safeArr(closes.length);
        let sumX = 0, sumX2 = 0;
        for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }

        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0, sumXY = 0, sumY2 = 0;
            const ySlice = [];
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j];
                ySlice.push(val);
                sumY += val;
                sumXY += j * val;
                sumY2 += val * val;
            }
            const n = period;
            const num = (n * sumXY) - (sumX * sumY);
            const den = (n * sumX2) - (sumX * sumX);
            const slope = den === 0 ? 0 : num / den;
            
            const intercept = (sumY - slope * sumX) / n;
            let ssTot = 0, ssRes = 0;
            const yMean = sumY / n;
            for(let j=0; j<period; j++) {
                const y = ySlice[j];
                const yPred = slope * j + intercept;
                ssTot += Math.pow(y - yMean, 2);
                ssRes += Math.pow(y - yPred, 2);
            }
            slopes[i] = slope;
            r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
        }
        return { slope: slopes, r2: r2s };
    }

    static chop(highs, lows, closes, period) {
        let result = TA.safeArr(closes.length);
        let tr = [highs[0] - lows[0]]; 
        for(let i=1; i<closes.length; i++) {
            tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i-1]), Math.abs(lows[i] - closes[i-1])));
        }
        for (let i = period; i < closes.length; i++) {
            let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
            for (let j = 0; j < period; j++) {
                sumTr += tr[i - j];
                if (highs[i - j] > maxHi) maxHi = highs[i - j];
                if (lows[i - j] < minLo) minLo = lows[i - j];
            }
            const range = maxHi - minLo;
            result[i] = (range === 0 || sumTr === 0) ? 0 : 100 * (Math.log10(sumTr / range) / Math.log10(period));
        }
        return result;
    }

    static findFVG(candles) {
        // Look at the most recent complete 3-candle sequence
        // Index: [..., c1, c2, c3, current]
        const len = candles.length;
        if (len < 5) return null;
        
        const c1 = candles[len - 4];
        const c2 = candles[len - 3]; // Impulse
        const c3 = candles[len - 2]; 

        let fvg = null;
        // Bullish
        if (c2.c > c2.o && c3.l > c1.h) { 
            fvg = { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        }
        // Bearish
        else if (c2.c < c2.o && c3.h < c1.l) {
            fvg = { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        }
        return fvg;
    }
}

// --- 📡 DATA PROVIDER ---
class DataProvider {
    constructor() {
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: 8000 });
    }

    async fetchAll() {
        try {
            // MTF: Fetch 3m and 15m concurrently
            const [ticker, kline, klineMTF, ob] = await Promise.all([
                this.api.get('/tickers', { params: { category: 'linear', symbol: config.symbol } }),
                this.api.get('/kline', { params: { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit } }),
                this.api.get('/kline', { params: { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 50 } }),
                this.api.get('/orderbook', { params: { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth } })
            ]);

            const parseC = (list) => list.reverse().map(c => ({
                o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5])
            }));

            return {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                candles: parseC(kline.data.result.list),
                candlesMTF: parseC(klineMTF.data.result.list),
                bids: ob.data.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                asks: ob.data.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }))
            };
        } catch (e) {
            console.warn(NEON.ORANGE(`[WARN] Data Fetch Fail: ${e.message}`));
            return null;
        }
    }
}

// --- 💰 PAPER EXCHANGE ---
class PaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null; 
    }

    evaluate(priceVal, signal) {
        const price = new Decimal(priceVal);

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
                const rawPnl = this.pos.side === 'BUY'
                    ? price.sub(this.pos.entry).mul(this.pos.qty)
                    : this.pos.entry.sub(price).mul(this.pos.qty);
                const fee = price.mul(this.pos.qty).mul(config.paper_trading.fee);
                const netPnl = rawPnl.sub(fee);
                this.balance = this.balance.add(netPnl);
                this.pos = null;
                console.log(`${NEON.BOLD(reason)}! PnL: ${netPnl.gte(0) ? NEON.GREEN('$' + netPnl.toFixed(2)) : NEON.RED('$' + netPnl.toFixed(2))}`);
            }
        } else if (signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) {
            if (!signal.entry || !signal.sl || !signal.tp) return;

            try {
                const entry = new Decimal(signal.entry);
                const sl = new Decimal(signal.sl);
                const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
                const dist = entry.sub(sl).abs();

                if (dist.isZero()) return; // Defensive check

                let qty = riskAmt.div(dist);
                const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
                if (qty.gt(maxQty)) qty = maxQty;

                if (qty.mul(price).lt(10)) { console.log(NEON.GRAY("Trade value too low (<$10). Skipped.")); return; }

                this.balance = this.balance.sub(entry.mul(qty).mul(config.paper_trading.fee)); // Entry Fee
                this.pos = { side: signal.action, entry, qty, sl, tp: new Decimal(signal.tp) };
                console.log(NEON.GREEN(`OPEN ${signal.action} @ ${entry.toFixed(2)} | Size: ${qty.toFixed(4)}`));
            } catch (e) { console.error(e.message); }
        }
    }
}

// --- 🧠 GEMINI BRAIN ---
class GeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { console.error("Missing GEMINI_API_KEY"); process.exit(1); }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(ctx) {
        // Prompt engineered for Regime Classification
        const prompt = `
        Act as an Institutional Algorithmic Scalper.
        
        MARKET CONTEXT:
        - Current Price: ${ctx.price}
        - Regime Indicators: Chop=${ctx.chop} (Low=Trend, High=Range), LinReg Slope=${ctx.trend_angle}, R2=${ctx.trend_quality}
        - Momentum: RSI=${ctx.rsi}, MFI=${ctx.mfi}
        - Volatility: Squeeze Active? ${ctx.squeeze ? 'YES (Explosion Imminent)' : 'NO'}
        - Structure: MTF Trend=${ctx.trend_mtf}, FVG=${ctx.fvg ? ctx.fvg.type + ' at ' + ctx.fvg.price : 'NONE'}
        - Order Flow: Walls=${JSON.stringify(ctx.walls)}

        INSTRUCTIONS:
        1. **Determine Regime:**
           - MOMENTUM: Chop < 40, R2 > 0.3. Strategy: Follow MTF Trend. Breakouts.
           - MEAN REVERSION: Chop > 60, RSI Extreme. Strategy: Fade Moves.
           - NOISE: Chop 40-60, Low R2. Strategy: HOLD.
        2. **Entry Logic:** Use FVG or Wall levels for precision.
        3. **Safety:** Do not Buy if RSI > 70 unless Squeeze Breakout. Do not Sell if RSI < 30 unless Squeeze Breakdown.

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json/g, '').replace(/```/g, '').trim();
            return JSON.parse(text);
        } catch (e) {
            return { action: "HOLD", confidence: 0, reason: "AI Error" };
        }
    }
}

// --- 🔄 MAIN LOOP ---
const dp = new DataProvider();
const ex = new PaperExchange();
const ai = new GeminiBrain();
const logger = {
    box: (title, lines) => {
        console.log(NEON.GRAY('─'.repeat(60)));
        console.log(chalk.bgHex('#222')(NEON.PURPLE.bold(` ${title} `.padEnd(60))));
        lines.forEach(l => console.log(l));
        console.log(NEON.GRAY('─'.repeat(60)));
    }
};

async function tick() {
    const d = await dp.fetchAll();
    if (!d) { await setTimeout(5000); return tick(); }

    // Extract Arrays
    const closes = d.candles.map(c => c.c);
    const highs = d.candles.map(c => c.h);
    const lows = d.candles.map(c => c.l);
    const volumes = d.candles.map(c => c.v);
    const mtfCloses = d.candlesMTF.map(c => c.c);

    // 1. Calculate Indicators
    const rsi = TA.rsi(closes, config.indicators.rsi);
    const mfi = TA.mfi(highs, lows, closes, volumes, config.indicators.mfi);
    const chop = TA.chop(highs, lows, closes, config.indicators.chop_period);
    const reg = TA.linReg(closes, config.indicators.linreg_period);
    const bb = TA.bollinger(closes, config.indicators.bb_period, config.indicators.bb_std);
    const kc = TA.keltner(highs, lows, closes, config.indicators.kc_period, config.indicators.kc_mult);
    const fvg = TA.findFVG(d.candles);
    
    // MTF Trend (Simple SMA slope on 15m)
    const mtfSma = TA.sma(mtfCloses, 20);
    const trendMTF = mtfCloses[mtfCloses.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";

    // 2. Advanced Logic Analysis
    const last = closes.length - 1;
    const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);

    // 3. Whale Wall Detection
    const avgBid = d.bids.reduce((s, b) => s + b.q, 0) / d.bids.length;
    const avgAsk = d.asks.reduce((s, a) => s + a.q, 0) / d.asks.length;
    const wallThresh = config.orderbook.wall_threshold;
    const buyWall = d.bids.find(b => b.q > avgBid * wallThresh);
    const sellWall = d.asks.find(a => a.q > avgAsk * wallThresh);

    // 4. Construct Context
    const ctx = {
        symbol: config.symbol,
        price: d.price,
        rsi: rsi[last].toFixed(2),
        mfi: mfi[last].toFixed(2),
        chop: chop[last].toFixed(2),
        trend_angle: reg.slope[last].toFixed(4),
        trend_quality: reg.r2[last].toFixed(2),
        trend_mtf: trendMTF,
        squeeze: isSqueeze,
        fvg: fvg,
        walls: {
            buy: buyWall ? buyWall.p : null,
            sell: sellWall ? sellWall.p : null
        }
    };

    // 5. Display & Execute
    console.clear();
    const regime = ctx.chop > 60 ? NEON.BLUE("MEAN REVERSION") : ctx.chop < 40 ? NEON.GREEN("MOMENTUM") : NEON.GRAY("NOISE/CHOP");
    const sqzTxt = isSqueeze ? NEON.RED("🔥 ACTIVE") : NEON.GRAY("Inactive");
    
    logger.box(`WHALEWAVE TITAN | ${d.price}`, [
        `Regime: ${regime} | MTF: ${trendMTF === 'BULLISH' ? NEON.GREEN(trendMTF) : NEON.RED(trendMTF)}`,
        `MFI: ${ctx.mfi} | RSI: ${ctx.rsi} | Chop: ${ctx.chop}`,
        `Slope: ${ctx.trend_angle} | R²: ${ctx.trend_quality} | Squeeze: ${sqzTxt}`,
        `FVG: ${fvg ? NEON.YELLOW(fvg.type + ' @ ' + fvg.price.toFixed(2)) : 'None'}`,
        `Walls: Buy[${buyWall ? NEON.GREEN(buyWall.p) : '--'}] Sell[${sellWall ? NEON.RED(sellWall.p) : '--'}]`
    ]);

    const sig = await ai.analyze(ctx);
    
    // AI Safety Override check
    if (sig.action === 'BUY' && typeof sig.entry === 'number') {
        // Ensure we aren't buying right into a sell wall
        if (sellWall && sig.entry > sellWall.p) console.log(NEON.ORANGE("⚠️ AI WARNING: Buying above Sell Wall."));
    }

    const col = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
    console.log(`SIGNAL: ${col(sig.action)} (${(sig.confidence * 100).toFixed(0)}%)`);
    console.log(chalk.dim(sig.reason));

    ex.evaluate(d.price, sig);
    
    if(ex.pos) {
        const curPnl = ex.pos.side==='BUY' ? new Decimal(d.price).sub(ex.pos.entry) : ex.pos.entry.sub(new Decimal(d.price));
        const pnlVal = curPnl.mul(ex.pos.qty);
        console.log(`${NEON.BLUE('POS:')} ${ex.pos.side} @ ${ex.pos.entry.toFixed(2)} | PnL: ${pnlVal.gte(0)?NEON.GREEN(pnlVal.toFixed(2)):NEON.RED(pnlVal.toFixed(2))}`);
    } else {
        console.log(`Balance: $${ex.balance.toFixed(2)}`);
    }

    await setTimeout(config.loop_delay * 1000);
    tick();
}

console.log(NEON.YELLOW("Booting Titan Engine..."));
tick();
