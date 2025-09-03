// src/api/bybit_api.js
import crypto from 'crypto-js';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import { SIDES } from '../core/constants.js';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export default class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = config.bybit.restUrl;
    }

    // NEW: Internal request method with retry logic
    async _request(method, endpoint, params = {}) {
        for (let i = 0; i < config.bybit.requestRetryAttempts; i++) {
            try {
                return await this._makeRequest(method, endpoint, params);
            } catch (error) {
                logger.warn(`Attempt ${i + 1} failed for ${method} ${endpoint}: ${error.message}`);
                if (i === config.bybit.requestRetryAttempts - 1) {
                    logger.error(`All retry attempts failed for ${method} ${endpoint}.`);
                    throw error; // Re-throw the error after all retries fail
                }
                const delay = Math.pow(2, i) * 1000; // Exponential backoff: 1s, 2s, 4s...
                await sleep(delay);
            }
        }
    }

    async _makeRequest(method, endpoint, params = {}) {
        const timestamp = Date.now().toString();
        const recvWindow = '20000';
        const queryString = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
        const signPayload = timestamp + this.apiKey + recvWindow + (queryString || '');
        const signature = crypto.HmacSHA256(signPayload, this.apiSecret).toString();

        const headers = {
            'X-BAPI-API-KEY': this.apiKey, 'X-BAPI-SIGN': signature,
            'X-BAPI-SIGN-TYPE': '2', 'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recvWindow, 'Content-Type': 'application/json',
        };

        const url = `${this.baseUrl}${endpoint}${method === 'GET' && queryString ? '?' + queryString : ''}`;
        const options = { method, headers };
        if (method !== 'GET') options.body = queryString;

        const response = await fetch(url, options);
        const data = await response.json();
        if (data.retCode !== 0) {
            throw new Error(`Bybit API Error: ${data.retMsg} (Code: ${data.retCode})`);
        }
        return data.result;
    }

    async getHistoricalMarketData(symbol, interval, limit = 200) {
        return this._request('GET', '/v5/market/kline', { category: 'linear', symbol, interval, limit });
    }

    async getAccountBalance() {
        const result = await this._request('GET', '/v5/account/wallet-balance', { accountType: 'UNIFIED' });
        const usdtBalance = result?.list?.[0]?.coin?.find(c => c.coin === 'USDT');
        return usdtBalance ? parseFloat(usdtBalance.walletBalance) : null;
    }

    async getCurrentPosition(symbol) {
        const result = await this._request('GET', '/v5/position/list', { category: 'linear', symbol });
        const position = result?.list?.find(p => p.symbol === symbol);
        return position && parseFloat(position.size) > 0 ? position : null;
    }

    async placeOrder(order) {
        const { symbol, side, qty, takeProfit, stopLoss } = order;
        const log = `Placing order: ${side} ${qty} ${symbol} | TP: ${takeProfit}, SL: ${stopLoss}`;
        if (config.dryRun) {
            logger.info(`[DRY RUN] ${log}`);
            return { orderId: `dry-run-${Date.now()}` };
        }
        logger.info(log);
        return this._request('POST', '/v5/order/create', {
            category: 'linear', symbol, side, orderType: 'Market',
            qty: qty.toString(), takeProfit: takeProfit.toString(), stopLoss: stopLoss.toString(),
        });
    }

    async closePosition(symbol, side) {
        const position = await this.getCurrentPosition(symbol);
        if (!position) {
            logger.warn("Attempted to close a position that does not exist.");
            return null;
        }
        const closeSide = side === SIDES.BUY ? SIDES.SELL : SIDES.BUY;
        return this.placeOrder({ symbol, side: closeSide, qty: position.size, takeProfit: 0, stopLoss: 0 });
    }
}