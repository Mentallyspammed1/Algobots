
const logLevels = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3,
    OFF: 4
};

let currentLogLevel = logLevels.INFO; // Default log level

const logger = {
    setLogLevel: function(level) {
        if (logLevels[level] !== undefined) {
            currentLogLevel = logLevels[level];
            console.log(`Log level set to: ${level}`);
        } else {
            console.error(`Invalid log level: ${level}. Valid levels are: ${Object.keys(logLevels).join(', ')}`);
        }
    },

    debug: function(message) {
        if (currentLogLevel <= logLevels.DEBUG) {
            console.log(`[${new Date().toISOString()}] [DEBUG] ${message}`);
        }
    },

    info: function(message) {
        if (currentLogLevel <= logLevels.INFO) {
            console.log(`[${new Date().toISOString()}] [INFO] ${message}`);
        }
    },

    warn: function(message) {
        if (currentLogLevel <= logLevels.WARN) {
            console.warn(`[${new Date().toISOString()}] [WARN] ${message}`);
        }
    },

    error: function(message) {
        if (currentLogLevel <= logLevels.ERROR) {
            console.error(`[${new Date().toISOString()}] [ERROR] ${message}`);
        }
    }
};

export default logger;
