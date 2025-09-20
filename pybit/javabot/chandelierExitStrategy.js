// chandelierExitStrategy.js
import logger from './logger.js';
import config from './config.js';
import { calculateATR } from './indicators.js';

/**
 * Generates a trading signal based on the Chandelier Exit strategy.
 * @param {Array<Object>} klines - An array of kline objects.
 * @returns {string} The trading signal: 'BUY', 'SELL', or 'HOLD'.
 */
async function generateSignal(klines) {
    if (!klines || klines.length < config.CE_ATR_PERIOD + 1) {
        logger.warn("Not enough klines for Chandelier Exit calculation. Waiting for more data...");
        return 'HOLD';
    }

    const atr = calculateATR(klines, config.CE_ATR_PERIOD);
    if (atr === null) {
        logger.warn("ATR could not be calculated. Awaiting more data...");
        return 'HOLD';
    }

    const relevantKlines = klines.slice(-config.CE_ATR_PERIOD);
    const highestHigh = Math.max(...relevantKlines.map(k => k.high));
    const lowestLow = Math.min(...relevantKlines.map(k => k.low));

    const chandelierExitLong = highestHigh - (atr * config.CE_ATR_MULTIPLIER);
    const chandelierExitShort = lowestLow + (atr * config.CE_ATR_MULTIPLIER);

    const currentClose = klines[klines.length - 1].close;

    logger.debug(`CE Long: ${chandelierExitLong.toFixed(2)}, CE Short: ${chandelierExitShort.toFixed(2)}, Current Close: ${currentClose.toFixed(2)}`);

    if (currentClose > chandelierExitShort) {
        return 'BUY';
    } else if (currentClose < chandelierExitLong) {
        return 'SELL';
    } else {
        return 'HOLD';
    }
}

export { generateSignal };
