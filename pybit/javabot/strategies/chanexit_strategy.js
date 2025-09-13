import { CONFIG } from './config.js';
import { logger, neon } from './logger.js';
import { bybitClient } from './bybit_api_client.js';
import { buildAllIndicators } from './indicators.js';
import { setTimeout } from 'timers/promises';
import { v4 as uuidv4 } from 'uuid';
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import moment from 'moment-timezone';
import { DataFrame } from 'dataframe-js';

// ====================== 
// CONFIGURATION (now from config.js) 
// ====================== 
const TRADING_SYMBOLS = CONFIG.TRADING_SYMBOLS;
const TIMEFRAME = CONFIG.TIMEFRAME;
const MIN_KLINES_FOR_STRATEGY = CONFIG.MIN_KLINES_FOR_STRATEGY;
const MAX_POSITIONS = CONFIG.MAX_POSITIONS;
const MAX_OPEN_ORDERS_PER_SYMBOL = CONFIG.MAX_OPEN_ORDERS_PER_SYMBOL;
const RISK_PER_TRADE_PCT = CONFIG.RISK_PER_TRADE_PCT;
const MARGIN_MODE = CONFIG.MARGIN_MODE;
const LEVERAGE = CONFIG.LEVERAGE;
const ORDER_TYPE = CONFIG.ORDER_TYPE;
const POST_ONLY = CONFIG.POST_ONLY;
const PRICE_DETECTION_THRESHOLD_PCT = CONFIG.PRICE_DETECTION_THRESHOLD_PCT;
const BREAKOUT_TRIGGER_PERCENT = CONFIG.BREAKOUT_TRIGGER_PERCENT;
const EMERGENCY_STOP_IF_DOWN_PCT = CONFIG.EMERGENCY_STOP_IF_DOWN_PCT;
const POSITION_RECONCILIATION_INTERVAL_MINUTES = CONFIG.POSITION_RECONCILIATION_INTERVAL_MINUTES;
const MIN_BARS_BETWEEN_TRADES = CONFIG.MIN_BARS_BETWEEN_TRADES;
const TRAILING_STOP_ACTIVE = CONFIG.TRAILING_STOP_ACTIVE;
const FIXED_PROFIT_TARGET_PCT = CONFIG.FIXED_PROFIT_TARGET_PCT;
const USE_FISHER_EXIT = CONFIG.USE_FISHER_EXIT;
const REWARD_RISK_RATIO = CONFIG.REWARD_RISK_RATIO;

// Indicator specific settings
const RSI_OVERBOUGHT = CONFIG.RSI_OVERBOUGHT;
const RSI_OVERSOLD = CONFIG.RSI_OVERSOLD;
const USE_EST_SLOW_FILTER = CONFIG.USE_EST_SLOW_FILTER;
const USE_STOCH_FILTER = CONFIG.USE_STOCH_FILTER;
const USE_MACD_FILTER = CONFIG.USE_MACD_FILTER;
const USE_ADX_FILTER = CONFIG.USE_ADX_FILTER;
const ADX_THRESHOLD = CONFIG.ADX_THRESHOLD;

// ====================== 
// SQLite position tracker 
// ====================== 
const DB_FILE = "scalper_positions.sqlite";
let db; // Will hold the opened database instance

async function _initDb() {
  db = await open({
    filename: DB_FILE,
    driver: sqlite3.Database
  });

  await db.exec(`
    CREATE TABLE IF NOT EXISTS trades(
        id TEXT PRIMARY KEY,
        order_id TEXT, -- Bybit order ID for tracking
        symbol TEXT,
        side TEXT,
        qty REAL,
        entry_time TEXT,
        entry_price REAL,
        sl REAL,
        tp REAL,
        status TEXT DEFAULT 'OPEN', -- OPEN, CLOSED, UNKNOWN, RECONCILED
        exit_time TEXT,
        exit_price REAL,
        pnl REAL
    )
  `);
  logger.info(neon.info(`Database initialized: ${DB_FILE}`));
}

// ====================== 
// UTILITIES 
// ====================== 
function getCurrentTime(tzStr) {
  const localTime = moment().tz(tzStr);
  const utcTime = moment.utc();
  return [localTime, utcTime];
}

