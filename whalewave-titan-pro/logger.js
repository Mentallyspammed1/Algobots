// logger.js
import fs from 'fs';
import path from 'path';

export class TradeLogger {
  constructor() {
    this.dir = path.resolve('./logs');
    if (!fs.existsSync(this.dir)) fs.mkdirSync(this.dir);
    this.session = Date.now();
    this.signalsFile = `${this.dir}/signals_${this.session}.json`;
    this.tradesFile = `${this.dir}/trades_${this.session}.json`;
  }

  appendJsonArray(file, record) {
    const arr = fs.existsSync(file)
      ? (() => {
          try { return JSON.parse(fs.readFileSync(file, 'utf-8')); }
          catch { return []; }
        })()
      : [];
    arr.push(record);
    fs.writeFileSync(file, JSON.stringify(arr, null, 2));
  }

  logSignal(signal, context) {
    const rec = {
      ...signal,
      price: context.price,
      wss: context.wss,
      regime: context.marketRegime,
      ts: new Date().toISOString()
    };
    this.appendJsonArray(this.signalsFile, rec);
  }

  logTrade(entryPrice, exitPrice, pnl, reason, side, strategy) {
    const trade = {
      side,
      strategy,
      entry: entryPrice.toNumber(),
      exit: exitPrice.toNumber(),
      pnl: pnl.toNumber(),
      reason,
      ts: new Date().toISOString()
    };
    this.appendJsonArray(this.tradesFile, trade);
  }
}
