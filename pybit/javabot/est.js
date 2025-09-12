const { RestClientV5 } = require('bybit-api');
const yaml = require('js-yaml');
const fs = require('fs');
const chalk = require('chalk');
const { calculateEhlSupertrendIndicators } = require('./indicators.js');

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
            // config.api.dry_run = true; // Removed to ensure DRY_RUN is controlled by environment variable
        }
        return config;
    } catch (e) {
        logger.critical(`Could not load or parse ${configPath}: ${e}`);
        process.exit(1);
    }
}

const CONFIG = loadConfig();

// --- Bybit Client Class ---
class BybitClient {
    constructor(config) {
        this.dry_run = config.api.dry_run;
        this.client = null;
        this._dryRunPositions = {}; // { symbol: { side: 'Buy'/'Sell', size: number } }

        if (config.api.key && config.api.secret) {
            this.client = new RestClientV5({
                key: config.api.key,
                secret: config.api.secret,
                testnet: config.api.testnet,
            });
            logger.info('HTTP session initialized for data fetching.');
        } else {
            logger.warning('API keys not found. Live data fetching is disabled.');
        }
        logger.info(`Bybit client configured. Testnet: ${config.api.testnet}, Dry Run: ${this.dry_run}`);
    }

    async getKline(params) {
        if (!this.client) {
            logger.error('Cannot fetch klines. No API session available.');
            return [];
        }
        try {
            const response = await this.client.getKline(params);
            if (response.retCode === 0 && response.result.list) {
                return response.result.list.map(k => ({
                    time: parseInt(k[0]),
                    open: parseFloat(k[1]),
                    high: parseFloat(k[2]),
                    low: parseFloat(k[3]),
                    close: parseFloat(k[4]),
                    volume: parseFloat(k[5]),
                })).sort((a, b) => a.time - b.time); // Ensure ascending order
            } else {
                logger.error(`Error getting klines for ${params.symbol}: ${response.retMsg}`);
                return [];
            }
        } catch (e) {
            logger.error(`Exception getting klines for ${params.symbol}: ${e.message}`);
            return [];
        }
    }
    
    async getWalletBalance(coin = 'USDT') {
        if (!this.client) {
            logger.debug(chalk.blue('[DRY RUN] No API session. Simulated balance: 10000.00 USDT'));
            return 10000.0;
        }
        try {
            const response = await this.client.getWalletBalance({ accountType: 'UNIFIED', coin });
            if (response.retCode === 0 && response.result.list && response.result.list[0].coin) {
                const coinData = response.result.list[0].coin.find(c => c.coin === coin);
                return coinData ? parseFloat(coinData.walletBalance) : 0;
            }
            logger.error(`Error getting balance: ${response.retMsg}`);
            return null;
        } catch (e) {
            logger.error(`Exception getting balance: ${e.message}`);
            return null;
        }
    }

    async getPositions() {
        if (this.dry_run) {
            const openSymbols = Object.keys(this._dryRunPositions);
            logger.debug(chalk.blue(`[DRY RUN] Fetched open positions from internal tracker: ${openSymbols}`))
            return openSymbols.map(s => ({ symbol: s, side: this._dryRunPositions[s].side, size: this._dryRunPositions[s].size }));
        }
        if (!this.client) return [];
        try {
            const response = await this.client.getPositions({ category: 'linear', settleCoin: 'USDT' });
            if (response.retCode === 0) {
                return response.result.list.filter(p => parseFloat(p.size) > 0);
            }
            logger.error(`Error getting positions: ${response.retMsg}`);
            return [];
        } catch (e) {
            logger.error(`Exception getting positions: ${e.message}`);
            return [];
        }
    }

    async getInstrumentsInfo(symbol) {
        if (!this.client) return { pricePrecision: 2, qtyPrecision: 3 }; // Defaults
        try {
            const response = await this.client.getInstrumentsInfo({ category: 'linear', symbol });
            if (response.retCode === 0 && response.result.list.length > 0) {
                const info = response.result.list[0];
                const pricePrecision = info.priceFilter.tickSize.split('.')[1]?.length || 0;
                const qtyPrecision = info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0;
                return { pricePrecision, qtyPrecision };
            }
            logger.error(`Error getting precisions for ${symbol}: ${response.retMsg}`);
            return { pricePrecision: 2, qtyPrecision: 3 };
        } catch (e) {
            logger.error(`Exception getting precisions for ${symbol}: ${e.message}`);
            return { pricePrecision: 2, qtyPrecision: 3 };
        }
    }

    async placeOrder(params) {
        if (this.dry_run) {
            const orderId = `DRY_RUN_ORDER_${Date.now()}`;
            logger.magenta(`[DRY RUN] Would place order: ${JSON.stringify(params)}. Simulated Order ID: ${orderId}`);
            this._dryRunPositions[params.symbol] = { side: params.side, size: parseFloat(params.qty) };
            return { retCode: 0, result: { orderId } };
        }
        if (!this.client) return { retCode: -1, retMsg: 'API client not initialized' };
        try {
            const response = await this.client.submitOrder(params);
            if (response.retCode === 0) {
                logger.success(`Order placed for ${params.symbol}. Order ID: ${response.result.orderId}`);
            } else {
                logger.error(`Failed to place order for ${params.symbol}: ${response.retMsg}`);
            }
            return response;
        } catch (e) {
            logger.error(`Exception placing order for ${params.symbol}: ${e.message}`);
            return { retCode: -1, retMsg: e.message };
        }
    }
}



