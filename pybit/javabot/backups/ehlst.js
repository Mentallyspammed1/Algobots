const fs = require('fs');
const path = require('path');
const process = require('process');
const yaml = require('js-yaml');
const axios = require('axios');
const CryptoJS = require('crypto-js');
const { calculateEhlSupertrendIndicators } = require('./stindicators.js');
const { DateTime, Settings } = require('luxon');
const { randomUUID } = require('crypto');
require('dotenv').config();
require('dotenv').config();

const colors = {
    GREEN: '\x1b[32m',
    RED: '\x1b[31m',
    YELLOW: '\x1b[33m',
    BLUE: '\x1b[34m',
    MAGENTA: '\x1b[35m',
    CYAN: '\x1b[36m',
    WHITE: '\x1b[37m',
    RESET: '\x1b[0m',
    BOLD: '\x1b[1m',
    LIGHTYELLOW_EX: '\x1b[93m',
    LIGHTGREEN_EX: '\x1b[92m',
    LIGHTCYAN_EX: '\x1b[96m'
};

class Logger {
    constructor() {
        this.level = 'INFO';
        this.isTTY = process.stdout.isTTY;
    }

    setLevel(level) {
        this.level = level.toUpperCase();
    }

    _log(level, message, color = colors.WHITE) {
        const timestamp = DateTime.local().toFormat('yyyy-MM-dd HH:mm:ss');
        const levelName = level.toUpperCase();

        const levels = {
            'DEBUG': 0,
            'INFO': 1,
            'WARNING': 2,
            'ERROR': 3,
            'CRITICAL': 4
        };

        if (levels[levelName] < levels[this.level]) {
            return;
        }

        let formattedMessage;
        if (this.isTTY) {
            formattedMessage = `${color}${timestamp} - BOT - ${levelName} - ${message}${colors.RESET}`;
        } else {
            formattedMessage = `${timestamp} - BOT - ${levelName} - ${message}`;
        }
        console.log(formattedMessage);
    }

    debug(message) { this._log('DEBUG', message, colors.CYAN); }
    info(message) { this._log('INFO', message, colors.WHITE); }
    warning(message) { this._log('WARNING', message, colors.YELLOW); }
    error(message) { this._log('ERROR', message, colors.RED); }
    critical(message) { this._log('CRITICAL', message, colors.BOLD + colors.RED); }
}

const logger = new Logger();

function loadConfig(configPath = "config.yaml") {
    let config;
    try {
        const fileContents = fs.readFileSync(configPath, 'utf8');
        config = yaml.load(fileContents);
        logger.info(`${colors.GREEN}Successfully summoned configuration from ${configPath}.${colors.RESET}`);
    } catch (e) {
        if (e.code === 'ENOENT') {
            logger.error(`${colors.RED}The arcane grimoire 'config.yaml' was not found. The ritual cannot proceed.${colors.RESET}`);
        } else {
            logger.error(`${colors.RED}The 'config.yaml' grimoire is corrupted: ${e}. The ritual is halted.${colors.RESET}`);
        }
        process.exit(1);
    }

    const apiKey = process.env.BYBIT_API_KEY;
    const apiSecret = process.env.BYBIT_API_SECRET;

    if (!apiKey || !apiSecret) {
        logger.warning(`${colors.YELLOW}BYBIT_API_KEY or BYBIT_API_SECRET not found in the environment. Dry run is enforced.${colors.RESET}`);
    }

    config.api.key = apiKey;
    config.api.secret = apiSecret;

    return config;
}

const CONFIG = loadConfig();
logger.setLevel(CONFIG.bot.log_level.toUpperCase());

class Bybit {
    constructor(api, secret, testnet = false, dry_run = false) {
        this.api = api;
        this.secret = secret;
        this.testnet = testnet;
        this.dry_run = dry_run;
        this.session = null;
        this._dry_run_positions = {};
        this.baseURL = testnet ? "https://api-testnet.bybit.com" : "https://api.bybit.com";

        if (this.api && this.secret) {
            this.session = true;
            logger.info(`${colors.CYAN}HTTP session initialized for data fetching.${colors.RESET}`);
        } else {
            logger.warning(`${colors.YELLOW}API keys not found. Live data fetching is disabled.${colors.RESET}`);
        }

        logger.info(`${colors.CYAN}Bybit client configured. Testnet: ${this.testnet}, Dry Run: ${this.dry_run}${colors.RESET}`);
    }

