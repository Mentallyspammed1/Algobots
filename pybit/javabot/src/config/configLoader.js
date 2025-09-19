import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';
import dotenv from 'dotenv';
import { configSchema } from './schema.js';
import { logger, neon } from '../../logger.js'; // Adjust path to logger
import lodash from 'lodash';

const { merge } = lodash;

dotenv.config(); // Load .env file

const DEFAULT_CONFIG_PATH = "config.yaml";

/**
 * Loads the YAML configuration file.
 * @param {string} configPath - The path to the YAML config file.
 * @returns {object} The parsed configuration object from the file.
 */
function loadFileConfig(configPath) {
    try {
        const fullPath = path.resolve(process.cwd(), configPath);
        if (fs.existsSync(fullPath)) {
            const fileContents = fs.readFileSync(fullPath, 'utf8');
            const loadedYaml = yaml.load(fileContents) || {};
            logger.info(neon.green(`Configuration successfully loaded from ${configPath}.`));
            return loadedYaml;
        }
    } catch (e) {
        logger.error(neon.error(`Error loading config file '${configPath}': ${e.message}.`));
    }
    logger.warn(neon.warn(`Configuration file not found at '${configPath}'. Using defaults.`));
    return {};
}

/**
 * Loads configuration from environment variables.
 * This is a placeholder to show how you might override specific nested values.
 * @returns {object} A configuration object derived from environment variables.
 */
function loadEnvConfig() {
    const envConfig = {};
    if (process.env.BYBIT_API_KEY) {
        merge(envConfig, { common: { API_KEY: process.env.BYBIT_API_KEY } });
    }
    if (process.env.BYBIT_API_SECRET) {
        merge(envConfig, { common: { API_SECRET: process.env.BYBIT_API_SECRET } });
    }
    if (process.env.TESTNET) {
        merge(envConfig, { common: { TESTNET: process.env.TESTNET } });
    }
    if (process.env.DRY_RUN) {
        merge(envConfig, { common: { DRY_RUN: process.env.DRY_RUN } });
    }
    // Add other environment variable mappings here if needed
    return envConfig;
}

/**
 * Initializes and validates the application configuration.
 * @returns {object} The final, validated configuration object.
 */
function initializeConfig() {
    // 1. Get defaults from the Zod schema itself
    const defaultConfig = configSchema.parse({});

    // 2. Load config from YAML file
    const fileConfig = loadFileConfig(DEFAULT_CONFIG_PATH);

    // 3. Load overrides from environment variables
    const envConfig = loadEnvConfig();

    // 4. Deep merge all configurations: defaults < file < environment
    const finalConfigObject = merge(defaultConfig, fileConfig, envConfig);

    try {
        // 5. Validate the final merged configuration against the schema
        const validatedConfig = configSchema.parse(finalConfigObject);
        logger.info(neon.green('Configuration validated successfully.'));

        if (validatedConfig.common.DRY_RUN) {
            logger.warn(neon.warn('Bot is running in DRY RUN mode. No real trades will be executed.'));
        }

        // Validate required API keys for non-dry-run mode
        if (!validatedConfig.common.DRY_RUN && (!validatedConfig.common.API_KEY || !validatedConfig.common.API_SECRET)) {
            logger.error(neon.error("CRITICAL: API_KEY and API_SECRET must be provided in .env or config.yaml for live trading."));
            process.exit(1);
        }

        return validatedConfig;

    } catch (error) {
        logger.error(neon.error('Configuration validation failed:'));
        error.errors.forEach(err => {
            logger.error(neon.error(`  - Path: ${err.path.join('.')}, Message: ${err.message}`));
        });
        process.exit(1);
    }
}

export const CONFIG = initializeConfig();
