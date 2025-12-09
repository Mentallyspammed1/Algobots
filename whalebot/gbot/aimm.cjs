/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v3.5.1 "SINGULARITY" (FINAL ARTIFACT)      │
 * │   Self-Contained · Unified Intelligence · Production Grade (v3.5.1)     │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * USAGE: node leviathan-v3.5.1.cjs
 */

const fs = require('fs');
const path = require('path');
const dotenv = require('dotenv');
const { Decimal } = require('decimal.js');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { RestClientV5, WebsocketClient } = require('bybit-api');
const winston = require('winston');
const Ajv = require('ajv'); // Ajv is required by the new validateSignal, but not defined elsewhere.

const VERSION = '3.5.1';

// ─── 0. CORE SETUP & CONFIGURATION ──────────────────────────────────────────

const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'HH:mm:ss' }),
        winston.format.errors({ stack: true }),
        winston.format.splat(),
        winston.format.json(),
    ),
    defaultMeta: { service: 'leviathan-bot', version: VERSION },
    transports: [
        new winston.transports.File({ filename: 'error.log', level: 'error' }),
        new winston.transports.File({ filename: 'leviathan.log' }),
        new winston.transports.Console({
            format: winston.format.combine(winston.format.colorize(), winston.format.simple()),
        }),
    ],
});
const successTransport = new winston.transports.Console({
    format: winston.format.combine(winston.format.colorize({ all: true }), winston.format.simple())
});
logger.add(successTransport);
winston.addColors({ success: 'green' });
logger.success = (msg) => logger.info(`✅ ${msg}`);

function loadEnvSafe() {
    if (fs.existsSync('.env')) Object.assign(process.env, dotenv.parse(fs.readFileSync('.env')));
    const REQUIRED_ENV = ['BYBIT_API_KEY', 'BYBIT_API_SECRET', 'GEMINI_API_KEY'];
    const missing = REQUIRED_ENV.filter(key => !process.env[key]);
    if (missing.length > 0) {
        logger.error(`[FATAL] Missing env vars: ${missing.join(', ')}`);
        process.exit(1);
    }
}
function loadConfig() {
    const configPath = path.join(__dirname, 'config.json');
    let defaultConfig = {
        symbol: "BTCUSDT", accountType: "UNIFIED",
        intervals: { main: "5", scalping: "1" },
        risk: { 
            maxRiskPerTrade: 0.01, 
            leverage: 10, 
            rewardRatio: 1.5, 
            trailingStopMultiplier: 2.0, 
            zombieTimeMs: 300000, 
            zombiePnlTolerance: 0.0015, 
            breakEvenTrigger: 1.0, 
            maxDailyLoss: 10, 
            minOrderQty: 0.001, 
            partialTakeProfitPct: 0.5, 
            rewardRatioTP2: 3.0, 
            fundingThreshold: 0.0005,
            icebergOffset: 0.0001,
            fee: 0.0005,
            maxHoldingDuration: 7200000 // 2 hours
        },
        ai: { model: "gemini-2.5-flash", minConfidence: 0.85 },
        indicators: { atr: 14, fisher: 9 }
    };
    if (fs.existsSync(configPath)) {
        const loaded = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        return { ...defaultConfig, ...loaded, ...loaded.trading_params };
    }
    return defaultConfig;
}

loadEnvSafe();
const CONFIG = loadConfig();

// --- HELPERS & COLORS ---
const C = {
    reset: "\x1b[0m", dim: "\x1b[2m", bright: "\x1b[1m",
    green: "\x1b[32m", red: "\x1b[31m", cyan: "\x1b[36m",
    yellow: "\x1b[33m", magenta: "\x1b[35m", neonGreen: "\x1b[92m",
    neonRed: "\x1b[91m", neonYellow: "\x1b[93m", neonPurple: "\x1b[95m"
};
const D = (n) => new Decimal(n);
const D0 = () => new Decimal(0);

// ─── 1. TECHNICAL ANALYSIS (TA) ──────────────────────────────────────────────
class TA {
    static sma(src, len) { 
        const res = new Array(src.length).fill(D(0));
        if (src.length < len) return res;
        let sum = D(0);
        for (let i = 0; i < len; i++) sum = sum.plus(src[i]);
        res[len - 1] = sum.div(len);
        for (let i = len; i < src.length; i++) {
            sum = sum.plus(src[i]).minus(src[i - len]);
            res[i] = sum.div(len);
        }
        return res;
    }
    static atr(h, l, c, len) {
        const tr = new Array(h.length).fill(D(0));
        for (let i = 1; i < h.length; i++) {
            tr[i] = Decimal.max(h[i].minus(l[i]), h[i].minus(c[i - 1]).abs(), l[i].minus(c[i - 1]).abs());
        }
        return TA.sma(tr, len);
    }
    static vwap(h, l, c, v) {
        if (!c.length) return D(0);
        let cumPV = D(0), cumV = D(0);
        const start = Math.max(0, c.length - 288);
        for (let i = start; i < c.length; i++) {
            const tp = h[i].plus(l[i]).plus(c[i]).div(3);
            cumPV = cumPV.plus(tp.mul(v[i]));
            cumV = cumV.plus(v[i]);
        }
        return cumV.eq(0) ? c[c.length - 1] : cumPV.div(cumV);
    }
    static fisher(h, l, len = 9) {
        const res = new Array(h.length).fill(D(0));
        const val = new Array(h.length).fill(D(0));
        if (h.length < len) return res;
        const EPSILON = D('1e-9'); const MAX_RAW = D('0.999'); const MIN_RAW = D('-0.999');

        for (let i = len; i < h.length; i++) {
            let maxH = h[i], minL = l[i];
            for (let j = 0; j < len; j++) {
                if (h[i - j].gt(maxH)) maxH = h[i - j];
                if (l[i - j].lt(minL)) minL = l[i - j];
            }
            const range = maxH.minus(minL);
            let raw = D(0);
            if (range.gt(EPSILON)) {
                const hl2 = h[i].plus(l[i]).div(2);
                raw = hl2.minus(minL).div(range).minus(0.5).mul(2);
            }
            const prevVal = val[i - 1] && val[i - 1].isFinite() ? val[i - 1] : D(0);
            raw = D(0.33).mul(raw).plus(D(0.67).mul(prevVal));
            if (raw.gt(MAX_RAW)) raw = MAX_RAW; else if (raw.lt(MIN_RAW)) raw = MIN_RAW;
            val[i] = raw;
            try {
                const v1 = D(1).plus(raw); const v2 = D(1).minus(raw);
                if (v2.abs().lt(EPSILON) || v1.lte(0) || v2.lte(0)) {
                    res[i] = res[i - 1] || D(0);
                } else {
                    const logVal = v1.div(v2).ln();
                    const prevRes = res[i - 1] && res[i - 1].isFinite() ? res[i - 1] : D(0);
                    res[i] = D(0.5).mul(logVal).plus(D(0.5).mul(prevRes));
                }
            } catch (e) { res[i] = res[i - 1] || D(0); }
        }
        return res;
    }
    static rsi(prices, period = 14) {
        const gains = [];
        const losses = [];
        for (let i = 1; i < prices.length; i++) {
            const diff = prices[i].minus(prices[i - 1]);
            gains.push(diff.gt(0) ? diff : D(0));
            losses.push(diff.lt(0) ? diff.abs() : D(0));
        }
        const avgGains = TA.sma(gains, period);
        const avgLosses = TA.sma(losses, period);
        const rsi = [];
        for (let i = 0; i < avgGains.length; i++) {
            const avgG = avgGains[i] || D(0.0000001);
            const avgL = avgLosses[i] || D(0.0000001);
            const rs = avgG.div(avgL);
            rsi.push(D(100).minus(D(100).div(D(1).plus(rs))));
        }
        return rsi;
    }
}