    async _sendRequest(method, endpoint, params = {}) {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const url = `${this.baseURL}${endpoint}`;

        let sign;
        let queryString = '';
        let bodyString = '';
        let headers = {
            'X-BAPI-API-KEY': this.api,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-RECV-WINDOW': recvWindow,
            'Content-Type': 'application/json'
        };

        if (method === 'GET') {
            queryString = new URLSearchParams(params).toString();
            const signPayload = timestamp + this.api + recvWindow + queryString;
            sign = CryptoJS.HmacSHA256(signPayload, this.secret).toString();
            headers['X-BAPI-SIGN'] = sign;
            try {
                const response = await axios.get(`${url}?${queryString}`, { headers });
                return response.data;
            } catch (error) {
                logger.error(`${colors.RED}GET request to ${endpoint} failed: ${error.message}${colors.RESET}`);
                if (error.response) logger.error(`Response: ${JSON.stringify(error.response.data)}`);
                return { retCode: -1, retMsg: error.message, result: null };
            }
        } else if (method === 'POST') {
            bodyString = JSON.stringify(params);
            const signPayload = timestamp + this.api + recvWindow + bodyString;
            sign = CryptoJS.HmacSHA256(signPayload, this.secret).toString();
            headers['X-BAPI-SIGN'] = sign;
            try {
                const response = await axios.post(url, params, { headers });
                return response.data;
            } catch (error) {
                logger.error(`${colors.RED}POST request to ${endpoint} failed: ${error.message}${colors.RESET}`);
                if (error.response) logger.error(`Response: ${JSON.stringify(error.response.data)}`);
                return { retCode: -1, retMsg: error.message, result: null };
            }
        } else {
            throw new Error('Unsupported HTTP method');
        }
    }

    async getBalance(coin = "USDT") {
        if (!this.session) {
            logger.debug(`${colors.BLUE}[DRY RUN] No API session. Simulated balance: 10000.00 USDT.${colors.RESET}`);
            return 10000.00;
        }
        try {
            const resp = await this._sendRequest('GET', '/v5/account/wallet-balance', { accountType: "UNIFIED", coin });
            if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
                const balanceDataList = resp.result.list[0].coin;
                for (const coinData of balanceDataList) {
                    if (coinData.coin === coin) {
                        const balance = parseFloat(coinData.walletBalance);
                        logger.debug(`${colors.BLUE}Fetched balance: ${balance} ${coin}${colors.RESET}`);
                        return balance;
                    }
                }
                logger.warning(`${colors.YELLOW}No balance data found for coin ${coin}.${colors.RESET}`);
                return 0.0;
            } else {
                logger.error(`${colors.RED}Error getting balance: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
                return null;
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting balance: ${err.message}${colors.RESET}`);
            return null;
        }
    }

