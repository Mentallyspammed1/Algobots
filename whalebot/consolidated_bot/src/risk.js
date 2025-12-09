/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Production Position Sizing Module)
 * ======================================================
 * Implements position sizing based on Kelly Criterion, volatility, and drawdown recovery rules.
 */

import { Decimal } from 'decimal.js';
import logger from '../logger.js'; // Use configured logger
import { ConfigManager } from '../config.js'; // Access config for risk parameters

// --- POSITION SIZING (KELLY/VOLATILITY ADJUSTED) ──────────────────────────
// Calculates optimal trade size based on risk management principles.
class ProductionPositionSizer {
    constructor(config) {
        this.config = config.risk; // Extract risk parameters from config
        this.equity = 10000;       // Initial equity (will be updated dynamically)
        this.consecutiveLosses = 0; // Counter for consecutive losing trades
        this.tradeHistory = [];    // Stores outcomes of recent trades for win rate calculation
        this.MAX_HISTORY = 100;    // Max trades to consider for win rate
        this.minSize = parseFloat(this.config.minOrderQty || '0.001'); // Minimum order quantity from config
        this.maxSize = parseFloat(this.config.maxOrderQty || '10.0');  // Maximum order quantity from config
        this.maxRiskPct = parseFloat(this.config.maxRiskPerTrade || '0.01'); // Max % of equity to risk per trade
        this.kellyFraction = this.config.kellyFraction || 0.25; // Fraction of Kelly Criterion to apply (safer sizing)
        this.winRate = 0.55; // Assumed win rate (can be dynamically calculated if history is rich)
    }

    // Calculates optimal position size based on signal, current market conditions, and risk parameters.
    getOptimalSize(signal, currentPrice, atr, avgAtr, drawdownMode = false) {
        try {
            const riskDistance = Math.abs(currentPrice - signal.sl); // Price distance to stop loss
            if (riskDistance <= 0) return this.minSize; // Return min size if SL is at or beyond entry

            // 1. Kelly Estimate: Calculate size based on Kelly Criterion for optimal growth potential.
            const kelly = this.calculateKellySize(this.equity, signal.sl, currentPrice, signal.tp);
            
            // 2. Volatility Adjustment: Modify size based on current vs. average volatility.
            const volAdjusted = this.calculateVolatilityAdjusted(kelly, atr, avgAtr);
            
            // 3. Drawdown/Loss Multiplier: Reduce size after consecutive losses.
            const finalSize = this.applyDrawdownMultiplier(volAdjusted, this.consecutiveLosses);
            
            // 4. Recovery Mode Adjustment: Further reduce size during recovery phase if applicable.
            const recoverySize = drawdownMode ? finalSize * 0.5 : finalSize; // Halve size if in recovery mode
            
            // Ensure the calculated size is within the defined min/max bounds.
            return Math.max(this.minSize, Math.min(recoverySize, this.maxSize));
        } catch (error) {
            logger.error(`Position sizing error: ${error.message}`);
            return this.minSize; // Default to minimum size on error
        }
    }

    // Calculates Kelly Criterion based sizing.
    calculateKellySize(equity, sl, entry, tp) { 
        try {
            const risk = Math.abs(entry - sl); // Risk amount in price terms
            const reward = Math.abs(tp - entry); // Reward amount in price terms
            if (risk <= 0 || reward <= 0) return this.minSize; // Ensure valid risk/reward

            const b = reward / risk; // Reward/Risk ratio (b = win/loss ratio)
            const p = Math.min(this.winRate, 0.95); // Assumed win rate (capped at 95%)
            const q = Decimal(1).minus(p); // Loss rate

            // Kelly Formula: f* = (bp - q) / b  (fraction of bankroll to bet)
            const f_star = (b * p - q) / b; 
            // Safe Kelly Fraction: Use a fraction of the full Kelly bet for reduced risk
            const safeF = f_star * this.kellyFraction;
            
            // Bound the fraction to avoid extreme sizing (e.g., 1% to 10% of equity)
            const boundedF = Math.max(0.01, Math.min(safeF, 0.1));
            const riskDollar = equity * boundedF; // Dollar amount to risk based on equity fraction
            const size = riskDollar / risk; // Position size = Risk Amount / Risk per unit

            // Ensure size is within min/max bounds
            return Math.max(this.minSize, Math.min(size, this.maxSize));
        } catch (error) {
            logger.error(`Kelly calculation error: ${error.message}`);
            return this.minSize;
        }
    }
    
    // Adjusts position size based on current volatility relative to average.
    calculateVolatilityAdjusted(baseSize, atr, avgAtr) {
        try {
            // Volatility ratio: current ATR / average ATR
            const volRatio = avgAtr > 0 ? Math.min(atr / avgAtr, 2.0) : 1.0; // Cap ratio at 2.0 to avoid extreme adjustments
            const adjustment = 1 / volRatio; // Inverse relationship: higher vol -> smaller size
            const adjusted = baseSize * adjustment;
            // Clamp adjusted size to min/max bounds
            return Math.max(this.minSize, Math.min(adjusted, this.maxSize)); 
        } catch (error) {
            logger.error(`Volatility adjustment error: ${error.message}`);
            return baseSize; // Return base size on error
        }
    }

