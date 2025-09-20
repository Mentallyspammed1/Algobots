import chalk from 'chalk';

const logger = {
    info: (msg) => console.log(chalk.cyan(`[INFO] ${msg}`)),
    success: (msg) => console.log(chalk.green(`[SUCCESS] ${msg}`)),
    warn: (msg) => console.log(chalk.yellow(`[WARN] ${msg}`)),
    error: (msg) => console.log(chalk.red(`[ERROR] ${msg}`)),
    debug: (msg) => console.log(chalk.blue(`[DEBUG] ${msg}`)),
    critical: (msg) => console.log(chalk.bold.red(`[CRITICAL] ${msg}`))
};

export default logger;