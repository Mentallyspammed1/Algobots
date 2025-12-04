import axios from 'axios';
import crypto from 'crypto';
import { Decimal } from 'decimal.js';
import { COLOR } from '../ui.js';
import * as Utils from '../utils.js';

class BaseExchange {
    getBalance() { return this.balance; }
    getPos() { return this.pos; }
    getSymbol() { return this.symbol; }
}

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
        this.client = axios.create({ baseURL: 'https://api.bybit.com'});
        this.pos = null;
        this.balance = 0;
        this.updateWallet();
    }

    async signRequest(method, endpoint, params) {
        const ts = Date.now().toString();
        const recvWindow = '5000';
        const payload = method === 'GET' ? new URLSearchParams(params).toString() : JSON.stringify(params);
        const signStr = ts + this.apiKey + recvWindow + payload;
        const signature = crypto.createHmac('sha256', this.apiSecret).update(signStr).digest('hex');
        return {
            'X-BAPI-API-KEY': this.apiKey, 'X-BAPI-TIMESTAMP': ts, 'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': recvWindow, 'Content-Type': 'application/json'
        };
    }

    async apiCall(method, endpoint, params = {}) {
        const headers = await this.signRequest(method, endpoint, params);
        try {
            const res = method === 'GET'
                ? await this.client.get(endpoint, { headers, params })
                : await this.client.post(endpoint, params, { headers });
            if (res.data.retCode !== 0) {
                throw new Error(`Bybit API Error ${res.data.retCode}: ${res.data.retMsg}`);
            }
            return res.data.result;
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] API Call Error (${method} ${endpoint}): ${e.message}`));
            return null;
        }
    }

    async updateWallet() {
        try {
            const res = await this.apiCall('GET', '/v5/account/wallet-balance', { accountType: 'UNIFIED', coin: 'USDT' });
            if (res?.list?.[0]?.coin?.[0]?.walletBalance) {
                this.balance = parseFloat(res.list[0].coin[0].walletBalance);
            }
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to update wallet: ${e.message}`));
            this.balance = 0;
        }
    }

    async execute(price, signal) {
        await this.updateWallet();
        // Position management logic would go here
        if (signal.action === 'HOLD') return;

        const qty = Utils.calcSize(this.balance, price, signal.sl, this.config.risk.maxRiskPerTrade);
        if (qty.lte(0)) return;

        await this.apiCall('POST', '/v5/position/set-leverage', { 
            category: 'linear', 
            symbol: this.symbol, 
            buyLeverage: this.config.risk.leverage.toString(), 
            sellLeverage: this.config.risk.leverage.toString() 
        });

        const side = signal.action === 'BUY' ? 'Buy' : 'Sell';
        const orderParams = {
            category: 'linear', symbol: this.symbol, side, orderType: 'Market',
            qty: qty.toString(), 
            stopLoss: new Decimal(signal.sl).toString(), 
            takeProfit: new Decimal(signal.tp).toString(), 
            timeInForce: 'GTC'
        };
        const res = await this.apiCall('POST', '/v5/order/create', orderParams);

        if (res) console.log(COLOR.GREEN(`[LiveBybitExchange] LIVE ORDER SENT: ${signal.action} ${qty.toString()}`));
        else console.error(COLOR.RED(`[LiveBybitExchange] Failed to place live order.`));
    }
     async close(price) { /* ... */ return 0; }
}

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
