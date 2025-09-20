import { KlineIntervalV5, OrderV5 } from "bybit-api";
import { Candle, Position } from "../core/types";

/**
 * Defines the contract for any exchange service, whether it's live, dry-run, or backtesting.
 * This abstraction allows the bot's core logic to remain unchanged while the data source and execution engine can be swapped.
 */
export interface IExchange {
  getInstrumentInfo(symbol: string): Promise<InstrumentInfo>;
  subscribeToStreams(symbol: string, interval: KlineIntervalV5): void;
  getKlineHistory(symbol: string, interval: KlineIntervalV5, limit: number): Promise<Candle[]>;
  getPosition(symbol: string): Promise<Position>;
  setLeverage(symbol: string, leverage: number): Promise<void>;
  placeLimitOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, price: number, reduceOnly?: boolean): Promise<string | undefined>;
  placeConditionalOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, triggerPrice: number, orderType?: 'Market' | 'Limit'): Promise<string | undefined>;
  cancelAllOrders(symbol: string): Promise<void>;
}
