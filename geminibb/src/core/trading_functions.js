// src/core/trading_functions.js
import Decimal from 'decimal.js';
import { Logger } from '../utils/logger.js';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const config = require('../../config.json');

const logger = new Logger('TRADING_FUNCTIONS');

export class TradingFunctions {
    constructor(bybitAdapter, riskPolicy) {
        this.bybitAdapter = bybitAdapter;
        this.riskPolicy = riskPolicy;
        this.useStubData = config.stubData.enabled;

        if (this.useStubData && !bybitAdapter.bybitEnabled) {
            logger.warn('Bybit API is disabled. Trading functions will use stub data.');
        } else if (this.useStubData && bybitAdapter.bybitEnabled) {
             logger.warn('Bybit API is enabled, but stub data is also enabled in config.json. Real API will be prioritized for private calls, stub for public if API fails.');
        }
    }

    /**
     * Gets current market data (ticker).
     * @param {string} symbol - Trading pair.
     * @returns {Promise<object|null>} - Ticker data or null if not found.
     */
    async getMarketData(symbol) {
        if (this.useStubData && !this.bybitAdapter.bybitEnabled) {
            logger.debug(`[STUB] Fetching market data for ${symbol}.`);
            const lastCandle = config.stubData.marketData.slice(-1)[0];
            return {
                symbol: symbol,
                lastPrice: new Decimal(lastCandle.close),
                timestamp: lastCandle.timestamp
            };
        }
        try {
            const data = await this.bybitAdapter.getRealTimeMarketData(symbol);
            if (data) {
                return {
                    symbol: data.symbol,
                    lastPrice: new Decimal(data.lastPrice),
                    timestamp: data.updatedTime
                };
            }
            return null;
        } catch (error) {
            logger.exception(`Error fetching market data for ${symbol}:`, error);
            if (this.useStubData) {
                logger.warn(`Failed to fetch real market data, falling back to stub data for ${symbol}.`);
                const lastCandle = config.stubData.marketData.slice(-1)[0];
                return {
                    symbol: symbol,
                    lastPrice: new Decimal(lastCandle.close),
                    timestamp: lastCandle.timestamp
                };
            }
            throw error;
        }
    }

    /**
     * Gets historical candlestick data.
     * @param {string} symbol - Trading pair.
     * @param {string} interval - Candlestick interval (e.g., '1h').
     * @param {number} limit - Number of candles.
     * @returns {Promise<Array<object>>} - Array of OHLCV data.
     */
    async getHistoricalData(symbol, interval, limit) {
        if (this.useStubData && !this.bybitAdapter.bybitEnabled) {
            logger.debug(`[STUB] Fetching historical data for ${symbol}, ${interval}, limit ${limit}.`);
            // Return a slice of stub data, ensuring it's in the correct format (Decimal for values)
            return config.stubData.marketData
                .slice(0, limit)
                .map(d => ({
                    timestamp: d.timestamp,
                    open: new Decimal(d.open),
                    high: new Decimal(d.high),
                    low: new Decimal(d.low),
                    close: new Decimal(d.close),
                    volume: new Decimal(d.volume)
                }));
        }
        try {
            const data = await this.bybitAdapter.getHistoricalMarketData(symbol, interval, limit);
            // Convert to Decimal for financial precision
            return data.map(d => ({
                timestamp: d.timestamp,
                open: new Decimal(d.open),
                high: new Decimal(d.high),
                low: new Decimal(d.low),
                close: new Decimal(d.close),
                volume: new Decimal(d.volume)
            }));
        } catch (error) {
            logger.exception(`Error fetching historical data for ${symbol}:`, error);
            if (this.useStubData) {
                 logger.warn(`Failed to fetch real historical data, falling back to stub data for ${symbol}.`);
                 return config.stubData.marketData
                    .slice(0, limit)
                    .map(d => ({
                        timestamp: d.timestamp,
                        open: new Decimal(d.open),
                        high: new Decimal(d.high),
                        low: new Decimal(d.low),
                        close: new Decimal(d.close),
                        volume: new Decimal(d.volume)
                    }));
            }
            throw error;
        }
    }

