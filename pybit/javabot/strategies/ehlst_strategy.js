import process from 'process';
import { DateTime } from 'luxon';
import { CONFIG } from './config.js';
import { logger, neon } from './logger.js';
import { bybitClient } from './bybit_api_client.js';
import { calculateEhlSupertrendIndicators } from './indicators.js';
import { spawnSync } from 'child_process';

// ====================== 
// CONFIGURATION (now from config.js) 
// ====================== 
const SYMBOL = CONFIG.SYMBOL; // Main symbol for this bot, if single symbol
const TRADING_SYMBOLS = CONFIG.TRADING_SYMBOLS; // For multi-symbol bots
const TIMEFRAME = CONFIG.TIMEFRAME;
const MIN_KLINES_FOR_STRATEGY = CONFIG.MIN_KLINES_FOR_STRATEGY;
const MAX_POSITIONS = CONFIG.MAX_POSITIONS;
const RISK_PER_TRADE_PCT = CONFIG.RISK_PER_TRADE_PCT;
const ORDER_QTY_USDT = CONFIG.ORDER_QTY_USDT; // Used in ehlst.js for order sizing
const LEVERAGE = CONFIG.LEVERAGE;
const MARGIN_MODE = CONFIG.MARGIN_MODE;
const REWARD_RISK_RATIO = CONFIG.REWARD_RISK_RATIO;
const USE_ATR_FOR_TP_SL = CONFIG.USE_ATR_FOR_TP_SL;
const TP_ATR_MULTIPLIER = CONFIG.TP_ATR_MULTIPLIER;
const SL_ATR_MULTIPLIER = CONFIG.SL_ATR_MULTIPLIER;

// ====================== 
// UTILITIES 
// ====================== 
async function timeout(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getCurrentTime(timezoneStr) {
    try {
        const localTime = DateTime.local().setZone(timezoneStr);
        const utcTime = DateTime.utc();
        if (!localTime.isValid) {
             logger.error(neon.error(`Unknown timezone: '${timezoneStr}'. Defaulting to UTC.`));
             return [DateTime.utc(), DateTime.utc()];
        }
        return [localTime, utcTime];
    } catch (e) {
        logger.error(neon.error(`Exception getting current time with timezone '${timezoneStr}': ${e.message}. Defaulting to UTC.`));
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
            spawnSync('termux-toast', [message], { stdio: 'inherit' });
        } catch (e) {
            logger.warn(neon.warn(`Could not send Termux toast: ${e.message}`));
        }
    }
}

function calculatePnl(side, entryPrice, exitPrice, qty) {
    return side === 'Buy' ? (exitPrice - entryPrice) * qty : (entryPrice - exitPrice) * qty;
}

