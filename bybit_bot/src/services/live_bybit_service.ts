import { RestClientV5, WebsocketClient, KlineIntervalV5, CategoryV5, PositionV5, OrderV5 } from 'bybit-api';
import { logger } from '../core/logger';
import { Candle, Position } from '../core/types';

import { IExchange } from './exchange_interface';

export class LiveBybitService implements IExchange {
  private restClient: RestClientV5;
  private wsClient: WebsocketClient;

  constructor(
    apiKey: string, 
    apiSecret: string, 
    testnet: boolean,
    private callbacks: {
        onCandle: (candle: Candle) => void;
        onOrderUpdate: (order: OrderV5) => void;
        onExecution: (execution: any) => void;
    }
  ) {
    this.restClient = new RestClientV5({ key: apiKey, secret: apiSecret, testnet });
    this.wsClient = new WebsocketClient({ key: apiKey, secret: apiSecret, market: 'v5', testnet });

    this.wsClient.on('error', (err) => {
      logger.error('WS Error:', err);
    });

    this.wsClient.on('update', (data) => {
        if (data.topic.startsWith('kline')) {
            const kline = data.data[0];
            if (kline.confirm) {
                this.callbacks.onCandle({
                    timestamp: parseInt(kline.start),
                    open: parseFloat(kline.open),
                    high: parseFloat(kline.high),
                    low: parseFloat(kline.low),
                    close: parseFloat(kline.close),
                    volume: parseFloat(kline.volume),
                });
            }
        } else if (data.topic === 'order') {
            data.data.forEach(order => this.callbacks.onOrderUpdate(order));
        } else if (data.topic === 'execution') {
            data.data.forEach(exec => this.callbacks.onExecution(exec));
        }
    });
  }

  subscribeToStreams(symbol: string, interval: KlineIntervalV5) {
    this.wsClient.subscribeV5([`kline.${interval}.${symbol}`, 'order', 'execution'], 'linear');
    logger.system(`Subscribed to streams for ${symbol} with interval ${interval}.`);
  }

