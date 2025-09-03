import { config } from '../config.js';
import logger from '../utils/logger.js';

export function applyRiskPolicy(proposedTrade, indicators) {
    if (!proposedTrade) {
        return { decision: 'HOLD', reason: 'No trade proposed by AI.' };
    }

    if (proposedTrade.name === 'proposeTrade') {
        const { confidence } = proposedTrade.args;
        if (confidence < config.ai.confidenceThreshold) {
            return { decision: 'HOLD', reason: `AI confidence (${confidence}) is below threshold (${config.ai.confidenceThreshold}).` };
        }
        // Add more checks here, e.g., volatility check with ATR
        // if (indicators.atr / indicators.price > 0.05) { // If ATR is >5% of price
        //     return { decision: 'HOLD', reason: 'Market volatility is too high.' };
        // }
    }

    logger.info(`Risk policy approved the proposed action: ${proposedTrade.name}`);
    return { decision: 'PROCEED', trade: proposedTrade };
}