/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v6.1 (Integrated Engine - MONOLITHIC)
 * ----------------------------------------------------------------------
 * - FIXED: All configuration and TA helper logic is now fully self-contained
 *          to avoid module import mismatches.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';
import {
    safeArr, safeGetFinalValue, wilders, sma, ema, atr, rsi, stoch, macd, adx, mfi,
    chop, cci, linReg, bollinger, keltner, superTrend, chandelierExit, vwap,
    findFVG, detectDivergence, historicalVolatility, marketRegime,
    fibPivots, getOrderbookLevels, getFibonacciPivotsAsSR, getHistoricalHighLowSR, combineAndFilterSR,
    calculateWSS, ehlersSuperTrendCross // Import newly added functions
} from './indicators.js'; // Import indicators
import logger from './logger.js'; // Import logger

dotenv.config();

// --- ⚙️ CONFIG LOADER (Reading from config.json) ---
let config = {};
try {
    const configContent = fs.readFileSync('config.json', 'utf-8');
    config = JSON.parse(configContent);
} catch (e) { console.error(chalk.red(`[CRITICAL] Could not load config.json: ${e.message}`)); process.exit(1); }
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME MANAGER ---
const NEON = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#00AFFF'),
    CYAN: chalk.hex('#00FFFF'), PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'), ORANGE: chalk.hex('#FF9F00'), BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
};

// --- 📡 ENHANCED DATA PROVIDER ---
class EnhancedDataProvider {
    constructor() { this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout }); }
    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try { return (await this.api.get(url, { params })).data; }
            catch (error) { if (attempt === retries) throw error; await setTimeout(Math.pow(config.api.backoff_factor, attempt) * 1000); }
        }
    }
    async fetchAll() {
        try {
            const tickerResponse = await this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol });
            if (!tickerResponse || !tickerResponse.result || !tickerResponse.result.list || tickerResponse.result.list.length === 0) { throw new Error('Invalid or empty ticker data received.'); }
            const price = parseFloat(tickerResponse.result.list[0].lastPrice);

            const klineResponse = await this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit });
            if (!klineResponse || !klineResponse.result || !klineResponse.result.list) { throw new Error('Invalid or empty kline data received.'); }
            const parseC = (list) => list.reverse().map(c => ({ o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) }));
            const candles = parseC(klineResponse.result.list);

            const klineMTFResponse = await this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 });
            if (!klineMTFResponse || !klineMTFResponse.result || !klineMTFResponse.result.list) { throw new Error('Invalid or empty klineMTF data received.'); }
            const candlesMTF = parseC(klineMTFResponse.result.list);

            const obResponse = await this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth });
            if (!obResponse || !obResponse.result || !obResponse.result.b || !obResponse.result.a) { throw new Error('Invalid or empty orderbook data received.'); }
            const bids = obResponse.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
            const asks = obResponse.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));

            const dailyResponse = await this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 });
            if (!dailyResponse || !dailyResponse.result || !dailyResponse.result.list || dailyResponse.result.list.length < 2 || !dailyResponse.result.list[1] || dailyResponse.result.list[1].length < 4) { throw new Error('Invalid or malformed daily kline data received.'); }
            const daily = { h: parseFloat(dailyResponse.result.list[1][2]), l: parseFloat(dailyResponse.result.list[1][3]), c: parseFloat(dailyResponse.result.list[1][4]) };
            
            return {
                price, candles, candlesMTF, bids, asks, daily, timestamp: Date.now()
            };
        } catch (e) { logger.warn(`[WARN] Data Fetch Fail: ${e.message}`); return null; } // Use logger here
    }
}

// --- 💰 EXCHANGE & RISK MANAGEMENT ---
class EnhancedPaperExchange {
    constructor(logger) { // Added logger parameter
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null;
        this.dailyPnL = new Decimal(0);
        this.logger = logger; // Store logger instance
    }

