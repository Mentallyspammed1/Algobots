// MTF Scalping Bot + Gemini SDK + Bybit WS + Advanced Analysis (DEFINITIVE ENHANCED – nanocolors)
// Runs on ARM64 Termux. Requires: ws, nanocolors, fs/promises, readline, child_process, @google/generative-ai, node-fetch

// --- Dependencies ---
const { exec } = require('child_process');
const fs = require('fs/promises');
const path = require('path');
const readline = require('readline');

let WebSocket, fetch, nano;
try {
  WebSocket = require('ws');
  nano = require('nanocolors');
  fetch = globalThis.fetch || require('node-fetch');
} catch (e) {
  console.error(nano.red("FATAL: Missing packages. Run: npm i ws nanocolors @google/generative-ai node-fetch"));
  process.exit(1);
}

// --- Colors & Styling (nanocolors) ---
const C = {
  buy:   nano.bold(nano.green),
  sell:  nano.bold(nano.red),
  hold:  nano.bold(nano.gray),
  price: nano.white,
  entry: nano.cyan,
  tp:    nano.bold(nano.green),
  sl:    nano.bold(nano.magenta),
  info:  nano.cyan,
  alert: nano.bold(nano.magenta),
  title: nano.bold(nano.magenta),
  reason: nano.gray,
  conf:  nano.white,
  label: nano.bold(nano.gray),
  red:   nano.red,
  green: nano.green,
  yellow: nano.yellow,
  cyan:  nano.cyan,
  gray:  nano.gray,
};

// --- CONFIGURATION ---
const CONFIG = {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY || null,
  ALERT_PHONE_NUMBER: process.env.ALERT_PHONE_NUMBER || null,
  MIN_CONFIDENCE_TO_ALERT: 85,
  GEMINI_MODEL: "gemini-1.5-flash",
  WS_URL: "wss://stream.bybit.com/v5/public/linear",
  API_URL: "https://api.bybit.com",
  PING_INTERVAL: 20_000,
  MAX_BUFFER: 200,
  HISTORICAL_DATA_DIR: path.join(__dirname, 'backtest_data'),
  PAPER_TRADES_FILE: path.join(__dirname, 'paper_trades.json'),
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
  PAPER_INITIAL_EQUITY: 10000,
  MAX_RECONNECT_ATTEMPTS: 10,
  RECONNECT_DELAY: 2000,
  API_RETRY_ATTEMPTS: 3,
  API_RETRY_DELAY: 1000,
  DEFAULT_RISK_PERCENT: 0.02,
  DEFAULT_LEVERAGE: 10,
};

// --- State ---
const state = {
  klineBuffer: new Map(),
  orderbook: new Map(),
  ticker: new Map(),
  tradeBuffer: new Map(),
  lastCandle: new Map(),
  pending: new Set(),
  lastSmsAlert: new Map(),
  symbolInfoCache: new Map(),
  indicatorCache: new Map(),
  paper: {
    position: null, // { symbol, type, entry, sl, tp, size, equity, timestamp }
    equity: CONFIG.PAPER_INITIAL_EQUITY,
    trades: [],
  },
};

