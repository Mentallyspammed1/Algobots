// unified_whalebot.js - Enhanced Version
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { URLSearchParams } from 'url';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';
import chalk from 'chalk';
import dotenv from 'dotenv';
import fetch from 'node-fetch';
import winston from 'winston';
import 'winston-daily-rotate-file';
import WebSocket from 'ws';
import _ from 'lodash';
import { execSync } from 'child_process';

// Initialize Decimal.js precision
Decimal.set({ precision: 28 });
dotenv.config();

// --- Constants ---
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = process.env.BYBIT_BASE_URL || "https://api.bybit.com";
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs/trading-bot/logs";
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });
const TIMEZONE = "UTC";
const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000;
const LOOP_DELAY_SECONDS = 15;

// Magic Numbers as Constants
const ADX_STRONG_TREND_THRESHOLD = 25;
const ADX_WEAK_TREND_THRESHOLD = 20;
const STOCH_RSI_MID_POINT = 50;
const MIN_CANDLESTICK_PATTERNS_BARS = 2;
const MIN_DATA_POINTS_TR = 2;
const MIN_DATA_POINTS_SMOOTHER_INIT = 2;
const MIN_DATA_POINTS_OBV = 2;
const MIN_DATA_POINTS_PSAR = 2;

// --- Utility Functions ---
function round_qty(qty, step) {
    if (step.lte(0)) return qty;
    return qty.div(step).floor().times(step);
}

function round_price(price, precision) {
    const factor = new Decimal(10).pow(precision);
    return price.times(factor).floor().div(factor);
}

function np_clip(value, min, max) {
    const val = new Decimal(value);
    if (val.lt(min)) return min;
    if (val.gt(max)) return max;
    return val;
}

// --- Indicator Colors ---
const INDICATOR_COLORS = {
    'EMA_Short': chalk.green,
    'EMA_Long': chalk.blue,
    'SMA_Long': chalk.cyan,
    'RSI': chalk.magenta,
    'StochRSI_K': chalk.yellow,
    'StochRSI_D': chalk.red,
    'BB_Upper': chalk.red,
    'BB_Middle': chalk.white,
    'BB_Lower': chalk.green,
    'CCI': chalk.cyan,
    'WR': chalk.magenta,
    'MFI': chalk.yellow,
    'OBV': chalk.blue,
    'OBV_EMA': chalk.cyan,
    'CMF': chalk.green,
    'Tenkan_Sen': chalk.red,
    'Kijun_Sen': chalk.blue,
    'Senkou_Span_A': chalk.yellow,
    'Senkou_Span_B': chalk.magenta,
    'Chikou_Span': chalk.cyan,
    'PSAR_Val': chalk.white,
    'PSAR_Dir': chalk.yellow,
    'VWAP': chalk.green,
    'ST_Fast_Dir': chalk.cyan,
    'ST_Fast_Val': chalk.white,
    'ST_Slow_Dir': chalk.blue,
    'ST_Slow_Val': chalk.white,
    'MACD_Line': chalk.green,
    'MACD_Signal': chalk.red,
    'MACD_Hist': chalk.yellow,
    'ADX': chalk.magenta,
    'PlusDI': chalk.green,
    'MinusDI': chalk.red,
    'Volatility_Index': chalk.cyan,
    'VWMA': chalk.blue,
    'Volume_Delta': chalk.yellow,
    'Kaufman_AMA': chalk.magenta,
    'Relative_Volume': chalk.green,
    'Market_Structure_Trend': chalk.cyan,
    'DEMA': chalk.yellow,
    'Keltner_Upper': chalk.red,
    'Keltner_Middle': chalk.white,
    'Keltner_Lower': chalk.green,
    'ROC': chalk.blue,
    'Candlestick_Pattern': chalk.magenta,
    'Pivot': chalk.white,
    'R1': chalk.green,
    'R2': chalk.lightGreen,
    'S1': chalk.red,
    'S2': chalk.lightRed,
    'Support_Level': chalk.green,
    'Resistance_Level': chalk.red
};

// --- Technical Indicators Implementation ---
const indicators = {
    calculate_sma: function(df, period) {
        const result = [];
        for (let i = period - 1; i < df.close.length; i++) {
            const sum = df.close.slice(i - period + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
            result.push(sum.dividedBy(period));
        }
        return result;
    },
    
    calculate_ema: function(df, period) {
        const result = [];
        const multiplier = new Decimal(2).dividedBy(new Decimal(period).plus(1));
        let ema = df.close[0];
        result.push(ema);
        
        for (let i = 1; i < df.close.length; i++) {
            ema = df.close[i].times(multiplier).plus(ema.times(new Decimal(1).minus(multiplier)));
            result.push(ema);
        }
        return result;
    },
    
    calculate_atr: function(df, period) {
        const tr = [];
        for (let i = 1; i < df.close.length; i++) {
            const high = df.high[i];
            const low = df.low[i];
            const prevClose = df.close[i - 1];
            const tr1 = high.minus(low);
            const tr2 = high.minus(prevClose).abs();
            const tr3 = low.minus(prevClose).abs();
            tr.push(Decimal.max(tr1, tr2, tr3));
        }
        
        const atr = [];
        let atrValue = tr[0];
        atr.push(atrValue);
        
        for (let i = 1; i < tr.length; i++) {
            atrValue = atrValue.times(new Decimal(period - 1)).plus(tr[i]).dividedBy(period);
            atr.push(atrValue);
        }
        return atr;
    },
    
    calculate_rsi: function(df, period) {
        const gains = [];
        const losses = [];
        
        for (let i = 1; i < df.close.length; i++) {
            const change = df.close[i].minus(df.close[i - 1]);
            gains.push(change.gt(0) ? change : new Decimal(0));
            losses.push(change.lt(0) ? change.abs() : new Decimal(0));
        }
        
        const rsi = [];
        let avgGain = gains.slice(0, period).reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
        let avgLoss = losses.slice(0, period).reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
        
        for (let i = period; i < gains.length; i++) {
            avgGain = avgGain.times(new Decimal(period - 1)).plus(gains[i]).dividedBy(period);
            avgLoss = avgLoss.times(new Decimal(period - 1)).plus(losses[i]).dividedBy(period);
            
            const rs = avgGain.dividedBy(avgLoss);
            rsi.push(new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs))));
        }
        return rsi;
    },
    
    calculate_stoch_rsi: function(df, rsiPeriod, kPeriod, dPeriod) {
        const rsi = indicators.calculate_rsi(df, rsiPeriod);
        const stochRsi = [];
        
        for (let i = rsiPeriod - 1; i < rsi.length; i++) {
            const slice = rsi.slice(i - rsiPeriod + 1, i + 1);
            const min = Decimal.min(...slice);
            const max = Decimal.max(...slice);
            const value = rsi[i].minus(min).dividedBy(max.minus(min)).times(100);
            stochRsi.push(value);
        }
        
        const k = [];
        for (let i = kPeriod - 1; i < stochRsi.length; i++) {
            const sum = stochRsi.slice(i - kPeriod + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
            k.push(sum.dividedBy(kPeriod));
        }
        
        const d = [];
        for (let i = dPeriod - 1; i < k.length; i++) {
            const sum = k.slice(i - dPeriod + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
            d.push(sum.dividedBy(dPeriod));
        }
        
        return { k, d };
    },
    
    calculate_bollinger_bands: function(df, period, stdDev) {
        const sma = indicators.calculate_sma(df, period);
        const upper = [];
        const lower = [];
        
        for (let i = 0; i < sma.length; i++) {
            const slice = df.close.slice(i, i + period);
            const mean = slice.reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
            const variance = slice.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0)).dividedBy(period);
            const std = variance.sqrt();
            
            upper.push(mean.plus(std.times(stdDev)));
            lower.push(mean.minus(std.times(stdDev)));
        }
        
        return { upper, middle: sma, lower };
    },
    
    calculate_cci: function(df, period) {
        const tp = [];
        for (let i = 0; i < df.close.length; i++) {
            tp.push(df.high[i].plus(df.low[i]).plus(df.close[i]).dividedBy(3));
        }
        
        const sma = indicators.calculate_sma({ close: tp }, period);
        const mad = [];
        
        for (let i = 0; i < sma.length; i++) {
            const slice = tp.slice(i, i + period);
            const mean = sma[i];
            const sum = slice.reduce((acc, val) => acc.plus(val.minus(mean).abs()), new Decimal(0));
            mad.push(sum.dividedBy(period));
        }
        
        const cci = [];
        for (let i = 0; i < sma.length; i++) {
            const value = tp[i + period - 1].minus(sma[i]).dividedBy(new Decimal(0.015).times(mad[i]));
            cci.push(value);
        }
        
        return cci;
    },
    
    calculate_williams_r: function(df, period) {
        const wr = [];
        for (let i = period - 1; i < df.close.length; i++) {
            const highest = Decimal.max(...df.high.slice(i - period + 1, i + 1));
            const lowest = Decimal.min(...df.low.slice(i - period + 1, i + 1));
            const value = highest.minus(df.close[i]).dividedBy(highest.minus(lowest)).times(new Decimal(-100));
            wr.push(value);
        }
        return wr;
    },
    
    calculate_mfi: function(df, period) {
        const tp = [];
        for (let i = 0; i < df.close.length; i++) {
            tp.push(df.high[i].plus(df.low[i]).plus(df.close[i]).dividedBy(3));
        }
        
        const positiveFlow = [];
        const negativeFlow = [];
        
        for (let i = 1; i < tp.length; i++) {
            if (tp[i].gt(tp[i - 1])) {
                positiveFlow.push(tp[i].times(df.volume[i]));
                negativeFlow.push(new Decimal(0));
            } else if (tp[i].lt(tp[i - 1])) {
                positiveFlow.push(new Decimal(0));
                negativeFlow.push(tp[i].times(df.volume[i]));
            } else {
                positiveFlow.push(new Decimal(0));
                negativeFlow.push(new Decimal(0));
            }
        }
        
        const mfi = [];
        for (let i = period - 1; i < positiveFlow.length; i++) {
            const posSum = positiveFlow.slice(i - period + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
            const negSum = negativeFlow.slice(i - period + 1, i + 1).reduce((acc, val) => acc.plus(val), new Decimal(0));
            
            if (negSum.isZero()) {
                mfi.push(new Decimal(100));
            } else {
                const moneyRatio = posSum.dividedBy(negSum);
                mfi.push(new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(moneyRatio))));
            }
        }
        return mfi;
    },
    
    calculate_obv: function(df, period) {
        const obv = [df.volume[0]];
        for (let i = 1; i < df.close.length; i++) {
            if (df.close[i].gt(df.close[i - 1])) {
                obv.push(obv[i - 1].plus(df.volume[i]));
            } else if (df.close[i].lt(df.close[i - 1])) {
                obv.push(obv[i - 1].minus(df.volume[i]));
            } else {
                obv.push(obv[i - 1]);
            }
        }
        
        const obvEma = indicators.calculate_ema({ close: obv }, period);
        return { obv, obv_ema: obvEma };
    },
    
    calculate_cmf: function(df, period) {
        const cmf = [];
        for (let i = period - 1; i < df.close.length; i++) {
            let sumVolume = new Decimal(0);
            let sumMoneyFlow = new Decimal(0);
            
            for (let j = i - period + 1; j <= i; j++) {
                const high = df.high[j];
                const low = df.low[j];
                const close = df.close[j];
                const volume = df.volume[j];
                
                const moneyFlowMultiplier = (close.minus(low).minus(high.minus(close))).dividedBy(high.minus(low));
                const moneyFlowVolume = moneyFlowMultiplier.times(volume);
                
                sumVolume = sumVolume.plus(volume);
                sumMoneyFlow = sumMoneyFlow.plus(moneyFlowVolume);
            }
            
            cmf.push(sumMoneyFlow.dividedBy(sumVolume));
        }
        return cmf;
    },
    
    calculate_ichimoku_cloud: function(df, tenkanPeriod, kijunPeriod, senkouBPeriod, chikouOffset) {
        const tenkanSen = [];
        const kijunSen = [];
        const senkouSpanA = [];
        const senkouSpanB = [];
        const chikouSpan = [];
        
        for (let i = tenkanPeriod - 1; i < df.close.length; i++) {
            const high = Decimal.max(...df.high.slice(i - tenkanPeriod + 1, i + 1));
            const low = Decimal.min(...df.low.slice(i - tenkanPeriod + 1, i + 1));
            tenkanSen.push(high.plus(low).dividedBy(2));
        }
        
        for (let i = kijunPeriod - 1; i < df.close.length; i++) {
            const high = Decimal.max(...df.high.slice(i - kijunPeriod + 1, i + 1));
            const low = Decimal.min(...df.low.slice(i - kijunPeriod + 1, i + 1));
            kijunSen.push(high.plus(low).dividedBy(2));
        }
        
        for (let i = kijunPeriod - 1; i < df.close.length; i++) {
            const a = tenkanSen[i - kijunPeriod + 1].plus(kijunSen[i - kijunPeriod + 1]).dividedBy(2);
            const high = Decimal.max(...df.high.slice(i - senkouBPeriod + 1, i + 1));
            const low = Decimal.min(...df.low.slice(i - senkouBPeriod + 1, i + 1));
            const b = high.plus(low).dividedBy(2);
            
            senkouSpanA.push(a);
            senkouSpanB.push(b);
        }
        
        for (let i = chikouOffset; i < df.close.length; i++) {
            chikouSpan.push(df.close[i - chikouOffset]);
        }
        
        return {
            tenkan_sen: tenkanSen,
            kijun_sen: kijunSen,
            senkou_span_a: senkouSpanA,
            senkou_span_b: senkouSpanB,
            chikou_span: chikouSpan
        };
    },
    
    calculate_psar: function(df, acceleration, maxAcceleration) {
        const psar = [];
        const direction = [];
        let ep = df.low[0];
        let sar = df.high[0];
        let af = acceleration;
        let trend = 1;
        
        psar.push(sar);
        direction.push(trend);
        
        for (let i = 1; i < df.close.length; i++) {
            const high = df.high[i];
            const low = df.low[i];
            
            if (trend === 1) {
                if (low.lt(sar)) {
                    trend = -1;
                    sar = Decimal.max(ep, high, df.high[i - 1]);
                    ep = low;
                    af = acceleration;
                } else {
                    if (high.gt(ep)) {
                        ep = high;
                        af = Decimal.min(af.plus(acceleration), maxAcceleration);
                    }
                    sar = sar.plus(af.times(ep.minus(sar)));
                    sar = Decimal.min(sar, df.low[i - 1], df.low[i - 2]);
                }
            } else {
                if (high.gt(sar)) {
                    trend = 1;
                    sar = Decimal.min(ep, low, df.low[i - 1]);
                    ep = high;
                    af = acceleration;
                } else {
                    if (low.lt(ep)) {
                        ep = low;
                        af = Decimal.min(af.plus(acceleration), maxAcceleration);
                    }
                    sar = sar.plus(af.times(ep.minus(sar)));
                    sar = Decimal.max(sar, df.high[i - 1], df.high[i - 2]);
                }
            }
            
            psar.push(sar);
            direction.push(trend);
        }
        
        return { psar, direction };
    },
    
    calculate_vwap: function(df) {
        const vwap = [];
        let cumulativeVolume = new Decimal(0);
        let cumulativeVolumePrice = new Decimal(0);
        
        for (let i = 0; i < df.close.length; i++) {
            const typicalPrice = df.high[i].plus(df.low[i]).plus(df.close[i]).dividedBy(3);
            const volume = df.volume[i];
            
            cumulativeVolume = cumulativeVolume.plus(volume);
            cumulativeVolumePrice = cumulativeVolumePrice.plus(typicalPrice.times(volume));
            
            vwap.push(cumulativeVolumePrice.dividedBy(cumulativeVolume));
        }
        
        return vwap;
    },
    
    calculate_ehlers_supertrend: function(df, period, multiplier) {
        const atr = indicators.calculate_atr(df, 14);
        const close = df.close.slice(14);
        const supertrend = [];
        const direction = [];
        
        let upperBand = close[0].plus(atr[0].times(multiplier));
        let lowerBand = close[0].minus(atr[0].times(multiplier));
        let trend = 1;
        
        supertrend.push(lowerBand);
        direction.push(trend);
        
        for (let i = 1; i < close.length; i++) {
            if (trend === 1) {
                if (close[i].lt(lowerBand)) {
                    trend = -1;
                    upperBand = close[i].plus(atr[i].times(multiplier));
                } else {
                    upperBand = Decimal.min(upperBand, close[i].plus(atr[i].times(multiplier)));
                    lowerBand = close[i].minus(atr[i].times(multiplier));
                }
            } else {
                if (close[i].gt(upperBand)) {
                    trend = 1;
                    lowerBand = close[i].minus(atr[i].times(multiplier));
                } else {
                    lowerBand = Decimal.max(lowerBand, close[i].minus(atr[i].times(multiplier)));
                    upperBand = close[i].plus(atr[i].times(multiplier));
                }
            }
            
            supertrend.push(trend === 1 ? lowerBand : upperBand);
            direction.push(trend);
        }
        
        return { supertrend, direction };
    },
    
    calculate_macd: function(df, fastPeriod, slowPeriod, signalPeriod) {
        const fastEma = indicators.calculate_ema(df, fastPeriod);
        const slowEma = indicators.calculate_ema(df, slowPeriod);
        
        const macdLine = [];
        for (let i = 0; i < fastEma.length; i++) {
            macdLine.push(fastEma[i].minus(slowEma[i]));
        }
        
        const signalLine = indicators.calculate_ema({ close: macdLine }, signalPeriod);
        const histogram = [];
        
        for (let i = 0; i < signalLine.length; i++) {
            histogram.push(macdLine[i + signalPeriod - 1].minus(signalLine[i]));
        }
        
        return {
            macd_line: macdLine.slice(signalPeriod - 1),
            signal_line: signalLine,
            histogram
        };
    },
    
    calculate_adx: function(df, period) {
        const tr = [];
        for (let i = 1; i < df.close.length; i++) {
            const high = df.high[i];
            const low = df.low[i];
            const prevClose = df.close[i - 1];
            const tr1 = high.minus(low);
            const tr2 = high.minus(prevClose).abs();
            const tr3 = low.minus(prevClose).abs();
            tr.push(Decimal.max(tr1, tr2, tr3));
        }
        
        const plusDM = [];
        const minusDM = [];
        
        for (let i = 1; i < df.close.length; i++) {
            const upMove = df.high[i].minus(df.high[i - 1]);
            const downMove = df.low[i - 1].minus(df.low[i]);
            
            if (upMove.gt(downMove) && upMove.gt(0)) {
                plusDM.push(upMove);
            } else {
                plusDM.push(new Decimal(0));
            }
            
            if (downMove.gt(upMove) && downMove.gt(0)) {
                minusDM.push(downMove);
            } else {
                minusDM.push(new Decimal(0));
            }
        }
        
        const atr = indicators.calculate_atr(df, period);
        const plusDI = [];
        const minusDI = [];
        const dx = [];
        
        for (let i = period - 1; i < tr.length; i++) {
            const trSlice = tr.slice(i - period + 1, i + 1);
            const plusDMSlice = plusDM.slice(i - period + 1, i + 1);
            const minusDMSlice = minusDM.slice(i - period + 1, i + 1);
            
            const trSum = trSlice.reduce((acc, val) => acc.plus(val), new Decimal(0));
            const plusDMSum = plusDMSlice.reduce((acc, val) => acc.plus(val), new Decimal(0));
            const minusDMSum = minusDMSlice.reduce((acc, val) => acc.plus(val), new Decimal(0));
            
            const plusDIValue = plusDMSum.dividedBy(trSum).times(100);
            const minusDIValue = minusDMSum.dividedBy(trSum).times(100);
            
            plusDI.push(plusDIValue);
            minusDI.push(minusDIValue);
            
            const diDiff = plusDIValue.minus(minusDIValue).abs();
            const diSum = plusDIValue.plus(minusDIValue);
            dx.push(diDiff.dividedBy(diSum).times(100));
        }
        
        const adx = [];
        for (let i = period - 1; i < dx.length; i++) {
            const dxSlice = dx.slice(i - period + 1, i + 1);
            const dxSum = dxSlice.reduce((acc, val) => acc.plus(val), new Decimal(0));
            adx.push(dxSum.dividedBy(period));
        }
        
        return {
            adx,
            plus_di: plusDI.slice(period - 1),
            minus_di: minusDI.slice(period - 1)
        };
    },
    
    calculate_volatility_index: function(df, period) {
        const returns = [];
        for (let i = 1; i < df.close.length; i++) {
            returns.push(df.close[i].dividedBy(df.close[i - 1]).minus(1));
        }
        
        const volatility = [];
        for (let i = period - 1; i < returns.length; i++) {
            const slice = returns.slice(i - period + 1, i + 1);
            const mean = slice.reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
            const variance = slice.reduce((acc, val) => acc.plus(val.minus(mean).pow(2)), new Decimal(0)).dividedBy(period);
            volatility.push(variance.sqrt().times(new Decimal(100)));
        }
        
        return volatility;
    },
    
    calculate_vwma: function(df, period) {
        const vwma = [];
        for (let i = period - 1; i < df.close.length; i++) {
            let volumeSum = new Decimal(0);
            let volumePriceSum = new Decimal(0);
            
            for (let j = i - period + 1; j <= i; j++) {
                volumeSum = volumeSum.plus(df.volume[j]);
                volumePriceSum = volumePriceSum.plus(df.close[j].times(df.volume[j]));
            }
            
            vwma.push(volumePriceSum.dividedBy(volumeSum));
        }
        
        return vwma;
    },
    
    calculate_volume_delta: function(df, period) {
        const volumeDelta = [];
        for (let i = period - 1; i < df.close.length; i++) {
            let buyVolume = new Decimal(0);
            let sellVolume = new Decimal(0);
            
            for (let j = i - period + 1; j <= i; j++) {
                const close = df.close[j];
                const open = df.open[j];
                const volume = df.volume[j];
                
                if (close.gt(open)) {
                    buyVolume = buyVolume.plus(volume);
                } else if (close.lt(open)) {
                    sellVolume = sellVolume.plus(volume);
                } else {
                    const halfVolume = volume.dividedBy(2);
                    buyVolume = buyVolume.plus(halfVolume);
                    sellVolume = sellVolume.plus(halfVolume);
                }
            }
            
            const delta = buyVolume.minus(sellVolume);
            volumeDelta.push(delta.dividedBy(buyVolume.plus(sellVolume)));
        }
        
        return volumeDelta;
    },
    
    calculate_kaufman_ama: function(df, period, fastPeriod, slowPeriod) {
        const change = [];
        for (let i = 1; i < df.close.length; i++) {
            change.push(df.close[i].minus(df.close[i - 1]).abs());
        }
        
        const volatility = [];
        for (let i = 1; i < df.close.length; i++) {
            let vol = new Decimal(0);
            for (let j = 1; j <= period; j++) {
                if (i - j >= 0) {
                    vol = vol.plus(df.close[i - j + 1].minus(df.close[i - j]).abs());
                }
            }
            volatility.push(vol);
        }
        
        const er = [];
        for (let i = 0; i < change.length; i++) {
            if (volatility[i].gt(0)) {
                er.push(change[i].dividedBy(volatility[i]));
            } else {
                er.push(new Decimal(0));
            }
        }
        
        const fastSC = new Decimal(2).dividedBy(new Decimal(fastPeriod).plus(1));
        const slowSC = new Decimal(2).dividedBy(new Decimal(slowPeriod).plus(1));
        
        const kama = [df.close[0]];
        for (let i = 1; i < df.close.length; i++) {
            const sc = er[i - 1].times(fastSC.minus(slowSC)).plus(slowSC).pow(2);
            kama.push(kama[i - 1].plus(sc.times(df.close[i].minus(kama[i - 1]))));
        }
        
        return kama;
    },
    
    calculate_relative_volume: function(df, period) {
        const volume = df.volume;
        const relativeVolume = [];
        
        for (let i = period - 1; i < volume.length; i++) {
            const slice = volume.slice(i - period + 1, i + 1);
            const avgVolume = slice.reduce((acc, val) => acc.plus(val), new Decimal(0)).dividedBy(period);
            relativeVolume.push(volume[i].dividedBy(avgVolume));
        }
        
        return relativeVolume;
    },
    
    calculate_market_structure: function(df, lookbackPeriod) {
        const trend = [];
        
        for (let i = lookbackPeriod; i < df.close.length; i++) {
            const highs = df.high.slice(i - lookbackPeriod, i);
            const lows = df.low.slice(i - lookbackPeriod, i);
            
            const currentHigh = df.high[i];
            const currentLow = df.low[i];
            
            const higherHighs = highs.filter(h => h.gt(currentHigh)).length === 0;
            const lowerLows = lows.filter(l => l.lt(currentLow)).length === 0;
            
            if (higherHighs && lowerLows) {
                trend.push("SIDEWAYS");
            } else if (higherHighs) {
                trend.push("UP");
            } else if (lowerLows) {
                trend.push("DOWN");
            } else {
                trend.push("SIDEWAYS");
            }
        }
        
        return trend;
    },
    
    calculate_dema: function(df, period) {
        const ema1 = indicators.calculate_ema(df, period);
        const ema2 = indicators.calculate_ema({ close: ema1 }, period);
        
        const dema = [];
        for (let i = 0; i < ema1.length; i++) {
            if (i < period - 1) {
                dema.push(new Decimal(NaN));
            } else {
                dema.push(ema1[i].times(2).minus(ema2[i - period + 1]));
            }
        }
        
        return dema;
    },
    
    calculate_keltner_channels: function(df, period, multiplier, atrPeriod) {
        const ema = indicators.calculate_ema(df, period);
        const atr = indicators.calculate_atr(df, atrPeriod);
        
        const upper = [];
        const lower = [];
        
        for (let i = 0; i < ema.length; i++) {
            const atrIndex = i + period - 1;
            if (atrIndex < atr.length) {
                upper.push(ema[i].plus(atr[atrIndex].times(multiplier)));
                lower.push(ema[i].minus(atr[atrIndex].times(multiplier)));
            } else {
                upper.push(new Decimal(NaN));
                lower.push(new Decimal(NaN));
            }
        }
        
        return { upper, middle: ema, lower };
    },
    
    calculate_roc: function(df, period) {
        const roc = [];
        for (let i = period; i < df.close.length; i++) {
            const change = df.close[i].minus(df.close[i - period]);
            const rocValue = change.dividedBy(df.close[i - period]).times(100);
            roc.push(rocValue);
        }
        return roc;
    },
    
    detect_candlestick_patterns: function(df) {
        const patterns = [];
        
        for (let i = 1; i < df.close.length; i++) {
            const prev = {
                open: df.open[i - 1],
                high: df.high[i - 1],
                low: df.low[i - 1],
                close: df.close[i - 1]
            };
            
            const curr = {
                open: df.open[i],
                high: df.high[i],
                low: df.low[i],
                close: df.close[i]
            };
            
            let pattern = "No Pattern";
            
            // Bullish Engulfing
            if (curr.close.gt(curr.open) && 
                prev.close.lt(prev.open) && 
                curr.open.lt(prev.close) && 
                curr.close.gt(prev.open)) {
                pattern = "Bullish Engulfing";
            }
            // Bearish Engulfing
            else if (curr.close.lt(curr.open) && 
                     prev.close.gt(prev.open) && 
                     curr.open.gt(prev.close) && 
                     curr.close.lt(prev.open)) {
                pattern = "Bearish Engulfing";
            }
            // Bullish Hammer
            else if (curr.close.gt(curr.open) && 
                     curr.low.lt(curr.open.minus(curr.close.minus(curr.open).times(0.3))) && 
                     curr.high.lt(curr.open.plus(curr.close.minus(curr.open).times(0.1)))) {
                pattern = "Bullish Hammer";
            }
            // Bearish Shooting Star
            else if (curr.close.lt(curr.open) && 
                     curr.high.gt(curr.open.plus(curr.open.minus(curr.close).times(0.3))) && 
                     curr.low.gt(curr.open.minus(curr.open.minus(curr.close).times(0.1)))) {
                pattern = "Bearish Shooting Star";
            }
            
            patterns.push(pattern);
        }
        
        return patterns;
    },
    
    calculate_fibonacci_levels: function(df, window) {
        if (df.length < window) return null;
        
        const slice = df.slice(df.length - window);
        const high = Decimal.max(...slice.high);
        const low = Decimal.min(...slice.low);
        const diff = high.minus(low);
        
        return {
            "0.0%": low,
            "23.6%": low.plus(diff.times(0.236)),
            "38.2%": low.plus(diff.times(0.382)),
            "50.0%": low.plus(diff.times(0.5)),
            "61.8%": low.plus(diff.times(0.618)),
            "78.6%": low.plus(diff.times(0.786)),
            "100.0%": high
        };
    },
    
    calculate_fibonacci_pivot_points: function(df) {
        const last = df[df.length - 1];
        const prev = df[df.length - 2];
        
        const high = last.high;
        const low = last.low;
        const close = last.close;
        
        const pivot = high.plus(low).plus(close).dividedBy(3);
        const range = high.minus(low);
        
        return {
            pivot,
            r1: pivot.plus(range.times(0.382)),
            r2: pivot.plus(range.times(0.618)),
            s1: pivot.minus(range.times(0.382)),
            s2: pivot.minus(range.times(0.618))
        };
    }
};

