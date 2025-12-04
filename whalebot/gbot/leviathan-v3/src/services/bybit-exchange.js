import { RestClientV5 } from 'bybit-api';
import { Decimal } from 'decimal.js';
import { COLOR } from '../ui.js';
import * as Utils from '../utils.js';

class BaseExchange {
    getBalance() { return this.balance; }
    getPos() { return this.pos; }
    getSymbol() { return this.symbol; }
}

/**
 * Live Bybit exchange interaction, now using the official bybit-api library.
 */
export class LiveBybitExchange extends BaseExchange {
    constructor(config) {
        super();
        this.config = config;
        this.symbol = config.symbol;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        if (!this.apiKey || !this.apiSecret) {
            throw new Error("[LiveBybitExchange] MISSING BYBIT API KEYS.");
        }

        // Initialize the REST client from the official library
        this.client = new RestClientV5({
            key: this.apiKey,
            secret: this.apiSecret,
        });

        this.pos = null;
        this.balance = 0;
        this.updateWallet();
    }

    async updateWallet() {
        try {
            const res = await this.client.getWalletBalance({ accountType: 'UNIFIED', coin: 'USDT' });
            if (res.retCode === 0 && res.result?.list?.[0]?.coin?.[0]?.walletBalance) {
                this.balance = parseFloat(res.result.list[0].coin[0].walletBalance);
            } else {
                 throw new Error(res.retMsg);
            }
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to update wallet: ${e.message}`));
            this.balance = 0;
        }
    }

    async execute(price, signal) {
        if (signal.action === 'HOLD') return;

        try {
            await this.updateWallet();
            
            const qty = Utils.calcSize(this.balance, price, signal.sl, this.config.risk.maxRiskPerTrade);
            if (qty.lte(0)) {
                console.warn(COLOR.YELLOW(`[LiveBybitExchange] Calculated quantity is zero or less. Holding.`));
                return;
            }

            await this.client.setLeverage({
                category: 'linear', 
                symbol: this.symbol, 
                buyLeverage: this.config.risk.leverage.toString(), 
                sellLeverage: this.config.risk.leverage.toString() 
            });

            const orderParams = {
                category: 'linear',
                symbol: this.symbol,
                side: signal.action === 'BUY' ? 'Buy' : 'Sell',
                orderType: 'Market',
                qty: qty.toString(),
                stopLoss: new Decimal(signal.sl).toFixed(2), // Ensure SL/TP are formatted correctly
                takeProfit: new Decimal(signal.tp).toFixed(2),
                timeInForce: 'GTC',
            };
            
            const res = await this.client.submitOrder(orderParams);

            if (res.retCode === 0) {
                console.log(COLOR.GREEN(`[LiveBybitExchange] LIVE ORDER SENT: ${signal.action} ${qty.toString()} | OrderID: ${res.result.orderId}`));
            } else {
                throw new Error(`Error ${res.retCode}: ${res.retMsg}`);
            }

        } catch (e) {
             console.error(COLOR.RED(`[LiveBybitExchange] Failed to place live order: ${e.message}`));
        }
    }
    
    async close(price) { 
        // Close logic would also use the client, e.g., by submitting an opposing order.
        // This is complex and depends on position state, so leaving as a placeholder.
        console.log(COLOR.PURPLE(`[LIVE] Position Close function called.`));
        return 0; 
    }
}

/**
 * Paper trading exchange, remains unchanged.
 */
export class PaperExchange extends BaseExchange {
    constructor(config, circuitBreaker) {
        super();
        this.cfg = config.risk;
        this.symbol = config.symbol;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
        this.lastPrice = 0;
        this.circuitBreaker = circuitBreaker;
    }

    evaluate(price, signal) {
        const px = new Decimal(price);
        this.lastPrice = price;

        if (this.pos) {
            const isFlip = signal.action !== 'HOLD' && signal.action !== this.pos.side;
            const slHit = (this.pos.side === 'BUY' && px.lte(this.pos.sl)) || (this.pos.side === 'SELL' && px.gte(this.pos.sl));
            const tpHit = (this.pos.side === 'BUY' && px.gte(this.pos.tp)) || (this.pos.side === 'SELL' && px.lte(this.pos.tp));

            if (isFlip || slHit || tpHit) {
                const reason = isFlip ? 'SIGNAL_FLIP' : (slHit ? 'STOP_LOSS' : 'TAKE_PROFIT');
                const pnl = this.close(px, reason);
                if (pnl !== 0) this.circuitBreaker.updatePnL(pnl);
            }
            return;
        }
        
        if (signal.action === 'HOLD' || (signal.confidence || 0) < this.cfg.minConfidence) {
            return;
        }

        this.open(px, signal);
    }

    open(price, sig) {
        const entry = new Decimal(price);
        let sl = new Decimal(sig.sl);
        let tp = new Decimal(sig.tp);

        if (sl.eq(0) || tp.eq(0)) {
            console.warn(COLOR.YELLOW(`[PaperExchange] AI provided invalid SL/TP. Holding.`));
            return;
        }

        const qty = Utils.calcSize(this.balance, entry, sl, this.cfg.maxRiskPerTrade);
        if (qty.lte(0)) {
            console.warn(COLOR.YELLOW(`[PaperExchange] Calculated quantity is zero. Holding.`));
            return;
        }

        this.pos = { side: sig.action, entry, qty, sl, tp };
        console.log(COLOR.GREEN(`[PaperExchange] PAPER OPEN ${sig.action} ${qty.toString()} @ ${entry.toFixed(2)} | TP: ${tp.toFixed(2)} SL: ${sl.toFixed(2)}`));
    }

    close(price, reason) {
        const p = this.pos;
        if (!p) return 0;
        
        const diff = p.side === 'BUY' ? price.sub(p.entry) : p.entry.sub(price);
        const pnl = diff.mul(p.qty).mul(new Decimal(1).sub(this.cfg.fee).sub(this.cfg.slippage));
        
        this.balance = this.balance.add(pnl);
        const col = pnl.gte(0) ? COLOR.GREEN : COLOR.RED;
        
        console.log(col(`[PaperExchange] ${reason}: PnL ${pnl.toFixed(2)} | New Bal: ${this.balance.toFixed(2)}`));
        
        this.pos = null;
        return pnl.toNumber();
    }
}