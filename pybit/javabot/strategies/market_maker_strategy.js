import WebSocket from 'ws';
import fs from 'fs';
import path from 'path';
import { exec } from 'child_process';
import { CONFIG } from './config.js';
import { logger, neon } from './logger.js';
import { bybitClient } from './bybit_api_client.js';
// import { getVolatility } from './indicators.js'; // Assuming getVolatility will be moved here or calculated from klines

// ====================== 
// CONFIGURATION (now from config.js) 
// ====================== 
const SYMBOL = CONFIG.SYMBOL;
const IS_TESTNET = CONFIG.TESTNET;
const DRY_RUN = CONFIG.DRY_RUN;

const BID_SPREAD_BASE = CONFIG.BID_SPREAD_BASE;
const ASK_SPREAD_BASE = CONFIG.ASK_SPREAD_BASE;
const SPREAD_MULTIPLIER = CONFIG.SPREAD_MULTIPLIER;
const MAX_ORDERS_PER_SIDE = CONFIG.MAX_ORDERS_PER_SIDE;
const MIN_ORDER_SIZE = CONFIG.MIN_ORDER_SIZE;
const ORDER_SIZE_FIXED = CONFIG.ORDER_SIZE_FIXED;
const VOLATILITY_WINDOW = CONFIG.VOLATILITY_WINDOW;
const VOLATILITY_FACTOR = CONFIG.VOLATILITY_FACTOR;
const REFRESH_INTERVAL = CONFIG.REFRESH_INTERVAL;
const HEARTBEAT_INTERVAL = CONFIG.HEARTBEAT_INTERVAL;
const RETRY_DELAY_BASE = CONFIG.RETRY_DELAY_BASE;
const MAX_NET_POSITION = CONFIG.MAX_NET_POSITION;
const STOP_ON_LARGE_POS = CONFIG.STOP_ON_LARGE_POS;
const PNL_CSV_PATH = CONFIG.PNL_CSV_PATH;
const USE_TERMUX_SMS = CONFIG.USE_TERMUX_SMS;
const SMS_PHONE_NUMBER = CONFIG.SMS_PHONE_NUMBER;
const POSITION_SKEW_FACTOR = CONFIG.POSITION_SKEW_FACTOR;
const VOLATILITY_SPREAD_FACTOR = CONFIG.VOLATILITY_SPREAD_FACTOR;
const STATE_FILE_PATH = CONFIG.STATE_FILE_PATH;
const FILL_PROBABILITY = CONFIG.FILL_PROBABILITY;
const SLIPPAGE_FACTOR = CONFIG.SLIPPAGE_FACTOR;
const GRID_SPACING_BASE = CONFIG.GRID_SPACING_BASE;
const IMBALANCE_SPREAD_FACTOR = CONFIG.IMBALANCE_SPREAD_FACTOR;
const IMBALANCE_ORDER_SIZE_FACTOR = CONFIG.IMBALANCE_ORDER_SIZE_FACTOR;

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
  hasValidCredentials: !!CONFIG.API_KEY && !!CONFIG.API_SECRET,
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
// CSV PNL WRITER
// ====================== 
const createCsvWriter = require('csv-writer').createObjectCsvWriter; // Keep require for now
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
      logger.info(neon.info('✅ Loaded saved state'), {
        netPosition: botState.netPosition,
        averageEntryPrice: botState.averageEntryPrice,
        realizedPnL: botState.realizedPnL,
        tradeCount: botState.tradeCount
      });
    }
  } catch (err) {
    logger.warn(neon.warn('Failed to load state'), { error: err.message });
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
    logger.info(neon.info('💾 State saved'), { path: STATE_FILE_PATH });
  } catch (err) {
    logger.error(neon.error('Failed to save state'), { error: err.message });
  }
}