// --- Configuration Management ---
class ConfigManager {
    constructor(filepath, logger) {
        this.filepath = filepath;
        this.logger = logger;
        this.config = {};
        this.load_config();
    }
    
    load_config() {
        const default_config = {
            "symbol": "BTCUSDT", 
            "interval": "15", 
            "loop_delay": LOOP_DELAY_SECONDS,
            "orderbook_limit": 50, 
            "signal_score_threshold": 2.0, 
            "cooldown_sec": 60,
            "hysteresis_ratio": 0.85, 
            "volume_confirmation_multiplier": 1.5,
            "trade_management": {
                "enabled": true, 
                "account_balance": 1000.0, 
                "risk_per_trade_percent": 1.0,
                "stop_loss_atr_multiple": 1.5, 
                "take_profit_atr_multiple": 2.0,
                "max_open_positions": 1, 
                "order_precision": 5, 
                "price_precision": 3,
                "slippage_percent": 0.001, 
                "trading_fee_percent": 0.0005,
            },
            "risk_guardrails": {
                "enabled": true, 
                "max_day_loss_pct": 3.0, 
                "max_drawdown_pct": 8.0,
                "cooldown_after_kill_min": 120, 
                "spread_filter_bps": 5.0, 
                "ev_filter_enabled": true,
            },
            "session_filter": {
                "enabled": false, 
                "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
            },
            "pyramiding": {
                "enabled": false, 
                "max_adds": 2, 
                "step_atr": 0.7, 
                "size_pct_of_initial": 0.5,
            },
            "mtf_analysis": {
                "enabled": true, 
                "higher_timeframes": ["60", "240"],
                "trend_indicators": ["ema", "ehlers_supertrend"], 
                "trend_period": 50,
                "mtf_request_delay_seconds": 0.5,
            },
            "ml_enhancement": {"enabled": false},
            "indicator_settings": {
                "atr_period": 14, 
                "ema_short_period": 9, 
                "ema_long_period": 21, 
                "rsi_period": 14,
                "stoch_rsi_period": 14, 
                "stoch_k_period": 3, 
                "stoch_d_period": 3,
                "bollinger_bands_period": 20, 
                "bollinger_bands_std_dev": 2.0, 
                "cci_period": 20,
                "williams_r_period": 14, 
                "mfi_period": 14, 
                "psar_acceleration": 0.02,
                "psar_max_acceleration": 0.2, 
                "sma_short_period": 10, 
                "sma_long_period": 50,
                "fibonacci_window": 60, 
                "ehlers_fast_period": 10, 
                "ehlers_fast_multiplier": 2.0,
                "ehlers_slow_period": 20, 
                "ehlers_slow_multiplier": 3.0, 
                "macd_fast_period": 12,
                "macd_slow_period": 26, 
                "macd_signal_period": 9, 
                "adx_period": 14,
                "ichimoku_tenkan_period": 9, 
                "ichimoku_kijun_period": 26,
                "ichimoku_senkou_span_b_period": 52, 
                "ichimoku_chikou_span_offset": 26,
                "obv_ema_period": 20, 
                "cmf_period": 20, 
                "rsi_oversold": 30, 
                "rsi_overbought": 70,
                "stoch_rsi_oversold": 20, 
                "stoch_rsi_overbought": 80, 
                "cci_oversold": -100,
                "cci_overbought": 100, 
                "williams_r_oversold": -80, 
                "williams_r_overbought": -20,
                "mfi_oversold": 20, 
                "mfi_overbought": 80, 
                "volatility_index_period": 20,
                "vwma_period": 20, 
                "volume_delta_period": 5, 
                "volume_delta_threshold": 0.2,
                "kama_period": 10, 
                "kama_fast_period": 2, 
                "kama_slow_period": 30,
                "relative_volume_period": 20, 
                "relative_volume_threshold": 1.5,
                "market_structure_lookback_period": 20, 
                "dema_period": 14,
                "keltner_period": 20, 
                "keltner_atr_multiplier": 2.0, 
                "roc_period": 12,
                "roc_oversold": -5.0, 
                "roc_overbought": 5.0,
            },
            "indicators": {
                "ema_alignment": true, 
                "sma_trend_filter": true, 
                "momentum": true,
                "volume_confirmation": true, 
                "stoch_rsi": true, 
                "rsi": true, 
                "bollinger_bands": true,
                "vwap": true, 
                "cci": true, 
                "wr": true, 
                "psar": true, 
                "sma_10": true, 
                "mfi": true,
                "orderbook_imbalance": true, 
                "fibonacci_levels": true, 
                "ehlers_supertrend": true,
                "macd": true, 
                "adx": true, 
                "ichimoku_cloud": true, 
                "obv": true, 
                "cmf": true,
                "volatility_index": true, 
                "vwma": true, 
                "volume_delta": true,
                "kaufman_ama": true, 
                "relative_volume": true, 
                "market_structure": true,
                "dema": true, 
                "keltner_channels": true, 
                "roc": true, 
                "candlestick_patterns": true,
                "fibonacci_pivot_points": true,
            },
            "weight_sets": {
                "default_scalping": {
                    "ema_alignment": 0.30, 
                    "sma_trend_filter": 0.20, 
                    "ehlers_supertrend_alignment": 0.40,
                    "macd_alignment": 0.30, 
                    "adx_strength": 0.25, 
                    "ichimoku_confluence": 0.35,
                    "psar": 0.15, 
                    "vwap": 0.15, 
                    "vwma_cross": 0.10, 
                    "sma_10": 0.05,
                    "bollinger_bands": 0.25, 
                    "momentum_rsi_stoch_cci_wr_mfi": 0.35,
                    "volume_confirmation": 0.10, 
                    "obv_momentum": 0.15, 
                    "cmf_flow": 0.10,
                    "volume_delta_signal": 0.10, 
                    "orderbook_imbalance": 0.10,
                    "mtf_trend_confluence": 0.25, 
                    "volatility_index_signal": 0.10,
                    "kaufman_ama_cross": 0.20, 
                    "relative_volume_confirmation": 0.10,
                    "market_structure_confluence": 0.25, 
                    "dema_crossover": 0.18,
                    "keltner_breakout": 0.20, 
                    "roc_signal": 0.12, 
                    "candlestick_confirmation": 0.15,
                    "fibonacci_pivot_points_confluence": 0.20,
                }
            },
            "execution": {
                "use_pybit": false, 
                "testnet": false, 
                "account_type": "UNIFIED", 
                "category": "linear",
                "position_mode": "ONE_WAY", 
                "tpsl_mode": "Full", 
                "buy_leverage": "3",
                "sell_leverage": "3", 
                "tp_trigger_by": "LastPrice", 
                "sl_trigger_by": "LastPrice",
                "default_time_in_force": "GTC", 
                "reduce_only_default": false,
                "post_only_default": false,
                "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
                "proxies": { "enabled": false, "http": "", "https": "" },
                "tp_scheme": {
                    "mode": "atr_multiples",
                    "targets": [
                        {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.40, "order_type": "Limit", "tif": "PostOnly", "post_only": true},
                        {"name": "TP2", "atr_multiple": 1.5, "size_pct": 0.40, "order_type": "Limit", "tif": "IOC", "post_only": false},
                        {"name": "TP3", "atr_multiple": 2.0, "size_pct": 0.20, "order_type": "Limit", "tif": "GTC", "post_only": false},
                    ],
                },
                "sl_scheme": {
                    "type": "atr_multiple", 
                    "atr_multiple": 1.5, 
                    "percent": 1.0,
                    "use_conditional_stop": true, 
                    "stop_order_type": "Market",
                },
                "breakeven_after_tp1": {
                    "enabled": true, 
                    "offset_type": "atr", 
                    "offset_value": 0.10,
                    "lock_in_min_percent": 0, 
                    "sl_trigger_by": "LastPrice",
                },
                "live_sync": {
                    "enabled": true, 
                    "poll_ms": 2500, 
                    "max_exec_fetch": 200,
                    "only_track_linked": true, 
                    "heartbeat": {"enabled": true, "interval_ms": 5000},
                },
            },
        };
        
        if (!fs.existsSync(this.filepath)) {
            try {
                fs.writeFileSync(this.filepath, JSON.stringify(default_config, null, 4), 'utf-8');
                this.logger.warn(`${chalk.yellow("Configuration file not found. Created default config at ")}${this.filepath}${chalk.reset()}`);
                this.config = default_config;
            } catch (e) {
                this.logger.error(`${chalk.red("Error creating default config file: ")}${e}${chalk.reset()}`);
                this.config = default_config;
            }
        } else {
            try {
                let current_config = JSON.parse(fs.readFileSync(this.filepath, 'utf-8'));
                this.config = _.mergeWith({}, default_config, current_config, (objValue, srcValue, key) => {
                    // Convert numeric properties in nested structures that should be Decimals
                    const decimalKeys = [
                        "minOrderSize", "maxPositionSizePercent", "riskPerTradePercent", "martingaleMultiplier",
                        "stopLossAtrMultiple", "takeProfitAtrMultiple", "partialTakeProfitPercent",
                        "partialTakeProfitAtrMultiple", "breakEvenThresholdAtrMultiple", "trailingAtrMultiple",
                        "slippage_percent", "trading_fee_percent", "account_balance"
                    ];
                    if (decimalKeys.includes(key) && typeof srcValue === 'number') {
                        return new Decimal(srcValue);
                    }
                    if (_.isArray(objValue) && _.isArray(srcValue)) {
                        return srcValue; // Overwrite arrays completely if in user config
                    }
                    // Let lodash handle default merge for other types
                    return undefined;
                });
                fs.writeFileSync(this.filepath, JSON.stringify(this.config, null, 4), 'utf-8');
                this.logger.info(`${chalk.green("Configuration loaded and updated at ")}${this.filepath}${chalk.reset()}`);
            } catch (e) {
                this.logger.error(`${chalk.red("Error loading config: ")}${e}. Using default.${chalk.reset()}`);
                this.config = default_config;
            }
        }
    }
}

