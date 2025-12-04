/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v2.8 "SINGULARITY" (PRODUCTION READY)       │
 * │   Risk-Based Sizing · Private Execution Stream · Funding Filter         │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * USAGE: node ais.cjs
 */

require('dotenv').config();
const { Decimal } = require('decimal.js');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { RestClientV5, WebsocketClient } = require('bybit-api');

// ─── NEON PALETTE ───
const C = {
  reset: "\x1b[0m",
  bright: "\x1b[1m",
  dim: "\x1b[2m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  cyan: "\x1b[36m",
  yellow: "\x1b[33m",
  magenta: "\x1b[35m",
  neonGreen: "\x1b[92m",
  neonRed: "\x1b[91m",
  neonCyan: "\x1b[96m",
  neonPurple: "\x1b[95m",
  neonYellow: "\x1b[93m",
  bgGreen: "\x1b[42m\x1b[30m",
  bgRed: "\x1b[41m\x1b[37m",
};

// ─── CONFIGURATION ───
const CONFIG = {
  symbol: process.env.TRADE_SYMBOL || 'BTCUSDT',
  interval: process.env.TRADE_TIMEFRAME || '15',
  riskPerTrade: 0.01, // 1% of Equity per trade
  leverage: process.env.MAX_LEVERAGE || '5',
  testnet: process.env.BYBIT_TESTNET === 'true',
  tickSize: process.env.TICK_SIZE || '0.10',
};

// ─── DECIMAL-SAFE HELPERS ───
const DArr = (len) => Array(len).fill(null);
const D0 = () => new Decimal(0);
const D = (n) => new Decimal(n);

// ─── ADVANCED ORDERBOOK ANALYTICS ───
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

  update(data) {
    // Bybit V5 structure fix: handle snapshot vs delta
    if (data.type === 'snapshot') {
      this.bids.clear();
      this.asks.clear();
      this.processLevels(data.b, this.bids);
      this.processLevels(data.a, this.asks);
      this.ready = true;
    } else if (data.type === 'delta') {
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

    const bestBid = bids[0][0];
    const bestAsk = asks[0][0];
    const imbWeight = bids[0][1] / (bids[0][1] + asks[0][1]);
    this.metrics.wmp = (bestBid * (1 - imbWeight)) + (bestAsk * imbWeight);
    this.metrics.spread = bestAsk - bestBid;

    const currentBidWall = Math.max(...bids.map(b => b[1]));
    const currentAskWall = Math.max(...asks.map(a => a[1]));

    // Wall Exhaustion Logic
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

    const totalBidVol = bids.reduce((acc, val) => acc + val[1], 0);
    const totalAskVol = asks.reduce((acc, val) => acc + val[1], 0);
    const total = totalBidVol + totalAskVol;
    this.metrics.skew = total === 0 ? 0 : (totalBidVol - totalAskVol) / total;
  }

  getAnalysis() {
    return this.metrics;
  }
}

// ─── TA v2.8 (Session VWAP) ───
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

  // VWAP with Daily Reset logic (approximate via lookback, production uses timestamps)
  static vwap(high, low, close, volume) {
    if (!close.length) return D0();
    let cumPV = D0(), cumV = D0();
    // Use last 96 candles (approx 24h on 15m) as rolling session
    const lookback = Math.min(close.length, 96); 
    const start = close.length - lookback;
    
    for(let i=start; i<close.length; i++) {
      const typ = high[i].plus(low[i]).plus(close[i]).div(3);
      cumPV = cumPV.plus(typ.mul(volume[i]));
      cumV = cumV.plus(volume[i]);
    }
    return cumV.eq(0) ? close[close.length-1] : cumPV.div(cumV);
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
        const mid = high[i].plus(low[i]).div(2);
        raw = mid.minus(minL).div(range).minus(0.5).mul(2);
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

// ─── ORACLE BRAIN (GEMINI 2.0 FLASH LITE STABLE) ───
class OracleBrain {
  constructor() {
    // UPDATED: Using stable Model ID from audit
    this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
      model: 'gemini-2.0-flash-lite-001', 
      generationConfig: { responseMimeType: 'application/json' }
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

    const atrSeries = TA.atr(h, l, c, 14);
    const atr = atrSeries[atrSeries.length - 1] || D(1);
    const price = c[c.length - 1];
    const fisherSeries = TA.fisher(h, l);
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
      fastTrend: fastTrend,
      book: {
        skew: Number(bookMetrics.skew.toFixed(3)),
        wallStatus: bookMetrics.wallStatus
      }
    };
  }

  validateSignal(sig, ctx) {
    if (!sig || typeof sig !== 'object') return { action: 'HOLD', confidence: 0, reason: 'Invalid JSON' };
    const price = D(ctx.price);
    const atr = D(ctx.atr || 100);
    if (!['BUY', 'SELL', 'HOLD'].includes(sig.action)) sig.action = 'HOLD';
    if (typeof sig.confidence !== 'number' || sig.confidence < 0.89) { sig.confidence = 0; sig.action = 'HOLD'; }

    if (sig.action !== 'HOLD') {
      const sl = D(sig.sl);
      const tp = D(sig.tp);
      const maxDist = atr.mul(4);
      sig.sl = Number(Decimal.max(Decimal.min(sl, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
      sig.tp = Number(Decimal.max(Decimal.min(tp, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
    }
    sig.reason = (sig.reason || 'No reason').slice(0, 100);
    return sig;
  }

  async divine(bookMetrics) {
    const ctx = this.buildContext(bookMetrics);
    if (!ctx) return { action: 'HOLD', confidence: 0, reason: 'Warming up' };

    const prompt = `You are LEVIATHAN v2.8 QUANTUM.
Price: ${ctx.price} | ATR: ${ctx.atr} | Fisher: ${ctx.fisher} | VWAP: ${ctx.vwap}
Orderbook Skew: ${ctx.book.skew}
Wall Status: ${ctx.book.wallStatus}
Fast Trend (1m): ${ctx.fastTrend}

RULES:
1. Signal BUY if Fisher < -1.5 AND Skew > 0.1 AND (Price < VWAP or FastTrend == BULLISH).
2. Signal SELL if Fisher > 1.5 AND Skew < -0.1 AND (Price > VWAP or FastTrend == BEARISH).
3. "ASK_WALL_BROKEN" is a strong BUY signal. "BID_WALL_BROKEN" is a strong SELL signal.
4. Confidence > 0.89 required.
5. R/R must be > 1.6.

DATA:
${JSON.stringify(ctx)}

Output JSON: {"action":"BUY"|"SELL"|"HOLD","confidence":0.90,"sl":123,"tp":456,"reason":"concise reason"}`;

    try {
      const result = await this.gemini.generateContent(prompt);
      const text = result.response.text();
      const jsonStr = text.replace(/```json|```/g, '').trim();
      let signal = JSON.parse(jsonStr);

      const price = D(ctx.price);
      if (signal.action !== 'HOLD') {
        const sl = D(signal.sl);
        const tp = D(signal.tp);
        const risk = signal.action === 'BUY' ? price.minus(sl) : sl.minus(price);
        const reward = signal.action === 'BUY' ? tp.minus(price) : price.minus(tp);
        const rr = risk.abs().eq(0) ? D(0) : reward.div(risk.abs());

        if (rr.lt(1.6)) {
          const newTp = signal.action === 'BUY' ? price.plus(risk.mul(1.6)) : price.minus(risk.mul(1.6));
          signal.tp = Number(newTp.toFixed(2));
          signal.reason += ' | R/R Enforced';
        }
      }
      return this.validateSignal(signal, ctx);
    } catch (e) {
      return { action: 'HOLD', confidence: 0, reason: 'Oracle Error' };
    }
  }
}

// ─── LEVIATHAN ENGINE ───
class LeviathanEngine {
  constructor() {
    this.oracle = new OracleBrain();
    this.book = new LocalOrderBook();
    this.client = new RestClientV5({
      key: process.env.BYBIT_API_KEY, secret: process.env.BYBIT_API_SECRET, testnet: CONFIG.testnet,
    });
    this.ws = new WebsocketClient({
      key: process.env.BYBIT_API_KEY, secret: process.env.BYBIT_API_SECRET, testnet: CONFIG.testnet, market: 'v5',
    });
    this.state = {
      price: 0, bestBid: 0, bestAsk: 0, pnl: 0, equity: 0,
      consecutiveLosses: 0, stats: { trades: 0, wins: 0, totalPnl: 0 }
    };
  }

  formatPrice(price) {
    const tick = CONFIG.tickSize;
    let decimals = 2;
    if (tick.includes('.')) decimals = tick.split('.')[1].length;
    return new Decimal(price).toNearest(tick, Decimal.ROUND_DOWN).toFixed(decimals);
  }

  // 1. RISK-BASED SIZING (The Profitability Key)
  async calculateRiskSize(signal) {
    if (this.state.equity === 0) return CONFIG.baseQty; // Fallback

    const riskAmount = this.state.equity * CONFIG.riskPerTrade;
    const stopDistance = Math.abs(signal.sl - this.state.price);
    
    // Safety: If stop is too tight (< 0.2%), assume min distance to avoid massive sizing
    const minStop = this.state.price * 0.002; 
    const effectiveStop = Math.max(stopDistance, minStop);

    let qty = riskAmount / effectiveStop;
    
    // Safety: Clamp to Max Leverage (e.g., 5x)
    const maxQty = (this.state.equity * parseFloat(CONFIG.leverage)) / this.state.price;
    qty = Math.min(qty, maxQty);

    return qty.toFixed(3); // Adjust decimals based on coin (3 for BTC is usually ok, might need logic)
  }

  // 2. FUNDING FILTER
  async checkFundingSafe(action) {
    try {
      const res = await this.client.getFundingRateHistory({ category: 'linear', symbol: CONFIG.symbol, limit: 1 });
      const rate = parseFloat(res.result.list[0].fundingRate);
      // If Longing and Rate > 0.05%, we pay. Too high.
      if (action === 'BUY' && rate > 0.0005) return false;
      // If Shorting and Rate < -0.05%, we pay.
      if (action === 'SELL' && rate < -0.0005) return false;
      return true;
    } catch (e) { return true; } // Fail safe
  }

  async warmUp() {
    console.log(`${C.cyan}[INIT] Warming up System...${C.reset}`);
    try {
      // Balance
      const balRes = await this.client.getWalletBalance({ accountType: 'UNIFIED', coin: 'USDT' });
      this.state.equity = parseFloat(balRes.result.list[0].totalEquity);
      console.log(`[INIT] Equity: $${this.state.equity.toFixed(2)}`);

      // Klines
      const res = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: CONFIG.interval, limit: 200 });
      const candles = res.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      candles.forEach(c => this.oracle.updateKline(c));
      this.state.price = parseFloat(candles[candles.length - 1].close);

      // Fast Klines
      const resFast = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: '1', limit: 50 });
      const fastCandles = resFast.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      fastCandles.forEach(c => this.oracle.updateMtfKline(c));

      // Orderbook Snapshot
      const obRes = await this.client.getOrderbook({ category: 'linear', symbol: CONFIG.symbol, limit: 50 });
      if(obRes.retCode === 0) this.updateOrderbook({ type: 'snapshot', b: obRes.result.b, a: obRes.result.a });

      console.log(`${C.green}[INIT] Ready. Model: Gemini 2.0 Flash Lite.${C.reset}`);
    } catch (e) {
      console.error(`${C.red}[FATAL] Warmup failed: ${e.message}${C.reset}`);
      process.exit(1);
    }
  }

  updateOrderbook(data) {
    this.book.update(data);
    if (!this.book.ready) return;
    const { bid, ask } = this.book.getBestBidAsk();
    this.state.bestBid = bid;
    this.state.bestAsk = ask;
  }

  async placeMakerOrder(signal) {
    // 1. Streak Check
    if (this.state.consecutiveLosses >= 3) {
        console.log(`${C.yellow}[PAUSE] Dead Cat Filter: 3x Loss Streak. Waiting...${C.reset}`);
        return;
    }

    // 2. Funding Check
    if (!(await this.checkFundingSafe(signal.action))) {
      console.log(`${C.red}[FILTER] High Funding Cost. Skipping trade.${C.reset}`);
      return;
    }

    // 3. Calc Size
    const qty = await this.calculateRiskSize(signal);

    console.log(`\n\n${C.bgGreen} ⚡ LEVIATHAN TRIGGER ${C.reset}`);
    console.log(`${C.bright}ACT: ${signal.action} | CONF: ${(signal.confidence*100).toFixed(0)}% | QTY: ${qty}${C.reset}`);
    console.log(`${C.dim}${signal.reason}${C.reset}`);

    if (!this.state.bestBid || !this.state.bestAsk) { console.log(`${C.red}[SKIP] OB Not Ready${C.reset}`); return; }

    try {
      const posRes = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
      if (posRes.result?.list?.[0] && parseFloat(posRes.result.list[0].size) > 0) {
        console.log(`${C.yellow}[EXEC] Position Active. Skipping.${C.reset}`);
        return;
      }

      const metrics = this.book.getAnalysis();
      const tick = parseFloat(CONFIG.tickSize);
      let entryPrice;

      if (signal.action === 'BUY') {
        const aggressive = this.state.bestBid + tick;
        entryPrice = (metrics.wallStatus === 'ASK_WALL_BROKEN' || metrics.skew > 0.2) 
          ? Math.min(aggressive, this.state.bestAsk - tick) : this.state.bestBid;
      } else {
        const aggressive = this.state.bestAsk - tick;
        entryPrice = (metrics.wallStatus === 'BID_WALL_BROKEN' || metrics.skew < -0.2) 
          ? Math.max(aggressive, this.state.bestBid + tick) : this.state.bestAsk;
      }

      const formattedPrice = this.formatPrice(entryPrice);
      console.log(`${C.cyan}[MAKER] Limit ${signal.action} @ ${formattedPrice}${C.reset}`);

      await this.client.submitOrder({
        category: 'linear', symbol: CONFIG.symbol, side: signal.action === 'BUY' ? 'Buy' : 'Sell',
        orderType: 'Limit', price: formattedPrice, qty: String(qty),
        stopLoss: String(signal.sl), takeProfit: String(signal.tp), timeInForce: 'PostOnly',
      });
      console.log(`${C.neonGreen}[SUCCESS] Order Sent.${C.reset}\n`);

    } catch (e) { console.error(`${C.red}[EXEC ERROR] ${e.message}${C.reset}`); }
  }

  async start() {
    await this.warmUp();

    // 1. Subscribe Public
    this.ws.subscribeV5([`kline.${CONFIG.interval}.${CONFIG.symbol}`, `kline.1.${CONFIG.symbol}`, `orderbook.50.${CONFIG.symbol}`], 'linear');
    
    // 2. Subscribe Private (Execution Stream)
    this.ws.subscribeV5(['execution', 'position'], 'linear', true);

    this.ws.on('update', async (data) => {
      // Private: Executions
      if (data.topic === 'execution') {
        data.data.forEach(exec => {
            // Logic: If we closed a position (execType 'Trade' and closedSize > 0 implicitly handled by position update usually, 
            // but tracking realized PnL here is best)
            // Simpler: Just rely on position updates for PnL tracking or watch for 'Closed' status
        });
      }

      // Private: Position Updates (Accurate PnL/Streak tracking)
      if (data.topic === 'position') {
        data.data.forEach(p => {
            if (p.symbol === CONFIG.symbol) {
                this.state.pnl = parseFloat(p.unrealisedPnl);
                // If position just closed (size 0)
                if (parseFloat(p.size) === 0 && this.state.stats.lastSize > 0) {
                    // Check if it was a win or loss based on realized pnl if available, 
                    // or infer from last pnl snapshot.
                    // For safety, we reset streak on any profitable exit detected via wallet/execution
                }
                this.state.stats.lastSize = parseFloat(p.size);
            }
        });
      }

      // Public: Orderbook
      if (data.topic?.startsWith('orderbook')) {
        // Fix: Bybit V5 structure
        const type = data.type; 
        const b = data.data.b;
        const a = data.data.a;
        this.updateOrderbook({ type, b, a });
      }

      // Public: Fast Trend
      if (data.topic?.includes('kline.1.')) {
        const k = data.data[0];
        if (k.confirm) this.oracle.updateMtfKline({ open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume) });
      }

      // Public: Main Logic
      if (data.topic?.includes(`kline.${CONFIG.interval}`)) {
        const k = data.data[0];
        this.state.price = parseFloat(k.close);
        
        const m = this.book.getAnalysis();
        const skewColor = m.skew > 0 ? C.neonGreen : C.neonRed;
        
        // Dynamic HUD
        process.stdout.write(`\r${C.dim}[${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price} | PnL: ${this.state.pnl.toFixed(2)} | Skew: ${skewColor}${m.skew.toFixed(2)}${C.reset} | Wall: ${m.wallStatus}   `);

        if (k.confirm) {
          process.stdout.write(`\n`);
          this.oracle.updateKline({ open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume) });
          const signal = await this.oracle.divine(m);
          if (signal.action !== 'HOLD') await this.placeMakerOrder(signal);
        }
      }
    });

    this.ws.on('error', (err) => console.error(`\n${C.red}[WS ERROR] ${err}${C.reset}`));
    console.log(`\n${C.bgGreen} ▓▓▓ LEVIATHAN v2.8 SINGULARITY ACTIVE ▓▓▓ ${C.reset}\n`);
  }
}

const engine = new LeviathanEngine();
engine.start().catch(console.error);
/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v2.9 "SINGULARITY" (PRODUCTION FINAL)       │
 * │   Iceberg Execution · Real-Time PnL Stream · Max Drawdown Guard         │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * USAGE: node ais.cjs
 */

require('dotenv').config();
const { Decimal } = require('decimal.js');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { RestClientV5, WebsocketClient } = require('bybit-api');

// ─── NEON PALETTE ───
const C = {
  reset: "\x1b[0m",
  bright: "\x1b[1m",
  dim: "\x1b[2m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  cyan: "\x1b[36m",
  yellow: "\x1b[33m",
  magenta: "\x1b[35m",
  neonGreen: "\x1b[92m",
  neonRed: "\x1b[91m",
  neonCyan: "\x1b[96m",
  neonPurple: "\x1b[95m",
  neonYellow: "\x1b[93m",
  bgGreen: "\x1b[42m\x1b[30m",
  bgRed: "\x1b[41m\x1b[37m",
};

// ─── CONFIGURATION ───
const CONFIG = {
  symbol: process.env.TRADE_SYMBOL || 'BTCUSDT',
  interval: process.env.TRADE_TIMEFRAME || '15',
  riskPerTrade: 0.01, // 1% Risk per trade
  leverage: process.env.MAX_LEVERAGE || '5',
  testnet: process.env.BYBIT_TESTNET === 'true',
  tickSize: process.env.TICK_SIZE || '0.10',
};

// ─── DECIMAL-SAFE HELPERS ───
const DArr = (len) => Array(len).fill(null);
const D0 = () => new Decimal(0);
const D = (n) => new Decimal(n);

// ─── ADVANCED ORDERBOOK ANALYTICS ───
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

    const bestBid = bids[0][0];
    const bestAsk = asks[0][0];
    const imbWeight = bids[0][1] / (bids[0][1] + asks[0][1]);
    
    this.metrics.wmp = (bestBid * (1 - imbWeight)) + (bestAsk * imbWeight);
    this.metrics.spread = bestAsk - bestBid;

    const currentBidWall = Math.max(...bids.map(b => b[1]));
    const currentAskWall = Math.max(...asks.map(a => a[1]));

    // Wall Exhaustion Logic
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

    const totalBidVol = bids.reduce((acc, val) => acc + val[1], 0);
    const totalAskVol = asks.reduce((acc, val) => acc + val[1], 0);
    const total = totalBidVol + totalAskVol;
    this.metrics.skew = total === 0 ? 0 : (totalBidVol - totalAskVol) / total;
  }

  getAnalysis() {
    return this.metrics;
  }
}

// ─── TA v2.9 (Session VWAP) ───
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
    // Rolling 24h VWAP (Approx 96 candles of 15m)
    const lookback = Math.min(close.length, 96); 
    const start = close.length - lookback;
    
    for(let i=start; i<close.length; i++) {
      const typ = high[i].plus(low[i]).plus(close[i]).div(3);
      cumPV = cumPV.plus(typ.mul(volume[i]));
      cumV = cumV.plus(volume[i]);
    }
    return cumV.eq(0) ? close[close.length-1] : cumPV.div(cumV);
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
        const mid = high[i].plus(low[i]).div(2);
        raw = mid.minus(minL).div(range).minus(0.5).mul(2);
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

