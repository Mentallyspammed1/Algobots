/**
 * Calculates order quantity dynamically based on inventory imbalance.
 * Increases buy size if short on inventory, and sell size if long.
 * @param {object} config - The bot's configuration object.
 * @param {number} inventory - Current inventory in base currency (negative for short, positive for long).
 * @param {number} price - The current price of the asset.
 * @returns {{buyQuantity: number, sellQuantity: number}}
 */
function calculateDynamicQuantities(config, inventory, price) {
    const baseOrderValue = config.mm_order_size_usdt;
    const maxInventoryBase = config.mm_max_inventory_base;

    // Normalize inventory between -1 and 1 based on max limit
    const normalizedInventory = Math.max(-1, Math.min(1, inventory / maxInventoryBase));

    // Calculate dynamic size multiplier (e.g., short inventory boosts buy size)
    // Buy multiplier: 1 - normalizedInventory (range from 0 to 2)
    const buyMultiplier = 1 - normalizedInventory;
    // Sell multiplier: 1 + normalizedInventory (range from 0 to 2)
    const sellMultiplier = 1 + normalizedInventory;

    // Calculate final quantities in base currency
    const buyQuantity = (baseOrderValue * buyMultiplier) / price;
    const sellQuantity = (baseOrderValue * sellMultiplier) / price;

    return { buyQuantity, sellQuantity };
}

/**
 * Executes a market order to reduce inventory back to zero when limit is hit.
 * @param {object} exchange - The CCXT exchange object.
 * @param {string} symbol - The trading symbol (e.g., 'BTC/USDT').
 * @param {number} inventory - Current inventory in base currency.
 * @param {number} maxInventoryBase - The maximum allowed inventory deviation.
 * @returns {Promise<void>}
 */
async function rebalanceInventory(exchange, symbol, inventory, maxInventoryBase) {
    const rebalanceThreshold = maxInventoryBase * 0.9; // Rebalance if inventory exceeds 90% of max limit
    const rebalanceQuantity = Math.abs(inventory); // Rebalance the full amount

    if (inventory > rebalanceThreshold) {
        log.warn(`[MM] Rebalancing: Inventory (${inventory.toFixed(4)}) exceeds threshold (${rebalanceThreshold}). Selling ${rebalanceQuantity.toFixed(4)}.`);
        try {
            await exchange.createMarketSellOrder(symbol, rebalanceQuantity);
            log.success(`[MM] Market sell rebalance successful for ${rebalanceQuantity.toFixed(4)} ${symbol}.`);
        } catch (e) {
            log.error(`[MM] Failed to execute market sell rebalance: ${e.message}`);
        }
    } else if (inventory < -rebalanceThreshold) {
        log.warn(`[MM] Rebalancing: Inventory (${inventory.toFixed(4)}) exceeds threshold (${-rebalanceThreshold}). Buying ${rebalanceQuantity.toFixed(4)}.`);
        try {
            await exchange.createMarketBuyOrder(symbol, rebalanceQuantity);
            log.success(`[MM] Market buy rebalance successful for ${rebalanceQuantity.toFixed(4)} ${symbol}.`);
        } catch (e) {
            log.error(`[MM] Failed to execute market buy rebalance: ${e.message}`);
        }
    }
}

/**
 * Calculates a dynamic spread percentage based on market volatility.
 * Uses a base spread and scales it by a factor derived from ATR.
 * @param {object[]} candles - Array of OHLCV candles (required for ATR).
 * @param {number} baseSpreadPercent - The base spread percentage from config.
 * @param {number} minSpreadPercent - Minimum allowed spread percentage.
 * @returns {number} The adjusted spread percentage.
 */
function calculateDynamicSpread(candles, baseSpreadPercent, minSpreadPercent) {
    if (candles.length < 2) return baseSpreadPercent;

    const highs = candles.map(x => x.h);
    const lows = candles.map(x => x.l);
    const closes = candles.map(x => x.c);
    const atrs = Quant.ATR(highs, lows, closes); // Assuming Quant.ATR function exists
    const currentPrice = closes[closes.length - 1];

    // Calculate a volatility factor: ATR relative to price.
    // Use a short lookback for volatility calculation (e.g., last 14 periods)
    const volatilityFactor = atrs.div(currentPrice).toNumber();

    // Scale spread based on volatility, ensuring minimum spread.
    // Example: spread = max(baseSpreadPercent, volatilityFactor * sensitivityMultiplier)
    const sensitivityMultiplier = 1.5; // Adjust based on desired responsiveness
    const dynamicSpread = Math.max(minSpreadPercent, baseSpreadPercent + volatilityFactor * sensitivityMultiplier);

    return dynamicSpread;
}