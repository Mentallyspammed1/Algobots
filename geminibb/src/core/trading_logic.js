
import { config } from '../config.js';
import logger from '../utils/logger.js';
// IMPROVEMENT 15: Use Decimal.js for precise financial calculations
import Decimal from 'decimal.js';

/**
 * Safely formats a numeric value to a fixed decimal string or returns 'N/A'.
 * @param {Decimal | number | null | undefined} value The number to format.
 * @param {number} precision The number of decimal places.
 * @returns {string} The formatted string or 'N/A'.
 */
const safeFormat = (value, precision) => {
    if (value instanceof Decimal) {
        return value.toFixed(precision);
    }
    if (typeof value === 'number' && !isNaN(value)) {
        return new Decimal(value).toFixed(precision);
    }
    return 'N/A';
};

/**
 * Calculates the position size based on risk percentage and stop-loss distance.
 * @param {Decimal} balance - The total account balance.
 * @param {Decimal} entryPrice - The current price of the asset.
 * @param {Decimal} stopLossPrice - The calculated stop-loss price.
 * @param {number} qtyPrecision - Dynamic quantity precision from Bybit API.
 * @param {number} minOrderQty - Dynamic min order quantity from Bybit API.
 * @returns {Decimal} The quantity to trade.
 */
export function calculatePositionSize(balance, entryPrice, stopLossPrice, qtyPrecision, minOrderQty, leverage = 1) { // Add leverage parameter, default to 1x
    balance = new Decimal(balance);
    entryPrice = new Decimal(entryPrice);
    stopLossPrice = new Decimal(stopLossPrice);
    leverage = new Decimal(leverage); // Ensure leverage is Decimal

    const riskAmount = balance.times(config.riskPercentage).dividedBy(100);
    const slippageCost = entryPrice.times(config.slippagePercentage).dividedBy(100);
    const effectiveEntryPrice = entryPrice.plus(slippageCost);

    const riskPerShare = effectiveEntryPrice.minus(stopLossPrice).abs();

    if (riskPerShare.isZero()) {
        logger.warn("Calculated risk per share is zero. Cannot calculate position size.");
        return new Decimal(0);
    }

    let quantity = riskAmount.dividedBy(riskPerShare);

    // IMPROVEMENT 12: Account for leverage in position sizing
    // The amount of capital actually put down (margin) is `quantity * entryPrice / leverage`.
    // So, we want `(quantity * entryPrice / leverage) >= riskAmount` for initial margin.
    // However, riskAmount is the total USDT risk at SL.
    // So, quantity = riskAmount / riskPerShare, then adjust for margin.
    // For risk-based sizing, the quantity calculated without leverage is generally correct
    // because `riskAmount` is already in the quote currency (e.g., USDT). Leverage affects
    // the margin used, not the PnL calculation itself, which is based on the notional size.
    // A more precise adjustment is needed for `initial margin`.
    // Let's assume `riskAmount` is the total notional value at risk.
    // If the account is cross-margin, the entire `balance` is available.
    // If isolated margin, it's `riskAmount / (entryPrice * leverage)`
    // For simplicity, let's keep the quantity calculation as is, but ensure `riskAmount`
    // is understood as the 'notional risk' the bot is willing to take, which is covered by margin.

    // Reduce quantity slightly to account for fees, ensuring it doesn't drop below min order size
    // For simplicity, we directly adjust quantity here. A more complex system might pre-calculate
    // the max fee and subtract it from riskAmount.
    const feeFactor = new Decimal(1).minus(new Decimal(config.exchangeFeePercentage).dividedBy(100));
    quantity = quantity.times(feeFactor);

    // IMPROVEMENT 16: Apply dynamic quantity precision
    const finalQuantity = quantity.toDecimalPlaces(qtyPrecision, Decimal.ROUND_DOWN);

    // IMPROVEMENT 16: Check against dynamic minOrderQty
    if (finalQuantity.lt(minOrderQty)) {
        logger.warn(`Calculated quantity (${finalQuantity.toFixed(qtyPrecision)}) is below min order size (${minOrderQty}). Cannot open position.`);
        return new Decimal(0);
    }

    const tradeCost = finalQuantity.times(entryPrice).times(new Decimal(config.exchangeFeePercentage).dividedBy(100));
    logger.info(`Position size calculated: ${finalQuantity.toFixed(qtyPrecision)}. Risking ${riskAmount.toFixed(2)} USDT with ${leverage.toFixed(2)}x leverage.`);
    return finalQuantity;
}

/**
 * Determines stop-loss and take-profit prices based on the configured strategy.
 * This acts as a controller, calling the appropriate underlying function.
 * @param {Decimal} entryPrice - The price at which the trade is entered.
 * @param {string} side - The side of the trade ('Buy' or 'Sell').
 * @param {Decimal} atr - The latest Average True Range value.
 * @param {number} pricePrecision - Dynamic price precision from Bybit API.
 * @returns {{stopLoss: Decimal, takeProfit: Decimal}}
 */