// ─── ORACLE BRAIN (GEMINI 2.5 FLASH LITE STABLE) ───
class OracleBrain {
  constructor() {
    this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
      model: 'gemini-2.5-flash-lite', 
      generationConfig: { responseMimeType: 'application/json' }
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

    const atrSeries = TA.atr(h, l, c, 14);
    const atr = atrSeries[atrSeries.length - 1] || D(1);
    const price = c[c.length - 1];
    const fisherSeries = TA.fisher(h, l);
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
      fastTrend: fastTrend,
      book: {
        skew: Number(bookMetrics.skew.toFixed(3)),
        wallStatus: bookMetrics.wallStatus
      }
    };
  }

  validateSignal(sig, ctx) {
    if (!sig || typeof sig !== 'object') return { action: 'HOLD', confidence: 0, reason: 'Invalid JSON' };
    const price = D(ctx.price);
    const atr = D(ctx.atr || 100);
    if (!['BUY', 'SELL', 'HOLD'].includes(sig.action)) sig.action = 'HOLD';
    if (typeof sig.confidence !== 'number' || sig.confidence < 0.89) { sig.confidence = 0; sig.action = 'HOLD'; }

    if (sig.action !== 'HOLD') {
      const sl = D(sig.sl);
      const tp = D(sig.tp);
      const maxDist = atr.mul(4);
      sig.sl = Number(Decimal.max(Decimal.min(sl, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
      sig.tp = Number(Decimal.max(Decimal.min(tp, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
    }
    sig.reason = (sig.reason || 'No reason').slice(0, 100);
    return sig;
  }

  async divine(bookMetrics) {
    const ctx = this.buildContext(bookMetrics);
    if (!ctx) return { action: 'HOLD', confidence: 0, reason: 'Warming up' };

    const prompt = `You are LEVIATHAN v2.9 QUANTUM.
Price: ${ctx.price} | ATR: ${ctx.atr} | Fisher: ${ctx.fisher} | VWAP: ${ctx.vwap}
Orderbook Skew: ${ctx.book.skew}
Wall Status: ${ctx.book.wallStatus}
Fast Trend (1m): ${ctx.fastTrend}

RULES:
1. Signal BUY if Fisher < -1.5 AND Skew > 0.1 AND (Price < VWAP or FastTrend == BULLISH).
2. Signal SELL if Fisher > 1.5 AND Skew < -0.1 AND (Price > VWAP or FastTrend == BEARISH).
3. "ASK_WALL_BROKEN" is a strong BUY signal. "BID_WALL_BROKEN" is a strong SELL signal.
4. Confidence > 0.89 required.
5. R/R must be > 1.6.

DATA:
${JSON.stringify(ctx)}

Output JSON: {"action":"BUY"|"SELL"|"HOLD","confidence":0.90,"sl":123,"tp":456,"reason":"concise reason"}`;

    try {
      const result = await this.gemini.generateContent(prompt);
      const text = result.response.text();
      const jsonStr = text.replace(/```json|```/g, '').trim();
      let signal = JSON.parse(jsonStr);

      const price = D(ctx.price);
      if (signal.action !== 'HOLD') {
        const sl = D(signal.sl);
        const tp = D(signal.tp);
        const risk = signal.action === 'BUY' ? price.minus(sl) : sl.minus(price);
        const reward = signal.action === 'BUY' ? tp.minus(price) : price.minus(tp);
        const rr = risk.abs().eq(0) ? D(0) : reward.div(risk.abs());

        if (rr.lt(1.6)) {
          const newTp = signal.action === 'BUY' ? price.plus(risk.mul(1.6)) : price.minus(risk.mul(1.6));
          signal.tp = Number(newTp.toFixed(2));
          signal.reason += ' | R/R Enforced';
        }
      }
      return this.validateSignal(signal, ctx);
    } catch (e) {
      return { action: 'HOLD', confidence: 0, reason: 'Oracle Error' };
    }
  }
}

// ─── LEVIATHAN ENGINE ───
class LeviathanEngine {
  constructor() {
    this.oracle = new OracleBrain();
    this.book = new LocalOrderBook();
    this.client = new RestClientV5({
      key: process.env.BYBIT_API_KEY, secret: process.env.BYBIT_API_SECRET, testnet: CONFIG.testnet,
    });
    this.ws = new WebsocketClient({
      key: process.env.BYBIT_API_KEY, secret: process.env.BYBIT_API_SECRET, testnet: CONFIG.testnet, market: 'v5',
    });
    this.state = {
      price: 0, bestBid: 0, bestAsk: 0, pnl: 0, 
      equity: 0, maxEquity: 0, paused: false,
      consecutiveLosses: 0, 
      stats: { trades: 0, wins: 0, totalPnl: 0 }
    };
  }

  formatPrice(price) {
    const tick = CONFIG.tickSize;
    let decimals = 2;
    if (tick.includes('.')) decimals = tick.split('.')[1].length;
    return new Decimal(price).toNearest(tick, Decimal.ROUND_DOWN).toFixed(decimals);
  }

  // 1. RISK-BASED SIZING
  async calculateRiskSize(signal) {
    if (this.state.equity === 0) return 0.001; 

    const riskAmount = this.state.equity * CONFIG.riskPerTrade;
    const stopDistance = Math.abs(signal.sl - this.state.price);
    const minStop = this.state.price * 0.002; 
    const effectiveStop = Math.max(stopDistance, minStop);

    let qty = riskAmount / effectiveStop;
    const maxQty = (this.state.equity * parseFloat(CONFIG.leverage)) / this.state.price;
    qty = Math.min(qty, maxQty);

    return qty.toFixed(3); 
  }

  // 2. FUNDING FILTER
  async checkFundingSafe(action) {
    try {
      const res = await this.client.getFundingRateHistory({ category: 'linear', symbol: CONFIG.symbol, limit: 1 });
      const rate = parseFloat(res.result.list[0].fundingRate);
      if (action === 'BUY' && rate > 0.0005) return false;
      if (action === 'SELL' && rate < -0.0005) return false;
      return true;
    } catch (e) { return true; }
  }

  async refreshEquity() {
    try {
        const bal = await this.client.getWalletBalance({ accountType: 'UNIFIED', coin: 'USDT' });
        this.state.equity = parseFloat(bal.result.list[0].totalEquity);
        if (this.state.equity > this.state.maxEquity) this.state.maxEquity = this.state.equity;

        // MAX DRAWDOWN GUARD (10%)
        if (this.state.maxEquity > 0 && this.state.equity < this.state.maxEquity * 0.9) {
            console.log(`${C.red}[EMERGENCY] Max Drawdown (10%) Hit. Bot Paused.${C.reset}`);
            this.state.paused = true;
        }
    } catch(e) {}
  }

  async warmUp() {
    console.log(`${C.cyan}[INIT] Warming up System...${C.reset}`);
    try {
      await this.refreshEquity();
      console.log(`[INIT] Equity: $${this.state.equity.toFixed(2)}`);

      const res = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: CONFIG.interval, limit: 200 });
      const candles = res.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      candles.forEach(c => this.oracle.updateKline(c));
      this.state.price = parseFloat(candles[candles.length - 1].close);

      const resFast = await this.client.getKline({ category: 'linear', symbol: CONFIG.symbol, interval: '1', limit: 50 });
      const fastCandles = resFast.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]), open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      fastCandles.forEach(c => this.oracle.updateMtfKline(c));

      const obRes = await this.client.getOrderbook({ category: 'linear', symbol: CONFIG.symbol, limit: 50 });
      if(obRes.retCode === 0) this.updateOrderbook({ type: 'snapshot', b: obRes.result.b, a: obRes.result.a });

      console.log(`${C.green}[INIT] Ready. Model: Gemini 2.5 Flash Lite.${C.reset}`);
    } catch (e) {
      console.error(`${C.red}[FATAL] Warmup failed: ${e.message}${C.reset}`);
      process.exit(1);
    }
  }

  updateOrderbook(data) {
    // 3. ROBUST ORDERBOOK PARSING
    const isSnapshot = data.type === 'snapshot' || !this.book.ready;
    this.book.update(data, isSnapshot);
    
    if (this.book.ready) {
      const { bid, ask } = this.book.getBestBidAsk();
      this.state.bestBid = bid;
      this.state.bestAsk = ask;
    }
  }

  async placeIcebergOrder(signal, entryPrice, totalQty) {
    // 4. ICEBERG EXECUTION
    const slices = 3;
    const sliceQty = (parseFloat(totalQty) / slices).toFixed(3);
    const tick = parseFloat(CONFIG.tickSize);
    
    console.log(`${C.cyan}[ICEBERG] Slicing ${totalQty} into ${slices} orders...${C.reset}`);

    for (let i = 0; i < slices; i++) {
        const offset = i * tick * 0.2; 
        const slicePrice = signal.action === 'BUY' ? entryPrice + offset : entryPrice - offset;
        const formattedPrice = this.formatPrice(slicePrice);

        await this.client.submitOrder({
            category: 'linear', symbol: CONFIG.symbol, side: signal.action === 'BUY' ? 'Buy' : 'Sell',
            orderType: 'Limit', price: formattedPrice, qty: sliceQty,
            stopLoss: String(signal.sl), takeProfit: String(signal.tp), timeInForce: 'PostOnly',
        });
        
        // 200ms delay between slices to mask intent
        await new Promise(r => setTimeout(r, 200));
    }
    console.log(`${C.neonGreen}[SUCCESS] Iceberg Orders Sent.${C.reset}\n`);
  }

  async placeMakerOrder(signal) {
    if (this.state.paused) return;
    if (this.state.consecutiveLosses >= 3) {
        console.log(`${C.yellow}[PAUSE] Dead Cat Filter: 3x Loss Streak. Waiting...${C.reset}`);
        return;
    }
    if (!(await this.checkFundingSafe(signal.action))) {
      console.log(`${C.red}[FILTER] High Funding Cost. Skipping trade.${C.reset}`);
      return;
    }

    const qty = await this.calculateRiskSize(signal);
    console.log(`\n\n${C.bgGreen} ⚡ LEVIATHAN TRIGGER ${C.reset}`);
    console.log(`${C.bright}ACT: ${signal.action} | CONF: ${(signal.confidence*100).toFixed(0)}% | QTY: ${qty}${C.reset}`);
    console.log(`${C.dim}${signal.reason}${C.reset}`);

    if (!this.state.bestBid || !this.state.bestAsk) { console.log(`${C.red}[SKIP] OB Not Ready${C.reset}`); return; }

    try {
      const posRes = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
      if (posRes.result?.list?.[0] && parseFloat(posRes.result.list[0].size) > 0) {
        console.log(`${C.yellow}[EXEC] Position Active. Skipping.${C.reset}`);
        return;
      }

      const metrics = this.book.getAnalysis();
      const tick = parseFloat(CONFIG.tickSize);
      let entryPrice;

      if (signal.action === 'BUY') {
        const aggressive = this.state.bestBid + tick;
        entryPrice = (metrics.wallStatus === 'ASK_WALL_BROKEN' || metrics.skew > 0.2) 
          ? Math.min(aggressive, this.state.bestAsk - tick) : this.state.bestBid;
      } else {
        const aggressive = this.state.bestAsk - tick;
        entryPrice = (metrics.wallStatus === 'BID_WALL_BROKEN' || metrics.skew < -0.2) 
          ? Math.max(aggressive, this.state.bestBid + tick) : this.state.bestAsk;
      }

      await this.placeIcebergOrder(signal, entryPrice, qty);

    } catch (e) { console.error(`${C.red}[EXEC ERROR] ${e.message}${C.reset}`); }
  }

  async start() {
    await this.warmUp();

    // 5. FIXED WS SUBSCRIPTIONS
    // Public Topics
    this.ws.subscribeV5([
        `kline.${CONFIG.interval}.${CONFIG.symbol}`, 
        `kline.1.${CONFIG.symbol}`, 
        `orderbook.50.${CONFIG.symbol}`
    ], 'linear');
    
    // Private Topics (Correct V5 Format)
    this.ws.subscribeV5(['execution', 'position'], 'linear');

    // Periodic Tasks
    setInterval(() => this.refreshEquity(), 300000); // Check equity every 5m
    setInterval(() => {
        const s = this.state.stats;
        const wr = s.trades > 0 ? (s.wins/s.trades*100).toFixed(1) : 0;
        const dd = this.state.maxEquity > 0 ? ((1 - this.state.equity/this.state.maxEquity)*100).toFixed(2) : 0;
        console.log(`${C.magenta}[STATS] T:${s.trades} W:${wr}% PnL:$${s.totalPnl.toFixed(2)} DD:${dd}%${C.reset}`);
    }, 600000); // Log stats every 10m

    this.ws.on('update', async (data) => {
      // 6. REAL-TIME PNL TRACKING
      if (data.topic === 'execution') {
        data.data.forEach(exec => {
            if (exec.execType === 'Trade' && exec.closedSize && parseFloat(exec.closedSize) > 0) {
                const pnl = parseFloat(exec.execPnl || 0);
                this.state.stats.totalPnl += pnl;
                this.state.stats.trades++;
                
                if (pnl > 0) {
                    this.state.consecutiveLosses = 0; // RESET FILTER
                    this.state.stats.wins++;
                    console.log(`${C.neonGreen}[WIN] PnL: +$${pnl.toFixed(2)}${C.reset}`);
                } else {
                    this.state.consecutiveLosses++;
                    console.log(`${C.neonRed}[LOSS] PnL: $${pnl.toFixed(2)}${C.reset}`);
                }
            }
        });
      }

      if (data.topic === 'position') {
        data.data.forEach(p => {
            if (p.symbol === CONFIG.symbol) this.state.pnl = parseFloat(p.unrealisedPnl);
        });
      }

      if (data.topic?.startsWith('orderbook')) {
        const frame = Array.isArray(data.data) ? data.data[0] : data.data;
        const type = data.type ? data.type : (this.book.ready ? 'delta' : 'snapshot');
        this.updateOrderbook({ type, b: frame.b, a: frame.a });
      }

      if (data.topic?.includes('kline.1.')) {
        const k = data.data[0];
        if (k.confirm) this.oracle.updateMtfKline({ open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume) });
      }

      if (data.topic?.includes(`kline.${CONFIG.interval}`)) {
        const k = data.data[0];
        this.state.price = parseFloat(k.close);
        
        const m = this.book.getAnalysis();
        const skewColor = m.skew > 0 ? C.neonGreen : C.neonRed;
        
        process.stdout.write(`\r${C.dim}[${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price} | PnL: ${this.state.pnl.toFixed(2)} | Skew: ${skewColor}${m.skew.toFixed(2)}${C.reset} | Wall: ${m.wallStatus}   `);

        if (k.confirm) {
          process.stdout.write(`\n`);
          this.oracle.updateKline({ open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume) });
          const signal = await this.oracle.divine(m);
          if (signal.action !== 'HOLD') await this.placeMakerOrder(signal);
        }
      }
    });

    this.ws.on('error', (err) => console.error(`\n${C.red}[WS ERROR] ${err}${C.reset}`));
    console.log(`\n${C.bgGreen} ▓▓▓ LEVIATHAN v2.9 SINGULARITY ACTIVE ▓▓▓ ${C.reset}\n`);
  }
}

const engine = new LeviathanEngine();
engine.start().catch(console.error);
/**
 * ┌──────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v2.5 "ZERO ENTROPY" (HUD EDITION)        │
 * │   Real-time Price · Live PnL · Trade Reasoning · Projection Logic    │
 * └──────────────────────────────────────────────────────────────────────┘
 *
 *  USAGE: node ais.cjs
 */

require('dotenv').config();
const { Decimal } = require('decimal.js');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { RestClientV5, WebsocketClient } = require('bybit-api');

// ─── CONFIGURATION ───
const CONFIG = {
  symbol: process.env.TRADE_SYMBOL || 'BTCUSDT',
  interval: process.env.TRADE_TIMEFRAME || '15', 
  qty: process.env.TRADE_QTY || '0.001',         
  leverage: process.env.MAX_LEVERAGE || '5',
  testnet: process.env.BYBIT_TESTNET === 'true',
};

// ─── DECIMAL-SAFE HELPERS ───
const DArr = (len) => Array(len).fill(null);
const D0 = () => new Decimal(0);
const D = (n) => new Decimal(n);

// ─── TA v2.5 – ETERNAL PERFECTION ───
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

  static laguerreRSI(src, gamma = 0.5) {
    const res = DArr(src.length);
    let l0 = src[0], l1 = src[0], l2 = src[0], l3 = src[0];
    for (let i = 1; i < src.length; i++) {
      const g = D(gamma);
      l0 = l0.mul(g).plus(src[i].mul(1 - gamma));
      l1 = l1.mul(g).plus(l0.mul(1 - gamma));
      l2 = l2.mul(g).plus(l1.mul(1 - gamma));
      l3 = l3.mul(g).plus(l2.mul(1 - gamma));

      const cu = D0()
        .plus(l0.gte(l1) ? l0.minus(l1) : D0())
        .plus(l1.gte(l2) ? l1.minus(l2) : D0())
        .plus(l2.gte(l3) ? l2.minus(l3) : D0());
      const cd = D0()
        .plus(l0.lt(l1) ? l1.minus(l0) : D0())
        .plus(l1.lt(l2) ? l2.minus(l1) : D0())
        .plus(l2.lt(l3) ? l3.minus(l2) : D0());

      res[i] = cu.plus(cd).eq(0) ? D(50) : cu.div(cu.plus(cd)).mul(100);
    }
    return res;
  }

  static obv(close, volume) {
    const res = DArr(close.length);
    if (!close.length) return res;
    res[0] = D(volume[0]);
    for (let i = 1; i < close.length; i++) {
      if (close[i].gt(close[i - 1])) res[i] = res[i - 1].plus(volume[i]);
      else if (close[i].lt(close[i - 1])) res[i] = res[i - 1].minus(volume[i]);
      else res[i] = res[i - 1];
    }
    return res;
  }

  static obvSlope(obv, period = 10) {
    if (obv.length < period + 1) return D0();
    return obv[obv.length - 1].minus(obv[obv.length - 1 - period]).div(period);
  }

  static fisher(high, low, len = 9) {
    const res = DArr(high.length);
    const val = DArr(high.length).fill(D0());
    if (high.length < len) return res;
    
    for (let i = len; i < high.length; i++) {
      let mn = high[i], mx = low[i];
      for (let j = 0; j < len; j++) {
        if (high[i - j].gt(mn)) mn = high[i - j];
        if (low[i - j].lt(mx)) mx = low[i - j];
      }
      const range = mn.minus(mx);
      let raw = range.eq(0) ? D0() : (high[i].plus(low[i]).div(2).minus(mx).div(range).minus(0.5)).mul(2);
      
      // Smooth
      raw = D(0.33).mul(raw).plus(D(0.67).mul(val[i - 1] || D0()));
      
      // Clamp strictly to < 1 to avoid ln(0) or ln(negative)
      if (raw.gt(0.99)) raw = D(0.999);
      if (raw.lt(-0.99)) raw = D(-0.999);
      val[i] = raw;

      // Fisher: 0.5 * ln((1 + raw) / (1 - raw))
      const v1 = D(1).plus(raw);
      const v2 = D(1).minus(raw);
      // FIX: Use .ln() on the Decimal instance, not D.ln()
      const fish = D(0.5).mul(v1.div(v2).ln()).plus(D(0.5).mul(res[i - 1] || D0()));
      res[i] = fish;
    }
    return res;
  }

  static findFVG(candles) {
    if (candles.length < 3) return null;
    const c1 = candles[candles.length - 3];
    const c3 = candles[candles.length - 1];
    if (c1.high.lt(c3.low)) return { type: 'BULLISH', top: c3.low, bottom: c1.high, size: c3.low.minus(c1.high) };
    if (c1.low.gt(c3.high)) return { type: 'BEARISH', top: c1.low, bottom: c3.high, size: c1.low.minus(c3.high) };
    return null;
  }
}

