// indicators.js

import { Decimal } from 'decimal.js'; // eslint-disable-line no-unused-vars

/**
 * Calculates the Average True Range (ATR) for a given set of klines.
 * @param {Array<Object>} klines - An array of kline objects, each with high, low, and close properties.
 * @param {number} period - The period over which to calculate the ATR.
 * @returns {number|null} The calculated ATR value, or null if insufficient data.
 */
function calculateATR(klines, period) {
    if (klines.length < period) {
        return null;
    }

    let trs = [];
    for (let i = 1; i < klines.length; i++) {
        const high = klines[i].high;
        const low = klines[i].low;
        const prevClose = klines[i - 1].close;

        const tr1 = high - low;
        const tr2 = Math.abs(high - prevClose);
        const tr3 = Math.abs(low - prevClose);
        trs.push(Math.max(tr1, tr2, tr3));
    }

    let atr = trs.slice(0, period).reduce((sum, tr) => sum + tr, 0) / period;

    for (let i = period; i < trs.length; i++) {
        atr = (atr * (period - 1) + trs[i]) / period;
    }

    return atr;
}

export {
    calculateATR,
};
