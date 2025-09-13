const BotRunner = require('./core/bot_runner.js');
const setupLogger = require('./utils/logger.js');
const { UNIFIED_CONFIG } = require('./config/unified_config.js');

const logger = setupLogger('main_entry', UNIFIED_CONFIG.bot.logLevel, [UNIFIED_CONFIG.api.key, UNIFIED_CONFIG.api.secret]);

async function start() {
    // Basic check for API keys
    if (!UNIFIED_CONFIG.api.key || !UNIFIED_CONFIG.api.secret || UNIFIED_CONFIG.api.key === 'YOUR_API_KEY' || UNIFIED_CONFIG.api.secret === 'YOUR_API_SECRET') {
        logger.critical("API_KEY or API_SECRET not set. Please configure your .env file or unified_config.js.");
        process.exit(1);
    }

    const botRunner = new BotRunner();
    try {
        await botRunner.run();
    } catch (err) {
        logger.critical(`Bot terminated due to a fatal error: ${err.message}`);
        process.exit(1);
    }
}

if (require.main === module) {
    start();
}