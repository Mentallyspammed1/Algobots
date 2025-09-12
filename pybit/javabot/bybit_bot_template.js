
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

// --- Bybit API Client Wrapper ---
class BybitClient {
    constructor(apiKey, apiSecret, testnet, dryRun) {
        this.dryRun = dryRun;
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
        logger.info(`Bybit client initialized. Testnet: ${testnet}, Dry Run: ${dryRun}`);
    }

    async getKlines(symbol, interval, limit) {
        if (this.dryRun) {
            logger.debug(`[DRY RUN] Simulating kline fetch for ${symbol} ${interval}min`);
            // Return dummy data for dry run
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
                category: 'linear',
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
                })).sort((a, b) => a.time - b.time); // Ensure ascending order
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
                accountType: 'UNIFIED',
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

    async placeOrder(symbol, side, qty, price = null, orderType = 'Market', takeProfit = null, stopLoss = null) {
        if (this.dryRun) {
            logger.info(chalk.magenta(`[DRY RUN] Would place ${orderType} ${side} order for ${qty} ${symbol} at ${price || 'market'}`));
            return { orderId: `DRY_ORDER_${Date.now()}`, status: 'FILLED' };
        }
        try {
            const params = {
                category: 'linear',
                symbol,
                side,
                orderType,
                qty: String(qty),
                timeInForce: 'GTC', // Good Till Cancel
            };
            if (price) params.price = String(price);
            if (takeProfit) {
                params.takeProfit = String(takeProfit);
                params.tpTriggerBy = 'MarkPrice'; // Or LastPrice, IndexPrice
            }
            if (stopLoss) {
                params.stopLoss = String(stopLoss);
                params.slTriggerBy = 'MarkPrice'; // Or LastPrice, IndexPrice
            }

            const response = await this.restClient.submitOrder(params);
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

    // You can add more API methods here (e.g., cancelOrder, getPositions, etc.)
    // For WebSocket, you can subscribe to topics:
    // subscribeToKline(symbol, interval, callback) {
    //     this.wsClient.subscribeV5(`kline.${interval}.${symbol}`, 'linear');
    //     this.wsClient.on('update', (data) => {
    //         if (data.topic === `kline.${interval}.${symbol}`) {
    //             callback(data.data);
    //         }
    //     });
    // }
}

// --- Bot Logic ---
async function generateSignal(klines) {
    // This is a placeholder for your trading strategy.
    // Analyze klines and other market data to decide whether to BUY, SELL, or HOLD.
    // Example: Simple moving average crossover
    if (!klines || klines.length < 20) {
        logger.warn("Not enough klines for signal generation.");
        return 'HOLD';
    }

    const lastClose = klines[klines.length - 1].close;
    const prevClose = klines[klines.length - 2].close;

    // Very basic example: Buy if price increased, Sell if price decreased
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
        await bybit.placeOrder(SYMBOL, 'Buy', qty, currentPrice);
    } else if (signal === 'SELL') {
        logger.info(`Executing SELL signal for ${SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        await bybit.placeOrder(SYMBOL, 'Sell', qty, currentPrice);
    } else {
        logger.info(`No trade executed. Signal: ${signal}`);
    }
}

// --- Main Bot Loop ---
async function main() {
    logger.info(chalk.bold.yellow(`Pyrmethus awakens the Bybit Trading Bot for ${SYMBOL}!`));
    logger.info(`Operating in ${TESTNET ? 'TESTNET' : 'MAINNET'} mode, ${DRY_RUN ? 'DRY RUN' : 'LIVE'} execution.`);

    const bybit = new BybitClient(API_KEY, API_SECRET, TESTNET, DRY_RUN);

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
    // Check for required environment variables
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
To run this bot:
1. Make sure you have Node.js installed.
2. Create a .env file in the same directory with your Bybit API credentials:
   BYBIT_API_KEY=
   BYBIT_API_SECRET=
   TESTNET=true  # or false for mainnet
   DRY_RUN=true  # or false for live trading
   SYMBOL=BTCUSDT
   TIMEFRAME=5
   LOOP_INTERVAL_MS=10000

3. Install dependencies:
   npm install dotenv bybit-api chalk

4. Run the bot:
   node bybit_bot_template.js
*/
