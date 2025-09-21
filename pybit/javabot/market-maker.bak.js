const axios = require('axios');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const { createLogger, format, transports } = require('winston');
const { HmacSHA256 } = require('crypto');
require('dotenv').config();

// ======================
// CONFIGURATION VALIDATION & DEFAULTS
// ======================

const REQUIRED_ENV_VARS = [
  'BYBIT_API_KEY',
  'BYBIT_SECRET',
  'SYMBOL',
  'TESTNET',
  'DRY_RUN'
];

const missing = REQUIRED_ENV_VARS.filter(key => !process.env[key]);
if (missing.length > 0) {
  console.error('❌ FATAL: Missing required environment variables:');
  missing.forEach(key => console.error(`   - ${key}`));
  console.error('\nPlease check your .env file and restart.');
  process.exit(1);
}

// === Core Config ===
const API_KEY = process.env.BYBIT_API_KEY;
const SECRET = process.env.BYBIT_SECRET;
const SYMBOL = process.env.SYMBOL;
const IS_TESTNET = process.env.TESTNET === 'true';
const DRY_RUN = process.env.DRY_RUN === 'true'; // 🔥 DRY RUN = TRUE (SAFE)

// === Trading Parameters ===
const BID_SPREAD_BASE = parseFloat(process.env.BID_SPREAD_BASE) || 0.03;
const ASK_SPREAD_BASE = parseFloat(process.env.ASK_SPREAD_BASE) || 0.03;
const SPREAD_MULTIPLIER = parseFloat(process.env.SPREAD_MULTIPLIER) || 1.5;
const MAX_ORDERS_PER_SIDE = parseInt(process.env.MAX_ORDERS_PER_SIDE) || 3;
const MIN_ORDER_SIZE = parseFloat(process.env.MIN_ORDER_SIZE) || 0.0001;
const ORDER_SIZE_FIXED = process.env.ORDER_SIZE_FIXED === 'true';
const VOLATILITY_WINDOW = parseInt(process.env.VOLATILITY_WINDOW) || 10;
const VOLATILITY_FACTOR = parseFloat(process.env.VOLATILITY_FACTOR) || 2.0;

// === Behavior & Risk ===
const REFRESH_INTERVAL = parseInt(process.env.REFRESH_INTERVAL) || 6000;
const HEARTBEAT_INTERVAL = parseInt(process.env.HEARTBEAT_INTERVAL) || 30000;
const RETRY_DELAY_BASE = parseInt(process.env.RETRY_DELAY_BASE) || 1000;
const MAX_NET_POSITION = parseFloat(process.env.MAX_NET_POSITION) || 0.01;
const STOP_ON_LARGE_POS = process.env.STOP_ON_LARGE_POS === 'true';
const FILL_PROBABILITY = parseFloat(process.env.FILL_PROBABILITY) || 0.15; // Dry-run fill chance
const SLIPPAGE_FACTOR = parseFloat(process.env.SLIPPAGE_FACTOR) || 0.001; // Simulate slippage

// === Logging & Alerts ===
const LOG_TO_FILE = process.env.LOG_TO_FILE === 'true';
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID;

// === API Base ===
const BASE_URL = IS_TESTNET ? 'https://api-testnet.bybit.com' : 'https://api.bybit.com';

// ======================
// GLOBAL STATE (Immutable Updates)
// ======================

const botState = {
  lastPrice: null,
  priceHistory: [],
  netPosition: 0,
  activeOrders: new Set(),
  retryCount: 0,
  lastRefresh: Date.now(),
  isPaused: false,
  hasValidCredentials: !!API_KEY && !!SECRET,
  isShuttingDown: false,
  wsReconnectAttempts: 0,
  maxWsReconnect: 10,
};

// ======================
// LOGGER SETUP (JSON + Console)
// ======================

const logDir = './logs';
if (!fs.existsSync(logDir)) fs.mkdirSync(logDir);

const logger = createLogger({
  level: LOG_LEVEL,
  format: format.combine(
    format.timestamp(),
    format.errors({ stack: true }),
    format.json()
  ),
  transports: [
    new transports.Console({ format: format.simple() }),
    ...(LOG_TO_FILE ? [new transports.File({ filename: path.join(logDir, 'bot.log') })] : [])
  ],
  exceptionHandlers: [
    new transports.File({ filename: path.join(logDir, 'exceptions.log') })
  ],
});

const log = (level, message, metadata = {}) => {
  const logEntry = { level, message, timestamp: new Date().toISOString(), ...metadata };
  logger.log(level, JSON.stringify(logEntry));
};