    /**
     * Gets account portfolio information.
     * @returns {Promise<object|null>} - Account details.
     */
    async getPortfolio() {
        if (this.useStubData && !this.bybitAdapter.bybitEnabled) {
            logger.debug('[STUB] Fetching portfolio data.');
            return {
                totalBalance: new Decimal(config.stubData.accountInfo.totalBalance),
                availableBalance: new Decimal(config.stubData.accountInfo.availableBalance),
                balances: Object.fromEntries(
                    Object.entries(config.stubData.accountInfo.balances).map(([asset, data]) => [
                        asset, { total: new Decimal(data.total), available: new Decimal(data.available) }
                    ])
                ),
                positions: config.stubData.accountInfo.positions
            };
        }
        try {
            return await this.bybitAdapter.getAccountInfo();
        } catch (error) {
            logger.exception('Error fetching portfolio:', error);
            if (this.useStubData) {
                logger.warn('Failed to fetch real portfolio, falling back to stub data.');
                return {
                    totalBalance: new Decimal(config.stubData.accountInfo.totalBalance),
                    availableBalance: new Decimal(config.stubData.accountInfo.availableBalance),
                    balances: Object.fromEntries(
                        Object.entries(config.stubData.accountInfo.balances).map(([asset, data]) => [
                            asset, { total: new Decimal(data.total), available: new Decimal(data.available) }
                        ])
                    ),
                    positions: config.stubData.accountInfo.positions
                };
            }
            throw error;
        }
    }

    /**
     * Places a market buy order.
     * @param {string} symbol - Trading pair.
     * @param {Decimal} quantity - Amount of base asset to buy.
     * @returns {Promise<object>} - Order response.
     */
    async marketBuy(symbol, quantity) {
        logger.info(`Attempting market buy: ${quantity} ${symbol}`);
        const currentPrice = (await this.getMarketData(symbol)).lastPrice;
        const validation = await this.riskPolicy.validateTradeProposal(symbol, 'Buy', quantity, currentPrice);

        if (!validation.isValid) {
            logger.warn(`Market buy validation failed: ${validation.message}`);
            return { success: false, message: validation.message };
        }

        return this.bybitAdapter.placeOrder(symbol, 'Buy', 'Market', quantity);
    }

    /**
     * Places a limit sell order.
     * @param {string} symbol - Trading pair.
     * @param {Decimal} quantity - Amount of base asset to sell.
     * @param {Decimal} price - Limit price.
     * @returns {Promise<object>} - Order response.
     */
    async limitSell(symbol, quantity, price) {
        logger.info(`Attempting limit sell: ${quantity} ${symbol} at ${price}`);
        const validation = await this.riskPolicy.validateTradeProposal(symbol, 'Sell', quantity, price);

        if (!validation.isValid) {
            logger.warn(`Limit sell validation failed: ${validation.message}`);
            return { success: false, message: validation.message };
        }
        return this.bybitAdapter.placeOrder(symbol, 'Sell', 'Limit', quantity, price);
    }

    /**
     * Cancels an order.
     * @param {string} symbol - Trading pair.
     * @param {string} orderId - Order ID.
     * @returns {Promise<object>} - Cancellation response.
     */
    async cancelOrder(symbol, orderId) {
        logger.info(`Attempting to cancel order: ${orderId} for ${symbol}`);
        return this.bybitAdapter.cancelOrder(symbol, orderId);
    }

    // Add more advanced trading functions here (e.g., set_stop_loss, get_open_orders)
    async getOpenOrders(symbol) {
        if (this.useStubData && !this.bybitAdapter.bybitEnabled) {
            logger.debug('[STUB] Returning stub open orders.');
            return config.stubData.openOrders;
        }
        try {
            // Bybit v5: /v5/order/realtime
            const response = await this.bybitAdapter._request('GET', '/v5/order/realtime', { category: 'spot', symbol });
            if (response.result && response.result.list) {
                return response.result.list;
            }
            return [];
        } catch (error) {
            logger.exception(`Error fetching open orders for ${symbol}:`, error);
            if (this.useStubData) {
                logger.warn(`Failed to fetch real open orders, falling back to stub data for ${symbol}.`);
                return config.stubData.openOrders;
            }
            throw error;
        }
    }
}