const TA = require('../../src/indicators'); // Import all TA functions

describe('Technical Analysis (TA) Functions', () => {

    test('SMA calculates correctly', () => {
        const data = [1,2,3,4,5,6,7];
        // Expect SMA(data, 3) to be [0,0,0,2,3,4,5] (with leading zeros)
        // The last actual SMA value is for [5,6,7] = 6
        // For the test expect(sma(data, 3)).toBe(4); it seems the original sma expected the SMA of the last 'len' elements
        // The new sma returns a full array with leading zeros.
        // We should test the last value of the SMA.
        expect(TA.sma(data, 3)[data.length-1]).toBe(6);
    });

    test('EMA smooths properly', () => {
        const closes = Array(50).fill(100).concat([101,102,103]);
        const val = TA.ema(closes, 20);
        // Expect the last value of EMA.
        expect(val[val.length-1]).toBeGreaterThan(100);
        expect(val[val.length-1]).toBeLessThan(103);
    });

    test('RSI detects overbought/oversold', () => {
        const upTrend = Array(20).fill().map((_,i) => 100 + i);
        const downTrend = Array(20).fill().map((_,i) => 100 - i);
        // Expect the last value of RSI.
        expect(TA.rsi(upTrend, 7)[upTrend.length-1]).toBeGreaterThan(70);
        expect(TA.rsi(downTrend, 7)[downTrend.length-1]).toBeLessThan(30);
    });

    test('SuperTrend flips on breakout', () => {
        const candles = Array(20).fill().map((_,i) => ({
            high: 100 + i*0.1, low: 99 + i*0.1, close: 100 + i*0.1
        }));
        const highs = candles.map(c => c.high);
        const lows = candles.map(c => c.low);
        const closes = candles.map(c => c.close);

        const st = TA.superTrend(highs, lows, closes, 10, 3);
        // Expect the last value of the trend.
        expect(st.trend[st.trend.length-1]).toBe(1);
    });
});