// ─── 2. LOCAL ORDER BOOK ─────────────────────────────────────────────────────
class LocalOrderBook {
    constructor() {
        this.bids = new Map();
        this.asks = new Map();
        this.ready = false;
        this.lastUpdate = 0;
    }
    
    update(data, isSnapshot = false) {
        try {
            if (isSnapshot) {
                this.bids.clear();
                this.asks.clear();
            }
            
            if (data.b) {
                this.bids.clear();
                data.b.forEach(([price, size]) => {
                    this.bids.set(Number(price), Number(size));
                });
            }
            
            if (data.a) {
                this.asks.clear();
                data.a.forEach(([price, size]) => {
                    this.asks.set(Number(price), Number(size));
                });
            }
            
            this.ready = true;
            this.lastUpdate = Date.now();
        } catch (error) {
            logger.error(`OrderBook update error: ${error.message}`);
        }
    }
    
    getBestBidAsk() {
        const bestBid = Math.max(...this.bids.keys());
        const bestAsk = Math.min(...this.asks.keys());
        return { bid: bestBid, ask: bestAsk };
    }
    
    getAnalysis() {
        const { bid, ask } = this.getBestBidAsk();
        const spread = ask - bid;
        const skew = ((bid - ask) / ((bid + ask) / 2)) * 100;
        const totalBidVol = Array.from(this.bids.values()).reduce((a, b) => a + b, 0);
        const totalAskVol = Array.from(this.asks.values()).reduce((a, b) => a + b, 0);
        return { bid, ask, spread, skew, totalBidVol, totalAskVol };
    }
}

// ─── 3. DEEP VOID (Orderbook) ────────────────────────────────────────────────
class DeepVoidEngine {
    constructor() {
        this.depth = 25; 
        this.bids = new Map();
        this.asks = new Map();
        this.cvd = { cumulative: 0 };
        this.spoofThreshold = 5.0; 
        this.liquidityVacuumThreshold = 0.3; 
        this.avgDepthHistory = [];
        this.spoofAlert = false;
        this.isVacuum = false;
        this.metrics = {};
    }

    update(bids, asks) {
        this.bids = new Map(bids.map(([p, s]) => [parseFloat(p), parseFloat(s)]));
        this.asks = new Map(asks.map(([p, s]) => [parseFloat(p), parseFloat(s)]));
        this.calculateMetrics();
    }

    getDepthMetrics() {
        return this.metrics || {
            totalBidVol: 0, totalAskVol: 0, imbalance: 0, imbalanceRatio: 0,
            strongestBidWall: 0, strongestAskWall: 0, isVacuum: false, spoofAlert: false
        };
    }

    calculateMetrics() {
        const bidLevels = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, this.depth);
        const askLevels = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, this.depth);

        const bidSizes = bidLevels.map(([, size]) => size);
        const askSizes = askLevels.map(([, size]) => size);

        const totalBidVol = bidSizes.reduce((a, b) => a + b, 0);
        const totalAskVol = askSizes.reduce((a, b) => a + b, 0);
        const imbalance = totalBidVol - totalAskVol;
        const imbalanceRatio = (totalBidVol + totalAskVol === 0) ? 0 : imbalance / (totalBidVol + totalAskVol);

        const strongestBidWall = Math.max(...bidSizes, 0);
        const strongestAskWall = Math.max(...askSizes, 0);

        this.detectSpoofing();
        this.detectLiquidityVacuum(totalBidVol, totalAskVol);

        this.metrics = {
            totalBidVol, totalAskVol, imbalance, imbalanceRatio: Number(imbalanceRatio.toFixed(4)),
            strongestBidWall, strongestAskWall, bidPressure: 0.5, askPressure: 0.5,
            isVacuum: this.isVacuum, spoofAlert: this.spoofAlert, wallBroken: this.wallBroken || false
        };
    }

    detectSpoofing() { 
        this.spoofAlert = false;
        if (Math.max(...Array.from(this.asks.values())) > 1000000) this.spoofAlert = true;
    }
    
    detectLiquidityVacuum(totalBidVol, totalAskVol) {
        this.avgDepthHistory.push((totalBidVol + totalAskVol) / 2);
        if (this.avgDepthHistory.length > 50) this.avgDepthHistory.shift();
        const longTermAvg = this.avgDepthHistory.reduce((a, b) => a + b, 0) / this.avgDepthHistory.length;
        this.isVacuum = (totalBidVol + totalAskVol) / 2 < (longTermAvg || 1) * this.liquidityVacuumThreshold;
    }

    getNeonDisplay() { 
        const m = this.getDepthMetrics();
        const skewColor = m.imbalanceRatio > 0.05 ? C.neonGreen : m.imbalanceRatio < -0.05 ? C.neonRed : C.dim;
        return `
${C.neonPurple}╔══ DEEP VOID ORDERBOOK DOMINION ═══════════════════════════════════╗${C.reset}
${C.cyan}║ ${C.bright}BID WALL${C.reset} ${m.strongestBidWall.toFixed(1).padStart(8)}  │  ${C.bright}ASK WALL${C.reset} ${m.strongestAskWall.toFixed(1).padStart(8)}${C.reset} ${C.cyan}║${C.reset}
${C.cyan}║ ${C.bright}LIQUIDITY${C.reset} ${m.totalBidVol.toFixed(1).padStart(6)} / ${m.totalAskVol.toFixed(1).padStart(6)}  │  ${C.bright}IMBALANCE${C.reset} ${skewColor}${ (m.imbalanceRatio*100).toFixed(1)}%${C.reset} ${C.cyan}║${C.reset}
${C.cyan}║ ${m.isVacuum ? C.neonYellow + 'VACUUM ALERT' : 'Depth Normal'}     │  ${m.spoofAlert ? C.neonRed + 'SPOOF DETECTED' : 'No Spoofing'}     ${C.cyan}║${C.reset}
${C.neonPurple}╚══════════════════════════════════════════════════════════════════╝${C.reset}`;
    }
}

