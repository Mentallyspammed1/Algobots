// main.js
import config from './config.js';
import logger from './logger.js';
import BybitClient from './bybitClient.js';
import { generateSignal } from './chandelierExitStrategy.js';
import { executeTrade } from './tradeExecutor.js';

// --- Utility Sleep Function: The Pause Between Breaths ---
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// --- Main Bot Loop: The Eternal Vigil ---
async function main() {
    logger.info(`Pyrmethus awakens the Chandelier Exit Bybit Trading Bot for ${config.SYMBOL}!`);
    logger.info(`Operating in ${config.TESTNET ? 'TESTNET' : 'MAINNET'} mode, ${config.DRY_RUN ? 'DRY RUN' : 'LIVE'} execution.`);
    logger.info(`Chandelier Exit configured with ATR Period: ${config.CE_ATR_PERIOD}, Multiplier: ${config.CE_ATR_MULTIPLIER}`);

    const bybit = new BybitClient();

    process.on('uncaughtException', (err) => {
        logger.critical(`Uncaught Exception: ${err.message}`);
        logger.error(err.stack);
        process.exit(1);
    });

    while (true) {
        try {
            logger.info(`Fetching klines for ${config.SYMBOL} (${config.TIMEFRAME}min)...`);
            const klines = await bybit.getKlines(config.SYMBOL, config.TIMEFRAME, config.CE_ATR_PERIOD * 2);

            if (!klines || klines.length < config.CE_ATR_PERIOD * 2) {
                logger.warn("Not enough klines for Chandelier Exit calculation. Waiting for more data...");
                await sleep(config.LOOP_INTERVAL_MS);
                continue;
            }

            const currentPrice = klines[klines.length - 1].close;
            logger.info(`Current price for ${config.SYMBOL}: ${currentPrice}`);

            const balance = await bybit.getWalletBalance();
            if (balance === null) {
                logger.error("Failed to get wallet balance. Retrying...");
                await sleep(config.LOOP_INTERVAL_MS);
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

        logger.info(`Sleeping for ${config.LOOP_INTERVAL_MS / 1000} seconds...`);
        await sleep(config.LOOP_INTERVAL_MS);
    }
}

if (import.meta.url === `file://${process.argv[1]}`) {
    main().catch(err => {
        logger.critical(`Bot terminated due to a fatal error: ${err.message}`);
        logger.error(err.stack);
        process.exit(1);
    });
}
