import { logger } from './logger';

export interface Trade {
    symbol: string;
    side: 'Buy' | 'Sell';
    entry_price: number;
    exit_price: number;
    size: number;
    pnl: number;
    pnl_pct: number;
    fees: number;
    entry_timestamp: number;
    exit_timestamp: number;
}

export class TradeMetrics {
    private trades: Trade[] = [];

    public addTrade(trade: Trade) {
        this.trades.push(trade);
        logger.success(`TRADE CLOSED: ${trade.side} ${trade.size} ${trade.symbol}. PNL: ${trade.pnl.toFixed(2)} USD (${trade.pnl_pct.toFixed(2)}%)`);
    }

    public displaySummary() {
        if (this.trades.length === 0) {
            logger.system('No trades have been closed yet.');
            return;
        }

        const total_trades = this.trades.length;
        const winning_trades = this.trades.filter(t => t.pnl > 0);
        const losing_trades = this.trades.filter(t => t.pnl <= 0);

        const total_pnl = this.trades.reduce((sum, t) => sum + t.pnl, 0);
        const win_rate = total_trades > 0 ? (winning_trades.length / total_trades) * 100 : 0;
        
        const gross_profit = winning_trades.reduce((sum, t) => sum + t.pnl, 0);
        const gross_loss = Math.abs(losing_trades.reduce((sum, t) => sum + t.pnl, 0));
        const profit_factor = gross_loss > 0 ? gross_profit / gross_loss : Infinity;

        const summary = `

+---------------------------------------+
|           TRADE METRICS               |
+---------------------------------------+
| Total Trades:    | ${total_trades.toString().padEnd(18)} |
| Winning Trades:  | ${winning_trades.length.toString().padEnd(18)} |
| Losing Trades:   | ${losing_trades.length.toString().padEnd(18)} |
| Win Rate:        | ${(win_rate.toFixed(2) + '%').padEnd(18)} |
+------------------+--------------------+
| Total PNL:       | ${(total_pnl.toFixed(2) + ' USD').padEnd(18)} |
| Gross Profit:    | ${(gross_profit.toFixed(2) + ' USD').padEnd(18)} |
| Gross Loss:      | ${(gross_loss.toFixed(2) + ' USD').padEnd(18)} |
| Profit Factor:   | ${profit_factor.toFixed(2).padEnd(18)} |
+---------------------------------------+
`;

        logger.system(summary);
    }
}
