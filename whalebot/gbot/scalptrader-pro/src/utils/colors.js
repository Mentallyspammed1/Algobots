const chalk = require('chalk');

const NEON = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#00AFFF'),
    CYAN: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'), GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'), BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
};

module.exports = NEON;
