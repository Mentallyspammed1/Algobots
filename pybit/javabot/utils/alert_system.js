import { execSync } from 'child_process';
import { logger } from '../logger.js';
import chalk from 'chalk';

/**
 * @class AlertSystem
 * @description Provides a system for sending alerts, including logging and Termux toast notifications.
 */
class AlertSystem {
    /**
     * @constructor
     * @description Initializes the AlertSystem and checks for Termux API availability.
     */
    constructor() {
        /**
         * @property {boolean} termux_api_available - Indicates if Termux API is available for toast notifications.
         */
        this.termux_api_available = this._check_termux_api();
    }

    /**
     * @private
     * @method _check_termux_api
     * @description Checks if the `termux-toast` command is available in the system.
     * @returns {boolean} True if `termux-toast` is found, false otherwise.
     */
    _check_termux_api() {
        try {
            execSync('which termux-toast', { stdio: 'pipe' });
            return true;
        } catch (e) {
            logger.warn(chalk.yellow("Termux toast notifications disabled (command not found)."));
            return false;
        }
    }

    /**
     * @method send_alert
     * @description Sends an alert message, logging it and optionally displaying it as a Termux toast.
     * @param {string} message - The alert message to send.
     * @param {string} [level="INFO"] - The severity level of the alert ("INFO", "WARNING", "ERROR").
     * @returns {void}
     */
    send_alert(message, level = "INFO") {
        const colorMap = {
            INFO: chalk.blue,
            WARNING: chalk.yellow,
            ERROR: chalk.red
        };
        const prefixMap = {
            INFO: "ℹ️ ",
            WARNING: "⚠️ ",
            ERROR: "⛔ "
        };

        const color = colorMap[level] || chalk.white;
        const prefix = prefixMap[level] || "";
        logger.log(level.toLowerCase(), `${prefix}${message}`);

        if (this.termux_api_available) {
            try {
                execSync(`termux-toast "${prefix}${message}"`, { timeout: 5000 });
            } catch (e) {
                logger.error(chalk.red(`Termux toast failed: ${e.message}`));
            }
        }
    }
}

export default AlertSystem;