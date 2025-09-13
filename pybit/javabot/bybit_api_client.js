import { RestClientV5 } from 'bybit-api';
import { CONFIG } from './config.js';
import { logger, neon } from './logger.js';
import { setTimeout } from 'timers/promises'; // For async sleep
import { v4 as uuidv4 } from 'uuid'; // For generating UUIDs

class BybitAPIClient {
  constructor() {
    this.api = CONFIG.API_KEY;
    this.secret = CONFIG.API_SECRET;
    this.testnet = CONFIG.TESTNET;
    this.dry_run = CONFIG.DRY_RUN;

    if (!this.api || !this.secret) {
      logger.error(neon.error("API Key and Secret must be provided in config.js or .env."));
      if (!this.dry_run) {
        process.exit(1);
      }
    }

    this.session = new RestClientV5({
      key: this.api,
      secret: this.secret,
      testnet: this.testnet,
      category: 'linear', // Default to linear category for most operations
    });
    logger.info(neon.info(`Bybit client initialized. Testnet: ${this.testnet}, Dry Run: ${this.dry_run}`));

    this._dry_run_positions = {}; // For simulating positions in dry run
  }

  async _retryWrapper(apiCall, ...args) {
    for (let attempt = 0; attempt < CONFIG.ORDER_RETRY_ATTEMPTS; attempt++) {
      try {
        const resp = await apiCall(...args);
        if (resp.retCode === 0) {
          return resp;
        } else {
          logger.error(neon.error(`API Error (attempt ${attempt + 1}/${CONFIG.ORDER_RETRY_ATTEMPTS}): ${resp.retMsg || 'Unknown error'} (Code: ${resp.retCode})`));
        }
      } catch (e) {
        logger.error(neon.error(`API Exception (attempt ${attempt + 1}/${CONFIG.ORDER_RETRY_ATTEMPTS}): ${e.message}`));
      }
      await setTimeout(CONFIG.ORDER_RETRY_DELAY_SECONDS * 1000);
    }
    return { retCode: -1, retMsg: 'Max retries reached', result: null };
  }

