// src/trading_ai_system.js
import 'dotenv/config';
import { config } from './config.js';
import BybitAPI from './api/bybit_api.js';
import { loadState, saveState, defaultState, getDecimalState } from './utils/state_manager.js';
import { calculatePositionSize, determineExitPrices } from './core/trading_logic.js';
import { applyRiskPolicy } from './core/risk_policy.js';
import logger from './utils/logger.js';
import { ACTIONS } from './core/constants.js';
import GeminiAPI from './api/gemini_api.js';
import FeatureEngineer from './features/feature_engineer.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for P&L calculations

// Helper to format the market context for the AI
function formatMarketContext(state, primaryIndicators, higherTfIndicators) {
    // IMPROVEMENT 15: Adjust safeFormat for Decimal.js
    const safeFormat = (value, precision) => {
        if (value instanceof Decimal) return value.toFixed(precision);
        if (typeof value === 'number' && !isNaN(value)) return new Decimal(value).toFixed(precision);
        return 'N/A';
    };

    let context = `## PRIMARY TIMEFRAME ANALYSIS (${config.primaryInterval}min)
`;
    context += formatIndicatorText(primaryIndicators);

    higherTfIndicators.forEach(htf => {
        context += `
## HIGHER TIMEFRAME CONTEXT (${htf.interval}min)
`;
        context += formatIndicatorText(htf.indicators);
    });

    if (state.inPosition) {
        // IMPROVEMENT 15: P&L calculation using Decimal.js
        const entryPrice = state.entryPrice;
        const quantity = state.quantity;
        const close = new Decimal(primaryIndicators.close); // Ensure close is Decimal
        
        const pnl = close.minus(entryPrice).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
        const pnlPercent = pnl.dividedBy(entryPrice.times(quantity)).times(100);
        context += `
## CURRENT POSITION
- **Status:** In a **${state.positionSide}** position.
- **Entry Price:** ${safeFormat(entryPrice, config.pricePrecision)}
- **Quantity:** ${safeFormat(quantity, config.quantityPrecision)}
- **Unrealized P/L:** ${safeFormat(pnl, 2)} USDT (${safeFormat(pnlPercent, 2)}%)`;
    } else {
        context += `
## CURRENT POSITION
- **Status:** FLAT (No open position).`;
    }
    // IMPROVEMENT 18: Add daily loss to context
    context += `
## DAILY RISK STATUS
- **Daily Loss:** ${safeFormat(state.dailyLoss, 2)} USDT (Limit: ${config.maxDailyLossPercentage}% of ${safeFormat(state.initialBalance, 2)} USDT)
`;
    return context;
}

function formatIndicatorText(indicators) {
    if (!indicators) return "  - No data available.\n";
    const { close, rsi, atr, macd, bb } = indicators;
    // IMPROVEMENT 15: Adjust safeFormat for Decimal.js
    const safeFormat = (value, precision) => {
        if (value instanceof Decimal) return value.toFixed(precision);
        if (typeof value === 'number' && !isNaN(value)) return new Decimal(value).toFixed(precision);
        return 'N/A';
    };


    let text = `  - **Price:** ${safeFormat(close, config.pricePrecision)}
`;
    if (rsi) text += `  - **Momentum (RSI):** ${safeFormat(rsi, 2)}
`;
    if (atr) text += `  - **Volatility (ATR):** ${safeFormat(atr, config.pricePrecision)}
`;
    if (macd) text += `  - **Trend (MACD Histogram):** ${safeFormat(macd.hist, 4)}
`;
    if (bb) text += `  - **Bollinger Bands:** Mid ${safeFormat(bb.mid, 2)}, Upper ${safeFormat(bb.upper, 2)}, Lower ${safeFormat(bb.lower, 2)}
`;
    return text;
}

class TradingAiSystem {
    constructor() {
        this.bybitApi = new BybitAPI(process.env.BYBIT_API_KEY, process.env.BYBIT_API_SECRET);
        this.geminiApi = new GeminiAPI(process.env.GEMINI_API_KEY);
        this.isProcessing = false;

        // NEW: Create persistent feature engineers for each timeframe
        this.featureEngineers = new Map();
        this.featureEngineers.set(config.primaryInterval, new FeatureEngineer());
        config.multiTimeframeIntervals.forEach(interval => {
            this.featureEngineers.set(interval, new FeatureEngineer());
        });
    }