function isMarketOpen(localTime, openHour, closeHour) {
  const currentHour = localTime.hour();
  if (openHour < closeHour) {
    return currentHour >= openHour && currentHour < closeHour;
  }
  return currentHour >= openHour || currentHour < closeHour;
}

// ====================== 
// HIGHER TF CONFIRMATION 
// ====================== 
async function higherTfTrend(symbol) {
  const htf = CONFIG.HIGHER_TF_TIMEFRAME;
  const short = CONFIG.H_TF_EMA_SHORT_PERIOD;
  const long = CONFIG.H_TF_EMA_LONG_PERIOD;
  const klines = await bybitClient.klines(symbol, htf, long + 5);
  if (!klines || klines.length < Math.max(short, long) + 1) {
    logger.debug(neon.dim(`Not enough data for HTF trend for ${symbol}.`));
    return 'none';
  }
  const df = new DataFrame(klines);
  const closePrices = df.toCollection().map(row => row.close);
  const emaS = calculateEMA(closePrices, short).slice(-1)[0]; // Assuming calculateEMA is available from indicators.js
  const emaL = calculateEMA(closePrices, long).slice(-1)[0]; // Assuming calculateEMA is available from indicators.js

  if (emaS > emaL) return 'long';
  if (emaS < emaL) return 'short';
  return 'none';
}

