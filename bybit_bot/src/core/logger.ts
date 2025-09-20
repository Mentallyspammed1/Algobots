import winston from 'winston';
import dotenv from 'dotenv';
import fs from 'fs';

dotenv.config();

const logDir = 'logs';

// Create the log directory if it does not exist
if (!fs.existsSync(logDir)) {
  fs.mkdirSync(logDir);
}

const logLevel = process.env.LOG_LEVEL || 'info';

// Define a neon color theme
const neon_colors = {
    error: 'bold red',
    warn: 'bold yellow',
    info: 'bold cyan',
    debug: 'bold magenta',
    success: 'bold green',
    system: 'bold blue',
};

winston.addColors(neon_colors);

const { combine, timestamp, printf, colorize } = winston.format;

// Custom format for the console to add icons and style
const consoleFormat = combine(
    colorize({ all: true }),
    timestamp({ format: 'HH:mm:ss' }),
    printf((info) => {
        const { timestamp, level, message, ...args } = info;
        const ts = timestamp.slice(0, 8);
        let icon = '⚙️';
        if (level.includes('error')) icon = '❌';
        if (level.includes('warn')) icon = '⚠️';
        if (level.includes('success')) icon = '✅';
        if (level.includes('info')) icon = 'ℹ️';

        return `${icon} [${ts}] ${level}: ${message} ${Object.keys(args).length ? JSON.stringify(args, null, 2) : ''}`;
    })
);

const logger = winston.createLogger({
  level: logLevel,
  levels: {
      error: 0,
      warn: 1,
      success: 2,
      system: 2,
      info: 2,
      debug: 3,
  },
  transports: [
    // File transport remains plain and structured
    new winston.transports.File({
      filename: `${logDir}/app.log`,
      format: combine(
        timestamp({ format: 'YYYY-MM-DD HH:mm:ss.SSS' }),
        printf((info) => `[${info.timestamp}] ${info.level.toUpperCase()}: ${info.message} ${Object.keys(info).slice(3).length ? JSON.stringify(info, null, 2) : ''}`)
      ),
    }),
    // Console transport gets the neon theme
    new winston.transports.Console({
        format: consoleFormat,
    }),
  ],
});

// Re-export with standard names for compatibility
const customLogger = {
    info: (message: string, ...args: any[]) => logger.info(message, ...args),
    warn: (message: string, ...args: any[]) => logger.warn(message, ...args),
    error: (message: string, ...args: any[]) => logger.error(message, ...args),
    debug: (message: string, ...args: any[]) => logger.debug(message, ...args),
    success: (message: string, ...args: any[]) => (logger as any).success(message, ...args),
    system: (message: string, ...args: any[]) => (logger as any).system(message, ...args),
};

export { customLogger as logger };