/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (API Wrapper and Exchange Interfaces)
 * ======================================================
 * Provides abstract interfaces for interacting with exchanges (live and paper trading).
 */

import axios from 'axios';
import { Decimal } from 'decimal.js';
import { ConfigManager } from '../config.js'; // Access config
import { NEON } from '../ui.js'; // For console coloring
import logger from '../logger.js'; // Use configured logger

// --- EXCHANGE INTERFACES ──────────────────────────────────────────────────
// Abstract base class for exchange interactions. Defines common methods.
export class Exchange {
    constructor(config, circuitBreaker) {
        this.config = config;
        this.circuitBreaker = circuitBreaker; // Reference to the risk management module
        this.position = null; // Current open position: { side, entry, qty, sl, tp, entryTimestamp, signalStrength }
        this.tradeHistory = []; // Log of closed trades
        this.lastTradeId = 1;   // Counter for unique trade IDs
    }

    // Returns the current open position details, or null if none.
    getPos() { return this.position; }
    // Returns the current balance, typically managed by the CircuitBreaker.
    getBalance() { return this.circuitBreaker.balance.toString(); } 

    // Evaluates a trade decision: opens new position, closes existing, or holds.
    evaluate(price, signal) {
        // First, check if trading is allowed based on risk limits managed by CircuitBreaker.
        if (!this.circuitBreaker.canTrade()) {
            if (this.position) this.closePosition(price, 'RISK_HALT'); // Force close if risk limits are breached
            return; // Stop further processing
        }

        const priceDecimal = new Decimal(price);
        
        // Handle closing an existing position if one is open.
        if (this.position) {
            this.checkAndClosePosition(priceDecimal, signal);
        }
        
        // Handle opening a new position if no position is open and the signal is valid.
        // Signal confidence must meet minimum threshold defined in config.
        if (!this.position && signal.action !== 'HOLD' && signal.confidence >= this.config.ai.minConfidence) {
            this.openPosition(priceDecimal, signal);
        }
    }

    // Checks if a position should be closed based on SL/TP hits or forced reasons (like risk halt).
    checkAndClosePosition(currentPrice, signal) {
        let close = false;
        let reason = signal.reason || ''; // Use AI's reason if provided, else default

        if (this.position.side === 'BUY') {
            // Close BUY position if halted, SL hit, or TP hit
            if (signal.action === 'RISK_HALT' || currentPrice.lte(this.position.sl)) {
                close = true; reason = reason || 'SL Hit';
            } else if (currentPrice.gte(this.position.tp)) {
                close = true; reason = reason || 'TP Hit';
            }
        } else { // SELL position
            // Close SELL position if halted, SL hit, or TP hit
            if (signal.action === 'RISK_HALT' || currentPrice.gte(this.position.sl)) {
                close = true; reason = reason || 'SL Hit';
            } else if (currentPrice.lte(this.position.tp)) {
                close = true; reason = reason || 'TP Hit';
            }
        }

        if (close) {
            this.closePosition(currentPrice, reason); // Execute the closing logic
        }
    }

    // Executes the logic for closing a position, updating balance and history.
    closePosition(exitPrice, reason) {
        const exitPriceDecimal = new Decimal(exitPrice);
        const entryPrice = new Decimal(this.position.entry);
        const quantity = new Decimal(this.position.qty);
        
        // Use paper trading fee and slippage for simulation, even in live mode (as a placeholder)
        const fee = exitPriceDecimal.mul(quantity).mul(this.config.paper_trading.fee);
        const slippage = exitPriceDecimal.mul(this.config.paper_trading.slippage);
        // Adjust exit price for slippage
        const executionPrice = this.position.side === 'BUY' ? exitPriceDecimal.sub(slippage) : exitPriceDecimal.add(slippage);

        // Calculate Profit/Loss
        const rawPnl = this.position.side === 'BUY'
            ? executionPrice.sub(entryPrice).mul(quantity) // Profit for BUY
            : entryPrice.sub(executionPrice).mul(quantity); // Profit for SELL
        
        const netPnl = rawPnl.sub(fee); // Deduct fees

        // Record trade in history for logging and analysis
        this.tradeHistory.push({
            id: this.lastTradeId++,
            timestamp: new Date().toISOString(),
            entryTimestamp: this.position.entryTimestamp,
            symbol: this.config.symbol,
            side: this.position.side,
            entryPrice: entryPrice.toFixed(4),
            exitPrice: executionPrice.toFixed(4),
            quantity: quantity.toFixed(4),
            pnl: netPnl.toFixed(2),
            pnlPercent: netPnl.div(entryPrice.mul(quantity)).mul(100).toFixed(2) + '%', // PnL as percentage of entry value
            reason: reason,
            fee: fee.toFixed(2),
            slippage: slippage.toFixed(4)
        });

        // Update overall balance and daily PnL via the CircuitBreaker
        this.circuitBreaker.recordTradeResult(netPnl.toFixed(2)); // Pass PnL as string

        const pnlColor = netPnl.gte(0) ? NEON.GREEN : NEON.RED;
        logger.success(`${reason}! PnL: ${pnlColor(netPnl.gte(0) ? `+${netPnl.toFixed(2)}` : netPnl.toFixed(2))}`);
        
        this.position = null; // Clear current position after closing
    }

