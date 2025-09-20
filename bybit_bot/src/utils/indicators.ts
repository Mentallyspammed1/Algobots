/**
 * A comprehensive collection of technical indicators for trend analysis.
 */
import { Candle } from '../core/types';

// =========== UTILITY FUNCTIONS ===========

const sum = (arr: number[]): number => arr.reduce((a, b) => a + b, 0);
const avg = (arr: number[]): number => sum(arr) / arr.length;

// =========== MOVING AVERAGES ===========

export class SMA {
    private period: number;
    private prices: number[] = [];

    constructor(period: number) {
        if (period <= 0) throw new Error('Period must be positive.');
        this.period = period;
    }

    update(price: number): number | null {
        this.prices.push(price);
        if (this.prices.length > this.period) {
            this.prices.shift();
        }
        if (this.prices.length < this.period) return null;
        return avg(this.prices);
    }
}

export class EMA {
  private alpha: number;
  public value: number | null = null;

  constructor(period: number) {
    if (period <= 0) throw new Error('Period must be positive.');
    this.alpha = 2 / (period + 1);
  }

  update(price: number): number {
    if (this.value === null) {
      this.value = price;
    } else {
      this.value = this.alpha * price + (1 - this.alpha) * this.value;
    }
    return this.value;
  }
}

export class WMA {
    private period: number;
    private prices: number[] = [];
    private weights: number[];

    constructor(period: number) {
        this.period = period;
        this.weights = Array.from({length: period}, (_, i) => i + 1);
    }

    update(price: number): number | null {
        this.prices.push(price);
        if (this.prices.length > this.period) {
            this.prices.shift();
        }
        if (this.prices.length < this.period) return null;

        const weightedSum = this.prices.reduce((sum, p, i) => sum + p * this.weights[i], 0);
        const weightSum = sum(this.weights.slice(0, this.prices.length));
        return weightedSum / weightSum;
    }
}

// =========== OSCILLATORS & MOMENTUM ===========

export class MACD {
    private fast_ema: EMA;
    private slow_ema: EMA;
    private signal_ema: EMA;
    public macd: number | null = null;
    public signal: number | null = null;
    public histogram: number | null = null;

    constructor(fast_period: number, slow_period: number, signal_period: number) {
        this.fast_ema = new EMA(fast_period);
        this.slow_ema = new EMA(slow_period);
        this.signal_ema = new EMA(signal_period);
    }

    update(price: number): { macd: number, signal: number, histogram: number } {
        const fast_val = this.fast_ema.update(price);
        const slow_val = this.slow_ema.update(price);
        this.macd = fast_val - slow_val;
        this.signal = this.signal_ema.update(this.macd);
        this.histogram = this.macd - this.signal;
        return { macd: this.macd, signal: this.signal, histogram: this.histogram };
    }
}

export class RSI {
    private period: number;
    private last_close: number | null = null;
    private avg_gain = 0;
    private avg_loss = 0;
    public value: number | null = null;

    constructor(period: number) {
        this.period = period;
    }

    update(price: number): number | null {
        if (this.last_close === null) {
            this.last_close = price;
            return null;
        }

        const change = price - this.last_close;
        const gain = change > 0 ? change : 0;
        const loss = change < 0 ? -change : 0;

        this.avg_gain = (this.avg_gain * (this.period - 1) + gain) / this.period;
        this.avg_loss = (this.avg_loss * (this.period - 1) + loss) / this.period;
        this.last_close = price;

        if (this.avg_loss === 0) {
            this.value = 100;
        } else {
            const rs = this.avg_gain / this.avg_loss;
            this.value = 100 - (100 / (1 + rs));
        }
        return this.value;
    }
}

export class Stochastic {
    private period: number;
    private k_smoothing: number;
    private highs: number[] = [];
    private lows: number[] = [];
    private closes: number[] = [];
    private last_k: number | null = null;

    constructor(period: number, k_smoothing: number) {
        this.period = period;
        this.k_smoothing = k_smoothing;
    }

    update(candle: Candle): { k: number, d: number } | null {
        this.highs.push(candle.high);
        this.lows.push(candle.low);
        this.closes.push(candle.close);

        if (this.highs.length > this.period) {
            this.highs.shift();
            this.lows.shift();
            this.closes.shift();
        }

        if (this.highs.length < this.period) return null;

        const highest_high = Math.max(...this.highs);
        const lowest_low = Math.min(...this.lows);
        
        const k = 100 * ((candle.close - lowest_low) / (highest_high - lowest_low));

        // Simple smoothing for %D line
        if (this.last_k === null) {
            this.last_k = k;
            return null;
        }

        const d = (this.last_k * (this.k_smoothing - 1) + k) / this.k_smoothing;
        this.last_k = k;

        return { k, d };
    }
}

// =========== TREND & VOLATILITY ===========

export class ADX {
    private period: number;
    private candles: Candle[] = [];
    private tr_ema: EMA;
    private dm_plus_ema: EMA;
    private dm_minus_ema: EMA;
    private adx_ema: EMA;
    public adx: number | null = null;
    public pdi: number | null = null;
    public mdi: number | null = null;