// ====================== 
// SIGNAL GENERATOR 
// ====================== 
const lastSignalBar = {};
async function generateSignal(symbol, df) {
  let minRequiredKlines = Math.max(
    MIN_KLINES_FOR_STRATEGY, CONFIG.TREND_EMA_PERIOD,
    CONFIG.EMA_LONG_PERIOD, CONFIG.ATR_PERIOD,
    CONFIG.RSI_PERIOD, CONFIG.VOLUME_MA_PERIOD || 20,
    CONFIG.VOLATILITY_LOOKBACK || 20,
    (CONFIG.EST_SLOW_LENGTH || 8) + 5, (CONFIG.EHLERS_FISHER_PERIOD || 8) + 5
  );
  if (USE_STOCH_FILTER) minRequiredKlines = Math.max(minRequiredKlines, CONFIG.STOCH_K_PERIOD + CONFIG.STOCH_SMOOTHING + 5);
  if (USE_MACD_FILTER) minRequiredKlines = Math.max(minRequiredKlines, CONFIG.MACD_SLOW_PERIOD + CONFIG.MACD_SIGNAL_PERIOD + 5);
  if (USE_ADX_FILTER) minRequiredKlines = Math.max(minRequiredKlines, CONFIG.ADX_PERIOD + 5);

  if (df.empty || df.count() < minRequiredKlines) {
    return ['none', 0, 0, 0, `not enough bars (${df.count()} < ${minRequiredKlines})`];
  }

  const dfWithIndicators = buildAllIndicators(df.toCollection()); // Pass raw data, buildAllIndicators expects array of objects
  const i = dfWithIndicators.count() - 1; // Current bar (last)
  const j = dfWithIndicators.count() - 2; // Previous bar

  if (i < 1) { // Need at least two bars for crossover checks
    return ['none', 0, 0, 0, 'not enough candles for crossover check'];
  }

  const criticalIndicators = ['close', 'atr', 'dynamic_multiplier', 'ema_s', 'ema_l', 'trend_ema', 'rsi', 'vol_spike', 'est_slow', 'fisher'];
  if (USE_STOCH_FILTER) criticalIndicators.push('stoch_k', 'stoch_d');
  if (USE_MACD_FILTER) criticalIndicators.push('macd_line', 'macd_signal');
  if (USE_ADX_FILTER) criticalIndicators.push('adx');

  const lastRow = dfWithIndicators.getRow(i).toDict();
  const prevRow = dfWithIndicators.getRow(j).toDict();

  const criticalIndicatorsExist = criticalIndicators.every(col => lastRow[col] !== undefined && !isNaN(lastRow[col]));
  if (!criticalIndicatorsExist) {
    return ['none', 0, 0, 0, 'critical indicators missing/NaN'];
  }

  const cp = lastRow.close;
  const atr = lastRow.atr;
  const dynamicMultiplier = lastRow.dynamic_multiplier;

  if (atr <= 0 || isNaN(atr) || isNaN(dynamicMultiplier)) {
    return ['none', 0, 0, 0, 'bad atr or dynamic multiplier'];
  }

  const riskDistance = atr * dynamicMultiplier;

  const htfTrend = await higherTfTrend(symbol);
  if (htfTrend === 'none') {
    return ['none', 0, 0, 0, 'htf neutral'];
  }

  const currentBarTimestamp = lastRow.time; // Assuming 'time' column is the timestamp
  if (symbol in lastSignalBar && (currentBarTimestamp - lastSignalBar[symbol]) < (MIN_BARS_BETWEEN_TRADES * TIMEFRAME * 60 * 1000)) { // Convert minutes to milliseconds
    return ['none', 0, 0, 0, 'cool-down period active'];
  }

  // Base conditions
  let longCond = (
    lastRow.ema_s > lastRow.ema_l &&
    prevRow.ema_s <= prevRow.ema_l &&
    cp > lastRow.trend_ema &&
    lastRow.rsi < RSI_OVERBOUGHT &&
    lastRow.vol_spike &&
    (htfTrend === 'long')
  );

  let shortCond = (
    lastRow.ema_s < lastRow.ema_l &&
    prevRow.ema_s >= prevRow.ema_l &&
    cp < lastRow.trend_ema &&
    lastRow.rsi > RSI_OVERSOLD &&
    lastRow.vol_spike &&
    (htfTrend === 'short')
  );

  // Ehlers Supertrend filter
  if (USE_EST_SLOW_FILTER) {
    longCond = longCond && (lastRow.est_slow === 1);
    shortCond = shortCond && (lastRow.est_slow === -1);
  }

  // Stochastic filter
  if (USE_STOCH_FILTER && 'stoch_k' in lastRow && 'stoch_d' in lastRow) {
    const stochKCurr = lastRow.stoch_k;
    const stochDCurr = lastRow.stoch_d;
    const stochKPrev = prevRow.stoch_k;
    const stochDPrev = prevRow.stoch_d;

    const longStochCond = (stochKCurr > stochDCurr && stochKPrev <= stochDPrev && stochKCurr < CONFIG.STOCH_OVERBOUGHT);
    const shortStochCond = (stochKCurr < stochDCurr && stochKPrev >= stochDPrev && stochKCurr > CONFIG.STOCH_OVERSOLD);

    longCond = longCond && longStochCond;
    shortCond = shortCond && shortStochCond;
  }

  // MACD filter
  if (USE_MACD_FILTER && 'macd_line' in lastRow && 'macd_signal' in lastRow) {
    const macdLineCurr = lastRow.macd_line;
    const macdSignalCurr = lastRow.macd_signal;
    const macdLinePrev = prevRow.macd_line;
    const macdSignalPrev = prevRow.macd_signal;

    const longMacdCond = (macdLineCurr > macdSignalCurr && macdLinePrev <= macdSignalPrev && macdLineCurr > 0);
    const shortMacdCond = (macdLineCurr < macdSignalCurr && macdLinePrev >= macdSignalPrev && macdLineCurr < 0);

    longCond = longCond && longMacdCond;
    shortCond = shortCond && shortMacdCond;
  }

  // ADX filter
  if (USE_ADX_FILTER && 'adx' in lastRow) {
    const adxCurr = lastRow.adx;
    const longAdxCond = (adxCurr > ADX_THRESHOLD);
    const shortAdxCond = (adxCurr > ADX_THRESHOLD);

    longCond = longCond && longAdxCond;
    shortCond = shortCond && shortAdxCond;
  }

  let signal = 'none';
  let tpPrice = null;
  let slPrice = null;
  let reason = 'no match';

  if (longCond) {
    signal = 'Buy';
    slPrice = cp - riskDistance;
    tpPrice = cp + (riskDistance * (REWARD_RISK_RATIO || 2.5));
    reason = 'EMA cross up, price above trend EMA, RSI not overbought, volume spike, HTF long';
  } else if (shortCond) {
    signal = 'Sell';
    slPrice = cp + riskDistance;
    tpPrice = cp - (riskDistance * (REWARD_RISK_RATIO || 2.5));
    reason = 'EMA cross down, price below trend EMA, RSI not oversold, volume spike, HTF short';
  }

  if (signal !== 'none') {
    lastSignalBar[symbol] = currentBarTimestamp;
  }

  return [signal, cp, slPrice, tpPrice, reason];
}

