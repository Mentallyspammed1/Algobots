const { RestClientV5, WebsocketClient } = require('bybit-api');
const { Decimal } = require('decimal.js');
const chalk = require('chalk');

/**
 * @typedef {object} Kline
 * @property {number} time
 * @property {Decimal} open
 * @property {Decimal} high
 * @property {Decimal} low
 * @property {Decimal} close
 * @property {Decimal} volume
 */

/**
 * Client for interacting with the Bybit V5 API, handling both REST and WebSocket connections.
 * Supports dry-run mode for testing without actual trades.
 */
class BybitClient {
    /**
     * Creates an instance of BybitClient.
     * @param {object} config - The configuration object for the bot.
     * @param {object} config.api - API configuration.
     * @param {boolean} config.api.dryRun - Whether to enable dry run mode.
     * @param {string} config.api.category - The trading category (e.g., 'linear').
     * @param {string} config.api.accountType - The Bybit account type (e.g., 'UNIFIED').
     * @param {string} config.api.key - The Bybit API key.
     * @param {string} config.api.secret - The Bybit API secret.
     * @param {boolean} config.api.testnet - Whether to connect to the testnet.
     */
    constructor(config) {
        this.dryRun = config.api.dryRun;
        this.category = config.api.category;
        this.accountType = config.api.accountType;
        this.restClient = new RestClientV5({
            key: config.api.key,
            secret: config.api.secret,
            testnet: config.api.testnet,
        });
        this.wsClient = new WebsocketClient({
            key: config.api.key,
            secret: config.api.secret,
            testnet: config.api.testnet,
        });
        this.klinesData = []; // Stores historical klines, updated by WebSocket
        this.wsConnected = false;

        // Assuming a global logger is available or passed in config
        console.log(chalk.cyan(`[INFO] Bybit client initialized. Testnet: ${config.api.testnet}, Dry Run: ${config.api.dryRun}, Category: ${config.api.category}, Account Type: ${config.api.accountType}`));
    }

