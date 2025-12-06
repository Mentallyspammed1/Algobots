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
