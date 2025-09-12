/* Wgwhalex – Enhanced Edition
    Adds Keltner Channels, Donchian Channels, ZigZag
    Now includes a backtesting module for performance analysis.
*/
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const { URLSearchParams } = require('url');
const { setInterval } = require('timers/promises'); // async sleep
const { Decimal } = require('decimal.js');
const { init: initColors, Fore, Style } = require('chalk');
const dotenv = require('dotenv');
const fetch = require('node-fetch');
const { createLogger, format, transports } = require('winston');
require('winston-daily-rotate-file');

Decimal.set({ precision: 28 });
initColors();
dotenv.config();

/* -------------- NEON COLOUR SCHEME -------------- */
const NEON_GREEN = Fore.greenBright;
const NEON_BLUE = Fore.cyan;
const NEON_PURPLE = Fore.magentaBright;
const NEON_YELLOW = Fore.yellowBright;
const NEON_RED = Fore.redBright;
const NEON_CYAN = Fore.cyanBright;
const RESET = Style.reset;

/* -------------- INDICATOR COLOURS -------------- */
const INDICATOR_COLORS = {
    SMA_10: Fore.blueBright,
    SMA_Long: Fore.blue,
    EMA_Short: Fore.magentaBright,
    EMA_Long: Fore.magenta,
    ATR: Fore.yellow,
    RSI: Fore.green,
    StochRSI_K: Fore.cyan,
    StochRSI_D: Fore.cyanBright,
    BB_Upper: Fore.red,
    BB_Middle: Fore.white,
    BB_Lower: Fore.red,
    CCI: Fore.greenBright,
    WR: Fore.redBright,
    MFI: Fore.green,
    OBV: Fore.blue,
    OBV_EMA: Fore.blueBright,
    CMF: Fore.magenta,
    Tenkan_Sen: Fore.cyan,
    Kijun_Sen: Fore.cyanBright,
    Senkou_Span_A: Fore.green,
    Senkou_Span_B: Fore.red,
    Chikou_Span: Fore.yellow,
    PSAR_Val: Fore.magenta,
    PSAR_Dir: Fore.magentaBright,
    VWAP: Fore.white,
    ST_Fast_Dir: Fore.blue,
    ST_Fast_Val: Fore.blueBright,
    ST_Slow_Dir: Fore.magenta,
    ST_Slow_Val: Fore.magentaBright,
    MACD_Line: Fore.green,
    MACD_Signal: Fore.greenBright,
    MACD_Hist: Fore.yellow,
    ADX: Fore.cyan,
    PlusDI: Fore.cyanBright,
    MinusDI: Fore.red,
    Volatility_Index: Fore.yellow,
    Volume_Delta: Fore.cyanBright,
    VWMA: Fore.white,
    /* NEW INDICATORS */
    KC_Upper: Fore.yellowBright,
    KC_Middle: Fore.yellow,
    KC_Lower: Fore.yellowBright,
    DC_Upper: Fore.cyan,
    DC_Middle: Fore.cyanBright,
    DC_Lower: Fore.cyan,
    ZigZag: Fore.redBright,
};

/* -------------- CONSTANTS -------------- */
const API_KEY = process.env.BYBIT_API_KEY;
const API_SECRET = process.env.BYBIT_API_SECRET;
const BASE_URL = (process.env.BYBIT_BASE_URL || "https://api.bybit.com").trim();
const CONFIG_FILE = "config.json";
const LOG_DIRECTORY = "bot_logs/trading-bot/logs";
fs.mkdirSync(LOG_DIRECTORY, { recursive: true });

const TIMEZONE_OFFSET = 0;
const MAX_API_RETRIES = 5;
const RETRY_DELAY_SECONDS = 7;
const REQUEST_TIMEOUT = 20000;
const LOOP_DELAY_SECONDS = 15;

const MIN_DATA_POINTS_TR = 2;
const MIN_DATA_POINTS_SMOOTHER = 2;
const MIN_DATA_POINTS_OBV = 2;
const MIN_DATA_POINTS_PSAR = 2;
const ADX_STRONG_TREND_THRESHOLD = 25;
const ADX_WEAK_TREND_THRESHOLD = 20;
const MIN_DATA_POINTS_VWMA = 2;
const MIN_DATA_POINTS_VOLATILITY = 2;

/* -------------- DEFAULT CONFIG (expanded) -------------- */
const defaultConfig = {
    /* ...... all your existing keys ...... */
    indicator_settings: {
        /* existing keys ...... */
        atr_period: 14,
        ema_short_period: 9,
        ema_long_period: 21,
        rsi_period: 14,
        stoch_rsi_period: 14,
        stoch_k_period: 3,
        stoch_d_period: 3,
        bollinger_bands_period: 20,
        bollinger_bands_std_dev: 2.0,
        cci_period: 20,
        williams_r_period: 14,
        mfi_period: 14,
        psar_acceleration: 0.02,
        psar_max_acceleration: 0.2,
        sma_short_period: 10,
        sma_long_period: 50,
        fibonacci_window: 60,
        ehlers_fast_period: 10,
        ehlers_fast_multiplier: 2.0,
        ehlers_slow_period: 20,
        ehlers_slow_multiplier: 3.0,
        macd_fast_period: 12,
        macd_slow_period: 26,
        macd_signal_period: 9,
        adx_period: 14,
        ichimoku_tenkan_period: 9,
        ichimoku_kijun_period: 26,
        ichimoku_senkou_span_b_period: 52,
        ichimoku_chikou_span_offset: 26,
        obv_ema_period: 20,
        cmf_period: 20,
        rsi_oversold: 30,
        rsi_overbought: 70,
        stoch_rsi_oversold: 20,
        stoch_rsi_overbought: 80,
        cci_oversold: -100,
        cci_overbought: 100,
        williams_r_oversold: -80,
        williams_r_overbought: -20,
        mfi_oversold: 20,
        mfi_overbought: 80,
        volatility_index_period: 20,
        vwma_period: 20,
        volume_delta_period: 5,
        volume_delta_threshold: 0.2,
        /* NEW INDICATORS */
        keltner_period: 20,
        keltner_multiplier: 1.5,
        donchian_period: 20,
        zigzag_depth: 5,
        zigzag_deviation: 0.3,
    },
    indicators: {
        /* existing keys ...... */
        ema_alignment: true,
        sma_trend_filter: true,
        momentum: true,
        volume_confirmation: true,
        stoch_rsi: true,
        rsi: true,
        bollinger_bands: true,
        vwap: true,
        cci: true,
        wr: true,
        psar: true,
        sma_10: true,
        mfi: true,
        orderbook_imbalance: true,
        fibonacci_levels: true,
        ehlers_supertrend: true,
        macd: true,
        adx: true,
        ichimoku_cloud: true,
        obv: true,
        cmf: true,
        volatility_index: true,
        vwma: true,
        volume_delta: true,
        /* NEW */
        keltner_channels: true,
        donchian_channels: true,
        zigzag: true,
    },
    weight_sets: {
        default_scalping: {
            /* existing keys ...... */
            ema_alignment: 0.22,
            sma_trend_filter: 0.28,
            momentum_rsi_stoch_cci_wr_mfi: 0.18,
            volume_confirmation: 0.12,
            bollinger_bands: 0.22,
            vwap: 0.22,
            psar: 0.22,
            sma_10: 0.07,
            orderbook_imbalance: 0.07,
            ehlers_supertrend_alignment: 0.55,
            macd_alignment: 0.28,
            adx_strength: 0.18,
            ichimoku_confluence: 0.38,
            obv_momentum: 0.18,
            cmf_flow: 0.12,
            mtf_trend_confluence: 0.32,
            volatility_index_signal: 0.15,
            vwma_cross: 0.15,
            volume_delta_signal: 0.10,
            /* NEW */
            keltner_breakout: 0.18,
            donchian_breakout: 0.18,
            zigzag_pivot: 0.12,
        },
    },
};

/* -------------- CONFIG LOADER (unchanged) -------------- */
function loadConfig(filepath, logger) {
    if (!fs.existsSync(filepath)) {
        try {
            fs.writeFileSync(filepath, JSON.stringify(defaultConfig, null, 4), 'utf-8');
            logger.warn(`${NEON_YELLOW}Configuration file not found. Created default config at ${filepath} for symbol ${defaultConfig.symbol}${RESET}`);
            return defaultConfig;
        } catch (e) {
            logger.error(`${NEON_RED}Error creating default config file: ${e.message}${RESET}`);
            return defaultConfig;
        }
    }
    try {
        let config = JSON.parse(fs.readFileSync(filepath, 'utf-8'));
        _ensureConfigKeys(config, defaultConfig);
        fs.writeFileSync(filepath, JSON.stringify(config, null, 4), 'utf-8');
        return config;
    } catch (e) {
        logger.error(`${NEON_RED}Error loading config: ${e.message}. Using default and attempting to save.${RESET}`);
        try { fs.writeFileSync(filepath, JSON.stringify(defaultConfig, null, 4), 'utf-8'); } catch (e2) {}
        return defaultConfig;
    }
}
function _ensureConfigKeys(config, defaultConfig) {
    for (const key in defaultConfig) {
        if (!config.hasOwnProperty(key)) config[key] = defaultConfig[key];
        else if (typeof defaultConfig[key] === 'object' && defaultConfig[key] !== null && !Array.isArray(defaultConfig[key]))
            _ensureConfigKeys(config[key], defaultConfig[key]);
    }
}

