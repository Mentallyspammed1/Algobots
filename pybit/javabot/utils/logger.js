const winston = require('winston');
require('winston-daily-rotate-file');
const chalk = require('chalk');

const LOG_DIRECTORY = "bot_logs/trading-bot/logs"; // Assuming this path is consistent

/**
 * Creates a custom printf format function for Winston that redacts sensitive words.
 * @param {function(object): string} template - The original template function for log messages.
 * @param {Array<string>} sensitiveWords - An array of words to redact from log messages.
 * @returns {function(object): string} A Winston format function.
 */
const sensitivePrintf = (template, sensitiveWords) => {
    const escapeRegExp = (string) => {
        return string.replace(/[.*+?^${}()|[\/\\]/g, '\\$&');
    };
    return winston.format.printf(info => {
        let message = template(info);
        for (const word of sensitiveWords) {
            if (typeof word === 'string' && message.includes(word)) {
                const escapedWord = escapeRegExp(word);
                message = message.replace(new RegExp(escapedWord, 'g'), '*'.repeat(word.length));
            }
        }
        return message;
    });
};

/**
 * Sets up a Winston logger with console and daily rotating file transports.
 * Sensitive words can be provided to be redacted from log messages.
 * @param {string} log_name - The base name for the log files.
 * @param {string} [level='info'] - The minimum level of messages to log (e.g., 'info', 'debug', 'error').
 * @param {Array<string>} [sensitiveWords=[]] - An array of words to redact from log messages.
 * @returns {winston.Logger} The configured Winston logger instance.
 */
const setupLogger = (log_name, level = 'info', sensitiveWords = []) => {
    const logger = winston.createLogger({
        level: level,
        format: winston.format.combine(
            winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
            winston.format.errors({ stack: true }),
            sensitivePrintf(info => `${info.timestamp} - ${info.level.toUpperCase()} - ${info.message}`, sensitiveWords)
        ),
        transports: [
            new winston.transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${log_name}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '10m',
                maxFiles: '5d'
            }),
            new winston.transports.Console({
                format: winston.format.combine(
                    winston.format.timestamp({ format: 'HH:mm:ss.SSS' }),
                    sensitivePrintf(info => {
                        let levelColor;
                        switch (info.level) {
                            case 'info': levelColor = chalk.cyan; break;
                            case 'warn': levelColor = chalk.yellow; break;
                            case 'error': levelColor = chalk.red; break;
                            case 'debug': levelColor = chalk.blue; break;
                            case 'critical': levelColor = chalk.magentaBright; break;
                            default: levelColor = chalk.white;
                        }
                        return `${levelColor(info.timestamp)} - ${levelColor(info.level.toUpperCase())} - ${levelColor(info.message)}`;
                    }, sensitiveWords)
                )
            })
        ],
        exitOnError: false
    });
    return logger;
};

module.exports = setupLogger;