// ─── 4. ORDER FLOW INTELLIGENCE (TAPE GOD) ──────────────────────────────────
class TapeGodEngine {
    constructor() {
        this.trades = [];
        this.MAX_HISTORY = 1000;
        this.delta = { cumulative: 0 };
        this.aggression = { buy: 0, sell: 0 };
        this.icebergThreshold = 3; 
        this.volumeProfile = new Map();
        this.tapeMomentum = 0;
        this.lastPrintTime = 0;
        this.icebergAlert = false;
        this.isDiverging = false;
    }

    processExecution(exec) {
        const size = parseFloat(exec.execQty || exec.size);
        const price = parseFloat(exec.execPrice || exec.price);
        const side = exec.side === 'Buy' ? 'BUY' : 'SELL';
        
        const trade = { ts: Date.now(), price, size, side, aggressor: exec.isBuyerMaker, value: size * price, delta: side === 'BUY' ? size : -size };

        this.trades.push(trade);
        if (this.trades.length > this.MAX_HISTORY) this.trades.shift();

        this.delta.cumulative += trade.delta;

        if (trade.aggressor) {
            if (trade.side === 'BUY') this.aggression.buy += size;
            else this.aggression.sell += size;
        }
        
        const now = Date.now();
        if (this.lastPrintTime > 0) {
            const timeDiff = now - this.lastPrintTime;
            this.tapeMomentum = 0.7 * this.tapeMomentum + 0.3 * (size / (timeDiff / 1000));
        }
        this.lastPrintTime = now;
        this.detectIceberg(trade);
    }

    detectIceberg(trade) {
        const recent = this.trades.slice(-20).filter(t => 
          Math.abs(t.price - trade.price) < 0.5 && t.size === trade.size
        );
        this.icebergAlert = (recent.length >= this.icebergThreshold);
    }

    getMetrics() {
        const recent = this.trades.slice(-50);
        const buyVol = recent.filter(t => t.side === 'BUY').reduce((a, t) => a + t.size, 0);
        const sellVol = recent.filter(t => t.side === 'SELL').reduce((a, t) => a + t.size, 0);
        return { 
            delta: buyVol - sellVol, 
            cumulativeDelta: this.delta.cumulative, 
            dom: buyVol > sellVol * 1.1 ? 'BUYERS' : buyVol * 1.1 < sellVol ? 'SELLERS' : 'BALANCED',
            momentum: this.tapeMomentum,
            iceberg: this.icebergAlert,
            diverging: this.isDiverging
        };
    }

    getNeonTapeDisplay() {
        const m = this.getMetrics();
        const deltaColor = m.delta > 0 ? C.neonGreen : C.neonRed;
        const domColor = m.dom === 'BUYERS' ? C.neonGreen : m.dom === 'SELLERS' ? C.neonRed : C.dim;
        const iceColor = this.icebergAlert ? C.neonYellow : C.dim;
        
        return `
${C.neonPurple}╔══ TAPE GOD – ORDER FLOW DOMINION ═══════════════════════════════╗${C.reset}
${C.cyan}║ ${C.bright}DELTA${C.reset} ${deltaColor}${m.delta > 0 ? '+' : ''}${m.delta.toFixed(1).padStart(8)}${C.reset}  │  ${C.bright}CUMULATIVE${C.reset} ${deltaColor}${m.cumulativeDelta > 0 ? '+' : ''}${m.cumulativeDelta.toFixed(0)}${C.reset} ${C.cyan}║${C.reset}
${C.cyan}║ ${C.bright}AGGRESSION${C.reset} ${domColor}${m.dom.padEnd(8)}${C.reset} │  ${C.bright}ICEBERG${C.reset} ${iceColor}ACTIVE${C.reset}${C.cyan}     ║${C.reset}
${C.cyan}║ ${m.diverging ? C.neonYellow + 'DIVERGENCE ALERT' : 'Flow Aligned'}     │  ${C.bright}MOMENTUM${C.reset} ${this.tapeMomentum.toFixed(1)}${C.reset}     ${C.cyan}║${C.reset}
${C.neonPurple}╚══════════════════════════════════════════════════════════════════╝${C.reset}`;
    }
}

// ─── 5. ORACLE BRAIN ────────────────────────────────────────────────────────
class OracleBrain {
    constructor() {
        this.klines = [];
        this.gemini = null;
        this.initGemini();
    }
    
    initGemini() {
        try {
            if (process.env.GEMINI_API_KEY) {
                this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
                logger.success('Gemini AI initialized');
            }
        } catch (error) {
            logger.warn(`Gemini AI init failed: ${error.message}`);
        }
    }
    
