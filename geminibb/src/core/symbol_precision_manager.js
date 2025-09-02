// src/core/symbol_precision_manager.js
import Decimal from 'decimal.js';
import { Logger } from '../utils/logger.js';

const logger = new Logger('SYMBOL_PRECISION');

export class SymbolPrecisionManager {
    constructor(bybitAdapter) {
        this.bybitAdapter = bybitAdapter;
        this.precisionCache = {}; // Cache for symbol precision rules
        logger.info('SymbolPrecisionManager initialized.');
    }

    /**
     * Fetches and caches precision rules for a given symbol from the exchange.
     * @param {string} symbol - Trading pair (e.g., 'BTCUSDT').
     * @returns {Promise<object>} - { pricePrecision: number, quantityPrecision: number }
     */
    async _fetchAndCachePrecision(symbol) {
        if (this.precisionCache[symbol]) {
            return this.precisionCache[symbol];
        }

        try {
            // Delegate to BybitAPI to fetch instrument info
            const info = await this.bybitAdapter._fetchSymbolInfo(symbol); // _fetchSymbolInfo is internal for now
            this.precisionCache[symbol] = info;
            logger.debug(`Fetched and cached precision for ${symbol}:`, info);
            return info;
        } catch (error) {
            logger.exception(`Failed to fetch precision for ${symbol}:`, error);
            // Fallback to a default or throw
            logger.warn(`Using default precision for ${symbol} (8 decimals).`);
            return { pricePrecision: 8, qtyPrecision: 8 }; // Default fallback
        }
    }

    /**
     * Rounds a price to the correct precision for a symbol.
     * @param {string} symbol - Trading pair.
     * @param {Decimal} price - The price to round.
     * @returns {Promise<Decimal>} - The rounded price.
     */
    async roundPrice(symbol, price) {
        const { pricePrecision } = await this._fetchAndCachePrecision(symbol);
        return price.toFixed(pricePrecision, Decimal.ROUND_DOWN); // Or ROUND_HALF_EVEN, ROUND_UP, etc.
    }

    /**
     * Rounds a quantity to the correct precision for a symbol.
     * @param {string} symbol - Trading pair.
     * @param {Decimal} quantity - The quantity to round.
     * @returns {Promise<Decimal>} - The rounded quantity.
     */
    async roundQuantity(symbol, quantity) {
        const { qtyPrecision } = await this._fetchAndCachePrecision(symbol);
        return quantity.toFixed(qtyPrecision, Decimal.ROUND_DOWN); // Or ROUND_HALF_EVEN, ROUND_UP, etc.
    }

    /**
     * Gets the price tick size for a symbol.
     * @param {string} symbol
     * @returns {Promise<Decimal>}
     */
    async getPriceTickSize(symbol) {
        const { pricePrecision } = await this._fetchAndCachePrecision(symbol);
        return new Decimal(1).dividedBy(new Decimal(10).pow(pricePrecision));
    }

    /**
     * Gets the quantity step size for a symbol.
     * @param {string} symbol
     * @returns {Promise<Decimal>}
     */
    async getQuantityStepSize(symbol) {
        const { qtyPrecision } = await this._fetchAndCachePrecision(symbol);
        return new Decimal(1).dividedBy(new Decimal(10).pow(qtyPrecision));
    }
}