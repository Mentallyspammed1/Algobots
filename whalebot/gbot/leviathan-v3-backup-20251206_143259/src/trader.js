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

    _calculateRiskSize(signal, price, balance) {
        if (balance <= 0 || !signal.sl || signal.sl <= 0) return 0;
        
        const riskAmount = balance * (this.config.risk.maxRiskPerTrade / 100);
        const stopDistance = Math.abs(price - signal.sl);
        if (stopDistance === 0) return 0;

        const qty = riskAmount / stopDistance;
        
        // Cap by leverage
        const maxQty = (balance * this.config.risk.leverage) / price;
        
        return Math.min(qty, maxQty);
    }

    async _checkFundingSafe(action) {
        const rate = await this.exchange.getFundingRate();
        // Funding is paid every 8 hours. A rate of 0.05% is high.
        const highFundingThreshold = 0.0005;

        if (action === 'BUY' && rate > highFundingThreshold) {
            console.warn(COLOR.YELLOW(`[Trader] Funding Filter: High positive funding rate (${(rate * 100).toFixed(4)}%). Skipping BUY.`));
            return false;
        }
        if (action === 'SELL' && rate < -highFundingThreshold) {
            console.warn(COLOR.YELLOW(`[Trader] Funding Filter: High negative funding rate (${(rate * 100).toFixed(4)}%). Skipping SELL.`));
            return false;
        }
        return true;
    }

    async _placeIcebergOrder(signal, entryPrice, totalQty) {
        const slices = this.config.risk.iceberg.slices || 3;
        if (slices <= 1) { // Just place a single limit order if slices is not > 1
             return this.exchange.placeOrder(
                this.config.symbol, 'Buy', totalQty, entryPrice,
                { type: 'Limit', timeInForce: 'PostOnly', sl: signal.sl, tp: signal.tp, aiDecision: signal }
            );
        }

        const sliceQty = (totalQty / slices).toFixed(5);
        const tickSize = 0.1; // This should ideally come from exchange info
        
        console.log(COLOR.CYAN(`[Trader] Iceberg execution: Slicing ${totalQty} into ${slices} orders...`));

        let orderPromises = [];
        for (let i = 0; i < slices; i++) {
            const offset = i * tickSize * 0.2;
            const slicePrice = entryPrice - offset; // Place orders slightly below for buys to act as maker

            orderPromises.push(
                this.exchange.placeOrder(
                    this.config.symbol, 'Buy', sliceQty, slicePrice,
                    { type: 'Limit', timeInForce: 'PostOnly', sl: signal.sl, tp: signal.tp, aiDecision: signal }
                )
            );
            // Small delay between orders
            await new Promise(r => setTimeout(r, 200));
        }
        
        const results = await Promise.all(orderPromises);
        console.log(COLOR.GREEN(`[Trader] Iceberg orders sent.`));
        return results.find(r => r); // Return the first successful order for logging
    }

    async execute(aiDecision, state) {
        const { currentPrice, position, balance, consecutiveLosses } = state;
        let orderResult = null;
        let newPosition = position;
        let newEntryPrice = state.entryPrice;

        if (this.circuitBreaker.isOpen()) {
            console.warn(COLOR.RED(`[Trader] Circuit breaker is OPEN. Skipping trade execution.`));
            return { orderResult, newPosition, newEntryPrice };
        }

        const loss_streak_threshold = this.config.risk.loss_streak_threshold || 3;
        if (consecutiveLosses >= loss_streak_threshold) {
            console.warn(COLOR.YELLOW(`[Trader] Paused due to ${consecutiveLosses} consecutive losses.`));
            return { orderResult, newPosition, newEntryPrice };
        }

        const canBuy = aiDecision.decision === 'BUY' && aiDecision.confidence > this.config.ai.minConfidence && position === 'none';
        const canSell = aiDecision.decision === 'SELL' && aiDecision.confidence > this.config.ai.minConfidence && position === 'long';

        if (canBuy) {
            if (!await this._checkFundingSafe('BUY')) {
                return { orderResult, newPosition, newEntryPrice };
            }
            const amount = this._calculateRiskSize(aiDecision, currentPrice, balance);
            if (amount > 0) {
                const entryPrice = aiDecision.aiEntry > 0 ? aiDecision.aiEntry : currentPrice;
                
                let order;
                if (this.config.risk.iceberg.enabled) {
                    order = await this._placeIcebergOrder(aiDecision, entryPrice, amount);
                } else {
                    order = await this.exchange.placeOrder(
                        this.config.symbol, 
                        'Buy', 
                        amount, 
                        entryPrice, 
                        { 
                            type: 'Limit', 
                            timeInForce: 'GTC', // GoodTillCancel for a single limit order
                            sl: aiDecision.sl,
                            tp: aiDecision.tp,
                            aiDecision: aiDecision
                        }
                    );
                }

                if (order) {
                    newPosition = 'long';
                    newEntryPrice = entryPrice; // Use intended entry price
                    orderResult = order;
                    console.log(COLOR.GREEN(`[Trader] BUY Order placed: ${JSON.stringify(order)}`));
                }
            }
        } else if (canSell) {
             if (!await this._checkFundingSafe('SELL')) {
                return { orderResult, newPosition, newEntryPrice };
            }
            const currentPosition = await this.exchange.getPos();
            const amount = currentPosition?.qty || this._calculateRiskSize(aiDecision, currentPrice, balance); // Use existing position size if available
            if (amount > 0) {
                const order = await this.exchange.placeOrder(
                    this.config.symbol, 
                    'Sell', 
                    amount, 
                    currentPrice, 
                    { 
                        type: 'Market', 
                        timeInForce: 'GTC' 
                    }
                );
                if (order) {
                    newPosition = 'none';
                    newEntryPrice = null;
                    orderResult = order;
                    console.log(COLOR.RED(`[Trader] SELL Order placed: ${JSON.stringify(order)}`));
                }
            }
        } else {
            // console.log(COLOR.GRAY(`[Trader] No trade executed.`));
        }

        return { orderResult, newPosition, newEntryPrice };
    }
}
