// src/utils/logger.js
import fs from 'fs';

const logStream = fs.createWriteStream('bot.log', { flags: 'a' });
const getTimestamp = () => new Date().toISOString();

const logToFile = (message) => {
    logStream.write(`${message}\n`);
};

const logger = {
    info: (message) => {
        const formatted = `[INFO][${getTimestamp()}] ${message}`;
        console.log(formatted);
        logToFile(formatted);
    },
    warn: (message) => {
        const formatted = `[WARN][${getTimestamp()}] ${message}`;
        console.warn(formatted);
        logToFile(formatted);
    },
    error: (message, error) => {
        const formatted = `[ERROR][${getTimestamp()}] ${message}`;
        console.error(formatted);
        logToFile(formatted);
        if (error) {
            const errorStack = error.stack || error.toString();
            console.error(errorStack);
            logToFile(errorStack);
        }
    },
    exception: (error) => {
        const message = `[EXCEPTION][${getTimestamp()}] An uncaught exception occurred:`
        console.error(message);
        logToFile(message);
        const errorStack = error.stack || error.toString();
        console.error(errorStack);
        logToFile(errorStack);
    }
};

export default logger;
