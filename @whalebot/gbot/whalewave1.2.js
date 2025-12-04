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
        scalping_interval: '1', // New: for hyper-scalping analysis
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
            // Ehlers specific
            fisher_period: 10, laguerre_gamma: 0.5,
            // Scalping specific (NEW)
            scalping_ema_period: 5, // Very fast EMA for scalping
            scalping_momentum_threshold: 0.6, // For Laguerre RSI or similar
            scalping_atr_multiplier: 1.0, // Tighter ATR for SL/TP
            scalping_profit_target_factor: 0.5, // Even smaller profit targets for scalping
            scalping_volume_period: 20, // NEW: Period for calculating average volume for scalping confirmation
            // WSS Weighting Configuration (ENHANCED)
            wss_weights: {
                trend_mtf_weight: 2.0, trend_scalp_weight: 1.0,
                momentum_normalized_weight: 1.5, macd_weight: 0.8,
                regime_weight: 0.7, squeeze_vol_weight: 0.5,
                liquidity_grab_weight: 1.2, divergence_weight: 1.8,
                volatility_weight: 0.4, action_threshold: 1.5, // Higher threshold for high conviction
                // Scalping WSS weights (NEW)
                scalping_momentum_weight: 1.8, // Emphasize fast momentum
                scalping_ehlers_weight: 1.5,   // Emphasize Ehlers indicators
                scalping_volume_weight: 0.8, // NEW: Weight for volume confirmation in scalping
                scalping_action_threshold: 1.0 // Lower threshold for scalping signals
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

    // --- Ehlers Indicators (Advanced Signal Processing) ---
    static fisherTransform(highs, lows, period = 10) {
        const len = highs.length;
        let fish = TA.safeArr(len), trigger = TA.safeArr(len);
        let values = TA.safeArr(len);
        let intermediate = TA.safeArr(len); // Smoothed price value for transformation

        for (let i = 1; i < len; i++) {
            const mid = (highs[i] + lows[i]) / 2;
            if (i < period -1) {
                fish[i] = 0; trigger[i] = 0; values[i] = 0; intermediate[i] = 0; continue;
            }

            let minL = Infinity, maxH = -Infinity;
            for (let j = 0; j < period; j++) {
                const h = highs[i-j], l = lows[i-j];
                if(h > maxH) maxH = h;
                if(l < minL) minL = l;
            }

            intermediate[i] = (2 * ((mid - minL) / (maxH - minL)) - 1) * 0.5 + 0.5 * intermediate[i - 1];
            intermediate[i] = Math.min(Math.max(intermediate[i], -0.999), 0.999);

            fish[i] = 0.5 * Math.log((1 + intermediate[i]) / (1 - intermediate[i])) + 0.5 * fish[i - 1];
            trigger[i] = fish[i - 1];
        }
        return { fish, trigger };
    }

    static laguerreRSI(closes, gamma = 0.5) {
        const len = closes.length;
        let l0 = TA.safeArr(len), l1 = TA.safeArr(len), l2 = TA.safeArr(len), l3 = TA.safeArr(len);
        let lrsi = TA.safeArr(len);

        l0[0] = closes[0]; l1[0] = closes[0]; l2[0] = closes[0]; l3[0] = closes[0];

        for (let i = 1; i < len; i++) {
            l0[i] = (1 - gamma) * closes[i] + gamma * l0[i - 1];
            l1[i] = -gamma * l0[i] + l0[i - 1] + gamma * l1[i - 1];
            l2[i] = -gamma * l1[i] + l1[i - 1] + gamma * l2[i - 1];
            l3[i] = -gamma * l2[i] + l2[i - 1] + gamma * l3[i - 1];

            let cu = 0, cd = 0;
            if (l0[i] >= l1[i]) { cu = l0[i] - l1[i]; } else { cd = l1[i] - l0[i]; }
            if (l1[i] >= l2[i]) { cu += l1[i] - l2[i]; } else { cd += l2[i] - l1[i]; }
            if (l2[i] >= l3[i]) { cu += l2[i] - l3[i]; } else { cd += l3[i] - l2[i]; }
            
            lrsi[i] = (cu + cd !== 0) ? cu / (cu + cd) : lrsi[i-1];
        }
        return lrsi.map(v => v * 100);
    }
    
    static ehlersSuperSmoother(data, period) {
        if (!data || data.length < 3) return TA.safeArr(data.length);
        const result = TA.safeArr(data.length);
        const a1 = Math.exp(-1.414 * Math.PI / period);
        const b1 = 2 * a1 * Math.cos(1.414 * Math.PI / period);
        const c2 = b1;
        const c3 = -a1 * a1;
        const c1 = 1 - c2 - c3;
        result[0] = data[0]; result[1] = data[1];
        for (let i = 2; i < data.length; i++) {
            result[i] = c1 * ((data[i] + data[i - 1]) / 2) + c2 * result[i - 1] + c3 * result[i - 2];
        }
        return result;
    }

    // --- Other Advanced Indicators ---
    static obv(closes, volumes) {
        if (!closes || !volumes || closes.length === 0) return [];
        let result = [0];
        for (let i = 1; i < closes.length; i++) {
            if (closes[i] > closes[i-1]) result.push(result[i-1] + volumes[i]);
            else if (closes[i] < closes[i-1]) result.push(result[i-1] - volumes[i]);
            else result.push(result[i-1]);
        }
        return result;
    }

    static parabolicSAR(highs, lows, afStart = 0.02, afInc = 0.02, afMax = 0.2) {
        const len = highs.length;
        if (len < 2) return { psar: [], trend: [] };
        let psar = TA.safeArr(len), trend = TA.safeArr(len), af = afStart, ep;

        // Initial trend determination
        if (lows[1] > lows[0]) {
            trend[0] = 1; trend[1] = 1; // Uptrend
            psar[0] = lows[0]; psar[1] = lows[0];
            ep = highs[1];
        } else {
            trend[0] = -1; trend[1] = -1; // Downtrend
            psar[0] = highs[0]; psar[1] = highs[0];
            ep = lows[1];
        }

        for (let i = 2; i < len; i++) {
            trend[i] = trend[i-1];
            const prevPsar = psar[i-1];
            
            if (trend[i] === 1) { // --- In Uptrend ---
                psar[i] = prevPsar + af * (ep - prevPsar);
                psar[i] = Math.min(psar[i], lows[i-1], lows[i-2] || Infinity);
                
                if (highs[i] > ep) {
                    ep = highs[i];
                    af = Math.min(af + afInc, afMax);
                }
                if (lows[i] < psar[i]) { // Reversal to downtrend
                    trend[i] = -1;
                    psar[i] = ep; // New PSAR is the previous extreme point
                    ep = lows[i];
                    af = afStart;
                }
            } else { // --- In Downtrend ---
                psar[i] = prevPsar - af * (prevPsar - ep);
                psar[i] = Math.max(psar[i], highs[i-1], highs[i-2] || -Infinity);

                 if (lows[i] < ep) {
                    ep = lows[i];
                    af = Math.min(af + afInc, afMax);
                }
                if (highs[i] > psar[i]) { // Reversal to uptrend
                    trend[i] = 1;
                    psar[i] = ep; // New PSAR is the previous extreme point
                    ep = highs[i];
                    af = afStart;
                }
            }
        }
        return { psar, trend };
    }

    static ichimoku(highs, lows, closes, p1 = 9, p2 = 26, p3 = 52) {
        const len = closes.length;
        let tenkan = TA.safeArr(len), kijun = TA.safeArr(len), senkouA = TA.safeArr(len), senkouB = TA.safeArr(len), chikou = TA.safeArr(len);

        for (let i = 0; i < len; i++) {
            // Chikou Span (current close plotted in the past)
            chikou[i] = (i >= p2) ? closes[i - p2] : 0;
    
            // Tenkan-sen (Conversion Line)
            if (i >= p1 - 1) {
                const highSlice = highs.slice(i - p1 + 1, i + 1);
                const lowSlice = lows.slice(i - p1 + 1, i + 1);
                tenkan[i] = (Math.max(...highSlice) + Math.min(...lowSlice)) / 2;
            }
            
            // Kijun-sen (Base Line)
            if (i >= p2 - 1) {
                const highSlice = highs.slice(i - p2 + 1, i + 1);
                const lowSlice = lows.slice(i - p2 + 1, i + 1);
                kijun[i] = (Math.max(...highSlice) + Math.min(...lowSlice)) / 2;
            }
        }
        
        // Senkou Spans (plotted in the future, so we calculate them and shift the array)
        let futureSenkouA = TA.safeArr(len + p2);
        let futureSenkouB = TA.safeArr(len + p2);

        for (let i = 0; i < len; i++) {
            // Senkou Span A
            if (tenkan[i] && kijun[i]) {
                futureSenkouA[i + p2] = (tenkan[i] + kijun[i]) / 2;
            }
            // Senkou Span B
            if (i >= p3 - 1) {
                const highSlice = highs.slice(i - p3 + 1, i + 1);
                const lowSlice = lows.slice(i - p3 + 1, i + 1);
                futureSenkouB[i + p2] = (Math.max(...highSlice) + Math.min(...lowSlice)) / 2;
            }
        }
        // Align senkou spans back to the original length
        senkouA = futureSenkouA.slice(0, len);
        senkouB = futureSenkouB.slice(0, len);

        return { tenkan, kijun, senkouA, senkouB, chikou };
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
    const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr,
            scalpingEma, scalpingLaguerre, scalpingFisher, scalpingC, scalpingV // NEW
          } = analysis;

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

    // --- NEW: 5. SCALPING COMPONENT ---
    let scalpingScore = 0;
    // Assuming scalping candles have same length as main candles.
    const scalpingLast = scalpingEma.length - 1; 
    
    // Laguerre RSI for fast momentum
    const laguerreVal = scalpingLaguerre[scalpingLast];
    let laguerreSignal = 0;
    if (laguerreVal > (100 - config.indicators.scalping_momentum_threshold * 100)) laguerreSignal = 1; // Bullish
    else if (laguerreVal < config.indicators.scalping_momentum_threshold * 100) laguerreSignal = -1; // Bearish

    // Fisher Transform for turning points
    const fisherVal = scalpingFisher.fish[scalpingLast];
    const fisherTrigger = scalpingFisher.trigger[scalpingLast];
    let fisherSignal = 0;
    if (fisherVal > fisherTrigger && fisherVal < 0.5) fisherSignal = 1; // Bullish cross below 0.5
    else if (fisherVal < fisherTrigger && fisherVal > -0.5) fisherSignal = -1; // Bearish cross above -0.5

    // Volume Confirmation (simple approach: check if current volume is above average)
    const scalpingVolumePeriod = config.indicators.scalping_volume_period;
    const startIndex = Math.max(0, scalpingLast - scalpingVolumePeriod + 1);
    const relevantVolumes = scalpingV.slice(startIndex, scalpingLast + 1);
    
    const avgScalpingVolume = relevantVolumes.reduce((sum, val) => sum + val, 0) / relevantVolumes.length;
    const currentScalpingVolume = scalpingV[scalpingLast];
    let volumeConfirmation = 0;
    if (currentScalpingVolume > avgScalpingVolume * 1.2) { // 20% above average volume
        volumeConfirmation = 1;
    }

    // Confluence for scalpingScore
    if (laguerreSignal === 1 && fisherSignal === 1 && volumeConfirmation === 1) {
        scalpingScore += (w.scalping_momentum_weight + w.scalping_ehlers_weight + w.scalping_volume_weight);
    } else if (laguerreSignal === -1 && fisherSignal === -1 && volumeConfirmation === 1) {
        scalpingScore -= (w.scalping_momentum_weight + w.scalping_ehlers_weight + w.scalping_volume_weight);
    } else {
        // Less conviction if not all align
        if (laguerreSignal === 1 && fisherSignal === 1) scalpingScore += (w.scalping_momentum_weight + w.scalping_ehlers_weight) * 0.5;
        else if (laguerreSignal === -1 && fisherSignal === -1) scalpingScore -= (w.scalping_momentum_weight + w.scalping_ehlers_weight) * 0.5;
        else scalpingScore += laguerreSignal * w.scalping_momentum_weight * 0.3 + fisherSignal * w.scalping_ehlers_weight * 0.3; // Give some weight even if not fully aligned
    }
    
    score += scalpingScore; // Add scalping score to overall score


    // --- 4. FINAL VOLATILITY ADJUSTMENT ---
    const volatility = analysis.volatility[analysis.volatility.length - 1] || 0;
    const avgVolatility = analysis.avgVolatility[analysis.volatility.length - 1] || 1;
    const volRatio = volatility / avgVolatility;

    let finalScore = score;
    let effectiveActionThreshold = w.action_threshold; // Default to main threshold

    // If a significant scalping signal, use the scalping action threshold
    if (Math.abs(scalpingScore) > (w.scalping_action_threshold / 2)) { 
        effectiveActionThreshold = w.scalping_action_threshold;
    }

    if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
    else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);
    
    return { score: parseFloat(finalScore.toFixed(2)), actionThreshold: effectiveActionThreshold };
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
            const [ticker, kline, klineMTF, klineScalping, ob, daily] = await Promise.all([ // Added klineScalping
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.scalping_interval, limit: config.limit }), // NEW
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);

            const parseC = (list) => list.reverse().map(c => ({ o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) }));

            return {
                price: parseFloat(ticker.result.list[0].lastPrice),
                candles: parseC(kline.result.list),
                candlesMTF: parseC(klineMTF.result.list),
                candlesScalping: parseC(klineScalping.result.list), // NEW
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
        OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD. Prioritize quick, high-probability trades with tight stops and targets for scalping.

        QUANTITATIVE BIAS:
        - **WSS Score (Crucial Filter):** ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
        - CRITICAL RULE: Action must align with WSS. BUY requires WSS >= ${ctx.effective_wss_action_threshold}. SELL requires WSS <= -${ctx.effective_wss_action_threshold}.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope) | ADX: ${ctx.adx}
        - Momentum: RSI=${ctx.rsi}, Stoch=${ctx.stoch_k}, MACD=${ctx.macd_hist}
        - Structure: VWAP=${ctx.vwap}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
        - Support/Resistance: ${ctx.sr_levels}

        SCALPING CONTEXT (${ctx.scalping_interval} interval):
        - Scalping EMA (${config.indicators.scalping_ema_period}): ${ctx.scalping_ema}
        - Scalping Laguerre RSI: ${ctx.scalping_laguerre_rsi} (highly responsive momentum)
        - Scalping Fisher Transform: ${ctx.scalping_fisher} (signal) vs ${ctx.scalping_fisher_trigger} (trigger) (turning points)

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0): Pullback to VWAP/EMA, anticipate continuation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES): Trade in direction of MTF trend on volatility expansion.
        3. MEAN_REVERSION (WSS Momentum < -1.0 or > 1.0, Chop > 60): Fade extreme RSI/Stoch.
        4. LIQUIDITY_GRAB (Price Near FVG/Wall): Fade or trade the retest/bounce of a liquidity zone.
        5. DIVERGENCE_HUNT (Divergence != NONE): High conviction reversal trade using swing high/low for SL.
        6. HYPER_SCALP (Strong Scalping Context): Fast entry and exit based on responsive indicators.

        INSTRUCTIONS:
        - If the WSS does not meet the threshold, or if no strategy is clear, return "HOLD".
        - For HYPER_SCALP, aim for very tight SL/TP (e.g., using config.indicators.scalping_atr_multiplier * ATR for SL and config.indicators.scalping_profit_target_factor * ATR for TP, or a very small fixed R:R like 1:1.2).
        - Calculate precise entry, SL, and TP (1:1.5 RR minimum, use ATR/Pivot/FVG for targets, but adapt for scalping).

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
        const scalpingC = data.candlesScalping.map(x => x.c); // NEW
        const scalpingH = data.candlesScalping.map(x => x.h); // NEW
        const scalpingL = data.candlesScalping.map(x => x.l); // NEW
        const scalpingV = data.candlesScalping.map(x => x.v); // NEW


        // Parallel Calculation (Full Suite)
        const [
            rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci,
            fisher, laguerre, obv, psar, ichimoku,
            // Scalping specific (NEW)
            scalpingEma, scalpingLaguerre, scalpingFisher // NEW
        ] = await Promise.all([
            TA.rsi(c, config.indicators.rsi), TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig), TA.adx(h, l, c, config.indicators.adx_period),
            TA.mfi(h, l, c, v, config.indicators.mfi), TA.chop(h, l, c, config.indicators.chop_period),
            TA.linReg(c, config.indicators.linreg_period), TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult), TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles), TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult),
            TA.cci(h, l, c, config.indicators.cci_period),
            // Ehlers and other advanced indicators
            TA.fisherTransform(h, l, config.indicators.fisher_period),
            TA.laguerreRSI(c, config.indicators.laguerre_gamma),
            TA.obv(c, v),
            TA.parabolicSAR(h, l),
            TA.ichimoku(h, l, c),
            // Scalping specific promises (NEW)
            TA.ema(scalpingC, config.indicators.scalping_ema_period), // NEW
            TA.laguerreRSI(scalpingC, config.indicators.laguerre_gamma), // NEW
            TA.fisherTransform(scalpingH, scalpingL, config.indicators.fisher_period) // NEW
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
            fisher, laguerre, obv, psar, ichimoku,
            scalpingC, scalpingV, scalpingEma, scalpingLaguerre, scalpingFisher, // Added scalpingV
            isSqueeze, divergence, volatility, avgVolatility, trendMTF, buyWall, sellWall, fibs
        };
        // --- CRITICAL WSS CALCULATION ---
        const wssResult = calculateWSS(analysis, data.price); // Capture the object
        analysis.wss = wssResult.score;
        analysis.effectiveWssActionThreshold = wssResult.actionThreshold; // Store the effective threshold
        analysis.avgVolatility = avgVolatility;
        return analysis;
    }

    buildContext(d, a) {
        const last = a.closes.length - 1;
        const scalpingLast = a.scalpingC.length - 1; 
        const linReg = TA.getFinalValue(a, 'reg', 4);
        const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

        return {
            price: d.price, rsi: a.rsi[last].toFixed(2), stoch_k: a.stoch.k[last].toFixed(0), macd_hist: (a.macd.hist[last] || 0).toFixed(4),
            adx: a.adx[last].toFixed(2), chop: a.chop[last].toFixed(2), vwap: a.vwap[last].toFixed(2),
            trend_angle: linReg.slope, trend_mtf: a.trendMTF, isSqueeze: a.isSqueeze ? 'YES' : 'NO', fvg: a.fvg, divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall }, fibs: a.fibs,
            volatility: a.volatility[last].toFixed(2), marketRegime: TA.marketRegime(a.closes, a.volatility),
            wss: a.wss, sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`,
            effective_wss_action_threshold: a.effectiveWssActionThreshold, 
            // NEW Indicator Outputs
            fisher_fish: a.fisher.fish[last]?.toFixed(2),
            fisher_trigger: a.fisher.trigger[last]?.toFixed(2),
            laguerre_rsi: a.laguerre[last]?.toFixed(2),
            obv: a.obv[last]?.toFixed(0),
            psar: a.psar.psar[last]?.toFixed(4),
            psar_trend: a.psar.trend[last] === 1 ? 'UP' : 'DOWN',
            ichimoku_tenkan: a.ichimoku.tenkan[last]?.toFixed(4),
            ichimoku_kijun: a.ichimoku.kijun[last]?.toFixed(4),
            ichimoku_senkouA: a.ichimoku.senkouA[last]?.toFixed(4),
            ichimoku_senkouB: a.ichimoku.senkouB[last]?.toFixed(4),
            ichimoku_chikou: a.ichimoku.chikou[last]?.toFixed(4),
            // Scalping Context
            scalping_ema: a.scalpingEma[scalpingLast]?.toFixed(4),
            scalping_laguerre_rsi: a.scalpingLaguerre[scalpingLast]?.toFixed(2),
            scalping_fisher: a.scalpingFisher.fish[scalpingLast]?.toFixed(2),
            scalping_fisher_trigger: a.scalpingFisher.trigger[scalpingLast]?.toFixed(2),
            scalping_interval: config.scalping_interval // Indicate the interval
        };
    }

    displayDashboard(d, ctx, sig) {
        console.clear();
        const border = NEON.GRAY('─'.repeat(80));
        console.log(border);
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` 🚀 WHALEWAVE TITAN v5.0 | ${config.symbol} | $${d.price.toFixed(4)} `).padEnd(80))));
        console.log(border);

        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        const wssColor = ctx.wss >= ctx.effective_wss_action_threshold ? NEON.GREEN : ctx.wss <= -ctx.effective_wss_action_threshold ? NEON.RED : NEON.YELLOW;
        console.log(`WSS: ${wssColor(ctx.wss)} | Threshold: ${ctx.effective_wss_action_threshold} | Strategy: ${NEON.BLUE(sig.strategy || 'SEARCHING')} | Signal: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        const regimeCol = ctx.marketRegime.includes('HIGH') ? NEON.RED : NEON.GREEN;
        console.log(`Regime: ${regimeCol(ctx.marketRegime)} | Vol: ${ctx.volatility} | Squeeze: ${ctx.isSqueeze === 'YES' ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${ctx.trend_mtf === 'BULLISH' ? NEON.GREEN('BULL') : NEON.RED('BEAR')} | Slope: ${ctx.trend_angle} | ADX: ${ctx.adx}`);
        console.log(border);

        // Current Indicators
        console.log(`RSI: ${ctx.rsi} | Stoch: ${ctx.stoch_k} | MACD: ${ctx.macd_hist} | Chop: ${ctx.chop}`);
        console.log(`Divergence: ${ctx.divergence !== 'NONE' ? NEON.YELLOW(ctx.divergence) : 'None'} | FVG: ${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : 'None'}`);
        console.log(`VWAP: ${ctx.vwap} | ${ctx.sr_levels}`);
        console.log(border);

        // NEW: Advanced & Ehlers Indicators
        console.log(NEON.BOLD(NEON.BLUE(`Advanced & Ehlers Indicators:`)));
        console.log(`Fisher (F/T): ${ctx.fisher_fish}/${ctx.fisher_trigger} | Laguerre RSI: ${ctx.laguerre_rsi} | OBV: ${ctx.obv}`);
        console.log(`PSAR: ${ctx.psar} (${ctx.psar_trend})`);
        console.log(`Ichimoku: Tenkan=${ctx.ichimoku_tenkan}, Kijun=${ctx.ichimoku_kijun}, Senkou A/B=${ctx.ichimoku_senkouA}/${ctx.ichimoku_senkouB}, Chikou=${ctx.ichimoku_chikou}`);
        console.log(border);

        // NEW: Scalping Context Indicators
        console.log(NEON.BOLD(NEON.BLUE(`Scalping Context (${ctx.scalping_interval}):`)));
        console.log(`EMA: ${ctx.scalping_ema} | Laguerre RSI: ${ctx.scalping_laguerre_rsi} | Fisher (F/T): ${ctx.scalping_fisher}/${ctx.scalping_fisher_trigger}`);
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
