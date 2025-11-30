const { Decimal } = require('decimal.js');
const config = require('../config');
const NEON = require('../utils/colors');

class EnhancedPaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance); this.startBal = this.balance;
        this.pos = null; this.dailyPnL = new Decimal(0);
    }
    canTrade() {
        const drawdown = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdown.gt(config.risk.max_drawdown)) { console.log(NEON.RED(`🚨 MAX DRAWDOWN HIT`)); return false; }
        const dailyLoss = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLoss.lt(-config.risk.daily_loss_limit)) { console.log(NEON.RED(`🚨 DAILY LOSS LIMIT HIT`)); return false; }
        return true;
    }
    evaluate(priceVal, signal) {
        if (!this.canTrade()) { if (this.pos) this.handlePositionClose(new Decimal(priceVal), "RISK_STOP"); return; }
        const price = new Decimal(priceVal);
        if (this.pos) this.handlePositionClose(price);
        if (!this.pos && signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) { this.handlePositionOpen(price, signal); }
    }
    handlePositionClose(price, forceReason = null) {
        let close = false, reason = forceReason || '';
        if (this.pos.side === 'BUY') { if (forceReason || price.lte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.gte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } } else { if (forceReason || price.gte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.lte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } }
        if (close) {
            const slippage = price.mul(config.paper_trading.slippage);
            const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
            const rawPnl = this.pos.side === 'BUY' ? exitPrice.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
            const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
            const netPnl = rawPnl.sub(fee);
            this.balance = this.balance.add(netPnl); this.dailyPnL = this.dailyPnL.add(netPnl);
            const color = netPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(`${NEON.BOLD(reason)}! PnL: ${color(netPnl.toFixed(2))} [${this.pos.strategy}]`);
            this.pos = null;
        }
    }
    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry); const sl = new Decimal(signal.sl); const tp = new Decimal(signal.tp);
        const dist = entry.sub(sl).abs(); if (dist.isZero()) return;
        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);
        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;
        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
        this.balance = this.balance.sub(fee);
        this.pos = { side: signal.action, entry: execPrice, qty: qty, sl: sl, tp: tp, strategy: signal.strategy };
        console.log(NEON.GREEN(`OPEN ${signal.action} [${signal.strategy}] @ ${execPrice.toFixed(4)} | Size: ${qty.toFixed(4)}`));
    }
}

module.exports = { EnhancedPaperExchange };
