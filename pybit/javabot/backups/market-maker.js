// market-maker.js (v3.7.0) - Production-Grade Market Maker
const axios = require('axios');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { createLogger, format, transports } = require('winston');
const chalk = require('chalk');
const createCsvWriter = require('csv-writer').createObjectCsvWriter;
const { exec } = require('child_process');
require('dotenv').config();

// ====================== 
// NEON THEME
// ====================== 
const neon = {
  info: chalk.hex('#00FFFF').bold,
  success: chalk.hex('#00FF00').bold,
  warn: chalk.hex('#FFAA00').bold,
  error: chalk.hex('#FF0000').bold,
  price: chalk.hex('#00FFAA').bold,
  pnl: (val) => (val >= 0 ? chalk.hex('#00FF00').bold : chalk.hex('#FF0000').bold)(val.toFixed(6)),
  bid: chalk.hex('#00AAFF').bold,
  ask: chalk.hex('#FF55FF').bold,
  header: chalk.hex('#FFFFFF').bgHex('#001122').bold,
  dim: chalk.dim,
};

// ====================== 
// CONFIGURATION
// ====================== 
const REQUIRED_ENV_VARS = ['BYBIT_API_KEY', 'BYBIT_SECRET', 'SYMBOL', 'TESTNET', 'DRY_RUN'];
const missing = REQUIRED_ENV_VARS.filter(key => !process.env[key]);
if (missing.length > 0) {
  console.error('❌ FATAL: Missing required environment variables:');
  missing.forEach(key => console.error(`   - ${key}`));
  process.exit(1);
}

const API_KEY = process.env.BYBIT_API_KEY;
const SECRET = process.env.BYBIT_SECRET;
const SYMBOL = process.env.SYMBOL;
const IS_TESTNET = process.env.TESTNET === 'true';
const DRY_RUN = process.env.DRY_RUN === 'true';

const BID_SPREAD_BASE = parseFloat(process.env.BID_SPREAD_BASE) || 0.00025;
const ASK_SPREAD_BASE = parseFloat(process.env.ASK_SPREAD_BASE) || 0.00025;
const SPREAD_MULTIPLIER = parseFloat(process.env.SPREAD_MULTIPLIER) || 1.5;
const MAX_ORDERS_PER_SIDE = parseInt(process.env.MAX_ORDERS_PER_SIDE) || 3;
const MIN_ORDER_SIZE = parseFloat(process.env.MIN_ORDER_SIZE) || 0.0001;
const ORDER_SIZE_FIXED = process.env.ORDER_SIZE_FIXED === 'true';
const VOLATILITY_WINDOW = parseInt(process.env.VOLATILITY_WINDOW) || 20;
const VOLATILITY_FACTOR = parseFloat(process.env.VOLATILITY_FACTOR) || 2.0;
const REFRESH_INTERVAL = parseInt(process.env.REFRESH_INTERVAL) || 5000;
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 30000;
const RETRY_DELAY_BASE = parseInt(process.env.RETRY_DELAY_BASE) || 1000;
const MAX_NET_POSITION = parseFloat(process.env.MAX_NET_POSITION) || 0.01;
const STOP_ON_LARGE_POS = process.env.STOP_ON_LARGE_POS === 'true';
const LOG_TO_FILE = process.env.LOG_TO_FILE === 'true';
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';
const PNL_CSV_PATH = process.env.PNL_CSV_PATH || './logs/pnl.csv';
const USE_TERMUX_SMS = process.env.USE_TERMUX_SMS === 'true';
const SMS_PHONE_NUMBER = process.env.SMS_PHONE_NUMBER || '';
const POSITION_SKEW_FACTOR = parseFloat(process.env.POSITION_SKEW_FACTOR) || 0.15;
const VOLATILITY_SPREAD_FACTOR = parseFloat(process.env.VOLATILITY_SPREAD_FACTOR) || 0.75;
const STATE_FILE_PATH = process.env.STATE_FILE_PATH || './logs/state.json';
const FILL_PROBABILITY = parseFloat(process.env.FILL_PROBABILITY) || 0.15;
const SLIPPAGE_FACTOR = parseFloat(process.env.SLIPPAGE_FACTOR) || 0.0001;
const GRID_SPACING_BASE = parseFloat(process.env.GRID_SPACING_BASE) || 0.00015;
const IMBALANCE_SPREAD_FACTOR = parseFloat(process.env.IMBALANCE_SPREAD_FACTOR) || 0.2;
const IMBALANCE_ORDER_SIZE_FACTOR = parseFloat(process.env.IMBALANCE_ORDER_SIZE_FACTOR) || 0.5;

