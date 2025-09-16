import { z } from 'zod';
import type { KlineEntry } from './bybit-api';
import { getKline as getKlineFromApi } from './bybit-api';

// #region Schemas and Types
export const IndicatorSettings = z.object({
  rsi: z.object({ period: z.number().int().positive().default(14), overbought: z.number().default(70), oversold: z.number().default(30) }).default({}),
  macd: z.object({ fast: z.number().int().positive().default(12), slow: z.number().int().positive().default(26), signal: z.number().int().positive().default(9) }).default({}),
  bollingerBands: z.object({ period: z.number().int().positive().default(20), stdDev: z.number().positive().default(2) }).default({}),
  stochastic: z.object({ period: z.number().int().positive().default(14), slowing: z.number().int().positive().default(3), overbought: z.number().default(80), oversold: z.number().default(20) }).default({}),
  atr: z.object({ period: z.number().int().positive().default(14) }).default({}),
  williamsR: z.object({ period: z.number().int().positive().default(14), overbought: z.number().default(-20), oversold: z.number().default(-80) }).default({}),
  cci: z.object({ period: z.number().int().positive().default(20), overbought: z.number().default(100), oversold: z.number().default(-100) }).default({}),
  roc: z.object({ period: z.number().int().positive().default(12) }).default({}),
  mfi: z.object({ period: z.number().int().positive().default(14), overbought: z.number().default(80), oversold: z.number().default(20) }).default({}),
  awesomeOscillator: z.object({ fast: z.number().int().positive().default(5), slow: z.number().int().positive().default(34) }).default({}),
  ichimokuCloud: z.object({ tenkan: z.number().int().positive().default(9), kijun: z.number().int().positive().default(26), senkou: z.number().int().positive().default(52), displacement: z.number().int().positive().default(26) }).default({}),
  sma: z.object({ period: z.number().int().positive().default(20) }).default({}),
  supertrendFast: z.object({ atrPeriod: z.number().int().positive().default(10), multiplier: z.number().positive().default(2) }).default({}),
  supertrendSlow: z.object({ atrPeriod: z.number().int().positive().default(20), multiplier: z.number().positive().default(4) }).default({}),
  fisher: z.object({ period: z.number().int().positive().default(9) }).default({}),
  ehlers: z.object({ period: z.number().int().positive().default(10) }).default({}),
  chandelier: z.object({ period: z.number().int().positive().default(22), multiplier: z.number().positive().default(3) }).default({}),
});
export type IndicatorSettings = z.infer<typeof IndicatorSettings>;

export const defaultIndicatorSettings: IndicatorSettings = IndicatorSettings.parse({});

const RsiResultSchema = z.object({ rsi: z.number() });
const MacdResultSchema = z.object({ macd: z.number(), signal: z.number(), histogram: z.number() });
const BollingerBandsResultSchema = z.object({ upper: z.number(), middle: z.number(), lower: z.number() });
const StochasticResultSchema = z.object({ k: z.number(), d: z.number() });
const AtrResultSchema = z.object({ atr: z.number() });
const ObvResultSchema = z.object({ obv: z.number() });
const WilliamsRResultSchema = z.object({ williamsR: z.number() });
const CciResultSchema = z.object({ cci: z.number() });
const RocResultSchema = z.object({ roc: z.number() });
const MfiResultSchema = z.object({ mfi: z.number() });
const AwesomeOscillatorResultSchema = z.object({ ao: z.number() });
const IchimokuCloudResultSchema = z.object({ tenkanSen: z.number(), kijunSen: z.number(), senkouSpanA: z.number(), senkouSpanB: z.number() });
const SmaResultSchema = z.object({ sma: z.number() });
const SupertrendResultSchema = z.object({ direction: z.enum(['buy', 'sell']), supertrend: z.number() });
const FisherTransformResultSchema = z.object({ fisher: z.number(), trigger: z.number() });
const EhlersTrendlineResultSchema = z.object({ trendline: z.number() });
const ChandelierExitResultSchema = z.object({ long: z.number(), short: z.number() });


