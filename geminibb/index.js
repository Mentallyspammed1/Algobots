// index.js
import dotenv from 'dotenv';
import { TradingAISystem } from './src/trading_ai_system.js';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const config = require('./config.json');
import { Logger } from './src/utils/logger.js';
import { Constants } from './src/utils/constants.js';

dotenv.config(); // Load environment variables from .env

const logger = new Logger('MAIN');

async function main() {
    // Validate essential environment variables
    if (!process.env.GEMINI_API_KEY) {
        logger.error('GEMINI_API_KEY is not set in environment variables. Exiting.');
        process.exit(1);
    }

    if (process.env.BYBIT_API_KEY && !process.env.BYBIT_API_SECRET) {
        logger.warn('BYBIT_API_KEY is set, but BYBIT_API_SECRET is missing. Bybit integration will be disabled.');
    }

    logger.info(`Starting AI Trading Bot (Version: ${Constants.APP_VERSION})`);
    logger.debug('Configuration loaded:', JSON.stringify(config, null, 2));

    try {
        const tradingAISystem = new TradingAISystem(
            process.env.GEMINI_API_KEY,
            process.env.BYBIT_API_KEY,
            process.env.BYBIT_API_SECRET,
                        process.env.USE_TESTNET === 'true',
            config
        );

        logger.info('Performing quantitative analysis for BTC/USDT...');
        const analysisResult = await tradingAISystem.performQuantitativeAnalysis('BTCUSDT', '1h');
        logger.info('Quantitative Analysis Result:', JSON.stringify(analysisResult, null, 2));

        // Example: Starting a conceptual live trading session
        // Note: This is conceptual and would involve a continuous loop.
        // await tradingAISystem.startLiveTradingSession('BTCUSDT', '1h');

    } catch (error) {
        logger.exception('An unhandled error occurred in main execution:', error);
    }
}

main();