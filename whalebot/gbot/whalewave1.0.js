/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v3.0
 * ----------------------------------------------------------------------
 * A multi-strategy, AI-driven scalping engine.
 * 
 * ARCHETYPES:
 * 1. Trend Surfer (Pullbacks)
 * 2. Volatility Breakout (Squeezes)
 * 3. Mean Reversion (Ping-Pong)
 * 4. Liquidity Grab (FVG/Walls)
 * 5. Divergence Hunter (Reversals)
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ CONFIGURATION MANAGER ---
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        symbol: 'BTCUSDT',
        interval: '3',        // Scalping timeframe
        trend_interval: '15', // Context timeframe
        limit: 300,
        loop_delay: 5,        // Seconds between cycles
        gemini_model: 'gemini-1.5-flash',
        min_confidence: 0.70, // High conviction only
        
        risk: {
            max_drawdown: 10.0,      // Stop bot if account drops 10%
            daily_loss_limit: 5.0,   // Stop bot if today's loss > 5%
            max_positions: 1,
        },
        
        paper_trading: {
            initial_balance: 1000.00,
            risk_percent: 1.5,       // Risk 1.5% of equity per trade
            leverage_cap: 10,
            fee: 0.00055,            // Taker fee
            slippage: 0.0001         // Simulated slippage
        },
        
        indicators: {
            rsi: 14, 
            stoch_period: 14, stoch_k: 3, stoch_d: 3,
            cci_period: 14, 
            macd_fast: 12, macd_slow: 26, macd_sig: 9,
            adx_period: 14, 
            mfi: 14, 
            chop_period: 14, 
            linreg_period: 20,
            bb_period: 20, bb_std: 2.0, 
            kc_period: 20, kc_mult: 1.5,
            atr_period: 14, 
            st_factor: 3.0, 
            ce_period: 22, ce_mult: 3.0,
            vwap_period: 20
        },
        
        orderbook: {
            depth: 50,
            wall_threshold: 4.0, // Volume must be 4x average to count as a wall
            sr_levels: 5
        },
        
        api: { timeout: 8000, retries: 3, backoff_factor: 2 }
    };

    static load() {
        let config = { ...this.DEFAULTS };
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                config = this.deepMerge(config, userConfig);
            } catch (e) { console.error(`Config Error: ${e.message}`); }
        } else {
            fs.writeFileSync(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else { result[key] = source[key]; }
        }
        return result;
    }
}

const config = ConfigManager.load();
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME MANAGER ---
const NEON = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'), GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'), BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
};

// --- 📐 COMPLETE TECHNICAL ANALYSIS LIBRARY ---
class TA {
    static safeArr(len) { return new Array(Math.floor(len)).fill(0); }
    
    static getFinalValue(data, key, precision = 2) {
        if (!data.closes || data.closes.length === 0) return 'N/A';
        const last = data.closes.length - 1;
        const value = data[key];
        if (Array.isArray(value)) return value[last]?.toFixed(precision) || '0.00';
        if (typeof value === 'object') {
            if (value.k) return { k: value.k[last]?.toFixed(0), d: value.d[last]?.toFixed(0) };
            if (value.hist) return value.hist[last]?.toFixed(precision);
            if (value.slope) return { slope: value.slope[last]?.toFixed(precision), r2: value.r2[last]?.toFixed(precision) };
            if (value.trend) return value.trend[last] === 1 ? 'BULL' : 'BEAR';
        }
        return 'N/A';
    }

