
const { RestClientV5, WebsocketClient } = require('bybit-api');
const dotenv = require('dotenv');
const chalk = require('chalk');
const { Decimal } = require('decimal.js');

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
const TIMEFRAME = parseInt(process.env.TIMEFRAME || '1'); // Kline timeframe in minutes (e.g., 1, 5, 15, 60)
const LOOP_INTERVAL_MS = parseInt(process.env.LOOP_INTERVAL_MS || '5000'); // Bot loop interval in milliseconds

// Indicator Periods
const RSI_PERIOD = parseInt(process.env.RSI_PERIOD || '14');
const SMA_SHORT_PERIOD = parseInt(process.env.SMA_SHORT_PERIOD || '10');
const SMA_LONG_PERIOD = parseInt(process.env.SMA_LONG_PERIOD || '30');

// --- Logger ---
const logger = {
    info: (msg) => console.log(chalk.cyan(`[INFO] ${msg}`)),
    success: (msg) => console.log(chalk.green(`[SUCCESS] ${msg}`)),
    warn: (msg) => console.log(chalk.yellow(`[WARN] ${msg}`)),
    error: (msg) => console.log(chalk.red(`[ERROR] ${msg}`)),
    debug: (msg) => console.log(chalk.blue(`[DEBUG] ${msg}`)),
    critical: (msg) => console.log(chalk.bold.red(`[CRITICAL] ${msg}`))
};

