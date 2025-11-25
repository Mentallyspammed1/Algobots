/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v5.0 (Final Production-Ready Code)
 * ----------------------------------------------------------------------
 * - WSS 2.0: Deeply enhanced Weighted Scoring System with normalization and level checks.
 * - HYBRID MODEL: Quantitative (WSS) Pre-filter + Qualitative (Gemini) Strategy Selector.
 * - ARBITRARY PRECISION: All financial math uses decimal.js.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ ENHANCED CONFIGURATION MANAGER (WSS WEIGHTS UPDATED) ---
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        symbol: 'BTCUSDT',
        interval: '3',
        trend_interval: '15',
        limit: 300,
        loop_delay: 5,
        gemini_model: 'gemini-1.5-flash',
        min_confidence: 0.70, 
        
        risk: {
            max_drawdown: 10.0, daily_loss_limit: 5.0, max_positions: 1,
        },
        
        paper_trading: {
            initial_balance: 1000.00, risk_percent: 1.5, leverage_cap: 10,
            fee: 0.00055, slippage: 0.0001
        },
        
        indicators: {
            // Standard
            rsi: 14, stoch_period: 14, stoch_k: 3, stoch_d: 3, cci_period: 14, 
            macd_fast: 12, macd_slow: 26, macd_sig: 9, adx_period: 14,
            // Advanced
            mfi: 14, chop_period: 14, linreg_period: 20, vwap_period: 20,
            bb_period: 20, bb_std: 2.0, kc_period: 20, kc_mult: 1.5,
            atr_period: 14, st_factor: 3.0, ce_period: 22, ce_mult: 3.0,
            // WSS Weighting Configuration (ENHANCED)
            wss_weights: {
                trend_mtf_weight: 2.0, trend_scalp_weight: 1.0,
                momentum_normalized_weight: 1.5, macd_weight: 0.8,
                regime_weight: 0.7, squeeze_vol_weight: 0.5,
                liquidity_grab_weight: 1.2, divergence_weight: 1.8,
                volatility_weight: 0.4, action_threshold: 1.5 // Higher threshold for high conviction
            }
        },
        
        orderbook: { depth: 50, wall_threshold: 4.0, sr_levels: 5 },
        api: { timeout: 8000, retries: 3, backoff_factor: 2 }
    };

    static load() {
        let config = { ...this.DEFAULTS };
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                config = this.deepMerge(config, userConfig);
            } catch (e) { console.error(chalk.red(`Config Error: ${e.message}`)); }
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

    // --- Core Math (SMA, EMA, Wilder's) ---
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

    // --- Core Indicators (ATR, RSI, Stoch, MACD, ADX, MFI, CCI, Chop) ---
    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        return this.wilders(tr, period);
    }
    static rsi(closes, period) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0); losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);
        return closes.map((_, i) => avgLoss[i] === 0 ? 100 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
    }
    static stoch(highs, lows, closes, period, kP, dP) {
        let rsi = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceH = highs.slice(i - period + 1, i + 1); const sliceL = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...sliceL); const maxH = Math.max(...sliceH);
            rsi[i] = (maxH - minL === 0) ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        const k = this.sma(rsi, kP); const d = this.sma(k, dP); return { k, d };
    }
    static macd(closes, fast, slow, sig) {
        const emaFast = this.ema(closes, fast); const emaSlow = this.ema(closes, slow);
        const line = emaFast.map((v, i) => v - emaSlow[i]); const signal = this.ema(line, sig);
        return { line, signal, hist: line.map((v, i) => v - signal[i]) };
    }
    static adx(highs, lows, closes, period) {
        let plusDM = [0], minusDM = [0];
        for (let i = 1; i < closes.length; i++) {
            const up = highs[i] - highs[i - 1]; const down = lows[i - 1] - lows[i];
            plusDM.push(up > down && up > 0 ? up : 0); minusDM.push(down > up && down > 0 ? down : 0);
        }
        const sTR = this.wilders(this.atr(highs, lows, closes, 1), period);
        const sPlus = this.wilders(plusDM, period); const sMinus = this.wilders(minusDM, period);
        let dx = [];
        for (let i = 0; i < closes.length; i++) {
            const pDI = sTR[i] === 0 ? 0 : (sPlus[i] / sTR[i]) * 100; const mDI = sTR[i] === 0 ? 0 : (sMinus[i] / sTR[i]) * 100;
            const sum = pDI + mDI;
            dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100);
        }
        return this.wilders(dx, period);
    }
    static mfi(h,l,c,v,p) { 
        let posFlow = [], negFlow = [];
        for (let i = 0; i < c.length; i++) {
            if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
            const tp = (h[i] + l[i] + c[i]) / 3; const prevTp = (h[i-1] + l[i-1] + c[i-1]) / 3;
            const raw = tp * v[i];
            if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
            else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
            else { posFlow.push(0); negFlow.push(0); }
        }
        let result = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < p; j++) { pSum += posFlow[i-j]; nSum += negFlow[i-j]; }
            if (nSum === 0) result[i] = 100; else result[i] = 100 - (100 / (1 + (pSum / nSum)));
        }
        return result;
    }
    static chop(h, l, c, p) {
        let result = TA.safeArr(c.length);
        let tr = [h[0] - l[0]]; 
        for(let i=1; i<c.length; i++) tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i-1]), Math.abs(l[i] - c[i-1])));
        for (let i = p - 1; i < c.length; i++) {
            let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
            for (let j = 0; j < p; j++) {
                sumTr += tr[i - j];
                if (h[i - j] > maxHi) maxHi = h[i - j];
                if (l[i - j] < minLo) minLo = l[i - j];
            }
            const range = maxHi - minLo;
            result[i] = (range === 0 || sumTr === 0) ? 0 : 100 * (Math.log10(sumTr / range) / Math.log10(p));
        }
        return result;
    }
    static cci(highs, lows, closes, period) {
        const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3); const smaTp = this.sma(tp, period);
        let cci = TA.safeArr(closes.length);
        for (let i = period - 1; i < tp.length; i++) {
            let meanDev = 0; for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
            meanDev /= period;
            cci[i] = (meanDev === 0) ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
        }
        return cci;
    }
    
    // --- Advanced Indicators (BB/KC, ST, CE, LinReg, VWAP, FVG, Divergence, Volatility) ---
    static linReg(closes, period) {
        let slopes = TA.safeArr(closes.length), r2s = TA.safeArr(closes.length);
        let sumX = 0, sumX2 = 0;
        for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }
        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0, sumXY = 0;
            const ySlice = [];
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j]; ySlice.push(val); sumY += val; sumXY += j * val;
            }
            const n = period;
            const num = (n * sumXY) - (sumX * sumY);
            const den = (n * sumX2) - (sumX * sumX);
            const slope = den === 0 ? 0 : num / den;
            const intercept = (sumY - slope * sumX) / n;
            let ssTot = 0, ssRes = 0;
            const yMean = sumY / n;
            for(let j=0; j<period; j++) {
                const y = ySlice[j]; const yPred = slope * j + intercept;
                ssTot += Math.pow(y - yMean, 2); ssRes += Math.pow(y - yPred, 2);
            }
            slopes[i] = slope; r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
        }
        return { slope: slopes, r2: r2s };
    }
    static bollinger(closes, period, stdDev) {
        const sma = this.sma(closes, period);
        let upper = [], lower = [], middle = sma;
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) { upper.push(0); lower.push(0); continue; }
            let sumSq = 0;
            for (let j = 0; j < period; j++) sumSq += Math.pow(closes[i - j] - sma[i], 2);
            const std = Math.sqrt(sumSq / period);
            upper.push(sma[i] + (std * stdDev)); lower.push(sma[i] - (std * stdDev));
        }
        return { upper, middle, lower };
    }
    static keltner(highs, lows, closes, period, mult) {
        const ema = this.ema(closes, period); const atr = this.atr(highs, lows, closes, period);
        return { upper: ema.map((e, i) => e + atr[i] * mult), lower: ema.map((e, i) => e - atr[i] * mult), middle: ema };
    }
    static superTrend(highs, lows, closes, period, factor) {
        const atr = this.atr(highs, lows, closes, period);
        let st = new Array(closes.length).fill(0); let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            let up = (highs[i] + lows[i]) / 2 + factor * atr[i];
            let dn = (highs[i] + lows[i]) / 2 - factor * atr[i];
            if (i > 0) {
                const prevST = st[i-1];
                if (trend[i-1] === 1) { up = up; dn = Math.max(dn, prevST); } else { up = Math.min(up, prevST); dn = dn; }
            }
            if (closes[i] > up) trend[i] = 1; else if (closes[i] < dn) trend[i] = -1; else trend[i] = trend[i-1];
            st[i] = trend[i] === 1 ? dn : up;
        }
        return { trend, value: st };
    }
    static chandelierExit(highs, lows, closes, period, mult) {
        const atr = this.atr(highs, lows, closes, period);
        let longStop = TA.safeArr(closes.length); let shortStop = TA.safeArr(closes.length);
        let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            const maxHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const minLow = Math.min(...lows.slice(i - period + 1, i + 1));
            longStop[i] = maxHigh - atr[i] * mult; shortStop[i] = minLow + atr[i] * mult;
            if (closes[i] > shortStop[i]) trend[i] = 1; else if (closes[i] < longStop[i]) trend[i] = -1; else trend[i] = trend[i-1];
        }
        return { trend, value: trend.map((t, i) => t === 1 ? longStop[i] : shortStop[i]) };
    }
    static vwap(h, l, c, v, p) {
        let vwap = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let sumPV = 0, sumV = 0;
            for (let j = 0; j < p; j++) {
                const tp = (h[i-j] + l[i-j] + c[i-j]) / 3; sumPV += tp * v[i-j]; sumV += v[i-j];
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
        if (len < period * 2) return 'NONE';
        const priceHigh = Math.max(...closes.slice(len - period, len)); const rsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period)); const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';
        const priceLow = Math.min(...closes.slice(len - period, len)); const rsiLow = Math.min(...rsi.slice(len - period, len));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period)); const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
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