// ====================== 
// MARKET DATA (ALWAYS LIVE) - Using bybitClient
// ====================== 
async function getOrderBook(retries = 3) {
  try {
    const [bestBid, bestAsk] = await bybitClient.getOrderbookLevels(SYMBOL, 5);

    if (bestBid === null && bestAsk === null) {
      logger.warn(neon.warn('Received an empty order book from Bybit API.'));
      if (retries > 0) {
        const delay = 2000 * Math.pow(2, retries - 1);
        logger.warn(neon.warn('Empty book. Retrying...'), { retries: retries - 1 });
        await new Promise(r => setTimeout(r, delay));
        return getOrderBook(retries - 1);
      }
      logger.warn(neon.warn('Empty book. Using fallback simulation.'));
      const mid = botState.lastPrice || 70000;
      const bid = { price: mid * 0.999, size: MIN_ORDER_SIZE };
      const ask = { price: mid * 1.001, size: MIN_ORDER_SIZE };
      return {
        bids: [bid], asks: [ask],
        midPrice: mid,
        imbalance: 0,
      };
    }

    // Simulate full order book structure for analysis
    const bids = bestBid !== null ? [{ price: bestBid, size: MIN_ORDER_SIZE * 10 }] : []; // Placeholder size
    const asks = bestAsk !== null ? [{ price: bestAsk, size: MIN_ORDER_SIZE * 10 }] : []; // Placeholder size

    if (bids.length === 0 || asks.length === 0) {
      logger.warn(neon.warn(`One side empty. Simulating for continuity. Bids: ${bids.length}, Asks: ${asks.length}`));
      const mid = botState.lastPrice || (bestBid + bestAsk) / 2 || 70000;
      if (bids.length === 0) bids.push({ price: mid * 0.999, size: MIN_ORDER_SIZE * 10 });
      if (asks.length === 0) asks.push({ price: mid * 1.001, size: MIN_ORDER_SIZE * 10 });
    }

    const midPrice = (bids[0].price + asks[0].price) / 2;
    const imbalance = (bids[0].size - asks[0].size) / Math.max(1e-9, (bids[0].size + asks[0].size));
    return { bids, asks, midPrice, imbalance };
  } catch (err) {
    if (retries > 0) {
      const delay = RETRY_DELAY_BASE * Math.pow(2, retries - 1);
      logger.warn(neon.warn(`Book fetch failed: ${err.message}. Retrying...`), { retries: retries - 1 });
      await new Promise(r => setTimeout(r, delay));
      return getOrderBook(retries - 1);
    }
    if (!Number.isFinite(botState.lastPrice)) throw err;
    logger.warn(neon.warn('Using fallback book due to failure.'), { error: err.message });
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
    logger.info(neon.info(`[PnL] 💰 Realized ${closePnl.toFixed(6)}`), { side, closeQty: closeQty.toFixed(6) });
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
  }]).catch(err => logger.error(neon.error('Failed to write PnL to CSV'), { error: err.message }));
}

function simulateFillEvent(orderSize) {
  if (!DRY_RUN) return;
  if (Math.random() > FILL_PROBABILITY) return;
  const side = Math.random() > 0.5 ? 'buy' : 'sell';
  const qty = orderSize;
  const last = Number.isFinite(botState.lastPrice) ? botState.lastPrice : 0;
  const price = last * (1 + (Math.random() - 0.5) * 2 * SLIPPAGE_FACTOR);
  logger.info(neon.info(`[DRY RUN] Simulated ${side.toUpperCase()} fill`), {
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
      logger.error(neon.error('Termux SMS failed'), { error: err.message });
      return;
    }
    if (stderr) logger.warn(neon.warn('Termux SMS stderr'), { stderr });
    logger.info(neon.info('Termux SMS sent'), { to: SMS_PHONE_NUMBER, message: digest + '...' });
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
    logger.info(neon.info(`[DRY RUN] Would place ${side.toUpperCase()} order`), {
      side, price: displayPrice, qty: displayQty, orderId
    });
    botState.activeOrders.add(orderId);
    return orderId;
  }
  if (!botState.hasValidCredentials) return null;
  try {
    const orderId = await bybitClient.placeLimitOrder(SYMBOL, side, price, qty, null, null, 'GTC', false);
    if (orderId) {
      botState.activeOrders.add(orderId);
      logger.info(neon.success(`✅ Placed ${side} order`), { side, price: displayPrice, qty: displayQty, orderId });
      return orderId;
    } else {
      logger.error(neon.error(`❌ Failed to place ${side} order`), { side, price, qty, msg: 'API error or unknown' });
      return null;
    }
  } catch (err) {
    logger.error(neon.error(`Exception placing ${side} order`), { side, price, qty, error: err.message });
    return null;
  }
}

async function cancelAllOrders() {
  if (DRY_RUN) {
    const count = botState.activeOrders.size;
    logger.info(neon.info(`[DRY RUN] Would cancel ${count} orders`), { orders: Array.from(botState.activeOrders) });
    botState.activeOrders.clear();
    return true;
  }
  if (!botState.hasValidCredentials) {
    logger.warn(neon.warn('Skipping cancel-all: Invalid API credentials.'));
    botState.activeOrders.clear();
    return true;
  }
  try {
    const resp = await bybitClient.cancelAllOpenOrders(SYMBOL);
    if (resp.retCode === 0) {
      logger.info(neon.info('🗑️ All orders canceled'));
      botState.activeOrders.clear();
      return true;
    } else {
      logger.error(neon.error('Failed to cancel all orders'), { retMsg: resp.retMsg });
      return false;
    }
  } catch (err) {
    logger.error(neon.error('Exception during cancel-all'), { error: err.message });
    return false;
  }
}

