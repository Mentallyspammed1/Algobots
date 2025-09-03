// main.js
import dotenv from 'dotenv';
import path from 'path';
dotenv.config({ path: path.resolve(process.cwd(), '.env'), override: true });
import TradingAiSystem from './src/trading_ai_system.js';
import BybitWebSocket from './src/api/bybit_websocket.js';
import logger from './src/utils/logger.js';
import { config } from './src/config.js';

function validateEnv() {
    if (!process.env.BYBIT_API_KEY || !process.env.BYBIT_API_SECRET || !process.env.GEMINI_API_KEY) {
        logger.error("FATAL: API keys are not configured. Please check your .env file.");
        process.exit(1);
    }
}

async function main() {
    logger.info("--- Initializing Gemini-Bybit Trading Bot v2.1 ---");
    validateEnv();

    if (config.dryRun) {
        logger.warn("*************************************************");
        logger.warn("*    DRY RUN MODE IS ENABLED.                    *");
        logger.warn("*    No real trades will be executed.            *");
        logger.warn("*************************************************");
    }

    const tradingSystem = new TradingAiSystem();

    const ws = new BybitWebSocket(() => tradingSystem.runAnalysisCycle());
    ws.connect();

    // Perform an initial run on startup to sync state immediately.
    setTimeout(() => tradingSystem.runAnalysisCycle(), 5000);

    // NEW: Periodic health check
    setInterval(() => {
        logger.info(`[HEALTH CHECK] Bot is running. WebSocket state: ${ws.ws?.readyState}`);
    }, 3600 * 1000); // Every hour
}

// NEW: Graceful shutdown
const shutdown = () => {
    logger.info("Shutdown signal received. Shutting down gracefully...");
    // Here you could add logic to close open positions if desired
    process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

main().catch(error => {
    logger.exception(error);
    process.exit(1);
});