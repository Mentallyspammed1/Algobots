import { CONFIG } from './config.js';
import { logger, neon } from './logger.js';

/**
 * @async
 * @function startStrategy
 * @description Dynamically imports and executes a trading strategy module.
 * It expects the strategy module to export either a `main` or `run_bot` async function.
 * @param {string} strategyName - The name of the strategy to start (e.g., "ehlst_strategy").
 * @param {Object} strategyConfig - The configuration object for the specific strategy.
 * @returns {Promise<void>} A promise that resolves when the strategy has finished execution or rejects if an error occurs.
 */
async function startStrategy(strategyName, strategyConfig) {
    logger.debug(`startStrategy: Attempting to start strategy: ${strategyName} with config: ${JSON.stringify(strategyConfig)}`);
    try {
        logger.info(neon.header(`Attempting to start strategy: ${strategyName}`));
        // Dynamically import the strategy module
        logger.debug(`startStrategy: Dynamically importing strategy module: ./strategies/${strategyName}_strategy.js`);
        const strategyModule = await import(`./strategies/${strategyName}_strategy.js`);
        logger.debug(`startStrategy: Strategy module imported for ${strategyName}.`);
        
        // Assuming each strategy module exports a main or run_bot function
        // And that these functions can accept a config object
        if (typeof strategyModule.main === 'function') {
            logger.debug(`startStrategy: Invoking 'main' function for ${strategyName}.`);
            await strategyModule.main(strategyConfig); // Pass strategyConfig
        } else if (typeof strategyModule.run_bot === 'function') {
            logger.debug(`startStrategy: Invoking 'run_bot' function for ${strategyName}.`);
            await strategyModule.run_bot(strategyConfig); // Pass strategyConfig
        } else {
            logger.error(neon.error(`Strategy ${strategyName} does not export a 'main' or 'run_bot' function.`));
        }
        logger.info(neon.success(`Strategy ${strategyName} started successfully.`));
        logger.debug(`startStrategy: Strategy ${strategyName} execution complete.`);
    } catch (error) {
        logger.critical(neon.error(`Failed to start strategy ${strategyName}: ${error.message}`), error);
        logger.debug(`startStrategy: Error details: ${error.stack}`);
    }
}

/**
 * @async
 * @function main
 * @description The main orchestration function for the bot. It identifies enabled strategies
 * from the `CONFIG` and initiates their execution concurrently.
 * Logs warnings if no strategies are enabled.
 * @returns {Promise<void>} A promise that resolves when all enabled strategies have been processed.
 */
async function main() {
    logger.info(neon.header('Bot Orchestrator Initiated!'));
    logger.debug('main: Bot Orchestrator main function started.');

    const enabledStrategies = Object.entries(CONFIG.STRATEGIES)
        .filter(([, strategyConfig]) => strategyConfig.enabled)
        .map(([strategyName]) => strategyName);

    if (enabledStrategies.length === 0) {
        logger.warn(neon.warn('No enabled strategies defined in config.js. Exiting.'));
        logger.debug('main: No enabled strategies found, exiting main function.');
        return;
    }

    logger.info(neon.info(`Enabled strategies: ${enabledStrategies.join(', ')}`));
    logger.debug(`main: Strategies to execute: ${JSON.stringify(enabledStrategies)}`);

    logger.debug('main: Mapping enabled strategies to startStrategy promises.');
    const strategyPromises = enabledStrategies.map(strategyName => {
        const strategyConfig = CONFIG.STRATEGIES[strategyName];
        return startStrategy(strategyName, strategyConfig); // Pass strategyConfig
    });
    
    logger.debug('main: Awaiting all strategy promises to settle.');
    await Promise.allSettled(strategyPromises);
    logger.debug('main: All strategy promises have settled.');

    logger.info(neon.header('All enabled strategies have been processed. Orchestrator finishing.'));
    logger.debug('main: Bot Orchestrator main function finished.');
}

/**
 * @description Immediately invoked async function to run the main orchestrator logic.
 * Handles any unhandled errors during the orchestration process.
 */
(async () => {
    try {
        await main();
    } catch (err) {
        logger.critical(neon.error(`Unhandled error in orchestrator main loop: ${err.message}`), err);
        process.exit(1);
    }
})();