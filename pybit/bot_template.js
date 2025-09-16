// -----------------------------------------------------------------------------
// Bybit Trading Bot Template in Node.js
//
// This template provides a basic framework for creating a Bybit trading bot.
// It includes configuration loading, logging, API interaction, and a main
// trading loop.
//
// To use this template:
// 1. Fill in the `calculateIndicators` function with your TA logic.
// 2. Fill in the `generateSignal` function with your trading strategy.
// 3. Create a `config.yaml` file with your settings.
// 4. Set your API keys as environment variables.
// 5. Run `npm install js-yaml @bybit-api/client chalk technicalindicators`.
// 6. Run the bot: `node bot_template.js`
// -----------------------------------------------------------------------------

const { RestClientV5 } = require('@bybit-api/client');
const yaml = require('js-yaml');
const fs = require('fs');
const chalk = require('chalk');
const ta = require('technicalindicators');

// --- 1. Logger ---
// A simple logger for formatted, colored console output.
const logger = {
    info: (msg) => console.log(chalk.white(`[INFO] ${msg}`)),
    debug: (msg) => console.log(chalk.cyan(`[DEBUG] ${msg}`)),
    warning: (msg) => console.log(chalk.yellow(`[WARN] ${msg}`)),
    error: (msg) => console.log(chalk.red(`[ERROR] ${msg}`)),
    success: (msg) => console.log(chalk.green(`[SUCCESS] ${msg}`)),
};

// --- 2. Configuration Loading ---
// Loads settings from `config.yaml` and API keys from environment variables.
function loadConfig(configPath = 'config.yaml') {
    try {
        const fileContents = fs.readFileSync(configPath, 'utf8');
        const config = yaml.load(fileContents);
        logger.success(`Configuration loaded from ${configPath}`);

        // Load API keys from environment variables
        config.api.key = process.env.BYBIT_API_KEY;
        config.api.secret = process.env.BYBIT_API_SECRET;

        // Enforce dry run if keys are missing
        if (!config.api.key || !config.api.secret) {
            logger.warning('API keys not found in environment. Enforcing dry run mode.');
            config.api.dry_run = true;
        }
        return config;
    } catch (e) {
        logger.error(`Could not load or parse ${configPath}: ${e}`);
        process.exit(1);
    }
}

const CONFIG = loadConfig('./bot/config.yaml');

// --- 3. Bybit API Client ---
// A wrapper class for the Bybit API client to handle requests and dry runs.
class BybitClient {
    constructor(config) {
        this.dry_run = config.api.dry_run;
        this.client = null;

        if (!this.dry_run) {
            this.client = new RestClientV5({
                key: config.api.key,
                secret: config.api.secret,
                testnet: config.api.testnet,
            });
            logger.info(`Bybit client initialized for ${config.api.testnet ? 'Testnet' : 'Mainnet'}.`);
        } else {
            logger.info('Bybit client is in DRY RUN mode. No real orders will be placed.');
        }
    }

    async getKline(params) {
        if (this.dry_run) {
            // In a real dry run, you might want to fetch data from a file or a different source.
            // For this template, we'll still fetch real data but won't trade on it.
            const realClient = new RestClientV5({ testnet: CONFIG.api.testnet });
            return realClient.getKline(params);
        }
        return this.client.getKline(params);
    }

    async getWalletBalance(params) {
        if (this.dry_run) return { retCode: 0, result: { list: [{ coin: [{ coin: 'USDT', walletBalance: '10000' }] }] } };
        return this.client.getWalletBalance(params);
    }

    async getPositions(params) {
        if (this.dry_run) return { retCode: 0, result: { list: [] } };
        return this.client.getPositions(params);
    }

    async getInstrumentsInfo(params) {
        if (this.dry_run) return { retCode: 0, result: { list: [{ priceFilter: { tickSize: '0.01' }, lotSizeFilter: { qtyStep: '0.001' } }] } };
        const realClient = new RestClientV5({ testnet: CONFIG.api.testnet });
        return realClient.getInstrumentsInfo(params);
    }

    async placeOrder(params) {
        if (this.dry_run) {
            const orderId = `DRY_RUN_${Date.now()}`;
            logger.success(`[DRY RUN] Would place order: ${JSON.stringify(params)}. Simulated Order ID: ${orderId}`);
            return { retCode: 0, result: { orderId } };
        }
        return this.client.submitOrder(params);
    }
}

// --- 4. Indicator Calculation ---
// Populates the DataFrame with various technical indicators.
function calculateIndicators(klines) {
    const closePrices = klines.map(k => k.close);

    // Example: Calculate a 14-period RSI
    const rsiInput = { values: closePrices, period: 14 };
    const rsi = ta.RSI.calculate(rsiInput);

    // Example: Calculate a 20-period SMA
    const smaInput = { values: closePrices, period: 20 };
    const sma = ta.SMA.calculate(smaInput);

    // MACD
    const macdInput = { 
        values: closePrices, 
        fastPeriod: 12, 
        slowPeriod: 26, 
        signalPeriod: 9, 
        SimpleMAOscillator: false, 
        SimpleMASignal: false
    };
    const macd = ta.MACD.calculate(macdInput);

    // Bollinger Bands
    const bbInput = { period: 20, values: closePrices, stdDev: 2 };
    const bb = ta.BollingerBands.calculate(bbInput);

    // Combine indicators with klines data
    // Note: Indicator arrays might be shorter than klines array.
    const df = klines.map((k, i) => {
        const rsiOffset = klines.length - rsi.length;
        const smaOffset = klines.length - sma.length;
        const macdOffset = klines.length - macd.length;
        const bbOffset = klines.length - bb.length;
        return {
            ...k,
            rsi: i >= rsiOffset ? rsi[i - rsiOffset] : null,
            sma: i >= smaOffset ? sma[i - smaOffset] : null,
            macd: i >= macdOffset ? macd[i - macdOffset] : null,
            bb: i >= bbOffset ? bb[i - bbOffset] : null,
        };
    });

    return df;
}

