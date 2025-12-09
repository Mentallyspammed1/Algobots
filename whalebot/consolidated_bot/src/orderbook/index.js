/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Order Book Analysis Module)
 * ======================================================
 * Processes and analyzes order book data for insights like walls, spoofing, and liquidity vacuums.
 */

import { Decimal } from 'decimal.js';
import { ConfigManager } from '../config.js'; // To access config settings
import { NEON } from '../ui.js'; // For console coloring
import logger from '../logger.js'; // Use the configured logger

// --- LOCAL ORDER BOOK ─────────────────────────────────────────────────────
// Processes and analyzes incoming order book data.
class LocalOrderBook {
    constructor() {
        this.bids = new Map(); // Stores bid price -> size
        this.asks = new Map(); // Stores ask price -> size
        this.ready = false;    // Flag indicating if the order book is initialized
        this.lastUpdate = 0;   // Timestamp of the last update
        this.depth = 25;       // Default depth to consider for analysis
    }
    
    // Updates the order book with new data. Handles snapshot or delta updates.
    update(data, isSnapshot = false) {
        try {
            // Clear existing data if it's a snapshot
            if (isSnapshot) {
                this.bids.clear();
                this.asks.clear();
            }
            
            // Update bids if present
            if (data.b) {
                this.bids.clear(); // Clear before adding new bids
                data.b.forEach(([price, size]) => {
                    this.bids.set(Number(price), Number(size));
                });
            }
            
            // Update asks if present
            if (data.a) {
                this.asks.clear(); // Clear before adding new asks
                data.a.forEach(([price, size]) => {
                    this.asks.set(Number(price), Number(size));
                });
            }
            
            this.ready = true; // Mark book as ready after update
            this.lastUpdate = Date.now();
        } catch (error) {
            logger.error(`LocalOrderBook update error: ${error.message}`);
        }
    }
    
    // Gets the best bid and ask prices from the order book.
    getBestBidAsk() {
        const bids = Array.from(this.bids.keys());
        const asks = Array.from(this.asks.keys());
        
        if (bids.length === 0 || asks.length === 0) {
            return { bid: 0, ask: 0 }; // Return zero if no bids or asks
        }
        
        const bestBid = Math.max(...bids); // Highest bid price
        const bestAsk = Math.min(...asks); // Lowest ask price
        return { bid: bestBid, ask: bestAsk };
    }
    
    // Analyzes the order book to extract metrics like spread, skew, volume, and walls.
    getAnalysis() {
        const { bid, ask } = this.getBestBidAsk();
        const spread = ask - bid;
        // Skew: (Bid - Ask) / ((Bid + Ask) / 2) * 100 - indicates imbalance
        const skew = bid && ask ? ((bid - ask) / ((bid + ask) / 2)) * 100 : 0;
        // Calculate total volume on top levels
        const totalBidVol = Array.from(this.bids.values()).reduce((a, b) => a + b, 0);
        const totalAskVol = Array.from(this.asks.values()).reduce((a, b) => a + b, 0);
        
        // Wall detection: Check top levels for significantly large orders
        // Top 5 bids sorted by price descending, Top 5 asks sorted by price ascending
        const topBidLevels = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, 5); 
        const topAskLevels = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, 5); 
        const bidWall = Math.max(...topBidLevels.map(([p, s]) => s), 0); // Max bid size among top levels
        const askWall = Math.max(...topAskLevels.map(([p, s]) => s), 0); // Max ask size among top levels
        
        let wallStatus = 'NORMAL';
        // Classify wall status based on volume comparison relative to total volume
        if (bidWall > totalAskVol * 3) wallStatus = 'BID_WALL_BROKEN'; // Significant bid volume suggests support
        else if (askWall > totalBidVol * 3) wallStatus = 'ASK_WALL_BROKEN'; // Significant ask volume suggests resistance
        
        return { 
            bid, 
            ask, 
            spread, 
            skew, 
            totalBidVol, 
            totalAskVol,
            wallStatus,
            bidWall,
            askWall,
            imbalanceRatio: (totalBidVol - totalAskVol) / (totalBidVol + totalAskVol || 1) // Ratio of imbalance to total volume
        };
    }
}

// --- DEEP VOID ENGINE ──────────────────────────────────────────────────────
// Provides more detailed order book metrics including spoofing and vacuum detection.
class DeepVoidEngine {
    constructor() {
        this.depth = 25; // Depth for analysis
        this.bids = new Map();
        this.asks = new Map();
        this.avgDepthHistory = []; // Rolling history for vacuum detection
        this.spoofAlert = false; // Flag for spoofing detection
        this.isVacuum = false; // Flag for liquidity vacuum detection
        this.metrics = { // Stores calculated metrics
            totalBidVol: 0, totalAskVol: 0, imbalance: 0, imbalanceRatio: 0,
            strongestBidWall: 0, strongestAskWall: 0, bidPressure: 0.5, askPressure: 0.5,
            isVacuum: false, spoofAlert: false, wallBroken: false
        };
        this.liquidityVacuumThreshold = 0.3; // Threshold for detecting a liquidity vacuum
    }
    
    // Updates the engine with new order book data.
    update(bids, asks) {
        if (!bids || !asks) return; // Do nothing if data is invalid
        
        // Update bids and asks from provided arrays, converting to numbers
        this.bids = new Map(bids.map(([p, s]) => [parseFloat(p), parseFloat(s)]));
        this.asks = new Map(asks.map(([p, s]) => [parseFloat(p), parseFloat(s)]));
        this.calculateMetrics(); // Recalculate metrics after update
    }
    
