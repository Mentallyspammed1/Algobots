// src/utils/constants.js
export const Constants = {
    APP_VERSION: '1.0.0-beta',
    AI_MODEL_DEFAULTS: {
        MODEL_NAME: 'gemini-1.5-flash',
        TEMPERATURE: 0.7,
        TOP_P: 0.95,
        TOP_K: 64,
        MAX_OUTPUT_TOKENS: 8192
    },
    RETRY_DEFAULTS: {
        MAX_ATTEMPTS: 5,
        INITIAL_DELAY_MS: 100,
        MAX_DELAY_MS: 2000,
        JITTER_FACTOR: 0.5
    },
    API_URLS: {
        GEMINI_BASE: 'https://generativelanguage.googleapis.com',
        BYBIT_REST_MAINNET: 'https://api.bybit.com',
        BYBIT_REST_TESTNET: 'https://api-testnet.bybit.com',
        BYBIT_WS_PUBLIC_MAINNET: 'wss://stream.bybit.com/v5/public',
        BYBIT_WS_PUBLIC_TESTNET: 'wss://stream-testnet.bybit.com/v5/public'
    },
    COLOR_CODES: {
        RESET: '\x1b[0m',
        BRIGHT: '\x1b[1m',
        DIM: '\x1b[2m',
        UNDERSCORE: '\x1b[4m',
        BLINK: '\x1b[5m',
        REVERSE: '\x1b[7m',
        HIDDEN: '\x1b[8m',

        BLACK: '\x1b[30m',
        RED: '\x1b[31m',
        GREEN: '\x1b[32m',
        YELLOW: '\x1b[33m',
        BLUE: '\x1b[34m',
        MAGENTA: '\x1b[35m',
        CYAN: '\x1b[36m',
        WHITE: '\x1b[37m',
        GRAY: '\x1b[90m',

        BG_BLACK: '\x1b[40m',
        BG_RED: '\x1b[41m',
        BG_GREEN: '\x1b[42m',
        BG_YELLOW: '\x1b[43m',
        BG_BLUE: '\x1b[44m',
        BG_MAGENTA: '\x1b[45m',
        BG_CYAN: '\x1b[46m',
        BG_WHITE: '\x1b[47m'
    }
};

export const OrderStatus = {
    NEW: 'NEW',
    PARTIALLY_FILLED: 'PARTIALLY_FILLED',
    FILLED: 'FILLED',
    CANCELED: 'CANCELED',
    REJECTED: 'REJECTED',
    EXPIRED: 'EXPIRED'
};

export const CandlestickIntervals = {
    '1m': '1',
    '3m': '3',
    '5m': '5',
    '15m': '15',
    '30m': '30',
    '1h': '60',
    '2h': '120',
    '4h': '240',
    '6h': '360',
    '12h': '720',
    '1d': 'D',
    '1w': 'W',
    '1M': 'M'
};