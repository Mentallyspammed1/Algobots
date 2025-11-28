/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v6.1 (Integrated Engine - MONOLITHIC)
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';

import {
    safeArr,
    atr,
    rsi,
    stoch,
    macd,
    adx,
    mfi,
    chop,
    cci,
    linReg,
    bollinger,
    keltner,
    superTrend,
    chandelierExit,
    vwap,
    findFVG,
    detectDivergence,
    historicalVolatility,
    marketRegime,
    fibPivots,
    getFibonacciPivotsAsSR,
    getHistoricalHighLowSR,
    combineAndFilterSR,
    calculateWSS,
    ehlersSuperTrendCross
} from './indicators.js';

import logger from './logger.js';

dotenv.config();

// --- ⚙️ CONFIG LOADER ---
let config = {};
try {
    const configContent = fs.readFileSync('config.json', 'utf-8');
    config = JSON.parse(configContent);
} catch (e) {
    console.error(chalk.red(`[CRITICAL] Could not load config.json: ${e.message}`));
    process.exit(1);
}
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME MANAGER (optional) ---
const NEON = {
    GREEN: chalk.hex('#39FF14'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#00AFFF'),
    CYAN: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'),
    YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'),
    BOLD: chalk.bold,
    bg: text => chalk.bgHex('#222')(text)
};

// --- 📡 ENHANCED DATA PROVIDER ---
class EnhancedDataProvider {
    constructor() {
        this.api = axios.create({
            baseURL: 'https://api.bybit.com/v5/market',
            timeout: config.api.timeout
        });
    }

    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const res = await this.api.get(url, { params });
                return res.data;
            } catch (error) {
                if (attempt === retries) throw error;
                const delay = Math.pow(config.api.backoff_factor, attempt) * 1000;
                await sleep(delay);
            }
        }
    }

    async fetchAll() {
        try {
            const tickerResponse = await this.fetchWithRetry('/tickers', {
                category: 'linear',
                symbol: config.symbol
            });
            const tickerList = tickerResponse?.result?.list;
            if (!tickerList || !tickerList.length) {
                throw new Error('Invalid or empty ticker data received.');
            }
            const price = parseFloat(tickerList[0].lastPrice);

            const klineResponse = await this.fetchWithRetry('/kline', {
                category: 'linear',
                symbol: config.symbol,
                interval: config.interval,
                limit: config.limit
            });
            const klineList = klineResponse?.result?.list;
            if (!klineList) {
                throw new Error('Invalid or empty kline data received.');
            }
            const parseC = list =>
                list
                    .slice()
                    .reverse()
                    .map(c => ({
                        o: parseFloat(c[1]),
                        h: parseFloat(c[2]),
                        l: parseFloat(c[3]),
                        c: parseFloat(c[4]),
                        v: parseFloat(c[5]),
                        t: parseInt(c[0])
                    }));
            const candles = parseC(klineList);

            const klineMTFResponse = await this.fetchWithRetry('/kline', {
                category: 'linear',
                symbol: config.symbol,
                interval: config.trend_interval,
                limit: 100
            });
            const klineMTFList = klineMTFResponse?.result?.list;
            if (!klineMTFList) {
                throw new Error('Invalid or empty klineMTF data received.');
            }
            const candlesMTF = parseC(klineMTFList);

            const obResponse = await this.fetchWithRetry('/orderbook', {
                category: 'linear',
                symbol: config.symbol,
                limit: config.orderbook.depth
            });
            const ob = obResponse?.result;
            if (!ob?.b || !ob?.a) {
                throw new Error('Invalid or empty orderbook data received.');
            }
            const bids = ob.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
            const asks = ob.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));

            const dailyResponse = await this.fetchWithRetry('/kline', {
                category: 'linear',
                symbol: config.symbol,
                interval: 'D',
                limit: 2
            });
            const dlist = dailyResponse?.result?.list;
            if (!dlist || dlist.length < 2 || !dlist[1] || dlist[1].length < 5) {
                throw new Error('Invalid or malformed daily kline data received.');
            }
            const daily = {
                h: parseFloat(dlist[1][2]),
                l: parseFloat(dlist[1][3]),
                c: parseFloat(dlist[1][4])
            };

            return {
                price,
                candles,
                candlesMTF,
                bids,
                asks,
                daily,
                timestamp: Date.now()
            };
        } catch (e) {
            logger.warn(`[WARN] Data Fetch Fail: ${e.message}`);
            return null;
        }
    }
}