// ====================== 
// EQUITY GUARD 
// ====================== 
let equityReference = null;
async function emergencyStop() {
  const currentEquity = await bybitClient.getBalance();
  if (equityReference === null) {
    equityReference = currentEquity;
    logger.info(neon.info(`Initial equity reference set to ${equityReference.toFixed(2)} USDT.`));
    return false;
  }

  if (currentEquity <= 0) {
    logger.warning(neon.warn("Current equity is zero or negative. Cannot calculate drawdown."));
    return false;
  }

  if (currentEquity < equityReference) {
    const drawdown = ((equityReference - currentEquity) / equityReference) * 100;
    if (drawdown >= EMERGENCY_STOP_IF_DOWN_PCT) {
      logger.critical(neon.error(`!!! EMERGENCY STOP !!! Equity down ${drawdown.toFixed(1)}%. Shutting down bot.`));
      return true;
    }
  }
  return false;
}

// ====================== 
// MAIN LOOP 
// ====================== 
async function main() {
  await _initDb(); // Initialize SQLite DB

  const symbols = TRADING_SYMBOLS;
  if (!symbols || symbols.length === 0) {
    logger.info(neon.warn("No symbols configured. Exiting."));
    return;
  }

  const modeInfo = CONFIG.DRY_RUN ? neon.magenta('DRY RUN') : neon.green('LIVE');
  const testnetInfo = CONFIG.TESTNET ? neon.yellow('TESTNET') : neon.blue('MAINNET');
  logger.info(neon.info(`Starting trading bot in ${modeInfo} mode on ${testnetInfo}. Checking ${symbols.length} symbols.`));
  logger.info(neon.info("Bot started – Press Ctrl+C to stop."));

  let lastReconciliationTime = moment.utc();

  try {
    while (true) {
      const [localTime, utcTime] = getCurrentTime(CONFIG.TIMEZONE);
      logger.info(neon.dim(`Local Time: ${localTime.format('YYYY-MM-DD HH:mm:ss')} | UTC Time: ${utcTime.format('YYYY-MM-DD HH:mm:ss')}`));

      if (!isMarketOpen(localTime, CONFIG.MARKET_OPEN_HOUR, CONFIG.MARKET_CLOSE_HOUR)) {
        logger.info(neon.info(`Market is closed (${CONFIG.MARKET_OPEN_HOUR}:00-${CONFIG.MARKET_CLOSE_HOUR}:00 ${CONFIG.TIMEZONE}). Skipping this cycle. Waiting ${CONFIG.LOOP_WAIT_TIME_SECONDS} seconds.`));
        await setTimeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
        continue;
      }

      if (await emergencyStop()) break;

      const balance = await bybitClient.getBalance();
      if (balance === null || balance <= 0) {
        logger.error(neon.error(`Cannot connect to API or balance is zero/negative (${balance}). Waiting ${CONFIG.LOOP_WAIT_TIME_SECONDS} seconds and retrying.`));
        await setTimeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
        continue;
      }

      logger.info(neon.info(`Current balance: ${balance.toFixed(2)} USDT`));

      const currentPositionsOnExchange = await bybitClient.getPositions();
      const currentPositionsSymbolsOnExchange = {};
      currentPositionsOnExchange.forEach(p => {
        currentPositionsSymbolsOnExchange[p.symbol] = p;
      });
      logger.info(neon.info(`You have ${currentPositionsOnExchange.length} open positions on exchange: ${Object.keys(currentPositionsSymbolsOnExchange).join(', ')}`));

      // --- Position Reconciliation (Exchange vs. DB) ---
      if (utcTime.diff(lastReconciliationTime, 'minutes') >= POSITION_RECONCILIATION_INTERVAL_MINUTES) {
        logger.info(neon.cyan('Performing position reconciliation...'));
        await reconcilePositions(currentPositionsSymbolsOnExchange, utcTime);
        lastReconciliationTime = utcTime;
      }

      // --- Position Exit Manager (Time, Chandelier Exit, Fisher Transform, Fixed Profit, Trailing Stop) ---
      let activeDbTrades = await db.all("SELECT id, symbol, side, entry_time, entry_price, sl, tp, order_id FROM trades WHERE status = 'OPEN'");

      const exitTasks = [];
      for (const trade of activeDbTrades) {
        const positionInfo = currentPositionsSymbolsOnExchange[trade.symbol];
        exitTasks.push(manageTradeExit(trade.id, trade.symbol, trade.side, trade.entry_time, trade.entry_price, trade.sl, trade.tp, positionInfo, utcTime));
      }
      await Promise.all(exitTasks);

      // Refresh active_db_trades after exits
      activeDbTrades = await db.all("SELECT id, symbol, side FROM trades WHERE status = 'OPEN'");
      const currentDbPositionsSymbols = activeDbTrades.map(t => t.symbol);

      // --- Signal Search and Order Placement ---
      const signalTasks = [];
      for (const symbol of symbols) {
        if (currentDbPositionsSymbols.length >= MAX_POSITIONS) {
          logger.info(neon.info(`Max positions (${MAX_POSITIONS}) reached. Halting signal checks for this cycle.`));
          break;
        }

        if (currentDbPositionsSymbols.includes(symbol)) {
          logger.debug(neon.dim(`Skipping ${symbol} as there is already an open position in DB tracker.`));
          continue;
        }

        const openOrdersForSymbol = await bybitClient.getOpenOrders(symbol);
        if (openOrdersForSymbol.length >= MAX_OPEN_ORDERS_PER_SYMBOL) {
          logger.debug(neon.dim(`Skipping ${symbol} as there are ${openOrdersForSymbol.length} open orders (max ${MAX_OPEN_ORDERS_PER_SYMBOL}).`));
          continue;
        }

        signalTasks.push(processSymbolForSignal(symbol, balance, utcTime));
      }

      await Promise.all(signalTasks);

      logger.info(neon.info(`--- Cycle finished. Waiting ${CONFIG.LOOP_WAIT_TIME_SECONDS} seconds for next loop. ---`));
      await setTimeout(CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
    }
  } finally {
    if (db) await db.close();
  }
}

async function reconcilePositions(exchangePositions, utcTime) {
  const dbPositions = {};
  const rows = await db.all("SELECT id, order_id, symbol, side, status, entry_price FROM trades WHERE status = 'OPEN'");
  rows.forEach(row => {
    dbPositions[row.symbol] = { db_id: row.id, order_id: row.order_id, side: row.side, status: row.status, entry_price: row.entry_price };
  });

  // 1. Mark DB positions as CLOSED if not found on exchange
  for (const symbol in dbPositions) {
    if (!exchangePositions[symbol]) {
      logger.warning(neon.warn(`Position for ${symbol} found in DB (ID: ${dbPositions[symbol].db_id}) but not on exchange. Marking as CLOSED.`));
      const currentPrice = await bybitClient.getCurrentPrice(symbol);
      const pnl = currentPrice !== null ? (currentPrice - dbPositions[symbol].entry_price) * (dbPositions[symbol].side === 'Buy' ? 1 : -1) : 0;
      await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id = ?",
        ['CLOSED', utcTime.toISOString(), currentPrice, pnl, dbPositions[symbol].db_id]);
    }
  }

  // 2. Add exchange positions to DB if not found in DB
  for (const symbol in exchangePositions) {
    if (!dbPositions[symbol]) {
      logger.warning(neon.warn(`Position for ${symbol} found on exchange but not in DB. Adding as RECONCILED.`));
      const exInfo = exchangePositions[symbol];
      const entryPrice = parseFloat(exInfo.avgPrice) > 0 ? parseFloat(exInfo.avgPrice) : parseFloat(exInfo.markPrice);
      const pUuid = uuidv4();
      await db.run("INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [pUuid, exInfo.orderId || 'N/A', symbol, exInfo.side, parseFloat(exInfo.size),
        utcTime.toISOString(), entryPrice,
        parseFloat(exInfo.stopLoss || 0), parseFloat(exInfo.takeProfit || 0), // Use current SL/TP from exchange
        'RECONCILED', null, null, null]); // Mark as reconciled, no exit details yet
    }
  }
}

