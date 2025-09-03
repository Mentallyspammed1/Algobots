// src/trading_ai_system.js
import 'dotenv/config';
import { config } from './config.js';
import BybitAPI from './api/bybit_api.js';
import { loadState, saveState, defaultState } from './utils/state_manager.js';
import { calculatePositionSize, determineExitPrices } from './core/trading_logic.js';
import { applyRiskPolicy } from './core/risk_policy.js';
import logger from './utils/logger.js';
import { ACTIONS } from './core/constants.js';
import GeminiAPI from './api/gemini_api.js';
import FeatureEngineer from './features/feature_engineer.js';

// Helper to format the market context for the AI
function formatMarketContext(state, primaryIndicators, higherTfIndicators) {
    const safeFormat = (value, precision) => (typeof value === 'number' && !isNaN(value) ? value.toFixed(precision) : 'N/A');

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
        const pnl = (primaryIndicators.close - state.entryPrice) * state.quantity * (state.positionSide === 'Buy' ? 1 : -1);
        const pnlPercent = (pnl / (state.entryPrice * state.quantity)) * 100;
        context += `
## CURRENT POSITION
- **Status:** In a **${state.positionSide}** position.
- **Entry Price:** ${safeFormat(state.entryPrice, config.pricePrecision)}
- **Unrealized P/L:** ${safeFormat(pnl, 2)} USDT (${safeFormat(pnlPercent, 2)}%)`;
    } else {
        context += "\n## CURRENT POSITION\n- **Status:** FLAT (No open position).";
    }
    return context;
}

function formatIndicatorText(indicators) {
    if (!indicators) return "  - No data available.\n";
    const { close, rsi, atr, macd, bb } = indicators;
    const safeFormat = (value, precision) => (typeof value === 'number' && !isNaN(value) ? value.toFixed(precision) : 'N/A');

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
            const state = await this.reconcileState();
            
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
            const aiDecision = await this.geminiApi.getTradeDecision(marketContext);
            const policyResult = applyRiskPolicy(aiDecision, primaryIndicators, state);

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

    async executeEntry(args, indicators) {
        logger.info(`Executing ENTRY: ${args.side}. Reason: ${args.reasoning}`);
        const { side } = args;
        const price = indicators.close;
        const atr = indicators.atr;

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");

        const { stopLoss, takeProfit } = determineExitPrices(price, side, atr);
        const quantity = calculatePositionSize(balance, price, stopLoss);

        if (quantity <= 0) {
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol, side, qty: quantity, takeProfit, stopLoss, 
        });

        if (orderResult && orderResult.orderId) {
            await saveState({
                inPosition: true, positionSide: side, entryPrice: price,
                quantity: quantity, orderId: orderResult.orderId,
                lastTradeTimestamp: 0 // Reset cooldown timer on entry
            });
            logger.info(`Successfully placed ENTRY order. Order ID: ${orderResult.orderId}`);
        }
    }
    
    async executeExit(state, args) {
        logger.info(`Executing EXIT from ${state.positionSide} position. Reason: ${args.reasoning}`);
        const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide);

        if (closeResult && closeResult.orderId) {
            await saveState({ ...defaultState, lastTradeTimestamp: Date.now() });
            logger.info(`Successfully placed EXIT order. Order ID: ${closeResult.orderId}`);
        }
    }

    async reconcileState() {
        logger.info("Reconciling local state with exchange...");
        const localState = await loadState();
        if (config.dryRun) {
            logger.info("[DRY RUN] Skipping remote state reconciliation.");
            return localState;
        }

        const exchangePosition = await this.bybitApi.getCurrentPosition(config.symbol);

        if (exchangePosition) {
            if (!localState.inPosition || localState.positionSide !== exchangePosition.side) {
                logger.warn("State discrepancy! Recovering state from exchange.");
                const recoveredState = {
                    ...localState, 
                    inPosition: true,
                    positionSide: exchangePosition.side,
                    entryPrice: parseFloat(exchangePosition.avgPrice),
                    quantity: parseFloat(exchangePosition.size),
                    orderId: localState.orderId, 
                };
                await saveState(recoveredState);
                return recoveredState;
            }
            logger.info(`State confirmed: In ${exchangePosition.side} position.`);
            return localState;
        } else {
            if (localState.inPosition) {
                logger.warn("State discrepancy! Position closed on exchange. Resetting state.");
                const newState = { ...defaultState, lastTradeTimestamp: Date.now() };
                await saveState(newState);
                return newState;
            }
            logger.info("State confirmed: No open position.");
            return localState;
        }
    }
}

export default TradingAiSystem;