// ======================
// UTILITIES
// ======================

function generateSignature(params, secret) {
  if (!secret) throw new Error('SECRET is undefined. Cannot generate signature.');
  const sortedParams = Object.keys(params)
    .sort()
    .map(key => `${key}=${params[key]}`)
    .join('&');
  return HmacSHA256(sortedParams, Buffer.from(secret, 'utf8')).toString('hex');
}

async function bybitRequest(endpoint, method, body = {}) {
  if (!botState.hasValidCredentials) {
    log('error', 'Cannot make API request: Invalid or missing API credentials.', { endpoint });
    throw new Error('Invalid API credentials');
  }

  const timestamp = Date.now().toString();
  const payload = {
    ...body,
    apiKey: API_KEY,
    timestamp,
    recvWindow: '5000',
  };

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
      timeout: 5000,
    });

    botState.retryCount = 0;
    return res.data;
  } catch (err) {
    botState.retryCount++;
    const delay = RETRY_DELAY_BASE * Math.pow(2, Math.min(botState.retryCount, 5));
    log('warn', `API Error ${endpoint}: ${err.response?.data?.retMsg || err.message}. Retrying in ${delay}ms (${botState.retryCount}/5)`);
    await new Promise(resolve => setTimeout(resolve, delay));

    if (botState.retryCount >= 5) {
      log('error', `Max retries exceeded for ${endpoint}`, { endpoint });
      throw new Error(`Max retries exceeded: ${endpoint}`);
    }

    return bybitRequest(endpoint, method, body);
  }
}

// Simulate price drift (realistic random walk)
function simulatePriceDrift(current) {
  const volatility = getVolatility();
  const drift = (Math.random() - 0.5) * 10 * (1 + volatility);
  return parseFloat((current + drift).toFixed(2));
}

// Calculate volatility (normalized % change)
function getVolatility() {
  if (botState.priceHistory.length < VOLATILITY_WINDOW) return 1.0;

  const recent = botState.priceHistory.slice(-VOLATILITY_WINDOW);
  const changes = recent.map((p, i) => i > 0 ? Math.abs(p - recent[i - 1]) : 0);
  const avgChange = changes.reduce((a, b) => a + b, 0) / changes.length;
  const avgPrice = recent.reduce((a, b) => a + b, 0) / recent.length;
  return avgChange / avgPrice;
}

// Dynamic order size based on volatility
function calculateOrderSize() {
  if (ORDER_SIZE_FIXED) return MIN_ORDER_SIZE;

  const vol = getVolatility();
  const baseSize = MIN_ORDER_SIZE;
  const size = baseSize * (1 + vol * VOLATILITY_FACTOR);
  return Math.max(MIN_ORDER_SIZE, Math.min(size, 0.01));
}

// Fetch or simulate ticker price
async function getTicker() {
  if (DRY_RUN) {
    botState.lastPrice = botState.lastPrice 
      ? simulatePriceDrift(botState.lastPrice) 
      : 70000;
    botState.priceHistory.push(botState.lastPrice);
    if (botState.priceHistory.length > 100) botState.priceHistory.shift();
    log('debug', 'Simulated ticker update', { price: botState.lastPrice });
    return botState.lastPrice;
  }

  const res = await bybitRequest('market/tickers', 'GET', { category: 'linear', symbol: SYMBOL });
  const price = parseFloat(res.result.list[0].lastPrice);
  botState.lastPrice = price;
  botState.priceHistory.push(price);
  if (botState.priceHistory.length > 100) botState.priceHistory.shift();
  return price;
}

