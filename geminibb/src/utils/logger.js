const RESET = "\x1b[0m";
const NEON_RED = "\x1b[38;5;196m";
const NEON_GREEN = "\x1b[38;5;46m";
const NEON_YELLOW = "\x1b[38;5;226m";
const NEON_BLUE = "\x1b[38;5;39m";

const getTimestamp = () => new Date().toISOString();

const logger = {
    info: (message) => console.log(`${NEON_GREEN}[INFO][${getTimestamp()}] ${message}${RESET}`),
    warn: (message) => console.warn(`${NEON_YELLOW}[WARN][${getTimestamp()}] ${message}${RESET}`),
    error: (message) => console.error(`${NEON_RED}[ERROR][${getTimestamp()}] ${message}${RESET}`),
    debug: (message) => console.log(`${NEON_BLUE}[DEBUG][${getTimestamp()}] ${message}${RESET}`),
    exception: (error) => {
        if (error instanceof Error) {
            console.error(`${NEON_RED}[EXCEPTION][${getTimestamp()}] ${error.message}\n${error.stack}${RESET}`);
        } else {
            console.error(`${NEON_RED}[EXCEPTION][${getTimestamp()}] ${String(error)}${RESET}`);
        }
    },
};

export default logger;