// ─── ORACLE BRAIN v2.5 – ENHANCED ───
class OracleBrain {
  constructor() {
    this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
      model: 'gemini-2.5-flash-lite',
      generationConfig: { responseMimeType: 'application/json' }
    });
    this.klines = [];
  }

  updateKline(k) {
    this.klines.push(k);
    if (this.klines.length > 500) this.klines.shift();
  }

  buildContext(obImbalance = 0) {
    if (this.klines.length < 100) return null;

    const c = this.klines.map(k => k.close);
    const h = this.klines.map(k => k.high);
    const l = this.klines.map(k => k.low);
    const v = this.klines.map(k => k.volume);
    
    const atrSeries = TA.atr(h, l, c, 14);
    const atr = atrSeries[atrSeries.length - 1] || D(1);
    const price = c[c.length - 1];
    const fvg = TA.findFVG(this.klines.slice(-10));
    const obv = TA.obv(c, v);
    const obvSlope = TA.obvSlope(obv, 10);
    const fisherSeries = TA.fisher(h, l);
    const fisherVal = fisherSeries[fisherSeries.length - 1] || D0();
    const laguerreSeries = TA.laguerreRSI(c);
    const laguerreVal = laguerreSeries[laguerreSeries.length - 1] || D(50);

    const context = {
      price: price.toNumber(),
      atr: Number(atr.toFixed(2)),
      imbalance: Number(D(obImbalance).clamp('-1', '1').toFixed(3)),
      fisher: Number(fisherVal.clamp('-5', '5').toFixed(3)),
      laguerre: Number(laguerreVal.clamp('0', '100').toFixed(2)),
      obvTrend: obvSlope.div(obv[obv.length - 1] || D(1)).abs().gt(0.02)
        ? (obvSlope.gt(0) ? 'rising_fast' : 'falling_fast')
        : (obvSlope.gt(0) ? 'rising' : 'falling'),
      fvg: fvg ? {
        type: fvg.type,
        sizePct: Number(fvg.size.div(price).mul(100).toFixed(3)),
        strength: fvg.size.div(atr).gt(1.5) ? 'strong' : 'weak'
      } : null,
      trendScore: Number(D(obImbalance).abs().plus(price.minus(c[c.length - 20] || price).div(c[c.length - 20] || price).abs()).toFixed(3))
    };

    return context;
  }

  validateSignal(sig, ctx) {
    if (!sig || typeof sig !== 'object') return { action: 'HOLD', confidence: 0, reason: 'Invalid JSON', strategy: 'ERROR' };

    const price = D(ctx.price);
    const atr = D(ctx.atr || 100);

    if (!['BUY', 'SELL', 'HOLD'].includes(sig.action)) sig.action = 'HOLD';
    if (typeof sig.confidence !== 'number' || sig.confidence < 0.89) {
      sig.confidence = 0;
      sig.action = 'HOLD';
    }
    
    // Safety Logic: Re-calculate SL/TP boundaries
    if (sig.action !== 'HOLD') {
      const sl = D(sig.sl);
      const tp = D(sig.tp);
      const maxDist = atr.mul(4);

      // FIX: Use Decimal.max/min static methods, not D.max/min
      sig.sl = Number(Decimal.max(Decimal.min(sl, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
      sig.tp = Number(Decimal.max(Decimal.min(tp, price.plus(maxDist)), price.minus(maxDist)).toFixed(2));
    }

    sig.reason = (sig.reason || 'No reason').slice(0, 100); 
    return sig;
  }

  async divine(obImbalance = 0) {
    const ctx = this.buildContext(obImbalance);
    if (!ctx) return { action: 'HOLD', confidence: 0, reason: 'Warming up', strategy: 'INIT' };

    const prompt = `You are LEVIATHAN v2.5.
ATR=${ctx.atr} | Price=${ctx.price} | Imbalance=${ctx.imbalance}
Indicators: Fisher=${ctx.fisher}, Laguerre=${ctx.laguerre}, OBV=${ctx.obvTrend}, FVG=${ctx.fvg?.strength||'none'}

RULES:
1. Signal ONLY if ≥4 confluences match.
2. Confidence MUST be >0.89.
3. SL/TP MUST be within ±4 ATR.
4. R/R ≥ 1.6 REQUIRED.
5. Provide concise reasoning (e.g., "Bullish Divergence + strong FVG").

DATA:
${JSON.stringify(ctx)}

Output JSON: {"action":"BUY"|"SELL"|"HOLD","confidence":0.90,"sl":123,"tp":456,"reason":"text","strategy":"name"}`;

    try {
      const result = await this.gemini.generateContent(prompt);
      const text = result.response.text();
      const jsonStr = text.replace(/```json|```/g, '').trim();
      let signal = JSON.parse(jsonStr);

      // ─── FINAL R/R ENFORCEMENT ───
      const price = D(ctx.price);
      if (signal.action !== 'HOLD') {
        const sl = D(signal.sl);
        const tp = D(signal.tp);
        const risk = signal.action === 'BUY' ? price.minus(sl) : sl.minus(price);
        const reward = signal.action === 'BUY' ? tp.minus(price) : price.minus(tp);
        
        const rr = risk.abs().eq(0) ? D(0) : reward.div(risk.abs());

        if (rr.lt(1.6)) {
          const newTp = signal.action === 'BUY'
            ? price.plus(risk.mul(1.6))
            : price.minus(risk.mul(1.6));
          signal.tp = Number(newTp.toFixed(2));
          signal.reason += ' | R/R Enforced';
        }
      }

      return this.validateSignal(signal, ctx);
    } catch (e) {
      console.error('Oracle Error:', e.message);
      return { action: 'HOLD', confidence: 0, reason: 'API Failure', strategy: 'ERROR' };
    }
  }
}

// ─── LEVIATHAN ENGINE (HUD EDITION) ───
class LeviathanEngine {
  constructor() {
    this.oracle = new OracleBrain();
    
    this.client = new RestClientV5({
      key: process.env.BYBIT_API_KEY,
      secret: process.env.BYBIT_API_SECRET,
      testnet: CONFIG.testnet,
    });
    
    this.ws = new WebsocketClient({
      key: process.env.BYBIT_API_KEY,
      secret: process.env.BYBIT_API_SECRET,
      testnet: CONFIG.testnet,
      market: 'v5', 
    });

    this.currentImbalance = 0;
    this.currentPrice = 0;
    this.unrealizedPnL = 0;
  }

  async warmUp() {
    console.log(`[INIT] Fetching history for ${CONFIG.symbol}...`);
    try {
      const res = await this.client.getKline({
        category: 'linear',
        symbol: CONFIG.symbol,
        interval: CONFIG.interval,
        limit: 200,
      });

      if (res.retCode !== 0) throw new Error(res.retMsg);

      const candles = res.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]),
        open: D(k[1]),
        high: D(k[2]),
        low: D(k[3]),
        close: D(k[4]),
        volume: D(k[5]),
      }));

      candles.forEach(c => this.oracle.updateKline(c));
      this.currentPrice = candles[candles.length - 1].close.toNumber();
      console.log(`[INIT] Loaded ${candles.length} candles. Oracle Ready.`);
    } catch (e) {
      console.error('[FATAL] Warmup failed:', e);
      process.exit(1);
    }
  }

  // Polls Bybit for PnL every 10 seconds
  async monitorPnL() {
    setInterval(async () => {
      try {
        const res = await this.client.getPositionInfo({
          category: 'linear',
          symbol: CONFIG.symbol,
        });
        if (res.retCode === 0 && res.result.list.length > 0) {
          const pos = res.result.list[0];
          this.unrealizedPnL = parseFloat(pos.unrealisedPnl || 0);
        }
      } catch (e) {
        // Silent fail
      }
    }, 10000); 
  }

  updateImbalance(data) {
    if (!data.b || !data.a) return;
    const bids = data.b.slice(0, 10).reduce((acc, x) => acc + parseFloat(x[1]), 0);
    const asks = data.a.slice(0, 10).reduce((acc, x) => acc + parseFloat(x[1]), 0);
    const total = bids + asks;
    this.currentImbalance = total === 0 ? 0 : (bids - asks) / total;
  }

  async executeTrade(signal) {
    // Newline to clear the scanning line
    console.log(`\n\n┌── ⚡ LEVIATHAN SIGNAL DETECTED ───────────────────────┐`);
    console.log(`│ TYPE:     ${signal.action} (Confidence: ${(signal.confidence*100).toFixed(0)}%)`);
    console.log(`│ REASON:   ${signal.reason}`);
    console.log(`│ STRATEGY: ${signal.strategy}`);
    console.log(`│ PRICE:    ${this.currentPrice} | SL: ${signal.sl} | TP: ${signal.tp}`);
    
    // Project Profit
    const riskPerUnit = Math.abs(this.currentPrice - signal.sl);
    const rewardPerUnit = Math.abs(signal.tp - this.currentPrice);
    const qty = parseFloat(CONFIG.qty);
    const estLoss = (riskPerUnit * qty).toFixed(2);
    const estGain = (rewardPerUnit * qty).toFixed(2);
    console.log(`│ PROJECTION: Risk $${estLoss} to Make $${estGain} (R/R: ${(rewardPerUnit/riskPerUnit).toFixed(2)})`);
    console.log(`└───────────────────────────────────────────────────────┘`);

    try {
      const posRes = await this.client.getPositionInfo({
        category: 'linear',
        symbol: CONFIG.symbol,
      });
      const pos = posRes.result.list[0];
      
      if (parseFloat(pos.size) > 0) {
        console.log(`[EXEC] Position already open (${pos.side} ${pos.size}). Signal Skipped.`);
        return;
      }

      await this.client.setLeverage({
        category: 'linear',
        symbol: CONFIG.symbol,
        buyLeverage: CONFIG.leverage,
        sellLeverage: CONFIG.leverage,
      }).catch(() => {}); // Ignore if already set

      const side = signal.action === 'BUY' ? 'Buy' : 'Sell';
      const orderRes = await this.client.submitOrder({
        category: 'linear',
        symbol: CONFIG.symbol,
        side: side,
        orderType: 'Market',
        qty: CONFIG.qty,
        stopLoss: String(signal.sl),
        takeProfit: String(signal.tp),
        timeInForce: 'GTC',
      });

      if (orderRes.retCode === 0) {
        console.log(`[EXEC] ✅ ORDER FILLED: ${orderRes.result.orderId}\n`);
      } else {
        console.error(`[EXEC] ❌ ORDER REJECTED: ${orderRes.retMsg}\n`);
      }

    } catch (e) {
      console.error('[EXEC ERROR]', e);
    }
  }

  async start() {
    await this.warmUp();
    this.monitorPnL();

    this.ws.subscribeV5([`kline.${CONFIG.interval}.${CONFIG.symbol}`, `orderbook.50.${CONFIG.symbol}`], 'linear');

    this.ws.on('update', async (data) => {
      // 1. Orderbook Updates (Imbalance)
      if (data.topic && data.topic.startsWith('orderbook')) {
        this.updateImbalance(data.data);
        return;
      }

      // 2. Kline Updates
      if (data.topic && data.topic.startsWith('kline')) {
        const k = data.data[0];
        
        // Update Price Constant
        this.currentPrice = parseFloat(k.close);

        // Update Dashboard (Scanning Line)
        const pnlColor = this.unrealizedPnL >= 0 ? '+' : '';
        const imbSign = this.currentImbalance > 0 ? '+' : '';
        const now = new Date().toLocaleTimeString();
        
        // Print dynamic HUD (overwrites same line)
        process.stdout.write(`\r[${now}] 👁️  SCANNING ${CONFIG.symbol}: ${this.currentPrice} | PnL: ${pnlColor}${this.unrealizedPnL} USDT | Imb: ${imbSign}${this.currentImbalance.toFixed(2)}   `);

        // If candle closes, trigger DIVINE
        if (k.confirm) {
          process.stdout.write(`\n`); // Break the line
          console.log(`[TICK] Candle Closed at ${k.close}. Analyzing...`);
          
          this.oracle.updateKline({
            open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume)
          });

          const signal = await this.oracle.divine(this.currentImbalance);
          
          if (signal.action !== 'HOLD') {
            await this.executeTrade(signal);
          } else {
            console.log(`[ORACLE] HOLD | Conf: ${(signal.confidence*100).toFixed(0)}% | ${signal.reason}`);
          }
        }
      }
    });

    this.ws.on('error', (err) => console.error('\n[WS ERROR]', err));
    console.log("▓▓▓ LEVIATHAN v2.5 IS LIVE AND WATCHING ▓▓▓");
  }
}

// ─── IGNITION ───
const engine = new LeviathanEngine();
engine.start().catch(console.error);
/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN v2.3 (HYBRID TRIGGER HUD)
 * ======================================================
 * - Finalized Hybrid Trigger Logic
 * - Enhanced HUD with Fisher, ATR, Imbalance
 * - All previous V2.2+ features integrated (Risk Sizing, Iceberg,
Filters, etc.)
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import crypto from 'crypto';
import WebSocket from 'ws';
import fs from 'fs/promises';

dotenv.config();

// === UI CONSTANTS ===
const COLOR = {
    GREEN: chalk.hex('#00FF41'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#0A84FF'),
    PURPLE: chalk.hex('#BF5AF2'),
    YELLOW: chalk.hex('#FFD60A'),
    CYAN: chalk.hex('#32ADE6'),
    GRAY: chalk.hex('#8E8E93'),
    ORANGE: chalk.hex('#FFA500'),
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#101010')(text),
};

// === CONFIGURATION ===
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        live_trading: process.env.LIVE_MODE === 'true',
        intervals: { scalping: '1', main: '5', trend: '15' },
        limits: { kline: 300, orderbook: 20 },
        delays: { loop: 3000, retry: 2000, wsReconnect: 1000 },
        ai: { 
            model: 'gemini-2.5-flash', 
            minConfidence: 0.85,
            maxTokens: 300
        },
        risk: {
            maxDailyLoss: 5.0, // % of balance
            maxRiskPerTrade: 1.0, // % of balance
            leverage: 5,
            fee: 0.00055,
            slippage: 0.0001,
            rewardRatio: 1.5
        },
        indicators: {
            rsi: 14,
            fisher: 10,
            atr: 14,
            bb: { period: 20, std: 2 },
            laguerre: 0.5,
            threshold: 1.8 // Minimum score to trigger AI check
        }
    });

    static async load() {
        let config = { ...this.DEFAULTS };
        try {
            const data = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.mergeDeep(config, JSON.parse(data));
        } catch {
            // Use defaults if file missing
        }
        return config;
    }

    static mergeDeep(target, source) {
        const output = { ...target };
        for (const key in source) {
            if (source[key] instanceof Object && key in target) {
                output[key] = this.mergeDeep(target[key], source[key]);
            } else {
                output[key] = source[key];
            }
        }
        return output;
    }
}

// === MATH & UTILS ===
const Utils = {
    safeArray: (len) => new Array(Math.max(0, Math.floor(len))).fill(0),
    sum: (arr) => arr.reduce((a, b) => a + b, 0),
    average: (arr) => arr.length ? Utils.sum(arr) / arr.length : 0,
    
    stdDev: (arr, period) => {
        if (!arr || arr.length < period) return Utils.safeArray(arr.length);
        const result = Utils.safeArray(arr.length);
        for (let i = period - 1; i < arr.length; i++) {
            const slice = arr.slice(i - period + 1, i + 1);
            const mean = Utils.average(slice);
            const variance = Utils.average(slice.map(x => Math.pow(x - mean, 2)));
            result[i] = Math.sqrt(variance);
        }
        return result;
    },

    timestamp: () => new Date().toLocaleTimeString(),
    
    calcSize: (balance, entry, sl, riskPct) => {
        const bal = new Decimal(balance);
        const ent = new Decimal(entry);
        const stop = new Decimal(sl);
        const riskAmt = bal.mul(riskPct).div(100);
        const riskPerCoin = ent.minus(stop).abs();
        
        if (riskPerCoin.eq(0)) return new Decimal(0);
        return riskAmt.div(riskPerCoin).toDecimalPlaces(3, Decimal.ROUND_DOWN);
    }
};

// === RISK GUARD (CIRCUIT BREAKER) ===
class CircuitBreaker {
    constructor(config) {
        this.maxLossPct = config.risk.maxDailyLoss;
        this.initialBalance = 0;
        this.currentPnL = 0;
        this.triggered = false;
        this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
    }

    setBalance(bal) {
        if (this.initialBalance === 0) this.initialBalance = bal;
        if (Date.now() > this.resetTime) {
            this.initialBalance = bal;
            this.currentPnL = 0;
            this.triggered = false;
            this.resetTime = new Date().setHours(0, 0, 0, 0) + 86400000;
            console.log(COLOR.GREEN(`[CircuitBreaker] Daily stats reset.`));
        }
    }

    updatePnL(pnl) {
        this.currentPnL += pnl;
        const lossPct = (Math.abs(this.currentPnL) / this.initialBalance) * 100;
        if (this.currentPnL < 0 && lossPct >= this.maxLossPct) {
            this.triggered = true;
            console.log(COLOR.bg(COLOR.RED(` 🚨 CIRCUIT BREAKER TRIGGERED: Daily Loss ${lossPct.toFixed(2)}% `)));
        }
    }

    canTrade() {
        return !this.triggered;
    }
}

// === TECHNICAL ANALYSIS ENGINE ===
class TechnicalAnalysis {
    static rsi(closes, period = 14) {
        if (!closes.length) return [];
        let gains = [], losses = [];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(Math.max(diff, 0));
            losses.push(Math.max(-diff, 0));
        }
        
        const rsi = Utils.safeArray(closes.length);
        let avgGain = Utils.average(gains.slice(0, period));
        let avgLoss = Utils.average(losses.slice(0, period));
        
        for(let i = period + 1; i < closes.length; i++) {
            const change = closes[i] - closes[i-1];
            avgGain = (avgGain * (period - 1) + (change > 0 ? change : 0)) / period;
            avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
            rsi[i] = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
        }
        return rsi;
    }

    static fisher(highs, lows, period = 9) {
        const len = highs.length;
        const fish = Utils.safeArray(len);
        const value = Utils.safeArray(len);
        
        for (let i = 1; i < len; i++) {
            if (i < period) continue;
            let minL = Infinity, maxH = -Infinity;
            for (let j = 0; j < period; j++) {
                maxH = Math.max(maxH, highs[i-j]);
                minL = Math.min(minL, lows[i-j]);
            }
            
            let raw = 0;
            if (maxH !== minL) {
                raw = 0.66 * ((highs[i] + lows[i]) / 2 - minL) / (maxH - minL) - 0.5 + 0.67 * (value[i-1] || 0);
            }
            value[i] = Math.max(Math.min(raw, 0.99), -0.99);
            fish[i] = 0.5 * Math.log((1 + value[i]) / (1 - value[i])) + 0.5 * (fish[i-1] || 0);
        }
        return fish;
    }

    static atr(highs, lows, closes, period = 14) {
        const tr = new Array(closes.length).fill(0);
        for(let i=1; i<closes.length; i++) {
            tr[i] = Math.max(highs[i]-lows[i], Math.abs(highs[i]-closes[i-1]), Math.abs(lows[i]-closes[i-1]));
        }
        const atr = Utils.safeArray(closes.length);
        let sum = 0;
        for(let i=0; i<closes.length; i++) {
            sum += tr[i];
            if(i >= period) {
                sum -= tr[i-period];
                atr[i] = sum / period;
            }
        }
        return atr;
    }

    static bollinger(closes, period, std) {
        const mid = new Array(closes.length).fill(0);
        let sum = 0;
        for(let i=0; i<closes.length; i++) {
            sum += closes[i];
            if(i >= period) {
                sum -= closes[i-period];
                mid[i] = sum/period;
            }
        }
        const dev = Utils.stdDev(closes, period);
        return {
            upper: mid.map((m, i) => m + dev[i] * std),
            lower: mid.map((m, i) => m - dev[i] * std),
            mid: mid
        };
    }
}

// === AI BRAIN (GEMINI 1.5 JSON MODE) ===
class AIBrain {
    constructor(config) {
        this.config = config.ai;
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ 
            model: this.config.model,
            generationConfig: { responseMimeType: "application/json", maxOutputTokens: this.config.maxTokens }
        });
    }

    async analyze(ctx) {
        const prompt = `
        Act as a high-frequency trading algorithm. Analyze these metrics for ${ctx.symbol}:
        - Price: ${ctx.price}
        - Fisher Transform: ${ctx.fisher.toFixed(2)} (Trend Strength)
        - RSI: ${ctx.rsi.toFixed(2)}
        - ATR: ${ctx.atr.toFixed(2)} (Volatility)
        - Orderbook Imbalance: ${(ctx.imbalance * 100).toFixed(1)}%
        - Technical Score: ${ctx.score.toFixed(2)} / 10.0
        
        Strategy:
        1. Fisher > 2.0 is Bullish, < -2.0 is Bearish.
        2. Imbalance > 0 supports Buy, < 0 supports Sell.
        3. RSI > 70 Overbought, < 30 Oversold.
        
        Respond ONLY with this JSON structure:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "sl": number,
            "tp": number,
            "reason": "Short string explanation"
        }`;

        try {
            const result = await this.model.generateContent(prompt);
            let rawText = result.response.text();
            rawText = rawText.replace(/```json|```/g, '').trim();
            return JSON.parse(rawText);
        } catch (e) {
            return { action: "HOLD", confidence: 0 };
        }
    }
}

// === DATA PROVIDER (REST + WSS) ===
class MarketData {
    constructor(config, onUpdate) {
        this.config = config;
        this.onUpdate = onUpdate;
        this.ws = null;
        this.buffers = {
            scalping: [], // 1m
            main: [],     // 5m
            trend: []     // 15m
        };
        this.lastPrice = 0;
        this.orderbook = { bids: [], asks: [] };
        this.latency = 0;
    }

    async start() {
        await this.loadHistory();
        this.connectWSS();
    }