  async placeLimitOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, price: number, reduceOnly: boolean = false): Promise<string | undefined> {
    try {
        logger.system(`Placing limit ${side} order for ${qty} ${symbol} at ${price}`);
        const response = await this.restClient.submitOrder({
            category: 'linear',
            symbol,
            side,
            orderType: 'Limit',
            qty: qty.toString(),
            price: price.toString(),
            reduceOnly,
            timeInForce: 'PostOnly', // Ensures it's a maker order
        });

        if (response.retCode !== 0) {
            throw new Error(`Limit order placement failed: ${response.retMsg}`);
        }
        const orderId = response.result.orderId;
        logger.success(`Limit ${side} order placed successfully. Order ID: ${orderId}`);
        return orderId;
    } catch (error) {
        logger.error(`Error placing limit order for ${symbol}:`, error);
    }
  }

  async placeConditionalOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, triggerPrice: number, orderType: 'Market' | 'Limit' = 'Market'): Promise<string | undefined> {
    try {
        logger.system(`Placing conditional ${side} order for ${qty} ${symbol} at trigger ${triggerPrice}`);
        const response = await this.restClient.submitOrder({
            category: 'linear',
            symbol,
            side,
            orderType,
            qty: qty.toString(),
            triggerPrice: triggerPrice.toString(),
            triggerDirection: side === 'Buy' ? 'Rise' : 'Fall',
            reduceOnly: true,
        });

        if (response.retCode !== 0) {
            throw new Error(`Conditional order placement failed: ${response.retMsg}`);
        }
        const orderId = response.result.orderId;
        logger.success(`Conditional ${side} order placed successfully. Order ID: ${orderId}`);
        return orderId;
    } catch (error) {
        logger.error(`Error placing conditional order for ${symbol}:`, error);
    }
  }

  async cancelAllOrders(symbol: string): Promise<void> {
    try {
        const response = await this.restClient.cancelAllOrders({ category: 'linear', symbol });
        if (response.retCode !== 0) {
            throw new Error(`Failed to cancel orders: ${response.retMsg}`);
        }
        logger.warn(`Cancelled all open orders for ${symbol}.`);
    } catch (error) {
        logger.error(`Error cancelling orders for ${symbol}:`, error);
    }
  }

    try {
      const response = await this.restClient.getKline({
        category: 'linear',
        symbol,
        interval,
        limit,
      });

      if (response.retCode !== 0) {
        throw new Error(response.retMsg);
      }

      // Bybit returns klines oldest to newest. We reverse to have newest first.
      return response.result.list.map(k => ({
        timestamp: parseInt(k[0]),
        open: parseFloat(k[1]),
        high: parseFloat(k[2]),
        low: parseFloat(k[3]),
        close: parseFloat(k[4]),
        volume: parseFloat(k[5]),
      })).reverse();
    } catch (error) {
      logger.error('Error fetching kline history:', error);
      return [];
    }
  }

  async getPosition(symbol: string): Promise<Position> {
    try {
        const response = await this.restClient.getPositionInfo({
            category: 'linear',
            symbol,
        });

        if (response.retCode !== 0) {
            throw new Error(response.retMsg);
        }

        const position = response.result.list[0];
        if (!position) {
            return this.getEmptyPosition(symbol);
        }

        return {
            symbol: position.symbol,
            side: position.side as 'Buy' | 'Sell' | 'None',
            size: parseFloat(position.size),
            entry_price: parseFloat(position.avgPrice),
            unrealised_pnl: parseFloat(position.unrealisedPnl),
        };

    } catch (error) {
        logger.error('Error fetching position:', error);
        return this.getEmptyPosition(symbol);
    }
  }

  async setLeverage(symbol: string, leverage: number): Promise<void> {
    try {
        const response = await this.restClient.setLeverage({
            category: 'linear',
            symbol,
            buyLeverage: leverage.toString(),
            sellLeverage: leverage.toString(),
        });
        if (response.retCode !== 0) {
            throw new Error(response.retMsg);
        }
        logger.success(`Leverage for ${symbol} set to ${leverage}x`);
    } catch (error) {
        logger.error(`Failed to set leverage for ${symbol}:`, error);
    }
  }

  async closePosition(symbol: string, side: 'Buy' | 'Sell', qty: number): Promise<void> {
    try {
        logger.system(`Placing market order to close ${side} position for ${qty} ${symbol}...`);
        const response = await this.restClient.submitOrder({
            category: 'linear',
            symbol,
            side,
            orderType: 'Market',
            qty: qty.toString(),
            reduceOnly: true, // This ensures the order only closes a position
        });

        if (response.retCode !== 0) {
            throw new Error(`Position close failed: ${response.retMsg}`);
        }

        logger.success(`Close order placed successfully. Order ID: ${response.result.orderId}`);

    } catch (error) {
        logger.error(`Error closing position for ${symbol}:`, error);
    }
  }

  async placeOrderWithSLTP(symbol: string, side: 'Buy' | 'Sell', qty: number, takeProfit: number, stopLoss: number): Promise<void> {
    try {
        logger.system(`Placing market ${side} order for ${qty} ${symbol} with TP:${takeProfit} and SL:${stopLoss}`);
        const response = await this.restClient.submitOrder({
            category: 'linear',
            symbol,
            side,
            orderType: 'Market',
            qty: qty.toString(),
            takeProfit: takeProfit.toString(),
            stopLoss: stopLoss.toString(),
            tpTriggerBy: 'LastPrice',
            slTriggerBy: 'LastPrice',
        });

        if (response.retCode !== 0) {
            throw new Error(`Order placement failed: ${response.retMsg}`);
        }

        logger.success(`Market ${side} order with SL/TP placed successfully. Order ID: ${response.result.orderId}`);

    } catch (error) {
        logger.error(`Error placing order with SL/TP for ${symbol}:`, error);
    }
  }

  private getEmptyPosition(symbol: string): Position {
    return {
        symbol,
        side: 'None',
        size: 0,
        entry_price: 0,
        unrealised_pnl: 0,
    };
  }
}