/* -------------- LOGGER (unchanged) -------------- */
class SensitiveFormatter {
    constructor(colors = false) {
        this.colors = colors;
        this.sensitiveWords = ["API_KEY", "API_SECRET", API_KEY, API_SECRET].filter(Boolean);
    }
    format(info) {
        let msg = info.message;
        this.sensitiveWords.forEach(w => {
            if (typeof w === 'string' && msg.includes(w))
                msg = msg.replace(new RegExp(w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '*'.repeat(w.length));
        });
        info.message = msg;
        return info;
    }
}
function setupLogger(logName, level = 'info') {
    const logger = createLogger({
        level,
        format: format.combine(
            format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
            format(new SensitiveFormatter(false).format),
            format.printf(i => `${i.timestamp} - ${i.level.toUpperCase()} - ${i.message}`)
        ),
        transports: [
            new transports.DailyRotateFile({
                dirname: LOG_DIRECTORY,
                filename: `${logName}-%DATE%.log`,
                datePattern: 'YYYY-MM-DD',
                zippedArchive: true,
                maxSize: '10m',
                maxFiles: '5d'
            })
        ],
        exitOnError: false
    });
    if (!logger.transports.some(t => t instanceof transports.Console)) {
        logger.add(new transports.Console({
            format: format.combine(
                format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
                format(new SensitiveFormatter(true).format),
                format.printf(i => {
                    let col;
                    switch (i.level) {
                        case 'info': col = NEON_BLUE; break;
                        case 'warn': col = NEON_YELLOW; break;
                        case 'error': col = NEON_RED; break;
                        default: col = RESET;
                    }
                    return `${col}${i.timestamp} - ${i.level.toUpperCase()} - ${i.message}${RESET}`;
                })
            )
        }));
    }
    return logger;
}

/* -------------- UTILS -------------- */
async function timeout(ms) { return new Promise(r => setTimeout(r, ms)); }

/* -------------- API WRAPPER (unchanged) -------------- */
async function createSessionFetch(url, options, logger) {
    let retries = 0;
    while (retries < MAX_API_RETRIES) {
        try {
            const res = await fetch(url, { ...options, timeout: REQUEST_TIMEOUT });
            if (!res.ok && [429, 500, 502, 503, 504].includes(res.status) && retries < MAX_API_RETRIES - 1) {
                logger.warn(`Request failed with status ${res.status}. Retrying in ${RETRY_DELAY_SECONDS}s...`);
                await timeout(RETRY_DELAY_SECONDS * 1000);
                retries++;
                continue;
            }
            return res;
        } catch (e) {
            if (['AbortError', 'FetchError'].includes(e.name) && retries < MAX_API_RETRIES - 1) {
                logger.warn(`Request failed: ${e.message}. Retrying in ${RETRY_DELAY_SECONDS}s...`);
                await timeout(RETRY_DELAY_SECONDS * 1000);
                retries++;
                continue;
            }
            throw e;
        }
    }
    throw new Error(`Max retries (${MAX_API_RETRIES}) exceeded for ${url}`);
}
function generateSignature(payload, apiSecret) {
    return crypto.createHmac('sha256', apiSecret).update(payload).digest('hex');
}
async function bybitRequest(method, endpoint, params = null, signed = false, logger = null) {
    if (!logger) logger = setupLogger('bybit_api');
    const url = `${BASE_URL}${endpoint}`;
    const headers = { 'Content-Type': 'application/json' };
    let opts = { method, headers };
    if (signed) {
        if (!API_KEY || !API_SECRET) { logger.error(`${NEON_RED}API_KEY or API_SECRET not set for signed request.${RESET}`); return null; }
        const ts = String(Date.now());
        const recvWindow = '20000';
        if (method === 'GET') {
            const qs = params ? new URLSearchParams(params).toString() : '';
            const paramStr = ts + API_KEY + recvWindow + qs;
            headers['X-BAPI-API-KEY'] = API_KEY;
            headers['X-BAPI-TIMESTAMP'] = ts;
            headers['X-BAPI-SIGN'] = generateSignature(paramStr, API_SECRET);
            headers['X-BAPI-RECV-WINDOW'] = recvWindow;
            opts.url = `${url}?${qs}`;
        } else {
            const body = JSON.stringify(params);
            const paramStr = ts + API_KEY + recvWindow + body;
            headers['X-BAPI-API-KEY'] = API_KEY;
            headers['X-BAPI-TIMESTAMP'] = ts;
            headers['X-BAPI-SIGN'] = generateSignature(paramStr, API_SECRET);
            headers['X-BAPI-RECV-WINDOW'] = recvWindow;
            opts.body = body;
            opts.url = url;
        }
    } else {
        opts.url = params ? `${url}?${new URLSearchParams(params).toString()}` : url;
    }
    try {
        const res = await createSessionFetch(opts.url, opts, logger);
        const j = await res.json();
        if (j.retCode !== 0) { logger.error(`${NEON_RED}Bybit API Error: ${j.retMsg} (Code: ${j.retCode})${RESET}`); return null; }
        return j;
    } catch (e) { logger.error(`${NEON_RED}Request Exception: ${e.message}${RESET}`); return null; }
}
async function fetchCurrentPrice(symbol, logger) {
    const r = await bybitRequest('GET', '/v5/market/tickers', { category: 'linear', symbol }, false, logger);
    if (r?.result?.list?.[0]?.lastPrice) return new Decimal(r.result.list[0].lastPrice);
    logger.warn(`${NEON_YELLOW}Could not fetch current price for ${symbol}.${RESET}`);
    return null;
}
async function fetchKlines(symbol, interval, limit, logger) {
    const r = await bybitRequest('GET', '/v5/market/kline', { category: 'linear', symbol, interval, limit }, false, logger);
    if (r?.result?.list) {
        const k = r.result.list.map(c => ({
            start_time: new Date(parseInt(c[0])),
            open: parseFloat(c[1]),
            high: parseFloat(c[2]),
            low: parseFloat(c[3]),
            close: parseFloat(c[4]),
            volume: parseFloat(c[5]),
            turnover: parseFloat(c[6]),
        })).sort((a, b) => a.start_time.getTime() - b.start_time.getTime());
        return new KlineData(k);
    }
    logger.warn(`${NEON_YELLOW}Could not fetch klines for ${symbol} ${interval}.${RESET}`);
    return null;
}
async function fetchOrderbook(symbol, limit, logger) {
    const r = await bybitRequest('GET', '/v5/market/orderbook', { category: 'linear', symbol, limit }, false, logger);
    return r?.result || null;
}

/* -------------- MINIMAL DATA-FRAME -------------- */
class KlineData {
    constructor(data = []) { this.data = data; }
    get length() { return this.data.length; }
    get empty() { return this.data.length === 0; }
    get(idx) { if (idx < 0) idx = this.data.length + idx; return this.data[idx]; }
    column(col) { return this.data.map(r => r[col]); }
    rollingMean(col, w) {
        if (this.length < w) return this.data.map(() => NaN);
        const s = this.column(col).map(parseFloat);
        const out = new Array(this.length).fill(NaN);
        for (let i = w - 1; i < this.length; i++) out[i] = s.slice(i - w + 1, i + 1).reduce((a, b) => a + b, 0) / w;
        return out;
    }
    ewmMean(col, span, minP = 0) {
        const s = this.column(col).map(parseFloat);
        if (s.length < minP) return new Array(s.length).fill(NaN);
        const α = 2 / (span + 1);
        const out = new Array(s.length).fill(NaN);
        let ema = 0; let count = 0;
        for (let i = 0; i < s.length; i++) {
            const v = s[i];
            if (isNaN(v)) { out[i] = NaN; continue; }
            ema = count === 0 ? v : v * α + ema * (1 - α);
            count++;
            out[i] = count >= minP ? ema : NaN;
        }
        return out;
    }
    diff(col) {
        const s = this.column(col).map(parseFloat);
        const out = [NaN];
        for (let i = 1; i < s.length; i++) out.push(s[i] - s[i - 1]);
        return out;
    }
    addColumn(name, vals) {
        if (vals.length !== this.data.length) throw new Error(`Length mismatch for ${name}`);
        this.data.forEach((r, i) => r[name] = vals[i]);
    }
}

/* -------------- POSITION MANAGER (unchanged) -------------- */
class PositionManager {
    constructor(cfg, logger, symbol) {
        this.cfg = cfg; this.logger = logger; this.symbol = symbol;
        this.openPositions = [];
        this.tmEnabled = cfg.trade_management.enabled;
        this.maxPos = cfg.trade_management.max_open_positions;
        this.ordPrec = cfg.trade_management.order_precision;
        this.prcPrec = cfg.trade_management.price_precision;
    }
    _balance() { return new Decimal(String(this.cfg.trade_management.account_balance)); }
    _orderSize(prc, atr) {
        if (!this.tmEnabled) return new Decimal(0);
        const bal = this._balance();
        const riskPct = new Decimal(String(this.cfg.trade_management.risk_per_trade_percent)).div(100);
        const slMult = new Decimal(String(this.cfg.trade_management.stop_loss_atr_multiple));
        const riskAmt = bal.mul(riskPct);
        const slDist = atr.mul(slMult);
        if (slDist.lte(0)) return new Decimal(0);
        let qty = riskAmt.div(slDist).div(prc);
        return qty.toDecimalPlaces(this.ordPrec, Decimal.ROUND_DOWN);
    }
    openPosition(side, prc, atr) {
        if (!this.tmEnabled) { this.logger.info(`${NEON_YELLOW}[${this.symbol}] Trade mgmt disabled – skip open.${RESET}`); return null; }
        if (this.openPositions.length >= this.maxPos) { this.logger.info(`${NEON_YELLOW}Max positions reached.${RESET}`); return null; }
        const qty = this._orderSize(prc, atr);
        if (qty.lte(0)) { this.logger.warn(`${NEON_YELLOW}Qty zero – skip.${RESET}`); return null; }
        const slMult = new Decimal(String(this.cfg.trade_management.stop_loss_atr_multiple));
        const tpMult = new Decimal(String(this.cfg.trade_management.take_profit_atr_multiple));
        let sl, tp;
        if (side === 'BUY') { sl = prc.sub(atr.mul(slMult)); tp = prc.add(atr.mul(tpMult)); }
        else { sl = prc.add(atr.mul(slMult)); tp = prc.sub(atr.mul(tpMult)); }
        const pos = {
            entry_time: new Date(), symbol: this.symbol, side,
            entry_price: prc.toDecimalPlaces(this.prcPrec, Decimal.ROUND_DOWN),
            qty, stop_loss: sl.toDecimalPlaces(this.prcPrec, Decimal.ROUND_DOWN),
            take_profit: tp.toDecimalPlaces(this.prcPrec, Decimal.ROUND_DOWN), status: 'OPEN',
        };
        this.openPositions.push(pos);
        this.logger.info(`${NEON_GREEN}[${this.symbol}] OPEN ${side} @ ${pos.entry_price}${RESET}`);
        return pos;
    }
    managePositions(prc, perf) {
        if (!this.tmEnabled || !this.openPositions.length) return;
        const toClose = [];
        this.openPositions.forEach((p, i) => {
            if (p.status !== 'OPEN') return;
            const side = p.side; const ep = new Decimal(p.entry_price);
            const sl = new Decimal(p.stop_loss); const tp = new Decimal(p.take_profit);
            const qty = new Decimal(p.qty);
            let closedBy = '', closeP = new Decimal(0);
            if (side === 'BUY') {
                if (prc.lte(sl)) { closedBy = 'STOP_LOSS'; closeP = prc; }
                else if (prc.gte(tp)) { closedBy = 'TAKE_PROFIT'; closeP = prc; }
            } else {
                if (prc.gte(sl)) { closedBy = 'STOP_LOSS'; closeP = prc; }
                else if (prc.lte(tp)) { closedBy = 'TAKE_PROFIT'; closeP = prc; }
            }
            if (closedBy) {
                p.status = 'CLOSED'; p.exit_time = new Date(); p.exit_price = closeP.toDecimalPlaces(this.prcPrec, Decimal.ROUND_DOWN); p.closed_by = closedBy;
                toClose.unshift(i);
                const pnl = side === 'BUY' ? closeP.sub(ep).mul(qty) : ep.sub(closeP).mul(qty);
                perf.recordTrade(p, pnl);
                this.logger.info(`${NEON_PURPLE}[${this.symbol}] CLOSE ${side} by ${closedBy} PnL ${pnl.toFixed(2)}${RESET}`);
            }
        });
        toClose.forEach(i => this.openPositions.splice(i, 1));
    }
    getOpenPositions() { return this.openPositions.filter(p => p.status === 'OPEN'); }
}

/* -------------- PERFORMANCE TRACKER (unchanged) -------------- */
class PerformanceTracker {
    constructor(logger) {
        this.logger = logger;
        this.trades = [];
        this.totalPnl = new Decimal(0);
        this.wins = 0; this.losses = 0;
    }
    recordTrade(pos, pnl) {
        this.trades.push({ ...pos, pnl });
        this.totalPnl = this.totalPnl.add(pnl);
        pnl.gt(0) ? this.wins++ : this.losses++;
        this.logger.info(`${NEON_CYAN}[${pos.symbol}] Trade recorded. Total PnL: ${this.totalPnl.toFixed(2)} Wins: ${this.wins} Losses: ${this.losses}${RESET}`);
    }
    getSummary() {
        const total = this.trades.length;
        return {
            total_trades: total,
            total_pnl: this.totalPnl,
            wins: this.wins,
            losses: this.losses,
            win_rate: total > 0 ? `${(this.wins / total * 100).toFixed(2)}%` : '0.00%',
        };
    }
}

/* -------------- ALERT SYSTEM (unchanged) -------------- */
class AlertSystem {
    constructor(logger) { this.logger = logger; }
    sendAlert(msg, lvl) {
        const map = { INFO: NEON_BLUE, WARNING: NEON_YELLOW, ERROR: NEON_RED };
        this.logger.info(`${map[lvl] || RESET}ALERT: ${msg}${RESET}`);
    }
}

/* -------------- TRADING ANALYZER -------------- */
class TradingAnalyzer {
    constructor(kd, cfg, logger, symbol) {
        this.kd = kd; this.cfg = cfg; this.logger = logger; this.symbol = symbol;
        this.iv = {}; this.fib = {}; this.w = cfg.weight_sets.default_scalping;
        this.is = cfg.indicator_settings;
        if (this.kd.empty) { this.logger.warn(`${NEON_YELLOW}Empty DataFrame – skip calc.${RESET}`); return; }
        this._calcAll();
        if (this.cfg.indicators.fibonacci_levels) this.calcFib();
    }
    _safe(f, name, min, ...a) {
        if (this.kd.length < min) { this.logger.debug(`Skip ${name} – need ${min} bars`); return null; }
        try { const r = f(...a); if (r === null || (Array.isArray(r) && r.every(v => v === null || (Array.isArray(v) && v.length === 0)))) return null; return r; } catch (e) { this.logger.error(`${NEON_RED}${name} calc err: ${e.message}${RESET}`); return null; }
    }
    _calcAll() {
        const c = this.cfg, s = this.is;
        /* SMA */
        if (c.indicators.sma_10) {
            const v = this._safe(() => this.kd.rollingMean('close', s.sma_short_period), 'SMA_10', s.sma_short_period);
            if (v) { this.kd.addColumn('SMA_10', v); this.iv.SMA_10 = v[v.length - 1]; }
        }
        if (c.indicators.sma_trend_filter) {
            const v = this._safe(() => this.kd.rollingMean('close', s.sma_long_period), 'SMA_Long', s.sma_long_period);
            if (v) { this.kd.addColumn('SMA_Long', v); this.iv.SMA_Long = v[v.length - 1]; }
        }
        /* EMA */
        if (c.indicators.ema_alignment) {
            const a = this._safe(() => this.kd.ewmMean('close', s.ema_short_period, s.ema_short_period), 'EMA_Short', s.ema_short_period);
            const b = this._safe(() => this.kd.ewmMean('close', s.ema_long_period, s.ema_long_period), 'EMA_Long', s.ema_long_period);
            if (a) { this.kd.addColumn('EMA_Short', a); this.iv.EMA_Short = a[a.length - 1]; }
            if (b) { this.kd.addColumn('EMA_Long', b); this.iv.EMA_Long = b[b.length - 1]; }
        }
        /* ATR */
        const tr = this._safe(() => this.calcTR(), 'TR', MIN_DATA_POINTS_TR);
        if (tr) {
            this.kd.addColumn('TR', tr);
            const atr = this._safe(() => this.ewmCustom(tr, s.atr_period, s.atr_period), 'ATR', s.atr_period);
            if (atr) { this.kd.addColumn('ATR', atr); this.iv.ATR = atr[atr.length - 1]; }
        }
        /* RSI */
        if (c.indicators.rsi) {
            const v = this._safe(() => this.calcRSI(s.rsi_period), 'RSI', s.rsi_period + 1);
            if (v) { this.kd.addColumn('RSI', v); this.iv.RSI = v[v.length - 1]; }
        }
        /* StochRSI */
        if (c.indicators.stoch_rsi) {
            const [k, d] = this._safe(() => this.calcStochRSI(s.stoch_rsi_period, s.stoch_k_period, s.stoch_d_period), 'StochRSI', s.stoch_rsi_period + s.stoch_d_period + s.stoch_k_period);
            if (k) { this.kd.addColumn('StochRSI_K', k); this.iv.StochRSI_K = k[k.length - 1]; }
            if (d) { this.kd.addColumn('StochRSI_D', d); this.iv.StochRSI_D = d[d.length - 1]; }
        }
        /* BB */
        if (c.indicators.bollinger_bands) {
            const [u, m, l] = this._safe(() => this.calcBB(s.bollinger_bands_period, s.bollinger_bands_std_dev), 'BB', s.bollinger_bands_period);
            if (u) { this.kd.addColumn('BB_Upper', u); this.iv.BB_Upper = u[u.length - 1]; }
            if (m) { this.kd.addColumn('BB_Middle', m); this.iv.BB_Middle = m[m.length - 1]; }
            if (l) { this.kd.addColumn('BB_Lower', l); this.iv.BB_Lower = l[l.length - 1]; }
        }
        /* CCI */
        if (c.indicators.cci) {
            const v = this._safe(() => this.calcCCI(s.cci_period), 'CCI', s.cci_period);
            if (v) { this.kd.addColumn('CCI', v); this.iv.CCI = v[v.length - 1]; }
        }
        /* WR */
        if (c.indicators.wr) {
            const v = this._safe(() => this.calcWR(s.williams_r_period), 'WR', s.williams_r_period);
            if (v) { this.kd.addColumn('WR', v); this.iv.WR = v[v.length - 1]; }
        }
        /* MFI */
        if (c.indicators.mfi) {
            const v = this._safe(() => this.calcMFI(s.mfi_period), 'MFI', s.mfi_period + 1);
            if (v) { this.kd.addColumn('MFI', v); this.iv.MFI = v[v.length - 1]; }
        }
        /* OBV */
        if (c.indicators.obv) {
            const [o, e] = this._safe(() => this.calcOBV(s.obv_ema_period), 'OBV', s.obv_ema_period);
            if (o) { this.kd.addColumn('OBV', o); this.iv.OBV = o[o.length - 1]; }
            if (e) { this.kd.addColumn('OBV_EMA', e); this.iv.OBV_EMA = e[e.length - 1]; }
        }
        /* CMF */
        if (c.indicators.cmf) {
            const v = this._safe(() => this.calcCMF(s.cmf_period), 'CMF', s.cmf_period);
            if (v) { this.kd.addColumn('CMF', v); this.iv.CMF = v[v.length - 1]; }
        }
        /* Ichimoku */
        if (c.indicators.ichimoku_cloud) {
            const [ten, kij, sa, sb, chi] = this._safe(() => this.calcIchimoku(s.ichimoku_tenkan_period, s.ichimoku_kijun_period, s.ichimoku_senkou_span_b_period, s.ichimoku_chikou_span_offset), 'Ichi',
                Math.max(s.ichimoku_tenkan_period, s.ichimoku_kijun_period, s.ichimoku_senkou_span_b_period) + s.ichimoku_chikou_span_offset);
            if (ten) { this.kd.addColumn('Tenkan_Sen', ten); this.iv.Tenkan_Sen = ten[ten.length - 1]; }
            if (kij) { this.kd.addColumn('Kijun_Sen', kij); this.iv.Kijun_Sen = kij[kij.length - 1]; }
            if (sa) { this.kd.addColumn('Senkou_Span_A', sa); this.iv.Senkou_Span_A = sa[sa.length - 1]; }
            if (sb) { this.kd.addColumn('Senkou_Span_B', sb); this.iv.Senkou_Span_B = sb[sb.length - 1]; }
            if (chi) { this.kd.addColumn('Chikou_Span', chi); this.iv.Chikou_Span = chi[chi.length - 1] || 0; }
        }
        /* PSAR */
        if (c.indicators.psar) {
            const [val, dir] = this._safe(() => this.calcPSAR(s.psar_acceleration, s.psar_max_acceleration), 'PSAR', MIN_DATA_POINTS_PSAR);
            if (val) { this.kd.addColumn('PSAR_Val', val); this.iv.PSAR_Val = val[val.length - 1]; }
            if (dir) { this.kd.addColumn('PSAR_Dir', dir); this.iv.PSAR_Dir = dir[dir.length - 1]; }
        }
        /* VWAP */
        if (c.indicators.vwap) {
            const v = this._safe(() => this.calcVWAP(), 'VWAP', 1);
            if (v) { this.kd.addColumn('VWAP', v); this.iv.VWAP = v[v.length - 1]; }
        }
        /* Ehlers ST */
        if (c.indicators.ehlers_supertrend) {
            const fast = this._safe(() => this.calcEhlersST(s.ehlers_fast_period, s.ehlers_fast_multiplier), 'EhlersSTfast', s.ehlers_fast_period * 3);
            if (fast) { this.kd.addColumn('st_fast_dir', fast.direction); this.kd.addColumn('st_fast_val', fast.supertrend); this.iv.ST_Fast_Dir = fast.direction[fast.direction.length - 1]; this.iv.ST_Fast_Val = fast.supertrend[fast.supertrend.length - 1]; }
            const slow = this._safe(() => this.calcEhlersST(s.ehlers_slow_period, s.ehlers_slow_multiplier), 'EhlersSTslow', s.ehlers_slow_period * 3);
            if (slow) { this.kd.addColumn('st_slow_dir', slow.direction); this.kd.addColumn('st_slow_val', slow.supertrend); this.iv.ST_Slow_Dir = slow.direction[slow.direction.length - 1]; this.iv.ST_Slow_Val = slow.supertrend[slow.supertrend.length - 1]; }
        }
        /* MACD */
        if (c.indicators.macd) {
            const [line, sig, hist] = this._safe(() => this.calcMACD(s.macd_fast_period, s.macd_slow_period, s.macd_signal_period), 'MACD', s.macd_slow_period + s.macd_signal_period);
            if (line) { this.kd.addColumn('MACD_Line', line); this.iv.MACD_Line = line[line.length - 1]; }
            if (sig) { this.kd.addColumn('MACD_Signal', sig); this.iv.MACD_Signal = sig[sig.length - 1]; }
            if (hist) { this.kd.addColumn('MACD_Hist', hist); this.iv.MACD_Hist = hist[hist.length - 1]; }
        }
        /* ADX */
        if (c.indicators.adx) {
            const [adx, pdi, mdi] = this._safe(() => this.calcADX(s.adx_period), 'ADX', s.adx_period * 2);
            if (adx) { this.kd.addColumn('ADX', adx); this.iv.ADX = adx[adx.length - 1]; }
            if (pdi) { this.kd.addColumn('PlusDI', pdi); this.iv.PlusDI = pdi[pdi.length - 1]; }
            if (mdi) { this.kd.addColumn('MinusDI', mdi); this.iv.MinusDI = mdi[mdi.length - 1]; }
        }
        /* Volatility Index */
        if (c.indicators.volatility_index) {
            const v = this._safe(() => this.calcVolIdx(s.volatility_index_period), 'VolIdx', s.volatility_index_period);
            if (v) { this.kd.addColumn('Volatility_Index', v); this.iv.Volatility_Index = v[v.length - 1]; }
        }
        /* VWMA */
        if (c.indicators.vwma) {
            const v = this._safe(() => this.calcVWMA(s.vwma_period), 'VWMA', s.vwma_period);
            if (v) { this.kd.addColumn('VWMA', v); this.iv.VWMA = v[v.length - 1]; }
        }
        /* Volume Delta */
        if (c.indicators.volume_delta) {
            const v = this._safe(() => this.calcVolDelta(s.volume_delta_period), 'VolDelta', s.volume_delta_period);
            if (v) { this.kd.addColumn('Volume_Delta', v); this.iv.Volume_Delta = v[v.length - 1]; }
        }
        /* -------------- NEW INDICATORS -------------- */
        /* Keltner Channels */
        if (c.indicators.keltner_channels) {
            const [u, m, l] = this._safe(() => this.calcKeltner(s.keltner_period, s.keltner_multiplier), 'Keltner', s.keltner_period + s.atr_period);
            if (u) { this.kd.addColumn('KC_Upper', u); this.iv.KC_Upper = u[u.length - 1]; }
            if (m) { this.kd.addColumn('KC_Middle', m); this.iv.KC_Middle = m[m.length - 1]; }
            if (l) { this.kd.addColumn('KC_Lower', l); this.iv.KC_Lower = l[l.length - 1]; }
        }
        /* Donchian Channels */
        if (c.indicators.donchian_channels) {
            const [u, m, l] = this._safe(() => this.calcDonchian(s.donchian_period), 'Donchian', s.donchian_period);
            if (u) { this.kd.addColumn('DC_Upper', u); this.iv.DC_Upper = u[u.length - 1]; }
            if (m) { this.kd.addColumn('DC_Middle', m); this.iv.DC_Middle = m[m.length - 1]; }
            if (l) { this.kd.addColumn('DC_Lower', l); this.iv.DC_Lower = l[l.length - 1]; }
        }
        /* ZigZag */
        if (c.indicators.zigzag) {
            const z = this._safe(() => this.calcZigZag(s.zigzag_depth, s.zigzag_deviation), 'ZigZag', s.zigzag_depth);
            if (z) { this.kd.addColumn('ZigZag', z); this.iv.ZigZag = z[z.length - 1]; }
        }
    }
    /* -------------- INDIVIDUAL CALC ROUTINES -------------- */
    calcTR() {
        if (this.kd.length < MIN_DATA_POINTS_TR) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close');
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 1; i < this.kd.length; i++) {
            out[i] = Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1]));
        }
        return out;
    }
    ewmCustom(series, span, minP = 0) {
        if (series.length < minP) return new Array(series.length).fill(NaN);
        const α = 2 / (span + 1);
        const out = new Array(series.length).fill(NaN);
        let ema = 0; let count = 0;
        for (let i = 0; i < series.length; i++) {
            const v = parseFloat(series[i]);
            if (isNaN(v)) { out[i] = NaN; continue; }
            ema = count === 0 ? v : v * α + ema * (1 - α);
            count++;
            out[i] = count >= minP ? ema : NaN;
        }
        return out;
    }
    calcRSI(p) {
        if (this.kd.length <= p) return new Array(this.kd.length).fill(NaN);
        const c = this.kd.column('close'), δ = this.kd.diff('close');
        const gain = δ.map(x => Math.max(0, x)), loss = δ.map(x => Math.max(0, -x));
        const avgG = this.ewmCustom(gain, p, p), avgL = this.ewmCustom(loss, p, p);
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) {
            if (!isNaN(avgG[i]) && !isNaN(avgL[i])) {
                if (avgL[i] === 0) out[i] = 100; else { const rs = avgG[i] / avgL[i]; out[i] = 100 - 100 / (1 + rs); }
            }
        }
        return out;
    }
    calcStochRSI(p, k, d) {
        const rsi = this.calcRSI(p);
        if (rsi.length <= p) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const lowest = new Array(this.kd.length).fill(NaN), highest = new Array(this.kd.length).fill(NaN);
        for (let i = p - 1; i < this.kd.length; i++) {
            const w = rsi.slice(i - p + 1, i + 1).filter(v => !isNaN(v));
            lowest[i] = Math.min(...w); highest[i] = Math.max(...w);
        }
        const kRaw = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) {
            if (!isNaN(rsi[i]) && !isNaN(highest[i]) && !isNaN(lowest[i])) {
                const den = highest[i] - lowest[i];
                kRaw[i] = den === 0 ? 0 : (rsi[i] - lowest[i]) / den * 100;
            }
        }
        const kSm = this.kd.rollingMean(kRaw, k), dSm = this.kd.rollingMean(kSm, d);
        return [kSm.map(v => Math.max(0, Math.min(100, v || 0))), dSm.map(v => Math.max(0, Math.min(100, v || 0)))];
    }
    calcBB(per, std) {
        if (this.kd.length < per) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const c = this.kd.column('close'), mid = this.kd.rollingMean('close', per);
        const σ = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            const w = c.slice(i - per + 1, i + 1), m = mid[i];
            σ[i] = Math.sqrt(w.reduce((s, x) => s + (x - m) ** 2, 0) / per);
        }
        const upper = mid.map((m, i) => m + σ[i] * std), lower = mid.map((m, i) => m - σ[i] * std);
        return [upper, mid, lower];
    }
    calcCCI(per) {
        if (this.kd.length < per) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close');
        const tp = h.map((x, i) => (x + l[i] + c[i]) / 3);
        const sma = this.kd.rollingMean(tp, per);
        const mad = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            const w = tp.slice(i - per + 1, i + 1);
            mad[i] = w.reduce((s, x) => s + Math.abs(x - sma[i]), 0) / per;
        }
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) if (!isNaN(tp[i]) && !isNaN(sma[i]) && !isNaN(mad[i])) out[i] = mad[i] === 0 ? 0 : (tp[i] - sma[i]) / (0.015 * mad[i]);
        return out;
    }
    calcWR(per) {
        if (this.kd.length < per) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close');
        const highest = new Array(this.kd.length).fill(NaN), lowest = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            const hw = h.slice(i - per + 1, i + 1), lw = l.slice(i - per + 1, i + 1);
            highest[i] = Math.max(...hw); lowest[i] = Math.min(...lw);
        }
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) if (!isNaN(c[i]) && !isNaN(highest[i]) && !isNaN(lowest[i])) {
            const den = highest[i] - lowest[i];
            out[i] = den === 0 ? -100 : -100 * ((highest[i] - c[i]) / den);
        }
        return out;
    }
    calcMFI(per) {
        if (this.kd.length <= per) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close'), v = this.kd.column('volume');
        const tp = h.map((x, i) => (x + l[i] + c[i]) / 3);
        const mf = tp.map((x, i) => x * v[i]);
        const pos = new Array(this.kd.length).fill(0), neg = new Array(this.kd.length).fill(0);
        for (let i = 1; i < this.kd.length; i++) {
            if (tp[i] > tp[i - 1]) pos[i] = mf[i]; else if (tp[i] < tp[i - 1]) neg[i] = mf[i];
        }
        const posSum = new Array(this.kd.length).fill(NaN), negSum = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            posSum[i] = pos.slice(i - per + 1, i + 1).reduce((a, b) => a + b, 0);
            negSum[i] = neg.slice(i - per + 1, i + 1).reduce((a, b) => a + b, 0);
        }
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) if (!isNaN(posSum[i]) && !isNaN(negSum[i])) {
            const ratio = negSum[i] === 0 ? (posSum[i] === 0 ? 0 : Infinity) : posSum[i] / negSum[i];
            out[i] = 100 - 100 / (1 + ratio);
        }
        return out;
    }
    calcOBV(emaPer) {
        if (this.kd.length < MIN_DATA_POINTS_OBV) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const c = this.kd.column('close'), v = this.kd.column('volume');
        const obv = new Array(this.kd.length).fill(0);
        if (this.kd.length > 0) obv[0] = v[0];
        for (let i = 1; i < this.kd.length; i++) {
            if (c[i] > c[i - 1]) obv[i] = obv[i - 1] + v[i];
            else if (c[i] < c[i - 1]) obv[i] = obv[i - 1] - v[i];
            else obv[i] = obv[i - 1];
        }
        const obve = this.ewmCustom(obv, emaPer, emaPer);
        return [obv, obve];
    }
    calcCMF(per) {
        if (this.kd.length < per) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close'), v = this.kd.column('volume');
        const mfm = new Array(this.kd.length).fill(0);
        for (let i = 0; i < this.kd.length; i++) {
            const hl = h[i] - l[i];
            mfm[i] = hl === 0 ? 0 : ((c[i] - l[i]) - (h[i] - c[i])) / hl;
        }
        const mfv = mfm.map((x, i) => x * v[i]);
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            const mfvSum = mfv.slice(i - per + 1, i + 1).reduce((a, b) => a + b, 0);
            const volSum = v.slice(i - per + 1, i + 1).reduce((a, b) => a + b, 0);
            out[i] = volSum === 0 ? 0 : mfvSum / volSum;
        }
        return out;
    }
    calcIchimoku(ten, kij, senB, chiOff) {
        const max = Math.max(ten, kij, senB) + chiOff;
        if (this.kd.length < max) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close');
        const calc = (arr, per) => {
            const outMax = new Array(this.kd.length).fill(NaN), outMin = new Array(this.kd.length).fill(NaN);
            for (let i = per - 1; i < this.kd.length; i++) {
                const w = arr.slice(i - per + 1, i + 1);
                outMax[i] = Math.max(...w); outMin[i] = Math.min(...w);
            }
            return [outMax, outMin];
        };
        const [hTen, lTen] = calc(h, ten), [hKij, lKij] = calc(h, kij), [hSenB, lSenB] = calc(h, senB);
        const tenkan = hTen.map((x, i) => (x + lTen[i]) / 2);
        const kijun = hKij.map((x, i) => (x + lKij[i]) / 2);
        const senA = new Array(this.kd.length).fill(NaN);
        for (let i = kij; i < this.kd.length; i++) senA[i] = (tenkan[i - kij] + kijun[i - kij]) / 2;
        const senB = new Array(this.kd.length).fill(NaN);
        for (let i = kij; i < this.kd.length; i++) senB[i] = (hSenB[i - kij] + lSenB[i - kij]) / 2;
        const chi = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) if (i + chiOff < this.kd.length) chi[i] = c[i + chiOff];
        return [tenkan, kijun, senA, senB, chi];
    }
    calcPSAR(acc, maxAcc) {
        if (this.kd.length < MIN_DATA_POINTS_PSAR) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close');
        const psar = new Array(this.kd.length).fill(NaN), bull = new Array(this.kd.length).fill(null), dir = new Array(this.kd.length).fill(0);
        let a = acc, ep = 0;
        if (c[0] < c[1]) { bull[1] = true; psar[1] = l[0]; ep = h[1]; } else { bull[1] = false; psar[1] = h[0]; ep = l[1]; }
        dir[1] = bull[1] ? 1 : -1; psar[0] = NaN;
        for (let i = 2; i < this.kd.length; i++) {
            const prevBull = bull[i - 1], prevPsar = psar[i - 1], prevEp = ep;
            let currPsar;
            if (prevBull) { currPsar = prevPsar + a * (prevEp - prevPsar); currPsar = Math.min(currPsar, l[i - 1], l[i]); }
            else { currPsar = prevPsar - a * (prevPsar - prevEp); currPsar = Math.max(currPsar, h[i - 1], h[i]); }
            let rev = false;
            if (prevBull && l[i] < currPsar) { bull[i] = false; rev = true; }
            else if (!prevBull && h[i] > currPsar) { bull[i] = true; rev = true; }
            else bull[i] = prevBull;
            if (rev) {
                a = acc; ep = bull[i] ? h[i] : l[i];
                if (bull[i]) psar[i] = Math.min(l[i], l[i - 1]); else psar[i] = Math.max(h[i], h[i - 1]);
            } else {
                if (bull[i]) { if (h[i] > ep) { ep = h[i]; a = Math.min(a + acc, maxAcc); } }
                else { if (l[i] < ep) { ep = l[i]; a = Math.min(a + acc, maxAcc); } }
                psar[i] = currPsar;
            }
            dir[i] = bull[i] ? 1 : -1;
        }
        psar[0] = psar[1]; dir[0] = dir[1];
        return [psar, dir];
    }
    calcVWAP() {
        if (this.kd.empty) return new Array(this.kd.length).fill(NaN);
        const h = this.kd.column('high'), l = this.kd.column('low'), c = this.kd.column('close'), v = this.kd.column('volume');
        const tp = h.map((x, i) => (x + l[i] + c[i]) / 3);
        const tpv = tp.map((x, i) => x * v[i]);
        let cumTpv = 0, cumVol = 0;
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) {
            cumTpv += tpv[i]; cumVol += v[i];
            out[i] = cumVol === 0 ? NaN : cumTpv / cumVol;
        }
        return out;
    }
    calcVolIdx(per) {
        if (this.kd.length < per || !this.iv.ATR) return new Array(this.kd.length).fill(NaN);
        const atr = this.kd.column('ATR'), c = this.kd.column('close');
        const norm = atr.map((a, i) => a / c[i]);
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) out[i] = norm.slice(i - per + 1, i + 1).reduce((a, b) => a + b, 0) / per;
        return out;
    }
    calcVWMA(per) {
        if (this.kd.length < per) return new Array(this.kd.length).fill(NaN);
        const c = this.kd.column('close'), v = this.kd.column('volume');
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            let pv = 0, vol = 0;
            for (let j = 0; j < per; j++) { pv += c[i - j] * v[i - j]; vol += v[i - j]; }
            out[i] = vol === 0 ? NaN : pv / vol;
        }
        return out;
    }
    calcVolDelta(per) {
        if (this.kd.length < MIN_DATA_POINTS_VOLATILITY) return new Array(this.kd.length).fill(NaN);
        const c = this.kd.column('close'), o = this.kd.column('open'), v = this.kd.column('volume');
        const buy = v.map((x, i) => c[i] > o[i] ? x : 0);
        const sell = v.map((x, i) => c[i] < o[i] ? x : 0);
        const out = new Array(this.kd.length).fill(NaN);
        for (let i = 0; i < this.kd.length; i++) {
            const start = Math.max(0, i - per + 1);
            const bSum = buy.slice(start, i + 1).reduce((a, x) => a + x, 0);
            const sSum = sell.slice(start, i + 1).reduce((a, x) => a + x, 0);
            const tot = bSum + sSum;
            out[i] = tot === 0 ? 0 : (bSum - sSum) / tot;
        }
        return out;
    }
    /* -------------- NEW INDICATOR CALCS -------------- */
    calcKeltner(per, mult) {
        if (this.kd.length < per) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const atr = this.kd.column('ATR');
        if (!atr) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const ema = this.ewmCustom(this.kd.column('close'), per, per);
        const upper = ema.map((m, i) => m + atr[i] * mult);
        const lower = ema.map((m, i) => m - atr[i] * mult);
        return [upper, ema, lower];
    }
    calcDonchian(per) {
        if (this.kd.length < per) return [new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN), new Array(this.kd.length).fill(NaN)];
        const h = this.kd.column('high'), l = this.kd.column('low');
        const upper = new Array(this.kd.length).fill(NaN), lower = new Array(this.kd.length).fill(NaN);
        for (let i = per - 1; i < this.kd.length; i++) {
            upper[i] = Math.max(...h.slice(i - per + 1, i + 1));
            lower[i] = Math.min(...l.slice(i - per + 1, i + 1));
        }
        const middle = upper.map((u, i) => (u + lower[i]) / 2);
        return [upper, middle, lower];
    }
    calcZigZag(depth, deviation) {
        if (this.kd.length < depth) return new Array(this.kd.length).fill(NaN);
        const c = this.kd.column('close');
        const out = new Array(this.kd.length).fill(NaN);
        let lastPivot = c[0]; let lastDir = 0; // 1 up, -1 down
        for (let i = 1; i < this.kd.length; i++) {
            const chg = (c[i] - lastPivot) / lastPivot * 100;
            if (lastDir >= 0) {
                if (chg >= deviation) { lastPivot = c[i]; lastDir = 1; out[i] = c[i]; }
                else if (chg <= -deviation) { lastPivot = c[i]; lastDir = -1; out[i] = c[i]; }
            } else {
                if (chg <= -deviation) { lastPivot = c[i]; lastDir = -1; out[i] = c[i]; }
                else if (chg >= deviation) { lastPivot = c[i]; lastDir = 1; out[i] = c[i]; }
            }
        }
        return out;
    }
    /* -------------- FIB LEVELS -------------- */
    calcFib() {
        const w = this.is.fibonacci_window;
        if (this.kd.length < w) { this.logger.warn(`${NEON_YELLOW}Need ${w} bars for Fib.${RESET}`); return; }
        const h = this.kd.column('high').slice(-w), l = this.kd.column('low').slice(-w);
        const hi = Math.max(...h), lo = Math.min(...l), diff = hi - lo;
        if (diff <= 0) { this.logger.warn(`${NEON_YELLOW}Invalid hi/lo for Fib.${RESET}`); return; }
        this.fib = {
            '0.0%': new Decimal(hi),
            '23.6%': new Decimal(hi - 0.236 * diff).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            '38.2%': new Decimal(hi - 0.382 * diff).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            '50.0%': new Decimal(hi - 0.500 * diff).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            '61.8%': new Decimal(hi - 0.618 * diff).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            '78.6%': new Decimal(hi - 0.786 * diff).toDecimalPlaces(5, Decimal.ROUND_DOWN),
            '100.0%': new Decimal(lo),
        };
    }
    /* -------------- SIGNAL GENERATION -------------- */
    _iv(key, def = NaN) { const v = this.iv[key]; return (typeof v === 'number' && !isNaN(v)) ? v : def; }
    _obImb(prc, ob) {
        if (!ob) return 0;
        const bids = (ob.b || []).reduce((s, b) => s.add(new Decimal(b[1])), new Decimal(0));
        const asks = (ob.a || []).reduce((s, a) => s.add(new Decimal(a[1])), new Decimal(0));
        const tot = bids.add(asks);
        return tot.eq(0) ? 0 : parseFloat(bids.sub(asks).div(tot).toString());
    }
    _mtfTrend(kd, type) {
        if (kd.empty) return 'UNKNOWN';
        const per = this.cfg.mtf_analysis.trend_period;
        const last = kd.get(-1).close;
        if (type === 'sma') {
            if (kd.length < per) return 'UNKNOWN';
            const sma = kd.rollingMean('close', per)[kd.length - 1];
            if (isNaN(sma)) return 'UNKNOWN';
            return last > sma ? 'UP' : last < sma ? 'DOWN' : 'SIDEWAYS';
        } else if (type === 'ema') {
            if (kd.length < per) return 'UNKNOWN';
            const ema = kd.ewmMean('close', per, per)[kd.length - 1];
            if (isNaN(ema)) return 'UNKNOWN';
            return last > ema ? 'UP' : last < ema ? 'DOWN' : 'SIDEWAYS';
        } else if (type === 'ehlers_supertrend') {
            const tmp = new TradingAnalyzer(kd, this.cfg, this.logger, this.symbol);
            const st = tmp.calcEhlersST(this.is.ehlers_slow_period, this.is.ehlers_slow_multiplier);
            if (st && st.direction && st.direction.length) return st.direction[st.direction.length - 1] === 1 ? 'UP' : st.direction[st.direction.length - 1] === -1 ? 'DOWN' : 'UNKNOWN';
        }
        return 'UNKNOWN';
    }
    generateTradingSignal(currentPrice, orderbookData, mtfTrends) {
        let score = 0.0;
        const c = this.cfg, w = this.w, s = this.is;
        if (this.kd.empty) { this.logger.warn(`${NEON_YELLOW}Empty DF – no signal.${RESET}`); return ['HOLD', 0]; }
        const cur = new Decimal(String(this.kd.get(-1).close));
        const prev = new Decimal(String(this.kd.length > 1 ? this.kd.get(-2).close : cur));

        /* EMA */
        if (c.indicators.ema_alignment) {
            const short = this._iv('EMA_Short'), long = this._iv('EMA_Long');
            if (!isNaN(short) && !isNaN(long)) {
                if (short > long) score += w.ema_alignment || 0;
                else if (short < long) score -= w.ema_alignment || 0;
            }
        }
        /* SMA */
        if (c.indicators.sma_trend_filter) {
            const long = this._iv('SMA_Long');
            if (!isNaN(long)) {
                if (cur.gt(long)) score += w.sma_trend_filter || 0;
                else if (cur.lt(long)) score -= w.sma_trend_filter || 0;
            }
        }
        /* Momentum */
        if (c.indicators.momentum) {
            const wt = w.momentum_rsi_stoch_cci_wr_mfi || 0;
            if (c.indicators.rsi) {
                const v = this._iv('RSI');
                if (!isNaN(v)) {
                    if (v < s.rsi_oversold) score += wt * 0.5;
                    else if (v > s.rsi_overbought) score -= wt * 0.5;
                }
            }
            if (c.indicators.stoch_rsi) {
                const k = this._iv('StochRSI_K'), d = this._iv('StochRSI_D');
                if (!isNaN(k) && !isNaN(d) && this.kd.length > 1) {
                    const pk = this.kd.get(-2).StochRSI_K, pd = this.kd.get(-2).StochRSI_D;
                    if (k > d && (isNaN(pk) || pk <= pd) && k < s.stoch_rsi_oversold) score += wt * 0.6;
                    else if (k < d && (isNaN(pk) || pk >= pd) && k > s.stoch_rsi_overbought) score -= wt * 0.6;
                    else if (k > d && k < 50) score += wt * 0.2;
                    else if (k < d && k > 50) score -= wt * 0.2;
                }
            }
            if (c.indicators.cci) {
                const v = this._iv('CCI');
                if (!isNaN(v)) {
                    if (v < s.cci_oversold) score += wt * 0.5;
                    else if (v > s.cci_overbought) score -= wt * 0.5;
                }
            }
            if (c.indicators.wr) {
                const v = this._iv('WR');
                if (!isNaN(v)) {
                    if (v < s.williams_r_oversold) score += wt * 0.5;
                    else if (v > s.williams_r_overbought) score -= wt * 0.5;
                }
            }
            if (c.indicators.mfi) {
                const v = this._iv('MFI');
                if (!isNaN(v)) {
                    if (v < s.mfi_oversold) score += wt * 0.5;
                    else if (v > s.mfi_overbought) score -= wt * 0.5;
                }
            }
        }
        /* Volume */
        if (c.indicators.volume_confirmation) {
            const wt = w.volume_confirmation || 0;
            if (c.indicators.obv) {
                const o = this._iv('OBV'), e = this._iv('OBV_EMA');
                if (!isNaN(o) && !isNaN(e) && o > e) score += wt * 0.5;
                else if (!isNaN(o) && !isNaN(e) && o < e) score -= wt * 0.5;
            }
            if (c.indicators.cmf) {
                const v = this._iv('CMF');
                if (!isNaN(v) && v > 0) score += wt * 0.5;
                else if (!isNaN(v) && v < 0) score -= wt * 0.5;
            }
        }
        /* BB */
        if (c.indicators.bollinger_bands) {
            const up = this._iv('BB_Upper'), lo = this._iv('BB_Lower');
            if (!isNaN(up) && !isNaN(lo)) {
                if (cur.lt(lo)) score += w.bollinger_bands || 0;
                else if (cur.gt(up)) score -= w.bollinger_bands || 0;
            }
        }
        /* VWAP */
        if (c.indicators.vwap) {
            const v = this._iv('VWAP');
            if (!isNaN(v)) {
                if (cur.gt(v)) score += w.vwap || 0;
                else if (cur.lt(v)) score -= w.vwap || 0;
            }
        }
        /* PSAR */
        if (c.indicators.psar) {
            const dir = this._iv('PSAR_Dir');
            if (!isNaN(dir)) {
                if (dir === 1) score += w.psar || 0;
                else if (dir === -1) score -= w.psar || 0;
            }
        }
        /* SMA 10 Cross */
        if (c.indicators.sma_10) {
            const v = this._iv('SMA_10');
            if (!isNaN(v) && this.kd.length > 1) {
                const prev = this.kd.get(-2);
                if (cur.gt(v) && prev.close < v) score += w.sma_10 || 0;
                else if (cur.lt(v) && prev.close > v) score -= w.sma_10 || 0;
            }
        }
        /* Orderbook Imbalance */
        if (c.indicators.orderbook_imbalance) {
            const imb = this._obImb(currentPrice, orderbookData);
            if (imb > 0.1) score += w.orderbook_imbalance || 0;
            else if (imb < -0.1) score -= w.orderbook_imbalance || 0;
        }
        /* Ehlers Supertrend */
        if (c.indicators.ehlers_supertrend) {
            const dir = this._iv('ST_Fast_Dir');
            if (!isNaN(dir)) {
                if (dir === 1) score += w.ehlers_supertrend_alignment || 0;
                else if (dir === -1) score -= w.ehlers_supertrend_alignment || 0;
            }
        }
        /* MACD */
        if (c.indicators.macd) {
            const line = this._iv('MACD_Line'), sig = this._iv('MACD_Signal');
            if (!isNaN(line) && !isNaN(sig) && this.kd.length > 1) {
                const prevLine = this.kd.get(-2).MACD_Line, prevSig = this.kd.get(-2).MACD_Signal;
                if (line > sig && prevLine <= prevSig) score += w.macd_alignment || 0;
                else if (line < sig && prevLine >= prevSig) score -= w.macd_alignment || 0;
            }
        }
        /* ADX */
        if (c.indicators.adx) {
            const adx = this._iv('ADX'), pdi = this._iv('PlusDI'), mdi = this._iv('MinusDI');
            if (!isNaN(adx) && !isNaN(pdi) && !isNaN(mdi)) {
                if (adx > ADX_STRONG_TREND_THRESHOLD) {
                    if (pdi > mdi) score += w.adx_strength || 0;
                    else if (mdi > pdi) score -= w.adx_strength || 0;
                }
            }
        }
        /* Volatility Index */
        if (c.indicators.volatility_index) {
            const v = this._iv('Volatility_Index');
            if (!isNaN(v) && this.kd.length > 1) {
                const pv = this.kd.get(-2).Volatility_Index;
                if (v > pv && v > 0.05) score += w.volatility_index_signal || 0; // rising vol is a buy signal
                else if (v < pv && v > 0.05) score -= w.volatility_index_signal || 0; // falling vol
            }
        }
        /* VWMA Cross */
        if (c.indicators.vwma) {
            const v = this._iv('VWMA');
            if (!isNaN(v)) {
                if (cur.gt(v)) score += w.vwma_cross || 0;
                else if (cur.lt(v)) score -= w.vwma_cross || 0;
            }
        }
        /* Volume Delta */
        if (c.indicators.volume_delta) {
            const v = this._iv('Volume_Delta');
            if (!isNaN(v)) {
                if (v > s.volume_delta_threshold) score += w.volume_delta_signal || 0;
                else if (v < -s.volume_delta_threshold) score -= w.volume_delta_signal || 0;
            }
        }
        /* MTF Confluence */
        if (c.mtf_analysis.enabled) {
            const mtfScore = Object.values(mtfTrends).reduce((acc, t) => {
                if (t === 'UP') return acc + (w.mtf_trend_confluence / Object.keys(mtfTrends).length);
                if (t === 'DOWN') return acc - (w.mtf_trend_confluence / Object.keys(mtfTrends).length);
                return acc;
            }, 0);
            score += mtfScore;
        }

        /* NEW INDICATOR SCORING */
        /* Keltner Channel Breakout */
        if (c.indicators.keltner_channels) {
            const up = this._iv('KC_Upper'), lo = this._iv('KC_Lower');
            if (!isNaN(up) && !isNaN(lo) && this.kd.length > 1) {
                const prev = this.kd.get(-2);
                if (cur.gt(up) && prev.close <= up) score += w.keltner_breakout || 0;
                else if (cur.lt(lo) && prev.close >= lo) score -= w.keltner_breakout || 0;
            }
        }
        /* Donchian Channel Breakout */
        if (c.indicators.donchian_channels) {
            const up = this._iv('DC_Upper'), lo = this._iv('DC_Lower');
            if (!isNaN(up) && !isNaN(lo) && this.kd.length > 1) {
                const prev = this.kd.get(-2);
                if (cur.gt(up) && prev.close <= up) score += w.donchian_breakout || 0;
                else if (cur.lt(lo) && prev.close >= lo) score -= w.donchian_breakout || 0;
            }
        }
        /* ZigZag Pivot */
        if (c.indicators.zigzag) {
            const v = this._iv('ZigZag');
            if (!isNaN(v)) {
                const lastIdx = this.kd.column('ZigZag').slice(0, -1).lastIndexOf(v);
                if (lastIdx !== -1) {
                    const lastPivotPrice = this.kd.get(lastIdx).close;
                    const lastPivotTime = this.kd.get(lastIdx).start_time;
                    const curTime = this.kd.get(-1).start_time;
                    const isSwingLow = cur.gt(lastPivotPrice) && (curTime.getTime() - lastPivotTime.getTime() > (s.zigzag_depth * 60 * 1000));
                    const isSwingHigh = cur.lt(lastPivotPrice) && (curTime.getTime() - lastPivotTime.getTime() > (s.zigzag_depth * 60 * 1000));
                    if (isSwingLow) score += w.zigzag_pivot || 0;
                    else if (isSwingHigh) score -= w.zigzag_pivot || 0;
                }
            }
        }

        /* Fibonacci Confluence */
        if (c.indicators.fibonacci_levels) {
            const m = this._iv('BB_Middle') || this._iv('KC_Middle') || this._iv('DC_Middle');
            if (!isNaN(m)) {
                const fibKeys = Object.keys(this.fib);
                const closestFib = fibKeys.reduce((prev, curr) => Math.abs(this.fib[curr].sub(m)) < Math.abs(this.fib[prev].sub(m)) ? curr : prev);
                const fibPrc = this.fib[closestFib];
                if (fibPrc.gt(cur)) score -= w.fibonacci_levels || 0;
                else if (fibPrc.lt(cur)) score += w.fibonacci_levels || 0;
            }
        }

        const signal = score > c.signal_threshold.buy ? 'BUY' : score < c.signal_threshold.sell ? 'SELL' : 'HOLD';
        return [signal, score];
    }
    /* -------------- PRETTY PRINT -------------- */
    displayIndicatorValuesAndPrice(currentPrice, latestKline, symbol) {
        if (!latestKline || !currentPrice) return;
        const o = new Decimal(String(latestKline.open)), h = new Decimal(String(latestKline.high)),
            l = new Decimal(String(latestKline.low)), c = new Decimal(String(latestKline.close));
        const dir = currentPrice.gt(o) ? NEON_GREEN + '▲' : NEON_RED + '▼';
        const chg = c.sub(o).div(o).mul(100).toFixed(2);
        let log = `\n${NEON_PURPLE}-------------------- ${symbol} | ${new Date().toISOString()} --------------------${RESET}\n`;
        log += `${NEON_GREEN}Price:${RESET} ${currentPrice.toFixed(5)} ${dir} (${chg}%) | ${NEON_GREEN}O:${o.toFixed(5)} H:${h.toFixed(5)} L:${l.toFixed(5)} C:${c.toFixed(5)}${RESET}\n`;

        const sections = {
            "Channels & Fibs": [
                'BB_Upper', 'BB_Middle', 'BB_Lower',
                'KC_Upper', 'KC_Middle', 'KC_Lower',
                'DC_Upper', 'DC_Middle', 'DC_Lower',
                'VWAP', 'VWMA',
            ],
            "Trends": [
                'SMA_Long', 'EMA_Long', 'ST_Slow_Val', 'ST_Slow_Dir', 'PSAR_Val', 'PSAR_Dir',
                'Tenkan_Sen', 'Kijun_Sen', 'Senkou_Span_A', 'Senkou_Span_B', 'Chikou_Span', 'ZigZag',
            ],
            "Momentum & Strength": [
                'RSI', 'StochRSI_K', 'StochRSI_D', 'CCI', 'WR', 'MFI', 'MACD_Line', 'MACD_Signal', 'MACD_Hist',
            ],
            "Volatility & Volume": [
                'ATR', 'Volatility_Index', 'OBV', 'OBV_EMA', 'CMF', 'Volume_Delta', 'ADX', 'PlusDI', 'MinusDI',
            ],
        };

        for (const [title, indicators] of Object.entries(sections)) {
            let sectionLog = `\n${NEON_BLUE}--- ${title} ---${RESET}\n`;
            let hasValues = false;
            for (const key of indicators) {
                const val = this._iv(key);
                if (!isNaN(val)) {
                    hasValues = true;
                    const color = INDICATOR_COLORS[key] || RESET;
                    sectionLog += `  ${color}${key}:${RESET} ${val.toFixed(2)}${RESET}\n`;
                }
            }
            if (hasValues) log += sectionLog;
        }

        if (this.cfg.indicators.fibonacci_levels) {
            log += `\n${NEON_BLUE}--- Fibs ---${RESET}\n`;
            let hasFibs = false;
            for (const [lvl, prc] of Object.entries(this.fib)) {
                if (prc) {
                    hasFibs = true;
                    log += `  ${NEON_CYAN}Fib ${lvl}:${RESET} ${prc.toFixed(5)}${RESET}\n`;
                }
            }
            if (hasFibs) log += `\n`;
        }
        this.logger.info(log);
    }
}