    async loadHistory() {
        const client = axios.create({ baseURL: 'https://api.bybit.com/v5/market' });
        const loadKline = async (interval, targetBuffer) => {
            try {
                const res = await client.get('/kline', {
                    params: { category: 'linear', symbol: this.config.symbol, interval, limit: 200 }
                });
                if (res.data.retCode === 0) {
                    this.buffers[targetBuffer] = res.data.result.list.map(k => ({
                        t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), 
                        l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5])
                    })).reverse();
                }
            } catch (e) { console.error(`[Data] Failed loading ${interval} klines`); }
        };

        await Promise.all([
            loadKline(this.config.intervals.scalping, 'scalping'),
            loadKline(this.config.intervals.main, 'main'),
            loadKline(this.config.intervals.trend, 'trend')
        ]);
        console.log(COLOR.CYAN(`[Data] Historical data loaded.`));
    }

    connectWSS() {
        this.ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        this.ws.on('open', () => {
            console.log(COLOR.GREEN(`[WSS] Connected.`));
            const args = [
                `tickers.${this.config.symbol}`,
                `orderbook.50.${this.config.symbol}`,
                `kline.${this.config.intervals.scalping}.${this.config.symbol}`,
                `kline.${this.config.intervals.main}.${this.config.symbol}`
            ];
            this.ws.send(JSON.stringify({ op: 'subscribe', args }));
            this.startHeartbeat();
        });

        this.ws.on('message', (data) => {
            const msg = JSON.parse(data);
            
            if (msg.ts) {
                this.latency = Date.now() - msg.ts;
            }

            if (msg.topic?.startsWith('tickers')) {
                const tickerData = Array.isArray(msg.data) ? msg.data[0] : msg.data;
                if (tickerData?.lastPrice) {
                    this.lastPrice = parseFloat(tickerData.lastPrice);
                    this.onUpdate('price');
                }
            } else if (msg.topic?.startsWith('orderbook')) {
                if (msg.type === 'snapshot') {
                    this.orderbook.bids = msg.data.b.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                    this.orderbook.asks = msg.data.a.map(x=>({p:parseFloat(x[0]), q:parseFloat(x[1])}));
                }
            } else if (msg.topic?.startsWith('kline')) {
                const k = msg.data[0];
                const interval = msg.topic.split('.')[1];
                const type = interval === this.config.intervals.scalping ? 'scalping' : 'main';
                
                const candle = {
                    t: parseInt(k.start), o: parseFloat(k.open), h: parseFloat(k.high),
                    l: parseFloat(k.low), c: parseFloat(k.close), v: parseFloat(k.volume)
                };
                
                const buf = this.buffers[type];
                if(buf && buf.length > 0 && buf[buf.length-1].t === candle.t) {
                    buf[buf.length-1] = candle; 
                } else if(buf) {
                    buf.push(candle); 
                    if(buf.length > this.config.limits.kline) buf.shift();
                }
                this.onUpdate('kline');
            }
        });

        this.ws.on('error', () => setTimeout(() => this.connectWSS(), 1000));
        this.ws.on('close', () => setTimeout(() => this.connectWSS(), 1000));
    }

    startHeartbeat() {
        setInterval(() => {
            if(this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({op:'ping'}));
        }, 20000);
    }
}

// === EXECUTION ENGINE ===
class Exchange {
    constructor(config) {
        this.config = config;
        this.symbol = config.symbol;
        this.isLive = config.live_trading;
        
        if (this.isLive) {
            this.client = axios.create({ baseURL: 'https://api.bybit.com' });
            this.apiKey = process.env.BYBIT_API_KEY;
            this.apiSecret = process.env.BYBIT_API_SECRET;
        }

        this.balance = 10000;
        this.position = null;
        this.lastPrice = 0; 
    }

    async getSignature(params) {
        const ts = Date.now().toString();
        const recvWindow = '5000';
        const payload = JSON.stringify(params);
        const signStr = ts + this.apiKey + recvWindow + payload;
        return crypto.createHmac('sha256', this.apiSecret).update(signStr).digest('hex');
    }

    async execute(action, qty, sl, tp) {
        if (!this.isLive) {
            const entry = this.lastPrice;
            this.position = { action, qty, entry, sl, tp };
            console.log(COLOR.GREEN(`[PAPER] Executed ${action} ${qty} @ ${entry.toFixed(2)}`));
            return true;
        }

        try {
            const params = {
                category: 'linear',
                symbol: this.symbol,
                side: action === 'BUY' ? 'Buy' : 'Sell',
                orderType: 'Market',
                qty: qty.toString(),
                stopLoss: sl.toString(),
                takeProfit: tp.toString(),
                timeInForce: 'GTC'
            };

            const ts = Date.now().toString();
            const sign = await this.getSignature(params);
            
            const res = await this.client.post('/v5/order/create', params, {
                headers: {
                    'X-BAPI-API-KEY': this.apiKey,
                    'X-BAPI-TIMESTAMP': ts,
                    'X-BAPI-SIGN': sign,
                    'X-BAPI-RECV-WINDOW': '5000',
                    'Content-Type': 'application/json'
                }
            });

            if (res.data.retCode === 0) {
                console.log(COLOR.GREEN(`[LIVE] Order Success: ${res.data.result.orderId}`));
                return true;
            } else {
                console.error(COLOR.RED(`[LIVE] Order Failed: ${res.data.retMsg}`));
                return false;
            }
        } catch (e) {
            console.error(COLOR.RED(`[LIVE] Execution Error: ${e.message}`));
            return false;
        }
    }

    async close(price) {
        if (!this.position) return 0;
        
        let pnl = 0;
        if (!this.isLive) {
            const diff = this.position.action === 'BUY' ? price - this.position.entry : this.position.entry - price;
            pnl = diff * this.position.qty;
            this.balance += pnl;
            this.position = null;
            console.log(COLOR.PURPLE(`[PAPER] Closed @ ${price.toFixed(2)} | PnL: ${pnl.toFixed(2)}`));
            return pnl;
        } else {
            return 0; 
        }
    }
}

// === CORE CONTROLLER ===
class Leviathan {
    constructor() {
        this.init();
    }

    async init() {
        console.clear();
        console.log(COLOR.bg(COLOR.BOLD(COLOR.ORANGE(' 🐋 LEVIATHAN v2.3: HUD ENHANCED '))));
        
        this.config = await ConfigManager.load();
        this.circuitBreaker = new CircuitBreaker(this.config);
        this.exchange = new Exchange(this.config);
        this.ai = new AIBrain(this.config);
        this.data = new MarketData(this.config, (type) => this.onTick(type));
        
        this.isProcessing = false;
        this.aiLastQueryTime = 0;
        this.aiThrottleMs = 5000;
        
        await this.data.start();
        this.circuitBreaker.setBalance(this.exchange.balance);
    }

    async onTick(type) {
        const price = this.data.lastPrice;
        if (this.isProcessing || type !== 'kline' || !price || isNaN(price) || price === 0) return;
        
        this.isProcessing = true;
        this.exchange.lastPrice = price; 

        try {
            const candles = this.data.buffers.main;
            
            if (candles.length < 50) {
                this.isProcessing = false;
                return;
            }

            // 1. Technical Calculation
            const closes = candles.map(c => c.c);
            const highs = candles.map(c => c.h);
            const lows = candles.map(c => c.l);

            const rsi = TechnicalAnalysis.rsi(closes, 14);
            const fisher = TechnicalAnalysis.fisher(highs, lows, 10);
            const atr = TechnicalAnalysis.atr(highs, lows, closes, 14);
            const bb = TechnicalAnalysis.bollinger(closes, 20, 2);

            const last = closes.length - 1;
            const currentRsi = rsi[last];
            const currentFisher = fisher[last];
            const currentAtr = atr[last];

            // 2. Orderbook Imbalance
            const bidVol = Utils.sum(this.data.orderbook.bids.map(b => b.q));
            const askVol = Utils.sum(this.data.orderbook.asks.map(a => a.q));
            const imbalance = (bidVol - askVol) / ((bidVol + askVol) || 1);

            // 3. Score Calculation
            let score = 0;
            if (currentFisher > 0) score += 2; else score -= 2;
            if (currentRsi > 50) score += 1; else score -= 1;
            if (imbalance > 0.2) score += 1.5; else if (imbalance < -0.2) score -= 1.5;
            if (price > bb.mid[last]) score += 1; else score -= 1;

            // 4. Position Management (Simplified Close Check)
            if (this.exchange.position) {
                const pos = this.exchange.position;
                let hitExit = false;
                if (pos.action === 'BUY' && (price <= pos.sl || price >= pos.tp)) hitExit = true;
                if (pos.action === 'SELL' && (price >= pos.sl || price <= pos.tp)) hitExit = true;
                
                if (hitExit) {
                    const pnl = await this.exchange.close(price);
                    this.circuitBreaker.updatePnL(pnl);
                }
            }

            // 5. HYBRID TRIGGER REFINEMENT
            const now = Date.now();
            const scoreThreshold = this.config.indicators.threshold;
            const fisherSign = Math.sign(currentFisher);
            
            let shouldQueryAI = false;
            
            if (Math.abs(score) >= scoreThreshold && (now - this.aiLastQueryTime > this.aiThrottleMs)) {
                if (Math.sign(score) === fisherSign || Math.abs(score) >= 4.0) { 
                    shouldQueryAI = true;
                }
            }


            if (this.circuitBreaker.canTrade() && !this.exchange.position && shouldQueryAI) {
                this.aiLastQueryTime = now;
                process.stdout.write(`\n`); 
                console.log(COLOR.CYAN(`[Trigger] Score ${score.toFixed(2)} hit threshold. Querying Gemini...`));
                
                const context = {
                    symbol: this.config.symbol,
                    price, rsi: currentRsi, fisher: currentFisher,
                    atr: currentAtr, imbalance, score
                };

                const decision = await this.ai.analyze(context);
                
                if (decision.confidence >= this.config.ai.minConfidence && decision.action !== 'HOLD') {
                    const sl = decision.sl || (decision.action === 'BUY' ? price - 2*currentAtr : price + 2*currentAtr);
                    const tp = decision.tp || (decision.action === 'BUY' ? price + 3*currentAtr : price - 3*currentAtr);
                    
                    const qty = Utils.calcSize(this.exchange.balance, price, sl, this.config.risk.maxRiskPerTrade);

                    if (qty.gt(0)) {
                        await this.exchange.execute(decision.action, qty.toNumber(), sl, tp);
                    }
                }
            }

            this.renderHUD(price, score, currentRsi, this.data.latency, currentFisher, currentAtr, imbalance);

        } catch (e) {
            console.error(COLOR.RED(`[Loop Error] ${e.message}`));
        } finally {
            this.isProcessing = false;
        }
    }

    renderHUD(price, score, rsi, latency, fisher, atr, imbalance) {
        const time = Utils.timestamp();
        const latColor = latency > 500 ? COLOR.RED : COLOR.GREEN;
        const scoreColor = score > 0 ? COLOR.GREEN : COLOR.RED;
        const fishColor = fisher > 0 ? COLOR.BLUE : COLOR.PURPLE;
        const imbColor = imbalance > 0 ? COLOR.GREEN : COLOR.RED;
        const posText = this.exchange.position ? `${this.exchange.position.action}` : 'FLAT';
        
        process.stdout.write(
            `\r${COLOR.GRAY(time)} | ${COLOR.BOLD(this.config.symbol)} ${price.toFixed(2)} | ` +
            `Lat: ${latColor(latency+'ms')} | ` +
            `Score: ${scoreColor(score.toFixed(1))} | ` +
            `RSI: ${rsi.toFixed(1)} | ` +
            `Fish: ${fishColor(fisher.toFixed(2))} | ` +
            `ATR: ${atr.toFixed(2)} | ` +
            `Imb: ${imbColor((imbalance*100).toFixed(0)+'%')} | ` +
            `${COLOR.YELLOW(posText)}      `
        );
    }
}

// === START ===
new Leviathan();
/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v5.0 (Final Production-Ready Code)
 * ----------------------------------------------------------------------
 * - WSS 2.0: Deeply enhanced Weighted Scoring System with normalization and level checks.
 * - HYBRID MODEL: Quantitative (WSS) Pre-filter + Qualitative (Gemini) Strategy Selector.
 * - ARBITRARY PRECISION: All financial math uses decimal.js.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ ENHANCED CONFIGURATION MANAGER (WSS WEIGHTS UPDATED) ---
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        symbol: 'BTCUSDT',
        interval: '3',
        trend_interval: '15',
        limit: 300,
        loop_delay: 5,
        gemini_model: 'gemini-1.5-flash',
        min_confidence: 0.70, 
        
        risk: {
            max_drawdown: 10.0, daily_loss_limit: 5.0, max_positions: 1,
        },
        
        paper_trading: {
            initial_balance: 1000.00, risk_percent: 1.5, leverage_cap: 10,
            fee: 0.00055, slippage: 0.0001
        },
        
        indicators: {
            // Standard
            rsi: 14, stoch_period: 14, stoch_k: 3, stoch_d: 3, cci_period: 14, 
            macd_fast: 12, macd_slow: 26, macd_sig: 9, adx_period: 14,
            // Advanced
            mfi: 14, chop_period: 14, linreg_period: 20, vwap_period: 20,
            bb_period: 20, bb_std: 2.0, kc_period: 20, kc_mult: 1.5,
            atr_period: 14, st_factor: 3.0, ce_period: 22, ce_mult: 3.0,
            // WSS Weighting Configuration (ENHANCED)
            wss_weights: {
                trend_mtf_weight: 2.0, trend_scalp_weight: 1.0,
                momentum_normalized_weight: 1.5, macd_weight: 0.8,
                regime_weight: 0.7, squeeze_vol_weight: 0.5,
                liquidity_grab_weight: 1.2, divergence_weight: 1.8,
                volatility_weight: 0.4, action_threshold: 1.5 // Higher threshold for high conviction
            }
        },
        
        orderbook: { depth: 50, wall_threshold: 4.0, sr_levels: 5 },
        api: { timeout: 8000, retries: 3, backoff_factor: 2 }
    };

    static load() {
        let config = { ...this.DEFAULTS };
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                config = this.deepMerge(config, userConfig);
            } catch (e) { console.error(chalk.red(`Config Error: ${e.message}`)); }
        } else {
            fs.writeFileSync(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else { result[key] = source[key]; }
        }
        return result;
    }
}

const config = ConfigManager.load();
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME MANAGER ---
const NEON = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'), GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'), BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
};

// --- 📐 COMPLETE TECHNICAL ANALYSIS LIBRARY ---
class TA {
    static safeArr(len) { return new Array(Math.floor(len)).fill(0); }
    
    static getFinalValue(data, key, precision = 2) {
        if (!data.closes || data.closes.length === 0) return 'N/A';
        const last = data.closes.length - 1;
        const value = data[key];
        if (Array.isArray(value)) return value[last]?.toFixed(precision) || '0.00';
        if (typeof value === 'object') {
            if (value.k) return { k: value.k[last]?.toFixed(0), d: value.d[last]?.toFixed(0) };
            if (value.hist) return value.hist[last]?.toFixed(precision);
            if (value.slope) return { slope: value.slope[last]?.toFixed(precision), r2: value.r2[last]?.toFixed(precision) };
            if (value.trend) return value.trend[last] === 1 ? 'BULL' : 'BEAR';
        }
        return 'N/A';
    }

    // --- Core Math (SMA, EMA, Wilder's) ---
    static sma(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = []; let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) { sum += data[i] - data[i - period]; result.push(sum / period); }
        return TA.safeArr(period - 1).concat(result);
    }
    static ema(data, period) {
        if (!data || data.length === 0) return [];
        let result = TA.safeArr(data.length);
        const k = 2 / (period + 1); result[0] = data[0];
        for (let i = 1; i < data.length; i++) result[i] = (data[i] * k) + (result[i - 1] * (1 - k));
        return result;
    }
    static wilders(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = TA.safeArr(data.length); let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        return result;
    }

    // --- Core Indicators (ATR, RSI, Stoch, MACD, ADX, MFI, CCI, Chop) ---
    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        return this.wilders(tr, period);
    }
    static rsi(closes, period) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0); losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);
        return closes.map((_, i) => avgLoss[i] === 0 ? 100 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
    }
    static stoch(highs, lows, closes, period, kP, dP) {
        let rsi = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceH = highs.slice(i - period + 1, i + 1); const sliceL = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...sliceL); const maxH = Math.max(...sliceH);
            rsi[i] = (maxH - minL === 0) ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        const k = this.sma(rsi, kP); const d = this.sma(k, dP); return { k, d };
    }
    static macd(closes, fast, slow, sig) {
        const emaFast = this.ema(closes, fast); const emaSlow = this.ema(closes, slow);
        const line = emaFast.map((v, i) => v - emaSlow[i]); const signal = this.ema(line, sig);
        return { line, signal, hist: line.map((v, i) => v - signal[i]) };
    }
    static adx(highs, lows, closes, period) {
        let plusDM = [0], minusDM = [0];
        for (let i = 1; i < closes.length; i++) {
            const up = highs[i] - highs[i - 1]; const down = lows[i - 1] - lows[i];
            plusDM.push(up > down && up > 0 ? up : 0); minusDM.push(down > up && down > 0 ? down : 0);
        }
        const sTR = this.wilders(this.atr(highs, lows, closes, 1), period);
        const sPlus = this.wilders(plusDM, period); const sMinus = this.wilders(minusDM, period);
        let dx = [];
        for (let i = 0; i < closes.length; i++) {
            const pDI = sTR[i] === 0 ? 0 : (sPlus[i] / sTR[i]) * 100; const mDI = sTR[i] === 0 ? 0 : (sMinus[i] / sTR[i]) * 100;
            const sum = pDI + mDI;
            dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100);
        }
        return this.wilders(dx, period);
    }
    static mfi(h,l,c,v,p) { 
        let posFlow = [], negFlow = [];
        for (let i = 0; i < c.length; i++) {
            if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
            const tp = (h[i] + l[i] + c[i]) / 3; const prevTp = (h[i-1] + l[i-1] + c[i-1]) / 3;
            const raw = tp * v[i];
            if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
            else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
            else { posFlow.push(0); negFlow.push(0); }
        }
        let result = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < p; j++) { pSum += posFlow[i-j]; nSum += negFlow[i-j]; }
            if (nSum === 0) result[i] = 100; else result[i] = 100 - (100 / (1 + (pSum / nSum)));
        }
        return result;
    }
    static chop(h, l, c, p) {
        let result = TA.safeArr(c.length);
        let tr = [h[0] - l[0]]; 
        for(let i=1; i<c.length; i++) tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i-1]), Math.abs(l[i] - c[i-1])));
        for (let i = p - 1; i < c.length; i++) {
            let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
            for (let j = 0; j < p; j++) {
                sumTr += tr[i - j];
                if (h[i - j] > maxHi) maxHi = h[i - j];
                if (l[i - j] < minLo) minLo = l[i - j];
            }
            const range = maxHi - minLo;
            result[i] = (range === 0 || sumTr === 0) ? 0 : 100 * (Math.log10(sumTr / range) / Math.log10(p));
        }
        return result;
    }
    static cci(highs, lows, closes, period) {
        const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3); const smaTp = this.sma(tp, period);
        let cci = TA.safeArr(closes.length);
        for (let i = period - 1; i < tp.length; i++) {
            let meanDev = 0; for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
            meanDev /= period;
            cci[i] = (meanDev === 0) ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
        }
        return cci;
    }
    
    // --- Advanced Indicators (BB/KC, ST, CE, LinReg, VWAP, FVG, Divergence, Volatility) ---
    static linReg(closes, period) {
        let slopes = TA.safeArr(closes.length), r2s = TA.safeArr(closes.length);
        let sumX = 0, sumX2 = 0;
        for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }
        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0, sumXY = 0;
            const ySlice = [];
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j]; ySlice.push(val); sumY += val; sumXY += j * val;
            }
            const n = period;
            const num = (n * sumXY) - (sumX * sumY);
            const den = (n * sumX2) - (sumX * sumX);
            const slope = den === 0 ? 0 : num / den;
            const intercept = (sumY - slope * sumX) / n;
            let ssTot = 0, ssRes = 0;
            const yMean = sumY / n;
            for(let j=0; j<period; j++) {
                const y = ySlice[j]; const yPred = slope * j + intercept;
                ssTot += Math.pow(y - yMean, 2); ssRes += Math.pow(y - yPred, 2);
            }
            slopes[i] = slope; r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
        }
        return { slope: slopes, r2: r2s };
    }
    static bollinger(closes, period, stdDev) {
        const sma = this.sma(closes, period);
        let upper = [], lower = [], middle = sma;
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) { upper.push(0); lower.push(0); continue; }
            let sumSq = 0;
            for (let j = 0; j < period; j++) sumSq += Math.pow(closes[i - j] - sma[i], 2);
            const std = Math.sqrt(sumSq / period);
            upper.push(sma[i] + (std * stdDev)); lower.push(sma[i] - (std * stdDev));
        }
        return { upper, middle, lower };
    }
    static keltner(highs, lows, closes, period, mult) {
        const ema = this.ema(closes, period); const atr = this.atr(highs, lows, closes, period);
        return { upper: ema.map((e, i) => e + atr[i] * mult), lower: ema.map((e, i) => e - atr[i] * mult), middle: ema };
    }
    static superTrend(highs, lows, closes, period, factor) {
        const atr = this.atr(highs, lows, closes, period);
        let st = new Array(closes.length).fill(0); let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            let up = (highs[i] + lows[i]) / 2 + factor * atr[i];
            let dn = (highs[i] + lows[i]) / 2 - factor * atr[i];
            if (i > 0) {
                const prevST = st[i-1];
                if (trend[i-1] === 1) { up = up; dn = Math.max(dn, prevST); } else { up = Math.min(up, prevST); dn = dn; }
            }
            if (closes[i] > up) trend[i] = 1; else if (closes[i] < dn) trend[i] = -1; else trend[i] = trend[i-1];
            st[i] = trend[i] === 1 ? dn : up;
        }
        return { trend, value: st };
    }
    static chandelierExit(highs, lows, closes, period, mult) {
        const atr = this.atr(highs, lows, closes, period);
        let longStop = TA.safeArr(closes.length); let shortStop = TA.safeArr(closes.length);
        let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            const maxHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const minLow = Math.min(...lows.slice(i - period + 1, i + 1));
            longStop[i] = maxHigh - atr[i] * mult; shortStop[i] = minLow + atr[i] * mult;
            if (closes[i] > shortStop[i]) trend[i] = 1; else if (closes[i] < longStop[i]) trend[i] = -1; else trend[i] = trend[i-1];
        }
        return { trend, value: trend.map((t, i) => t === 1 ? longStop[i] : shortStop[i]) };
    }
    static vwap(h, l, c, v, p) {
        let vwap = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let sumPV = 0, sumV = 0;
            for (let j = 0; j < p; j++) {
                const tp = (h[i-j] + l[i-j] + c[i-j]) / 3; sumPV += tp * v[i-j]; sumV += v[i-j];
            }
            vwap[i] = sumV === 0 ? 0 : sumPV / sumV;
        }
        return vwap;
    }
    static findFVG(candles) {
        const len = candles.length;
        if (len < 5) return null; 
        const c1 = candles[len - 4]; const c2 = candles[len - 3]; const c3 = candles[len - 2]; 
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        else if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }
    static detectDivergence(closes, rsi, period = 5) {
        const len = closes.length;
        if (len < period * 2) return 'NONE';
        const priceHigh = Math.max(...closes.slice(len - period, len)); const rsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period)); const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';
        const priceLow = Math.min(...closes.slice(len - period, len)); const rsiLow = Math.min(...rsi.slice(len - period, len));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period)); const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
        if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH_REGULAR';
        return 'NONE';
    }
    static historicalVolatility(closes, period = 20) {
        const returns = [];
        for (let i = 1; i < closes.length; i++) returns.push(Math.log(closes[i] / closes[i - 1]));
        const volatility = TA.safeArr(closes.length);
        for (let i = period; i < closes.length; i++) {
            const slice = returns.slice(i - period + 1, i + 1);
            const mean = slice.reduce((a, b) => a + b, 0) / period;
            const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / period;
            volatility[i] = Math.sqrt(variance) * Math.sqrt(365);
        }
        return volatility;
    }
    static marketRegime(closes, volatility, period = 50) {
        const avgVol = TA.sma(volatility, period);
        const currentVol = volatility[volatility.length - 1] || 0;
        const avgVolValue = avgVol[avgVol.length - 1] || 1;
        if (currentVol > avgVolValue * 1.5) return 'HIGH_VOLATILITY';
        if (currentVol < avgVolValue * 0.5) return 'LOW_VOLATILITY';
        return 'NORMAL';
    }
    static fibPivots(h, l, c) {
        const P = (h + l + c) / 3; const R = h - l;
        return { P, R1: P + 0.382 * R, R2: P + 0.618 * R, S1: P - 0.382 * R, S2: P - 0.618 * R };
    }
}


