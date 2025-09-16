import { Decimal } from 'decimal.js';
import { logger } from '../logger.js';
import chalk from 'chalk';

/**
 * @class PerformanceTracker
 * @description Tracks and calculates the trading performance metrics, including PnL, win rate, and drawdown.
 */
class PerformanceTracker {
    /**
     * @constructor
     * @description Initializes the performance tracker with configuration and sets up all metrics to zero.
     * @param {Object} config - The configuration object, used for `TRADE_MANAGEMENT.TRADING_FEE_PERCENT`.
     */
    constructor(config) {
        this.config = config;
        /** @property {Array<Object>} trades - Stores a history of all recorded trades. */
        this.trades = [];
        /** @property {Decimal} total_pnl - The cumulative net Profit and Loss. */
        this.total_pnl = new Decimal("0");
        /** @property {Decimal} gross_profit - The sum of all winning trades' net PnL. */
        this.gross_profit = new Decimal("0");
        /** @property {Decimal} gross_loss - The sum of all losing trades' absolute net PnL. */
        this.gross_loss = new Decimal("0");
        /** @property {number} wins - The count of winning trades. */
        this.wins = 0;
        /** @property {number} losses - The count of losing trades. */
        this.losses = 0;
        /** @property {Decimal} peak_pnl - The highest `total_pnl` achieved. */
        this.peak_pnl = new Decimal("0");
        /** @property {Decimal} max_drawdown - The maximum drawdown experienced. */
        this.max_drawdown = new Decimal("0");
        /** @property {Decimal} trading_fee_percent - The trading fee percentage from configuration. */
        this.trading_fee_percent = new Decimal(config.TRADE_MANAGEMENT.TRADING_FEE_PERCENT);
    }

    /**
     * @method record_trade
     * @description Records a completed trade, updates PnL, and other performance metrics.
     * Calculates net PnL after accounting for trading fees.
     * @param {Object} position - The position object representing the closed trade.
     * @param {Decimal} pnl - The gross PnL for the trade before fees.
     * @returns {void}
     */
    record_trade(position, pnl) {
        const entry_fee = position.entry_price.times(position.qty).times(this.trading_fee_percent);
        const exit_fee = position.exit_price.times(position.qty).times(this.trading_fee_percent);
        const total_fees = entry_fee.plus(exit_fee);
        const pnl_net = pnl.minus(total_fees);

        const trade = {
            ...position,
            fees: total_fees,
            pnl_gross: pnl,
            pnl_net: pnl_net
        };

        this.trades.push(trade);
        this.total_pnl = this.total_pnl.plus(pnl_net);

        if (pnl_net.gt(0)) {
            this.wins++;
            this.gross_profit = this.gross_profit.plus(pnl_net);
        } else {
            this.losses++;
            this.gross_loss = this.gross_loss.plus(pnl_net.abs());
        }

        if (this.total_pnl.gt(this.peak_pnl)) this.peak_pnl = this.total_pnl;
        const drawdown = this.peak_pnl.minus(this.total_pnl);
        if (drawdown.gt(this.max_drawdown)) this.max_drawdown = drawdown;

        logger.info(
            chalk.cyan(`Trade recorded | Net PnL: ${pnl_net.toFixed(4)} | Total: ${this.total_pnl.toFixed(4)}`)
        );
    }

    /**
     * @method day_pnl
     * @description Calculates the total net PnL for trades that exited today.
     * @returns {Decimal} The total net PnL for the current day.
     */
    day_pnl() {
        const today = new Date().toISOString().slice(0, 10);
        return this.trades
            .filter(t => t.exit_time?.toISOString().slice(0, 10) === today)
            .reduce((sum, t) => sum.plus(t.pnl_net || new Decimal(0)), new Decimal(0));
    }

    /**
     * @method get_summary
     * @description Generates a summary object of the overall trading performance.
     * @returns {Object} An object containing various performance metrics like total trades, total PnL, win rate, etc.
     */
    get_summary() {
        const total_trades = this.trades.length;
        const win_rate = total_trades > 0 ? (this.wins / total_trades) * 100 : 0;
        const profit_factor = this.gross_loss.gt(0) ? this.gross_profit.dividedBy(this.gross_loss) : new Decimal("Infinity");
        const avg_win = this.wins > 0 ? this.gross_profit.dividedBy(this.wins) : new Decimal("0");
        const avg_loss = this.losses > 0 ? this.gross_loss.dividedBy(this.losses) : new Decimal("0");

        return {
            total_trades,
            total_pnl: this.total_pnl,
            gross_profit: this.gross_profit,
            gross_loss: this.gross_loss,
            profit_factor,
            max_drawdown: this.max_drawdown,
            wins: this.wins,
            losses: this.losses,
            win_rate: `${win_rate.toFixed(2)}%`,
            avg_win,
            avg_loss
        };
    }
}

export default PerformanceTracker;