async function manageTradeExit(tradeId, symbol, side, entryTimeStr, entryPrice, slDb, tpDb, positionInfo, utcTime) {
  if (!positionInfo) {
    logger.info(neon.info(`Position for ${symbol} not found on exchange while managing trade ${tradeId}. Marking as CLOSED in DB tracker.`));
    const currentPrice = await bybitClient.getCurrentPrice(symbol);
    const pnl = currentPrice !== null ? (currentPrice - entryPrice) * (side === 'Buy' ? 1 : -1) : 0;
    await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
      ['CLOSED', utcTime.toISOString(), currentPrice, pnl, tradeId]);
    return;
  }

  const klines = await bybitClient.klines(symbol, TIMEFRAME, (CONFIG.MAX_HOLDING_CANDLES || 50) + 5);
  if (!klines || klines.length < 2) {
    logger.warning(neon.warn(`Not enough klines for ${symbol} to manage existing trade. Skipping exit check.`));
    return;
  }

  const dfWithIndicators = buildAllIndicators(klines);
  const lastRow = dfWithIndicators.getRow(dfWithIndicators.count() - 1).toDict();
  const prevRow = dfWithIndicators.getRow(dfWithIndicators.count() - 2).toDict(); // For Fisher check
  const currentPrice = lastRow.close;

  let reasonToExit = null;

  // Calculate PNL for fixed profit target
  let currentPnlPercentage = 0.0;
  if (entryPrice > 0) {
    if (side === 'Buy') {
      currentPnlPercentage = (currentPrice - entryPrice) / entryPrice;
    } else { // Sell
      currentPnlPercentage = (entryPrice - currentPrice) / entryPrice;
    }
  }

  // Fixed Profit Target Exit
  if (FIXED_PROFIT_TARGET_PCT > 0 && currentPnlPercentage >= FIXED_PROFIT_TARGET_PCT) {
    reasonToExit = `Fixed Profit Target (${(FIXED_PROFIT_TARGET_PCT * 100).toFixed(1)}%) reached (Current PnL: ${(currentPnlPercentage * 100).toFixed(1)}%)`;
  }

  // Chandelier Exit (Trailing Stop equivalent, dynamic update if active)
  let newSlPrice = slDb; // Start with current SL in DB
  if (TRAILING_STOP_ACTIVE) {
    let chSl;
    if (side === 'Buy') {
      chSl = lastRow.ch_long;
      if (chSl > newSlPrice) { // Only trail SL upwards
        newSlPrice = chSl;
      }
    } else if (side === 'Sell') {
      chSl = lastRow.ch_short;
      if (chSl < newSlPrice) { // Only trail SL downwards
        newSlPrice = chSl;
      }
    }

    const [pricePrec, _] = await bybitClient.getPrecisions(symbol);
    newSlPrice = parseFloat(newSlPrice.toFixed(pricePrec));

    // Only modify if SL moved significantly
    if (Math.abs(newSlPrice - slDb) / slDb > 0.0001) {
      await bybitClient.modifyPositionTpsl(symbol, parseFloat(tpDb.toFixed(pricePrec)), newSlPrice);
      await db.run("UPDATE trades SET sl = ? WHERE id=?", [newSlPrice, tradeId]);
      logger.debug(neon.dim(`[${symbol}] Trailing Stop Loss updated to ${newSlPrice.toFixed(4)}.`));
      slDb = newSlPrice; // Update for current check
    }

    // Check if price hit the *current* effective stop loss (either initial or trailed)
    if (side === 'Buy' && currentPrice <= slDb) {
      reasonToExit = `Stop Loss hit (current price ${currentPrice.toFixed(4)} <= SL ${slDb.toFixed(4)})`;
    } else if (side === 'Sell' && currentPrice >= slDb) {
      reasonToExit = `Stop Loss hit (current price ${currentPrice.toFixed(4)} >= SL ${slDb.toFixed(4)})`;
    }
  }

  // Fisher Transform Flip Early Exit
  if (reasonToExit === null && USE_FISHER_EXIT) {
    if (side === 'Buy' && lastRow.fisher < 0 && prevRow.fisher >= 0) {
      reasonToExit = `Fisher Transform (bearish flip: ${lastRow.fisher.toFixed(2)})`;
    } else if (side === 'Sell' && lastRow.fisher > 0 && prevRow.fisher <= 0) {
      reasonToExit = `Fisher Transform (bullish flip: ${lastRow.fisher.toFixed(2)})`;
    }
  }

  // Time-based Exit
  const entryDt = moment.utc(entryTimeStr);
  const elapsedMinutes = utcTime.diff(entryDt, 'minutes');
  const elapsedCandles = elapsedMinutes / TIMEFRAME;
  if (reasonToExit === null && elapsedCandles >= (CONFIG.MAX_HOLDING_CANDLES || 50)) {
    reasonToExit = `Max holding candles (${CONFIG.MAX_HOLDING_CANDLES}) exceeded`;
  }

  if (reasonToExit) {
    logger.info(neon.magenta(`Closing ${side} position for ${symbol} due to: ${reasonToExit}`));
    await bybitClient.cancelAllOpenOrders(symbol);
    await setTimeout(500); // 0.5 seconds
    await bybitClient.closePosition(symbol);

    const pnl = (currentPrice - entryPrice) * (side === 'Buy' ? 1 : -1);
    await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
      ['CLOSED', utcTime.toISOString(), currentPrice, pnl, tradeId]);
    logger.info(neon.info(`Trade ${tradeId} for ${symbol} marked as CLOSED in DB tracker. PNL: ${pnl.toFixed(2)} USDT`));
  }
}

