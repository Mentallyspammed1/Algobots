import { InstrumentInfo } from '../core/types';
import { logger } from '../core/logger';

export class Precision {
    private instrumentInfo: InstrumentInfo;

    constructor(instrumentInfo: InstrumentInfo) {
        this.instrumentInfo = instrumentInfo;
    }

    /**
     * Rounds a price to the correct precision (tick size).
     * @param price The price to round.
     * @returns The rounded price.
     */
    public roundPrice(price: number): number {
        const precision = this.instrumentInfo.price_precision;
        return Math.round(price / precision) * precision;
    }

    /**
     * Rounds a quantity to the correct precision (qty step).
     * @param qty The quantity to round.
     * @returns The rounded quantity.
     */
    public roundQuantity(qty: number): number {
        const precision = this.instrumentInfo.qty_precision;
        return Math.round(qty / precision) * precision;
    }

    /**
     * Checks if an order quantity meets the minimum requirements.
     * @param qty The quantity.
     * @param price The price (for notional value check).
     * @returns True if valid, false otherwise.
     */
    public checkMinOrder(qty: number, price: number): boolean {
        const notional = qty * price;
        if (qty < this.instrumentInfo.min_qty) {
            logger.warn(`Order quantity ${qty} is below minimum allowed quantity ${this.instrumentInfo.min_qty}.`);
            return false;
        }
        if (notional < this.instrumentInfo.min_amt) {
            logger.warn(`Order notional value ${notional.toFixed(2)} is below minimum allowed amount ${this.instrumentInfo.min_amt}.`);
            return false;
        }
        return true;
    }
}