    /**
     * Closes an open position for a given symbol.
     * @param {string} symbol - The trading symbol (e.g., 'BTCUSDT').
     * @returns {Promise<object|null>} An object with success status or null if an error occurred.
     */
    async closePosition(symbol) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would close position for ${symbol}`));
            return { success: true };
        }
        try {
            const positionInfo = await this.getPositionInfo(symbol);
            if (!positionInfo || positionInfo.length === 0 || new Decimal(positionInfo[0].size).lte(0)) {
                console.log(chalk.yellow(`[WARN] No open position to close for ${symbol}.`));
                return { success: true };
            }

            const position = positionInfo[0];
            const side = position.side === 'Buy' ? 'Sell' : 'Buy';
            const qty = new Decimal(position.size);

            const response = await this.restClient.submitOrder({
                category: this.category,
                symbol,
                side,
                orderType: 'Market',
                qty: qty.toString(),
                reduceOnly: true,
                timeInForce: 'FOC', // Fill or Kill
            });

            if (response.retCode === 0) {
                console.log(chalk.green(`[SUCCESS] Position for ${symbol} closed. Order ID: ${response.result.orderId}`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to close position for ${symbol}: ${response.retMsg} (Code: ${response.retCode})`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception closing position for ${symbol}: ${error.message}`));
            return null;
        }
    }

    /**
     * Retrieves historical kline data for a given symbol and interval.
     * @param {string} symbol - The trading symbol (e.g., 'BTCUSDT').
     * @param {string} interval - The kline interval (e.g., '1', '5', '60').
     * @param {number} limit - The number of klines to retrieve.
     * @returns {Promise<Array<Kline>|null>} An array of kline objects or null if an error occurred.
     */
    async getKlines(symbol, interval, limit) {
        if (this.dryRun) {
            console.log(chalk.blue(`[DRY RUN] Simulating kline fetch for ${symbol} ${interval}min`));
            return Array.from({ length: limit }).map((_, i) => ({
                time: Date.now() - (limit - 1 - i) * interval * 60 * 1000,
                open: new Decimal(30000 + Math.random() * 100),
                high: new Decimal(30100 + Math.random() * 100),
                low: new Decimal(29900 - Math.random() * 100),
                close: new Decimal(30000 + Math.random() * 100),
                volume: new Decimal(100 + Math.random() * 50),
            }));
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
                    open: new Decimal(k[1]),
                    high: new Decimal(k[2]),
                    low: new Decimal(k[3]),
                    close: new Decimal(k[4]),
                    volume: new Decimal(k[5]),
                })).sort((a, b) => a.time - b.time);
            } else {
                console.log(chalk.red(`[ERROR] Error getting klines for ${symbol}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception getting klines for ${symbol}: ${error.message}`));
            return null;
        }
    }

    /**
     * Retrieves the wallet balance for a specified coin.
     * @param {string} [coin='USDT'] - The coin to get the balance for.
     * @returns {Promise<Decimal|null>} The balance as a Decimal object or null if an error occurred.
     */
    async getWalletBalance(coin = 'USDT') {
        if (this.dryRun) {
            console.log(chalk.blue(`[DRY RUN] Simulated balance: 10000.00 ${coin}`));
            return new Decimal(10000.00);
        }
        try {
            const response = await this.restClient.getWalletBalance({
                accountType: this.accountType,
                coin,
            });
            if (response.retCode === 0 && response.result && response.result.list && response.result.list.length > 0) {
                const coinData = response.result.list[0].coin.find(c => c.coin === coin);
                return coinData ? new Decimal(coinData.walletBalance) : new Decimal(0);
            } else {
                console.log(chalk.red(`[ERROR] Error getting balance: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception getting balance: ${error.message}`));
            return null;
        }
    }

    /**
     * Places a new order on the exchange.
     * @param {object} params - Order parameters.
     * @param {string} params.symbol - The trading symbol.
     * @param {string} params.side - Order side ('Buy' or 'Sell').
     * @param {string} params.orderType - Order type ('Market', 'Limit', 'Conditional').
     * @param {string} params.qty - Order quantity.
     * @param {string} [params.price] - Order price (for Limit and Conditional orders).
     * @param {string} [params.takeProfit] - Take profit price.
     * @param {string} [params.stopLoss] - Stop loss price.
     * @param {boolean} [params.reduceOnly] - Reduce only flag.
     * @param {string} [params.timeInForce] - Time in force policy.
     * @returns {Promise<object|null>} The order result object or null if an error occurred.
     */
    async placeOrder(params) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would place order: ${JSON.stringify(params)}`));
            return { orderId: `DRY_ORDER_${Date.now()}`, status: 'FILLED' };
        }
        try {
            const response = await this.restClient.submitOrder({
                category: this.category,
                ...params,
            });
            if (response.retCode === 0) {
                console.log(chalk.green(`[SUCCESS] Order placed: ${response.result.orderId}`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to place order: ${response.retMsg} (Code: ${response.retCode})`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception placing order: ${error.message}`));
            return null;
        }
    }

    /**
     * Places a market order.
     * @param {string} symbol - The trading symbol.
     * @param {string} side - Order side ('Buy' or 'Sell').
     * @param {Decimal} qty - Order quantity.
     * @param {Decimal|null} [takeProfit=null] - Take profit price.
     * @param {Decimal|null} [stopLoss=null] - Stop loss price.
     * @param {boolean} [reduceOnly=false] - Reduce only flag.
     * @returns {Promise<object|null>} The order result object or null if an error occurred.
     */
    async placeMarketOrder(symbol, side, qty, takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType: 'Market',
            qty: qty.toString(),
            timeInForce: 'GTC',
            reduceOnly: reduceOnly ? true : false,
        };
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    /**
     * Places a limit order.
     * @param {string} symbol - The trading symbol.
     * @param {string} side - Order side ('Buy' or 'Sell').
     * @param {Decimal} qty - Order quantity.
     * @param {Decimal} price - Order price.
     * @param {string} [timeInForce='GTC'] - Time in force policy.
     * @param {boolean} [postOnly=false] - Post only flag.
     * @param {Decimal|null} [takeProfit=null] - Take profit price.
     * @param {Decimal|null} [stopLoss=null] - Stop loss price.
     * @param {boolean} [reduceOnly=false] - Reduce only flag.
     * @returns {Promise<object|null>} The order result object or null if an error occurred.
     */
    async placeLimitOrder(symbol, side, qty, price, timeInForce = 'GTC', postOnly = false, takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType: 'Limit',
            qty: qty.toString(),
            price: price.toString(),
            timeInForce,
            postOnly: postOnly ? true : false,
            reduceOnly: reduceOnly ? true : false,
        };
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    /**
     * Places a conditional order (e.g., Stop Market, Take Profit Market).
     * @param {string} symbol - The trading symbol.
     * @param {string} side - Order side ('Buy' or 'Sell').
     * @param {Decimal} qty - Order quantity.
     * @param {Decimal} triggerPrice - The price that triggers the order.
     * @param {string} [orderType='Market'] - The type of order to be placed when triggered ('Market' or 'Limit').
     * @param {Decimal|null} [price=null] - The order price if orderType is 'Limit'.
     * @param {string} [triggerBy='MarkPrice'] - The price type to use for triggering.
     * @param {Decimal|null} [takeProfit=null] - Take profit price.
     * @param {Decimal|null} [stopLoss=null] - Stop loss price.
     * @param {boolean} [reduceOnly=false] - Reduce only flag.
     * @returns {Promise<object|null>} The order result object or null if an error occurred.
     */
    async placeConditionalOrder(symbol, side, qty, triggerPrice, orderType = 'Market', price = null, triggerBy = 'MarkPrice', takeProfit = null, stopLoss = null, reduceOnly = false) {
        const params = {
            symbol,
            side,
            orderType,
            qty: qty.toString(),
            triggerPrice: triggerPrice.toString(),
            triggerBy,
            timeInForce: 'GTC',
            reduceOnly: reduceOnly ? true : false,
        };
        if (orderType === 'Limit' && price) params.price = price.toString();
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

    /**
     * Cancels a specific open order.
     * @param {string} symbol - The trading symbol.
     * @param {string} orderId - The ID of the order to cancel.
     * @returns {Promise<object|null>} The cancellation result object or null if an error occurred.
     */
    async cancelOrder(symbol, orderId) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would cancel order ${orderId} for ${symbol}`));
            return { orderId, status: 'CANCELED' };
        }
        try {
            const response = await this.restClient.cancelOrder({
                category: this.category,
                symbol,
                orderId,
            });
            if (response.retCode === 0) {
                console.log(chalk.green(`[SUCCESS] Order ${orderId} cancelled.`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to cancel order ${orderId}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception cancelling order ${orderId}: ${error.message}`));
            return null;
        }
    }

    /**
     * Cancels all open orders for a given symbol.
     * @param {string} symbol - The trading symbol.
     * @returns {Promise<object|null>} The cancellation result object or null if an error occurred.
     */
    async cancelAllOpenOrders(symbol) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would cancel all open orders for ${symbol}`));
            return { success: true };
        }
        try {
            const response = await this.restClient.cancelAllOrders({
                category: this.category,
                symbol,
            });
            if (response.retCode === 0) {
                console.log(chalk.green(`[SUCCESS] All open orders for ${symbol} cancelled.`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to cancel all orders for ${symbol}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception cancelling all orders for ${symbol}: ${error.message}`));
            return null;
        }
    }

    /**
     * Amends an existing order.
     * @param {string} symbol - The trading symbol.
     * @param {string} orderId - The ID of the order to amend.
     * @param {Decimal|null} [newQty=null] - The new quantity for the order.
     * @param {Decimal|null} [newPrice=null] - The new price for the order.
     * @returns {Promise<object|null>} The amendment result object or null if an error occurred.
     */
    async amendOrder(symbol, orderId, newQty = null, newPrice = null) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would amend order ${orderId} for ${symbol} with qty: ${newQty}, price: ${newPrice}`));
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
                console.log(chalk.green(`[SUCCESS] Order ${orderId} amended.`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to amend order ${orderId}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception amending order ${orderId}: ${error.message}`));
            return null;
        }
    }

    /**
     * Retrieves a list of open orders.
     * @param {string|null} [symbol=null] - The trading symbol. If null, retrieves open orders for all symbols.
     * @returns {Promise<Array<object>|null>} An array of open order objects or null if an error occurred.
     */
    async getOpenOrders(symbol = null) {
        if (this.dryRun) {
            console.log(chalk.blue(`[DRY RUN] Simulating get open orders for ${symbol || 'all symbols'}`));
            return [];
        }
        try {
            const params = { category: this.category };
            if (symbol) params.symbol = symbol;
            const response = await this.restClient.getOpenOrders(params);
            if (response.retCode === 0) {
                return response.result.list;
            } else {
                console.log(chalk.red(`[ERROR] Error getting open orders: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception getting open orders: ${error.message}`));
            return null;
        }
    }

    /**
     * Retrieves position information for a given symbol or all symbols.
     * @param {string|null} [symbol=null] - The trading symbol. If null, retrieves positions for all symbols.
     * @returns {Promise<Array<object>|null>} An array of position objects or null if an error occurred.
     */
    async getPositionInfo(symbol = null) {
        if (this.dryRun) {
            console.log(chalk.blue(`[DRY RUN] Simulating get position info for ${symbol || 'all symbols'}`));
            return [];
        }
        try {
            const params = { category: this.category };
            if (symbol) params.symbol = symbol;
            const response = await this.restClient.getPositionInfo(params);
            if (response.retCode === 0) {
                return response.result.list;
            } else {
                console.log(chalk.red(`[ERROR] Error getting position info: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception getting position info: ${error.message}`));
            return null;
        }
    }

    /**
     * Sets the leverage for a given symbol.
     * @param {string} symbol - The trading symbol.
     * @param {number} buyLeverage - The leverage for buy orders.
     * @param {number} sellLeverage - The leverage for sell orders.
     * @returns {Promise<object|null>} The result object or null if an error occurred.
     */
    async setLeverage(symbol, buyLeverage, sellLeverage) {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would set leverage for ${symbol} to Buy: ${buyLeverage}x, Sell: ${sellLeverage}x`));
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
                console.log(chalk.green(`[SUCCESS] Leverage set for ${symbol}.`));
                return response.result;
            } else if ([110026, 110043].includes(response.retCode)) {
                console.log(chalk.yellow(`[WARN] Leverage already set for ${symbol} or no change needed.`));
                return { success: true };
            } else {
                console.log(chalk.red(`[ERROR] Failed to set leverage for ${symbol}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception setting leverage for ${symbol}: ${error.message}`));
            return null;
        }
    }

    /**
     * Sets Take Profit, Stop Loss, and Trailing Stop for a position.
     * @param {string} symbol - The trading symbol.
     * @param {Decimal|null} [takeProfit=null] - Take profit price.
     * @param {Decimal|null} [stopLoss=null] - Stop loss price.
     * @param {Decimal|null} [trailingStop=null] - Trailing stop value.
     * @param {string} [tpTriggerBy='MarkPrice'] - Trigger type for take profit.
     * @param {string} [slTriggerBy='MarkPrice'] - Trigger type for stop loss.
     * @returns {Promise<object|null>} The result object or null if an error occurred.
     */
    async setTradingStop(symbol, takeProfit = null, stopLoss = null, trailingStop = null, tpTriggerBy = 'MarkPrice', slTriggerBy = 'MarkPrice') {
        if (this.dryRun) {
            console.log(chalk.magenta(`[DRY RUN] Would set TP/SL/Trailing for ${symbol}. TP: ${takeProfit}, SL: ${stopLoss}, Trailing: ${trailingStop}`));
            return { success: true };
        }
        const params = {
            category: this.category,
            symbol,
        };
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = tpTriggerBy; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = slTriggerBy; }
        if (trailingStop) params.trailingStop = trailingStop.toString();

        try {
            const response = await this.restClient.setTradingStop(params);
            if (response.retCode === 0) {
                console.log(chalk.green(`[SUCCESS] TP/SL/Trailing set for ${symbol}.`));
                return response.result;
            } else {
                console.log(chalk.red(`[ERROR] Failed to set TP/SL/Trailing for ${symbol}: ${response.retMsg}`));
                return null;
            }
        } catch (error) {
            console.log(chalk.red(`[ERROR] Exception setting TP/SL/Trailing for ${symbol}: ${error.message}`));
            return null;
        }
    }

    /**
     * Connects to the Bybit WebSocket for real-time kline data.
     * @param {string} symbol - The trading symbol.
     * @param {string} interval - The kline interval.
     */
    connectWebSocket(symbol, interval) {
        if (this.wsConnected) {
            console.log(chalk.cyan("WebSocket already connected."));
            return;
        }

        console.log(chalk.cyan(`Connecting WebSocket for ${symbol} ${interval}min klines...`));
        this.wsClient.subscribeV5(`kline.${interval}.${symbol}`, this.category);

        this.wsClient.on('open', () => {
            this.wsConnected = true;
            console.log(chalk.green("WebSocket connection established."));
        });

        this.wsClient.on('update', (data) => {
            if (data.topic === `kline.${interval}.${symbol}` && data.data && data.data.length > 0) {
                const newKline = data.data[0];
                if (newKline.confirm) {
                    const formattedKline = {
                        time: parseInt(newKline.start),
                        open: new Decimal(newKline.open),
                        high: new Decimal(newKline.high),
                        low: new Decimal(newKline.low),
                        close: new Decimal(newKline.close),
                        volume: new Decimal(newKline.volume),
                    };
                    const existingIndex = this.klinesData.findIndex(k => k.time === formattedKline.time);
                    if (existingIndex !== -1) {
                        this.klinesData[existingIndex] = formattedKline;
                        console.log(chalk.blue(`[DEBUG] Updated kline for ${symbol} at ${new Date(formattedKline.time).toLocaleTimeString()}`));
                    } else {
                        this.klinesData.push(formattedKline);
                        this.klinesData.sort((a, b) => a.time - b.time);
                        if (this.klinesData.length > 200) {
                            this.klinesData.shift();
                        }
                        console.log(chalk.blue(`[DEBUG] Added new kline for ${symbol} at ${new Date(formattedKline.time).toLocaleTimeString()}`));
                    }
                }
            }
        });

        this.wsClient.on('close', () => {
            this.wsConnected = false;
            console.log(chalk.yellow("WebSocket connection closed. Attempting to reconnect..."));
            setTimeout(() => this.connectWebSocket(symbol, interval), 5000);
        });

        this.wsClient.on('error', (err) => {
            console.log(chalk.red(`[ERROR] WebSocket error: ${err.message}`));
            this.wsConnected = false;
        });
    }
}

module.exports = BybitClient;