/* -------------- CORE EXECUTION LOOP -------------- */
async function main() {
    const logger = setupLogger('main');
    logger.info(`${NEON_GREEN}Starting Trading Bot...${RESET}`);
    const configFile = path.join(process.cwd(), CONFIG_FILE);
    const config = loadConfig(configFile, logger);
    const symbol = config.symbol;
    const interval = config.interval;
    const loopDelay = config.loop_delay_seconds || LOOP_DELAY_SECONDS;

    // Run the backtest first to see how the strategy performs
    await runBacktest(config, logger, symbol, interval);

    // After backtest, start the live trading loop
    const pm = new PositionManager(config, logger, symbol);
    const perf = new PerformanceTracker(logger);
    const alerts = new AlertSystem(logger);

    while (true) {
        try {
            logger.info(`${NEON_PURPLE}Fetching live data for ${symbol} at ${interval} interval...${RESET}`);
            const klines = await fetchKlines(symbol, interval, 200, logger);
            const currentPrice = await fetchCurrentPrice(symbol, logger);
            const orderbookData = await fetchOrderbook(symbol, 10, logger);

            if (!klines || klines.empty || !currentPrice) {
                logger.warn(`${NEON_YELLOW}Failed to get required data. Retrying...${RESET}`);
                await setInterval(loopDelay * 1000);
                continue;
            }

            const analyzer = new TradingAnalyzer(klines, config, logger, symbol);
            if (klines.empty) {
                logger.warn(`${NEON_YELLOW}Klines are empty after analysis. Retrying...${RESET}`);
                await setInterval(loopDelay * 1000);
                continue;
            }

            const latestKline = klines.get(-1);
            analyzer.displayIndicatorValuesAndPrice(currentPrice, latestKline, symbol);

            const [signal, score] = analyzer.generateTradingSignal(currentPrice, orderbookData, {}); // MTF trends not used in this simplified loop
            logger.info(`${NEON_CYAN}Generated Signal: ${signal} (Score: ${score.toFixed(4)})${RESET}`);

            if (config.trade_management.enabled) {
                pm.managePositions(currentPrice, perf);
                if (signal === 'BUY' && pm.getOpenPositions().length < pm.maxPos) {
                    pm.openPosition('BUY', currentPrice, new Decimal(String(analyzer._iv('ATR', 0))));
                } else if (signal === 'SELL' && pm.getOpenPositions().length < pm.maxPos) {
                    pm.openPosition('SELL', currentPrice, new Decimal(String(analyzer._iv('ATR', 0))));
                }
            }

        } catch (e) {
            logger.error(`${NEON_RED}An error occurred in the main loop: ${e.message}${RESET}`);
            alerts.sendAlert(`Bot Error: ${e.message}`, 'ERROR');
        }

        logger.info(`${NEON_PURPLE}Sleeping for ${loopDelay}s...${RESET}`);
        await setInterval(loopDelay * 1000);
    }
}

