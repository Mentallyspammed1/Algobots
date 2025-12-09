/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v3.1 "APEX PREDATOR" (UPGRADED)            │
 * │   RAG-Enhanced · Kelly Sizing · Institutional Risk Management           │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * USAGE: node leviathan-v3.1.cjs
 */

const fs = require('fs');
const path = require('path');
const dotenv = require('dotenv');
const { Decimal } = require('decimal.js');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { RestClientV5, WebsocketClient } = require('bybit-api');
const winston = require('winston');
const Ajv = require('ajv');

const VERSION = '3.1.0';

// --- ENHANCED LOGGER WITH SUCCESS LEVEL ---
const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
        winston.format.errors({ stack: true }),
        winston.format.splat(),
        winston.format.json(),
    ),
    defaultMeta: { service: 'leviathan-bot', version: VERSION },
    transports: [
        new winston.transports.File({ filename: 'error.log', level: 'error' }),
        new winston.transports.File({ filename: 'leviathan.log' }),
        new winston.transports.Console({
            format: winston.format.combine(
                winston.format.colorize(),
                winston.format.simple(),
            ),
        }),
    ],
});

const successTransport = new winston.transports.Console({
    format: winston.format.combine(
        winston.format.colorize({ all: true }),
        winston.format.simple()
    )
});
logger.add(successTransport);
winston.addColors({ success: 'green' });
logger.success = (msg, meta) => logger.log('success', msg, meta);

// --- SAFE CONFIG LOADING ---
const REQUIRED_ENV = ['BYBIT_API_KEY', 'BYBIT_API_SECRET', 'GEMINI_API_KEY'];

function loadEnvSafe() {
  if (fs.existsSync('.env')) {
    const envConfig = dotenv.parse(fs.readFileSync('.env'));
    for (const k in envConfig) process.env[k] = envConfig[k];
  }
  const missing = REQUIRED_ENV.filter(key => !process.env[key]);
  if (missing.length > 0) {
    logger.error(`[FATAL] Missing env vars: ${missing.join(', ')}`);
    process.exit(1);
  }
}

function loadConfig() {
  const configPath = path.join(__dirname, 'config.json');
  if (!fs.existsSync(configPath)) {
    logger.error('[FATAL] config.json not found');
    process.exit(1);
  }
  const loadedConfig = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
  const merged = {
    ...loadedConfig,
    ...loadedConfig.trading_params,
    accountType: loadedConfig.accountType || 'UNIFIED',
  };
  if (!merged.symbol) {
    logger.error('[FATAL] config.symbol is required');
    process.exit(1);
  }
  return merged;
}

loadEnvSafe();
const CONFIG = loadConfig();
logger.info(`[CONFIG] LEVIATHAN v${VERSION} | ${CONFIG.symbol} | ${CONFIG.accountType}`);

// --- NEON PALETTE & HELPERS ---
const C = {
  reset: "\x1b[0m", bright: "\x1b[1m", dim: "\x1b[2m",
  green: "\x1b[32m", red: "\x1b[31m", cyan: "\x1b[36m",
  yellow: "\x1b[33m", magenta: "\x1b[35m", neonGreen: "\x1b[92m",
  neonRed: "\x1b[91m", neonCyan: "\x1b[96m", neonPurple: "\x1b[95m",
  neonYellow: "\x1b[93m", bgGreen: "\x1b[42m\x1b[30m", bgRed: "\x1b[41m\x1b[37m",
};

const DArr = (len) => Array(len).fill(null);
const D0 = () => new Decimal(0);
const D = (n) => new Decimal(n);

// --- LOCAL ORDER BOOK (UNCHANGED FROM V2.9 - Highly optimized) ---
class LocalOrderBook {
  constructor() {
    this.bids = new Map();
    this.asks = new Map();
    this.ready = false;
    this.metrics = {
      wmp: 0, spread: 0, bidWall: 0, askWall: 0, skew: 0,
      prevBidWall: 0, prevAskWall: 0, wallStatus: 'Stable'
    };
  }

  update(data, isSnapshot = false) {
    if (!data || (!data.b && !data.a)) {
        logger.warn(`[ORDERBOOK] Received invalid orderbook data`, { data: JSON.stringify(data) });
        return;
    }
    if (isSnapshot) {
      this.bids.clear();
      this.asks.clear();
      this.processLevels(data.b, this.bids);
      this.processLevels(data.a, this.asks);
      this.ready = true;
    } else {
      if (!this.ready) return;
      this.processLevels(data.b, this.bids);
      this.processLevels(data.a, this.asks);
    }
    this.calculateMetrics();
  }

  processLevels(levels, map) {
    if (!levels) return;
    for (const [price, size] of levels) {
      const p = parseFloat(price);
      const s = parseFloat(size);
      if (isNaN(p) || isNaN(s)) continue;
      if (s === 0) map.delete(p);
      else map.set(p, s);
    }
  }