    // Returns the calculated depth metrics.
    getDepthMetrics() { 
        return this.metrics; 
    }
    
    // Calculates detailed order book metrics.
    calculateMetrics() {
        try {
            // Get top bid/ask levels based on depth
            const bidLevels = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, this.depth);
            const askLevels = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, this.depth);
            const bidSizes = bidLevels.map(([, size]) => size);
            const askSizes = askLevels.map(([, size]) => size);
            
            // Calculate total volumes
            const totalBidVol = bidSizes.reduce((a, b) => a + b, 0);
            const totalAskVol = askSizes.reduce((a, b) => a + b, 0);
            const imbalance = totalBidVol - totalAskVol;
            const imbalanceRatio = (totalBidVol + totalAskVol === 0) ? 0 : imbalance / (totalBidVol + totalAskVol);
            const strongestBidWall = Math.max(...bidSizes, 0); // Max bid size
            const strongestAskWall = Math.max(...askSizes, 0); // Max ask size
            
            this.detectSpoofing(); // Check for spoofing patterns
            this.detectLiquidityVacuum(totalBidVol, totalAskVol); // Check for liquidity vacuum
            
            // Update the metrics object
            this.metrics = {
                totalBidVol: totalBidVol || 0,
                totalAskVol: totalAskVol || 0,
                imbalance: imbalance || 0,
                imbalanceRatio: Number((imbalanceRatio || 0).toFixed(4)),
                strongestBidWall: strongestBidWall || 0,
                strongestAskWall: strongestAskWall || 0,
                bidPressure: 0.5, // Placeholder value
                askPressure: 0.5, // Placeholder value
                isVacuum: this.isVacuum || false,
                spoofAlert: this.spoofAlert || false,
                wallBroken: this.wallBroken || false
            };
        } catch (error) {
            logger.error(`DeepVoid calculateMetrics error: ${error.message}`);
            // Keep existing metrics on error to avoid state corruption
        }
    }
    
    // Detects potential spoofing by looking for unusually large orders that disappear.
    detectSpoofing() { 
        this.spoofAlert = false; 
        try {
            // Check top ask levels for unusually large orders compared to average
            const topAskSizes = Array.from(this.asks.values()).sort((a, b) => b - a).slice(0, 5);
            const avgTopAsk = topAskSizes.reduce((a, b) => a + b, 0) / (topAskSizes.length || 1);
            if (topAskSizes[0] > avgTopAsk * 5) this.spoofAlert = true; // Alert if top ask is significantly larger than average
        } catch (error) {
            // Ignore spoof detection errors
        }
    }
    
    // Detects a liquidity vacuum where total volume drops significantly.
    detectLiquidityVacuum(totalBidVol, totalAskVol) {
        try {
            // Maintain a history of total depth (bid + ask)
            this.avgDepthHistory.push((totalBidVol + totalAskVol) / 2);
            if (this.avgDepthHistory.length > 50) this.avgDepthHistory.shift(); // Keep history size limited
            
            // Calculate long-term average depth
            const longTermAvg = this.avgDepthHistory.reduce((a, b) => a + b, 0) / (this.avgDepthHistory.length || 1);
            // If current depth is much lower than average, it's a vacuum
            this.isVacuum = (totalBidVol + totalAskVol) / 2 < (longTermAvg || 1) * this.liquidityVacuumThreshold;
        } catch (error) {
            // Ignore vacuum detection errors
        }
    }
    
    // Provides a formatted console display of order book metrics using NEON colors.
    getNeonDisplay() { 
        const m = this.getDepthMetrics();
        // Color code skew based on imbalance
        const skewColor = (m.imbalanceRatio || 0) > 0.05 ? NEON.GREEN : (m.imbalanceRatio || 0) < -0.05 ? NEON.RED : NEON.GRAY;
        
        // Construct the display string with appropriate colors and padding
        return `\n${NEON.PURPLE}╔══ DEEP VOID ORDERBOOK DOMINION ═══════════════════════════════════╗${NEON.reset}\n${NEON.CYAN}║ ${NEON.BOLD}BID WALL${NEON.reset} ${(m.strongestBidWall || 0).toFixed(1).padStart(8)}  │  ${NEON.BOLD}ASK WALL${NEON.reset} ${(m.strongestAskWall || 0).toFixed(1).padStart(8)}${NEON.reset} ${NEON.CYAN}║${NEON.reset}\n${NEON.CYAN}║ ${NEON.BOLD}LIQUIDITY${NEON.reset} ${(m.totalBidVol || 0).toFixed(1).padStart(6)} / ${(m.totalAskVol || 0).toFixed(1).padStart(6)}  │  ${NEON.BOLD}IMBALANCE${NEON.reset} ${skewColor}${ ((m.imbalanceRatio || 0) * 100).toFixed(1)}%${NEON.reset} ${NEON.CYAN}║${NEON.reset}\n${NEON.CYAN}║ ${m.isVacuum ? NEON.YELLOW + 'VACUUM ALERT' : 'Depth Normal'}     │  ${m.spoofAlert ? NEON.RED + 'SPOOF DETECTED' : 'No Spoofing'}     ${NEON.CYAN}║${NEON.reset}\n${NEON.PURPLE}╚══════════════════════════════════════════════════════════════════╝${NEON.reset}`;
    }
}

// Export classes for use in other modules
export { LocalOrderBook, DeepVoidEngine };