    constructor(period: number) {
        this.period = period;
        this.tr_ema = new EMA(period);
        this.dm_plus_ema = new EMA(period);
        this.dm_minus_ema = new EMA(period);
        this.adx_ema = new EMA(period);
    }

    update(candle: Candle): { adx: number, pdi: number, mdi: number } | null {
        this.candles.push(candle);
        if (this.candles.length < 2) return null;
        if (this.candles.length > this.period + 1) {
            this.candles.shift();
        }

        const prev_candle = this.candles[this.candles.length - 2];
        
        const tr = Math.max(candle.high - candle.low, Math.abs(candle.high - prev_candle.close), Math.abs(candle.low - prev_candle.close));
        this.tr_ema.update(tr);

        const dm_plus = candle.high - prev_candle.high > prev_candle.low - candle.low ? Math.max(candle.high - prev_candle.high, 0) : 0;
        const dm_minus = prev_candle.low - candle.low > candle.high - prev_candle.high ? Math.max(prev_candle.low - candle.low, 0) : 0;
        
        this.dm_plus_ema.update(dm_plus);
        this.dm_minus_ema.update(dm_minus);

        const tr_ema_val = this.tr_ema.value;
        if (tr_ema_val === null || tr_ema_val === 0) return null;

        this.pdi = (this.dm_plus_ema.value! / tr_ema_val) * 100;
        this.mdi = (this.dm_minus_ema.value! / tr_ema_val) * 100;

        const dx = (Math.abs(this.pdi - this.mdi) / (this.pdi + this.mdi)) * 100;
        if (isNaN(dx)) return null;

        this.adx = this.adx_ema.update(dx);

        return { adx: this.adx, pdi: this.pdi, mdi: this.mdi };
    }
}

export class ATR {
    public readonly period: number;
    private candles: Candle[] = [];
    private atr_ema: EMA;
    public value: number | null = null;

    constructor(period: number) {
        this.period = period;
        this.atr_ema = new EMA(period);
    }

    update(candle: Candle): number | null {
        this.candles.push(candle);
        if (this.candles.length < 2) return null;
        if (this.candles.length > this.period + 1) {
            this.candles.shift();
        }
        const prev_candle = this.candles[this.candles.length - 2];
        const tr = Math.max(candle.high - candle.low, Math.abs(candle.high - prev_candle.close), Math.abs(candle.low - prev_candle.close));
        this.value = this.atr_ema.update(tr);
        return this.value;
    }
}

export class SuperTrend {
    private atr: ATR;
    private factor: number;
    public value: number | null = null;
    public direction: 'up' | 'down' = 'up';
    private last_final_upper_band = 0;
    private last_final_lower_band = 0;

    constructor(period: number, factor: number) {
        this.atr = new ATR(period);
        this.factor = factor;
    }

    update(candle: Candle): { value: number, direction: 'up' | 'down' } | null {
        const atr_val = this.atr.update(candle);
        if (atr_val === null) return null;

        const basic_upper_band = (candle.high + candle.low) / 2 + this.factor * atr_val;
        const basic_lower_band = (candle.high + candle.low) / 2 - this.factor * atr_val;

        const final_upper_band = (basic_upper_band < this.last_final_upper_band || this.candles[this.candles.length-2].close > this.last_final_upper_band) ? basic_upper_band : this.last_final_upper_band;
        const final_lower_band = (basic_lower_band > this.last_final_lower_band || this.candles[this.candles.length-2].close < this.last_final_lower_band) ? basic_lower_band : this.last_final_lower_band;

        if (this.value === null) { // First run
            this.direction = 'up';
            this.value = final_lower_band;
        } else if (this.value === this.last_final_upper_band && candle.close > final_upper_band) {
            this.direction = 'up';
            this.value = final_lower_band;
        } else if (this.value === this.last_final_lower_band && candle.close < final_lower_band) {
            this.direction = 'down';
            this.value = final_upper_band;
        } else {
            this.value = this.direction === 'up' ? final_lower_band : final_upper_band;
        }
        
        this.last_final_upper_band = final_upper_band;
        this.last_final_lower_band = final_lower_band;

        return { value: this.value, direction: this.direction };
    }

    // Need to manage candles internally for SuperTrend
    private candles: Candle[] = [];
    private manage_candles(candle: Candle) {
        this.candles.push(candle);
        if (this.candles.length > this.atr.period + 1) {
            this.candles.shift();
        }
    }

    // Wrapper for update to manage candles
    public next(candle: Candle): { value: number, direction: 'up' | 'down' } | null {
        this.manage_candles(candle);
        return this.update(candle);
    }
}

export class BollingerBands {
    private sma: SMA;
    private period: number;
    private stdDevFactor: number;
    private prices: number[] = [];

    constructor(period: number, stdDevFactor: number) {
        this.sma = new SMA(period);
        this.period = period;
        this.stdDevFactor = stdDevFactor;
    }

