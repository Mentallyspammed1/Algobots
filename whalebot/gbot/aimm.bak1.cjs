/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v2.6 "DEEP DIVE" (QUANTUM EDITION)          │
 * │   Deep Book Analytics · Order Flow Walls · Gemini 2.0 Flash Lite        │
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
  qty: process.env.TRADE_QTY || '0.001',
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
      wmp: 0,        // Weighted Mid Price
      spread: 0,     // Bid-Ask Spread
      bidWall: 0,    // Largest Bid Size
      askWall: 0,    // Largest Ask Size
      skew: 0        // Orderbook Skew (-1 to 1)
    };
  }

  update(data) {
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

  // ─── QUANTITATIVE ANALYSIS ───
  calculateMetrics() {
    if (!this.ready || this.bids.size === 0 || this.asks.size === 0) return;

    // Convert Maps to sorted Arrays (Top 20 depth)
    const bids = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, 20);
    const asks = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, 20);

    const bestBid = bids[0][0];
    const bestAsk = asks[0][0];

    // 1. Weighted Mid Price (WMP)
    // Considers volume pressure near the spread
    const imbWeight = bids[0][1] / (bids[0][1] + asks[0][1]);
    this.metrics.wmp = (bestBid * (1 - imbWeight)) + (bestAsk * imbWeight);

    // 2. Spread
    this.metrics.spread = bestAsk - bestBid;

    // 3. Wall Detection (Largest order in top 20)
    this.metrics.bidWall = Math.max(...bids.map(b => b[1]));
    this.metrics.askWall = Math.max(...asks.map(a => a[1]));

    // 4. Volume Skew (Total Vol Top 20)
    const totalBidVol = bids.reduce((acc, val) => acc + val[1], 0);
    const totalAskVol = asks.reduce((acc, val) => acc + val[1], 0);
    const total = totalBidVol + totalAskVol;
    this.metrics.skew = total === 0 ? 0 : (totalBidVol - totalAskVol) / total;
  }

  getAnalysis() {
    return this.metrics;
  }
}

// ─── TA v2.5 (Standard) ───
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

  static fisher(high, low, len = 9) {
    const res = DArr(high.length).fill(D0());
    const val = DArr(high.length).fill(D0());
    if (high.length < len) return res;

    const EPSILON = D('1e-9');
    const MAX_RAW = D('0.999');
    const MIN_RAW = D('-0.999');

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
      if (raw.gt(MAX_RAW)) raw = MAX_RAW;
      else if (raw.lt(MIN_RAW)) raw = MIN_RAW;
      val[i] = raw;
      try {
        const v1 = D(1).plus(raw);
        const v2 = D(1).minus(raw);
        if (v2.abs().lt(EPSILON) || v1.lte(0) || v2.lte(0)) {
           res[i] = res[i - 1] || D0();
        } else {
           const logVal = v1.div(v2).ln();
           const prevRes = res[i - 1] && res[i - 1].isFinite() ? res[i - 1] : D0();
           res[i] = D(0.5).mul(logVal).plus(D(0.5).mul(prevRes));
        }
      } catch (e) {
        res[i] = res[i - 1] || D0();
      }
    }
    return res;
  }
}

