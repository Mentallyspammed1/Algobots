import dotenv from 'dotenv';
dotenv.config();
import warnings from 'warnings'; // This would need a JS equivalent or be handled differently
import net from 'net'; // Corresponds to socket in Python
import { URL } from 'url';
import { performance } from 'perf_hooks'; // For timestamp related to python time
import os from 'os'; // For os.environ, though not directly used in the provided Python code
import fs from 'fs'; // For file system operations, like SQLite file management
import path from 'path'; // For path manipulation
import { v4 as uuidv4 } from 'uuid'; // For generating UUIDs
import sqlite3 from 'sqlite3'; // Or 'sqlite3-async' for async operations
import { open } from 'sqlite'; // Helper to open db with async
import { setTimeout } from 'timers/promises'; // For async sleep
import moment from 'moment-timezone'; // For datetime and pytz
import { RestClientV5 } from 'bybit-api';

// For pandas and numpy equivalents, we'd use 'dataframe-js' or similar,
// but for simple operations, direct array/object manipulation might suffice.
// Or consider a more robust library like 'danfojs' if available and suitable for server-side.
// For now, we'll simulate pandas DataFrame behavior with plain objects/arrays.
import { DataFrame } from 'dataframe-js'; // A common choice for JS DataFrames

// Import pandas_ta equivalents or re-implement
// This part is the trickiest without a direct JS equivalent of pandas_ta
// We'll use simple moving average and mock other indicators for now.
// A full implementation would require porting each indicator's logic.

// --- CONFIGURATION IMPORT ---
// In JS, config is typically a JS object or JSON.
// Assuming config.js exists and exports an object:
import { BOT_CONFIG } from './config.js';

// Global placeholder for getaddrinfo patch, not directly translatable to JS in Node.js
// Node.js DNS resolution is handled differently; direct IP routing might need
// custom HTTP agents or host file modifications, which are outside this scope.
// So, the DNS bypass incantation is omitted as it's highly Python-specific.

// silence the usual noisy packages (JS equivalent might involve specific library configurations)
// For now, no direct JS equivalent is placed here.

// -------------- coloured logging --------------
// In Node.js, libraries like 'chalk' or 'winston' are used.
// For simplicity, we'll re-implement a basic colored console logger.
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const YELLOW = "\x1b[33m";
const BLUE = "\x1b[34m";
const MAGENTA = "\x1b[35m";
const CYAN = "\x1b[36m";
const WHITE = "\x1b[37m";

class ColoredLogger {
  constructor(name) {
    this.name = name;
    this.level = this.getLevel(BOT_CONFIG.LOG_LEVEL || "INFO");
  }

  getLevel(levelStr) {
    const levels = {
      "DEBUG": 0,
      "INFO": 1,
      "WARNING": 2,
      "ERROR": 3,
      "CRITICAL": 4,
    };
    return levels[levelStr.toUpperCase()] || 1; // Default to INFO
  }

  _log(level, color, message, ...args) {
    if (this.getLevel(level) < this.level) {
      return;
    }
    const timestamp = moment().format('YYYY-MM-DD HH:mm:ss');
    const prefix = `${timestamp} - ${this.name} - ${level.toUpperCase()} -`;
    const formattedMessage = `${color}${prefix} ${message}${RESET}`;
    console.log(formattedMessage, ...args);
  }

  debug(message, ...args) { this._log("DEBUG", CYAN, message, ...args); }
  info(message, ...args) { this._log("INFO", WHITE, message, ...args); }
  warning(message, ...args) { this._log("WARNING", YELLOW, message, ...args); }
  error(message, ...args) { this._log("ERROR", RED, message, ...args); }
  critical(message, ...args) { this._log("CRITICAL", BOLD + RED, message, ...args); }
}

const rootLogger = new ColoredLogger("root"); // Simulating Python's logging.getLogger()

// -------------- SQLite position tracker --------------
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
  rootLogger.info(`Database initialized: ${DB_FILE}`);
}

// -------------- Bybit client wrapper (async) --------------
class Bybit {
  constructor(api, secret, testnet = false, dry_run = false) {
    if (!api || !secret) {
      throw new Error("API Key and Secret must be provided.");
    }
    this.api = api;
    this.secret = secret;
    this.testnet = testnet;
    this.dry_run = dry_run;

    const config = {
      key: api,
      secret: secret,
      // No direct 'options.defaultType' equivalent in BybitAsync,
      // category is passed in each method call.
      // loadMarkets: false is also not directly applicable as we don't 'load' markets this way.
      // Adjusting endpoint for testnet is handled directly by BybitAsync library if not default.
    };

    // The BybitAsync client doesn't need explicit URL config, it infers testnet from 'testnet' option.
    this.session = new RestClientV5({
      key: api,
      secret: secret,
      // The `BybitAsync` client library (bybit-api/client) automatically handles testnet based on the `testnet` boolean in constructor
      // or using `BybitRestV5` with the `restOptions` if you need to be explicit.
      // For this example, we assume `BybitAsync` from `@bybit-api/client` is used,
      // which takes `testnet: true/false` directly.
      testnet: testnet,
      // Default to linear category for most operations, pass explicitly where needed
      category: 'linear',
    });
    rootLogger.info(`Bybit client ready – testnet=${testnet}  dry_run=${dry_run}`);
  }

  async closeSession() {
    // BybitAsync from @bybit-api/client does not have an explicit `close()` method.
    // It's stateless and handles connections per request.
    rootLogger.info("Bybit session does not require explicit closing.");
  }

