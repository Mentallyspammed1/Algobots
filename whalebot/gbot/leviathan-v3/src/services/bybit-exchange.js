import { RestClientV5 } from 'bybit-api';
import { Decimal } from 'decimal.js';
import fs from 'fs/promises'; // Import fs for journaling
import { COLOR } from '../ui.js';
import * as Utils from '../utils.js';

// Helper to append to the journal
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
    // ... (LiveBybitExchange remains unchanged for now)
    constructor(config) {
        super();
        this.config = config;
        this.symbol = config.symbol;
        this.apiKey = process.env.BYBIT_API_KEY;
        this.apiSecret = process.env.BYBIT_API_SECRET;
        if (!this.apiKey || !this.apiSecret) {
            throw new Error("[LiveBybitExchange] MISSING BYBIT API KEYS.");
        }
        this.client = new RestClientV5({ key: this.apiKey, secret: this.apiSecret });
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

    async execute(price, signal, context) {
        // In a real implementation, the context would be saved here for journaling
        if (signal.action === 'HOLD') return;
        // ... live trading logic
    }
     async close(price) { /* ... */ return 0; }
}

export class PaperExchange extends BaseExchange {
    // Add aiBrain to constructor parameters
    constructor(config, circuitBreaker, aiBrain) {
        super();
        this.cfg = config.risk;
        this.symbol = config.symbol;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
        this.lastPrice = 0;
        this.circuitBreaker = circuitBreaker;
        this.aiBrain = aiBrain; // Store the AI brain instance
    }

    async placeOrder(symbol, side, amount, price, params = {}) {
        const priceDec = new Decimal(price);
        const qty = new Decimal(amount);

        if (side === 'Buy') {
            if (this.pos) {
                console.warn(COLOR.YELLOW(`[PaperExchange] Attempted to BUY while already in a position. Ignoring.`));
                return null;
            }

            // Default rewardRatio if not in config
            const rewardRatio = this.cfg.rewardRatio || 1.5;
            const slPrice = priceDec.times(new Decimal(1).minus(new Decimal(this.cfg.maxRiskPerTrade).div(100)));
            const tpPrice = priceDec.times(new Decimal(1).plus(new Decimal(this.cfg.maxRiskPerTrade * rewardRatio).div(100)));

            this.pos = { 
                side: 'long', 
                entry: priceDec, 
                qty, 
                sl: slPrice, 
                tp: tpPrice,
                entryContext: { price: price, timestamp: Date.now() },
                aiDecision: { decision: 'BUY', from: 'refactored_trader' }
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
                qty: this.pos?.qty?.toString() || amount.toString(),
                price: priceDec.toString(),
                orderStatus: 'Filled',
                pnl 
            };
        }
        return null;
    }

    async close(price, reason) { // Make close async
        const p = this.pos;
        if (!p) return 0;
        
        const diff = p.side === 'long' ? price.sub(p.entry) : p.entry.sub(price);
        const pnl = diff.mul(p.qty).mul(new Decimal(1).sub(this.cfg.fee).sub(this.cfg.slippage));
        
        this.balance = this.balance.add(pnl);
        const col = pnl.gte(0) ? COLOR.GREEN : COLOR.RED;
        
        console.log(col(`[PaperExchange] ${reason}: PnL ${pnl.toFixed(2)} | New Bal: ${this.balance.toFixed(2)}`));
        
        // --- NEW: Create and save journal entry ---
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
            aiAnalysis = await this.aiBrain.analyzeTrade(tradeDetails); // Call AI for analysis
        } catch (e) {
            console.error(COLOR.RED(`[PaperExchange] Error during AI post-trade analysis: ${e.message}`));
        }

        const journalEntry = {
            timestamp: new Date().toISOString(),
            ...tradeDetails, // Include all tradeDetails
            aiAnalysis: aiAnalysis // Add AI analysis to the journal entry
        };
        await appendToJournal(journalEntry); // Await journal write
        
        this.pos = null;
        return pnl.toNumber();
    }
}