import crypto from 'crypto';
import { config } from '../config.js';
import logger from '../utils/logger.js';

// Helper function to handle API responses robustly
async function handleResponse(response, path) {
    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        const data = await response.json();
        if (data.retCode !== 0) {
            throw new Error(`Bybit API Error (${path}): ${data.retMsg} (retCode: ${data.retCode})`);
        }
        return data.result;
    } else {
        const text = await response.text();
        logger.error(`Bybit API did not return JSON. Status: ${response.status}. Path: ${path}. Response body:`);
        console.error(text); // Log the raw response for debugging
        throw new Error(`Bybit API did not return JSON. Received: ${contentType}`);
    }
}


class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.apiKey = apiKey;
        this.apiSecret = apiSecret;
        this.baseUrl = config.bybit.restUrl;
    }

    generateSignature(timestamp, recvWindow, params) {
        const paramStr = timestamp + this.apiKey + recvWindow + params;
        return crypto.createHmac('sha256', this.apiSecret).update(paramStr).digest('hex');
    }

    async sendRequest(path, method, body = null) {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const bodyString = body ? JSON.stringify(body) : '';
        const signature = this.generateSignature(timestamp, recvWindow, bodyString);

        const headers = {
            'X-BAPI-API-KEY': this.apiKey,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': recvWindow,
            'Content-Type': 'application/json',
        };

        try {
            const response = await fetch(this.baseUrl + path, { method, headers, body: body ? bodyString : null });
            const result = await handleResponse(response, path);
            return result;
        } catch (error) {
            logger.exception(error);
            return null;
        }
    }

    async getHistoricalMarketData(symbol, interval, limit = 200) {
        const path = `/v5/market/kline?category=linear&symbol=${symbol}&interval=${interval}&limit=${limit}`;
        // Public endpoint, no signature needed
        try {
            const response = await fetch(this.baseUrl + path);
            const result = await handleResponse(response, path);
            return result ? result.list : null;
        } catch (error) {
            logger.exception(error);
            return null;
        }
    }

    async getAccountBalance(coin = 'USDT') {
        const path = `/v5/account/wallet-balance?accountType=UNIFIED&coin=${coin}`;
        const result = await this.sendRequest(path, 'GET');
        if (result && result.list && result.list.length > 0) {
            return parseFloat(result.list[0].totalEquity);
        }
        return null;
    }

    async placeOrder({ symbol, side, qty, takeProfit, stopLoss }) {
        const path = '/v5/order/create';
        const body = {
            category: 'linear',
            symbol,
            side,
            orderType: 'Market',
            qty: String(qty),
            takeProfit: takeProfit ? String(takeProfit) : undefined,
            stopLoss: stopLoss ? String(stopLoss) : undefined,
        };
        logger.info(`Placing order: ${JSON.stringify(body)}`);
        return this.sendRequest(path, 'POST', body);
    }

    async closePosition(symbol, side) {
        const path = '/v5/order/create';
        const position = await this.getOpenPosition(symbol);
        if (!position) {
            logger.warn(`Attempted to close position for ${symbol}, but no position was found.`);
            return null;
        }
        
        const body = {
            category: 'linear',
            symbol,
            side: side === 'Buy' ? 'Sell' : 'Buy', // Opposite side to close
            orderType: 'Market',
            qty: position.size,
            reduceOnly: true,
        };
        logger.info(`Closing position with order: ${JSON.stringify(body)}`);
        return this.sendRequest(path, 'POST', body);
    }

    async getOpenPosition(symbol) {
        const path = `/v5/position/list?category=linear&symbol=${symbol}`;
        const result = await this.sendRequest(path, 'GET');
        if (result && result.list && result.list.length > 0) {
            // Assuming one position per symbol for one-way mode
            const openPosition = result.list.find(p => p.size > 0);
            return openPosition || null;
        }
        return null;
    }
}

export default BybitAPI;