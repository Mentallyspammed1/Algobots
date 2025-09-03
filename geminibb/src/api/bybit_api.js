// src/api/bybit_api.js
import crypto from 'crypto-js';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import Decimal from 'decimal.js';
import axios from 'axios';
import { z } from 'zod';


const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// IMPROVEMENT 1: Simple Request Queue for Rate Limiting
const requestQueue = [];
let isProcessingQueue = false;

// IMPROVEMENT 6: Schema for placeOrder parameters
const PlaceOrderSchema = z.object({
    symbol: z.string(),
    side: z.enum(['Buy', 'Sell']),
    qty: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).refine(n => n > 0, "Quantity must be positive."),
    takeProfit: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    stopLoss: z.union([z.number().gte(0), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(),
    orderType: z.enum(['Market', 'Limit', 'PostOnly']).default('Market'),
    price: z.union([z.number().positive(), z.string().regex(/^\d*\.?\d+$/).transform(Number)]).optional(), // Optional by default
}).superRefine((data, ctx) => { // Refine to make price mandatory for Limit/PostOnly
    if (data.orderType !== 'Market' && (data.price === undefined || data.price === null)) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Price is required for Limit or PostOnly orders.",
            path: ['price'],
        });
    }
});


export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = config.bybit.testnet ? 'https://api-testnet.bybit.com' : config.bybit.restUrl;
        logger.info(`Bybit API configured for ${config.bybit.testnet ? 'TESTNET' : 'MAINNET'}`);

        // IMPROVEMENT 2: Initialize axios instance
        this.axiosInstance = axios.create({
            baseURL: this.baseUrl,
            timeout: config.bybit.requestTimeoutMs, // IMPROVEMENT 3: Request Timeout
            headers: { 'Content-Type': 'application/json' },
        });

        // IMPROVEMENT 1: Dynamic Rate Limit Tracking (conceptual)
        this.rateLimitTracker = {
            lastRequestTime: 0,
            // A more advanced system would parse X-RateLimit-* headers to dynamically adjust `requestIntervalMs`.
            // For now, it respects the configured `requestIntervalMs` as a minimum delay.
        };

        // IMPROVEMENT 2: Axios Interceptor for logging and basic error handling
        this.axiosInstance.interceptors.response.use(
            response => {
                logger.debug(`API Response [${response.config.method}] ${response.config.url}: Status ${response.status}`);
                return response;
            },
            error => {
                logger.error(`API Request Error [${error.config?.method}] ${error.config?.url}: ${error.message}`);
                if (error.response) {
                    logger.error(`Response data: ${JSON.stringify(error.response.data)}`);
                    const retCode = error.response.data?.retCode;
                    const retMsg = error.response.data?.retMsg;
                    // IMPROVEMENT 2: Detailed error reporting and throwing
                    if (retCode !== undefined) {
                        const specificError = `Bybit API Error (${retCode}): ${retMsg || 'Unknown error'}. Request: ${error.config?.url}`;
                        logger.error(specificError);
                        // Enhance with specific known error codes for more actionable advice
                        if (retCode === 10001) throw new Error(`Authentication Failed: Invalid API key/signature. Check credentials. (${retCode})`);
                        if (retCode === 110001) throw new Error(`Trading Error: Insufficient Balance. (${retCode})`);
                        if (retCode === 110007) throw new Error(`Trading Error: Order quantity too small. (${retCode})`);
                        throw new Error(specificError); // Throw a general Bybit API error
                    }
                } else if (error.request) {
                    // The request was made but no response was received (e.g., network error, timeout)
                    logger.error(`No response received for [${error.config?.method}] ${error.config?.url}. Network or Timeout error.`);
                    throw new Error(`Network Error: No response from Bybit. Check internet or API status.`);
                }
                // Fallback for other errors (e.g., config error)
                return Promise.reject(new Error(`General Request Error: ${error.message}`));
            }
        );

        this.symbolInfo = {}; // IMPROVEMENT 8: Cache symbol info
        this.loadSymbolInfo(); // Load on startup
    }

    // NEW: Internal request method with retry logic
    // IMPROVEMENT 8: Fetch and cache symbol information
    async loadSymbolInfo() {
        try {
            // Use _request which goes through the queue
            const result = await this._request('GET', '/v5/market/instruments-info', { category: 'linear', symbol: config.symbol }, false);
            if (result && result.list && result.list.length > 0) {
                const info = result.list[0];
                this.symbolInfo = {
                    pricePrecision: parseInt(info.priceFilter.tickSize.split('.')[1]?.length || 0),
                    qtyPrecision: parseInt(info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0),
                    minOrderQty: new Decimal(info.lotSizeFilter.minOrderQty), // Store as Decimal
                    maxOrderQty: new Decimal(info.lotSizeFilter.maxOrderQty), // Store as Decimal
                };
                logger.info(`Symbol info for ${config.symbol} loaded: Price Precision ${this.symbolInfo.pricePrecision}, Qty Precision ${this.symbolInfo.qtyPrecision}, Min Qty ${this.symbolInfo.minOrderQty.toString()}`);
            } else {
                logger.warn(`Could not load symbol info for ${config.symbol}. Using default config precisions.`);
            }
        } catch (error) {
            logger.error(`Error loading symbol info: ${error.message}. Using default config precisions.`);
        }
    }

    getQtyPrecision() { return this.symbolInfo.qtyPrecision ?? config.bybit.qtyPrecision; }
    getPricePrecision() { return this.symbolInfo.pricePrecision ?? config.bybit.pricePrecision; }
    getMinOrderQty() { return this.symbolInfo.minOrderQty ?? new Decimal(config.bybit.minOrderSize); }

    // IMPROVEMENT 1: Process requests via a queue to respect rate limits
    async _request(method, endpoint, params = {}, isPrivate = true, retryCount = 0) { // Add retryCount parameter
        return new Promise((resolve, reject) => {
            requestQueue.push({ method, endpoint, params, isPrivate, resolve, reject, retryCount });
            this._processQueue();
        });
    }

    async _processQueue() {
        if (isProcessingQueue) return;
        isProcessingQueue = true;

        while (requestQueue.length > 0) {
            const request = requestQueue.shift();
            const { method, endpoint, params, isPrivate, resolve, reject, retryCount } = request;

            try {
                // IMPROVEMENT 1: Dynamic Rate Limit Enforcement
                const now = Date.now();
                const timeSinceLastRequest = now - this.rateLimitTracker.lastRequestTime;
                if (timeSinceLastRequest < config.bybit.requestIntervalMs) {
                    const delay = config.bybit.requestIntervalMs - timeSinceLastRequest;
                    logger.debug(`Rate limit delay: waiting ${delay}ms before next request to Bybit.`);
                    await sleep(delay);
                }
                this.rateLimitTracker.lastRequestTime = Date.now(); // Update after potential sleep

                const result = await this._makeRequest(method, endpoint, params, isPrivate);
                resolve(result);
            } catch (error) {
                // IMPROVEMENT 1: Implement retry logic for specific errors
                if (retryCount < config.bybit.maxRetries && error.message.includes('Bybit API Error')) { // Only retry specific API errors
                    const delay = Math.min(config.bybit.maxRetryDelayMs, Math.pow(2, retryCount) * 1000); // Exponential backoff
                    logger.warn(`API request failed, retrying in ${delay / 1000}s (attempt ${retryCount + 1}): ${error.message}`);
                    requestQueue.unshift({ ...request, retryCount: retryCount + 1 }); // Re-add to front of queue with incremented retry count
                    await sleep(delay); // Wait before retrying
                } else {
                    reject(error); // Reject if max retries reached or it's a non-retryable error
                }
            }
        }
        isProcessingQueue = false;
    }

    async _makeRequest(method, endpoint, params = {}, isPrivate = true) {
        const timestamp = Date.now().toString();
        const recvWindow = config.bybit.recvWindow; // IMPROVEMENT 3: Configurable recvWindow

        let queryString = '';
        let signPayload = '';

        if (isPrivate) { // Only sign private endpoints
            queryString = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
            signPayload = timestamp + this.apiKey + recvWindow + (queryString || '');
        } else { // Public endpoints don't require signature
            queryString = new URLSearchParams(params).toString();
            // Public requests don't need API key, signature, etc.
        }

        const signature = isPrivate ? crypto.HmacSHA256(signPayload, this.apiSecret).toString() : '';

        const headers = {
            'Content-Type': 'application/json',
            // IMPROVEMENT 2: Pass API keys only for private requests
            ...(isPrivate && {
                'X-BAPI-API-KEY': this.apiKey,
                'X-BAPI-SIGN': signature,
                'X-BAPI-SIGN-TYPE': '2',
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': recvWindow,
            })
        };

        const url = `${endpoint}${method === 'GET' && queryString ? '?' + queryString : ''}`;
        const options = {
            method,
            headers,
            // IMPROVEMENT 2: axios handles body differently
            data: method !== 'GET' ? queryString : undefined,
            params: method === 'GET' ? params : undefined,
        };

        logger.debug(`Sending API request: ${method} ${url} with params: ${JSON.stringify(params)}`);

        // Use axios instance
        const response = await this.axiosInstance(url, options);
        const data = response.data;

        if (data.retCode !== 0) {
            throw new Error(`Bybit API Error: ${data.retMsg} (Code: ${data.retCode})`);
        }
        return data.result;
    }

    async getHistoricalMarketData(symbol, interval, limit = 200) {
        // IMPROVEMENT 3: Dynamically use category
        return this._request('GET', '/v5/market/kline', { category: config.bybit.category, symbol, interval, limit }, false);
    }

    async getAccountBalance() {
        // IMPROVEMENT 3: Configurable accountType
        const result = await this._request('GET', '/v5/account/wallet-balance', { accountType: config.bybit.accountType });
        const usdtBalance = result?.list?.[0]?.coin?.find(c => c.coin === 'USDT');
        return usdtBalance ? parseFloat(usdtBalance.walletBalance) : null;
    }

    async getCurrentPosition(symbol) {
        // IMPROVEMENT 8: Dynamically use category from config
        const result = await this._request('GET', '/v5/position/list', { category: config.bybit.category, symbol });
        const position = result?.list?.find(p => p.symbol === symbol && parseFloat(p.size) > 0); // Ensure size > 0
        return position || null;
    }

    async placeOrder(order) {
        // ... (existing validation) ...
        const validatedOrder = validationResult.data;

        const { symbol, side, qty, takeProfit, stopLoss, orderType, price } = validatedOrder;
        
        // IMPROVEMENT 3: Apply dynamic precision and min order size fetched from symbolInfo
        const qtyPrecision = this.getQtyPrecision();
        const pricePrecision = this.getPricePrecision();
        const minOrderQty = this.getMinOrderQty();

        const qtyToPlace = new Decimal(qty).toDecimalPlaces(qtyPrecision, Decimal.ROUND_DOWN); // Ensure quantity is within step size
        const tpToPlace = takeProfit !== undefined && takeProfit !== 0 ? new Decimal(takeProfit).toDecimalPlaces(pricePrecision) : undefined;
        const slToPlace = stopLoss !== undefined && stopLoss !== 0 ? new Decimal(stopLoss).toDecimalPlaces(pricePrecision) : undefined;
        const priceToPlace = price !== undefined ? new Decimal(price).toDecimalPlaces(pricePrecision) : undefined;

        // Ensure minimum order quantity check is robust
        if (qtyToPlace.lt(minOrderQty)) {
            throw new Error(`Order quantity ${qtyToPlace.toFixed(qtyPrecision)} is below minimum order quantity ${minOrderQty.toFixed(qtyPrecision)} for ${symbol}.`);
        }
        if (qtyToPlace.eq(0)) { // Ensure quantity is not zero after rounding
            throw new Error(`Order quantity rounded to zero for ${symbol}. Original: ${qty}`);
        }

        const log = `Placing order: ${side} ${qtyToPlace.toFixed(qtyPrecision)} ${symbol} | Type: ${orderType} | Price: ${priceToPlace || 'N/A'} | TP: ${tpToPlace || 'N/A'}, SL: ${slToPlace || 'N/A'}`;
        if (config.dryRun) {
            logger.info(`[DRY RUN] ${log}`);
            return { orderId: `dry-run-${Date.now()}` };
        }
        logger.info(log);

        const orderParams = {
            category: config.bybit.category,
            symbol, side, orderType,
            qty: qtyToPlace.toString(), // Bybit API expects string for qty
            ...(orderType !== 'Market' && priceToPlace && { price: priceToPlace.toString() }), // price for Limit/PostOnly
            ...(tpToPlace && { takeProfit: tpToPlace.toString() }),
            ...(slToPlace && { stopLoss: slToPlace.toString() }),
            timeInForce: 'GTC',
            // IMPROVEMENT: Optionally add `reduceOnly: true` for closing orders if desired
        };
        
        return this._request('POST', '/v5/order/create', orderParams);
    }

    async closePosition(symbol, side) {
        const position = await this.getCurrentPosition(symbol);
        if (!position) {
            logger.warn("Attempted to close a position that does not exist or has zero size.");
            return null;
        }
        const closeSide = side === SIDES.BUY ? SIDES.SELL : SIDES.BUY;
        // IMPROVEMENT 4: Force market order for closing
        return this.placeOrder({ symbol, side: closeSide, qty: parseFloat(position.size), orderType: 'Market', takeProfit: 0, stopLoss: 0 });
    }

        // IMPROVEMENT 5: Method to cancel a specific order by ID
    async cancelOrder(symbol, orderId) {
        logger.info(`Attempting to cancel order ${orderId} for ${symbol}.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would cancel order ${orderId} for ${symbol}.`);
            return { result: 'dry-run-cancel-order' };
        }
        try {
            const result = await this._request('POST', '/v5/order/cancel', {
                category: config.bybit.category,
                symbol: symbol,
                orderId: orderId,
            });
            logger.info(`Successfully cancelled order ${orderId} for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to cancel order ${orderId} for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    // IMPROVEMENT 20: Method to cancel all open orders for a symbol
    async cancelAllOpenOrders(symbol) {
        logger.info(`Attempting to cancel all open orders for ${symbol}.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would cancel all open orders for ${symbol}.`);
            return { result: 'dry-run-cancel' };
        }
        try {
            const result = await this._request('POST', '/v5/order/cancel-all', {
                category: config.bybit.category,
                symbol: symbol,
            });
            logger.info(`Successfully cancelled all open orders for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to cancel all open orders for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    /**
     * Retrieves all open orders for a given symbol.
     * @param {string} symbol The trading symbol (e.g., 'BTCUSDT').
     * @returns {Promise<Array>} An array of open orders.
     */
    async getOpenOrders(symbol) {
        logger.info(`Fetching open orders for ${symbol}.`);
        try {
            // Bybit API v5 uses openOnly = 0 to filter for unfilled/partially filled orders
            const result = await this._request('GET', '/v5/order/realtime', {
                category: config.bybit.category,
                symbol: symbol,
                openOnly: 0,
            });
            return result?.list || [];
        } catch (error) {
            logger.error(`Failed to fetch open orders for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    /**
     * Amends an existing order (price or quantity).
     * @param {string} symbol The trading symbol.
     * @param {string} orderId The ID of the order to amend.
     * @param {number} [newQty] New quantity for the order.
     * @param {number} [newPrice] New price for the order.
     * @returns {Promise<object>} The result of the amendment.
     */
    async amendOrder(symbol, orderId, newQty, newPrice) {
        if (!newQty && !newPrice) {
            throw new Error("Either new quantity or new price must be provided for order amendment.");
        }
        logger.info(`Attempting to amend order ${orderId} for ${symbol}. New Qty: ${newQty || 'N/A'}, New Price: ${newPrice || 'N/A'}`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would amend order ${orderId} for ${symbol}. New Qty: ${newQty || 'N/A'}, New Price: ${newPrice || 'N/A'}`);
            return { orderId, result: 'dry-run-amend-order' };
        }

        const orderParams = {
            category: config.bybit.category,
            symbol: symbol,
            orderId: orderId,
            ...(newQty !== undefined && { qty: new Decimal(newQty).toDecimalPlaces(this.getQtyPrecision()).toString() }),
            ...(newPrice !== undefined && { price: new Decimal(newPrice).toDecimalPlaces(this.getPricePrecision()).toString() }),
        };

        try {
            const result = await this._request('POST', '/v5/order/amend', orderParams);
            logger.info(`Successfully amended order ${orderId} for ${symbol}.`);
            return result;
        } catch (error) {
            logger.error(`Failed to amend order ${orderId} for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    /**
     * Retrieves ticker information for a specific symbol.
     * @param {string} [symbol] The trading symbol (e.g., 'BTCUSDT'). Defaults to config.symbol.
     * @returns {Promise<object|null>} Ticker data for the symbol, or null if not found.
     */
    async getTickers(symbol = config.symbol) {
        logger.debug(`Fetching ticker for ${symbol}.`);
        try {
            const params = { category: config.bybit.category, symbol };
            const result = await this._request('GET', '/v5/market/tickers', params, false);
            return result?.list?.[0] || null; // Return single ticker
        } catch (error) {
            logger.error(`Failed to fetch ticker data for ${symbol}: ${error.message}`);
            throw error;
        }
    }

    /**
     * Sets the leverage for a specific symbol.
     * @param {string} symbol The trading symbol (e.g., 'BTCUSDT').
     * @param {number} leverage The desired leverage (e.g., 10, 25, 50).
     * @returns {Promise<object>} The result of the leverage setting operation.
     */
    async setLeverage(symbol, leverage) {
        if (!Number.isInteger(leverage) || leverage <= 0) {
            throw new Error("Leverage must be a positive integer.");
        }
        logger.info(`Attempting to set leverage for ${symbol} to ${leverage}x.`);
        if (config.dryRun) {
            logger.info(`[DRY RUN] Would set leverage for ${symbol} to ${leverage}x.`);
            return { symbol, leverage, result: 'dry-run-set-leverage' };
        }
        try {
            const result = await this._request('POST', '/v5/position/set-leverage', {
                category: config.bybit.category,
                symbol: symbol,
                buyLeverage: leverage.toString(), // Bybit API expects strings
                sellLeverage: leverage.toString(),
            });
            logger.info(`Successfully set leverage for ${symbol} to ${leverage}x.`);
            return result;
        } catch (error) {
            logger.error(`Failed to set leverage for ${symbol} to ${leverage}x: ${error.message}`);
            throw error;
        }
    }