// --- Logging ---
async function logToFile(message) {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] ${message}\n`;
  try {
    await fs.appendFile(path.join(__dirname, 'bot.log'), logMessage);
  } catch (e) {
    console.error(C.red(`Failed to write to log: ${e.message}`));
  }
}

// --- UTILITY FUNCTIONS ---
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const promptUser = (query) => new Promise(resolve => rl.question(C.cyan(query), resolve));

async function getSymbolInfo(symbol) {
  if (state.symbolInfoCache.has(symbol)) return state.symbolInfoCache.get(symbol);
  for (let attempt = 1; attempt <= CONFIG.API_RETRY_ATTEMPTS; attempt++) {
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
      if (attempt === CONFIG.API_RETRY_ATTEMPTS) {
        console.error(C.red(`\nSymbol info fetch failed for ${symbol}: ${e.message}`));
        await logToFile(`Symbol info fetch failed for ${symbol}: ${e.message}`);
        process.exit(1);
      }
      await new Promise(resolve => setTimeout(resolve, CONFIG.API_RETRY_DELAY * attempt));
    }
  }
}

function formatPrice(price, symbolInfo) {
  return (typeof price === 'number' && symbolInfo) ? price.toFixed(symbolInfo.decimals) : "N/A";
}

function getIntervalMs(tf) {
  const m = { '1m': 60, '3m': 180, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };
  return (m[tf] || 60) * 1000;
}

// --- Paper Trading ---
async function loadPaperState() {
  try {
    const data = await fs.readFile(CONFIG.PAPER_TRADES_FILE, 'utf-8');
    const parsed = JSON.parse(data);
    state.paper.equity = parsed.equity || CONFIG.PAPER_INITIAL_EQUITY;
    state.paper.trades = parsed.trades || [];
    if (parsed.position) {
      state.paper.position = parsed.position;
      console.log(C.green(`📂 Paper position restored: ${parsed.position.type} ${parsed.position.symbol} @ ${formatPrice(parsed.position.entry, await getSymbolInfo(parsed.position.symbol))}`));
      await logToFile(`Paper position restored: ${JSON.stringify(parsed.position)}`);
    }
  } catch (e) {
    console.log(C.yellow("📂 No saved paper state found. Starting fresh."));
    await logToFile("No saved paper state found.");
  }
}

async function savePaperState() {
  const toSave = {
    equity: state.paper.equity,
    trades: state.paper.trades,
    position: state.paper.position,
  };
  try {
    await fs.writeFile(CONFIG.PAPER_TRADES_FILE, JSON.stringify(toSave, null, 2));
    await logToFile("Paper state saved.");
  } catch (e) {
    console.error(C.red(`Failed to save paper state: ${e.message}`));
    await logToFile(`Failed to save paper state: ${e.message}`);
  }
}

async function openPaperTrade(symbol, type, entry, sl, tp, symbolInfo, riskPercent, leverage) {
  const size = (state.paper.equity * riskPercent * leverage) / Math.abs(entry - sl);
  const trade = {
    symbol, type, entry, sl, tp, size,
    equity: state.paper.equity,
    timestamp: Date.now(),
  };
  state.paper.position = trade;
  await savePaperState();
  console.log(C.green(`📈 PAPER ${type} ${symbol} @ ${formatPrice(entry, symbolInfo)} | Size: ${size.toFixed(2)} | Risk: ${(riskPercent * 100).toFixed(1)}% | Lev: ${leverage}x`));
  await logToFile(`Opened paper trade: ${JSON.stringify(trade)}`);
}

async function closePaperTrade(exitPrice, result, symbolInfo) {
  const pos = state.paper.position;
  if (!pos) return;

  const slippage = exitPrice * CONFIG.SLIPPAGE_PERCENT * (pos.type === 'BUY' ? -1 : 1);
  const finalExit = exitPrice + slippage;
  const entryFee = pos.entry * CONFIG.FEE_RATE;
  const exitFee = finalExit * CONFIG.FEE_RATE;
  const pnl = (pos.type === 'BUY' ? (finalExit - pos.entry) : (pos.entry - finalExit)) * pos.size - entryFee - exitFee;
  const pnlPercent = (pnl / (pos.entry * pos.size)) * 100;

  state.paper.equity += pnl;
  state.paper.trades.push({ ...pos, exitPrice: finalExit, result, pnl, pnlPercent, closeTime: Date.now() });
  state.paper.position = null;
  await savePaperState();

  const color = result === 'win' ? C.green : C.red;
  console.log(color(`📉 PAPER ${result.toUpperCase()}: ${pos.type} ${pos.symbol}`));
  console.log(color(`  Exit: ${formatPrice(finalExit, symbolInfo)} | PnL: ${pnlPercent > 0 ? '+' : ''}${pnlPercent.toFixed(2)}% ($${pnl.toFixed(2)})`));
  console.log(C.info(`  Equity: $${state.paper.equity.toFixed(2)}`));
  await logToFile(`Closed paper trade: ${pos.type} ${pos.symbol}, PnL: ${pnlPercent.toFixed(2)}%, Equity: ${state.paper.equity.toFixed(2)}`);
}

// --- INDICATORS & MARKET STRUCTURE ---
function sma(d, p) {
  if (d.length < p) return null;
  return d.slice(-p).reduce((s, c) => s + parseFloat(c.c), 0) / p;
}

function getEmaSeries(d, p) {
  if (d.length < p) return [];
  const data = d.map(c => parseFloat(c.c));
  const a = 2 / (p + 1);
  let cur = data.slice(0, p).reduce((s, r) => s + r, 0) / p;
  const ema = new Array(p).fill(cur);
  for (let i = p; i < data.length; i++) {
    cur = (data[i] - cur) * a + cur;
    ema[i] = cur;
  }
  return ema;
}

function macd(d) {
  if (d.length < 26) return { macd: null, histogram: null, signal: null };
  const e12 = getEmaSeries(d, 12), e26 = getEmaSeries(d, 26);
  const macdLine = e12.map((f, i) => f !== null && e26[i] !== null ? f - e26[i] : null).filter(v => v !== null);
  if (macdLine.length < 9) return { macd: null, histogram: null, signal: null };
  const signal = getEmaSeries(macdLine.map(m => ({ c: m })), 9);
  const m = macdLine[macdLine.length - 1], s = signal[signal.length - 1];
  return { macd: m, histogram: m && s ? m - s : null, signal: s };
}

function rsi(d, p) {
  if (d.length < p + 1) return null;
  let g = 0, l = 0;
  for (let i = d.length - p; i < d.length; i++) {
    const diff = parseFloat(d[i].c) - parseFloat(d[i - 1].c);
    if (diff > 0) g += diff; else l += Math.abs(diff);
  }
  if (l === 0) return 100;
  return 100 - (100 / (1 + (g / p) / (l / p)));
}

function atr(d, p) {
  if (d.length < p + 1) return null;
  const trs = [];
  for (let i = d.length - p; i < d.length; i++) {
    const c = d[i], pc = d[i - 1];
    trs.push(Math.max(parseFloat(c.h) - parseFloat(c.l), Math.abs(parseFloat(c.h) - parseFloat(pc.c)), Math.abs(parseFloat(c.l) - parseFloat(pc.c))));
  }
  return trs.reduce((a, b) => a + b, 0) / p;
}

function calculateIndicators(df, symbol, tf) {
  const cacheKey = `${symbol}_${tf}_${df[df.length - 1]?.t}`;
  const cached = state.indicatorCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CONFIG.INDICATOR_CACHE_TTL) {
    return cached.data;
  }

  if (df.length < 50) return {};
  const macdResult = macd(df);
  const atrs = [];
  for (let i = CONFIG.ATR_PERIOD; i <= df.length; i++) {
    const a = atr(df.slice(0, i), CONFIG.ATR_PERIOD);
    if (a !== null) atrs.push(a);
  }
  const avgAtr = atrs.length ? atrs.reduce((s, a) => s + a, 0) / atrs.length : null;
  const indicators = {
    sma: sma(df, CONFIG.SMA_PERIOD),
    rsi: rsi(df, CONFIG.RSI_PERIOD),
    atr: atr(df, CONFIG.ATR_PERIOD),
    avgAtr,
    macd: macdResult.macd,
    macdHist: macdResult.histogram,
    macdSignal: macdResult.signal,
    close: parseFloat(df[df.length - 1].c),
    volume: parseFloat(df[df.length - 1].v),
  };

  state.indicatorCache.set(cacheKey, { data: indicators, timestamp: Date.now() });
  if (state.indicatorCache.size > 1000) {
    const oldestKey = state.indicatorCache.keys().next().value;
    state.indicatorCache.delete(oldestKey);
  }

  return indicators;
}

function calculateSRLevels(candles, lookback = CONFIG.SR_LOOKBACK) {
  if (candles.length < lookback * 2 + 1) return { supports: [], resistances: [] };
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
  if (candles.length < 2) return null;
  const recent = candles.slice(-lookback);
  const map = new Map();
  recent.forEach(c => {
    const h = parseFloat(c.h), l = parseFloat(c.l), v = parseFloat(c.v);
    const step = (h - l) / Math.max(1, Math.floor(v / 1000));
    for (let p = l; p <= h; p += step) {
      const r = Math.round(p * 100) / 100;
      map.set(r, (map.get(r) || 0) + v / Math.max(1, Math.floor((h - l) / step)));
    }
  });
  const sorted = Array.from(map).sort((a, b) => a[0] - b[0]);
  if (!sorted.length) return null;
  const total = sorted.reduce((s, [, v]) => s + v, 0);
  const poc = sorted.reduce((m, c) => c[1] > m[1] ? c : m, sorted[0])[0];
  let cum = 0, vah = poc, val = poc, l = sorted.findIndex(p => p[0] === poc), r = l;
  while (cum < total * 0.7 && (l > 0 || r < sorted.length - 1)) {
    const lv = l > 0 ? sorted[l - 1][1] : 0;
    const rv = r < sorted.length - 1 ? sorted[r + 1][1] : 0;
    if (lv >= rv && l > 0) { cum += lv; val = sorted[--l][0]; }
    else if (r < sorted.length - 1) { cum += rv; vah = sorted[++r][0]; }
    else break;
  }
  return { poc, vah, val, totalVol: total };
}

function calculateOrderFlow(candles, tradeBuffer) {
  if (!tradeBuffer || tradeBuffer.length < 10 || candles.length < 2) return null;
  const now = candles[candles.length - 1].t;
  const start = now, end = now + getIntervalMs('1m');
  let buy = 0, sell = 0;
  tradeBuffer.filter(t => t.ts >= start && t.ts < end).forEach(t => {
    if (t.side === 'buy') buy += t.size;
    else sell += t.size;
  });
  const delta = buy - sell, total = buy + sell;
  const deltaPct = total > 0 ? (delta / total) * 100 : 0;

  let cvd = 0;
  for (let i = Math.max(0, candles.length - CONFIG.CVD_LOOKBACK); i < candles.length; i++) {
    const s = candles[i].t, e = s + getIntervalMs('1m');
    let b = 0, se = 0;
    tradeBuffer.filter(t => t.ts >= s && t.ts < e).forEach(t => {
      if (t.side === 'buy') b += t.size;
      else se += t.size;
    });
    cvd += (b - se);
  }

  const priceUp = parseFloat(candles[candles.length - 1].c) > parseFloat(candles[candles.length - 2].c);
  const deltaDown = delta < 0;
  const divergence = priceUp && deltaDown ? 'bearish' : !priceUp && delta > 0 ? 'bullish' : null;

  return { delta, deltaPct, buyVol: buy, sellVol: sell, cvd, divergence };
}

function sendSmsAlert(number, message) {
  if (!number) return;
  exec(`termux-sms-send -n "${number}" "${message}"`, (err) => {
    if (err) {
      console.error(C.red("SMS failed:"), err.message);
      logToFile(`SMS failed: ${err.message}`);
    } else {
      console.log(C.green(`📩 SMS sent: ${message}`));
      logToFile(`SMS sent: ${message}`);
    }
  });
}

// --- AI CORE ---
class AnalysisCore {
  constructor(geminiApiKey) {
    if (!geminiApiKey) throw new Error("GEMINI_API_KEY is required.");
    this.genAI = require('@google/generative-ai').GoogleGenerativeAI;
    this.genAI = new this.genAI(geminiApiKey);
    const systemInstruction = `Elite Bybit scalper AI. Identify high-probability scalp trades (1-5m hold, 1.5:1+ R:R, 0.1-0.5% risk).