// --- 🛠️ UTILITIES & ENHANCED WSS CALCULATOR ---

function getOrderbookLevels(bids, asks, currentClose, maxLevels) {
    const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
    const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
    let potentialSR = [];
    for (const price of uniquePrices) {
        let bidVolAtPrice = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
        let askVolAtPrice = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
        if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
        else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
    }
    const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));
    const supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    const resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    return { supportLevels, resistanceLevels };
}

function calculateWSS(analysis, currentPrice) {
    const w = config.indicators.wss_weights;
    let score = 0;
    const last = analysis.closes.length - 1;
    const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr } = analysis;

    // --- 1. TREND COMPONENT ---
    let trendScore = 0;
    // Base MTF Trend
    trendScore += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);
    // Scalp Trend (ST/CE)
    if (st.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    if (ce.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    // Scale total Trend by R2 (Quality of Trend)
    const r2 = reg.r2[last];
    trendScore *= r2; 
    score += trendScore;

    // --- 2. MOMENTUM COMPONENT (Normalized) ---
    let momentumScore = 0;
    const rsiVal = rsi[last];
    const stochK = stoch.k[last];
    // Normalized RSI (stronger signal closer to 0/100)
    if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50; else momentumScore -= (rsiVal - 50) / 50;
    // Normalized Stoch K
    if (stochK < 50) momentumScore += (50 - stochK) / 50; else momentumScore -= (stochK - 50) / 50;
    // MACD Histogram Check
    const macdHist = macd.hist[last];
    if (macdHist > 0) momentumScore += w.macd_weight; else if (macdHist < 0) momentumScore -= w.macd_weight;
    score += momentumScore * w.momentum_normalized_weight;


    // --- 3. STRUCTURE / LIQUIDITY COMPONENT ---
    let structureScore = 0;
    // Squeeze
    if (analysis.isSqueeze) structureScore += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight);
    // Divergence (High conviction signal)
    if (divergence.includes('BULLISH')) structureScore += w.divergence_weight;
    else if (divergence.includes('BEARISH')) structureScore -= w.divergence_weight;
    // FVG/Wall Proximity (Liquidity grab potential)
    const price = currentPrice;
    const atrVal = atr[last];
    if (fvg) {
        if (fvg.type === 'BULLISH' && price > fvg.bottom && price < fvg.top) structureScore += w.liquidity_grab_weight;
        else if (fvg.type === 'BEARISH' && price < fvg.top && price > fvg.bottom) structureScore -= w.liquidity_grab_weight;
    }
    if (buyWall && (price - buyWall) < atrVal) structureScore += w.liquidity_grab_weight * 0.5; 
    else if (sellWall && (sellWall - price) < atrVal) structureScore -= w.liquidity_grab_weight * 0.5;
    score += structureScore;

    // --- 4. FINAL VOLATILITY ADJUSTMENT ---
    const volatility = analysis.volatility[analysis.volatility.length - 1] || 0;
    const avgVolatility = analysis.avgVolatility[analysis.avgVolatility.length - 1] || 1;
    const volRatio = volatility / avgVolatility;

    let finalScore = score;
    if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
    else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);
    
    return parseFloat(finalScore.toFixed(2));
}

