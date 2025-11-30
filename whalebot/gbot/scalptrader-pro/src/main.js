const { TradingEngine } = require('./engine');
const { Decimal } = require('decimal.js');

// Set Decimal.js precision globally
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

const engine = new TradingEngine();
process.on('SIGINT', () => { 
    engine.isRunning = false; 
    console.log(engine.NEON.RED("\n🛑 SHUTTING DOWN GRACEFULLY...")); 
    process.exit(0);
});
process.on('SIGTERM', () => { engine.isRunning = false; process.exit(0); });
engine.start();