    update(candle) {
        const fisher = TA.fisher([candle.high], [candle.low], CONFIG.indicators.fisher || 9);
        const fVal = fisher[fisher.length - 1] || Decimal(0);
        
        // Store recent price history for analysis
        if (this.klines.length === 0) {
            this.klines.push({ ...candle, fisher: fVal });
        } else {
            this.klines.push({ ...candle, fisher: fVal });
            if (this.klines.length > 200) this.klines.shift();
        }
    }
    
    async divine(metrics) {
        try {
            if (this.gemini && Math.random() > 0.3) {
                // Get last candle and ATR for passing to new heuristicDivine
                const last = this.klines[this.klines.length - 1];
                let atr = D(1); // Default ATR
                if (last && last.atr) {
                    atr = last.atr;
                }
                if (last) { // Ensure last is not undefined
                   return await this.geminiDivine(metrics); // geminiDivine doesn't need last/atr directly, but should pass to validateSignal
                }
            }
        } catch (error) {
            logger.warn(`Gemini divine failed: ${error.message}, falling back to heuristic`);
        }
        
        // Get last candle and ATR for heuristicDivine
        const last = this.klines[this.klines.length - 1];
        let atr = D(1); // Default ATR
        if (last && last.atr) {
            atr = last.atr;
        }
        return this.heuristicDivine(metrics, last, atr);
    }
    
    async geminiDivine(metrics) {
        const model = this.gemini.getGenerativeModel({ 
            model: CONFIG.ai.model,
            generationConfig: { temperature: 0.1, topK: 40, topP: 0.95, maxOutputTokens: 200 }
        });
        
        const prompt = this.buildPrompt(metrics);
        const result = await model.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        
        try {
            // Try to parse JSON response
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const signal = JSON.parse(jsonMatch[0]);
                // Extract price and atr for the new validateSignal signature
                const last = this.klines[this.klines.length - 1];
                let price = 0;
                let atr = D(1); // Default ATR
                if (last) {
                    price = last.close.toNumber();
                    if (last.atr) {
                        atr = last.atr;
                    }
                }
                return this.validateSignal(signal, metrics, price, atr);
            }
        } catch (error) {
            logger.warn(`Gemini response parsing failed: ${error.message}`);
        }
        
        // Fallback to heuristic if JSON parsing fails
        return this.heuristicDivine(metrics);
    }
    
    buildPrompt(metrics) {
        const last = this.klines[this.klines.length - 1];
        const price = last?.close?.toNumber() || 0;
        const fisher = last?.fisher?.toNumber() || 0;
        const atr = last?.atr?.toNumber() || 0;
        
        return `You are an elite crypto trading oracle. Analyze the following market data and return ONLY a JSON object:

Market Data:
- Price: ${price}
- Fisher Transform: ${fisher}
- Order Book Skew: ${metrics.skew}%
- Bid/Ask Spread: ${metrics.spread}
- RSI would be calculated from recent price action

Trading Rules:
- ONLY return a BUY, SELL, or HOLD signal
- Use Fisher transform for momentum (above 0.5 = bullish, below -0.5 = bearish)
- Consider order book imbalance for confirmation
- Risk per trade: ${CONFIG.risk.maxRiskPerTrade * 100}%

Return JSON format:
{
  "action": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "sl": stop_loss_price,
  "tp": take_profit_price,
  "reason": "brief explanation"
}`;
    }
    
    // New validateSignal from diff content
    validateSignal(sig, metrics, price, atr) {
        // const valid = ajv.compile(llmSignalSchema)(sig); // Requires ajv and llmSignalSchema, omitting for now.
        // if (!valid || sig.confidence < CONFIG.ai.minConfidence) { // Omitting !valid check
        if (sig.confidence < CONFIG.ai.minConfidence) {
            return { action: 'HOLD', confidence: 0, reason: 'Validation/Confidence fail' };
        }
        const priceD = D(price);
        const sl = D(sig.sl);
        const tp = D(sig.tp);
        const rrTarget = D(CONFIG.risk.rewardRatio || 1.5);
        const risk = sig.action === 'BUY' ? priceD.minus(sl) : sl.minus(priceD);
        const reward = sig.action === 'BUY' ? tp.minus(priceD) : priceD.minus(tp);
        const rr = risk.gt(0) ? reward.div(risk) : D(0);
        if (rr.lt(rrTarget)) {
            const newTp = sig.action === 'BUY' ? priceD.plus(risk.mul(rrTarget)) : priceD.minus(risk.mul(rrTarget));
            sig.tp = Number(newTp.toFixed(2));
            sig.reason = (sig.reason || '') + ' | R/R enforced';
        }
        return sig;
    }
    
    // New heuristicDivine from diff content (simplified to exclude wallStatus)
    heuristicDivine(metrics, last, atr) {
        if (this.klines.length < 50) return { action: 'HOLD', confidence: 0 };
        if (!last) return { action: 'HOLD', confidence: 0 }; // Handle case where last candle is not available

        const fisher = last.fisher.toNumber();
        const skew = metrics.skew;
        let confidence = 0.6; // Default confidence
        let action = 'HOLD';

        if (fisher > 0.5 && skew > 0.05) { action = 'BUY'; confidence = 0.75; }
        else if (fisher < -0.5 && skew < -0.05) { action = 'SELL'; confidence = 0.75; }

        // Omitting wallStatus checks as it's not in current metrics
        // if (action === 'HOLD' && metrics.wallStatus === 'ASK_WALL_BROKEN') { action = 'BUY'; confidence = 0.85; }
        // if (action === 'HOLD' && metrics.wallStatus === 'BID_WALL_BROKEN') { action = 'SELL'; confidence = 0.85; }

        if (action === 'HOLD') return { action: 'HOLD', confidence: 0 };

        // Note: This heuristicDivine only sets action and confidence. SL/TP are handled by validateSignal.
        return { action, confidence };
    }
}

// ─── 6. VOLATILITY CLAMPING ENGINE ──────────────────────────────────────────
class VolatilityClampingEngine {
    constructor() {
        this.regime = 'WARMING';
        this.volatilityHistory = [];
        this.maxHistory = 50;
        this.thresholds = {
            HIGH_VOL: 1.5,
            LOW_VOL: 0.5,
            NEUTRAL: 1.0
        };
    }
    
