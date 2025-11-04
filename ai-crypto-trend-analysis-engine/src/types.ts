
export interface Kline {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type TrendDirection = 'Uptrend' | 'Downtrend' | 'Sideways';
export type HigherTimeframeTrends = { [key: string]: TrendDirection };

export interface TimeframeAlignmentEntry {
    interval: string;
    trend: TrendDirection;
}

export interface Analysis {
  trend: TrendDirection;
  signal: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  scalpingThesis: string;
  scalpingStrategy: string;
  tradeUrgency: 'Immediate' | 'Monitor' | 'Low';
  reasoning: string;
  key_factors: string[];
  supportLevel: number;
  resistanceLevel: number;
  entryPrice: number;
  takeProfitLevels: number[];
  stopLossLevel: number;
  timeframe_alignment?: TimeframeAlignmentEntry[];
}

export interface Orderbook {
  symbol: string;
  bids: [string, string][]; // [price, size]
  asks: [string, string][]; // [price, size]
  timestamp: number;
}

export interface LiquidityLevel {
    price: number;
    volume: number;
    type: 'support' | 'resistance';
}

export interface OrderbookAnalysis {
    supportLevels: LiquidityLevel[];
    resistanceLevels: LiquidityLevel[];
}


// --- Mirrored from Python Project ---
export interface MomentumIndicators {
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  macd_histogram?: number;
  stochastic_k?: number;
  stochastic_d?: number;
  williamsr?: number;
}

export interface VolumeIndicators {
  obv?: number;
  vwap?: number;
}

export interface VolatilityIndicators {
  atr?: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
  bb_width?: number;
}

export interface TrendIndicators {
  adx?: number;
  plus_di?: number;
  minus_di?: number;
  ichimoku_conversion?: number;
  ichimoku_base?: number;
  ichimoku_span_a?: number;
  ichimoku_span_b?: number;
  ichimoku_lagging?: number;
}

export interface EhlersIndicators {
  fisher_transform?: number;
  fisher_trigger?: number;
  stoch_rsi_k?: number;
  stoch_rsi_d?: number;
}

export interface IndicatorData {
  momentum?: MomentumIndicators;
  volume?: VolumeIndicators;
  volatility?: VolatilityIndicators;
  trend?: TrendIndicators;
  ehlers?: EhlersIndicators;
}
// ---------------------------------

export interface AnalysisResult {
  id: string;
  symbol: string;
  interval: string;
  analysis: Analysis;
  klines: Kline[];
  indicators: IndicatorData;
  current_price: number;
  timestamp: Date;
  confidence: number;
  meets_confidence: boolean;
  orderbook?: Orderbook;
  orderbookAnalysis?: OrderbookAnalysis;
}

// --- New Features ---
export interface PriceAlert {
  id: number;
  symbol: string;
  price: number;
  condition: 'above' | 'below';
  triggered: boolean;
}

export interface TickerData {
  price: number;
  direction: 'up' | 'down' | 'neutral';
}