Rules:
1. HTF Bias: Up (Price>SMA + RSI>50 + CVD+), Down (opposite), Range (else)
2. LTF Entry: MACD cross/RSI bounce/delta surge aligned with bias
3. Confluence: Near POC/VA + delta/CVD matching
4. SL: Behind S/R or ATR*1.5 | TP: Next S/R or orderbook wall, min 1.5R
5. Filters: Confidence>80%, HOLD if R:R<1.5, ATR<0.5*avg, OB Imbalance > 30%
Output JSON: {"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":123.45,"tp":124.56,"sl":122.34,"reason":{"bias":"...","entry_trigger":"...","sl_rationale":"...","tp_rationale":"..."}}`;
    this.model = this.genAI.getGenerativeModel({
      model: CONFIG.GEMINI_MODEL,
      generationConfig: { responseMimeType: "application/json", temperature: 0.2, topP: 0.7, maxOutputTokens: 600 },
      systemInstruction,
    });
  }

  makePrompt(symbol, klineData, symbolInfo, timeframes, srLevels, orderbookData, volumeProfileData, orderFlowData) {
    const htf = timeframes[timeframes.length - 1], ltf = timeframes[0];
    const price = parseFloat(klineData[ltf]?.latest?.c);
    if (!price) return "";

    let prompt = `SNAPSHOT ${symbol}: Price ${formatPrice(price, symbolInfo)}\n\n`;
    prompt += `S/R (${htf}): Supports ${srLevels.supports.map(p => formatPrice(p, symbolInfo)).join(',') || '—'} Resistances ${srLevels.resistances.map(p => formatPrice(p, symbolInfo)).join(',') || '—'}\n\n`;
    if (orderbookData) prompt += `Orderbook: Imbalance ${orderbookData.imbalance.toFixed(1)}% BuyWalls ${orderbookData.buyWalls.map(w => `${w.size.toFixed(1)}@${formatPrice(w.price, symbolInfo)}`).join(' ') || '—'} SellWalls ${orderbookData.sellWalls.map(w => `${w.size.toFixed(1)}@${formatPrice(w.price, symbolInfo)}`).join(' ') || '—'}\n\n`;
    if (volumeProfileData) prompt += `Volume Profile (${ltf}): POC ${formatPrice(volumeProfileData.poc, symbolInfo)} VA ${formatPrice(volumeProfileData.val, symbolInfo)}–${formatPrice(volumeProfileData.vah, symbolInfo)} ${price >= volumeProfileData.val && price <= volumeProfileData.vah ? 'IN' : 'OUT'}\n\n`;
    if (orderFlowData) prompt += `Order Flow: Delta ${orderFlowData.deltaPct > 0 ? '+' : ''}${orderFlowData.deltaPct.toFixed(1)}% CVD ${orderFlowData.cvd > 0 ? '+' : ''}${orderFlowData.cvd}${orderFlowData.divergence ? ` Divergence ${orderFlowData.divergence.toUpperCase()}` : ''}\n\n`;

    for (const [tf, { candles }] of Object.entries(klineData)) {
      if (!candles || candles.length < 50) continue;
      const ind = calculateIndicators(candles, symbol, tf);
      prompt += `${tf}: SMA ${formatPrice(ind.sma, symbolInfo)} RSI ${ind.rsi?.toFixed(1) || '—'} ATR ${formatPrice(ind.atr, symbolInfo)} AvgATR ${formatPrice(ind.avgAtr, symbolInfo)} MACD ${ind.macd?.toFixed(2) || '—'} Hist ${ind.macdHist?.toFixed(2) || '—'} Signal ${ind.macdSignal?.toFixed(2) || '—'}\n`;
    }
    prompt += `\nOutput JSON: {"signal":"BUY|SELL|HOLD","confidence":0-100,"entry":123.45,"tp":124.56,"sl":122.34,"reason":{"bias":"...","entry_trigger":"...","sl_rationale":"...","tp_rationale":"..."}}`;
    return prompt.trim();
  }

  async callGemini(prompt) {
    for (let attempt = 1; attempt <= CONFIG.API_RETRY_ATTEMPTS; attempt++) {
      try {
        const result = await this.model.generateContent(prompt);
        const response = await result.response;
        if (!response.candidates?.[0]?.content?.parts?.[0]?.text) throw new Error("No text in Gemini response");
        return response.text().trim();
      } catch (e) {
        if (attempt === CONFIG.API_RETRY_ATTEMPTS) {
          console.error(C.red("Gemini API Error:") + ` ${e.message}`);
          await logToFile(`Gemini API Error: ${e.message}`);
          throw e;
        }
        await new Promise(resolve => setTimeout(resolve, CONFIG.API_RETRY_DELAY * attempt));
      }
    }
  }

  parseSignal(raw) {
    try {
      const jsonString = (raw.match(/```json\s*([\s\S]*?)\s*```/) || [null, raw])[1]?.trim() || raw.trim();
      const signal = JSON.parse(jsonString);
      const reason = signal.reason || {};
      return {
        signal: ["BUY", "SELL", "HOLD"].includes(signal.signal?.toUpperCase()) ? signal.signal.toUpperCase() : "HOLD",
        confidence: Math.min(100, Math.max(0, parseInt(signal.confidence) || 0)),
        entry: typeof signal.entry === 'number' ? signal.entry : null,
        tp: typeof signal.tp === 'number' ? signal.tp : null,
        sl: typeof signal.sl === 'number' ? signal.sl : null,
        reason: {
          bias: reason.bias || "N/A",
          entry_trigger: reason.entry_trigger || "N/A",
          sl_rationale: reason.sl_rationale || "N/A",
          tp_rationale: reason.tp_rationale || "N/A",
        },
      };
    } catch (e) {
      console.error(C.red("Failed to parse Gemini signal:") + ` ${e.message}`);
      await logToFile(`Failed to parse Gemini signal: ${e.message}`);
      return { signal: "HOLD", confidence: 0, reason: { bias: "Response parsing error" } };
    }
  }

  async analyze(symbol, klineData, symbolInfo, timeframes, obData, vpData, ofData) {
    if (!klineData || Object.keys(klineData).length === 0) return null;
    const htf = timeframes[timeframes.length - 1];
    const srLevels = calculateSRLevels(klineData[htf]?.candles || [], CONFIG.SR_LOOKBACK);
    const prompt = this.makePrompt(symbol, klineData, symbolInfo, timeframes, srLevels, obData, vpData, ofData);
    if (!prompt) return null;

    const rawResponse = await this.callGemini(prompt).catch(() => null);
    return rawResponse ? this.parseSignal(rawResponse) : null;
  }
}

// --- LIVE / PAPER BOT ---
class TradingBot {
  constructor(symbols, timeframes, geminiKey, phoneNumber, mode = 'live', riskPercent = CONFIG.DEFAULT_RISK_PERCENT, leverage = CONFIG.DEFAULT_LEVERAGE, paperEquity = CONFIG.PAPER_INITIAL_EQUITY) {
    this.symbols = symbols;
    this.timeframes = timeframes.sort((a, b) => parseInt(a) - parseInt(b));
    this.triggerTf = this.timeframes[0];
    this.analysisCore = new AnalysisCore(geminiKey);
    this.phoneNumber = phoneNumber;
    this.mode = mode.toLowerCase();
    this.riskPercent = riskPercent;
    this.leverage = leverage;
    this.paperEquity = paperEquity;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.pingTimer = null;
    if (this.mode === 'paper') {
      CONFIG.PAPER_INITIAL_EQUITY = paperEquity;
      loadPaperState();
    }
  }

  connect() {
    console.log(C.info(`\n📡 Connecting to Bybit WS [${this.mode.toUpperCase()}]...`));
    this.ws = new WebSocket(CONFIG.WS_URL);
    this.ws.on('open', () => {
      console.log(C.buy("✅ Connected."));
      this.reconnectAttempts = 0;
      this.subscribe();
      this.ping();
      logToFile("WebSocket connected.");
    });
    this.ws.on('message', d => this.onMessage(d));
    this.ws.on('close', () => this.reconnectWS());
    this.ws.on('error', e => {
      console.error(C.red("WS Error:") + ` ${e.message}`);
      logToFile(`WebSocket error: ${e.message}`);
    });
  }

  subscribe() {
    const args = [];
    for (const symbol of this.symbols) {
      if (!state.klineBuffer.has(symbol)) state.klineBuffer.set(symbol, new Map());
      if (!state.orderbook.has(symbol)) state.orderbook.set(symbol, { bids: [], asks: [], ts: 0 });
      if (!state.ticker.has(symbol)) state.ticker.set(symbol, {});
      if (!state.tradeBuffer.has(symbol)) state.tradeBuffer.set(symbol, []);
      if (!state.lastSmsAlert.has(symbol)) state.lastSmsAlert.set(symbol, 0);

      this.timeframes.forEach(tf => {
        args.push(`kline.${tf}.${symbol}`);
        if (!state.klineBuffer.get(symbol).has(tf)) state.klineBuffer.get(symbol).set(tf, []);
        state.lastCandle.set(`${symbol}${tf}`, 0);
      });
      args.push(`orderbook.${CONFIG.ORDERBOOK_DEPTH}.${symbol}`, `tickers.${symbol}`, `trade.${symbol}`);
    }
    this.ws.send(JSON.stringify({ op: "subscribe", args }));
    console.log(C.buy(`📊 Subscribed: ${this.symbols.join(', ')} on ${this.timeframes.join(', ')}`));
    logToFile(`Subscribed: ${args.join(', ')}`);
  }

  ping() {
    clearInterval(this.pingTimer);
    this.pingTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send('{"op":"ping"}');
      }
    }, CONFIG.PING_INTERVAL);
  }

  reconnectWS() {
    clearInterval(this.pingTimer);
    if (this.reconnectAttempts < CONFIG.MAX_RECONNECT_ATTEMPTS) {
      this.reconnectAttempts++;
      const delay = CONFIG.RECONNECT_DELAY * this.reconnectAttempts;
      console.log(C.yellow(`🔄 Reconnect attempt ${this.reconnectAttempts}/${CONFIG.MAX_RECONNECT_ATTEMPTS} in ${delay / 1000}s...`));
      logToFile(`Reconnect attempt ${this.reconnectAttempts}/${CONFIG.MAX_RECONNECT_ATTEMPTS}`);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error(C.red("❌ Max reconnect attempts reached. Exiting."));
      logToFile("Max reconnect attempts reached. Exiting.");
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

    const updateLevel = (arr, updates) => {
      updates.forEach(([price, qty]) => {
        const p = parseFloat(price), q = parseFloat(qty);
        const idx = arr.findIndex(e => e.p === p);
        if (q === 0) {
          if (idx >= 0) arr.splice(idx, 1);
        } else {
          if (idx >= 0) arr[idx].q = q;
          else arr.push({ p, q });
        }
      });
      arr.sort((a, b) => (arr === ob.bids ? b.p - a.p : a.p - b.p));
    };

    if (data.type === "snapshot") {
      ob.bids = (data.b || []).map(([p, q]) => ({ p: parseFloat(p), q: parseFloat(q) }));
      ob.asks = (data.a || []).map(([p, q]) => ({ p: parseFloat(p), q: parseFloat(q) }));
    } else {
      updateLevel(ob.bids, data.b || []);
      updateLevel(ob.asks, data.a || []);
    }
    ob.ts = Date.now();
  }

  formatOrderbook(symbol) {
    const ob = state.orderbook.get(symbol);
    if (!ob || ob.bids.length === 0 || ob.asks.length === 0) return null;

    const bids = ob.bids.slice(0, CONFIG.ORDERBOOK_DEPTH);
    const asks = ob.asks.slice(0, CONFIG.ORDERBOOK_DEPTH);
    const bidVol = bids.reduce((s, b) => s + b.q, 0);
    const askVol = asks.reduce((s, a) => s + a.q, 0);
    const totalVol = bidVol + askVol;
    const imbalance = totalVol > 0 ? ((bidVol - askVol) / totalVol) * 100 : 0;
    const avgBid = bidVol / bids.length, avgAsk = askVol / asks.length;
    const buyWalls = bids.filter(b => b.q > avgBid * 3.5).map(b => ({ price: b.p, size: b.q })).slice(0, 2);
    const sellWalls = asks.filter(a => a.q > avgAsk * 3.5).map(a => ({ price: a.p, size: a.q })).slice(0, 2);

    return { imbalance, buyWalls, sellWalls };
  }

  onTicker(msg) {
    const symbol = msg.topic.split('.').pop();
    state.ticker.set(symbol, { price: parseFloat(msg.data.markPrice), change24h: parseFloat(msg.data.price24hPcnt) * 100 });
  }

  onTrade(msg) {
    const symbol = msg.topic.split('.').pop();
    const buffer = state.tradeBuffer.get(symbol);
    if (!buffer) return;

    msg.data.forEach(trade => {
      buffer.push({
        ts: Date.now(),
        price: parseFloat(trade.price),
        size: parseFloat(trade.size),
        side: trade.isBuyerMaker ? 'sell' : 'buy',
      });
    });

    if (buffer.length > 500) buffer.splice(0, buffer.length - 500);
  }

  async onKline(msg) {
    const [_, tf, symbol] = msg.topic.split('.');
    const k = msg.data[0];
    if (!k || !k.confirm) return;

    const candle = { t: parseInt(k.start), o: k.open, h: k.high, l: k.low, c: k.close, v: k.volume };
    const buf = state.klineBuffer.get(symbol)?.get(tf);
    if (!buf) return;
    const key = `${symbol}${tf}`;
    const last = state.lastCandle.get(key) || 0;

    if (candle.t > last) {
      if (buf.length >= CONFIG.MAX_BUFFER) buf.shift();
      buf.push(candle);
      state.lastCandle.set(key, candle.t);

      const klineData = { triggerTf: tf };
      this.timeframes.forEach(t => {
        const b = state.klineBuffer.get(symbol)?.get(t);
        if (b && b.length > 0) klineData[t] = { candles: b, latest: b[b.length - 1] };
      });
      const symbolInfo = await getSymbolInfo(symbol).catch(() => null);
      const obData = this.formatOrderbook(symbol);
      if (symbolInfo && klineData[this.triggerTf]) {
        this.printLiveDashboard(symbol, klineData, symbolInfo, obData);
      }

      // Paper Trading: Check SL/TP
      if (this.mode === 'paper' && state.paper.position?.symbol === symbol) {
        const pos = state.paper.position;
        const price = parseFloat(candle.c);
        const h = parseFloat(candle.h), l = parseFloat(candle.l);

        if (pos.type === 'BUY') {
          if (l <= pos.sl) await closePaperTrade(pos.sl, 'loss', symbolInfo);
          else if (h >= pos.tp) await closePaperTrade(pos.tp, 'win', symbolInfo);
        } else {
          if (h >= pos.sl) await closePaperTrade(pos.sl, 'loss', symbolInfo);
          else if (l <= pos.tp) await closePaperTrade(pos.tp, 'win', symbolInfo);
        }
      }

      if (tf === this.triggerTf && !state.pending.has(symbol)) {
        const ready = this.timeframes.every(t => state.klineBuffer.get(symbol)?.get(t)?.length >= 50);
        if (ready) {
          state.pending.add(symbol);
          setTimeout(async () => {
            try {
              const fullData = {};
              this.timeframes.forEach(t => {
                const b = state.klineBuffer.get(symbol)?.get(t);
                if (b && b.length >= 50) fullData[t] = { candles: b, latest: b[b.length - 1] };
              });
              if (Object.keys(fullData).length < this.timeframes.length) return;
              const vpData = calculateVolumeProfile(fullData[this.triggerTf].candles, CONFIG.VP_LOOKBACK);
              const ofData = calculateOrderFlow(fullData[this.triggerTf].candles, state.tradeBuffer.get(symbol));
              const signal = await this.analysisCore.analyze(symbol, fullData, symbolInfo, this.timeframes, obData, vpData, ofData);
              if (signal && signal.signal !== 'HOLD' && !state.paper.position) {
                this.printSignal(symbol, parseFloat(candle.c), signal, symbolInfo);
                if (this.mode === 'paper') {
                  await openPaperTrade(symbol, signal.signal, signal.entry, signal.sl, signal.tp, symbolInfo, this.riskPercent, this.leverage);
                }
                this.alertSignal(symbol, signal, symbolInfo);
              }
            } catch (e) {
              console.error(C.red("Analysis failed:") + ` ${e.message}`);
              await logToFile(`Analysis failed: ${e.message}`);
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
    const latest = klineData[tf]?.latest;
    if (!latest || !symbolInfo) return;

    const price = parseFloat(latest.c);
    const ind = calculateIndicators(klineData[tf].candles, symbol, tf);
    const htf = this.timeframes[this.timeframes.length - 1];
    const sr = calculateSRLevels(klineData[htf]?.candles || [], CONFIG.SR_LOOKBACK);
    const vp = calculateVolumeProfile(klineData[tf].candles, CONFIG.VP_LOOKBACK);
    const of = calculateOrderFlow(klineData[tf].candles, state.tradeBuffer.get(symbol)) || {};
    const htfInd = calculateIndicators(klineData[htf]?.candles || [], symbol, htf);

    const isBullish = htfInd.close > htfInd.sma && htfInd.rsi > 50 && of.cvd > 0;
    const isBearish = htfInd.close < htfInd.sma && htfInd.rsi < 50 && of.cvd < 0;
    const trend = isBullish ? C.buy('📈 Bullish') : isBearish ? C.sell('📉 Bearish') : C.hold('↔ Sideways');

    console.log(C.title(`\n📊 ${symbol} [${tf}] | HTF: ${trend}`));
    console.log(C.label('Price: ') + C.price(`$${formatPrice(price, symbolInfo)}`) +
                C.label(' | SMA: ') + `${formatPrice(ind.sma, symbolInfo)}` +
                C.label(' | RSI: ') + `${ind.rsi?.toFixed(1) || 'N/A'}` +
                C.label(' | Vol: ') + `${ind.volume.toFixed(0)}`);
    console.log(C.label('MACD: ') + `${ind.macd?.toFixed(2) || 'N/A'}` +
                C.label(' | Hist: ') + `${ind.macdHist?.toFixed(2) || 'N/A'}` +
                C.label(' | Signal: ') + `${ind.macdSignal?.toFixed(2) || 'N/A'}` +
                C.label(' | ATR: ') + `${formatPrice(ind.atr, symbolInfo)}`);
    if (vp) console.log(C.label('VP: ') + `POC $${formatPrice(vp.poc, symbolInfo)} | VA $${formatPrice(vp.val, symbolInfo)}–$${formatPrice(vp.vah, symbolInfo)}`);
    if (of.deltaPct !== undefined) {
      const deltaColor = of.deltaPct > 0 ? C.buy : C.sell;
      console.log(C.label('OF: ') + deltaColor(`Δ ${of.deltaPct > 0 ? '+' : ''}${of.deltaPct.toFixed(1)}%`) +
                  C.label(' | CVD: ') + `${of.cvd > 0 ? '+' : ''}${of.cvd.toFixed(0)}` +
                  (of.divergence ? C.alert(` | DIV ${of.divergence.toUpperCase()}`) : ''));
    }
    console.log(C.label('S/R: ') + C.gray(`S ${sr.supports.map(p => formatPrice(p, symbolInfo)).join(', ') || '—'} | R ${sr.resistances.map(p => formatPrice(p, symbolInfo)).join(', ') || '—'}`));
    const next = Math.ceil((parseInt(latest.t) + getIntervalMs(tf)) / 1000 - Date.now() / 1000);
    console.log(C.gray(`Next candle in ${next}s`));

    // Paper Position Display
    if (this.mode === 'paper' && state.paper.position?.symbol === symbol) {
      const pos = state.paper.position;
      const unrealized = (pos.type === 'BUY' ? (price - pos.entry) : (pos.entry - price)) * pos.size;
      const unrealizedPct = (unrealized / (pos.entry * pos.size)) * 100;
      const color = unrealized >= 0 ? C.green : C.red;
      console.log(color(`📊 PAPER POSITION: ${pos.type} @ ${formatPrice(pos.entry, symbolInfo)} | SL: ${formatPrice(pos.sl, symbolInfo)} | TP: ${formatPrice(pos.tp, symbolInfo)}`));
      console.log(color(`  Unrealized: ${unrealizedPct > 0 ? '+' : ''}${unrealizedPct.toFixed(2)}% ($${unrealized.toFixed(2)})`));
      console.log(C.info(`  Equity: $${state.paper.equity.toFixed(2)}`));
    }

    console.log(C.info('═'.repeat(50)));
  }

  printSignal(symbol, price, signal, symbolInfo) {
    const color = signal.signal === "BUY" ? C.buy : signal.signal === "SELL" ? C.sell : C.hold;
    const confColor = signal.confidence >= CONFIG.MIN_CONFIDENCE_TO_ALERT ? C.alert : C.conf;

    console.log(C.title(`\n📣 SCALP SIGNAL: ${symbol}`));
    console.log('┌' + '─'.repeat(48) + '┐');
    console.log(`│ ${C.label('Price:')} ${C.price(`$${formatPrice(price, symbolInfo)}`)} ${color(`| ${signal.signal}`)} ${confColor(`| Conf: ${signal.confidence}%`)} │`);
    if (signal.signal !== 'HOLD' && signal.entry && signal.tp && signal.sl) {
      const rr = Math.abs(signal.tp - signal.entry) / Math.abs(signal.entry - signal.sl);
      console.log(`│ ${C.label('Entry:')} ${C.entry(`$${formatPrice(signal.entry, symbolInfo)}`)} ${C.label('| TP:')} ${C.tp(`$${formatPrice(signal.tp, symbolInfo)}`)} ${C.label('| SL:')} ${C.sl(`$${formatPrice(signal.sl, symbolInfo)}`)} ${C.info(`| R:R ${rr.toFixed(2)}`)} │`);
      console.log('├' + '─'.repeat(48) + '┤');
      console.log(`│ ${C.label('Bias:')}    ${C.reason(signal.reason.bias.slice(0, 40))} │`);
      console.log(`│ ${C.label('Trigger:')} ${C.reason(signal.reason.entry_trigger.slice(0, 40))} │`);
      console.log(`│ ${C.label('SL:')}      ${C.reason(signal.reason.sl_rationale.slice(0, 40))} │`);
      console.log(`│ ${C.label('TP:')}      ${C.reason(signal.reason.tp_rationale.slice(0, 40))} │`);
    } else {
      console.log(`│ ${C.reason(signal.reason.bias)} │`);
    }
    console.log('└' + '─'.repeat(48) + '┘');
    logToFile(`Signal generated: ${JSON.stringify(signal)}`);
  }

  alertSignal(symbol, signal, symbolInfo) {
    if (signal.signal === "HOLD" || signal.confidence < CONFIG.MIN_CONFIDENCE_TO_ALERT) return;
    const lastAlert = state.lastSmsAlert.get(symbol) || 0;
    if (Date.now() - lastAlert < 15 * 60 * 1000) return;
    const msg = `${symbol} ${signal.signal} | Conf: ${signal.confidence}% | E: ${formatPrice(signal.entry, symbolInfo)} | TP: ${formatPrice(signal.tp, symbolInfo)} | SL: ${formatPrice(signal.sl, symbolInfo)}`;
    sendSmsAlert(this.phoneNumber, msg);
    state.lastSmsAlert.set(symbol, Date.now());
  }
}

// --- BACKTESTING ENGINE ---
class Backtester {
  constructor(symbol, timeframes, days, geminiKey, riskPercent = CONFIG.DEFAULT_RISK_PERCENT, leverage = CONFIG.DEFAULT_LEVERAGE) {
    this.symbol = symbol;
    this.timeframes = timeframes.sort((a, b) => parseInt(a) - parseInt(b));
    this.triggerTf = this.timeframes[0];
    this.days = days;
    this.analysisCore = new AnalysisCore(geminiKey);
    this.riskPercent = riskPercent;
    this.leverage = leverage;
    this.equity = CONFIG.BACKTEST_INITIAL_EQUITY;
    this.peakEquity = CONFIG.BACKTEST_INITIAL_EQUITY;
    this.maxDrawdown = 0;
    this.trades = [];
    this.returns = [];
    this.historicalData = {};
  }

  async fetchHistoricalData(interval) {
    const limit = 1000;
    let candles = [];
    let endTime = Date.now();
    console.log(C.yellow(`📥 Fetching ${this.days}d of ${interval} for ${this.symbol}...`));

    while (endTime > Date.now() - this.days * 86400000) {
      const startTime = endTime - limit * getIntervalMs(interval);
      const url = `${CONFIG.API_URL}/v5/market/kline?category=linear&symbol=${this.symbol}&interval=${interval}&start=${startTime}&end=${endTime}&limit=${limit}`;
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.retCode !== 0) throw new Error(data.retMsg || "Invalid data");

        const klines = data.result.list.map(k => ({
          t: parseInt(k[0]), o: parseFloat(k[1]), h: parseFloat(k[2]), l: parseFloat(k[3]), c: parseFloat(k[4]), v: parseFloat(k[5])
        })).reverse();
        candles = [...klines, ...candles];
        if (klines.length < limit) break;
        endTime = klines[0].t - 1;
        process.stdout.write(C.gray(`\rFetched ${candles.length} ${interval} candles...`));
        await new Promise(r => setTimeout(r, 600));
      } catch (e) {
        console.error(C.red(`Error fetching ${interval} data: ${e.message}`));
        await logToFile(`Error fetching ${interval} data: ${e.message}`);
        break;
      }
    }
    console.log(C.buy(`\n✅ Fetched ${candles.length} ${interval} candles.`));
    return candles;
  }

  async prepareData() {
    await fs.mkdir(CONFIG.HISTORICAL_DATA_DIR, { recursive: true });
    const file = path.join(CONFIG.HISTORICAL_DATA_DIR, `${this.symbol}_${this.days}d.json`);
    try {
      this.historicalData = JSON.parse(await fs.readFile(file, 'utf-8'));
      console.log(C.buy(`📂 Loaded backtest data from ${file}`));
      await logToFile(`Loaded backtest data from ${file}`);
    } catch (e) {
      console.log(C.yellow(`📂 Fetching new data for ${this.symbol}...`));
      for (const tf of this.timeframes) {
        this.historicalData[tf] = await this.fetchHistoricalData(tf);
      }
      await fs.writeFile(file, JSON.stringify(this.historicalData, null, 2));
      console.log(C.buy(`📂 Saved backtest data to ${file}`));
      await logToFile(`Saved backtest data to ${file}`);
    }
  }

  async run() {
    await this.prepareData();
    const symbolInfo = await getSymbolInfo(this.symbol);
    const primaryData = this.historicalData[this.triggerTf];
    if (!primaryData || primaryData.length < CONFIG.MAX_BUFFER) {
      console.error(C.red(`❌ Insufficient data for ${this.triggerTf}: ${primaryData?.length || 0} candles`));
      await logToFile(`Insufficient data for ${this.triggerTf}: ${primaryData?.length || 0} candles`);
      return;
    }

    const buffers = new Map(this.timeframes.map(tf => [tf, []]));
    let currentTrade = null;

    for (let i = 0; i < primaryData.length; i++) {
      const candle = primaryData[i];
      this.timeframes.forEach(tf => {
        const tfData = this.historicalData[tf];
        const c = tfData.find(k => k.t === candle.t);
        if (c) {
          const buf = buffers.get(tf);
          if (buf.length >= CONFIG.MAX_BUFFER) buf.shift();
          buf.push(c);
        }
      });

      const ready = this.timeframes.every(tf => buffers.get(tf).length >= 50);
      if (!ready) continue;

      const klineData = {};
      this.timeframes.forEach(tf => {
        const b = buffers.get(tf);
        klineData[tf] = { candles: b, latest: b[b.length - 1] };
      });

      process.stdout.write(C.gray(`\r📈 Simulating ${new Date(candle.t).toLocaleString()} | Equity: $${this.equity.toFixed(2)} | Trades: ${this.trades.length}`));

      if (currentTrade) {
        const { type, entry, sl, tp, size, timestamp } = currentTrade;
        let exitPrice = null, result = null;

        if (type === 'BUY') {
          if (candle.l <= sl) { exitPrice = sl; result = 'loss'; }
          else if (candle.h >= tp) { exitPrice = tp; result = 'win'; }
        } else {
          if (candle.h >= sl) { exitPrice = sl; result = 'loss'; }
          else if (candle.l <= tp) { exitPrice = tp; result = 'win'; }
        }

        if (exitPrice) {
          const slippage = exitPrice * CONFIG.SLIPPAGE_PERCENT * (type === 'BUY' ? -1 : 1);
          const finalExit = exitPrice + slippage;
          const entryFee = entry * CONFIG.FEE_RATE;
          const exitFee = finalExit * CONFIG.FEE_RATE;
          const pnl = (type === 'BUY' ? (finalExit - entry) : (entry - finalExit)) * size - entryFee - exitFee;
          const pnlPercent = (pnl / (entry * size)) * 100;
          const duration = (candle.t - timestamp) / 60000;

          this.equity += pnl;
          this.peakEquity = Math.max(this.peakEquity, this.equity);
          this.maxDrawdown = Math.max(this.maxDrawdown, ((this.peakEquity - this.equity) / this.peakEquity) * 100);
          this.trades.push({ ...currentTrade, exitPrice: finalExit, result, pnl, pnlPercent, duration, closeTime: candle.t });
          this.returns.push(pnlPercent);
          currentTrade = null;
          await logToFile(`Backtest trade closed: ${type} ${this.symbol}, PnL: ${pnlPercent.toFixed(2)}%`);
        }
      }

      if (!currentTrade) {
        const signal = await this.analysisCore.analyze(this.symbol, klineData, symbolInfo, this.timeframes, null, null, null);
        if (signal && signal.signal !== 'HOLD' && signal.entry && signal.tp && signal.sl) {
          const rr = Math.abs(signal.tp - signal.entry) / Math.abs(signal.entry - signal.sl);
          if (rr >= 1.5) {
            const size = (this.equity * this.riskPercent * this.leverage) / Math.abs(signal.entry - signal.sl);
            currentTrade = {
              type: signal.signal,
              entry: signal.entry,
              sl: signal.sl,
              tp: signal.tp,
              size,
              timestamp: candle.t,
              confidence: signal.confidence,
              reason: signal.reason,
            };
            await logToFile(`Backtest trade opened: ${JSON.stringify(currentTrade)}`);
          }
        }
      }
    }

    await this.saveTradesToCsv();
    this.printResults(symbolInfo);
  }

  async saveTradesToCsv() {
    const csv = ['timestamp,type,entry,exit,sl,tp,size,pnl,pnlPercent,duration,confidence'];
    this.trades.forEach(t => {
      csv.push(`${new Date(t.timestamp).toISOString()},${t.type},${t.entry},${t.exitPrice || ''},${t.sl},${t.tp},${t.size.toFixed(2)},${t.pnl?.toFixed(2) || ''},${t.pnlPercent?.toFixed(2) || ''},${t.duration?.toFixed(1) || ''},${t.confidence}`);
    });
    await fs.writeFile(path.join(CONFIG.HISTORICAL_DATA_DIR, `${this.symbol}_trades.csv`), csv.join('\n'));
    console.log(C.buy(`📂 Saved backtest trades to ${this.symbol}_trades.csv`));
    await logToFile(`Saved backtest trades to ${this.symbol}_trades.csv`);
  }

  printResults(symbolInfo) {
    console.log(C.title(`\n📊 BACKTEST RESULTS: ${this.symbol} (${this.days}d)`));
    if (this.trades.length === 0) {
      console.log(C.yellow("⚠ No trades executed."));
      return;
    }

    const wins = this.trades.filter(t => t.result === 'win').length;
    const winRate = (wins / this.trades.length * 100).toFixed(2);
    const totalReturn = ((this.equity - CONFIG.BACKTEST_INITIAL_EQUITY) / CONFIG.BACKTEST_INITIAL_EQUITY * 100).toFixed(2);
    const avgReturn = this.returns.reduce((a, b) => a + b, 0) / this.returns.length;
    const variance = this.returns.map(r => Math.pow(r - avgReturn, 2)).reduce((a, b) => a + b, 0) / this.returns.length;
    const sharpe = variance > 0 ? (avgReturn / Math.sqrt(variance)) * Math.sqrt(252) : 0;
    const avgDuration = this.trades.reduce((a, t) => a + (t.duration || 0), 0) / this.trades.length;
    const expectancy = (winRate / 100 * avgReturn) - ((1 - winRate / 100) * Math.abs(avgReturn));

    console.log(C.info(`Trades: ${this.trades.length} | Wins: ${wins} (${winRate}%)`));
    console.log(C.info(`Total Return: ${totalReturn > 0 ? '+' : ''}${totalReturn}% | Equity: $${this.equity.toFixed(2)}`));
    console.log(C.info(`Max Drawdown: ${this.maxDrawdown.toFixed(2)}% | Sharpe: ${sharpe.toFixed(2)}`));
    console.log(C.info(`Avg Trade Duration: ${avgDuration.toFixed(1)} min | Expectancy: ${expectancy.toFixed(2)}%`));
    console.log(C.info('═'.repeat(50)));
  }
}

// --- CLI ---
async function main() {
  const args = {};
  process.argv.slice(2).forEach((v, i, a) => {
    if (v.startsWith('--')) args[v.slice(2)] = a[i + 1] && !a[i + 1].startsWith('--') ? a[i + 1] : true;
  });

  console.log(C.title(`\n🚀 Definitive Gemini Scalping Engine [${new Date().toLocaleString('en-US', { timeZone: 'CET' })}]`));

  const symbol = (args.symbol || await promptUser('Symbol (e.g., BTCUSDT): ')).toUpperCase();
  const timeframes = (args.timeframes || await promptUser('Timeframes (e.g., 1,5,15): ')).split(',').map(t => t.trim()).sort((a, b) => parseInt(a) - parseInt(b));
  const mode = (args.mode || 'live').toLowerCase();
  const geminiKey = args['gemini-key'] || CONFIG.GEMINI_API_KEY;
  const phone = args['phone-number'] || CONFIG.ALERT_PHONE_NUMBER;
  const riskPercent = parseFloat(args['risk-percent'] || CONFIG.DEFAULT_RISK_PERCENT);
  const leverage = parseFloat(args['leverage'] || CONFIG.DEFAULT_LEVERAGE);
  const paperEquity = parseFloat(args['paper-equity'] || CONFIG.PAPER_INITIAL_EQUITY);

  if (!geminiKey) {
    console.error(C.red("❌ GEMINI_API_KEY required"));
    await logToFile("GEMINI_API_KEY missing");
    process.exit(1);
  }

  rl.close();

  console.log(C.info(`Mode: ${mode.toUpperCase()} | Symbol: ${symbol} | TFs: ${timeframes.join(', ')} | Risk: ${(riskPercent * 100).toFixed(1)}% | Lev: ${leverage}x`));
  await getSymbolInfo(symbol);
  if (!phone && mode !== 'backtest') console.log(C.red("📩 SMS Alerts: DISABLED"));

  if (mode === 'live' || mode === 'paper') {
    new TradingBot([symbol], timeframes, geminiKey, phone, mode, riskPercent, leverage, paperEquity).connect();
  } else if (mode === 'backtest') {
    const days = parseInt(args.days || CONFIG.BACKTEST_DAYS);
    new Backtester(symbol, timeframes, days, geminiKey, riskPercent, leverage).run();
  } else {
    console.error(C.red(`❌ Invalid mode: ${mode}. Use 'live', 'paper', or 'backtest'.`));
    await logToFile(`Invalid mode: ${mode}`);
    process.exit(1);
  }

  process.on('SIGINT', async () => {
    console.log(C.title("\n🛑 Shutting down..."));
    if (mode === 'paper') await savePaperState();
    await logToFile("Bot shutdown.");
    process.exit(0);
  });
}

main().catch(async e => {
  console.error(C.red("FATAL:") + ` ${e.message}`);
  await logToFile(`FATAL: ${e.message}`);
  process.exit(1);
});
