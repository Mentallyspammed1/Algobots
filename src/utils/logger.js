const colors = {
    reset: '\x1b[0m',
    black: '\x1b[30m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
    white: '\x1b[37m',
    gray: '\x1b[90m',
    brightRed: '\x1b[91m',
    brightGreen: '\x1b[92m',
    brightYellow: '\x1b[93m',
    brightBlue: '\x1b[94m',
    brightMagenta: '\x1b[95m',
    brightCyan: '\x1b[96m',
    brightWhite: '\x1b[97m',
    bold: '\x1b[1m',
    dim: '\x1b[2m',
    underscore: '\x1b[4m',
    neonPink: '\x1b[38;5;198m',
    neonOrange: '\x1b[38;5;208m',
    neonLime: '\x1b[38;5;154m',
    neonBlue: '\x1b[38;5;39m',
};

function color(text, colorCode) {
    return `${colorCode}${text}${colors.reset}`;
}

let currentLogLevel = 'info';

function log(level, message, colorCode = colors.gray) {
    const levels = { silent: 0, error: 1, warn: 2, info: 3, debug: 4 };
    if (levels[currentLogLevel] >= levels[level]) {
        const now = new Date().toLocaleTimeString();
        console.log(color(`[${now}] [${level.toUpperCase()}] ${message}`, colorCode));
    }
}

function setLogLevel(level) {
    currentLogLevel = level;
}

module.exports = {
    colors,
    color,
    log,
    setLogLevel,
};