const BASE_URL = IS_TESTNET ? 'https://api-testnet.bybit.com' : 'https://api.bybit.com';

// ====================== 
// GLOBAL STATE
// ====================== 
const botState = {
  lastPrice: null,
  priceHistory: [],
  netPosition: 0,
  averageEntryPrice: 0,
  activeOrders: new Set(),
  retryCount: 0,
  lastRefresh: Date.now(),
  isPaused: false,
  hasValidCredentials: !!API_KEY && !!SECRET,
  isShuttingDown: false,
  wsReconnectAttempts: 0,
  maxWsReconnect: 10,
  realizedPnL: 0,
  unrealizedPnL: 0,
  totalPnL: 0,
  tradeCount: 0,
  lastSmsAt: 0,
  lastSmsDigest: '',
};

// ====================== 
// LOGGER
// ====================== 
const logDir = './logs';
if (!fs.existsSync(logDir)) fs.mkdirSync(logDir);
const logger = createLogger({
  level: LOG_LEVEL,
  format: format.combine(format.timestamp(), format.errors({ stack: true }), format.json()),
  transports: [
    new transports.Console({ format: format.simple() }),
    ...(LOG_TO_FILE ? [new transports.File({ filename: path.join(logDir, 'bot.log') })] : [])
  ],
  exceptionHandlers: [new transports.File({ filename: path.join(logDir, 'exceptions.log') })],
});

const log = (level, message, metadata = {}) => {
  const logEntry = { level, message, timestamp: new Date().toISOString(), ...metadata };
  logger.log(level, JSON.stringify(logEntry));
};

// ====================== 
// CSV PNL WRITER
// ====================== 
const pnlCsvWriter = createCsvWriter({
  path: PNL_CSV_PATH,
  header: [
    { id: 'timestamp', title: 'Timestamp' },
    { id: 'event', title: 'Event' },
    { id: 'price', title: 'Price' },
    { id: 'qty', title: 'Qty' },
    { id: 'side', title: 'Side' },
    { id: 'realizedPnL', title: 'Realized PnL' },
    { id: 'unrealizedPnL', title: 'Unrealized PnL' },
    { id: 'totalPnL', title: 'Total PnL' },
    { id: 'netPosition', title: 'Net Position' },
  ],
  append: true,
});
if (!fs.existsSync(PNL_CSV_PATH)) {
  fs.writeFileSync(PNL_CSV_PATH, 'Timestamp,Event,Price,Qty,Side,Realized PnL,Unrealized PnL,Total PnL,Net Position\n');
}

// ====================== 
// STATE MANAGEMENT
// ====================== 
function loadState() {
  try {
    if (fs.existsSync(STATE_FILE_PATH)) {
      const json = JSON.parse(fs.readFileSync(STATE_FILE_PATH, 'utf8'));
      botState.netPosition = Number(json.netPosition) || 0;
      botState.averageEntryPrice = Number(json.averageEntryPrice) || 0;
      botState.realizedPnL = Number(json.realizedPnL) || 0;
      botState.tradeCount = Number(json.tradeCount) || 0;
      log('info', '✅ Loaded saved state', {
        netPosition: botState.netPosition,
        averageEntryPrice: botState.averageEntryPrice,
        realizedPnL: botState.realizedPnL,
        tradeCount: botState.tradeCount
      });
    }
  } catch (err) {
    log('warn', 'Failed to load state', { error: err.message });
  }
}
function saveState() {
  try {
    const data = {
      netPosition: botState.netPosition,
      averageEntryPrice: botState.averageEntryPrice,
      realizedPnL: botState.realizedPnL,
      tradeCount: botState.tradeCount,
      timestamp: new Date().toISOString(),
    };
    fs.writeFileSync(STATE_FILE_PATH, JSON.stringify(data, null, 2));
    log('info', '💾 State saved', { path: STATE_FILE_PATH });
  } catch (err) {
    log('error', 'Failed to save state', { error: err.message });
  }
}