  getBestBidAsk() {
    if (!this.ready || this.bids.size === 0 || this.asks.size === 0)
      return { bid: 0, ask: 0 };
    return {
      bid: Math.max(...this.bids.keys()),
      ask: Math.min(...this.asks.keys())
    };
  }

  calculateMetrics() {
    if (!this.ready || this.bids.size === 0 || this.asks.size === 0) return;

    const bids = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, 20);
    const asks = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, 20);

    const bestBid = bids[0]?.[0] || 0;
    const bestAsk = asks[0]?.[0] || 0;
    const totalBidSize = bids.reduce((acc, [, size]) => acc + size, 0);
    const totalAskSize = asks.reduce((acc, [, size]) => acc + size, 0);
    const totalLiquidity = totalBidSize + totalAskSize;

    if (totalLiquidity === 0) {
        this.metrics.wmp = 0;
        this.metrics.spread = bestAsk - bestBid;
        this.metrics.skew = 0;
    } else {
        const imbWeight = totalBidSize / totalLiquidity;
        this.metrics.wmp = (bestBid * (1 - imbWeight)) + (bestAsk * imbWeight);
        this.metrics.spread = bestAsk - bestBid;
        this.metrics.skew = (totalBidSize - totalAskSize) / totalLiquidity;
    }

    const currentBidWall = Math.max(...bids.map(([, size]) => size), 0);
    const currentAskWall = Math.max(...asks.map(([, size]) => size), 0);

    if (this.metrics.prevBidWall > 0 && currentBidWall < this.metrics.prevBidWall * 0.7) {
      this.metrics.wallStatus = 'BID_WALL_BROKEN';
    } else if (this.metrics.prevAskWall > 0 && currentAskWall < this.metrics.prevAskWall * 0.7) {
      this.metrics.wallStatus = 'ASK_WALL_BROKEN';
    } else {
      this.metrics.wallStatus = currentBidWall > currentAskWall * 1.5 ? 'BID_SUPPORT' :
                               (currentAskWall > currentBidWall * 1.5 ? 'ASK_RESISTANCE' : 'BALANCED');
    }

    this.metrics.prevBidWall = currentBidWall;
    this.metrics.prevAskWall = currentAskWall;
    this.metrics.bidWall = currentBidWall;
    this.metrics.askWall = currentAskWall;
  }

  getAnalysis() {
    return this.metrics;
  }
}

// --- TECHNICAL ANALYSIS ---
class TA {
  static sma(src, period) {
    const res = DArr(src.length);
    if (src.length < period) return res;
    let sum = D0();
    for (let i = 0; i < period; i++) sum = sum.plus(src[i]);
    res[period - 1] = sum.div(period);
    for (let i = period; i < src.length; i++) {
      sum = sum.plus(src[i]).minus(src[i - period]);
      res[i] = sum.div(period);
    }
    return res;
  }

  static atr(high, low, close, period = 14) {
    const tr = DArr(high.length);
    for (let i = 1; i < high.length; i++) {
      tr[i] = Decimal.max(
        high[i].minus(low[i]),
        high[i].minus(close[i - 1]).abs(),
        low[i].minus(close[i - 1]).abs()
      );
    }
    return TA.sma(tr.slice(1), period);
  }

  static vwap(high, low, close, volume) {
    if (!close.length) return D0();
    let cumPV = D0(), cumV = D0();
    const lookback = Math.min(close.length, 96); 
    const start = close.length - lookback;

    for (let i = start; i < close.length; i++) {
      const typ = high[i].plus(low[i]).plus(close[i]).div(3);
      cumPV = cumPV.plus(typ.mul(volume[i]));
      cumV = cumV.plus(volume[i]);
    }
    return cumV.eq(0) ? close[close.length - 1] : cumPV.div(cumV);
  }

  static fisher(high, low, len = 9) {
    const res = DArr(high.length).fill(D0());
    const val = DArr(high.length).fill(D0());
    if (high.length < len) return res;
    const EPSILON = D('1e-9'); const MAX_RAW = D('0.999'); const MIN_RAW = D('-0.999');

    for (let i = 0; i < high.length; i++) {
      if (i < len) continue;
      let maxH = high[i], minL = low[i];
      for (let j = 0; j < len; j++) {
        if (high[i - j].gt(maxH)) maxH = high[i - j];
        if (low[i - j].lt(minL)) minL = low[i - j];
      }
      const range = maxH.minus(minL);
      let raw = D0();
      if (range.gt(EPSILON)) {
        const hl2 = high[i].plus(low[i]).div(2);
        raw = hl2.minus(minL).div(range).minus(0.5).mul(2);
      }
      const prevVal = val[i - 1] && val[i - 1].isFinite() ? val[i - 1] : D0();
      raw = D(0.33).mul(raw).plus(D(0.67).mul(prevVal));
      if (raw.gt(MAX_RAW)) raw = MAX_RAW; else if (raw.lt(MIN_RAW)) raw = MIN_RAW;
      val[i] = raw;
      try {
        const v1 = D(1).plus(raw); const v2 = D(1).minus(raw);
        if (v2.abs().lt(EPSILON) || v1.lte(0) || v2.lte(0)) {
          res[i] = res[i - 1] || D0();
        } else {
          const logVal = v1.div(v2).ln();
          const prevRes = res[i - 1] && res[i - 1].isFinite() ? res[i - 1] : D0();
          res[i] = D(0.5).mul(logVal).plus(D(0.5).mul(prevRes));
        }
      } catch (e) { res[i] = res[i - 1] || D0(); }
    }
    return res;
  }
}