    // NEW: Method to calculate indicators using the correct stateful engineer
    calculateIndicators(klines, interval) {
        const featureEngineer = this.featureEngineers.get(interval);
        if (!featureEngineer) {
            throw new Error(`No feature engineer found for interval: ${interval}`);
        }

        if (!klines || klines.length === 0) return null;
        const reversedKlines = [...klines].reverse();
        const formattedKlines = reversedKlines.map(k => ({
            t: parseInt(k[0]),
            o: parseFloat(k[1]),
            h: parseFloat(k[2]),
            l: parseFloat(k[3]),
            c: parseFloat(k[4]),
            v: parseFloat(k[5]),
        }));

        let lastFeature;
        for (const kline of formattedKlines) {
            lastFeature = featureEngineer.next(kline);
        }
        return lastFeature;
    }

    async runAnalysisCycle() {
        if (this.isProcessing) {
            logger.warn("Skipping analysis cycle: a previous one is still active.");
            return;
        }
        this.isProcessing = true;
        logger.info("=========================================");
        logger.info(`Starting new analysis cycle for ${config.symbol}...`);

        try {
            let state = await this.reconcileState();
            
            // IMPROVEMENT 20: Check if bot is in a HALT state
            if (state.isHalted) { // Assuming a `isHalted` flag could be added to state
                logger.warn(`Bot is currently HALTED due to risk policy. Reason: ${state.haltReason || 'Unknown'}. Skipping trading actions.`);
                return;
            }

            // IMPROVEMENT 18: Initialize initialBalance if not set
            if (state.initialBalance.isZero()) {
                const currentBalance = await this.bybitApi.getAccountBalance();
                if (currentBalance) {
                    state.initialBalance = new Decimal(currentBalance);
                    await saveState(state);
                    logger.info(`Initial balance set to ${state.initialBalance.toFixed(2)} USDT.`);
                } else {
                    logger.error("Could not retrieve initial account balance. Daily loss limit may not function correctly.");
                }
            }
            
            const allIntervals = [config.primaryInterval, ...config.multiTimeframeIntervals];
            const klinesPromises = allIntervals.map(interval => 
                this.bybitApi.getHistoricalMarketData(config.symbol, interval)
            );
            const klinesResults = await Promise.all(klinesPromises);

            const indicatorResults = klinesResults.map((result, i) => {
                const interval = allIntervals[i];
                if (!result || !result.list) {
                    logger.warn(`Failed to fetch market data for interval ${interval}.`);
                    return null;
                }
                return this.calculateIndicators(result.list, interval);
            });

            const primaryIndicators = indicatorResults[0];
            if (!primaryIndicators) {
                throw new Error("Failed to calculate primary indicators.");
            }

            const higherTfIndicators = indicatorResults.slice(1).map((indicators, i) => ({
                interval: config.multiTimeframeIntervals[i],
                indicators: indicators
            }));

            const marketContext = formatMarketContext(state, primaryIndicators, higherTfIndicators);
            // IMPROVEMENT 14: Pass position state to AI for dynamic prompting
            const aiDecision = await this.geminiApi.getTradeDecision(marketContext, state.inPosition, state.positionSide);
            const policyResult = applyRiskPolicy(aiDecision, primaryIndicators, state);

            // IMPROVEMENT 20: Handle HALT decision from risk policy
            if (policyResult.decision === ACTIONS.HALT) {
                logger.critical(`Risk policy HALT: ${policyResult.reason}. Bot operations suspended.`);
                // Update state to reflect HALT, and save.
                await saveState({ ...state, isHalted: true, haltReason: policyResult.reason });
                return; // Stop further processing
            }

            if (policyResult.decision === 'HOLD') {
                logger.info(`Decision: HOLD. Reason: ${policyResult.reason}`);
                return;
            }

            const { name, args } = policyResult.trade;
            if (name === ACTIONS.PROPOSE_TRADE) {
                await this.executeEntry(args, primaryIndicators);
            } else if (name === ACTIONS.PROPOSE_EXIT) {
                await this.executeExit(state, args);
            }
        } catch (error) {
            logger.exception(error);
        } finally {
            this.isProcessing = false;
            logger.info("Analysis cycle finished.");
            logger.info("=========================================\n");
        }
    }

    // Minor update to executeEntry to take state
    async executeEntry(args, indicators, state) {
        logger.info(`Executing ENTRY: ${args.side}. Reason: ${args.reasoning}`);
        const { side } = args;
        const price = new Decimal(indicators.close); // Ensure price is Decimal
        const atr = new Decimal(indicators.atr); // Ensure atr is Decimal

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");
        const balanceDecimal = new Decimal(balance); // Convert balance to Decimal

        const { stopLoss, takeProfit } = determineExitPrices(price, side, atr, this.bybitApi.getPricePrecision());
        const quantity = calculatePositionSize(balanceDecimal, price, stopLoss, this.bybitApi.getQtyPrecision(), this.bybitApi.getMinOrderQty());

        if (quantity.lte(0)) { // Use lte for Decimal
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol, side, qty: quantity, takeProfit, stopLoss, 
        });