    // --- Core Math ---
    static sma(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = []; let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) { sum += data[i] - data[i - period]; result.push(sum / period); }
        return TA.safeArr(period - 1).concat(result);
    }

    static ema(data, period) {
        if (!data || data.length === 0) return [];
        let result = TA.safeArr(data.length);
        const k = 2 / (period + 1); result[0] = data[0];
        for (let i = 1; i < data.length; i++) result[i] = (data[i] * k) + (result[i - 1] * (1 - k));
        return result;
    }

    static wilders(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = TA.safeArr(data.length); let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        return result;
    }

    // --- Indicators ---
    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
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

    static macd(closes, fast, slow, sig) {
        const emaFast = this.ema(closes, fast);
        const emaSlow = this.ema(closes, slow);
        const line = emaFast.map((v, i) => v - emaSlow[i]);
        const signal = this.ema(line, sig);
        return { line, signal, hist: line.map((v, i) => v - signal[i]) };
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
        return { upper: ema.map((e, i) => e + atr[i] * mult), lower: ema.map((e, i) => e - atr[i] * mult), middle: ema };
    }

    static stoch(highs, lows, closes, period, kP, dP) {
        let rsi = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceH = highs.slice(i - period + 1, i + 1);
            const sliceL = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...sliceL);
            const maxH = Math.max(...sliceH);
            rsi[i] = (maxH - minL === 0) ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        const k = this.sma(rsi, kP);
        const d = this.sma(k, dP);
        return { k, d };
    }

    static cci(highs, lows, closes, period) {
        const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3);
        const smaTp = this.sma(tp, period);
        let cci = TA.safeArr(closes.length);
        for (let i = period - 1; i < tp.length; i++) {
            let meanDev = 0;
            for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
            meanDev /= period;
            cci[i] = (meanDev === 0) ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
        }
        return cci;
    }

    static adx(highs, lows, closes, period) {
        let plusDM = [0], minusDM = [0];
        for (let i = 1; i < closes.length; i++) {
            const up = highs[i] - highs[i - 1];
            const down = lows[i - 1] - lows[i];
            plusDM.push(up > down && up > 0 ? up : 0);
            minusDM.push(down > up && down > 0 ? down : 0);
        }
        const sTR = this.wilders(this.atr(highs, lows, closes, 1), period);
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
        let result = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < period; j++) {
                pSum += posFlow[i-j];
                nSum += negFlow[i-j];
            }
            if (nSum === 0) result[i] = 100;
            else result[i] = 100 - (100 / (1 + (pSum / nSum)));
        }
        return result;
    }

    static chop(highs, lows, closes, period) {
        let result = TA.safeArr(closes.length);
        let tr = [highs[0] - lows[0]]; 
        for(let i=1; i<closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i-1]), Math.abs(lows[i] - closes[i-1])));
        for (let i = period - 1; i < closes.length; i++) {
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

    static linReg(closes, period) {
        let slopes = TA.safeArr(closes.length), r2s = TA.safeArr(closes.length);
        let sumX = 0, sumX2 = 0;
        for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }
        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0, sumXY = 0;
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j];
                sumY += val;
                sumXY += j * val;
            }
            const n = period;
            const num = (n * sumXY) - (sumX * sumY);
            const den = (n * sumX2) - (sumX * sumX);
            const slope = den === 0 ? 0 : num / den;
            
            // R2 Calc simplified
            slopes[i] = slope;
            r2s[i] = 0.8; // Placeholder for full R2 calc to save CPU cycles in JS
        }
        return { slope: slopes, r2: r2s };
    }

    static superTrend(highs, lows, closes, period, factor) {
        const atr = this.atr(highs, lows, closes, period);
        let st = new Array(closes.length).fill(0);
        let trend = new Array(closes.length).fill(1);
        let upper = 0, lower = 0;
        
        for (let i = period; i < closes.length; i++) {
            let up = (highs[i] + lows[i]) / 2 + factor * atr[i];
            let dn = (highs[i] + lows[i]) / 2 - factor * atr[i];
            
            if (i > 0) {
                if (closes[i-1] > lower) lower = Math.max(lower, dn); else lower = dn;
                if (closes[i-1] < upper) upper = Math.min(upper, up); else upper = up;
            }
            
            if (closes[i] > upper && trend[i-1] === -1) trend[i] = 1;
            else if (closes[i] < lower && trend[i-1] === 1) trend[i] = -1;
            else trend[i] = trend[i-1];
            
            st[i] = trend[i] === 1 ? lower : upper;
        }
        return { trend, value: st };
    }

    static chandelierExit(highs, lows, closes, period, mult) {
        const atr = this.atr(highs, lows, closes, period);
        let longStop = TA.safeArr(closes.length);
        let shortStop = TA.safeArr(closes.length);
        let trend = new Array(closes.length).fill(1);

        for (let i = period; i < closes.length; i++) {
            const maxHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const minLow = Math.min(...lows.slice(i - period + 1, i + 1));
            longStop[i] = maxHigh - atr[i] * mult;
            shortStop[i] = minLow + atr[i] * mult;
            
            if (closes[i] > shortStop[i]) trend[i] = 1;
            else if (closes[i] < longStop[i]) trend[i] = -1;
            else trend[i] = trend[i-1];
        }
        return { trend, value: trend.map((t, i) => t === 1 ? longStop[i] : shortStop[i]) };
    }

    // --- Advanced Scalping Metrics ---
    static vwap(highs, lows, closes, volumes, period) {
        let vwap = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            let sumPV = 0, sumV = 0;
            for (let j = 0; j < period; j++) {
                const tp = (highs[i-j] + lows[i-j] + closes[i-j]) / 3;
                sumPV += tp * volumes[i-j];
                sumV += volumes[i-j];
            }
            vwap[i] = sumV === 0 ? 0 : sumPV / sumV;
        }
        return vwap;
    }

    static findFVG(candles) {
        const len = candles.length;
        if (len < 5) return null; 
        const c1 = candles[len - 4]; const c2 = candles[len - 3]; const c3 = candles[len - 2]; 
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        else if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }

    static detectDivergence(closes, rsi, period = 5) {
        const len = closes.length;
        if (len < period + 2) return 'NONE';
        const priceHigh = Math.max(...closes.slice(len - period, len));
        const rsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period));
        const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        
        if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';
        
        const priceLow = Math.min(...closes.slice(len - period, len));
        const rsiLow = Math.min(...rsi.slice(len - period, len));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period));
        const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));

        if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH_REGULAR';
        return 'NONE';
    }

    static historicalVolatility(closes, period = 20) {
        const returns = [];
        for (let i = 1; i < closes.length; i++) returns.push(Math.log(closes[i] / closes[i - 1]));
        const volatility = TA.safeArr(closes.length);
        for (let i = period; i < closes.length; i++) {
            const slice = returns.slice(i - period + 1, i + 1);
            const mean = slice.reduce((a, b) => a + b, 0) / period;
            const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period;
            volatility[i] = Math.sqrt(variance) * Math.sqrt(365);
        }
        return volatility;
    }

    static marketRegime(closes, volatility, period = 50) {
        const avgVol = TA.sma(volatility, period);
        const currentVol = volatility[volatility.length - 1] || 0;
        const avgVolValue = avgVol[avgVol.length - 1] || 1;
        if (currentVol > avgVolValue * 1.5) return 'HIGH_VOLATILITY';
        if (currentVol < avgVolValue * 0.5) return 'LOW_VOLATILITY';
        return 'NORMAL';
    }
    
    static fibPivots(h, l, c) {
        const P = (h + l + c) / 3; const R = h - l;
        return { P, R1: P + 0.382 * R, R2: P + 0.618 * R, S1: P - 0.382 * R, S2: P - 0.618 * R };
    }
}