// ====================== 
// SIGNATURE & API
// ====================== 
function generateSignature(params, secret) {
  if (!secret) throw new Error('SECRET is undefined.');
  const sortedParams = Object.keys(params)
    .sort()
    .map(key => `${key}=${params[key]}`)
    .join('&');
  return crypto.createHmac('sha256', secret).update(sortedParams).digest('hex');
}

async function bybitRequest(endpoint, method, body = {}, retries = 3) {
  if (!botState.hasValidCredentials) throw new Error('Invalid API credentials');

  const timestamp = Date.now().toString();
  const payload = { ...body, apiKey: API_KEY, timestamp, recvWindow: '5000' };
  const signature = generateSignature(payload, SECRET);

  const headers = {
    'Content-Type': 'application/json',
    'X-BAPI-API-KEY': API_KEY,
    'X-BAPI-SIGN': signature,
    'X-BAPI-TIMESTAMP': timestamp,
    'X-BAPI-RECV-WINDOW': '5000',
  };

  const url = `${BASE_URL}/v5/${endpoint}`;

  try {
    const res = await axios({
      url,
      method,
      headers,
      data: method === 'POST' ? payload : undefined,
      params: method === 'GET' ? payload : undefined,
      timeout: 7000,
      validateStatus: () => true,
    });

    if (res.status === 429 || res.data?.retCode === 10006) {
      const retryAfter = parseInt(res.headers['retry-after'] || '3', 10) * 1000;
      log('warn', `Rate limit hit. Waiting ${retryAfter}ms`, { endpoint });
      await new Promise(r => setTimeout(r, Math.max(1000, retryAfter)));
      return bybitRequest(endpoint, method, body, retries - 1);
    }

    if (!res.data || (res.data.retCode !== 0 && res.status >= 400)) {
      const msg = res.data?.retMsg || `HTTP ${res.status}`;
      if (retries > 0) {
        const delay = RETRY_DELAY_BASE * Math.pow(2, retries - 1);
        log('warn', `API error: ${msg}. Retrying in ${delay}ms (${retries - 1} left)`, { endpoint });
        await new Promise(r => setTimeout(r, delay));
        return bybitRequest(endpoint, method, body, retries - 1);
      }
      throw new Error(`API failure: ${msg}`);
    }

    botState.retryCount = 0;
    return res.data;
  } catch (err) {
    if (retries > 0) {
      const delay = RETRY_DELAY_BASE * Math.pow(2, retries - 1);
      log('warn', `Request error: ${err.message}. Retrying in ${delay}ms (${retries - 1} left)`, { endpoint });
      await new Promise(r => setTimeout(r, delay));
      return bybitRequest(endpoint, method, body, retries - 1);
    }
    throw err;
  }
}