    update(price: number): { middle: number; upper: number; lower: number } | null {
        this.prices.push(price);
        if (this.prices.length > this.period) {
            this.prices.shift();
        }

        const middle = this.sma.update(price);
        if (middle === null) return null;

        const stdDev = Math.sqrt(
            this.prices.reduce((sq, p) => sq + Math.pow(p - middle, 2), 0) / this.prices.length
        );

        return {
            middle,
            upper: middle + stdDev * this.stdDevFactor,
            lower: middle - stdDev * this.stdDevFactor,
        };
    }
}

export class IchimokuCloud {
    private candles: Candle[] = [];
    public tenkan_sen: number | null = null;
    public kijun_sen: number | null = null;
    public senkou_span_a: number | null = null;
    public senkou_span_b: number | null = null;
    public chikou_span: number | null = null;

    constructor(
        private tenkan_period: number = 9,
        private kijun_period: number = 26,
        private senkou_b_period: number = 52
    ) {}

    private getHighest(period: number, offset: number = 0): number {
        const slice = this.candles.slice(this.candles.length - period - offset, this.candles.length - offset);
        return Math.max(...slice.map(c => c.high));
    }

    private getLowest(period: number, offset: number = 0): number {
        const slice = this.candles.slice(this.candles.length - period - offset, this.candles.length - offset);
        return Math.min(...slice.map(c => c.low));
    }

    update(candle: Candle): any {
        this.candles.push(candle);
        const max_period = Math.max(this.tenkan_period, this.kijun_period, this.senkou_b_period) + this.kijun_period;
        if (this.candles.length > max_period) {
            this.candles.shift();
        }

        if (this.candles.length >= this.tenkan_period) {
            this.tenkan_sen = (this.getHighest(this.tenkan_period) + this.getLowest(this.tenkan_period)) / 2;
        }

        if (this.candles.length >= this.kijun_period) {
            this.kijun_sen = (this.getHighest(this.kijun_period) + this.getLowest(this.kijun_period)) / 2;
        }

        if (this.tenkan_sen && this.kijun_sen) {
            this.senkou_span_a = (this.tenkan_sen + this.kijun_sen) / 2;
        }

        if (this.candles.length >= this.senkou_b_period + this.kijun_period) {
             const senkou_b_high = this.getHighest(this.senkou_b_period, this.kijun_period);
             const senkou_b_low = this.getLowest(this.senkou_b_period, this.kijun_period);
             this.senkou_span_b = (senkou_b_high + senkou_b_low) / 2;
        }

        if (this.candles.length > this.kijun_period) {
            this.chikou_span = this.candles[this.candles.length - 1 - this.kijun_period].close;
        }
        
        return {
            tenkan_sen: this.tenkan_sen,
            kijun_sen: this.kijun_sen,
            senkou_span_a: this.senkou_span_a,
            senkou_span_b: this.senkou_span_b,
            chikou_span: this.chikou_span,
        };
    }
}

// Add more indicators here...
// Momentum, ROC, CCI, Parabolic SAR, VWAP, Awesome Oscillator, Aroon etc.

// =========== Ehlers Indicators ===========

export class EhlersInstantaneousTrendline {
    private alpha: number;
    private prices: number[] = [];
    public trend: number | null = null;
    private trigger: number | null = null;

    constructor(period: number) {
        this.alpha = 2 / (period + 1);
    }

    update(price: number): { trend: number, trigger: number } | null {
        this.prices.push(price);
        if (this.prices.length < 7) return null; // Needs a few bars to stabilize
        if (this.prices.length > 100) this.prices.shift(); // Prevent memory leak

        const p = this.prices;
        const len = p.length - 1;

        // Simplified ITrend calculation
        const term1 = (p[len] + 2 * p[len-1] + 2 * p[len-2] + p[len-3]) / 6;
        this.trend = (this.alpha - (this.alpha**2)/4) * term1 + 
                     0.5 * (this.alpha**2) * this.prices[len-2] - 
                     (this.alpha - 0.75 * (this.alpha**2)) * this.prices[len-4];

        this.trigger = 2 * this.trend - this.prices[len-2]; // Lagging trigger

        return { trend: this.trend, trigger: this.trigger };
    }
}

export class EhlersFisherTransform {
    private period: number;
    private prices: number[] = [];
    public fisher: number | null = null;
    public trigger: number | null = null; // Trigger is the previous Fisher value

    constructor(period: number) {
        this.period = period;
    }

    private getHighest(arr: number[]): number {
        return Math.max(...arr);
    }

    private getLowest(arr: number[]): number {
        return Math.min(...arr);
    }

    update(price: number): { fisher: number, trigger: number } | null {
        this.prices.push(price);
        if (this.prices.length > this.period) {
            this.prices.shift();
        }
        if (this.prices.length < this.period) return null;

        const highest = this.getHighest(this.prices);
        const lowest = this.getLowest(this.prices);

        let value = 0.33 * 2 * ((price - lowest) / (highest - lowest) - 0.5) + 0.67 * (this.fisher || 0);
        value = Math.min(Math.max(value, -0.999), 0.999); // Clamp value

        const new_fisher = 0.5 * Math.log((1 + value) / (1 - value));
        this.trigger = this.fisher;
        this.fisher = new_fisher;

        if (this.trigger === null) return null;

        return { fisher: this.fisher, trigger: this.trigger };
    }
}