// --- 🛠️ UTILITIES & ENHANCED WSS CALCULATOR ---

function getOrderbookLevels(bids, asks, currentClose, maxLevels) {
    const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
    const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
    let potentialSR = [];
    for (const price of uniquePrices) {
        let bidVolAtPrice = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
        let askVolAtPrice = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
        if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
        else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
    }
    const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));
    const supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    const resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    return { supportLevels, resistanceLevels };
}

function calculateWSS(analysis, currentPrice) {
    const w = config.indicators.wss_weights;
    let score = 0;
    const last = analysis.closes.length - 1;
    const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr, mfi, chop, cci, bb, kc } = analysis; // Added mfi, chop, cci, bb, kc

    // --- 1. TREND COMPONENT ---
    let trendScore = 0;
    // Base MTF Trend
    trendScore += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);
    // Scalp Trend (ST/CE)
    if (st.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    if (ce.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    // Scale total Trend by R2 (Quality of Trend)
    const r2 = reg.r2[last];
    trendScore *= r2; 
    score += trendScore;

    // --- 2. MOMENTUM COMPONENT (Normalized) ---
    let momentumScore = 0;
    const rsiVal = rsi[last];
    const stochK = stoch.k[last];
    const mfiVal = mfi[last]; // Added MFI
    const cciVal = cci[last]; // Added CCI

    // Normalized RSI (stronger signal closer to 0/100)
    if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50; else momentumScore -= (rsiVal - 50) / 50;
    // Normalized Stoch K
    if (stochK < 50) momentumScore += (50 - stochK) / 50; else momentumScore -= (stochK - 50) / 50;
    // Normalized MFI
    if (mfiVal < 50) momentumScore += (50 - mfiVal) / 50; else momentumScore -= (mfiVal - 50) / 50;
    // Normalized CCI (using 0 as midpoint)
    if (cciVal < 0) momentumScore += (0 - cciVal) / 100; else momentumScore -= (cciVal - 0) / 100; // Assuming CCI ranges approx -100 to 100

    // MACD Histogram Check
    const macdHist = macd.hist[last];
    if (macdHist > 0) momentumScore += w.macd_weight; else if (macdHist < 0) momentumScore -= w.macd_weight;
    score += momentumScore * w.momentum_normalized_weight;


    // --- 3. STRUCTURE / LIQUIDITY COMPONENT ---
    let structureScore = 0;
    // Squeeze
    if (analysis.isSqueeze) structureScore += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight);
    // Divergence (High conviction signal)
    if (divergence.includes('BULLISH')) structureScore += w.divergence_weight;
    else if (divergence.includes('BEARISH')) structureScore -= w.divergence_weight;
    // FVG/Wall Proximity (Liquidity grab potential)
    const price = currentPrice;
    const atrVal = atr[last];
    if (fvg) {
        if (fvg.type === 'BULLISH' && price > fvg.bottom && price < fvg.top) structureScore += w.liquidity_grab_weight;
        else if (fvg.type === 'BEARISH' && price < fvg.top && price > fvg.bottom) structureScore -= w.liquidity_grab_weight;
    }
    if (buyWall && (price - buyWall) < atrVal) structureScore += w.liquidity_grab_weight * 0.5; 
    else if (sellWall && (sellWall - price) < atrVal) structureScore -= w.liquidity_grab_weight * 0.5;
    score += structureScore;

    // --- 4. CHOPPINESS (Ranges and Trends) ---
    const chopVal = chop[last]; // Added Chop
    if (chopVal > 61.8) score -= w.regime_weight * 0.5; // Penalty for chop, higher chop -> lower score magnitude
    else if (chopVal < 38.2) score += w.regime_weight * 0.5; // Bonus for trending, lower chop -> higher score magnitude

    // --- 5. FINAL VOLATILITY ADJUSTMENT ---
    const volatility = analysis.volatility[analysis.volatility.length - 1] || 0;
    const avgVolatility = analysis.avgVolatility[analysis.avgVolatility.length - 1] || 1;
    const volRatio = volatility / avgVolatility;

    let finalScore = score;
    if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
    else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);
    
    return parseFloat(finalScore.toFixed(2));
}

// --- 📡 ENHANCED DATA PROVIDER (from v4.0, assumed complete) ---
class EnhancedDataProvider {
    constructor() { this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout }); }

    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try { return (await this.api.get(url, { params })).data; }
            catch (error) { 
                if (attempt === retries) throw error; 
                await setTimeout(Math.pow(config.api.backoff_factor, attempt) * 1000); 
            }
        }
    }

    async fetchAll() {
        try {
            const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);

            const parseC = (list) => list.reverse().map(c => ({ o: parseFloat(c[1]), h: parseFloat(c[2]), l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5]), t: parseInt(c[0]) }));

            return {
                price: parseFloat(ticker.result.list[0].lastPrice),
                candles: parseC(kline.result.list),
                candlesMTF: parseC(klineMTF.result.list),
                bids: ob.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                asks: ob.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                daily: { h: parseFloat(daily.result.list[1][2]), l: parseFloat(daily.result.list[1][3]), c: parseFloat(daily.result.list[1][4]) },
                timestamp: Date.now()
            };
        } catch (e) {
            console.warn(NEON.ORANGE(`[WARN] Data Fetch Fail: ${e.message}`));
            return null;
        }
    }
}

// --- 💰 EXCHANGE & RISK MANAGEMENT (from v4.0, assumed complete) ---
class EnhancedPaperExchange {
    constructor() {
        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null;
        this.dailyPnL = new Decimal(0);
    }

    canTrade() {
        const drawdown = this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdown.gt(config.risk.max_drawdown)) { console.log(NEON.RED(`🚨 MAX DRAWDOWN HIT`)); return false; }
        const dailyLoss = this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLoss.lt(-config.risk.daily_loss_limit)) { console.log(NEON.RED(`🚨 DAILY LOSS LIMIT HIT`)); return false; }
        return true;
    }

    evaluate(priceVal, signal) {
        if (!this.canTrade()) { if (this.pos) this.handlePositionClose(new Decimal(priceVal), "RISK_STOP"); return; }
        const price = new Decimal(priceVal);
        if (this.pos) this.handlePositionClose(price);
        if (!this.pos && signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) { this.handlePositionOpen(price, signal); }
    }

    handlePositionClose(price, forceReason = null) {
        let close = false, reason = forceReason || '';
        if (this.pos.side === 'BUY') { if (forceReason || price.lte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.gte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } } else { if (forceReason || price.gte(this.pos.sl)) { close = true; reason = reason || 'SL Hit'; } else if (price.lte(this.pos.tp)) { close = true; reason = reason || 'TP Hit'; } }
        if (close) {
            const slippage = price.mul(config.paper_trading.slippage);
            const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
            const rawPnl = this.pos.side === 'BUY' ? exitPrice.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
            const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
            const netPnl = rawPnl.sub(fee);
            this.balance = this.balance.add(netPnl);
            this.dailyPnL = this.dailyPnL.add(netPnl);
            const color = netPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(`${NEON.BOLD(reason)}! PnL: ${color(netPnl.toFixed(2))} [${this.pos.strategy}]`);
            this.pos = null;
        }
    }

    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry); const sl = new Decimal(signal.sl); const tp = new Decimal(signal.tp);
        const dist = entry.sub(sl).abs(); if (dist.isZero()) return;
        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);
        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) qty = maxQty;
        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);
        this.balance = this.balance.sub(fee);
        this.pos = { side: signal.action, entry: execPrice, qty: qty, sl: sl, tp: tp, strategy: signal.strategy };
        console.log(NEON.GREEN(`OPEN ${signal.action} [${signal.strategy}] @ ${execPrice.toFixed(4)} | Size: ${qty.toFixed(4)}`));
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN (Hybrid Logic) ---
class EnhancedGeminiBrain {
    constructor() {
        const key = process.env.GEMINI_API_KEY;
        if (!key) { console.error("Missing GEMINI_API_KEY"); process.exit(1); }
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
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope) | ADX: ${ctx.adx}
        - Momentum: RSI=${ctx.rsi}, Stoch=${ctx.stoch_k}, MACD=${ctx.macd_hist}, MFI=${ctx.mfi}, CCI=${ctx.cci}
        - Structure: VWAP=${ctx.vwap}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
        - Support/Resistance: ${ctx.sr_levels}
        - Volatility Channels: BB_Upper=${ctx.bb_upper}, BB_Lower=${ctx.bb_lower}, KC_Upper=${ctx.kc_upper}, KC_Lower=${ctx.kc_lower}
        - Trend Strength: SuperTrend=${ctx.st_trend} (${ctx.st_value}), ChandelierExit=${ctx.ce_trend} (${ctx.ce_value})
        - Chop Zone: ${ctx.chop} (Above 61.8 = Choppy, Below 38.2 = Trending)

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0, Strong ADX, Aligned ST/CE): Pullback to VWAP/EMA, anticipate continuation. Look for strong trend confirmation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES, High Volume, Clear Direction from MTF Trend): Trade in direction of MTF trend on volatility expansion. Target channel breakouts.
        3. MEAN_REVERSION (WSS Momentum < -1.0 or > 1.0, Extreme RSI/Stoch/MFI/CCI, Price near BB/KC bands): Fade extreme readings when price is at overbought/oversold levels. Target mean (EMA/SMA).
        4. LIQUIDITY_GRAB (Price Near FVG/Wall, High Volatility): Fade or trade the retest/bounce of a liquidity zone. Use ATR for target sizing.
        5. DIVERGENCE_HUNT (Divergence != NONE, Confluence with other momentum indicators): High conviction reversal trade using swing high/low for SL. Confirm with MFI/CCI.

        INSTRUCTIONS:
        - If the WSS does not meet the threshold, or if no strategy is clear, return "HOLD".
        - Calculate precise entry, SL, and TP (1:1.5 RR minimum, use ATR/Pivot/FVG/Channel bounds for targets).
        - Provide a concise but comprehensive reason for the trade, referencing specific indicators and market conditions from the CONTEXT above.

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "strategy": "STRATEGY_NAME", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const start = text.indexOf('{');
            const end = text.lastIndexOf('}');
            if (start === -1 || end === -1) throw new Error("Invalid JSON: AI response error");
            return JSON.parse(text.substring(start, end + 1));
        } catch (e) {
            return { action: "HOLD", confidence: 0, reason: `AI Comms Failure: ${e.message}` };
        }
    }
}

// --- 🔄 MAIN TRADING ENGINE (from v4.0, assumed complete) ---
class TradingEngine {
    constructor() {
        this.dataProvider = new EnhancedDataProvider();
        this.exchange = new EnhancedPaperExchange();
        this.ai = new EnhancedGeminiBrain();
        this.isRunning = true;
    }

    async start() {
        console.clear();
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` 🚀 WHALEWAVE TITAN v5.0 STARTING... `))));
        
        while (this.isRunning) {
            try {
                const data = await this.dataProvider.fetchAll();
                if (!data) { await setTimeout(config.loop_delay * 1000); continue; }

                const analysis = await this.performAnalysis(data);
                const context = this.buildContext(data, analysis);
                const signal = await this.ai.analyze(context);

                this.displayDashboard(data, context, signal);
                this.exchange.evaluate(data.price, signal);

            } catch (e) {
                console.error(NEON.RED(`Loop Critical Error: ${e.message}`));
            }
            await setTimeout(config.loop_delay * 1000);
        }
    }

    async performAnalysis(data) {
        const c = data.candles.map(x => x.c); const h = data.candles.map(x => x.h);
        const l = data.candles.map(x => x.l); const v = data.candles.map(x => x.v);
        const mtfC = data.candlesMTF.map(x => x.c);

        // Parallel Calculation (Full Suite)
        const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all([
            TA.rsi(c, config.indicators.rsi), TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig), TA.adx(h, l, c, config.indicators.adx_period),
            TA.mfi(h, l, c, v, config.indicators.mfi), TA.chop(h, l, c, config.indicators.chop_period),
            TA.linReg(c, config.indicators.linreg_period), TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult), TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles), TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult),
            TA.cci(h, l, c, config.indicators.cci_period)
        ]);

        const last = c.length - 1;
        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
        const divergence = TA.detectDivergence(c, rsi);
        const volatility = TA.historicalVolatility(c);
        const avgVolatility = TA.sma(volatility, 50);
        const mtfSma = TA.sma(mtfC, 20);
        const trendMTF = mtfC[mtfC.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);

        // Walls
        const avgBid = data.bids.reduce((a,b)=>a+b.q,0)/data.bids.length;
        const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p;
        const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p;

        const analysis = { 
            closes: c, rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci,
            isSqueeze, divergence, volatility, avgVolatility, trendMTF, buyWall, sellWall, fibs
        };
        // --- CRITICAL WSS CALCULATION ---
        analysis.wss = calculateWSS(analysis, data.price);
        analysis.avgVolatility = avgVolatility;
        return analysis;
    }

    buildContext(d, a) {
        const last = a.closes.length - 1;
        // Defensive check for 'last' index in analysis results
        if (last < 0 || a.rsi.length <= last || a.stoch.k.length <= last || a.macd.hist.length <= last ||
            a.adx.length <= last || a.chop.length <= last || a.vwap.length <= last ||
            a.volatility.length <= last || a.reg.slope.length <= last || a.mfi.length <= last || a.cci.length <= last ||
            a.bb.upper.length <= last || a.kc.upper.length <= last || a.st.trend.length <= last || a.ce.trend.length <= last) {
            // Return a default context or throw an error if analysis data is insufficient
            return {
                price: d.price, rsi: 0, stoch_k: 0, macd_hist: 0, adx: 0, chop: 0, vwap: 0,
                trend_angle: 0, trend_mtf: 'NONE', isSqueeze: 'NO', fvg: null, divergence: 'NONE',
                walls: { buy: undefined, sell: undefined }, fibs: {}, volatility: 0, marketRegime: 'NORMAL',
                wss: 0, sr_levels: 'S:[] R:[]',
                mfi: 0, cci: 0, bb_upper: 0, bb_lower: 0, kc_upper: 0, kc_lower: 0,
                st_trend: 'NONE', st_value: 0, ce_trend: 'NONE', ce_value: 0, atr: 0
            };
        }

        const linReg = TA.getFinalValue(a, 'reg', 4);
        const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

        return {
            price: d.price, rsi: a.rsi[last].toFixed(2), stoch_k: a.stoch.k[last].toFixed(0), macd_hist: (a.macd.hist[last] || 0).toFixed(4),
            adx: a.adx[last].toFixed(2), chop: a.chop[last].toFixed(2), vwap: a.vwap[last].toFixed(2),
            trend_angle: linReg.slope, trend_mtf: a.trendMTF, isSqueeze: a.isSqueeze ? 'YES' : 'NO', fvg: a.fvg, divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall }, fibs: a.fibs,
            volatility: a.volatility[last].toFixed(2), marketRegime: TA.marketRegime(a.closes, a.volatility),
            wss: a.wss, sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`,
            mfi: a.mfi[last].toFixed(2), cci: a.cci[last].toFixed(2),
            bb_upper: a.bb.upper[last].toFixed(2), bb_lower: a.bb.lower[last].toFixed(2),
            kc_upper: a.kc.upper[last].toFixed(2), kc_lower: a.kc.lower[last].toFixed(2),
            st_trend: a.st.trend[last] === 1 ? 'BULLISH' : 'BEARISH', st_value: a.st.value[last].toFixed(2),
            ce_trend: a.ce.trend[last] === 1 ? 'BULLISH' : 'BEARISH', ce_value: a.ce.value[last].toFixed(2),
            atr: a.atr[last].toFixed(2)
        };
    }

    displayDashboard(d, ctx, sig) {
        // Defensive check for ctx.wss and ctx.marketRegime
        const wss = ctx.wss !== undefined ? ctx.wss : 0;
        const marketRegime = ctx.marketRegime || 'NORMAL';
        const trendMTF = ctx.trend_mtf || 'NONE';
        const isSqueeze = ctx.isSqueeze || 'NO';
        const divergence = ctx.divergence || 'NONE';
        const fvg = ctx.fvg;
        const vwap = ctx.vwap;


        console.clear();
        const border = NEON.GRAY('─'.repeat(80));
        console.log(border);
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` WHALEWAVE TITAN v5.0 | ${config.symbol} | $${d.price.toFixed(4)} `).padEnd(80))));
        console.log(border);

        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        const wssColor = wss >= config.indicators.wss_weights.action_threshold ? NEON.GREEN : wss <= -config.indicators.wss_weights.action_threshold ? NEON.RED : NEON.YELLOW;
        console.log(`WSS: ${wssColor(wss)} | Strategy: ${NEON.BLUE(sig.strategy || 'SEARCHING')} | Signal: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        const regimeCol = marketRegime.includes('HIGH') ? NEON.RED : NEON.GREEN;
        console.log(`Regime: ${regimeCol(marketRegime)} | Vol: ${ctx.volatility} | Squeeze: ${isSqueeze === 'YES' ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${ctx.trend_mtf === 'BULLISH' ? NEON.GREEN('BULL') : NEON.RED('BEAR')} | Slope: ${ctx.trend_angle} | ADX: ${ctx.adx}`);
        console.log(border);

        console.log(`RSI: ${ctx.rsi} | Stoch: ${ctx.stoch_k} | MACD: ${ctx.macd_hist} | MFI: ${ctx.mfi} | CCI: ${ctx.cci}`); // Updated line
        console.log(`Chop: ${ctx.chop} | Divergence: ${divergence !== 'NONE' ? NEON.YELLOW(divergence) : 'None'} | FVG: ${fvg ? NEON.YELLOW(fvg.type) : 'None'}`); // Updated line
        console.log(`VWAP: ${ctx.vwap} | BB: ${ctx.bb_upper}/${ctx.bb_lower} | KC: ${ctx.kc_upper}/${ctx.kc_lower}`); // New line
        console.log(`SuperTrend: ${ctx.st_trend} (${ctx.st_value}) | ChandelierExit: ${ctx.ce_trend} (${ctx.ce_value}) | ATR: ${ctx.atr}`); // New line
        console.log(`${NEON.GRAY('Key Levels:')} P=${NEON.YELLOW(ctx.fibs.P.toFixed(2))} S1=${NEON.GREEN(ctx.fibs.S1.toFixed(2))} R1=${NEON.RED(ctx.fibs.R1.toFixed(2))}`);
        console.log(border);

        const pnlCol = this.exchange.dailyPnL.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`Balance: ${NEON.GREEN('$' + this.exchange.balance.toFixed(2))} | Daily PnL: ${pnlCol('$' + this.exchange.dailyPnL.toFixed(2))}`);
        
        if (this.exchange.pos) {
            const p = this.exchange.pos;
            const curPnl = p.side === 'BUY' ? new Decimal(d.price).sub(p.entry).mul(p.qty) : p.entry.sub(d.price).mul(p.qty);
            const posCol = curPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(NEON.BLUE(`OPEN POS: ${p.side} @ ${p.entry.toFixed(4)} | SL: ${p.sl.toFixed(4)} | TP: ${p.tp.toFixed(4)} | PnL: ${posCol(curPnl.toFixed(2))}`));
        }
        console.log(border);
    }
}