export const IndicatorDataSchema = z.object({
    rsi: RsiResultSchema.optional(),
    macd: MacdResultSchema.optional(),
    bollingerBands: BollingerBandsResultSchema.optional(),
    stochastic: StochasticResultSchema.optional(),
    atr: AtrResultSchema.optional(),
    obv: ObvResultSchema.optional(),
    williamsR: WilliamsRResultSchema.optional(),
    cci: CciResultSchema.optional(),
    roc: RocResultSchema.optional(),
    mfi: MfiResultSchema.optional(),
    awesomeOscillator: AwesomeOscillatorResultSchema.optional(),
    ichimokuCloud: IchimokuCloudResultSchema.optional(),
    sma: SmaResultSchema.optional(),
    supertrendFast: SupertrendResultSchema.optional(),
    supertrendSlow: SupertrendResultSchema.optional(),
    fisher: FisherTransformResultSchema.optional(),
    ehlers: EhlersTrendlineResultSchema.optional(),
    chandelier: ChandelierExitResultSchema.optional(),
});
export type IndicatorData = z.infer<typeof IndicatorDataSchema>;
// #endregion

// Export getKline for external use (e.g. in actions.ts)
export const getKline = getKlineFromApi;

// #region Calculation Utilities
function sma(data: number[], period: number): (number | null)[] {
    if (data.length < period) return new Array(data.length).fill(null);
    
    const results: (number | null)[] = new Array(period - 1).fill(null);
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += data[i];
    }
    results.push(sum / period);

    for (let i = period; i < data.length; i++) {
        sum += data[i] - data[i - period];
        results.push(sum / period);
    }
    return results;
}

function ema(data: number[], period: number): (number | null)[] {
    if (data.length < period) return new Array(data.length).fill(null);
    
    const results: (number | null)[] = [];
    const multiplier = 2 / (period + 1);
    
    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += data[i];
        results.push(null);
    }
    
    let prevEma = sum / period;
    results[period - 1] = prevEma;

    for (let i = period; i < data.length; i++) {
        const emaValue = (data[i] - prevEma) * multiplier + prevEma;
        results.push(emaValue);
        prevEma = emaValue;
    }
    return results;
}

abstract class Indicator<T = number | object | null> {
    protected data: KlineEntry[];
    constructor(data: KlineEntry[]) { this.data = data; }
    abstract calculate(): (T | null)[];
    
    public getResult(): T | undefined {
        const results = this.calculate();
        const lastResult = results.length > 0 ? results[results.length - 1] : null;

        if (lastResult === null || lastResult === undefined) return undefined;

        if (typeof lastResult === 'object') {
            for (const key in lastResult) {
                const value = (lastResult as any)[key];
                if (typeof value === 'number' && (isNaN(value) || !isFinite(value))) {
                    return undefined;
                }
            }
        } else if (typeof lastResult === 'number' && (isNaN(lastResult) || !isFinite(lastResult))) {
            return undefined;
        }

        return lastResult as T;
    }
}
// #endregion

// #region Indicator Classes
class SMA extends Indicator<z.infer<typeof SmaResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof SmaResultSchema> | null)[] {
        const closes = this.data.map(d => d.close);
        const smaValues = sma(closes, this.period);
        return smaValues.map(s => s === null ? null : { sma: s });
    }
}

class RSI extends Indicator<z.infer<typeof RsiResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof RsiResultSchema> | null)[] {
        const closes = this.data.map(d => d.close);
        if (closes.length <= this.period) return new Array(closes.length).fill(null);

        const results: (z.infer<typeof RsiResultSchema> | null)[] = new Array(this.period).fill(null);
        let gains = 0, losses = 0;

        for (let i = 1; i <= this.period; i++) {
            const diff = closes[i] - closes[i - 1];
            if (diff > 0) gains += diff;
            else losses -= diff;
        }

        let avgGain = gains / this.period;
        let avgLoss = losses / this.period;

        let rs = avgLoss !== 0 ? avgGain / avgLoss : 0;
        results.push({ rsi: 100 - (100 / (1 + rs)) });

        for (let i = this.period + 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            let gain = 0, loss = 0;
            if (diff > 0) gain = diff;
            else loss = -diff;

            avgGain = (avgGain * (this.period - 1) + gain) / this.period;
            avgLoss = (avgLoss * (this.period - 1) + loss) / this.period;
            
            rs = avgLoss !== 0 ? avgGain / avgLoss : 0;
            results.push({ rsi: 100 - (100 / (1 + rs)) });
        }
        return results;
    }
}

