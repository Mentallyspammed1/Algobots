const { Decimal } = require('decimal.js');

/**
 * Asynchronous sleep function that pauses execution for a specified duration.
 * 
 * @param {number} ms - The duration in milliseconds to sleep.
 * @returns {Promise<void>} A promise that resolves after the specified duration.
 */
async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Rounds quantity to exchange step size
 * @param {Decimal} qty
 * @param {Decimal} step
 * @returns {Decimal}
 */
function round_qty(qty, step) {
    if (step.lte(0)) return qty;
    return qty.dividedToIntegerBy(step).times(step);
}

/**
 * Rounds price to specified decimal precision
 * @param {Decimal} price
 * @param {number} precision
 * @returns {Decimal}
 */
function round_price(price, precision) {
    if (precision < 0) precision = 0;
    const factor = new Decimal(10).pow(precision);
    return Decimal.floor(price.times(factor)).dividedBy(factor);
}

/**
 * Clamps value between min and max
 * @param {number} val
 * @param {number} min
 * @param {number} max
 * @returns {number}
 */
function np_clip(val, min, max) {
    return Math.min(Math.max(val, min), max);
}

module.exports = {
    sleep,
    round_qty,
    round_price,
    np_clip,
};