// Fetch or simulate order book with realistic depth and imbalance
async function getOrderBook() {
  if (DRY_RUN) {
    const midPrice = botState.lastPrice || 70000;
    const bidPrice = midPrice * (1 - BID_SPREAD_BASE);
    const askPrice = midPrice * (1 + ASK_SPREAD_BASE);

    // Simulate imbalance: -1 (all sells) to +1 (all buys)
    const imbalance = (Math.random() - 0.5) * 2;
    const bidDepth = Math.max(0.2, 1 + imbalance * 0.8);
    const askDepth = Math.max(0.2, 1 - imbalance * 0.8);

    const generateOrders = (base, depth, count, isBid) => 
      Array.from({ length: count }, (_, i) => ({
        price: isBid 
          ? (base - i * 20 * depth).toFixed(1)
          : (base + i * 20 * depth).toFixed(1),
        size: (ORDER_SIZE_FIXED ? MIN_ORDER_SIZE : calculateOrderSize() * (1 - i * 0.2)).toFixed(6),
      }));

    const bids = generateOrders(bidPrice, bidDepth, 5, true).map(b => ({
      price: parseFloat(b.price),
      size: parseFloat(b.size)
    }));

    const asks = generateOrders(askPrice, askDepth, 5, false).map(a => ({
      price: parseFloat(a.price),
      size: parseFloat(a.size)
    }));

    log('debug', 'Simulated order book', { midPrice, imbalance: imbalance.toFixed(2), bidDepth, askDepth });
    return { bids, asks, midPrice, imbalance };
  }

  try {
    const res = await axios.get(`${BASE_URL}/v5/market/orderbook`, {
      params: { category: 'linear', symbol: SYMBOL, limit: 5 }
    });

    const bids = res.data.result.bids.map(b => ({ price: parseFloat(b[0]), size: parseFloat(b[1]) }));
    const asks = res.data.result.asks.map(a => ({ price: parseFloat(a[0]), size: parseFloat(a[1]) }));

    const midPrice = (bids[0]?.price + asks[0]?.price) / 2;
    const imbalance = (bids[0]?.size - asks[0]?.size) / (bids[0]?.size + asks[0]?.size);

    return { bids, asks, midPrice, imbalance };
  } catch (err) {
    log('error', 'Failed to fetch order book', { error: err.message });
    throw err;
  }
}

// Simulate fill events (dry run only)
function simulateFillEvent() {
  if (!DRY_RUN) return;

  const fillRate = FILL_PROBABILITY;
  if (Math.random() > fillRate) return;

  const side = Math.random() > 0.5 ? 'buy' : 'sell';
  const baseSize = calculateOrderSize();
  const slippage = (Math.random() - 0.5) * 2 * SLIPPAGE_FACTOR * (botState.lastPrice || 70000);
  const effectivePrice = (botState.lastPrice || 70000) + slippage;

  const delta = side === 'buy' ? baseSize : -baseSize;
  botState.netPosition += delta;

  log('info', `[DRY RUN] ✅ Simulated ${side.toUpperCase()} fill`, {
    side,
    size: baseSize.toFixed(6),
    price: effectivePrice.toFixed(2),
    netPosition: botState.netPosition.toFixed(6),
    slippage: slippage.toFixed(2)
  });
}

