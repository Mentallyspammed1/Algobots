import { KlineIntervalV5 } from 'bybit-api';

// ======== CONFIGURATION INTERFACES ========

export interface BotConfig {
  symbol: string;
  interval: KlineIntervalV5;
  leverage: number;
  max_leverage: number;
  position_size_usd: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  entry_order_type: 'Market' | 'Limit';
  limit_order_price_offset_pct: number;
  run_mode: 'LIVE' | 'DRY_RUN' | 'BACKTEST';
  strategy: StrategyConfig;
}

export interface StrategyConfig {
  name: string;
  params: { [key: string]: number };
  weights: { [key: string]: number };
  thresholds: {
    long: number;
    short: number;
  };
}

// ======== STRATEGY INTERFACES ========

export type Signal = 'long' | 'short' | 'hold';

export interface Strategy {
  readonly name: string;
  update(candle: Candle): void;
  getSignal(): Signal;
}

// ======== DATA MODELS ========

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Position {
  symbol: string;
  side: 'Buy' | 'Sell' | 'None';
  size: number;
  entry_price: number;
  unrealised_pnl: number;
}

export interface InstrumentInfo {
  price_precision: number; // e.g., 0.01
  qty_precision: number;   // e.g., 0.001
  min_qty: number;
  min_amt: number; // Minimum order notional value
}