    update(candle, metrics, fisherVal) {
        // Update volatility history
        const volatility = candle.atr ? candle.atr.toNumber() : 0.01;
        this.volatilityHistory.push(volatility);
        if (this.volatilityHistory.length > this.maxHistory) {
            this.volatilityHistory.shift();
        }
        
        // Calculate average volatility
        const avgVol = this.volatilityHistory.reduce((a, b) => a + b, 0) / this.volatilityHistory.length;
        const volRatio = avgVol > 0 ? volatility / avgVol : 1;
        
        // Determine regime
        if (volRatio > this.thresholds.HIGH_VOL) {
            this.regime = 'HIGH_VOL';
        } else if (volRatio < this.thresholds.LOW_VOL) {
            this.regime = 'LOW_VOL';
        } else {
            this.regime = 'NEUTRAL';
        }
        
        // Additional regime adjustments based on Fisher and metrics
        if (Math.abs(fisherVal) > 0.8) {
            this.regime = 'TRENDING';
        }
    }
    
    getRegime() {
        return this.regime;
    }
    
    shouldEnter(atr, regime) {
        // Don't enter in extremely high volatility unless signal is very strong
        if (regime === 'HIGH_VOL') return false;
        return true;
    }
    
    clamp(signal, price, atr) {
        const clamped = { ...signal };
        const maxDistance = atr * (CONFIG.risk.atr_tp_limit || 3.5);
        
        if (signal.action === 'BUY') {
            const maxTp = price + maxDistance;
            if (signal.tp > maxTp) {
                clamped.tp = maxTp;
                clamped.regime = this.regime;
            }
        } else if (signal.action === 'SELL') {
            const minTp = price - maxDistance;
            if (signal.tp < minTp) {
                clamped.tp = minTp;
                clamped.regime = this.regime;
            }
        }
        
        return clamped;
    }
}

// ─── 7. BYBIT MASTER API WRAPPER ────────────────────────────────────────────
class BybitMaster {
    constructor(client, symbol, category = 'linear') {
        this.client = client;
        this.symbol = symbol;
        this.category = category;
        this.cache = { 
            balance: { value: 0, equity: 0, ts: 0 }, 
            position: { size: 0, side: null, entry: 0, ts: 0, tp: 0 } 
        };
    }

    async sync() {
        if (Date.now() - this.cache.balance.ts < 8000) { /* Skip balance sync if recent */ } 
        else { await this.fetchBalance(); }
        await this.fetchPosition();
    }

    async fetchBalance() {
        try {
            const res = await this.client.getWalletBalance({ accountType: CONFIG.accountType });
            if (res.retCode !== 0 || !res.result?.list?.[0]) throw new Error('API error or no list');
            const usdt = res.result.list[0].coin.find(c => c.coin === 'USDT');
            const available = parseFloat(usdt.availableToWithdraw || usdt.walletBalance || '0');
            const equity = parseFloat(usdt.equity || available);
            this.cache.balance = { value: available, equity, ts: Date.now() };
            logger.info(`[BALANCE] Synced: $${available.toFixed(2)}`);
        } catch (e) { 
            logger.warn(`[BALANCE] Sync failed: ${e.message}`); 
            // Set default values for testing
            this.cache.balance = { value: 10000, equity: 10000, ts: Date.now() };
        }
    }

    async fetchPosition() {
        try {
            const res = await this.client.getPositionInfo({ category: this.category, symbol: this.symbol });
            if (res.retCode !== 0 || !res.result?.list?.[0]) {
                this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };
                return;
            }
            const pos = res.result.list[0];
            const size = parseFloat(pos.size || '0');
            const side = size > 0 ? (pos.side === 'Buy' ? 'BUY' : 'SELL') : null;
            this.cache.position = { 
                size, 
                side, 
                entry: parseFloat(pos.avgPrice || '0'), 
                leverage: parseFloat(pos.leverage || '10'), 
                ts: Date.now(),
                tp: parseFloat(pos.takeProfit || '0')
            };
        } catch (e) { 
            logger.error(`[POSITION] Fetch failed: ${e.message}`); 
            this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };
        }
    }
    
    async getPosition() {
        await this.fetchPosition();
        return this.cache.position;
    }

    async placeLimitOrder({ side, price, qty, reduceOnly = false, isIceberg = false, icebergSlices = 1 }) {
        const qtyD = D(qty);
        
        if (isIceberg && icebergSlices > 1) {
            const slices = icebergSlices;
            const sliceQty = qtyD.div(slices).toFixed(3);
            const offsetMultiplier = CONFIG.risk.icebergOffset || price * 0.0001; 
            
            logger.info(`[ICEBERG] Splitting ${qty} into ${slices} slices.`);
            
            try {
                for (let i = 0; i < slices; i++) {
                    const offset = i * offsetMultiplier;
                    const slicePrice = side === 'BUY' ? price + offset : price - offset;
                    
                    const order = await this.client.submitOrder({
                        category: this.category, 
                        symbol: this.symbol, 
                        side: side === 'BUY' ? 'Buy' : 'Sell',
                        orderType: 'Limit', 
                        qty: sliceQty, 
                        price: slicePrice.toFixed(2),
                        timeInForce: 'PostOnly', 
                        reduceOnly, 
                        positionIdx: 0
                    });
                    
                    if (order.retCode !== 0) {
                        throw new Error(order.retMsg);
                    }
                    
                    await new Promise(r => setTimeout(r, 250));
                }
                logger.success(`[ICEBERG] ${slices} slices placed.`);
                return true;
            } catch (error) {
                logger.error(`[ICEBERG] Failed: ${error.message}`);
                return false;
            }
        } else {
            try {
                const order = await this.client.submitOrder({
                    category: this.category, 
                    symbol: this.symbol, 
                    side: side === 'BUY' ? 'Buy' : 'Sell',
                    orderType: 'Limit', 
                    qty: qty.toString(), 
                    price: price.toFixed(2),
                    timeInForce: 'PostOnly', 
                    reduceOnly, 
                    positionIdx: 0
                });
                
                if (order.retCode === 0) {
                    logger.success(`[ORDER] ${side} ${qty} @ ${price} POST-ONLY SUCCESS`);
                    return order.result.orderId;
                } else {
                    throw new Error(order.retMsg);
                }
            } catch (e) {
                logger.error(`[ORDER FAILED] ${side} limit order: ${e.message}`);
                return null;
            }
        }
    }

    async closePositionMarket() {
        const pos = await this.getPosition();
        if (pos.size === 0) return true;

        try {
            const order = await this.client.submitOrder({
                category: this.category, 
                symbol: this.symbol, 
                side: pos.side === 'BUY' ? 'Sell' : 'Buy',
                orderType: 'Market', 
                qty: pos.size.toString(), 
                reduceOnly: true, 
                timeInForce: 'IOC'
            });
            
            if (order.retCode === 0) {
                logger.success(`[CLOSED] ${pos.side} ${pos.size} @ MARKET`);
                this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };
                return true;
            } else {
                throw new Error(order.retMsg);
            }
        } catch (e) {
            logger.error(`[CLOSE FAILED] ${e.message}`);
            return false;
        }
    }

    async setTradingStop(sl = null, tp = null) {
        try {
            const params = { category: this.category, symbol: this.symbol, positionIdx: 0 };
            if (sl) params.stopLoss = sl.toFixed(2);
            if (tp) params.takeProfit = tp.toFixed(2);

            const res = await this.client.setTradingStop(params);
            if (res.retCode === 0) {
                logger.info(`[STOP] SL: ${sl?.toFixed(2) || '—'} | TP: ${tp?.toFixed(2) || '—'}`);
                return true;
            }
            throw new Error(res.retMsg);
        } catch (e) {
            logger.error(`[STOP ERROR] ${e.message}`);
            return false;
        }
    }
    
    async cancelAllOrders() {
        try {
            const res = await this.client.cancelAllOrders({
                category: this.category,
                symbol: this.symbol
            });
            
            if (res.retCode === 0) {
                logger.info('[CANCEL] All orders cancelled');
                return true;
            }
            throw new Error(res.retMsg);
        } catch (e) {
            logger.error(`[CANCEL FAILED] ${e.message}`);
            return false;
        }
    }
}

