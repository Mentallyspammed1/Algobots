import { RestClientV5 } from 'bybit-api';
import { logger, neon } from './logger.js';
import { setTimeout } from 'timers/promises'; // For async sleep
import { v4 as uuidv4 } from 'uuid'; // For generating UUIDs

/**
 * @class BybitAPIClient
 * @description A client for interacting with the Bybit V5 API, providing methods for market data,
 * order management, position management, and account information.
 * Supports dry-run simulations and includes a retry mechanism for API calls.
 */
class BybitAPIClient {
  /**
   * @constructor
   * @description Initializes the BybitAPIClient with API key, secret, testnet/dry-run flags,
   * and sets up the RestClientV5 session.
   * Exits the process if API key/secret are missing and not in dry-run mode.
   * @param {object} config - The configuration object containing API_KEY, API_SECRET, TESTNET, DRY_RUN.
   */
  constructor(config) {
    this.api = config.API_KEY;
    this.secret = config.API_SECRET;
    this.testnet = config.TESTNET;
    this.dry_run = config.DRY_RUN;
    this.order_retry_attempts = config.ORDER_RETRY_ATTEMPTS;
    this.order_retry_delay_seconds = config.ORDER_RETRY_DELAY_SECONDS;

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

    /**
     * @private
     * @property {Object} _dry_run_positions - Internal tracker for simulating positions in dry run mode.
     */
    this._dry_run_positions = {};
  }

  /**
   * @private
   * @method _retryWrapper
   * @description A private helper method to wrap API calls with a retry mechanism.
   * It retries failed API calls up to a configured number of attempts with a delay.
   * @param {Function} apiCall - The Bybit API method to call (e.g., this.session.getWalletBalance).
   * @param {...any} args - Arguments to pass to the apiCall function.
   * @returns {Promise<Object>} The response from the API call, or an error object if max retries are reached.
   */
  async _retryWrapper(apiCall, ...args) {
    for (let attempt = 0; attempt < this.order_retry_attempts; attempt++) {
      try {
        const resp = await apiCall(...args);
        if (resp.retCode === 0) {
          return resp;
        } else {
          logger.error(neon.error(`API Error (attempt ${attempt + 1}/${this.order_retry_attempts}): ${resp.retMsg || 'Unknown error'} (Code: ${resp.retCode})`));
        }
      } catch (e) {
        logger.error(neon.error(`API Exception (attempt ${attempt + 1}/${this.order_retry_attempts}): ${e.message}`));
      }
      await setTimeout(this.order_retry_delay_seconds * 1000);
    }
    return { retCode: -1, retMsg: 'Max retries reached', result: null };
  }

  /**
   * @method getBalance
   * @description Fetches the wallet balance for a specified coin.
   * In dry-run mode, returns a simulated balance.
   * @param {string} [coin="USDT"] - The cryptocurrency symbol (e.g., "USDT", "BTC").
   * @returns {Promise<number>} The wallet balance as a float, or 0 if not found/error.
   */
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

  /**
   * @method getPositions
   * @description Retrieves a list of open positions.
   * In dry-run mode, returns simulated open positions.
   * @param {string} [settleCoin="USDT"] - The settlement coin for the positions (e.g., "USDT").
   * @returns {Promise<Array<Object>>} An array of open position objects.
   */
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

  /**
   * @method getTickers
   * @description Fetches a list of tradable symbols (tickers) that include 'USDT' and exclude 'USDC'.
   * @returns {Promise<Array<string>|null>} An array of symbol strings (e.g., ["BTCUSDT", "ETHUSDT"]), or null on error.
   */
  async getTickers() {
    const resp = await this._retryWrapper(this.session.getTickers.bind(this.session), { category: "linear" });
    if (resp.retCode === 0 && resp.result && resp.result.list) {
      return resp.result.list.filter(t => t.symbol.includes('USDT') && !t.symbol.includes('USDC')).map(t => t.symbol);
    }
    return null;
  }

  /**
   * @method klines
   * @description Retrieves historical candlestick data for a given symbol and timeframe.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {string} timeframe - The kline interval (e.g., "1", "5", "60", "D").
   * @param {number} [limit=500] - The maximum number of klines to retrieve.
   * @returns {Promise<Array<Object>>} An array of kline objects, each with time, open, high, low, close, volume, and turnover. Returns an empty array on error or if NaN values are found.
   */
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