async function runBacktest(config, logger, symbol, interval) {
    logger.info(`${NEON_YELLOW}--- STARTING BACKTEST ---${RESET}`);
    const backtestKlines = await fetchKlines(symbol, interval, 500, logger); // Fetch a larger dataset for backtesting
    if (!backtestKlines || backtestKlines.empty) {
        logger.error(`${NEON_RED}Failed to get historical data for backtest. Skipping...${RESET}`);
        return;
    }

    const btPm = new PositionManager(config, logger, symbol);
    const btPerf = new PerformanceTracker(logger);
    
    // Iterate through the historical data bar by bar
    for (let i = 200; i < backtestKlines.length; i++) {
        const slicedKlines = new KlineData(backtestKlines.data.slice(0, i + 1));
        const currentKline = slicedKlines.get(-1);

        const analyzer = new TradingAnalyzer(slicedKlines, config, logger, symbol);
        const [signal, score] = analyzer.generateTradingSignal(new Decimal(currentKline.close), null, {});
        
        // Simulate trade logic
        if (signal === 'BUY') {
            btPm.openPosition('BUY', new Decimal(currentKline.close), new Decimal(String(analyzer._iv('ATR', 0))));
        } else if (signal === 'SELL') {
            btPm.openPosition('SELL', new Decimal(currentKline.close), new Decimal(String(analyzer._iv('ATR', 0))));
        }
        
        // Manage positions at the close of each bar
        btPm.managePositions(new Decimal(currentKline.close), btPerf);
    }

    // Output backtest summary
    const summary = btPerf.getSummary();
    const summaryLog = `\n${NEON_BLUE}--- BACKTEST SUMMARY FOR ${symbol} ---${RESET}
${NEON_CYAN}Total Trades:${RESET} ${summary.total_trades}
${NEON_CYAN}Total PnL:${RESET} ${summary.total_pnl.toFixed(5)}
${NEON_CYAN}Wins:${RESET} ${summary.wins}
${NEON_CYAN}Losses:${RESET} ${summary.losses}
${NEON_CYAN}Win Rate:${RESET} ${summary.win_rate}
${NEON_YELLOW}-----------------------------------${RESET}\n`;
    logger.info(summaryLog);
    logger.info(`${NEON_YELLOW}--- BACKTEST COMPLETE ---${RESET}`);
}


if (require.main === module) {
    main().catch(err => {
        const logger = setupLogger('main');
        logger.error(`${NEON_RED}Fatal exception: ${err.message}${RESET}`);
        process.exit(1);
    });
}