    // Reduces position size multiplier based on consecutive losses.
    applyDrawdownMultiplier(size, consecutiveLosses) {
        try {
            // Reduce size exponentially with consecutive losses (e.g., 0.85^N multiplier)
            const multiplier = Math.pow(0.85, consecutiveLosses);
            return size * multiplier;
        } catch (error) {
            logger.error(`Drawdown multiplier error: ${error.message}`);
            return size; // Return original size on error
        }
    }
    
    // Records trade outcome to update win rate and consecutive losses counter.
    recordTrade(outcome) {
        try {
            this.tradeHistory.push(outcome);
            if (this.tradeHistory.length > this.MAX_HISTORY) this.tradeHistory.shift(); // Maintain history size
            // Update consecutive losses counter
            this.consecutiveLosses = outcome.pnl < 0 ? this.consecutiveLosses + 1 : 0; 
        } catch (error) {
            logger.error(`Record trade error: ${error.message}`);
        }
    }
    
    // Updates the current equity value.
    updateEquity(newEquity) {
        try {
            this.equity = newEquity;
        } catch (error) {
            logger.error(`Update equity error: ${error.message}`);
        }
    }
}

// --- DRAWDOWN TRACKER & RECOVERY ──────────────────────────────────────────
// Manages equity drawdown, daily loss limits, and recovery mode.
class DrawdownTracker {
    constructor(config) {
        this.peakEquity = 0; // Highest equity reached in the session
        this.maxDailyLoss = parseFloat(config.daily_loss_limit || '10'); // Max daily loss % from config
        this.drawdownRecoveryMode = false; // Flag indicating recovery mode status
        this.dailyDrawdown = 0; // Current drawdown for the day
        this.equityHistory = []; // Stores equity over time for drawdown calculation
        this.dailyResetTime = this.getNextDailyReset(); // Timestamp for resetting daily drawdown
        this.recoveryThreshold = parseFloat(config.recoveryThreshold || '0.5'); // Threshold to exit recovery mode (as a fraction of max daily loss)
    }
    
    // Calculates the timestamp for the start of the next day (for daily reset).
    getNextDailyReset() {
        try {
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            tomorrow.setHours(0, 0, 0, 0); // Set to midnight of next day
            return tomorrow.getTime();
        } catch (error) {
            logger.error(`Error calculating next daily reset time: ${error.message}`);
            return Date.now() + 24 * 60 * 60 * 1000; // Fallback to 24 hours from now
        }
    }
    
    // Updates equity, peak equity, and daily drawdown.
    update(currentEquity) {
        try {
            const now = Date.now();
            // Reset daily drawdown if current time exceeds the daily reset time
            if (now > this.dailyResetTime) { 
                this.dailyDrawdown = 0; 
                this.dailyResetTime = this.getNextDailyReset(); // Set next reset time
            }
            this.equityHistory.push({ equity: currentEquity, timestamp: now });
            if (this.equityHistory.length > 500) this.equityHistory.shift(); // Limit history size
            
            // Update peak equity if current equity is higher
            if (currentEquity > this.peakEquity) this.peakEquity = currentEquity;
            
            // Calculate current daily drawdown from peak equity
            this.dailyDrawdown = Math.max(0, this.peakEquity - currentEquity);
        } catch (error) {
            logger.error(`Drawdown update error: ${error.message}`);
        }
    }
    
    // Checks if the bot is in recovery mode (after hitting daily loss limit).
    isRecoveryMode() {
        try {
            // Calculate daily loss as a percentage of peak equity
            const dailyLossPct = (this.peakEquity > 0) ? (this.dailyDrawdown / this.peakEquity) * 100 : 0;
            if (dailyLossPct > this.maxDailyLoss) { 
                // If max daily loss exceeded, enter recovery mode
                this.drawdownRecoveryMode = true; 
                return true; 
            }
            // If in recovery mode and daily loss is below recovery threshold, exit recovery mode
            if (this.drawdownRecoveryMode && dailyLossPct < (this.maxDailyLoss * this.recoveryThreshold)) {
                this.drawdownRecoveryMode = false;
                logger.success('[RECOVERY] Exited recovery mode');
            }
            return this.drawdownRecoveryMode;
        } catch (error) {
            logger.error(`Recovery mode check error: ${error.message}`);
            return false; // Assume not in recovery mode on error
        }
    }
    
    // Returns parameters to use when in recovery mode (e.g., lower risk).
    getRecoveryParameters() { 
        return { 
            maxRiskPerTrade: 0.005, // Reduced risk per trade during recovery
            minConfidence: 0.90,    // Higher confidence required for trades in recovery
            rewardRatio: 2.0        // Higher R/R target during recovery
        }; 
    }
}

export { ProductionPositionSizer, DrawdownTracker };