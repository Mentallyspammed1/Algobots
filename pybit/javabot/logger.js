import { createLogger, format, transports } from 'winston';
import chalk from 'chalk';
import fs from 'fs';
import path from 'path';
import { CONFIG } from './config.js';

// ====================== 
// NEON THEME (from market-maker.js) 
// ====================== 
const neon = {
  info: chalk.hex('#00FFFF').bold,
  success: chalk.hex('#00FF00').bold,
  warn: chalk.hex('#FFAA00').bold,
  error: chalk.hex('#FF0000').bold,
  price: chalk.hex('#00FFAA').bold,
  pnl: (val) => (val >= 0 ? chalk.hex('#00FF00').bold : chalk.hex('#FF0000').bold)(val.toFixed(6)),
  bid: chalk.hex('#00AAFF').bold,
  ask: chalk.hex('#FF55FF').bold,
  header: chalk.hex('#FFFFFF').bgHex('#001122').bold,
  dim: chalk.dim,
};

// ====================== 
// LOGGER 
// ====================== 
const logDir = './bot_logs'; // Centralized log directory
if (!fs.existsSync(logDir)) fs.mkdirSync(logDir);

const customFormat = format.printf(({ level, message, timestamp, stack }) => {
    let formattedMessage = message;
    // Apply neon colors for console output
    if (process.stdout.isTTY) {
        switch (level) {
            case 'info':
                formattedMessage = neon.info(message);
                break;
            case 'warn':
                formattedMessage = neon.warn(message);
                break;
            case 'error':
                formattedMessage = neon.error(message);
                break;
            case 'debug':
                formattedMessage = chalk.cyan(message);
                break;
            case 'critical':
                formattedMessage = chalk.bold.red(message);
                break;
            default:
                formattedMessage = chalk.white(message);
        }
    }
    return `${timestamp} [${level.toUpperCase()}]: ${formattedMessage}${stack ? '\n' + stack : ''}`;
});

export const logger = createLogger({
  level: CONFIG.LOG_LEVEL || 'info',
  format: format.combine(
    format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
    format.errors({ stack: true }),
    customFormat
  ),
  transports: [
    new transports.Console(),
    ...(CONFIG.LOG_TO_FILE ? [new transports.File({ filename: path.join(logDir, 'bot.log') })] : []),
    new transports.File({ filename: path.join(logDir, 'exceptions.log'), level: 'error' }) // Separate file for errors
  ],
  exceptionHandlers: [
    new transports.File({ filename: path.join(logDir, 'exceptions.log') })
  ],
  rejectionHandlers: [
    new transports.File({ filename: path.join(logDir, 'rejections.log') })
  ]
});

// Export neon theme for direct use in modules if needed
export { neon };