class MACD extends Indicator<z.infer<typeof MacdResultSchema>> {
    constructor(data: KlineEntry[], private fast: number, private slow: number, private signal: number) { super(data); }
    calculate(): (z.infer<typeof MacdResultSchema> | null)[] {
        const closes = this.data.map(d => d.close);
        const emaFast = ema(closes, this.fast);
        const emaSlow = ema(closes, this.slow);

        const macdLine = emaFast.map((f, i) => (f === null || emaSlow[i] === null) ? null : f - emaSlow[i]!);
        const signalLine = ema(macdLine.filter(m => m !== null) as number[], this.signal);

        let signalIdx = 0;
        return macdLine.map(m => {
            if (m === null) return null;
            const signalVal = signalLine[signalIdx];
            signalIdx++;
            if (signalVal === null || signalVal === undefined) return null;
            return { macd: m, signal: signalVal, histogram: m - signalVal };
        });
    }
}

class BollingerBands extends Indicator<z.infer<typeof BollingerBandsResultSchema>> {
    constructor(data: KlineEntry[], private period: number, private stdDev: number) { super(data); }
    calculate(): (z.infer<typeof BollingerBandsResultSchema> | null)[] {
        const closes = this.data.map(d => d.close);
        const middleBand = sma(closes, this.period);

        return middleBand.map((mb, i) => {
            if (mb === null) return null;
            const slice = closes.slice(i - this.period + 1, i + 1);
            const variance = slice.reduce((acc, val) => acc + Math.pow(val - mb, 2), 0) / this.period;
            const sd = Math.sqrt(variance);
            return { upper: mb + (sd * this.stdDev), middle: mb, lower: mb - (sd * this.stdDev) };
        });
    }
}

class Stochastic extends Indicator<z.infer<typeof StochasticResultSchema>> {
    constructor(data: KlineEntry[], private period: number, private slowing: number) { super(data); }
    calculate(): (z.infer<typeof StochasticResultSchema> | null)[] {
        const kValues: (number | null)[] = new Array(this.period - 1).fill(null);
        for (let i = this.period - 1; i < this.data.length; i++) {
            const slice = this.data.slice(i - this.period + 1, i + 1);
            const highestHigh = Math.max(...slice.map(d => d.high));
            const lowestLow = Math.min(...slice.map(d => d.low));
            const k = lowestLow === highestHigh ? 100 : ((this.data[i].close - lowestLow) / (highestHigh - lowestLow)) * 100;
            kValues.push(k);
        }
        const dValues = sma(kValues.filter(k => k !== null) as number[], this.slowing);
        
        let dIdx = 0;
        return kValues.map(k => {
            if(k === null) return null;
            const d = dValues[dIdx];
            dIdx++;
            if (d === null || d === undefined) return null;
            return { k, d };
        })
    }
}

class ATR extends Indicator<z.infer<typeof AtrResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof AtrResultSchema> | null)[] {
        if (this.data.length < this.period) return new Array(this.data.length).fill(null);

        const trs: number[] = [this.data[0].high - this.data[0].low];
        for (let i = 1; i < this.data.length; i++) {
            trs.push(Math.max(
                this.data[i].high - this.data[i].low,
                Math.abs(this.data[i].high - this.data[i-1].close),
                Math.abs(this.data[i].low - this.data[i-1].close)
            ));
        }
        const atrSma = sma(trs, this.period);
        return atrSma.map(a => a === null ? null : { atr: a });
    }
}

class OBV extends Indicator<z.infer<typeof ObvResultSchema>> {
    constructor(data: KlineEntry[]) { super(data); }
    calculate(): (z.infer<typeof ObvResultSchema> | null)[] {
        if(this.data.length === 0) return [];
        const results: (z.infer<typeof ObvResultSchema> | null)[] = [{ obv: 0 }];
        for (let i = 1; i < this.data.length; i++) {
            const prevObv = results[i-1]!.obv;
            const close = this.data[i].close;
            const prevClose = this.data[i - 1].close;
            const volume = this.data[i].volume;
            if (close > prevClose) results.push({ obv: prevObv + volume });
            else if (close < prevClose) results.push({ obv: prevObv - volume });
            else results.push({ obv: prevObv });
        }
        return results;
    }
}

