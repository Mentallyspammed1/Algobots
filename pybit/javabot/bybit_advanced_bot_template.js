
const { RestClientV5, WebsocketClient } = require('bybit-api');
const dotenv = require('dotenv');
const chalk = require('chalk');

// Load environment variables from .env file
dotenv.config();

// --- Configuration ---
const API_KEY = process.env.BYBIT_API_KEY || 'YOUR_API_KEY';
const API_SECRET = process.env.BYBIT_API_SECRET || 'YOUR_API_SECRET';
const TESTNET = process.env.TESTNET === 'true'; // Set to 'true' for testnet, 'false' for mainnet
const DRY_RUN = process.env.DRY_RUN === 'true';   // Set to 'true' to simulate trades without real execution
const SYMBOL = process.env.SYMBOL || 'BTCUSDT';
const CATEGORY = process.env.CATEGORY || 'linear'; // e.g., 'linear', 'spot', 'inverse'
const ACCOUNT_TYPE = process.env.ACCOUNT_TYPE || 'UNIFIED'; // e.g., 'UNIFIED', 'CONTRACT', 'SPOT'
const TIMEFRAME = parseInt(process.env.TIMEFRAME || '5'); // Kline timeframe in minutes (e.g., 1, 5, 15, 60)
const LOOP_INTERVAL_MS = parseInt(process.env.LOOP_INTERVAL_MS || '10000'); // Bot loop interval in milliseconds

// --- Logger ---
const logger = {
    info: (msg) => console.log(chalk.cyan(`[INFO] ${msg}`)),
    success: (msg) => console.log(chalk.green(`[SUCCESS] ${msg}`)),
    warn: (msg) => console.log(chalk.yellow(`[WARN] ${msg}`)),
    error: (msg) => console.log(chalk.red(`[ERROR] ${msg}`)),
    debug: (msg) => console.log(chalk.blue(`[DEBUG] ${msg}`)),
    critical: (msg) => console.log(chalk.bold.red(`[CRITICAL] ${msg}`))
};

// --- Bybit API Client Wrapper with Advanced Order Functions ---
class BybitClient {
    constructor(apiKey, apiSecret, testnet, dryRun, category, accountType) {
        this.dryRun = dryRun;
        this.category = category;
        this.accountType = accountType;
        this.restClient = new RestClientV5({
            key: apiKey,
            secret: apiSecret,
            testnet: testnet,
        });
        this.wsClient = new WebsocketClient({
            key: apiKey,
            secret: apiSecret,
            testnet: testnet,
        });
        logger.info(`Bybit client initialized. Testnet: ${testnet}, Dry Run: ${dryRun}, Category: ${category}, Account Type: ${accountType}`);
    }