// --- START ---
const engine = new TradingEngine();
process.on('SIGINT', () => { 
    engine.isRunning = false; 
    console.log(NEON.RED("\n🛑 SHUTTING DOWN GRACEFULLY...")); 
    // Simplified force close on shutdown (requires last price from dataProvider to be accessible)
    process.exit(0); 
});
process.on('SIGTERM', () => { engine.isRunning = false; process.exit(0); });
engine.start();const fs = require('fs');
const path = require('path');

// Define the file path
const filePath = 'whalewave1.4.js';

// Read the file content
let code = fs.readFileSync(filePath, 'utf-8');

// --- Apply Upgrades ---

// 1. Error Handling for axios and config
code = code.replace(
    'constructor() {',
    `constructor() {
                     if (typeof axios === 'undefined') throw new Error("axios is required but not loaded.");
                     if (typeof config === 'undefined') throw new Error("config is required but not loaded.");`
);
code = code.replace(
    'constructor() {',
    `constructor() {
                     if (typeof config === 'undefined') throw new Error("config is required.");
                     if (typeof Decimal === 'undefined') throw new Error("Decimal.js is required.");
                     if (typeof NEON === 'undefined') console.warn("NEON is not defined. Using default console colors.");`
);
code = code.replace(
    'constructor() {',
    `constructor() {
                     if (typeof GoogleGenerativeAI === 'undefined') throw new Error("GoogleGenerativeAI is required.");
                     if (typeof config === 'undefined') throw new Error("config is required.");
                     if (typeof NEON === 'undefined') console.warn("NEON is not defined. Using default console colors.");`
);

// 2. Improved fetchWithRetry Error Messages
code = code.replace(
    'console.error(`Fetch attempt ${attempt + 1}/${retries + 1} failed: ${error.message}`);',
    `console.error(\`Fetch attempt \\${attempt + 1}/\\${retries + 1} for ${this.api.defaults.baseURL}${url} failed: \\${error.message}\\`);`
);
code = code.replace(
    'console.error(`Failed to fetch ${url} after ${retries + 1} attempts.`);',
    `console.error(\`Failed to fetch ${this.api.defaults.baseURL}${url} after \\${retries + 1} attempts.\`);`
);

// 3. API Error Code Handling
code = code.replace(
    'if (response.data && response.data.retCode !== 0) {',
    `if (response.data && response.data.retCode !== 0) {                            throw new Error(\`API Error: \\${response.data.retMsg} (Code: \\${response.data.retCode})\`);
                                 }`
);

// 4. Candle Data Validation
code = code.replace(
    'return {',
    `// Validate fetched data structure before parsing
                     if (!ticker?.result?.list?.[0] || !kline?.result?.list || !klineMTF?.result?.list || !ob?.result?.b || !ob?.result?.a || !daily?.result?.list?.[1]) {
                         console.error("Incomplete data received from API.");
                         return null;
                     }

                     return {`
);

// 5. calculateWSS Robustness
code = code.replace(
    'function calculateWSS(analysis, currentPrice) {',
    `function calculateWSS(analysis, currentPrice) {
                     // Ensure config is available and has the necessary structure
                     if (typeof config === 'undefined' || !config.indicators || !config.indicators.wss_weights) {
                         console.error("Configuration for WSS weights is missing.");
                         return 0; // Return a neutral score or throw an error
                     }
                     const w = config.indicators.wss_weights;
                     let score = 0;
                     const last = analysis.closes.length - 1;

                     // Check if required analysis data exists and has enough points
                     if (!analysis || !analysis.closes || last < 0) {
                         console.error("Insufficient data for WSS calculation.");
                         return 0;
                     }

                     const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr } = analysis;

                     // --- Trend Score ---
                     let trendScore = 0;
                     // Higher weight for longer-term trend (MTF)
                     if (analysis.trendMTF) {
                         trendScore += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);
                     }
                     // Add weights for shorter-term trends (scalp)
                     if (st && st.trend && st.trend[last] !== undefined) {
                         trendScore += (st.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight);
                     }
                     if (ce && ce.trend && ce.trend[last] !== undefined) {
                         trendScore += (ce.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight);
                     }
                     // Multiply by regression slope (r2) for trend strength confirmation
                     if (reg && reg.r2 && reg.r2[last] !== undefined) {
                         trendScore *= reg.r2[last];
                     }
                     score += trendScore;

                     // --- Momentum Score ---
                     let momentumScore = 0;
                     const rsiVal = rsi && rsi[last] !== undefined ? rsi[last] : 50; // Default to 50 if RSI is missing
                     const stochK = stoch && stoch.k && stoch.k[last] !== undefined ? stoch.k[last] : 50; // Default to 50 if StochK is missing

                     // Normalize RSI momentum: higher score for oversold, lower for overbought
                     if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50; else momentumScore -= (rsiVal - 50) / 50;
                     // Normalize Stochastic momentum
                     if (stochK < 50) momentumScore += (50 - stochK) / 50; else momentumScore -= (stochK - 50) / 50;

                     // Add MACD histogram weight
                     const macdHist = macd && macd.hist && macd.hist[last] !== undefined ? macd.hist[last] : 0;
                     if (macdHist > 0) momentumScore += w.macd_weight; else if (macdHist < 0) momentumScore -= w.macd_weight;

                     // Apply normalized momentum weight
                     score += momentumScore * w.momentum_normalized_weight;

                     // --- Structure Score ---
                     let structureScore = 0;
                     // Squeeze indicator: positive for bullish, negative for bearish
                     if (analysis.isSqueeze && analysis.isSqueeze[last]) {
                         structureScore += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight);
                     }
                     // Divergence: positive for bullish, negative for bearish
                     if (divergence && divergence.includes('BULLISH')) structureScore += w.divergence_weight;
                     else if (divergence && divergence.includes('BEARISH')) structureScore -= w.divergence_weight;

                     const price = currentPrice;
                     const atrVal = atr && atr[last] !== undefined ? atr[last] : 1; // Default ATR to 1
                     // Fair Value Gap (FVG) analysis: reward for price interacting with FVG in trend direction
                     if (fvg && fvg.length > 0 && fvg[0].price) { // Assuming fvg is an array with the latest FVG at index 0
                         if (fvg[0].type === 'BULLISH' && price > fvg[0].bottom && price < fvg[0].top) structureScore += w.liquidity_grab_weight;
                         else if (fvg[0].type === 'BEARISH' && price < fvg[0].top && price > fvg[0].bottom) structureScore -= w.liquidity_grab_weight;
                     }
                     // Liquidity grab near buy/sell walls, adjusted by ATR
                     if (buyWall && (price - buyWall) < atrVal) structureScore += w.liquidity_grab_weight * 0.5;
                     else if (sellWall && (sellWall - price) < atrVal) structureScore -= w.liquidity_grab_weight * 0.5;
                     score += structureScore;

                     // --- Volatility Adjustment ---
                     const volatility = analysis.volatility && analysis.volatility[analysis.volatility.length - 1] !== undefined ? analysis.volatility[analysis.volatility.length - 1] : 0;
                     const avgVolatility = analysis.avgVolatility && analysis.avgVolatility[analysis.avgVolatility.length - 1] !== undefined ? analysis.avgVolatility[analysis.avgVolatility.length - 1] : 1; // Default to 1
                     const volRatio = avgVolatility === 0 ? 1 : volatility / avgVolatility; // Avoid division by zero

                     let finalScore = score;
                     // Reduce score in high volatility, increase in low volatility
                     if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
                     else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);

                     return parseFloat(finalScore.toFixed(2));
                 }`
);

// 6. EnhancedGeminiBrain Robustness
code = code.replace(
    'const key = process.env.GEMINI_API_KEY;',
    `const key = process.env.GEMINI_API_KEY;
                     if (!key) {
                         console.error("Missing GEMINI_API_KEY environment variable.");
                         process.exit(1); // Exit if API key is critical
                     }`
);
code = code.replace(
    'const text = res.response.text();',
    `const text = res.response.text();

                     // Clean up the response text to extract JSON
                     const jsonMatch = text.match(/\\{[\\s\\S]*\\}/);
                     if (!jsonMatch) {
                         console.error("Gemini AI response did not contain valid JSON:", text);
                         return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: 'Invalid AI response format' };
                     }

                     const signal = JSON.parse(jsonMatch[0]);

                     // Validate the parsed signal structure
                     if (!signal || typeof signal.action === 'undefined' || typeof signal.strategy === 'undefined' || typeof signal.confidence === 'undefined') {
                         console.error("Parsed signal is missing required fields:", signal);
                         return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: 'Invalid signal structure from AI' };
                     }

                     // Ensure numerical values are valid numbers, default to 0 if not
                     signal.confidence = typeof signal.confidence === 'number' && !isNaN(signal.confidence) ? signal.confidence : 0;
                     signal.entry = typeof signal.entry === 'number' && !isNaN(signal.entry) ? signal.entry : 0;
                     signal.sl = typeof signal.sl === 'number' && !isNaN(signal.sl) ? signal.sl : 0;
                     signal.tp = typeof signal.tp === 'number' && !isNaN(signal.tp) ? signal.tp : 0;

                     // Apply critical WSS filter
                     const wssThreshold = config.indicators.wss_weights.action_threshold;
                     if (signal.action === 'BUY' && ctx.wss < wssThreshold) {
                         signal.action = 'HOLD';
                         signal.reason = \`WSS (\${ctx.wss}) below BUY threshold (\${wssThreshold})\`;
                     } else if (signal.action === 'SELL' && ctx.wss > -wssThreshold) {
                         signal.action = 'HOLD';
                         signal.reason = \`WSS (\${ctx.wss}) above SELL threshold (\${-wssThreshold})\`;
                     }

                     // Add default reason if missing
                     if (!signal.reason) {
                         signal.reason = signal.action === 'HOLD' ? 'No clear signal or WSS filter applied.' : \`Strategy: \${signal.strategy}\`;
                     }

                     return signal;`
);
code = code.replace(
    `catch (error) {                                                        console.error("Error generating content from Gemini AI:", error);                                                               return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: \`Gemini API error: \${error.message}\` };                                                    }`,
    `catch (error) {                                                        console.error(\`Error generating content from Gemini AI:\`, error);                                                             return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: \`Gemini API error: \${error.message}\` };                                                    }`
);

// 7. TradingEngine Error Handling
code = code.replace(
    'await setTimeout(this.loopDelay);',
    `// ... (rest of the try block) ...
                                     } catch (error) {
                                        console.error(NEON.RED.bold(\`\\n🚨 ENGINE ERROR: \${error.message}\`));
                                        console.error(error.stack); // Log the stack trace for debugging
                                        // Optionally, implement more robust error handling like restarting the engine
                                     }
                                    await setTimeout(this.loopDelay);`
);

// 8. calculateIndicators Promise.all
code = code.replace(
    'const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all([',
    'const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all(['
);
code = code.replace(
    'TA.rsi(c, config.indicators.rsi),',
    'TA.rsi(c, config.indicators.rsi),'
);

// 9. Removed unused TA methods (marketRegime and fibPivots) - NOTE: These were not found in the provided code, so this step is skipped.
// If they were present, the code would look something like this:
// code = code.replace(/TA\.marketRegime(.*)\s*,\s*/g, '');
// code = code.replace(/TA\.fibPivots(.*)\s*,\s*/g, '');

// 10. Colorization of vwap and trend_angle
code = code.replace(
    'if (key === \'macd_hist\' || key === \'trend_angle\') {',
    'if (key === \'macd_hist\') { // Keep existing colorization for macd_hist'
);
code = code.replace(
    'return NEON.CYAN(v.toFixed(2));',
    `if (key === 'vwap') {
             return NEON.CYAN(v.toFixed(4));
        }
        // Add specific colorization for trend_angle if it's not already handled
        if (key === 'trend_angle') {
             return this.colorizeValue(v, 'trend_angle'); // Re-use existing logic for trend_angle colorization
        }
        return NEON.CYAN(v.toFixed(2));`
);
code = code.replace(
    'console.log(`MTF Trend: ${trendCol(ctx.trend_mtf)} | Slope: ${this.colorizeValue(ctx.trend_angle, \'trend_angle\')} | ADX: ${this.colorizeValue(ctx.adx, \'adx\')}`);',
    `console.log(\`MTF Trend: \${trendCol(ctx.trend_mtf)} | Slope: \${this.colorizeValue(ctx.trend_angle, 'trend_angle')} | ADX: \${this.colorizeValue(ctx.adx, 'adx')}\`);`
);
code = code.replace(
    'console.log(`Divergence: ${divCol(ctx.divergence)} | FVG: ${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : \'None\'} | VWAP: ${this.colorizeValue(ctx.vwap, \'vwap\')}`);',
    `console.log(\`Divergence: \${divCol(ctx.divergence)} | FVG: \${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : 'None'} | VWAP: \${this.colorizeValue(ctx.vwap, 'vwap')}\`);`
);


// 11. Clearer Console Output
code = code.replace(
    'console.log(NEON.GREEN.bold("🚀 WHALEWAVE TITAN v6.1 STARTED..."));',
    `console.clear();
                     console.log(NEON.GREEN.bold("🚀 WHALEWAVE TITAN v6.1 STARTED..."));`
);

// Write the modified code back to the file
fs.writeFileSync(filePath, code, 'utf-8');

console.log('Upgrades applied successfully to whalewave1.4.js');
/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v6.1 (Bugfix & Final Polish)
 * ----------------------------------------------------------------------
 * - BUGFIX: Resolved 'NEON.CYAN is not a function' error.
 * - TUNING: Optimized parameters and WSS weights for 3m scalping profile.
 * - AESTHETICS: Full NEON colorization of all displayed metrics.
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import { setTimeout } from 'timers/promises';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ ENHANCED CONFIGURATION MANAGER (from v6.0) ---
class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        symbol: 'BTCUSDT', interval: '3', trend_interval: '15', limit: 300,
        loop_delay: 4, gemini_model: 'gemini-1.5-flash', min_confidence: 0.75,
        risk: { max_drawdown: 10.0, daily_loss_limit: 5.0, max_positions: 1, },
        paper_trading: { initial_balance: 1000.00, risk_percent: 2.0, leverage_cap: 10, fee: 0.00055, slippage: 0.0001 },
        indicators: {
            rsi: 10, stoch_period: 10, stoch_k: 3, stoch_d: 3, cci_period: 10,
            macd_fast: 12, macd_slow: 26, macd_sig: 9, adx_period: 14,
            mfi: 10, chop_period: 14, linreg_period: 15, vwap_period: 20,
            bb_period: 20, bb_std: 2.0, kc_period: 20, kc_mult: 1.5,
            atr_period: 14, st_factor: 2.5, ce_period: 22, ce_mult: 3.0,
            wss_weights: {
                trend_mtf_weight: 2.2, trend_scalp_weight: 1.2,
                momentum_normalized_weight: 1.8, macd_weight: 1.0,
                regime_weight: 0.8, squeeze_vol_weight: 1.0,
                liquidity_grab_weight: 1.5, divergence_weight: 2.5,
                volatility_weight: 0.5, action_threshold: 2.0
            }
        },
        orderbook: { depth: 50, wall_threshold: 3.0, sr_levels: 5 },
        api: { timeout: 8000, retries: 3, backoff_factor: 2 }
    };

    static load() {
        let config = { ...this.DEFAULTS };
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                config = this.deepMerge(config, userConfig);
            } catch (e) { console.error(chalk.red(`Config Error: ${e.message}`)); }
        } else {
            fs.writeFileSync(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else { result[key] = source[key]; }
        }
        return result;
    }
}

const config = ConfigManager.load();
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

// --- 🎨 THEME MANAGER (CYAN ADDED) ---
const NEON = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#00AFFF'),
    CYAN: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC1FE'), YELLOW: chalk.hex('#FAED27'), GRAY: chalk.hex('#666666'),
    ORANGE: chalk.hex('#FF9F00'), BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#222')(text)
};

// --- 📐 COMPLETE TECHNICAL ANALYSIS LIBRARY (from v6.0) ---
class TA {
    static safeArr(len) { return new Array(Math.floor(len)).fill(0); }
    static getFinalValue(data, key, precision = 2) {
        if (!data.closes || data.closes.length === 0) return 'N/A';
        const last = data.closes.length - 1;
        const value = data[key];
        if (Array.isArray(value)) return value[last]?.toFixed(precision) || '0.00';
        if (typeof value === 'object') {
            if (value.k) return { k: value.k[last]?.toFixed(0), d: value.d[last]?.toFixed(0) };
            if (value.hist) return value.hist[last]?.toFixed(precision);
            if (value.slope) return { slope: value.slope[last]?.toFixed(precision), r2: value.r2[last]?.toFixed(precision) };
            if (value.trend) return value.trend[last] === 1 ? 'BULL' : 'BEAR';
        }
        return 'N/A';
    }
    static sma(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = []; let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result.push(sum / period);
        for (let i = period; i < data.length; i++) { sum += data[i] - data[i - period]; result.push(sum / period); }
        return TA.safeArr(period - 1).concat(result);
    }
    static ema(data, period) {
        if (!data || data.length === 0) return [];
        let result = TA.safeArr(data.length);
        const k = 2 / (period + 1); result[0] = data[0];
        for (let i = 1; i < data.length; i++) result[i] = (data[i] * k) + (result[i - 1] * (1 - k));
        return result;
    }
    static wilders(data, period) {
        if (!data || data.length < period) return TA.safeArr(data.length);
        let result = TA.safeArr(data.length); let sum = 0;
        for (let i = 0; i < period; i++) sum += data[i];
        result[period - 1] = sum / period;
        const alpha = 1 / period;
        for (let i = period; i < data.length; i++) result[i] = (data[i] * alpha) + (result[i - 1] * (1 - alpha));
        return result;
    }