// ====================== 
// MARKET DATA (ALWAYS LIVE)
// ====================== 
async function getOrderBook(retries = 3) {
  try {
    const res = await axios.get(`${BASE_URL}/v5/market/orderbook`, {
      params: { category: 'linear', symbol: SYMBOL, limit: 5 },
      timeout: 7000,
      validateStatus: () => true,
    });

    if (res.status !== 200) throw new Error(`HTTP ${res.status}`);
    if (res.data?.retCode !== 0) {
      if (res.data?.retMsg?.includes('rate limit')) throw new Error('Rate limit hit');
      throw new Error(res.data.retMsg || 'Bybit error');
    }
    if (!res.data?.result || typeof res.data.result !== 'object') {
      throw new Error('Invalid response structure');
    }
    const rawBids = res.data.result.b || [];
    const rawAsks = res.data.result.a || [];

    if (rawBids.length === 0 && rawAsks.length === 0) {
      log('warn', 'Received an empty order book from Bybit API.', { response: res.data });
      if (retries > 0) {
        const delay = 2000 * Math.pow(2, retries - 1);
        log('warn', 'Empty book. Retrying...', { retries: retries - 1 });
        await new Promise(r => setTimeout(r, delay));
        return getOrderBook(retries - 1);
      }
      log('warn', 'Empty book. Using fallback simulation.');
      const mid = botState.lastPrice || 70000;
      const bid = { price: mid * 0.999, size: MIN_ORDER_SIZE };
      const ask = { price: mid * 1.001, size: MIN_ORDER_SIZE };
      return {
        bids: [bid], asks: [ask],
        midPrice: mid,
        imbalance: 0,
      };
    }

    if (rawBids.length === 0 || rawAsks.length === 0) {
      log('warn', `One side empty. Simulating for continuity.`, { bids: rawBids.length, asks: rawAsks.length });
      if (rawBids.length === 0) rawBids.push([(mid * 0.999).toString(), rawAsks[0][1]]);
      if (rawAsks.length === 0) rawAsks.push([(mid * 1.001).toString(), rawBids[0][1]]);
    }

    const bids = rawBids.map(b => ({ price: parseFloat(b[0]), size: parseFloat(b[1]) }))
      .filter(b => Number.isFinite(b.price) && Number.isFinite(b.size) && b.price > 0 && b.size > 0);
    const asks = rawAsks.map(a => ({ price: parseFloat(a[0]), size: parseFloat(a[1]) }))
      .filter(a => Number.isFinite(a.price) && Number.isFinite(a.size) && a.price > 0 && a.size > 0);

    if (bids.length === 0 || asks.length === 0) {
      throw new Error('No valid bids or asks after filtering');
    }

    const midPrice = (bids[0].price + asks[0].price) / 2;
    const imbalance = (bids[0].size - asks[0].size) / Math.max(1e-9, (bids[0].size + asks[0].size));
    return { bids, asks, midPrice, imbalance };
  } catch (err) {
    if (retries > 0) {
      const delay = 2000 * Math.pow(2, retries - 1);
      log('warn', `Book fetch failed: ${err.message}. Retrying...`, { retries: retries - 1 });
      await new Promise(r => setTimeout(r, delay));
      return getOrderBook(retries - 1);
    }
    if (!Number.isFinite(botState.lastPrice)) throw err;
    log('warn', 'Using fallback book due to failure.', { error: err.message });
    const midPrice = botState.lastPrice;
    return {
      bids: [{ price: midPrice * 0.999, size: MIN_ORDER_SIZE }],
      asks: [{ price: midPrice * 1.001, size: MIN_ORDER_SIZE }],
      midPrice,
      imbalance: 0,
    };
  }
}

function getVolatility() {
  if (botState.priceHistory.length < VOLATILITY_WINDOW) return 0.001;
  const recent = botState.priceHistory.slice(-VOLATILITY_WINDOW);
  const changes = recent.map((p, i) => i > 0 ? Math.abs((p - recent[i - 1]) / recent[i - 1]) : 0);
  const avgChange = changes.reduce((a, b) => a + b, 0) / Math.max(1, changes.length - 1);
  return Math.max(0, avgChange);
}

// ====================== 
// ANALYSIS & DISPLAY
// ====================== 
function analyzeOrderBook(bids, asks) {
  const totalBidSize = bids.reduce((sum, b) => sum + b.size, 0);
  const totalAskSize = asks.reduce((sum, a) => sum + a.size, 0);
  const imbalance = (totalBidSize - totalAskSize) / Math.max(1e-9, (totalBidSize + totalAskSize));
  const depth = { bids: totalBidSize, asks: totalAskSize, ratio: totalBidSize / Math.max(1e-9, totalAskSize) };
  const bidHeat = bids.map(b => ({ ...b, heat: (b.size / Math.max(1e-9, totalBidSize)) * 100 }));
  const askHeat = asks.map(a => ({ ...a, heat: (a.size / Math.max(1e-9, totalAskSize)) * 100 }));
  return { imbalance, depth, bidHeat, askHeat };
}

