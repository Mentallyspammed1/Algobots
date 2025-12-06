import { RestClientV5 } from 'bybit-api';
import { Decimal } from 'decimal.js';
import fs from 'fs/promises';
import { COLOR } from '../ui.js';
import * as Utils from '../utils.js';

async function appendToJournal(entry) {
    try {
        await fs.appendFile('trade-journal.jsonl', JSON.stringify(entry) + '\n');
    } catch (e) {
        console.error(COLOR.RED(`[Journal] Failed to write to journal: ${e.message}`));
    }
}

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
        this.client = new RestClientV5({ key: this.apiKey, secret: this.apiSecret, testnet: false });
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

    async placeOrder(symbol, side, amount, price, params) {
        try {
            const orderRequest = {
                category: 'linear',
                symbol,
                side,
                orderType: params.type || 'Market',
                qty: amount.toString(),
                price: params.type === 'Limit' ? price.toString() : undefined,
                timeInForce: params.timeInForce || 'GTC',
            };

            if (params.sl && params.sl > 0) {
                orderRequest.stopLoss = params.sl.toString();
            }
            if (params.tp && params.tp > 0) {
                orderRequest.takeProfit = params.tp.toString();
            }

            const order = await this.client.submitOrder(orderRequest);
            return order;
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to place order: ${e.message}`));
            return null;
        }
    }

    async getFundingRate() {
        try {
            const res = await this.client.getFundingRateHistory({ category: 'linear', symbol: this.symbol, limit: 1 });
            if (res.retCode === 0 && res.result.list?.[0]?.fundingRate) {
                return parseFloat(res.result.list[0].fundingRate);
            }
            return 0;
        } catch (e) {
            console.error(COLOR.RED(`[LiveBybitExchange] Failed to get funding rate: ${e.message}`));
            return 0;
        }
    }

    async maintainPosition(price) {
        return { positionClosed: false };
    }
}

export class PaperExchange extends BaseExchange {
    constructor(config, circuitBreaker, aiBrain) {
        super();
        this.cfg = config.risk;
        this.symbol = config.symbol;
        this.balance = new Decimal(this.cfg.initialBalance || 10000);
        this.startBal = this.balance;
        this.pos = null;
        this.lastPrice = 0;
        this.circuitBreaker = circuitBreaker;
        this.aiBrain = aiBrain;
    }

    getFundingRate() {
        return 0; // No real funding in paper mode
    }

    async placeOrder(symbol, side, amount, price, params = {}) {
        const priceDec = new Decimal(price);
        const qty = new Decimal(amount);

        if (side === 'Buy') {
            if (this.pos) {
                console.warn(COLOR.YELLOW(`[PaperExchange] Attempted to BUY while already in a position. Ignoring.`));
                return null;
            }

            // Use AI-provided SL/TP if available, otherwise fall back to calculated ones
            const slPrice = params.sl && params.sl > 0 
                ? new Decimal(params.sl) 
                : priceDec.times(new Decimal(1).minus(new Decimal(this.cfg.maxRiskPerTrade).div(100)));
            
            const tpPrice = params.tp && params.tp > 0
                ? new Decimal(params.tp)
                : priceDec.times(new Decimal(1).plus(new Decimal(this.cfg.maxRiskPerTrade * (this.cfg.rewardRatio || 1.5)).div(100)));

            this.pos = { 
                side: 'long', 
                entry: priceDec, 
                qty, 
                sl: slPrice, 
                tp: tpPrice,
                entryContext: { price: price, timestamp: Date.now() },
                aiDecision: params.aiDecision || { decision: 'BUY', from: 'paper_trader' }
            };
            
            const order = {
                orderId: `paper-buy-${Date.now()}`,
                symbol: this.symbol,
                side: 'Buy',
                qty: qty.toString(),
                price: priceDec.toString(),
                orderStatus: 'Filled'
            };

            console.log(COLOR.GREEN(`[PaperExchange] PAPER OPEN LONG: ${order.qty} @ ${order.price} | TP: ${this.pos.tp.toFixed(2)} SL: ${this.pos.sl.toFixed(2)}`));
            return order;

        } else if (side === 'Sell') {
            if (!this.pos) {
                console.warn(COLOR.YELLOW(`[PaperExchange] Attempted to SELL with no open position. Ignoring.`));
                return null;
            }

            const pnl = await this.close(priceDec, 'SIGNAL_SELL');
            
            return { 
                orderId: `paper-sell-${Date.now()}`,
                symbol: this.symbol,
                side: 'Sell',
                qty: amount.toString(),
                price: priceDec.toString(),
                orderStatus: 'Filled',
                pnl 
            };
        }
        return null;
    }
    
    async maintainPosition(currentPrice) {
        if (this.pos) {
            const px = new Decimal(currentPrice);

            const slHit = (this.pos.side === 'long' && px.lte(this.pos.sl));
            const tpHit = (this.pos.side === 'long' && px.gte(this.pos.tp));

            if (slHit || tpHit) {
                const reason = slHit ? 'STOP_LOSS' : 'TAKE_PROFIT';
                const pnl = await this.close(px, reason);
                return { positionClosed: true, pnl: pnl };
            }
        }
        return { positionClosed: false };
    }

    async close(price, reason) {
        const p = this.pos;
        if (!p) return 0;
        
        const diff = p.side === 'long' ? price.sub(p.entry) : p.entry.sub(price);
        const pnl = diff.mul(p.qty).mul(new Decimal(1).sub(this.cfg.fee || 0).sub(this.cfg.slippage || 0));
        
        this.balance = this.balance.add(pnl);
        const col = pnl.gte(0) ? COLOR.GREEN : COLOR.RED;
        
        console.log(col(`[PaperExchange] ${reason}: PnL ${pnl.toFixed(2)} | New Bal: ${this.balance.toFixed(2)}`));
        
        const tradeDetails = {
            symbol: this.symbol,
            side: p.side,
            entry: p.entry.toNumber(),
            exit: price.toNumber(),
            pnl: pnl.toNumber(),
            exitReason: reason,
            entryContext: p.entryContext,
            aiDecision: p.aiDecision
        };

        let aiAnalysis = 'No AI analysis available.';
        try {
            if (this.aiBrain) {
                aiAnalysis = await this.aiBrain.analyzeTrade(tradeDetails);
            }
        } catch (e) {
            console.error(COLOR.RED(`[PaperExchange] Error during AI post-trade analysis: ${e.message}`));
        }

        const journalEntry = {
            timestamp: new Date().toISOString(),
            ...tradeDetails,
            aiAnalysis: aiAnalysis
        };
        await appendToJournal(journalEntry);
        
        this.pos = null;
        return pnl.toNumber();
    }
}