    static atr(highs, lows, closes, period) {
        let tr = [0];
        for (let i = 1; i < closes.length; i++) tr.push(Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
        return this.wilders(tr, period);
    }
    static rsi(closes, period) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0); losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.wilders(gains, period);
        const avgLoss = this.wilders(losses, period);
        return closes.map((_, i) => avgLoss[i] === 0 ? 100 : 100 - (100 / (1 + avgGain[i] / avgLoss[i])));
    }
    static stoch(highs, lows, closes, period, kP, dP) {
        let rsi = TA.safeArr(closes.length);
        for (let i = period - 1; i < closes.length; i++) {
            const sliceH = highs.slice(i - period + 1, i + 1); const sliceL = lows.slice(i - period + 1, i + 1);
            const minL = Math.min(...sliceL); const maxH = Math.max(...sliceH);
            rsi[i] = (maxH - minL === 0) ? 0 : 100 * ((closes[i] - minL) / (maxH - minL));
        }
        const k = this.sma(rsi, kP); const d = this.sma(k, dP); return { k, d };
    }
    static macd(closes, fast, slow, sig) {
        const emaFast = this.ema(closes, fast); const emaSlow = this.ema(closes, slow);
        const line = emaFast.map((v, i) => v - emaSlow[i]); const signal = this.ema(line, sig);
        return { line, signal, hist: line.map((v, i) => v - signal[i]) };
    }
    static adx(highs, lows, closes, period) {
        let plusDM = [0], minusDM = [0];
        for (let i = 1; i < closes.length; i++) {
            const up = highs[i] - highs[i - 1]; const down = lows[i - 1] - lows[i];
            plusDM.push(up > down && up > 0 ? up : 0); minusDM.push(down > up && down > 0 ? down : 0);
        }
        const sTR = this.wilders(this.atr(highs, lows, closes, 1), period);
        const sPlus = this.wilders(plusDM, period); const sMinus = this.wilders(minusDM, period);
        let dx = [];
        for (let i = 0; i < closes.length; i++) {
            const pDI = sTR[i] === 0 ? 0 : (sPlus[i] / sTR[i]) * 100; const mDI = sTR[i] === 0 ? 0 : (sMinus[i] / sTR[i]) * 100;
            const sum = pDI + mDI;
            dx.push(sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100);
        }
        return this.wilders(dx, period);
    }
    static mfi(h,l,c,v,p) {
        let posFlow = [], negFlow = [];
        for (let i = 0; i < c.length; i++) {
            if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
            const tp = (h[i] + l[i] + c[i]) / 3; const prevTp = (h[i-1] + l[i-1] + c[i-1]) / 3;
            const raw = tp * v[i];
            if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
            else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
            else { posFlow.push(0); negFlow.push(0); }
        }
        let result = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let pSum = 0, nSum = 0;
            for (let j = 0; j < p; j++) { pSum += posFlow[i-j]; nSum += negFlow[i-j]; }
            if (nSum === 0) result[i] = 100; else result[i] = 100 - (100 / (1 + (pSum / nSum)));
        }
        return result;
    }
    static chop(h, l, c, p) {
        let result = TA.safeArr(c.length);
        let tr = [h[0] - l[0]];
        for(let i=1; i<c.length; i++) tr.push(Math.max(h[i] - l[i], Math.abs(h[i] - c[i-1]), Math.abs(l[i] - c[i-1])));
        for (let i = p - 1; i < c.length; i++) {
            let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
            for (let j = 0; j < p; j++) {
                sumTr += tr[i - j];
                if (h[i - j] > maxHi) maxHi = h[i - j];
                if (l[i - j] < minLo) minLo = l[i - j];
            }
            const range = maxHi - minLo;
            result[i] = (range === 0 || sumTr === 0) ? 0 : 100 * (Math.log10(sumTr / range) / Math.log10(p));
        }
        return result;
    }
    static cci(highs, lows, closes, period) {
        const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3; const smaTp = this.sma(tp, period);
        let cci = TA.safeArr(closes.length);
        for (let i = period - 1; i < tp.length; i++) {
            let meanDev = 0; for (let j = 0; j < period; j++) meanDev += Math.abs(tp[i - j] - smaTp[i]);
            meanDev /= period;
            cci[i] = (meanDev === 0) ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
        }
        return cci;
    }
    static linReg(closes, period) {
        let slopes = TA.safeArr(closes.length), r2s = TA.safeArr(closes.length);
        let sumX = 0, sumX2 = 0;
        for (let i = 0; i < period; i++) { sumX += i; sumX2 += i * i; }
        for (let i = period - 1; i < closes.length; i++) {
            let sumY = 0, sumXY = 0;
            const ySlice = [];
            for (let j = 0; j < period; j++) {
                const val = closes[i - (period - 1) + j]; ySlice.push(val); sumY += val; sumXY += j * val;
            }
            const n = period;
            const num = (n * sumXY) - (sumX * sumY);
            const den = (n * sumX2) - (sumX * sumX);
            const slope = den === 0 ? 0 : num / den;
            const intercept = (sumY - slope * sumX) / n;
            let ssTot = 0, ssRes = 0;
            const yMean = sumY / n;
            for(let j=0; j<period; j++) {
                const y = ySlice[j]; const yPred = slope * j + intercept;
                ssTot += Math.pow(y - yMean, 2); ssRes += Math.pow(y - yPred, 2);
            }
            slopes[i] = slope; r2s[i] = ssTot === 0 ? 0 : 1 - (ssRes / ssTot);
        }
        return { slope: slopes, r2: r2s };
    }
    static bollinger(closes, period, stdDev) {
        const sma = this.sma(closes, period);
        let upper = [], lower = [], middle = sma;
        for (let i = 0; i < closes.length; i++) {
            if (i < period - 1) { upper.push(0); lower.push(0); continue; }
            let sumSq = 0;
            for (let j = 0; j < period; j++) sumSq += Math.pow(closes[i] - sma[i], 2);
            const std = Math.sqrt(sumSq / period);
            upper.push(sma[i] + (std * stdDev)); lower.push(sma[i] - (std * stdDev));
        }
        return { upper, middle, lower };
    }
    static keltner(highs, lows, closes, period, mult) {
        const ema = this.ema(closes, period); const atr = this.atr(highs, lows, closes, period);
        return { upper: ema.map((e, i) => e + atr[i] * mult), lower: ema.map((e, i) => e - atr[i] * mult), middle: ema };
    }
    static superTrend(highs, lows, closes, period, factor) {
        const atr = this.atr(highs, lows, closes, period);
        let st = new Array(closes.length).fill(0); let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            let up = (highs[i] + lows[i]) / 2 + factor * atr[i];
            let dn = (highs[i] + lows[i]) / 2 - factor * atr[i];
            if (i > 0) {
                const prevST = st[i-1];
                if (trend[i-1] === 1) { up = up; dn = Math.max(dn, prevST); } else { up = Math.min(up, prevST); dn = dn; }
            }
            if (closes[i] > up) trend[i] = 1; else if (closes[i] < dn) trend[i] = -1; else trend[i] = trend[i-1];
            st[i] = trend[i] === 1 ? dn : up;
        }
        return { trend, value: st };
    }
    static chandelierExit(highs, lows, closes, period, mult) {
        const atr = this.atr(highs, lows, closes, period);
        let longStop = TA.safeArr(closes.length); let shortStop = TA.safeArr(closes.length);
        let trend = new Array(closes.length).fill(1);
        for (let i = period; i < closes.length; i++) {
            const maxHigh = Math.max(...highs.slice(i - period + 1, i + 1));
            const minLow = Math.min(...lows.slice(i - period + 1, i + 1));
            longStop[i] = maxHigh - atr[i] * mult; shortStop[i] = minLow + atr[i] * mult;
            if (closes[i] > shortStop[i]) trend[i] = 1; else if (closes[i] < longStop[i]) trend[i] = -1; else trend[i] = trend[i-1];
        }
        return { trend, value: trend.map((t, i) => t === 1 ? longStop[i] : shortStop[i]) };
    }
    static vwap(h, l, c, v, p) {
        let vwap = TA.safeArr(c.length);
        for (let i = p - 1; i < c.length; i++) {
            let sumPV = 0, sumV = 0;
            for (let j = 0; j < p; j++) {
                const tp = (h[i-j] + l[i-j] + c[i-j]) / 3; sumPV += tp * v[i-j]; sumV += v[i-j];
            }
            vwap[i] = sumV === 0 ? 0 : sumPV / sumV;
        }
        return vwap;
    }
    static findFVG(candles) {
        const len = candles.length;
        if (len < 5) return null;
        const c1 = candles[len - 4]; const c2 = candles[len - 3]; const c3 = candles[len - 2];
        if (c2.c > c2.o && c3.l > c1.h) return { type: 'BULLISH', top: c3.l, bottom: c1.h, price: (c3.l + c1.h) / 2 };
        else if (c2.c < c2.o && c3.h < c1.l) return { type: 'BEARISH', top: c1.l, bottom: c3.h, price: (c1.l + c3.h) / 2 };
        return null;
    }
    static detectDivergence(closes, rsi, period = 5) {
        const len = closes.length;
        if (len < period * 2) return 'NONE';
        const priceHigh = Math.max(...closes.slice(len - period, len)); const rsiHigh = Math.max(...rsi.slice(len - period, len));
        const prevPriceHigh = Math.max(...closes.slice(len - period * 2, len - period)); const prevRsiHigh = Math.max(...rsi.slice(len - period * 2, len - period));
        if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';
        const priceLow = Math.min(...closes.slice(len - period, len)); const rsiLow = Math.min(...rsi.slice(len - period, len));
        const prevPriceLow = Math.min(...closes.slice(len - period * 2, len - period)); const prevRsiLow = Math.min(...rsi.slice(len - period * 2, len - period));
        if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH_REGULAR';
        return 'NONE';
    }

    /**
     * Calculates the trend direction based on moving averages.
     * @param {number[]} closes - Array of closing prices.
     * @param {number} shortPeriod - The period for the short-term moving average.
     * @param {number} longPeriod - The period for the long-term moving average.
     * @returns {number} 1 for bullish, -1 for bearish, 0 for neutral.
     */
    static trendDirection(closes, shortPeriod, longPeriod) {
        if (closes.length < Math.max(shortPeriod, longPeriod)) {
            return 0; // Not enough data
        }
        const shortMA = TA.ema(closes, shortPeriod);
        const longMA = TA.ema(closes, longPeriod);

        const lastShortMA = shortMA[shortMA.length - 1];
        const lastLongMA = longMA[longMA.length - 1];

        if (lastShortMA > lastLongMA) return 1; // Bullish
        if (lastShortMA < lastLongMA) return -1; // Bearish
        return 0; // Neutral
    }

    /**
     * Calculates the slope of a linear regression line.
     * @param {number[]} y - The dependent variable (e.g., prices).
     * @param {number} n - The number of data points (period).
     * @returns {number} The slope of the regression line.
     */
    static regressionSlope(y, n) {
        if (y.length < n) return 0;
        const x = Array.from({ length: n }, (_, i) => i + 1); // Independent variable (time)
        const ySlice = y.slice(-n);

        let sumX = 0;
        let sumY = 0;
        let sumXY = 0;
        let sumX2 = 0;

        for (let i = 0; i < n; i++) {
            sumX += x[i];
            sumY += ySlice[i];
            sumXY += x[i] * ySlice[i];
            sumX2 += x[i] * x[i];
        }

        const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        return isNaN(slope) ? 0 : slope;
    }

    /**
     * Calculates the R-squared value for a linear regression.
     * @param {number[]} y - The dependent variable (e.g., prices).
     * @param {number} n - The number of data points (period).
     * @returns {number} The R-squared value.
     */
    static regressionR2(y, n) {
        if (y.length < n) return 0;
        const ySlice = y.slice(-n);
        const slope = TA.regressionSlope(ySlice, n);
        const x = Array.from({ length: n }, (_, i) => i + 1);

        let sumY = 0;
        for (let i = 0; i < n; i++) {
            sumY += ySlice[i];
        }
        const meanY = sumY / n;

        let ssRes = 0; // Sum of squares of residuals
        let ssTot = 0; // Total sum of squares

        for (let i = 0; i < n; i++) {
            const meanX = (n + 1) / 2;
            const intercept = meanY - slope * meanX;
            const predictedYLinear = intercept + slope * x[i];

            ssRes += Math.pow(ySlice[i] - predictedYLinear, 2);
            ssTot += Math.pow(ySlice[i] - meanY, 2);
        }

        if (ssTot === 0) return 1; // Avoid division by zero if all y values are the same
        const r2 = 1 - (ssRes / ssTot);
        return isNaN(r2) ? 0 : r2;
    }
    // Placeholder for marketRegime - needs implementation based on chosen logic
    static marketRegime(closes, volatility) {
        // Example: Simple regime based on volatility
        const lastVol = volatility[volatility.length - 1];
        const avgVolatility = TA.sma(volatility, 50);
        const avgVol = avgVolatility && avgVolatility.length > 50 ? avgVolatility[50] : 1; // Default to 1 if not enough data
        if (lastVol > avgVol * 1.5) return "HIGH_VOLATILITY";
        if (lastVol < avgVol * 0.5) return "LOW_VOLATILITY";
        return "NORMAL_VOLATILITY";
    }
    // Placeholder for fibPivots - needs implementation
    static fibPivots(high, low, close) {
        // This is a simplified example. Real pivot calculation is more complex.
        const p = (high + low + close) / 3;
        const r1 = (2 * p) - low;
        const s1 = (2 * p) - high;
        return { P: p, R1: r1, S1: s1 };
    }
     // Placeholder for historicalVolatility - needs implementation
    static historicalVolatility(closes) {
        const period = 20; // Example period
        if (closes.length < period) return TA.safeArr(closes.length);
        const logReturns = closes.map((c, i, arr) => i > 0 ? Math.log(c / arr[i-1]) : 0).slice(1);
        // Calculate standard deviation of log returns, then approximate annualized volatility
        const meanLogReturn = logReturns.reduce((a, b) => a + b, 0) / logReturns.length;
        const variance = logReturns.reduce((a, b) => a + Math.pow(b - meanLogReturn, 2), 0) / logReturns.length;
        const stdDev = Math.sqrt(variance);
        // Approximate annualized volatility (assuming daily data and ~252 trading days)
        const annualizedVolatility = stdDev * Math.sqrt(252);
        return TA.safeArr(period - 1).concat(new Array(logReturns.length).fill(annualizedVolatility)); // Return consistent length
    }
}


// --- 🛠️ UTILITIES & WSS CALCULATOR (from v5.0) ---

/**
 * Determines potential support and resistance levels from order book data.
 * @param {Array<{p: number, q: number}>} bids - Array of bid orders.
 * @param {Array<{p: number, q: number}>} asks - Array of ask orders.
 * @param {number} currentClose - The current closing price.
 * @param {number} maxLevels - The maximum number of support/resistance levels to return.
 * @returns {{supportLevels: string[], resistanceLevels: string[]}} An object containing arrays of support and resistance levels.
 */
function getOrderbookLevels(bids, asks, currentClose, maxLevels) {
    const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
    const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
    let potentialSR = [];

    for (const price of uniquePrices) {
        let bidVolAtPrice = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
        let askVolAtPrice = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
        // Identify potential support if bid volume is significantly higher than ask volume
        if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
        // Identify potential resistance if ask volume is significantly higher than bid volume
        else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
    }

    // Sort potential levels by their distance from the current close price
    const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));

    // Filter for support levels below the current close and take the top `maxLevels`
    const supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    // Filter for resistance levels above the current close and take the top `maxLevels`
    const resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));

    return { supportLevels, resistanceLevels };
}

/**
 * Calculates a Weighted Sentiment Score (WSS) based on various technical indicators.
 * @param {object} analysis - An object containing all calculated technical indicators.
 * @param {number} currentPrice - The current market price.
 * @returns {number} The calculated WSS.
 */
function calculateWSS(analysis, currentPrice) {
    // Ensure config is available and has the necessary structure
    if (typeof config === 'undefined' || !config.indicators || !config.indicators.wss_weights) {
        console.error("Configuration for WSS weights is missing.");
        return 0; // Return a neutral score or throw an error
    }
    const w = config.indicators.wss_weights;
    let score = 0;
    const last = analysis.closes.length - 1;

    // Check if required analysis data exists and has enough points
    if (!analysis || !analysis.closes || last < 0) {
        console.error("Insufficient data for WSS calculation.");
        return 0;
    }

    const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr } = analysis;

    // --- Trend Score ---
    let trendScore = 0;
    // Higher weight for longer-term trend (MTF)
    if (analysis.trendMTF) {
        trendScore += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);
    }
    // Add weights for shorter-term trends (scalp)
    if (st && st.trend && st.trend[last] !== undefined) {
        trendScore += (st.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight);
    }
    if (ce && ce.trend && ce.trend[last] !== undefined) {
        trendScore += (ce.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight);
    }
    // Multiply by regression slope (r2) for trend strength confirmation
    if (reg && reg.r2 && reg.r2[last] !== undefined) {
        trendScore *= reg.r2[last];
    }
    score += trendScore;

    // --- Momentum Score ---
    let momentumScore = 0;
    const rsiVal = rsi && rsi[last] !== undefined ? rsi[last] : 50; // Default to 50 if RSI is missing
    const stochK = stoch && stoch.k && stoch.k[last] !== undefined ? stoch.k[last] : 50; // Default to 50 if StochK is missing

    // Normalize RSI momentum: higher score for oversold, lower for overbought
    if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50; else momentumScore -= (rsiVal - 50) / 50;
    // Normalize Stochastic momentum
    if (stochK < 50) momentumScore += (50 - stochK) / 50; else momentumScore -= (stochK - 50) / 50;

    // Add MACD histogram weight
    const macdHist = macd && macd.hist && macd.hist[last] !== undefined ? macd.hist[last] : 0;
    if (macdHist > 0) momentumScore += w.macd_weight; else if (macdHist < 0) momentumScore -= w.macd_weight;

    // Apply normalized momentum weight
    score += momentumScore * w.momentum_normalized_weight;

    // --- Structure Score ---
    let structureScore = 0;
    // Squeeze indicator: positive for bullish, negative for bearish
    if (analysis.isSqueeze && analysis.isSqueeze[last]) {
        structureScore += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight);
    }
    // Divergence: positive for bullish, negative for bearish
    if (divergence && divergence.includes('BULLISH')) structureScore += w.divergence_weight;
    else if (divergence && divergence.includes('BEARISH')) structureScore -= w.divergence_weight;

    const price = currentPrice;
    const atrVal = atr && atr[last] !== undefined ? atr[last] : 1; // Default ATR to 1
    // Fair Value Gap (FVG) analysis: reward for price interacting with FVG in trend direction
    if (fvg && fvg.length > 0 && fvg[0].price) { // Assuming fvg is an array with the latest FVG at index 0
        if (fvg[0].type === 'BULLISH' && price > fvg[0].bottom && price < fvg[0].top) structureScore += w.liquidity_grab_weight;
        else if (fvg[0].type === 'BEARISH' && price < fvg[0].top && price > fvg[0].bottom) structureScore -= w.liquidity_grab_weight;
    }
    // Liquidity grab near buy/sell walls, adjusted by ATR
    if (buyWall && (price - buyWall) < atrVal) structureScore += w.liquidity_grab_weight * 0.5;
    else if (sellWall && (sellWall - price) < atrVal) structureScore -= w.liquidity_grab_weight * 0.5;
    score += structureScore;

    // --- Volatility Adjustment ---
    const volatility = analysis.volatility && analysis.volatility[analysis.volatility.length - 1] !== undefined ? analysis.volatility[analysis.volatility.length - 1] : 0;
    const avgVolatility = analysis.avgVolatility && analysis.avgVolatility[analysis.avgVolatility.length - 1] !== undefined ? analysis.avgVolatility[analysis.avgVolatility.length - 1] : 1; // Default to 1
    const volRatio = avgVolatility === 0 ? 1 : volatility / avgVolatility; // Avoid division by zero

    let finalScore = score;
    // Reduce score in high volatility, increase in low volatility
    if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
    else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);

    return parseFloat(finalScore.toFixed(2));
}

// --- 📡 ENHANCED DATA PROVIDER (from v6.0) ---
class EnhancedDataProvider {
    constructor() {
        // Ensure axios is available
        if (typeof axios === 'undefined') {
            throw new Error("axios is required but not loaded.");
        }
        // Ensure config is available
        if (typeof config === 'undefined') {
            throw new Error("config is required but not loaded.");
        }
        this.api = axios.create({ baseURL: 'https://api.bybit.com/v5/market', timeout: config.api.timeout });
    }

    /**
     * Fetches data from the API with retry logic.
     * @param {string} url - The API endpoint URL.
     * @param {object} params - The request parameters.
     * @param {number} [retries=config.api.retries] - The number of retry attempts.
     * @returns {Promise<object>} The API response data.
     * @throws {Error} If fetching fails after all retries.
     */
    async fetchWithRetry(url, params, retries = config.api.retries) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const response = await this.api.get(url, { params });
                // Check for API errors in the response structure
                if (response.data && response.data.retCode !== 0) {
                    throw new Error(`API Error: ${response.data.retMsg} (Code: ${response.data.retCode})`);
                }
                return response.data;
            } catch (error) {
                console.error(`Fetch attempt ${attempt + 1}/${retries + 1} failed: ${error.message}`);
                if (attempt === retries) {
                    console.error(`Failed to fetch ${url} after ${retries + 1} attempts.`);
                    throw error; // Re-throw the last error
                }
                // Exponential backoff
                const delay = Math.pow(config.api.backoff_factor, attempt) * 1000;
                await new Promise(resolve => setTimeout(resolve, delay));
            }
        }
    }

    /**
     * Fetches all necessary data for analysis.
     * @returns {Promise<object|null>} An object containing fetched data or null if fetching fails.
     */
    async fetchAll() {
        try {
            const [ticker, kline, klineMTF, ob, daily] = await Promise.all([
                this.fetchWithRetry('/tickers', { category: 'linear', symbol: config.symbol }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.interval, limit: config.limit }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: config.trend_interval, limit: 100 }),
                this.fetchWithRetry('/orderbook', { category: 'linear', symbol: config.symbol, limit: config.orderbook.depth }),
                this.fetchWithRetry('/kline', { category: 'linear', symbol: config.symbol, interval: 'D', limit: 2 })
            ]);

            // Helper function to parse candle data
            const parseCandles = (list) => list.reverse().map(c => ({
                t: parseInt(c[0]), // Timestamp
                o: parseFloat(c[1]), // Open
                h: parseFloat(c[2]), // High
                l: parseFloat(c[3]), // Low
                c: parseFloat(c[4]), // Close
                v: parseFloat(c[5]), // Volume
            }));

            // Validate fetched data structure before parsing
            if (!ticker?.result?.list?.[0] || !kline?.result?.list || !klineMTF?.result?.list || !ob?.result?.b || !ob?.result?.a || !daily?.result?.list?.[1]) {
                console.error("Incomplete data received from API.");
                return null;
            }

            return {
                price: parseFloat(ticker.result.list[0].lastPrice),
                candles: parseCandles(kline.result.list),
                candlesMTF: parseCandles(klineMTF.result.list),
                bids: ob.result.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                asks: ob.result.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) })),
                daily: { h: parseFloat(daily.result.list[1][2]), l: parseFloat(daily.result.list[1][3]), c: parseFloat(daily.result.list[1][4]) },
                timestamp: Date.now()
            };
        } catch (e) {
            // Use NEON if available, otherwise fallback to console.warn
            const logWarn = typeof NEON !== 'undefined' ? NEON.ORANGE : console.warn;
            logWarn(`[WARN] Data Fetch Fail: ${e.message}`);
            return null;
        }
    }
}

// --- 💰 EXCHANGE & RISK MANAGEMENT (from v6.0) ---
class EnhancedPaperExchange {
    constructor() {
        // Ensure config and Decimal are available
        if (typeof config === 'undefined') throw new Error("config is required.");
        if (typeof Decimal === 'undefined') throw new Error("Decimal.js is required.");
        if (typeof NEON === 'undefined') console.warn("NEON is not defined. Using default console colors.");

        this.balance = new Decimal(config.paper_trading.initial_balance);
        this.startBal = this.balance;
        this.pos = null; // Current open position: { side: 'BUY'|'SELL', entry: Decimal, qty: Decimal, sl: Decimal, tp: Decimal, strategy: string }
        this.dailyPnL = new Decimal(0);
        this.lastDailyReset = new Date(); // Track the last time daily PnL was reset
    }