// --- Logging Setup ---
const sensitivePrintf = (template, sensitiveWords) => {
    const escapeRegExp = (string) => {
        return string.replace(/[.*+?^${}()|[\\]/g, '\\$&');
    };
    return winston.format.printf(info => {
        let message = template(info);
        for (const word of sensitiveWords) {
            if (typeof word === 'string' && message.includes(word)) {
                const escapedWord = escapeRegExp(word);
                message = message.replace(new RegExp(escapedWord, 'g'), '*'.repeat(word.length));
            }
        }
        return message;
    });
};

const setup_logger = (log_name, level = 'info') => {
    const logger = winston.createLogger({
        level: level,
        format: winston.format.combine(
            winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
            winston.format.errors({ stack: true }),
            sensitivePrintf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`, [API_KEY, API_SECRET].filter(Boolean))
        ),
        transports: [
            new winston.transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${log_name}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '10m',
                maxFiles: '5d'
            }),
            new winston.transports.Console({
                format: winston.format.combine(
                    winston.format.timestamp({ format: 'HH:mm:ss.SSS' }),
                    sensitivePrintf(info => {
                        let levelColor;
                        switch (info.level) {
                            case 'info': levelColor = chalk.cyan; break;
                            case 'warn': levelColor = chalk.yellow; break;
                            case 'error': levelColor = chalk.red; break;
                            case 'debug': levelColor = chalk.blue; break;
                            case 'critical': levelColor = chalk.magentaBright; break;
                            default: levelColor = chalk.white;
                        }
                        return `${levelColor(info.timestamp)} - ${levelColor(info.level.toUpperCase())} - ${levelColor(info.message)}`;
                    }, [API_KEY, API_SECRET].filter(Boolean))
                )
            })
        ],
        exitOnError: false
    });
    return logger;
};
const logger = setup_logger("wgwhalex_bot");

// --- API Interaction ---
class BybitClient {
    constructor(api_key, api_secret, base_url, logger) {
        this.api_key = api_key;
        this.api_secret = api_secret;
        this.base_url = base_url;
        this.logger = logger;
        this.enabled = api_key && api_secret; // Check if API keys are provided
    }
    
    _generate_signature(payload) {
        return crypto.createHmac('sha256', this.api_secret).update(payload).digest('hex');
    }
    
    async _send_signed_request(method, endpoint, params) {
        if (!this.enabled) {
            this.logger.error(`${chalk.red("API keys not configured for signed request.")}`);
            return null;
        }
        
        const timestamp = String(Date.now());
        const recv_window = "20000";
        const headers = {"Content-Type": "application/json"};
        const url = `${this.base_url}${endpoint}`;
        let param_str;
        
        if (method === "GET") {
            const query_string = params ? new URLSearchParams(params).toString() : "";
            param_str = timestamp + this.api_key + recv_window + query_string;
            headers["X-BAPI-API-KEY"] = this.api_key;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = this._generate_signature(param_str);
            headers["X-BAPI-RECV-WINDOW"] = recv_window;
            this.logger.debug(`GET Request: ${url}?${query_string}`);
            return fetch(`${url}?${query_string}`, { method: "GET", headers, timeout: REQUEST_TIMEOUT });
        } else { // POST
            const json_params = params ? JSON.stringify(params) : "";
            param_str = timestamp + this.api_key + recv_window + json_params;
            headers["X-BAPI-API-KEY"] = this.api_key;
            headers["X-BAPI-TIMESTAMP"] = timestamp;
            headers["X-BAPI-SIGN"] = this._generate_signature(param_str);
            headers["X-BAPI-RECV-WINDOW"] = recv_window;
            this.logger.debug(`POST Request: ${url} with payload ${json_params}`);
            return fetch(url, { method: "POST", headers, body: json_params, timeout: REQUEST_TIMEOUT });
        }
    }
    
    async _handle_api_response(response) {
        try {
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP Error: ${response.status} - ${errorText}`);
            }
            const data = await response.json();
            if (data.retCode !== 0) {
                this.logger.error(`${chalk.red("Bybit API Error: ")}${data.retMsg} (Code: ${data.retCode})${chalk.reset()}`);
                return null;
            }
            return data;
        } catch (e) {
            this.logger.error(`${chalk.red("API Response Error: ")}${e.message}${chalk.reset()}`);
            return null;
        }
    }
    
    async bybit_request(method, endpoint, params = null, signed = false) {
        for (let attempt = 0; attempt < MAX_API_RETRIES; attempt++) {
            try {
                let response;
                if (signed) {
                    response = await this._send_signed_request(method, endpoint, params);
                } else {
                    const url = `${this.base_url}${endpoint}`;
                    const query_string = params ? new URLSearchParams(params).toString() : "";
                    this.logger.debug(`Public Request: ${url}?${query_string}`);
                    response = await fetch(`${url}?${query_string}`, { method: "GET", timeout: REQUEST_TIMEOUT });
                }
                if (response) {
                    const data = await this._handle_api_response(response);
                    if (data !== null) return data;
                }
            } catch (e) {
                this.logger.error(`${chalk.red("Request Attempt ")}${attempt + 1}/${MAX_API_RETRIES} failed: ${e.message}${chalk.reset()}`);
            }
            await setTimeout(RETRY_DELAY_SECONDS * 1000 * (attempt + 1)); // Exponential backoff
        }
        return null;
    }
    
    async fetch_current_price(symbol) {
        const endpoint = "/v5/market/tickers";
        const params = {"category": "linear", "symbol": symbol};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result && response.result.list) {
            const price = new Decimal(response.result.list[0].lastPrice);
            this.logger.debug(`Fetched current price for ${symbol}: ${price}`);
            return price;
        }
        this.logger.warning(`${chalk.yellow("Could not fetch current price for ")}${symbol}${chalk.reset()}`);
        return null;
    }
    
    async fetch_klines(symbol, interval, limit) {
        const endpoint = "/v5/market/kline";
        const params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result && response.result.list) {
            const df_data = response.result.list.map(k => ({
                start_time: new Date(parseInt(k[0])),
                open: new Decimal(k[1]), 
                high: new Decimal(k[2]), 
                low: new Decimal(k[3]),
                close: new Decimal(k[4]), 
                volume: new Decimal(k[5]), 
                turnover: new Decimal(k[6])
            }));
            // Sort by time in ascending order to match pandas behavior
            df_data.sort((a, b) => a.start_time.getTime() - b.start_time.getTime());
            this.logger.debug(`Fetched ${df_data.length} ${interval} klines for ${symbol}.`);
            return df_data; // Return as array of objects for JS processing
        }
        this.logger.warning(`${chalk.yellow("Could not fetch klines for ")}${symbol} ${interval}${chalk.reset()}`);
        return null;
    }
    
    async fetch_orderbook(symbol, limit) {
        const endpoint = "/v5/market/orderbook";
        const params = {"category": "linear", "symbol": symbol, "limit": limit};
        const response = await this.bybit_request("GET", endpoint, params);
        if (response && response.result) {
            this.logger.debug(`Fetched orderbook for ${symbol} with limit ${limit}.`);
            return response.result;
        }
        this.logger.warning(`${chalk.yellow("Could not fetch orderbook for ")}${symbol}${chalk.reset()}`);
        return null;
    }
    
    async get_wallet_balance(coin = "USDT") {
        if (!this.enabled) return new Decimal(0);
        
        const endpoint = "/v5/account/wallet-balance";
        const params = {"accountType": "UNIFIED", "coin": coin};
        const response = await this.bybit_request("GET", endpoint, params, true);
        if (response && response.result && response.result.list && response.result.list.length > 0) {
            const coin_info = response.result.list[0].coin.find(c => c.coin === coin);
            if (coin_info) return new Decimal(coin_info.walletBalance);
        }
        this.logger.warning(`${chalk.yellow("Could not fetch wallet balance for ")}${coin}${chalk.reset()}`);
        return new Decimal(0);
    }
    
    async set_leverage(symbol, buy_leverage, sell_leverage) {
        if (!this.enabled) return false;
        
        const endpoint = "/v5/position/set-leverage";
        const params = {
            "category": "linear", 
            "symbol": symbol, 
            "buyLeverage": String(buy_leverage), 
            "sellLeverage": String(sell_leverage)
        };
        const response = await this.bybit_request("POST", endpoint, params, true);
        return response !== null;
    }
    
    _side_to_bybit(side) {
        return side === "BUY" ? "Buy" : "Sell";
    }
    
    async place_order(symbol, side, orderType, qty, price = null, stopLoss = null, takeProfit = null, isLeverage = 1, timeInForce = "GTC") {
        if (!this.enabled) return null;
        
        const endpoint = "/v5/order/create";
        const params = {
            category: "linear", 
            symbol, 
            side: this._side_to_bybit(side), 
            orderType,
            qty: qty.toString(), 
            isLeverage, 
            timeInForce
        };
        
        if (price !== null) params.price = price.toString();
        if (stopLoss !== null) { 
            params.stopLoss = stopLoss.toString(); 
            params.slTriggerBy = "MarkPrice"; 
        }
        if (takeProfit !== null) { 
            params.takeProfit = takeProfit.toString(); 
            params.tpTriggerBy = "MarkPrice"; 
        }
        
        const response = await this.bybit_request("POST", endpoint, params, true);
        if (response && response.result) {
            this.logger.info(`${chalk.green("Order placed: ")}${side} ${qty.toString()} ${symbol} SL: ${stopLoss ? stopLoss.toString() : 'N/A'}, TP: ${takeProfit ? takeProfit.toString() : 'N/A'}${chalk.reset()}`);
            return response.result;
        }
        return null;
    }
}

// --- Position Management ---
class PositionManager {
    constructor(config, logger, symbol, pybit_client) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.open_positions = []; // Local tracking of open positions
        this.trade_management_enabled = config.trade_management.enabled;
        this.max_open_positions = config.trade_management.max_open_positions;
        this.order_precision = config.trade_management.order_precision;
        this.price_precision = config.trade_management.price_precision;
        this.slippage_percent = new Decimal(config.trade_management.slippage_percent);
        this.pybit = pybit_client; // HTTP client for order placement
        
        // Placeholder for qty_step, will be updated from exchange
        this.qty_step = new Decimal("0.000001"); 
        this._update_precision_from_exchange();
    }
    
    async _update_precision_from_exchange() {
        if (!this.pybit.enabled) return;
        
        const info = await this.pybit.bybit_request("GET", "/v5/market/instruments-info", {category: "linear", symbol: this.symbol});
        if (info && info.result && info.result.list && info.result.list.length > 0) {
            const instrument = info.result.list[0];
            if (instrument.lotSizeFilter) {
                this.qty_step = new Decimal(instrument.lotSizeFilter.qtyStep);
                this.order_precision = this.qty_step.precision();
                this.logger.info(`${chalk.blue("Updated qty_step: ")}${this.qty_step}, order_precision: ${this.order_precision}${chalk.reset()}`);
            }
            if (instrument.priceFilter) {
                this.price_precision = new Decimal(instrument.priceFilter.tickSize).precision();
                this.logger.info(`${chalk.blue("Updated price_precision: ")}${this.price_precision}${chalk.reset()}`);
            }
        }
    }
    
    _get_current_balance() {
        // In live trading, this would call Pybit client to get real balance
        // For simulation, use config account balance
        return new Decimal(this.config.trade_management.account_balance);
    }
    
    _calculate_order_size(current_price, atr_value, conviction = 1.0) {
        if (!this.trade_management_enabled) return new Decimal("0");
        
        const account_balance = this._get_current_balance();
        const base_risk_pct = new Decimal(this.config.trade_management.risk_per_trade_percent).dividedBy(100);
        const risk_multiplier = new Decimal(np_clip(0.5 + conviction, 0.5, 1.5));
        const risk_pct = base_risk_pct.times(risk_multiplier);
        const stop_loss_atr_multiple = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const risk_amount = account_balance.times(risk_pct);
        const stop_loss_distance = atr_value.times(stop_loss_atr_multiple);
        
        if (stop_loss_distance.lte(0)) {
            this.logger.warning(`${chalk.yellow("Stop loss distance is zero or negative. Cannot calculate order size.")}${chalk.reset()}`);
            return new Decimal("0");
        }
        
        const order_value = risk_amount.dividedBy(stop_loss_distance);
        let order_qty = order_value.dividedBy(current_price);
        
        return round_qty(order_qty, this.qty_step);
    }
    
    _compute_stop_loss_price(side, entry_price, atr_value) {
        const sl_cfg = this.config.execution.sl_scheme;
        let sl;
        
        if (sl_cfg.type === "atr_multiple") {
            const sl_mult = new Decimal(sl_cfg.atr_multiple);
            sl = (side === "BUY") ? entry_price.minus(atr_value.times(sl_mult)) : entry_price.plus(atr_value.times(sl_mult));
        } else { // percent
            const sl_pct = new Decimal(sl_cfg.percent).dividedBy(100);
            sl = (side === "BUY") ? entry_price.times(new Decimal(1).minus(sl_pct)) : entry_price.times(new Decimal(1).plus(sl_pct));
        }
        
        return round_price(sl, this.price_precision);
    }
    
    _calculate_take_profit_price(signal, current_price, atr_value) {
        const tp_mult = new Decimal(this.config.trade_management.take_profit_atr_multiple);
        const tp = (signal === "BUY") ? current_price.plus(atr_value.times(tp_mult)) : current_price.minus(atr_value.times(tp_mult));
        return round_price(tp, this.price_precision);
    }
    
    async open_position(signal, current_price, atr_value, conviction) {
        if (!this.trade_management_enabled || this.open_positions.length >= this.max_open_positions) {
            this.logger.info(`${chalk.yellow("Cannot open new position (max reached or disabled).")}${chalk.reset()}`);
            return null;
        }
        
        const order_qty = this._calculate_order_size(current_price, atr_value, conviction);
        if (order_qty.lte(0)) {
            this.logger.warning(`${chalk.yellow("Order quantity is zero. Cannot open position.")}${chalk.reset()}`);
            return null;
        }
        
        const stop_loss = this._compute_stop_loss_price(signal, current_price, atr_value);
        const take_profit = this._calculate_take_profit_price(signal, current_price, atr_value);
        
        // Apply slippage for initial entry in simulation
        let adjusted_entry_price_sim = current_price;
        if (signal === "BUY") {
            adjusted_entry_price_sim = current_price.times(new Decimal(1).plus(this.slippage_percent));
        } else { // SELL
            adjusted_entry_price_sim = current_price.times(new Decimal(1).minus(this.slippage_percent));
        }
        
        const position = {
            "entry_time": new Date(), 
            "symbol": this.symbol, 
            "side": signal,
            "entry_price": round_price(adjusted_entry_price_sim, this.price_precision), 
            "qty": order_qty,
            "stop_loss": stop_loss, 
            "take_profit": take_profit,
            "status": "OPEN", 
            "link_prefix": `wgx_${Date.now()}`, 
            "adds": 0,
            "order_id": null, 
            "stop_loss_order_id": null, 
            "take_profit_order_ids": []
        };
        
        // For live trading, actually place orders via pybit_client
        if (this.config.execution.use_pybit && this.pybit && this.pybit.enabled) {
            try {
                this.logger.info(`${chalk.blue("Placing live market order for ")}${signal} ${order_qty.toString()} ${this.symbol} at ${current_price.toString()}...${chalk.reset()}`);
                const resp = await this.pybit.place_order(
                    this.symbol, 
                    this.pybit._side_to_bybit(signal), 
                    "Market", 
                    order_qty, 
                    null, 
                    stop_loss, 
                    take_profit
                );
                
                if (resp && resp.orderId) {
                    position.order_id = resp.orderId;
                    this.logger.info(`${chalk.green("Live entry submitted (Order ID: ")}${position.order_id}).${chalk.reset()}`);
                    // TP/SL are set with the main order in this simplified Pybit call, but a more complex TP scheme would need separate orders.
                } else {
                    this.logger.error(`${chalk.red("Live entry failed. Simulating only. Response: ")}${JSON.stringify(resp)}${chalk.reset()}`);
                }
            } catch (e) {
                this.logger.error(`${chalk.red("Exception during live entry: ")}${e.message}. Simulating only.${chalk.reset()}`);
            }
        }
        
        this.open_positions.push(position);
        this.logger.info(`${chalk.green("Opened ")}${signal} position (local/simulated): ${JSON.stringify(position)}${chalk.reset()}`);
        return position;
    }
    
    _check_and_close_position(position, current_price, slippage_percent, price_precision, logger) {
        const side = position.side;
        const stop_loss = position.stop_loss;
        const take_profit = position.take_profit;
        let closed_by = null;
        let close_price = new Decimal("0");
        
        if (side === "BUY") {
            if (current_price.lte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).minus(slippage_percent));
            } else if (current_price.gte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).minus(slippage_percent));
            }
        } else if (side === "SELL") {
            if (current_price.gte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).plus(slippage_percent));
            } else if (current_price.lte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).plus(slippage_percent));
            }
        }
        
        if (closed_by) {
            const adjusted_close_price = round_price(close_price, price_precision);
            return { is_closed: true, adjusted_close_price, closed_by };
        }
        return { is_closed: false, adjusted_close_price: new Decimal("0"), closed_by: "" };
    }
    
    manage_positions(current_price, performance_tracker) {
        if (!this.trade_management_enabled || !this.open_positions) {
            return;
        }
        
        const positions_to_close_indices = [];
        for (let i = 0; i < this.open_positions.length; i++) {
            const position = this.open_positions[i];
            if (position.status === "OPEN") {
                const { is_closed, adjusted_close_price, closed_by } = this._check_and_close_position(
                    position, current_price, this.slippage_percent, this.price_precision, this.logger
                );
                
                if (is_closed) {
                    position.status = "CLOSED";
                    position.exit_time = new Date();
                    position.exit_price = adjusted_close_price;
                    position.closed_by = closed_by;
                    positions_to_close_indices.push(i);
                    
                    const pnl = position.side === "BUY"
                        ? (adjusted_close_price.minus(position.entry_price)).times(position.qty)
                        : (position.entry_price.minus(adjusted_close_price)).times(position.qty);
                    
                    performance_tracker.record_trade(position, pnl);
                    this.logger.info(`${chalk.magenta("Closed ")}${position.side} position by ${closed_by}: ${JSON.stringify(position)}. PnL: ${pnl.normalize().toFixed(2)}${chalk.reset()}`);
                    
                    // Cancel any open orders for this position if live
                    if (this.config.execution.use_pybit && this.pybit && this.pybit.enabled) {
                        this.pybit.bybit_request("POST", "/v5/order/cancel-all", {
                            category: "linear",
                            symbol: this.symbol,
                            orderLinkId: position.link_prefix + "_entry" // For example, cancel by entry link prefix
                        }, true); // Signed request
                    }
                }
            }
        }
        
        // Remove closed positions by creating a new list
        this.open_positions = this.open_positions.filter((_, index) => !positions_to_close_indices.includes(index));
    }
    
    get_open_positions() {
        return this.open_positions.filter(pos => pos.status === "OPEN");
    }
    
    trail_stop(pos, current_price, atr_value) {
        // This is for simulated positions primarily, live trailing stops are typically set on exchange
        if (pos.status !== 'OPEN' || this.config.execution.use_pybit) return; 
        
        const atr_mult = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const side = pos.side;
        pos.best_price = pos.best_price || pos.entry_price; // Initialize if not present
        let new_sl = pos.stop_loss;
        
        if (side === "BUY") {
            pos.best_price = Decimal.max(pos.best_price, current_price);
            const calculated_sl = pos.best_price.minus(atr_mult.times(atr_value));
            if (calculated_sl.gt(new_sl)) {
                new_sl = calculated_sl;
                this.logger.debug(`${chalk.blue("Trailing BUY SL to ")}${new_sl.toFixed(2)}${chalk.reset()}`);
            }
        } else { // SELL
            pos.best_price = Decimal.min(pos.best_price, current_price);
            const calculated_sl = pos.best_price.plus(atr_mult.times(atr_value));
            if (calculated_sl.lt(new_sl)) {
                new_sl = calculated_sl;
                this.logger.debug(`${chalk.blue("Trailing SELL SL to ")}${new_sl.toFixed(2)}${chalk.reset()}`);
            }
        }
        
        pos.stop_loss = round_price(new_sl, this.price_precision);
    }
    
    async try_pyramid(current_price, atr_value) {
        if (!this.trade_management_enabled || !this.open_positions.length || this.config.pyramiding.enabled === false) return; 
        
        const py_cfg = this.config.pyramiding;
        if (!py_cfg.enabled) return;
        
        for (const pos of this.open_positions) {
            if (pos.status !== "OPEN") continue;
            const adds = pos.adds || 0;
            if (adds >= py_cfg.max_adds) continue;
            
            const step_atr_mult = new Decimal(py_cfg.step_atr);
            const step_distance = step_atr_mult.times(atr_value);
            let target_price = new Decimal("0");
            
            if (pos.side === "BUY") {
                target_price = pos.entry_price.plus(step_distance.times(new Decimal(adds).plus(1)));
            } else { // SELL
                target_price = pos.entry_price.minus(step_distance.times(new Decimal(adds).plus(1)));
            }
            
            let should_add = false;
            if (pos.side === "BUY" && current_price.gte(target_price)) {
                should_add = true;
            } else if (pos.side === "SELL" && current_price.lte(target_price)) {
                should_add = true;
            }
            
            if (should_add) {
                const size_pct_of_initial = new Decimal(py_cfg.size_pct_of_initial);
                const add_qty = round_qty(pos.qty.times(size_pct_of_initial), this.qty_step);
                
                if (add_qty.gt(0)) {
                    // Update average entry price and total quantity
                    const total_cost = (pos.qty.times(pos.entry_price)).plus(add_qty.times(current_price));
                    pos.qty = pos.qty.plus(add_qty);
                    pos.entry_price = total_cost.dividedBy(pos.qty);
                    pos.adds = adds + 1; // Increment add count
                    this.logger.info(`${chalk.green("Pyramiding add #")}${pos.adds} qty=${add_qty.normalize()}. New avg price: ${pos.entry_price.normalize().toFixed(this.price_precision)}${chalk.reset()}`);
                    
                    // For live trading, place an actual order for pyramiding
                    if (this.config.execution.use_pybit && this.pybit && this.pybit.enabled) {
                        try {
                            const resp = await this.pybit.place_order(
                                this.symbol, 
                                this.pybit._side_to_bybit(pos.side), 
                                "Market", 
                                add_qty, 
                                null, 
                                pos.stop_loss, 
                                pos.take_profit
                            );
                            if (resp && resp.orderId) {
                                this.logger.info(`${chalk.green("Live pyramiding order placed (Order ID: ")}${resp.orderId}).${chalk.reset()}`);
                            }
                        } catch (e) {
                            this.logger.error(`${chalk.red("Exception during live pyramiding: ")}${e.message}${chalk.reset()}`);
                        }
                    }
                }
            }
        }
    }
}