// ====================== 
// SIGNAL GENERATION 
// ====================== 
function generateEhlSupertrendSignals(klines, currentPrice, pricePrecision, qtyPrecision, strategyConfig) { // Added strategyConfig
    logger.debug(`generateEhlSupertrendSignals: Generating signals with config: ${JSON.stringify(strategyConfig)}`);
    // Extract relevant config from strategyConfig or fall back to global CONFIG
    const MIN_KLINES_FOR_STRATEGY = strategyConfig.MIN_KLINES_FOR_STRATEGY || CONFIG.MIN_KLINES_FOR_STRATEGY;
    const RSI_CONFIRM_LONG_THRESHOLD = strategyConfig.RSI_CONFIRM_LONG_THRESHOLD || CONFIG.RSI_CONFIRM_LONG_THRESHOLD;
    const RSI_OVERBOUGHT = strategyConfig.RSI_OVERBOUGHT || CONFIG.RSI_OVERBOUGHT;
    const RSI_OVERSOLD = strategyConfig.RSI_OVERSOLD || CONFIG.RSI_OVERSOLD;
    const RSI_CONFIRM_SHORT_THRESHOLD = strategyConfig.RSI_CONFIRM_SHORT_THRESHOLD || CONFIG.RSI_CONFIRM_SHORT_THRESHOLD;
    const ADX_THRESHOLD = strategyConfig.ADX_THRESHOLD || CONFIG.ADX_THRESHOLD;
    const USE_ATR_FOR_TP_SL = strategyConfig.USE_ATR_FOR_TP_SL || CONFIG.USE_ATR_FOR_TP_SL;
    const TP_ATR_MULTIPLIER = strategyConfig.TP_ATR_MULTIPLIER || CONFIG.TP_ATR_MULTIPLIER;
    const SL_ATR_MULTIPLIER = strategyConfig.SL_ATR_MULTIPLIER || CONFIG.SL_ATR_MULTIPLIER;
    const REWARD_RISK_RATIO = strategyConfig.REWARD_RISK_RATIO || CONFIG.REWARD_RISK_RATIO;


    if (!klines || klines.length < MIN_KLINES_FOR_STRATEGY) {
        logger.debug(`generateEhlSupertrendSignals: Not enough klines (${klines ? klines.length : 0}) for strategy. Required: ${MIN_KLINES_FOR_STRATEGY}`);
        return ['none', null, null, null, [], false];
    }

    const dfIndicators = calculateEhlSupertrendIndicators(klines, strategyConfig); // Pass strategyConfig
    if (!dfIndicators || dfIndicators.length < MIN_KLINES_FOR_STRATEGY) {
        logger.debug(`generateEhlSupertrendSignals: Not enough indicator data (${dfIndicators ? dfIndicators.length : 0}) for strategy. Required: ${MIN_KLINES_FOR_STRATEGY}`);
        return ['none', null, null, null, dfIndicators, false];
    }

    const lastRow = dfIndicators[dfIndicators.length - 1];
    const prevRow = dfIndicators[dfIndicators.length - 2];

    if (!prevRow) {
        return ['none', null, null, null, dfIndicators, false];
    }
    
    const longTrendConfirmed = lastRow.st_slow_direction > 0;
    const shortTrendConfirmed = lastRow.st_slow_direction < 0;
    
    const fastCrossesAboveSlow = prevRow.st_fast_line <= prevRow.st_slow_line && lastRow.st_fast_line > lastRow.st_slow_line;
    const fastCrossesBelowSlow = prevRow.st_fast_line >= prevRow.st_slow_line && lastRow.st_fast_line < lastRow.st_slow_line;
    
    const fisherConfirmLong = lastRow.fisher > lastRow.fisher_signal;
    const rsiConfirmLong = RSI_CONFIRM_LONG_THRESHOLD < lastRow.rsi && lastRow.rsi < RSI_OVERBOUGHT;
    
    const fisherConfirmShort = lastRow.fisher < lastRow.fisher_signal;
    const rsiConfirmShort = RSI_OVERSOLD < lastRow.rsi && lastRow.rsi < RSI_CONFIRM_SHORT_THRESHOLD;
    
    const volumeConfirm = lastRow.volume_spike || prevRow.volume_spike;
    const adxConfirm = lastRow.adx > ADX_THRESHOLD;
    
    let signal = 'none';
    let riskDistance = null;
    let tpPrice = null;
    let slPrice = null;

    if (longTrendConfirmed && fastCrossesAboveSlow && adxConfirm && ((fisherConfirmLong ? 1 : 0) + (rsiConfirmLong ? 1 : 0) + (volumeConfirm ? 1 : 0) >= 2)) {
        signal = 'Buy';
        slPrice = prevRow.st_slow_line;
        riskDistance = currentPrice - slPrice;
        if (riskDistance > 0) {
            if (USE_ATR_FOR_TP_SL) {
                const atrVal = lastRow.atr;
                tpPrice = parseFloat((currentPrice + (atrVal * TP_ATR_MULTIPLIER)).toFixed(pricePrecision));
                slPrice = parseFloat((currentPrice - (atrVal * SL_ATR_MULTIPLIER)).toFixed(pricePrecision));
                riskDistance = currentPrice - slPrice;
            } else {
                tpPrice = parseFloat((currentPrice + (riskDistance * REWARD_RISK_RATIO)).toFixed(pricePrecision));
                slPrice = parseFloat(slPrice.toFixed(pricePrecision));
            }
        } else {
            signal = 'none';
        }

    } else if (shortTrendConfirmed && fastCrossesBelowSlow && adxConfirm && ((fisherConfirmShort ? 1 : 0) + (rsiConfirmShort ? 1 : 0) + (volumeConfirm ? 1 : 0) >= 2)) {
        signal = 'Sell';
        slPrice = prevRow.st_slow_line;
        riskDistance = slPrice - currentPrice;
        if (riskDistance > 0) {
            if (USE_ATR_FOR_TP_SL) {
                const atrVal = lastRow.atr;
                tpPrice = parseFloat((currentPrice - (atrVal * TP_ATR_MULTIPLIER)).toFixed(pricePrecision));
                slPrice = parseFloat((currentPrice + (atrVal * SL_ATR_MULTIPLIER)).toFixed(pricePrecision));
                riskDistance = slPrice - currentPrice;
            } else {
                tpPrice = parseFloat((currentPrice - (riskDistance * REWARD_RISK_RATIO)).toFixed(pricePrecision));
                slPrice = parseFloat(slPrice.toFixed(pricePrecision));
            }
        } else {
            signal = 'none';
        }
    }
            
    return [signal, riskDistance, tpPrice, slPrice, dfIndicators, volumeConfirm];
}

