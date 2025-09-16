
const { BybitIndicatorModule } = require('./indicators.js');


const colors = {
    GREEN: '\x1b[32m',
    RED: '\x1b[31m',
    YELLOW: '\x1b[33m',
    BLUE: '\x1b[34m',
    MAGENTA: '\x1b[35m',
    CYAN: '\x1b[36m',
    WHITE: '\x1b[37m',
    RESET: '\x1b[0m',
    BOLD: '\x1b[1m',
    LIGHTYELLOW_EX: '\x1b[93m',
    LIGHTGREEN_EX: '\x1b[92m',
    LIGHTCYAN_EX: '\x1b[96m'
};

class Logger {
    constructor() {
        this.level = 'INFO';
        this.isTTY = process.stdout.isTTY;
    }

    setLevel(level) {
        this.level = level.toUpperCase();
    }

    _log(level, message, color = colors.WHITE) {
        const timestamp = DateTime.local().toFormat('yyyy-MM-dd HH:mm:ss');
        const levelName = level.toUpperCase();

        const levels = {
            'DEBUG': 0,
            'INFO': 1,
            'WARNING': 2,
            'ERROR': 3,
            'CRITICAL': 4
        };

        if (levels[levelName] < levels[this.level]) {
            return;
        }

        let formattedMessage;
        if (this.isTTY) {
            formattedMessage = `${color}${timestamp} - BOT - ${levelName} - ${message}${colors.RESET}`;
        } else {
            formattedMessage = `${timestamp} - BOT - ${levelName} - ${message}`;
        }
        console.log(formattedMessage);
    }

    debug(message) { this._log('DEBUG', message, colors.CYAN); }
    info(message) { this._log('INFO', message, colors.WHITE); }
    warning(message) { this._log('WARNING', message, colors.YELLOW); }
    error(message) { this._log('ERROR', message, colors.RED); }
    critical(message) { this._log('CRITICAL', message, colors.BOLD + colors.RED); }
}

const logger = new Logger();

function loadConfig(configPath = "config.yaml") {
    let config;
    try {
        const fileContents = fs.readFileSync(configPath, 'utf8');
        config = yaml.load(fileContents);
        logger.info(`${colors.GREEN}Successfully summoned configuration from ${configPath}.${colors.RESET}`);
    } catch (e) {
        if (e.code === 'ENOENT') {
            logger.error(`${colors.RED}The arcane grimoire 'config.yaml' was not found. The ritual cannot proceed.${colors.RESET}`);
        } else {
            logger.error(`${colors.RED}The 'config.yaml' grimoire is corrupted: ${e}. The ritual is halted.${colors.RESET}`);
        }
        process.exit(1);
    }

    const apiKey = process.env.BYBIT_API_KEY;
    const apiSecret = process.env.BYBIT_API_SECRET;

    if (!apiKey || !apiSecret) {
        logger.warning(`${colors.YELLOW}BYBIT_API_KEY or BYBIT_API_SECRET not found in the environment. Dry run is enforced.${colors.RESET}`);
        config.api.dry_run = true;
    }

    config.api.key = apiKey;
    config.api.secret = apiSecret;

    return config;
}

const CONFIG = loadConfig();
logger.setLevel(CONFIG.bot.log_level.toUpperCase());



let indicatorModule;
try {
    indicatorModule = new BybitIndicatorModule(
        CONFIG.api.key,
        CONFIG.api.secret,
    );
    const modeInfo = CONFIG.api.dry_run ? `${colors.MAGENTA}${colors.BOLD}DRY RUN${colors.RESET}` : `${colors.GREEN}${colors.BOLD}LIVE${colors.RESET}`;
    const testnetInfo = CONFIG.api.testnet ? `${colors.YELLOW}TESTNET${colors.RESET}` : `${colors.BLUE}MAINNET${colors.RESET}`;
    logger.info(`${colors.LIGHTYELLOW_EX}Successfully connected to Bybit API in ${modeInfo} mode on ${testnetInfo}.${colors.RESET}`);
    logger.debug(`${colors.CYAN}Bot configuration: ${JSON.stringify(CONFIG)}${colors.RESET}`);
} catch (e) {
    logger.error(`${colors.RED}Failed to connect to Bybit API: ${e.message}${colors.RESET}`);
    process.exit(1);
}

