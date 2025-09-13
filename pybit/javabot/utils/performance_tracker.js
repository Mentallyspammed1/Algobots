import { Decimal } from 'decimal.js';
import { logger } from '../logger.js';
import chalk from 'chalk';

class PerformanceTracker {
    constructor(config) {
        this.config = config;
        this.trades = [];
        this.total_pnl = new Decimal("0");
        this.gross_profit = new Decimal("0");
        this.gross_loss = new Decimal("0");
        this.wins = 0;
        this.losses = 0;
        this.peak_pnl = new Decimal("0");
        this.max_drawdown = new Decimal("0");
        this.trading_fee_percent = new Decimal(config.TRADE_MANAGEMENT.TRADING_FEE_PERCENT);
    }

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

    day_pnl() {
        const today = new Date().toISOString().slice(0, 10);
        return this.trades
            .filter(t => t.exit_time?.toISOString().slice(0, 10) === today)
            .reduce((sum, t) => sum.plus(t.pnl_net || new Decimal(0)), new Decimal(0));
    }

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