// --- 💰 EXCHANGE & RISK MANAGEMENT ---
class EnhancedPaperExchange {
    constructor(loggerInstance) {
        this.logger = loggerInstance;
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null;
        this.dailyPnL = new Decimal(0);
    }

    canTrade() {
        const drawdownPct = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdownPct.gt(config.risk.max_drawdown)) {
            this.logger.warn('🚨 MAX DRAWDOWN HIT - Trading disabled.');
            return false;
        }
        const dailyLossPct = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLossPct.lt(-config.risk.daily_loss_limit)) {
            this.logger.warn('🚨 DAILY LOSS LIMIT HIT - Trading disabled.');
            return false;
        }
        return true;
    }

    maybeCloseForRisk(price) {
        if (!this.canTrade() && this.pos) {
            this.handlePositionClose(price, 'RISK_STOP');
        }
    }

    evaluateSignal(priceVal, signal) {
        const price = new Decimal(priceVal);

        this.maybeCloseForRisk(price);
        if (!this.canTrade()) return;

        // Always check SL/TP on open position
        this.checkSLTP(price);

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

    checkSLTP(price) {
        if (!this.pos) return;
        this.handlePositionClose(price);
    }

    handlePositionClose(price, forceReason = null) {
        if (!this.pos) return;

        let close = false;
        let reason = forceReason || '';
        const side = this.pos.side;

        if (side === 'BUY') {
            if (forceReason || price.lte(this.pos.sl)) {
                close = true;
                reason ||= 'SL Hit';
            } else if (price.gte(this.pos.tp)) {
                close = true;
                reason ||= 'TP Hit';
            }
        } else {
            if (forceReason || price.gte(this.pos.sl)) {
                close = true;
                reason ||= 'SL Hit';
            } else if (price.lte(this.pos.tp)) {
                close = true;
                reason ||= 'TP Hit';
            }
        }

        if (!close) return;

        const slippage = price.mul(config.paper_trading.slippage);
        const exitPrice = side === 'BUY' ? price.sub(slippage) : price.add(slippage);

        const rawPnl =
            side === 'BUY'
                ? exitPrice.sub(this.pos.entry).mul(this.pos.qty)
                : this.pos.entry.sub(exitPrice).mul(this.pos.qty);

        const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
        const netPnl = rawPnl.sub(fee);

        this.balance = this.balance.add(netPnl);
        this.dailyPnL = this.dailyPnL.add(netPnl);

        this.logger.logTrade(
            this.pos.entry,
            exitPrice,
            netPnl,
            reason,
            side,
            this.pos.strategy
        );
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

        this.logger.logPositionOpen(
            signal.action,
            this.pos.strategy,
            execPrice.toFixed(4),
            qty.toFixed(4)
        );
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN ---
class EnhancedGeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) {
            console.error('Missing GEMINI_API_KEY');
            process.exit(1);
        }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({
            model: config.gemini_model
        });
    }

    async analyze(ctx) {
        const wssBias = ctx.wss > 0 ? 'BULLISH' : ctx.wss < 0 ? 'BEARISH' : 'NEUTRAL';
        const actionThreshold = config.indicators.wss_weights.action_threshold ?? 2.0;

        const prompt = `
ACT AS: Institutional Scalping Algorithm.
OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD.

WSS Score: ${ctx.wss.toFixed(3)} (Bias: ${wssBias})
RULE: BUY requires WSS >= ${actionThreshold}. SELL requires WSS <= -${actionThreshold}.

MARKET CONTEXT:
- Price: ${ctx.price}
- Volatility (ATR): ${ctx.volatility.toFixed(4)}
- Regime: ${ctx.marketRegime}
- Trend (MTF  ${config.trend_interval}m): ${ctx.trend_mtf}
- ADX: ${ctx.adx.toFixed(2)}
- RSI: ${ctx.rsi.toFixed(2)}, StochK: ${ctx.stoch_k.toFixed(0)}, MACD Hist: ${ctx.macd_hist.toFixed(4)}
- VWAP: ${ctx.vwap.toFixed(2)}
- CCI: ${ctx.cci !== null ? ctx.cci.toFixed(2) : 'null'}
- Divergence: ${ctx.divergence ? ctx.divergence.type : 'None'}

RESPONSE FORMAT (JSON ONLY):
{
  "strategy_id": <1-5 or "HOLD">,
  "confidence": <0.0-1.0>,
  "action": "<BUY|SELL|HOLD>",
  "reason": "<short explanation>",
  "entry": <number|null>,
  "sl": <number|null>,
  "tp": <number|null>
}
        `.trim();

        try {
            const res = await this.model.generateContent(prompt);
            const response = await res.response;
            const text = response.text?.() ?? response.text;

            if (!text || typeof text !== 'string') {
                logger.warn('[AI WARN] Empty AI response');
                return {
                    strategy_id: 'HOLD',
                    confidence: 0,
                    action: 'HOLD',
                    reason: 'Empty AI response',
                    entry: null,
                    sl: null,
                    tp: null
                };
            }

            const start = text.indexOf('{');
            const end = text.lastIndexOf('}');
            if (start === -1 || end === -1) {
                logger.warn(`[AI WARN] Non-JSON AI response: ${text}`);
                return {
                    strategy_id: 'HOLD',
                    confidence: 0,
                    action: 'HOLD',
                    reason: 'Non-JSON AI response',
                    entry: null,
                    sl: null,
                    tp: null
                };
            }

            const jsonStr = text.slice(start, end + 1);
            const parsed = JSON.parse(jsonStr);

            if (!['BUY', 'SELL', 'HOLD'].includes(parsed.action)) parsed.action = 'HOLD';
            parsed.confidence =
                typeof parsed.confidence === 'number' ? parsed.confidence : 0;

            return parsed;
        } catch (e) {
            logger.error(`[AI ERROR] Gemini API Error: ${e.message}`);
            return {
                strategy_id: 'HOLD',
                confidence: 0,
                action: 'HOLD',
                reason: 'AI analysis failed',
                entry: null,
                sl: null,
                tp: null
            };
        }
    }
}