function displayOrderBook(bids, asks, midPrice, analysis) {
  const safeMid = Number.isFinite(midPrice) ? midPrice : 0;
  const imbStr = Number.isFinite(analysis.imbalance) ? (analysis.imbalance * 100).toFixed(2) : '0.00';
  const depthBidsStr = Number.isFinite(analysis.depth.bids) ? analysis.depth.bids.toFixed(4) : '0.0000';
  const depthAsksStr = Number.isFinite(analysis.depth.asks) ? analysis.depth.asks.toFixed(4) : '0.0000';
  const depthRatioStr = Number.isFinite(analysis.depth.ratio) ? analysis.depth.ratio.toFixed(2) : '1.00';
  console.log('\n' + neon.header('📊 LIVE ORDER BOOK ANALYSIS'));
  console.log(`${neon.dim('Mid Price:')} ${neon.price(`$${safeMid.toFixed(2)}`)}`);
  console.log(`${neon.dim('Imbalance:')} ${analysis.imbalance >= 0 ? neon.bid('BUY ') : neon.ask('SELL ')} ${imbStr}%`);
  console.log(`${neon.dim('Depth:')} ${neon.bid('Bid')} ${depthBidsStr} | ${neon.ask('Ask')} ${depthAsksStr} | Ratio: ${depthRatioStr}`);
  console.log('\n' + neon.bid('BIDS') + neon.dim(' (Heat %)') + ' | ' + neon.ask('ASKS') + neon.dim(' (Heat %)'));
  let cumulativeBid = 0, cumulativeAsk = 0;
  for (let i = 0; i < Math.min(5, Math.max(bids.length, asks.length)); i++) {
    const bid = analysis.bidHeat[i];
    const ask = analysis.askHeat[i];
    if (bid) cumulativeBid += bid.size;
    if (ask) cumulativeAsk += ask.size;
    const bidLine = bid ? `${neon.bid(`$${bid.price.toFixed(2)}`)} ${neon.dim(`${bid.size.toFixed(4)}`)} ${neon.dim(`(${cumulativeBid.toFixed(4)})`)}` : ''.padEnd(36);
    const bidHeatStr = bid ? neon.bid(`${(bid.heat || 0).toFixed(1)}%`) : ''.padEnd(8);
    const askLine = ask ? `${neon.ask(`$${ask.price.toFixed(2)}`)} ${neon.dim(`${ask.size.toFixed(4)}`)} ${neon.dim(`(${cumulativeAsk.toFixed(4)})`)}` : ''.padEnd(36);
    const askHeatStr = ask ? neon.ask(`${(ask.heat || 0).toFixed(1)}%`) : ''.padEnd(8);
    console.log(`${bidLine.padEnd(36)} ${bidHeatStr.padEnd(8)} | ${askLine.padEnd(36)} ${askHeatStr}`);
  }
  console.log();
}

// ====================== 
// PNL & FILL SIMULATION
// ====================== 
function updatePnL(side, qty, price) {
  const oldPos = botState.netPosition;
  const tradeDelta = side === 'buy' ? qty : -qty;
  const newPos = oldPos + tradeDelta;

  if (oldPos !== 0 && Math.sign(oldPos) !== Math.sign(newPos)) {
    const closeQty = Math.min(Math.abs(oldPos), Math.abs(tradeDelta));
    const closePnl = (price - botState.averageEntryPrice) * -oldPos;
    botState.realizedPnL += closePnl;
    botState.tradeCount += 1;
    log('info', `[PnL] 💰 Realized ${closePnl.toFixed(6)}`, { side, closeQty: closeQty.toFixed(6) });
  }

  if (newPos === 0) {
    botState.averageEntryPrice = 0;
  } else if (Math.sign(oldPos) === Math.sign(newPos) || oldPos === 0) {
    botState.averageEntryPrice = ((botState.averageEntryPrice * oldPos) + (price * tradeDelta)) / newPos;
  } else {
    botState.averageEntryPrice = price;
  }
  botState.netPosition = newPos;
  if (botState.netPosition !== 0 && Number.isFinite(botState.lastPrice)) {
    botState.unrealizedPnL = (botState.lastPrice - botState.averageEntryPrice) * botState.netPosition;
  } else {
    botState.unrealizedPnL = 0;
  }
  botState.totalPnL = botState.realizedPnL + botState.unrealizedPnL;
  pnlCsvWriter.writeRecords([{
    timestamp: new Date().toISOString(),
    event: 'FILL',
    price,
    qty,
    side,
    realizedPnL: botState.realizedPnL,
    unrealizedPnL: botState.unrealizedPnL,
    totalPnL: botState.totalPnL,
    netPosition: botState.netPosition,
  }]).catch(() => {});
}

function simulateFillEvent(orderSize) {
  if (!DRY_RUN) return;
  if (Math.random() > FILL_PROBABILITY) return;
  const side = Math.random() > 0.5 ? 'buy' : 'sell';
  const qty = orderSize;
  const last = Number.isFinite(botState.lastPrice) ? botState.lastPrice : 0;
  const price = last * (1 + (Math.random() - 0.5) * 2 * SLIPPAGE_FACTOR);
  log('info', `[DRY RUN] Simulated ${side.toUpperCase()} fill`, {
    side, qty: qty.toFixed(6), price: price.toFixed(2)
  });
  updatePnL(side, qty, price);
}