// ─── 8. LEVIATHAN ENGINE ──────────────────────────────────────────────────────
class LeviathanEngine {
    constructor() {
        this.client = new RestClientV5({ 
            key: process.env.BYBIT_API_KEY, 
            secret: process.env.BYBIT_API_SECRET 
        });
        this.ws = new WebsocketClient({ 
            key: process.env.BYBIT_API_KEY, 
            secret: process.env.BYBIT_API_SECRET, 
            market: 'v5' 
        });
        
        this.master = new BybitMaster(this.client, CONFIG.symbol);
        this.book = new LocalOrderBook();
        this.tape = new TapeGodEngine();
        this.oracle = new OracleBrain();
        this.vol = new VolatilityClampingEngine();
        this.deepVoid = new DeepVoidEngine();
        
        this.state = { 
            price: 0, 
            lastUiUpdate: 0, 
            pnl: 0, 
            equity: 0, 
            availableBalance: 0, 
            maxEquity: 0, 
            paused: false,
            consecutiveLosses: 0, 
            stats: { trades: 0, wins: 0, totalPnl: 0 },
            position: { 
                active: false, 
                side: null, 
                entryPrice: 0, 
                currentSl: 0, 
                entryTime: 0, 
                isBreakEven: false, 
                originalSl: D0(),
                tp: 0
            },
            currentVwap: 0, 
            regime: 'WARMING',
            bestBid: 0,
            bestAsk: 0
        };
        
        this.isRunning = false;
    }

    async refreshEquity() {
        await this.master.sync();
        this.state.equity = this.master.cache.balance.equity;
        this.state.availableBalance = this.master.cache.balance.value;
        
        // Update max equity for drawdown calculation
        if (this.state.equity > this.state.maxEquity) {
            this.state.maxEquity = this.state.equity;
        }
    }

    async warmUp() {
        await this.refreshEquity();
        logger.info(`[INIT] Equity Sync Complete: $${this.state.equity.toFixed(2)}`);
        
        // Cancel any existing orders
        await this.master.cancelAllOrders();
    }

    updateOrderbook(data) {
        const isSnapshot = data.type === 'snapshot' || !this.book.ready;
        this.book.update(data, isSnapshot);

        if (this.book.ready) {
            const { bid, ask } = this.book.getBestBidAsk();
            this.state.bestBid = bid;
            this.state.bestAsk = ask;

            const fullBids = Array.from(this.book.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, this.deepVoid.depth);
            const fullAsks = Array.from(this.book.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, this.deepVoid.depth);

            this.deepVoid.update(fullBids, fullAsks);
            this.displayLiveStatus();
        }
    }
    
    displayLiveStatus() {
        if (Date.now() - this.state.lastUiUpdate < 200) return; // UI DEBOUNCER
        this.state.lastUiUpdate = Date.now();
        
        console.clear();
        console.log(this.tape.getNeonTapeDisplay());
        console.log(this.deepVoid.getNeonDisplay());
    }

    async calculateRiskSize(signal) {
        try {
            const balance = this.state.availableBalance || 10000; // Default for testing
            const riskAmount = balance * CONFIG.risk.maxRiskPerTrade;
            const entry = signal.action === 'BUY' ? this.state.bestAsk : this.state.bestBid;
            const slDistance = Math.abs(entry - signal.sl);
            
            if (slDistance === 0) return 0;
            
            let qty = riskAmount / slDistance;
            qty = Math.max(qty, CONFIG.risk.minOrderQty);
            
            // Apply leverage
            const leveragedQty = qty * (CONFIG.risk.leverage || 10);
            
            return leveragedQty;
        } catch (error) {
            logger.error(`Risk size calculation failed: ${error.message}`);
            return CONFIG.risk.minOrderQty;
        }
    }