// --- Helper: calculate all indicators for latest bar using your config schema ---
function calculateIndicators(data, config) {
    const { price, candles, candlesMTF } = data;

    const closes = candles.map(c => c.c);
    const highs = candles.map(c => c.h);
    const lows = candles.map(c => c.l);
    const volumes = candles.map(c => c.v);

    const idx = closes.length - 1;

    const indCfg = config.indicators;

    // Core series
    const rsiArr = rsi(closes, indCfg.rsi);
    const { k: stochKArr, d: stochDArr } = stoch(
        highs,
        lows,
        closes,
        indCfg.stoch_period,
        indCfg.stoch_k,
        indCfg.stoch_d
    );
    const macdData = macd(
        closes,
        indCfg.macd_fast,
        indCfg.macd_slow,
        indCfg.macd_sig
    );
    const adxArr = adx(highs, lows, closes, indCfg.adx_period);
    const mfiArr = mfi(
        highs,
        lows,
        closes,
        volumes,
        indCfg.mfi
    );
    const atrArr = atr(highs, lows, closes, indCfg.atr_period);

    const chopArr = chop(highs, lows, closes, indCfg.chop_period);
    const cciArr = cci(highs, lows, closes, indCfg.cci_period);
    const lrArr = linReg(closes, indCfg.linreg_period);

    const bbArr = bollinger(
        closes,
        indCfg.bb_period,
        indCfg.bb_std
    );
    const kcArr = keltner(
        highs,
        lows,
        closes,
        indCfg.kc_period,
        indCfg.kc_mult,
        indCfg.atr_period
    );
    const stArr = superTrend(
        highs,
        lows,
        closes,
        indCfg.atr_period,
        indCfg.st_factor
    );
    const ceArr = chandelierExit(
        highs,
        lows,
        closes,
        indCfg.ce_period,
        indCfg.ce_mult
    );
    const vwapArr = vwap(highs, lows, closes, volumes);

    const fvgArr = findFVG(highs, lows);

    // Use MFI period as a proxy HV period if you want HV; else skip
    const hvPeriod = indCfg.mfi;
    const hvArr = historicalVolatility(closes, hvPeriod);

    // Fib pivots and SR using full history; no explicit period in config
    const fibsArr = fibPivots(highs, lows, closes);
    const fibSR = getFibonacciPivotsAsSR(fibsArr);
    const hlSR = getHistoricalHighLowSR(highs, lows, indCfg.bb_period); // use bb_period as generic window
    const combinedSR = combineAndFilterSR(fibSR, hlSR);

    const divArr = detectDivergence(
        closes,
        macdData.macd,
        indCfg.linreg_period // reuse linreg period as lookback
    );

    const regimeArr = marketRegime(
        adxArr,
        hvArr,
        25,     // default ADX threshold
        0.01    // default vol threshold
    );

    const estcArr = ehlersSuperTrendCross(closes);

    // Adapt your wss_weights into calculateWSS config
    const wssSignals = calculateWSS(
        closes,
        highs,
        lows,
        volumes,
        {
            indicators: {
                rsi: {
                    period: indCfg.rsi,
                    overbought: 70,
                    oversold: 30
                },
                macd: {
                    fastPeriod: indCfg.macd_fast,
                    slowPeriod: indCfg.macd_slow,
                    signalPeriod: indCfg.macd_sig
                },
                smaCrossover: {
                    fastPeriod: indCfg.rsi,      // arbitrary: use rsi period
                    slowPeriod: indCfg.bb_period // arbitrary: use bb period
                }
            },
            weights: {
                rsi: indCfg.wss_weights.momentum_normalized_weight ?? 1,
                macd: indCfg.wss_weights.macd_weight ?? 1,
                smaCrossover: indCfg.wss_weights.trend_scalp_weight ?? 1
            },
            thresholds: {
                buy: indCfg.wss_weights.action_threshold ?? 2.0,
                sell: -(indCfg.wss_weights.action_threshold ?? 2.0)
            }
        }
    );

    return {
        price,
        rsi: safeArr(rsiArr, idx) ?? 50,
        stoch_k: safeArr(stochKArr, idx) ?? 50,
        stoch_d: safeArr(stochDArr, idx) ?? 50,
        macd: safeArr(macdData.macd, idx) ?? 0,
        macd_signal: safeArr(macdData.signal, idx) ?? 0,
        macd_hist: safeArr(macdData.hist, idx) ?? 0,
        adx: safeArr(adxArr, idx) ?? 0,
        mfi: safeArr(mfiArr, idx) ?? 50,
        volatility: safeArr(atrArr, idx) ?? 0,
        chop: safeArr(chopArr, idx),
        cci: safeArr(cciArr, idx),
        vwap: safeArr(vwapArr, idx) ?? price,
        fvg: safeArr(fvgArr, idx),
        divergence: safeArr(divArr, idx),
        fibs: safeArr(fibsArr, idx) || {},
        sr_levels: safeArr(combinedSR, idx) || [],
        marketRegime: safeArr(regimeArr, idx) || 'Unknown',
        wss: safeArr(wssSignals, idx) ?? 0,
        estc: safeArr(estcArr, idx) ?? 0,
        trend_angle: safeArr(lrArr, idx) ?? null,
        trend_mtf:
            candlesMTF.length >= 2
                ? (candlesMTF[candlesMTF.length - 1].c >
                  candlesMTF[0].c
                      ? 'Up'
                      : 'Down')
                : 'Flat'
    };
}

