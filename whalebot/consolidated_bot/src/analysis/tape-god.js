/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Tape God Engine Module)
 * ======================================================
 * Analyzes real-time trade execution data (tape) for insights into market pressure, momentum, and potential spoofing.
 */

import { Decimal } from 'decimal.js';
import logger from '../logger.js'; // Use configured logger
import { ConfigManager } from '../config.js'; // Access config
import { NEON } from '../ui.js';    // For console coloring

// --- TAPE GOD ENGINE ──────────────────────────────────────────────────────
// Analyzes real-time trade execution data (tape) for insights into market pressure, momentum, and potential spoofing.
class TapeGodEngine {
    constructor() {
        this.trades = []; // Stores recent trade executions
        this.MAX_HISTORY = 1000; // Max number of trades to keep in history
        this.delta = { cumulative: Decimal(0) }; // Cumulative delta (volume difference)
        this.aggression = { buy: Decimal(0), sell: Decimal(0) }; // Aggregated volume by aggressor side
        this.icebergThreshold = 3; // Number of similar trades to detect iceberg orders
        this.volumeProfile = new Map(); // Tracks volume at price levels
        this.tapeMomentum = 0; // Calculated tape momentum
        this.lastPrintTime = 0; // Timestamp for rate limiting UI updates
        this.icebergAlert = false; // Flag for iceberg detection
        this.isDiverging = false; // Flag for divergence detection (not fully implemented here)
    }
    
    // Processes a single execution event from the trade stream.
    processExecution(exec) {
        try {
            // Parse execution details: size, price, side, aggressor status
            const size = parseFloat(exec.execQty || exec.size);
            const price = parseFloat(exec.execPrice || exec.price);
            const side = exec.side === 'Buy' ? 'BUY' : 'SELL';
            
            // Create a trade object for internal tracking
            const trade = { 
                ts: Date.now(), // Timestamp of processing
                price, 
                size, 
                side, 
                aggressor: exec.isBuyerMaker, // True if buyer was maker (ask side aggressor)
                value: size * price, 
                delta: side === 'BUY' ? size : -size // Delta contribution (+ve for buy, -ve for sell)
            };

            // Maintain trade history buffer
            this.trades.push(trade);
            if (this.trades.length > this.MAX_HISTORY) this.trades.shift(); // Remove oldest trade if buffer exceeds max

            // Update cumulative delta
            this.delta.cumulative = this.delta.cumulative.plus(Decimal(trade.delta));
            
            // Update aggression metrics based on aggressor
            if (trade.aggressor) { 
                if (trade.side === 'BUY') this.aggression.buy = this.aggression.buy.plus(size); 
                else this.aggression.sell = this.aggression.sell.plus(size); 
            }
            
            // Calculate tape momentum (rate of trade volume over time) using EMA
            const now = Date.now();
            if (this.lastPrintTime > 0) {
                const timeDiff = now - this.lastPrintTime; // Time elapsed since last print
                // EMA calculation for momentum: 70% previous value, 30% current rate
                this.tapeMomentum = 0.7 * this.tapeMomentum + 0.3 * (size / (timeDiff / 1000)); 
            }
            this.lastPrintTime = now; // Update last print time
            this.detectIceberg(trade); // Check for iceberg orders
            
            // Update volume profile (tracks volume traded at price buckets)
            const bucket = Math.floor(price / 10) * 10; // Define price buckets (e.g., every $10)
            const current = this.volumeProfile.get(bucket) || { buy: 0, sell: 0 }; // Get current bucket volume or initialize
            if (side === 'BUY') current.buy += size;
            else current.sell += size;
            this.volumeProfile.set(bucket, current); // Update volume for the bucket
            
            // Clean old entries from volume profile to prevent excessive growth
            if (this.volumeProfile.size > 100) {
                const entries = Array.from(this.volumeProfile.entries());
                entries.slice(0, 20).forEach(([key]) => this.volumeProfile.delete(key)); // Remove oldest entries
            }
        } catch (error) {
            logger.error(`TapeGod processExecution error: ${error.message}`);
        }
    }
    