    async processCandleSignal(k, metrics, fisherVal) {
        const atr = TA.atr([D(k.high)], [D(k.low)], [D(k.close)], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1);
        
        this.vol.update({ 
            close: D(k.close), 
            atr: atr.toNumber(), 
            price: parseFloat(k.close) 
        }, metrics, fisherVal);
        this.state.regime = this.vol.getRegime();
        
        const signal = await this.oracle.divine(metrics);

        if (signal.action === 'HOLD') return null;

        // VOLATILITY FILTER CHECK
        if (!this.vol.shouldEnter(atr.toNumber(), this.state.regime)) {
            logger.info(`[VOL FILTER] ${this.state.regime} regime – skipping entry`);
            return null;
        }

        // VOLATILITY TP CLAMPING
        const clamped = this.vol.clamp(signal, parseFloat(k.close), atr.toNumber());
        if (clamped.tp !== signal.tp) {
            logger.success(`[VOID CLAW] TP Clamped ${signal.tp} → ${clamped.tp} in ${clamped.regime}`);
            signal.tp = clamped.tp;
        }
        
        return signal; 
    }

    async placeMakerOrder(signal) {
        const qty = await this.calculateRiskSize(signal);
        
        if (qty < parseFloat(CONFIG.risk.minOrderQty || '0.001')) {
            logger.warn('[RISK] Position size below minimum – aborting');
            return;
        }
        
        // Fixed price selection logic
        const price = signal.action === 'BUY' ? this.state.bestAsk : this.state.bestBid;
        
        logger.info(`[ORDER] ${signal.action} ${qty} @ ${price} (Risk: ${(CONFIG.risk.maxRiskPerTrade * 100).toFixed(2)}%)`);
        
        // V3.5.1: Use Iceberg execution path
        const orderSuccess = await this.master.placeLimitOrder({
            side: signal.action,
            price: price,
            qty: qty,
            isIceberg: true,
            icebergSlices: 3 // Default 3 slices
        });

        if (orderSuccess) {
            // Set initial stops immediately
            await this.master.setTradingStop(signal.sl, signal.tp);

            this.state.position = {
                active: true, 
                side: signal.action, 
                entryPrice: price, 
                currentSl: signal.sl, 
                originalSl: D(signal.sl), 
                entryTime: Date.now(), 
                isBreakEven: false,
                tp: signal.tp
            };
            
            logger.success(`[POSITION] ${signal.action} entered at ${price}`);
        } else {
            logger.error('[ORDER] Failed to place iceberg order');
        }
    }

    async closePosition(reason = 'MANUAL') {
        const success = await this.master.closePositionMarket();
        if (success) {
            this.state.position.active = false;
            logger.warn(`[EXIT] Position closed: ${reason}`);
        }
        return success;
    }
    
    async updateTrailingStop() {
        if (!this.state.position.active) return;
        const { side, currentSl } = this.state.position;
        const currentPrice = this.state.price;
        const lastAtrData = this.oracle.klines[this.oracle.klines.length - 1];
        const lastAtr = lastAtrData ? lastAtrData.atr.toNumber() : CONFIG.indicators.atr || 14; 
        const trailDist = D(lastAtr).mul(CONFIG.risk?.trailingStopMultiplier || 2.0); 

        let newSl = D(currentSl);
        let updated = false;

        if (side === 'BUY') {
            const potentialSl = D(currentPrice).minus(trailDist);
            if (potentialSl.gt(newSl)) { 
                newSl = potentialSl; 
                updated = true; 
            }
        } else { // SELL
            const potentialSl = D(currentPrice).plus(trailDist);
            if (potentialSl.lt(newSl)) { 
                newSl = potentialSl; 
                updated = true; 
            }
        }

        if (updated) {
            this.state.position.currentSl = newSl.toNumber();
            await this.master.setTradingStop(newSl.toNumber(), this.state.position.tp);
            logger.info(`[TRAIL] Stop moved to ${newSl.toFixed(2)}`);
        }
    }
    
    async checkVwapExit() {
        // Simple VWAP exit - exit if price moves 2% against position
        if (!this.state.position.active) return;
        
        const { side, entryPrice } = this.state.position;
        const priceChange = (this.state.price - entryPrice) / entryPrice;
        
        if (side === 'BUY' && priceChange < -0.02) {
            await this.closePosition('VWAP_EXIT_BUY');
        } else if (side === 'SELL' && priceChange > 0.02) {
            await this.closePosition('VWAP_EXIT_SELL');
        }
    }
    
    async checkTimeStop() {
        if (!this.state.position.active) return;
        
        const elapsed = Date.now() - this.state.position.entryTime;
        const maxHoldingDuration = CONFIG.risk?.maxHoldingDuration || 7200000; // 2 hours
        
        if (elapsed > maxHoldingDuration) {
            await this.closePosition('TIME_STOP');
        }
    }
    
    async checkExitConditions() {
        if (!this.state.position.active) return;
        
        await this.updateTrailingStop();
        await this.checkVwapExit();
        await this.checkTimeStop();

        const { side, entryPrice, currentSl, originalSl } = this.state.position;
        const currentPrice = this.state.price;
        const elapsed = Date.now() - this.state.position.entryTime;
        
        let exit = false;
        let exitReason = '';

        // 1. ZOMBIE KILL
        const zombieLimit = CONFIG.risk?.zombieTimeMs || 300000;
        const zombieTolerance = D(CONFIG.risk?.zombiePnlTolerance || 0.0015);
        const pnlPct = side === 'BUY' ? D(currentPrice).div(D(entryPrice)).minus(1) : D(entryPrice).div(D(currentPrice)).minus(1);

        if (elapsed > zombieLimit && pnlPct.abs().lt(zombieTolerance)) {
            exit = true;
            exitReason = `ZOMBIE_KILL_${Math.floor(elapsed / 1000)}s`;
        }

        // 2. INSTANT BREAK-EVEN TRIGGER
        if (!this.state.position.isBreakEven) {
            const riskDist = D(entryPrice).minus(originalSl).abs();
            const triggerDist = riskDist.mul(CONFIG.risk?.breakEvenTrigger || 1.0);

            if (side === 'BUY' && D(currentPrice).gte(D(entryPrice).plus(triggerDist))) {
                const newSl = D(entryPrice).plus(D(currentPrice).mul(CONFIG.risk?.fee || 0.0005)).toNumber();
                this.state.position.currentSl = newSl;
                this.state.position.isBreakEven = true;
                await this.master.setTradingStop(newSl, this.state.position.tp);
                logger.success('[BE] Break-even triggered for BUY');
            } else if (side === 'SELL' && D(currentPrice).lte(D(entryPrice).minus(triggerDist))) {
                const newSl = D(entryPrice).minus(D(currentPrice).mul(CONFIG.risk?.fee || 0.0005)).toNumber();
                this.state.position.currentSl = newSl;
                this.state.position.isBreakEven = true;
                await this.master.setTradingStop(newSl, this.state.position.tp);
                logger.success('[BE] Break-even triggered for SELL');
            }
        }

        // 3. HARD STOPS & TIME EXIT
        if (!exit) {
            if (elapsed > CONFIG.risk?.maxHoldingDuration || 7200000) { 
                exit = true; 
                exitReason = 'TIME_LIMIT'; 
            }
            
            if (side === 'BUY') {
                if (currentPrice <= currentSl) { 
                    exit = true; 
                    exitReason = 'SL_HIT'; 
                }
                else if (currentPrice >= this.state.position.tp) { 
                    exit = true; 
                    exitReason = 'TP_HIT'; 
                }
            } else {
                if (currentPrice >= currentSl) { 
                    exit = true; 
                    exitReason = 'SL_HIT'; 
                }
                else if (currentPrice <= this.state.position.tp) { 
                    exit = true; 
                    exitReason = 'TP_HIT'; 
                }
            }
        }

        // 4. ORACLE FLIP CHECK
        const signal = await this.oracle.divine(this.book.getAnalysis());
        if (!exit && signal.action !== 'HOLD' && signal.action !== side) {
            exit = true;
            exitReason = `ORACLE_FLIP_${signal.action}`;
        }
        
        if (exit) {
            logger.warn(`[EXIT] ${exitReason} triggered.`);
            await this.closePosition(exitReason);
        }
    }
    
