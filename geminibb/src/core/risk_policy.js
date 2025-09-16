// src/core/risk_policy.js
import logger from '../utils/logger.js';
import { ACTIONS } from './constants.js';
import { config } from '../config.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for P&L calculations

export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    // IMPROVEMENT 18: Max Daily Loss Policy
    const now = Date.now();
    const today = new Date(now).toISOString().split('T')[0];
    const pnlResetDate = state.dailyPnlResetDate;
    let dailyLoss = new Decimal(state.dailyLoss);

    if (pnlResetDate !== today) {
        logger.info(`Resetting daily P&L. Old date: ${pnlResetDate}, New date: ${today}. Old loss: ${dailyLoss.toFixed(2)}`);
        dailyLoss = new Decimal(0); // Reset daily loss
        state.dailyPnlResetDate = today; // Update the reset date
        state.dailyLoss = dailyLoss.toString(); // Save the new loss
    }

    if (dailyLoss.gte(config.maxDailyLossPercentage / 100 * state.initialBalance)) { // IMPROVEMENT 18: Compare against initial balance
        const reason = `Risk policy violation: Max daily loss limit of ${config.maxDailyLossPercentage}% reached. Current daily loss: ${dailyLoss.toFixed(2)} USDT.`;
        logger.error(reason);
        return { decision: ACTIONS.HALT, reason, trade: null }; // Return ACTIONS.HALT
    }

    // IMPROVEMENT 14: Max Overall Drawdown Policy
    // This requires a real-time account balance, which for simplicity here,
    // we'll approximate. A robust system would fetch this directly from Bybit.
    const currentPrice = new Decimal(indicators.close);
    let currentEquity = new Decimal(state.initialBalance); // Start with initial balance

    if (state.inPosition) {
        // If in position, add unrealized P&L to initial balance (approximation)
        const entryPrice = new Decimal(state.entryPrice);
        const quantity = new Decimal(state.quantity);
        const unrealizedPnl = currentPrice.minus(entryPrice).times(quantity).times(state.positionSide === 'Buy' ? 1 : -1);
        currentEquity = currentEquity.plus(unrealizedPnl);
    }
    // We assume initialBalance is set at bot start. If not, this check won't run.
    if (state.initialBalance.gt(0) && currentEquity.lt(state.initialBalance)) {
        const drawdown = state.initialBalance.minus(currentEquity).dividedBy(state.initialBalance).times(100);
        if (drawdown.gte(config.maxOverallDrawdownPercentage)) {
            const reason = `Risk policy violation: Max overall drawdown limit of ${config.maxOverallDrawdownPercentage}% reached. Current drawdown: ${drawdown.toFixed(2)}%.`;
            logger.critical(reason);
            return { decision: ACTIONS.HALT, reason, trade: null };
        }
    }

    if (name === ACTIONS.PROPOSE_TRADE) {
        // Rule 1: Prevent entering a trade if indicators are missing.
        if (!indicators || !indicators.close || !indicators.atr) { // Ensure 'close' is used for price
            const reason = "Cannot enter trade due to missing critical indicator data (Current Price or ATR).";
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // Rule 2: Prevent entering a trade if already in a position.
        if (state.inPosition) {
            const reason = `Risk policy violation: AI proposed a new trade while already in a ${state.positionSide} position.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // Rule 3: Enforce cooldown period between trades.
        const cooldownMs = config.tradeCooldownMinutes * 60 * 1000;
        if (state.lastTradeTimestamp > 0 && (now - state.lastTradeTimestamp < cooldownMs)) {
            const minutesRemaining = ((cooldownMs - (now - state.lastTradeTimestamp)) / 60000).toFixed(1);
            const reason = `Risk policy violation: Cannot open new trade. In cooldown period for another ${minutesRemaining} minutes.`;
            logger.info(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // IMPROVEMENT 15: Minimum ATR filter
        if (!indicators.atr || new Decimal(indicators.atr).lt(config.minAtrThreshold)) {
            const reason = `Risk policy violation: ATR (${indicators.atr ? indicators.atr.toFixed(2) : 'N/A'}) is below minimum threshold (${config.minAtrThreshold.toFixed(2)}). Avoiding low volatility trade.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // IMPROVEMENT 18: Max Open Positions check (conceptual for now, as state only supports one)
        if (state.openPositionsCount >= config.maxOpenPositions) {
            const reason = `Risk policy violation: Max open positions (${config.maxOpenPositions}) reached.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
    }

    if (name === ACTIONS.PROPOSE_EXIT && !state.inPosition) {
        const reason = `Risk policy violation: AI proposed an exit but there is no open position.`;
        logger.warn(reason);
        return { decision: 'HOLD', reason, trade: null };
    }

    logger.info("AI decision passed risk policy checks.");
    return { decision: 'EXECUTE', reason: 'AI proposal is valid and passes risk checks.', trade: aiDecision };
}