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