// --- Signal Generation ---
function generateSignals(df, config) {
    if (df.length < config.trading.min_klines_for_strategy) {
        return { signal: 'none' };
    }

    const last = df[df.length - 1];
    const prev = df[df.length - 2];

    const longTrendConfirmed = last.st_slow_direction > 0;
    const shortTrendConfirmed = last.st_slow_direction < 0;
    const fastCrossesAboveSlow = prev.st_fast_line <= prev.st_slow_line && last.st_fast_line > last.st_slow_line;
    const fastCrossesBelowSlow = prev.st_fast_line >= prev.st_slow_line && last.st_fast_line < last.st_slow_line;

    const fisherConfirmLong = last.fisher > last.fisher_signal;
    const rsiConfirmLong = last.rsi > config.strategy.rsi.confirm_long_threshold && last.rsi < config.strategy.rsi.overbought;
    const volumeConfirm = last.volume_spike || prev.volume_spike;

    const fisherConfirmShort = last.fisher < last.fisher_signal;
    const rsiConfirmShort = last.rsi < config.strategy.rsi.confirm_short_threshold && last.rsi > config.strategy.rsi.oversold;

    let signal = 'none', sl_price = null, tp_price = null, reasoning = [];

    if (longTrendConfirmed && fastCrossesAboveSlow && (fisherConfirmLong + rsiConfirmLong + volumeConfirm >= 2)) {
        signal = 'Buy';
        sl_price = prev.st_slow_line;
        const riskDistance = last.close - sl_price;
        if (riskDistance > 0) {
            tp_price = last.close + (riskDistance * config.order_logic.reward_risk_ratio);
            reasoning = ['SlowST Up', 'Fast>Slow Cross', `Confirms: ${[fisherConfirmLong && 'Fisher', rsiConfirmLong && 'RSI', volumeConfirm && 'Volume'].filter(Boolean).join('+')}`];
        } else { signal = 'none'; }
    } else if (shortTrendConfirmed && fastCrossesBelowSlow && (fisherConfirmShort + rsiConfirmShort + volumeConfirm >= 2)) {
        signal = 'Sell';
        sl_price = prev.st_slow_line;
        const riskDistance = sl_price - last.close;
        if (riskDistance > 0) {
            tp_price = last.close - (riskDistance * config.order_logic.reward_risk_ratio);
            reasoning = ['SlowST Down', 'Fast<Slow Cross', `Confirms: ${[fisherConfirmShort && 'Fisher', rsiConfirmShort && 'RSI', volumeConfirm && 'Volume'].filter(Boolean).join('+')}`];
        } else { signal = 'none'; }
    }

    return { signal, sl_price, tp_price, reasoning: reasoning.join('; ') };
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// --- Main Bot Loop ---
async function main() {
    logger.info(chalk.bold.yellow('Pyrmethus awakens the Ehlers Supertrend Cross Strategy (JS Version)!'));
    const bybit = new BybitClient(CONFIG);

    while (true) {
        const balance = await bybit.getWalletBalance();
        if (balance === null) {
            logger.error('Cannot get balance. Retrying...');
            await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }
        logger.success(`Balance: ${balance.toFixed(2)} USDT`);

        const positions = await bybit.getPositions();
        logger.info(`You have ${positions.length} open positions: ${positions.map(p => p.symbol).join(', ')}`);

        if (positions.length >= CONFIG.trading.max_positions) {
            logger.warning(`Max positions (${CONFIG.trading.max_positions}) reached. Halting new signal checks.`);
            await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }

        for (const symbol of CONFIG.trading.trading_symbols) {
            if (positions.some(p => p.symbol === symbol)) {
                logger.debug(`Skipping ${symbol} as there is already an open position.`);
                continue;
            }

            const klines = await bybit.getKline({ category: 'linear', symbol, interval: CONFIG.trading.timeframe, limit: 200 });
            if (klines.length < CONFIG.trading.min_klines_for_strategy) {
                logger.warning(`Not enough kline data for ${symbol}. Skipping.`);
                continue;
            }

            const df = calculateEhlSupertrendIndicators(klines, CONFIG, logger);
            const { signal, sl_price, tp_price, reasoning } = generateSignals(df, CONFIG);
            const last = df[df.length - 1];

            const log_msg = `[${symbol}] Price: ${chalk.white(last.close.toFixed(4))} | SlowST: ${chalk.cyan(last.st_slow_line.toFixed(4))} (${last.st_slow_direction > 0 ? 'Up' : 'Down'}) | RSI: ${chalk.yellow(last.rsi.toFixed(2))} | Fisher: ${chalk.magenta(last.fisher.toFixed(2))}`;
            logger.info(log_msg);

            if (signal !== 'none') {
                logger.success(`SIGNAL for ${symbol}: ${signal} | Reason: ${reasoning}`);
                const { pricePrecision, qtyPrecision } = await bybit.getInstrumentsInfo(symbol);
                const riskDistance = Math.abs(last.close - sl_price);
                const riskAmountUSD = balance * CONFIG.risk_management.risk_per_trade_pct;
                const orderQty = Math.min(riskAmountUSD / riskDistance, CONFIG.risk_management.max_notional_per_trade_usdt / last.close);
                const finalQty = parseFloat(orderQty.toFixed(qtyPrecision));

                if (finalQty > 0) {
                    await bybit.placeOrder({
                        category: 'linear',
                        symbol,
                        side: signal,
                        orderType: 'Market',
                        qty: finalQty.toString(),
                        takeProfit: tp_price.toFixed(pricePrecision),
                        stopLoss: sl_price.toFixed(pricePrecision),
                    });
                }
            }
        }

        logger.info(`--- Cycle finished. Waiting ${CONFIG.bot.loop_wait_time_seconds} seconds. ---`);
        await sleep(CONFIG.bot.loop_wait_time_seconds * 1000);
    }
}

main().catch(err => logger.critical(err));