  async getBalance(coin = "USDT") {
    if (this.dry_run) {
      logger.debug(neon.dim(`[DRY RUN] Simulated balance: 10000.00 ${coin}`));
      return 10000.00;
    }
    const resp = await this._retryWrapper(this.session.getWalletBalance.bind(this.session), { accountType: 'UNIFIED' });
    if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
      const coinInfo = resp.result.list[0].coin.find(c => c.coin === coin);
      if (coinInfo) {
        return parseFloat(coinInfo.walletBalance || 0);
      }
      logger.warning(neon.warn(`Balance for ${coin} not found in response.`));
    }
    return 0;
  }

  async getPositions(settleCoin = "USDT") {
    if (this.dry_run) {
      const openSymbols = Object.keys(this._dry_run_positions);
      logger.debug(neon.dim(`[DRY RUN] Fetched open positions from internal tracker: ${openSymbols}`));
      return openSymbols.map(symbol => ({ symbol, side: this._dry_run_positions[symbol].side, size: this._dry_run_positions[symbol].size }));
    }
    const resp = await this._retryWrapper(this.session.getPositionInfo.bind(this.session), { category: 'linear', settleCoin: settleCoin });
    if (resp.retCode === 0 && resp.result && resp.result.list) {
      return resp.result.list.filter(p => parseFloat(p.size) > 0);
    }
    return [];
  }

  async getTickers() {
    const resp = await this._retryWrapper(this.session.getTickers.bind(this.session), { category: "linear" });
    if (resp.retCode === 0 && resp.result && resp.result.list) {
      return resp.result.list.filter(t => t.symbol.includes('USDT') && !t.symbol.includes('USDC')).map(t => t.symbol);
    }
    return null;
  }

  async klines(symbol, timeframe, limit = 500) {
    const resp = await this._retryWrapper(this.session.getKlines.bind(this.session), {
      category: 'linear',
      symbol: symbol,
      interval: String(timeframe),
      limit: limit
    });

    if (resp.retCode === 0 && resp.result && resp.result.list) {
      // Bybit returns [timestamp, open, high, low, close, volume, turnover]
      const data = resp.result.list.map(row => ({
        time: parseFloat(row[0]),
        open: parseFloat(row[1]),
        high: parseFloat(row[2]),
        low: parseFloat(row[3]),
        close: parseFloat(row[4]),
        volume: parseFloat(row[5]),
        turnover: parseFloat(row[6]),
      }));
      
      // Check for NaN in OHLC
      const hasNan = data.some(k => isNaN(k.open) || isNaN(k.high) || isNaN(k.low) || isNaN(k.close));
      if (hasNan) {
          logger.warning(neon.warn(`NaN values found in OHLC for ${symbol}. Discarding klines.`));
          return [];
      }
      return data;
    }
    return [];
  }

  async getCurrentPrice(symbol) {
    const resp = await this._retryWrapper(this.session.getTickers.bind(this.session), { category: 'linear', symbol: symbol });
    if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
      return parseFloat(resp.result.list[0].lastPrice);
    }
    return null;
  }

  async getOrderbookLevels(symbol, limit = 50) {
    const resp = await this._retryWrapper(this.session.getOrderbook.bind(this.session), { category: 'linear', symbol: symbol, limit: limit });
    if (resp.retCode === 0 && resp.result) {
      const bestBid = resp.result.b.length > 0 ? parseFloat(resp.result.b[0][0]) : null;
      const bestAsk = resp.result.a.length > 0 ? parseFloat(resp.result.a[0][0]) : null;
      return [bestBid, bestAsk];
    }
    return [null, null];
  }

  async getPrecisions(symbol) {
    const resp = await this._retryWrapper(this.session.getInstrumentsInfo.bind(this.session), { category: 'linear', symbol: symbol });
    if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
      const info = resp.result.list[0];
      const priceStep = info.priceFilter.tickSize;
      const qtyStep = info.lotSizeFilter.qtyStep;
      const pricePrec = priceStep.includes('.') ? priceStep.split('.')[1].length : 0;
      const qtyPrec = qtyStep.includes('.') ? qtyStep.split('.')[1].length : 0;
      const minOrderQty = parseFloat(info.lotSizeFilter.minOrderQty);
      return [pricePrec, qtyPrec, minOrderQty];
    }
    return [0, 0, 0.001];
  }

  async setMarginModeAndLeverage(symbol, mode, leverage) {
    if (this.dry_run) {
      logger.info(neon.dim(`[DRY RUN] Would set ${symbol} margin=${mode === 1 ? 'Isolated' : 'Cross'} ${leverage}x`));
      return;
    }
    const resp = await this._retryWrapper(this.session.setLeverage.bind(this.session), {
      category: 'linear',
      symbol: symbol,
      buyLeverage: String(leverage),
      sellLeverage: String(leverage),
    });
    if (resp.retCode === 0) {
      logger.info(neon.info(`${symbol} margin=${mode === 1 ? 'Isolated' : 'Cross'} ${leverage}x set.`));
    } else if ([110026, 110043].includes(resp.retCode)) { // Already set
      logger.debug(neon.dim(`${symbol} margin/leverage already set (Code: ${resp.retCode}).`));
    }
  }

  async placeOrderCommon(symbol, side, orderType, qty, price = null, triggerPrice = null, tpPrice = null, slPrice = null, timeInForce = 'GTC', reduceOnly = false) {
    if (this.dry_run) {
      const oid = `DRY_${uuidv4()}`;
      let logMsg = neon.dim(`[DRY RUN] ${orderType} ${side} ${qty} ${symbol}`);
      if (price !== null) logMsg += ` price=${price}`;
      if (triggerPrice !== null) logMsg += ` trigger=${triggerPrice}`;
      if (tpPrice !== null) logMsg += ` TP=${tpPrice}`;
      if (slPrice !== null) logMsg += ` SL=${slPrice}`;
      if (reduceOnly) logMsg += ` ReduceOnly`;
      logger.info(`${logMsg}. Simulated Order ID: ${oid}`);
      this._dry_run_positions[symbol] = { side: side, size: qty };
      return oid;
    }

    const [pricePrecision, qtyPrecision] = await this.getPrecisions(symbol);

    const params = {
      category: 'linear',
      symbol: symbol,
      side: side,
      orderType: orderType,
      qty: String(parseFloat(qty).toFixed(qtyPrecision)),
      timeInForce: timeInForce,
      reduceOnly: reduceOnly ? 1 : 0,
    };
    if (price !== null) params.price = String(parseFloat(price).toFixed(pricePrecision));
    if (triggerPrice !== null) {
      params.triggerPrice = String(parseFloat(triggerPrice).toFixed(pricePrecision));
      params.triggerBy = 'MarkPrice'; // Or LastPrice, IndexPrice
    }
    if (tpPrice !== null) {
      params.takeProfit = String(parseFloat(tpPrice).toFixed(pricePrecision));
      params.tpTriggerBy = 'Market'; // 'Market', 'LastPrice', 'IndexPrice'
    }
    if (slPrice !== null) {
      params.stopLoss = String(parseFloat(slPrice).toFixed(pricePrecision));
      params.slTriggerBy = 'Market'; // 'Market', 'LastPrice', 'IndexPrice'
    }

    const resp = await this._retryWrapper(this.session.placeOrder.bind(this.session), params);
    if (resp.retCode === 0) {
      logger.info(neon.success(`Order placed for ${symbol} (${orderType} ${side} ${qty}). Order ID: ${resp.result.orderId}`));
      return resp.result.orderId;
    }
    if (resp.retCode === 10001) {
      logger.error(neon.error(`Order placement failed for ${symbol} due to API error ${resp.retCode}: ${resp.retMsg || 'Unknown API error'}`));
      return null; // Do not retry immediately for specific critical errors
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
      logger.warning(neon.warn(`Conditional limit order requested for ${symbol} without explicit price. Using trigger_price as limit execution price.`));
    }
    return await this.placeOrderCommon(symbol, side, orderType, qty, price, triggerPrice, tpPrice, slPrice, 'GTC', reduceOnly);
  }

  async cancelAllOpenOrders(symbol) {
    if (this.dry_run) {
      logger.info(neon.dim(`[DRY RUN] Would cancel all open orders for ${symbol}.`));
      return { retCode: 0, retMsg: 'OK' };
    }
    const resp = await this._retryWrapper(this.session.cancelAllOrders.bind(this.session), { category: 'linear', symbol: symbol });
    if (resp.retCode === 0) {
      logger.info(neon.info(`All open orders for ${symbol} cancelled successfully.`));
      return resp;
    }
    return resp;
  }

  async modifyPositionTpsl(symbol, tpPrice, slPrice) {
    if (this.dry_run) {
      logger.info(neon.dim(`[DRY RUN] Would modify TP/SL for ${symbol}. TP:${tpPrice}, SL:${slPrice}`));
      return { retCode: 0, retMsg: 'OK' };
    }
    const params = { category: 'linear', symbol: symbol };
    if (tpPrice !== null) params.takeProfit = String(tpPrice);
    if (slPrice !== null) params.stopLoss = String(slPrice);
    params.tpTriggerBy = 'Market';
    params.slTriggerBy = 'Market';

    const resp = await this._retryWrapper(this.session.setTradingStop.bind(this.session), params);
    if (resp.retCode === 0) {
      logger.debug(neon.dim(`Modified TP/SL for ${symbol}. TP:${tpPrice}, SL:${slPrice}`));
      return resp;
    } else if (resp.retCode === 110026) { // No position to modify
      logger.warning(neon.warn(`No active position for ${symbol} to modify TP/SL.`));
    }
    return resp;
  }

  async getOpenOrders(symbol = null) {
    if (this.dry_run) {
      return [];
    }
    const params = { category: 'linear' };
    if (symbol) params.symbol = symbol;
    const resp = await this._retryWrapper(this.session.getOpenOrders.bind(this.session), params);
    if (resp.retCode === 0 && resp.result && resp.result.list) {
      return resp.result.list;
    }
    return [];
  }

  async closePosition(symbol) {
    if (this.dry_run) {
      logger.info(neon.dim(`[DRY RUN] Would close position for ${symbol} with a market order.`));
      if (this._dry_run_positions[symbol]) {
        delete this._dry_run_positions[symbol];
      }
      return `DRY_CLOSE_${uuidv4()}`;
    }

    const posResp = await this._retryWrapper(this.session.getPositionInfo.bind(this.session), { category: 'linear', symbol: symbol });
    if (posResp.retCode !== 0 || !posResp.result || !posResp.result.list || posResp.result.list.length === 0) {
      logger.warning(neon.warn(`Could not get position details for ${symbol} to close. ${posResp.retMsg || 'No position found'}`));
      return null;
    }

    const positionInfo = posResp.result.list.find(p => parseFloat(p.size) > 0);
    if (!positionInfo) {
      logger.info(neon.info(`No open position found for ${symbol} to close (size is 0).`));
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
  }

  // This is a placeholder for time synchronization, as bybit-api handles timestamps internally.
  // If explicit time sync is needed for other purposes, it would go here.
  async syncTime() {
    logger.debug(neon.dim("Time synchronization handled by bybit-api library internally."));
    return Date.now();
  }
}

export const bybitClient = new BybitAPIClient();
