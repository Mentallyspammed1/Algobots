// src/utils/logger.js
import { Constants } from './constants.js';

const { COLOR_CODES } = Constants;

export class Logger {
    constructor(moduleName = 'APP') {
        this.moduleName = moduleName;
        this.timestamp = () => new Date().toISOString();
    }

    _log(level, message, colorCode, data = null) {
        const dataString = data ? `
${JSON.stringify(data, null, 2)}` : '';
        console.log(`${colorCode}[${this.timestamp()}] [${this.moduleName}] [${level}] ${message}${dataString}${COLOR_CODES.RESET}`);
    }

    info(message, data = null) {
        this._log('INFO', message, COLOR_CODES.CYAN, data);
    }

    warn(message, data = null) {
        this._log('WARN', message, COLOR_CODES.YELLOW, data);
    }

    error(message, data = null) {
        this._log('ERROR', message, COLOR_CODES.RED, data);
    }

    debug(message, data = null) {
        if (process.env.NODE_ENV === 'development') { // Only log debug in dev environment
            this._log('DEBUG', message, COLOR_CODES.MAGENTA, data);
        }
    }

    log(message, data = null) {
        this._log('LOG', message, COLOR_CODES.WHITE, data);
    }

    exception(message, error, data = null) {
        this._log('EXCEPTION', `${message} ${error.message}`, COLOR_CODES.RED, {
            errorStack: error.stack,
            ...data
        });
    }
}
