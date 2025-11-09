const { exec } = require('child_process');
const fs = require('fs/promises');
const path = require('path');
const readline = require('readline');

const chalk = require('chalk'); // Ensure chalk is installed: npm install chalk

const C = {
  buy: chalk.bold.hex('#39FF14'), sell: chalk.bold.hex('#FF3333'), hold: chalk.bold.hex('#CCCCCC'),
  price: chalk.white, entry: chalk.hex('#00FFFF'), tp: chalk.hex('#CCFF00'), sl: chalk.bold.hex('#FF00FF'),
  info: chalk.hex('#00FFFF'), alert: chalk.bold.hex('#FF00FF'), title: chalk.bold.hex('#FF00FF'),
  reason: chalk.gray, conf: chalk.white, label: chalk.bold.hex('#CCCCCC'),
  // Ensure cyan is defined as a fallback function that returns the text as-is
  cyan: (text) => text
};

// If chalk is successfully loaded, override the fallback cyan with chalk's cyan
if (chalk) {
    C.cyan = chalk.cyan;
}


const CONFIG = {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY || null,
  ALERT_PHONE_NUMBER: process.env.ALERT_PHONE_NUMBER || null,
  MIN_CONFIDENCE_TO_ALERT: 85,
  GEMINI_MODEL: "gemini-2.5-flash-lite",
  WS_URL: "wss://stream.bybit.com/v5/public/linear",
  API_URL: "https://api.bybit.com",
  PING_INTERVAL: 20000,
  MAX_BUFFER: 200,
  HISTORICAL_DATA_DIR: path.join(__dirname, 'backtest_data'),
  ORDERBOOK_DEPTH: 50,
  INDICATOR_CACHE_TTL: 5000,
  SR_LOOKBACK: 10,
  VP_LOOKBACK: 50,
  CVD_LOOKBACK: 20,
  SMA_PERIOD: 20,
  RSI_PERIOD: 14,
  ATR_PERIOD: 14,
  FEE_RATE: 0.00055,
  SLIPPAGE_PERCENT: 0.0005,
  BACKTEST_INITIAL_EQUITY: 10000,
  BACKTEST_DAYS: 30,
  BACKTEST_MAX_RECONNECTS: 10,
  BACKTEST_RECONNECT_DELAY_MULTIPLIER: 2000,
};

const state = {
  klineBuffer: new Map(), orderbook: new Map(), ticker: new Map(), tradeBuffer: new Map(),
  lastCandle: new Map(), pending: new Set(), lastSmsAlert: new Map(),
  symbolInfoCache: new Map(), indicatorCache: new Map(),
};

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const promptUser = (query) => new Promise(resolve => rl.question(C.cyan(query), resolve));

