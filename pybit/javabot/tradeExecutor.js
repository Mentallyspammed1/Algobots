// tradeExecutor.js
import logger from './logger.js';
import config from './config.js';

/**
 * Executes a trade based on the generated signal.
 * @param {Object} bybit - The BybitClient instance.
 * @param {string} signal - The trading signal ('BUY' or 'SELL').
 * @param {number} currentPrice - The current market price.
 * @param {number} balance - The available wallet balance.
 */
async function executeTrade(bybit, signal, currentPrice, balance) {
    const tradeAmount = balance * config.TRADE_AMOUNT_PERCENTAGE;
    const qty = tradeAmount / currentPrice;

    if (signal === 'BUY') {
        logger.info(`Executing BUY signal for ${config.SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        const takeProfitPrice = currentPrice * (1 + config.TAKE_PROFIT_PERCENTAGE);
        const stopLossPrice = currentPrice * (1 - config.STOP_LOSS_PERCENTAGE);
        await bybit.placeMarketOrder(config.SYMBOL, 'Buy', qty, takeProfitPrice, stopLossPrice);
    } else if (signal === 'SELL') {
        logger.info(`Executing SELL signal for ${config.SYMBOL}. Quantity: ${qty.toFixed(5)}`);
        const takeProfitPrice = currentPrice * (1 - config.TAKE_PROFIT_PERCENTAGE);
        const stopLossPrice = currentPrice * (1 + config.STOP_LOSS_PERCENTAGE);
        await bybit.placeMarketOrder(config.SYMBOL, 'Sell', qty, takeProfitPrice, stopLossPrice);
    } else {
        logger.info(`No trade executed. Signal: ${signal}. The market remains tranquil.`);
    }
}

export { executeTrade };
