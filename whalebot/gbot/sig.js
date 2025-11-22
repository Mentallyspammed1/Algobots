/**
 * 🌊 WHALEWAVE PRO (Stable Edition - Pyrmethus Reforged)
 * -----------------------------------------------------
 * - Fixed AI Error: Added strict numeric validation for entry/sl/tp.
 * - Defensive Math: PaperExchange now catches undefined values before crashing.
 * - Robust Parsing: AI output is sanitized before JSON parsing.
 * - Model: Uses stable 'gemini-1.5-flash'.
 * - Enhanced: Added Orderbook analysis for better context.
 * - Enhanced: Implemented VWAP and Fibonacci Pivots.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// Precision setup
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 NEON THEME ---
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

// --- CONFIGURATION ---
const CONFIG_FILE = 'config.json';
const DEFAULTS = {
    symbol: 'BTCUSDT',
    interval: '15',
    limit: 300,
    loop_delay: 15,
    gemini_model: 'gemini-1.5-flash',
    min_confidence: 0.70,
    max_drawdown_stop: 0.15,
    paper_trading: {
        initial_balance: 1000.00,
        risk_percent: 1.0,
        leverage_cap: 10,
        slippage: 0.0002,
        fee: 0.00055
    },
    indicators: {
        rsi: 14,
        stoch_period: 14, stoch_k: 3, stoch_d: 3,
        cci_period: 20,
        bb_period: 20, bb_std: 2.0,
        macd_fast: 12, macd_slow: 26, macd_sig: 9,
        adx_period: 14,
        ehlers_period: 10, ehlers_mult: 3.0,
        vwap_period: 20 // VWAP period for smoothing/context
    },
    orderbook: {
      depth: 50,
      imbalance_threshold: 0.05,
      support_resistance_levels: 5
    }
};

// Load Config
let config = DEFAULTS;
if (fs.existsSync(CONFIG_FILE)) {
    try {
        const userConfig = JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
        config = { ...DEFAULTS, ...userConfig, indicators: { ...DEFAULTS.indicators, ...userConfig.indicators } };
    } catch (e) {
        console.error(NEON.RED("Config Error: Using defaults."));
    }
} else {
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(DEFAULTS, null, 2));
}

// --- LOGGING UTILS ---
const logger = {
    info: (msg) => console.log(NEON.BLUE(`[INFO] `) + chalk.white(msg)),
    success: (msg) => console.log(NEON.GREEN(`[OK] `) + chalk.white(msg)),
    warn: (msg) => console.log(NEON.ORANGE(`[WARN] `) + chalk.white(msg)),
    error: (msg) => console.log(NEON.RED(`[ERR] `) + chalk.white(msg)),
    box: (title, lines) => {
        const len = 60;
        const border = NEON.GRAY('─'.repeat(len));
        console.log(border);
        console.log(chalk.bgHex('#222')(NEON.PURPLE.bold(` ${title} `.padEnd(len))));
        console.log(border);
        lines.forEach(l => console.log(chalk.hex('#DDD')(` ${l}`)));
        console.log(border);
    }
};

// --- TA LIBRARY ---
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

    static stochRsi(closes, rsiP, kP, dP) {
        const rsi = this.rsi(closes, rsiP);
        let stochRsi = [];
        for (let i = 0; i < rsi.length; i++) {
            if (i < rsiP) { stochRsi.push(0); continue; }
            const slice = rsi.slice(i - rsiP + 1, i + 1);
            const min = Math.min(...slice);
            const max = Math.max(...slice);
            stochRsi.push(max - min === 0 ? 0 : (rsi[i] - min) / (max - min));
        }
        const k = this.sma(stochRsi.map(x => x * 100), kP);
        const d = this.sma(k, dP);
        return { k, d };
    }

    static cci(highs, lows, closes, period) {
        const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3);
        const smaTp = this.sma(tp, period);
        let cci = [];
        for (let i = 0; i < tp.length; i++) {
            if (i < period) { cci.push(0); continue; }
            let meanDev = 0;
            for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
            meanDev /= period;
            cci.push(meanDev === 0 ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev));
        }
        return cci;
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

    static macd(closes, fast, slow, sig) {
        const emaFast = this.ema(closes, fast);
        const emaSlow = this.ema(closes, slow);
        const line = emaFast.map((v, i) => v - emaSlow[i]);
        const signal = this.ema(line, sig);
        return { line, signal, hist: line.map((v, i) => v - signal[i]) };
    }

    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) {
            tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        }
        return this.wilders(tr, period);
    }

    static adx(highs, lows, closes, period) {
        let plusDM = [0], minusDM = [0], tr = [0];
        for (let i = 1; i < closes.length; i++) {
            const up = highs[i] - highs[i - 1];
            const down = lows[i - 1] - lows[i];
            plusDM.push(up > down && up > 0 ? up : 0);
            minusDM.push(down > up && down > 0 ? down : 0);
            tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        }
        const sTR = this.wilders(tr, period);
        const sPlus = this.wilders(plusDM, period);
        const sMinus = this.wilders(minusDM, period);
        let dx = [];
        for (let i = 0; i < closes.length; i++) {
            const pDI = sTR[i] === 0 ? 0 : (sPlus[i] / sTR[i]) * 100;
            const mDI = sTR[i] === 0 ? 0 : (sMinus[i] / sTR[i]) * 100;
            const sum = pDI + mDI;
            dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100);
        }
        return this.wilders(dx, period);
    }

    static superSmoother(data, period) {
        const a1 = Math.exp(-Math.SQRT2 * Math.PI / period);
        const b1 = 2 * a1 * Math.cos(Math.SQRT2 * Math.PI / period);
        const c2 = b1;
        const c3 = -a1 * a1;
        const c1 = 1 - c2 - c3;
        let filt = TA.safeArr(data.length);
        filt[0] = data[0] || 0;
        if (data.length > 1) filt[1] = data[1];
        for (let i = 2; i < data.length; i++) {
            filt[i] = c1 * (data[i] + data[i - 1]) / 2 + c2 * filt[i - 1] + c3 * filt[i - 2];
        }
        return filt;
    }

    static ehlersSuperTrend(highs, lows, closes, period, mult) {
        const hl2 = highs.map((h, i) => (h + lows[i]) / 2);
        const sPrice = this.superSmoother(hl2, period);
        let tr = [0];
        for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        const sATR = this.superSmoother(tr, period);
        let trend = new Array(closes.length).fill(1);
        let st = new Array(closes.length).fill(0);

        for (let i = 1; i < closes.length; i++) {
            const up = sPrice[i] + mult * sATR[i];
            const dn = sPrice[i] - mult * sATR[i];
            const prevT = trend[i - 1];
            const prevST = st[i - 1];

            if (prevT === 1) {
                if (closes[i] < Math.max(dn, prevST)) { trend[i] = -1; st[i] = up; }
                else { trend[i] = 1; st[i] = Math.max(dn, prevST); }
            } else {
                if (closes[i] > Math.min(up, prevST)) { trend[i] = 1; st[i] = dn; }
                else { trend[i] = -1; st[i] = Math.min(up, prevST); }
            }
        }
        return { trend, value: st };
    }

    static vwap(highs, lows, closes, volumes) {
        let vwap = [];
        let cumVol = 0;
        let cumVolPrice = 0;
        for(let i=0; i<closes.length; i++) {
            const typical = (highs[i] + lows[i] + closes[i]) / 3;
            const volPrice = typical * volumes[i];
            cumVol += volumes[i];
            cumVolPrice += volPrice;
            vwap.push(cumVol > 0 ? cumVolPrice / cumVol : 0);
        }
        return vwap;
    }

    static fibPivots(h, l, c) {
        const P = (h + l + c) / 3;
        const R = h - l;
        return {
            P,
            R1: P + 0.382 * R, R2: P + 0.618 * R, R3: P + R,
            S1: P - 0.382 * R, S2: P - 0.618 * R, S3: P - R
        };
    }
}

// --- MARKET DATA ---
class DataProvider {
    constructor() {
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: 10000 });
    }

    async fetchAll(symbol, interval, limit) {
        try {
            const [ticker, kline, ob, daily] = await Promise.all([
                this.api.get('/tickers', { params: { category: 'linear', symbol } }),
                this.api.get('/kline', { params: { category: 'linear', symbol, interval, limit } }),
                this.api.get('/orderbook', { params: { category: 'linear', symbol, limit: config.orderbook.depth } }),
                this.api.get('/kline', { params: { category: 'linear', symbol, interval: 'D', limit: 2 } })
            ]);

            const candles = kline.data.result.list.reverse().map(c => ({
                o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5])
            }));

            const bids = ob.data.result.b || []; // Safety fallback
            const asks = ob.data.result.a || []; // Safety fallback
            const bidVol = bids.reduce((a, b) => a + parseFloat(b[1]), 0);
            const askVol = asks.reduce((a, b) => a + parseFloat(b[1]), 0);

            const prevDay = daily.data.result.list[1];

            return {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                candles,
                rawBids: bids,
                rawAsks: asks,
                obImbalance: (bidVol - askVol) / (bidVol + askVol || 1),
                daily: {
                    h: parseFloat(prevDay[2]),
                    l: parseFloat(prevDay[3]),
                    c: parseFloat(prevDay[4])
                }
            };
        } catch (e) {
            logger.warn(`Data Fetch Warning: ${e.message}`);
            return null;
        }
    }
}

// --- PAPER EXCHANGE ---
class PaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.positions = new Map();
        this.pos = null; // Current active position for the symbol
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
                logger.warn(`${NEON.BOLD(reason)}! PnL: ${netPnl.gte(0) ? NEON.GREEN('$' + netPnl.toFixed(2)) : NEON.RED('$' + netPnl.toFixed(2))}`);
                return;
            }
        } else if (signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) {
            
            // --- 🛡️ SAFETY: CHECK FOR NUMERIC VALUES ---
            if (!signal.entry || !signal.sl || !signal.tp) {
                logger.warn("Signal ignored: AI returned incomplete trade data (missing Entry/SL/TP).");
                return;
            }

            try {
                const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
                
                // Calculate distance safely
                const dist = new Decimal(Math.abs(signal.entry - signal.sl));
                
                // Prevent division by zero
                if (dist.isZero()) {
                     logger.warn("Signal ignored: SL is same as Entry.");
                     return;
                }

                let qty = riskAmt.div(dist);
                const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
                if (qty.gt(maxQty)) qty = maxQty;
                
                // Minimum value check
                if (qty.mul(price).lt(10)) {
                    logger.warn("Signal ignored: Trade value too low (< $10).");
                    return;
                }

                const entryPrice = new Decimal(signal.entry);
                const fee = entryPrice.mul(qty).mul(config.paper_trading.fee);
                this.balance = this.balance.sub(fee);

                this.pos = {
                    side: signal.action,
                    entry: entryPrice,
                    qty: qty,
                    sl: new Decimal(signal.sl),
                    tp: new Decimal(signal.tp)
                };
                logger.success(`OPEN ${NEON.BOLD(signal.action)} @ ${entryPrice.toFixed(2)} | Size: ${qty.toFixed(4)}`);
            
            } catch (err) {
                logger.error(`Trade Execution Logic Failed: ${err.message}`);
            }
        }
    }
}

// --- AI BRAIN ---
class GeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { logger.error("Missing GEMINI_API_KEY"); process.exit(1); }

        const genAI = new GoogleGenerativeAI(key);
        this.model = genAI.getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(data) {
        const clean = (v) => (typeof v === 'number' && isFinite(v)) ? v : 0;

        const ctx = {
            symbol: config.symbol,
            price: clean(data.price),
            trend: data.ehlers_trend,
            rsi: clean(data.rsi).toFixed(2),
            stoch: `${clean(data.stoch_k).toFixed(0)}/${clean(data.stoch_d).toFixed(0)}`,
            adx: clean(data.adx).toFixed(2),
            macd_hist: clean(data.macd_hist).toFixed(4),
            ob_imbalance: clean(data.ob_imbalance).toFixed(2),
            atr: clean(data.atr).toFixed(4),
            vwap: clean(data.vwap).toFixed(4),
            supportLevels: data.supportLevels.map(l => clean(l).toFixed(2)),
            resistanceLevels: data.resistanceLevels.map(l => clean(l).toFixed(2)),
            fibs: { P: clean(data.fibs.P).toFixed(2), S1: clean(data.fibs.S1).toFixed(2), R1: clean(data.fibs.R1).toFixed(2) }
        };

        const prompt = `
        Act as an Institutional Crypto Scalper.
        Data: ${JSON.stringify(ctx)}

        Strategy:
        1. Trend Alignment: Only trade with Ehlers Trend.
        2. Momentum: RSI < 30 (Buy) / > 70 (Sell). Stoch crossing.
        3. Volume: High ADX (>20) supports trend trades.
        4. Structure: Use Fib levels, Support/Resistance, and VWAP for entry/exit context.
        5. Orderbook: Consider imbalance for confirmation.

        IMPORTANT: 
        - "entry", "sl", and "tp" MUST be valid numbers if action is BUY or SELL. 
        - Do not use strings for prices. Do not return null for prices in a trade.
        - If no valid setup, action is "HOLD".

        Output valid JSON only. No markdown code blocks.
        JSON Format: { "action": "BUY" | "SELL" | "HOLD", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const result = await this.model.generateContent(prompt);
            let text = result.response.text();
            text = text.replace(/```json/g, '').replace(/```/g, '').trim();
            
            const parsed = JSON.parse(text);

            // --- 🛡️ SAFETY: VALIDATE AI OUTPUT ---
            if (parsed.action !== 'HOLD') {
                if (
                    typeof parsed.entry !== 'number' || 
                    typeof parsed.sl !== 'number' || 
                    typeof parsed.tp !== 'number'
                ) {
                    logger.warn("AI Malformed Output: Missing numeric entry/sl/tp. Forcing HOLD.");
                    return { action: "HOLD", confidence: 0, reason: "AI Error: Invalid numeric data." };
                }
            }

            return parsed;
        } catch (e) {
            logger.error(`AI ERROR: ${e.message}`);
            return { action: "HOLD", confidence: 0, reason: `AI Fail` };
        }
    }
}

// --- MAIN LOOP ---
const dp = new DataProvider();
const ex = new PaperExchange();
const ai = new GeminiBrain();
let running = true;

const shutdown = () => {
    running = false;
    console.log('\n');
    logger.warn("🛑 SHUTDOWN INITIATED...");
    const pnl = ex.balance.sub(ex.startBal);
    const pnlColor = pnl.gte(0) ? NEON.GREEN : NEON.RED;
    logger.box("SESSION SUMMARY", [
        `Final Balance: $${ex.balance.toFixed(2)}`,
        `Total PnL:     ${pnlColor('$' + pnl.toFixed(2))}`,
        `Active Pos:    ${ex.pos ? 'YES' : 'NO'}`
    ]);
    process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

async function tick() {
    if (!running) return;
    const d = await dp.fetchAll(config.symbol, config.interval, config.limit);
    if (!d) { await setTimeout(5000); if(running) tick(); return; }

    const closes = d.candles.map(c => c.c);
    const highs = d.candles.map(c => c.h);
    const lows = d.candles.map(c => c.l);
    const volumes = d.candles.map(c => c.v);

    const rsi = TA.rsi(closes, config.indicators.rsi);
    const stoch = TA.stochRsi(closes, config.indicators.rsi, config.indicators.stoch_k, config.indicators.stoch_d);
    const cci = TA.cci(highs, lows, closes, config.indicators.cci_period);
    const bb = TA.bollinger(closes, config.indicators.bb_period, config.indicators.bb_std);
    const macd = TA.macd(closes, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig);
    const atr = TA.atr(highs, lows, closes, config.indicators.rsi); // Using RSI period for ATR for consistency
    const adx = TA.adx(highs, lows, closes, config.indicators.adx_period);
    const ehlers = TA.ehlersSuperTrend(highs, lows, closes, config.indicators.ehlers_period, config.indicators.ehlers_mult);
    const vwap = TA.vwap(highs, lows, closes, volumes);
    const fibs = TA.fibPivots(d.daily.h, d.daily.l, d.daily.c);

    const last = d.candles.length - 1;
    const currentClose = closes[last];
    const currentRSI = rsi[last];
    const currentStochK = stoch.k[last];
    const currentStochD = stoch.d[last];
    const currentADX = adx[last];
    const currentATR = atr[last];
    const currentMACDHist = macd.hist[last];
    const currentCCI = cci[last];
    const currentVWAP = vwap[last];
    const currentEhlersTrend = ehlers.trend[last] === 1 ? 'BULLISH' : 'BEARISH';
    const currentEhlersValue = ehlers.value[last];

    let bbPos = 0; // 0: outside, 1: above, -1: below
    if (currentClose > bb.upper[last]) bbPos = 1;
    else if (currentClose < bb.lower[last]) bbPos = -1;

    let volRatio = 1;
    if (volumes.length > 1) {
        const avgVol = TA.sma(volumes, config.indicators.vwap_period)[last];
        volRatio = avgVol > 0 ? volumes[last] / avgVol : 1;
    }

    // --- Orderbook Analysis ---
    // FIX: Added safety check (|| []) to prevent crash if bids/asks are undefined
    const bids = (d.rawBids || []).slice(0, config.orderbook.depth).map(b => ({ price: parseFloat(b[0]), qty: parseFloat(b[1]) }));
    const asks = (d.rawAsks || []).slice(0, config.orderbook.depth).map(a => ({ price: parseFloat(a[0]), qty: parseFloat(a[1]) }));

    const bidVolTotal = bids.reduce((sum, b) => sum + b.qty, 0);
    const askVolTotal = asks.reduce((sum, a) => sum + a.qty, 0);
    const obImbalance = (bidVolTotal - askVolTotal) / (bidVolTotal + askVolTotal || 1);

    let supportLevels = [];
    let resistanceLevels = [];
    let orderbookBias = 'NEUTRAL';
    let priceZone = 'NEUTRAL';

    if (bids.length > 0 && asks.length > 0) {
        const maxBidPrice = bids[0].price;
        const minAskPrice = asks[0].price;

        // Simple price zone detection
        if (currentClose > currentVWAP && currentClose > fibs.R1) priceZone = 'RESISTANCE';
        else if (currentClose < currentVWAP && currentClose < fibs.S1) priceZone = 'SUPPORT';
        else if (currentClose > currentVWAP && currentClose < fibs.R1 && currentClose > fibs.P) priceZone = 'UPPER_MID';
        else if (currentClose < currentVWAP && currentClose > fibs.S1 && currentClose < fibs.P) priceZone = 'LOWER_MID';
        else if (currentClose > currentVWAP) priceZone = 'ABOVE_VWAP';
        else if (currentClose < currentVWAP) priceZone = 'BELOW_VWAP';
        else priceZone = 'AT_VWAP';

        if (priceZone === 'SUPPORT' || priceZone === 'BELOW_VWAP') priceZone = 'SUPPORT';
        else if (priceZone === 'RESISTANCE' || priceZone === 'ABOVE_VWAP') priceZone = 'RESISTANCE';
        else if (priceZone === 'AT_VWAP') priceZone = 'CRITICAL';

        // Basic flow bias
        if (obImbalance > config.orderbook.imbalance_threshold) orderbookBias = 'BULLISH';
        else if (obImbalance < -config.orderbook.imbalance_threshold) orderbookBias = 'BEARISH';

        // Identify Support/Resistance levels (simplified)
        const pricePoints = [...bids.map(b => b.price), ...asks.map(a => a.price)];
        const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);

        let potentialSR = [];
        for (const price of uniquePrices) {
            let bidVolAtPrice = bids.filter(b => b.price === price).reduce((s, b) => s + b.qty, 0);
            let askVolAtPrice = asks.filter(a => a.price === price).reduce((s, a) => s + a.qty, 0);
            if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
            else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
        }
        potentialSR.sort((a, b) => a.price - b.price);

        // Find levels closest to current price
        const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));

        supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, config.orderbook.support_resistance_levels).map(p => p.price);
        resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, config.orderbook.support_resistance_levels).map(p => p.price);
    }
    // --- End Orderbook Analysis ---

    const analysisData = {
        price: d.price,
        rsi: currentRSI,
        stoch_k: currentStochK,
        stoch_d: currentStochD,
        adx: currentADX,
        atr: currentATR,
        macd_hist: currentMACDHist,
        cci: currentCCI,
        bb_pos: bbPos,
        ehlers_trend: currentEhlersTrend,
        ehlers_val: currentEhlersValue,
        ob_imbalance: obImbalance,
        vwap: currentVWAP,
        vol_ratio: volRatio,
        fibs: fibs,
        supportLevels: supportLevels,
        resistanceLevels: resistanceLevels,
        orderbookBias: orderbookBias,
        priceZone: priceZone
    };

    console.clear();
    const trendCol = analysisData.ehlers_trend === 'BULLISH' ? NEON.GREEN : NEON.RED;
    const volCol = analysisData.vol_ratio > 1.5 ? NEON.YELLOW : NEON.GRAY;
    const obCol = analysisData.orderbookBias === 'BULLISH' ? NEON.GREEN : analysisData.orderbookBias === 'BEARISH' ? NEON.RED : NEON.GRAY;
    const zoneCol = analysisData.priceZone === 'SUPPORT' ? NEON.GREEN : analysisData.priceZone === 'RESISTANCE' ? NEON.RED : analysisData.priceZone === 'CRITICAL' ? NEON.YELLOW : NEON.GRAY;

    logger.box(`WHALEWAVE | ${config.symbol} | ${d.price}`, [
        `Trend: ${trendCol(analysisData.ehlers_trend)} | RSI: ${analysisData.rsi.toFixed(1)} | ADX: ${analysisData.adx.toFixed(1)}`,
        `Stoch: ${analysisData.stoch_k.toFixed(0)}/${analysisData.stoch_d.toFixed(0)} | MACD: ${analysisData.macd_hist.toFixed(2)}`,
        `Vol Ratio: ${volCol(analysisData.vol_ratio.toFixed(1))} | OB Imbal: ${analysisData.ob_imbalance.toFixed(2)}`,
        `OB Flow: ${obCol(analysisData.orderbookBias)} | Zone: ${zoneCol(analysisData.priceZone)}`,
        `Support: ${analysisData.supportLevels.join(', ')}`,
        `Resistance: ${analysisData.resistanceLevels.join(', ')}`,
        `VWAP: ${analysisData.vwap.toFixed(4)}`
    ]);

    const sig = await ai.analyze(analysisData);
    const sigCol = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;

    console.log(`${NEON.PURPLE.bold('SIGNAL:')} ${sigCol(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
    console.log(chalk.dim(sig.reason));

    ex.evaluate(d.price, sig);
    if(ex.pos) {
        const curPnl = ex.pos.side==='BUY'
            ? new Decimal(d.price).sub(ex.pos.entry)
            : ex.pos.entry.sub(new Decimal(d.price));
        const pnlVal = curPnl.mul(ex.pos.qty);
        const pnlCol = pnlVal.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`${NEON.BLUE('POS:')} ${ex.pos.side} @ ${ex.pos.entry.toFixed(2)} | SL: ${ex.pos.sl.toFixed(2)} | TP: ${ex.pos.tp.toFixed(2)} | PnL: ${pnlCol(pnlVal.toFixed(2))}`);
    } else {
        console.log(NEON.GRAY("No active position."));
    }
    console.log(`Balance: $${ex.balance.toFixed(2)}`);

    await setTimeout(config.loop_delay * 1000);
    if (running) tick();
}

// Start
logger.info("Booting...");
tick();
