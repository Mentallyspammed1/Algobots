const { RestClientV5, WebsocketClient } = require('bybit-api');

class BybitAPI {
    constructor(apiKey, apiSecret) {
        this.restClient = new RestClientV5({
            key: apiKey,
            secret: apiSecret,
        });
        this.wsClient = new WebsocketClient({
            key: apiKey,
            secret: apiSecret,
        });
    }

    // Market Data
    async getKline(symbol, interval, limit) {
        try {
            const response = await this.restClient.getKline({
                category: 'linear', // Assuming linear for now, can be made dynamic
                symbol,
                interval,
                limit,
            });
            return response.result.list;
        } catch (error) {
            console.error('Error getting kline data:', error);
            throw error;
        }
    }

    async getOrderBook(symbol, limit) {
        try {
            const response = await this.restClient.getOrderbook({
                category: 'linear', // Assuming linear for now
                symbol,
                limit,
            });
            return response.result;
        } catch (error) {
            console.error('Error getting order book:', error);
            throw error;
        }
    }

    // Order Management
    async placeOrder(params) {
        try {
            const response = await this.restClient.submitOrder({
                category: 'linear', // Assuming linear for now
                ...params,
            });
            return response.result;
        } catch (error) {
            console.error('Error placing order:', error);
            throw error;
        }
    }

    async cancelOrder(orderId, symbol) {
        try {
            const response = await this.restClient.cancelOrder({
                category: 'linear', // Assuming linear for now
                symbol,
                orderId,
            });
            return response.result;
        } catch (error) {
            console.error('Error cancelling order:', error);
            throw error;
        }
    }

    async amendOrder(params) {
        try {
            const response = await this.restClient.amendOrder({
                category: 'linear', // Assuming linear for now
                ...params,
            });
            return response.result;
        } catch (error) {
            console.error('Error amending order:', error);
            throw error;
        }
    }

    // Account Information
    async getWalletBalance(coin) {
        try {
            const response = await this.restClient.getWalletBalance({
                accountType: 'UNIFIED', // As per previous context, assuming UNIFIED
                coin,
            });
            return response.result;
        } catch (error) {
            console.error('Error getting wallet balance:', error);
            throw error;
        }
    }

    // WebSocket Subscriptions
    subscribeToKline(symbol, interval, callback) {
        this.wsClient.subscribeV5(`kline.${interval}.${symbol}`, 'linear');
        this.wsClient.on('update', (data) => {
            if (data.topic === `kline.${interval}.${symbol}`) {
                callback(data.data);
            }
        });
    }

    subscribeToOrderbook(symbol, depth, callback) {
        this.wsClient.subscribeV5(`orderbook.${depth}.${symbol}`, 'linear');
        this.wsClient.on('update', (data) => {
            if (data.topic === `orderbook.${depth}.${symbol}`) {
                callback(data.data);
            }
        });
    }

    subscribeToPrivateTopic(topic, callback) {
        this.wsClient.subscribeV5(topic, 'linear'); // 'linear' for private topics as well
        this.wsClient.on('update', (data) => {
            if (data.topic === topic) {
                callback(data.data);
            }
        });
    }
}

module.exports = BybitAPI;
