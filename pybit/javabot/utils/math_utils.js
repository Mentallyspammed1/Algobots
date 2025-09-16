import { Decimal } from 'decimal.js';

/**
 * @function round_qty
 * @description Rounds a quantity to the nearest valid step size for an exchange.
 * @param {Decimal} qty - The quantity to round.
 * @param {Decimal} step - The step size (e.g., 0.001).
 * @returns {Decimal} The rounded quantity.
 */
export function round_qty(qty, step) {
    if (step.lte(0)) return qty;
    return qty.dividedToIntegerBy(step).times(step);
}

/**
 * @function round_price
 * @description Rounds a price to a specified decimal precision.
 * @param {Decimal} price - The price to round.
 * @param {number} precision - The number of decimal places to round to.
 * @returns {Decimal} The rounded price.
 */
export function round_price(price, precision) {
    if (precision < 0) precision = 0;
    const factor = new Decimal(10).pow(precision);
    return Decimal.floor(price.times(factor)).dividedBy(factor);
}

/**
 * @function np_clip
 * @description Clamps a numerical value between a minimum and maximum value.
 * @param {number} val - The value to clamp.
 * @param {number} min - The minimum allowed value.
 * @param {number} max - The maximum allowed value.
 * @returns {number} The clamped value.
 */
export function np_clip(val, min, max) {
    return Math.min(Math.max(val, min), max);
}