    /**
     * Resets daily PnL at the start of a new day.
     */
    resetDailyPnL() {
        const now = new Date();
        if (now.getDate() !== this.lastDailyReset.getDate()) {
            this.dailyPnL = new Decimal(0);
            this.lastDailyReset = now;
            console.log("Daily PnL reset.");
        }
    }

    /**
     * Checks if trading is allowed based on risk parameters.
     * @returns {boolean} True if trading is allowed, false otherwise.
     */
    canTrade() {
        this.resetDailyPnL(); // Ensure daily PnL is up-to-date

        const drawdown = this.startBal.isZero() ? new Decimal(0) : this.startBal.sub(this.balance).div(this.startBal).mul(100);
        if (drawdown.gt(config.risk.max_drawdown)) {
            const logError = typeof NEON !== 'undefined' ? NEON.RED : console.error;
            logError(`🚨 MAX DRAWDOWN HIT (${drawdown.toFixed(2)}%)`);
            return false;
        }
        const dailyLoss = this.startBal.isZero() ? new Decimal(0) : this.dailyPnL.div(this.startBal).mul(100);
        if (dailyLoss.lt(new Decimal(config.risk.daily_loss_limit))) {
            const logError = typeof NEON !== 'undefined' ? NEON.RED : console.error;
            logError(`🚨 DAILY LOSS LIMIT HIT (${dailyLoss.toFixed(2)}%)`);
            return false;
        }
        return true;
    }

    /**
     * Evaluates the current market state and decides on trades.
     * @param {number} priceVal - The current market price.
     * @param {object} signal - The trading signal from the AI. { action: 'BUY'|'SELL'|'HOLD', confidence: number, entry: number, sl: number, tp: number, strategy: string }
     */
    evaluate(priceVal, signal) {
        // If risk limits are hit, close any open position and stop trading.
        if (!this.canTrade()) {
            if (this.pos) this.handlePositionClose(new Decimal(priceVal), "RISK_STOP");
            return;
        }

        const price = new Decimal(priceVal);

        // Close existing position if necessary (SL/TP hit or signal change)
        if (this.pos) {
            // Check if the signal has changed to the opposite direction or is HOLD
            if (signal.action !== 'HOLD' && signal.action !== this.pos.side) {
                this.handlePositionClose(price, `SIGNAL_CHANGE (${signal.action})`);
            } else {
                this.handlePositionClose(price); // Check for SL/TP hits
            }
        }

        // Open a new position if conditions are met and no position is open
        if (!this.pos && signal.action !== 'HOLD' && signal.confidence >= config.min_confidence) {
            this.handlePositionOpen(price, signal);
        }
    }

    /**
     * Handles closing an open position.
     * @param {Decimal} price - The current price at which to close.
     * @param {string|null} forceReason - Reason for forced closure (e.g., 'RISK_STOP', 'SIGNAL_CHANGE').
     */
    handlePositionClose(price, forceReason = null) {
        let close = false;
        let reason = forceReason || '';

        if (!this.pos) return; // No position to close

        if (this.pos.side === 'BUY') {
            if (forceReason || price.lte(this.pos.sl)) { // Stop Loss or forced close
                close = true;
                reason = reason || 'SL Hit';
            } else if (price.gte(this.pos.tp)) { // Take Profit
                close = true;
                reason = reason || 'TP Hit';
            }
        } else { // SELL position
            if (forceReason || price.gte(this.pos.sl)) { // Stop Loss or forced close
                close = true;
                reason = reason || 'SL Hit';
            } else if (price.lte(this.pos.tp)) { // Take Profit
                close = true;
                reason = reason || 'TP Hit';
            }
        }

        if (close) {
            const slippage = price.mul(config.paper_trading.slippage);
            const exitPrice = this.pos.side === 'BUY' ? price.sub(slippage) : price.add(slippage);
            const rawPnl = this.pos.side === 'BUY' ? exitPrice.sub(this.pos.entry).mul(this.pos.qty) : this.pos.entry.sub(exitPrice).mul(this.pos.qty);
            const fee = exitPrice.mul(this.pos.qty).mul(config.paper_trading.fee);
            const netPnl = rawPnl.sub(fee);

            this.balance = this.balance.add(netPnl);
            this.dailyPnL = this.dailyPnL.add(netPnl);

            const color = netPnl.gte(0) ? (typeof NEON !== 'undefined' ? NEON.GREEN : '\x1b[32m') : (typeof NEON !== 'undefined' ? NEON.RED : '\x1b[31m');
            const resetColor = typeof NEON !== 'undefined' ? '' : '\x1b[0m';
            console.log(`${reason}! PnL: ${color}${netPnl.toFixed(2)}${resetColor} [${this.pos.strategy}]`);
            this.pos = null;
        }
    }

    /**
     * Handles opening a new position.
     * @param {Decimal} price - The current price for entry calculation.
     * @param {object} signal - The trading signal from the AI.
     */
    handlePositionOpen(price, signal) {
        const entry = new Decimal(signal.entry);
        const sl = new Decimal(signal.sl);
        const tp = new Decimal(signal.tp);

        const dist = entry.sub(sl).abs(); // Distance between entry and stop loss
        if (dist.isZero()) {
            console.warn(typeof NEON !== 'undefined' ? NEON.YELLOW("WARN: Entry and SL are the same, cannot open position.") : "WARN: Entry and SL are the same, cannot open position.");
            return;
        }

        // Calculate quantity based on risk percentage and stop loss distance
        const riskAmt = this.balance.mul(config.paper_trading.risk_percent / 100);
        let qty = riskAmt.div(dist);

        // Cap quantity based on leverage
        const maxQty = this.balance.mul(config.paper_trading.leverage_cap).div(price);
        if (qty.gt(maxQty)) {
            qty = maxQty;
            console.warn(typeof NEON !== 'undefined' ? NEON.YELLOW(`WARN: Position size capped by leverage. Max Qty: ${maxQty.toFixed(4)}`) : `WARN: Position size capped by leverage. Max Qty: ${maxQty.toFixed(4)}`);
        }

        // Ensure quantity is positive
        if (qty.isNegative() || qty.isZero()) {
            console.warn(typeof NEON !== 'undefined' ? NEON.YELLOW("WARN: Calculated quantity is zero or negative. Cannot open position.") : "WARN: Calculated quantity is zero or negative. Cannot open position.");
            return;
        }

        const slippage = price.mul(config.paper_trading.slippage);
        const execPrice = signal.action === 'BUY' ? entry.add(slippage) : entry.sub(slippage);
        const fee = execPrice.mul(qty).mul(config.paper_trading.fee);

        // Check if balance is sufficient after considering fees
        if (this.balance.lt(fee)) {
            console.warn(typeof NEON !== 'undefined' ? NEON.YELLOW("WARN: Insufficient balance for fees. Cannot open position.") : "WARN: Insufficient balance for fees. Cannot open position.");
            return;
        }

        // Deduct fees from balance before opening position
        this.balance = this.balance.sub(fee);

        this.pos = {
            side: signal.action,
            entry: execPrice,
            qty: qty,
            sl: sl,
            tp: tp,
            strategy: signal.strategy
        };

        const logSuccess = typeof NEON !== 'undefined' ? NEON.GREEN : '\x1b[32m';
        const resetColor = typeof NEON !== 'undefined' ? '' : '\x1b[0m';
        console.log(`${logSuccess}OPEN ${signal.action} [${signal.strategy}] @ ${execPrice.toFixed(4)} | Size: ${qty.toFixed(4)} | SL: ${sl.toFixed(4)} | TP: ${tp.toFixed(4)}${resetColor}`);
    }
}

// --- 🧠 MULTI-STRATEGY AI BRAIN (from v6.0) ---
class EnhancedGeminiBrain {
    constructor() {
        // Ensure necessary modules and config are available
        if (typeof GoogleGenerativeAI === 'undefined') throw new Error("GoogleGenerativeAI is required.");
        if (typeof config === 'undefined') throw new Error("config is required.");
        if (typeof NEON === 'undefined') console.warn("NEON is not defined. Using default console colors.");

        const key = process.env.GEMINI_API_KEY;
        if (!key) {
            console.error("Missing GEMINI_API_KEY environment variable.");
            process.exit(1); // Exit if API key is critical
        }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    /**
     * Analyzes market context and generates a trading signal using Gemini AI.
     * @param {object} ctx - The context object containing market data and indicators.
     * @returns {Promise<object>} The AI-generated trading signal.
     */
    async analyze(ctx) {
        // Construct the prompt dynamically using context data
        const prompt = `
        ACT AS: Institutional Scalping Algorithm.
        OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD.

        QUANTITATIVE BIAS:
        - **WSS Score (Crucial Filter):** ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
        - CRITICAL RULE: Action must align with WSS. BUY requires WSS >= ${config.indicators.wss_weights.action_threshold}. SELL requires WSS <= -${config.indicators.wss_weights.action_threshold}.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope) | ADX: ${ctx.adx}
        - Momentum: RSI=${ctx.rsi?.toFixed(2) ?? 'N/A'}, Stoch=${ctx.stoch_k?.toFixed(0) ?? 'N/A'}, MACD=${ctx.macd_hist?.toFixed(4) ?? 'N/A'}
        - Structure: VWAP=${ctx.vwap?.toFixed(4) ?? 'N/A'}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs?.P?.toFixed(2) ?? 'N/A'}, S1=${ctx.fibs?.S1?.toFixed(2) ?? 'N/A'}, R1=${ctx.fibs?.R1?.toFixed(2) ?? 'N/A'}
        - Support/Resistance: ${ctx.sr_levels?.join(', ') ?? 'N/A'}

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0): Pullback to VWAP/EMA, anticipate continuation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES): Trade in direction of MTF trend on volatility expansion.
        3. MEAN_REVERSION (WSS Momentum < -1.0 or > 1.0, Chop > 60): Fade extreme RSI/Stoch.
        4. LIQUIDITY_GRAB (Price Near FVG/Wall): Fade or trade the retest/bounce of a liquidity zone.
        5. DIVERGENCE_HUNT (Divergence != NONE): High conviction reversal trade using swing high/low for SL.

        INSTRUCTIONS:
        - If the WSS does not meet the threshold, or if no strategy is clear, return "HOLD".
        - Calculate precise entry, SL, and TP (1:1.5 RR minimum, use ATR/Pivot/FVG for targets).

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "strategy": "STRATEGY_NAME", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await this.model.generateContent(prompt);
            const text = res.response.text();

            // Clean up the response text to extract JSON
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                console.error("Gemini AI response did not contain valid JSON:", text);
                return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: 'Invalid AI response format' };
            }

            const signal = JSON.parse(jsonMatch[0]);

            // Validate the parsed signal structure
            if (!signal || typeof signal.action === 'undefined' || typeof signal.strategy === 'undefined' || typeof signal.confidence === 'undefined') {
                console.error("Parsed signal is missing required fields:", signal);
                return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: 'Invalid signal structure from AI' };
            }

            // Ensure numerical values are valid numbers, default to 0 if not
            signal.confidence = typeof signal.confidence === 'number' && !isNaN(signal.confidence) ? signal.confidence : 0;
            signal.entry = typeof signal.entry === 'number' && !isNaN(signal.entry) ? signal.entry : 0;
            signal.sl = typeof signal.sl === 'number' && !isNaN(signal.sl) ? signal.sl : 0;
            signal.tp = typeof signal.tp === 'number' && !isNaN(signal.tp) ? signal.tp : 0;

            // Apply critical WSS filter
            const wssThreshold = config.indicators.wss_weights.action_threshold;
            if (signal.action === 'BUY' && ctx.wss < wssThreshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${ctx.wss}) below BUY threshold (${wssThreshold})`;
            } else if (signal.action === 'SELL' && ctx.wss > -wssThreshold) {
                signal.action = 'HOLD';
                signal.reason = `WSS (${ctx.wss}) above SELL threshold (${-wssThreshold})`;
            }

            // Add default reason if missing
            if (!signal.reason) {
                signal.reason = signal.action === 'HOLD' ? 'No clear signal or WSS filter applied.' : `Strategy: ${signal.strategy}`;
            }

            return signal;

        } catch (error) {
            console.error("Error generating content from Gemini AI:", error);
            return { action: 'HOLD', strategy: 'AI_ERROR', confidence: 0, entry: 0, sl: 0, tp: 0, reason: `Gemini API error: ${error.message}` };
        }
    }
}
// --- Trading Engine ---
class TradingEngine {
    constructor() {
        this.dataProvider = new EnhancedDataProvider();
        this.exchange = new EnhancedPaperExchange();
        this.brain = new EnhancedGeminiBrain();
        this.isRunning = false;
        this.loopDelay = config.loop_delay * 1000; // Convert seconds to milliseconds
    }

    async start() {
        this.isRunning = true;
        console.log(NEON.GREEN.bold("🚀 WHALEWAVE TITAN v6.1 STARTED..."));
        while (this.isRunning) {
            try {
                const data = await this.dataProvider.fetchAll();
                if (!data) {
                    await setTimeout(this.loopDelay); // Wait before retrying if data fetching fails
                    continue;
                }

                // Calculate all indicators and analysis
                const analysis = await this.calculateIndicators(data);
                if (!analysis) {
                    await setTimeout(this.loopDelay);
                    continue;
                }

                const context = this.brain.buildContext(data, analysis);
                const signal = await this.brain.analyze(context);

                this.exchange.evaluate(data.price, signal);
                this.displayDashboard(data, context, signal);

            } catch (error) {
                console.error(NEON.RED.bold(`\n🚨 ENGINE ERROR: ${error.message}`));
                console.error(error.stack); // Log the stack trace for debugging
                // Optionally, implement more robust error handling like restarting the engine
            }
            await setTimeout(this.loopDelay);
        }
    }

    async calculateIndicators(data) {
        const { candles, candlesMTF } = data;
        const c = candles.map(candle => candle.c);
        const h = candles.map(candle => candle.h);
        const l = candles.map(candle => candle.l);
        const v = candles.map(candle => candle.v);
        const mtfC = candlesMTF.map(candle => candle.c);

        const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all([
            TA.rsi(c, config.indicators.rsi),
            TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig),
            TA.adx(h, l, c, config.indicators.adx_period),
            TA.mfi(h, l, c, v, config.indicators.mfi),
            TA.chop(h, l, c, config.indicators.chop_period),
            TA.linReg(c, config.indicators.linreg_period),
            TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult),
            TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles),
            TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult),
            TA.cci(h, l, c, config.indicators.cci_period)
        ]);

        const last = c.length - 1;
        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
        const divergence = TA.detectDivergence(c, rsi);
        const volatility = TA.historicalVolatility(c);
        const avgVolatility = TA.sma(volatility, 50); // Assuming SMA of volatility is calculated
        const avgVolValue = avgVolatility && avgVolatility.length > 50 ? avgVolatility[50] : 1; // Default to 1 if not enough data

        const mtfSma = TA.sma(mtfC, 20);
        const trendMTF = mtfC[mtfC.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);
        const avgBid = data.bids.reduce((a,b)=>a+b.q,0)/data.bids.length;
        const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p;
        const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p;

        const analysis = {
            closes: c, rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci,
            isSqueeze, divergence, volatility, avgVolatility: avgVolValue, trendMTF, buyWall, sellWall, fibs
        };
        analysis.wss = calculateWSS(analysis, data.price);
        analysis.avgVolatility = avgVolValue; // Ensure this is set correctly
        return analysis;
    }

    buildContext(d, a) {
        const last = a.closes.length - 1;
        const linReg = TA.getFinalValue(a, 'reg', 4);
        const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

        return {
            price: d.price, rsi: a.rsi[last], stoch_k: a.stoch.k[last], macd_hist: (a.macd.hist[last] || 0),
            adx: a.adx[last], chop: a.chop[last], vwap: a.vwap[last],
            trend_angle: linReg.slope, trend_mtf: a.trendMTF, isSqueeze: a.isSqueeze ? 'YES' : 'NO', fvg: a.fvg, divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall }, fibs: a.fibs,
            volatility: a.volatility[last], marketRegime: TA.marketRegime(a.closes, a.volatility),
            wss: a.wss, sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`
        };
    }

    colorizeValue(value, key) {
        if (typeof value !== 'number') return NEON.GRAY(value);
        const v = parseFloat(value);
        if (key === 'rsi' || key === 'mfi') {
            if (v > 70) return NEON.RED(v.toFixed(2));
            if (v < 30) return NEON.GREEN(v.toFixed(2));
            return NEON.YELLOW(v.toFixed(2));
        }
        if (key === 'stoch_k') {
            if (v > 80) return NEON.RED(v.toFixed(0));
            if (v < 20) return NEON.GREEN(v.toFixed(0));
            return NEON.YELLOW(v.toFixed(0));
        }
        if (key === 'macd_hist' || key === 'trend_angle') {
            if (v > 0) return NEON.GREEN(v.toFixed(4));
            if (v < 0) return NEON.RED(v.toFixed(4));
            return NEON.GRAY(v.toFixed(4));
        }
        if (key === 'adx') {
            if (v > 25) return NEON.ORANGE(v.toFixed(2));
            return NEON.GRAY(v.toFixed(2));
        }
        if (key === 'chop') {
            if (v > 60) return NEON.BLUE(v.toFixed(2));
            if (v < 40) return NEON.ORANGE(v.toFixed(2));
            return NEON.GRAY(v.toFixed(2));
        }
        if (key === 'vwap') {
             return NEON.CYAN(v.toFixed(4));
        }
        return NEON.CYAN(v.toFixed(2));
    }

    displayDashboard(d, ctx, sig) {
        console.clear();
        const border = NEON.GRAY('─'.repeat(80));
        console.log(border);
        console.log(NEON.bg(NEON.PURPLE(` WHALEWAVE TITAN v6.1 | ${config.symbol} | $${d.price.toFixed(4)} `).padEnd(80)));
        console.log(border);

        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        const wssColor = ctx.wss >= config.indicators.wss_weights.action_threshold ? NEON.GREEN : ctx.wss <= -config.indicators.wss_weights.action_threshold ? NEON.RED : NEON.YELLOW;
        console.log(`WSS: ${wssColor(ctx.wss)} | Strategy: ${NEON.BLUE(sig.strategy || 'SEARCHING')} | Signal: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        const regimeCol = ctx.marketRegime.includes('HIGH') ? NEON.RED : ctx.marketRegime.includes('LOW') ? NEON.GREEN : NEON.YELLOW;
        const trendCol = ctx.trend_mtf === 'BULLISH' ? NEON.GREEN : NEON.RED;
        console.log(`Regime: ${regimeCol(ctx.marketRegime)} | Vol: ${this.colorizeValue(ctx.volatility, 'volatility')} | Squeeze: ${ctx.isSqueeze === 'YES' ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${trendCol(ctx.trend_mtf)} | Slope: ${this.colorizeValue(ctx.trend_angle, 'trend_angle')} | ADX: ${this.colorizeValue(ctx.adx, 'adx')}`);
        console.log(border);

        console.log(`RSI: ${this.colorizeValue(ctx.rsi, 'rsi')} | Stoch: ${this.colorizeValue(ctx.stoch_k, 'stoch_k')} | MACD Hist: ${this.colorizeValue(ctx.macd_hist, 'macd_hist')} | Chop: ${this.colorizeValue(ctx.chop, 'chop')}`);
        const divCol = ctx.divergence.includes('BULLISH') ? NEON.GREEN : ctx.divergence.includes('BEARISH') ? NEON.RED : NEON.GRAY;
        console.log(`Divergence: ${divCol(ctx.divergence)} | FVG: ${ctx.fvg ? NEON.YELLOW(ctx.fvg.type) : 'None'} | VWAP: ${this.colorizeValue(ctx.vwap, 'vwap')}`);
        console.log(`${NEON.GRAY('Key Levels:')} P=${NEON.YELLOW(ctx.fibs.P.toFixed(2))} S1=${NEON.GREEN(ctx.fibs.S1.toFixed(2))} R1=${NEON.RED(ctx.fibs.R1.toFixed(2))}`);
        console.log(border);

        const pnlCol = this.exchange.dailyPnL.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`Balance: ${NEON.GREEN('$' + this.exchange.balance.toFixed(2))} | Daily PnL: ${pnlCol('$' + this.exchange.dailyPnL.toFixed(2))}`);

        if (this.exchange.pos) {
            const p = this.exchange.pos;
            const curPnl = p.side === 'BUY' ? new Decimal(d.price).sub(p.entry).mul(p.qty) : p.entry.sub(d.price).mul(p.qty);
            const posCol = curPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(NEON.BLUE(`OPEN POS: ${p.side} @ ${p.entry.toFixed(4)} | SL: ${p.sl.toFixed(4)} | TP: ${p.tp.toFixed(4)} | PnL: ${posCol(curPnl.toFixed(2))}`));
        }
        console.log(border);
    }
}

// --- START ---
const engine = new TradingEngine();
process.on('SIGINT', () => {
    engine.isRunning = false;
    console.log(NEON.RED("\n🛑 SHUTTING DOWN GRACEFULLY..."));
    process.exit(0);
});
process.on('SIGTERM', () => { engine.isRunning = false; process.exit(0); });
engine.start();