// --- 🚀 MAIN TRADING ENGINE ---
async function main() {
    const dataProvider = new EnhancedDataProvider();
    const exchange = new EnhancedPaperExchange(logger);
    const aiBrain = new EnhancedGeminiBrain();
    let lastSignal = { action: 'HOLD', strategy_id: 'HOLD' };

    logger.info('🚀 Starting Trading Engine...');

    while (true) {
        const data = await dataProvider.fetchAll();
        if (!data) {
            await sleep(config.loop_delay * 1000);
            continue;
        }

        const indicators = calculateIndicators(data, config);
        const signal = await aiBrain.analyze(indicators);

        const actionAllowed =
            signal.action !== 'HOLD' &&
            signal.confidence >= config.min_confidence;

        if (actionAllowed) {
            if (
                signal.action !== lastSignal.action ||
                signal.strategy_id !== lastSignal.strategy_id
            ) {
                logger.logSignal(
                    signal.strategy_id,
                    signal.confidence,
                    signal.action,
                    signal.reason,
                    signal.entry,
                    signal.sl,
                    signal.tp
                );
                lastSignal = {
                    action: signal.action,
                    strategy_id: signal.strategy_id
                };
            }

            const entry =
                typeof signal.entry === 'number' ? signal.entry : data.price;
            const sl = typeof signal.sl === 'number' ? signal.sl : data.price;
            const tp = typeof signal.tp === 'number' ? signal.tp : data.price;

            exchange.evaluateSignal(data.price, {
                ...signal,
                entry,
                sl,
                tp,
                strategy: `AI_${signal.strategy_id}`
            });
        } else {
            if (lastSignal.action !== 'HOLD') {
                logger.info(
                    'Signal expired or confidence too low. Holding / closing if needed.'
                );
                lastSignal = { action: 'HOLD', strategy_id: 'HOLD' };
            }
            exchange.maybeCloseForRisk(new Decimal(data.price));
        }

        // Always check SL/TP each loop
        exchange.checkSLTP(new Decimal(data.price));

        await sleep(config.loop_delay * 1000);
    }
}

// --- Entry Point ---
main().catch(error => {
    logger.error(`[ENGINE CRASH] Unhandled error: ${error.message}`, error);
    process.exit(1);
});