// ─── ORACLE BRAIN (GEMINI 2.0 FLASH LITE) ───
class OracleBrain {
  constructor() {
    // Uses the latest fast model from Google
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

  buildContext(bookMetrics) {
    if (this.klines.length < 100) return null;

    const c = this.klines.map(k => k.close);
    const h = this.klines.map(k => k.high);
    const l = this.klines.map(k => k.low);

    const atrSeries = TA.atr(h, l, c, 14);
    const atr = atrSeries[atrSeries.length - 1] || D(1);
    const price = c[c.length - 1];
    const fisherSeries = TA.fisher(h, l);
    const fisherVal = fisherSeries[fisherSeries.length - 1] || D0();

    // Determine Wall Status
    let wallStatus = 'Balanced';
    if (bookMetrics.bidWall > bookMetrics.askWall * 1.5) wallStatus = 'Bid Wall (Support)';
    if (bookMetrics.askWall > bookMetrics.bidWall * 1.5) wallStatus = 'Ask Wall (Resistance)';

    return {
      price: price.toNumber(),
      atr: Number(atr.toFixed(2)),
      fisher: Number(fisherVal.clamp('-5', '5').toFixed(3)),
      book: {
        skew: Number(bookMetrics.skew.toFixed(3)),
        wmp: Number(bookMetrics.wmp.toFixed(2)),
        spread: Number(bookMetrics.spread.toFixed(4)),
        wall: wallStatus,
        bidPower: bookMetrics.bidWall,
        askPower: bookMetrics.askWall
      }
    };
  }

  validateSignal(sig, ctx) {
    if (!sig || typeof sig !== 'object') return { action: 'HOLD', confidence: 0, reason: 'Invalid JSON' };
    const price = D(ctx.price);
    const atr = D(ctx.atr || 100);

    if (!['BUY', 'SELL', 'HOLD'].includes(sig.action)) sig.action = 'HOLD';
    if (typeof sig.confidence !== 'number' || sig.confidence < 0.89) {
      sig.confidence = 0;
      sig.action = 'HOLD';
    }

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

    const prompt = `You are LEVIATHAN QUANTUM.
Price: ${ctx.price} | ATR: ${ctx.atr} | Fisher: ${ctx.fisher}
Orderbook Skew: ${ctx.book.skew} (-1 Bearish to 1 Bullish)
Market Structure: ${ctx.book.wall}
Weighted Mid Price: ${ctx.book.wmp}

RULES:
1. Signal BUY if Fisher < -1.5 AND Skew > 0.1 (Absorption).
2. Signal SELL if Fisher > 1.5 AND Skew < -0.1 (Distribution).
3. If "Bid Wall" exists, price may bounce up. If "Ask Wall" exists, price may reject down.
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

      // R/R Check
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

    this.state = {
      price: 0,
      bestBid: 0,
      bestAsk: 0,
      pnl: 0,
      ticker: { high24: 0, low24: 0, vol24: 0, change24: 0 },
    };
  }

  formatPrice(price) {
    const tick = CONFIG.tickSize;
    let decimals = 2;
    if (tick.includes('.')) decimals = tick.split('.')[1].length;
    return new Decimal(price).toNearest(tick, Decimal.ROUND_DOWN).toFixed(decimals);
  }

  async warmUp() {
    console.log(`${C.cyan}[INIT] Fetching history for ${CONFIG.symbol}...${C.reset}`);
    try {
      // 1. Klines
      const res = await this.client.getKline({
        category: 'linear',
        symbol: CONFIG.symbol,
        interval: CONFIG.interval,
        limit: 200,
      });
      if (res.retCode !== 0) throw new Error(res.retMsg);
      const candles = res.result.list.reverse().map(k => ({
        startTime: parseInt(k[0]),
        open: D(k[1]), high: D(k[2]), low: D(k[3]), close: D(k[4]), volume: D(k[5]),
      }));
      candles.forEach(c => this.oracle.updateKline(c));
      this.state.price = parseFloat(candles[candles.length - 1].close);
      
      // 2. Tickers
      const tickerRes = await this.client.getTickers({ category: 'linear', symbol: CONFIG.symbol });
      if(tickerRes.retCode === 0 && tickerRes.result.list.length > 0) {
        const t = tickerRes.result.list[0];
        this.state.ticker.change24 = (parseFloat(t.price24hPcnt) * 100).toFixed(2);
      }

      // 3. Snapshot
      const obRes = await this.client.getOrderbook({ category: 'linear', symbol: CONFIG.symbol, limit: 50 });
      if(obRes.retCode === 0) {
        this.updateOrderbook({ type: 'snapshot', b: obRes.result.b, a: obRes.result.a });
      }

      console.log(`${C.green}[INIT] System Ready.${C.reset}`);
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
    console.log(`\n\n${C.bgGreen} ⚡ LEVIATHAN SIGNAL ${C.reset}`);
    console.log(`${C.bright}TYPE: ${signal.action} | CONF: ${(signal.confidence*100).toFixed(0)}%${C.reset}`);
    console.log(`${C.dim}Reason: ${signal.reason}${C.reset}`);

    if (!this.state.bestBid || !this.state.bestAsk) {
      console.log(`${C.red}[SKIP] Orderbook Not Ready${C.reset}`);
      return;
    }

    try {
      const posRes = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
      if (posRes.result?.list?.[0] && parseFloat(posRes.result.list[0].size) > 0) {
        console.log(`${C.yellow}[EXEC] Position Active. Skipping.${C.reset}`);
        return;
      }

      // ─── SMART ENTRY ───
      // If skew is positive (bullish), bid aggressively at (Bid + Tick).
      // If we see a Bid Wall, bid right above it to front-run the wall.
      const metrics = this.book.getAnalysis();
      const tick = parseFloat(CONFIG.tickSize);
      let entryPrice;

      if (signal.action === 'BUY') {
        const aggressive = this.state.bestBid + tick;
        const passive = this.state.bestBid;
        entryPrice = (metrics.skew > 0.2) ? Math.min(aggressive, this.state.bestAsk - tick) : passive;
      } else {
        const aggressive = this.state.bestAsk - tick;
        const passive = this.state.bestAsk;
        entryPrice = (metrics.skew < -0.2) ? Math.max(aggressive, this.state.bestBid + tick) : passive;
      }

      const formattedPrice = this.formatPrice(entryPrice);
      console.log(`${C.cyan}[MAKER] PostOnly ${signal.action} @ ${formattedPrice} (Skew: ${metrics.skew.toFixed(2)})${C.reset}`);

      await this.client.submitOrder({
        category: 'linear',
        symbol: CONFIG.symbol,
        side: signal.action === 'BUY' ? 'Buy' : 'Sell',
        orderType: 'Limit',
        price: formattedPrice,
        qty: CONFIG.qty,
        stopLoss: String(signal.sl),
        takeProfit: String(signal.tp),
        timeInForce: 'PostOnly',
      });
      console.log(`${C.neonGreen}[SUCCESS] Order Submitted${C.reset}\n`);

    } catch (e) {
      console.error(`${C.red}[EXEC ERROR] ${e.message}${C.reset}`);
    }
  }

  async start() {
    await this.warmUp();

    // PnL Monitor
    setInterval(async () => {
      try {
        const res = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
        if (res.result.list?.[0]) this.state.pnl = parseFloat(res.result.list[0].unrealisedPnl || 0);
      } catch (e) {}
    }, 5000);

    this.ws.subscribeV5([`kline.${CONFIG.interval}.${CONFIG.symbol}`, `orderbook.50.${CONFIG.symbol}`, `tickers.${CONFIG.symbol}`], 'linear');

    this.ws.on('update', async (data) => {
      if (data.topic?.startsWith('tickers')) {
        const t = data.data;
        if (t.price24hPcnt) this.state.ticker.change24 = (parseFloat(t.price24hPcnt) * 100).toFixed(2);
      }

      if (data.topic?.startsWith('orderbook')) {
        this.updateOrderbook({ type: data.type, b: data.data.b, a: data.data.a });
        return;
      }

      if (data.topic?.startsWith('kline')) {
        const k = data.data[0];
        this.state.price = parseFloat(k.close);
        
        // NEON HUD
        const m = this.book.getAnalysis();
        const skewColor = m.skew > 0 ? C.neonGreen : C.neonRed;
        const hud = `\r${C.dim}[${new Date().toLocaleTimeString()}]${C.reset} ${C.bright}${CONFIG.symbol}${C.reset} ` +
          `${C.neonCyan}${this.state.price.toFixed(2)}${C.reset} | PnL: ${this.state.pnl.toFixed(2)} ` +
          `| Skew: ${skewColor}${m.skew.toFixed(2)}${C.reset} | Wall: ${m.bidWall > m.askWall ? C.green+'BID'+C.reset : C.red+'ASK'+C.reset}    `;
        process.stdout.write(hud);

        if (k.confirm) {
          process.stdout.write(`\n`);
          this.oracle.updateKline({ open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume) });
          const signal = await this.oracle.divine(m);
          if (signal.action !== 'HOLD') await this.placeMakerOrder(signal);
        }
      }
    });

    this.ws.on('error', (err) => console.error(`\n${C.red}[WS ERROR] ${err}${C.reset}`));
    console.log(`\n${C.bgGreen} ▓▓▓ LEVIATHAN v2.6 DEEP DIVE ACTIVE ▓▓▓ ${C.reset}\n`);
  }
}

const engine = new LeviathanEngine();
engine.start().catch(console.error);
