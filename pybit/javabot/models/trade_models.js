const { Decimal } = require('decimal.js');

/**
 * Represents a single trade executed by the bot.
 */
class Trade {
    /**
     * Creates an instance of Trade.
     * @param {object} params - Trade parameters.
     * @param {string} params.id - Unique ID of the trade.
     * @param {string} params.order_id - Order ID from the exchange.
     * @param {string} params.symbol - Trading symbol.
     * @param {string} params.side - Trade side ('Buy' or 'Sell').
     * @param {Decimal|number} params.qty - Quantity of the trade.
     * @param {string} params.entry_time - ISO string of entry time.
     * @param {Decimal|number} params.entry_price - Entry price.
     * @param {Decimal|number} params.sl - Stop loss price.
     * @param {Decimal|number} params.tp - Take profit price.
     * @param {string} [params.status='OPEN'] - Current status of the trade.
     * @param {string|null} [params.exit_time=null] - ISO string of exit time.
     * @param {Decimal|number|null} [params.exit_price=null] - Exit price.
     * @param {Decimal|number|null} [params.pnl=null] - Profit and Loss.
     */
    constructor({
        id,
        order_id,
        symbol,
        side,
        qty,
        entry_time,
        entry_price,
        sl,
        tp,
        status = 'OPEN',
        exit_time = null,
        exit_price = null,
        pnl = null
    }) {
        this.id = id;
        this.order_id = order_id;
        this.symbol = symbol;
        this.side = side;
        this.qty = new Decimal(qty);
        this.entry_time = entry_time; // ISO string
        this.entry_price = new Decimal(entry_price);
        this.sl = new Decimal(sl);
        this.tp = new Decimal(tp);
        this.status = status;
        this.exit_time = exit_time;
        this.exit_price = exit_price ? new Decimal(exit_price) : null;
        this.pnl = pnl ? new Decimal(pnl) : null;
    }
}

/**
 * Represents an open position on the exchange.
 */
class Position {
    /**
     * Creates an instance of Position.
     * @param {object} params - Position parameters.
     * @param {string} params.symbol - Trading symbol.
     * @param {string} params.side - Position side ('Buy' or 'Sell').
     * @param {Decimal|number} params.size - Size of the position.
     * @param {Decimal|number} params.avgPrice - Average entry price.
     * @param {Decimal|number} params.markPrice - Mark price.
     * @param {Decimal|number} params.leverage - Leverage used.
     * @param {Decimal|number} params.liqPrice - Liquidation price.
     * @param {Decimal|number} params.bustPrice - Bust price.
     * @param {Decimal|number} params.riskLimitValue - Risk limit value.
     * @param {Decimal|number} params.takeProfit - Take profit price.
     * @param {Decimal|number} params.stopLoss - Stop loss price.
     * @param {Decimal|number} params.unrealisedPnl - Unrealized PnL.
     * @param {string} params.createdTime - Creation time.
     * @param {string} params.updatedTime - Last update time.
     */
    constructor({
        symbol,
        side,
        size,
        avgPrice,
        markPrice,
        leverage,
        liqPrice,
        bustPrice,
        riskLimitValue,
        takeProfit,
        stopLoss,
        unrealisedPnl,
        createdTime,
        updatedTime
    }) {
        this.symbol = symbol;
        this.side = side;
        this.size = new Decimal(size);
        this.avgPrice = new Decimal(avgPrice);
        this.markPrice = new Decimal(markPrice);
        this.leverage = new Decimal(leverage);
        this.liqPrice = new Decimal(liqPrice);
        this.bustPrice = new Decimal(bustPrice);
        this.riskLimitValue = new Decimal(riskLimitValue);
        this.takeProfit = new Decimal(takeProfit);
        this.stopLoss = new Decimal(stopLoss);
        this.unrealisedPnl = new Decimal(unrealisedPnl);
        this.createdTime = createdTime;
        this.updatedTime = updatedTime;
    }
}

module.exports = { Trade, Position };