export function determineExitPrices(entryPrice, side, atr, pricePrecision) {
    // IMPROVEMENT 15: Ensure all inputs are Decimal
    entryPrice = new Decimal(entryPrice);
    atr = new Decimal(atr);

    if (config.stopLossStrategy === 'atr' && atr.gt(0)) {
        return determineExitPricesATR(entryPrice, side, atr, pricePrecision);
    } else if (config.stopLossStrategy === 'trailing') { // IMPROVEMENT 17: Trailing Stop-Loss Placeholder
        logger.warn("Trailing stop-loss is not yet fully implemented. Using ATR or Percentage fallback.");
        return determineExitPricesATR(entryPrice, side, atr, pricePrecision); // Fallback
    }
    // Fallback to the percentage-based method
    return determineExitPricesPercentage(entryPrice, side, pricePrecision);
}

/**
 * Determines exit prices using a fixed percentage.
 * @private
 */
function determineExitPricesPercentage(entryPrice, side, pricePrecision) {
    const slDistance = entryPrice.times(config.stopLossPercentage).dividedBy(100);
    const tpDistance = slDistance.times(config.riskToRewardRatio);

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(slDistance);
        takeProfit = entryPrice.plus(tpDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(slDistance);
        takeProfit = entryPrice.minus(tpDistance);
    }
    // IMPROVEMENT 16: Apply dynamic price precision
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}

/**
 * Determines exit prices using the Average True Range (ATR) for market-adaptive stops.
 * @private
 */
function determineExitPricesATR(entryPrice, side, atr, pricePrecision) {
    const slDistance = atr.times(config.atrMultiplier);
    const tpDistance = slDistance.times(config.riskToRewardRatio);

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(slDistance);
        takeProfit = entryPrice.plus(tpDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(slDistance);
        takeProfit = entryPrice.minus(tpDistance);
    }
    logger.info(`ATR-based exits calculated: SL=${stopLoss.toFixed(pricePrecision)}, TP=${takeProfit.toFixed(pricePrecision)}`);
    // IMPROVEMENT 16: Apply dynamic price precision
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}

/**
 * Adjusts the stop loss to break-even (entry price + fees) if a minimum profit threshold is met.
 * @param {Decimal} currentPrice - The current market price.
 * @param {object} position - The current position details (entryPrice, positionSide, quantity).
 * @param {Decimal} currentStopLoss - The current stop loss level.
 * @param {number} pricePrecision - Price precision from Bybit API.
 * @returns {Decimal} The new, adjusted stop loss price.
 */
export function adjustStopLossToBreakEven(currentPrice, position, currentStopLoss, pricePrecision) {
    const entryPrice = new Decimal(position.entryPrice);
    const positionSide = position.positionSide;
    const quantity = new Decimal(position.quantity);

    // Calculate profit needed to reach break-even threshold (e.g., 0.5% profit)
    const profitThresholdAmount = entryPrice.times(quantity).times(config.breakEvenProfitPercentage).dividedBy(100);

    let unrealizedPnl;
    if (positionSide === 'Buy') {
        unrealizedPnl = currentPrice.minus(entryPrice).times(quantity);
    } else { // Sell
        unrealizedPnl = entryPrice.minus(currentPrice).times(quantity);
    }

    if (unrealizedPnl.gte(profitThresholdAmount)) {
        // Calculate break-even price including estimated fees
        const estimatedFees = entryPrice.times(config.exchangeFeePercentage).dividedBy(100);
        let breakEvenPrice;
        if (positionSide === 'Buy') {
            breakEvenPrice = entryPrice.plus(estimatedFees);
        } else { // Sell
            breakEvenPrice = entryPrice.minus(estimatedFees);
        }

        // Only move SL if the new break-even price is better (or equal) than the current SL
        // For Buy: new SL must be >= current SL (higher price is better)
        // For Sell: new SL must be <= current SL (lower price is better)
        if ((positionSide === 'Buy' && breakEvenPrice.gte(currentStopLoss)) ||
            (positionSide === 'Sell' && breakEvenPrice.lte(currentStopLoss))) {
            logger.info(`Moving stop loss to break-even for ${positionSide} position. Old SL: ${currentStopLoss.toFixed(pricePrecision)}, New SL: ${breakEvenPrice.toFixed(pricePrecision)}`);
            return breakEvenPrice.toDecimalPlaces(pricePrecision);
        }
    }
    return currentStopLoss; // No change to SL
}

// IMPROVEMENT 17: Placeholder for Trailing Stop-Loss logic
/*
function determineExitPricesTrailing(entryPrice, side, atr, pricePrecision, currentPrice) {
    // This would typically involve dynamic updates based on currentPrice,
    // not just a single calculation at entry. For an initial setup, it
    // might set an initial stop loss and then allow the system to adjust it.
    // For a snippet, we'll keep it simple for initial setup.
    const initialSlDistance = atr.times(config.atrMultiplier);
    let stopLoss;
    if (side === 'Buy') {
        stopLoss = entryPrice.minus(initialSlDistance);
    } else { // Sell
        stopLoss = entryPrice.plus(initialSlDistance);
    }
    // TP for trailing stops is often not a fixed target, but for Bybit API
    // we might still need to provide one, or manage it separately.
    const takeProfit = side === 'Buy' ? entryPrice.plus(initialSlDistance.times(config.riskToRewardRatio)) : entryPrice.minus(initialSlDistance.times(config.riskToRewardRatio));

    logger.info(`Trailing SL (initial) calculated: SL=${stopLoss.toFixed(pricePrecision)}, TP=${takeProfit.toFixed(pricePrecision)}`);
    return {
        stopLoss: stopLoss.toDecimalPlaces(pricePrecision),
        takeProfit: takeProfit.toDecimalPlaces(pricePrecision)
    };
}
*/
