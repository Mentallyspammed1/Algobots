// bybitClient.js
import { RestClientV5, WebsocketClient } from 'bybit-api';
import logger from './logger.js';
import config from './config.js';

class BybitClient {
    constructor() {
        this.dryRun = config.DRY_RUN;
        this.category = config.CATEGORY;
        this.accountType = config.ACCOUNT_TYPE;
        
        this.restClient = new RestClientV5({
            key: config.API_KEY,
            secret: config.API_SECRET,
            testnet: config.TESTNET,
        });
        
        this.wsClient = new WebsocketClient({
            key: config.API_KEY,
            secret: config.API_SECRET,
            testnet: config.TESTNET,
        });
        logger.info(`Bybit client initialized. Testnet: ${config.TESTNET}, Dry Run: ${config.DRY_RUN}, Category: ${config.CATEGORY}, Account Type: ${config.ACCOUNT_TYPE}`);
    }

    async getKlines(symbol, interval, limit) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating kline fetch for ${symbol} ${interval}min`);
            const dummyKlines = [];
            let lastClose = 30000;
            for (let i = 0; i < limit; i++) {
                const open = lastClose + (Math.random() - 0.5) * 50;
                const close = open + (Math.random() - 0.5) * 100;
                const high = Math.max(open, close) + Math.random() * 50;
                const low = Math.min(open, close) - Math.random() * 50;
                dummyKlines.push({
                    time: Date.now() - (limit - 1 - i) * interval * 60 * 1000,
                    open: open,
                    high: high,
                    low: low,
                    close: close,
                    volume: 100 + Math.random() * 50,
                });
                lastClose = close;
            }
            return dummyKlines;
        }
        try {
            const response = await this.restClient.getKline({
                category: this.category,
                symbol,
                interval: String(interval),
                limit,
            });
            if (response.retCode === 0 && response.result && response.result.list) {
                return response.result.list.map(k => ({
                    time: parseInt(k[0]),
                    open: parseFloat(k[1]),
                    high: parseFloat(k[2]),
                    low: parseFloat(k[3]),
                    close: parseFloat(k[4]),
                    volume: parseFloat(k[5]),
                })).sort((a, b) => a.time - b.time);
            } else {
                logger.error(`Error fetching klines for ${symbol}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception fetching klines for ${symbol}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async getWalletBalance(coin = 'USDT') {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulated balance: ${config.DEFAULT_DUMMY_BALANCE} ${coin}`);
            return config.DEFAULT_DUMMY_BALANCE;
        }
        try {
            const response = await this.restClient.getWalletBalance({
                accountType: this.accountType,
                coin,
            });
            if (response.retCode === 0 && response.result && response.result.list && response.result.list.length > 0) {
                const coinData = response.result.list[0].coin.find(c => c.coin === coin);
                return coinData ? parseFloat(coinData.walletBalance) : 0;
            } else {
                logger.error(`Error fetching balance: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception fetching balance: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async placeOrder(params) {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would place order: ${JSON.stringify(params)}`);
            return { orderId: `DRY_ORDER_${Date.now()}`, status: 'FILLED' };
        }
        try {
            const response = await this.restClient.submitOrder({
                category: this.category,
                ...params,
            });
            if (response.retCode === 0) {
                logger.success(`Order placed: ${response.result.orderId}`);
                return response.result;
            } else {
                logger.error(`Failed to place order: ${response.retMsg} (Code: ${response.retCode})`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception placing order: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async placeMarketOrder(symbol, side, qty, takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType: 'Market',
            qty: String(qty),
            timeInForce: 'GTC',
            reduceOnly: reduceOnly ? true : false,
        };
        if (takeProfit) { params.takeProfit = String(takeProfit); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = String(stopLoss); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    async placeLimitOrder(symbol, side, qty, price, timeInForce = 'GTC', postOnly = false, takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType: 'Limit',
            qty: String(qty),
            price: String(price),
            timeInForce,
            postOnly: postOnly ? true : false,
            reduceOnly: reduceOnly ? true : false,
        };
        if (takeProfit) { params.takeProfit = String(takeProfit); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = String(stopLoss); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    async placeConditionalOrder(symbol, side, qty, triggerPrice, orderType = 'Market', price = null, triggerBy = 'MarkPrice', takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType,
            qty: String(qty),
            triggerPrice: String(triggerPrice),
            triggerBy,
            timeInForce: 'GTC',
            reduceOnly: reduceOnly ? true : false,
        };
        if (orderType === 'Limit' && price) params.price = String(price);
        if (takeProfit) { params.takeProfit = String(takeProfit); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = String(stopLoss); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    async cancelOrder(symbol, orderId) {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would cancel order ${orderId} for ${symbol}`);
            return { orderId, status: 'CANCELED' };
        }
        try {
            const response = await this.restClient.cancelOrder({
                category: this.category,
                symbol,
                orderId,
            });
            if (response.retCode === 0) {
                logger.success(`Order ${orderId} cancelled.`);
                return response.result;
            } else {
                logger.error(`Failed to cancel order ${orderId}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception cancelling order ${orderId}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async cancelAllOpenOrders(symbol) {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would cancel all open orders for ${symbol}`);
            return { success: true };
        }
        try {
            const response = await this.restClient.cancelAllOrders({
                category: this.category,
                symbol,
            });
            if (response.retCode === 0) {
                logger.success(`All open orders for ${symbol} cancelled.`);
                return response.result;
            } else {
                logger.error(`Failed to cancel all orders for ${symbol}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception cancelling all orders for ${symbol}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async amendOrder(symbol, orderId, newQty = null, newPrice = null) {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would amend order ${orderId} for ${symbol} with qty: ${newQty}, price: ${newPrice}`);
            return { orderId, status: 'AMENDED' };
        }
        const params = {
            category: this.category,
            symbol,
            orderId,
        };
        if (newQty) params.qty = String(newQty);
        if (newPrice) params.price = String(newPrice);

        try {
            const response = await this.restClient.amendOrder(params);
            if (response.retCode === 0) {
                logger.success(`Order ${orderId} amended.`);
                return response.result;
            } else {
                logger.error(`Failed to amend order ${orderId}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception amending order ${orderId}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async getOpenOrders(symbol = null) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating get open orders for ${symbol || 'all symbols'}`);
            return [];
        }
        try {
            const params = { category: this.category };
            if (symbol) params.symbol = symbol;
            const response = await this.restClient.getOpenOrders(params);
            if (response.retCode === 0) {
                return response.result.list;
            } else {
                logger.error(`Error getting open orders: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting open orders: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async getPositionInfo(symbol = null) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating get position info for ${symbol || 'all symbols'}`);
            return [];
        }
        try {
            const params = { category: this.category };
            if (symbol) params.symbol = symbol;
            const response = await this.restClient.getPositionInfo(params);
            if (response.retCode === 0) {
                return response.result.list;
            } else {
                logger.error(`Error getting position info: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting position info: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async setLeverage(symbol, buyLeverage, sellLeverage) {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would set leverage for ${symbol} to Buy: ${buyLeverage}x, Sell: ${sellLeverage}x`);
            return { success: true };
        }
        try {
            const response = await this.restClient.setLeverage({
                category: this.category,
                symbol,
                buyLeverage: String(buyLeverage),
                sellLeverage: String(sellLeverage),
            });
            if (response.retCode === 0) {
                logger.success(`Leverage set for ${symbol}.`);
                return response.result;
            } else if ([110026, 110043].includes(response.retCode)) {
                logger.warn(`Leverage already set for ${symbol} or no change needed.`);
                return { success: true };
            }
            else {
                logger.error(`Failed to set leverage for ${symbol}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception setting leverage for ${symbol}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    async setTradingStop(symbol, takeProfit = null, stopLoss = null, trailingStop = null, tpTriggerBy = 'MarkPrice', slTriggerBy = 'MarkPrice') {
        if (this.dryRun) {
            logger.info(`[DRY RUN] Would set TP/SL/Trailing for ${symbol}. TP: ${takeProfit}, SL: ${stopLoss}, Trailing: ${trailingStop}`);
            return { success: true };
        }
        const params = {
            category: this.category,
            symbol,
        };
        if (takeProfit) { params.takeProfit = String(takeProfit); params.tpTriggerBy = tpTriggerBy; }
        if (stopLoss) { params.stopLoss = String(stopLoss); params.slTriggerBy = slTriggerBy; }
        if (trailingStop) params.trailingStop = String(trailingStop);

        try {
            const response = await this.restClient.setTradingStop(params);
            if (response.retCode === 0) {
                logger.success(`TP/SL/Trailing set for ${symbol}.`);
                return response.result;
            } else {
                logger.error(`Failed to set TP/SL/Trailing for ${symbol}: ${response.retMsg}. Code: ${response.retCode}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception setting TP/SL/Trailing for ${symbol}: ${error.message}. Full error: ${JSON.stringify(error)}`);
            return null;
        }
    }

    subscribeToKline(symbol, interval, callback) {
        this.wsClient.subscribeV5(`kline.${interval}.${symbol}`, this.category);
        this.wsClient.on('update', (data) => {
            if (data.topic === `kline.${interval}.${symbol}`) {
                callback(data.data);
            }
        });
    }

    subscribeToOrderbook(symbol, depth, callback) {
        this.wsClient.subscribeV5(`orderbook.${depth}.${symbol}`, this.category);
        this.wsClient.on('update', (data) => {
            if (data.topic === `orderbook.${depth}.${symbol}`) {
                callback(data.data);
            }
        });
    }

    subscribeToPrivateTopic(topic, callback) {
        this.wsClient.subscribeV5(topic, this.category);
        this.wsClient.on('update', (data) => {
            if (data.topic === topic) {
                callback(data.data);
            }
        });
    }
}

export default BybitClient;