class WilliamsR extends Indicator<z.infer<typeof WilliamsRResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof WilliamsRResultSchema> | null)[] {
        return this.data.map((_, i) => {
            if (i < this.period - 1) return null;
            const slice = this.data.slice(i - this.period + 1, i + 1);
            const highestHigh = Math.max(...slice.map(d => d.high));
            const lowestLow = Math.min(...slice.map(d => d.low));
            const r = lowestLow === highestHigh ? -50 : ((highestHigh - this.data[i].close) / (highestHigh - lowestLow)) * -100;
            return { williamsR: r };
        });
    }
}

class CCI extends Indicator<z.infer<typeof CciResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof CciResultSchema> | null)[] {
        return this.data.map((_, i) => {
            if (i < this.period - 1) return null;
            const slice = this.data.slice(i - this.period + 1, i + 1);
            const typicalPrices = slice.map(d => (d.high + d.low + d.close) / 3);
            const smaTp = typicalPrices.reduce((a, b) => a + b, 0) / this.period;
            const meanDeviation = typicalPrices.reduce((acc, val) => acc + Math.abs(val - smaTp), 0) / this.period;
            if(meanDeviation === 0) return { cci: 0 };
            const cci = ((typicalPrices[this.period - 1] - smaTp) / (0.015 * meanDeviation));
            return { cci };
        });
    }
}

class ROC extends Indicator<z.infer<typeof RocResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof RocResultSchema> | null)[] {
        const closes = this.data.map(d => d.close);
        return closes.map((c, i) => {
            if (i < this.period) return null;
            const prevClose = closes[i - this.period];
            if(prevClose === 0) return { roc: 0 };
            return { roc: ((c - prevClose) / prevClose) * 100 };
        });
    }
}

class MFI extends Indicator<z.infer<typeof MfiResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof MfiResultSchema> | null)[] {
        const typicalPrices = this.data.map(d => (d.high + d.low + d.close) / 3);
        const rawMoneyFlow = typicalPrices.map((tp, i) => tp * this.data[i].volume);

        const posMoneyFlow: number[] = [], negMoneyFlow: number[] = [];
        for (let i = 1; i < typicalPrices.length; i++) {
            if (typicalPrices[i] > typicalPrices[i-1]) {
                posMoneyFlow.push(rawMoneyFlow[i]);
                negMoneyFlow.push(0);
            } else {
                posMoneyFlow.push(0);
                negMoneyFlow.push(rawMoneyFlow[i]);
            }
        }
        
        const results: (z.infer<typeof MfiResultSchema> | null)[] = new Array(this.period).fill(null);

        for (let i = this.period; i < typicalPrices.length; i++) {
            const posSum = posMoneyFlow.slice(i - this.period, i).reduce((a, b) => a + b, 0);
            const negSum = negMoneyFlow.slice(i - this.period, i).reduce((a, b) => a + b, 0);
            if (negSum === 0) {
                 results.push({ mfi: 100 });
                 continue;
            }
            const moneyRatio = posSum / negSum;
            results.push({ mfi: 100 - (100 / (1 + moneyRatio)) });
        }
        return results;
    }
}

class AwesomeOscillator extends Indicator<z.infer<typeof AwesomeOscillatorResultSchema>> {
    constructor(data: KlineEntry[], private fast: number, private slow: number) { super(data); }
    calculate(): (z.infer<typeof AwesomeOscillatorResultSchema> | null)[] {
        const midpoints = this.data.map(d => (d.high + d.low) / 2);
        const smaFast = sma(midpoints, this.fast);
        const smaSlow = sma(midpoints, this.slow);
        return smaSlow.map((s, i) => {
            if (s === null || smaFast[i] === null) return null;
            return { ao: smaFast[i]! - s };
        });
    }
}