    async getPositions(settleCoin = "USDT") {
        if (this.dry_run) {
            const openSymbols = Object.keys(this._dry_run_positions);
            logger.debug(`${colors.BLUE}[DRY RUN] Fetched open positions from internal tracker: ${openSymbols}${colors.RESET}`);
            return openSymbols;
        }
        if (!this.session) return [];
        try {
            const resp = await this._sendRequest('GET', '/v5/position/list', { category: 'linear', settleCoin });
            if (resp.retCode === 0 && resp.result && resp.result.list) {
                return resp.result.list.filter(elem => parseFloat(elem.size || 0) > 0).map(elem => elem.symbol);
            } else {
                logger.error(`${colors.RED}Error getting positions: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
                return [];
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting positions: ${err.message}${colors.RESET}`);
            return [];
        }
    }

    async getTickers() {
        if (!this.session) {
            logger.debug(`${colors.BLUE}[DRY RUN] No API session. Returning symbols from config.${colors.RESET}`);
            return CONFIG.trading.trading_symbols;
        }
        try {
            const resp = await this._sendRequest('GET', '/v5/market/tickers', { category: 'linear' });
            if (resp.retCode === 0 && resp.result && resp.result.list) {
                return resp.result.list.filter(elem => elem.symbol.includes('USDT') && !elem.symbol.includes('USDC')).map(elem => elem.symbol);
            } else {
                logger.error(`${colors.RED}Error getting tickers: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
                return null;
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting tickers: ${err.message}${colors.RESET}`);
            return null;
        }
    }

    async klines(symbol, timeframe, limit = 500) {
        if (!this.session) {
            logger.error(`${colors.RED}Cannot fetch klines for ${symbol}. No API session available.${colors.RESET}`);
            return [];
        }
        try {
            const resp = await this._sendRequest('GET', '/v5/market/kline', { category: 'linear', symbol, interval: String(timeframe), limit });
            if (resp.retCode === 0 && resp.result && resp.result.list) {
                const df = resp.result.list.map(kline => ({
                    time: DateTime.fromMillis(parseInt(kline[0])).toJSDate(),
                    open: parseFloat(kline[1]),
                    high: parseFloat(kline[2]),
                    low: parseFloat(kline[3]),
                    close: parseFloat(kline[4]),
                    volume: parseFloat(kline[5])
                })).sort((a, b) => a.time.getTime() - b.time.getTime());

                const hasNan = df.some(k => isNaN(k.open) || isNaN(k.high) || isNaN(k.low) || isNaN(k.close));
                if (hasNan) {
                    logger.warning(`${colors.YELLOW}NaN values found in OHLC for ${symbol}. Discarding klines.${colors.RESET}`);
                    return [];
                }

                logger.debug(`${colors.BLUE}Fetched ${df.length} klines for ${symbol} (${timeframe}min).${colors.RESET}`);
                return df;
            } else {
                logger.error(`${colors.RED}Error getting klines for ${symbol}: ${resp.retMsg || 'No data'}${colors.RESET}`);
                return [];
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting klines for ${symbol}: ${err.message}${colors.RESET}`);
            return [];
        }
    }

    async getOrderbookLevels(symbol, limit = 50) {
        if (!this.session) return [null, null];
        try {
            const resp = await this._sendRequest('GET', '/v5/market/orderbook', { category: 'linear', symbol, limit });
            if (resp.retCode === 0 && resp.result) {
                const bids = resp.result.b.map(b => ({ price: parseFloat(b[0]), volume: parseFloat(b[1]) }));
                const asks = resp.result.a.map(a => ({ price: parseFloat(a[0]), volume: parseFloat(a[1]) }));

                let strongSupport = null;
                if (bids.length > 0) {
                    strongSupport = bids.reduce((max, bid) => (bid.volume > max.volume ? bid : max), bids[0]).price;
                }

                let strongResistance = null;
                if (asks.length > 0) {
                    strongResistance = asks.reduce((max, ask) => (ask.volume > max.volume ? ask : max), asks[0]).price;
                }
                return [strongSupport, strongResistance];
            } else {
                logger.error(`${colors.RED}Error getting orderbook for ${symbol}: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
                return [null, null];
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting orderbook for ${symbol}: ${err.message}${colors.RESET}`);
            return [null, null];
        }
    }

    async getPrecisions(symbol) {
        if (!this.session) return [2, 3, 0.001];
        try {
            const resp = await this._sendRequest('GET', '/v5/market/instruments-info', { category: 'linear', symbol });
            if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
                const info = resp.result.list[0];
                const pricePrecision = info.priceFilter.tickSize.split('.')[1]?.length || 0;
                const qtyPrecision = info.lotSizeFilter.qtyStep.split('.')[1]?.length || 0;
                const minOrderQty = parseFloat(info.lotSizeFilter.minOrderQty);
                return [pricePrecision, qtyPrecision, minOrderQty];
            } else {
                logger.error(`${colors.RED}Error getting precisions for ${symbol}: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
                return [2, 3, 0.001];
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting precisions for ${symbol}: ${err.message}${colors.RESET}`);
            return [2, 3, 0.001];
        }
    }

    async setMarginModeAndLeverage(symbol, mode, leverage) {
        if (this.dry_run) {
            logger.info(`${colors.MAGENTA}[DRY RUN] Would set margin mode to ${mode === 1 ? 'Isolated' : 'Cross'} and leverage to ${leverage}x for ${symbol}.${colors.RESET}`);
            return;
        }
        try {
            const resp = await this._sendRequest('POST', '/v5/position/set-leverage', {
                category: 'linear',
                symbol,
                buyLeverage: String(leverage),
                sellLeverage: String(leverage)
            });
            if (resp.retCode === 0) {
                logger.info(`${colors.GREEN}Leverage set to ${leverage}x for ${symbol}. (Margin mode implicit/assumed by Unified account setup).${colors.RESET}`);
            } else if ([110026, 110043].includes(resp.retCode)) {
                logger.debug(`${colors.YELLOW}Leverage already set for ${symbol}.${colors.RESET}`);
            } else {
                logger.warning(`${colors.YELLOW}Failed to set leverage for ${symbol}: ${resp.retMsg || 'Unknown error'}${colors.RESET}`);
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception setting leverage for ${symbol}: ${err.message}${colors.RESET}`);
        }
    }

    async placeOrderCommon(symbol, side, orderType, qty, price = null, triggerPrice = null, tpPrice = null, slPrice = null, timeInForce = 'GTC') {
        if (this.dry_run) {
            const dummyOrderId = `DRY_RUN_ORDER_${randomUUID()}`;
            let logMsg = `${colors.MAGENTA}[DRY RUN] Would place order for ${symbol} (${orderType} ${side} ${qty.toFixed(6)})`;
            if (price !== null) logMsg += ` at price ${price.toFixed(6)}`;
            if (tpPrice !== null) logMsg += ` with TP ${tpPrice.toFixed(6)}`;
            if (slPrice !== null) logMsg += ` and SL ${slPrice.toFixed(6)}`;
            logger.info(`${logMsg}. Simulated Order ID: ${dummyOrderId}${colors.RESET}`);
            this._dry_run_positions[symbol] = { side: side, size: qty };
            return dummyOrderId;
        }
        try {
            const [pricePrecision, qtyPrecision] = await this.getPrecisions(symbol);
            const params = {
                category: 'linear',
                symbol,
                side,
                orderType,
                qty: qty.toFixed(qtyPrecision),
                timeInForce
            };
            if (price !== null) params.price = price.toFixed(pricePrecision);
            if (triggerPrice !== null) {
                params.triggerPrice = triggerPrice.toFixed(pricePrecision);
                params.triggerBy = 'MarkPrice';
            }
            if (tpPrice !== null) {
                params.takeProfit = tpPrice.toFixed(pricePrecision);
                params.tpTriggerBy = 'MarkPrice';
            }
            if (slPrice !== null) {
                params.stopLoss = slPrice.toFixed(pricePrecision);
                params.slTriggerBy = 'MarkPrice';
            }

            const response = await this._sendRequest('POST', '/v5/order/create', params);
            if (response.retCode === 0) {
                const orderId = response.result.orderId;
                logger.info(`${colors.GREEN}Order placed for ${symbol}. Order ID: ${orderId}${colors.RESET}`);
                return orderId;
            } else {
                logger.error(`${colors.RED}Failed to place order for ${symbol}: ${response.retMsg || 'Unknown error'}${colors.RESET}`);
                return null;
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception placing order for ${symbol}: ${err.message}${colors.RESET}`);
            return null;
        }
    }

    async placeMarketOrder(symbol, side, qty, tpPrice = null, slPrice = null) {
        return this.placeOrderCommon(symbol, side, 'Market', qty, null, null, tpPrice, slPrice);
    }

    async placeLimitOrder(symbol, side, price, qty, tpPrice = null, slPrice = null, timeInForce = 'GTC') {
        return this.placeOrderCommon(symbol, side, 'Limit', qty, price, null, tpPrice, slPrice, timeInForce);
    }

    async placeConditionalOrder(symbol, side, qty, triggerPrice, orderType = 'Market', price = null, tpPrice = null, slPrice = null) {
        if (orderType === 'Limit' && price === null) {
            price = triggerPrice;
            logger.warning(`${colors.YELLOW}Conditional limit order for ${symbol} using trigger_price as limit price.${colors.RESET}`);
        }
        return this.placeOrderCommon(symbol, side, orderType, qty, price, triggerPrice, tpPrice, slPrice);
    }

    async cancelAllOpenOrders(symbol) {
        if (this.dry_run) {
            logger.info(`${colors.MAGENTA}[DRY RUN] Would cancel all open orders for ${symbol}.${colors.RESET}`);
            return { retCode: 0, retMsg: 'OK' };
        }
        try {
            const response = await this._sendRequest('POST', '/v5/order/cancel-all', { category: 'linear', symbol });
            if (response.retCode === 0) {
                logger.info(`${colors.GREEN}All open orders for ${symbol} cancelled.${colors.RESET}`);
            } else {
                logger.warning(`${colors.YELLOW}Failed to cancel orders for ${symbol}: ${response.retMsg || 'Unknown error'}${colors.RESET}`);
            }
            return response;
        } catch (err) {
            logger.error(`${colors.RED}Exception cancelling orders for ${symbol}: ${err.message}${colors.RESET}`);
            return { retCode: -1, retMsg: err.message };
        }
    }

    async getOpenOrders(symbol = null) {
        if (this.dry_run) {
            return [];
        }
        try {
            const params = { category: 'linear' };
            if (symbol) params.symbol = symbol;
            const response = await this._sendRequest('GET', '/v5/order/realtime', params);
            if (response.retCode === 0 && response.result && response.result.list) {
                return response.result.list;
            } else {
                logger.error(`${colors.RED}Error getting open orders: ${response.retMsg || 'Unknown error'}${colors.RESET}`);
                return [];
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting open orders: ${err.message}${colors.RESET}`);
            return [];
        }
    }

    async getOrderStatus(symbol, orderId) {
        if (this.dry_run) {
            logger.info(`${colors.MAGENTA}[DRY RUN] Would check status for order ID ${orderId}.${colors.RESET}`);
            return { orderId, status: 'Filled', symbol, side: 'Buy', execQty: '0.001', avgPrice: '30000.00' };
        }
        try {
            const response = await this._sendRequest('GET', '/v5/order/realtime', { category: 'linear', symbol, orderId });
            if (response.retCode === 0 && response.result && response.result.list && response.result.list.length > 0) {
                return response.result.list[0];
            } else {
                logger.error(`${colors.RED}Error getting order status for ${orderId}: ${response.retMsg || 'Unknown error'}${colors.RESET}`);
                return null;
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception getting order status for ${orderId}: ${err.message}${colors.RESET}`);
            return null;
        }
    }

    async syncTime() {
        try {
            const start = Date.now();
            const response = await axios.get(`${this.baseURL}/v3/public/time`);
            const end = Date.now();
            const serverTime = response.data.time; // Use top-level 'time' field (milliseconds)
            this.timeOffset = serverTime - ((start + end) / 2);
            logger.info(`${colors.GREEN}Time synchronized with Bybit server. Offset: ${this.timeOffset.toFixed(2)}ms${colors.RESET}`);
        } catch (err) {
            logger.error(`${colors.RED}Failed to sync time with Bybit server: ${err.message}${colors.RESET}`);
        }
    }

    async syncTime() {
        try {
            const start = Date.now();
            const response = await axios.get(`${this.baseURL}/v3/public/time`);
            const end = Date.now();
            const serverTime = response.data.time; // Use top-level 'time' field (milliseconds)
            this.timeOffset = serverTime - ((start + end) / 2);
            logger.info(`${colors.GREEN}Time synchronized with Bybit server. Offset: ${this.timeOffset.toFixed(2)}ms${colors.RESET}`);
        } catch (err) {
            logger.error(`${colors.RED}Failed to sync time with Bybit server: ${err.message}${colors.RESET}`);
        }
    }

    async closePosition(symbol) {
        if (this.dry_run) {
            logger.info(`${colors.MAGENTA}[DRY RUN] Would close position for ${symbol}.${colors.RESET}`);
            if (this._dry_run_positions[symbol]) {
                delete this._dry_run_positions[symbol];
            }
            return `DRY_RUN_CLOSE_ORDER_${randomUUID()}`;
        }
        try {
            const positionsResp = await this._sendRequest('GET', '/v5/position/list', { category: 'linear', symbol });
            if (positionsResp.retCode !== 0 || !positionsResp.result || !positionsResp.result.list) {
                logger.warning(`${colors.YELLOW}Could not get position details for ${symbol} to close.${colors.RESET}`);
                return null;
            }
            const positionInfo = positionsResp.result.list.find(pos => parseFloat(pos.size) > 0);
            if (!positionInfo) {
                logger.info(`${colors.CYAN}No open position found for ${symbol} to close.${colors.RESET}`);
                return null;
            }
            const closeSide = positionInfo.side === 'Buy' ? 'Sell' : 'Buy';
            const orderId = await this.placeMarketOrder(symbol, closeSide, parseFloat(positionInfo.size));
            if (orderId) {
                logger.info(`${colors.GREEN}Market order placed to close ${symbol} position. Order ID: ${orderId}${colors.RESET}`);
                return orderId;
            } else {
                logger.error(`${colors.RED}Failed to place market order to close ${symbol} position.${colors.RESET}`);
                return null;
            }
        } catch (err) {
            logger.error(`${colors.RED}Exception closing position for ${symbol}: ${err.message}${colors.RESET}`);
            return null;
        }
    }
}

let bybit_client;
try {
    bybit_client = new Bybit(
        CONFIG.api.key,
        CONFIG.api.secret,
        CONFIG.api.testnet,
        CONFIG.api.dry_run
    );
    const modeInfo = CONFIG.api.dry_run ? `${colors.MAGENTA}${colors.BOLD}DRY RUN${colors.RESET}` : `${colors.GREEN}${colors.BOLD}LIVE${colors.RESET}`;
    const testnetInfo = CONFIG.api.testnet ? `${colors.YELLOW}TESTNET${colors.RESET}` : `${colors.BLUE}MAINNET${colors.RESET}`;
    logger.info(`${colors.LIGHTYELLOW_EX}Successfully connected to Bybit API in ${modeInfo} mode on ${testnetInfo}.${colors.RESET}`);
    logger.debug(`${colors.CYAN}Bot configuration: ${JSON.stringify(CONFIG)}${colors.RESET}`);
} catch (e) {
    logger.error(`${colors.RED}Failed to connect to Bybit API: ${e.message}${colors.RESET}`);
    process.exit(1);
}

async function timeout(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function getCurrentTime(timezoneStr) {
    try {
        const localTime = DateTime.local().setZone(timezoneStr);
        const utcTime = DateTime.utc();
        if (!localTime.isValid) {
             logger.error(`${colors.RED}Unknown timezone: '${timezoneStr}'. Defaulting to UTC.${colors.RESET}`);
             return [DateTime.utc(), DateTime.utc()];
        }
        return [localTime, utcTime];
    } catch (e) {
        logger.error(`${colors.RED}Exception getting current time with timezone '${timezoneStr}': ${e.message}. Defaulting to UTC.${colors.RESET}`);
        return [DateTime.utc(), DateTime.utc()];
    }
}

function isMarketOpen(localTime, openHour, closeHour) {
    const currentHour = localTime.hour;
    const openHourInt = parseInt(openHour);
    const closeHourInt = parseInt(closeHour);
    if (openHourInt < closeHourInt) {
        return currentHour >= openHourInt && currentHour < closeHourInt;
    } else {
        return currentHour >= openHourInt || currentHour < closeHourInt;
    }
}

function sendTermuxToast(message) {
    if (process.platform === 'linux' && process.env.TERMUX_VERSION) {
        try {
            const { spawnSync } = require('child_process');
            spawnSync('termux-toast', [message], { stdio: 'inherit' });
        } catch (e) {
            logger.warning(`${colors.YELLOW}Could not send Termux toast: ${e.message}${colors.RESET}`);
        }
    }
}

function calculatePnl(side, entryPrice, exitPrice, qty) {
    return side === 'Buy' ? (exitPrice - entryPrice) * qty : (entryPrice - exitPrice) * qty;
}



function generateEhlSupertrendSignals(klines, currentPrice, pricePrecision, qtyPrecision) {
    const minKlines = CONFIG.trading.min_klines_for_strategy;
    if (!klines || klines.length < minKlines) {
        return ['none', null, null, null, [], false];
    }

    const dfIndicators = calculateEhlSupertrendIndicators(klines, CONFIG, logger);
    if (!dfIndicators || dfIndicators.length < minKlines) {
        return ['none', null, null, null, dfIndicators, false];
    }

    const lastRow = dfIndicators[dfIndicators.length - 1];
    const prevRow = dfIndicators[dfIndicators.length - 2];

    if (!prevRow) {
        return ['none', null, null, null, dfIndicators, false];
    }
    
    const longTrendConfirmed = lastRow.st_slow_direction > 0;
    const shortTrendConfirmed = lastRow.st_slow_direction < 0;
    
    const fastCrossesAboveSlow = prevRow.st_fast_line <= prevRow.st_slow_line && lastRow.st_fast_line > lastRow.st_slow_line;
    const fastCrossesBelowSlow = prevRow.st_fast_line >= prevRow.st_slow_line && lastRow.st_fast_line < lastRow.st_slow_line;
    
    const fisherConfirmLong = lastRow.fisher > lastRow.fisher_signal;
    const rsiConfirmLong = CONFIG.strategy.rsi.confirm_long_threshold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.overbought;
    
    const fisherConfirmShort = lastRow.fisher < lastRow.fisher_signal;
    const rsiConfirmShort = CONFIG.strategy.rsi.oversold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.confirm_short_threshold;
    
    const volumeConfirm = lastRow.volume_spike || prevRow.volume_spike;
    const adxConfirm = lastRow.adx > CONFIG.strategy.adx.threshold;
    
    let signal = 'none';
    let riskDistance = null;
    let tpPrice = null;
    let slPrice = null;

    if (longTrendConfirmed && fastCrossesAboveSlow && adxConfirm && ((fisherConfirmLong ? 1 : 0) + (rsiConfirmLong ? 1 : 0) + (volumeConfirm ? 1 : 0) >= 2)) {
        signal = 'Buy';
        slPrice = prevRow.st_slow_line;
        riskDistance = currentPrice - slPrice;
        if (riskDistance > 0) {
            if (CONFIG.order_logic.use_atr_for_tp_sl) {
                const atrVal = lastRow.atr;
                tpPrice = parseFloat((currentPrice + (atrVal * CONFIG.order_logic.tp_atr_multiplier)).toFixed(pricePrecision));
                slPrice = parseFloat((currentPrice - (atrVal * CONFIG.order_logic.sl_atr_multiplier)).toFixed(pricePrecision));
                riskDistance = currentPrice - slPrice;
            } else {
                tpPrice = parseFloat((currentPrice + (riskDistance * CONFIG.order_logic.reward_risk_ratio)).toFixed(pricePrecision));
                slPrice = parseFloat(slPrice.toFixed(pricePrecision));
            }
        } else {
            signal = 'none';
        }

    } else if (shortTrendConfirmed && fastCrossesBelowSlow && adxConfirm && ((fisherConfirmShort ? 1 : 0) + (rsiConfirmShort ? 1 : 0) + (volumeConfirm ? 1 : 0) >= 2)) {
        signal = 'Sell';
        slPrice = prevRow.st_slow_line;
        riskDistance = slPrice - currentPrice;
        if (riskDistance > 0) {
            if (CONFIG.order_logic.use_atr_for_tp_sl) {
                const atrVal = lastRow.atr;
                tpPrice = parseFloat((currentPrice - (atrVal * CONFIG.order_logic.tp_atr_multiplier)).toFixed(pricePrecision));
                slPrice = parseFloat((currentPrice + (atrVal * CONFIG.order_logic.sl_atr_multiplier)).toFixed(pricePrecision));
                riskDistance = slPrice - currentPrice;
            } else {
                tpPrice = parseFloat((currentPrice - (riskDistance * CONFIG.order_logic.reward_risk_ratio)).toFixed(pricePrecision));
                slPrice = parseFloat(slPrice.toFixed(pricePrecision));
            }
        } else {
            signal = 'none';
        }
    }
            
    return [signal, riskDistance, tpPrice, slPrice, dfIndicators, volumeConfirm];
}

async function main() {
    console.log(`${colors.LIGHTYELLOW_EX}${colors.BOLD}Pyrmethus awakens the Ehlers Supertrend Cross Strategy!${colors.RESET}`);
    
    const symbols = CONFIG.trading.trading_symbols;
    if (!symbols || symbols.length === 0) {
        logger.info(`${colors.YELLOW}No symbols in config.yaml. Exiting.${colors.RESET}`);
        return;
    }

    const activeTrades = {};
    let cumulativePnl = 0.0;

    while (true) {
        const [localTime, utcTime] = getCurrentTime(CONFIG.bot.timezone);
        logger.info(`${colors.WHITE}Local: ${localTime.toFormat('yyyy-MM-dd HH:mm:ss')} | UTC: ${utcTime.toFormat('yyyy-MM-dd HH:mm:ss')}${colors.RESET}`);

        if (!isMarketOpen(localTime, CONFIG.bot.market_open_hour, CONFIG.bot.market_close_hour)) {
            logger.info(`${colors.YELLOW}Market closed. Waiting...${colors.RESET}`);
            await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }
            
        const balance = await bybit_client.getBalance();
        if (balance === null) {
            logger.error(`${colors.RED}Cannot get balance. Retrying...${colors.RESET}`);
            await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
            continue;
        }
        
        logger.info(`${colors.LIGHTGREEN_EX}Balance: ${balance.toFixed(2)} USDT${colors.RESET}`);
        const currentPositions = await bybit_client.getPositions();
        logger.info(`${colors.LIGHTCYAN_EX}${currentPositions.length} open positions: ${currentPositions.join(', ')}${colors.RESET}`);

        for (const symbol of symbols) {
            if (currentPositions.length >= CONFIG.trading.max_positions) {
                logger.info(`${colors.YELLOW}Max positions reached. No new trades.${colors.RESET}`);
                break;
            }
            if (currentPositions.includes(symbol) || activeTrades[symbol]) {
                continue;
            }

            const klines = await bybit_client.klines(symbol, CONFIG.trading.timeframe, CONFIG.trading.min_klines_for_strategy + 5);
            if (!klines || klines.length === 0) {
                logger.warning(`${colors.YELLOW}Not enough kline data for ${symbol}. Skipping.${colors.RESET}`);
                continue;
            }
            
            const currentPrice = klines[klines.length - 1].close;
            const [pricePrecision, qtyPrecision, minOrderQty] = await bybit_client.getPrecisions(symbol);
            
            const [signal, risk, tp, sl, dfIndicators, volConfirm] = generateEhlSupertrendSignals(klines, currentPrice, pricePrecision, qtyPrecision);

            if (dfIndicators && dfIndicators.length > 1) {
                const lastRow = dfIndicators[dfIndicators.length - 1];
                const logMsg = (
                    `[${symbol}] ` +
                    `Price: ${colors.WHITE}${currentPrice.toFixed(4)}${colors.RESET} | ` +
                    `SlowST: ${colors.CYAN}${lastRow.st_slow_line.toFixed(4)} (${lastRow.st_slow_direction > 0 ? 'Up' : 'Down'})${colors.RESET} | ` +
                    `FastST: ${colors.CYAN}${lastRow.st_fast_line.toFixed(4)}${colors.RESET} | ` +
                    `RSI: ${colors.YELLOW}${lastRow.rsi.toFixed(2)}${colors.RESET} | ` +
                    `Fisher: ${colors.MAGENTA}${lastRow.fisher.toFixed(2)} (Sig: ${lastRow.fisher_signal.toFixed(2)})${colors.RESET} | ` +
                    `ADX: ${colors.BLUE}${lastRow.adx.toFixed(2)}${colors.RESET} | ` +
                    `VolSpike: ${(volConfirm ? colors.GREEN : colors.RED)}${volConfirm ? 'Yes' : 'No'}${colors.RESET}`
                );
                logger.info(logMsg);
            } else {
                logger.warning(`[${symbol}] Could not generate indicator data for logging.`);
            }

            if (signal !== 'none' && risk !== null && risk > 0) {
                const lastRow = dfIndicators[dfIndicators.length - 1];
                const prevRow = dfIndicators[dfIndicators.length - 2];
                const reasoning = [];

                if (signal === 'Buy') {
                    reasoning.push(`SlowST is Up (${prevRow.st_slow_line.toFixed(4)})`);
                    reasoning.push(`FastST crossed above SlowST (${prevRow.st_fast_line.toFixed(4)} -> ${lastRow.st_fast_line.toFixed(4)})`);
                    reasoning.push(`ADX > ${CONFIG.strategy.adx.threshold} (${lastRow.adx.toFixed(2)})`);
                    const confirmations = [];
                    if (lastRow.fisher > lastRow.fisher_signal) confirmations.push(`Fisher (${lastRow.fisher.toFixed(2)} > ${lastRow.fisher_signal.toFixed(2)})`);
                    if (CONFIG.strategy.rsi.confirm_long_threshold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.overbought) confirmations.push(`RSI (${lastRow.rsi.toFixed(2)})`);
                    if (volConfirm) confirmations.push("Volume Spike");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                } else {
                    reasoning.push(`SlowST is Down (${prevRow.st_slow_line.toFixed(4)})`);
                    reasoning.push(`FastST crossed below SlowST (${prevRow.st_fast_line.toFixed(4)} -> ${lastRow.st_fast_line.toFixed(4)})`);
                    reasoning.push(`ADX > ${CONFIG.strategy.adx.threshold} (${lastRow.adx.toFixed(2)})`);
                    const confirmations = [];
                    if (lastRow.fisher < lastRow.fisher_signal) confirmations.push(`Fisher (${lastRow.fisher.toFixed(2)} < ${lastRow.fisher_signal.toFixed(2)})`);
                    if (CONFIG.strategy.rsi.oversold < lastRow.rsi && lastRow.rsi < CONFIG.strategy.rsi.confirm_short_threshold) confirmations.push(`RSI (${lastRow.rsi.toFixed(2)})`);
                    if (volConfirm) confirmations.push("Volume Spike");
                    reasoning.push(`Confirms (${confirmations.length}/2): ${confirmations.join(', ')}`);
                }

                logger.info(`${(signal === 'Buy' ? colors.GREEN : colors.RED)}${colors.BOLD}${signal.toUpperCase()} SIGNAL for ${symbol} at ${currentPrice.toFixed(4)} | TP: ${tp.toFixed(4)}, SL: ${sl.toFixed(4)} | Reason: ${reasoning.join('; ')}${colors.RESET}`);
                
                const riskAmountUsdt = balance * CONFIG.risk_management.risk_per_trade_pct;
                let orderQty = Math.min(riskAmountUsdt / risk, CONFIG.risk_management.order_qty_usdt / currentPrice);

                if (orderQty > 0 && orderQty < minOrderQty) {
                    logger.warning(`${colors.YELLOW}Calculated order qty ${orderQty.toFixed(qtyPrecision + 2)} is below minimum ${minOrderQty}. Checking if minimum is viable...${colors.RESET}`);
                    
                    const minQtyPositionValue = minOrderQty * currentPrice;
                    const minQtyMargin = minQtyPositionValue / CONFIG.risk_management.leverage;
                    const minQtyRiskUsdt = risk * minOrderQty;

                    if (minQtyMargin < balance && minQtyRiskUsdt <= riskAmountUsdt) {
                        logger.info(`${colors.GREEN}Adjusting order quantity to the minimum allowed: ${minOrderQty}${colors.RESET}`);
                        orderQty = minOrderQty;
                    } else {
                        logger.warning(`${colors.YELLOW}Minimum order quantity is not viable (margin or risk). Skipping trade.${colors.RESET}`);
                        orderQty = 0;
                    }
                }
                
                orderQty = parseFloat(orderQty.toFixed(qtyPrecision));

                if (orderQty > 0) {
                    await bybit_client.setMarginModeAndLeverage(symbol, CONFIG.risk_management.margin_mode, CONFIG.risk_management.leverage);
                    await timeout(500);
                    const orderId = await bybit_client.placeMarketOrder(symbol, signal, orderQty, tp, sl);
                    if (orderId) {
                        activeTrades[symbol] = { entry_time: utcTime.toISO(), order_id: orderId, side: signal, entry_price: currentPrice, qty: orderQty, sl: sl, tp: tp };
                        sendTermuxToast(`${signal.toUpperCase()} Signal: ${symbol}`);
                    }
                } else {
                    logger.warning(`${colors.YELLOW}Calculated order quantity for ${symbol} is zero or too small. Skipping.${colors.RESET}`);
                }
            } else {
                logger.debug(`[${symbol}] No signal generated on this candle.`);
            }
        }
        
        for (const symbol in { ...activeTrades }) {
            if (bybit_client.dry_run && activeTrades[symbol]) {
                logger.info(`${colors.MAGENTA}[DRY RUN] Simulating trade completion for ${symbol}.${colors.RESET}`);
                const currentKline = await bybit_client.klines(symbol, CONFIG.trading.timeframe, 1);
                if (currentKline.length > 0) {
                    const exitPrice = currentKline[0].close;
                    const pnl = calculatePnl(activeTrades[symbol].side, activeTrades[symbol].entry_price, exitPrice, activeTrades[symbol].qty);
                    cumulativePnl += pnl;
                    logger.info(`${colors.MAGENTA}[DRY RUN] ${symbol} trade completed. PnL: ${pnl.toFixed(2)}. Cumulative PnL: ${cumulativePnl.toFixed(2)}${colors.RESET}`);
                }
                delete activeTrades[symbol];
                continue;
            }

            if (!currentPositions.includes(symbol) && activeTrades[symbol]) {
                 logger.info(`${colors.GREEN}Position for ${symbol} appears closed on exchange. Removing from active trades.${colors.RESET}`);
                 delete activeTrades[symbol];
            }
        }

        await timeout(CONFIG.bot.loop_wait_time_seconds * 1000);
    }
}

if (require.main === module) {
    main().catch(err => {
        logger.critical(`Unhandled error in main loop: ${err.message}`);
        console.error(err);
        process.exit(1);
    });
}