  /**
   * @method getCurrentPrice
   * @description Fetches the last traded price for a given symbol.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @returns {Promise<number|null>} The current price as a float, or null on error.
   */
  async getCurrentPrice(symbol) {
    const resp = await this._retryWrapper(this.session.getTickers.bind(this.session), { category: 'linear', symbol: symbol });
    if (resp.retCode === 0 && resp.result && resp.result.list && resp.result.list.length > 0) {
      return parseFloat(resp.result.list[0].lastPrice);
    }
    return null;
  }

  /**
   * @method getOrderbookLevels
   * @description Retrieves the best bid and best ask prices from the order book.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {number} [limit=50] - The number of order book levels to retrieve.
   * @returns {Promise<Array<number|null>>} An array containing [bestBid, bestAsk], or [null, null] on error.
   */
  async getOrderbookLevels(symbol, limit = 50) {
    const resp = await this._retryWrapper(this.session.getOrderbook.bind(this.session), { category: 'linear', symbol: symbol, limit: limit });
    if (resp.retCode === 0 && resp.result) {
      const bestBid = resp.result.b.length > 0 ? parseFloat(resp.result.b[0][0]) : null;
      const bestAsk = resp.result.a.length > 0 ? parseFloat(resp.result.a[0][0]) : null;
      return [bestBid, bestAsk];
    }
    return [null, null];
  }

  /**
   * @method getPrecisions
   * @description Fetches price and quantity precision (step sizes) and minimum order quantity for a symbol.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @returns {Promise<Array<number>>} An array containing [pricePrecision, qtyPrecision, minOrderQty]. Defaults to [0, 0, 0.001] on error.
   */
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

  /**
   * @method setMarginModeAndLeverage
   * @description Sets the margin mode (isolated/cross) and leverage for a given symbol.
   * In dry-run mode, logs the intended action without execution.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {number} mode - Margin mode: 0 for Cross Margin, 1 for Isolated Margin.
   * @param {number} leverage - The desired leverage value (e.g., 10).
   * @returns {Promise<void>}
   */
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

  /**
   * @private
   * @method placeOrderCommon
   * @description Common method for placing various types of orders (Market, Limit, Conditional).
   * Handles dry-run simulation, precision formatting, and integrates TP/SL.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {string} side - Order side: "Buy" or "Sell".
   * @param {string} orderType - Order type: "Market", "Limit", "Conditional".
   * @param {number} qty - The quantity of the asset to trade.
   * @param {number|null} [price=null] - The price for Limit orders. Required for Limit, optional for Market.
   * @param {number|null} [triggerPrice=null] - The trigger price for Conditional orders.
   * @param {number|null} [tpPrice=null] - Take Profit price.
   * @param {number|null} [slPrice=null] - Stop Loss price.
   * @param {string} [timeInForce="GTC"] - Time in Force policy (e.g., "GTC", "IOC", "FOK").
   * @param {boolean} [reduceOnly=false] - Whether the order is to reduce an existing position only.
   * @returns {Promise<string|null>} The order ID if successful, or null on failure.
   */
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

  /**
   * @method placeMarketOrder
   * @description Places a market order.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {string} side - Order side: "Buy" or "Sell".
   * @param {number} qty - The quantity of the asset to trade.
   * @param {number|null} [tpPrice=null] - Take Profit price.
   * @param {number|null} [slPrice=null] - Stop Loss price.
   * @param {boolean} [reduceOnly=false] - Whether the order is to reduce an existing position only.
   * @returns {Promise<string|null>} The order ID if successful, or null on failure.
   */
  async placeMarketOrder(symbol, side, qty, tpPrice = null, slPrice = null, reduceOnly = false) {
    return await this.placeOrderCommon(symbol, side, 'Market', qty, null, null, tpPrice, slPrice, 'GTC', reduceOnly);
  }

