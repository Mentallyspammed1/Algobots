
import { config } from '../config.js';
import logger from '../utils/logger.js';

/**
 * Safely formats a numeric value to a fixed decimal string or returns 'N/A'.
 * @param {number | null | undefined} value The number to format.
 * @param {number} precision The number of decimal places.
 * @returns {string} The formatted string or 'N/A'.
 */
const safeFormat = (value, precision) => {
    if (typeof value === 'number' && !isNaN(value)) {
        return value.toFixed(precision);
    }
    return 'N/A';
};

/**
 * Calculates the position size based on risk percentage and stop-loss distance.
 * @param {number} balance - The total account balance.
 * @param {number} currentPrice - The current price of the asset.
 * @param {number} stopLossPrice - The calculated stop-loss price.
 * @returns {number} The quantity to trade, rounded to the configured precision.
 */
export function calculatePositionSize(balance, entryPrice, stopLossPrice) {
    const riskAmount = balance * (config.riskPercentage / 100);
    const slippageCost = entryPrice * (config.slippagePercentage / 100);
    const effectiveEntryPrice = entryPrice + slippageCost; // Assume worst-case slippage
    
    const riskPerShare = Math.abs(effectiveEntryPrice - stopLossPrice);
    if (riskPerShare === 0) return 0;
    
    const quantity = riskAmount / riskPerShare;
    const tradeCost = quantity * entryPrice * (config.exchangeFeePercentage / 100);

    // Reduce quantity slightly to account for fees
    const finalQuantity = parseFloat((quantity * (1 - (config.exchangeFeePercentage / 100))).toFixed(config.quantityPrecision));

    if (finalQuantity < config.minOrderSize) {
        logger.warn(`Calculated quantity (${finalQuantity}) is below min order size (${config.minOrderSize}). Cannot open position.`);
        return 0;
    }
    logger.info(`Position size calculated: ${finalQuantity}. Risking ${riskAmount.toFixed(2)} USDT with trade cost ~${tradeCost.toFixed(2)} USDT.`);
    return finalQuantity;
}

/**
 * Determines stop-loss and take-profit prices based on the configured strategy.
 * This acts as a controller, calling the appropriate underlying function.
 * @param {number} entryPrice - The price at which the trade is entered.
 * @param {string} side - The side of the trade ('Buy' or 'Sell').
 * @param {number} atr - The latest Average True Range value.
 * @returns {{stopLoss: number, takeProfit: number}}
 */
export function determineExitPrices(entryPrice, side, atr) {
    if (config.stopLossStrategy === 'atr' && typeof atr === 'number' && atr > 0) {
        return determineExitPricesATR(entryPrice, side, atr);
    }
    // Fallback to the percentage-based method
    return determineExitPricesPercentage(entryPrice, side);
}

/**
 * Determines exit prices using a fixed percentage.
 * @private
 */
function determineExitPricesPercentage(entryPrice, side) {
    const slDistance = entryPrice * (config.stopLossPercentage / 100);
    const tpDistance = slDistance * config.riskToRewardRatio;

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice - slDistance;
        takeProfit = entryPrice + tpDistance;
    } else { // Sell
        stopLoss = entryPrice + slDistance;
        takeProfit = entryPrice - tpDistance;
    }
    return {
        stopLoss: parseFloat(stopLoss.toFixed(config.pricePrecision)),
        takeProfit: parseFloat(takeProfit.toFixed(config.pricePrecision))
    };
}

/**
 * Determines exit prices using the Average True Range (ATR) for market-adaptive stops.
 * @private
 */
function determineExitPricesATR(entryPrice, side, atr) {
    const slDistance = atr * config.atrMultiplier;
    const tpDistance = slDistance * config.riskToRewardRatio;

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice - slDistance;
        takeProfit = entryPrice + tpDistance;
    } else { // Sell
        stopLoss = entryPrice + slDistance;
        takeProfit = entryPrice - tpDistance;
    }
    logger.info(`ATR-based exits calculated: SL=${stopLoss.toFixed(config.pricePrecision)}, TP=${takeProfit.toFixed(config.pricePrecision)}`);
    return {
        stopLoss: parseFloat(stopLoss.toFixed(config.pricePrecision)),
        takeProfit: parseFloat(takeProfit.toFixed(config.pricePrecision))
    };
}
