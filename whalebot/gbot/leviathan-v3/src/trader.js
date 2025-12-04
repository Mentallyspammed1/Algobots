/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v3.5 (Refactored)
 * ======================================================
 * Trader Module
 *
 * This module handles all trade execution logic, including order placement
 * and interaction with the circuit breaker.
 */

import { COLOR } from './ui.js';

export class Trader {
    constructor(exchange, circuitBreaker, config) {
        this.exchange = exchange;
        this.circuitBreaker = circuitBreaker;
        this.config = config;
    }

    async execute(aiDecision, state) {
        const { currentPrice, position } = state;
        let orderResult = null;
        let newPosition = position;
        let newEntryPrice = state.entryPrice;

        if (this.circuitBreaker.isOpen()) {
            console.warn(COLOR.RED(`[Trader] Circuit breaker is OPEN. Skipping trade execution.`));
            return { orderResult, newPosition, newEntryPrice };
        }

        const canBuy = aiDecision.decision === 'BUY' && aiDecision.confidence > this.config.ai.minConfidence && position === 'none';
        const canSell = aiDecision.decision === 'SELL' && aiDecision.confidence > this.config.ai.minConfidence && position === 'long';

        if (canBuy) {
            const amount = this.config.trade_amount_usd / currentPrice;
            const order = await this.exchange.placeOrder(this.config.symbol, 'Buy', amount, currentPrice, { type: 'Market', timeInForce: 'GTC' });
            if (order) {
                newPosition = 'long';
                newEntryPrice = currentPrice;
                orderResult = order;
                console.log(COLOR.GREEN(`[Trader] BUY Order placed: ${JSON.stringify(order)}`));
            }
        } else if (canSell) {
            const amount = this.config.trade_amount_usd / currentPrice;
            const order = await this.exchange.placeOrder(this.config.symbol, 'Sell', amount, currentPrice, { type: 'Market', timeInForce: 'GTC' });
            if (order) {
                newPosition = 'none';
                newEntryPrice = null;
                orderResult = order;
                console.log(COLOR.RED(`[Trader] SELL Order placed: ${JSON.stringify(order)}`));
            }
        } else {
            console.log(COLOR.GRAY(`[Trader] No trade executed.`));
        }

        return { orderResult, newPosition, newEntryPrice };
    }
}