// ====================== 
// SMS ALERTS (TERMUX)
// ====================== 
function sendTermuxSMS(message) {
  if (!USE_TERMUX_SMS || !SMS_PHONE_NUMBER) return;
  const now = Date.now();
  const digest = message.slice(0, 120);
  if (now - botState.lastSmsAt < 60000 && botState.lastSmsDigest === digest) return;
  const cmd = `termux-sms-send -n "${SMS_PHONE_NUMBER}" "${message.slice(0, 150)}"`;
  exec(cmd, (err, stdout, stderr) => {
    if (err) {
      log('error', 'Termux SMS failed', { error: err.message });
      return;
    }
    if (stderr) log('warn', 'Termux SMS stderr', { stderr });
    log('info', 'Termux SMS sent', { to: SMS_PHONE_NUMBER, message: digest + '...' });
  });
  botState.lastSmsAt = now;
  botState.lastSmsDigest = digest;
}

// ====================== 
// ORDER & RISK MANAGEMENT
// ====================== 
async function placeOrder(side, price, qty) {
  const displayPrice = Number.isFinite(price) ? price.toFixed(1) : String(price);
  const displayQty = Number.isFinite(qty) ? qty.toFixed(6) : String(qty);
  if (DRY_RUN) {
    const orderId = `DRY_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    log('info', `[DRY RUN] Would place ${side.toUpperCase()} order`, {
      side, price: displayPrice, qty: displayQty, orderId
    });
    botState.activeOrders.add(orderId);
    return orderId;
  }
  if (!botState.hasValidCredentials) return null;
  try {
    const res = await bybitRequest('order/create', 'POST', {
      category: 'linear',
      symbol: SYMBOL,
      side: side.toUpperCase(),
      orderType: 'Limit',
      qty: qty.toString(),
      price: price.toString(),
      timeInForce: 'GTC',
      reduceOnly: false,
      closeOnTrigger: false,
    });
    if (res.retCode === 0) {
      const orderId = res.result.orderId;
      botState.activeOrders.add(orderId);
      log('info', `✅ Placed ${side} order`, { side, price: displayPrice, qty: displayQty, orderId });
      return orderId;
    } else {
      log('error', `❌ Failed to place ${side} order`, { side, price, qty, msg: res.retMsg });
      return null;
    }
  } catch (err) {
    log('error', `Exception placing ${side} order`, { side, price, qty, error: err.message });
    return null;
  }
}

async function cancelAllOrders() {
  if (DRY_RUN) {
    const count = botState.activeOrders.size;
    log('info', `[DRY RUN] Would cancel ${count} orders`, { orders: Array.from(botState.activeOrders) });
    botState.activeOrders.clear();
    return true;
  }
  if (!botState.hasValidCredentials) {
    log('warn', 'Skipping cancel-all: Invalid API credentials.');
    botState.activeOrders.clear();
    return true;
  }
  try {
    const res = await bybitRequest('order/cancel-all', 'POST', { category: 'linear', symbol: SYMBOL });
    if (res.retCode === 0) {
      log('info', '🗑️ All orders canceled');
      botState.activeOrders.clear();
      return true;
    } else {
      log('error', 'Failed to cancel all orders', { retMsg: res.retMsg });
      return false;
    }
  } catch (err) {
    log('error', 'Exception during cancel-all', { error: err.message });
    return false;
  }
}

function checkRiskLimits() {
  if (STOP_ON_LARGE_POS && Math.abs(botState.netPosition) >= MAX_NET_POSITION) {
    if (!botState.isPaused) {
      botState.isPaused = true;
      log('warn', `⚠️ POSITION RISK TRIGGERED: Net ${botState.netPosition.toFixed(6)} ≥ ${MAX_NET_POSITION} → PAUSED`);
      sendTermuxSMS(`⚠️ PAUSED: Net pos ${botState.netPosition.toFixed(6)} BTC > limit ${MAX_NET_POSITION}`);
    }
    return false;
  }
  if (botState.isPaused && Math.abs(botState.netPosition) < MAX_NET_POSITION * 0.8) {
    botState.isPaused = false;
    log('info', `✅ RISK CLEARED: Net ${botState.netPosition.toFixed(6)} < ${MAX_NET_POSITION * 0.8} → RESUMED`);
    sendTermuxSMS(`✅ RESUMED: Net pos ${botState.netPosition.toFixed(6)} BTC back within limit`);
  }
  return true;
}

// ====================== 
// HEARTBEAT
// ====================== 
function startHeartbeat() {
  setInterval(() => {
    console.log('\n' + neon.header('📈 STATUS HEARTBEAT'));
    console.log(`${neon.dim('Last Price:')} ${neon.price(`$${(botState.lastPrice ?? 0).toFixed(2)}`)}`);
    console.log(`${neon.dim('Net Position:')} ${neon.pnl(botState.netPosition)} BTC`);
    console.log(`${neon.dim('Avg Entry:')} ${neon.price(`$${(botState.averageEntryPrice ?? 0).toFixed(2)}`)}`);
    console.log(`${neon.dim('Realized PnL:')} ${neon.pnl(botState.realizedPnL)}`);
    console.log(`${neon.dim('Unrealized PnL:')} ${neon.pnl(botState.unrealizedPnL)}`);
    console.log(`${neon.dim('Total PnL:')} ${neon.pnl(botState.totalPnL)}`);
    console.log(`${neon.dim('Trades:')} ${neon.success(String(botState.tradeCount))}`);
    console.log(`${neon.dim('Active Orders:')} ${botState.activeOrders.size}`);
    console.log(`${neon.dim('Volatility:')} ${getVolatility().toFixed(6)}`);
    console.log(`${neon.dim('Is Paused:')} ${botState.isPaused ? neon.warn('YES') : neon.success('NO')}\n`);
  }, HEARTBEAT_INTERVAL);
}

// ====================== 
// WEBSOCKET (Ticker for price history)
// ====================== 
function setupWebSocket() {
  const wssUrl = IS_TESTNET
    ? 'wss://stream-testnet.bybit.com/v5/public/linear'
    : 'wss://stream.bybit.com/v5/public/linear';
  const ws = new WebSocket(wssUrl);
  ws.on('open', () => {
    botState.wsReconnectAttempts = 0;
    log('info', '🔌 Connected to Bybit WebSocket');
    ws.send(JSON.stringify({ op: 'subscribe', args: [`ticker.${SYMBOL}`] }));
  });
  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data);
      if (msg.topic && msg.topic.startsWith('ticker.') && msg.data?.lastPrice) {
        const newPrice = parseFloat(msg.data.lastPrice);
        if (Number.isFinite(newPrice)) {
          botState.lastPrice = newPrice;
          botState.priceHistory.push(newPrice);
          if (botState.priceHistory.length > 200) botState.priceHistory.shift();
        }
      }
    } catch (err) {
      log('warn', 'Invalid WebSocket message', { err: err.message });
    }
  });
  ws.on('close', () => {
    log('warn', '🔌 WebSocket disconnected. Reconnecting...');
    const delay = Math.min(1000 * Math.pow(2, botState.wsReconnectAttempts++), 30000);
    setTimeout(setupWebSocket, delay);
  });
  ws.on('error', (err) => {
    log('error', 'WebSocket error', { error: err.message });
  });
}

// ====================== 
// REFRESH CYCLE
// ====================== 
async function refreshOrders() {
  if (botState.isShuttingDown || botState.isPaused) {
    log('info', 'Market maker paused or shutting down. Skipping refresh.');
    return;
  }
  try {
    const { bids, asks, midPrice, imbalance } = await getOrderBook();
    botState.lastPrice = midPrice;
    const analysis = analyzeOrderBook(bids, asks, midPrice);
    displayOrderBook(bids, asks, midPrice, analysis);

    const vol = getVolatility();
    const volatilitySpread = vol * VOLATILITY_SPREAD_FACTOR;
    const positionSkew = (botState.netPosition / Math.max(1e-9, MAX_NET_POSITION)) * POSITION_SKEW_FACTOR;
    const imbalanceSpread = imbalance * IMBALANCE_SPREAD_FACTOR;
    const bidSpread = Math.max(0.00005, BID_SPREAD_BASE + volatilitySpread + Math.max(0, positionSkew) + imbalanceSpread);
    const askSpread = Math.max(0.00005, ASK_SPREAD_BASE + volatilitySpread - Math.min(0, positionSkew) - imbalanceSpread);
    const baseBidPrice = midPrice * (1 - bidSpread);
    const baseAskPrice = midPrice * (1 + askSpread);

    let orderSize = MIN_ORDER_SIZE;
    if (!ORDER_SIZE_FIXED) {
      const vol = getVolatility();
      orderSize = MIN_ORDER_SIZE * (1 + vol * VOLATILITY_FACTOR);
      // Further adjust based on imbalance
      orderSize *= (1 + Math.abs(imbalance) * IMBALANCE_ORDER_SIZE_FACTOR);
    }
    orderSize = Math.max(MIN_ORDER_SIZE, Math.min(orderSize, 0.01)); // Apply min/max limits

    log('info', '📊 Refreshing orders', {
      midPrice: midPrice.toFixed(2),
      bidSpread: bidSpread.toFixed(5),
      askSpread: askSpread.toFixed(5),
      volSpread: volatilitySpread.toFixed(5),
      posSkew: positionSkew.toFixed(5),
      imbSpread: imbalanceSpread.toFixed(5),
      orderSize: orderSize.toFixed(6)
    });

    await cancelAllOrders();
    const tasks = [];
    const gridSpacing = GRID_SPACING_BASE * (1 + vol * 0.5);
    for (let i = 0; i < MAX_ORDERS_PER_SIDE; i++) {
      tasks.push(placeOrder('buy', baseBidPrice * (1 - i * gridSpacing), orderSize));
      tasks.push(placeOrder('sell', baseAskPrice * (1 + i * gridSpacing), orderSize));
    }
    await Promise.all(tasks);
    simulateFillEvent(orderSize);
    checkRiskLimits();
    log('debug', 'Order refresh completed', { duration: `${Date.now() - Date.now()}ms`, ordersPlaced: botState.activeOrders.size });
  } catch (err) {
    log('error', '❌ Refresh failed', { error: err.message });
    sendTermuxSMS(`[BOT ERROR] ${err.message.slice(0, 120)}`);
  }
}

// ====================== 
// GRACEFUL SHUTDOWN
// ====================== 
const shutdown = async (signal) => {
  if (botState.isShuttingDown) return;
  botState.isShuttingDown = true;
  log('info', `🛑 Received ${signal}, shutting down gracefully...`);
  try {
    await cancelAllOrders();
  } catch (_) {}
  saveState();
  sendTermuxSMS(`[SHUTDOWN] Bot stopped by ${signal}. PnL: ${botState.totalPnL.toFixed(6)}`);
  log('info', '✅ Shutdown complete.');
  process.exit(0);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('uncaughtException', (err) => {
  log('error', 'Uncaught Exception', { error: err.message, stack: err.stack });
  sendTermuxSMS(`[CRASH] ${err.message.slice(0, 120)}`);
  shutdown('uncaughtException');
});
process.on('unhandledRejection', (reason) => {
  const msg = reason?.message || String(reason);
  log('error', 'Unhandled Rejection', { reason: msg });
  sendTermuxSMS(`[REJECTION] ${msg.slice(0, 120)}`);
  shutdown('unhandledRejection');
});

// ====================== 
// STARTUP
// ====================== 
async function startBot() {
  log('info', '🚀 Starting Neon Market Maker Bot...', {
    version: '3.7.0',
    symbol: SYMBOL,
    testnet: IS_TESTNET,
    dryRun: DRY_RUN,
    dataSource: 'Live Bybit API',
    maxPosition: MAX_NET_POSITION,
    volatilityWindow: VOLATILITY_WINDOW,
    smsAlerts: USE_TERMUX_SMS ? SMS_PHONE_NUMBER : 'disabled',
  });

  if (DRY_RUN) {
    console.log('\n' + neon.header('🔥 DRY RUN MODE — SIMULATING TRADES WITH LIVE MARKET DATA 🔥'));
    console.log(neon.dim('💡 Tip: Bot is resilient to empty books, rate limits, and crashes.') + '\n');
  }

  loadState();
  startHeartbeat();
  setupWebSocket();
  await refreshOrders();
  setInterval(refreshOrders, REFRESH_INTERVAL);
}

// === LAUNCH ===
startBot().catch(err => {
  log('error', 'Bot failed to start', { error: err.message, stack: err.stack });
  sendTermuxSMS(`[STARTUP FAIL] ${err.message.slice(0, 120)}`);
  process.exit(1);
});