    canTrade() {
        const drawdownPct = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdownPct.gt(config.risk.max_drawdown)) {
            // Use logger.warn instead of console.log
            this.logger.warn('🚨 MAX DRAWDOWN HIT - Trading disabled.');
            return false;
        }
        const dailyLossPct = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLossPct.lt(-config.risk.daily_loss_limit)) {
            // Use logger.warn instead of console.log
            this.logger.warn('🚨 DAILY LOSS LIMIT HIT - Trading disabled.');
            return false;
        }
        return true;
    }

    evaluate(priceVal, signal) {
        if (!this.canTrade()) {
            if (this.pos) this.handlePositionClose(new Decimal(priceVal), 'RISK_STOP');
            return;
        }
        const price = new Decimal(priceVal);
        if (this.pos) this.handlePositionClose(price);

        const validAction = 
            signal && 
            (signal.action === 'BUY' || signal.action === 'SELL') && 
            typeof signal.entry === 'number' && 
            typeof signal.sl === 'number' && 
            typeof signal.tp === 'number';

        if (!this.pos && validAction && signal.confidence >= config.min_confidence) {
            this.handlePositionOpen(price, signal);
        }
    }

    handlePositionClose(price, forceReason = null) {
        if (!this.pos) return;

        let close = false;
        let reason = forceReason || '';
        if (this.pos.side === 'BUY') {
            if (forceReason || price.lte(this.pos.sl)) { close = true; reason ||= 'SL Hit'; } 
            else if (price.gte(this.pos.tp)) { close = true; reason ||= 'TP Hit'; }
        } else {
            if (forceReason || price.gte(this.pos.sl)) { close = true; reason ||= 'SL Hit'; } 
            else if (price.lte(this.pos.tp)) { close = true; reason ||= 'TP Hit'; }
        }

        if (!close) return;

        const slippage = price.mul(config.paper_trading.slippage);
        const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
        const rawPnl = this.pos.side === 'BUY'
            ? exitPrice.sub(this.pos.entry).mul(this.pos.qty)
            : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
        const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
        const netPnl = rawPnl.sub(fee);

        this.balance = this.balance.add(netPnl);
        this.dailyPnL = this.dailyPnL.add(netPnl);
        
        // Use logger.logTrade for trade closing information
        this.logger.logTrade(this.pos.entry, exitPrice, netPnl, reason, this.pos.side, this.pos.strategy);
        this.pos = null;
    }

    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry);
        const sl = new Decimal(signal.sl);
        const tp = new Decimal(signal.tp);
        const dist = entry.sub(sl).abs();
        if (dist.isZero()) return;

        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);

        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;

        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
        this.balance = this.balance.sub(fee);

        this.pos = {
            side: signal.action,
            entry: execPrice,
            qty,
            sl,
            tp,
            strategy: signal.strategy || 'UNKNOWN'
        };

        // Use logger for position open event
        this.logger.logPositionOpen(signal.action, this.pos.strategy, execPrice.toFixed(4), qty.toFixed(4));
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN ---
class EnhancedGeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { console.error('Missing GEMINI_API_KEY'); process.exit(1); }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(ctx) {
        const prompt = `
        ACT AS: Institutional Scalping Algorithm.
        OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD.

        QUANTITATIVE BIAS:
        - **WSS Score (Crucial Filter):** ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
        - CRITICAL RULE: Action must align with WSS. BUY requires WSS >= ${config.indicators.wss_weights.action_threshold}. SELL requires WSS <= -${config.indicators.wss_weights.action_threshold}.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility.toFixed(4)} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle.slope.toFixed(4)} (Slope) | ADX: ${ctx.adx.toFixed(2)}
        - Momentum: RSI=${ctx.rsi.toFixed(2)}, Stoch=${ctx.stoch_k.toFixed(0)}, MACD=${ctx.macd_hist.toFixed(4)}
        - Structure: VWAP=${ctx.vwap.toFixed(4)}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
        - Support/Resistance: ${ctx.sr_levels}

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0): Pullback to VWAP/EMA, anticipate continuation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES): Trade in direction of MTF trend on volatility expansion.
        3. MEAN_REVERSION (WSS | > 2.0): Fade extreme RSI/Stoch readings, anticipate reversal.
        4. LIQUIDITY_GRAB (FVG/SR levels): Trade retests of identified zones.
        5. DIVERGENCE_REVERSAL (Strong Divergence): Trade reversals on confirmed divergences.

        RESPONSE FORMAT (JSON):
        {
          "strategy_id": <1-5 or "HOLD">
          "confidence": <0.0-1.0>,
          "action": "<BUY|SELL|HOLD>",
          "reason": "<Brief explanation of the signal based on context and WSS>\n",
          "entry": <entry_price_if_BUY_or_SELL | null>,
          "sl": <stop_loss_price | null>,
          "tp": <take_profit_price | null>
        }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const response = await res.response;
            const text = response.text();
            
            // Add validation for AI response text
            if (!text || typeof text !== 'string' || !text.trim().startsWith('{') || !text.trim().endsWith('}')) {
                logger.warn(`[AI WARN] Invalid or empty AI response received. Response text: "${text}"`);
                return { strategy_id: 'HOLD', confidence: 0, action: 'HOLD', reason: 'Invalid AI response', entry: null, sl: null, tp: null };
            }

            const jsonStartIndex = text.indexOf('{');
            const jsonEndIndex = text.lastIndexOf('}');
            if (jsonStartIndex === -1 || jsonEndIndex === -1) throw new Error(
                `AI response is not valid JSON. Response: ${text}`
            );

            const jsonString = text.substring(jsonStartIndex, jsonEndIndex + 1);
            return JSON.parse(jsonString);
        } catch (e) {
            logger.error(`[AI ERROR] Gemini API Error: ${e.message}`);
            return { strategy_id: 'HOLD', confidence: 0, action: 'HOLD', reason: 'AI analysis failed', entry: null, sl: null, tp: null };
        }
    }
}

// --- Helper function to calculate all indicators ---
function calculateIndicators(data, config) {
    const { price, candles, candlesMTF, bids, asks, daily, timestamp } = data;
    const indicators = { ...data }; // Start with raw data

    // --- Core Indicators ---
    indicators.rsi = rsi(candles, config.indicators.rsi_period);
    indicators.stoch_k = stoch(candles, config.indicators.stoch_k_period, config.indicators.stoch_d_period)[0];
    indicators.stoch_d = stoch(candles, config.indicators.stoch_k_period, config.indicators.stoch_d_period)[1];
    const macdData = macd(candles, config.indicators.macd_fast_period, config.indicators.macd_slow_period, config.indicators.macd_signal_period);
    indicators.macd = macdData.MACD;
    indicators.macd_signal = macdData.MACDSignal;
    indicators.macd_hist = macdData.MACDHist;
    indicators.adx = adx(candles, config.indicators.adx_period);
    indicators.mfi = mfi(candles, config.indicators.mfi_period);
    indicators.chop = chop(candles, config.indicators.chop_period);
    indicators.cci = cci(candles, config.indicators.cci_period);
    indicators.linReg = linReg(candles, config.indicators.linreg_period);
    const bb = bollinger(candles, config.indicators.bb_period, config.indicators.bb_std_dev);
    indicators.bb_upper = bb.upper;
    indicators.bb_middle = bb.middle;
    indicators.bb_lower = bb.lower;
    const kc = keltner(candles, config.indicators.kc_period, config.indicators.kc_multiplier);
    indicators.kc_upper = kc.upper;
    indicators.kc_middle = kc.middle;
    indicators.kc_lower = kc.lower;
    const st = superTrend(candles, config.indicators.st_period, config.indicators.st_multiplier);
    indicators.superTrend = st.superTrend;
    indicators.st_direction = st.direction;
    const ce = chandelierExit(candles, config.indicators.ce_period, config.indicators.ce_multiplier);
    indicators.chandelierExit = ce.chandelierExit;
    indicators.chandelier_direction = ce.direction;
    indicators.vwap = vwap(candles);

    // --- Structure & Advanced Indicators ---
    const fvgData = findFVG(candles);
    indicators.fvg = fvgData;
    indicators.divergence = detectDivergence(candles, config.indicators.divergence_period);
    indicators.historicalVolatility = historicalVolatility(candles, config.indicators.hv_period);
    indicators.marketRegime = marketRegime(candles, config.indicators.regime_threshold);
    const fibs = fibPivots(candles);
    indicators.fibs = fibs;
    const sr = getFibonacciPivotsAsSR(fibs);
    indicators.sr_levels = sr;
    const highLowSR = getHistoricalHighLowSR(candles, config.indicators.sr_period);
    indicators.highLowSR = highLowSR;
    const combinedSR = combineAndFilterSR(sr, highLowSR);
    indicators.sr_levels = combinedSR;

    // --- Volatility & Trend Angle ---
    indicators.volatility = atr(candles, config.indicators.atr_period);
    const trendAngle = linReg(candles, config.indicators.trend_angle_period);
    indicators.trend_angle = { slope: trendAngle.slope, intercept: trendAngle.intercept };

    // --- WSS Calculation ---
    const wssResult = calculateWSS(indicators, config.indicators.wss_weights);
    indicators.wss = wssResult.wss;
    indicators.wss_trend = wssResult.trend;

    // --- Ehlers Supertrend Cross (New Strategy Component) ---
    const estc = ehlersSuperTrendCross(candles, config.indicators.estc_period, config.indicators.estc_multiplier, config.indicators.estc_filter_alpha);
    indicators.estc = estc.estc;
    indicators.estc_direction = estc.direction;

    // --- Add more indicators as needed ---

    return indicators;
}

// --- Entry Point ---
main().catch(error => {
    logger.error(`[ENGINE CRASH] Unhandled error: ${error.message}`, error);
    process.exit(1);
});