// --- 📡 ENHANCED DATA PROVIDER (from v4.0, assumed complete) ---
class EnhancedDataProvider {
    constructor() { this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout }); }

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
            const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);

            const parseC = (list) => list.reverse().map(c => ({ o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) }));

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

// --- 💰 EXCHANGE & RISK MANAGEMENT (from v4.0, assumed complete) ---
class EnhancedPaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null;
        this.dailyPnL = new Decimal(0);
    }

    canTrade() {
        const drawdown = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdown.gt(config.risk.max_drawdown)) { console.log(NEON.RED(`🚨 MAX DRAWDOWN HIT`)); return false; }
        const dailyLoss = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLoss.lt(-config.risk.daily_loss_limit)) { console.log(NEON.RED(`🚨 DAILY LOSS LIMIT HIT`)); return false; }
        return true;
    }

    evaluate(priceVal, signal) {
        if (!this.canTrade()) { if (this.pos) this.handlePositionClose(new Decimal(priceVal), "RISK_STOP"); return; }
        const price = new Decimal(priceVal);
        if (this.pos) this.handlePositionClose(price);
        if (!this.pos && signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) { this.handlePositionOpen(price, signal); }
    }

    handlePositionClose(price, forceReason = null) {
        let close = false, reason = forceReason || '';
        if (this.pos.side === 'BUY') { if (forceReason || price.lte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.gte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } } else { if (forceReason || price.gte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.lte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } }
        if (close) {
            const slippage = price.mul(config.paper_trading.slippage);
            const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
            const rawPnl = this.pos.side === 'BUY' ? exitPrice.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
            const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
            const netPnl = rawPnl.sub(fee);
            this.balance = this.balance.add(netPnl);
            this.dailyPnL = this.dailyPnL.add(netPnl);
            const color = netPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(`${NEON.BOLD(reason)}! PnL: ${color(netPnl.toFixed(2))} [${this.pos.strategy}]`);
            this.pos = null;
        }
    }

    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry); const sl = new Decimal(signal.sl); const tp = new Decimal(signal.tp);
        const dist = entry.sub(sl).abs(); if (dist.isZero()) return;
        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);
        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;
        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
        this.balance = this.balance.sub(fee);
        this.pos = { side: signal.action, entry: execPrice, qty: qty, sl: sl, tp: tp, strategy: signal.strategy };
        console.log(NEON.GREEN(`OPEN ${signal.action} [${signal.strategy}] @ ${execPrice.toFixed(4)} | Size: ${qty.toFixed(4)}`));
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN (Hybrid Logic) ---
class EnhancedGeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { console.error("Missing GEMINI_API_KEY"); process.exit(1); }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(ctx) {
        const prompt = `
        ACT AS: Institutional Scalping Algorithm.
        OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD.

        QUANTITATIVE BIAS:
        - **WSS Score (Crucial Filter):** ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
        - CRITICAL RULE: Action must align with WSS. BUY requires WSS >= ${config.indicators.wss_weights.action_threshold}. SELL requires WSS <= -${config.indicators.wss_weights.action_threshold}.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope) | ADX: ${ctx.adx}
        - Momentum: RSI=${ctx.rsi}, Stoch=${ctx.stoch_k}, MACD=${ctx.macd_hist}
        - Structure: VWAP=${ctx.vwap}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
        - Support/Resistance: ${ctx.sr_levels}

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0): Pullback to VWAP/EMA, anticipate continuation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES): Trade in direction of MTF trend on volatility expansion.
        3. MEAN_REVERSION (WSS Momentum < -1.0 or > 1.0, Chop > 60): Fade extreme RSI/Stoch.
        4. LIQUIDITY_GRAB (Price Near FVG/Wall): Fade or trade the retest/bounce of a liquidity zone.
        5. DIVERGENCE_HUNT (Divergence != NONE): High conviction reversal trade using swing high/low for SL.

        INSTRUCTIONS:
        - If the WSS does not meet the threshold, or if no strategy is clear, return "HOLD".
        - Calculate precise entry, SL, and TP (1:1.5 RR minimum, use ATR/Pivot/FVG for targets).

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "strategy": "STRATEGY_NAME", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const start = text.indexOf('{');
            const end = text.lastIndexOf('}');
            if (start === -1 || end === -1) throw new Error("Invalid JSON: AI response error");
            return JSON.parse(text.substring(start, end + 1));
        } catch (e) {
            return { action: "HOLD", confidence: 0, reason: `AI Comms Failure: ${e.message}` };
        }
    }
}

// --- 🔄 MAIN TRADING ENGINE (from v4.0, assumed complete) ---
class TradingEngine {
    constructor() {
        this.dataProvider = new EnhancedDataProvider();
        this.exchange = new EnhancedPaperExchange();
        this.ai = new EnhancedGeminiBrain();
        this.isRunning = true;
    }

    async start() {
        console.clear();
        console.log(NEON.bg(NEON.PURPLE(` 🚀 WHALEWAVE TITAN v5.0 STARTING... `)));
        
        while (this.isRunning) {
            try {
                const data = await this.dataProvider.fetchAll();
                if (!data) { await setTimeout(config.loop_delay * 1000); continue; }

                const analysis = await this.performAnalysis(data);
                const context = this.buildContext(data, analysis);
                const signal = await this.ai.analyze(context);

                this.displayDashboard(data, context, signal);
                this.exchange.evaluate(data.price, signal);

            } catch (e) {
                console.error(NEON.RED(`Loop Critical Error: ${e.message}`));
            }
            await setTimeout(config.loop_delay * 1000);
        }
    }

    async performAnalysis(data) {
        const c = data.candles.map(x => x.c); const h = data.candles.map(x => x.h);
        const l = data.candles.map(x => x.l); const v = data.candles.map(x => x.v);
        const mtfC = data.candlesMTF.map(x => x.c);

        // Parallel Calculation (Full Suite)
        const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all([
            TA.rsi(c, config.indicators.rsi), TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig), TA.adx(h, l, c, config.indicators.adx_period),
            TA.mfi(h, l, c, v, config.indicators.mfi), TA.chop(h, l, c, config.indicators.chop_period),
            TA.linReg(c, config.indicators.linreg_period), TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult), TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles), TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult),
            TA.cci(h, l, c, config.indicators.cci_period)
        ]);

        const last = c.length - 1;
        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
        const divergence = TA.detectDivergence(c, rsi);
        const volatility = TA.historicalVolatility(c);
        const avgVolatility = TA.sma(volatility, 50);
        const mtfSma = TA.sma(mtfC, 20);
        const trendMTF = mtfC[mtfC.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);

        // Walls
        const avgBid = data.bids.reduce((a,b)=>a+b.q,0)/data.bids.length;
        const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p;
        const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p;

        const analysis = { 
            closes: c, rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci,
            isSqueeze, divergence, volatility, avgVolatility, trendMTF, buyWall, sellWall, fibs
        };
        // --- CRITICAL WSS CALCULATION ---
        analysis.wss = calculateWSS(analysis, data.price);
        analysis.avgVolatility = avgVolatility;
        return analysis;
    }

    buildContext(d, a) {
        const last = a.closes.length - 1;
        const linReg = TA.getFinalValue(a, 'reg', 4);
        const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

        return {
            price: d.price, rsi: a.rsi[last].toFixed(2), stoch_k: a.stoch.k[last].toFixed(0), macd_hist: (a.macd.hist[last] || 0).toFixed(4),
            adx: a.adx[last].toFixed(2), chop: a.chop[last].toFixed(2), vwap: a.vwap[last].toFixed(2),
            trend_angle: linReg.slope, trend_mtf: a.trendMTF, isSqueeze: a.isSqueeze ? 'YES' : 'NO', fvg: a.fvg, divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall }, fibs: a.fibs,
            volatility: a.volatility[last].toFixed(2), marketRegime: TA.marketRegime(a.closes, a.volatility),
            wss: a.wss, sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`
        };
    }

    displayDashboard(d, ctx, sig) {
        console.clear();
        const border = NEON.GRAY('─'.repeat(80));
        console.log(border);
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` WHALEWAVE TITAN v5.0 | ${config.symbol} | $${d.price.toFixed(4)} `).padEnd(80))));
        console.log(border);

        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        const wssColor = ctx.wss >= config.indicators.wss_weights.action_threshold ? NEON.GREEN : ctx.wss <= -config.indicators.wss_weights.action_threshold ? NEON.RED : NEON.YELLOW;
        console.log(`WSS: ${wssColor(ctx.wss)} | Strategy: ${NEON.BLUE(sig.strategy || 'SEARCHING')} | Signal: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        const regimeCol = ctx.marketRegime.includes('HIGH') ? NEON.RED : NEON.GREEN;
        console.log(`Regime: ${regimeCol(ctx.marketRegime)} | Vol: ${ctx.volatility} | Squeeze: ${ctx.isSqueeze === 'YES' ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${ctx.trend_mtf === 'BULLISH' ? NEON.GREEN('BULL') : NEON.RED('BEAR')} | Slope: ${ctx.trend_angle} | ADX: ${ctx.adx}`);
        console.log(border);

        console.log(`RSI: ${ctx.rsi} | Stoch: ${ctx.stoch_k} | MACD: ${ctx.macd_hist} | Chop: ${ctx.chop}`);
        console.log(`Divergence: ${ctx.divergence !== 'NONE' ? NEON.YELLOW(ctx.divergence) : 'None'} | FVG: ${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : 'None'}`);
        console.log(`VWAP: ${ctx.vwap} | ${ctx.sr_levels}`);
        console.log(border);

        const pnlCol = this.exchange.dailyPnL.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`Balance: ${NEON.GREEN('$' + this.exchange.balance.toFixed(2))} | Daily PnL: ${pnlCol('$' + this.exchange.dailyPnL.toFixed(2))}`);
        
        if (this.exchange.pos) {
            const p = this.exchange.pos;
            const curPnl = p.side === 'BUY' ? new Decimal(d.price).sub(p.entry).mul(p.qty) : p.entry.sub(d.price).mul(p.qty);
            const posCol = curPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(NEON.BLUE(`OPEN POS: ${p.side} @ ${p.entry.toFixed(4)} | SL: ${p.sl.toFixed(4)} | TP: ${p.tp.toFixed(4)} | PnL: ${posCol(curPnl.toFixed(2))}`));
        }
        console.log(border);
    }
}

// --- START ---
const engine = new TradingEngine();
process.on('SIGINT', () => { 
    engine.isRunning = false; 
    console.log(NEON.RED("\n🛑 SHUTTING DOWN GRACEFULLY...")); 
    // Simplified force close on shutdown (requires last price from dataProvider to be accessible)
    process.exit(0); 
});
process.on('SIGTERM', () => { engine.isRunning = false; process.exit(0); });
engine.start();