    // Executes the logic for opening a new position.
    openPosition(entryPrice, signal) {
        try {
            const entry = new Decimal(signal.entry);
            const sl = new Decimal(signal.sl);
            const tp = new Decimal(signal.tp);
            
            // Calculate position size based on risk management parameters from CircuitBreaker
            const quantity = this.circuitBreaker.calculatePositionSize(entry, sl, signal.confidence);

            // Check if the calculated trade value is sufficient to proceed
            if (!this.circuitBreaker.isTradeValueSufficient(quantity, entry)) {
                logger.log('gray', "Trade value too low (<$10). Skipped.");
                return;
            }

            // Apply slippage to the entry price for simulation realism
            const slippage = entry.mul(this.config.paper_trading.slippage);
            const executionPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
            
            // Deduct trading fees upfront (simplified model for paper trading)
            const fee = executionPrice.mul(quantity).mul(this.config.paper_trading.fee);
            this.circuitBreaker.balance = this.circuitBreaker.balance.sub(fee); // Directly adjust balance for fee

            // Set the new position details
            this.position = {
                side: signal.action,
                entry: executionPrice,
                qty: quantity,
                sl,
                tp,
                entryTimestamp: new Date().toISOString(),
                signalStrength: signal.confidence
            };

            logger.log('green', `OPEN ${signal.action} @ ${executionPrice.toFixed(4)} | Size: ${quantity.toFixed(4)} | Strength: ${(signal.confidence * 100).toFixed(0)}%`);
        } catch (e) {
            logger.error(`Position opening error: ${e.message}`);
        }
    }
    
    // Displays the trade history in a formatted way.
    displayTradeHistory() {
        if (this.tradeHistory.length === 0) {
            logger.log('gray', "No trades executed yet.");
            return;
        }
        logger.log('cyan', `\n--- Trade History (${this.tradeHistory.length} trades) ---`);
        this.tradeHistory.forEach(trade => {
            const pnlColor = trade.pnl.startsWith('-') ? NEON.RED : NEON.GREEN;
            logger.log('default',
                `${NEON.CYAN(trade.id)}: ${trade.side} ${trade.symbol} @ ${trade.entryPrice} → ${trade.exitPrice} | ` +
                `PnL: ${pnlColor(trade.pnl)} (${trade.pnlPercent}) | Reason: ${trade.reason}`
            );
        });
    }
}

// --- LIVE BYBIT EXCHANGE ──────────────────────────────────────────────────
// Interface for interacting with the live Bybit trading API.
// NOTE: This is a placeholder. Actual implementation requires secure API key handling,
// signature generation, and robust error handling for Bybit API calls.
export class LiveBybitExchange extends Exchange {
    constructor(config, circuitBreaker) {
        super(config, circuitBreaker);
        this.api = axios.create({
            baseURL: 'https://api.bybit.com', // Use live API endpoint
            timeout: this.config.api.timeout,
            headers: { 
                'X-BAPI-API-KEY': process.env.BYBIT_API_KEY || '',
                // 'X-BAPI-TIMESTAMP': '...', // Timestamp needs to be dynamically generated
                // 'X-BAPI-SIGN': '...', // Signature needs to be generated
                'X-BAPI-RECV-WINDOW': '5000' // Example recv_window
            }
        });
        logger.log('yellow', "[LiveExchange] WARNING: Live trading API integration is a placeholder. Signature generation and actual order placement are not fully implemented.");
    }