    async getKlines(symbol, interval, limit) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating kline fetch for ${symbol} ${interval}min`);
            return Array.from({ length: limit }).map((_, i) => ({
                time: Date.now() - (limit - 1 - i) * interval * 60 * 1000,
                open: 30000 + Math.random() * 100,
                high: 30100 + Math.random() * 100,
                low: 29900 - Math.random() * 100,
                close: 30000 + Math.random() * 100,
                volume: 100 + Math.random() * 50,
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
                    open: parseFloat(k[1]),
                    high: parseFloat(k[2]),
                    low: parseFloat(k[3]),
                    close: parseFloat(k[4]),
                    volume: parseFloat(k[5]),
                })).sort((a, b) => a.time - b.time);
            } else {
                logger.error(`Error getting klines for ${symbol}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting klines for ${symbol}: ${error.message}`);
            return null;
        }
    }

    async getWalletBalance(coin = 'USDT') {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulated balance: 10000.00 ${coin}`);
            return 10000.00;
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
                logger.error(`Error getting balance: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting balance: ${error.message}`);
            return null;
        }
    }

    async placeOrder(params) {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would place order: ${JSON.stringify(params)}`));
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
            logger.error(`Exception placing order: ${error.message}`);
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
            logger.info(chalk.magenta(`[DRY RUN] Would cancel order ${orderId} for ${symbol}`));
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
                logger.error(`Failed to cancel order ${orderId}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception cancelling order ${orderId}: ${error.message}`);
            return null;
        }
    }

    async cancelAllOpenOrders(symbol) {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would cancel all open orders for ${symbol}`));
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
                logger.error(`Failed to cancel all orders for ${symbol}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception cancelling all orders for ${symbol}: ${error.message}`);
            return null;
        }
    }

    async amendOrder(symbol, orderId, newQty = null, newPrice = null) {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would amend order ${orderId} for ${symbol} with qty: ${newQty}, price: ${newPrice}`));
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
                logger.error(`Failed to amend order ${orderId}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception amending order ${orderId}: ${error.message}`);
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
                logger.error(`Error getting open orders: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting open orders: ${error.message}`);
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
                logger.error(`Error getting position info: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception getting position info: ${error.message}`);
            return null;
        }
    }

    async setLeverage(symbol, buyLeverage, sellLeverage) {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would set leverage for ${symbol} to Buy: ${buyLeverage}x, Sell: ${sellLeverage}x`));
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
                return { success: true }; // Treat as success if already set
            } else {
                logger.error(`Failed to set leverage for ${symbol}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception setting leverage for ${symbol}: ${error.message}`);
            return null;
        }
    }

    async setTradingStop(symbol, takeProfit = null, stopLoss = null, trailingStop = null, tpTriggerBy = 'MarkPrice', slTriggerBy = 'MarkPrice') {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would set TP/SL/Trailing for ${symbol}. TP: ${takeProfit}, SL: ${stopLoss}, Trailing: ${trailingStop}`));
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
                logger.error(`Failed to set TP/SL/Trailing for ${symbol}: ${response.retMsg}`);
                return null;
            }
        } catch (error) {
            logger.error(`Exception setting TP/SL/Trailing for ${symbol}: ${error.message}`);
            return null;
        }
    }

    // WebSocket Subscriptions (Examples)
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
        // Private topics require authentication. Ensure your API key has permissions.
        // Example topics: 'position', 'execution', 'order'
        this.wsClient.subscribeV5(topic, this.category);
        this.wsClient.on('update', (data) => {
            if (data.topic === topic) {
                callback(data.data);
            }
        });
    }
}

// --- Bot Logic (Placeholders) ---
async function generateSignal(klines) {
    // Implement your advanced trading strategy here.
    // This is a placeholder. Example: Use indicators, price action, etc.
    if (!klines || klines.length < 2) {
        logger.warn("Not enough klines for signal generation.");
        return 'HOLD';
    }

    const lastClose = klines[klines.length - 1].close;
    const prevClose = klines[klines.length - 2].close;

    if (lastClose > prevClose) {
        return 'BUY';
    } else if (lastClose < prevClose) {
        return 'SELL';
    } else {
        return 'HOLD';
    }
}

async function executeTrade(bybit, signal, currentPrice, balance) {
    const tradeAmount = balance * 0.01; // Example: Risk 1% of balance
    const qty = tradeAmount / currentPrice; // Calculate quantity based on current price

    if (signal === 'BUY') {
        logger.info(`Executing BUY signal for ${SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        // Example: Place a market order with a 0.5% TP and 0.2% SL
        const takeProfitPrice = currentPrice * 1.005;
        const stopLossPrice = currentPrice * 0.998;
        await bybit.placeMarketOrder(SYMBOL, 'Buy', qty, takeProfitPrice, stopLossPrice);
    } else if (signal === 'SELL') {
        logger.info(`Executing SELL signal for ${SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        // Example: Place a limit order at current price with a 0.5% TP and 0.2% SL
        const takeProfitPrice = currentPrice * 0.995;
        const stopLossPrice = currentPrice * 1.002;
        await bybit.placeLimitOrder(SYMBOL, 'Sell', qty, currentPrice, 'GTC', false, takeProfitPrice, stopLossPrice);
    } else {
        logger.info(`No trade executed. Signal: ${signal}`);
    }
}

// --- Main Bot Loop ---
async function main() {
    logger.info(chalk.bold.yellow(`Pyrmethus awakens the Advanced Bybit Trading Bot for ${SYMBOL}!`));
    logger.info(`Operating in ${TESTNET ? 'TESTNET' : 'MAINNET'} mode, ${DRY_RUN ? 'DRY RUN' : 'LIVE'} execution.`);

    const bybit = new BybitClient(API_KEY, API_SECRET, TESTNET, DRY_RUN, CATEGORY, ACCOUNT_TYPE);

    // Optional: Set leverage once at startup
    // await bybit.setLeverage(SYMBOL, 10, 10); // Set 10x leverage for both buy and sell

    while (true) {
        try {
            logger.info(`Fetching klines for ${SYMBOL} (${TIMEFRAME}min)...`);
            const klines = await bybit.getKlines(SYMBOL, TIMEFRAME, 100); // Fetch last 100 klines

            if (!klines || klines.length === 0) {
                logger.warn("Failed to fetch klines or no data. Retrying...");
                await sleep(LOOP_INTERVAL_MS);
                continue;
            }

            const currentPrice = klines[klines.length - 1].close;
            logger.info(`Current price for ${SYMBOL}: ${currentPrice}`);

            const balance = await bybit.getWalletBalance();
            if (balance === null) {
                logger.error("Failed to get wallet balance. Retrying...");
                await sleep(LOOP_INTERVAL_MS);
                continue;
            }
            logger.info(`Current balance: ${balance.toFixed(2)} USDT`);

            const signal = await generateSignal(klines);
            logger.info(`Generated signal: ${signal}`);

            await executeTrade(bybit, signal, currentPrice, balance);

            // Example: Get open positions and orders (for monitoring)
            // const openPositions = await bybit.getPositionInfo(SYMBOL);
            // logger.info(`Open Positions: ${openPositions.length}`);
            // const openOrders = await bybit.getOpenOrders(SYMBOL);
            // logger.info(`Open Orders: ${openOrders.length}`);

        } catch (error) {
            logger.critical(`An unhandled error occurred in the main loop: ${error.message}`);
            logger.error(error.stack);
        }

        logger.info(`Sleeping for ${LOOP_INTERVAL_MS / 1000} seconds...`);
        await sleep(LOOP_INTERVAL_MS);
    }
}

// --- Utility Sleep Function ---
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// --- Entry Point ---
if (require.main === module) {
    // Basic check for API keys
    if (API_KEY === 'YOUR_API_KEY' || API_SECRET === 'YOUR_API_SECRET') {
        logger.critical("API_KEY or API_SECRET not set. Please configure your .env file.");
        process.exit(1);
    }
    main().catch(err => {
        logger.critical(`Bot terminated due to a fatal error: ${err.message}`);
        process.exit(1);
    });
}

/*
To run this advanced bot:
1. Make sure you have Node.js installed.
2. Create a .env file in the same directory with your Bybit API credentials and bot settings:
   BYBIT_API_KEY=YOUR_BYBIT_API_KEY
   BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
   TESTNET=true        # or false for mainnet
   DRY_RUN=true        # or false for live trading
   SYMBOL=BTCUSDT
   CATEGORY=linear     # or spot, inverse
   ACCOUNT_TYPE=UNIFIED # or CONTRACT, SPOT
   TIMEFRAME=5
   LOOP_INTERVAL_MS=10000

3. Install dependencies:
   npm install dotenv bybit-api chalk

4. Run the bot:
   node bybit_advanced_bot_template.js

Important Notes:
- Fill in BYBIT_API_KEY and BYBIT_API_SECRET in your .env file.
- Ensure your API key has the necessary permissions for the operations you intend to perform (e.g., Trade, Read Data).
- For live trading (DRY_RUN=false), exercise extreme caution and thoroughly test your strategy in a testnet environment first.
- This template provides common order types. Refer to Bybit's official V5 API documentation for all available parameters and advanced order features.
*/