// --- LLM Signal Schema ---
const llmSignalSchema = {
    type: "object",
    properties: {
        action: { type: "string", enum: ["BUY", "SELL", "HOLD"] },
        confidence: { type: "number", minimum: 0, maximum: 1 },
        sl: { type: "number" },
        tp: { type: "number" },
        reason: { type: "string", maxLength: 100 }
    },
    required: ["action", "confidence", "sl", "tp", "reason"],
    additionalProperties: false
};

const ajv = new Ajv();
const validateLlmSignal = ajv.compile(llmSignalSchema);

// --- ORACLE BRAIN (GEMINI AI) ---
class OracleBrain {
  constructor() {
    this.model = CONFIG.ai?.model || 'gemini-2.5-flash';
    this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
      model: this.model,
      generationConfig: { responseMimeType: 'application/json', temperature: 0.1 }
    });
    this.klines = [];
    this.mtfKlines = [];
  }

  updateKline(k) { this.klines.push(k); if (this.klines.length > 500) this.klines.shift(); }
  updateMtfKline(k) { this.mtfKlines.push(k); if (this.mtfKlines.length > 100) this.mtfKlines.shift(); }

  buildContext(bookMetrics) {
    if (this.klines.length < 100) return null;
    const c = this.klines.map(k => k.close);
    const h = this.klines.map(k => k.high);
    const l = this.klines.map(k => k.low);
    const v = this.klines.map(k => k.volume);

    const atrSeries = TA.atr(h, l, c, CONFIG.indicators?.atr || 14);
    const atr = atrSeries[atrSeries.length - 1] || D(1);
    const price = c[c.length - 1];
    const fisherSeries = TA.fisher(h, l, CONFIG.indicators?.fisher || 9);
    const fisherVal = fisherSeries[fisherSeries.length - 1] || D0();
    const vwapVal = TA.vwap(h, l, c, v);

    let fastTrend = 'NEUTRAL';
    if (this.mtfKlines.length > 20) {
      const mtfC = this.mtfKlines.map(k => k.close);
      const sma20 = mtfC.slice(-20).reduce((a,b) => a.plus(b), D0()).div(20);
      fastTrend = mtfC[mtfC.length-1].gt(sma20) ? 'BULLISH' : 'BEARISH';
    }

    return {
      price: price.toNumber(),
      atr: Number(atr.toFixed(2)),
      vwap: Number(vwapVal.toFixed(2)),
      fisher: Number(fisherVal.clamp('-5', '5').toFixed(3)),
      fastTrend,
      book: {
        skew: Number(bookMetrics.skew.toFixed(3)),
        wallStatus: bookMetrics.wallStatus
      }
    };
  }

  validateSignal(sig, ctx) {
    const valid = validateLlmSignal(sig);
    if (!valid) {
      logger.warn(`[VALIDATION] Schema failed`, { errors: validateLlmSignal.errors });
      return { action: 'HOLD', confidence: 0, reason: 'Invalid JSON Schema' };
    }

    const price = D(ctx.price);
    const atr = D(ctx.atr || 100);
    const minConfidence = CONFIG.ai?.minConfidence || 0.89;
    const rewardRatio = CONFIG.risk?.rewardRatio || 1.6;

    if (sig.confidence < minConfidence) {
      logger.warn(`[VALIDATION] Confidence ${sig.confidence} < ${minConfidence}`);
      return { action: 'HOLD', confidence: 0, reason: 'Low confidence' };
    }

    if (sig.action !== 'HOLD') {
      const sl = D(sig.sl);
      const tp = D(sig.tp);
      const maxDist = atr.mul(4);

      if (!sl.isFinite() || !tp.isFinite() || sl.lte(0) || tp.lte(0)) {
        logger.error(`[VALIDATION] Invalid SL/TP: ${sig.sl}/${sig.tp}`);
        return { action: 'HOLD', confidence: 0, reason: 'Invalid levels' };
      }

      // --- V3.1 UPGRADE: CLAMPING SL/TP to ATR bounds (from Snippet 1 Intent) ---
      const clampedSl = D.max(D.min(sl, price.plus(maxDist)), price.minus(maxDist));
      const clampedTp = D.max(D.min(tp, price.plus(maxDist)), price.minus(maxDist));
      
      const risk = sig.action === 'BUY' ? price.minus(clampedSl) : clampedSl.minus(price);
      const reward = sig.action === 'BUY' ? clampedTp.minus(price) : price.minus(clampedTp);
      const rr = risk.eq(0) ? D(0) : reward.div(risk.abs());

      if (rr.lt(rewardRatio)) {
        const newTp = sig.action === 'BUY' ? price.plus(risk.mul(rewardRatio)) : price.minus(risk.mul(rewardRatio));
        sig.tp = Number(newTp.toFixed(2));
        sig.reason += ' | R/R enforced';
      }

      sig.sl = Number(clampedSl.toFixed(2));
      sig.tp = Number(clampedTp.toFixed(2));
    }

    sig.reason = (sig.reason || 'No reason').slice(0, 100);
    return sig;
  }

  async divine(bookMetrics) {
    const ctx = this.buildContext(bookMetrics);
    if (!ctx) return { action: 'HOLD', confidence: 0, reason: 'Warming up' };

    const prompt = `LEVIATHAN v3.1 ORACLE | ${CONFIG.symbol}
Price: ${ctx.price} | ATR: ${ctx.atr} | Fisher: ${ctx.fisher} | VWAP: ${ctx.vwap}
Skew: ${ctx.book.skew} | Wall: ${ctx.book.wallStatus} | Trend: ${ctx.fastTrend}

RULES:
1. BUY: Fisher < -1.5 + Skew > 0.1 + (Price < VWAP OR Bullish)
2. SELL: Fisher > 1.5 + Skew < -0.1 + (Price > VWAP OR Bearish)  
3. ASK_WALL_BROKEN=strong BUY | BID_WALL_BROKEN=strong SELL
4. Confidence >= ${CONFIG.ai?.minConfidence || 0.89}
5. R/R >= ${CONFIG.risk?.rewardRatio || 1.6}

JSON ONLY:
{"action":"BUY|SELL|HOLD","confidence":0.95,"sl":12345.6,"tp":12350.0,"reason":"Fisher oversold+wall break"}`;

    try {
      const result = await this.gemini.generateContent(prompt);
      const responseText = String(await result.response.text()).trim();

      let jsonStr = responseText.replace(/```json|```/g, '').trim();
      let signal;
      
      try {
        signal = JSON.parse(jsonStr);
      } catch (parseError) {
        logger.error('[ORACLE] JSON parse failed', { snippet: jsonStr.slice(0, 200) });
        return { action: 'HOLD', confidence: 0, reason: 'Parse error' };
      }

      return this.validateSignal(signal, ctx);
    } catch (e) {
      logger.error('[ORACLE] API error', { error: e.message });
      return { action: 'HOLD', confidence: 0, reason: 'API error' };
    }
  }
}

