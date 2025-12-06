import { COLOR } from './ui.js';

/**
 * A circuit breaker to halt trading if the daily loss limit is exceeded.
 */
export class CircuitBreaker {
    constructor(config) {
        this.maxLossPct = config.risk.maxDailyLoss;
        this.maxDrawdownPct = config.risk.maxDrawdown || 10.0;
        this.initialBalance = 0;
        this.maxEquity = 0;
        this.currentPnL = 0;
        this.triggered = false;
        this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
    }

    setBalance(bal) {
        if (this.initialBalance === 0) {
            this.initialBalance = bal;
            this.maxEquity = bal;
        }

        if (bal > this.maxEquity) {
            this.maxEquity = bal;
        }
        
        if (Date.now() > this.resetTime) {
            this.initialBalance = bal;
            this.currentPnL = 0;
            this.triggered = false;
            this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
            console.log(COLOR.GREEN(`[CircuitBreaker] Daily stats reset.`));
        }

        // Max Drawdown Check
        if (this.maxEquity > 0) {
            const drawdown = (this.maxEquity - bal) / this.maxEquity * 100;
            if (drawdown >= this.maxDrawdownPct) {
                this.triggered = true;
                console.log(COLOR.bg(COLOR.RED(` 🚨 MAX DRAWDOWN TRIGGERED: ${drawdown.toFixed(2)}% `)));
            }
        }
    }

    updatePnL(pnl) {
        this.currentPnL += pnl;
        const lossPct = (Math.abs(this.currentPnL) / this.initialBalance) * 100;
        if (this.currentPnL < 0 && lossPct >= this.maxLossPct) {
            this.triggered = true;
            console.log(COLOR.bg(COLOR.RED(` 🚨 DAILY LOSS TRIGGERED: ${lossPct.toFixed(2)}% `)));
        }
    }

    isOpen() {
        return this.triggered;
    }
    
    trip(reason) {
        this.triggered = true;
        console.error(COLOR.RED(`[CircuitBreaker] TRIP forced by reason: ${reason}`));
    }
    
    reset() {
        this.triggered = false;
        console.log(COLOR.GREEN(`[CircuitBreaker] Manually reset.`));
    }
}