async function processSymbolForSignal(symbol, balance, utcTime) {
  const klines = await bybitClient.klines(symbol, TIMEFRAME, 200);
  if (!klines || klines.length < MIN_KLINES_FOR_STRATEGY) {
    logger.warning(neon.warn(`Not enough klines data for ${symbol} (needed >${MIN_KLINES_FOR_STRATEGY}). Skipping.`));
    return;
  }

  const df = new DataFrame(klines);
  const [signal, currentPrice, slPrice, tpPrice, signalReason] = await generateSignal(symbol, df);

  const dfWithIndicators = buildAllIndicators(klines);
  if (!dfWithIndicators.empty) {
    const lastRowIndicators = dfWithIndicators.getRow(dfWithIndicators.count() - 1).toDict();
    let logDetails = (
      `Price: ${currentPrice.toFixed(4)} | ` +
      `ATR (${CONFIG.ATR_PERIOD}): ${lastRowIndicators.atr.toFixed(4)} | ` +
      `Dyn Mult: ${lastRowIndicators.dynamic_multiplier.toFixed(2)} | ` +
      `EMA S(${CONFIG.EMA_SHORT_PERIOD}): ${lastRowIndicators.ema_s.toFixed(4)} | ` +
      `EMA L(${CONFIG.EMA_LONG_PERIOD}): ${lastRowIndicators.ema_l.toFixed(4)} | ` +
      `Trend EMA(${CONFIG.TREND_EMA_PERIOD}): ${lastRowIndicators.trend_ema.toFixed(4)} | ` +
      `RSI(${CONFIG.RSI_PERIOD}): ${lastRowIndicators.rsi.toFixed(2)} | ` +
      `Vol Spike: ${lastRowIndicators.vol_spike ? 'Yes' : 'No'} | ` +
      `EST Slow: ${lastRowIndicators.est_slow.toFixed(2)} | ` +
      `Fisher: ${lastRowIndicators.fisher.toFixed(2)}`
    );
    if (USE_STOCH_FILTER) {
      logDetails += ` | Stoch K/D: ${lastRowIndicators.stoch_k.toFixed(2)}/${lastRowIndicators.stoch_d.toFixed(2)}`;
    }
    if (USE_MACD_FILTER) {
      logDetails += ` | MACD Line/Sig: ${lastRowIndicators.macd_line.toFixed(2)}/${lastRowIndicators.macd_signal.toFixed(2)}`;
    }
    if (USE_ADX_FILTER) {
      logDetails += ` | ADX: ${lastRowIndicators.adx.toFixed(2)}`;
    }
    logger.debug(neon.dim(`[${symbol}] Indicators: ${logDetails}`));
  }

  if (signal === 'none') {
    logger.debug(neon.dim(`[${symbol}] No trading signal (${signalReason}).`));
    return;
  }

  logger.info(neon.info(`${signal === 'Buy' ? neon.green(signal) : neon.red(signal)} SIGNAL for ${symbol} ${signal === 'Buy' ? '📈' : '📉'}`));
  logger.info(neon.info(`[${symbol}] Reasoning: ${signalReason}. Calculated TP: ${tpPrice !== null ? tpPrice.toFixed(4) : 'N/A'}, SL: ${slPrice !== null ? slPrice.toFixed(4) : 'N/A'}`));

  const [pricePrecision, qtyPrecision] = await bybitClient.getPrecisions(symbol);

  const capitalForRisk = balance;
  const riskAmountUsdt = capitalForRisk * RISK_PER_TRADE_PCT;

  const riskDistance = slPrice !== null ? Math.abs(currentPrice - slPrice) : 0;
  if (riskDistance <= 0) {
    logger.warning(neon.warn(`[${symbol}] Calculated risk_distance is zero or negative. Skipping order.`));
    return;
  }

  const orderQtyRiskBased = riskAmountUsdt / riskDistance;
  const maxNotionalQty = (CONFIG.MAX_NOTIONAL_PER_TRADE_USDT || 1e9) / currentPrice;
  const orderQtyCalculated = Math.min(orderQtyRiskBased, maxNotionalQty);
  const orderQty = parseFloat(orderQtyCalculated.toFixed(qtyPrecision));

  if (orderQty <= 0) {
    logger.warning(neon.warn(`[${symbol}] Calculated order quantity is zero or negative (${orderQty}). Skipping order.`));
    return;
  }

  await bybitClient.setMarginModeAndLeverage(symbol, MARGIN_MODE, LEVERAGE);
  await setTimeout(500); // 0.5 seconds

  let orderId = null;
  const orderTypeConfig = ORDER_TYPE.toLowerCase();

  const [bestBid, bestAsk] = await bybitClient.getOrderbookLevels(symbol);

  if (orderTypeConfig === 'limit') {
    let limitExecutionPrice = null;
    if (signal === 'Buy' && bestBid !== null && (currentPrice - bestBid) < (currentPrice * PRICE_DETECTION_THRESHOLD_PCT)) {
      limitExecutionPrice = parseFloat(bestBid.toFixed(pricePrecision));
      logger.info(neon.info(`[${symbol}] Price near best bid at ${bestBid.toFixed(4)}. Placing Limit Order to Buy at bid.`));
    } else if (signal === 'Sell' && bestAsk !== null && (bestAsk - currentPrice) < (currentPrice * PRICE_DETECTION_THRESHOLD_PCT)) {
      limitExecutionPrice = parseFloat(bestAsk.toFixed(pricePrecision));
      logger.info(neon.info(`[${symbol}] Price near best ask at ${bestAsk.toFixed(4)}. Placing Limit Order to Sell at ask.`));
    } else {
      limitExecutionPrice = parseFloat(currentPrice.toFixed(pricePrecision));
      logger.info(neon.info(`[${symbol}] No specific S/R condition for limit. Placing Limit Order at current price ${limitExecutionPrice.toFixed(4)}.`));
    }

    if (limitExecutionPrice) {
      orderId = await bybitClient.placeLimitOrder(
        symbol, signal, limitExecutionPrice, orderQty,
        tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
        slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null,
        POST_ONLY ? 'PostOnly' : 'GTC'
      );
    }
  } else if (orderTypeConfig === 'conditional') {
    let triggerPrice = null;
    if (signal === 'Buy') {
      triggerPrice = currentPrice * (1 + BREAKOUT_TRIGGER_PERCENT);
    } else {
      triggerPrice = currentPrice * (1 - BREAKOUT_TRIGGER_PERCENT);
    }

    triggerPrice = parseFloat(triggerPrice.toFixed(pricePrecision));
    logger.info(neon.info(`[${symbol}] Placing Conditional Market Order triggered at ${triggerPrice.toFixed(4)}.`));
    orderId = await bybitClient.placeConditionalOrder(
      symbol, signal, orderQty, triggerPrice,
      'Market', null,
      tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
      slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null
    );
  } else { // Market Order
    logger.info(neon.info(`[${symbol}] Placing Market Order.`));
    orderId = await bybitClient.placeMarketOrder(
      symbol, signal, orderQty,
      tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
      slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null
    );
  }

  if (orderId) {
    await db.run("INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
      [uuidv4(), orderId, symbol, signal, orderQty, utcTime.toISOString(), currentPrice, slPrice, tpPrice, 'OPEN', null, null, null]);
    logger.info(neon.info(`New trade logged for ${symbol} (${signal} ${orderQty}). Order ID: ${orderId}`));
  }
}

// ====================== 
// LAUNCH 
// ====================== 
(async () => {
    try {
      await main();
    } catch (e) {
      if (e.message === "User interrupted") {
        logger.info(neon.info("Bot stopped by user via KeyboardInterrupt."));
      } else {
        logger.critical(neon.error(`Bot terminated due to an unexpected error: ${e.message}`), e);
      }
    } finally {
      // Any final cleanup if needed
    }
})();
