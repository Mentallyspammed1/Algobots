/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Volatility Clamping Module)
 * ======================================================
 * Adjusts trading parameters (like Take Profit) dynamically based on detected market volatility regimes.
 */

import { Decimal } from 'decimal.js';
import logger from '../logger.js'; // Use configured logger
import { NEON } from '../ui.js';    // For console coloring
import { ConfigManager } from '../config.js'; // Access config settings

// --- VOLATILITY CLAMPING ENGINE ──────────────────────────────────────────
// Adjusts trading parameters (e.g., TP) dynamically based on volatility and market regimes.
class VolatilityClampingEngine {
    constructor() {
        this.history = []; // Stores historical data for regime analysis
        this.REGIME_WINDOW = 48; // Number of data points for regime calculation (e.g., 48 candles)
        this.MAX_CLAMP_MULT = 5.5; // Max multiplier for TP/SL distance (safety clamp)
        this.MIN_CLAMP_MULT = 1.2; // Min multiplier for TP/SL distance
        this.CHOP_THRESHOLD = 0.45; // Threshold for classifying as choppy market
        this.VOL_BREAKOUT_MULT = 1.8; // Multiplier for detecting volatility breakout
        this.regime = 'WARMING'; // Initial market regime state
    }
    
    // Updates the engine with new candle context, order book metrics, and Fisher Transform value.
    update(candleContext, bookMetrics, fisher) {
        try {
            const volatility = candleContext.atr || 0.01; // Use ATR as volatility measure, default to 0.01 if not available
            this.history.push({ 
                atr: volatility, 
                skew: bookMetrics.imbalanceRatio || 0, // Order book imbalance ratio
                fisher: Math.abs(fisher || 0), // Absolute Fisher Transform value
                price: candleContext.price, 
                ts: Date.now() // Timestamp of the update
            });
            // Limit history size to prevent memory issues
            if (this.history.length > 200) this.history.shift();
            
            // Calculate average ATR over a recent window (e.g., last 20 points)
            const avgAtr = this.history.slice(-20).reduce((a, c) => a + c.atr, 0) / Math.max(1, this.history.length);
            this.determineRegime(avgAtr, volatility); // Determine current market regime
        } catch (error) {
            logger.error(`VolatilityClamping update error: ${error.message}`);
        }
    }
    
    // Determines the current market regime based on volatility ratio and entropy.
    determineRegime(avgAtr, currentAtr) {
        try {
            if (this.history.length < this.REGIME_WINDOW) { 
                this.regime = 'WARMING'; // Regime is not yet determined if history is insufficient
                return; 
            }
            // Calculate volatility ratio (current ATR / average ATR)
            const volRatio = avgAtr === 0 ? 1 : currentAtr / avgAtr; 
            // Calculate entropy (measure of market chaos/choppiness) from skew and Fisher transform
            const entropy = this.history.reduce((a, c) => a + Math.abs(c.skew) + c.fisher, 0) / this.REGIME_WINDOW;
            
            // Classify regime based on conditions
            if (volRatio > this.VOL_BREAKOUT_MULT && entropy < this.CHOP_THRESHOLD) {
                this.regime = 'BREAKOUT'; // High volatility and low chop suggests breakout potential
            } else if (entropy > this.CHOP_THRESHOLD) {
                this.regime = 'CHOPPY'; // High entropy indicates choppy/ranging market
            } else if (volRatio > 1.3) {
                this.regime = 'TRENDING'; // Increased volatility suggests trending market
            } else {
                this.regime = 'RANGING'; // Otherwise, assume ranging market
            }
        } catch (error) {
            this.regime = 'WARMING'; // Default to warming on error
            logger.error(`VolatilityClamping determineRegime error: ${error.message}`);
        }
    }
    
    getRegime() { return this.regime; } // Returns the current market regime string
    
    // Determines if entry conditions are met based on regime and volatility.
    shouldEnter(atr, regime) {
        if (regime === 'CHOPPY') return false; // Do not enter in choppy markets
        if (regime === 'BREAKOUT') return true; // Always consider entries in breakout regime
        
        // Calculate average ATR over a recent window (e.g., last 20 points)
        const avgAtr = this.history.slice(-20).reduce((a, c) => a + c.atr, 0) / Math.max(1, this.history.length);
        
        // Enter if current ATR is significantly higher than average (indicates potential move)
        return (avgAtr > 0 && atr > avgAtr * 1.2); 
    }
    
    // Clamps the Take Profit (TP) level based on regime and ATR, ensuring it's within reasonable bounds.
    clamp(signal, price, atr) {
        try {
            const regime = this.getRegime(); // Get current regime
            // Determine multiplier based on regime for TP distance calculation
            const mult = regime === 'BREAKOUT' ? 5.0 : regime === 'CHOPPY' ? 1.5 : 3.0;
            const maxDist = Decimal(atr).mul(mult); // Max allowed distance for TP based on ATR and multiplier
            const entry = Decimal(price); // Entry price as Decimal
            const dir = signal.action === 'BUY' ? 1 : -1; // Direction multiplier (1 for BUY, -1 for SELL)
            
            // Calculate proposed TP based on signal's Risk/Reward ratio
            const baseDist = Decimal(atr).mul(CONFIG.risk?.rewardRatio || 1.5); 
            const proposedTp = entry.plus(baseDist.mul(dir));
            
            // Calculate clamped TP based on max allowed distance
            const clampedTp = entry.plus(maxDist.mul(dir));
            
            // Final TP is the minimum of proposed TP and clamped TP for BUY, or maximum for SELL
            // This ensures TP is within reasonable volatility bounds but still respects R/R target if it's tighter.
            const finalTp = dir === 1 ? Decimal.min(proposedTp, clampedTp) : Decimal.max(proposedTp, clampedTp);
            
            return { tp: Number(finalTp.toFixed(2)), regime }; // Return clamped TP and regime info
        } catch (error) {
            logger.error(`VolatilityClamping clamp error: ${error.message}`);
            return { tp: signal.tp, regime }; // Return original signal TP and regime on error
        }
    }
}

export { VolatilityClampingEngine };