// --- 5. Signal Generation ---
// Generates a trading signal based on the calculated indicators.
function generateSignal(df) {
    const last = df[df.length - 1];
    const prev = df[df.length - 2];

    let signal = 'none';
    let sl_price = null;
    let tp_price = null;
    let reasoning = 'No condition met';

    // Example Strategy: RSI crossover
    // Buy when RSI crosses above 30
    if (prev.rsi <= 30 && last.rsi > 30) {
        signal = 'Buy';
        sl_price = last.close * 0.98; // 2% stop loss
        tp_price = last.close * 1.04; // 4% take profit
        reasoning = `RSI crossed above 30 (${last.rsi.toFixed(2)})`;
    }
    // Sell when RSI crosses below 70
    else if (prev.rsi >= 70 && last.rsi < 70) {
        signal = 'Sell';
        sl_price = last.close * 1.02; // 2% stop loss
        tp_price = last.close * 0.96; // 4% take profit
        reasoning = `RSI crossed below 70 (${last.rsi.toFixed(2)})`;
    }

    return { signal, sl_price, tp_price, reasoning };
}

// --- 6. Main Bot Loop ---
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function main() {
    logger.info(chalk.bold.yellow('--- Bybit Bot Template Starting ---'));
    const bybit = new BybitClient(CONFIG);

    while (true) {
        try {
            // --- Check Balance and Positions ---
            const balanceRes = await bybit.getWalletBalance({ accountType: 'UNIFIED' });
            if (balanceRes.retCode !== 0) {
                logger.error(`Could not get balance: ${balanceRes.retMsg}`);
                await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
                continue;
            }
            const balance = parseFloat(balanceRes.result.list[0].coin.find(c => c.coin === 'USDT').walletBalance);
            logger.info(`Current Balance: ${balance.toFixed(2)} USDT`);

            const positionsRes = await bybit.getPositions({ category: 'linear', settleCoin: 'USDT' });
            const openPositions = positionsRes.result.list.filter(p => parseFloat(p.size) > 0);
            logger.info(`Open Positions: ${openPositions.length}`);

            if (openPositions.length >= CONFIG.trading.max_positions) {
                logger.warning(`Max positions reached (${CONFIG.trading.max_positions}). Skipping new entries.`);
                await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
                continue;
            }

            // --- Iterate Through Symbols and Generate Signals ---
            for (const symbol of CONFIG.trading.trading_symbols) {
                if (openPositions.some(p => p.symbol === symbol)) {
                    logger.debug(`Already in a position for ${symbol}. Skipping.`);
                    continue;
                }

                // 1. Fetch Data
                const klinesRes = await bybit.getKline({
                    category: 'linear',
                    symbol,
                    interval: CONFIG.trading.timeframe,
                    limit: 200 // Fetch enough data for indicators
                });

                if (klinesRes.retCode !== 0 || !klinesRes.result.list || klinesRes.result.list.length === 0) {
                    logger.warning(`Could not fetch klines for ${symbol}: ${klinesRes.retMsg}`);
                    continue;
                }
                const klines = klinesRes.result.list.map(k => ({
                    time: parseInt(k[0]),
                    open: parseFloat(k[1]),
                    high: parseFloat(k[2]),
                    low: parseFloat(k[3]),
                    close: parseFloat(k[4]),
                    volume: parseFloat(k[5]),
                })).sort((a, b) => a.time - b.time);

                // 2. Calculate Indicators
                const df = calculateIndicators(klines);
                const last = df[df.length - 1];
                logger.debug(`[${symbol}] Current Price: ${last.close.toFixed(4)}, RSI: ${last.rsi ? last.rsi.toFixed(2) : 'N/A'}`);

                // 3. Generate Signal
                const { signal, sl_price, tp_price, reasoning } = generateSignal(df);

                if (signal !== 'none') {
                    logger.success(`Signal for ${symbol}: ${signal} | Reason: ${reasoning}`);

                    // 4. Place Order
                    const infoRes = await bybit.getInstrumentsInfo({ category: 'linear', symbol });
                    const info = infoRes.result.list[0];
                    const pricePrecision = info.priceFilter.tickSize.split('.')[1]?.length || 0;
                    const qtyPrecision = info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0;


                    const orderQty = (CONFIG.risk_management.order_qty_usdt / last.close).toFixed(qtyPrecision);

                    if (parseFloat(orderQty) > 0) {
                        const orderParams = {
                            category: 'linear',
                            symbol,
                            side: signal,
                            orderType: 'Market',
                            qty: orderQty,
                            takeProfit: tp_price.toFixed(pricePrecision),
                            stopLoss: sl_price.toFixed(pricePrecision),
                        };
                        await bybit.placeOrder(orderParams);
                    } else {
                        logger.warning(`Calculated order quantity for ${symbol} is zero. Skipping.`);
                    }
                }
            }
        } catch (e) {
            logger.error(`An error occurred in the main loop: ${e.message}`);
        }

        logger.info(`--- Cycle finished. Waiting ${CONFIG.bot.loop_wait_time_seconds} seconds. ---`);
        await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
    }
}

main().catch(err => logger.error(`Bot crashed: ${err.stack}`));