class IchimokuCloud extends Indicator<z.infer<typeof IchimokuCloudResultSchema>> {
    constructor(data: KlineEntry[], private tenkan: number, private kijun: number, private senkou: number) { super(data); }
    calculate(): (z.infer<typeof IchimokuCloudResultSchema> | null)[] {
        const results: (z.infer<typeof IchimokuCloudResultSchema> | null)[] = [];
        for (let i = 0; i < this.data.length; i++) {
            const tenkanSen = this.getTenkan(i);
            const kijunSen = this.getKijun(i);
            const senkouSpanA = (tenkanSen !== null && kijunSen !== null) ? (tenkanSen + kijunSen) / 2 : null;
            const senkouSpanB = this.getSenkouB(i);
            results.push( tenkanSen === null ? null : { tenkanSen, kijunSen, senkouSpanA, senkouSpanB });
        }
        return results;
    }
    private getTenkan(i: number) {
        if (i < this.tenkan - 1) return null;
        const slice = this.data.slice(i - this.tenkan + 1, i + 1);
        const high = Math.max(...slice.map(d => d.high));
        const low = Math.min(...slice.map(d => d.low));
        return (high + low) / 2;
    }
    private getKijun(i: number) {
        if (i < this.kijun - 1) return null;
        const slice = this.data.slice(i - this.kijun + 1, i + 1);
        const high = Math.max(...slice.map(d => d.high));
        const low = Math.min(...slice.map(d => d.low));
        return (high + low) / 2;
    }
    private getSenkouB(i: number) {
        if (i < this.senkou - 1) return null;
        const slice = this.data.slice(i - this.senkou + 1, i + 1);
        const high = Math.max(...slice.map(d => d.high));
        const low = Math.min(...slice.map(d => d.low));
        return (high + low) / 2;
    }
}

class Supertrend extends Indicator<z.infer<typeof SupertrendResultSchema>> {
    constructor(data: KlineEntry[], private period: number, private multiplier: number) { super(data); }
    calculate(): (z.infer<typeof SupertrendResultSchema> | null)[] {
        const atrIndicator = new ATR(this.data, this.period);
        const atrs = atrIndicator.calculate();
        const results: (z.infer<typeof SupertrendResultSchema> | null)[] = new Array(this.data.length).fill(null);
        let direction: 'buy' | 'sell' = 'buy';
        let upperBand = 0, lowerBand = 0, supertrend = 0;

        for (let i = this.period; i < this.data.length; i++) {
            const close = this.data[i].close;
            const high = this.data[i].high;
            const low = this.data[i].low;
            const atrResult = atrs[i];

            if (atrResult === null) continue;
            const atr = atrResult.atr;

            const prevResult = results[i-1];
            const prevSupertrend = prevResult ? prevResult.supertrend : 0;
            const prevDirection = prevResult ? prevResult.direction : 'buy';

            upperBand = ((high + low) / 2) + (this.multiplier * atr);
            lowerBand = ((high + low) / 2) - (this.multiplier * atr);
            
            if (prevDirection === 'buy') {
                if (close < prevSupertrend) {
                    direction = 'sell';
                    supertrend = upperBand;
                } else {
                    direction = 'buy';
                    supertrend = Math.max(lowerBand, prevSupertrend);
                }
            } else { // 'sell'
                if (close > prevSupertrend) {
                    direction = 'buy';
                    supertrend = lowerBand;
                } else {
                    direction = 'sell';
                    supertrend = Math.min(upperBand, prevSupertrend);
                }
            }
            results[i] = { direction, supertrend };
        }
        return results;
    }
}


class FisherTransform extends Indicator<z.infer<typeof FisherTransformResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof FisherTransformResultSchema> | null)[] {
        const results: (z.infer<typeof FisherTransformResultSchema> | null)[] = [];
        let fisherValues: number[] = [];
        for (let i = 0; i < this.data.length; i++) {
             if (i < this.period - 1) {
                results.push(null);
                continue;
            }
            const slice = this.data.slice(i - this.period + 1, i + 1);
            const highest = Math.max(...slice.map(d => (d.high + d.low)/2));
            const lowest = Math.min(...slice.map(d => (d.high + d.low)/2));
            let value = 0.33 * 2 * ((((this.data[i].high + this.data[i].low)/2 - lowest) / (highest - lowest)) - 0.5) + 0.67 * (results[i-1]?.fisher ?? 0);
            if (value > 0.99) value = 0.999;
            if (value < -0.99) value = -0.999;

            const fisher = 0.5 * Math.log((1 + value) / (1 - value))
            fisherValues.push(fisher);
            const trigger = fisherValues.length > 1 ? fisherValues[fisherValues.length - 2] : 0;
            results.push({ fisher, trigger });
        }
        return results;
    }
}