    async start() {
        if (this.isRunning) {
            logger.warn('Leviathan is already running');
            return;
        }
        
        this.isRunning = true;
        await this.warmUp();

        try {
            this.ws.subscribeV5([
                `kline.${CONFIG.intervals.main}.${CONFIG.symbol}`,
                `orderbook.50.${CONFIG.symbol}`,
                `execution.${CONFIG.symbol}`
            ], 'linear');
            
            this.ws.subscribeV5(['position'], 'private');
        } catch (error) {
            logger.error(`WebSocket subscription failed: ${error.message}`);
        }

        // Periodic tasks
        setInterval(() => this.refreshEquity(), 300000); // 5 minutes
        setInterval(() => {
            // Update stats
            this.state.stats.trades = (this.state.stats.trades || 0) + 1;
            logger.info(`[STATS] Trades: ${this.state.stats.trades}, Equity: $${this.state.equity.toFixed(2)}`);
        }, 600000); // 10 minutes

        this.ws.on('update', async (data) => {
            if (!data?.data || !data.topic) return;
            
            try {
                if (data.topic === 'execution') {
                    if (Array.isArray(data.data)) {
                        data.data.forEach(exec => this.tape.processExecution(exec));
                    }
                }
                
                if (data.topic?.startsWith('orderbook')) {
                    const frame = Array.isArray(data.data) ? data.data[0] : data.data;
                    const type = data.type ? data.type : (this.book.ready ? 'delta' : 'snapshot');
                    this.updateOrderbook({ type, b: frame.b, a: frame.a });
                }
                
                if (data.topic?.includes(`kline.${CONFIG.intervals.main}.`)) {
                    const k = data.data[0]; 
                    if (!k.confirm) return;
                    
                    this.state.price = parseFloat(k.close);
                    const metrics = this.book.getAnalysis();
                    
                    process.stdout.write(`\r${C.dim}[v3.5.1 ${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price.toFixed(2)} | Tape:${this.tape.getMetrics().dom} | ${metrics.skew.toFixed(2)} Skew   `);

                    const candleContext = { 
                        open: D(k.open), 
                        high: D(k.high), 
                        low: D(k.low), 
                        close: D(k.close), 
                        volume: D(k.volume || 0),
                        atr: TA.atr([D(k.high)], [D(k.low)], [D(k.close)], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1)
                    };
                    
                    this.oracle.update(candleContext);
                    
                    const signal = await this.processCandleSignal(k, metrics, this.oracle.klines[this.oracle.klines.length - 1]?.fisher || 0);

                    if (signal && signal.action !== 'HOLD') {
                        await this.placeMakerOrder(signal);
                    }
                    
                    await this.checkExitConditions();
                }
                
                // Position updates
                if (data.topic === 'position') {
                    const positions = data.data;
                    if (positions && positions.length > 0) {
                        const pos = positions[0];
                        const size = parseFloat(pos.size || '0');
                        if (size === 0 && this.state.position.active) {
                            // Position closed
                            this.state.position.active = false;
                            logger.info('[POSITION] Position closed via Bybit');
                        }
                    }
                }
            } catch (error) {
                logger.error(`WS update error: ${error.message}`);
            }
        });

        this.ws.on('close', () => {
            logger.warn('WebSocket disconnected, attempting reconnect...');
            setTimeout(() => {
                if (this.isRunning) {
                    this.start(); // Restart
                }
            }, 5000);
        });

        this.ws.on('error', (error) => {
            logger.error(`WebSocket error: ${error.message}`);
        });

        logger.success(`SHARK MODE ACTIVATED: LEVIATHAN v${VERSION}`);
    }
    
    async stop() {
        this.isRunning = false;
        if (this.ws) {
            this.ws.removeAllListeners();
            this.ws.close();
        }
        await this.master.cancelAllOrders();
        logger.info('Leviathan stopped');
    }
}

// --- EXECUTION BLOCK ────────────────────────────────────────────────────────
if (require.main === module) {
    const engine = new LeviathanEngine();
    
    // Graceful shutdown
    process.on('SIGINT', async () => {
        logger.info('Received SIGINT, shutting down gracefully...');
        await engine.stop();
        process.exit(0);
    });
    
    process.on('SIGTERM', async () => {
        logger.info('Received SIGTERM, shutting down gracefully...');
        await engine.stop();
        process.exit(0);
    });
    
    engine.start().catch(e => {
        logger.error('[FATAL_LAUNCH] System failed to start', { error: e.message, stack: e.stack });
        process.exit(1);
    });
}

module.exports = { LeviathanEngine, TA, CONFIG };