function checkRiskLimits() {
  if (STOP_ON_LARGE_POS && Math.abs(botState.netPosition) >= MAX_NET_POSITION) {
    if (!botState.isPaused) {
      botState.isPaused = true;
      logger.warn(neon.warn(`⚠️ POSITION RISK TRIGGERED: Net ${botState.netPosition.toFixed(6)} ≥ ${MAX_NET_POSITION} → PAUSED`));
      sendTermuxSMS(`⚠️ PAUSED: Net pos ${botState.netPosition.toFixed(6)} BTC > limit ${MAX_NET_POSITION}`);
    }
    return false;
  }
  if (botState.isPaused && Math.abs(botState.netPosition) < MAX_NET_POSITION * 0.8) {
    botState.isPaused = false;
    logger.info(neon.info(`✅ RISK CLEARED: Net ${botState.netPosition.toFixed(6)} < ${MAX_NET_POSITION * 0.8} → RESUMED`));
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
    logger.info(neon.info('🔌 Connected to Bybit WebSocket'));
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
      logger.warn(neon.warn('Invalid WebSocket message'), { err: err.message });
    }
  });
  ws.on('close', () => {
    logger.warn(neon.warn('🔌 WebSocket disconnected. Reconnecting...'));
    const delay = Math.min(1000 * Math.pow(2, botState.wsReconnectAttempts++), 30000);
    setTimeout(setupWebSocket, delay);
  });
  ws.on('error', (err) => {
    logger.error(neon.error('WebSocket error'), { error: err.message });
  });
}

// ====================== 
// REFRESH CYCLE
// ====================== 
async function refreshOrders() {
  if (botState.isShuttingDown || botState.isPaused) {
    logger.info(neon.info('Market maker paused or shutting down. Skipping refresh.'));
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

    logger.info(neon.info('📊 Refreshing orders'), {
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
    logger.debug(neon.dim('Order refresh completed'), { duration: `${Date.now() - botState.lastRefresh}ms`, ordersPlaced: botState.activeOrders.size });
    botState.lastRefresh = Date.now();
  } catch (err) {
    logger.error(neon.error('❌ Refresh failed'), { error: err.message });
    sendTermuxSMS(`[BOT ERROR] ${err.message.slice(0, 120)}`);
  }
}

// ====================== 
// GRACEFUL SHUTDOWN
// ====================== 
const shutdown = async (signal) => {
  if (botState.isShuttingDown) return;
  botState.isShuttingDown = true;
  logger.info(neon.info(`🛑 Received ${signal}, shutting down gracefully...`));
  try {
    await cancelAllOrders();
  } catch (_) {} // Ignore errors during shutdown
  saveState();
  sendTermuxSMS(`[SHUTDOWN] Bot stopped by ${signal}. PnL: ${botState.totalPnL.toFixed(6)}`);
  logger.info(neon.info('✅ Shutdown complete.'));
  process.exit(0);
};

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('uncaughtException', (err) => {
  logger.error(neon.error('Uncaught Exception'), { error: err.message, stack: err.stack });
  sendTermuxSMS(`[CRASH] ${err.message.slice(0, 120)}`);
  shutdown('uncaughtException');
});
process.on('unhandledRejection', (reason) => {
  const msg = reason?.message || String(reason);
  logger.error(neon.error('Unhandled Rejection'), { reason: msg });
  sendTermuxSMS(`[REJECTION] ${msg.slice(0, 120)}`);
  shutdown('unhandledRejection');
});

// ====================== 
// STARTUP
// ====================== 
async function startBot(strategyConfig) { // Added strategyConfig parameter
  logger.info(neon.info('🚀 Starting Neon Market Maker Bot...'), {
    version: '3.7.0',
    symbol: strategyConfig.SYMBOL || SYMBOL, // Use strategyConfig for symbol
    testnet: strategyConfig.TESTNET || IS_TESTNET, // Use strategyConfig for testnet
    dryRun: strategyConfig.DRY_RUN || DRY_RUN, // Use strategyConfig for dryRun
    dataSource: 'Live Bybit API',
    maxPosition: strategyConfig.MAX_NET_POSITION || MAX_NET_POSITION, // Use strategyConfig
    volatilityWindow: strategyConfig.VOLATILITY_WINDOW || VOLATILITY_WINDOW, // Use strategyConfig
    smsAlerts: (strategyConfig.USE_TERMUX_SMS || USE_TERMUX_SMS) ? (strategyConfig.SMS_PHONE_NUMBER || SMS_PHONE_NUMBER) : 'disabled', // Use strategyConfig
  });

  if (strategyConfig.DRY_RUN || DRY_RUN) { // Use strategyConfig for dryRun
    console.log('\n' + neon.header('🔥 DRY RUN MODE — SIMULATING TRADES WITH LIVE MARKET DATA 🔥'));
    console.log(neon.dim('💡 Tip: Bot is resilient to empty books, rate limits, and crashes.') + '\n');
  }

  loadState();
  startHeartbeat();
  setupWebSocket();
  await refreshOrders();
  setInterval(refreshOrders, strategyConfig.REFRESH_INTERVAL || REFRESH_INTERVAL); // Use strategyConfig
}

// === LAUNCH ===
startBot().catch(err => {
  logger.error(neon.error('Bot failed to start'), { error: err.message, stack: err.stack });
  sendTermuxSMS(`[STARTUP FAIL] ${err.message.slice(0, 120)}`);
  process.exit(1);
});