// --- Performance Tracking ---
class PerformanceTracker {
    constructor(logger, config) {
        this.logger = logger;
        this.config = config;
        this.trades = [];
        this.total_pnl = new Decimal("0");
        this.gross_profit = new Decimal("0");
        this.gross_loss = new Decimal("0");
        this.wins = 0;
        this.losses = 0;
        this.peak_pnl = new Decimal("0");
        this.max_drawdown = new Decimal("0");
        this.trading_fee_percent = new Decimal(config.trade_management.trading_fee_percent);
    }
    
    record_trade(position, pnl) {
        const trade_record = {
            "entry_time": position.entry_time,
            "exit_time": position.exit_time,
            "symbol": position.symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": position.exit_price,
            "qty": position.qty,
            "pnl_gross": pnl,
            "closed_by": position.closed_by,
        };
        
        const entry_fee_amount = position.entry_price.times(position.qty).times(this.trading_fee_percent);
        const exit_fee_amount = position.exit_price.times(position.qty).times(this.trading_fee_percent);
        const total_fees = entry_fee_amount.plus(exit_fee_amount);
        
        const pnl_net = pnl.minus(total_fees);
        trade_record.fees = total_fees;
        trade_record.pnl_net = pnl_net;
        
        this.trades.push(trade_record);
        this.total_pnl = this.total_pnl.plus(pnl_net);
        
        if (pnl_net.gt(0)) {
            this.wins += 1;
            this.gross_profit = this.gross_profit.plus(pnl_net);
        } else {
            this.losses += 1;
            this.gross_loss = this.gross_loss.plus(pnl_net.abs());
        }
        
        if (this.total_pnl.gt(this.peak_pnl)) this.peak_pnl = this.total_pnl;
        const drawdown = this.peak_pnl.minus(this.total_pnl);
        if (drawdown.gt(this.max_drawdown)) this.max_drawdown = drawdown;
        
        this.logger.info(
            `${chalk.cyan("Trade recorded. Gross PnL: ")}${pnl.normalize().toFixed(4)}, Fees: ${total_fees.normalize().toFixed(4)}, Net PnL: ${pnl_net.normalize().toFixed(4)}. ` +
            `Total PnL: ${this.total_pnl.normalize().toFixed(4)}${chalk.reset()}`
        );
    }
    
    day_pnl() {
        const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
        let pnl_for_day = new Decimal("0");
        
        for (const t of this.trades) {
            const trade_date = t.exit_time ? t.exit_time.toISOString().slice(0, 10) : t.entry_time.toISOString().slice(0, 10);
            if (trade_date === today) {
                pnl_for_day = pnl_for_day.plus(t.pnl_net || new Decimal("0"));
            }
        }
        
        return pnl_for_day;
    }
    
    get_summary() {
        const total_trades = this.trades.length;
        const win_rate = total_trades > 0 ? (this.wins / total_trades) * 100 : 0;
        const profit_factor = this.gross_loss.gt(0) ? this.gross_profit.dividedBy(this.gross_loss) : new Decimal("Infinity");
        const avg_win = this.wins > 0 ? this.gross_profit.dividedBy(this.wins) : new Decimal("0");
        const avg_loss = this.losses > 0 ? this.gross_loss.dividedBy(this.losses) : new Decimal("0");
        
        return {
            "total_trades": total_trades,
            "total_pnl": this.total_pnl,
            "gross_profit": this.gross_profit,
            "gross_loss": this.gross_loss,
            "profit_factor": profit_factor,
            "max_drawdown": this.max_drawdown,
            "wins": this.wins,
            "losses": this.losses,
            "win_rate": `${win_rate.toFixed(2)}%`,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        };
    }
}

// --- Alert System ---
class AlertSystem {
    constructor(logger) {
        this.logger = logger;
        this.termux_api_available = this._check_termux_api();
    }
    
    _check_termux_api() {
        try {
            // Check if 'which termux-toast' returns a path
            execSync('which termux-toast', { stdio: 'pipe' });
            return true;
        } catch (e) {
            this.logger.warn(`${chalk.yellow("The 'termux-toast' command was not found. Termux toast notifications will be disabled.")}${chalk.reset()}`);
            return false;
        }
    }
    
    send_alert(message, level = "INFO") {
        if (level === "INFO") {
            this.logger.info(`${chalk.blue("ALERT [INFO]: ")}${message}${chalk.reset()}`);
        } else if (level === "WARNING") {
            this.logger.warning(`${chalk.yellow("ALERT [WARNING]: ")}${message}${chalk.reset()}`);
        } else if (level === "ERROR") {
            this.logger.error(`${chalk.red("ALERT [ERROR]: ")}${message}${chalk.reset()}`);
        } else {
            this.logger.info(`ALERT [${level.toUpperCase()}]: ${message}`);
        }
        
        if (this.termux_api_available) {
            try {
                const toast_message_prefix = {
                    "INFO": "ℹ️ ",
                    "WARNING": "⚠️ ",
                    "ERROR": "⛔ ",
                }[level] || "";
                
                execSync(`termux-toast "${toast_message_prefix}${message}"`, { timeout: 5000 });
                this.logger.debug("Termux toast alert sent.");
            } catch (e) {
                this.logger.error(`${chalk.red("An error occurred while sending Termux toast: ")}${e.message}${chalk.reset()}`);
            }
        }
    }
}

// --- Trading Analysis ---
class TradingAnalyzer {
    constructor(df_raw, config, logger, symbol) {
        // Convert raw data (array of objects) to an internal format usable by indicator functions
        this.df = this._process_dataframe(df_raw); 
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.fib_levels = {};
        this.weights = config.weight_sets.default_scalping;
        this.indicator_settings = config.indicator_settings;
        
        if (this.df.close.length === 0) { // Check length of a core column
            this.logger.warning(`${chalk.yellow("TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.")}${chalk.reset()}`);
            return;
        }
        
        this._calculate_all_indicators();
        
        if (this.config.indicators.fibonacci_levels) {
            this.calculate_fibonacci_levels();
        }
        
        if (this.config.indicators.fibonacci_pivot_points) {
            this.calculate_fibonacci_pivot_points();
        }
    }
    
    _process_dataframe(df_raw) {
        // Convert array of kline objects into object of arrays with Decimal values
        const processed_df = {
            start_time: [], 
            open: [], 
            high: [], 
            low: [], 
            close: [], 
            volume: [], 
            turnover: []
        };
        
        df_raw.forEach(row => {
            processed_df.start_time.push(row.start_time);
            processed_df.open.push(new Decimal(row.open));
            processed_df.high.push(new Decimal(row.high));
            processed_df.low.push(new Decimal(row.low));
            processed_df.close.push(new Decimal(row.close));
            processed_df.volume.push(new Decimal(row.volume));
            processed_df.turnover.push(new Decimal(row.turnover));
        });
        
        // Add a .length property for compatibility with pandas len(df) checks
        processed_df.length = processed_df.close.length;
        
        // Add .iloc for pandas-like access for specific indicators
        processed_df.iloc = (index) => {
            if (index < 0) index = processed_df.length + index; // Handle negative indexing
            const row = {};
            for (const key in processed_df) {
                if (Array.isArray(processed_df[key])) {
                    row[key] = processed_df[key][index];
                }
            }
            return row;
        };
        
        return processed_df;
    }
    
    _safe_calculate(func, name, min_data_points, ...args) {
        if (this.df.length < min_data_points) {
            this.logger.debug(`${chalk.blue("Skipping indicator '")}${name}${chalk.blue("': Not enough data. Need ")}${min_data_points}${chalk.blue(", have ")}${this.df.length}${chalk.blue(".")}${chalk.reset()}`);
            return null;
        }
        
        try {
            // All indicator functions now directly use the `this.df` structure
            const result = func(this.df, this.indicator_settings, this.logger, this.symbol, ...args);
            
            // Check if result is empty or invalid
            const is_empty = (
                result === null ||
                (Array.isArray(result) && result.length === 0) || // For array of values
                (typeof result === 'object' && result !== null && Object.keys(result).length === 0) || // For empty object
                (result instanceof Decimal && result.isNaN()) // For single Decimal.js NaN
            );
            
            if (is_empty) {
                this.logger.warning(`${chalk.yellow("Indicator '")}${name}${chalk.yellow("' returned empty or None after calculation. Not enough valid data?")}${chalk.reset()}`);
            }
            
            return result;
        } catch (e) {
            this.logger.error(`${chalk.red("Error calculating indicator '")}${name}${chalk.red("': ")}${e.message}${chalk.reset()}`);
            return null;
        }
    }
    