// Place order (dry-run or real)
async function placeOrder(side, price, qty) {
  const displayPrice = price.toFixed(1);
  const displayQty = qty.toFixed(6);

  if (DRY_RUN) {
    const orderId = `DRY_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
    log('info', `[DRY RUN] Would place ${side.toUpperCase()} order`, {
      side, price: displayPrice, qty: displayQty, orderId
    });
    botState.activeOrders.add(orderId);
    return orderId;
  }

  if (!botState.hasValidCredentials) {
    log('error', 'Cannot place order: Invalid API credentials.', { side, price, qty });
    return null;
  }

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
      log('info', `✅ Placed ${side} order`, {
        side, price: displayPrice, qty: displayQty, orderId
      });
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

// Cancel all orders (dry-run safe)
async function cancelAllOrders() {
  if (DRY_RUN) {
    const count = botState.activeOrders.size;
    log('info', `[DRY RUN] Would cancel ${count} orders`, { orders: Array.from(botState.activeOrders) });
    botState.activeOrders.clear();
    return true;
  }

  if (!botState.hasValidCredentials) {
    log('warn', 'Skipping cancel-all: Invalid API credentials. Assuming manual intervention.');
    botState.activeOrders.clear();
    return true;
  }

  try {
    const res = await bybitRequest('order/cancel-all', 'POST', {
      category: 'linear',
      symbol: SYMBOL,
    });

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

// Fetch active orders from exchange
async function fetchActiveOrders() {
  if (DRY_RUN) {
    return Array.from(botState.activeOrders).map(id => ({
      orderId: id,
      side: id.includes('DRY_') ? 'Buy' : 'Sell',
      status: 'New',
      price: 0,
      qty: 0,
    }));
  }

  if (!botState.hasValidCredentials) return [];

  try {
    const res = await bybitRequest('order/query', 'GET', {
      category: 'linear',
      symbol: SYMBOL,
      limit: 50,
    });

    if (res.retCode !== 0) {
      log('error', 'Failed to query active orders', { retMsg: res.retMsg });
      return [];
    }

    return res.result.list.filter(o => o.status === 'New');
  } catch (err) {
    log('error', 'Exception fetching active orders', { error: err.message });
    return [];
  }
}

// Check risk limits and pause/resume
function checkRiskLimits() {
  if (STOP_ON_LARGE_POS && Math.abs(botState.netPosition) >= MAX_NET_POSITION) {
    if (!botState.isPaused) {
      log('warn', `⚠️ POSITION RISK TRIGGERED: Net position ${botState.netPosition.toFixed(6)} BTC ≥ ${MAX_NET_POSITION} BTC → PAUSING MARKET MAKER`);
      botState.isPaused = true;
      sendTelegramAlert(`⚠️ MARKET MAKER PAUSED: Net position ${botState.netPosition.toFixed(6)} BTC exceeds limit of ${MAX_NET_POSITION} BTC.`);
    }
    return false;
  }

  if (botState.isPaused && Math.abs(botState.netPosition) < MAX_NET_POSITION * 0.8) {
    log('info', `✅ RISK LIMIT CLEARED: Net position ${botState.netPosition.toFixed(6)} BTC → RESUMING MARKET MAKER`);
    botState.isPaused = false;
    sendTelegramAlert(`✅ MARKET MAKER RESUMED: Net position ${botState.netPosition.toFixed(6)} BTC now within safe limit.`);
  }

  return true;
}

// Send Telegram alert (with retry)
async function sendTelegramAlert(message) {
  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) return;

  try {
    await axios.post(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
      chat_id: TELEGRAM_CHAT_ID,
      text: message,
      parse_mode: 'HTML',
    }, { timeout: 3000 });
    log('info', 'Telegram alert sent');
  } catch (err) {
    log('error', 'Failed to send Telegram alert', { error: err.message });
  }
}

// Heartbeat telemetry
function startHeartbeat() {
  setInterval(() => {
    const activeBidCount = [...botState.activeOrders].filter(id => id.startsWith('DRY_')).length / 2 || 0;
    const activeAskCount = botState.activeOrders.size - activeBidCount;

    const volatility = getVolatility();
    const orderSize = calculateOrderSize();

    log('info', '🕒 STATUS HEARTBEAT', {
      lastPrice: botState.lastPrice?.toFixed(2),
      netPosition: botState.netPosition.toFixed(6),
      activeOrders: botState.activeOrders.size,
      activeBidCount,
      activeAskCount,
      volatility: isNaN(volatility) ? 'NaN' : volatility.toFixed(6),
      orderSize: isNaN(orderSize) ? 'NaN' : orderSize.toFixed(6),
      isPaused: botState.isPaused,
      dryRun: DRY_RUN,
      lastRefresh: Date.now() - botState.lastRefresh,
      hasValidCredentials: botState.hasValidCredentials,
      fillProbability: FILL_PROBABILITY,
    });
  }, HEARTBEAT_INTERVAL);
}

// Graceful shutdown
const shutdown = async (signal) => {
  if (botState.isShuttingDown) return;
  botState.isShuttingDown = true;

  log('info', `🛑 Received ${signal}, shutting down gracefully...`);

  if (botState.hasValidCredentials) {
    log('info', 'Attempting to cancel all orders via API...');
    await cancelAllOrders();
  } else {
    log('warn', 'Skipping API cancel: Invalid or missing API credentials. Orders may remain open on exchange.');
    botState.activeOrders.clear();
  }

  log('info', '✅ Orders canceled (or skipped). Exiting.');
  process.exit(0);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('uncaughtException', (err) => {
  log('error', 'Uncaught Exception', { error: err.message, stack: err.stack });
  shutdown('uncaughtException');
});
process.on('unhandledRejection', (reason, promise) => {
  log('error', 'Unhandled Rejection', { reason: reason.message, promise });
  shutdown('unhandledRejection');
});

// ======================
// MAIN ENTRY POINT
// ======================

async function startBot() {
  log('info', '🚀 Starting Bybit Market Maker Bot...', {
    version: '2.3.0',
    symbol: SYMBOL,
    testnet: IS_TESTNET,
    dryRun: DRY_RUN,
    maxPosition: MAX_NET_POSITION,
    refreshInterval: REFRESH_INTERVAL,
    volatilityWindow: VOLATILITY_WINDOW,
    hasValidCredentials: botState.hasValidCredentials,
    fillProbability: FILL_PROBABILITY,
    slippageFactor: SLIPPAGE_FACTOR,
  });

  if (DRY_RUN) {
    console.log('\n' + '█'.repeat(60));
    console.log('█           ⚠️  DRY RUN MODE ACTIVE — NO REAL ORDERS WILL BE PLACED           █');
    console.log('█           💡 Use DRY_RUN=false only after thorough testing             █');
    console.log('█           🔐 TESTNET=false but DRY_RUN=true → SAFE SIMULATION            █');
    console.log('█'.repeat(60) + '\n');
  }

  if (!botState.hasValidCredentials) {
    log('error', 'CRITICAL: API_KEY or SECRET is missing. Bot will operate in read-only mode.');
    console.error('\n❌ FATAL: Missing or invalid API credentials. Please fix your .env file.\n');
  }

  startHeartbeat();

  // Initial sync
  await refreshOrders();
  botState.lastRefresh = Date.now();

  // Schedule periodic refresh
  setInterval(refreshOrders, REFRESH_INTERVAL);
}

// WebSocket setup with exponential backoff
function setupWebSocket() {
  if (botState.wsReconnectAttempts >= botState.maxWsReconnect) {
    log('warn', 'Max WebSocket reconnect attempts reached. Skipping.');
    return;
  }

  const wssUrl = IS_TESTNET
    ? 'wss://stream-testnet.bybit.com/v5/public/linear'
    : 'wss://stream.bybit.com/v5/public/linear';

  const ws = new WebSocket(wssUrl);

  ws.on('open', () => {
    botState.wsReconnectAttempts = 0;
    log('info', '🔌 Connected to Bybit WebSocket');
    ws.send(JSON.stringify({
      op: 'subscribe',
      args: [`ticker.${SYMBOL}`]
    }));
  });

  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data);
      if (msg.topic && msg.topic.startsWith('ticker.')) {
        const newPrice = parseFloat(msg.data.lastPrice);
        botState.lastPrice = newPrice;
        botState.priceHistory.push(newPrice);
        if (botState.priceHistory.length > 100) botState.priceHistory.shift();

        if (DRY_RUN) {
          log('debug', 'WebSocket price update (simulated)', { price: newPrice });
        } else {
          log('debug', 'WebSocket price update', { price: newPrice });
        }
      }
    } catch (err) {
      log('warn', 'Invalid WebSocket message', { data: data.toString().substring(0, 100) });
    }
  });

  ws.on('close', () => {
    log('warn', '🔌 WebSocket disconnected. Reconnecting...');
    const delay = Math.min(1000 * Math.pow(2, botState.wsReconnectAttempts), 30000);
    botState.wsReconnectAttempts++;
    setTimeout(setupWebSocket, delay);
  });

  ws.on('error', (err) => {
    log('error', 'WebSocket error', { error: err.message });
  });
}

// Refresh market maker orders
async function refreshOrders() {
  if (botState.isShuttingDown || botState.isPaused) {
    log('info', 'Market maker paused or shutting down. Skipping refresh.');
    return;
  }

  const startTime = Date.now();

  try {
    const { bids, asks, midPrice, imbalance } = await getOrderBook();
    botState.lastPrice = midPrice;

    // Dynamic spread based on imbalance
    const baseBidSpread = BID_SPREAD_BASE * (1 + Math.max(0, imbalance * SPREAD_MULTIPLIER));
    const baseAskSpread = ASK_SPREAD_BASE * (1 - Math.min(0, imbalance * SPREAD_MULTIPLIER));

    const bidPrice = midPrice * (1 - baseBidSpread);
    const askPrice = midPrice * (1 + baseAskSpread);

    const orderSize = calculateOrderSize();

    log('info', '📊 Refreshing orders', {
      midPrice,
      bidPrice,
      askPrice,
      imbalance: imbalance.toFixed(4),
      volatility: getVolatility().toFixed(6),
      orderSize: orderSize.toFixed(6),
      netPosition: botState.netPosition.toFixed(6),
    });

    await cancelAllOrders();

    const placeOrders = async (side, price, offset) => {
      for (let i = 0; i < MAX_ORDERS_PER_SIDE; i++) {
        const adjustedPrice = side === 'buy' 
          ? price * (1 - i * offset) 
          : price * (1 + i * offset);
        const orderId = await placeOrder(side, adjustedPrice, orderSize);
        if (orderId) botState.activeOrders.add(orderId);
      }
    };

    // Parallel placement
    await Promise.all([
      placeOrders('buy', bidPrice, 0.00015),
      placeOrders('sell', askPrice, 0.00015)
    ]);

    // Simulate fills after order refresh
    simulateFillEvent();

    checkRiskLimits();

    const duration = Date.now() - startTime;
    log('debug', 'Order refresh completed', { duration: `${duration}ms`, ordersPlaced: botState.activeOrders.size });

  } catch (err) {
    log('error', '❌ Refresh failed', { error: err.message });
  }
}

// Start everything
setupWebSocket();
startBot().catch(err => {
  log('error', 'Bot failed to start', { error: err.message, stack: err.stack });
  process.exit(1);
});