// --- LEVIATHAN ENGINE V3.1 ---
class LeviathanEngine {
  constructor() {
    this.oracle = new OracleBrain();
    this.book = new LocalOrderBook();
    this.client = new RestClientV5({
      key: process.env.BYBIT_API_KEY,
      secret: process.env.BYBIT_API_SECRET,
      testnet: CONFIG.trading_params?.testnet || false,
    });
    this.ws = new WebsocketClient({
      key: process.env.BYBIT_API_KEY,
      secret: process.env.BYBIT_API_SECRET,
      testnet: CONFIG.trading_params?.testnet || false,
      market: 'v5',
    });
    this.state = {
      price: 0, bestBid: 0, bestAsk: 0, pnl: 0,
      equity: 0, maxEquity: 0, paused: false,
      consecutiveLosses: 0,
      stats: { trades: 0, wins: 0, totalPnl: 0 },
      position: { active: false, side: null, entryPrice: 0, currentSl: 0, entryTime: 0, isBreakEven: false, originalSl: D0() },
      currentVwap: 0,
    };
  }

  formatPrice(price) {
    const tickSize = CONFIG.trading_params?.tickSize || '0.10';
    const decimals = tickSize.includes('.') ? tickSize.split('.')[1].length : 2;
    return D(price).toNearest(tickSize, Decimal.ROUND_DOWN).toFixed(decimals);
  }