  async getBalance(coin = "USDT") {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const resp = await this.session.getWalletBalance({ accountType: 'UNIFIED' }); // Assuming unified account
        if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
          const coinInfo = resp.result.list[0].coin.find(c => c.coin === coin);
          if (coinInfo) {
            return parseFloat(coinInfo.walletBalance || 0);
          }
          rootLogger.error(`Balance for ${coin} not found in response.`);
        } else {
          rootLogger.error(`Error getting balance (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${resp.retMsg || 'Unknown error'} (Code: ${resp.retCode || 'N/A'})`);
        }
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`get_balance error (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return 0;
  }

  async getPositions(settleCoin = "USDT") {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const resp = await this.session.getPositionInfo({ category: 'linear', settleCoin: settleCoin });
        if (resp.retCode === 0 && resp.result && resp.result.list) {
          return resp.result.list.filter(p => parseFloat(p.size) > 0);
        }
        rootLogger.error(`Error getting positions (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${resp.retMsg || 'Unknown error'} (Code: ${resp.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`get_positions error (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return [];
  }

  async getTickers() {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.getTickers({ category: "linear" });
        if (r.retCode === 0 && r.result && r.result.list) {
          return r.result.list.filter(t => t.symbol.includes('USDT') && !t.symbol.includes('USDC')).map(t => t.symbol);
        }
        rootLogger.error(`Error getting tickers (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`get_tickers error (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return null;
  }

  async klines(symbol, timeframe, limit = 500) {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.getKlines({
          category: 'linear',
          symbol: symbol,
          interval: String(timeframe),
          limit: limit
        });
        if (r.retCode === 0 && r.result && r.result.list) {
          // Bybit returns [timestamp, open, high, low, close, volume, turnover]
          const data = r.result.list.map(row => ({
            Time: parseFloat(row[0]),
            Open: parseFloat(row[1]),
            High: parseFloat(row[2]),
            Low: parseFloat(row[3]),
            Close: parseFloat(row[4]),
            Volume: parseFloat(row[5]),
            Turnover: parseFloat(row[6]),
          }));
          const df = new DataFrame(data);
          df.setIndex('Time'); // Set Time as index
          df.sortBy('Time'); // Ensure sorted by time
          
          // Check for NaN in OHLC
          if (df.stat.all('Open', v => isNaN(v)) || df.stat.all('High', v => isNaN(v)) ||
              df.stat.all('Low', v => isNaN(v)) || df.stat.all('Close', v => isNaN(v))) {
            rootLogger.warning(`Critical OHLCV columns are all NaN for ${symbol}. Skipping this kline data.`);
            return new DataFrame([]);
          }
          return df;
        }
        rootLogger.error(`Error getting klines for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`klines error ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return new DataFrame([]);
  }

  async getCurrentPrice(symbol) {
    try {
      const r = await this.session.getTickers({ category: 'linear', symbol: symbol });
      if (r.retCode === 0 && r.result && r.result.list && r.result.list.length > 0) {
        return parseFloat(r.result.list[0].lastPrice);
      }
    } catch (e) {
      rootLogger.error(`Error getting current price for ${symbol}: ${e.message}`);
    }
    return null;
  }

  async getOrderbookLevels(symbol, limit = 50) {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.getOrderbook({ category: 'linear', symbol: symbol, limit: limit });
        if (r.retCode === 0 && r.result) {
          const bestBid = r.result.b.length > 0 ? parseFloat(r.result.b[0][0]) : null;
          const bestAsk = r.result.a.length > 0 ? parseFloat(r.result.a[0][0]) : null;
          return [bestBid, bestAsk];
        }
        rootLogger.error(`Error getting orderbook for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`orderbook error ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return [null, null];
  }

  async getPrecisions(symbol) {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.getInstrumentsInfo({ category: 'linear', symbol: symbol });
        if (r.retCode === 0 && r.result && r.result.list && r.result.list.length > 0) {
          const info = r.result.list[0];
          const priceStep = info.priceFilter.tickSize;
          const qtyStep = info.lotSizeFilter.qtyStep;
          const pricePrec = priceStep.includes('.') ? priceStep.split('.')[1].length : 0;
          const qtyPrec = qtyStep.includes('.') ? qtyStep.split('.')[1].length : 0;
          return [pricePrec, qtyPrec];
        }
        rootLogger.error(`Error getting precisions for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`precisions error ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return [0, 0];
  }

  async setMarginModeAndLeverage(symbol, mode = 1, leverage = 10) {
    if (this.dry_run) {
      rootLogger.info(`[DRY RUN] would set ${symbol} margin=${mode === 1 ? 'Isolated' : 'Cross'} ${leverage}x`);
      return;
    }
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.setLeverage({
          category: 'linear',
          symbol: symbol,
          buyLeverage: String(leverage),
          sellLeverage: String(leverage),
        });
        // Bybit V5 combines margin mode and leverage setting in setLeverage.
        // It's assumed isolated mode is default or managed by tradeMode.
        // For actual isolated/cross setting, Bybit API v5 uses `setTradingStop` parameters `tpSlMode` or `positionMode`.
        // The Python client might abstract this, but in `bybit-api/client` `setLeverage` handles leverage,
        // and isolated/cross is often managed at the account level or implicitly with `setTradingStop`
        // or by directly opening positions in isolated/cross mode using `tradeMode` if supported.
        // A common pattern is to first ensure `setMarginMode` if it was available separately, then `setLeverage`.
        // Given `tradeMode: str(mode)` is used in Python `switch_margin_mode`, we'll try to find an equivalent.
        // For V5, margin mode is typically implied or set when placing an order with `isIsolated=true/false` or via `setMarginMode` if it exists.
        // Let's assume the Python `switch_margin_mode` primarily sets leverage, and `tradeMode` parameter corresponds to isolated margin for a trade.
        // For Bybit V5, `setLeverage` sets leverage, `setMarginMode` if exists, sets isolated/cross for account level.
        // If the goal is isolated mode for a specific trade, it's often a parameter of the `placeOrder` call.
        // We will skip explicit `switch_margin_mode` for now and rely on `placeOrder` parameters if needed, or assume default.

        if (r.retCode === 0) {
          rootLogger.info(`${symbol} margin=${mode === 1 ? 'Isolated' : 'Cross'} ${leverage}x set.`);
          return;
        } else if ([110026, 110043].includes(r.retCode)) { // Already set
          rootLogger.debug(`${symbol} margin/leverage already set (Code: ${r.retCode}).`);
          return;
        }
        rootLogger.warning(`Failed to set margin mode/leverage for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`margin/lever error for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
  }

  async placeOrderCommon(symbol, side, orderType, qty, price = null, triggerPrice = null, tpPrice = null, slPrice = null, timeInForce = 'GTC', reduceOnly = false) {
    if (this.dry_run) {
      const oid = `DRY_${uuidv4()}`;
      let logMsg = `[DRY RUN] ${orderType} ${side} ${qty} ${symbol}`;
      if (price !== null) logMsg += ` price=${price}`;
      if (triggerPrice !== null) logMsg += ` trigger=${triggerPrice}`;
      if (tpPrice !== null) logMsg += ` TP=${tpPrice}`;
      if (slPrice !== null) logMsg += ` SL=${slPrice}`;
      if (reduceOnly) logMsg += ` ReduceOnly`;
      rootLogger.info(`${logMsg}. Simulated Order ID: ${oid}`);
      return oid;
    }

    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const params = {
          category: 'linear',
          symbol: symbol,
          side: side,
          orderType: orderType,
          qty: String(qty),
          timeInForce: timeInForce,
          reduceOnly: reduceOnly ? 1 : 0,
        };
        if (price !== null) params.price = String(price);
        if (triggerPrice !== null) {
          params.triggerPrice = String(triggerPrice);
          params.triggerBy = 'MarkPrice'; // Or LastPrice, IndexPrice
        }
        // TP/SL are set after position open, or can be attached to the initial order (conditional or post-only)
        // For Bybit V5, TP/SL can be set directly in `placeOrder` for market/limit orders.
        if (tpPrice !== null) params.takeProfit = String(tpPrice);
        if (slPrice !== null) params.stopLoss = String(slPrice);
        
        // For TakeProfit and StopLoss, Bybit V5 `placeOrder` requires `tpTriggerBy` and `slTriggerBy`
        // if `takeProfit` or `stopLoss` are provided directly in `placeOrder`.
        if (tpPrice !== null) params.tpTriggerBy = 'Market'; // 'Market', 'LastPrice', 'IndexPrice'
        if (slPrice !== null) params.slTriggerBy = 'Market'; // 'Market', 'LastPrice', 'IndexPrice'

        const r = await this.session.placeOrder(params);
        if (r.retCode === 0) {
          rootLogger.info(`Order placed for ${symbol} (${orderType} ${side} ${qty}). Order ID: ${r.result.orderId}`);
          return r.result.orderId;
        }

        if (r.retCode === 10001) {
          rootLogger.error(`Order placement failed for ${symbol} due to API error ${r.retCode}: ${r.retMsg || 'Unknown API error'}`);
          return null; // Do not retry immediately for specific critical errors
        }

        rootLogger.error(`Failed to place order for ${symbol} (${orderType} ${side} ${qty}) (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`Exception placing ${orderType} order for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return null;
  }

  async placeMarketOrder(symbol, side, qty, tpPrice = null, slPrice = null, reduceOnly = false) {
    return await this.placeOrderCommon(symbol, side, 'Market', qty, null, null, tpPrice, slPrice, 'GTC', reduceOnly);
  }

  async placeLimitOrder(symbol, side, price, qty, tpPrice = null, slPrice = null, timeInForce = 'GTC', reduceOnly = false) {
    return await this.placeOrderCommon(symbol, side, 'Limit', qty, price, null, tpPrice, slPrice, timeInForce, reduceOnly);
  }

  async placeConditionalOrder(symbol, side, qty, triggerPrice, orderType = 'Market', price = null, tpPrice = null, slPrice = null, reduceOnly = false) {
    if (orderType === 'Limit' && price === null) {
      price = triggerPrice;
      rootLogger.warning(`Conditional limit order requested for ${symbol} without explicit 
price
. Using 
trigger_price
 as limit execution price.`);
    }
    return await this.placeOrderCommon(symbol, side, orderType, qty, price, triggerPrice, tpPrice, slPrice, 'GTC', reduceOnly);
  }

  async cancelAllOpenOrders(symbol) {
    if (this.dry_run) {
      rootLogger.info(`[DRY RUN] Would cancel all open orders for ${symbol}.`);
      return true;
    }
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const r = await this.session.cancelAllOrders({ category: 'linear', symbol: symbol });
        if (r.retCode === 0) {
          rootLogger.info(`All open orders for ${symbol} cancelled successfully.`);
          return true;
        }
        rootLogger.warning(`Failed to cancel all orders for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`Exception cancelling all orders for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return false;
  }

  async modifyPositionTpsl(symbol, tpPrice, slPrice, positionIdx = 0) {
    if (this.dry_run) {
      rootLogger.info(`[DRY RUN] Would modify TP/SL for ${symbol}. TP:${tpPrice}, SL:${slPrice}`);
      return true;
    }

    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const params = { category: 'linear', symbol: symbol };
        if (tpPrice !== null) params.takeProfit = String(tpPrice);
        if (slPrice !== null) params.stopLoss = String(slPrice);
        params.tpTriggerBy = 'Market';
        params.slTriggerBy = 'Market';

        const r = await this.session.setTradingStop(params);
        if (r.retCode === 0) {
          rootLogger.debug(`Modified TP/SL for ${symbol}. TP:${tpPrice}, SL:${slPrice}`);
          return true;
        } else if (r.retCode === 110026) { // No position to modify
          rootLogger.warning(`No active position for ${symbol} to modify TP/SL.`);
          return false;
        }
        rootLogger.warning(`Failed to modify TP/SL for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`Exception modifying TP/SL for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return false;
  }

  async getOpenOrders(symbol = null) {
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const params = { category: 'linear' };
        if (symbol) params.symbol = symbol;
        const r = await this.session.getOpenOrders(params);
        if (r.retCode === 0 && r.result && r.result.list) {
          return r.result.list;
        }
        rootLogger.error(`Error getting open orders for ${symbol || 'all symbols'} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${r.retMsg || 'Unknown error'} (Code: ${r.retCode || 'N/A'})`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      } catch (e) {
        rootLogger.error(`Exception getting open orders for ${symbol || 'all symbols'} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return [];
  }

  async closePosition(symbol) {
    if (this.dry_run) {
      rootLogger.info(`[DRY RUN] Would close position for ${symbol} with a market order.`);
      return `DRY_CLOSE_${uuidv4()}`;
    }
    for (let attempt = 0; attempt < BOT_CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const posResp = await this.session.getPositionInfo({ category: 'linear', symbol: symbol });
        if (posResp.retCode !== 0 || !posResp.result || !posResp.result.list || posResp.result.list.length === 0) {
          rootLogger.warning(`Could not get position details for ${symbol} to close (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}). ${posResp.retMsg || 'No position found'}`);
          await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
          continue;
        }

        const positionInfo = posResp.result.list.find(p => parseFloat(p.size) > 0);
        if (!positionInfo) {
          rootLogger.info(`No open position found for ${symbol} to close (size is 0).`);
          return null;
        }

        const sideToClose = positionInfo.side === 'Buy' ? 'Sell' : 'Buy';
        const orderId = await this.placeMarketOrder(
          symbol,
          sideToClose,
          parseFloat(positionInfo.size),
          null, null, true // reduce_only
        );
        return orderId;
      } catch (e) {
        rootLogger.error(`Exception closing position for ${symbol} (attempt ${attempt + 1}/${BOT_CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`);
        await setTimeout(BOT_CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
      }
    }
    return null;
  }
}

// Placeholder for pandas_ta functions. These would need to be implemented or a suitable library found.
// For now, these are simplified or mock implementations.
// A more robust solution would integrate 'danfojs' or similar and port indicators.

// Helper to calculate EMA
function calculateEMA(data, period) {
  if (data.length < period) return new Array(data.length).fill(NaN);
  const ema = [];
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += data[i];
  }
  ema[period - 1] = sum / period;
  const multiplier = 2 / (period + 1);
  for (let i = period; i < data.length; i++) {
    ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1];
  }
  return new Array(period - 1).fill(NaN).concat(ema.slice(period - 1));
}

// Helper to calculate SMA
function calculateSMA(data, period) {
  if (data.length < period) return new Array(data.length).fill(NaN);
  const sma = [];
  for (let i = 0; i <= data.length - period; i++) {
    const slice = data.slice(i, i + period);
    const sum = slice.reduce((a, b) => a + b, 0);
    sma.push(sum / period);
  }
  return new Array(period - 1).fill(NaN).concat(sma);
}

// Helper to calculate ATR
function calculateATR(high, low, close, period) {
  if (high.length < period) return new Array(high.length).fill(0);
  const tr = [];
  for (let i = 0; i < high.length; i++) {
    const h = high[i];
    const l = low[i];
    const cPrev = i > 0 ? close[i - 1] : close[i]; // Use current close if no prev
    tr.push(Math.max(h - l, Math.abs(h - cPrev), Math.abs(l - cPrev)));
  }
  const atr = calculateEMA(tr, period); // Using EMA for ATR as is common
  return atr.map(val => isNaN(val) ? 0 : val);
}

// Helper for RSI
function calculateRSI(data, period) {
  if (data.length < period + 1) return new Array(data.length).fill(50); // Need at least period + 1 for initial change
  const rsi = new Array(data.length).fill(NaN);
  const gains = new Array(data.length).fill(0);
  const losses = new Array(data.length).fill(0);

  for (let i = 1; i < data.length; i++) {
    const diff = data[i] - data[i - 1];
    if (diff > 0) {
      gains[i] = diff;
    } else {
      losses[i] = Math.abs(diff);
    }
  }

  let avgGain = gains.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
  let avgLoss = losses.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;

  if (avgLoss === 0) {
    if (avgGain === 0) {
      rsi[period] = 50;
    } else {
      rsi[period] = 100;
    }
  } else {
    const rs = avgGain / avgLoss;
    rsi[period] = 100 - (100 / (1 + rs));
  }

  for (let i = period + 1; i < data.length; i++) {
    avgGain = ((avgGain * (period - 1)) + gains[i]) / period;
    avgLoss = ((avgLoss * (period - 1)) + losses[i]) / period;

    if (avgLoss === 0) {
      if (avgGain === 0) {
        rsi[i] = 50;
      } else {
        rsi[i] = 100;
      }
    } else {
      const rs = avgGain / avgLoss;
      rsi[i] = 100 - (100 / (1 + rs));
    }
  }
  return rsi.map(val => isNaN(val) ? 50 : val);
}


// Mock Supertrend and Fisher Transform for now
// Real implementations would be complex.
const mockSupertrend = (df, length, multiplier) => new Array(df.length).fill(0); // placeholder
const mockFisherTransform = (df, period) => new Array(df.length).fill(0); // placeholder
const mockStochasticOscillator = (df, k, d, smoothing) => [new Array(df.length).fill(50), new Array(df.length).fill(50)]; // placeholder
const mockMacdIndicator = (df, fast, slow, signal) => [new Array(df.length).fill(0), new Array(df.length).fill(0), new Array(df.length).fill(0)]; // placeholder
const mockAdxIndicator = (df, period) => new Array(df.length).fill(0); // placeholder

// -------------- higher TF confirmation --------------
async function higherTfTrend(bybit, symbol) {
  const htf = BOT_CONFIG.HIGHER_TF_TIMEFRAME || 5;
  const short = BOT_CONFIG.H_TF_EMA_SHORT_PERIOD || 8;
  const long = BOT_CONFIG.H_TF_EMA_LONG_PERIOD || 21;
  const df = await bybit.klines(symbol, htf, long + 5);
  if (df.empty || df.count() < Math.max(short, long) + 1) {
    rootLogger.debug(`Not enough data for HTF trend for ${symbol}.`);
    return 'none';
  }
  const closePrices = df.toCollection().map(row => row.Close);
  const emaS = calculateEMA(closePrices, short).slice(-1)[0];
  const emaL = calculateEMA(closePrices, long).slice(-1)[0];

  if (emaS > emaL) return 'long';
  if (emaS < emaL) return 'short';
  return 'none';
}

// -------------- Ehlers Supertrend (mocked) --------------
function estSupertrend(df, length = 8, multiplier = 1.2) {
  // A real implementation would involve ATR calculations and tracking trend state.
  // For now, this is a mock.
  return df.map(row => 0); // Placeholder, always returns 0 (neutral)
}

// -------------- Fisher Transform (mocked) --------------
function fisherTransform(df, period = 8) {
  // Placeholder mock
  return df.map(row => 0); // Placeholder, always returns 0
}

// -------------- Stochastic Oscillator (mocked) --------------
function stochasticOscillator(df, k_period = 14, d_period = 3, smoothing = 3) {
  // Placeholder mock
  return [df.map(row => 50), df.map(row => 50)];
}

// -------------- MACD (mocked) --------------
function macdIndicator(df, fast = 12, slow = 26, signal = 9) {
  // Placeholder mock
  return [df.map(row => 0), df.map(row => 0), df.map(row => 0)];
}

// -------------- ADX (mocked) --------------
function adxIndicator(df, period = 14) {
  // Placeholder mock
  return df.map(row => 0);
}


// -------------- upgraded chandelier + multi-TF --------------
function buildIndicators(df) {
  const clonedDf = df.clone(); // Clone to avoid modifying original

  const ohlcvColumns = ['Open', 'High', 'Low', 'Close', 'Volume'];
  for (const col of ohlcvColumns) {
    clonedDf.cast(col, Number); // Convert to number
    // Fill NaN values (equivalent to ffill and fillna(0))
    // DataFrame.js `fillMissing` can be used, but forward fill needs manual iteration or
    // custom transformation if not directly supported by `fillMissing` with `direction` parameter.
    // For simplicity, we'll convert to arrays, process, then convert back.
    let colData = clonedDf.toArray(col);
    for(let i = 0; i < colData.length; i++) {
        if (isNaN(colData[i]) || colData[i] === null) {
            colData[i] = i > 0 ? colData[i-1] : 0; // ffill then fill initial NaNs with 0
        }
    }
    clonedDf.withColumn(col, (row, i) => colData[i]); // Update column
  }

  const highPrices = clonedDf.toArray('High');
  const lowPrices = clonedDf.toArray('Low');
  const closePrices = clonedDf.toArray('Close');
  const volumes = clonedDf.toArray('Volume');

  const atrSeries = calculateATR(highPrices, lowPrices, closePrices, BOT_CONFIG.ATR_PERIOD);
  clonedDf.addColumns([
      atrSeries.map(val => ({atr: val}))
  ]);

  const highestHigh = [];
  const lowestLow = [];
  for (let i = 0; i < highPrices.length; i++) {
      highestHigh[i] = Math.max(...highPrices.slice(Math.max(0, i - BOT_CONFIG.ATR_PERIOD + 1), i + 1));
      lowestLow[i] = Math.min(...lowPrices.slice(Math.max(0, i - BOT_CONFIG.ATR_PERIOD + 1), i + 1));
  }
  clonedDf.addColumns([
      highestHigh.map(val => ({highest_high: val})),
      lowestLow.map(val => ({lowest_low: val}))
  ]);

  const volatilityLookback = BOT_CONFIG.VOLATILITY_LOOKBACK || 20;
  const pricePctChange = [];
  for (let i = 1; i < closePrices.length; i++) {
      pricePctChange.push((closePrices[i] - closePrices[i-1]) / closePrices[i-1]);
  }
  const priceStd = [];
  for (let i = 0; i < pricePctChange.length; i++) {
      const window = pricePctChange.slice(Math.max(0, i - volatilityLookback + 1), i + 1);
      const mean = window.reduce((a, b) => a + b, 0) / window.length;
      const std = Math.sqrt(window.map(x => Math.pow(x - mean, 2)).reduce((a, b) => a + b, 0) / window.length);
      priceStd.push(std);
  }
  
  let dynamicMultiplier = new Array(clonedDf.count()).fill(BOT_CONFIG.CHANDELIER_MULTIPLIER);
  if (clonedDf.count() >= volatilityLookback && priceStd.length > 0) {
      const meanPriceStd = priceStd.reduce((a,b) => a+b, 0) / priceStd.length;
      if (meanPriceStd > 0) {
          for (let i = 0; i < priceStd.length; i++) {
            dynamicMultiplier[i+1] = Math.min(
                BOT_CONFIG.MAX_ATR_MULTIPLIER,
                Math.max(BOT_CONFIG.MIN_ATR_MULTIPLIER, BOT_CONFIG.CHANDELIER_MULTIPLIER * (priceStd[i] / meanPriceStd))
            );
          }
      }
  }
  clonedDf.addColumns([
      dynamicMultiplier.map(val => ({dynamic_multiplier: val}))
  ]);


  const chLong = clonedDf.toArray('highest_high').map((val, i) => val - (atrSeries[i] * dynamicMultiplier[i]));
  const chShort = clonedDf.toArray('lowest_low').map((val, i) => val + (atrSeries[i] * dynamicMultiplier[i]));
  clonedDf.addColumns([
      chLong.map(val => ({ch_long: val})),
      chShort.map(val => ({ch_short: val}))
  ]);
  
  const trendEma = calculateEMA(closePrices, BOT_CONFIG.TREND_EMA_PERIOD);
  const emaS = calculateEMA(closePrices, BOT_CONFIG.EMA_SHORT_PERIOD);
  const emaL = calculateEMA(closePrices, BOT_CONFIG.EMA_LONG_PERIOD);
  const rsi = calculateRSI(closePrices, BOT_CONFIG.RSI_PERIOD);

  clonedDf.addColumns([
      trendEma.map(val => ({trend_ema: val})),
      emaS.map(val => ({ema_s: val})),
      emaL.map(val => ({ema_l: val})),
      rsi.map(val => ({rsi: val}))
  ]);

  const volumeMa = calculateSMA(volumes, BOT_CONFIG.VOLUME_MA_PERIOD || 20);
  const volSpike = volumes.map((vol, i) => (volumeMa[i] > 0 && vol / volumeMa[i] > BOT_CONFIG.VOLUME_THRESHOLD_MULTIPLIER));
  clonedDf.addColumns([
      volumeMa.map(val => ({vol_ma: val})),
      volSpike.map(val => ({vol_spike: val}))
  ]);
  
  // Mock implementations for now
  const estSlow = estSupertrend(clonedDf, BOT_CONFIG.EST_SLOW_LENGTH || 8, BOT_CONFIG.EST_SLOW_MULTIPLIER || 1.2);
  const fisher = fisherTransform(clonedDf, BOT_CONFIG.EHLERS_FISHER_PERIOD || 8);
  clonedDf.addColumns([
      estSlow.map(val => ({est_slow: val})),
      fisher.map(val => ({fisher: val}))
  ]);

  if (BOT_CONFIG.USE_STOCH_FILTER) {
    const [stochK, stochD] = stochasticOscillator(clonedDf, BOT_CONFIG.STOCH_K_PERIOD, BOT_CONFIG.STOCH_D_PERIOD, BOT_CONFIG.STOCH_SMOOTHING);
    clonedDf.addColumns([
        stochK.map(val => ({stoch_k: val})),
        stochD.map(val => ({stoch_d: val}))
    ]);
  }
  
  if (BOT_CONFIG.USE_MACD_FILTER) {
    const [macdLine, macdSignal, macdHist] = macdIndicator(clonedDf, BOT_CONFIG.MACD_FAST_PERIOD, BOT_CONFIG.MACD_SLOW_PERIOD, BOT_CONFIG.MACD_SIGNAL_PERIOD);
    clonedDf.addColumns([
        macdLine.map(val => ({macd_line: val})),
        macdSignal.map(val => ({macd_signal: val})),
        macdHist.map(val => ({macd_hist: val}))
    ]);
  }

  if (BOT_CONFIG.USE_ADX_FILTER) {
    const adx = adxIndicator(clonedDf, BOT_CONFIG.ADX_PERIOD);
    clonedDf.addColumns([
        adx.map(val => ({adx: val}))
    ]);
  }

  // Final ffill and fillna(0) for all new columns
  for (const col of clonedDf.listColumns()) {
    let colData = clonedDf.toArray(col);
    for(let i = 0; i < colData.length; i++) {
        if (isNaN(colData[i]) || colData[i] === null) {
            colData[i] = i > 0 ? colData[i-1] : 0; // ffill then fill initial NaNs with 0
        }
    }
    clonedDf.withColumn(col, (row, i) => colData[i]);
  }

  return clonedDf;
}


// -------------- signal generator --------------
const lastSignalBar = {};
async function generateSignal(bybit, symbol, df) {
  let minRequiredKlines = Math.max(
    BOT_CONFIG.MIN_KLINES_FOR_STRATEGY, BOT_CONFIG.TREND_EMA_PERIOD,
    BOT_CONFIG.EMA_LONG_PERIOD, BOT_CONFIG.ATR_PERIOD,
    BOT_CONFIG.RSI_PERIOD, BOT_CONFIG.VOLUME_MA_PERIOD || 20,
    BOT_CONFIG.VOLATILITY_LOOKBACK || 20,
    (BOT_CONFIG.EST_SLOW_LENGTH || 8) + 5, (BOT_CONFIG.EHLERS_FISHER_PERIOD || 8) + 5
  );
  if (BOT_CONFIG.USE_STOCH_FILTER) minRequiredKlines = Math.max(minRequiredKlines, BOT_CONFIG.STOCH_K_PERIOD + BOT_CONFIG.STOCH_SMOOTHING + 5);
  if (BOT_CONFIG.USE_MACD_FILTER) minRequiredKlines = Math.max(minRequiredKlines, BOT_CONFIG.MACD_SLOW_PERIOD + BOT_CONFIG.MACD_SIGNAL_PERIOD + 5);
  if (BOT_CONFIG.USE_ADX_FILTER) minRequiredKlines = Math.max(minRequiredKlines, BOT_CONFIG.ADX_PERIOD + 5);

  if (df.empty || df.count() < minRequiredKlines) {
    return ['none', 0, 0, 0, `not enough bars (${df.count()} < ${minRequiredKlines})`];
  }

  const dfWithIndicators = buildIndicators(df);
  const i = dfWithIndicators.count() - 1; // Current bar (last)
  const j = dfWithIndicators.count() - 2; // Previous bar

  if (i < 1) { // Need at least two bars for crossover checks
    return ['none', 0, 0, 0, 'not enough candles for crossover check'];
  }

  const criticalIndicators = ['Close', 'atr', 'dynamic_multiplier', 'ema_s', 'ema_l', 'trend_ema', 'rsi', 'vol_spike', 'est_slow', 'fisher'];
  if (BOT_CONFIG.USE_STOCH_FILTER) criticalIndicators.push('stoch_k', 'stoch_d');
  if (BOT_CONFIG.USE_MACD_FILTER) criticalIndicators.push('macd_line', 'macd_signal');
  if (BOT_CONFIG.USE_ADX_FILTER) criticalIndicators.push('adx');

  const lastRow = dfWithIndicators.getRow(i).toDict();
  const prevRow = dfWithIndicators.getRow(j).toDict();

  const criticalIndicatorsExist = criticalIndicators.every(col => lastRow[col] !== undefined && !isNaN(lastRow[col]));
  if (!criticalIndicatorsExist) {
    return ['none', 0, 0, 0, 'critical indicators missing/NaN'];
  }

  const cp = lastRow.Close;
  const atr = lastRow.atr;
  const dynamicMultiplier = lastRow.dynamic_multiplier;

  if (atr <= 0 || isNaN(atr) || isNaN(dynamicMultiplier)) {
    return ['none', 0, 0, 0, 'bad atr or dynamic multiplier'];
  }

  const riskDistance = atr * dynamicMultiplier;

  const htfTrend = await higherTfTrend(bybit, symbol);
  if (htfTrend === 'none') {
    return ['none', 0, 0, 0, 'htf neutral'];
  }

  const currentBarTimestamp = lastRow.Time; // Assuming 'Time' column is the timestamp
  if (symbol in lastSignalBar && (currentBarTimestamp - lastSignalBar[symbol]) < (BOT_CONFIG.MIN_BARS_BETWEEN_TRADES * BOT_CONFIG.TIMEFRAME * 60 * 1000)) { // Convert minutes to milliseconds
    return ['none', 0, 0, 0, 'cool-down period active'];
  }

  // Base conditions
  let longCond = (
    lastRow.ema_s > lastRow.ema_l &&
    prevRow.ema_s <= prevRow.ema_l &&
    cp > lastRow.trend_ema &&
    lastRow.rsi < BOT_CONFIG.RSI_OVERBOUGHT &&
    lastRow.vol_spike &&
    (htfTrend === 'long')
  );

  let shortCond = (
    lastRow.ema_s < lastRow.ema_l &&
    prevRow.ema_s >= prevRow.ema_l &&
    cp < lastRow.trend_ema &&
    lastRow.rsi > BOT_CONFIG.RSI_OVERSOLD &&
    lastRow.vol_spike &&
    (htfTrend === 'short')
  );

  // Ehlers Supertrend filter
  if (BOT_CONFIG.USE_EST_SLOW_FILTER) {
    longCond = longCond && (lastRow.est_slow === 1);
    shortCond = shortCond && (lastRow.est_slow === -1);
  }

  // Stochastic filter
  if (BOT_CONFIG.USE_STOCH_FILTER && 'stoch_k' in lastRow && 'stoch_d' in lastRow) {
    const stochKCurr = lastRow.stoch_k;
    const stochDCurr = lastRow.stoch_d;
    const stochKPrev = prevRow.stoch_k;
    const stochDPrev = prevRow.stoch_d;

    const longStochCond = (stochKCurr > stochDCurr && stochKPrev <= stochDPrev && stochKCurr < BOT_CONFIG.STOCH_OVERBOUGHT);
    const shortStochCond = (stochKCurr < stochDCurr && stochKPrev >= stochDPrev && stochKCurr > BOT_CONFIG.STOCH_OVERSOLD);

    longCond = longCond && longStochCond;
    shortCond = shortCond && shortStochCond;
  }

  // MACD filter
  if (BOT_CONFIG.USE_MACD_FILTER && 'macd_line' in lastRow && 'macd_signal' in lastRow) {
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
  if (BOT_CONFIG.USE_ADX_FILTER && 'adx' in lastRow) {
    const adxCurr = lastRow.adx;
    const longAdxCond = (adxCurr > BOT_CONFIG.ADX_THRESHOLD);
    const shortAdxCond = (adxCurr > BOT_CONFIG.ADX_THRESHOLD);

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
    tpPrice = cp + (riskDistance * (BOT_CONFIG.REWARD_RISK_RATIO || 2.5));
    reason = 'EMA cross up, price above trend EMA, RSI not overbought, volume spike, HTF long';
  } else if (shortCond) {
    signal = 'Sell';
    slPrice = cp + riskDistance;
    tpPrice = cp - (riskDistance * (BOT_CONFIG.REWARD_RISK_RATIO || 2.5));
    reason = 'EMA cross down, price below trend EMA, RSI not oversold, volume spike, HTF short';
  }

  if (signal !== 'none') {
    lastSignalBar[symbol] = currentBarTimestamp;
  }

  return [signal, cp, slPrice, tpPrice, reason];
}

// -------------- equity guard --------------
let equityReference = null;
async function emergencyStop(bybit) {
  const currentEquity = await bybit.getBalance();
  if (equityReference === null) {
    equityReference = currentEquity;
    rootLogger.info(`Initial equity reference set to ${equityReference.toFixed(2)} USDT.`);
    return false;
  }

  if (currentEquity <= 0) {
    rootLogger.warning("Current equity is zero or negative. Cannot calculate drawdown.");
    return false;
  }

  if (currentEquity < equityReference) {
    const drawdown = ((equityReference - currentEquity) / equityReference) * 100;
    if (drawdown >= (BOT_CONFIG.EMERGENCY_STOP_IF_DOWN_PCT || 15)) {
      rootLogger.critical(`${BOLD}${RED}!!! EMERGENCY STOP !!! Equity down ${drawdown.toFixed(1)}%. Shutting down bot.${RESET}`);
      return true;
    }
  }
  return false;
}

// -------------- main loop --------------
async function main() {
  await _initDb(); // Initialize SQLite DB

  const symbols = BOT_CONFIG.TRADING_SYMBOLS;
  if (!symbols || symbols.length === 0) {
    rootLogger.info("No symbols configured. Exiting.");
    return;
  }

  const bybit = new Bybit(BOT_CONFIG.API_KEY, BOT_CONFIG.API_SECRET, BOT_CONFIG.TESTNET, BOT_CONFIG.DRY_RUN);

  const modeInfo = BOT_CONFIG.DRY_RUN ? `${MAGENTA}${BOLD}DRY RUN${RESET}` : `${GREEN}${BOLD}LIVE${RESET}`;
  const testnetInfo = BOT_CONFIG.TESTNET ? `${YELLOW}TESTNET${RESET}` : `${BLUE}MAINNET${RESET}`;
  rootLogger.info(`Starting trading bot in ${modeInfo} mode on ${testnetInfo}. Checking ${symbols.length} symbols.`);
  rootLogger.info("Bot started – Press Ctrl+C to stop.");

  let lastReconciliationTime = moment.utc();

  try {
    while (true) {
      const [localTime, utcTime] = getCurrentTime(BOT_CONFIG.TIMEZONE);
      rootLogger.info(`Local Time: ${localTime.format('YYYY-MM-DD HH:mm:ss')} | UTC Time: ${utcTime.format('YYYY-MM-DD HH:mm:ss')}`);

      if (!isMarketOpen(localTime, BOT_CONFIG.MARKET_OPEN_HOUR, BOT_CONFIG.MARKET_CLOSE_HOUR)) {
        rootLogger.info(`Market is closed (${BOT_CONFIG.MARKET_OPEN_HOUR}:00-${BOT_CONFIG.MARKET_CLOSE_HOUR}:00 ${BOT_CONFIG.TIMEZONE}). Skipping this cycle. Waiting ${BOT_CONFIG.LOOP_WAIT_TIME_SECONDS} seconds.`);
        await setTimeout(BOT_CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
        continue;
      }

      if (await emergencyStop(bybit)) break;

      const balance = await bybit.getBalance();
      if (balance === null || balance <= 0) {
        rootLogger.error(`Cannot connect to API or balance is zero/negative (${balance}). Waiting ${BOT_CONFIG.LOOP_WAIT_TIME_SECONDS} seconds and retrying.`);
        await setTimeout(BOT_CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
        continue;
      }

      rootLogger.info(`Current balance: ${balance.toFixed(2)} USDT`);

      const currentPositionsOnExchange = await bybit.getPositions();
      const currentPositionsSymbolsOnExchange = {};
      currentPositionsOnExchange.forEach(p => {
        currentPositionsSymbolsOnExchange[p.symbol] = p;
      });
      rootLogger.info(`You have ${currentPositionsOnExchange.length} open positions on exchange: ${Object.keys(currentPositionsSymbolsOnExchange)}`);

      // --- Position Reconciliation (Exchange vs. DB) ---
      if (utcTime.diff(lastReconciliationTime, 'minutes') >= (BOT_CONFIG.POSITION_RECONCILIATION_INTERVAL_MINUTES || 5)) {
        rootLogger.info(`${CYAN}Performing position reconciliation...${RESET}`);
        await reconcilePositions(bybit, currentPositionsSymbolsOnExchange, utcTime);
        lastReconciliationTime = utcTime;
      }

      // --- Position Exit Manager (Time, Chandelier Exit, Fisher Transform, Fixed Profit, Trailing Stop) ---
      let activeDbTrades = await db.all("SELECT id, symbol, side, entry_time, entry_price, sl, tp, order_id FROM trades WHERE status = 'OPEN'");

      const exitTasks = [];
      for (const trade of activeDbTrades) {
        const positionInfo = currentPositionsSymbolsOnExchange[trade.symbol];
        exitTasks.push(manageTradeExit(bybit, trade.id, trade.symbol, trade.side, trade.entry_time, trade.entry_price, trade.sl, trade.tp, positionInfo, utcTime));
      }
      await Promise.all(exitTasks);

      // Refresh active_db_trades after exits
      activeDbTrades = await db.all("SELECT id, symbol, side FROM trades WHERE status = 'OPEN'");
      const currentDbPositionsSymbols = activeDbTrades.map(t => t.symbol);

      // --- Signal Search and Order Placement ---
      const signalTasks = [];
      for (const symbol of symbols) {
        if (currentDbPositionsSymbols.length >= (BOT_CONFIG.MAX_POSITIONS || 1)) {
          rootLogger.info(`Max positions (${BOT_CONFIG.MAX_POSITIONS}) reached. Halting signal checks for this cycle.`);
          break;
        }

        if (currentDbPositionsSymbols.includes(symbol)) {
          rootLogger.debug(`Skipping ${symbol} as there is already an open position in DB tracker.`);
          continue;
        }

        const openOrdersForSymbol = await bybit.getOpenOrders(symbol);
        if (openOrdersForSymbol.length >= (BOT_CONFIG.MAX_OPEN_ORDERS_PER_SYMBOL || 1)) {
          rootLogger.debug(`Skipping ${symbol} as there are ${openOrdersForSymbol.length} open orders (max ${BOT_CONFIG.MAX_OPEN_ORDERS_PER_SYMBOL}).`);
          continue;
        }

        signalTasks.push(processSymbolForSignal(bybit, symbol, balance, utcTime));
      }

      await Promise.all(signalTasks);

      rootLogger.info(`--- Cycle finished. Waiting ${BOT_CONFIG.LOOP_WAIT_TIME_SECONDS} seconds for next loop. ---`);
      await setTimeout(BOT_CONFIG.LOOP_WAIT_TIME_SECONDS * 1000);
    }
  } finally {
    // await bybit.closeSession(); // Not needed for BybitAsync from @bybit-api/client
    if (db) await db.close();
  }
}

async function reconcilePositions(bybit, exchangePositions, utcTime) {
  const dbPositions = {};
  const rows = await db.all("SELECT id, order_id, symbol, side, status, entry_price FROM trades WHERE status = 'OPEN'");
  rows.forEach(row => {
    dbPositions[row.symbol] = { db_id: row.id, order_id: row.order_id, side: row.side, status: row.status, entry_price: row.entry_price };
  });

  // 1. Mark DB positions as CLOSED if not found on exchange
  for (const symbol in dbPositions) {
    if (!exchangePositions[symbol]) {
      rootLogger.warning(`Position for ${symbol} found in DB (ID: ${dbPositions[symbol].db_id}) but not on exchange. Marking as CLOSED.`);
      const currentPrice = await bybit.getCurrentPrice(symbol);
      const pnl = currentPrice !== null ? (currentPrice - dbPositions[symbol].entry_price) * (dbPositions[symbol].side === 'Buy' ? 1 : -1) : 0;
      await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id = ?",
        ['CLOSED', utcTime.toISOString(), currentPrice, pnl, dbPositions[symbol].db_id]);
    }
  }

  // 2. Add exchange positions to DB if not found in DB
  for (const symbol in exchangePositions) {
    if (!dbPositions[symbol]) {
      rootLogger.warning(`Position for ${symbol} found on exchange but not in DB. Adding as RECONCILED.`);
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

async function manageTradeExit(bybit, tradeId, symbol, side, entryTimeStr, entryPrice, slDb, tpDb, positionInfo, utcTime) {
  if (!positionInfo) {
    rootLogger.info(`Position for ${symbol} not found on exchange while managing trade ${tradeId}. Marking as CLOSED in DB tracker.`);
    const currentPrice = await bybit.getCurrentPrice(symbol);
    const pnl = currentPrice !== null ? (currentPrice - entryPrice) * (side === 'Buy' ? 1 : -1) : 0;
    await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
      ['CLOSED', utcTime.toISOString(), currentPrice, pnl, tradeId]);
    return;
  }

  const klinesDf = await bybit.klines(symbol, BOT_CONFIG.TIMEFRAME, (BOT_CONFIG.MAX_HOLDING_CANDLES || 50) + 5);
  if (klinesDf.empty || klinesDf.count() < 2) {
    rootLogger.warning(`Not enough klines for ${symbol} to manage existing trade. Skipping exit check.`);
    return;
  }

  const dfWithIndicators = buildIndicators(klinesDf);
  const lastRow = dfWithIndicators.getRow(dfWithIndicators.count() - 1).toDict();
  const prevRow = dfWithIndicators.getRow(dfWithIndicators.count() - 2).toDict(); // For Fisher check
  const currentPrice = lastRow.Close;

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
  if ((BOT_CONFIG.FIXED_PROFIT_TARGET_PCT || 0) > 0 && currentPnlPercentage >= BOT_CONFIG.FIXED_PROFIT_TARGET_PCT) {
    reasonToExit = `Fixed Profit Target (${(BOT_CONFIG.FIXED_PROFIT_TARGET_PCT * 100).toFixed(1)}%) reached (Current PnL: ${(currentPnlPercentage * 100).toFixed(1)}%)`;
  }

  // Chandelier Exit (Trailing Stop equivalent, dynamic update if active)
  let newSlPrice = slDb; // Start with current SL in DB
  if (BOT_CONFIG.TRAILING_STOP_ACTIVE) {
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

    const [pricePrec, _] = await bybit.getPrecisions(symbol);
    newSlPrice = parseFloat(newSlPrice.toFixed(pricePrec));

    // Only modify if SL moved significantly
    if (Math.abs(newSlPrice - slDb) / slDb > 0.0001) {
      await bybit.modifyPositionTpsl(symbol, parseFloat(tpDb.toFixed(pricePrec)), newSlPrice);
      await db.run("UPDATE trades SET sl = ? WHERE id=?", [newSlPrice, tradeId]);
      rootLogger.debug(`[${symbol}] Trailing Stop Loss updated to ${newSlPrice.toFixed(4)}.`);
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
  if (reasonToExit === null && BOT_CONFIG.USE_FISHER_EXIT) {
    if (side === 'Buy' && lastRow.fisher < 0 && prevRow.fisher >= 0) {
      reasonToExit = `Fisher Transform (bearish flip: ${lastRow.fisher.toFixed(2)})`;
    } else if (side === 'Sell' && lastRow.fisher > 0 && prevRow.fisher <= 0) {
      reasonToExit = `Fisher Transform (bullish flip: ${lastRow.fisher.toFixed(2)})`;
    }
  }

  // Time-based Exit
  const entryDt = moment.utc(entryTimeStr);
  const elapsedMinutes = utcTime.diff(entryDt, 'minutes');
  const elapsedCandles = elapsedMinutes / BOT_CONFIG.TIMEFRAME;
  if (reasonToExit === null && elapsedCandles >= (BOT_CONFIG.MAX_HOLDING_CANDLES || 50)) {
    reasonToExit = `Max holding candles (${BOT_CONFIG.MAX_HOLDING_CANDLES}) exceeded`;
  }

  if (reasonToExit) {
    rootLogger.info(`${MAGENTA}Closing ${side} position for ${symbol} due to: ${reasonToExit}${RESET}`);
    await bybit.cancelAllOpenOrders(symbol);
    await setTimeout(500); // 0.5 seconds
    await bybit.closePosition(symbol);

    const pnl = (currentPrice - entryPrice) * (side === 'Buy' ? 1 : -1);
    await db.run("UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id=?",
      ['CLOSED', utcTime.toISOString(), currentPrice, pnl, tradeId]);
    rootLogger.info(`Trade ${tradeId} for ${symbol} marked as CLOSED in DB tracker. PNL: ${pnl.toFixed(2)} USDT`);
  }
}

async function processSymbolForSignal(bybit, symbol, balance, utcTime) {
  const klinesDf = await bybit.klines(symbol, BOT_CONFIG.TIMEFRAME, 200);
  if (klinesDf.empty || klinesDf.count() < BOT_CONFIG.MIN_KLINES_FOR_STRATEGY) {
    rootLogger.warning(`Not enough klines data for ${symbol} (needed >${BOT_CONFIG.MIN_KLINES_FOR_STRATEGY}). Skipping.`);
    return;
  }

  const [signal, currentPrice, slPrice, tpPrice, signalReason] = await generateSignal(bybit, symbol, klinesDf);

  const dfWithIndicators = buildIndicators(klinesDf);
  if (!dfWithIndicators.empty) {
    const lastRowIndicators = dfWithIndicators.getRow(dfWithIndicators.count() - 1).toDict();
    let logDetails = (
      `Price: ${currentPrice.toFixed(4)} | ` +
      `ATR (${BOT_CONFIG.ATR_PERIOD}): ${lastRowIndicators.atr.toFixed(4)} | ` +
      `Dyn Mult: ${lastRowIndicators.dynamic_multiplier.toFixed(2)} | ` +
      `EMA S(${BOT_CONFIG.EMA_SHORT_PERIOD}): ${lastRowIndicators.ema_s.toFixed(4)} | ` +
      `EMA L(${BOT_CONFIG.EMA_LONG_PERIOD}): ${lastRowIndicators.ema_l.toFixed(4)} | ` +
      `Trend EMA(${BOT_CONFIG.TREND_EMA_PERIOD}): ${lastRowIndicators.trend_ema.toFixed(4)} | ` +
      `RSI(${BOT_CONFIG.RSI_PERIOD}): ${lastRowIndicators.rsi.toFixed(2)} | ` +
      `Vol Spike: ${lastRowIndicators.vol_spike ? 'Yes' : 'No'} | ` +
      `EST Slow: ${lastRowIndicators.est_slow.toFixed(2)} | ` +
      `Fisher: ${lastRowIndicators.fisher.toFixed(2)}`
    );
    if (BOT_CONFIG.USE_STOCH_FILTER) {
      logDetails += ` | Stoch K/D: ${lastRowIndicators.stoch_k.toFixed(2)}/${lastRowIndicators.stoch_d.toFixed(2)}`;
    }
    if (BOT_CONFIG.USE_MACD_FILTER) {
      logDetails += ` | MACD Line/Sig: ${lastRowIndicators.macd_line.toFixed(2)}/${lastRowIndicators.macd_signal.toFixed(2)}`;
    }
    if (BOT_CONFIG.USE_ADX_FILTER) {
      logDetails += ` | ADX: ${lastRowIndicators.adx.toFixed(2)}`;
    }
    rootLogger.debug(`[${symbol}] Indicators: ${logDetails}`);
  }

  if (signal === 'none') {
    rootLogger.debug(`[${symbol}] No trading signal (${signalReason}).`);
    return;
  }

  rootLogger.info(`${BOLD}${signal === 'Buy' ? GREEN : RED}${signal} SIGNAL for ${symbol} ${signal === 'Buy' ? '📈' : '📉'}${RESET}`);
  rootLogger.info(`[${symbol}] Reasoning: ${signalReason}. Calculated TP: ${tpPrice !== null ? tpPrice.toFixed(4) : 'N/A'}, SL: ${slPrice !== null ? slPrice.toFixed(4) : 'N/A'}`);

  const [pricePrecision, qtyPrecision] = await bybit.getPrecisions(symbol);

  const capitalForRisk = balance;
  const riskAmountUsdt = capitalForRisk * BOT_CONFIG.RISK_PER_TRADE_PCT;

  const riskDistance = slPrice !== null ? Math.abs(currentPrice - slPrice) : 0;
  if (riskDistance <= 0) {
    rootLogger.warning(`[${symbol}] Calculated risk_distance is zero or negative. Skipping order.`);
    return;
  }

  const orderQtyRiskBased = riskAmountUsdt / riskDistance;
  const maxNotionalQty = (BOT_CONFIG.MAX_NOTIONAL_PER_TRADE_USDT || 1e9) / currentPrice;
  const orderQtyCalculated = Math.min(orderQtyRiskBased, maxNotionalQty);
  const orderQty = parseFloat(orderQtyCalculated.toFixed(qtyPrecision));

  if (orderQty <= 0) {
    rootLogger.warning(`[${symbol}] Calculated order quantity is zero or negative (${orderQty}). Skipping order.`);
    return;
  }

  await bybit.setMarginModeAndLeverage(symbol, BOT_CONFIG.MARGIN_MODE, BOT_CONFIG.LEVERAGE);
  await setTimeout(500); // 0.5 seconds

  let orderId = null;
  const orderTypeConfig = (BOT_CONFIG.ORDER_TYPE || "Market").toLowerCase();

  const [bestBid, bestAsk] = await bybit.getOrderbookLevels(symbol);

  if (orderTypeConfig === 'limit') {
    let limitExecutionPrice = null;
    if (signal === 'Buy' && bestBid !== null && (currentPrice - bestBid) < (currentPrice * BOT_CONFIG.PRICE_DETECTION_THRESHOLD_PCT)) {
      limitExecutionPrice = parseFloat(bestBid.toFixed(pricePrecision));
      rootLogger.info(`[${symbol}] Price near best bid at ${bestBid.toFixed(4)}. Placing Limit Order to Buy at bid.`);
    } else if (signal === 'Sell' && bestAsk !== null && (bestAsk - currentPrice) < (currentPrice * BOT_CONFIG.PRICE_DETECTION_THRESHOLD_PCT)) {
      limitExecutionPrice = parseFloat(bestAsk.toFixed(pricePrecision));
      rootLogger.info(`[${symbol}] Price near best ask at ${bestAsk.toFixed(4)}. Placing Limit Order to Sell at ask.`);
    } else {
      limitExecutionPrice = parseFloat(currentPrice.toFixed(pricePrecision));
      rootLogger.info(`[${symbol}] No specific S/R condition for limit. Placing Limit Order at current price ${limitExecutionPrice.toFixed(4)}.`);
    }

    if (limitExecutionPrice) {
      orderId = await bybit.placeLimitOrder(
        symbol, signal, limitExecutionPrice, orderQty,
        tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
        slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null,
        BOT_CONFIG.POST_ONLY ? 'PostOnly' : 'GTC'
      );
    }
  } else if (orderTypeConfig === 'conditional') {
    let triggerPrice = null;
    if (signal === 'Buy') {
      triggerPrice = currentPrice * (1 + (BOT_CONFIG.BREAKOUT_TRIGGER_PERCENT || 0.001));
    } else {
      triggerPrice = currentPrice * (1 - (BOT_CONFIG.BREAKOUT_TRIGGER_PERCENT || 0.001));
    }

    triggerPrice = parseFloat(triggerPrice.toFixed(pricePrecision));
    rootLogger.info(`[${symbol}] Placing Conditional Market Order triggered at ${triggerPrice.toFixed(4)}.`);
    orderId = await bybit.placeConditionalOrder(
      symbol, signal, orderQty, triggerPrice,
      'Market', null,
      tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
      slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null
    );
  } else {
    rootLogger.info(`[${symbol}] Placing Market Order.`);
    orderId = await bybit.placeMarketOrder(
      symbol, signal, orderQty,
      tpPrice !== null ? parseFloat(tpPrice.toFixed(pricePrecision)) : null,
      slPrice !== null ? parseFloat(slPrice.toFixed(pricePrecision)) : null
    );
  }

  if (orderId) {
    await db.run("INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
      [uuidv4(), orderId, symbol, signal, orderQty, utcTime.toISOString(), currentPrice, slPrice, tpPrice, 'OPEN', null, null, null]);
    rootLogger.info(`New trade logged for ${symbol} (${signal} ${orderQty}). Order ID: ${orderId}`);
  }
}


// -------------- tiny helpers --------------
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

// -------------- start --------------
if (import.meta.main) { // Equivalent to Python's `if __name__ == "__main__":`
  (async () => {
    try {
      await main();
    } catch (e) {
      if (e.message === "User interrupted") {
        rootLogger.info("Bot stopped by user via KeyboardInterrupt.");
      } else {
        rootLogger.critical(`Bot terminated due to an unexpected error: ${e.message}`, e);
      }
    } finally {
      // Any final cleanup if needed
    }
  })();
}