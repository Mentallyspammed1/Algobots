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

    evaluate(price, signal, context) { 
        const px = new Decimal(price);
        this.lastPrice = price;

        if (this.pos) {
            const isFlip = signal.action !== 'HOLD' && signal.action !== this.pos.side;
            const slHit = (this.pos.side === 'BUY' && px.lte(this.pos.sl)) || (this.pos.side === 'SELL' && px.gte(this.pos.sl));
            const tpHit = (this.pos.side === 'BUY' && px.gte(this.pos.tp)) || (this.pos.side === 'SELL' && px.lte(this.pos.tp));

            if (isFlip || slHit || tpHit) {
                const reason = isFlip ? 'SIGNAL_FLIP' : (slHit ? 'STOP_LOSS' : 'TAKE_PROFIT');
                // Ensure close is awaited as it's now async
                this.close(px, reason).then(pnl => {
                    if (pnl !== 0) this.circuitBreaker.updatePnL(pnl);
                });
            }
            return;
        }
        
        // Corrected access to minConfidence
        if (signal.action === 'HOLD' || (signal.confidence || 0) < this.aiBrain.config.minConfidence) { 
            return;
        }

        this.open(px, signal, context); 
    }

    open(price, sig, context) { 
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

        this.pos = { 
            side: sig.action, 
            entry, 
            qty, 
            sl, 
            tp,
            entryContext: { ...context },
            aiDecision: { ...sig }
        };
        console.log(COLOR.GREEN(`[PaperExchange] PAPER OPEN ${sig.action} ${qty.toString()} @ ${entry.toFixed(2)} | TP: ${tp.toFixed(2)} SL: ${sl.toFixed(2)}`));
    }

    async close(price, reason) { // Make close async
        const p = this.pos;
        if (!p) return 0;
        
        const diff = p.side === 'BUY' ? price.sub(p.entry) : p.entry.sub(price);
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