  /**
   * @method placeLimitOrder
   * @description Places a limit order.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {string} side - Order side: "Buy" or "Sell".
   * @param {number} price - The price for the limit order.
   * @param {number} qty - The quantity of the asset to trade.
   * @param {number|null} [tpPrice=null] - Take Profit price.
   * @param {number|null} [slPrice=null] - Stop Loss price.
   * @param {string} [timeInForce="GTC"] - Time in Force policy (e.g., "GTC", "IOC", "FOK").
   * @param {boolean} [reduceOnly=false] - Whether the order is to reduce an existing position only.
   * @returns {Promise<string|null>} The order ID if successful, or null on failure.
   */
  async placeLimitOrder(symbol, side, price, qty, tpPrice = null, slPrice = null, timeInForce = 'GTC', reduceOnly = false) {
    return await this.placeOrderCommon(symbol, side, 'Limit', qty, price, null, tpPrice, slPrice, timeInForce, reduceOnly);
  }

  /**
   * @method placeConditionalOrder
   * @description Places a conditional order (e.g., Stop Market, Stop Limit).
   * If orderType is 'Limit' and price is not provided, triggerPrice will be used as limit price.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {string} side - Order side: "Buy" or "Sell".
   * @param {number} qty - The quantity of the asset to trade.
   * @param {number} triggerPrice - The price that triggers the order.
   * @param {string} [orderType="Market"] - The type of order to place once triggered ("Market" or "Limit").
   * @param {number|null} [price=null] - The limit price if orderType is "Limit".
   * @param {number|null} [tpPrice=null] - Take Profit price.
   * @param {number|null} [slPrice=null] - Stop Loss price.
   * @param {boolean} [reduceOnly=false] - Whether the order is to reduce an existing position only.
   * @returns {Promise<string|null>} The order ID if successful, or null on failure.
   */
  async placeConditionalOrder(symbol, side, qty, triggerPrice, orderType = 'Market', price = null, tpPrice = null, slPrice = null, timeInForce = 'GTC', reduceOnly = false) {
    if (orderType === 'Limit' && price === null) {
      price = triggerPrice;
      logger.warning(neon.warn(`Conditional limit order requested for ${symbol} without explicit price. Using trigger_price as limit execution price.`));
    }
    return await this.placeOrderCommon(symbol, side, orderType, qty, price, triggerPrice, tpPrice, slPrice, timeInForce, reduceOnly);
  }

  /**
   * @method cancelAllOpenOrders
   * @description Cancels all active open orders for a given symbol.
   * In dry-run mode, logs the intended action without execution.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @returns {Promise<Object>} The API response object.
   */
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

  /**
   * @method modifyPositionTpsl
   * @description Modifies the Take Profit (TP) and Stop Loss (SL) levels for an existing position.
   * In dry-run mode, logs the intended action without execution.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @param {number|null} tpPrice - The new Take Profit price, or null to not change.
   * @param {number|null} slPrice - The new Stop Loss price, or null to not change.
   * @returns {Promise<Object>} The API response object.
   */
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
    } else if ([110026, 110043].includes(resp.retCode)) { // No position to modify
      logger.warning(neon.warn(`No active position for ${symbol} to modify TP/SL.`));
    }
    return resp;
  }

  /**
   * @method getOpenOrders
   * @description Retrieves a list of active open orders for a given symbol, or all symbols if none specified.
   * In dry-run mode, returns an empty array.
   * @param {string|null} [symbol=null] - The trading pair symbol (e.g., "BTCUSDT"), or null for all symbols.
   * @returns {Promise<Array<Object>>} An array of open order objects.
   */
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

  /**
   * @method closePosition
   * @description Closes an existing open position for a given symbol using a market order.
   * In dry-run mode, logs the intended action and updates internal simulated positions.
   * @param {string} symbol - The trading pair symbol (e.g., "BTCUSDT").
   * @returns {Promise<string|null>} The order ID of the closing order if successful, or null on failure.
   */
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

  /**
   * @method syncTime
   * @description Placeholder for time synchronization. The `bybit-api` library handles timestamps internally.
   * If explicit time sync is needed for other purposes, it would be implemented here.
   * @returns {Promise<number>} The current timestamp from Date.now().
   */
  async syncTime() {
    logger.debug(neon.dim("Time synchronization handled by bybit-api library internally."));
    return Date.now();
  }
}

export default BybitAPIClient;