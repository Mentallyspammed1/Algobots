// src/core/risk_policy.js
import logger from '../utils/logger.js';
import { ACTIONS } from './constants.js';
import { config } from '../config.js';

export function applyRiskPolicy(aiDecision, indicators, state) {
    const { name, args } = aiDecision;

    if (name === ACTIONS.HOLD) {
        return { decision: 'HOLD', reason: args.reasoning, trade: null };
    }

    if (name === ACTIONS.PROPOSE_TRADE) {
        // Rule 1: Prevent entering a trade if indicators are missing.
        if (!indicators || !indicators.price || !indicators.atr) {
            const reason = "Cannot enter trade due to missing critical indicator data (Price or ATR).";
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // Rule 2: Prevent entering a trade if already in a position.
        if (state.inPosition) {
            const reason = `Risk policy violation: AI proposed a new trade while already in a ${state.positionSide} position.`;
            logger.warn(reason);
            return { decision: 'HOLD', reason, trade: null };
        }
        // NEW Rule 3: Enforce cooldown period between trades.
        const now = Date.now();
        const cooldownMs = config.tradeCooldownMinutes * 60 * 1000;
        if (state.lastTradeTimestamp > 0 && (now - state.lastTradeTimestamp < cooldownMs)) {
            const minutesRemaining = ((cooldownMs - (now - state.lastTradeTimestamp)) / 60000).toFixed(1);
            const reason = `Risk policy violation: Cannot open new trade. In cooldown period for another ${minutesRemaining} minutes.`;
            logger.info(reason);
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