// src/api/bybit_api.js
import fetch from 'node-fetch';
import crypto from 'crypto';
import { Logger } from '../utils/logger.js';
import { withRetry } from '../utils/retry_handler.js';
import { Constants, CandlestickIntervals } from '../utils/constants.js';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const config = require('../../config.json');
import Decimal from 'decimal.js'; // For symbol precision and financial calculations

const logger = new Logger('BYBIT_API');

export class BybitAPI {
    constructor(apiKey, apiSecret, useTestnet = false) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.useTestnet = useTestnet;
        this.baseUrl = useTestnet ? Constants.API_URLS.BYBIT_REST_TESTNET : Constants.API_URLS.BYBIT_REST_MAINNET;
        this.wsBaseUrl = useTestnet ? Constants.API_URLS.BYBIT_WS_PUBLIC_TESTNET : Constants.API_URLS.BYBIT_WS_PUBLIC_MAINNET;
        this.accountDataCache = {}; // Cache for account info
        this.symbolPrecision = {}; // Cache for symbol precision rules
        this.bybitEnabled = !!(apiKey && apiSecret);

        if (!this.bybitEnabled) {
            logger.warn('Bybit API Key or Secret missing. Bybit integration will be disabled. Using stub data.');
        } else {
            logger.info(`Bybit integration enabled. Using ${this.useTestnet ? 'TESTNET' : 'MAINNET'}.`);
        }
    }

    /**
     * Generates the HMAC-SHA256 signature for Bybit requests.
     * NOTE: This is a simplified placeholder. Real Bybit signing involves more parameters
     * and depends on the request type (GET/POST) and API version.
     * Refer to Bybit API documentation for precise signing logic.
     * @param {string} params - The query string or JSON payload string.
     * @param {string} timestamp - Current timestamp in milliseconds.
     * @returns {string} - The HMAC-SHA256 signature.
     */
    _generateSignature(params, timestamp) {
        
        // For actual Bybit API, the signature string depends on the request method and parameters.
        // Example for v5 private GET/POST:
        // const paramStr = timestamp + this.apiKey + recvWindow + params;
        // return crypto.createHmac('sha256', this.apiSecret).update(paramStr).digest('hex');

        logger.warn('Bybit signature generation is a placeholder. Implement actual HMAC-SHA256 based on Bybit docs.');
        // For demonstration, a dummy signature
        return crypto.createHmac('sha256', this.apiSecret || 'dummy_secret').update(params + timestamp).digest('hex');
    }

    /**
     * Internal method to make signed HTTP requests to Bybit.
     * @param {string} method - HTTP method (GET, POST).
     * @param {string} path - API endpoint path.
     * @param {object} params - Query parameters or body payload.
     * @param {boolean} isPrivate - Whether the endpoint requires authentication.
     * @returns {Promise<object>} - JSON response from Bybit.
     */
    async _request(method, path, params = {}, isPrivate = true) {
        if (!this.bybitEnabled && isPrivate) {
            logger.warn(`Bybit disabled, cannot make private request to ${path}.`);
            throw new Error('Bybit API is not enabled for private requests.');
        }
        if (!this.bybitEnabled && !isPrivate && config.stubData.enabled) {
             logger.warn(`Bybit disabled for public request to ${path}. Using stub data.`);
             // For public data, we might need a more sophisticated stub for varying data.
             if (path.includes('kline')) return { result: { list: config.stubData.marketData } };
             if (path.includes('ticker')) return { result: { list: [{ lastPrice: config.stubData.marketData.slice(-1)[0].close.toString() }] } };
             return {};
        }


        const timestamp = Date.now().toString();
        const recvWindow = 5000; // Bybit recommended window

        let url = `${this.baseUrl}${path}`;
        let headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        };

        let requestBody = null;
        if (isPrivate) {
            headers['X-BAPI-API-KEY'] = this.apiKey;
            headers['X-BAPI-TIMESTAMP'] = timestamp;
            headers['X-BAPI-RECV-WINDOW'] = recvWindow;

            let signParams = '';
            if (method === 'GET') {
                signParams = new URLSearchParams(params).toString();
                url += `?${signParams}`;
            } else if (method === 'POST') {
                requestBody = JSON.stringify(params);
                signParams = timestamp + this.apiKey + recvWindow + requestBody; // This is a simplified example
            }
            headers['X-BAPI-SIGN'] = this._generateSignature(signParams, timestamp);
        } else if (method === 'GET') {
            url += `?${new URLSearchParams(params).toString()}`;
        } else if (method === 'POST') {
            requestBody = JSON.stringify(params);
        }

        const fetchCall = async () => {
            const response = await fetch(url, {
                method: method,
                headers: headers,
                body: requestBody
            });

            if (!response.ok) {
                const errorText = await response.text();
                logger.error(`Bybit API Error: ${response.status} ${response.statusText} - ${errorText}`);
                const error = new Error(`Bybit API Error: ${response.statusText}`);
                error.response = response; // Attach response for retry handler
                throw error;
            }
            return response.json();
        };

        return withRetry(fetchCall, {
            maxAttempts: config.retry.maxAttempts,
            initialDelayMs: config.retry.initialDelayMs,
            maxDelayMs: config.retry.maxDelayMs,
            jitterFactor: config.retry.jitterFactor
        })();
    }

    /**
     * Fetches real-time ticker data for a symbol.
     * @param {string} symbol - Trading pair (e.g., 'BTCUSDT').
     * @returns {Promise<object>} - Ticker data.
     */
    async getRealTimeMarketData(symbol) {
        // Example for Bybit v5: /v5/market/tickers
        const response = await this._request('GET', '/v5/market/tickers', { category: 'spot', symbol }, false);
        if (response.result && response.result.list && response.result.list.length > 0) {
            return response.result.list[0];
        }
        return null;
    }

    /**
     * Fetches historical candlestick data.
     * @param {string} symbol - Trading pair (e.g., 'BTCUSDT').
     * @param {string} interval - Candlestick interval (e.g., '1h', '1d').
     * @param {number} limit - Number of candles to retrieve.
     * @returns {Promise<Array<object>>} - Array of OHLCV data.
     */
    async getHistoricalMarketData(symbol, interval, limit = 200) {
        const bybitInterval = CandlestickIntervals[interval];
        if (!bybitInterval) {
            throw new Error(`Invalid interval: ${interval}`);
        }
        const response = await this._request('GET', '/v5/market/kline', {
            category: 'spot',
            symbol,
            interval: bybitInterval,
            limit
        }, false);

        if (response.result && response.result.list) {
            // Bybit returns [timestamp, open, high, low, close, volume, turnover]
            // We want to map it to a more generic OHLCV format, with numeric types.
            // NOTE: Original request mentioned pd.DataFrame, this is the JS equivalent.
            return response.result.list.map(kline => ({
                timestamp: parseInt(kline[0]),
                open: parseFloat(kline[1]),
                high: parseFloat(kline[2]),
                low: parseFloat(kline[3]),
                close: parseFloat(kline[4]),
                volume: parseFloat(kline[5])
            })).reverse(); // Bybit returns newest first, reverse for oldest first
        }
        return [];
    }

    /**
     * Retrieves account information (balances, positions).
     * @returns {Promise<object>} - Account details.
     */
    async getAccountInfo() {
        if (!this.bybitEnabled && config.stubData.enabled) {
            logger.debug('Bybit disabled, returning stub account info.');
            return config.stubData.accountInfo;
        }

        if (Object.keys(this.accountDataCache).length > 0) {
            logger.debug('Returning cached account info.');
            return this.accountDataCache;
        }

        const response = await this._request('GET', '/v5/account/wallet-balance', { accountType: 'UNIFIED' });
        // Process response to a simplified format if needed
        if (response.result && response.result.list && response.result.list.length > 0) {
            const walletBalance = response.result.list[0];
            const balances = {};
            walletBalance.coin.forEach(c => {
                balances[c.coin] = {
                    total: new Decimal(c.walletBalance),
                    available: new Decimal(c.availableToWithdraw)
                };
            });
            this.accountDataCache = {
                totalBalance: new Decimal(walletBalance.totalEquity),
                availableBalance: new Decimal(walletBalance.totalAvailableBalance),
                balances: balances,
                positions: [] // Fetch positions separately if needed
            };
            return this.accountDataCache;
        }
        return null;
    }

    /**
     * Places an order on Bybit.
     * @param {string} symbol - Trading pair.
     * @param {string} side - 'Buy' or 'Sell'.
     * @param {string} orderType - 'Market' or 'Limit'.
     * @param {Decimal} qty - Quantity.
     * @param {Decimal} [price] - Price for limit orders.
     * @param {Decimal} [stopLoss] - Stop loss price.
     * @param {Decimal} [takeProfit] - Take profit price.
     * @returns {Promise<object>} - Order placement response.
     */
    async placeOrder(symbol, side, orderType, qty, price = null, stopLoss = null, takeProfit = null) {
        if (!this.bybitEnabled && config.stubData.enabled) {
            logger.debug('Bybit disabled, returning stub order placement response.');
            return {
                orderId: 'STUB_ORDER_' + Date.now(),
                symbol, side, orderType, qty: qty.toString(), price: price?.toString(),
                status: Constants.OrderStatus.NEW,
                timestamp: Date.now()
            };
        }

        const params = {
            category: 'spot', // Or 'linear'/'inverse' for derivatives
            symbol: symbol,
            side: side,
            orderType: orderType,
            qty: qty.toFixed(this._getQtyPrecision(symbol)), // Ensure precision
            price: price ? price.toFixed(this._getPricePrecision(symbol)) : undefined,
            triggerDirection: 0, // Not used for spot market/limit
            timeInForce: 'GTC', // Good-Till-Canceled
            isLeverage: 0, // Not using leverage for spot
            orderLinkId: `order_${Date.now()}` // Unique ID
        };
        if (stopLoss) params.stopLoss = stopLoss.toFixed(this._getPricePrecision(symbol));
        if (takeProfit) params.takeProfit = takeProfit.toFixed(this._getPricePrecision(symbol));

        return await this._request('POST', '/v5/order/create', params);
    }

    /**
     * Cancels an open order.
     * @param {string} symbol - Trading pair.
     * @param {string} orderId - Order ID to cancel.
     * @returns {Promise<object>} - Cancellation response.
     */
    async cancelOrder(symbol, orderId) {
        if (!this.bybitEnabled && config.stubData.enabled) {
            logger.debug(`Bybit disabled, returning stub order cancellation for ${orderId}.`);
            return {
                orderId: orderId,
                status: Constants.OrderStatus.CANCELED,
                message: 'Order cancelled (stub).'
            };
        }
        return await this._request('POST', '/v5/order/cancel', { category: 'spot', symbol, orderId });
    }

    /**
     * Retrieves precision rules for a symbol. Caches the result.
     * @param {string} symbol - Trading pair.
     * @returns {Promise<object>} - Precision rules (price precision, quantity precision).
     */
    async _fetchSymbolInfo(symbol) {
        if (this.symbolPrecision[symbol]) {
            return this.symbolPrecision[symbol];
        }

        const response = await this._request('GET', '/v5/market/instruments-info', { category: 'spot', symbol }, false);
        if (response.result && response.result.list && response.result.list.length > 0) {
            const instrument = response.result.list[0];
            this.symbolPrecision[symbol] = {
                pricePrecision: instrument.priceFilter.tickSize.split('.')[1]?.length || 0,
                qtyPrecision: instrument.lotSizeFilter.qtyStep.split('.')[1]?.length || 0
            };
            return this.symbolPrecision[symbol];
        }
        throw new Error(`Could not fetch instrument info for ${symbol}`);
    }

    async _getPricePrecision(symbol) {
        const info = await this._fetchSymbolInfo(symbol);
        return info.pricePrecision;
    }

    async _getQtyPrecision(symbol) {
        const info = await this._fetchSymbolInfo(symbol);
        return info.qtyPrecision;
    }

    // Placeholder for WebSocket connection (conceptual)
    connectWebSocket() {
        logger.warn('WebSocket connection is conceptual and not fully implemented.');
        // const ws = new WebSocket(`${this.wsBaseUrl}/public/v5/spot`);
        // ws.onopen = () => logger.info('Bybit WebSocket connected.');
        // ws.onmessage = (event) => logger.debug('WS Message:', event.data);
        // ws.onerror = (error) => logger.error('WS Error:', error);
        // ws.onclose = () => logger.warn('Bybit WebSocket closed.');
    }
}