    _calculate_all_indicators() {
        this.logger.debug(`${chalk.blue("Calculating all technical indicators...")}${chalk.reset()}`);
        const cfg_indicators = this.config.indicators;
        const isd = this.indicator_settings;
        
        // SMA
        if (cfg_indicators.sma_10) {
            const sma_10 = this._safe_calculate(indicators.calculate_sma, "SMA_10", isd.sma_short_period, isd.sma_short_period);
            if (sma_10 !== null && sma_10.length > 0) this.indicator_values["SMA_10"] = sma_10[sma_10.length - 1];
        }
        
        if (cfg_indicators.sma_trend_filter) {
            const sma_long = this._safe_calculate(indicators.calculate_sma, "SMA_Long", isd.sma_long_period, isd.sma_long_period);
            if (sma_long !== null && sma_long.length > 0) this.indicator_values["SMA_Long"] = sma_long[sma_long.length - 1];
        }
        
        // EMA
        if (cfg_indicators.ema_alignment) {
            const ema_short = this._safe_calculate(indicators.calculate_ema, "EMA_Short", isd.ema_short_period, isd.ema_short_period);
            const ema_long = this._safe_calculate(indicators.calculate_ema, "EMA_Long", isd.ema_long_period, isd.ema_long_period);
            if (ema_short !== null && ema_short.length > 0) this.indicator_values["EMA_Short"] = ema_short[ema_short.length - 1];
            if (ema_long !== null && ema_long.length > 0) this.indicator_values["EMA_Long"] = ema_long[ema_long.length - 1];
        }
        
        // ATR (TR is calculated internally by ATR)
        if (cfg_indicators.atr) {
            const atr = this._safe_calculate(indicators.calculate_atr, "ATR", isd.atr_period, isd.atr_period);
            if (atr !== null && atr.length > 0) this.indicator_values["ATR"] = atr[atr.length - 1];
        }
        
        // RSI
        if (cfg_indicators.rsi) {
            const rsi = this._safe_calculate(indicators.calculate_rsi, "RSI", isd.rsi_period + 1, isd.rsi_period);
            if (rsi !== null && rsi.length > 0) this.indicator_values["RSI"] = rsi[rsi.length - 1];
        }
        
        // StochRSI
        if (cfg_indicators.stoch_rsi) {
            const stoch_rsi_k_d = this._safe_calculate(indicators.calculate_stoch_rsi, "StochRSI", 
                                                    isd.stoch_rsi_period + isd.stoch_k_period + isd.stoch_d_period,
                                                    isd.stoch_rsi_period, isd.stoch_k_period, isd.stoch_d_period);
            if (stoch_rsi_k_d !== null) {
                this.indicator_values["StochRSI_K"] = stoch_rsi_k_d.k[stoch_rsi_k_d.k.length - 1];
                this.indicator_values["StochRSI_D"] = stoch_rsi_k_d.d[stoch_rsi_k_d.d.length - 1];
            }
        }
        
        // Bollinger Bands
        if (cfg_indicators.bollinger_bands) {
            const bb_bands = this._safe_calculate(indicators.calculate_bollinger_bands, "BollingerBands", 
                                                    isd.bollinger_bands_period,
                                                    isd.bollinger_bands_period, isd.bollinger_bands_std_dev);
            if (bb_bands !== null) {
                this.indicator_values["BB_Upper"] = bb_bands.upper[bb_bands.upper.length - 1];
                this.indicator_values["BB_Middle"] = bb_bands.middle[bb_bands.middle.length - 1];
                this.indicator_values["BB_Lower"] = bb_bands.lower[bb_bands.lower.length - 1];
            }
        }
        
        // CCI
        if (cfg_indicators.cci) {
            const cci = this._safe_calculate(indicators.calculate_cci, "CCI", isd.cci_period, isd.cci_period);
            if (cci !== null && cci.length > 0) this.indicator_values["CCI"] = cci[cci.length - 1];
        }
        
        // Williams %R
        if (cfg_indicators.wr) {
            const wr = this._safe_calculate(indicators.calculate_williams_r, "WR", isd.williams_r_period, isd.williams_r_period);
            if (wr !== null && wr.length > 0) this.indicator_values["WR"] = wr[wr.length - 1];
        }
        
        // MFI
        if (cfg_indicators.mfi) {
            const mfi = this._safe_calculate(indicators.calculate_mfi, "MFI", isd.mfi_period + 1, isd.mfi_period);
            if (mfi !== null && mfi.length > 0) this.indicator_values["MFI"] = mfi[mfi.length - 1];
        }
        
        // OBV
        if (cfg_indicators.obv) {
            const obv_ema_vals = this._safe_calculate(indicators.calculate_obv, "OBV", isd.obv_ema_period, isd.obv_ema_period);
            if (obv_ema_vals !== null) {
                this.indicator_values["OBV"] = obv_ema_vals.obv[obv_ema_vals.obv.length - 1];
                this.indicator_values["OBV_EMA"] = obv_ema_vals.obv_ema[obv_ema_vals.obv_ema.length - 1];
            }
        }
        
        // CMF
        if (cfg_indicators.cmf) {
            const cmf = this._safe_calculate(indicators.calculate_cmf, "CMF", isd.cmf_period, isd.cmf_period);
            if (cmf !== null && cmf.length > 0) this.indicator_values["CMF"] = cmf[cmf.length - 1];
        }
        
        // Ichimoku Cloud
        if (cfg_indicators.ichimoku_cloud) {
            const ichimoku_components = this._safe_calculate(indicators.calculate_ichimoku_cloud, "IchimokuCloud",
                                                            Math.max(isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period) + isd.ichimoku_chikou_span_offset,
                                                            isd.ichimoku_tenkan_period, isd.ichimoku_kijun_period, isd.ichimoku_senkou_span_b_period, isd.ichimoku_chikou_span_offset);
            if (ichimoku_components !== null) {
                this.indicator_values["Tenkan_Sen"] = ichimoku_components.tenkan_sen[ichimoku_components.tenkan_sen.length - 1];
                this.indicator_values["Kijun_Sen"] = ichimoku_components.kijun_sen[ichimoku_components.kijun_sen.length - 1];
                this.indicator_values["Senkou_Span_A"] = ichimoku_components.senkou_span_a[ichimoku_components.senkou_span_a.length - 1];
                this.indicator_values["Senkou_Span_B"] = ichimoku_components.senkou_span_b[ichimoku_components.senkou_span_b.length - 1];
                this.indicator_values["Chikou_Span"] = ichimoku_components.chikou_span[ichimoku_components.chikou_span.length - 1];
            }
        }
        
        // PSAR
        if (cfg_indicators.psar) {
            const psar_vals = this._safe_calculate(indicators.calculate_psar, "PSAR", MIN_DATA_POINTS_PSAR,
                                                  isd.psar_acceleration, isd.psar_max_acceleration);
            if (psar_vals !== null) {
                this.indicator_values["PSAR_Val"] = psar_vals.psar[psar_vals.psar.length - 1];
                this.indicator_values["PSAR_Dir"] = psar_vals.direction[psar_vals.direction.length - 1];
            }
        }
        
        // VWAP
        if (cfg_indicators.vwap) {
            const vwap = this._safe_calculate(indicators.calculate_vwap, "VWAP", 1);
            if (vwap !== null && vwap.length > 0) this.indicator_values["VWAP"] = vwap[vwap.length - 1];
        }
        
        // Ehlers SuperTrend
        if (cfg_indicators.ehlers_supertrend) {
            const st_fast_result = this._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast",
                                                        isd.ehlers_fast_period * 3, isd.ehlers_fast_period, isd.ehlers_fast_multiplier);
            if (st_fast_result !== null && st_fast_result.direction.length > 0) {
                this.indicator_values["ST_Fast_Dir"] = st_fast_result.direction[st_fast_result.direction.length - 1];
                this.indicator_values["ST_Fast_Val"] = st_fast_result.supertrend[st_fast_result.supertrend.length - 1];
            }
            
            const st_slow_result = this._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow",
                                                        isd.ehlers_slow_period * 3, isd.ehlers_slow_period, isd.ehlers_slow_multiplier);
            if (st_slow_result !== null && st_slow_result.direction.length > 0) {
                this.indicator_values["ST_Slow_Dir"] = st_slow_result.direction[st_slow_result.direction.length - 1];
                this.indicator_values["ST_Slow_Val"] = st_slow_result.supertrend[st_slow_result.supertrend.length - 1];
            }
        }
        
        // MACD
        if (cfg_indicators.macd) {
            const macd_vals = this._safe_calculate(indicators.calculate_macd, "MACD",
                                                  isd.macd_slow_period + isd.macd_signal_period,
                                                  isd.macd_fast_period, isd.macd_slow_period, isd.macd_signal_period);
            if (macd_vals !== null) {
                this.indicator_values["MACD_Line"] = macd_vals.macd_line[macd_vals.macd_line.length - 1];
                this.indicator_values["MACD_Signal"] = macd_vals.signal_line[macd_vals.signal_line.length - 1];
                this.indicator_values["MACD_Hist"] = macd_vals.histogram[macd_vals.histogram.length - 1];
            }
        }
        
        // ADX
        if (cfg_indicators.adx) {
            const adx_vals = this._safe_calculate(indicators.calculate_adx, "ADX", isd.adx_period * 2, isd.adx_period);
            if (adx_vals !== null) {
                this.indicator_values["ADX"] = adx_vals.adx[adx_vals.adx.length - 1];
                this.indicator_values["PlusDI"] = adx_vals.plus_di[adx_vals.plus_di.length - 1];
                this.indicator_values["MinusDI"] = adx_vals.minus_di[adx_vals.minus_di.length - 1];
            }
        }
        
        // Volatility Index
        if (cfg_indicators.volatility_index) {
            const vol_idx = this._safe_calculate(indicators.calculate_volatility_index, "Volatility_Index", isd.volatility_index_period, isd.volatility_index_period);
            if (vol_idx !== null && vol_idx.length > 0) this.indicator_values["Volatility_Index"] = vol_idx[vol_idx.length - 1];
        }
        
        // VWMA
        if (cfg_indicators.vwma) {
            const vwma = this._safe_calculate(indicators.calculate_vwma, "VWMA", isd.vwma_period, isd.vwma_period);
            if (vwma !== null && vwma.length > 0) this.indicator_values["VWMA"] = vwma[vwma.length - 1];
        }
        
        // Volume Delta
        if (cfg_indicators.volume_delta) {
            const vol_delta = this._safe_calculate(indicators.calculate_volume_delta, "Volume_Delta", isd.volume_delta_period, isd.volume_delta_period);
            if (vol_delta !== null && vol_delta.length > 0) this.indicator_values["Volume_Delta"] = vol_delta[vol_delta.length - 1];
        }
        
        // Kaufman AMA
        if (cfg_indicators.kaufman_ama) {
            const kama = this._safe_calculate(indicators.calculate_kaufman_ama, "Kaufman_AMA",
                                              isd.kama_period + isd.kama_slow_period,
                                              isd.kama_period, isd.kama_fast_period, isd.kama_slow_period);
            if (kama !== null && kama.length > 0) this.indicator_values["Kaufman_AMA"] = kama[kama.length - 1];
        }
        
        // Relative Volume
        if (cfg_indicators.relative_volume) {
            const rv = this._safe_calculate(indicators.calculate_relative_volume, "Relative_Volume", isd.relative_volume_period, isd.relative_volume_period);
            if (rv !== null && rv.length > 0) this.indicator_values["Relative_Volume"] = rv[rv.length - 1];
        }
        
        // Market Structure
        if (cfg_indicators.market_structure) {
            const ms_trend = this._safe_calculate(indicators.calculate_market_structure, "Market_Structure",
                                                  isd.market_structure_lookback_period * 2, isd.market_structure_lookback_period);
            if (ms_trend !== null && ms_trend.length > 0) this.indicator_values["Market_Structure_Trend"] = ms_trend[ms_trend.length - 1];
        }
        
        // DEMA
        if (cfg_indicators.dema) {
            const dema = this._safe_calculate(indicators.calculate_dema, "DEMA", isd.dema_period * 2, this.df.close, isd.dema_period);
            if (dema !== null && dema.length > 0) this.indicator_values["DEMA"] = dema[dema.length - 1];
        }
        
        // Keltner Channels
        if (cfg_indicators.keltner_channels) {
            const kc_bands = this._safe_calculate(indicators.calculate_keltner_channels, "KeltnerChannels",
                                                  isd.keltner_period + isd.atr_period,
                                                  isd.keltner_period, isd.keltner_atr_multiplier, isd.atr_period);
            if (kc_bands !== null) {
                this.indicator_values["Keltner_Upper"] = kc_bands.upper[kc_bands.upper.length - 1];
                this.indicator_values["Keltner_Middle"] = kc_bands.middle[kc_bands.middle.length - 1];
                this.indicator_values["Keltner_Lower"] = kc_bands.lower[kc_bands.lower.length - 1];
            }
        }
        
        // ROC
        if (cfg_indicators.roc) {
            const roc = this._safe_calculate(indicators.calculate_roc, "ROC", isd.roc_period + 1, isd.roc_period);
            if (roc !== null && roc.length > 0) this.indicator_values["ROC"] = roc[roc.length - 1];
        }
        
        // Candlestick Patterns
        if (cfg_indicators.candlestick_patterns) {
            const patterns = this._safe_calculate(indicators.detect_candlestick_patterns, "Candlestick_Patterns", MIN_CANDLESTICK_PATTERNS_BARS);
            if (patterns !== null && patterns.length > 0) this.indicator_values["Candlestick_Pattern"] = patterns[patterns.length - 1];
        }
        
        // Final cleanup for indicator values
        for (const key in this.indicator_values) {
            const val = this.indicator_values[key];
            if (Array.isArray(val) && val.length === 0) { // If an indicator result was an empty array
                this.indicator_values[key] = new Decimal(NaN);
            } else if (val === null || (val instanceof Decimal && val.isNaN())) { // Or null/NaN
                 this.indicator_values[key] = new Decimal(NaN);
            }
        }
        
        this.logger.debug(`${chalk.blue("Indicators calculated. Final indicator_values:")}${JSON.stringify(this.indicator_values, null, 2)}${chalk.reset()}`);
    }
    
    calculate_fibonacci_levels() {
        const window = this.config.indicator_settings.fibonacci_window;
        const fib_levels = indicators.calculate_fibonacci_levels(this.df, window);
        if (fib_levels) {
            this.fib_levels = fib_levels;
        } else {
            this.logger.warning(`${chalk.yellow("[")}${this.symbol}${chalk.yellow("] Fibonacci retracement levels could not be calculated.")}${chalk.reset()}`);
        }
    }
    
    calculate_fibonacci_pivot_points() {
        if (this.df.length < 2) {
            this.logger.warning(`${chalk.yellow("[")}${this.symbol}${chalk.yellow("] DataFrame is too short for Fibonacci Pivot Points calculation. Need at least 2 bars.")}${chalk.reset()}`);
            return;
        }
        
        const pivot_data = indicators.calculate_fibonacci_pivot_points(this.df);
        if (pivot_data) {
            const price_precision_str = "0." + "0" * (this.config.trade_management.price_precision - 1) + "1";
            this.indicator_values["Pivot"] = pivot_data.pivot.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.indicator_values["R1"] = pivot_data.r1.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.indicator_values["R2"] = pivot_data.r2.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.indicator_values["S1"] = pivot_data.s1.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.indicator_values["S2"] = pivot_data.s2.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.logger.debug(`${chalk.blue("[")}${this.symbol}${chalk.blue("] Calculated Fibonacci Pivot Points.")}${chalk.reset()}`);
        } else {
            this.logger.warning(`${chalk.yellow("[")}${this.symbol}${chalk.yellow("] Fibonacci Pivot Points could not be calculated.")}${chalk.reset()}`);
        }
    }
    
    _get_indicator_value(key, default_value = new Decimal(NaN)) {
        const value = this.indicator_values[key];
        return (value instanceof Decimal && !value.isNaN()) ? value : default_value;
    }
    
    _check_orderbook(orderbook_data) {
        if (!orderbook_data || !orderbook_data.b || !orderbook_data.a) return 0.0;
        
        const bids = orderbook_data.b;
        const asks = orderbook_data.a;
        const bid_volume = bids.reduce((sum, b) => sum.plus(new Decimal(b[1])), new Decimal("0"));
        const ask_volume = asks.reduce((sum, a) => sum.plus(new Decimal(a[1])), new Decimal("0"));
        
        if (bid_volume.plus(ask_volume).isZero()) return 0.0;
        
        const imbalance = bid_volume.minus(ask_volume).dividedBy(bid_volume.plus(ask_volume));
        this.logger.debug(`${chalk.blue("[")}${this.symbol}${chalk.blue("] Orderbook Imbalance: ")}${imbalance.toFixed(4)} (Bids: ${bid_volume.toFixed(2)}, Asks: ${ask_volume.toFixed(2)})${chalk.reset()}`);
        return imbalance.toNumber();
    }
    
    calculate_support_resistance_from_orderbook(orderbook_data) {
        if (!orderbook_data || !orderbook_data.b || !orderbook_data.a) return;
        
        const bids = orderbook_data.b;
        const asks = orderbook_data.a;
        
        let max_bid_volume = new Decimal("0");
        let support_level = new Decimal("0");
        for (const [bid_price_str, bid_volume_str] of bids) {
            const bid_volume_decimal = new Decimal(bid_volume_str);
            if (bid_volume_decimal.gt(max_bid_volume)) {
                max_bid_volume = bid_volume_decimal;
                support_level = new Decimal(bid_price_str);
            }
        }
        
        let max_ask_volume = new Decimal("0");
        let resistance_level = new Decimal("0");
        for (const [ask_price_str, ask_volume_str] of asks) {
            const ask_volume_decimal = new Decimal(ask_volume_str);
            if (ask_volume_decimal.gt(max_ask_volume)) {
                max_ask_volume = ask_volume_decimal;
                resistance_level = new Decimal(ask_price_str);
            }
        }
        
        const price_precision_str = "0." + "0" * (this.config.trade_management.price_precision - 1) + "1";
        if (support_level.gt(0)) {
            this.indicator_values["Support_Level"] = support_level.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.logger.debug(`${chalk.blue("[")}${this.symbol}${chalk.blue("] Identified Support Level: ")}${support_level.toString()} (Volume: ${max_bid_volume.toString()})${chalk.reset()}`);
        }
        if (resistance_level.gt(0)) {
            this.indicator_values["Resistance_Level"] = resistance_level.quantize(new Decimal(price_precision_str), Decimal.ROUND_DOWN);
            this.logger.debug(`${chalk.blue("[")}${this.symbol}${chalk.blue("] Identified Resistance Level: ")}${resistance_level.toString()} (Volume: ${max_ask_volume.toString()})${chalk.reset()}`);
        }
    }
    
    _get_mtf_trend(higher_tf_df_raw, indicator_type) {
        const higher_tf_df = this._process_dataframe(higher_tf_df_raw);
        if (higher_tf_df.length === 0) return "UNKNOWN";
        
        const last_close = higher_tf_df.close[higher_tf_df.close.length - 1];
        const period = this.config.mtf_analysis.trend_period;
        const indicator_settings = this.config.indicator_settings;
        
        // Use the shared indicator calculation functions
        if (indicator_type === "sma") {
            if (higher_tf_df.length < period) return "UNKNOWN";
            const sma = indicators.calculate_sma(higher_tf_df, period)[higher_tf_df.length - 1];
            if (last_close.gt(sma)) return "UP";
            if (last_close.lt(sma)) return "DOWN";
            return "SIDEWAYS";
        } else if (indicator_type === "ema") {
            if (higher_tf_df.length < period) return "UNKNOWN";
            const ema = indicators.calculate_ema(higher_tf_df, period)[higher_tf_df.length - 1];
            if (last_close.gt(ema)) return "UP";
            if (last_close.lt(ema)) return "DOWN";
            return "SIDEWAYS";
        } else if (indicator_type === "ehlers_supertrend") {
            const st_result = indicators.calculate_ehlers_supertrend(
                higher_tf_df,
                indicator_settings.ehlers_slow_period,
                indicator_settings.ehlers_slow_multiplier,
            );
            if (st_result !== null && st_result.direction.length > 0) {
                const st_dir = st_result.direction[st_result.direction.length - 1];
                if (st_dir === 1) return "UP";
                if (st_dir === -1) return "DOWN";
            }
            return "UNKNOWN";
        }
        return "UNKNOWN";
    }
    
    _score_adx(trend_strength_multiplier_in) {
        let adx_contrib = 0.0;
        const signal_breakdown_contrib = {};
        let trend_strength_multiplier_out = trend_strength_multiplier_in;
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        const isd = this.indicator_settings;
        
        if (cfg_indicators.adx) {
            const adx_val = this._get_indicator_value("ADX");
            const plus_di = this._get_indicator_value("PlusDI");
            const minus_di = this._get_indicator_value("MinusDI");
            const adx_weight = weights.adx_strength;
            
            if (!adx_val.isNaN() && !plus_di.isNaN() && !minus_di.isNaN()) {
                if (adx_val.gt(ADX_STRONG_TREND_THRESHOLD)) {
                    if (plus_di.gt(minus_di)) {
                        adx_contrib = adx_weight;
                        this.logger.debug(`${chalk.blue("ADX: Strong BUY trend (ADX > ")}${ADX_STRONG_TREND_THRESHOLD}${chalk.blue(", +DI > -DI).")}${chalk.reset()}`);
                        trend_strength_multiplier_out = 1.2;
                    } else if (minus_di.gt(plus_di)) {
                        adx_contrib = -adx_weight;
                        this.logger.debug(`${chalk.blue("ADX: Strong SELL trend (ADX > ")}${ADX_STRONG_TREND_THRESHOLD}${chalk.blue(", -DI > +DI).")}${chalk.reset()}`);
                        trend_strength_multiplier_out = 1.2;
                    }
                } else if (adx_val.lt(ADX_WEAK_TREND_THRESHOLD)) {
                    this.logger.debug(`${chalk.blue("ADX: Weak trend (ADX < ")}${ADX_WEAK_TREND_THRESHOLD}${chalk.blue("). Neutral signal.")}${chalk.reset()}`);
                    trend_strength_multiplier_out = 0.8;
                }
                signal_breakdown_contrib["ADX"] = adx_contrib;
            }
        }
        
        return { adx_contrib, trend_strength_multiplier_out, breakdown: signal_breakdown_contrib };
    }
    
    _score_ema_alignment(current_close, trend_multiplier) {
        let ema_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.ema_alignment) {
            const ema_short = this._get_indicator_value("EMA_Short");
            const ema_long = this._get_indicator_value("EMA_Long");
            
            if (!ema_short.isNaN() && !ema_long.isNaN()) {
                const weight = weights.ema_alignment * trend_multiplier;
                if (ema_short.gt(ema_long)) {
                    ema_contrib = weight;
                } else if (ema_short.lt(ema_long)) {
                    ema_contrib = -weight;
                }
                signal_breakdown_contrib["EMA Alignment"] = ema_contrib;
            }
        }
        
        return { ema_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_sma_trend_filter(current_close) {
        let sma_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.sma_trend_filter) {
            const sma_long = this._get_indicator_value("SMA_Long");
            if (!sma_long.isNaN()) {
                const weight = weights.sma_trend_filter;
                if (current_close.gt(sma_long)) {
                    sma_contrib = weight;
                } else if (current_close.lt(sma_long)) {
                    sma_contrib = -weight;
                }
                signal_breakdown_contrib["SMA Trend Filter"] = sma_contrib;
            }
        }
        
        return { sma_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_momentum_indicators() {
        let momentum_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const active_indicators = this.config.indicators;
        const isd = this.indicator_settings;
        const momentum_weight = this.weights.momentum_rsi_stoch_cci_wr_mfi;
        
        // RSI
        if (active_indicators.rsi) {
            const rsi = this._get_indicator_value("RSI");
            if (!rsi.isNaN()) {
                if (rsi.lt(isd.rsi_oversold)) momentum_contrib += momentum_weight * 0.5;
                else if (rsi.gt(isd.rsi_overbought)) momentum_contrib -= momentum_weight * 0.5;
                signal_breakdown_contrib["RSI"] = momentum_contrib;
            }
        }
        
        // StochRSI Crossover
        if (active_indicators.stoch_rsi) {
            const stoch_k = this._get_indicator_value("StochRSI_K");
            const stoch_d = this._get_indicator_value("StochRSI_D");
            
            if (!stoch_k.isNaN() && !stoch_d.isNaN() && this.df.length > 1) {
                const prev_stoch_k = this.df.iloc(this.df.length - 2).StochRSI_K;
                const prev_stoch_d = this.df.iloc(this.df.length - 2).StochRSI_D;
                let stoch_contrib = 0.0;
                
                if (stoch_k.gt(stoch_d) && prev_stoch_k.lte(prev_stoch_d) && stoch_k.lt(isd.stoch_rsi_oversold)) {
                    stoch_contrib = momentum_weight * 0.6;
                    this.logger.debug(`${chalk.blue("StochRSI: Bullish crossover from oversold.")}${chalk.reset()}`);
                } else if (stoch_k.lt(stoch_d) && prev_stoch_k.gte(prev_stoch_d) && stoch_k.gt(isd.stoch_rsi_overbought)) {
                    stoch_contrib = -momentum_weight * 0.6;
                    this.logger.debug(`${chalk.blue("StochRSI: Bearish crossover from overbought.")}${chalk.reset()}`);
                } else if (stoch_k.gt(stoch_d) && stoch_k.lt(STOCH_RSI_MID_POINT)) { // General bullish momentum
                    stoch_contrib = momentum_weight * 0.2;
                } else if (stoch_k.lt(stoch_d) && stoch_k.gt(STOCH_RSI_MID_POINT)) { // General bearish momentum
                    stoch_contrib = -momentum_weight * 0.2;
                }
                
                momentum_contrib += stoch_contrib;
                signal_breakdown_contrib["StochRSI Crossover"] = stoch_contrib;
            }
        }
        
        // CCI
        if (active_indicators.cci) {
            const cci = this._get_indicator_value("CCI");
            if (!cci.isNaN()) {
                let cci_contrib = 0.0;
                if (cci.lt(isd.cci_oversold)) cci_contrib = momentum_weight * 0.4;
                else if (cci.gt(isd.cci_overbought)) cci_contrib = -momentum_weight * 0.4;
                momentum_contrib += cci_contrib;
                signal_breakdown_contrib["CCI"] = cci_contrib;
            }
        }
        
        // Williams %R
        if (active_indicators.wr) {
            const wr = this._get_indicator_value("WR");
            if (!wr.isNaN()) {
                let wr_contrib = 0.0;
                if (wr.lt(isd.williams_r_oversold)) wr_contrib = momentum_weight * 0.4;
                else if (wr.gt(isd.williams_r_overbought)) wr_contrib = -momentum_weight * 0.4;
                momentum_contrib += wr_contrib;
                signal_breakdown_contrib["Williams %R"] = wr_contrib;
            }
        }
        
        // MFI
        if (active_indicators.mfi) {
            const mfi = this._get_indicator_value("MFI");
            if (!mfi.isNaN()) {
                let mfi_contrib = 0.0;
                if (mfi.lt(isd.mfi_oversold)) mfi_contrib = momentum_weight * 0.4;
                else if (mfi.gt(isd.mfi_overbought)) mfi_contrib = -momentum_weight * 0.4;
                momentum_contrib += mfi_contrib;
                signal_breakdown_contrib["MFI"] = mfi_contrib;
            }
        }
        
        return { momentum_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_bollinger_bands(current_close) {
        let bb_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.bollinger_bands) {
            const bb_upper = this._get_indicator_value("BB_Upper");
            const bb_lower = this._get_indicator_value("BB_Lower");
            
            if (!bb_upper.isNaN() && !bb_lower.isNaN()) {
                if (current_close.lt(bb_lower)) bb_contrib = weights.bollinger_bands * 0.5;
                else if (current_close.gt(bb_upper)) bb_contrib = -weights.bollinger_bands * 0.5;
                signal_breakdown_contrib["Bollinger Bands"] = bb_contrib;
            }
        }
        
        return { bb_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_vwap(current_close, prev_close) {
        let vwap_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.vwap) {
            const vwap = this._get_indicator_value("VWAP");
            if (!vwap.isNaN()) {
                if (current_close.gt(vwap)) vwap_contrib = weights.vwap * 0.2;
                else if (current_close.lt(vwap)) vwap_contrib = -weights.vwap * 0.2;
                
                if (this.df.length > 1) {
                    const prev_vwap = this.df.iloc(this.df.length - 2).VWAP;
                    if (current_close.gt(vwap) && prev_close.lte(prev_vwap)) {
                        vwap_contrib += weights.vwap * 0.3;
                        this.logger.debug(`${chalk.blue("VWAP: Bullish crossover detected.")}${chalk.reset()}`);
                    } else if (current_close.lt(vwap) && prev_close.gte(prev_vwap)) {
                        vwap_contrib -= weights.vwap * 0.3;
                        this.logger.debug(`${chalk.blue("VWAP: Bearish crossover detected.")}${chalk.reset()}`);
                    }
                }
                signal_breakdown_contrib["VWAP"] = vwap_contrib;
            }
        }
        
        return { vwap_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_psar(current_close, prev_close) {
        let psar_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.psar) {
            const psar_val = this._get_indicator_value("PSAR_Val");
            const psar_dir = this._get_indicator_value("PSAR_Dir");
            
            if (!psar_val.isNaN() && !psar_dir.isNaN()) {
                if (psar_dir === 1) psar_contrib = weights.psar * 0.5;
                else if (psar_dir === -1) psar_contrib = -weights.psar * 0.5;
                
                if (this.df.length > 1) {
                    const prev_psar_val = this.df.iloc(this.df.length - 2).PSAR_Val;
                    if (current_close.gt(psar_val) && prev_close.lte(prev_psar_val)) {
                        psar_contrib += weights.psar * 0.4;
                        this.logger.debug(`${chalk.blue("PSAR: Bullish reversal detected.")}${chalk.reset()}`);
                    } else if (current_close.lt(psar_val) && prev_close.gte(prev_psar_val)) {
                        psar_contrib -= weights.psar * 0.4;
                        this.logger.debug(`${chalk.blue("PSAR: Bearish reversal detected.")}${chalk.reset()}`);
                    }
                }
                signal_breakdown_contrib["PSAR"] = psar_contrib;
            }
        }
        
        return { psar_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_orderbook_imbalance(orderbook_data) {
        let imbalance_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        const current_close = this.df.close[this.df.close.length - 1];
        
        if (cfg_indicators.orderbook_imbalance && orderbook_data) {
            const imbalance = this._check_orderbook(orderbook_data);
            imbalance_contrib = imbalance * weights.orderbook_imbalance;
            signal_breakdown_contrib["Orderbook Imbalance"] = imbalance_contrib;
            this.calculate_support_resistance_from_orderbook(orderbook_data);
        }
        
        return { imbalance_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_fibonacci_levels(current_close, prev_close) {
        let fib_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.fibonacci_levels && this.fib_levels) {
            for (const level_name in this.fib_levels) {
                const level_price = this.fib_levels[level_name];
                if (level_name !== "0.0%" && level_name !== "100.0%" && current_close.gt(0) && current_close.minus(level_price).abs().dividedBy(current_close).lt(new Decimal("0.001"))) {
                    this.logger.debug(`${chalk.blue("Price near Fibonacci level ")}${level_name}: ${level_price.toFixed(2)}${chalk.reset()}`);
                    if (this.df.length > 1) {
                        if (current_close.gt(prev_close) && current_close.gt(level_price)) fib_contrib += weights.fibonacci_levels * 0.1;
                        else if (current_close.lt(prev_close) && current_close.lt(level_price)) fib_contrib -= weights.fibonacci_levels * 0.1;
                    }
                }
            }
            signal_breakdown_contrib["Fibonacci Levels"] = fib_contrib;
        }
        
        return { fib_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_fibonacci_pivot_points(current_close, prev_close) {
        let fib_pivot_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.fibonacci_pivot_points) {
            const pivot = this._get_indicator_value("Pivot");
            const r1 = this._get_indicator_value("R1");
            const r2 = this._get_indicator_value("R2");
            const s1 = this._get_indicator_value("S1");
            const s2 = this._get_indicator_value("S2");
            
            if (!pivot.isNaN() && !r1.isNaN() && !r2.isNaN() && !s1.isNaN() && !s2.isNaN()) {
                const weight = weights.fibonacci_pivot_points_confluence;
                
                // Bullish signals
                if (current_close.gt(r1) && prev_close.lte(r1)) fib_pivot_contrib += weight * 0.5;
                else if (current_close.gt(r2) && prev_close.lte(r2)) fib_pivot_contrib += weight * 1.0;
                else if (current_close.gt(pivot) && prev_close.lte(pivot)) fib_pivot_contrib += weight * 0.2;
                
                // Bearish signals
                else if (current_close.lt(s1) && prev_close.gte(s1)) fib_pivot_contrib -= weight * 0.5;
                else if (current_close.lt(s2) && prev_close.gte(s2)) fib_pivot_contrib -= weight * 1.0;
                else if (current_close.lt(pivot) && prev_close.gte(pivot)) fib_pivot_contrib -= weight * 0.2;
                
                signal_breakdown_contrib["Fibonacci Pivot Points"] = fib_pivot_contrib;
            }
        }
        
        return { fib_pivot_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_ehlers_supertrend(trend_multiplier) {
        let st_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.ehlers_supertrend) {
            const st_fast_dir = this._get_indicator_value("ST_Fast_Dir");
            const st_slow_dir = this._get_indicator_value("ST_Slow_Dir");
            const prev_st_fast_dir = this.df.length > 1 ? this.df.iloc(this.df.length - 2).ST_Fast_Dir : new Decimal(NaN);
            const weight = weights.ehlers_supertrend_alignment * trend_multiplier;
            
            if (!st_fast_dir.isNaN() && !st_slow_dir.isNaN() && !prev_st_fast_dir.isNaN()) {
                if (st_slow_dir === 1 && st_fast_dir === 1 && prev_st_fast_dir === -1) {
                    st_contrib = weight;
                    this.logger.debug(`${chalk.blue("Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend).")}${chalk.reset()}`);
                } else if (st_slow_dir === -1 && st_fast_dir === -1 && prev_st_fast_dir === 1) {
                    st_contrib = -weight;
                    this.logger.debug(`${chalk.blue("Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend).")}${chalk.reset()}`);
                } else if (st_slow_dir === 1 && st_fast_dir === 1) {
                    st_contrib = weight * 0.3;
                } else if (st_slow_dir === -1 && st_fast_dir === -1) {
                    st_contrib = -weight * 0.3;
                }
                signal_breakdown_contrib["Ehlers SuperTrend"] = st_contrib;
            }
        }
        
        return { st_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_macd(trend_multiplier) {
        let macd_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.macd) {
            const macd_line = this._get_indicator_value("MACD_Line");
            const signal_line = this._get_indicator_value("MACD_Signal");
            const histogram = this._get_indicator_value("MACD_Hist");
            const weight = weights.macd_alignment * trend_multiplier;
            
            if (!macd_line.isNaN() && !signal_line.isNaN() && !histogram.isNaN() && this.df.length > 1) {
                const prev_macd_line = this.df.iloc(this.df.length - 2).MACD_Line;
                const prev_signal_line = this.df.iloc(this.df.length - 2).MACD_Signal;
                
                if (macd_line.gt(signal_line) && prev_macd_line.lte(prev_signal_line)) {
                    macd_contrib = weight;
                    this.logger.debug(`${chalk.blue("MACD: BUY signal (MACD line crossed above Signal line).")}${chalk.reset()}`);
                } else if (macd_line.lt(signal_line) && prev_macd_line.gte(prev_signal_line)) {
                    macd_contrib = -weight;
                    this.logger.debug(`${chalk.blue("MACD: SELL signal (MACD line crossed below Signal line).")}${chalk.reset()}`);
                } else if (histogram.gt(0) && this.df.iloc(this.df.length - 2).MACD_Hist.lt(0)) {
                    macd_contrib = weight * 0.2;
                } else if (histogram.lt(0) && this.df.iloc(this.df.length - 2).MACD_Hist.gt(0)) {
                    macd_contrib = -weight * 0.2;
                }
                signal_breakdown_contrib["MACD"] = macd_contrib;
            }
        }
        
        return { macd_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_ichimoku_cloud(current_close, trend_multiplier) {
        let ichimoku_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.ichimoku_cloud) {
            const tenkan_sen = this._get_indicator_value("Tenkan_Sen");
            const kijun_sen = this._get_indicator_value("Kijun_Sen");
            const senkou_span_a = this._get_indicator_value("Senkou_Span_A");
            const senkou_span_b = this._get_indicator_value("Senkou_Span_B");
            const chikou_span = this._get_indicator_value("Chikou_Span");
            const weight = weights.ichimoku_confluence * trend_multiplier;
            
            if (!tenkan_sen.isNaN() && !kijun_sen.isNaN() && !senkou_span_a.isNaN() && !senkou_span_b.isNaN() && !chikou_span.isNaN() && this.df.length > 1) {
                const prev_tenkan_sen = this.df.iloc(this.df.length - 2).Tenkan_Sen;
                const prev_kijun_sen = this.df.iloc(this.df.length - 2).Kijun_Sen;
                const prev_senkou_span_a = this.df.iloc(this.df.length - 2).Senkou_Span_A;
                const prev_senkou_span_b = this.df.iloc(this.df.length - 2).Senkou_Span_B;
                const prev_chikou_span = this.df.iloc(this.df.length - 2).Chikou_Span;
                
                // Tenkan-sen / Kijun-sen crossover
                if (tenkan_sen.gt(kijun_sen) && prev_tenkan_sen.lte(prev_kijun_sen)) {
                    ichimoku_contrib += weight * 0.5;
                    this.logger.debug(`${chalk.blue("Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish).")}${chalk.reset()}`);
                } else if (tenkan_sen.lt(kijun_sen) && prev_tenkan_sen.gte(prev_kijun_sen)) {
                    ichimoku_contrib -= weight * 0.5;
                    this.logger.debug(`${chalk.blue("Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish).")}${chalk.reset()}`);
                }
                
                // Price breaks above/below Kumo (Cloud)
                const kumo_upper_prev = Decimal.max(prev_senkou_span_a, prev_senkou_span_b);
                const kumo_upper = Decimal.max(senkou_span_a, senkou_span_b);
                const kumo_lower_prev = Decimal.min(prev_senkou_span_a, prev_senkou_span_b);
                const kumo_lower = Decimal.min(senkou_span_a, senkou_span_b);
                
                if (current_close.gt(kumo_upper) && this.df.iloc(this.df.length - 2).close.lte(kumo_upper_prev)) {
                    ichimoku_contrib += weight * 0.7;
                    this.logger.debug(`${chalk.blue("Ichimoku: Price broke above Kumo (strong bullish).")}${chalk.reset()}`);
                } else if (current_close.lt(kumo_lower) && this.df.iloc(this.df.length - 2).close.gte(kumo_lower_prev)) {
                    ichimoku_contrib -= weight * 0.7;
                    this.logger.debug(`${chalk.blue("Ichimoku: Price broke below Kumo (strong bearish).")}${chalk.reset()}`);
                }
                
                // Chikou Span crossover price
                if (chikou_span.gt(current_close) && prev_chikou_span.lte(this.df.iloc(this.df.length - 2).close)) {
                    ichimoku_contrib += weight * 0.3;
                    this.logger.debug(`${chalk.blue("Ichimoku: Chikou Span crossed above price (bullish confirmation).")}${chalk.reset()}`);
                } else if (chikou_span.lt(current_close) && prev_chikou_span.gte(this.df.iloc(this.df.length - 2).close)) {
                    ichimoku_contrib -= weight * 0.3;
                    this.logger.debug(`${chalk.blue("Ichimoku: Chikou Span crossed below price (bearish confirmation).")}${chalk.reset()}`);
                }
                
                signal_breakdown_contrib["Ichimoku Cloud"] = ichimoku_contrib;
            }
        }
        
        return { ichimoku_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_obv() {
        let obv_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.obv) {
            const obv_val = this._get_indicator_value("OBV");
            const obv_ema = this._get_indicator_value("OBV_EMA");
            const weight = weights.obv_momentum;
            
            if (!obv_val.isNaN() && !obv_ema.isNaN() && this.df.length > 1) {
                const prev_obv_val = this.df.iloc(this.df.length - 2).OBV;
                const prev_obv_ema = this.df.iloc(this.df.length - 2).OBV_EMA;
                
                if (obv_val.gt(obv_ema) && prev_obv_val.lte(prev_obv_ema)) {
                    obv_contrib = weight * 0.5;
                    this.logger.debug(`${chalk.blue("OBV: Bullish crossover detected.")}${chalk.reset()}`);
                } else if (obv_val.lt(obv_ema) && prev_obv_val.gte(prev_obv_ema)) {
                    obv_contrib = -weight * 0.5;
                    this.logger.debug(`${chalk.blue("OBV: Bearish crossover detected.")}${chalk.reset()}`);
                }
                
                if (this.df.length > 2) {
                    const prev_prev_obv_val = this.df.iloc(this.df.length - 3).OBV;
                    if (obv_val.gt(this.df.iloc(this.df.length - 2).OBV) && this.df.iloc(this.df.length - 2).OBV.gt(prev_prev_obv_val)) {
                        obv_contrib += weight * 0.2;
                    } else if (obv_val.lt(this.df.iloc(this.df.length - 2).OBV) && this.df.iloc(this.df.length - 2).OBV.lt(prev_prev_obv_val)) {
                        obv_contrib -= weight * 0.2;
                    }
                }
                signal_breakdown_contrib["OBV"] = obv_contrib;
            }
        }
        
        return { obv_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_cmf() {
        let cmf_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.cmf) {
            const cmf_val = this._get_indicator_value("CMF");
            const weight = weights.cmf_flow;
            
            if (!cmf_val.isNaN()) {
                if (cmf_val.gt(0)) {
                    cmf_contrib = weight * 0.5;
                } else if (cmf_val.lt(0)) {
                    cmf_contrib = -weight * 0.5;
                }
                
                if (this.df.length > 2) {
                    const prev_cmf_val = this.df.iloc(this.df.length - 2).CMF;
                    const prev_prev_cmf_val = this.df.iloc(this.df.length - 3).CMF;
                    
                    if (cmf_val.gt(prev_cmf_val) && prev_cmf_val.gt(prev_prev_cmf_val)) {
                        cmf_contrib += weight * 0.3;
                    } else if (cmf_val.lt(prev_cmf_val) && prev_cmf_val.lt(prev_prev_cmf_val)) {
                        cmf_contrib -= weight * 0.3;
                    }
                }
                signal_breakdown_contrib["CMF"] = cmf_contrib;
            }
        }
        
        return { cmf_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_volatility_index(signal_score_current) {
        let vol_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.volatility_index) {
            const vol_idx = this._get_indicator_value("Volatility_Index");
            const weight = weights.volatility_index_signal;
            
            if (!vol_idx.isNaN()) {
                if (this.df.length > 2) {
                    const prev_vol_idx = this.df.iloc(this.df.length - 2).Volatility_Index;
                    const prev_prev_vol_idx = this.df.iloc(this.df.length - 3).Volatility_Index;
                    
                    if (vol_idx.gt(prev_vol_idx) && prev_vol_idx.gt(prev_prev_vol_idx)) { // Increasing volatility
                        this.logger.debug(`${chalk.blue("Volatility Index: Increasing volatility.")}${chalk.reset()}`);
                        if (signal_score_current > 0) vol_contrib = weight * 0.2;
                        else if (signal_score_current < 0) vol_contrib = -weight * 0.2;
                    } else if (vol_idx.lt(prev_vol_idx) && prev_vol_idx.lt(prev_prev_vol_idx)) { // Decreasing volatility
                        this.logger.debug(`${chalk.blue("Volatility Index: Decreasing volatility.")}${chalk.reset()}`);
                        if (Math.abs(signal_score_current) > 0) vol_contrib = signal_score_current * -0.2;
                    }
                }
                signal_breakdown_contrib["Volatility Index"] = vol_contrib;
            }
        }
        
        return { vol_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_vwma_cross(current_close, prev_close, trend_multiplier) {
        let vwma_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.vwma) {
            const vwma = this._get_indicator_value("VWMA");
            const weight = weights.vwma_cross;
            
            if (!vwma.isNaN() && this.df.length > 1) {
                const prev_vwma = this.df.iloc(this.df.length - 2).VWMA;
                
                if (current_close.gt(vwma) && prev_close.lte(prev_vwma)) { // Bullish crossover
                    vwma_contrib = weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("VWMA: Bullish crossover (price above VWMA).")}${chalk.reset()}`);
                } else if (current_close.lt(vwma) && prev_close.gte(prev_vwma)) { // Bearish crossover
                    vwma_contrib = -weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("VWMA: Bearish crossover (price below VWMA).")}${chalk.reset()}`);
                }
                signal_breakdown_contrib["VWMA Cross"] = vwma_contrib;
            }
        }
        
        return { vwma_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_volume_delta() {
        let vol_delta_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        const isd = this.indicator_settings;
        
        if (cfg_indicators.volume_delta) {
            const volume_delta = this._get_indicator_value("Volume_Delta");
            const volume_delta_threshold = new Decimal(isd.volume_delta_threshold);
            const weight = weights.volume_delta_signal;
            
            if (!volume_delta.isNaN()) {
                if (volume_delta.gt(volume_delta_threshold)) { // Strong buying pressure
                    vol_delta_contrib = weight;
                    this.logger.debug(`${chalk.blue("Volume Delta: Strong buying pressure detected.")}${chalk.reset()}`);
                } else if (volume_delta.lt(volume_delta_threshold.neg())) { // Strong selling pressure
                    vol_delta_contrib = -weight;
                    this.logger.debug(`${chalk.blue("Volume Delta: Strong selling pressure detected.")}${chalk.reset()}`);
                } else if (volume_delta.gt(0)) { // Moderate buying pressure
                    vol_delta_contrib = weight * 0.3;
                } else if (volume_delta.lt(0)) { // Moderate selling pressure
                    vol_delta_contrib = -weight * 0.3;
                }
                signal_breakdown_contrib["Volume Delta"] = vol_delta_contrib;
            }
        }
        
        return { vol_delta_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_kaufman_ama_cross(current_close, prev_close, trend_multiplier) {
        let kama_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.kaufman_ama) {
            const kama = this._get_indicator_value("Kaufman_AMA");
            const weight = weights.kaufman_ama_cross;
            
            if (!kama.isNaN() && this.df.length > 1) {
                const prev_kama = this.df.iloc(this.df.length - 2).Kaufman_AMA;
                
                if (current_close.gt(kama) && prev_close.lte(prev_kama)) { // Bullish crossover
                    kama_contrib = weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("KAMA: Bullish crossover (price above KAMA).")}${chalk.reset()}`);
                } else if (current_close.lt(kama) && prev_close.gte(prev_kama)) { // Bearish crossover
                    kama_contrib = -weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("KAMA: Bearish crossover (price below KAMA).")}${chalk.reset()}`);
                }
                signal_breakdown_contrib["Kaufman AMA Cross"] = kama_contrib;
            }
        }
        
        return { kama_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_relative_volume(current_close, prev_close) {
        let rv_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        const isd = this.indicator_settings;
        
        if (cfg_indicators.relative_volume) {
            const relative_volume = this._get_indicator_value("Relative_Volume");
            const volume_threshold = new Decimal(isd.relative_volume_threshold);
            const weight = weights.relative_volume_confirmation;
            
            if (!relative_volume.isNaN()) {
                if (relative_volume.gte(volume_threshold)) { // Significantly higher volume
                    if (current_close.gt(prev_close)) { // Bullish bar with high volume
                        rv_contrib = weight;
                        this.logger.debug(`${chalk.blue("Volume: High relative bullish volume (")}${relative_volume.toFixed(2)}${chalk.blue("x average).")}${chalk.reset()}`);
                    } else if (current_close.lt(prev_close)) { // Bearish bar with high volume
                        rv_contrib = -weight;
                        this.logger.debug(`${chalk.blue("Volume: High relative bearish volume (")}${relative_volume.toFixed(2)}${chalk.blue("x average).")}${chalk.reset()}`);
                    }
                }
                signal_breakdown_contrib["Relative Volume"] = rv_contrib;
            }
        }
        
        return { rv_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_market_structure(trend_multiplier) {
        let ms_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.market_structure) {
            const ms_trend = this._get_indicator_value("Market_Structure_Trend", "SIDEWAYS");
            const weight = weights.market_structure_confluence;
            
            if (ms_trend === "UP") {
                ms_contrib = weight * trend_multiplier;
                this.logger.debug(`${chalk.blue("Market Structure: Confirmed Uptrend.")}${chalk.reset()}`);
            } else if (ms_trend === "DOWN") {
                ms_contrib = -weight * trend_multiplier;
                this.logger.debug(`${chalk.blue("Market Structure: Confirmed Downtrend.")}${chalk.reset()}`);
            }
            signal_breakdown_contrib["Market Structure"] = ms_contrib;
        }
        
        return { ms_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_dema_crossover(trend_multiplier) {
        let dema_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.dema && cfg_indicators.ema_alignment) {
            const dema = this._get_indicator_value("DEMA");
            const ema_short = this._get_indicator_value("EMA_Short");
            const weight = weights.dema_crossover;
            
            if (!dema.isNaN() && !ema_short.isNaN() && this.df.length > 1) {
                const prev_dema = this.df.iloc(this.df.length - 2).DEMA;
                const prev_ema_short = this.df.iloc(this.df.length - 2).EMA_Short;
                
                if (dema.gt(ema_short) && prev_dema.lte(prev_ema_short)) {
                    dema_contrib = weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("DEMA: Bullish crossover (DEMA above EMA_Short).")}${chalk.reset()}`);
                } else if (dema.lt(ema_short) && prev_dema.gte(prev_ema_short)) {
                    dema_contrib = -weight * trend_multiplier;
                    this.logger.debug(`${chalk.blue("DEMA: Bearish crossover (DEMA below EMA_Short).")}${chalk.reset()}`);
                }
                signal_breakdown_contrib["DEMA Crossover"] = dema_contrib;
            }
        }
        
        return { dema_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_keltner_channels(current_close, prev_close) {
        let kc_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.keltner_channels) {
            const kc_upper = this._get_indicator_value("Keltner_Upper");
            const kc_lower = this._get_indicator_value("Keltner_Lower");
            const weight = weights.keltner_breakout;
            
            if (!kc_upper.isNaN() && !kc_lower.isNaN() && this.df.length > 1) {
                const prev_kc_upper = this.df.iloc(this.df.length - 2).Keltner_Upper;
                const prev_kc_lower = this.df.iloc(this.df.length - 2).Keltner_Lower;
                
                if (current_close.gt(kc_upper) && prev_close.lte(prev_kc_upper)) {
                    kc_contrib = weight;
                    this.logger.debug(`${chalk.blue("Keltner Channels: Bullish breakout above upper channel.")}${chalk.reset()}`);
                } else if (current_close.lt(kc_lower) && prev_close.gte(prev_kc_lower)) {
                    kc_contrib = -weight;
                    this.logger.debug(`${chalk.blue("Keltner Channels: Bearish breakout below lower channel.")}${chalk.reset()}`);
                }
                signal_breakdown_contrib["Keltner Channels"] = kc_contrib;
            }
        }
        
        return { kc_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_roc_signals(trend_multiplier) {
        let roc_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        const isd = this.indicator_settings;
        
        if (cfg_indicators.roc) {
            const roc = this._get_indicator_value("ROC");
            const weight = weights.roc_signal;
            
            if (!roc.isNaN()) {
                if (roc.lt(isd.roc_oversold)) { // Bullish signal from oversold
                    roc_contrib = weight * 0.7;
                    this.logger.debug(`${chalk.blue("ROC: Oversold (")}${roc.toFixed(2)}${chalk.blue("), potential bounce.")}${chalk.reset()}`);
                } else if (roc.gt(isd.roc_overbought)) { // Bearish signal from overbought
                    roc_contrib = -weight * 0.7;
                    this.logger.debug(`${chalk.blue("ROC: Overbought (")}${roc.toFixed(2)}${chalk.blue("), potential pullback.")}${chalk.reset()}`);
                }
                
                if (this.df.length > 1) { // Zero-line crossover (simple trend indication)
                    const prev_roc = this.df.iloc(this.df.length - 2).ROC;
                    if (roc.gt(0) && prev_roc.lte(0)) {
                        roc_contrib += weight * 0.3 * trend_multiplier; // Bullish zero-line cross
                        this.logger.debug(`${chalk.blue("ROC: Bullish zero-line crossover.")}${chalk.reset()}`);
                    } else if (roc.lt(0) && prev_roc.gte(0)) {
                        roc_contrib -= weight * 0.3 * trend_multiplier; // Bearish zero-line cross
                        this.logger.debug(`${chalk.blue("ROC: Bearish zero-line crossover.")}${chalk.reset()}`);
                    }
                }
                signal_breakdown_contrib["ROC"] = roc_contrib;
            }
        }
        
        return { roc_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_candlestick_patterns() {
        let cp_contrib = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_indicators = this.config.indicators;
        const weights = this.weights;
        
        if (cfg_indicators.candlestick_patterns) {
            const pattern = this._get_indicator_value("Candlestick_Pattern", "No Pattern");
            const weight = weights.candlestick_confirmation;
            
            if (pattern === "Bullish Engulfing" || pattern === "Bullish Hammer") {
                cp_contrib = weight;
                this.logger.debug(`${chalk.blue("Candlestick: Detected Bullish Pattern (")}${pattern}${chalk.blue(").")}${chalk.reset()}`);
            } else if (pattern === "Bearish Engulfing" || pattern === "Bearish Shooting Star") {
                cp_contrib = -weight;
                this.logger.debug(`${chalk.blue("Candlestick: Detected Bearish Pattern (")}${pattern}${chalk.blue(").")}${chalk.reset()}`);
            }
            signal_breakdown_contrib["Candlestick Pattern"] = cp_contrib;
        }
        
        return { cp_contrib, breakdown: signal_breakdown_contrib };
    }
    
    _score_mtf_confluence(mtf_trends) {
        let mtf_contribution = 0.0;
        const signal_breakdown_contrib = {};
        const cfg_mtf = this.config.mtf_analysis;
        const weights = this.weights;
        
        if (cfg_mtf.enabled && mtf_trends) {
            let mtf_buy_count = 0;
            let mtf_sell_count = 0;
            const total_mtf_indicators = Object.keys(mtf_trends).length;
            
            for (const _tf_indicator in mtf_trends) {
                const trend = mtf_trends[_tf_indicator];
                if (trend === "UP") mtf_buy_count++;
                else if (trend === "DOWN") mtf_sell_count++;
            }
            
            const mtf_weight = weights.mtf_trend_confluence;
            
            if (total_mtf_indicators > 0) {
                if (mtf_buy_count === total_mtf_indicators) { // All TFs agree bullish
                    mtf_contribution = mtf_weight * 1.5;
                    this.logger.debug(`${chalk.blue("MTF: All ")}${total_mtf_indicators}${chalk.blue(" higher TFs are UP. Strong bullish confluence.")}${chalk.reset()}`);
                } else if (mtf_sell_count === total_mtf_indicators) { // All TFs agree bearish
                    mtf_contribution = -mtf_weight * 1.5;
                    this.logger.debug(`${chalk.blue("MTF: All ")}${total_mtf_indicators}${chalk.blue(" higher TFs are DOWN. Strong bearish confluence.")}${chalk.reset()}`);
                } else { // Mixed or some agreement
                    const normalized_mtf_score = (mtf_buy_count - mtf_sell_count) / total_mtf_indicators;
                    mtf_contribution = mtf_weight * normalized_mtf_score;
                }
                signal_breakdown_contrib["MTF Confluence"] = mtf_contribution;
                this.logger.debug(`${chalk.blue("MTF Confluence: Buy: ")}${mtf_buy_count}${chalk.blue(", Sell: ")}${mtf_sell_count}${chalk.blue(". MTF contribution: ")}${mtf_contribution.toFixed(2)}${chalk.reset()}`);
            }
        }
        
        return { mtf_contribution, breakdown: signal_breakdown_contrib };
    }
    
    _dynamic_threshold(base_threshold) {
        const atr_now = this._get_indicator_value("ATR", new Decimal("0.0"));
        
        if (this.df.length < 50 || atr_now.isNaN() || atr_now.lte(0)) return base_threshold; // Not enough data for dynamic check
        
        // Calculate rolling mean of ATR. Simulate pandas rolling().mean().iloc[-1]
        const atr_series = this.df.ATR; // Assume ATR is already calculated and available as an array in df
        if (!atr_series || atr_series.length < 50) return base_threshold;
        
        const atr_ma = atr_series.slice(atr_series.length - 50).reduce((sum, val) => sum.plus(val), new Decimal("0")).dividedBy(new Decimal("50"));
        
        if (atr_ma.lte(0)) return base_threshold;
        
        const ratio = Decimal.min(new Decimal("1.5"), Decimal.max(new Decimal("0.9"), atr_now.dividedBy(atr_ma)));
        return base_threshold * ratio.toNumber();
    }
    
    _market_regime() {
        const ema_short = this._get_indicator_value("EMA_Short");
        const ema_long = this._get_indicator_value("EMA_Long");
        const adx = this._get_indicator_value("ADX");
        
        if (ema_short.isNaN() || ema_long.isNaN() || adx.isNaN()) {
            return "UNKNOWN";
        }
        
        const trend_up = ema_short.gt(ema_long);
        const trend_down = ema_short.lt(ema_long);
        const strong_trend = adx.gt(ADX_STRONG_TREND_THRESHOLD);
        
        if (trend_up && strong_trend) {
            return "STRONG_UPTREND";
        } else if (trend_down && strong_trend) {
            return "STRONG_DOWNTREND";
        } else if (trend_up) {
            return "UPTREND";
        } else if (trend_down) {
            return "DOWNTREND";
        } else {
            return "RANGING";
        }
    }
    
    generate_trading_signal(current_price, orderbook_data, mtf_trends) {
        let signal_score = 0.0;
        const signal_breakdown = {};
        
        if (this.df.length === 0) {
            this.logger.warning(`${chalk.yellow("[")}${this.symbol}${chalk.yellow("] DataFrame is empty in generate_trading_signal. Cannot generate signal.")}${chalk.reset()}`);
            return ["HOLD", 0.0, {}];
        }
        
        const current_close = this.df.close[this.df.close.length - 1];
        const prev_close = (this.df.length > 1) ? this.df.close[this.df.length - 2] : current_close;
        
        let trend_strength_multiplier = 1.0;
        
        // ADX is calculated first to determine overall trend strength for other indicators
        const { adx_contrib, trend_strength_multiplier: new_trend_multiplier, breakdown: adx_breakdown } = this._score_adx(trend_strength_multiplier);
        signal_score += adx_contrib;
        Object.assign(signal_breakdown, adx_breakdown);
        trend_strength_multiplier = new_trend_multiplier; // Update multiplier
        
        // --- Aggregate scores from all enabled indicators ---
        const scorers_to_run = [
            // Returns: {contrib, breakdown}
            [this._score_ema_alignment, [current_close, trend_strength_multiplier]],
            [this._score_sma_trend_filter, [current_close]],
            [this._score_momentum_indicators, []],
            [this._score_bollinger_bands, [current_close]],
            [this._score_vwap, [current_close, prev_close]],
            [this._score_psar, [current_close, prev_close]],
            [this._score_fibonacci_levels, [current_close, prev_close]],
            [this._score_fibonacci_pivot_points, [current_close, prev_close]],
            [this._score_ehlers_supertrend, [trend_strength_multiplier]],
            [this._score_macd, [trend_strength_multiplier]],
            [this._score_ichimoku_cloud, [current_close]],
            [this._score_obv, []],
            [this._score_cmf, []],
            [this._score_vwma_cross, [current_close, prev_close]],
            [this._score_volume_delta, []],
            [this._score_kaufman_ama_cross, [current_close, prev_close]],
            [this._score_relative_volume, [current_close, prev_close]],
            [this._score_market_structure, [trend_strength_multiplier]],
            [this._score_dema_crossover, [trend_strength_multiplier]],
            [this._score_keltner_channels, [current_close, prev_close]],
            [this._score_roc_signals, [trend_strength_multiplier]],
            [this._score_candlestick_patterns, []],
        ];
        
        for (const [scorer_func, args] of scorers_to_run) {
            const { contrib, breakdown } = scorer_func(...args);
            signal_score += contrib;
            Object.assign(signal_breakdown, breakdown);
        }
        
        // Volatility index is scored separately as it depends on the *current* signal score
        const { vol_contrib, breakdown: vol_breakdown } = this._score_volatility_index(signal_score);
        signal_score += vol_contrib;
        Object.assign(signal_breakdown, vol_breakdown);
        
        const { imbalance_contrib, breakdown: imbalance_breakdown } = this._score_orderbook_imbalance(orderbook_data);
        signal_score += imbalance_contrib;
        Object.assign(signal_breakdown, imbalance_breakdown);
        
        const { mtf_contribution, breakdown: mtf_breakdown } = this._score_mtf_confluence(mtf_trends);
        signal_score += mtf_contribution;
        Object.assign(signal_breakdown, mtf_breakdown);
        
        // --- Final Signal Decision with Dynamic Threshold, Hysteresis, and Cooldown ---
        const base_threshold = Math.max(this.config.signal_score_threshold, 1.0);
        const dynamic_threshold = this._dynamic_threshold(base_threshold);
        
        const last_score = this.config._last_score || 0.0;
        const hysteresis_ratio = this.config.hysteresis_ratio;
        
        let final_signal = "HOLD";
        
        // Hysteresis: prevent rapid flip-flopping around the threshold
        if (Math.sign(signal_score) !== Math.sign(last_score) && Math.abs(signal_score) < Math.abs(last_score) * hysteresis_ratio) {
            final_signal = "HOLD"; // Stay in previous state or hold
        } else { // Regular threshold check
            if (signal_score >= dynamic_threshold) final_signal = "BUY";
            else if (signal_score <= -dynamic_threshold) final_signal = "SELL";
        }
        
        // Cooldown period: prevent multiple entries in short succession
        const cooldown_sec = this.config.cooldown_sec;
        const now_ts = Math.floor(Date.now() / 1000);
        const last_signal_ts = this.config._last_signal_ts || 0;
        
        if (cooldown_sec > 0 && now_ts - last_signal_ts < cooldown_sec && final_signal !== "HOLD") {
            this.logger.info(`${chalk.yellow("Signal ignored due to cooldown (")}${cooldown_sec}${chalk.yellow("s). Next signal possible in ")}${cooldown_sec - (now_ts - last_signal_ts)}${chalk.yellow("s.)")}${chalk.reset()}`);
            final_signal = "HOLD";
        }
        
        // Store current score and timestamp for next loop's hysteresis/cooldown check
        this.config._last_score = signal_score;
        if (final_signal === "BUY" || final_signal === "SELL") this.config._last_signal_ts = now_ts;
        
        this.logger.info(`${chalk.yellow("Regime: ")}${this._market_regime()}${chalk.yellow(" | Score: ")}${signal_score.toFixed(2)}${chalk.yellow(" | DynThresh: ")}${dynamic_threshold.toFixed(2)}${chalk.yellow(" | Final: ")}${final_signal}${chalk.reset()}`);
        
        return [final_signal, signal_score, signal_breakdown];
    }
    
    calculate_entry_tp_sl(current_price, atr_value, signal) {
        const stop_loss_atr_multiple = new Decimal(this.config.trade_management.stop_loss_atr_multiple);
        const take_profit_atr_multiple = new Decimal(this.config.trade_management.take_profit_atr_multiple);
        
        let stop_loss, take_profit;
        if (signal === "BUY") {
            stop_loss = current_price.minus(atr_value.times(stop_loss_atr_multiple));
            take_profit = current_price.plus(atr_value.times(take_profit_atr_multiple));
        } else { // SELL
            stop_loss = current_price.plus(atr_value.times(stop_loss_atr_multiple));
            take_profit = current_price.minus(atr_value.times(take_profit_atr_multiple));
        }
        
        return [
            round_price(take_profit, this.config.trade_management.price_precision),
            round_price(stop_loss, this.config.trade_management.price_precision)
        ];
    }
}

// --- Display Functions ---
function display_indicator_values_and_price(config, logger, current_price, analyzer, orderbook_data, mtf_trends, signal_breakdown) {
    logger.info(`${chalk.blue("---")}${chalk.reset()}Current Market Data & Indicators${chalk.blue("---")}${chalk.reset()}`);
    logger.info(`${chalk.green("Current Price: ")}${current_price.normalize()}${chalk.reset()}`);
    
    if (analyzer.df.length === 0) {
        logger.warning(`${chalk.yellow("Cannot display indicators: DataFrame is empty after calculations.")}${chalk.reset()}`);
        return;
    }
    
    logger.info(`${chalk.cyan("---")}${chalk.reset()}Indicator Values${chalk.cyan("---")}${chalk.reset()}`);
    for (const indicator_name in analyzer.indicator_values) {
        const value = analyzer.indicator_values[indicator_name];
        const color = INDICATOR_COLORS[indicator_name] || chalk.yellow;
        
        if (value instanceof Decimal) {
            logger.info(`  ${color}${indicator_name.padEnd(20)}: ${value.normalize().toString()}${chalk.reset()}`);
        } else if (typeof value === 'number') {
            logger.info(`  ${color}${indicator_name.padEnd(20)}: ${value.toFixed(8)}${chalk.reset()}`);
        } else {
            logger.info(`  ${color}${indicator_name.padEnd(20)}: ${value}${chalk.reset()}`);
        }
    }
    
    if (analyzer.fib_levels && Object.keys(analyzer.fib_levels).length > 0) {
        logger.info(`${chalk.cyan("---")}${chalk.reset()}Fibonacci Retracement Levels${chalk.cyan("---")}${chalk.reset()}`);
        for (const level_name in analyzer.fib_levels) {
            const level_price = analyzer.fib_levels[level_name];
            logger.info(`  ${chalk.yellow(level_name.padEnd(20))}: ${level_price.normalize().toString()}${chalk.reset()}`);
        }
    }
    
    if (config.indicators.fibonacci_pivot_points) {
        const pivot = analyzer._get_indicator_value("Pivot");
        const r1 = analyzer._get_indicator_value("R1");
        const r2 = analyzer._get_indicator_value("R2");
        const s1 = analyzer._get_indicator_value("S1");
        const s2 = analyzer._get_indicator_value("S2");
        
        if (!pivot.isNaN() && !r1.isNaN() && !s1.isNaN()) {
            logger.info(`${chalk.cyan("---")}${chalk.reset()}Fibonacci Pivot Points${chalk.cyan("---")}${chalk.reset()}`);
            logger.info(`  ${INDICATOR_COLORS.Pivot.padEnd(20)}Pivot              : ${pivot.normalize().toString()}${chalk.reset()}`);
            logger.info(`  ${INDICATOR_COLORS.R1.padEnd(20)}R1                 : ${r1.normalize().toString()}${chalk.reset()}`);
            logger.info(`  ${INDICATOR_COLORS.R2.padEnd(20)}R2                 : ${r2.normalize().toString()}${chalk.reset()}`);
            logger.info(`  ${INDICATOR_COLORS.S1.padEnd(20)}S1                 : ${s1.normalize().toString()}${chalk.reset()}`);
            logger.info(`  ${INDICATOR_COLORS.S2.padEnd(20)}S2                 : ${s2.normalize().toString()}${chalk.reset()}`);
        }
    }
    
    if (analyzer.indicator_values.Support_Level || analyzer.indicator_values.Resistance_Level) {
        logger.info(`${chalk.cyan("---")}${chalk.reset()}Orderbook S/R Levels${chalk.cyan("---")}${chalk.reset()}`);
        if (analyzer.indicator_values.Support_Level && !analyzer.indicator_values.Support_Level.isNaN()) {
            logger.info(`  ${INDICATOR_COLORS.Support_Level.padEnd(20)}Support Level     : ${analyzer.indicator_values.Support_Level.normalize().toString()}${chalk.reset()}`);
        }
        if (analyzer.indicator_values.Resistance_Level && !analyzer.indicator_values.Resistance_Level.isNaN()) {
            logger.info(`  ${INDICATOR_COLORS.Resistance_Level.padEnd(20)}Resistance Level  : ${analyzer.indicator_values.Resistance_Level.normalize().toString()}${chalk.reset()}`);
        }
    }
    
    if (mtf_trends && Object.keys(mtf_trends).length > 0) {
        logger.info(`${chalk.cyan("---")}${chalk.reset()}Multi-Timeframe Trends${chalk.cyan("---")}${chalk.reset()}`);
        for (const tf_indicator in mtf_trends) {
            const trend = mtf_trends[tf_indicator];
            logger.info(`  ${chalk.yellow(tf_indicator.padEnd(20))}: ${trend}${chalk.reset()}`);
        }
    }
    
    if (signal_breakdown && Object.keys(signal_breakdown).length > 0) {
        logger.info(`${chalk.cyan("---")}${chalk.reset()}Signal Score Breakdown${chalk.cyan("---")}${chalk.reset()}`);
        const sorted_breakdown = Object.entries(signal_breakdown).sort(([, a], [, b]) => Math.abs(b) - Math.abs(a));
        for (const [indicator, contribution] of sorted_breakdown) {
            const color = (contribution > 0) ? chalk.green : (contribution < 0) ? chalk.red : chalk.yellow;
            logger.info(`  ${color}${indicator.padEnd(25)}: ${contribution.toFixed(2)}${chalk.reset()}`);
        }
    }
    
    // Concise Trend Summary
    logger.info(`${chalk.magenta("---")}${chalk.reset()}Current Trend Summary${chalk.magenta("---")}${chalk.reset()}`);
    const trend_summary_lines = [];
    
    // EMA Alignment
    const ema_short = analyzer._get_indicator_value("EMA_Short");
    const ema_long = analyzer._get_indicator_value("EMA_Long");
    if (!ema_short.isNaN() && !ema_long.isNaN()) {
        if (ema_short.gt(ema_long)) trend_summary_lines.push(`${chalk.green("EMA Cross  : ▲ Up")}${chalk.reset()}`);
        else if (ema_short.lt(ema_long)) trend_summary_lines.push(`${chalk.red("EMA Cross  : ▼ Down")}${chalk.reset()}`);
        else trend_summary_lines.push(`${chalk.yellow("EMA Cross  : ↔ Sideways")}${chalk.reset()}`);
    }
    
    // Ehlers SuperTrend (Slow)
    const st_slow_dir = analyzer._get_indicator_value("ST_Slow_Dir");
    if (!st_slow_dir.isNaN()) {
        if (st_slow_dir === 1) trend_summary_lines.push(`${chalk.green("SuperTrend : ▲ Up")}${chalk.reset()}`);
        else if (st_slow_dir === -1) trend_summary_lines.push(`${chalk.red("SuperTrend : ▼ Down")}${chalk.reset()}`);
        else trend_summary_lines.push(`${chalk.yellow("SuperTrend : ↔ Sideways")}${chalk.reset()}`);
    }
    
    // MACD Histogram (momentum)
    const macd_hist = analyzer._get_indicator_value("MACD_Hist");
    if (!macd_hist.isNaN()) {
        if (analyzer.df.length > 1) { // Check previous exists
            const prev_macd_hist = analyzer.df.iloc(analyzer.df.length - 2).MACD_Hist;
            if (macd_hist.gt(0) && prev_macd_hist.lte(0)) trend_summary_lines.push(`${chalk.green("MACD Hist  : ↑ Bullish Cross")}${chalk.reset()}`);
            else if (macd_hist.lt(0) && prev_macd_hist.gte(0)) trend_summary_lines.push(`${chalk.red("MACD Hist  : ↓ Bearish Cross")}${chalk.reset()}`);
            else if (macd_hist.gt(0)) trend_summary_lines.push(`${chalk.lightGreen("MACD Hist  : Above 0")}${chalk.reset()}`);
            else if (macd_hist.lt(0)) trend_summary_lines.push(`${chalk.lightRed("MACD Hist  : Below 0")}${chalk.reset()}`);
        } else trend_summary_lines.push(`${chalk.yellow("MACD Hist  : N/A")}${chalk.reset()}`);
    }
    
    // ADX Strength
    const adx_val = analyzer._get_indicator_value("ADX");
    if (!adx_val.isNaN()) {
        if (adx_val.gt(ADX_STRONG_TREND_THRESHOLD)) {
            const plus_di = analyzer._get_indicator_value("PlusDI");
            const minus_di = analyzer._get_indicator_value("MinusDI");
            if (!plus_di.isNaN() && !minus_di.isNaN()) {
                if (plus_di.gt(minus_di)) trend_summary_lines.push(`${chalk.lightGreen("ADX Trend  : Strong Up (")}${adx_val.toFixed(0)}${chalk.lightGreen(")")}${chalk.reset()}`);
                else trend_summary_lines.push(`${chalk.lightRed("ADX Trend  : Strong Down (")}${adx_val.toFixed(0)}${chalk.lightRed(")")}${chalk.reset()}`);
            }
        } else if (adx_val.lt(ADX_WEAK_TREND_THRESHOLD)) trend_summary_lines.push(`${chalk.yellow("ADX Trend  : Weak/Ranging (")}${adx_val.toFixed(0)}${chalk.yellow(")")}${chalk.reset()}`);
        else trend_summary_lines.push(`${chalk.cyan("ADX Trend  : Moderate (")}${adx_val.toFixed(0)}${chalk.cyan(")")}${chalk.reset()}`);
    }
    
    // Ichimoku Cloud (Kumo position)
    const senkou_span_a = analyzer._get_indicator_value("Senkou_Span_A");
    const senkou_span_b = analyzer._get_indicator_value("Senkou_Span_B");
    if (!senkou_span_a.isNaN() && !senkou_span_b.isNaN()) {
        const kumo_upper = Decimal.max(senkou_span_a, senkou_span_b);
        const kumo_lower = Decimal.min(senkou_span_a, senkou_span_b);
        if (current_price.gt(kumo_upper)) trend_summary_lines.push(`${chalk.green("Ichimoku   : Above Kumo")}${chalk.reset()}`);
        else if (current_price.lt(kumo_lower)) trend_summary_lines.push(`${chalk.red("Ichimoku   : Below Kumo")}${chalk.reset()}`);
        else trend_summary_lines.push(`${chalk.yellow("Ichimoku   : Inside Kumo")}${chalk.reset()}`);
    }
    
    // MTF Confluence
    if (mtf_trends && Object.keys(mtf_trends).length > 0) {
        const up_count = Object.values(mtf_trends).filter(t => t === "UP").length;
        const down_count = Object.values(mtf_trends).filter(t => t === "DOWN").length;
        const total = Object.keys(mtf_trends).length;
        if (total > 0) {
            if (up_count === total) trend_summary_lines.push(`${chalk.green("MTF Confl. : All Bullish (")}${up_count}/${total}${chalk.green(")")}${chalk.reset()}`);
            else if (down_count === total) trend_summary_lines.push(`${chalk.red("MTF Confl. : All Bearish (")}${down_count}/${total}${chalk.red(")")}${chalk.reset()}`);
            else if (up_count > down_count) trend_summary_lines.push(`${chalk.lightGreen("MTF Confl. : Mostly Bullish (")}${up_count}/${total}${chalk.lightGreen(")")}${chalk.reset()}`);
            else if (down_count > up_count) trend_summary_lines.push(`${chalk.lightRed("MTF Confl. : Mostly Bearish (")}${down_count}/${total}${chalk.lightRed(")")}${chalk.reset()}`);
            else trend_summary_lines.push(`${chalk.yellow("MTF Confl. : Mixed (")}${up_count}/${total} Bull, ${down_count}/${total} Bear)${chalk.reset()}`);
        }
    }
    
    for (const line of trend_summary_lines) {
        logger.info(`  ${line}`);
    }
    logger.info(`${chalk.blue("---")}${chalk.reset()}`);
}

// --- Main Execution Logic ---
async function main() {
    const config_manager = new ConfigManager(CONFIG_FILE, logger);
    const config = config_manager.config; // Get the loaded config
    const alert_system = new AlertSystem(logger);
    const bybit_client = new BybitClient(API_KEY, API_SECRET, BASE_URL, logger);
    
    // Validate interval format at startup
    const valid_bybit_intervals = ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"];
    if (!valid_bybit_intervals.includes(config.interval)) {
        logger.error(`${chalk.red("Invalid primary interval '")}${config.interval}${chalk.red("' in config.json. Exiting.")}${chalk.reset()}`);
        process.exit(1);
    }
    
    for (const htf_interval of config.mtf_analysis.higher_timeframes) {
        if (!valid_bybit_intervals.includes(htf_interval)) {
            logger.error(`${chalk.red("Invalid higher timeframe interval '")}${htf_interval}${chalk.red("' in config.json. Exiting.")}${chalk.reset()}`);
            process.exit(1);
        }
    }
    
    logger.info(`${chalk.green("---")}${chalk.reset()}Whalebot Trading Bot Initialized${chalk.green("---")}${chalk.reset()}`);
    logger.info(`Symbol: ${config.symbol}, Interval: ${config.interval}`);
    logger.info(`Live Trading Enabled: ${config.execution.use_pybit}`);
    logger.info(`Trade Management Enabled: ${config.trade_management.enabled}`);
    
    const position_manager = new PositionManager(config, logger, config.symbol, bybit_client);
    const performance_tracker = new PerformanceTracker(logger, config);
    
    // Initial setup for live trading if enabled
    if (config.execution.use_pybit && bybit_client.api_key && bybit_client.api_secret) {
        const leverage_set = await bybit_client.set_leverage(
            config.symbol,
            config.execution.buy_leverage,
            config.execution.sell_leverage
        );
        
        if (leverage_set) {
            logger.info(`${chalk.green("Leverage set successfully: Buy ")}${config.execution.buy_leverage}x, Sell ${config.execution.sell_leverage}x${chalk.reset()}`);
        } else {
            logger.error(`${chalk.red("Failed to set leverage. Check API permissions or account status.")}${chalk.reset()}`);
            alert_system.send_alert(`Failed to set leverage for ${config.symbol}. Check API settings.`, "ERROR");
            // Depending on criticality, you might want to exit here.
        }
        
        await position_manager._update_precision_from_exchange(); // Update precision from live exchange
    }
    
    while (true) {
        const loop_start_time = Date.now();
        try {
            logger.info(`${chalk.magenta("---")}${chalk.reset()}New Analysis Loop Started (${new Date().toISOString()}${chalk.magenta(") ---")}${chalk.reset()}`);
            
            // --- GUARDRAILS & FILTERS ---
            const guard = config.risk_guardrails;
            if (guard.enabled) {
                const current_account_balance = position_manager._get_current_balance();
                const equity = current_account_balance.plus(performance_tracker.total_pnl);
                
                const day_loss = performance_tracker.day_pnl();
                const max_day_loss_amount = equity.times(new Decimal(guard.max_day_loss_pct).dividedBy(100));
                const max_dd_amount = equity.times(new Decimal(guard.max_drawdown_pct).dividedBy(100));
                
                if ((max_day_loss_amount.gt(0) && day_loss.lte(max_day_loss_amount.neg())) || (performance_tracker.max_drawdown.gte(max_dd_amount))) {
                    logger.critical(`${chalk.red("KILL SWITCH ACTIVATED: Risk limits hit. Day PnL: ")}${day_loss.normalize().toFixed(2)}${chalk.red(", Max Day Loss: ")}${max_day_loss_amount.normalize().toFixed(2)}. Max Drawdown: ${performance_tracker.max_drawdown.normalize().toFixed(2)}, Max Allowed Drawdown: ${max_dd_amount.normalize().toFixed(2)}. Cooling down.${chalk.reset()}`);
                    alert_system.send_alert(`KILL SWITCH: Risk limits hit for ${config.symbol}. Cooling down.`, "ERROR");
                    await setTimeout(config.risk_guardrails.cooldown_after_kill_min * 60 * 1000); // Longer cooldown
                    continue; // Skip to next loop iteration after cooldown
                }
            }
            
            // Session filter check
            // if (!in_allowed_session(config)) { // Removed in_allowed_session as it's not present in consolidated code.
            //     logger.info(`${chalk.blue("Outside allowed trading session. Holding.")}${chalk.reset()}`);
            //     await setTimeout(config.loop_delay * 1000);
            //     continue;
            // }
            
            // --- DATA FETCHING ---
            const current_price = await bybit_client.fetch_current_price(config.symbol);
            if (current_price === null || current_price.isZero()) {
                alert_system.send_alert(`[${config.symbol}] Failed to fetch current price. Skipping loop.`, "WARNING");
                await setTimeout(config.loop_delay * 1000);
                continue;
            }
            
            const df_raw = await bybit_client.fetch_klines(config.symbol, config.interval, 1000);
            if (df_raw === null || df_raw.length === 0) {
                alert_system.send_alert(`[${config.symbol}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.`, "WARNING");
                await setTimeout(config.loop_delay * 1000);
                continue;
            }
            
            let orderbook_data = null;
            if (config.indicators.orderbook_imbalance) {
                orderbook_data = await bybit_client.fetch_orderbook(config.symbol, config.orderbook_limit);
                if (orderbook_data === null) {
                    logger.warning(`${chalk.yellow("Failed to fetch orderbook data.")}${chalk.reset()}`);
                }
            }
            
            // --- MTF ANALYSIS ---
            const mtf_trends = {};
            if (config.mtf_analysis.enabled) {
                for (const htf_interval of config.mtf_analysis.higher_timeframes) {
                    logger.debug(`Fetching klines for MTF interval: ${htf_interval}`);
                    const htf_df_raw = await bybit_client.fetch_klines(config.symbol, htf_interval, 1000);
                    if (htf_df_raw !== null && htf_df_raw.length > 0) {
                        // Pass raw data, TradingAnalyzer will process it
                        const temp_htf_analyzer = new TradingAnalyzer(htf_df_raw, config, logger, config.symbol);
                        for (const trend_ind of config.mtf_analysis.trend_indicators) {
                            const trend = temp_htf_analyzer._get_mtf_trend(htf_df_raw, trend_ind); // Pass raw for MTF analysis
                            mtf_trends[`${htf_interval}_${trend_ind}`] = trend;
                            logger.debug(`MTF Trend (${htf_interval}, ${trend_ind}): ${trend}`);
                        }
                    } else {
                        logger.warning(`${chalk.yellow("Could not fetch klines for higher timeframe ")}${htf_interval}${chalk.yellow(" or it was empty. Skipping MTF trend for this TF.")}${chalk.reset()}`);
                    }
                    await setTimeout(config.mtf_analysis.mtf_request_delay_seconds * 1000); // Delay between MTF requests
                }
            }
            
            // --- ANALYSIS & SIGNAL GENERATION ---
            const analyzer = new TradingAnalyzer(df_raw, config, logger, config.symbol);
            if (analyzer.df.length === 0) {
                alert_system.send_alert(`[${config.symbol}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.`, "WARNING");
                await setTimeout(config.loop_delay * 1000);
                continue;
            }
            
            const [trading_signal, signal_score, signal_breakdown] = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends);
            const atr_value = analyzer._get_indicator_value("ATR", new Decimal("0.01"));
            
            // Store last ATR for breakeven logic in PositionManager (passed via config)
            config._last_atr_value = atr_value.toString();
            
            // --- Display Current State ---
            display_indicator_values_and_price(config, logger, current_price, analyzer, orderbook_data, mtf_trends, signal_breakdown);
            
            // --- POSITION MANAGEMENT ---
            // Update trailing stops for existing simulated positions
            for (const pos of position_manager.get_open_positions()) {
                position_manager.trail_stop(pos, current_price, atr_value);
            }
            
            // Manage (close) simulated positions based on SL/TP hits
            position_manager.manage_positions(current_price, performance_tracker);
            
            // Attempt to pyramid on simulated positions if conditions met
            position_manager.try_pyramid(current_price, atr_value);
            
            // --- EXECUTION ---
            if (trading_signal === "BUY" || trading_signal === "SELL") {
                // Calculate conviction based on signal strength (0 to 1, or scaled)
                const conviction = Math.min(1.0, Math.max(0.0, (Math.abs(signal_score) - config.signal_score_threshold) / config.signal_score_threshold));
                
                if (Math.abs(signal_score) >= config.signal_score_threshold) {
                    position_manager.open_position(trading_signal, current_price, atr_value, conviction);
                } else {
                    logger.info(`${chalk.blue("Signal below threshold (")}${config.signal_score_threshold.toFixed(2)}${chalk.blue("). Holding. Score: ")}${signal_score.toFixed(2)}${chalk.reset()}`);
                }
            } else {
                logger.info(`${chalk.blue("No strong trading signal. Holding. Score: ")}${signal_score.toFixed(2)}${chalk.reset()}`);
            }
            
            const open_positions_summary = position_manager.get_open_positions();
            if (open_positions_summary.length > 0) {
                logger.info(`${chalk.cyan("Open Positions: ")}${open_positions_summary.length}${chalk.reset()}`);
                for (const pos of open_positions_summary) {
                    logger.info(`  - ${pos.side} ${pos.qty.normalize().toString()} ${pos.symbol} @ ${pos.entry_price.normalize().toString()} (SL: ${pos.stop_loss.normalize().toString()}, TP: ${pos.take_profit.normalize().toString()}, Adds: ${pos.adds || 0})${chalk.reset()}`);
                }
            } else {
                logger.info(`${chalk.cyan("No open positions.")}${chalk.reset()}`);
            }
            
            const perf_summary = performance_tracker.get_summary();
            logger.info(`${chalk.yellow("Performance Summary: Total Net PnL: ")}${perf_summary.total_pnl.normalize().toFixed(2)}, Wins: ${perf_summary.wins}, Losses: ${perf_summary.losses}, Win Rate: ${perf_summary.win_rate}, Max Drawdown: ${perf_summary.max_drawdown.normalize().toFixed(2)}${chalk.reset()}`);
            
            logger.info(`${chalk.magenta("---")}${chalk.reset()}Analysis Loop Finished. Waiting ${config.loop_delay}${chalk.magenta("s ---")}${chalk.reset()}`);
            
        } catch (e) {
            alert_system.send_alert(`[${config.symbol}] An unhandled error occurred in the main loop: ${e.message}`, "ERROR");
            logger.error(`${chalk.red("Unhandled exception in main loop:")}${e.message}${e.stack}${chalk.reset()}`);
            await setTimeout(config.loop_delay * 2 * 1000); // Longer wait on error
        }
        
        const elapsed_time = Date.now() - loop_start_time;
        const remaining_delay = (config.loop_delay * 1000) - elapsed_time;
        if (remaining_delay > 0) {
            await setTimeout(remaining_delay);
        }
    }
}

// Ensure the Path prototype has a to_string method if needed for compatibility (e.g. for Python Path objects)
// In JS, Path is part of built-in 'path' module, not a class like Python's pathlib.Path.
// Direct access to methods like `.mkdir` is via `fs.mkdirSync`.
const Path = (p) => {
    return {
        filepath: p,
        mkdir: (options) => fs.mkdirSync(p, options),
        exists: () => fs.existsSync(p),
        open: (mode, encoding) => fs.readFileSync(p, encoding), // For reading, simple sync for config
        toString: () => p, // For display
        parent: Path(path.dirname(p)) // Basic parent implementation
    };
};

main();
