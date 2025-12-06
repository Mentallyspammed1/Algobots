import fs from 'node:fs/promises';
import path from 'node:path';

import { safeArray } from './utils.js'; // Assuming safeArray is in utils.js
import { ema, rsi, fisher, atr, bollinger, macd, stochRSI, adx, williamsR } from './technical-analysis.js';
import { sma, wma, t3, superTrend, vwap, hullMA, choppiness, connorsRSI, kaufmanER, ichimoku, schaffTC, dpo } from './technical-analysis-advanced.js';

describe('Technical Analysis Functions with Historical Data', () => {
    let klines = [];
    let closes = [];
    let highs = [];
    let lows = [];
    let volumes = [];

    beforeAll(async () => {
        const filePath = path.resolve(process.cwd(), 'historical_klines.json');
        const data = await fs.readFile(filePath, 'utf-8');
        klines = JSON.parse(data);

        closes = klines.map(k => k.close);
        highs = klines.map(k => k.high);
        lows = klines.map(k => k.low);
        volumes = klines.map(k => k.volume);

        if (klines.length === 0) {
            throw new Error("No historical klines loaded. Please ensure historical_klines.json exists and contains data.");
        }
    });

    // Helper to check basic array properties for indicator results
    const checkIndicatorOutput = (output, inputLength, expectedZeroPrefixLength = 0, isNested = false) => {
        if (!isNested) {
            expect(Array.isArray(output)).toBe(true);
            expect(output.length).toBe(inputLength);
            // Check that initial values are zero or NaN (depending on indicator logic)
            for (let i = 0; i < expectedZeroPrefixLength; i++) {
                // Allow for 0 or NaN during warm-up
                expect(output[i] === 0 || isNaN(output[i]) || !isFinite(output[i])).toBe(true);
            }
            // Check that subsequent values are numbers and not NaN
            for (let i = expectedZeroPrefixLength; i < inputLength; i++) {
                expect(typeof output[i]).toBe('number');
                expect(isNaN(output[i])).toBe(false);
                expect(isFinite(output[i])).toBe(true); // Ensure not Infinity
            }
        } else {
            // For nested indicators like MACD, Bollinger, etc.
            Object.values(output).forEach(arr => {
                expect(Array.isArray(arr)).toBe(true);
                expect(arr.length).toBe(inputLength);
                for (let i = 0; i < expectedZeroPrefixLength; i++) {
                    // Allow for 0 or NaN during warm-up for nested arrays as well
                    expect(arr[i] === 0 || isNaN(arr[i]) || !isFinite(arr[i])).toBe(true);
                }
                for (let i = expectedZeroPrefixLength; i < inputLength; i++) {
                    expect(typeof arr[i]).toBe('number');
                    expect(isNaN(arr[i])).toBe(false);
                    expect(isFinite(arr[i])).toBe(true); // Ensure not Infinity
                }
            });
        }
    };

    describe('sma', () => {
        it('should calculate SMA correctly and return expected length and type with historical data', () => {
            const period = 20;
            const smaValues = sma(closes, period);
            checkIndicatorOutput(smaValues, closes.length, period - 1);
        });
    });

    describe('ema', () => {
        it('should calculate EMA correctly and return expected length and type with historical data', () => {
            const period = 20;
            const emaValues = ema(closes, period);
            checkIndicatorOutput(emaValues, closes.length, period - 1);
        });
    });

    describe('rsi', () => {
        it('should calculate RSI correctly and return expected length and type with historical data', () => {
            const period = 14;
            const rsiValues = rsi(closes, period);
            checkIndicatorOutput(rsiValues, closes.length, period);
            // Additionally check that RSI values are within the 0-100 range after the warm-up period
            for (let i = period; i < rsiValues.length; i++) {
                expect(rsiValues[i]).toBeGreaterThanOrEqual(0);
                expect(rsiValues[i]).toBeLessThanOrEqual(100);
            }
        });
    });

    describe('fisher', () => {
        it('should calculate Fisher Transform correctly and return expected length and type with historical data', () => {
            const period = 9;
            const fisherValues = fisher(highs, lows, period);
            checkIndicatorOutput(fisherValues, klines.length, period - 1);
        });
    });

    describe('atr', () => {
        it('should calculate ATR correctly and return expected length and type with historical data', () => {
            const period = 14;
            const atrValues = atr(highs, lows, closes, period);
            checkIndicatorOutput(atrValues, klines.length, period); // ATR usually needs initial period to warm up
        });
    });

    describe('bollinger', () => {
        it('should calculate Bollinger Bands correctly and return expected length and type with historical data', () => {
            const period = 20;
            const stdDev = 2;
            const bbValues = bollinger(closes, period, stdDev);
            checkIndicatorOutput(bbValues, klines.length, period - 1, true); // Nested output
        });
    });

    describe('macd', () => {
        it('should calculate MACD correctly and return expected length and type with historical data', () => {
            const fastPeriod = 12;
            const slowPeriod = 26;
            const signalPeriod = 9;
            const macdValues = macd(closes, fastPeriod, slowPeriod, signalPeriod);
            checkIndicatorOutput(macdValues, klines.length, slowPeriod + signalPeriod - 2, true); // Nested output, longest period for warm-up
        });
    });

    describe('stochRSI', () => {
        it('should calculate StochRSI correctly and return expected length and type with historical data', () => {
            const rsiPeriod = 14;
            const stochPeriod = 14;
            const kPeriod = 3;
            const dPeriod = 3;
            const stochRSIValues = stochRSI(closes, rsiPeriod, stochPeriod, kPeriod, dPeriod);
            checkIndicatorOutput(stochRSIValues, klines.length, rsiPeriod + stochPeriod - 1, true); // Nested output, combined period for warm-up
            
            // Additionally check that %K and %D values are within the 0-100 range
            for (let i = rsiPeriod + stochPeriod - 1; i < stochRSIValues.k.length; i++) {
                expect(stochRSIValues.k[i]).toBeGreaterThanOrEqual(0);
                expect(stochRSIValues.k[i]).toBeLessThanOrEqual(100);
                expect(stochRSIValues.d[i]).toBeGreaterThanOrEqual(0);
                expect(stochRSIValues.d[i]).toBeLessThanOrEqual(100);
            }
        });
    });

    describe('adx', () => {
        it('should calculate ADX correctly and return expected length and type with historical data', () => {
            const period = 14;
            const adxValues = adx(highs, lows, closes, period);
            checkIndicatorOutput(adxValues, klines.length, period * 2 -1, true); // Nested output, ADX takes longer to warm up
        });
    });

    describe('williamsR', () => {
        it('should calculate Williams %R correctly and return expected length and type with historical data', () => {
            const period = 14;
            const wrValues = williamsR(highs, lows, closes, period);
            checkIndicatorOutput(wrValues, klines.length, period - 1);
            // Additionally check that W%R values are within the -100 to 0 range
            for (let i = period - 1; i < wrValues.length; i++) {
                expect(wrValues[i]).toBeGreaterThanOrEqual(-100);
                expect(wrValues[i]).toBeLessThanOrEqual(0);
            }
        });
    });

    describe('wma', () => {
        it('should calculate WMA correctly and return expected length and type with historical data', () => {
            const period = 20;
            const wmaValues = wma(closes, period);
            checkIndicatorOutput(wmaValues, closes.length, period - 1);
        });
    });

    describe('t3', () => {
        it('should calculate T3 Moving Average correctly and return expected length and type with historical data', () => {
            const period = 10;
            const t3Values = t3(closes, period);
            checkIndicatorOutput(t3Values, closes.length, period * 6 -1); // T3 has a very long warm-up period
        });
    });

    describe('superTrend', () => {
        it('should calculate SuperTrend correctly and return expected length and type with historical data', () => {
            const period = 10;
            const multiplier = 3;
            const stValues = superTrend(highs, lows, closes, period, multiplier);
            expect(stValues).toHaveProperty('trend');
            expect(stValues).toHaveProperty('direction');
            checkIndicatorOutput(stValues.trend, klines.length, period - 1);
            checkIndicatorOutput(stValues.direction, klines.length, period - 1);
        });
    });

    describe('vwap', () => {
        it('should calculate VWAP correctly and return expected length and type with historical data', () => {
            // VWAP often starts calculating from the first bar, so minimal zero prefix is expected if any.
            // However, our implementation accumulates, so the whole array should have values.
            const vwapValues = vwap(highs, lows, closes, volumes);
            checkIndicatorOutput(vwapValues, klines.length, 0); 
        });
    });

    describe('hullMA', () => {
        it('should calculate Hull Moving Average correctly and return expected length and type with historical data', () => {
            const period = 16;
            const hmaValues = hullMA(closes, period);
            // Hull MA warm-up depends on WMA inside, roughly period + sqrtPeriod - 2
            checkIndicatorOutput(hmaValues, closes.length, period + Math.floor(Math.sqrt(period)) - 2); 
        });
    });

    describe('choppiness', () => {
        it('should calculate Choppiness Index correctly and return expected length and type with historical data', () => {
            const period = 14;
            const choppinessValues = choppiness(highs, lows, closes, period);
            checkIndicatorOutput(choppinessValues, klines.length, period - 1);
            // Additionally check that Choppiness values are within the 0-100 range
            for (let i = period - 1; i < choppinessValues.length; i++) {
                expect(choppinessValues[i]).toBeGreaterThanOrEqual(0);
                expect(choppinessValues[i]).toBeLessThanOrEqual(100);
            }
        });
    });

    describe('connorsRSI', () => {
        it('should calculate Connors RSI correctly and return expected length and type with historical data', () => {
            const rsiPeriod = 3;
            const streakRsiPeriod = 2;
            const rankPeriod = 100;
            const crsiValues = connorsRSI(closes, rsiPeriod, streakRsiPeriod, rankPeriod);
            // Warm up period is largely determined by rankPeriod
            checkIndicatorOutput(crsiValues, klines.length, rankPeriod - 1);
            for (let i = rankPeriod - 1; i < crsiValues.length; i++) {
                expect(crsiValues[i]).toBeGreaterThanOrEqual(0);
                expect(crsiValues[i]).toBeLessThanOrEqual(100);
            }
        });
    });

    describe('kaufmanER', () => {
        it('should calculate Kaufman Efficiency Ratio correctly and return expected length and type with historical data', () => {
            const period = 10;
            const kerValues = kaufmanER(closes, period);
            checkIndicatorOutput(kerValues, klines.length, period);
            for (let i = period; i < kerValues.length; i++) {
                expect(kerValues[i]).toBeGreaterThanOrEqual(0);
                expect(kerValues[i]).toBeLessThanOrEqual(1);
            }
        });
    });

    describe('ichimoku', () => {
        it('should calculate Ichimoku Cloud components correctly and return expected length and type with historical data', () => {
            const span1 = 9;
            const span2 = 26;
            const span3 = 52;
            const ichimokuValues = ichimoku(highs, lows, closes, span1, span2, span3);
            expect(ichimokuValues).toHaveProperty('conv');
            expect(ichimokuValues).toHaveProperty('base');
            expect(ichimokuValues).toHaveProperty('spanA');
            expect(ichimokuValues).toHaveProperty('spanB');
            // Longest period for warm-up is span3 for spanB
            checkIndicatorOutput(ichimokuValues, klines.length, span3 - 1, true);
        });
    });

    describe('schaffTC', () => {
        it('should calculate Schaff Trend Cycle correctly and return expected length and type with historical data', () => {
            const fast = 23;
            const slow = 50;
            const cycle = 10;
            const stcValues = schaffTC(closes, fast, slow, cycle);
            // STC has multiple EMA and StochRSI calculations internally, so a significant warm-up is expected.
            // Based on (slow for MACD line) + (cycle for StochRSI) + (cycle for StochRSI) + (3 for final EMA)
            // A more precise calculation: warm-up from macd line is `slow-1`, then stochRSI on macd line is `(slow-1) + cycle`, then ema of stochRsi is `(slow-1) + cycle + 3`.
            // Let's use an estimate `slow + 2 * cycle`.
            checkIndicatorOutput(stcValues, klines.length, slow + (2 * cycle)); 
        });
    });

    describe('dpo', () => {
        it('should calculate Detrended Price Oscillator correctly and return expected length and type with historical data', () => {
            const period = 21;
            const dpoValues = dpo(closes, period);
            checkIndicatorOutput(dpoValues, klines.length, period - 1);
        });
    });
});