// --- Bybit API Client Wrapper with Advanced Order Functions and WebSockets ---
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
        this.klinesData = []; // Stores historical klines, updated by WebSocket
        this.wsConnected = false;

        logger.info(`Bybit client initialized. Testnet: ${testnet}, Dry Run: ${dryRun}, Category: ${category}, Account Type: ${accountType}`);
    }

    async getKlines(symbol, interval, limit) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating kline fetch for ${symbol} ${interval}min`);
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
            qty: qty.toString(),
            timeInForce: 'GTC',
            reduceOnly: reduceOnly ? true : false,
        };
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = 'MarkPrice'; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = 'MarkPrice'; }
        return this.placeOrder(params);
    }

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
                return { success: true };
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
        if (takeProfit) { params.takeProfit = takeProfit.toString(); params.tpTriggerBy = tpTriggerBy; }
        if (stopLoss) { params.stopLoss = stopLoss.toString(); params.slTriggerBy = slTriggerBy; }
        if (trailingStop) params.trailingStop = trailingStop.toString();

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

    // --- WebSocket Connection and Data Handling ---
    connectWebSocket(symbol, interval) {
        if (this.wsConnected) {
            logger.info("WebSocket already connected.");
            return;
        }

        logger.info(`Connecting WebSocket for ${symbol} ${interval}min klines...`);
        this.wsClient.subscribeV5(`kline.${interval}.${symbol}`, this.category);

        this.wsClient.on('open', () => {
            this.wsConnected = true;
            logger.success("WebSocket connection established.");
        });

        this.wsClient.on('update', (data) => {
            if (data.topic === `kline.${interval}.${symbol}` && data.data && data.data.length > 0) {
                const newKline = data.data[0]; // Assuming one kline per update for simplicity
                // Only process if the kline is closed (confirm = true)
                if (newKline.confirm) {
                    const formattedKline = {
                        time: parseInt(newKline.start),
                        open: new Decimal(newKline.open),
                        high: new Decimal(newKline.high),
                        low: new Decimal(newKline.low),
                        close: new Decimal(newKline.close),
                        volume: new Decimal(newKline.volume),
                    };
                    // Add or update the kline in our local store
                    const existingIndex = this.klinesData.findIndex(k => k.time === formattedKline.time);
                    if (existingIndex !== -1) {
                        this.klinesData[existingIndex] = formattedKline;
                        logger.debug(`Updated kline for ${symbol} at ${new Date(formattedKline.time).toLocaleTimeString()}`);
                    } else {
                        this.klinesData.push(formattedKline);
                        this.klinesData.sort((a, b) => a.time - b.time); // Keep sorted
                        // Keep klinesData to a reasonable size, e.g., last 200 bars
                        if (this.klinesData.length > 200) {
                            this.klinesData.shift();
                        }
                        logger.debug(`Added new kline for ${symbol} at ${new Date(formattedKline.time).toLocaleTimeString()}`);
                    }
                }
            }
        });

        this.wsClient.on('close', () => {
            this.wsConnected = false;
            logger.warn("WebSocket connection closed. Attempting to reconnect...");
            // Implement reconnection logic if needed
            setTimeout(() => this.connectWebSocket(symbol, interval), 5000); // Reconnect after 5 seconds
        });

        this.wsClient.on('error', (err) => {
            logger.error(`WebSocket error: ${err.message}`);
            this.wsConnected = false;
        });
    }
}

// --- Indicator Calculator ---
class IndicatorCalculator {
    constructor(klines) {
        this.klines = klines; // Array of kline objects (with Decimal values)
    }

    // Simple Moving Average (SMA)
    calculateSMA(period) {
        if (this.klines.length < period) return new Decimal(NaN);
        const closes = this.klines.slice(-period).map(k => k.close);
        const sum = closes.reduce((acc, val) => acc.plus(val), new Decimal(0));
        return sum.dividedBy(period);
    }

    // Relative Strength Index (RSI)
    calculateRSI(period) {
        if (this.klines.length < period + 1) return new Decimal(NaN);

        const closes = this.klines.map(k => k.close);
        let gains = new Decimal(0);
        let losses = new Decimal(0);

        // Calculate initial average gain and loss
        for (let i = 1; i <= period; i++) {
            const change = closes[i].minus(closes[i - 1]);
            if (change.gt(0)) {
                gains = gains.plus(change);
            } else {
                losses = losses.plus(change.abs());
            }
        }
        let avgGain = gains.dividedBy(period);
        let avgLoss = losses.dividedBy(period);

        // Calculate subsequent average gain and loss using Wilder's smoothing method
        for (let i = period + 1; i < closes.length; i++) {
            const change = closes[i].minus(closes[i - 1]);
            if (change.gt(0)) {
                avgGain = (avgGain.times(period - 1).plus(change)).dividedBy(period);
                avgLoss = (avgLoss.times(period - 1)).dividedBy(period);
            } else {
                avgLoss = (avgLoss.times(period - 1).plus(change.abs())).dividedBy(period);
                avgGain = (avgGain.times(period - 1)).dividedBy(period);
            }
        }

        if (avgLoss.eq(0)) return new Decimal(100); // No losses, RSI is 100
        const rs = avgGain.dividedBy(avgLoss);
        return new Decimal(100).minus(new Decimal(100).dividedBy(new Decimal(1).plus(rs)));
    }

    // You can add more indicator calculations here (e.g., EMA, MACD, Bollinger Bands)
}

// --- Bot Logic ---
async function generateSignal(bybitClient, indicatorCalculator) {
    // Ensure we have enough klines for indicator calculation
    if (bybitClient.klinesData.length < Math.max(RSI_PERIOD, SMA_LONG_PERIOD) + 1) {
        logger.warn("Not enough klines for reliable signal generation.");
        return 'HOLD';
    }

    const latestKline = bybitClient.klinesData[bybitClient.klinesData.length - 1];
    const currentPrice = latestKline.close;

    const rsi = indicatorCalculator.calculateRSI(RSI_PERIOD);
    const smaShort = indicatorCalculator.calculateSMA(SMA_SHORT_PERIOD);
    const smaLong = indicatorCalculator.calculateSMA(SMA_LONG_PERIOD);

    logger.debug(`Current Price: ${currentPrice.toFixed(2)} | RSI(${RSI_PERIOD}): ${rsi.toFixed(2)} | SMA(${SMA_SHORT_PERIOD}): ${smaShort.toFixed(2)} | SMA(${SMA_LONG_PERIOD}): ${smaLong.toFixed(2)}`);

    // Example Strategy: RSI + SMA Crossover
    // Buy Signal: RSI is oversold (<30) AND short SMA crosses above long SMA
    // Sell Signal: RSI is overbought (>70) AND short SMA crosses below long SMA

    const prevSmaShort = indicatorCalculator.calculateSMA(SMA_SHORT_PERIOD, bybitClient.klinesData.slice(0, -1));
    const prevSmaLong = indicatorCalculator.calculateSMA(SMA_LONG_PERIOD, bybitClient.klinesData.slice(0, -1));

    const isRSIOversold = rsi.lt(30);
    const isRSIOverbought = rsi.gt(70);

    const smaCrossUp = smaShort.gt(smaLong) && prevSmaShort.lte(prevSmaLong); // Short SMA crosses above Long SMA
    const smaCrossDown = smaShort.lt(smaLong) && prevSmaShort.gte(prevSmaLong); // Short SMA crosses below Long SMA

    if (isRSIOversold && smaCrossUp) {
        logger.info(chalk.green("BUY Signal: RSI Oversold and SMA Crossover Up!"));
        return 'BUY';
    } else if (isRSIOverbought && smaCrossDown) {
        logger.info(chalk.red("SELL Signal: RSI Overbought and SMA Crossover Down!"));
        return 'SELL';
    } else {
        return 'HOLD';
    }
}

async function executeTrade(bybit, signal, currentPrice, balance) {
    const tradeAmount = balance.times(0.01); // Example: Risk 1% of balance
    const qty = tradeAmount.dividedBy(currentPrice); // Calculate quantity based on current price

    // Ensure quantity is positive and reasonable
    if (qty.lte(0.00001)) { // Adjust minimum quantity as per exchange rules
        logger.warn(`Calculated quantity ${qty.toFixed(5)} is too small. Skipping trade.`);
        return;
    }

    // Example: Place orders with 0.5% TP and 0.2% SL
    const takeProfitPct = new Decimal(0.005);
    const stopLossPct = new Decimal(0.002);

    if (signal === 'BUY') {
        logger.info(`Executing BUY signal for ${SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        const takeProfitPrice = currentPrice.times(new Decimal(1).plus(takeProfitPct));
        const stopLossPrice = currentPrice.times(new Decimal(1).minus(stopLossPct));
        await bybit.placeMarketOrder(SYMBOL, 'Buy', qty, takeProfitPrice, stopLossPrice);
    } else if (signal === 'SELL') {
        logger.info(`Executing SELL signal for ${SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        const takeProfitPrice = currentPrice.times(new Decimal(1).minus(takeProfitPct));
        const stopLossPrice = currentPrice.times(new Decimal(1).plus(stopLossPct));
        await bybit.placeMarketOrder(SYMBOL, 'Sell', qty, takeProfitPrice, stopLossPrice);
    } else {
        logger.info(`No trade executed. Signal: ${signal}`);
    }
}

// --- Main Bot Loop ---
async function main() {
    logger.info(chalk.bold.yellow(`Pyrmethus awakens the Full-Featured Bybit Trading Bot for ${SYMBOL}!`));
    logger.info(`Operating in ${TESTNET ? 'TESTNET' : 'MAINNET'} mode, ${DRY_RUN ? 'DRY RUN' : 'LIVE'} execution.`);

    const bybit = new BybitClient(API_KEY, API_SECRET, TESTNET, DRY_RUN, CATEGORY, ACCOUNT_TYPE);

    // Initial fetch of klines to populate data for indicators
    const initialKlines = await bybit.getKlines(SYMBOL, TIMEFRAME, 200); // Fetch more historical data
    if (initialKlines) {
        bybit.klinesData = initialKlines;
        logger.info(`Loaded ${bybit.klinesData.length} initial klines.`);
    } else {
        logger.critical("Failed to load initial klines. Exiting.");
        process.exit(1);
    }

    // Connect WebSocket for real-time kline updates
    bybit.connectWebSocket(SYMBOL, TIMEFRAME);

    // Wait for WebSocket to connect and receive some data
    while (!bybit.wsConnected || bybit.klinesData.length < Math.max(RSI_PERIOD, SMA_LONG_PERIOD) + 1) {
        logger.info("Waiting for WebSocket connection and sufficient kline data...");
        await sleep(3000); // Wait 3 seconds before re-checking
    }
    logger.success("WebSocket connected and sufficient kline data available.");

    const indicatorCalculator = new IndicatorCalculator(bybit.klinesData);

    while (true) {
        try {
            // Ensure klinesData is up-to-date from WebSocket
            // Indicator calculations will use the latest klinesData directly
            indicatorCalculator.klines = bybit.klinesData; // Update the klines reference

            const balance = await bybit.getWalletBalance();
            if (balance === null) {
                logger.error("Failed to get wallet balance. Retrying...");
                await sleep(LOOP_INTERVAL_MS);
                continue;
            }
            logger.info(`Current balance: ${balance.toFixed(2)} USDT`);

            const signal = await generateSignal(bybit, indicatorCalculator);
            logger.info(`Generated signal: ${signal}`);

            // Only execute trade if we have a valid signal and sufficient klines
            if (signal !== 'HOLD' && bybit.klinesData.length >= Math.max(RSI_PERIOD, SMA_LONG_PERIOD) + 1) {
                const currentPrice = bybit.klinesData[bybit.klinesData.length - 1].close;
                await executeTrade(bybit, signal, currentPrice, balance);
            } else if (signal === 'HOLD') {
                logger.info("Holding position. No trade action.");
            }

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
To run this full-featured bot:
1. Make sure you have Node.js installed.
2. Create a .env file in the same directory with your Bybit API credentials and bot settings:
   BYBIT_API_KEY=YOUR_BYBIT_API_KEY
   BYBIT_API_SECRET=YOUR_BYBIT_API_SECRET
   TESTNET=true        # or false for mainnet
   DRY_RUN=true        # or false for live trading
   SYMBOL=BTCUSDT
   CATEGORY=linear     # or spot, inverse
   ACCOUNT_TYPE=UNIFIED # or CONTRACT, SPOT
   TIMEFRAME=1         # Kline timeframe for WebSocket (e.g., 1, 5, 15, 60)
   LOOP_INTERVAL_MS=5000 # Main loop interval
   RSI_PERIOD=14
   SMA_SHORT_PERIOD=10
   SMA_LONG_PERIOD=30

3. Install dependencies:
   npm install dotenv bybit-api chalk decimal.js

4. Run the bot:
   node bybit_full_featured_bot_template.js

Important Notes:
- Fill in BYBIT_API_KEY and BYBIT_API_SECRET in your .env file.
- Ensure your API key has the necessary permissions for the operations you intend to perform (e.g., Trade, Read Data).
- For live trading (DRY_RUN=false), exercise extreme caution and thoroughly test your strategy in a testnet environment first.
- The `generateSignal` function contains a simple example strategy (RSI + SMA crossover). You will need to replace this with your own, more sophisticated trading logic.
- WebSocket kline updates are used for real-time indicator calculation. The `klinesData` array in `BybitClient` is kept updated by WebSocket messages.
- This template uses `decimal.js` for precise financial calculations. Ensure all price/quantity values are converted to `Decimal` objects before calculations and back to strings for API calls.
*/