    // Detects potential iceberg orders by looking for repeated large trades at the same price.
    detectIceberg(trade) {
        try {
            // Find recent trades with the same price and size
            const recent = this.trades.slice(-20).filter(t => 
              Math.abs(t.price - trade.price) < 0.5 && t.size === trade.size // Check for near-identical trades
            );
            // Set alert if threshold met (e.g., 3 similar trades)
            this.icebergAlert = (recent.length >= this.icebergThreshold); 
        } catch (error) {
            // Ignore iceberg detection errors
        }
    }
    
    // Returns aggregated metrics from recent trades.
    getMetrics() {
        try {
            const recent = this.trades.slice(-50); // Analyze last 50 trades
            const buyVol = recent.filter(t => t.side === 'BUY').reduce((a, t) => a + t.size, 0);
            const sellVol = recent.filter(t => t.side === 'SELL').reduce((a, t) => a + t.size, 0);
            
            // Determine Dominance (DOM) based on recent buy/sell volume
            let dom = 'BALANCED';
            if (buyVol > sellVol * 1.1) dom = 'BUYERS'; // Buyer dominance
            else if (sellVol > buyVol * 1.1) dom = 'SELLERS'; // Seller dominance

            return { 
                delta: buyVol - sellVol, // Net volume difference
                cumulativeDelta: this.delta.cumulative, // Total cumulative delta
                dom, // Dominance indicator
                momentum: this.tapeMomentum, // Calculated tape momentum
                iceberg: this.icebergAlert // Iceberg order alert status
            };
        } catch (error) {
            logger.error(`TapeGod getMetrics error: ${error.message}`);
            // Return default values on error
            return { delta: 0, cumulativeDelta: 0, dom: 'BALANCED', momentum: 0, iceberg: false }; 
        }
    }
    
    // Provides a formatted console display of tape metrics using NEON colors.
    getNeonTapeDisplay() {
        try {
            const m = this.getMetrics();
            const deltaColor = m.delta > 0 ? NEON.GREEN : NEON.RED; // Color delta based on sign
            
            // Construct the display string with colors and padding
            return `\n${NEON.PURPLE}╔══ TAPE GOD – ORDER FLOW DOMINION ═══════════════════════════════╗${NEON.reset}\n${NEON.CYAN}║ ${NEON.BOLD}DELTA${NEON.reset} ${deltaColor}${m.delta > 0 ? '+' : ''}${m.delta.toFixed(1).padStart(8)}${NEON.reset}  │  ${NEON.BOLD}CUMULATIVE${NEON.reset} ${deltaColor}${m.cumulativeDelta > 0 ? '+' : ''}${m.cumulativeDelta.toFixed(0)}${NEON.reset} ${NEON.CYAN}║${NEON.reset}\n${NEON.CYAN}║ ${NEON.BOLD}AGGRESSION${NEON.reset} ${m.dom.padEnd(8)} │  ${NEON.BOLD}MOMENTUM${NEON.reset} ${m.momentum.toFixed(1)}${NEON.reset}     ${NEON.CYAN}║${NEON.reset}\n${NEON.CYAN}║ ${m.iceberg ? NEON.YELLOW + 'ICEBERG DETECTED' : 'Flow Aligned'}     │  ${NEON.BOLD}VOL PROFILE${NEON.reset} Active     ${NEON.CYAN}║${NEON.reset}\n${NEON.PURPLE}╚══════════════════════════════════════════════════════════════════╝${NEON.reset}`;
        } catch (error) {
            logger.error(`TapeGod getNeonTapeDisplay error: ${error.message}`);
            // Return a default display if an error occurs
            return `\n${NEON.PURPLE}╔══ TAPE GOD – ORDER FLOW DOMINION ═══════════════════════════════╗${NEON.reset}\n${NEON.CYAN}║ ${NEON.BOLD}DELTA${NEON.reset} 0.0  │  CUMULATIVE 0 ║\n${NEON.CYAN}║ ${NEON.BOLD}AGGRESSION${NEON.reset} BALANCED │  ${NEON.BOLD}MOMENTUM${NEON.reset} 0.0     ${NEON.CYAN}║${NEON.reset}\n${NEON.CYAN}║ Flow Aligned     │  ${NEON.BOLD}VOL PROFILE${NEON.reset} Active     ${NEON.CYAN}║${NEON.reset}\n${NEON.PURPLE}╚══════════════════════════════════════════════════════════════════╝${NEON.reset}`;
        }
    }
}

export { TapeGodEngine };