// ====================== 
// MAIN BOT LOGIC 
// ====================== 
async function main(strategyConfig) { // Added strategyConfig parameter
    logger.info(neon.header('Pyrmethus awakens the Ehlers Supertrend Cross Strategy!'));
    logger.debug(`ehlst_strategy: Initializing with config: ${JSON.stringify(strategyConfig)}`);
    
    // Extract strategy-specific config, falling back to global CONFIG if not provided
    const SYMBOL = strategyConfig.SYMBOL || CONFIG.SYMBOL;
    const TRADING_SYMBOLS = strategyConfig.TRADING_SYMBOLS || CONFIG.TRADING_SYMBOLS;
    const TIMEFRAME = strategyConfig.TIMEFRAME || CONFIG.TIMEFRAME;
    const MIN_KLINES_FOR_STRATEGY = strategyConfig.MIN_KLINES_FOR_STRATEGY || CONFIG.MIN_KLINES_FOR_STRATEGY;
    const MAX_POSITIONS = strategyConfig.MAX_POSITIONS || CONFIG.MAX_POSITIONS;
    const RISK_PER_TRADE_PCT = strategyConfig.RISK_PER_TRADE_PCT || CONFIG.RISK_PER_TRADE_PCT;
    const ORDER_QTY_USDT = strategyConfig.ORDER_QTY_USDT || CONFIG.ORDER_QTY_USDT;
    const LEVERAGE = strategyConfig.LEVERAGE || CONFIG.LEVERAGE;
    const MARGIN_MODE = strategyConfig.MARGIN_MODE || CONFIG.MARGIN_MODE;
    const REWARD_RISK_RATIO = strategyConfig.REWARD_RISK_RATIO || CONFIG.REWARD_RISK_RATIO;
    const USE_ATR_FOR_TP_SL = strategyConfig.USE_ATR_FOR_TP_SL || CONFIG.USE_ATR_FOR_TP_SL;
    const TP_ATR_MULTIPLIER = strategyConfig.TP_ATR_MULTIPLIER || CONFIG.TP_ATR_MULTIPLIER;
    const SL_ATR_MULTIPLIER = strategyConfig.SL_ATR_MULTIPLIER || CONFIG.SL_ATR_MULTIPLIER;

    const symbols = TRADING_SYMBOLS;
    if (!symbols || symbols.length === 0) {
        logger.info(neon.warn('No symbols in config.yaml. Exiting.'));
        return;
    }

    const activeTrades = {};
    let cumulativePnl = 0.0;

    while (true) {
        const [localTime, utcTime] = getCurrentTime(CONFIG.TIMEZONE);
        logger.info(neon.dim(`Local: ${localTime.toFormat('yyyy-MM-dd HH:mm:ss')} | UTC: ${utcTime.toFormat('yyyy-MM-dd HH:mm:ss')}`));

        if (!isMarketOpen(localTime, CONFIG.MARKET_OPEN_HOUR, CONFIG.MARKET_CLOSE_HOUR)) {
            logger.info(neon.warn('Market closed. Waiting...'));
            await timeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
            continue;
        }
            
        const balance = await bybitClient.getBalance();
        if (balance === null) {
            logger.error(neon.error('Cannot get balance. Retrying...'));
            await timeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
            continue;
        }
        
        logger.info(neon.success(`Balance: ${balance.toFixed(2)} USDT`));
        const currentPositions = await bybitClient.getPositions();
        logger.info(neon.info(`${currentPositions.length} open positions: ${currentPositions.map(p => p.symbol).join(', ')}`));

        for (const symbol of symbols) {
            if (currentPositions.length >= MAX_POSITIONS) {
                logger.info(neon.warn('Max positions reached. No new trades.'));
                break;
            }
            if (currentPositions.some(p => p.symbol === symbol) || activeTrades[symbol]) {
                continue;
            }

            const klines = await bybitClient.klines(symbol, TIMEFRAME, MIN_KLINES_FOR_STRATEGY + 5);
            if (!klines || klines.length === 0) {
                logger.warn(neon.warn(`Not enough kline data for ${symbol}. Skipping.`));
                continue;
            }
            
            const currentPrice = klines[klines.length - 1].close;
            const [pricePrecision, qtyPrecision, minOrderQty] = await bybitClient.getPrecisions(symbol);
            
            const [signal, risk, tp, sl, dfIndicators, volConfirm] = generateEhlSupertrendSignals(klines, currentPrice, pricePrecision, qtyPrecision, strategyConfig);

            if (dfIndicators && dfIndicators.length > 1) {
                const lastRow = dfIndicators[dfIndicators.length - 1];
                const prevRow = dfIndicators[dfIndicators.length - 2];
                const logMsg = (
                    `[${symbol}] ` +
                    `Price: ${neon.price(currentPrice.toFixed(4))} | ` +
                    `SlowST: ${neon.cyan(lastRow.st_slow_line.toFixed(4))} (${lastRow.st_slow_direction > 0 ? 'Up' : 'Down'}) | ` +
                    `FastST: ${neon.cyan(lastRow.st_fast_line.toFixed(4))} | ` +
                    `RSI: ${neon.warn(lastRow.rsi.toFixed(2))} | ` +
                    `Fisher: ${neon.magenta(lastRow.fisher.toFixed(2))} (Sig: ${lastRow.fisher_signal.toFixed(2)}) | ` +
                    `ADX: ${neon.blue(lastRow.adx.toFixed(2))} | ` +
                    `VolSpike: ${(volConfirm ? neon.success('Yes') : neon.error('No'))}`
                );
                logger.info(logMsg);
            } else {
                logger.warn(neon.warn(`[${symbol}] Could not generate indicator data for logging.`));
            }

            if (signal !== 'none' && risk !== null && risk > 0) {
                const lastRow = dfIndicators[dfIndicators.length - 1];
                const prevRow = dfIndicators[dfIndicators.length - 2];
                const reasoning = [];

                if (signal === 'Buy') {
                    reasoning.push(`SlowST is Up (${prevRow.st_slow_line.toFixed(4)})`);
                    reasoning.push(`FastST crossed above SlowST (${prevRow.st_fast_line.toFixed(4)} -> ${lastRow.st_fast_line.toFixed(4)})`);
                    reasoning.push(`ADX > ${ADX_THRESHOLD} (${lastRow.adx.toFixed(2)})`);
                    const confirmations = [];
                    if (lastRow.fisher > lastRow.fisher_signal) confirmations.push(`Fisher (${lastRow.fisher.toFixed(2)} > ${lastRow.fisher_signal.toFixed(2)})`);
                    if (RSI_CONFIRM_LONG_THRESHOLD < lastRow.rsi && lastRow.rsi < RSI_OVERBOUGHT) confirmations.push(`RSI (${lastRow.rsi.toFixed(2)})`);
                    if (volConfirm) confirmations.push("Volume Spike");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                } else {
                    reasoning.push(`SlowST is Down (${prevRow.st_slow_line.toFixed(4)})`);
                    reasoning.push(`FastST crossed below SlowST (${prevRow.st_fast_line.toFixed(4)} -> ${lastRow.st_fast_line.toFixed(4)})`);
                    reasoning.push(`ADX > ${ADX_THRESHOLD} (${lastRow.adx.toFixed(2)})`);
                    const confirmations = [];
                    if (lastRow.fisher < lastRow.fisher_signal) confirmations.push(`Fisher (${lastRow.fisher.toFixed(2)} < ${lastRow.fisher_signal.toFixed(2)})`);
                    if (RSI_OVERSOLD < lastRow.rsi && lastRow.rsi < RSI_CONFIRM_SHORT_THRESHOLD) confirmations.push(`RSI (${lastRow.rsi.toFixed(2)})`);
                    if (volConfirm) confirmations.push("Volume Spike");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                }

                logger.info(`${(signal === 'Buy' ? neon.success(signal) : neon.error(signal))} SIGNAL for ${symbol} at ${currentPrice.toFixed(4)} | TP: ${tp.toFixed(4)}, SL: ${sl.toFixed(4)} | Reason: ${reasoning.join('; ')}`);
                
                const riskAmountUsdt = balance * RISK_PER_TRADE_PCT;
                let orderQty = Math.min(riskAmountUsdt / risk, ORDER_QTY_USDT / currentPrice);

                if (orderQty > 0 && orderQty < minOrderQty) {
                    logger.warning(neon.warn(`Calculated order qty ${orderQty.toFixed(qtyPrecision + 2)} is below minimum ${minOrderQty}. Checking if minimum is viable...`));
                    
                    const minQtyPositionValue = minOrderQty * currentPrice;
                    const minQtyMargin = minQtyPositionValue / LEVERAGE;
                    const minQtyRiskUsdt = risk * minOrderQty;

                    if (minQtyMargin < balance && minQtyRiskUsdt <= riskAmountUsdt) {
                        logger.info(neon.info(`Adjusting order quantity to the minimum allowed: ${minOrderQty}`));
                        orderQty = minOrderQty;
                    } else {
                        logger.warning(neon.warn(`Minimum order quantity is not viable (margin or risk). Skipping trade.`));
                        orderQty = 0;
                    }
                }
                
                orderQty = parseFloat(orderQty.toFixed(qtyPrecision));

                if (orderQty > 0) {
                    await bybitClient.setMarginModeAndLeverage(symbol, MARGIN_MODE, LEVERAGE);
                    await timeout(500);
                    const orderId = await bybitClient.placeMarketOrder(symbol, signal, orderQty, tp, sl);
                    if (orderId) {
                        activeTrades[symbol] = { entry_time: utcTime.toISO(), order_id: orderId, side: signal, entry_price: currentPrice, qty: orderQty, sl: sl, tp: tp };
                        sendTermuxToast(`${signal.toUpperCase()} Signal: ${symbol}`);
                    }
                } else {
                    logger.warning(neon.warn(`Calculated order quantity for ${symbol} is zero or too small. Skipping.`));
                }
            } else {
                logger.debug(neon.dim(`[${symbol}] No signal generated on this candle.`));
            }
        }
        
        for (const symbol in { ...activeTrades }) {
            if (bybitClient.dry_run && activeTrades[symbol]) {
                logger.info(neon.dim(`[DRY RUN] Simulating trade completion for ${symbol}.`));
                const currentKline = await bybitClient.klines(symbol, TIMEFRAME, 1);
                if (currentKline.length > 0) {
                    const exitPrice = currentKline[0].close;
                    const pnl = calculatePnl(activeTrades[symbol].side, activeTrades[symbol].entry_price, exitPrice, activeTrades[symbol].qty);
                    cumulativePnl += pnl;
                    logger.info(neon.dim(`[DRY RUN] ${symbol} trade completed. PnL: ${pnl.toFixed(2)}. Cumulative PnL: ${cumulativePnl.toFixed(2)}`));
                }
                delete activeTrades[symbol];
                continue;
            }

            // Check if position is closed on exchange
            const exchangePositions = await bybitClient.getPositions();
            if (!exchangePositions.some(p => p.symbol === symbol) && activeTrades[symbol]) {
                 logger.info(neon.info(`Position for ${symbol} appears closed on exchange. Removing from active trades.`));
                 delete activeTrades[symbol];
            }
        }

        await timeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
    }
}

// ====================== 
// LAUNCH 
// ====================== 
(async () => {
    try {
        await main(CONFIG);
    } catch (err) {
        logger.critical(neon.error(`Unhandled error in main loop: ${err.message}`), err);
        process.exit(1);
    }
})();
