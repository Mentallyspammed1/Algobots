import { COLOR } from './ui.js';

/**
 * A circuit breaker to halt trading if the daily loss limit is exceeded.
 */
export class CircuitBreaker {
    constructor(config) {
        this.maxLossPct = config.risk.maxDailyLoss;
        this.initialBalance = 0;
        this.currentPnL = 0;
        this.triggered = false;
        this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
    }

    setBalance(bal) {
        if (this.initialBalance === 0) this.initialBalance = bal;
        
        if (Date.now() > this.resetTime) {
            this.initialBalance = bal;
            this.currentPnL = 0;
            this.triggered = false;
            this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
            console.log(COLOR.GREEN(`[CircuitBreaker] Daily stats reset.`));
        }
    }

    updatePnL(pnl) {
        this.currentPnL += pnl;
        const lossPct = (Math.abs(this.currentPnL) / this.initialBalance) * 100;
        if (this.currentPnL < 0 && lossPct >= this.maxLossPct) {
            this.triggered = true;
            console.log(COLOR.bg(COLOR.RED(` 🚨 CIRCUIT BREAKER TRIGGERED: Daily Loss ${lossPct.toFixed(2)}% `)));
        }
    }

    canTrade() {
        return !this.triggered;
    }
}