    // Placeholder for live order placement logic.
    async placeOrder(side, quantity, price, sl, tp) {
        logger.log('yellow', `[LiveExchange] Attempting to place ${side} order... (Placeholder)`);
        // Example API call structure (requires proper params and signature):
        /*
        try {
            const timestamp = Date.now().toString();
            const signature = this.generateSignature(timestamp); // Implement signature generation
            
            const response = await this.api.post('/v5/order/create', {
                category: 'linear',
                symbol: this.config.symbol,
                side: side.toUpperCase(),
                orderType: 'Limit', // Or 'Market'
                qty: quantity.toString(),
                price: price.toString(),
                stopLoss: sl?.toString(), // Optional SL
                takeProfit: tp?.toString(), // Optional TP
                timeInForce: 'GTC', // Good 'Til Cancelled
            }, { headers: { 'X-BAPI-TIMESTAMP': timestamp, 'X-BAPI-SIGN': signature } });

            if (response.data.retCode === 0) { // Success code from Bybit
                logger.success(`[LiveExchange] Order placed successfully. OrderID: ${response.data.result.orderId}`);
                // Update position state based on successful order
                // Note: Fees and slippage for live trades are handled differently
                return { success: true, orderId: response.data.result.orderId };
            } else {
                throw new Error(response.data.retMsg);
            }
        } catch (error) {
            logger.error(`[LiveExchange] Order placement failed: ${error.message}`);
            return { success: false, message: error.message };
        }
        */
       return { success: false, message: "Live order placement not implemented." };
    }
    
    // Placeholder for closing a live position.
    async closeLivePosition(exitPrice, reason) {
        logger.log('yellow', `[LiveExchange] Attempting to close position... (Placeholder)`);
        // In a real implementation, this would involve:
        // 1. Placing a market order to close the position.
        // 2. Cancelling existing SL/TP and placing a new market order.
        const result = await this.placeOrder(this.position.side === 'BUY' ? 'SELL' : 'BUY', this.position.qty, exitPrice, null, null); // Simplified: closing order
        if (result.success) {
             // If the order was successful, finalize state update via base class method
             super.closePosition(exitPrice, reason); // Call parent method to finalize state
        } else {
            logger.error(`[LiveExchange] Failed to close position: ${result.message}`);
        }
        return result; // Return the result of the placeholder operation
    }

    // Overrides `evaluate` to use live trading logic.
    evaluate(price, signal) {
         if (!this.circuitBreaker.canTrade()) {
            if (this.position) this.closePosition(price, 'RISK_HALT');
            return;
        }
        // For live, we'd call `placeOrder` or `closeLivePosition`
        if (this.position) {
            // Using price directly as exitPrice for simplicity. Real logic might involve market orders.
            this.closePosition(price, signal.reason || 'Manual Close'); // Relies on placeholder
        } else if (signal.action !== 'HOLD' && signal.confidence >= this.config.ai.minConfidence) {
            this.openPosition(new Decimal(price), signal); // Relies on placeholder
        }
    }
    
    // Overrides `openPosition` to use live order placement.
     async openPosition(entryPrice, signal) {
        const quantity = this.circuitBreaker.calculatePositionSize(entryPrice, signal.sl, signal.confidence);
         if (!this.circuitBreaker.isTradeValueSufficient(quantity, entryPrice)) {
            logger.log('gray', "Trade value too low (<$10). Skipped.");
            return;
        }
        // Note: Live fees and slippage might differ and should ideally be fetched or configured.
        // Using paper trading config as placeholder for fee calculation.
        const result = await this.placeOrder(signal.action, quantity, signal.entry, signal.sl, signal.tp);
        if (result.success) {
            // If order was successfully placed, update internal state.
            // This requires mapping the order response to the 'position' object.
            // For now, calling base method which assumes immediate execution for simulation.
            super.openPosition(entryPrice, signal); 
        } else {
             logger.error(`[LiveExchange] Failed to open position: ${result.message}`);
        }
    }

     // Overrides `closePosition` to use live closing logic.
     async closePosition(exitPrice, reason) {
         // In live mode, calling closePosition should trigger the live closing mechanism.
         await this.closeLivePosition(exitPrice, reason);
     }

     // Placeholder for generating Bybit API signature. CRITICAL for live trading.
     generateSignature(timestamp) {
         logger.warn("Signature generation not implemented. Please implement secure signature generation for live trading.");
         return 'MOCK_SIGNATURE'; // Replace with actual signature generation
     }
}

// --- PAPER TRADING EXCHANGE ──────────────────────────────────────────────
// Simulates trading without real money, using paper trading parameters from config.
export class PaperExchange extends Exchange {
    constructor(config, circuitBreaker) {
        super(config, circuitBreaker);
        // Initialize balance from config for paper trading
        this.circuitBreaker.setBalance(this.config.paper_trading.initial_balance); 
        logger.log('cyan', `[PaperExchange] Initial balance: $${this.config.paper_trading.initial_balance.toFixed(2)}`);
    }

    // Paper trading uses the base Exchange class's logic. All calculations
    // (fees, slippage, position sizing) are based on the paper_trading config.
    // No direct API calls are made, so methods like placeOrder/closePosition from base class
    // are effectively simulated by the logic in evaluate/open/closePosition.
}
