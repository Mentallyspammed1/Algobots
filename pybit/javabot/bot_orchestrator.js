import { CONFIG } from './src/config/configLoader.js';
import { logger, neon } from './logger.js';
import BybitAPIClient from './bybit_api_client.js';

/**
 * @async
 * @function startStrategy
 * @description Dynamically imports and executes a trading strategy module.
 * It expects the strategy module to export either a `main` or `run_bot` async function.
 * @param {string} strategyName - The name of the strategy to start (e.g., "ehlst_strategy").
 * @param {Object} strategyConfig - The configuration object for the specific strategy.
 * @param {BybitAPIClient} bybitClient - The initialized Bybit API client instance.
 * @returns {Promise<void>} A promise that resolves when the strategy has finished execution or rejects if an error occurs.
 */
async function startStrategy(strategyName, strategyConfig, bybitClient) {
    logger.debug(`startStrategy: Attempting to start strategy: ${strategyName} with config: ${JSON.stringify(strategyConfig)}`);
    try {
        logger.info(neon.header(`Attempting to start strategy: ${strategyName}`));
        // Construct the module path for dynamic import
        logger.debug(`startStrategy: Dynamically importing strategy module: ./strategies/${strategyName}_strategy.js`);
        const strategyModule = await import(`./strategies/${strategyName}_strategy.js`);
        logger.debug(`startStrategy: Strategy module imported for ${strategyName}.`);
        
        // Check for and invoke the strategy's entry point function (main or run_bot)
        // Pass the strategy-specific configuration and the bybitClient to the entry point
        if (typeof strategyModule.main === 'function') {
            logger.debug(`startStrategy: Invoking 'main' function for ${strategyName}.`);
            await strategyModule.main(strategyConfig, bybitClient); // Pass strategyConfig and bybitClient
        } else if (typeof strategyModule.run_bot === 'function') {
            logger.debug(`startStrategy: Invoking 'run_bot' function for ${strategyName}.`);
            await strategyModule.run_bot(strategyConfig, bybitClient); // Pass strategyConfig and bybitClient
        } else {
            // Log an error if the strategy module does not export a recognized entry point
            logger.error(neon.error(`Strategy ${strategyName} does not export a 'main' or 'run_bot' function.`));
        }
        logger.info(neon.success(`Strategy ${strategyName} started successfully.`));
        logger.debug(`startStrategy: Strategy ${strategyName} execution complete.`);
    } catch (error) {
        // Catch and log any errors that occur during strategy import or execution
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

    // Initialize the Bybit API client once for all strategies
    const bybitClient = new BybitAPIClient(CONFIG.common);

    // Filter and collect the names of all enabled strategies from the new configuration structure
    const enabledStrategies = Object.entries(CONFIG.strategies)
        .filter(([, strategyConfig]) => strategyConfig.enabled)
        .map(([strategyName]) => strategyName);

    // If no strategies are enabled in the configuration, log a warning and exit
    if (enabledStrategies.length === 0) {
        logger.warn(neon.warn('No enabled strategies found in config.yaml. Exiting.'));
        logger.debug('main: No enabled strategies found, exiting main function.');
        return;
    }

    logger.info(neon.info(`Enabled strategies: ${enabledStrategies.join(', ')}`));
    logger.debug(`main: Strategies to execute: ${JSON.stringify(enabledStrategies)}`);

    // Create an array of promises, each representing the asynchronous execution of a strategy
    logger.debug('main: Mapping enabled strategies to startStrategy promises.');
    const strategyPromises = enabledStrategies.map(strategyName => {
        // Pass the common config, indicator config, and specific strategy config
        const combinedConfig = {
            ...CONFIG.common,
            ...CONFIG.indicators,
            ...CONFIG.strategies[strategyName]
        };
        return startStrategy(strategyName, combinedConfig, bybitClient);
    });
    
    // Wait for all strategy execution promises to complete (either resolve or reject)
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
        // Catch any unhandled errors from the main orchestration flow and log them critically
        logger.critical(neon.error(`Unhandled error in orchestrator main loop: ${err.message}`), err);
        process.exit(1); // Exit the process on critical unhandled errors
    }
})();
