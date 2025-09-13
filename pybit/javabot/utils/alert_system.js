import { execSync } from 'child_process';
import { logger } from '../logger.js';
import chalk from 'chalk';

class AlertSystem {
    constructor() {
        this.termux_api_available = this._check_termux_api();
    }

    _check_termux_api() {
        try {
            execSync('which termux-toast', { stdio: 'pipe' });
            return true;
        } catch (e) {
            logger.warn(chalk.yellow("Termux toast notifications disabled (command not found)."));
            return false;
        }
    }

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
