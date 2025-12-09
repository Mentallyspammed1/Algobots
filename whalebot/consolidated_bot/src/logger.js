import winston from 'winston';
import path from 'path';
import fs from 'fs';
import dotenv from 'dotenv';
import { Decimal } from 'decimal.js'; // For precise calculations
import { ConfigManager } from './config.js'; // To access config settings like LOG_LEVEL
import { fileURLToPath } from 'url'; // Needed for __dirname in ES modules

// Resolve __dirname in ES module context
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load environment variables from .env file if it exists
if (fs.existsSync(path.join(__dirname, '.env'))) {
    Object.assign(process.env, dotenv.parse(fs.readFileSync(path.join(__dirname, '.env'))));
}

// Configure Winston logger
const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || ConfigManager.DEFAULTS.logLevel || 'info', // Default to 'info' or config value
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }), // Timestamp for logs
        winston.format.errors({ stack: true }), // Include stack trace for errors
        winston.format.splat(), // Support string interpolation like printf
        winston.format.json(), // Output logs in JSON format
    ),
    defaultMeta: { 
        service: 'leviathan-bot', 
        version: '3.6.2' // Version from config or package.json
    },
    transports: [
        // Log errors to a separate file
        new winston.transports.File({ filename: 'error.log', level: 'error' }),
        // Log all other levels to a general log file
        new winston.transports.File({ filename: 'leviathan.log' }),
        // Log info and above to the console
        new winston.transports.Console({
            format: winston.format.combine(
                winston.format.colorize({ all: true }), // Colorize console output
                winston.format.simple() // Use simple format for console
            ),
            level: 'info' // Console log level
        }),
    ],
});

// Add custom colors for success messages
winston.addColors({ success: 'green' });
// Helper for success logs
logger.success = (msg) => logger.info(`✅ ${msg}`);

// Validate required environment variables
const REQUIRED_ENV = ['BYBIT_API_KEY', 'BYBIT_API_SECRET', 'GEMINI_API_KEY'];
const missingEnv = REQUIRED_ENV.filter(key => !process.env[key]);
if (missingEnv.length > 0) {
    logger.error(`[FATAL] Missing required environment variables: ${missingEnv.join(', ')}. Please set them in your .env file or system environment.`);
    // Consider exiting here if critical env vars are missing, or handle gracefully if possible
    // process.exit(1); 
}

export default logger;