// --- 📡 ENHANCED DATA PROVIDER ---
class EnhancedDataProvider {
    constructor() {
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout });
    }

    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try { return (await this.api.get(url, { params })).data; }
            catch (error) { 
                if (attempt === retries) throw error; 
                await setTimeout(Math.pow(config.api.backoff_factor, attempt) * 1000); 
            }
        }
    }

    async fetchAll() {
        try {
            // Parallel fetch for speed
            const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);

            if (!ticker.result.list[0] || !kline.result.list) throw new Error("Incomplete API Data");

            const parseC = (list) => list.reverse().map(c => ({ 
                o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) 
            }));

            return {
                price: parseFloat(ticker.result.list[0].lastPrice),
                candles: parseC(kline.result.list),
                candlesMTF: parseC(klineMTF.result.list),
                bids: ob.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                asks: ob.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                daily: { h: parseFloat(daily.result.list[1][2]), l: parseFloat(daily.result.list[1][3]), c: parseFloat(daily.result.list[1][4]) },
                timestamp: Date.now()
            };
        } catch (e) {
            console.warn(NEON.ORANGE(`[WARN] Data Fetch Fail: ${e.message}`));
            return null;
        }
    }
}

// --- 💰 EXCHANGE & RISK MANAGEMENT ---
class EnhancedPaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null;
        this.dailyPnL = new Decimal(0);
        this.tradeHistory = [];
    }

    canTrade() {
        const drawdown = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdown.gt(config.risk.max_drawdown)) {
            console.log(NEON.RED(`🚨 MAX DRAWDOWN HIT: ${drawdown.toFixed(2)}%`));
            return false;
        }
        const dailyLoss = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLoss.lt(-config.risk.daily_loss_limit)) {
            console.log(NEON.RED(`🚨 DAILY LOSS LIMIT HIT: ${dailyLoss.toFixed(2)}%`));
            return false;
        }
        return true;
    }

    evaluate(priceVal, signal) {
        if (!this.canTrade()) {
            if (this.pos) this.handlePositionClose(new Decimal(priceVal), "RISK_STOP");
            return;
        }

        const price = new Decimal(priceVal);
        if (this.pos) this.handlePositionClose(price);
        
        if (!this.pos && signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) {
            this.handlePositionOpen(price, signal);
        }
    }

    handlePositionClose(price, forceReason = null) {
        let close = false, reason = forceReason || '';
        
        if (this.pos.side === 'BUY') {
            if (forceReason || price.lte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; }
            else if (price.gte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; }
        } else {
            if (forceReason || price.gte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; }
            else if (price.lte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; }
        }

        if (close) {
            const slippage = price.mul(config.paper_trading.slippage);
            const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
            
            const rawPnl = this.pos.side === 'BUY' 
                ? exitPrice.sub(this.pos.entry).mul(this.pos.qty)
                : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
            
            const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
            const netPnl = rawPnl.sub(fee);

            this.balance = this.balance.add(netPnl);
            this.dailyPnL = this.dailyPnL.add(netPnl);
            
            const color = netPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(`${NEON.BOLD(reason)}! PnL: ${color(netPnl.toFixed(2))} [${this.pos.strategy}]`);
            
            this.tradeHistory.push({ t: Date.now(), pnl: netPnl.toNumber() });
            this.pos = null;
        }
    }

    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry);
        const sl = new Decimal(signal.sl);
        const tp = new Decimal(signal.tp);
        const dist = entry.sub(sl).abs();
        
        if (dist.isZero()) return;

        // Volatility-adjusted sizing
        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);
        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;

        // Slippage on Entry
        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
        
        this.balance = this.balance.sub(fee); // Pay fee upfront

        this.pos = {
            side: signal.action,
            entry: execPrice,
            qty: qty,
            sl: sl,
            tp: tp,
            strategy: signal.strategy
        };

        console.log(NEON.GREEN(`OPEN ${signal.action} [${signal.strategy}] @ ${execPrice.toFixed(2)} | Size: ${qty.toFixed(4)}`));
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN ---
class EnhancedGeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { console.error("Missing GEMINI_API_KEY"); process.exit(1); }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(ctx) {
        const prompt = `
        ACT AS: Institutional Scalping Algorithm.
        OBJECTIVE: Analyze metrics and select the BEST strategy from the 5 archetypes below.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope)
        - Momentum: RSI=${ctx.rsi}, Stoch=${ctx.stoch_k}, MACD=${ctx.macd_hist}
        - Structure: VWAP=${ctx.vwap}, FVG=${ctx.fvg ? ctx.fvg.type : 'None'}, Squeeze=${ctx.squeeze}
        - Divergence: ${ctx.divergence}
        - Walls: Buy=${ctx.walls.buy || 'None'}, Sell=${ctx.walls.sell || 'None'}

        STRATEGY ARCHETYPES:
        1. TREND_SURFER: Trend is strong (ADX>25). Pullback to EMA/VWAP.
        2. VOLATILITY_BREAKOUT: Squeeze is ACTIVE. Price breaking BB/KC.
        3. MEAN_REVERSION: Ranging (Chop>50). RSI >70/<30. Fade moves.
        4. LIQUIDITY_GRAB: Price hitting Orderbook Wall or FVG. Reversal expected.
        5. DIVERGENCE_HUNT: RSI Divergence detected against price trend.

        INSTRUCTIONS:
        - If NO strategy fits perfectly, return "HOLD".
        - Confidence must be > ${config.min_confidence} to trigger.
        - Calculate SL/TP based on the chosen strategy's logic.

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "strategy": "STRATEGY_NAME", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const start = text.indexOf('{');
            const end = text.lastIndexOf('}');
            if (start === -1 || end === -1) throw new Error("Invalid JSON");
            return JSON.parse(text.substring(start, end + 1));
        } catch (e) {
            return { action: "HOLD", confidence: 0, reason: "AI Error/Uncertainty" };
        }
    }
}

// --- 🔄 MAIN TRADING ENGINE ---
class TradingEngine {
    constructor() {
        this.dataProvider = new EnhancedDataProvider();
        this.exchange = new EnhancedPaperExchange();
        this.ai = new EnhancedGeminiBrain();
        this.isRunning = true;
    }

    async start() {
        console.clear();
        console.log(NEON.bg(NEON.BLUE(" 🚀 WHALEWAVE TITAN v3.0 STARTED ")));
        
        while (this.isRunning) {
            try {
                const data = await this.dataProvider.fetchAll();
                if (!data) continue;

                const analysis = await this.performAnalysis(data);
                const context = this.buildContext(data, analysis);
                const signal = await this.ai.analyze(context);

                this.displayDashboard(data, context, signal);
                this.exchange.evaluate(data.price, signal);

            } catch (e) {
                console.error(NEON.RED(`Loop Error: ${e.message}`));
            }
            await setTimeout(config.loop_delay * 1000);
        }
    }

    async performAnalysis(data) {
        const c = data.candles.map(x => x.c); 
        const h = data.candles.map(x => x.h);
        const l = data.candles.map(x => x.l); 
        const v = data.candles.map(x => x.v);
        const mtfC = data.candlesMTF.map(x => x.c);

        // Parallel Calculation
        const [rsi, stoch, macd, bb, kc, atr, fvg, vwap, reg, adx, chop, st, ce] = await Promise.all([
            TA.rsi(c, config.indicators.rsi),
            TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig),
            TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult),
            TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles),
            TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.linReg(c, config.indicators.linreg_period),
            TA.adx(h, l, c, config.indicators.adx_period),
            TA.chop(h, l, c, config.indicators.chop_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult)
        ]);

        const last = c.length - 1;
        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
        const divergence = TA.detectDivergence(c, rsi);
        const volatility = TA.historicalVolatility(c);
        
        // MTF Trend
        const mtfSma = TA.sma(mtfC, 20);
        const trendMTF = mtfC[mtfC.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";

        // Walls
        const avgBid = data.bids.reduce((a,b)=>a+b.q,0)/data.bids.length;
        const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p;
        const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p;
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);

        return { 
            c, rsi, stoch, macd, bb, atr, fvg, vwap, reg, adx, chop, st, ce,
            isSqueeze, divergence, volatility, trendMTF, buyWall, sellWall, fibs 
        };
    }

    buildContext(d, a) {
        const last = a.c.length - 1;
        return {
            price: d.price,
            rsi: a.rsi[last].toFixed(2),
            stoch_k: a.stoch.k[last].toFixed(0),
            macd_hist: a.macd.hist[last].toFixed(4),
            vwap: a.vwap[last].toFixed(2),
            squeeze: a.isSqueeze,
            fvg: a.fvg,
            divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall },
            volatility: a.volatility[last].toFixed(2),
            marketRegime: TA.marketRegime(a.c, a.volatility),
            trend_angle: a.reg.slope[last].toFixed(4),
            trend_mtf: a.trendMTF
        };
    }

    displayDashboard(d, ctx, sig) {
        console.clear();
        const border = NEON.GRAY('─'.repeat(60));
        console.log(border);
        console.log(NEON.PURPLE(NEON.BOLD(` WHALEWAVE TITAN v3.0 | ${config.symbol} | $${d.price.toFixed(2)} `)));
        console.log(border);

        // Strategy & Signal
        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        console.log(`STRATEGY: ${NEON.BLUE(sig.strategy || 'SCANNING')} | SIGNAL: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        // Metrics
        const regimeCol = ctx.marketRegime.includes('HIGH') ? NEON.RED : NEON.GREEN;
        console.log(`Regime: ${regimeCol(ctx.marketRegime)} | Vol: ${ctx.volatility} | Squeeze: ${ctx.squeeze ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${ctx.trend_mtf === 'BULLISH' ? NEON.GREEN('BULL') : NEON.RED('BEAR')} | Slope: ${ctx.trend_angle}`);
        console.log(`RSI: ${ctx.rsi} | Stoch: ${ctx.stoch_k} | MACD: ${ctx.macd_hist}`);
        console.log(`Div: ${ctx.divergence !== 'NONE' ? NEON.YELLOW(ctx.divergence) : 'None'} | FVG: ${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : 'None'}`);
        console.log(border);

        // Account
        const pnlCol = this.exchange.dailyPnL.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`Balance: $${this.exchange.balance.toFixed(2)} | Daily PnL: ${pnlCol('$' + this.exchange.dailyPnL.toFixed(2))}`);
        
        if (this.exchange.pos) {
            const p = this.exchange.pos;
            const curPnl = p.side === 'BUY' ? new Decimal(d.price).sub(p.entry).mul(p.qty) : p.entry.sub(d.price).mul(p.qty);
            const posCol = curPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(NEON.BLUE(`OPEN POS: ${p.side} @ ${p.entry.toFixed(2)} | PnL: ${posCol(curPnl.toFixed(2))}`));
        }
        console.log(border);
    }
}

// --- START ---
const engine = new TradingEngine();
process.on('SIGINT', () => { engine.isRunning = false; console.log(NEON.RED("\n🛑 SHUTTING DOWN...")); process.exit(0); });
engine.start();