async function timeout(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getCurrentTime(timezoneStr) {
    try {
        const localTime = DateTime.local().setZone(timezoneStr);
        const utcTime = DateTime.utc();
        if (!localTime.isValid) {
             logger.error(`${colors.RED}Unknown timezone: '${timezoneStr}'. Defaulting to UTC.${colors.RESET}`);
             return [DateTime.utc(), DateTime.utc()];
        }
        return [localTime, utcTime];
    } catch (e) {
        logger.error(`${colors.RED}Exception getting current time with timezone '${timezoneStr}': ${e.message}. Defaulting to UTC.${colors.RESET}`);
        return [DateTime.utc(), DateTime.utc()];
    }
}

function isMarketOpen(localTime, openHour, closeHour) {
    const currentHour = localTime.hour;
    const openHourInt = parseInt(openHour);
    const closeHourInt = parseInt(closeHour);
    if (openHourInt < closeHourInt) {
        return currentHour >= openHourInt && currentHour < closeHourInt;
    } else {
        return currentHour >= openHourInt || currentHour < closeHourInt;
    }
}

function sendTermuxToast(message) {
    if (process.platform === 'linux' && process.env.TERMUX_VERSION) {
        try {
            const { spawnSync } = require('child_process');
            spawnSync('termux-toast', [message], { stdio: 'inherit' });
        } catch (e) {
            logger.warning(`${colors.YELLOW}Could not send Termux toast: ${e.message}${colors.RESET}`);
        }
    }
}

function calculatePnl(side, entryPrice, exitPrice, qty) {
    return side === 'Buy' ? (exitPrice - entryPrice) * qty : (entryPrice - exitPrice) * qty;
}

async function main() {
    console.log(`${colors.LIGHTYELLOW_EX}${colors.BOLD}Pyrmethus awakens the Ehlers Supertrend Cross Strategy!${colors.RESET}`);
    
    const symbols = CONFIG.trading.trading_symbols;
    if (!symbols || symbols.length === 0) {
        logger.info(`${colors.YELLOW}No symbols in config.yaml. Exiting.${colors.RESET}`);
        return;
    }

    const activeTrades = {};
    let cumulativePnl = 0.0;

    while (true) {
        const [localTime, utcTime] = getCurrentTime(CONFIG.bot.timezone);
        logger.info(`${colors.WHITE}Local: ${localTime.toFormat('yyyy-MM-dd HH:mm:ss')} | UTC: ${utcTime.toFormat('yyyy-MM-dd HH:mm:ss')}${colors.RESET}`);

        if (!isMarketOpen(localTime, CONFIG.bot.market_open_hour, CONFIG.bot.market_close_hour)) {
            logger.info(`${colors.YELLOW}Market closed. Waiting...${colors.RESET}`);
            await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }
            
        const balanceRes = await indicatorModule.exchange.fetchBalance();
        const balance = balanceRes.total.USDT;
        if (!balance) {
            logger.error(`${colors.RED}Cannot get balance. Retrying...${colors.RESET}`);
            await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }
        
        logger.info(`${colors.LIGHTGREEN_EX}Balance: ${balance.toFixed(2)} USDT${colors.RESET}`);
        const currentPositions = await indicatorModule.exchange.fetchPositions();
        const openPositions = currentPositions.filter(p => p.info.size > 0);
        logger.info(`${colors.LIGHTCYAN_EX}${openPositions.length} open positions: ${openPositions.map(p=>p.symbol).join(', ')}${colors.RESET}`);

        for (const symbol of symbols) {
            indicatorModule.symbol = symbol;
            if (openPositions.length >= CONFIG.trading.max_positions) {
                logger.info(`${colors.YELLOW}Max positions reached. No new trades.${colors.RESET}`);
                break;
            }
            if (openPositions.some(p => p.symbol === symbol)) {
                continue;
            }

            const klines = await indicatorModule.fetchOHLCV(CONFIG.trading.min_klines_for_strategy + 5);
            if (!klines || klines.length === 0) {
                logger.warning(`${colors.YELLOW}Not enough kline data for ${symbol}. Skipping.${colors.RESET}`);
                continue;
            }
            
            const currentPrice = klines[klines.length - 1].close;
            const { pricePrecision, qtyPrecision } = await indicatorModule.exchange.loadMarkets().then(m => ({
                pricePrecision: m[symbol].precision.price,
                qtyPrecision: m[symbol].precision.amount
            }));
            
            const [signal, risk, tp, sl, dfIndicators, volConfirm] = generateEhlSupertrendSignals(klines, currentPrice, pricePrecision, qtyPrecision);

            if (dfIndicators && dfIndicators.length > 1) {
                const lastRow = dfIndicators[dfIndicators.length - 1];
                const logMsg = (
                    `[${symbol}] ` +
                    `Price: ${colors.WHITE}${currentPrice.toFixed(4)}${colors.RESET} | ` +
                    `SlowST: ${colors.CYAN}${lastRow.st_slow_line.toFixed(4)} (${lastRow.st_slow_direction > 0 ? 'Up' : 'Down'})${colors.RESET} | ` +
                    `FastST: ${colors.CYAN}${lastRow.st_fast_line.toFixed(4)}${colors.RESET} | ` +
                    `RSI: ${colors.YELLOW}${lastRow.rsi.toFixed(2)}${colors.RESET} | ` +
                    `Fisher: ${colors.MAGENTA}${lastRow.fisher.toFixed(2)} (Sig: ${lastRow.fisher_signal.toFixed(2)})${colors.RESET} | ` +
                    `VolSpike: ${(volConfirm ? colors.GREEN : colors.RED)}${volConfirm ? 'Yes' : 'No'}${colors.RESET}`
                );
                logger.info(logMsg);
            } else {
                logger.warning(`[${symbol}] Could not generate indicator data for logging.`);
            }

            if (signal !== 'none' && risk !== null && risk > 0) {
                const reasoning = [];
                const lastRow = dfIndicators[dfIndicators.length - 1];
                if (signal === 'Buy') {
                    reasoning.push("SlowST is Up");
                    reasoning.push("FastST crossed above SlowST");
                    const confirmations = [];
                    if (lastRow.fisher > lastRow.fisher_signal) confirmations.push("Fisher");
                    if (CONFIG.strategy.rsi.confirm_long_threshold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.overbought) confirmations.push("RSI");
                    if (volConfirm) confirmations.push("Volume");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                } else {
                    reasoning.push("SlowST is Down");
                    reasoning.push("FastST crossed below SlowST");
                    const confirmations = [];
                    if (lastRow.fisher < lastRow.fisher_signal) confirmations.push("Fisher");
                    if (CONFIG.strategy.rsi.oversold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.confirm_short_threshold) confirmations.push("RSI");
                    if (volConfirm) confirmations.push("Volume");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                }

                logger.info(`${(signal === 'Buy' ? colors.GREEN : colors.RED)}${colors.BOLD}${signal.toUpperCase()} SIGNAL for ${symbol} at ${currentPrice.toFixed(4)} | TP: ${tp.toFixed(4)}, SL: ${sl.toFixed(4)} | Reason: ${reasoning.join('; ')}${colors.RESET}`);
                
                const riskAmountUsdt = balance * CONFIG.risk_management.risk_per_trade_pct;
                let orderQty = Math.min(riskAmountUsdt / risk, CONFIG.risk_management.order_qty_usdt / currentPrice);
                orderQty = parseFloat(orderQty.toFixed(qtyPrecision));

                if (orderQty > 0) {
                    // Order placement logic would be here, using indicatorModule.exchange
                    logger.info(`[DRY RUN] Would place market ${signal} order for ${orderQty} ${symbol}`);
                    activeTrades[symbol] = { entry_time: utcTime.toISO(), side: signal, entry_price: currentPrice, qty: orderQty, sl: sl, tp: tp };
                    sendTermuxToast(`${signal.toUpperCase()} Signal: ${symbol}`);
                }
            } else {
                logger.debug(`[${symbol}] No signal generated on this candle.`);
            }
        }
        
        await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
    }
}

if (require.main === module) {
    main().catch(err => {
        logger.critical(`Unhandled error in main loop: ${err.message}`);
        console.error(err);
        process.exit(1);
    });
}
