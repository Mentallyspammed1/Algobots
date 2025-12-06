import { Decimal } from 'decimal.js';

/**
 * A collection of pure utility functions for mathematical operations and data handling.
 */

/**
 * Creates a new array of a given length, filled with zeros.
 * @param {number} len The length of the array.
 * @returns {number[]} A new array filled with zeros.
 */
export const safeArray = (len) => new Array(Math.max(0, Math.floor(len))).fill(0);

/**
 * Calculates the sum of all numbers in an array.
 * @param {number[]} arr The array of numbers.
 * @returns {number} The sum of the numbers.
 */
export const sum = (arr) => arr.reduce((a, b) => a + b, 0);

/**
 * Calculates the average of numbers in an array.
 * @param {number[]} arr The array of numbers.
 * @returns {number} The average of the numbers.
 */
export const average = (arr) => (arr && arr.length ? sum(arr) / arr.length : 0);

/**
 * Calculates the standard deviation of a slice of an array.
 * This is not optimal for per-tick updates but reflects the original logic.
 * @param {number[]} arr The array of numbers.
 * @param {number} period The period over which to calculate the standard deviation.
 * @returns {number[]} An array containing the standard deviation for each point.
 */
export const stdDev = (arr, period) => {
    if (!arr || arr.length < period) return safeArray(arr.length);
    const result = safeArray(arr.length);
    for (let i = period - 1; i < arr.length; i++) {
        const slice = arr.slice(i - period + 1, i + 1);
        const mean = average(slice);
        const variance = average(slice.map(x => Math.pow(x - mean, 2)));
        result[i] = Math.sqrt(variance);
    }
    return result;
};

/**
 * Gets the current time as a formatted string.
 * @returns {string} Formatted time string (HH:MM:SS).
 */
export const timestamp = () => new Date().toLocaleTimeString();

/**
 * Calculates the trade size based on balance and risk parameters.
 * @param {number|string} balance The total balance.
 * @param {number|string} entry The entry price.
 * @param {number|string} sl The stop-loss price.
 * @param {number} riskPct The percentage of the balance to risk.
 * @returns {Decimal} The calculated trade size.
 */
export const calcSize = (balance, entry, sl, riskPct) => {
    const bal = new Decimal(balance);
    const ent = new Decimal(entry);
    const stop = new Decimal(sl);
    const riskAmt = bal.mul(riskPct).div(100);
    const riskPerCoin = ent.minus(stop).abs();
    
    if (riskPerCoin.eq(0)) return new Decimal(0);
    
    // Returns position size in base currency (e.g., BTC for BTCUSDT)
    return riskAmt.div(riskPerCoin).toDecimalPlaces(3, Decimal.ROUND_DOWN);
};