        if (orderResult && orderResult.orderId) {
            await saveState({
                ...state, // Persist other state values
                inPosition: true, positionSide: side, entryPrice: price.toString(), // Store as string
                quantity: quantity.toString(), orderId: orderResult.orderId,
                lastTradeTimestamp: 0, // Reset cooldown timer on entry (0 or current time for new cooldown)
                openPositionsCount: (state.openPositionsCount || 0) + 1, // Increment count
                // Add initialBalance if it's the first trade for the day/session
                initialBalance: state.initialBalance === '0' ? balanceDecimal.toString() : state.initialBalance
            });
            logger.info(`Successfully placed ENTRY order. Order ID: ${orderResult.orderId}`);
        }
    }
    
    async executeExit(state, args) {
        logger.info(`Executing EXIT from ${state.positionSide} position. Reason: ${args.reasoning}`);
        const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide);

        if (closeResult && closeResult.orderId) {
            // Calculate PnL for daily loss tracking
            // This is a simplified PnL calculation; a full system would use exchange data for realized PnL.
            const currentPrice = new Decimal(this.featureEngineers.get(config.primaryInterval).last.close);
            const entryPrice = new Decimal(state.entryPrice);
            const quantity = new Decimal(state.quantity);
            const positionPnl = (currentPrice.minus(entryPrice)).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
            
            const newDailyLoss = new Decimal(state.dailyLoss).plus(positionPnl.lt(0) ? positionPnl.abs() : 0); // Add absolute loss if PnL is negative

            await saveState({
                ...defaultState, // Reset to default state
                lastTradeTimestamp: Date.now(), // Set cooldown
                dailyLoss: newDailyLoss.toString(), // Update daily loss
                dailyPnlResetDate: state.dailyPnlResetDate, // Keep current day for PnL
                initialBalance: state.initialBalance, // Keep initial balance
                openPositionsCount: Math.max(0, (state.openPositionsCount || 1) - 1), // Decrement count
            });
            logger.info(`Successfully placed EXIT order. Order ID: ${closeResult.orderId}. Position P&L: ${positionPnl.toFixed(2)}.`);
        }
    }

    async reconcileState() {
        logger.info("Reconciling local state with exchange...");
        const localState = await loadState(); // IMPROVEMENT 18: Load state as Decimal.js objects
        if (config.dryRun) {
            logger.info("[DRY RUN] Skipping remote state reconciliation.");
            return localState;
        }

        const exchangePosition = await this.bybitApi.getCurrentPosition(config.symbol);
        // IMPROVEMENT 20: Reconcile open orders (e.g., pending TP/SL orders)
        // This is a more complex task. For now, we'll assume TP/SL are OCO or managed by Bybit.
        // A full implementation would fetch open orders and update localState.openOrders array.

        if (exchangePosition) {
            const exchangeQty = new Decimal(exchangePosition.size);
            const exchangeAvgPrice = new Decimal(exchangePosition.avgPrice);
            const exchangeSide = exchangePosition.side;

            // Check for discrepancies and update
            if (!localState.inPosition || !localState.quantity.eq(exchangeQty) || !localState.entryPrice.eq(exchangeAvgPrice) || localState.positionSide !== exchangeSide) {
                logger.warn("State discrepancy detected! Recovering state from exchange.");
                const recoveredState = {
                    ...localState, 
                    inPosition: true,
                    positionSide: exchangeSide,
                    entryPrice: exchangeAvgPrice,
                    quantity: exchangeQty,
                    orderId: localState.orderId, // Preserve local order ID if known, or fetch from exchange if possible
                    openPositionsCount: 1,
                };
                await saveState(recoveredState);
                return recoveredState;
            }
            logger.info(`State confirmed: In ${exchangePosition.side} position (Qty: ${exchangeQty.toFixed(this.bybitApi.getQtyPrecision())}, Avg Price: ${exchangeAvgPrice.toFixed(this.bybitApi.getPricePrecision())}).`);
            return localState;
        } else {
            // If no position on exchange, but local state says there is one
            if (localState.inPosition) {
                logger.warn("State discrepancy! Position closed on exchange. Resetting local state.");
                const newState = { 
                    ...defaultState, 
                    lastTradeTimestamp: Date.now(),
                    initialBalance: localState.initialBalance, // Preserve initial balance
                    dailyLoss: localState.dailyLoss, // Preserve daily loss
                    dailyPnlResetDate: localState.dailyPnlResetDate, // Preserve reset date
                };
                await saveState(newState);
                return newState;
            }
            logger.info("State confirmed: No open position.");
            return localState;
        }
    }
}

export default TradingAiSystem;