class EhlersTrendline extends Indicator<z.infer<typeof EhlersTrendlineResultSchema>> {
    constructor(data: KlineEntry[], private period: number) { super(data); }
    calculate(): (z.infer<typeof EhlersTrendlineResultSchema> | null)[] {
        const prices = this.data.map(d => (d.high + d.low) / 2);
        const trendlines: (number|null)[] = [];
        for (let i = 0; i < prices.length; i++) {
             if (i < this.period) {
                trendlines.push(null);
                continue;
            }
            let sum = 0;
            for (let j = 0; j < this.period; j++) {
                sum += prices[i - j] * (j + 1);
            }
            trendlines.push(sum / ((this.period * (this.period + 1)) / 2));
        }
        return trendlines.map(t => t === null ? null : { trendline: t });
    }
}

class ChandelierExit extends Indicator<z.infer<typeof ChandelierExitResultSchema>> {
    constructor(data: KlineEntry[], private period: number, private multiplier: number) { super(data); }
    calculate(): (z.infer<typeof ChandelierExitResultSchema> | null)[] {
        const atrIndicator = new ATR(this.data, this.period);
        const atrs = atrIndicator.calculate();
        const results: (z.infer<typeof ChandelierExitResultSchema> | null)[] = [];
        
        for (let i = 0; i < this.data.length; i++) {
             if (i < this.period || atrs[i] === null) {
                results.push(null);
                continue;
            }
            const dataSlice = this.data.slice(i - this.period + 1, i + 1);
            const highestHigh = Math.max(...dataSlice.map(d => d.high));
            const lowestLow = Math.min(...dataSlice.map(d => d.low));
            const atr = atrs[i]!.atr;

            results.push({
                long: highestHigh - atr * this.multiplier,
                short: lowestLow + atr * this.multiplier,
            });
        }
        return results;
    }
}
// #endregion

// #region Main Calculation Function
export function calculateIndicators(data: KlineEntry[], settings: IndicatorSettings): IndicatorData | null {
  if (data.length === 0) return null;

  return {
    sma: new SMA(data, settings.sma.period).getResult(),
    rsi: new RSI(data, settings.rsi.period).getResult(),
    macd: new MACD(data, settings.macd.fast, settings.macd.slow, settings.macd.signal).getResult(),
    bollingerBands: new BollingerBands(data, settings.bollingerBands.period, settings.bollingerBands.stdDev).getResult(),
    stochastic: new Stochastic(data, settings.stochastic.period, settings.stochastic.slowing).getResult(),
    atr: new ATR(data, settings.atr.period).getResult(),
    obv: new OBV(data).getResult(),
    williamsR: new WilliamsR(data, settings.williamsR.period).getResult(),
    cci: new CCI(data, settings.cci.period).getResult(),
    roc: new ROC(data, settings.roc.period).getResult(),
    mfi: new MFI(data, settings.mfi.period).getResult(),
    awesomeOscillator: new AwesomeOscillator(data, settings.awesomeOscillator.fast, settings.awesomeOscillator.slow).getResult(),
    ichimokuCloud: new IchimokuCloud(data, settings.ichimokuCloud.tenkan, settings.ichimokuCloud.kijun, settings.ichimokuCloud.senkou).getResult(),
    supertrendFast: new Supertrend(data, settings.supertrendFast.atrPeriod, settings.supertrendFast.multiplier).getResult(),
    supertrendSlow: new Supertrend(data, settings.supertrendSlow.atrPeriod, settings.supertrendSlow.multiplier).getResult(),
    fisher: new FisherTransform(data, settings.fisher.period).getResult(),
    ehlers: new EhlersTrendline(data, settings.ehlers.period).getResult(),
    chandelier: new ChandelierExit(data, settings.chandelier.period, settings.chandelier.multiplier).getResult(),
  };
}
// #endregion
