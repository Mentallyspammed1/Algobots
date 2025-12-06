/**
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │   WHALEWAVE PRO – LEVIATHAN v2.5 "MARKET MAKER" (NUCLEAR EDITION)       │
 * │   Directional Maker Logic · Penny Jumping · Local Orderbook · Neon HUD  │
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
  tickSize: process.env.TICK_SIZE || '0.10', // CRITICAL: Matches exchange tick size
};

// ─── DECIMAL-SAFE HELPERS ───
const DArr = (len) => Array(len).fill(null);
const D0 = () => new Decimal(0);
const D = (n) => new Decimal(n);

// ─── LOCAL ORDERBOOK MANAGER (SNAPSHOT + DELTA) ───
class LocalOrderBook {
  constructor() {
    this.bids = new Map();
    this.asks = new Map();
    this.ready = false;
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
    
    // Bids: High to Low | Asks: Low to High
    const bestBid = Math.max(...this.bids.keys());
    const bestAsk = Math.min(...this.asks.keys());
    
    return { bid: bestBid, ask: bestAsk };
  }

  getImbalance(depth = 10) {
    if (!this.ready) return 0;

    const bidLevels = Array.from(this.bids.entries())
      .map(([p, s]) => ({ p, s })).sort((a, b) => b.p - a.p).slice(0, depth);
    const askLevels = Array.from(this.asks.entries())
      .map(([p, s]) => ({ p, s })).sort((a, b) => a.p - b.p).slice(0, depth);

    const bidVol = bidLevels.reduce((sum, l) => sum + l.s, 0);
    const askVol = askLevels.reduce((sum, l) => sum + l.s, 0);
    const total = bidVol + askVol;

    return total === 0 ? 0 : (bidVol - askVol) / total;
  }
}

// ─── TA v2.5 – ETERNAL PERFECTION (HARDENED) ───
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

  // ─── HARDENED FISHER TRANSFORM ───
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

      // Smooth
      const prevVal = val[i - 1] && val[i - 1].isFinite() ? val[i - 1] : D0();
      raw = D(0.33).mul(raw).plus(D(0.67).mul(prevVal));

      // Clamp
      if (raw.gt(MAX_RAW)) raw = MAX_RAW;
      else if (raw.lt(MIN_RAW)) raw = MIN_RAW;
      val[i] = raw;

      // Log Safety
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

  static findFVG(candles) {
    if (candles.length < 3) return null;
    const c1 = candles[candles.length - 3];
    const c3 = candles[candles.length - 1];
    if (c1.high.lt(c3.low)) return { type: 'BULLISH', top: c3.low, bottom: c1.high, size: c3.low.minus(c1.high) };
    if (c1.low.gt(c3.high)) return { type: 'BEARISH', top: c1.low, bottom: c3.high, size: c1.low.minus(c3.high) };
    return null;
  }
}

// ─── ORACLE BRAIN v2.5 ───
class OracleBrain {
  constructor() {
    this.gemini = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
      model: 'gemini-1.5-flash',
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

    return {
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
    };
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

  async divine(obImbalance = 0) {
    const ctx = this.buildContext(obImbalance);
    if (!ctx) return { action: 'HOLD', confidence: 0, reason: 'Warming up', strategy: 'INIT' };

    const prompt = `You are LEVIATHAN v2.5 MARKET MAKER.
ATR=${ctx.atr} | Price=${ctx.price} | Imbalance=${ctx.imbalance}
Fisher=${ctx.fisher} | Laguerre=${ctx.laguerre} | OBV=${ctx.obvTrend}

RULES:
1. Signal ONLY if ≥4 confluences match.
2. Confidence MUST be >0.89.
3. SL/TP MUST be within ±4 ATR.
4. R/R ≥ 1.6 REQUIRED.
5. Strategy: "Directional Maker" - we will Limit Order into the trend.

DATA:
${JSON.stringify(ctx)}

Output JSON: {"action":"BUY"|"SELL"|"HOLD","confidence":0.90,"sl":123,"tp":456,"reason":"text","strategy":"name"}`;

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
          const newTp = signal.action === 'BUY'
            ? price.plus(risk.mul(1.6))
            : price.minus(risk.mul(1.6));
          signal.tp = Number(newTp.toFixed(2));
          signal.reason += ' | R/R Enforced';
        }
      }
      return this.validateSignal(signal, ctx);
    } catch (e) {
      return { action: 'HOLD', confidence: 0, reason: 'Oracle Silent', strategy: 'ERROR' };
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
      imbalance: 0,
      bestBid: 0,
      bestAsk: 0,
      pnl: 0,
      ticker: { high24: 0, low24: 0, vol24: 0, change24: 0 },
    };
  }

  // Smart Tick Precision
  formatPrice(price) {
    const tick = CONFIG.tickSize;
    let decimals = 2;
    if (tick.includes('.')) decimals = tick.split('.')[1].length;
    return new Decimal(price).toNearest(tick, Decimal.ROUND_DOWN).toFixed(decimals);
  }

  async warmUp() {
    console.log(`${C.cyan}[INIT] Fetching history for ${CONFIG.symbol}...${C.reset}`);
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
      this.state.price = parseFloat(candles[candles.length - 1].close);
      console.log(`${C.green}[INIT] Loaded ${candles.length} candles. Oracle Ready.${C.reset}`);
    } catch (e) {
      console.error(`${C.red}[FATAL] Warmup failed: ${e.message}${C.reset}`);
      process.exit(1);
    }
  }

  async monitorPnL() {
    setInterval(async () => {
      try {
        const res = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
        if (res.retCode === 0 && res.result.list && res.result.list.length > 0) {
          const pos = res.result.list[0];
          this.state.pnl = parseFloat(pos.unrealisedPnl || 0);
        }
      } catch (e) {}
    }, 5000);
  }

  updateOrderbook(data) {
    // 1. Feed the Local Book
    this.book.update(data);
    if (!this.book.ready) return;

    // 2. Derive State
    const { bid, ask } = this.book.getBestBidAsk();
    this.state.bestBid = bid;
    this.state.bestAsk = ask;
    this.state.imbalance = this.book.getImbalance(20); // Deep depth
  }

  async placeMakerOrder(signal) {
    console.log(`\n\n${C.bgGreen} ⚡ LEVIATHAN MAKER SIGNAL ${C.reset}`);
    console.log(`${C.bright}TYPE: ${signal.action} | CONF: ${(signal.confidence*100).toFixed(0)}%${C.reset}`);
    console.log(`${C.dim}Reason: ${signal.reason}${C.reset}`);

    if (!this.state.bestBid || !this.state.bestAsk) {
      console.log(`${C.red}[SKIP] Orderbook Not Ready${C.reset}`);
      return;
    }

    try {
      const posRes = await this.client.getPositionInfo({ category: 'linear', symbol: CONFIG.symbol });
      const pos = posRes.result?.list?.[0];
      
      if (pos && parseFloat(pos.size) > 0) {
        console.log(`${C.yellow}[EXEC] Position Active. Skipping new entry.${C.reset}`);
        return;
      }

      // ─── PENNY JUMPING STRATEGY ───
      let entryPrice;
      const tick = parseFloat(CONFIG.tickSize);
      
      if (signal.action === 'BUY') {
        // Buy: If Imbalance > 0 (Buy Pressure), jump in front of best bid. 
        // Safety: Cap at BestAsk - Tick to avoid taker fees.
        const aggressivePrice = this.state.bestBid + tick;
        const safeLimit = this.state.bestAsk - tick;
        entryPrice = (this.state.imbalance > 0.15) 
          ? Math.min(aggressivePrice, safeLimit)
          : this.state.bestBid;
      } else {
        // Sell: If Imbalance < 0 (Sell Pressure), under-cut best ask.
        // Safety: Floor at BestBid + Tick.
        const aggressivePrice = this.state.bestAsk - tick;
        const safeLimit = this.state.bestBid + tick;
        entryPrice = (this.state.imbalance < -0.15)
          ? Math.max(aggressivePrice, safeLimit)
          : this.state.bestAsk;
      }

      const formattedPrice = this.formatPrice(entryPrice);

      console.log(`${C.cyan}[MAKER] PostOnly ${signal.action} @ ${formattedPrice}${C.reset}`);
      console.log(`Book: ${this.state.bestBid} / ${this.state.bestAsk} | Imb: ${this.state.imbalance.toFixed(2)}`);

      await this.client.setLeverage({ category: 'linear', symbol: CONFIG.symbol, buyLeverage: CONFIG.leverage, sellLeverage: CONFIG.leverage }).catch(()=>{});

      const orderRes = await this.client.submitOrder({
        category: 'linear',
        symbol: CONFIG.symbol,
        side: signal.action === 'BUY' ? 'Buy' : 'Sell',
        orderType: 'Limit',
        price: formattedPrice,
        qty: CONFIG.qty,
        stopLoss: String(signal.sl),
        takeProfit: String(signal.tp),
        timeInForce: 'PostOnly', // THE MAKER SECRET
      });

      if (orderRes.retCode === 0) {
        console.log(`${C.neonGreen}[SUCCESS] Order Placed: ${orderRes.result.orderId}${C.reset}\n`);
      } else {
        console.error(`${C.neonRed}[FAIL] ${orderRes.retMsg}${C.reset}\n`);
      }

    } catch (e) {
      console.error(`${C.red}[EXEC ERROR] ${e.message}${C.reset}`);
    }
  }

  async start() {
    await this.warmUp();
    this.monitorPnL();

    // Subscribe: Candles, Orderbook (Depth 50), Tickers
    this.ws.subscribeV5([
      `kline.${CONFIG.interval}.${CONFIG.symbol}`, 
      `orderbook.50.${CONFIG.symbol}`,
      `tickers.${CONFIG.symbol}`
    ], 'linear');

    this.ws.on('update', async (data) => {
      // 1. Ticker Data
      if (data.topic && data.topic.startsWith('tickers')) {
        const t = data.data;
        this.state.ticker.high24 = t.high24h;
        this.state.ticker.low24 = t.low24h;
        this.state.ticker.vol24 = t.volume24h;
        this.state.ticker.change24 = t.price24hPcnt;
      }

      // 2. Orderbook Data (Snapshot/Delta)
      if (data.topic && data.topic.startsWith('orderbook')) {
        // Bybit V5: data.type is 'snapshot' or 'delta'
        this.updateOrderbook({
            type: data.type,
            b: data.data.b,
            a: data.data.a
        });
        return;
      }

      // 3. Kline Data (Trigger)
      if (data.topic && data.topic.startsWith('kline')) {
        const k = data.data[0];
        this.state.price = parseFloat(k.close);

        // ─── NEON HUD ───
        const pnlColor = this.state.pnl >= 0 ? C.neonGreen : C.neonRed;
        const imbColor = this.state.imbalance > 0 ? C.neonGreen : C.neonRed;
        const now = new Date().toLocaleTimeString();
        
        const hud = `\r${C.dim}[${now}]${C.reset} ${C.bright}${CONFIG.symbol}${C.reset} ` +
          `${C.neonCyan}${this.state.price.toFixed(2)}${C.reset} ` +
          `| PnL: ${pnlColor}$${this.state.pnl.toFixed(2)}${C.reset} ` +
          `| Imb: ${imbColor}${this.state.imbalance.toFixed(2)}${C.reset} ` +
          `| B/A: ${this.state.bestBid}/${this.state.bestAsk} ` +
          `| 24h: ${C.neonPurple}${this.state.ticker.change24 || '0'}%${C.reset}    `;

        process.stdout.write(hud);

        if (k.confirm) {
          process.stdout.write(`\n`); 
          console.log(`${C.yellow}[TICK] Candle Closed. Divining Direction...${C.reset}`);
          
          this.oracle.updateKline({
            open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume)
          });

          const signal = await this.oracle.divine(this.state.imbalance);
          
          if (signal.action !== 'HOLD') {
            await this.placeMakerOrder(signal);
          } else {
            console.log(`${C.dim}[WAIT] Oracle Holding (Conf: ${(signal.confidence*100).toFixed(0)}%) | ${signal.reason}${C.reset}`);
          }
        }
      }
    });

    this.ws.on('error', (err) => console.error(`\n${C.red}[WS ERROR] ${err}${C.reset}`));
    console.log(`\n${C.bgGreen} ▓▓▓ LEVIATHAN v2.5 (NUCLEAR) ACTIVE ▓▓▓ ${C.reset}\n`);
  }
}

// ─── IGNITION ───
const engine = new LeviathanEngine();
engine.start().catch(console.error);
