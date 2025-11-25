import { Decimal } from 'decimal.js';
import chalk from 'chalk';

const NEON = {
    GREEN: chalk.hex('#39FF14'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'),
    YELLOW: chalk.hex('#FAED27'),
    ORANGE: chalk.hex('#FF9F00'),
    GRAY: chalk.hex('#666666
    BOLD: chalk.bold
};

class TradeHistory {
    constructor() {
        this.trades = [];
        this.nextId = 1;
        Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });
    }

    addTrade(tradeRecord) {
        this.trades.push(tradeRecord);
    }

    getTrades() {
        return this.trades;
    }

    getTradesBySymbol(symbol) {
        return this.trades.filter(trade => trade.symbol === symbol);
    }

    getTotalPnL() {
        if (this.trades.length === 0) {
            return new Decimal(0);
        }
        return this.trades.reduce((total, trade) => total.add(new Decimal(trade.pnl)), new Decimal(0));
    }

    getTradeCount() {
        return this.trades.length;
    }

    displaySummary() {
        console.log('\n--- Trade History Summary ---');
        if (this.trades.length === 0) {
            console.log(NEON.GRAY("No trades recorded yet."));
            return;
        }

        const totalPnl = this.getTotalPnL();
        const pnlColor = totalPnl.gte(0) ? NEON.GREEN : NEON.RED;

        console.log(`Total Trades: ${this.getTradeCount()}`);
        console.log(`Total PnL: ${pnlColor(`$${totalPnl.toFixed(2)}`)}
`);

        console.log("Last 5 Trades:");
        const lastTrades = this.trades.slice(-5).reverse();
        lastTrades.forEach(trade => {
            const pnlColor = new Decimal(trade.pnl).gte(0) ? NEON.GREEN : NEON.RED;
            console.log(`  [${trade.timestamp}] ${trade.side} ${trade.symbol} | Entry: ${trade.entryPrice} | Exit: ${trade.exitPrice} | Qty: ${trade.quantity.toFixed(4)} | PnL: ${pnlColor(trade.pnl)} | Reason: ${trade.reason}`);
        });
        console.log('---------------------------');
    }
}

export default TradeHistory;
