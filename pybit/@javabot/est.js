const yaml = require('js-yaml');
const fs = require('fs');
const chalk = require('chalk');
const { BybitIndicatorModule } = require('./indicators.js');

// --- Logger with Chalk ---
const logger = {
    info: (msg) => console.log(chalk.white(msg)),
    debug: (msg) => console.log(chalk.cyan(msg)),
    warning: (msg) => console.log(chalk.yellow(msg)),
    error: (msg) => console.log(chalk.red(msg)),
    critical: (msg) => console.log(chalk.bold.red(msg)),
    success: (msg) => console.log(chalk.green(msg)),
    magenta: (msg) => console.log(chalk.magenta(msg)),
}; 

// --- Configuration Loading ---
function loadConfig(configPath = 'config.yaml') {
    try {
        const fileContents = fs.readFileSync(configPath, 'utf8');
        const config = yaml.load(fileContents);
        logger.success(`Successfully summoned configuration from ${configPath}`);
        
        config.api.key = process.env.BYBIT_API_KEY;
        config.api.secret = process.env.BYBIT_API_SECRET;

        if (!config.api.key || !config.api.secret) {
            logger.warning('BYBIT_API_KEY or BYBIT_API_SECRET not found in environment. Dry run is enforced.');
            config.api.dry_run = true;
        }
        return config;
    } catch (e) {
        logger.critical(`Could not load or parse ${configPath}: ${e}`);
        process.exit(1);
    }
}

const CONFIG = loadConfig();

// --- Bybit Client Class ---
async function main() {
    logger.info(chalk.bold.yellow('Pyrmethus awakens the Ehlers Supertrend Cross Strategy (JS Version)!'));
    
    const indicatorModule = new BybitIndicatorModule(CONFIG.api.key, CONFIG.api.secret, CONFIG.trading.trading_symbols[0], CONFIG.trading.timeframe);

    while (true) {
        try {
            for (const symbol of CONFIG.trading.trading_symbols) {
                indicatorModule.symbol = symbol; // Update symbol for the module

                const balanceRes = await indicatorModule.exchange.fetchBalance();
                const balance = balanceRes.total.USDT;
                logger.success(`Balance: ${balance.toFixed(2)} USDT`);

                const positions = await indicatorModule.exchange.fetchPositions();
                const openPositions = positions.filter(p => p.info.size > 0 && p.symbol === symbol);

                if (openPositions.length > 0) {
                    logger.debug(`Already in a position for ${symbol}. Skipping.`);
                    continue;
                }

                if (openPositions.length >= CONFIG.trading.max_positions) {
                    logger.warning(`Max positions (${CONFIG.trading.max_positions}) reached. Halting new signal checks.`);
                    break;
                }

                const klines = await indicatorModule.fetchOHLCV(200);
                if (klines.length < CONFIG.trading.min_klines_for_strategy) {
                    logger.warning(`Not enough kline data for ${symbol}. Skipping.`);
                    continue;
                }

                const supertrend = await indicatorModule.getSupertrend(CONFIG.strategy.est_slow.length, CONFIG.strategy.est_slow.multiplier);
                const rsi = await indicatorModule.getRSI(CONFIG.strategy.rsi.period);
                const fisher = await indicatorModule.getFisherTransform(CONFIG.strategy.ehlers_fisher.period);

                const { signal, sl_price, tp_price, reasoning } = generateSignals(klines, supertrend, rsi, fisher, CONFIG);
                const last = klines[klines.length - 1];

                const log_msg = `[${symbol}] Price: ${chalk.white(last.close.toFixed(4))} | RSI: ${chalk.yellow(rsi.toFixed(2))}`;
                logger.info(log_msg);

                if (signal !== 'none') {
                    logger.success(`SIGNAL for ${symbol}: ${signal} | Reason: ${reasoning}`);
                    // Order placement logic would go here, using a proper Bybit client.
                }
            }
        } catch (e) {
            logger.error(`An error occurred in the main loop: ${e.message}`);
        }

        logger.info(`--- Cycle finished. Waiting ${CONFIG.bot.loop_wait_time_seconds} seconds. ---`);
        await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
    }
}

main().catch(err => logger.critical(err));