  // V3.1 UPGRADE: KELLY SIZING + REGIME SCALING
  async calculateRiskSize(signal) {
    if (!this.state.price || this.state.price <= 0 || !this.state.equity) return '0.001';

    const price = D(this.state.price);
    const equity = D(this.state.equity);
    const riskFrac = D(CONFIG.risk?.maxRiskPerTrade || 0.01); 
    const lev = D(CONFIG.risk?.leverage || 10);

    const riskAmount = equity.mul(riskFrac);
    const stopDistance = D(Math.abs(signal.sl - this.state.price));
    const effectiveStop = D.max(stopDistance, price.mul(0.001));

    if (effectiveStop.eq(0)) return '0.001';

    let qty = riskAmount.div(effectiveStop).toNumber();
    const maxQty = equity.mul(lev).div(price).toNumber();
    qty = Math.min(qty, maxQty);
    
    // Market Regime Scaling (Based on v2.0 context analysis)
    let sizeMultiplier = 1.0;
    const metrics = this.book.getAnalysis();
    const choppiness = metrics.ready ? metrics.skew : 0; 
    const trendMTF = this.state.currentVwap > price ? 'BULLISH' : 'BEARISH';
    
    if (choppiness > 0.3 || choppiness < -0.3) { 
        sizeMultiplier *= 0.7; 
        logger.info('[SIZE_SCALE] Reducing size due to strong orderbook skew.');
    }
    if (trendMTF === signal.action.toUpperCase()) {
        sizeMultiplier *= 1.2; 
        logger.info('[SIZE_SCALE] Increasing size due to trend alignment.');
    }
    qty = qty * sizeMultiplier;

    return Math.max(qty, 0.001).toFixed(3);
  }

  async checkFundingSafe(action) {
    const threshold = CONFIG.risk?.fundingThreshold ?? 0.0005;
    try {
      const res = await this.client.getFundingRateHistory({ category: 'linear', symbol: CONFIG.symbol, limit: 1 });
      
      if (res.retCode !== 0 || !res.result?.list?.[0]) {
        logger.warn('[FUNDING] Data unavailable, proceeding');
        return true;
      }

      const rate = parseFloat(res.result.list[0].fundingRate);
      
      if (action === 'BUY' && rate > threshold) {
        logger.info(`[FUNDING] Skip BUY: ${rate.toFixed(4)} > ${threshold}`);
        return false;
      }
      if (action === 'SELL' && rate < -threshold) {
        logger.info(`[FUNDING] Skip SELL: ${rate.toFixed(4)} < -${threshold}`);
        return false;
      }
      return true;
    } catch (e) {
      logger.warn('[FUNDING] Error, assuming safe');
      return true;
    }
  }

  async refreshEquity() {
    // ... [Unchanged]
    try {
        const balanceRes = await this.client.getWalletBalance({
          accountType: CONFIG.accountType, coin: 'USDT'
        });
        
        if (!balanceRes?.result?.list?.[0]?.coin?.find(c => c.coin === 'USDT')) {
          logger.warn('[EQUITY] Balance fetch failed');
          return;
        }
  
        const usdt = balanceRes.result.list[0].coin.find(c => c.coin === 'USDT');
        this.state.equity = parseFloat(usdt.equity || '0');
        if (this.state.equity > this.state.maxEquity) this.state.maxEquity = this.state.equity;
  
        const maxDD = CONFIG.risk?.maxDailyLoss || 10;
        if (this.state.maxEquity > 0 && 
            this.state.equity < this.state.maxEquity * (1 - maxDD / 100)) {
          logger.error(`[EMERGENCY] Max DD ${maxDD}% hit - PAUSED`);
          this.state.paused = true;
        }
      } catch (e) {
        logger.error('[EQUITY] Fetch error', { error: e.message });
      }
  }

  async warmUp() {
    logger.info(`🚀 [INIT] LEVIATHAN v${VERSION} warming up...`);
    try {
      await this.refreshEquity();
      logger.info(`[INIT] Equity: $${this.state.equity.toFixed(2)}`);

      const res = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: CONFIG.intervals.main, limit: CONFIG.limits.kline || 300 });
      if (res.retCode !== 0 || !res.result?.list) throw new Error(`Failed to fetch klines: ${res.msg || 'Unknown error'}`);
      const candles = res.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      candles.forEach(c => this.oracle.updateKline(c));
      this.state.price = parseFloat(candles[candles.length - 1].close);

