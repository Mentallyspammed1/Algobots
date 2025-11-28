// enhancedPaperExchange.js
import { Decimal } from 'decimal.js';
import { config } from './config.js';
import chalk from 'chalk';

export class EnhancedPaperExchange {
  constructor(logger) {
    this.balance = new Decimal(config.paper_trading.initial_balance);
    this.startBal = this.balance;
    this.pos = null;
    this.dailyPnL = new Decimal(0);
    this.logger = logger;
  }

  canTrade() {
    const drawdownPct = this.startBal.sub(this.balance).div(this.startBal).mul(100);
    if (drawdownPct.gt(config.risk.max_drawdown)) {
      console.log(chalk.RED('🚨 MAX DRAWDOWN HIT - Trading disabled.'));
      return false;
    }
    const dailyLossPct = this.dailyPnL.div(this.startBal).mul(100);
    if (dailyLossPct.lt(-config.risk.daily_loss_limit)) {
      console.log(chalk.RED('🚨 DAILY LOSS LIMIT HIT - Trading disabled.'));
      return false;
    }
    return true;
  }

  evaluate(priceVal, signal) {
    if (!this.canTrade()) {
      if (this.pos) this.handlePositionClose(new Decimal(priceVal), 'RISK_STOP');
      return;
    }
    const price = new Decimal(priceVal);
    if (this.pos) this.handlePositionClose(price);

    const validAction =
      signal &&
      (signal.action === 'BUY' || signal.action === 'SELL') &&
      typeof signal.entry === 'number' &&
      typeof signal.sl === 'number' &&
      typeof signal.tp === 'number';

    if (!this.pos && validAction && signal.confidence >= config.min_confidence) {
      this.handlePositionOpen(price, signal);
    }
  }

  handlePositionClose(price, forceReason = null) {
    if (!this.pos) return;

    let close = false;
    let reason = forceReason || '';
    if (this.pos.side === 'BUY') {
      if (forceReason || price.lte(this.pos.sl)) { close = true; reason ||= 'SL Hit'; }
      else if (price.gte(this.pos.tp)) { close = true; reason ||= 'TP Hit'; }
    } else {
      if (forceReason || price.gte(this.pos.sl)) { close = true; reason ||= 'SL Hit'; }
      else if (price.lte(this.pos.tp)) { close = true; reason ||= 'TP Hit'; }
    }

    if (!close) return;

    const slippage = price.mul(config.paper_trading.slippage);
    const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
    const rawPnl = this.pos.side === 'BUY'
      ? exitPrice.sub(this.pos.entry).mul(this.pos.qty)
      : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
    const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
    const netPnl = rawPnl.sub(fee);

    this.balance = this.balance.add(netPnl);
    this.dailyPnL = this.dailyPnL.add(netPnl);
    const color = netPnl.gte(0) ? chalk.green : chalk.red;
    console.log(`${chalk.bold(reason)}! PnL: ${color(netPnl.toFixed(2))} [${this.pos.strategy}]`);

    this.logger.logTrade(this.pos.entry, exitPrice, netPnl, reason, this.pos.side, this.pos.strategy);
    this.pos = null;
  }

  handlePositionOpen(price, signal) {
    const entry = new Decimal(signal.entry);
    const sl = new Decimal(signal.sl);
    const tp = new Decimal(signal.tp);
    const dist = entry.sub(sl).abs();
    if (dist.isZero()) return;

    const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
    let qty = riskAmt.div(dist);

    const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
    if (qty.gt(maxQty)) qty = maxQty;

    const slippage = price.mul(config.paper_trading.slippage);
    const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
    const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
    this.balance = this.balance.sub(fee);

    this.pos = {
      side: signal.action,
      entry: execPrice,
      qty,
      sl,
      tp,
      strategy: signal.strategy || 'UNKNOWN'
    };

    console.log(
      chalk.green(
        `OPEN ${signal.action} [${this.pos.strategy}] @ ${execPrice.toFixed(4)} | Size: ${qty.toFixed(4)}`
      )
    );
  }
}
