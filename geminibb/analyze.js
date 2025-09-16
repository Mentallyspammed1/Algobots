// analyze.js
import 'dotenv/config';
import TradingAiSystem from './src/trading_ai_system.js';
import logger from './src/utils/logger.js';
import { config } from './src/config.js';

async function runAnalysis() {
    logger.info(`--- Running On-Demand Analysis for ${config.symbol} ---`);
    if (!process.env.BYBIT_API_KEY || !process.env.GEMINI_API_KEY) {
        logger.error("API keys are not configured. Please check your .env file.");
        process.exit(1);
    }
    
    // We can reuse the TradingAiSystem for its logic, but we won't start the WebSocket.
    const tradingSystem = new TradingAiSystem();

    try {
        // This manually triggers one cycle of the main logic loop.
        await tradingSystem.runAnalysisCycle();
        logger.info("--- On-Demand Analysis Complete ---");
    } catch (error) {
        logger.error("An error occurred during analysis.", error);
    }
}

runAnalysis();