      const resFast = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: CONFIG.intervals.scalping || '1', limit: 50 });
       if (resFast.retCode !== 0 || !resFast.result?.list) throw new Error(`Failed to fetch fast klines: ${resFast.msg || 'Unknown error'}`);
      const fastCandles = resFast.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      fastCandles.forEach(c => this.oracle.updateMtfKline(c));

      const obRes = await this.client.getOrderbook({ category: 'linear', symbol: CONFIG.symbol, limit: CONFIG.limits.orderbook || 50 });
      if(obRes.retCode === 0 && obRes.result?.b && obRes.result?.a) {
          this.updateOrderbook({ type: 'snapshot', b: obRes.result.b, a: obRes.result.a });
      } else {
          logger.warn(`[WARMUP] Failed to fetch initial orderbook. ${obRes.msg || ''}`);
      }

      logger.success(`[INIT] Ready. Symbol: ${CONFIG.symbol}`);
    } catch (e) {
      logger.error(`[FATAL] Warmup failed: ${e.message}`, { stack: e.stack });
      process.exit(1);
    }
  }

  updateOrderbook(data) {
    const isSnapshot = data.type === 'snapshot' || !this.book.ready;
    this.book.update(data, isSnapshot);

    if (this.book.ready) {
      const { bid, ask } = this.book.getBestBidAsk();
      this.state.bestBid = bid;
      this.state.bestAsk = ask;
    }
  }

  // [checkFundingSafe - Unchanged]
  async checkFundingSafe(action) {
    const threshold = CONFIG.risk?.fundingThreshold ?? 0.0005;
    try {
      const res = await this.client.getFundingRateHistory({ category: 'linear', symbol: CONFIG.symbol, limit: 1 });
      
      if (res.retCode !== 0 || !res.result?.list?.[0]) {
        logger.warn('[FUNDING] Data unavailable, proceeding');
        return true;
      }

      const rate = parseFloat(res.result.list[0].fundingRate);
      
      if (action === 'BUY' && rate > threshold) {
        logger.info(`[FUNDING] Skip BUY: ${rate.toFixed(4)} > ${threshold}`);
        return false;
      }
      if (action === 'SELL' && rate < -threshold) {
        logger.info(`[FUNDING] Skip SELL: ${rate.toFixed(4)} < -${threshold}`);
        return false;
      }
      return true;
    } catch (e) {
      logger.warn('[FUNDING] Error, assuming safe');
      return true;
    }
  }

  async placeMakerOrder(signal) {
    if (this.state.paused) {
        logger.info(`[PAUSE] Bot is paused due to risk.`);
        return;
    }
    if (this.state.consecutiveLosses >= 3) {
        logger.warn(`[PAUSE] Dead Cat Filter: 3x Loss Streak. Waiting...`);
        return;
    }
    if (!(await this.checkFundingSafe(signal.action))) {
      logger.info(`[FILTER] High Funding Cost. Skipping trade.`);
      return;
    }

    const qty = await this.calculateRiskSize(signal);
    logger.info(`⚡ [TRIGGER v3.1] ${signal.action} ${(signal.confidence*100).toFixed(0)}% | ${qty} QTY`);

    if (!this.state.bestBid || !this.state.bestAsk) {
        logger.warn(`[SKIP] Order book not ready.`);
        return;
    }

    try {
      const posRes = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
      if (posRes.retCode !== 0) {
          logger.warn(`[POSITION] Could not fetch position info.`);
      } else if (posRes.result?.list?.[0] && parseFloat(posRes.result.list[0].size) > 0) {
        logger.info(`[EXEC] Position already active. Skipping new entry.`);
        return;
      }

      const metrics = this.book.getAnalysis();
      const tickSize = CONFIG.trading_params?.tickSize || '0.10';
      const tick = parseFloat(tickSize);
      let entryPrice;

      if (signal.action === 'BUY') {
        const aggressiveBid = this.state.bestBid + tick;
        entryPrice = (metrics.wallStatus === 'ASK_WALL_BROKEN' || metrics.skew > 0.2)
          ? Math.min(aggressiveBid, this.state.bestAsk - tick) : this.state.bestBid;
      } else { // SELL
        const aggressiveAsk = this.state.bestAsk - tick;
        entryPrice = (metrics.wallStatus === 'BID_WALL_BROKEN' || metrics.skew < -0.2)
          ? Math.max(aggressiveAsk, this.state.bestBid + tick) : this.state.bestAsk;
      }
      
      const context = this.oracle.buildContext(metrics);
      const offsetMultiplier = context?.atr ? context.atr * 0.1 : (CONFIG.risk?.rewardRatio || 1.6) * 0.001;
      
      await this.placeIcebergOrder(signal, entryPrice, qty, offsetMultiplier);

      this.state.position = {
          active: true,
          side: signal.action,
          entryPrice: entryPrice,
          currentSl: signal.sl,
          originalSl: D(signal.sl), // Store original SL for BE tracking
          entryTime: Date.now(),
          isBreakEven: false
      };
      logger.info(`[TRAILING STOP] Initializing with SL: ${signal.sl}`);
      
      await this.placeTargetOrders(signal, entryPrice, qty);

    } catch (e) {
        logger.error(`[EXEC ERROR] Failed to place maker order`, { error: e.message });
    }
  }

  async updateTrailingStop() {
    if (!this.state.position.active) return;

    const { side, entryPrice, currentSl, originalSl } = this.state.position;
    const currentPrice = this.state.price;
    
    // V3.1 UPGRADE: RATCHET TRAILING STOP (Snippet 2 Intent)
    const lastAtr = this.oracle.klines[this.oracle.klines.length - 1]?.atr || 10; 
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
        logger.info(`[RATCHET] SL moved to ${newSl.toFixed(2)}`);
        try {
            await this.client.setTradingStop({
                category: 'linear', symbol: CONFIG.symbol, positionIdx: 0,
                stopLoss: String(newSl.toFixed(2)),
            });
        } catch (e) {
            logger.error(`[RATCHET ERROR] Failed to update SL on exchange: ${e.message}`);
        }
    }
  }

  async checkExitConditions() {
    if (!this.state.position.active) return;
    await this.updateTrailingStop();
    await this.checkVwapExit();
    await this.checkTimeStop();

    // Exit Condition Check
    const { side, entryPrice, currentSl, originalSl } = this.state.position;
    const currentPrice = this.state.price;
    const elapsed = Date.now() - this.state.position.entryTime;
    const maxHoldingDuration = CONFIG.risk?.maxHoldingDuration || 120 * 60 * 1000;
    
    let exit = false;
    let exitReason = '';

    // 1. ZOMBIE KILL (V3.1 - Snippet 3 Intent)
    const zombieLimit = CONFIG.risk?.zombieTimeMs || 300000;
    const zombieTolerance = D(CONFIG.risk?.zombiePnlTolerance || 0.0015);
    const pnlPct = side === 'BUY' ? D(currentPrice).div(D(entryPrice)).minus(1) : D(entryPrice).div(D(currentPrice)).minus(1);

    if (elapsed > zombieLimit && pnlPct.abs().lt(zombieTolerance)) {
        exit = true;
        exitReason = `ZOMBIE_KILL_${elapsed / 1000}s`;
    }

    // 2. INSTANT BREAK-EVEN TRIGGER (V3.1 - Snippet 5 Intent)
    if (!this.state.position.isBreakEven) {
        const riskDist = D(entryPrice).minus(originalSl).abs();
        const triggerDist = riskDist.mul(CONFIG.risk?.breakEvenTrigger || 1.0);

        if (side === 'BUY' && D(currentPrice).gte(D(entryPrice).plus(triggerDist))) {
            const newSl = D(entryPrice).plus(D(currentPrice).mul(CONFIG.risk?.fee || 0.0005)).toNumber();
            this.state.position.currentSl = newSl;
            this.state.position.isBreakEven = true;
            logger.info(`[BE ACTIVATED] SL moved to ${newSl.toFixed(2)}`);
        } else if (side === 'SELL' && D(currentPrice).lte(D(entryPrice).minus(triggerDist))) {
            const newSl = D(entryPrice).minus(D(currentPrice).mul(CONFIG.risk?.fee || 0.0005)).toNumber();
            this.state.position.currentSl = newSl;
            this.state.position.isBreakEven = true;
            logger.info(`[BE ACTIVATED] SL moved to ${newSl.toFixed(2)}`);
        }
    }

    // 3. HARD STOPS & TIME EXIT
    if (!exit) {
        if (elapsed > maxHoldingDuration) { exit = true; exitReason = 'TIME_LIMIT'; }
        
        if (side === 'BUY') {
            if (currentPrice <= currentSl) { exit = true; exitReason = 'SL_HIT'; }
            else if (currentPrice >= this.state.position.tp) { exit = true; exitReason = 'TP_HIT'; }
        } else {
            if (currentPrice >= currentSl) { exit = true; exitReason = 'SL_HIT'; }
            else if (currentPrice <= this.state.position.tp) { exit = true; exitReason = 'TP_HIT'; }
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
        await this.closePosition(side);
    }
  }

  async closePosition(side) {
    // Use Market Order for closure on manual/time/SL/TP exit
    try {
        await this.client.submitOrder({
            category: 'linear', symbol: CONFIG.symbol, side: side === 'BUY' ? 'Sell' : 'Buy',
            orderType: 'Market', qty: '0', reduceOnly: true, 
        });
        this.state.position.active = false;
        logger.info(`[POSITION CLOSED] Position manually closed.`);
    } catch (e) {
        logger.error(`[CLOSE POSITION ERROR] Failed to close position: ${e.message}`);
        this.state.position.active = false;
    }
  }

  async checkVwapExit() {
    if (!this.state.position.active || !this.state.currentVwap) return;

    const { side } = this.state.position;
    const currentPrice = this.state.price;
    const currentVwap = this.state.currentVwap;

    let exitSignal = false;
    if (side === 'BUY' && currentPrice < currentVwap) {
        exitSignal = true;
    } else if (side === 'SELL' && currentPrice > currentVwap) {
        exitSignal = true;
    }

    if (exitSignal) {
        logger.warn(`[VWAP EXIT] Price crossed VWAP (${currentVwap.toFixed(2)}). Closing trade.`);
        await this.closePosition(side);
    }
  }

  async checkTimeStop() {
    if (!this.state.position.active) return;

    const duration = Date.now() - this.state.position.entryTime;
    const maxHoldingDuration = CONFIG.risk?.maxHoldingDuration || 120 * 60 * 1000; 

    if (duration > maxHoldingDuration) {
        logger.warn(`[TIME STOP] Position held too long (${(duration / 60000).toFixed(1)}m). Closing trade.`);
        await this.closePosition(this.state.position.side);
    }
  }

  async start() {
    await this.warmUp();

    const topics = [
      `kline.${CONFIG.intervals.main}.${CONFIG.symbol}`,
      `kline.${CONFIG.intervals.scalping || '1'}.${CONFIG.symbol}`,
      `orderbook.50.${CONFIG.symbol}`
    ];

    this.ws.subscribeV5(topics, 'linear');
    this.ws.subscribeV5(['execution', 'position'], 'private');

    setInterval(() => this.refreshEquity(), 300000);
    setInterval(() => { 
        const s = this.state.stats;
        const wr = s.trades > 0 ? (s.wins / s.trades * 100).toFixed(1) : 0;
        const dd = this.state.maxEquity > 0 ? ((1 - this.state.equity / this.state.maxEquity) * 100).toFixed(2) : 0;
        logger.info(`[STATS v3.1] Trades: ${s.trades} | Win Rate: ${wr}% | PnL: $${s.totalPnl.toFixed(2)} | DD: ${dd}%`);
    }, 600000);

    // --- KLINE WS HANDLER (Streaming Decisions) ---
    this.ws.on('update', async (data) => {
      if (!data?.data || !data.topic) return;

      if (data.topic === 'execution') {
          for (const exec of data.data) {
              if (exec.execType === 'Trade' && exec.closedSize && parseFloat(exec.closedSize) > 0) {
                  const pnl = parseFloat(exec.execPnl || 0);
                  this.state.stats.totalPnl += pnl;
                  this.state.stats.trades++;

                  if (pnl > 0) {
                      this.state.consecutiveLosses = 0;
                      this.state.stats.wins++;
                      logger.success(`[TRADE] WIN: +$${pnl.toFixed(2)}`);
                  } else {
                      this.state.consecutiveLosses++;
                      logger.warn(`[TRADE] LOSS: $${pnl.toFixed(2)}`);
                  }
              }
          }
      }

      if (data.topic === 'position') {
          for (const p of data.data) {
              if (p.symbol === CONFIG.symbol) {
                  this.state.pnl = parseFloat(p.unrealisedPnl || 0);
                  break;
              }
          }
      }

      if (data.topic?.startsWith('orderbook')) {
          const frame = Array.isArray(data.data) ? data.data[0] : data.data;
          const type = data.type ? data.type : (this.book.ready ? 'delta' : 'snapshot');
          this.updateOrderbook({ type, b: frame.b, a: frame.a });
      }

      // Main kline handler (triggers decision logic)
      const klineTopic = CONFIG.intervals.main;
      if (data.topic?.includes(`kline.${klineTopic}.`)) {
          const k = data.data[0]; 
          if (!k.open || !k.close) return;
          
          this.state.price = parseFloat(k.close);
          const metrics = this.book.getAnalysis();
          const skewColor = metrics.skew > 0 ? C.neonGreen : C.neonRed;

          // Live terminal update
          process.stdout.write(`\r${C.dim}[v3.1 ${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price.toFixed(2)} | PnL: ${this.state.pnl.toFixed(2)} | Skew: ${skewColor}${metrics.skew.toFixed(2)}%${C.reset} | Wall: ${metrics.wallStatus}   `);

          if (k.confirm) { 
            process.stdout.write('\n'); 
            this.oracle.updateKline({ 
              open: D(k.open), high: D(k.high), low: D(k.low), 
              close: D(k.close), volume: D(k.volume) 
            });
            
            this.state.currentVwap = this.oracle.buildContext(metrics)?.vwap || 0;
            const signal = await this.oracle.divine(metrics);
            
            if (signal.action !== 'HOLD') {
              await this.placeMakerOrder(signal);
            }
            await this.checkExitConditions();
          }
      }
    });

    logger.success(`🦈 LEVIATHAN v${VERSION} HUNTING ${CONFIG.symbol}`);
  }
}

// --- EXPORTS + CLI READY ---
module.exports = { LeviathanEngine, VERSION, CONFIG };

if (require.main === module) {
  (async () => {
    const engine = new LeviathanEngine();
    await engine.start();
  })().catch(e => {
    logger.error('[FATAL_LAUNCH] System failed to start', { error: e.message, stack: e.stack });
    process.exit(1);
  });
}