async function getSymbolInfo(symbol) {
  if (state.symbolInfoCache.has(symbol)) return state.symbolInfoCache.get(symbol);
  try {
    const url = `${CONFIG.API_URL}/v5/market/instruments-info?category=linear&symbol=${symbol}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { result } = await res.json();
    const info = result.list[0];
    if (!info) throw new Error("Symbol not found");

    const tickSize = info.priceFilter.tickSize;
    const decimals = tickSize.includes('.') ? tickSize.split('.')[1].length : 0;
    const symbolInfo = { tickSize, decimals };
    state.symbolInfoCache.set(symbol, symbolInfo);
    return symbolInfo;
  } catch (e) {
    console.error(C.red(`\nSymbol info fetch failed for ${symbol}: ${e.message}`));
    process.exit(1);
  }
}

function formatPrice(price, symbolInfo) {
  return (typeof price === 'number' && symbolInfo) ? price.toFixed(symbolInfo.decimals) : "N/A";
}

function getIntervalMs(tf) {
  const m = { '1m': 60, '3m': 180, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };
  return (m[tf] || 60) * 1000;
}

function sma(d, p) {
  if (!d || d.length < p) return null;
  const data = d.map(c => parseFloat(c.c));
  return data.slice(-p).reduce((s, c) => s + c, 0) / p;
}

function getEmaSeries(d, p) {
  if (!d || d.length < p) return [];
  const data = d.map(c => parseFloat(c.c));
  const a = 2 / (p + 1);
  let cur = data.slice(0, p).reduce((s, r) => s + r, 0) / p;
  const ema = new Array(p).fill(cur);
  for (let i = p; i < data.length; i++) {
    cur = (data[i] - cur) * a + cur;
    ema.push(cur);
  }
  return ema;
}

function macd(d) {
  if (!d || d.length < 26) return { macd: null, histogram: null, signal: null };
  const e12 = getEmaSeries(d.slice(-50), 12); // Limit lookback for performance
  const e26 = getEmaSeries(d.slice(-50), 26);
  if (e12.length < 9 || e26.length < 9) return { macd: null, histogram: null, signal: null };

  const macdLine = [];
  for (let i = 0; i < Math.min(e12.length, e26.length); i++) {
    macdLine.push(e12[i] - e26[i]);
  }
  if (macdLine.length < 9) return { macd: null, histogram: null, signal: null };

  const signalLine = getEmaSeries(macdLine.map(m => ({ c: m })), 9);
  const lastMacd = macdLine[macdLine.length - 1];
  const lastSignal = signalLine[signalLine.length - 1];

  return {
    macd: lastMacd,
    histogram: lastMacd !== null && lastSignal !== null ? lastMacd - lastSignal : null,
    signal: lastSignal,
  };
}

function rsi(d, p) {
  if (!d || d.length < p + 1) return null;
  const data = d.map(c => parseFloat(c.c));
  let avgGain = 0, avgLoss = 0;
  for (let i = data.length - p; i < data.length; i++) {
    const diff = data[i] - data[i - 1];
    if (diff > 0) avgGain += diff;
    else avgLoss += Math.abs(diff);
  }
  avgGain /= p;
  avgLoss /= p;

  if (avgLoss === 0) return 100;
  return 100 - (100 / (1 + (avgGain / avgLoss)));
}

function atr(d, p) {
  if (!d || d.length < p + 1) return null;
  let sumTR = 0;
  for (let i = d.length - p; i < d.length; i++) {
    const h = parseFloat(d[i].h), l = parseFloat(d[i].l), c = parseFloat(d[i].c);
    const pc = parseFloat(d[i - 1].c);
    const tr = Math.max(h - l, Math.abs(h - pc), Math.abs(l - pc));
    sumTR += tr;
  }
  return sumTR / p;
}

function calculateIndicators(df) {
  if (!df || df.length < Math.max(CONFIG.SMA_PERIOD, CONFIG.RSI_PERIOD, CONFIG.ATR_PERIOD, 50)) return {};
  const lastCandle = df[df.length - 1];
  const indicators = {
    sma: sma(df, CONFIG.SMA_PERIOD),
    rsi: rsi(df, CONFIG.RSI_PERIOD),
    atr: atr(df, CONFIG.ATR_PERIOD),
    close: parseFloat(lastCandle.c),
    high: parseFloat(lastCandle.h),
    low: parseFloat(lastCandle.l),
    volume: parseFloat(lastCandle.v),
    timestamp: lastCandle.t,
  };
  const macdResult = macd(df);
  indicators.macd = macdResult.macd;
  indicators.macdHist = macdResult.histogram;
  indicators.macdSignal = macdResult.signal;

  const atrSeries = [];
  for (let i = CONFIG.ATR_PERIOD; i <= df.length; i++) {
    const slice = df.slice(df.length - i);
    const a = atr(slice, CONFIG.ATR_PERIOD);
    if (a !== null) atrSeries.push(a);
  }
  indicators.avgAtr = atrSeries.length > 0 ? atrSeries.reduce((s, a) => s + a, 0) / atrSeries.length : null;

  return indicators;
}

function calculateSRLevels(candles, lookback = CONFIG.SR_LOOKBACK) {
  if (!candles || candles.length < lookback * 2 + 1) return { supports: [], resistances: [] };
  const supports = new Set(), resistances = new Set();
  for (let i = lookback; i < candles.length - lookback; i++) {
    const h = parseFloat(candles[i].h), l = parseFloat(candles[i].l);
    let isPH = true, isPL = true;
    for (let j = i - lookback; j <= i + lookback; j++) {
      if (i === j) continue;
      if (parseFloat(candles[j].h) > h) isPH = false;
      if (parseFloat(candles[j].l) < l) isPL = false;
    }
    if (isPH) resistances.add(h);
    if (isPL) supports.add(l);
  }
  const price = parseFloat(candles[candles.length - 1].c);
  return {
    supports: [...supports].sort((a, b) => b - a).filter(p => p < price).slice(0, 3),
    resistances: [...resistances].sort((a, b) => a - b).filter(p => p > price).slice(0, 3)
  };
}

function calculateVolumeProfile(candles, lookback = CONFIG.VP_LOOKBACK) {
  if (!candles || candles.length < 2) return null;
  const recent = candles.slice(-lookback);
  const map = new Map();
  recent.forEach(c => {
    const h = parseFloat(c.h), l = parseFloat(c.l), v = parseFloat(c.v);
    const range = h - l;
    if (range < 0.00001) return; // Avoid division by zero or near-zero
    const numPoints = Math.max(10, Math.floor(range / 0.0001)); // Define resolution, e.g., every $0.0001
    const step = range / numPoints;
    const volumePerStep = v / numPoints;

    for (let i = 0; i < numPoints; i++) {
      const p = l + i * step;
      const roundedP = parseFloat(p.toFixed(8)); // Use high precision for key
      map.set(roundedP, (map.get(roundedP) || 0) + volumePerStep);
    }
  });

  const sorted = Array.from(map).sort((a, b) => a[0] - b[0]);
  if (!sorted.length) return null;

  const totalVolume = sorted.reduce((s, [_, v]) => s + v, 0);
  let poc = sorted[0][0], maxVol = sorted[0][1];
  sorted.forEach(([price, vol]) => {
    if (vol > maxVol) {
      maxVol = vol;
      poc = price;
    }
  });

  let volumeArea = 0;
  let vah = poc, val = poc;
  const targetVolume = totalVolume * 0.7;
  let cumulativeVolume = 0;

  const pocIndex = sorted.findIndex(p => p[0] === poc);
  let leftIndex = pocIndex, rightIndex = pocIndex;

  while (cumulativeVolume < targetVolume && (leftIndex > 0 || rightIndex < sorted.length - 1)) {
    const leftVol = leftIndex > 0 ? sorted[leftIndex - 1][1] : 0;
    const rightVol = rightIndex < sorted.length - 1 ? sorted[rightIndex + 1][1] : 0;

    if (leftVol >= rightVol && leftIndex > 0) {
      cumulativeVolume += leftVol;
      val = sorted[--leftIndex][0];
    } else if (rightIndex < sorted.length - 1) {
      cumulativeVolume += rightVol;
      vah = sorted[++rightIndex][0];
    } else {
      break;
    }
  }
  return { poc, vah, val, totalVol: totalVolume };
}


function calculateOrderFlow(candles, tradeBuffer) {
  if (!tradeBuffer || tradeBuffer.length < 10 || !candles || candles.length < 2) return null;
  const lastCandle = candles[candles.length - 1];
  const intervalMs = getIntervalMs('1m');
  const candleStart = lastCandle.t;
  const candleEnd = candleStart + intervalMs;

  let buyVol = 0, sellVol = 0;
  tradeBuffer.filter(t => t.ts >= candleStart && t.ts < candleEnd).forEach(t => {
    if (t.side === 'buy') buyVol += t.size;
    else sellVol += t.size;
  });

  const delta = buyVol - sellVol;
  const totalVol = buyVol + sellVol;
  const deltaPct = totalVol > 0 ? (delta / totalVol) * 100 : 0;

  let cvd = 0;
  for (let i = Math.max(0, candles.length - CONFIG.CVD_LOOKBACK); i < candles.length; i++) {
    const s = candles[i].t, e = s + intervalMs;
    let b = 0, se = 0;
    tradeBuffer.filter(t => t.ts >= s && t.ts < e).forEach(t => {
    if (t.side === 'buy') {
        b += t.size;
    } else {
        se += t.size;
    }
});
    cvd += (b - se);
  }

  const priceUp = parseFloat(lastCandle.c) > parseFloat(candles[candles.length - 2].c);
  const deltaDown = delta < 0;
  const divergence = priceUp && deltaDown ? 'bearish' : !priceUp && delta > 0 ? 'bullish' : null;

  return { delta, deltaPct, buyVol, sellVol, cvd, divergence };
}

function sendSmsAlert(number, message) {
  if (!number) return;
  exec(`termux-sms-send -n "${number}" "${message}"`, (err) => {
    if (err) console.error(chalk.red("SMS failed:"), err.message);
    else console.log(C.green(`SMS sent: ${message}`));
  });
}

class AnalysisCore {
  constructor(geminiKey) {
    if (!geminiKey) throw new Error("GEMINI_API_KEY required");
    const { GoogleGenerativeAI } = require('@google/generative-ai');
    this.genAI = new GoogleGenerativeAI(geminiKey);
    const system = `Elite Bybit scalper AI. ID 1 high-prob scalp (1-5m hold, 1.5:1+ R:R, 0.1-0.5% risk).
RULES:
1. HTF Bias: Up (P>SMA + RSI>50 + CVD+), Down (opp), Range (else)
2. LTF Entry: MACD cross/RSI bounce/delta surge aligned w/ bias
3. Confluence: Near POC/VA + delta/CVD matching
4. SL: Behind S/R or ATR*1.5 | TP: Next S/R/wall, min 1.5R
5. Filters: Conf>80%, HOLD if R:R<1.5, ATR<0.5*avg, OB| >30%
Output ONLY minified JSON. Reference data in reason.`;
    this.model = this.genAI.getGenerativeModel({
      model: CONFIG.GEMINI_MODEL,
      generationConfig: { responseMimeType: "application/json", temperature: 0.2, topP: 0.7, maxOutputTokens: 600 },
      systemInstruction: system,
    });
  }

  makePrompt(symbol, data, symbolInfo, timeframes, srLevels, obData, vpData, ofData) {
    const htf = timeframes[timeframes.length - 1], ltf = timeframes[0];
    const price = parseFloat(data[ltf]?.latest?.c);
    if (price === undefined) return "";

    let p = `SNAPSHOT ${symbol}: P ${formatPrice(price, symbolInfo)}\n\n`;
    p += `S/R (${htf}): S ${srLevels.supports.map(p=>formatPrice(p,symbolInfo)).join(',')||'—'} R ${srLevels.resistances.map(p=>formatPrice(p,symbolInfo)).join(',')||'—'}\n\n`;
    if (obData) p += `OB: Imb ${obData.imbalance.toFixed(1)}% BW ${obData.buyWalls.map(w=>`${w.size.toFixed(1)}@${formatPrice(w.price,symbolInfo)}`).join(' ')||'—'} SW ${obData.sellWalls.map(w=>`${w.size.toFixed(1)}@${formatPrice(w.price,symbolInfo)}`).join(' ')||'—'}\n\n`;
    if (vpData) p += `VP (${ltf}): POC ${formatPrice(vpData.poc, symbolInfo)} VA ${formatPrice(vpData.val, symbolInfo)}–${formatPrice(vpData.vah, symbolInfo)} ${price >= vpData.val && price <= vpData.vah ? 'IN' : 'OUT'}\n\n`;
    if (ofData) p += `OF: Δ ${ofData.deltaPct > 0 ? '+' : ''}${ofData.deltaPct.toFixed(1)}% CVD ${ofData.cvd > 0 ? '+' : ''}${ofData.cvd}${ofData.divergence ? ` DIV ${ofData.divergence.toUpperCase()}` : ''}\n\n`;
    for (const [tf, { candles }] of Object.entries(data)) {
      if (!candles || candles.length < 50) continue;
      const ind = calculateIndicators(candles);
      p += `${tf}: SMA ${formatPrice(ind.sma, symbolInfo)} RSI ${ind.rsi?.toFixed(1)||'—'} ATR ${formatPrice(ind.atr, symbolInfo)} AvgATR ${formatPrice(ind.avgAtr, symbolInfo)}\n`;
    }
    p += `\nOUTPUT (JSON): {"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":123.45,"tp":124.56,"sl":122.34,"reason":{"bias":"...","entry_trigger":"...","sl_rationale":"...","tp_rationale":"..."}}`;
    return p.trim();
  }

  async callGemini(prompt) {
    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      if (!response.candidates || response.candidates.length === 0) throw new Error("No candidates returned.");
      const text = response.text();
      return text.trim();
    } catch (e) {
      console.error(C.red("Gemini Error:"), e.message);
      throw e;
    }
  }

  parseSignal(raw) {
    try {
      const jsonStr = (raw.match(/```json\s*([\s\S]*?)\s*```/) || [null, raw])[1]?.trim() || raw.trim();
      const obj = JSON.parse(jsonStr);
      const r = obj.reason || {};
      return {
        signal: ["BUY","SELL","HOLD"].includes(obj.signal?.toUpperCase()) ? obj.signal.toUpperCase() : "HOLD",
        conf: Math.min(100, Math.max(0, parseInt(obj.confidence) || 0)),
        entry: typeof obj.entry === 'number' ? obj.entry : null,
        tp: typeof obj.tp === 'number' ? obj.tp : null,
        sl: typeof obj.sl === 'number' ? obj.sl : null,
        reason: {
          bias: r.bias || "N/A",
          entry_trigger: r.entry_trigger || "N/A",
          sl_rationale: r.sl_rationale || "N/A",
          tp_rationale: r.tp_rationale || "N/A",
        },
      };
    } catch (e) {
      console.error(C.red("Parse failed:"), e.message);
      return { signal: "HOLD", conf: 0, reason: { bias: "Parse error" } };
    }
  }

  async analyze(symbol, klineData, symbolInfo, timeframes, obData, vpData, ofData) {
    if (!klineData || Object.keys(klineData).length === 0) return null;
    const htf = timeframes[timeframes.length - 1];
    const srLevels = calculateSRLevels(klineData[htf]?.candles || [], CONFIG.SR_LOOKBACK);
    const prompt = this.makePrompt(symbol, klineData, symbolInfo, timeframes, srLevels, obData, vpData, ofData);
    if (!prompt) return null;
    const resp = await this.callGemini(prompt).catch(() => null);
    return resp ? this.parseSignal(resp) : null;
  }
}

class ScalpBot {
  constructor(symbols, timeframes, geminiKey, phoneNumber) {
    this.symbols = symbols;
    this.timeframes = timeframes.sort((a, b) => parseInt(a) - parseInt(b));
    this.triggerTf = this.timeframes[0];
    this.analysisCore = new AnalysisCore(geminiKey);
    this.phoneNumber = phoneNumber;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.pingTimer = null;
  }

  connect() {
    console.log(C.info("\nConnecting to Bybit WS..."));
    this.ws = new WebSocket(CONFIG.WS_URL);
    this.ws.on('open', () => { console.log(C.buy("Connected. Subscribing...")); this.reconnectAttempts = 0; this.subscribe(); this.startPing(); });
    this.ws.on('message', d => this.onMessage(d));
    this.ws.on('close', () => this.reconnectWS());
    this.ws.on('error', e => console.error(C.red("WS Error:"), e.message));
  }

  subscribe() {
    const args = [];
    for (const s of this.symbols) {
      if (!state.klineBuffer.has(s)) state.klineBuffer.set(s, new Map());
      if (!state.orderbook.has(s)) state.orderbook.set(s, { bids: [], asks: [], ts: 0 });
      if (!state.ticker.has(s)) state.ticker.set(s, {});
      if (!state.tradeBuffer.has(s)) state.tradeBuffer.set(s, []);
      if (!state.lastSmsAlert.has(s)) state.lastSmsAlert.set(s, 0);

      for (const tf of this.timeframes) {
        args.push(`kline.${tf}.${s}`);
        if (!state.klineBuffer.get(s).has(tf)) state.klineBuffer.get(s).set(tf, []);
        state.lastCandle.set(s + tf, 0);
      }
      args.push(`orderbook.${CONFIG.ORDERBOOK_DEPTH}.${s}`, `tickers.${s}`, `trade.${s}`);
    }
    this.ws.send(JSON.stringify({ op: "subscribe", args }));
    console.log(C.buy(`Subscribed: ${this.symbols.join(', ')} on ${this.timeframes.join(', ')}`));
  }

  startPing() {
    clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('{"op":"ping"}');
      }
    }, CONFIG.PING_INTERVAL);
  }

  reconnectWS() {
    console.log(C.yellow("Connection closed. Reconnecting..."));
    clearInterval(this.pingTimer);
    if (this.reconnectAttempts < CONFIG.BACKTEST_MAX_RECONNECTS) {
      const delay = CONFIG.BACKTEST_RECONNECT_DELAY_MULTIPLIER * (this.reconnectAttempts + 1);
      console.log(C.yellow(`Attempt ${this.reconnectAttempts + 1}/${CONFIG.BACKTEST_MAX_RECONNECTS}. Retrying in ${delay / 1000}s...`));
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), delay);
    } else {
      console.error(C.red("Max reconnect attempts reached. Exiting."));
      process.exit(1);
    }
  }

  async onMessage(raw) {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }
    if (!msg.topic) return;

    if (msg.topic.includes("kline")) await this.onKline(msg);
    else if (msg.topic.includes("orderbook")) this.onOrderbook(msg);
    else if (msg.topic.includes("tickers")) this.onTicker(msg);
    else if (msg.topic.includes("trade")) this.onTrade(msg);
  }

  onOrderbook(msg) {
    const symbol = msg.topic.split('.').pop();
    const data = msg.data;
    const ob = state.orderbook.get(symbol);
    if (!ob) return;

    const updateOrderbook = (arr, updates) => {
      updates.forEach(([price, qty]) => {
        const p = parseFloat(price), q = parseFloat(qty);
        const index = arr.findIndex(e => e.p === p);
        if (q === 0) {
          if (index >= 0) arr.splice(index, 1);
        } else {
          if (index >= 0) arr[index].q = q;
          else arr.push({ p, q });
        }
      });
      arr.sort((a, b) => (arr === ob.bids ? b.p - a.p : a.p - b.p));
    };

    if (data.type === "snapshot") {
      ob.bids = (data.b || data.bids || []).map(([p, q]) => ({ p: parseFloat(p), q: parseFloat(q) }));
      ob.asks = (data.a || data.asks || []).map(([p, q]) => ({ p: parseFloat(p), q: parseFloat(q) }));
    } else {
      updateOrderbook(ob.bids, data.b || data.bids || []);
      updateOrderbook(ob.asks, data.a || data.asks || []);
    }
    ob.ts = Date.now();
  }

  formatOB(symbol) {
    const ob = state.orderbook.get(symbol);
    if (!ob || ob.bids.length === 0 || ob.asks.length === 0) return null;

    const bids = ob.bids.slice(0, CONFIG.ORDERBOOK_DEPTH);
    const asks = ob.asks.slice(0, CONFIG.ORDERBOOK_DEPTH);

    const totalBidVolume = bids.reduce((sum, b) => sum + b.q, 0);
    const totalAskVolume = asks.reduce((sum, a) => sum + a.q, 0);
    const totalVolume = totalBidVolume + totalAskVolume;

    const imbalance = totalVolume > 0 ? ((totalBidVolume - totalAskVolume) / totalVolume) * 100 : 0;

    const avgBidSize = totalBidVolume / bids.length;
    const avgAskSize = totalAskVolume / asks.length;

    const buyWalls = bids.filter(b => b.q > avgBidSize * 3.5).map(b => ({ price: b.p, size: b.q })).slice(0, 2);
    const sellWalls = asks.filter(a => a.q > avgAskSize * 3.5).map(a => ({ price: a.p, size: a.q })).slice(0, 2);

    return { imbalance, buyWalls, sellWalls };
  }

  onTicker(msg) {
    const symbol = msg.topic.split('.').pop();
    const data = msg.data;
    state.ticker.set(symbol, { price: parseFloat(data.markPrice), change24h: parseFloat(data.price24hPcnt) * 100 });
  }

  onTrade(msg) {
    const symbol = msg.topic.split('.').pop();
    const buffer = state.tradeBuffer.get(symbol);
    if (!buffer) return;

    msg.data.forEach(trade => {
      const aggressiveSide = trade.isBuyerMaker ? 'sell' : 'buy';
      buffer.push({
        ts: Date.now(),
        price: parseFloat(trade.price),
        size: parseFloat(trade.size),
        side: aggressiveSide,
      });
    });

    if (buffer.length > 500) {
      buffer.shift(); // Keep buffer size manageable
    }
  }

  async onKline(msg) {
    const [_, tf, symbol] = msg.topic.split('.');
    const candleData = msg.data[0];
    if (!candleData || !candleData.confirm) return;

    const candle = {
      t: parseInt(candleData.start),
      o: parseFloat(candleData.open),
      h: parseFloat(candleData.high),
      l: parseFloat(candleData.low),
      c: parseFloat(candleData.close),
      v: parseFloat(candleData.volume),
    };

    const buffer = state.klineBuffer.get(symbol)?.get(tf);
    if (!buffer) return;

    const key = symbol + tf;
    const lastTimestamp = state.lastCandle.get(key) || 0;

    if (candle.t > lastTimestamp) {
      if (buffer.length >= CONFIG.MAX_BUFFER) buffer.shift();
      buffer.push(candle);
      state.lastCandle.set(key, candle.t);

      const klineDataAggregated = { triggerTf: tf };
      this.timeframes.forEach(t => {
        const buf = state.klineBuffer.get(symbol)?.get(t);
        if (buf && buf.length > 0) {
          klineDataAggregated[t] = { candles: buf, latest: buf[buf.length - 1] };
        }
      });

      const symbolInfo = await getSymbolInfo(symbol).catch(() => null);
      const obData = this.formatOB(symbol);

      if (symbolInfo && klineDataAggregated[this.triggerTf]) {
        this.printLiveDashboard(symbol, klineDataAggregated, symbolInfo, obData);
      }

      if (tf === this.triggerTf && !state.pending.has(symbol)) {
        const isReady = this.timeframes.every(t => state.klineBuffer.get(symbol)?.get(t)?.length >= 50);
        if (isReady) {
          state.pending.add(symbol);
          setTimeout(async () => {
            try {
              const fullKlineData = {};
              this.timeframes.forEach(t => {
                const b = state.klineBuffer.get(symbol)?.get(t);
                if (b && b.length >= 50) fullKlineData[t] = { candles: b, latest: b[b.length - 1] };
              });

              if (Object.keys(fullKlineData).length < this.timeframes.length) return;

              const vpData = calculateVolumeProfile(fullKlineData[this.triggerTf].candles, CONFIG.VP_LOOKBACK);
              const ofData = calculateOrderFlow(fullKlineData[this.triggerTf].candles, state.tradeBuffer.get(symbol));
              const signal = await this.analysisCore.analyze(symbol, fullKlineData, symbolInfo, this.timeframes, obData, vpData, ofData);

              if (signal) {
                this.printSignal(symbol, candle.c, signal, symbolInfo);
                this.alertSignal(symbol, signal, symbolInfo);
              }
            } catch (e) {
              console.error(C.red("Analysis failed:"), e.message);
            } finally {
              state.pending.delete(symbol);
            }
          }, 100);
        }
      }
    }
  }

  printLiveDashboard(symbol, klineData, symbolInfo, obData) {
    const tf = this.triggerTf;
    const latestCandle = klineData[tf]?.latest;
    if (!latestCandle || !symbolInfo) return;

    const price = parseFloat(latestCandle.c);
    const indicatorsLTF = calculateIndicators(klineData[tf].candles);
    const htf = this.timeframes[this.timeframes.length - 1];
    const srLevels = calculateSRLevels(klineData[htf]?.candles || [], CONFIG.SR_LOOKBACK);
    const vpData = calculateVolumeProfile(klineData[tf].candles, CONFIG.VP_LOOKBACK);
    const ofData = calculateOrderFlow(klineData[tf].candles, state.tradeBuffer.get(symbol)) || {};
    const indicatorsHTF = calculateIndicators(klineData[htf]?.candles || []);

    const isBullishHTF = indicatorsHTF.close > indicatorsHTF.sma && indicatorsHTF.rsi > 50 && ofData.cvd > 0;
    const isBearishHTF = indicatorsHTF.close < indicatorsHTF.sma && indicatorsHTF.rsi < 50 && ofData.cvd < 0;
    const trend = isBullishHTF ? C.buy('🐂 Bullish') : isBearishHTF ? C.sell('🐻 Bearish') : C.hold(' sideways');

    console.log(C.title(`\nLIVE: ${symbol} [${tf}] | HTF Trend: ${trend}`));
    console.log(`  ${C.price(`P: $${formatPrice(price, symbolInfo)}`)} | SMA: ${formatPrice(indicatorsLTF.sma, symbolInfo)} | RSI: ${indicatorsLTF.rsi?.toFixed(1) || 'N/A'}`);
    if (vpData) console.log(`  POC: $${formatPrice(vpData.poc, symbolInfo)} | VA: $${formatPrice(vpData.val, symbolInfo)}–$${formatPrice(vpData.vah, symbolInfo)}`);
    if (ofData.deltaPct !== undefined) {
      const deltaColor = ofData.deltaPct > 0 ? C.buy : C.sell;
      console.log(`  ${deltaColor(`Δ: ${ofData.deltaPct > 0 ? '+' : ''}${ofData.deltaPct.toFixed(1)}%`)} | CVD: ${ofData.cvd > 0 ? '+' : ''}${ofData.cvd.toFixed(0)} ${ofData.divergence ? `| ${C.alert(`DIV: ${ofData.divergence.toUpperCase()}`)}` : ''}`);
    }
    const now = Date.now();
    const nextCandleTime = latestCandle.t + getIntervalMs(tf);
    const timeUntilNext = Math.max(0, Math.ceil((nextCandleTime - now) / 1000));
    console.log(chalk.gray(`  S: ${srLevels.supports.map(p => formatPrice(p, symbolInfo)).join(', ') || '—'} | R: ${srLevels.resistances.map(p => formatPrice(p, symbolInfo)).join(', ') || '—'} | Next in ${timeUntilNext}s`));
    console.log(C.info("─".repeat(70)));
  }

  alertSignal(symbol, signal, symbolInfo) {
    if (signal.signal === "HOLD" || signal.conf < CONFIG.MIN_CONFIDENCE_TO_ALERT) return;
    const lastAlertTime = state.lastSmsAlert.get(symbol) || 0;
    if (Date.now() - lastAlertTime > 15 * 60 * 1000) {
      const msg = `${symbol} ${signal.signal} | Conf: ${signal.conf}% | E: ${formatPrice(signal.entry, symbolInfo)} | SL: ${formatPrice(signal.sl, symbolInfo)}`;
      sendSmsAlert(this.phoneNumber, msg);
      state.lastSmsAlert.set(symbol, Date.now());
    }
  }

  printSignal(symbol, price, s, symbolInfo) {
    const color = s.signal === "BUY" ? C.buy : s.signal === "SELL" ? C.sell : C.hold;
    const confColor = s.conf >= CONFIG.MIN_CONFIDENCE_TO_ALERT ? C.alert : C.conf;
    console.log(C.title(`\nSCALP SIGNAL: ${symbol}`));
    console.log(`  ${C.price(`Price: $${formatPrice(price, symbolInfo)}`)} | ${color(s.signal)} | ${confColor(`Conf: ${s.conf}%`)}`);
    if (s.signal !== 'HOLD' && s.entry && s.tp && s.sl) {
      const rr = (Math.abs(s.tp - s.entry) / Math.abs(s.entry - s.sl)).toFixed(2);
      console.log(`  ${C.entry(`E: $${formatPrice(s.entry, symbolInfo)}`)} ${C.tp(`TP: $${formatPrice(s.tp, symbolInfo)}`)} ${C.sl(`SL: $${formatPrice(s.sl, symbolInfo)}`)} ${C.info(`R:R ${rr}`)}`);
      console.log(chalk.gray("─".repeat(60)));
      console.log(`  ${C.label("Bias:")}    ${C.reason(s.reason.bias)}`);
      console.log(`  ${C.label("Trigger:")} ${C.reason(s.reason.entry_trigger)}`);
      console.log(`  ${C.label("SL:")}      ${C.reason(s.reason.sl_rationale)}`);
      console.log(`  ${C.label("TP:")}      ${C.reason(s.reason.tp_rationale)}`);
    } else {
      console.log(`  ${C.reason(s.reason.bias)}`);
    }
    console.log(C.title("─".repeat(60)));
  }
}

class Backtester {
  constructor(symbol, timeframes, geminiKey) {
    this.symbol = symbol;
    this.timeframes = timeframes.sort((a, b) => parseInt(a) - parseInt(b));
    this.triggerTf = this.timeframes[0];
    this.analysisCore = new AnalysisCore(geminiKey);
    this.historicalData = {};
    this.trades = [];
    this.returns = [];
    this.equity = CONFIG.BACKTEST_INITIAL_EQUITY;
    this.peakEquity = CONFIG.BACKTEST_INITIAL_EQUITY;
    this.maxDD = 0;
  }

  async fetchHistoricalData(interval, days) {
    const limit = 1000;
    let allCandles = [];
    let endTime = Date.now();
    console.log(C.yellow(`Fetching ${days}d of ${interval} for ${this.symbol}...`));

    while (endTime > Date.now() - days * 86400000) {
      const startTime = endTime - limit * getIntervalMs(interval);
      const url = `${CONFIG.API_URL}/v5/market/kline?category=linear&symbol=${this.symbol}&interval=${interval}&start=${startTime}&end=${endTime}&limit=${limit}`;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.retCode !== 0 || !data.result?.list) throw new Error(data.retMsg || "Invalid data format");

        const klines = data.result.list.map(k => ({ t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5]) })).reverse();
        allCandles = [...klines, ...allCandles];

        if (klines.length < limit) break;
        endTime = klines[0].t - 1;
        process.stdout.write(C.gray(`\rFetched ${allCandles.length} candles...`));
        await new Promise(r => setTimeout(r, 600));
      } catch (error) {
        console.error(C.red(`Error fetching ${interval} for ${this.symbol}: ${error.message}`));
        break;
      }
    }
    console.log(C.buy(`\nFetched ${allCandles.length} ${interval} candles.`));
    return allCandles;
  }

  async prepareData() {
    await fs.mkdir(CONFIG.HISTORICAL_DATA_DIR, { recursive: true });
    const file = path.join(CONFIG.HISTORICAL_DATA_DIR, `${this.symbol}_${CONFIG.BACKTEST_DAYS}d.json`);
    try {
      const fileContent = await fs.readFile(file, 'utf-8');
      this.historicalData = JSON.parse(fileContent);
      console.log(C.buy(`Loaded backtest data from ${file}`));
    } catch (e) {
      console.log(C.yellow(`Data file not found or invalid. Fetching data...`));
      for (const tf of this.timeframes) {
        this.historicalData[tf] = await this.fetchHistoricalData(tf, CONFIG.BACKTEST_DAYS);
      }
      await fs.writeFile(file, JSON.stringify(this.historicalData, null, 2));
      console.log(C.buy(`Saved historical data to ${file}`));
    }
  }

  async run() {
    await this.prepareData();
    const symbolInfo = await getSymbolInfo(this.symbol);
    const primaryData = this.historicalData[this.triggerTf];
    if (!primaryData || primaryData.length < CONFIG.MAX_BUFFER) {
      console.error(C.red(`Insufficient data for backtest on ${this.triggerTf}. Found ${primaryData?.length || 0} candles, need at least ${CONFIG.MAX_BUFFER}.`));
      return;
    }

    const buffers = new Map();
    this.timeframes.forEach(tf => buffers.set(tf, []));
    let currentTrade = null;

    for (let i = 0; i < primaryData.length; i++) {
      const currentCandle = primaryData[i];
      this.timeframes.forEach(tf => {
        const tfData = this.historicalData[tf];
        const candle = tfData.find(k => k.t === currentCandle.t);
        if (candle) {
          const buffer = buffers.get(tf);
          if (buffer.length >= CONFIG.MAX_BUFFER) buffer.shift();
          buffer.push(candle);
        }
      });

      const isDataReady = this.timeframes.every(tf => buffers.get(tf).length >= 50);
      if (!isDataReady) continue;

      const candleDataForAnalysis = {};
      this.timeframes.forEach(tf => {
        const buffer = buffers.get(tf);
        candleDataForAnalysis[tf] = { candles: buffer, latest: buffer[buffer.length - 1] };
      });

      process.stdout.write(C.gray(`\rSimulating: ${new Date(currentCandle.t).toLocaleString()} | Equity: $${this.equity.toFixed(0)} | Trades: ${this.trades.length} | MaxDD: ${this.maxDD.toFixed(2)}%`));

      // Check for trade exit
      if (currentTrade) {
        const { type, entryPrice, sl, tp } = currentTrade;
        let exitPrice = null, outcome = null;

        if (type === 'BUY') {
          if (currentCandle.l <= sl) { exitPrice = sl; outcome = 'loss'; }
          else if (currentCandle.h >= tp) { exitPrice = tp; outcome = 'win'; }
        } else { // SELL
          if (currentCandle.h >= sl) { exitPrice = sl; outcome = 'loss'; }
          else if (currentCandle.l <= tp) { exitPrice = tp; outcome = 'win'; }
        }

        if (exitPrice !== null) {
          const realizedEntryFee = entryPrice * CONFIG.FEE_RATE;
          const realizedSlippage = exitPrice * CONFIG.SLIPPAGE_PERCENT * (type === 'BUY' ? 1 : -1);
          const finalExitPrice = exitPrice + realizedSlippage;
          const realizedExitFee = finalExitPrice * CONFIG.FEE_RATE;
          const pnl = (type === 'BUY' ? (finalExitPrice - entryPrice) : (entryPrice - finalExitPrice)) - realizedEntryFee - realizedExitFee;
          const pnlPercent = (pnl / entryPrice) * 100;

          this.equity += (pnl / entryPrice) * this.equity;
          this.peakEquity = Math.max(this.peakEquity, this.equity);
          this.maxDD = Math.max(this.maxDD, ((this.peakEquity - this.equity) / this.peakEquity) * 100);

          this.trades.push({ ...currentTrade, outcome, exitPrice: finalExitPrice, pnl, pnlPercent, timestamp: currentCandle.t });
          this.returns.push(pnlPercent);
          currentTrade = null;
        }
      }

      // Check for new trade entry
      if (!currentTrade) {
        const signal = await this.analysisCore.analyze(this.symbol, candleDataForAnalysis, symbolInfo, this.timeframes, null, null, null);
        if (signal && signal.signal !== 'HOLD' && signal.entry && signal.tp && signal.sl) {
          const entryPrice = signal.entry;
          const sl = signal.sl;
          const tp = signal.tp;
          const risk = Math.abs(entryPrice - sl);
          const reward = Math.abs(tp - entryPrice);

          if (reward >= risk * 1.5) { // Ensure R:R is met
            currentTrade = {
              type: signal.signal,
              entryPrice: entryPrice,
              sl: sl,
              tp: tp,
              timestamp: currentCandle.t,
              confidence: signal.conf,
              reason: signal.reason,
            };
          }
        }
      }
    }
    this.printResults();
  }

  printResults() {
    console.log(C.title(`\n\n--- BACKTEST RESULTS: ${this.symbol} (${CONFIG.BACKTEST_DAYS} days) ---`));
    if (this.trades.length === 0) {
      console.log(C.yellow("No trades were executed during the backtest."));
      return;
    }

    const wins = this.trades.filter(t => t.outcome === 'win').length;
    const winRate = (wins / this.trades.length * 100).toFixed(2);
    const totalReturnPercent = ((this.equity - CONFIG.BACKTEST_INITIAL_EQUITY) / CONFIG.BACKTEST_INITIAL_EQUITY * 100).toFixed(2);

    const avgReturn = this.returns.reduce((a, b) => a + b, 0) / this.returns.length;
    const variance = this.returns.map(r => Math.pow(r - avgReturn, 2)).reduce((a, b) => a + b, 0) / this.returns.length;
    const stdDev = Math.sqrt(variance);
    const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0; // Assuming 252 trading days

    const profitLoss = this.trades.reduce((acc, t) => acc + t.pnl, 0);
    const grossProfit = this.trades.filter(t => t.outcome === 'win').reduce((acc, t) => acc + t.pnl, 0);
    const grossLoss = this.trades.filter(t => t.outcome === 'loss').reduce((acc, t) => acc + Math.abs(t.pnl), 0);
    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : "∞";

    console.log(C.info(`Total Trades: ${this.trades.length} | Wins: ${wins} | Losses: ${this.trades.length - wins}`));
    console.log(C.info(`Win Rate: ${winRate}% | Profit Factor: ${profitFactor}`));
    console.log(C.info(`Total Return: ${totalReturnPercent}% | Final Equity: $${this.equity.toFixed(2)}`));
    console.log(C.info(`Max Drawdown: ${this.maxDD.toFixed(2)}% | Sharpe Ratio: ${sharpeRatio.toFixed(2)}`));
    console.log(C.info("─".repeat(70)));

    // Optionally print trade details
    // console.log("\nTrade Log:");
    // this.trades.forEach(t => {
    //   console.log(`  ${new Date(t.timestamp).toLocaleString()} | ${t.type} | ${t.outcome.toUpperCase()} | Entry: ${formatPrice(t.entryPrice, symbolInfo)} | Exit: ${formatPrice(t.exitPrice, symbolInfo)} | PNL: ${t.pnlPercent.toFixed(2)}%`);
    // });
  }
}

async function main() {
  const args = {};
  process.argv.slice(2).forEach((v, i, a) => { if (v.startsWith('--')) args[v.slice(2)] = a[i + 1] && !a[i + 1].startsWith('--') ? a[i + 1] : true; });

  console.log(C.title(`\n--- Definitive Gemini Scalping Engine ---`));

  const symbol = args.symbol || await promptUser('Symbol (e.g. BTCUSDT): ');
  const timeframesInput = args.timeframes || await promptUser('Timeframes (comma-separated, e.g., 1,5,15): ');
  const timeframes = timeframesInput.split(',').map(t => t.trim()).sort((a, b) => parseInt(a) - parseInt(b));

  rl.close();

  const mode = args.mode || 'live';
  const geminiApiKey = args['gemini-key'] || CONFIG.GEMINI_API_KEY;
  if (!geminiApiKey) { console.error(C.red("GEMINI_API_KEY is required. Set it as an environment variable or use --gemini-key.")); process.exit(1); }

  console.log(C.info(`Mode: ${mode.toUpperCase()} | Symbol: ${symbol.toUpperCase()} | Timeframes: ${timeframes.join(', ')}`));
  await getSymbolInfo(symbol.toUpperCase()); // Pre-fetch symbol info

  if (mode === 'live') {
    const alertPhoneNumber = args['phone-number'] || CONFIG.ALERT_PHONE_NUMBER;
    if (!alertPhoneNumber) console.log(C.red("SMS Alerts: DISABLED (ALERT_PHONE_NUMBER not set)"));
    new ScalpBot([symbol.toUpperCase()], timeframes, geminiApiKey, alertPhoneNumber).connect();
  } else if (mode === 'backtest') {
    const backtester = new Backtester(symbol.toUpperCase(), timeframes, geminiApiKey);
    await backtester.run();
  } else {
    console.error(chalk.red(`Invalid mode: ${mode}. Use 'live' or 'backtest'.`));
    process.exit(1);
  }

  process.on('SIGINT', () => { console.log(C.title("\nShutting down...")); process.exit(0); });
}

main().catch(e => console.error("FATAL ERROR:", e));
